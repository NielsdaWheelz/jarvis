"""Project work that the serving process can still account for."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Text, func, select

from jarvis.actions import scoped_delegation
from jarvis.db import (
    action,
    active_native_attempt,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
)
from jarvis.home_reads import conversation_token, owed_messages
from jarvis.messages import CATCHUP_SOURCE, latest_control, pending_input_order

if TYPE_CHECKING:
    from provider_runtime.agent_runtime import AgentToolUse

    from jarvis.actions import StoredAction
    from jarvis.kernel import DeferredRoute
    from jarvis.ownership import Database
    from jarvis.workspace_mcp import WorkspaceApprovals

_TRIGGERS = {
    ("owner", "web"): "you",
    ("host", "email_event"): "mail",
    ("host", "event_status"): "mail",
    ("host", "work_wake"): "todo",
    ("host", "action"): "result",
    ("host", CATCHUP_SOURCE): "recovery",
}
_ACTIVITY_FAMILIES = frozenset(
    ("gmail", "calendar", "drive", "maps", "memory", "web", "work", "agent", "receipt")
)


def _activity(tool: str) -> str:
    family = tool.partition(".")[0]
    if family == "docs":
        return "drive"
    return family if family in _ACTIVITY_FAMILIES else "other"


class Presence:
    def __init__(self, database: Database, scope: str) -> None:
        self._database, self._scope = database, scope
        self._attempt: UUID | None = None
        self._effects: dict[UUID, tuple[datetime, str]] = {}
        self._stock: dict[str, str] = {}
        self.deferral: DeferredRoute | None = None

    def arm(self, attempt: UUID) -> None:
        self._attempt = attempt
        self._stock.clear()
        self.deferral = None

    def clear_attempt(self) -> None:
        self._attempt = None
        self._stock.clear()

    def stock(self, event: AgentToolUse) -> None:
        if event.phase == "completed":
            self._stock.pop(event.tool_call_id, None)
        elif event.phase == "started":
            activity = "other"
            if event.name in {"commandExecution", "run_command"}:
                activity = "shell"
            elif event.name == "webSearch":
                activity = "web"
            self._stock[event.tool_call_id] = activity

    def enter_effect(self, stored: StoredAction) -> None:
        self._effects[stored.id] = (datetime.now(UTC), _activity(stored.tool_name))

    def leave_effect(self, identifier: UUID) -> None:
        self._effects.pop(identifier)

    async def read(
        self, approvals: WorkspaceApprovals | None
    ) -> tuple[str, dict[str, object]]:
        # The owned connection serializes every writer of these facts.
        async with self._database.connect() as connection:
            attempt = self._attempt
            effect = next(iter(self._effects.values()), None)
            stock = self._stock[next(reversed(self._stock))] if self._stock else None
            deferral = self.deferral
            google_waiting = approvals is not None and bool(approvals.pending())
            as_of = datetime.now(UTC)

            paused = await connection.scalar(latest_control(self._scope)) == "pause"
            armed_at = None
            delivered: set[UUID] = set()
            triggers: set[str] = set()
            activity = None
            mode = None
            if attempt is not None:
                armed_at = await connection.scalar(
                    select(native_attempt.c.armed_at).where(
                        native_attempt.c.id == attempt,
                        native_attempt.c.conversation_id == self._scope,
                        active_native_attempt,
                    )
                )
            if armed_at is not None:
                inputs = await connection.execute(
                    select(
                        message.c.id,
                        message.c.role,
                        message.c.source,
                        native_input_delivery.c.was_waking,
                    )
                    .join(
                        native_input_delivery,
                        message.c.id == native_input_delivery.c.message_id,
                    )
                    .where(
                        native_input_delivery.c.attempt_id == attempt,
                        native_input_delivery.c.state != "rejected",
                    )
                )
                for item in inputs:
                    delivered.add(item.id)
                    if item.was_waking and (
                        trigger := _TRIGGERS.get((item.role, item.source))
                    ):
                        triggers.add(trigger)
                invocation = (
                    await connection.execute(
                        select(
                            native_invocation.c.tool_id,
                            native_invocation.c.frozen_contract["effect"].as_string(),
                        )
                        .where(
                            native_invocation.c.attempt_id == attempt,
                            native_invocation.c.reply_recorded_at.is_(None),
                        )
                        .order_by(native_invocation.c.ordinal)
                        .limit(1)
                    )
                ).one_or_none()
                if invocation is not None:
                    tool, tool_effect = invocation
                    activity = _activity(tool)
                    mode = "write" if tool_effect == "Write" else "read"
                elif stock is not None:
                    activity, mode = stock, "read"
            if effect is not None:
                triggers.add("you")
                if armed_at is None:
                    armed_at = effect[0]
                    activity, mode = effect[1], "write"

            pending = (
                await connection.execute(
                    select(
                        message.c.id,
                        (message.c.role == "owner").label("owner"),
                        message.c.native_retry_after,
                    )
                    .where(
                        message.c.source_conversation_id == self._scope,
                        message.c.role.in_(("owner", "host")),
                        message.c.request_state == "pending",
                        message.c.control_kind.is_(None),
                        message.c.processing_parked_at.is_(None),
                        message.c.id.not_in(delivered),
                    )
                    .order_by(*pending_input_order)
                )
            ).all()
            actions = select(action.c.id).where(
                message.c.trace["waiting_action_ids"].op("?")(action.c.id.cast(Text)),
            )
            owner = (
                await connection.execute(
                    select(message.c.id, message.c.request_state)
                    .where(
                        message.c.source_conversation_id == self._scope,
                        message.c.role == "owner",
                        message.c.source == "web",
                        message.c.control_kind.is_(None),
                        message.c.processing_parked_at.is_(None),
                        (message.c.request_state == "pending")
                        | (
                            (message.c.request_state == "waiting")
                            & (message.c.wait_reason == "approval")
                            & actions.where(
                                action.c.status.in_(("queued", "executing"))
                            ).exists()
                            & ~actions.where(
                                action.c.status == "awaiting_approval"
                            ).exists()
                        ),
                    )
                    .order_by(message.c.created_at.desc(), message.c.id.desc())
                    .limit(1)
                )
            ).one_or_none()
            workers = await connection.scalar(
                select(func.count())
                .select_from(action)
                .where(
                    scoped_delegation(self._scope),
                    action.c.status == "queued",
                )
            )
            owed: list[dict[str, str | None]] = [
                {"kind": kind, "href": f"/m/{identifier}"}
                for identifier, kind in await owed_messages(connection, self._scope)
            ]
            if google_waiting:
                owed.append({"kind": "google", "href": None})
            chat = await conversation_token(connection, self._scope)

        until, reason = None, None
        state = "idle"
        retry_times = [
            item.native_retry_after
            for item in pending
            if item.native_retry_after is not None and item.native_retry_after > as_of
        ]
        if paused:
            state = "paused"
        elif armed_at is not None:
            state = "working"
        elif pending:
            if deferral is not None:
                state, until, reason = "standby", deferral.reset_at, deferral.reason
            elif len(retry_times) == len(pending):
                state, until = "retrying", min(retry_times)
            else:
                state = "queued"

        you = None
        if owner is not None:
            ahead = next(
                (index for index, item in enumerate(pending) if item.id == owner.id), 0
            )
            you_state = state
            if not paused:
                if owner.id in delivered or owner.request_state == "waiting":
                    you_state = "working"
                elif state == "working":
                    you_state = "queued"
            you = {"state": you_state, "ahead": ahead}

        owner_count = sum(item.owner for item in pending)
        return as_of.isoformat(), {
            "state": state,
            "until": until.isoformat() if until is not None else None,
            "reason": reason,
            "draining": paused and armed_at is not None,
            "work": None
            if armed_at is None
            else {
                "since": armed_at.isoformat(),
                "triggers": [
                    trigger
                    for trigger in ("you", "mail", "todo", "result", "recovery")
                    if trigger in triggers
                ],
                "activity": activity,
                "mode": mode,
            },
            "you": you,
            "queued": {"you": owner_count, "other": len(pending) - owner_count},
            "workers": workers,
            "owed": owed,
            "chat": chat,
        }

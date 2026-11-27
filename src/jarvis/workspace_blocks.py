"""Durable owner interaction for blocked Workspace operations."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Coroutine
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import Text, func, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import (
    action,
    event_cursor,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
    workspace_block,
)
from jarvis.home_notices import enqueue_notice
from jarvis.messages import append_waking_input
from jarvis.ownership import Database, lock_conversation
from jarvis.workspace_mcp import Product, WorkspaceError, WorkspaceRequest

if TYPE_CHECKING:
    from jarvis.workspace_write_models import UncertainVerification
    from jarvis.write_connectors import WorkspaceReceipt


Origin = Literal["read", "write", "verification", "source"]
_OPEN = ("waiting", "needs_owner", "checking")
_PRODUCTS = ("gmail", "calendar", "drive", "docs")
_REASONS = {
    "consent_required",
    "consent_expired",
    "approval_busy",
    "denied",
    "rate_limited",
    "temporary",
    "grant_unavailable",
    "scope_missing",
    "policy_block",
    "withheld",
    "partial",
    "screened",
    "not_found",
    "invalid_response",
    "unsupported",
    "uncertain",
    "precondition_failed",
    "source_changed",
    "exhausted",
    "target_observed",
    "target_differs",
    "label_still_present",
}
_LOCAL_INTERRUPTION = {
    "cancelled",
    "not_admitted",
    "workspace_input_changed",
    "workspace_read_not_authorized",
    "workspace_read_outside_invocation",
}
# A verification request reuses its accepted action lineage without becoming a write.
verifying_workspace: ContextVar[UUID | None] = ContextVar(
    "verifying_workspace", default=None
)
_PUBLIC_OPERATIONS = {
    "calendar.list_calendars": "list_calendars",
    "calendar.list_events": "list_events",
    "calendar.read_event": "get_event",
    "docs.read": "get_document",
    "gmail.read_message": "get_message",
    "gmail.read_thread": "get_thread",
    "gmail.search": "search_threads",
}
_RESUME = "workspace_resume"


def _classification(
    reason: str, *, now: datetime, retry_at: datetime | None
) -> tuple[str, str, datetime | None]:
    if reason in {"grant_unavailable", "scope_missing"}:
        return "needs_owner", "reconnect", None
    if reason in {"consent_required", "consent_expired"}:
        return "needs_owner", "answer_google", None
    if reason in {"denied", "policy_block"}:
        return "denied", "none", None
    if reason in {"source_changed", "precondition_failed"}:
        return "superseded", "none", None
    if reason == "approval_busy":
        return "waiting", "wait", now
    if reason in {"rate_limited", "temporary"}:
        return "waiting", "wait", max(retry_at or now, now + timedelta(minutes=1))
    if reason in {"uncertain", "label_still_present"}:
        return "needs_owner", "verify", None
    return "denied", "none", None


class WorkspaceBlocks:
    def __init__(self, database: Database, scope: str) -> None:
        self._database = database
        self._scope = scope
        self.notify_work: Callable[[], None] = lambda: None
        self.notify_delivery: Callable[[], None] = lambda: None
        self.notify_source: Callable[[], None] = lambda: None
        self.approval_busy: Callable[[], bool] = lambda: False
        self.is_live_round: Callable[[str], bool] = lambda _: False
        self.verify_action: (
            Callable[[UUID, bool], Awaitable[WorkspaceReceipt | UncertainVerification]]
            | None
        ) = None
        self.current_grant: Callable[[], UUID | None] | None = None

    async def observe(
        self,
        error: WorkspaceError,
        *,
        invocation_id: UUID,
        action_id: UUID | None = None,
        verification: bool = False,
        tool_id: str | None = None,
        verification_available: bool = True,
    ) -> None:
        request = error.request
        if error.kind in _LOCAL_INTERRUPTION:
            return
        reason = {
            "document_write_rejected": "denied",
            "raw_unavailable": "partial",
            "unsupported_part": "partial",
            "too_large": "partial",
        }.get(error.kind, error.kind)
        if request is None and reason not in _REASONS:
            return
        if request is None:
            if tool_id is None:
                return
            family, _, name = tool_id.partition(".")
            if family not in _PRODUCTS:
                return
            product = family
            operation = _PUBLIC_OPERATIONS.get(tool_id, name)
            key = hashlib.sha256(f"{self._scope}:{invocation_id}".encode()).hexdigest()
            grant_id = None
        else:
            product, operation, key, grant_id = (
                request.product,
                request.operation,
                request.target_key,
                request.grant_id,
            )
        async with self._database.begin() as conn:
            await lock_conversation(conn, self._scope)
            if request is None and reason == "uncertain" and action_id is not None:
                existing = await conn.scalar(
                    select(workspace_block.c.id)
                    .where(
                        workspace_block.c.origin_kind == "verification",
                        workspace_block.c.origin_id == action_id,
                        workspace_block.c.reason == reason,
                    )
                    .limit(1)
                )
                if existing is not None:
                    return
            origin, origin_id, ref = await self.invocation_origin(
                conn,
                invocation_id,
                action_id=action_id,
                verification=verification or reason == "uncertain",
            )
            if origin == "read":
                retry = await self._retried_read(
                    conn, invocation_id, product, operation, key, grant_id
                )
                if retry is not None:
                    origin_id = retry["origin_id"]
                    ref = retry["operation_ref"]
                    if reason in {"approval_busy", "temporary", "rate_limited"}:
                        attempts = await conn.scalar(
                            select(func.count())
                            .select_from(message)
                            .where(
                                message.c.source == "workspace_retry",
                                message.c.source_message_id.like(
                                    str(retry["id"]) + ":%"
                                ),
                            )
                        )
                        if attempts is not None and attempts >= 5:
                            reason = "exhausted"
            await self.record(
                conn,
                origin=origin,
                origin_id=origin_id,
                ref=ref,
                product=product,
                operation=operation,
                key=key,
                grant_id=grant_id,
                reason=reason,
                retry_at=error.retry_at,
                verification_available=verification_available,
            )
        self.notify_delivery()
        self.notify_work()

    async def _retried_read(
        self,
        conn: AsyncConnection,
        invocation_id: UUID,
        product: Product,
        operation: str,
        key: str,
        grant_id: UUID | None,
    ) -> RowMapping | None:
        retry = (
            (
                await conn.execute(
                    select(workspace_block)
                    .join(
                        message,
                        message.c.source_message_id.startswith(
                            workspace_block.c.id.cast(Text) + ":"
                        ),
                    )
                    .join(
                        native_input_delivery,
                        native_input_delivery.c.message_id == message.c.id,
                    )
                    .join(
                        native_invocation,
                        native_invocation.c.attempt_id
                        == native_input_delivery.c.attempt_id,
                    )
                    .where(
                        native_invocation.c.id == invocation_id,
                        native_invocation.c.proposal["input_ids"].has_key(
                            message.c.id.cast(Text)
                        ),
                        proven_native_delivery,
                        message.c.source == "workspace_retry",
                        message.c.source_conversation_id == self._scope,
                        workspace_block.c.origin_kind == "read",
                        workspace_block.c.product == product,
                        workspace_block.c.operation == operation,
                        workspace_block.c.target_key == key,
                        workspace_block.c.grant_id.is_not_distinct_from(grant_id),
                        workspace_block.c.state == "checking",
                    )
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        return retry

    async def invocation_origin(
        self,
        conn: AsyncConnection,
        invocation_id: UUID,
        *,
        action_id: UUID | None = None,
        verification: bool = False,
    ) -> tuple[Origin, UUID, dict[str, object]]:
        row = (
            await conn.execute(
                select(
                    native_invocation.c.attempt_id,
                    native_invocation.c.action_id,
                    native_invocation.c.proposal,
                )
                .join(native_attempt)
                .where(
                    native_invocation.c.id == invocation_id,
                    native_invocation.c.validation == "accepted",
                    native_attempt.c.conversation_id == self._scope,
                )
            )
        ).one()
        action_id = action_id or row.action_id
        if action_id is not None:
            origin = "verification" if verification else "write"
            return (
                origin,
                action_id,
                {
                    "action_id": str(action_id),
                    "invocation_id": str(invocation_id),
                    "stage": origin,
                },
            )
        delivered = (
            await conn.execute(
                select(message.c.source, message.c.source_message_id)
                .join(
                    native_input_delivery,
                    native_input_delivery.c.message_id == message.c.id,
                )
                .where(
                    native_input_delivery.c.attempt_id == row.attempt_id,
                    message.c.id.in_(
                        [UUID(value) for value in row.proposal["input_ids"]]
                    ),
                    proven_native_delivery,
                    native_input_delivery.c.was_waking,
                )
                .order_by(native_input_delivery.c.ordinal)
                .limit(2)
            )
        ).all()
        wake_id = invocation_id
        if len(delivered) == 1:
            source, source_id = delivered[0]
            if source == "work_wake" and source_id:
                wake_id = UUID(source_id.split(":", 1)[0])
        return "read", wake_id, {"invocation_id": str(invocation_id)}

    async def record(
        self,
        conn: AsyncConnection,
        *,
        origin: Origin,
        origin_id: UUID,
        ref: dict[str, object],
        product: Product,
        operation: str,
        key: str,
        grant_id: UUID | None,
        reason: str,
        retry_at: datetime | None = None,
        verification_available: bool = True,
    ) -> UUID:
        """Upsert one operation within the owning conversation transaction."""
        reason = reason if reason in _REASONS else "invalid_response"
        now = datetime.now(UTC)
        state, remedy, due = _classification(reason, now=now, retry_at=retry_at)
        if reason == "uncertain" and not verification_available:
            state, remedy = "superseded", "none"
        previous = (
            (
                await conn.execute(
                    select(workspace_block)
                    .where(
                        workspace_block.c.origin_kind == origin,
                        workspace_block.c.origin_id == origin_id,
                        workspace_block.c.product == product,
                        workspace_block.c.operation == operation,
                        workspace_block.c.target_key == key,
                    )
                    .order_by(workspace_block.c.updated_at.desc())
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous is not None:
            prior_ref = {
                k: v
                for k, v in previous["operation_ref"].items()
                if k not in {"round_id", "claim_id"}
            }
            same_ref = prior_ref == {
                k: v for k, v in ref.items() if k not in {"round_id", "claim_id"}
            }
            if previous["state"] not in _OPEN:
                if previous["reason"] == reason and same_ref:
                    return cast(UUID, previous["id"])
                previous = None
            elif reason in {"approval_busy", "consent_required"} and same_ref:
                claim_id = previous["operation_ref"].get("claim_id")
                if claim_id is not None:
                    ref = ref | {"claim_id": claim_id}
        if (
            previous is not None
            and previous["state"] == state
            and previous["reason"] == reason
            and previous["operation_ref"] == ref
            and (due is None or due <= (previous["retry_at"] or now))
        ):
            return cast(UUID, previous["id"])
        identifier = uuid4() if previous is None else cast(UUID, previous["id"])
        anchor = (
            None if previous is None else cast(UUID | None, previous["notice_anchor"])
        )
        enqueue = False
        if state == "needs_owner" and anchor is None:
            if remedy == "reconnect" and grant_id is not None:
                anchor = await conn.scalar(
                    select(workspace_block.c.notice_anchor)
                    .where(
                        workspace_block.c.grant_id == grant_id,
                        workspace_block.c.product == product,
                        workspace_block.c.remedy == remedy,
                        workspace_block.c.state.in_(_OPEN),
                        workspace_block.c.notice_anchor.is_not(None),
                    )
                    .order_by(workspace_block.c.updated_at.desc())
                    .limit(1)
                )
            if anchor is None:
                anchor = identifier
                enqueue = True
        values = dict(
            reason=reason,
            state=state,
            remedy=remedy,
            retry_at=due,
            operation_ref=ref,
            notice_anchor=anchor,
            updated_at=now,
        )
        if previous is None:
            body = (
                "gmail hit a problem checking for new mail."
                if origin == "source"
                else f"{product} operation blocked."
            )
            if origin == "verification":
                accepted = (
                    await conn.execute(
                        select(
                            action.c.tool_name,
                            action.c.status,
                            action.c.result["type"].as_string(),
                        ).where(action.c.id == origin_id)
                    )
                ).one_or_none()
                if accepted is not None and (
                    accepted[1] == "succeeded" or accepted[2] == "workspace_ack_v1"
                ):
                    body = (
                        "the draft was created. google blocked verification."
                        if accepted[0] == "gmail.create_draft"
                        else f"{product} accepted the change. verification is blocked."
                    )
                else:
                    body = f"{product} could not confirm the original change."
            await conn.execute(
                insert(message).values(
                    id=identifier,
                    role="host",
                    text=body,
                    source="workspace_block",
                    source_conversation_id=self._scope,
                    source_message_id=str(identifier),
                    created_at=now,
                    processed_at=now,
                )
            )
            await conn.execute(
                insert(workspace_block).values(
                    **values,
                    id=identifier,
                    origin_kind=origin,
                    origin_id=origin_id,
                    product=product,
                    operation=operation,
                    target_key=key,
                    grant_id=grant_id,
                )
            )
        else:
            await conn.execute(
                update(workspace_block)
                .where(workspace_block.c.id == identifier)
                .values(**values, revision=workspace_block.c.revision + 1)
            )
        if enqueue:
            await enqueue_notice(conn, identifier, kind="question")
        return identifier

    async def resume(self, identifier: UUID, revision: int, submission: UUID) -> int:
        async with self._database.begin() as conn:
            await lock_conversation(conn, self._scope)
            replay = (
                await conn.execute(
                    select(
                        message.c.source_conversation_id,
                        message.c.home,
                        message.c.trace,
                    ).where(
                        message.c.source == "web",
                        message.c.source_message_id == str(submission),
                    )
                )
            ).one_or_none()
            if replay is not None:
                return (
                    202
                    if (
                        replay.source_conversation_id == self._scope
                        and replay.home is not None
                        and replay.home.get("request_sha256") == _RESUME
                        and replay.trace.get("block_id") == str(identifier)
                        and replay.trace.get("revision") == revision
                    )
                    else 409
                )
            block = (
                (
                    await conn.execute(
                        select(workspace_block)
                        .join(message, message.c.id == workspace_block.c.id)
                        .where(
                            workspace_block.c.id == identifier,
                            message.c.source_conversation_id == self._scope,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if block is None or block["state"] not in _OPEN:
                return 410
            if block["state"] != "needs_owner" or block["revision"] != revision:
                return 409
            current = self.current_grant() if self.current_grant is not None else None
            if self.current_grant is not None and block["grant_id"] is not None:
                if current is None and block["remedy"] == "reconnect":
                    return 409
                if current != block["grant_id"]:
                    if current is not None:
                        await self._close_replaced_grants(conn, current)
                    else:
                        await self._set_state(conn, identifier, "superseded")
                    return 410
            round_id = block["operation_ref"].get("round_id")
            if round_id is not None and self.is_live_round(round_id):
                # The open provider choice is the action. Never replay its call.
                return 409
            now = datetime.now(UTC)
            claim_id = uuid4()
            if not await self._claim(conn, block, now, claim_id):
                return 410
            if block["remedy"] == "reconnect" and block["notice_anchor"] is not None:
                siblings = (
                    await conn.execute(
                        select(workspace_block).where(
                            workspace_block.c.id != identifier,
                            workspace_block.c.notice_anchor == block["notice_anchor"],
                            workspace_block.c.remedy == "reconnect",
                            workspace_block.c.state == "needs_owner",
                        )
                    )
                ).mappings()
                for sibling in siblings:
                    await self._claim(conn, sibling, now, claim_id)
            await conn.execute(
                insert(message).values(
                    id=claim_id,
                    role="host",
                    text="google workspace resume requested.",
                    source="web",
                    source_conversation_id=self._scope,
                    source_message_id=str(submission),
                    created_at=now,
                    processed_at=now,
                    home={"request_sha256": _RESUME},
                    trace={
                        "block_id": str(identifier),
                        "revision": revision,
                        "operation_ref": block["operation_ref"],
                    },
                )
            )
        self.notify_work()
        self.notify_source()
        return 202

    async def _close_replaced_grants(
        self, conn: AsyncConnection, current: UUID
    ) -> None:
        await conn.execute(
            update(workspace_block)
            .where(
                workspace_block.c.id.in_(
                    select(message.c.id).where(
                        message.c.source_conversation_id == self._scope
                    )
                ),
                workspace_block.c.grant_id.is_not(None),
                workspace_block.c.grant_id != current,
                workspace_block.c.state.in_(_OPEN),
            )
            .values(
                state="superseded",
                reason="source_changed",
                remedy="none",
                retry_at=None,
                updated_at=datetime.now(UTC),
                revision=workspace_block.c.revision + 1,
            )
        )

    async def _claim(
        self,
        conn: AsyncConnection,
        block: RowMapping,
        now: datetime,
        claim_id: UUID | None,
    ) -> bool:
        ref = {
            k: v
            for k, v in block["operation_ref"].items()
            if k not in {"round_id", "claim_id"}
        }
        if block["origin_kind"] == "source":
            run = await conn.execute(
                update(event_cursor)
                .where(
                    event_cursor.c.account_id == ref["account"],
                    event_cursor.c.enabled,
                    event_cursor.c.progress["label_id"].as_string() == ref["label_id"],
                    event_cursor.c.progress["grant_id"].as_string()
                    == str(block["grant_id"]),
                    event_cursor.c.error["episode_id"].as_string()
                    == str(block["origin_id"]),
                )
                .values(next_poll_at=now)
            )
            if run.rowcount != 1:
                await self._set_state(conn, block["id"], "superseded")
                return False
        await conn.execute(
            update(workspace_block)
            .where(workspace_block.c.id == block["id"])
            .values(
                state="checking",
                retry_at=now,
                updated_at=now,
                operation_ref=ref
                if claim_id is None
                else ref | {"claim_id": str(claim_id)},
                revision=workspace_block.c.revision + 1,
            )
        )
        return True

    async def _set_state(
        self,
        conn: AsyncConnection,
        identifier: UUID,
        state: str,
        *,
        retry_at: datetime | None = None,
        reason: str | None = None,
        remedy: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "state": state,
            "retry_at": retry_at,
            "updated_at": datetime.now(UTC),
            "revision": workspace_block.c.revision + 1,
        }
        if reason is not None:
            values["reason"] = reason
        if state in {"resolved", "superseded", "denied"}:
            values["remedy"] = "none"
        elif remedy is not None:
            values["remedy"] = remedy
        await conn.execute(
            update(workspace_block)
            .where(workspace_block.c.id == identifier)
            .values(**values)
        )

    async def source_attended(
        self,
        conn: AsyncConnection,
        episode: UUID,
        operation: str,
        key: str,
        account: str,
        progress: dict[str, object],
    ) -> bool:
        return (
            await conn.scalar(
                select(workspace_block.c.id)
                .join(message, message.c.id == workspace_block.c.id)
                .where(
                    message.c.source_conversation_id == self._scope,
                    workspace_block.c.origin_kind == "source",
                    workspace_block.c.origin_id == episode,
                    workspace_block.c.operation == operation,
                    workspace_block.c.target_key == key,
                    (
                        (workspace_block.c.state == "checking")
                        | (
                            (workspace_block.c.state == "waiting")
                            & (workspace_block.c.reason == "approval_busy")
                        )
                    ),
                    workspace_block.c.grant_id == UUID(str(progress["grant_id"])),
                    select(message.c.id)
                    .where(
                        message.c.id.cast(Text)
                        == workspace_block.c.operation_ref["claim_id"].as_string(),
                        message.c.source == "web",
                        message.c.role == "host",
                        message.c.home["request_sha256"].as_string() == _RESUME,
                        message.c.source_conversation_id == self._scope,
                    )
                    .correlate(workspace_block)
                    .exists(),
                    workspace_block.c.operation_ref["account"].as_string() == account,
                    workspace_block.c.operation_ref["label_id"].as_string()
                    == progress["label_id"],
                )
            )
            is not None
        )

    async def source_denied(
        self, conn: AsyncConnection, episode: UUID, operation: str, key: str
    ) -> bool:
        return (
            await conn.scalar(
                select(workspace_block.c.id)
                .where(
                    workspace_block.c.origin_kind == "source",
                    workspace_block.c.origin_id == episode,
                    workspace_block.c.operation == operation,
                    workspace_block.c.target_key == key,
                    workspace_block.c.state == "denied",
                    workspace_block.c.reason == "denied",
                )
                .limit(1)
            )
            is not None
        )

    async def source_unblocked(self, conn: AsyncConnection, episode: UUID) -> bool:
        return (
            await conn.scalar(
                select(workspace_block.c.id)
                .where(
                    workspace_block.c.origin_kind == "source",
                    workspace_block.c.origin_id == episode,
                    workspace_block.c.state == "waiting",
                    workspace_block.c.reason == "approval_busy",
                )
                .limit(1)
            )
            is not None
        )

    async def source_complete(
        self, conn: AsyncConnection, episode: UUID, remaining: set[UUID]
    ) -> None:
        await conn.execute(
            update(workspace_block)
            .where(
                workspace_block.c.origin_kind == "source",
                workspace_block.c.origin_id == episode,
                workspace_block.c.state.in_(_OPEN),
                workspace_block.c.id.not_in(remaining),
            )
            .values(
                state="resolved",
                remedy="none",
                retry_at=None,
                updated_at=datetime.now(UTC),
                revision=workspace_block.c.revision + 1,
            )
        )

    def wake_released(self) -> None:
        self.notify_work()
        self.notify_source()

    async def provider_success(self, request: WorkspaceRequest, invoking: str) -> None:
        if request.arrival_episode is not None:
            return
        admitted = False
        async with self._database.begin() as conn:
            await lock_conversation(conn, self._scope)
            if (
                self.current_grant is not None
                and self.current_grant() != request.grant_id
            ):
                return
            invocation_id = UUID(invoking)
            inv = (
                await conn.execute(
                    select(native_invocation.c.attempt_id, native_invocation.c.proposal)
                    .join(native_attempt)
                    .where(
                        native_invocation.c.id == invocation_id,
                        native_attempt.c.conversation_id == self._scope,
                    )
                )
            ).one_or_none()
            if inv is None:
                return
            retry_sources = (
                await conn.execute(
                    select(message.c.source_message_id)
                    .join(
                        native_input_delivery,
                        native_input_delivery.c.message_id == message.c.id,
                    )
                    .where(
                        native_input_delivery.c.attempt_id == inv.attempt_id,
                        message.c.id.in_(
                            [UUID(value) for value in inv.proposal["input_ids"]]
                        ),
                        proven_native_delivery,
                        message.c.source == "workspace_retry",
                    )
                )
            ).scalars()
            ids = [UUID(source.split(":", 1)[0]) for source in retry_sources if source]
            form_only = workspace_block.c.origin_kind != "verification"
            verifying = verifying_workspace.get()
            if verifying is not None:
                form_only = form_only | (
                    (workspace_block.c.id != verifying)
                    & (workspace_block.c.reason == "consent_required")
                    & workspace_block.c.operation_ref["round_id"]
                    .as_string()
                    .is_not(None)
                )
            await conn.execute(
                update(workspace_block)
                .where(
                    workspace_block.c.product == request.product,
                    workspace_block.c.operation == request.operation,
                    workspace_block.c.target_key == request.target_key,
                    workspace_block.c.grant_id == request.grant_id,
                    workspace_block.c.state.in_(_OPEN),
                    form_only,
                    (
                        workspace_block.c.operation_ref["invocation_id"].as_string()
                        == invoking
                    )
                    | workspace_block.c.id.in_(ids),
                )
                .values(
                    state="resolved",
                    remedy="none",
                    retry_at=None,
                    updated_at=datetime.now(UTC),
                    revision=workspace_block.c.revision + 1,
                )
            )

            reconnects = (
                await conn.execute(
                    select(workspace_block)
                    .join(message, message.c.id == workspace_block.c.id)
                    .where(
                        message.c.source_conversation_id == self._scope,
                        workspace_block.c.product == request.product,
                        workspace_block.c.grant_id == request.grant_id,
                        workspace_block.c.state == "needs_owner",
                        workspace_block.c.remedy == "reconnect",
                        (
                            (workspace_block.c.reason == "grant_unavailable")
                            | (
                                (workspace_block.c.reason == "scope_missing")
                                & (workspace_block.c.operation == request.operation)
                            )
                        ),
                    )
                )
            ).mappings()
            for block in reconnects:
                admitted = (
                    await self._claim(conn, block, datetime.now(UTC), None) or admitted
                )
        if admitted:
            self.notify_work()
            self.notify_source()

    async def expire_interrupted_forms(self) -> None:
        """A restored form has no provider token or owner choice to apply."""
        async with self._database.begin() as conn:
            await lock_conversation(conn, self._scope)
            await conn.execute(
                update(workspace_block)
                .where(
                    workspace_block.c.id.in_(
                        select(message.c.id).where(
                            message.c.source_conversation_id == self._scope
                        )
                    ),
                    workspace_block.c.operation_ref["round_id"]
                    .as_string()
                    .is_not(None),
                    workspace_block.c.state.in_(_OPEN),
                )
                .values(
                    state="needs_owner",
                    reason="consent_expired",
                    remedy="answer_google",
                    retry_at=None,
                    operation_ref=workspace_block.c.operation_ref.op("-")("round_id"),
                    updated_at=datetime.now(UTC),
                    revision=workspace_block.c.revision + 1,
                )
            )

    async def effect_succeeded(self, action_id: UUID) -> None:
        async with self._database.begin() as conn:
            await lock_conversation(conn, self._scope)
            await conn.execute(
                update(workspace_block)
                .where(
                    workspace_block.c.origin_kind == "write",
                    workspace_block.c.origin_id == action_id,
                    workspace_block.c.state.in_(_OPEN),
                )
                .values(
                    state="resolved",
                    remedy="none",
                    retry_at=None,
                    updated_at=datetime.now(UTC),
                    revision=workspace_block.c.revision + 1,
                )
            )

    async def run_due(
        self, *, verification_available: bool = True
    ) -> tuple[datetime | None, Callable[[], Coroutine[object, object, None]] | None]:
        """Advance ordinary retries and select at most one original-effect read."""
        now = datetime.now(UTC)
        verification: RowMapping | None = None
        next_retry = None
        async with self._database.begin() as conn:
            await lock_conversation(conn, self._scope)
            current = self.current_grant() if self.current_grant is not None else None
            if current is not None:
                await self._close_replaced_grants(conn, current)
            await conn.execute(
                update(workspace_block)
                .where(
                    workspace_block.c.state == "checking",
                    workspace_block.c.retry_at.is_(None),
                    select(message.c.id)
                    .where(
                        message.c.source == "workspace_retry",
                        message.c.source_conversation_id == self._scope,
                        message.c.source_message_id
                        == (
                            workspace_block.c.id.cast(Text)
                            + ":"
                            + (workspace_block.c.revision - 1).cast(Text)
                        ),
                        message.c.request_state.in_(("completed", "stopped")),
                    )
                    .exists(),
                )
                .values(
                    state="superseded",
                    remedy="none",
                    updated_at=now,
                    revision=workspace_block.c.revision + 1,
                )
            )
            await conn.execute(
                update(workspace_block)
                .where(
                    workspace_block.c.state == "checking",
                    workspace_block.c.origin_kind != "source",
                    workspace_block.c.retry_at.is_(None),
                    workspace_block.c.operation_ref["round_id"]
                    .as_string()
                    .is_not(None),
                    select(native_invocation.c.id)
                    .join(native_attempt)
                    .where(
                        native_invocation.c.id.cast(Text)
                        == workspace_block.c.operation_ref["invocation_id"].as_string(),
                        native_attempt.c.conversation_id == self._scope,
                        native_attempt.c.product_outcome.is_not(None)
                        | native_attempt.c.fenced_at.is_not(None),
                    )
                    .correlate(workspace_block)
                    .exists(),
                )
                .values(
                    state="superseded",
                    remedy="none",
                    updated_at=now,
                    revision=workspace_block.c.revision + 1,
                )
            )
            candidates = (
                await conn.execute(
                    select(workspace_block)
                    .join(message, message.c.id == workspace_block.c.id)
                    .where(
                        message.c.source_conversation_id == self._scope,
                        workspace_block.c.origin_kind != "source",
                        workspace_block.c.state.in_(("waiting", "checking")),
                        workspace_block.c.retry_at.is_not(None),
                    )
                    .order_by(workspace_block.c.retry_at, workspace_block.c.id)
                )
            ).mappings()
            for block in candidates:
                if block["reason"] == "approval_busy" and self.approval_busy():
                    continue
                is_verification = block["origin_kind"] == "verification"
                if is_verification and (
                    not verification_available or verification is not None
                ):
                    continue
                if block["retry_at"] > now:
                    next_retry = cast(datetime, block["retry_at"])
                    break
                if (
                    block["origin_kind"] == "verification"
                    and self.verify_action is not None
                ):
                    verification = block
                else:
                    await self._wake_origin(conn, block, now)
        return next_retry, partial(
            self._verify, verification
        ) if verification is not None else None

    async def _verify(self, block: RowMapping) -> None:
        assert self.verify_action is not None
        ref = block["operation_ref"]
        action_id = UUID(ref["action_id"])
        marker = verifying_workspace.set(block["id"])
        try:
            claim = ref.get("claim_id")
            error = None
            try:
                confirmed = await self.verify_action(action_id, claim is not None)
            except WorkspaceError as exc:
                confirmed = None
                error = exc
            async with self._database.begin() as conn:
                await lock_conversation(conn, self._scope)
                granted = block["grant_id"]
                if (
                    granted is None
                    and confirmed is not None
                    and not isinstance(confirmed, str)
                ):
                    granted = confirmed.grant_id
                current = (
                    self.current_grant() if self.current_grant is not None else granted
                )
                if current is not None and granted is not None and current != granted:
                    await self._close_replaced_grants(conn, current)

                owned = workspace_block.c.revision == block["revision"]
                interrupted = (
                    error is not None
                    and error.kind in _LOCAL_INTERRUPTION | {"consent_expired"}
                )
                if claim is not None:
                    # Provider consent advances the same claim's revision.
                    form_updated = (
                        workspace_block.c.reason == "consent_required"
                    ) & workspace_block.c.operation_ref["round_id"].as_string().is_not(
                        None
                    )
                    if interrupted:
                        form_updated = form_updated | (
                            (workspace_block.c.state == "needs_owner")
                            & (workspace_block.c.reason == "consent_expired")
                        )
                    owned = (
                        workspace_block.c.operation_ref["claim_id"].as_string() == claim
                    ) & (owned | form_updated)
                states = _OPEN if error is not None else ("waiting", "checking")
                if (
                    await conn.scalar(
                        select(workspace_block.c.id).where(
                            workspace_block.c.id == block["id"],
                            workspace_block.c.state.in_(states),
                            owned,
                        )
                    )
                    is None
                ):
                    return

                if interrupted:
                    # The original verification owns the next attempt. The
                    # expired provider form remains visible as dated evidence.
                    await conn.execute(
                        update(workspace_block)
                        .where(
                            workspace_block.c.id != block["id"],
                            workspace_block.c.origin_kind == "verification",
                            workspace_block.c.origin_id == action_id,
                            workspace_block.c.operation_ref["invocation_id"].as_string()
                            == ref["invocation_id"],
                            workspace_block.c.state == "needs_owner",
                            workspace_block.c.reason == "consent_expired",
                        )
                        .values(
                            state="superseded",
                            remedy="none",
                            retry_at=None,
                            updated_at=datetime.now(UTC),
                            revision=workspace_block.c.revision + 1,
                        )
                    )
                if error is not None and error.kind in _LOCAL_INTERRUPTION:
                    await self._set_state(
                        conn,
                        block["id"],
                        "needs_owner",
                        reason=block["reason"],
                        remedy=block["remedy"],
                    )
                    return
                if error is not None:
                    await self.record(
                        conn,
                        origin="verification",
                        origin_id=action_id,
                        ref=ref,
                        product=cast(Product, block["product"]),
                        operation=block["operation"],
                        key=block["target_key"],
                        grant_id=block["grant_id"],
                        reason=error.kind
                        if error.kind in _REASONS
                        else "invalid_response",
                        retry_at=error.retry_at,
                    )
                else:
                    assert confirmed is not None
                    receipt = None
                    if granted is not None and current != granted:
                        state, reason = "superseded", "source_changed"
                    elif isinstance(confirmed, str):
                        state = "superseded"
                        reason = (
                            confirmed
                            if confirmed in {"target_observed", "target_differs"}
                            else "uncertain"
                        )
                    elif (
                        confirmed.action_id != action_id
                        or confirmed.grant_id != granted
                    ):
                        state, reason = "denied", "invalid_response"
                    elif confirmed.verification != "verified":
                        state = "denied"
                        reason = (
                            confirmed.reason
                            if confirmed.reason in _REASONS
                            else "invalid_response"
                        )
                    else:
                        state, reason = "resolved", "target_observed"
                        receipt = confirmed.model_dump(mode="json")
                    await conn.execute(
                        update(workspace_block)
                        .where(workspace_block.c.id == block["id"])
                        .values(
                            state=state,
                            reason=reason,
                            remedy="none",
                            retry_at=None,
                            verified_receipt=receipt,
                            updated_at=datetime.now(UTC),
                            revision=workspace_block.c.revision + 1,
                        )
                    )
        finally:
            verifying_workspace.reset(marker)
        self.notify_delivery()

    async def _wake_origin(
        self, conn: AsyncConnection, block: RowMapping, now: datetime
    ) -> None:
        ref = block["operation_ref"]
        invocation_id = UUID(ref["invocation_id"])
        candidates = (
            (
                await conn.execute(
                    select(message.c.id)
                    .join(
                        native_input_delivery,
                        native_input_delivery.c.message_id == message.c.id,
                    )
                    .join(
                        native_invocation,
                        native_invocation.c.attempt_id
                        == native_input_delivery.c.attempt_id,
                    )
                    .where(
                        native_invocation.c.id == invocation_id,
                        native_invocation.c.proposal["input_ids"].has_key(
                            message.c.id.cast(Text)
                        ),
                        proven_native_delivery,
                        message.c.source_conversation_id == self._scope,
                        message.c.processing_parked_at.is_(None),
                        message.c.request_state.in_(("pending", "waiting")),
                        message.c.control_kind.is_(None),
                    )
                    .order_by(native_input_delivery.c.ordinal)
                )
            )
            .scalars()
            .all()
        )
        if not candidates:
            await self._set_state(conn, block["id"], "superseded")
            return
        info = (
            f"google workspace retry for {block['product']} {block['operation']}. "
            f"block {block['id']}. original invocation {invocation_id}. "
            "unfinished inputs " + ", ".join(str(i) for i in candidates) + "."
        )
        action_id = ref.get("action_id")
        if action_id is not None:
            effect = (
                await conn.execute(
                    select(action.c.status, action.c.attempts).where(
                        action.c.id == UUID(action_id)
                    )
                )
            ).one_or_none()
            if effect is None:
                await self._set_state(
                    conn, block["id"], "superseded", reason="uncertain"
                )
                return
            if effect.status == "succeeded":
                await self._set_state(conn, block["id"], "resolved")
                return
            if effect.status in {"executing", "uncertain"} and effect.attempts:
                await self.record(
                    conn,
                    origin="verification",
                    origin_id=UUID(action_id),
                    ref=ref | {"stage": "verification"},
                    product=block["product"],
                    operation=block["operation"],
                    key=block["target_key"],
                    grant_id=block["grant_id"],
                    reason="uncertain",
                )
                await self._set_state(conn, block["id"], "superseded")
                self.notify_delivery()
                return
            info += (
                f" original action {action_id} is {effect.status}. "
                "use the original result before deciding whether new work is needed."
            )
        await append_waking_input(
            conn,
            role="host",
            text=info,
            source="workspace_retry",
            source_conversation_id=self._scope,
            source_message_id=f"{block['id']}:{block['revision']}",
            created_at=now,
            parent_request_id=candidates[0] if len(candidates) == 1 else None,
        )
        await self._set_state(
            conn, block["id"], "superseded" if action_id is not None else "checking"
        )

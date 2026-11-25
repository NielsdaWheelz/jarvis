"""Native Workspace authority comes from the current delivered input and grant."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from typing import cast as type_cast
from uuid import UUID
from zoneinfo import ZoneInfo

from llm_agent_kernel import NativeDispatchLineage
from llm_tools import InvocationPosition, ToolId, canonical_json_bytes
from sqlalchemy import String, case, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.admission import JarvisOwner
from jarvis.db import (
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
    work,
)
from jarvis.messages import latest_control
from jarvis.ownership import lock_conversation
from jarvis.workspace_checks import (
    CheckRead,
    WorkspaceOccurrence,
    completed_workspace_reads,
)
from jarvis.workspace_enrollment import WorkspaceEnrollment
from jarvis.workspace_mcp import WorkspaceError
from jarvis.workspace_reads import Token, WorkspaceReadAccess

# Scope-bearing wire selectors. The adapter owns parsing, presentation and paging.
_READ_CALLS: dict[str, tuple[str, dict[str, str]]] = {
    "gmail.search": ("search_threads", {"query": "query"}),
    "gmail.read_thread": ("get_thread", {"threadId": "thread_id"}),
    "gmail.get_message": ("get_message", {"messageId": "message_id"}),
    "gmail.list_drafts": ("list_drafts", {"query": "query"}),
    "gmail.get_draft": ("get_draft", {"draftId": "draft_id"}),
    "calendar.list_calendars": ("list_calendars", {}),
    "calendar.list_events": (
        "list_events",
        {"calendarId": "calendar_id", "startTime": "time_min", "endTime": "time_max"},
    ),
    "calendar.get_event": (
        "get_event",
        {"calendarId": "calendar_id", "eventId": "event_id"},
    ),
}
WORKSPACE_READ_IDS = frozenset(map(ToolId, _READ_CALLS))
_access = ContextVar[WorkspaceReadAccess | None]("workspace_read", default=None)


@dataclass(frozen=True, slots=True)
class NativeWorkspaceRead(WorkspaceReadAccess):
    grant_id: UUID
    source_digest: str
    require_current: Callable[[AsyncConnection | None], Awaitable[None]]


def current_workspace_read() -> WorkspaceReadAccess:
    access = _access.get()
    if access is None:
        raise WorkspaceError("workspace_read_not_authorized")
    return access


def native_read_at(position: InvocationPosition) -> NativeWorkspaceRead | None:
    access = _access.get()
    if (
        isinstance(access, NativeWorkspaceRead)
        and str(position) == "native-invocation:" + access.invocation_id
    ):
        return access
    return None


@contextmanager
def bind_workspace_read(access: WorkspaceReadAccess) -> Iterator[None]:
    token = _access.set(access)
    try:
        yield
    finally:
        _access.reset(token)


def is_workspace_wake(source: str, text: str) -> bool:
    return (
        source == "work_wake"
        and json.loads(text)["record"].get("workspace_check") is not None
    )


async def check_observations(
    connection: AsyncConnection,
    attempt_id: UUID,
    occurrence: WorkspaceOccurrence,
    *,
    input_ids: tuple[str, ...] | None = None,
) -> list[CheckRead]:
    """Read accepted replies at their original, completed callback positions."""
    rows = await connection.execute(
        completed_workspace_reads(
            attempt_id,
            occurrence.check.grant_id,
            input_ids or (str(occurrence.occurrence_id),),
        )
        .where(native_invocation.c.reply_recorded_at >= occurrence.due_at)
        .order_by(native_invocation.c.ordinal)
    )
    valid: list[CheckRead] = []
    for row in rows:
        read = CheckRead.from_receipt(row.id, row.tool_id, row.arguments, row.value)
        if (
            read is not None
            and read.observed_at >= occurrence.due_at
            and occurrence.authorize_read(read.tool, read.arguments, valid)
        ):
            valid.append(read)
    return valid


class WorkspaceHost:
    def __init__(
        self,
        owner: JarvisOwner,
        *,
        owner_zone: ZoneInfo,
        enrollment: Callable[[], WorkspaceEnrollment | None],
    ) -> None:
        self.owner = owner
        self.owner_zone = owner_zone
        self.enrollment = enrollment

    async def occurrence_current(
        self,
        connection: AsyncConnection,
        occurrence: WorkspaceOccurrence,
        control_sequence: int,
    ) -> bool:
        changed = await connection.scalar(
            select(message.c.id)
            .where(
                message.c.source_conversation_id == self.owner.scope_id,
                message.c.control_sequence > control_sequence,
                or_(
                    message.c.control_kind == "pause",
                    message.c.control_targets.contains([occurrence.occurrence_id]),
                ),
            )
            .limit(1)
        )
        if changed is not None or await connection.scalar(
            latest_control(self.owner.scope_id)
        ) not in {"resume", "stop"}:
            return False
        row = (
            (
                await connection.execute(
                    select(work)
                    .where(work.c.id == occurrence.work_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        grant = self.enrollment()
        now = datetime.now(UTC)
        return now >= occurrence.due_at and occurrence.current(
            row, grant.grant_id if grant else None, now
        )

    async def committed_match(
        self,
        connection: AsyncConnection,
        occurrence_id: UUID,
        todo_id: UUID,
        as_of: datetime | None = None,
    ) -> WorkspaceOccurrence | None:
        """Resolve the original committed occurrence for a send or deliberate tap."""
        final = message.alias("check_result")
        row = (
            await connection.execute(
                select(
                    message.c.text,
                    native_attempt.c.armed_at,
                    native_attempt.c.request["control_sequence"]
                    .as_integer()
                    .label("control_sequence"),
                )
                .select_from(message)
                .join(
                    native_input_delivery,
                    native_input_delivery.c.message_id == message.c.id,
                )
                .join(
                    native_attempt,
                    native_attempt.c.id == native_input_delivery.c.attempt_id,
                )
                .join(
                    final,
                    cast(final.c.id, String)
                    == native_attempt.c.product_outcome["response_id"].as_string(),
                )
                .where(
                    message.c.id == occurrence_id,
                    message.c.source_conversation_id == self.owner.scope_id,
                    message.c.source == "work_wake",
                    message.c.role == "host",
                    message.c.request_state == "completed",
                    proven_native_delivery,
                    final.c.source == "native_final",
                    final.c.role == "assistant",
                    final.c.source_conversation_id == self.owner.scope_id,
                    final.c.home.contains(
                        {
                            "workspace_result": {
                                "occurrence_id": str(occurrence_id),
                                "outcome": "match",
                            },
                            "todo_result": {"todo_id": str(todo_id)},
                        }
                    ),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        occurrence = WorkspaceOccurrence.from_wake(
            occurrence_id, row.text, self.owner_zone, as_of or row.armed_at
        )
        if (
            occurrence is None
            or occurrence.work_id != todo_id
            or not await self.occurrence_current(
                connection, occurrence, row.control_sequence
            )
        ):
            return None
        return occurrence

    async def match_current(self, occurrence_id: UUID, todo_id: UUID) -> bool:
        async with self.owner.database.begin() as connection:
            await lock_conversation(connection, self.owner.scope_id)
            return (
                await self.committed_match(connection, occurrence_id, todo_id)
                is not None
            )

    async def _delivered_inputs(
        self, connection: AsyncConnection, lineage: NativeDispatchLineage
    ):
        rows = (
            await connection.execute(
                select(
                    message.c.id,
                    message.c.role,
                    message.c.source,
                    message.c.request_state,
                    message.c.processing_parked_at,
                    message.c.home,
                    case((message.c.source == "work_wake", message.c.text)).label(
                        "wake_text"
                    ),
                    native_input_delivery.c.delivery_id,
                    native_input_delivery.c.was_waking,
                )
                .join(
                    native_input_delivery,
                    native_input_delivery.c.message_id == message.c.id,
                )
                .where(
                    native_input_delivery.c.attempt_id == UUID(lineage.attempt_id),
                    proven_native_delivery,
                    message.c.source_conversation_id == self.owner.scope_id,
                    message.c.control_kind.is_(None),
                )
                .order_by(native_input_delivery.c.ordinal)
            )
        ).all()
        if not rows or tuple(str(row.id) for row in rows) != tuple(lineage.input_ids):
            raise WorkspaceError("workspace_input_changed")
        return rows

    async def permits_local_read(
        self, lineage: NativeDispatchLineage, tool: str, arguments: dict[str, Any]
    ) -> bool:
        """A check can inspect its own todo and the receipts of its current request."""
        async with self.owner.database.begin() as connection:
            await lock_conversation(connection, self.owner.scope_id)
            rows = await self._delivered_inputs(connection, lineage)
            origin = rows[0]
            refresh = origin.home and origin.home.get("workspace_refresh")
            if refresh:
                todo_id = refresh["todo_id"]
            elif is_workspace_wake(origin.source, origin.wake_text):
                todo_id = json.loads(origin.wake_text)["record"]["id"]
            else:
                return True
            if (
                len(rows) != 1
                or origin.request_state not in {"pending", "waiting"}
                or origin.processing_parked_at is not None
            ):
                return False
            if tool == "receipt.read":
                return arguments.get("request_ref") == str(origin.id)
            return tool == "work.get" and arguments.get("id") == todo_id

    async def read_access(
        self, lineage: NativeDispatchLineage, tool: str, arguments: dict[str, Any]
    ) -> NativeWorkspaceRead:
        grant = self.enrollment()
        if grant is None:
            raise WorkspaceError("grant_unavailable")
        if (
            tool not in _READ_CALLS
            or lineage.permit.scope_id != self.owner.scope_id
            or lineage.permit.owner_token != self.owner.token
        ):
            raise WorkspaceError("workspace_read_not_authorized")
        attempt_id = UUID(lineage.attempt_id)

        async def authorize(connection: AsyncConnection) -> bool:
            await lock_conversation(connection, self.owner.scope_id)
            attempt = (
                await connection.execute(
                    select(
                        native_attempt.c.armed_at,
                        native_attempt.c.request["control_sequence"]
                        .as_integer()
                        .label("control_sequence"),
                    )
                    .join(
                        native_invocation,
                        native_invocation.c.attempt_id == native_attempt.c.id,
                    )
                    .where(
                        native_attempt.c.id == attempt_id,
                        native_attempt.c.conversation_id == self.owner.scope_id,
                        native_attempt.c.owner_epoch == str(self.owner.token),
                        native_attempt.c.fenced_at.is_(None),
                        native_attempt.c.terminal_at.is_(None),
                        native_attempt.c.product_outcome.is_(None),
                        native_invocation.c.id == UUID(lineage.invocation_id),
                        native_invocation.c.ordinal == lineage.ordinal,
                        native_invocation.c.tool_id == tool,
                        native_invocation.c.validation == "accepted",
                        native_invocation.c.frozen_contract["effect"].as_string()
                        == "Read",
                        native_invocation.c.proposal["input_ids"]
                        == list(lineage.input_ids),
                    )
                )
            ).one_or_none()
            if (
                attempt is None
                or self.enrollment() != grant
                or await connection.scalar(latest_control(self.owner.scope_id))
                not in {"resume", "stop"}
            ):
                raise WorkspaceError("workspace_read_not_authorized")
            rows = await self._delivered_inputs(connection, lineage)
            latest = [row for row in rows if row.delivery_id == rows[-1].delivery_id]
            owners = [
                row
                for row in latest
                if row.role == "owner"
                and row.request_state in {"pending", "waiting"}
                and row.processing_parked_at is None
                and row.was_waking
            ]
            occurrence = None
            if owners:
                if any(
                    "workspace_refresh"
                    not in type_cast(dict[str, object], row.home or {})
                    for row in owners
                ):
                    return False
                # A deliberate alert tap carries the exact local todo and original
                # occurrence. Its search is fresh, scoped, and owner-budgeted.
                if len(owners) == 1:
                    refresh = owners[0].home["workspace_refresh"]
                    occurrence = await self.committed_match(
                        connection,
                        UUID(refresh["occurrence_id"]),
                        UUID(refresh["todo_id"]),
                        attempt.armed_at,
                    )
            elif (
                len(rows) == 1
                and rows[0].was_waking
                and rows[0].role == "host"
                and rows[0].source == "work_wake"
                and rows[0].request_state == "pending"
                and rows[0].processing_parked_at is None
            ):
                occurrence = WorkspaceOccurrence.from_wake(
                    rows[0].id, rows[0].wake_text, self.owner_zone, attempt.armed_at
                )
                if occurrence and not await self.occurrence_current(
                    connection, occurrence, attempt.control_sequence
                ):
                    occurrence = None
            if occurrence is None:
                raise WorkspaceError("workspace_read_not_authorized")
            if occurrence.authorize_read(tool, arguments, ()):
                return not owners
            observations = await check_observations(
                connection, attempt_id, occurrence, input_ids=lineage.input_ids
            )
            if not occurrence.authorize_read(tool, arguments, observations):
                raise WorkspaceError("workspace_read_outside_check")
            return not owners

        async with self.owner.database.begin() as connection:
            background = await authorize(connection)

        async def require_current(connection: AsyncConnection | None) -> None:
            if connection is None:
                async with self.owner.database.begin() as connection:
                    await require_current(connection)
            elif await authorize(connection) != background:
                raise WorkspaceError("workspace_input_changed")

        # Local MIME sections, offsets and projection digests can share one paid
        # RAW fetch. A local list suffix can reread the same provider page too.
        # Freeze the upstream resource and provider token before occupying the position.
        operation_name, target_fields = _READ_CALLS[tool]
        target = {key: arguments.get(field) for key, field in target_fields.items()}
        token = None
        if arguments.get("cursor") is not None:
            selection = {k: v for k, v in arguments.items() if k != "cursor"}
            scope = sha256(
                canonical_json_bytes(
                    [grant.account, str(grant.grant_id), tool, selection]
                )
            ).hexdigest()
            token = Token.open(arguments["cursor"], scope).token
        source_digest = sha256(
            canonical_json_bytes([str(grant.grant_id), tool, target, token])
        ).hexdigest()

        async def before_send(
            public: str,
            selectors: dict[str, object],
            product: str,
            operation: str,
            wire: dict[str, object],
        ) -> None:
            if (
                public != tool
                or selectors != arguments
                or product != tool.partition(".")[0]
                or operation != operation_name
                or wire.get("pageToken") != token
                or any(wire.get(key) != value for key, value in target.items())
                or wire.get("includeTrash") is True
            ):
                raise WorkspaceError("workspace_read_outside_check")
            await require_current(None)

        return NativeWorkspaceRead(
            lineage.invocation_id,
            background,
            before_send,
            grant.grant_id,
            source_digest,
            require_current,
        )

"""Authorize Workspace reads at an accepted, current main invocation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from llm_agent_kernel import NativeDispatchLineage
from llm_tools import InvocationPosition, ToolId, canonical_json_bytes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.admission import JarvisOwner
from jarvis.db import (
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
)
from jarvis.messages import latest_control
from jarvis.ownership import lock_conversation
from jarvis.workspace_enrollment import WorkspaceEnrollment
from jarvis.workspace_mcp import DRIVE_SCOPE, WorkspaceError
from jarvis.workspace_reads import (
    DriveCursor,
    Token,
    WorkspaceReadAccess,
    workspace_cursor_scope,
)

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
    "drive.search": ("search_files", {"query": "query"}),
    "drive.recent": ("list_recent_files", {}),
    "drive.get": ("get_file_metadata", {"fileId": "id"}),
    "drive.permissions": ("get_file_permissions", {"fileId": "id"}),
    "drive.read": ("read_file_content", {"fileId": "id"}),
    "drive.download": (
        "download_file_content",
        {"fileId": "id", "exportMimeType": "export_type"},
    ),
    "docs.read": ("get_document", {"documentId": "id"}),
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


class WorkspaceHost:
    def __init__(
        self,
        owner: JarvisOwner,
        *,
        enrollment: Callable[[], WorkspaceEnrollment | None],
    ) -> None:
        self.owner = owner
        self.enrollment = enrollment

    async def read_access(
        self,
        lineage: NativeDispatchLineage,
        tool: str,
        arguments: dict[str, Any],
    ) -> NativeWorkspaceRead:
        if (
            tool not in _READ_CALLS
            or lineage.permit.scope_id != self.owner.scope_id
            or lineage.permit.owner_token != self.owner.token
        ):
            raise WorkspaceError("workspace_read_not_authorized")
        grant = self.enrollment()
        if grant is None:
            raise WorkspaceError("grant_unavailable")
        drive = tool.startswith(("drive.", "docs."))
        attempt_id = UUID(lineage.attempt_id)
        input_ids = tuple(map(UUID, lineage.input_ids))

        async def authorize(connection: AsyncConnection) -> None:
            await lock_conversation(connection, self.owner.scope_id)
            latest = self.enrollment()
            if latest is None or latest != grant:
                raise WorkspaceError("grant_unavailable")
            if drive and DRIVE_SCOPE not in latest.scopes:
                raise WorkspaceError("scope_missing")
            invocation = await connection.scalar(
                select(native_invocation.c.id)
                .join(
                    native_attempt,
                    native_attempt.c.id == native_invocation.c.attempt_id,
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
                    native_invocation.c.frozen_contract["effect"].as_string() == "Read",
                    native_invocation.c.proposal["input_ids"]
                    == list(lineage.input_ids),
                    native_invocation.c.proposal["through_checkpoint"]
                    .as_string()
                    .is_not_distinct_from(lineage.through_checkpoint),
                )
            )
            if invocation is None or await connection.scalar(
                latest_control(self.owner.scope_id)
            ) not in {"resume", "stop"}:
                raise WorkspaceError("workspace_read_not_authorized")
            # A later steering delivery cannot change an accepted callback.
            delivered = (
                await connection.execute(
                    select(
                        message.c.id,
                        (
                            message.c.request_state.in_(("pending", "waiting"))
                            & message.c.processing_parked_at.is_(None)
                        ).label("live"),
                    )
                    .join(
                        native_input_delivery,
                        native_input_delivery.c.message_id == message.c.id,
                    )
                    .where(
                        native_input_delivery.c.attempt_id == attempt_id,
                        proven_native_delivery,
                        message.c.source_conversation_id == self.owner.scope_id,
                        message.c.control_kind.is_(None),
                        message.c.id.in_(input_ids),
                    )
                    .order_by(native_input_delivery.c.ordinal)
                )
            ).all()
            if tuple(row.id for row in delivered) != input_ids:
                raise WorkspaceError("workspace_input_changed")
            if not any(row.live for row in delivered):
                raise WorkspaceError("workspace_read_not_authorized")

        async def require_current(connection: AsyncConnection | None) -> None:
            if connection is None:
                async with self.owner.database.begin() as connection:
                    await authorize(connection)
            else:
                await authorize(connection)

        await require_current(None)

        # Local MIME sections, offsets and projection digests can share one paid
        # RAW fetch. A local list suffix can reread the same provider page too.
        # Freeze the upstream resource and provider token before occupying the position.
        operation_name, target_fields = _READ_CALLS[tool]
        target = {key: arguments.get(field) for key, field in target_fields.items()}
        token = None
        if arguments.get("cursor") is not None:
            scope = workspace_cursor_scope(
                grant.subject if drive else grant.account,
                grant.grant_id,
                tool,
                arguments,
            )
            token = (
                (DriveCursor if drive else Token).open(arguments["cursor"], scope).token
            )
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
            download_metadata = (
                tool == "drive.download" and operation == "get_file_metadata"
            )
            revision_metadata = tool == "drive.get" and operation == "get_file_revision"
            requested = {"fileId": target["fileId"]} if download_metadata else target
            if (
                public != tool
                or selectors != arguments
                or product != tool.partition(".")[0]
                or (
                    operation != operation_name
                    and not (download_metadata or revision_metadata)
                )
                or (revision_metadata and wire != target)
                or wire.get("pageToken") != token
                or any(wire.get(key) != value for key, value in requested.items())
                or wire.get("includeTrash") is True
            ):
                raise WorkspaceError("workspace_read_outside_invocation")
            await require_current(None)

        return NativeWorkspaceRead(
            invocation_id=lineage.invocation_id,
            before_send=before_send,
            grant_id=grant.grant_id,
            source_digest=source_digest,
            require_current=require_current,
        )

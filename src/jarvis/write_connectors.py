"""Execute one immutable Workspace action under its live host authority."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from llm_tools import DeclaredToolFailure, ExecutionContext, HandlerSuccess
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.mail_files import MailFileFailure
from jarvis.workspace_mcp import (
    HUMAN_WAIT_SECONDS,
    WORKSPACE_DRIVE_RPC_LIMIT,
    WorkspaceError,
    workspace_attempts,
)
from jarvis.workspace_write_models import (
    CalendarWriteReceipt,
    DiscardReceipt,
    DraftWriteReceipt,
    DriveWriteReceipt,
    FrozenDriveCreate,
    FrozenDriveRevise,
    FrozenWorkspaceWrite,
    SubmissionSource,
)

if TYPE_CHECKING:
    from jarvis.attachments import AttachmentStore
    from jarvis.workspace_writes import WorkspaceWrites

type WorkspaceReceipt = (
    DraftWriteReceipt | DiscardReceipt | CalendarWriteReceipt | DriveWriteReceipt
)


def submission_source_id(frozen: FrozenWorkspaceWrite) -> UUID | None:
    effect = frozen.effect
    return (
        effect.source.value.submission_id
        if isinstance(effect, FrozenDriveCreate | FrozenDriveRevise)
        and isinstance(effect.source.value, SubmissionSource)
        else None
    )


def write_rpc_limit(tool: str) -> int:
    # RPCs are preflight/readback traffic under a single logical write entry.
    from jarvis.write_tools import GMAIL_WRITE_POLICY

    return (
        WORKSPACE_DRIVE_RPC_LIMIT
        if tool.startswith(("drive.", "docs."))
        else GMAIL_WRITE_POLICY.max_attempts
    )


class WorkspaceWriteFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    type: Literal["WorkspaceWriteFailure"] = "WorkspaceWriteFailure"
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")]
    retry_at: AwareDatetime | None = None
    known_no_effect: bool = False
    differences: Annotated[str, Field(max_length=8192)] | None = None


def workspace_failure(exc: WorkspaceError) -> WorkspaceWriteFailure:
    from jarvis.workspace_writes import WorkspaceWriteConflict

    detail = None
    if isinstance(exc, WorkspaceWriteConflict):
        detail = json.dumps(exc.differences, ensure_ascii=False, separators=(",", ":"))
        if len(detail.encode()) > 8192:
            detail = json.dumps({"changed_fields": sorted(exc.differences)})
    return WorkspaceWriteFailure(
        code=exc.kind,
        retry_at=exc.retry_at,
        differences=detail,
        known_no_effect=exc.known_no_effect,
    )


@dataclass(frozen=True, slots=True)
class WorkspaceWriteEntry:
    frozen: FrozenWorkspaceWrite
    invocation_id: UUID
    authorize: Callable[[AsyncConnection | None], Awaitable[None]]
    prepare_attempts: int
    prepare_seconds: float
    prepare_human_elapsed: float
    prepare_consent_rounds: int
    submissions: AttachmentStore

    async def before_send(self) -> None:
        await self.authorize(None)


async def execute_workspace_write(
    writes: WorkspaceWrites,
    context: ExecutionContext,
) -> HandlerSuccess[WorkspaceReceipt]:
    from jarvis.actions import ActionPositionRecorder

    recorder = context.recorder
    if not isinstance(recorder, ActionPositionRecorder):
        raise RuntimeError("workspace write requires its durable action recorder")
    entry = recorder.workspace_entry
    if (
        entry is None
        or str(entry.frozen.action_id) != context.effect_id
        or context.position != context.effect_id
        or entry.frozen.tool != context.grant.id
    ):
        raise RuntimeError("workspace write differs from its recorded action")
    source = submission_source_id(entry.frozen)

    async def acknowledge(receipt: WorkspaceReceipt) -> None:
        await recorder.record_workspace_ack(receipt)
        if source is not None and isinstance(receipt, DriveWriteReceipt):
            await entry.submissions.acknowledge(
                source, receipt.action_id, receipt.subject, receipt.file_id
            )

    try:
        seconds = (
            context.grant.limits.deadline_seconds
            - HUMAN_WAIT_SECONDS
            - entry.prepare_seconds
        )
        maximum = write_rpc_limit(entry.frozen.tool) - entry.prepare_attempts
        if seconds <= 0 or maximum <= 0:
            raise WorkspaceError("budget_exceeded", known_no_effect=source is not None)
        with workspace_attempts(
            maximum,
            seconds=seconds,
            human_elapsed=entry.prepare_human_elapsed,
            consent_rounds=entry.prepare_consent_rounds,
        ):
            result = await writes.execute(
                entry.frozen,
                invocation_id=str(entry.invocation_id),
                before_send=entry.before_send,
                record_ack=acknowledge,
                capture_draft=recorder.capture_draft_revision
                if entry.frozen.tool == "gmail.create_draft"
                else None,
            )
    except MailFileFailure as exc:
        raise DeclaredToolFailure(exc.detail, actual_attempts=1) from exc
    except WorkspaceError as exc:
        raise DeclaredToolFailure(workspace_failure(exc), actual_attempts=1) from exc
    if source is not None and isinstance(result, DriveWriteReceipt):
        if result.verification == "verified":
            await entry.submissions.verify(source, result.action_id)
    return HandlerSuccess(result, actual_attempts=1)

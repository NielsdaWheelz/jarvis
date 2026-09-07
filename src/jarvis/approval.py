"""Deterministic host-owned approval rendering."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from llm_tools import ToolId
from pydantic import BaseModel

from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarUpdateEventInput,
    GmailSendDraftInput,
)

APPROVAL_ATTACHMENT_MAX_BYTES = 1_000_000
APPROVAL_ATTACHMENT_MEDIA_TYPE = "text/plain; charset=utf-8"


class ApprovalRenderError(ValueError):
    """An approval cannot be rendered exactly and safely."""


@dataclass(frozen=True, slots=True)
class ApprovalAttachment:
    """One complete host-generated approval payload."""

    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ApprovalPresentation:
    """The bounded Discord message and its complete payload attachment."""

    content: str
    attachment: ApprovalAttachment


def render_approval(
    action_id: UUID,
    tool_name: ToolId,
    value: object,
) -> ApprovalPresentation:
    """Render the exact validated stored arguments for a supported action."""

    expected_type: type[BaseModel]
    title: str
    if tool_name == ToolId("gmail.send_draft"):
        expected_type = GmailSendDraftInput
        title = "Send Gmail draft"
    elif tool_name == ToolId("calendar.create_event"):
        expected_type = CalendarCreateEventInput
        title = "Create Google Calendar event"
    elif tool_name == ToolId("calendar.update_event"):
        expected_type = CalendarUpdateEventInput
        title = "Update Google Calendar event"
    elif tool_name == ToolId("calendar.delete_event"):
        expected_type = CalendarDeleteEventInput
        title = "Delete Google Calendar event"
    else:
        raise ApprovalRenderError("approval-bearing tool has no host renderer")

    if not isinstance(value, expected_type):
        raise ApprovalRenderError("stored approval arguments have the wrong type")

    payload = {
        "action_id": str(action_id),
        "arguments": cast("dict[str, object]", value.model_dump(mode="json")),
        "tool_name": str(tool_name),
    }
    encoded = (
        "Jarvis approval payload\n"
        "This UTF-8 JSON document is the complete action payload. JSON string "
        "escapes are representational and preserve the exact stored text.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    if len(encoded) > APPROVAL_ATTACHMENT_MAX_BYTES:
        raise ApprovalRenderError("approval payload exceeds its attachment bound")

    return ApprovalPresentation(
        content=(
            f"Approval required: {title}\n"
            f"Action ID: {action_id}\n"
            "The attached UTF-8 text file is the complete payload. Approve executes "
            "exactly that payload; Deny executes nothing."
        ),
        attachment=ApprovalAttachment(
            filename=f"jarvis-approval-{action_id}.txt",
            media_type=APPROVAL_ATTACHMENT_MEDIA_TYPE,
            content=encoded,
        ),
    )


def render_inactive_approval(
    action_id: UUID,
    tool_name: ToolId,
    arguments: Mapping[str, object],
    content: str,
) -> ApprovalPresentation:
    """Render a cancelled undelivered action with no functional decision."""

    if not content:
        raise ApprovalRenderError("inactive approval content is empty")
    payload = {
        "action_id": str(action_id),
        "arguments": dict(arguments),
        "tool_name": str(tool_name),
    }
    encoded = (
        "Jarvis cancelled approval payload\n"
        "This action was cancelled before delivery and cannot be executed. "
        "The JSON below preserves the complete former payload.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    if len(encoded) > APPROVAL_ATTACHMENT_MAX_BYTES:
        raise ApprovalRenderError("inactive approval payload exceeds its bound")
    return ApprovalPresentation(
        content=content,
        attachment=ApprovalAttachment(
            filename=f"jarvis-cancelled-approval-{action_id}.txt",
            media_type=APPROVAL_ATTACHMENT_MEDIA_TYPE,
            content=encoded,
        ),
    )


__all__ = [
    "APPROVAL_ATTACHMENT_MAX_BYTES",
    "ApprovalAttachment",
    "ApprovalPresentation",
    "ApprovalRenderError",
    "render_approval",
    "render_inactive_approval",
]

"""Deterministic application write classification."""

from __future__ import annotations

from typing import Literal

from llm_tools import ToolId

from jarvis.agent_tools import (
    AgentCancelWaitInput,
    AgentCloseInput,
    AgentKeysInput,
    AgentSendInput,
    AgentStartInput,
    AgentStopInput,
    AgentWaitInput,
)
from jarvis.attachment_tools import AttachmentDeleteInput, AttachmentRetainInput
from jarvis.event_tools import EventsConfigureInput
from jarvis.work_tools import WorkCreateInput, WorkDeleteInput, WorkUpdateInput
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
)

type WriteAuthority = Literal["automatic", "approval_required", "rejected"]


def classify_write(
    tool_id: ToolId,
    value: object,
    *,
    verified_owner_only_calendar_ids: tuple[str, ...],
    live_calendar_event: CalendarEventSnapshot | None = None,
) -> WriteAuthority:
    """Classify authority without granting it or creating durable state."""

    name = str(tool_id)
    if (name, type(value)) in {
        ("events.configure", EventsConfigureInput),
        ("attachment.retain", AttachmentRetainInput),
        ("work.create", WorkCreateInput),
        ("work.update", WorkUpdateInput),
        ("work.delete", WorkDeleteInput),
        ("agent.start", AgentStartInput),
        ("agent.send", AgentSendInput),
        ("agent.keys", AgentKeysInput),
        ("agent.text", AgentSendInput),
        ("agent.stop", AgentStopInput),
        ("agent.close", AgentCloseInput),
        ("agent.wait", AgentWaitInput),
        ("agent.cancel_wait", AgentCancelWaitInput),
    }:
        return "automatic"
    if name == "attachment.delete" and isinstance(value, AttachmentDeleteInput):
        return "approval_required"
    if name in {"gmail.create_draft", "gmail.update_draft"}:
        return "automatic"
    if name == "gmail.send_draft":
        return "approval_required"
    verified = set(verified_owner_only_calendar_ids)
    if name == "calendar.create_event" and isinstance(value, CalendarCreateEventInput):
        return (
            "automatic"
            if value.calendar_id in verified
            and not value.notify_attendees
            and not value.event.attendees
            else "approval_required"
        )
    if name == "calendar.update_event" and isinstance(value, CalendarUpdateEventInput):
        if live_calendar_event is None or live_calendar_event != value.expected:
            return "rejected"
        return (
            "automatic"
            if value.expected.calendar_id in verified
            and not value.notify_attendees
            and not live_calendar_event.writable.attendees
            and not value.replacement.attendees
            else "approval_required"
        )
    if name == "calendar.delete_event" and isinstance(value, CalendarDeleteEventInput):
        if live_calendar_event is None or live_calendar_event != value.expected:
            return "rejected"
        return (
            "automatic"
            if value.expected.calendar_id in verified
            and not value.notify_attendees
            and not live_calendar_event.writable.attendees
            else "approval_required"
        )
    return "rejected"


__all__ = ["WriteAuthority", "classify_write"]

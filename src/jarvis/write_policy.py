"""Deterministic application write classification."""

from __future__ import annotations

from typing import Literal

from llm_tools import ToolId

from jarvis.agent_tools import (
    AgentCloseInput,
    AgentDelegateInput,
    AgentKeysInput,
    AgentSendInput,
    AgentStartInput,
    AgentStopInput,
)
from jarvis.attachment_tools import AttachmentDeleteInput, AttachmentRetainInput
from jarvis.event_tools import EventsConfigureInput
from jarvis.work_tools import WorkCreateInput, WorkDeleteInput, WorkUpdateInput
from jarvis.workspace_write_models import (
    CreateDraft,
    CreateEvent,
    DeleteEvent,
    DiscardDraft,
    PrepareReplacement,
    UpdateEvent,
)

type WriteAuthority = Literal["automatic", "approval_required", "rejected"]


def classify_write(
    tool_id: ToolId,
    value: object,
) -> WriteAuthority:
    """Classify authority without granting it or creating durable state."""

    name = str(tool_id)
    if (name, type(value)) in {
        ("events.configure", EventsConfigureInput),
        ("gmail.create_draft", CreateDraft),
        ("gmail.prepare_replacement", PrepareReplacement),
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
        ("agent.delegate", AgentDelegateInput),
    }:
        return "automatic"
    if (name, type(value)) in {
        ("attachment.delete", AttachmentDeleteInput),
        ("gmail.discard_draft", DiscardDraft),
        ("calendar.create_event", CreateEvent),
        ("calendar.update_event", UpdateEvent),
        ("calendar.delete_event", DeleteEvent),
    }:
        return "approval_required"
    return "rejected"

"""Deterministic write authority and AutomaticWriteGate projections."""

from __future__ import annotations

from typing import Literal, cast

from llm_tools import ToolId

from jarvis.agent_tools import (
    AgentKeysInput,
    AgentRefInput,
    AgentSendInput,
    AgentStartInput,
    AgentWriteTarget,
)
from jarvis.schedule_tools import (
    ScheduleCancelRequest,
    ScheduleCreateRequest,
    ScheduleWakeInput,
)
from jarvis.write_gate import (
    EffectAudience,
    EffectTarget,
    OmittedFreeform,
    WriteEffectDescriptor,
)
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailSendDraftInput,
    GmailUpdateDraftInput,
    TimedEventTime,
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
        ("agent.start", AgentStartInput),
        ("agent.send", AgentSendInput),
        ("agent.keys", AgentKeysInput),
        ("agent.interrupt", AgentRefInput),
        ("agent.stop", AgentRefInput),
        ("agent.kill", AgentRefInput),
    }:
        return "automatic"
    if name in {"gmail.create_draft", "gmail.update_draft", "schedule.wake"}:
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


def write_effect_descriptor(
    tool_id: ToolId,
    value: object,
    *,
    target: AgentWriteTarget | None = None,
) -> WriteEffectDescriptor:
    """Project one strictly validated input into the gate's scalar allowlist."""

    name = str(tool_id)
    if name == "agent.start" and isinstance(value, AgentStartInput):
        return WriteEffectDescriptor(
            operation="start",
            targets=(
                EffectTarget(kind="machine", value=value.machine),
                EffectTarget(kind="profile", value=value.profile),
                *(
                    ()
                    if value.cwd is None
                    else (EffectTarget(kind="cwd", value=value.cwd),)
                ),
                EffectTarget(kind="terminal_name", value=value.name),
            ),
        )
    if name in {
        "agent.send",
        "agent.keys",
        "agent.interrupt",
        "agent.stop",
        "agent.kill",
    } and isinstance(value, AgentSendInput | AgentKeysInput | AgentRefInput):
        if target is None:
            raise ValueError("addressed agent write requires its original target")
        return WriteEffectDescriptor(
            operation=cast(
                Literal["send", "keys", "interrupt", "stop", "kill"],
                name.removeprefix("agent."),
            ),
            targets=(
                EffectTarget(kind="machine", value=target.machine),
                *(
                    ()
                    if target.name is None
                    else (EffectTarget(kind="terminal_name", value=target.name),)
                ),
                EffectTarget(kind="pane", value=target.pane),
            ),
            omitted_freeform=(
                (OmittedFreeform.from_text("worker_input", value.text),)
                if isinstance(value, AgentSendInput)
                else ()
            ),
            closure_scope=(
                "native_linked_workspace_group_may_close"
                if name in {"agent.stop", "agent.kill"}
                else None
            ),
        )
    if name == "gmail.create_draft" and isinstance(value, GmailCreateDraftInput):
        return _gmail_descriptor("create", value.content)
    if name == "gmail.update_draft" and isinstance(value, GmailUpdateDraftInput):
        base = _gmail_descriptor("update", value.replacement)
        return base.model_copy(
            update={
                "targets": (
                    EffectTarget(kind="draft_id", value=value.draft_id),
                    *base.targets,
                ),
                "omitted_freeform": (
                    *base.omitted_freeform,
                    OmittedFreeform.from_text(
                        "expected_content", value.expected_content_digest
                    ),
                ),
            }
        )
    if name == "gmail.send_draft" and isinstance(value, GmailSendDraftInput):
        base = _gmail_descriptor("send", value.content)
        return base.model_copy(
            update={
                "targets": (
                    EffectTarget(kind="draft_id", value=value.draft_id),
                    EffectTarget(kind="thread_id", value=value.thread_id),
                    *base.targets,
                ),
            }
        )
    if name == "calendar.create_event" and isinstance(value, CalendarCreateEventInput):
        return _calendar_descriptor(
            "create",
            value.event,
            calendar_id=value.calendar_id,
            event_id=None,
            notify_attendees=value.notify_attendees,
            has_expected_etag=None,
        )
    if name == "calendar.update_event" and isinstance(value, CalendarUpdateEventInput):
        return _calendar_descriptor(
            "update",
            value.replacement,
            calendar_id=value.expected.calendar_id,
            event_id=value.expected.event_id,
            notify_attendees=value.notify_attendees,
            has_expected_etag=True,
        )
    if name == "calendar.delete_event" and isinstance(value, CalendarDeleteEventInput):
        expected = value.expected
        return WriteEffectDescriptor(
            operation="delete",
            targets=(
                EffectTarget(kind="calendar_id", value=expected.calendar_id),
                EffectTarget(kind="event_id", value=expected.event_id),
            ),
            audience=tuple(
                EffectAudience(kind="attendee", address=item.address)
                for item in expected.writable.attendees
            ),
            notify_attendees=value.notify_attendees,
            has_expected_etag=True,
        )
    if name == "schedule.wake" and isinstance(value, ScheduleWakeInput):
        request = value.request
        if isinstance(request, ScheduleCreateRequest):
            return WriteEffectDescriptor(
                operation="create",
                execute_after=request.execute_after,
                omitted_freeform=(
                    OmittedFreeform.from_text("instruction", request.instruction),
                ),
            )
        assert isinstance(request, ScheduleCancelRequest)
        return WriteEffectDescriptor(
            operation="cancel",
            targets=(
                EffectTarget(
                    kind="target_action_id",
                    value=str(request.target_action_id),
                ),
            ),
        )
    raise ValueError("validated Write has no gate projection")


def _gmail_descriptor(
    operation: Literal["create", "update", "send"],
    content: GmailContent,
) -> WriteEffectDescriptor:
    targets: list[EffectTarget] = []
    reply = content.reply_to
    if reply is not None:
        targets.extend(
            (
                EffectTarget(kind="thread_id", value=reply.thread_id),
                EffectTarget(kind="reply_message_id", value=reply.parent_message_id),
            )
        )
    audience = (
        *(EffectAudience(kind="to", address=item.address) for item in content.to),
        *(EffectAudience(kind="cc", address=item.address) for item in content.cc),
        *(EffectAudience(kind="bcc", address=item.address) for item in content.bcc),
    )
    return WriteEffectDescriptor(
        operation=operation,
        targets=tuple(targets),
        audience=audience,
        has_reply_target=reply is not None,
        omitted_freeform=(
            OmittedFreeform.from_text("subject", content.subject),
            OmittedFreeform.from_text("body_text", content.body_text),
        ),
    )


def _calendar_descriptor(
    operation: Literal["create", "update"],
    event: CalendarWritableEvent,
    *,
    calendar_id: str,
    event_id: str | None,
    notify_attendees: bool,
    has_expected_etag: bool | None,
) -> WriteEffectDescriptor:
    targets = [EffectTarget(kind="calendar_id", value=calendar_id)]
    if event_id is not None:
        targets.append(EffectTarget(kind="event_id", value=event_id))
    start = event.start
    end = event.end
    time_zone = start.time_zone if isinstance(start, TimedEventTime) else None
    starts_at = (
        start.date_time.isoformat()
        if isinstance(start, TimedEventTime)
        else start.date.isoformat()
    )
    ends_at = (
        end.date_time.isoformat()
        if isinstance(end, TimedEventTime)
        else end.date.isoformat()
    )
    omitted = [OmittedFreeform.from_text("summary", event.summary)]
    if event.description is not None:
        omitted.append(OmittedFreeform.from_text("description", event.description))
    if event.location is not None:
        omitted.append(OmittedFreeform.from_text("location", event.location))
    return WriteEffectDescriptor(
        operation=operation,
        targets=tuple(targets),
        audience=tuple(
            EffectAudience(kind="attendee", address=item.address)
            for item in event.attendees
        ),
        starts_at=starts_at,
        ends_at=ends_at,
        event_timezone=time_zone,
        recurrence_count=len(event.recurrence),
        reminder_count=len(event.reminders),
        notify_attendees=notify_attendees,
        use_default_reminders=event.use_default_reminders,
        has_expected_etag=has_expected_etag,
        omitted_freeform=tuple(omitted),
    )


__all__ = ["WriteAuthority", "classify_write", "write_effect_descriptor"]

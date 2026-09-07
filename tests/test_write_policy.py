from __future__ import annotations

from datetime import UTC, datetime, timedelta

from llm_tools import ToolId

from jarvis.schedule_tools import ScheduleCreateRequest, ScheduleWakeInput
from jarvis.write_policy import classify_write, write_effect_descriptor
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailSendDraftInput,
    Mailbox,
    TimedEventTime,
)

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


def _content(body: str = "Synthetic body") -> GmailContent:
    return GmailContent(
        to=(Mailbox(name=None, address="owner@example.invalid"),),
        cc=(),
        bcc=(),
        subject="Synthetic subject",
        body_text=body,
        reply_to=None,
    )


def _event(*, attendees: tuple[Mailbox, ...] = ()) -> CalendarWritableEvent:
    return CalendarWritableEvent(
        summary="Synthetic event",
        description=None,
        location=None,
        start=TimedEventTime(date_time=NOW, time_zone="UTC"),
        end=TimedEventTime(date_time=NOW + timedelta(hours=1), time_zone="UTC"),
        recurrence=(),
        attendees=attendees,
        use_default_reminders=True,
        reminders=(),
    )


def _snapshot(event: CalendarWritableEvent) -> CalendarEventSnapshot:
    return CalendarEventSnapshot(
        calendar_id="owner@example.invalid",
        event_id="event-id",
        etag='"etag"',
        status="confirmed",
        writable=event,
        organizer=Mailbox(name=None, address="owner@example.invalid"),
        updated_at=NOW,
    )


def test_host_authority_classification_is_exhaustive_and_fail_closed() -> None:
    content = _content()
    assert (
        classify_write(
            ToolId("gmail.create_draft"),
            GmailCreateDraftInput(content=content),
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "automatic"
    )
    assert (
        classify_write(
            ToolId("gmail.send_draft"),
            GmailSendDraftInput(
                draft_id="draft",
                thread_id="thread",
                jarvis_effect_id="a" * 64,
                content=content,
            ),
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "approval_required"
    )
    create = CalendarCreateEventInput(
        calendar_id="owner@example.invalid",
        event=_event(),
        notify_attendees=False,
    )
    assert (
        classify_write(
            ToolId("calendar.create_event"),
            create,
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "automatic"
    )
    assert (
        classify_write(
            ToolId("calendar.create_event"),
            create.model_copy(update={"calendar_id": "shared@example.invalid"}),
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "approval_required"
    )
    attendee = Mailbox(name=None, address="other@example.invalid")
    assert (
        classify_write(
            ToolId("calendar.create_event"),
            create.model_copy(update={"event": _event(attendees=(attendee,))}),
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "approval_required"
    )

    expected = _snapshot(_event())
    update = CalendarUpdateEventInput(
        expected=expected,
        replacement=_event(),
        notify_attendees=False,
    )
    delete = CalendarDeleteEventInput(expected=expected, notify_attendees=False)
    for tool_id, value in (
        (ToolId("calendar.update_event"), update),
        (ToolId("calendar.delete_event"), delete),
    ):
        assert (
            classify_write(
                tool_id,
                value,
                verified_owner_only_calendar_ids=("owner@example.invalid",),
                live_calendar_event=expected,
            )
            == "automatic"
        )
        assert (
            classify_write(
                tool_id,
                value,
                verified_owner_only_calendar_ids=("owner@example.invalid",),
                live_calendar_event=None,
            )
            == "rejected"
        )

    schedule = ScheduleWakeInput(
        request=ScheduleCreateRequest(
            execute_after=NOW + timedelta(hours=1), instruction="Synthetic reminder"
        )
    )
    assert (
        classify_write(
            ToolId("schedule.wake"),
            schedule,
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "automatic"
    )
    assert (
        classify_write(
            ToolId("unknown.write"),
            object(),
            verified_owner_only_calendar_ids=("owner@example.invalid",),
        )
        == "rejected"
    )


def test_gate_descriptor_omits_freeform_payload_but_binds_its_digest() -> None:
    private_payload = "Synthetic payload that the gate must not receive."
    descriptor = write_effect_descriptor(
        ToolId("gmail.create_draft"),
        GmailCreateDraftInput(content=_content(private_payload)),
    )
    encoded = descriptor.model_dump_json()

    assert private_payload not in encoded
    assert descriptor.operation == "create"
    assert [item.kind for item in descriptor.audience] == ["to"]
    assert [item.kind for item in descriptor.omitted_freeform] == [
        "subject",
        "body_text",
    ]
    assert descriptor.omitted_freeform[1].utf8_bytes == len(private_payload.encode())
    assert descriptor.omitted_freeform[1].sha256

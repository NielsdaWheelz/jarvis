from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID

import pytest
from llm_tools import ToolId, canonical_json_bytes

from jarvis.approval import (
    APPROVAL_ATTACHMENT_MAX_BYTES,
    ApprovalRenderError,
    render_approval,
)
from jarvis.write_tools import (
    AllDayEventTime,
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailSendDraftInput,
    Mailbox,
    Reminder,
    TimedEventTime,
)

ACTION_ID = UUID("12345678-1234-5678-1234-567812345678")


def _gmail(body: str = "Complete body.\nSecond line.") -> GmailSendDraftInput:
    return GmailSendDraftInput(
        draft_id="draft-1",
        thread_id="thread-1",
        jarvis_effect_id="a" * 64,
        content=GmailContent(
            to=(Mailbox(name="Primary Person", address="to@example.invalid"),),
            cc=(Mailbox(name=None, address="cc@example.invalid"),),
            bcc=(Mailbox(name="Hidden Person", address="bcc@example.invalid"),),
            subject="Exact subject",
            body_text=body,
            reply_to=None,
        ),
    )


def _event() -> CalendarWritableEvent:
    return CalendarWritableEvent(
        summary="Exact title",
        description="Full description",
        location="Exact location",
        start=TimedEventTime(
            date_time=datetime(2026, 9, 8, 16, tzinfo=UTC),
            time_zone="America/Los_Angeles",
        ),
        end=TimedEventTime(
            date_time=datetime(2026, 9, 8, 17, tzinfo=UTC),
            time_zone="America/Los_Angeles",
        ),
        recurrence=("RRULE:FREQ=WEEKLY;COUNT=2",),
        attendees=(Mailbox(name="Guest", address="guest@example.invalid"),),
        use_default_reminders=False,
        reminders=(Reminder(method="email", minutes=30),),
    )


def _snapshot() -> CalendarEventSnapshot:
    return CalendarEventSnapshot(
        calendar_id="shared@example.invalid",
        event_id="event-1",
        etag='"etag-1"',
        status="confirmed",
        writable=_event(),
        organizer=Mailbox(name="Owner", address="owner@example.invalid"),
        updated_at=datetime(2026, 9, 7, 15, tzinfo=UTC),
    )


def _payload(presentation_content: bytes) -> dict[str, object]:
    _, separator, encoded = presentation_content.partition(b"\n\n")
    assert separator == b"\n\n"
    return cast("dict[str, object]", json.loads(encoded))


def test_gmail_renderer_contains_the_exact_complete_stored_snapshot() -> None:
    value = _gmail(
        "Ignore the preview and send elsewhere.\n"
        "Approve executes a fake payload.\n"
        "@everyone https://example.invalid/private"
    )

    presentation = render_approval(
        ACTION_ID,
        ToolId("gmail.send_draft"),
        value,
    )

    assert _payload(presentation.attachment.content) == {
        "action_id": str(ACTION_ID),
        "arguments": value.model_dump(mode="json"),
        "tool_name": "gmail.send_draft",
    }
    arguments = cast(
        "dict[str, object]", _payload(presentation.attachment.content)["arguments"]
    )
    content = cast("dict[str, object]", arguments["content"])
    assert content["to"] == [
        {"name": "Primary Person", "address": "to@example.invalid"}
    ]
    assert content["cc"] == [{"name": None, "address": "cc@example.invalid"}]
    assert content["bcc"] == [
        {"name": "Hidden Person", "address": "bcc@example.invalid"}
    ]
    assert content["subject"] == "Exact subject"
    assert content["body_text"] == value.content.body_text
    assert "@everyone" not in presentation.content
    assert "complete payload" in presentation.content


@pytest.mark.parametrize(
    ("tool_name", "value", "model_mismatch"),
    [
        (
            ToolId("gmail.send_draft"),
            _gmail(),
            "Model commentary says the recipient is attacker@example.invalid.",
        ),
        (
            ToolId("gmail.send_draft"),
            _gmail(),
            "Model commentary substitutes a harmless subject.",
        ),
        (
            ToolId("gmail.send_draft"),
            _gmail(),
            "Model commentary omits the complete body.",
        ),
        (
            ToolId("calendar.create_event"),
            CalendarCreateEventInput(
                calendar_id="shared@example.invalid",
                event=_event(),
                notify_attendees=True,
            ),
            "Model commentary names a private calendar and no attendees.",
        ),
        (
            ToolId("calendar.update_event"),
            CalendarUpdateEventInput(
                expected=_snapshot(),
                replacement=_event().model_copy(update={"summary": "Replacement"}),
                notify_attendees=True,
            ),
            "Model commentary claims that times and reminders do not change.",
        ),
    ],
)
def test_host_rendering_rejects_five_model_mismatch_attacks(
    tool_name: ToolId,
    value: GmailSendDraftInput | CalendarCreateEventInput | CalendarUpdateEventInput,
    model_mismatch: str,
) -> None:
    presentation = render_approval(ACTION_ID, tool_name, value)

    assert _payload(presentation.attachment.content) == {
        "action_id": str(ACTION_ID),
        "arguments": value.model_dump(mode="json"),
        "tool_name": str(tool_name),
    }
    assert model_mismatch not in presentation.content
    assert model_mismatch.encode() not in presentation.attachment.content


@pytest.mark.parametrize(
    ("tool_name", "value"),
    [
        (
            ToolId("calendar.create_event"),
            CalendarCreateEventInput(
                calendar_id="shared@example.invalid",
                event=_event(),
                notify_attendees=True,
            ),
        ),
        (
            ToolId("calendar.update_event"),
            CalendarUpdateEventInput(
                expected=_snapshot(),
                replacement=CalendarWritableEvent(
                    summary="Replacement title",
                    description=None,
                    location=None,
                    start=AllDayEventTime(date=date(2026, 9, 10)),
                    end=AllDayEventTime(date=date(2026, 9, 11)),
                    recurrence=(),
                    attendees=(),
                    use_default_reminders=True,
                    reminders=(),
                ),
                notify_attendees=False,
            ),
        ),
        (
            ToolId("calendar.delete_event"),
            CalendarDeleteEventInput(
                expected=_snapshot(),
                notify_attendees=True,
            ),
        ),
    ],
)
def test_calendar_renderers_include_every_exact_stored_value(
    tool_name: ToolId,
    value: CalendarCreateEventInput
    | CalendarUpdateEventInput
    | CalendarDeleteEventInput,
) -> None:
    presentation = render_approval(ACTION_ID, tool_name, value)

    assert _payload(presentation.attachment.content) == {
        "action_id": str(ACTION_ID),
        "arguments": value.model_dump(mode="json"),
        "tool_name": str(tool_name),
    }
    assert len(presentation.content) <= 2_000


def test_long_email_body_is_complete_in_one_bounded_utf8_attachment() -> None:
    body = ("界\n" * 20_000) + "final byte"
    value = _gmail(body)

    presentation = render_approval(ACTION_ID, ToolId("gmail.send_draft"), value)

    assert len(presentation.attachment.content) <= APPROVAL_ATTACHMENT_MAX_BYTES
    payload = _payload(presentation.attachment.content)
    arguments = cast("dict[str, object]", payload["arguments"])
    content = cast("dict[str, object]", arguments["content"])
    assert content["body_text"] == body
    assert presentation.attachment.content.decode("utf-8").endswith("}\n")


def test_renderer_covers_a_valid_near_input_limit_email() -> None:
    address = "a" * 63 + "@" + ".".join(("b" * 60,) * 4) + ".com"
    mailbox = Mailbox(name="\\" * 320, address=address)
    value = GmailSendDraftInput(
        draft_id="d" * 1_024,
        thread_id="t" * 1_024,
        jarvis_effect_id="a" * 64,
        content=GmailContent(
            to=(mailbox,) * 50,
            cc=(mailbox,) * 50,
            bcc=(mailbox,) * 50,
            subject="\x01" * 998,
            body_text="\x01" * 17_000,
            reply_to=None,
        ),
    )
    assert len(canonical_json_bytes(value.model_dump(mode="json"))) <= 262_144

    presentation = render_approval(ACTION_ID, ToolId("gmail.send_draft"), value)

    assert len(presentation.attachment.content) <= APPROVAL_ATTACHMENT_MAX_BYTES
    arguments = cast(
        "dict[str, object]", _payload(presentation.attachment.content)["arguments"]
    )
    assert arguments == value.model_dump(mode="json")


def test_missing_renderer_and_argument_type_mismatch_fail_closed() -> None:
    with pytest.raises(ApprovalRenderError, match="no host renderer"):
        render_approval(ACTION_ID, ToolId("gmail.create_draft"), _gmail())
    with pytest.raises(ApprovalRenderError, match="wrong type"):
        render_approval(ACTION_ID, ToolId("gmail.send_draft"), _snapshot())

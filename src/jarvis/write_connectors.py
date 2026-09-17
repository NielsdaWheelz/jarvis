"""Bounded host-owned Google write connectors."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Literal, Protocol, cast
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import ValidationError

from jarvis.connectors import MAX_PROVIDER_BODY_BYTES
from jarvis.read_tools import (
    CALENDAR_API_BASE_URL,
    GMAIL_API_BASE_URL,
    ConnectorFailure,
)
from jarvis.write_tools import (
    AllDayEventTime,
    CalendarCreateEventInput,
    CalendarCreateEventSuccess,
    CalendarDeleteEventInput,
    CalendarDeleteEventSuccess,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarUpdateEventSuccess,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    GmailSendDraftInput,
    GmailSendDraftSuccess,
    GmailUpdateDraftInput,
    Mailbox,
    Reminder,
    TimedEventTime,
    WriteAttemptBudget,
    WriteConnectorFailure,
    WriteResponse,
)

RECONCILIATION_DELAYS_SECONDS = (0.0, 2.0, 8.0)
_GMAIL_CREATE_SCAN_PAGE_SIZE = 8
_GMAIL_CREATE_SCAN_MAX_PAGES = 5
_GMAIL_CREATE_SCAN_MAX_DRAFTS = 40
_GMAIL_CREATE_SCAN_MAX_RAW_GETS = 40
_GMAIL_CREATE_SCAN_MAX_BYTES = 16 * 1024 * 1024
_GMAIL_CREATE_SCAN_MAX_SECONDS = 30.0
_MAX_THREAD_MESSAGES = 100
_GMAIL_SEND_MAX_BYTES = 16 * 1024 * 1024
_GMAIL_SEND_MAX_SECONDS = 30.0


class GoogleAccessTokens(Protocol):
    async def access_token(self) -> tuple[str, int]: ...

    def invalidate_access_token(self) -> None: ...


class GmailUpdateBasisStager(Protocol):
    async def __call__(
        self,
        *,
        action_id: UUID,
        draft_id: str,
        thread_id: str,
        jarvis_effect_id: str,
        old_content_digest: str,
    ) -> object: ...


class ActionExternalAttemptStager(Protocol):
    async def __call__(
        self,
        *,
        action_id: UUID,
        actual_external_attempts: int,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ReconciliationResult[ValueT]:
    outcome: Literal["succeeded", "absent", "uncertain"]
    evidence: str
    value: ValueT | None = None

    def __post_init__(self) -> None:
        if (self.outcome == "succeeded") != (self.value is not None):
            raise ValueError("reconciliation value does not match its outcome")


@dataclass(frozen=True, slots=True)
class CalendarCurrentSnapshot:
    outcome: Literal["found", "not_found", "unsupported", "unavailable"]
    value: CalendarEventSnapshot | None
    attempts: int

    def __post_init__(self) -> None:
        if (self.outcome == "found") != (self.value is not None):
            raise ValueError("current Calendar value does not match its outcome")
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("Calendar read attempts are invalid")


@dataclass(frozen=True, slots=True)
class GmailUpdateReconciliationBasis:
    type: Literal["gmail_update_reconciliation_v1"]
    draft_id: str
    thread_id: str
    jarvis_effect_id: str
    old_content_digest: str

    def __post_init__(self) -> None:
        if (
            not self.draft_id
            or len(self.draft_id.encode()) > 1_024
            or not self.thread_id
            or len(self.thread_id.encode()) > 1_024
            or len(self.jarvis_effect_id) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.jarvis_effect_id
            )
            or len(self.old_content_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.old_content_digest
            )
        ):
            raise ValueError("Gmail update reconciliation basis is invalid")


@dataclass(frozen=True, slots=True)
class _ObservedDraft:
    result: GmailDraftSuccess
    content: GmailContent


@dataclass(frozen=True, slots=True)
class _GmailDraftScan:
    drafts: tuple[_ObservedDraft, ...]
    complete: bool
    next_page_token: Literal["absent", "present", "invalid", "unknown"]
    malformed: bool


@dataclass(frozen=True, slots=True)
class _GmailThreadScan:
    messages: tuple[_ObservedDraft, ...]
    bounded_complete: bool
    thread_complete: bool


@dataclass(slots=True)
class _ResponseByteBudget:
    remaining: int

    def consume(self, size: int) -> bool:
        if size > self.remaining:
            self.remaining = 0
            return False
        self.remaining -= size
        return True


@dataclass(frozen=True, slots=True)
class _CancelledCalendarEvent:
    pass


def _gmail_create_scan_evidence(
    reason: str, round_number: int, scan: _GmailDraftScan
) -> str:
    complete = "true" if scan.complete else "false"
    return (
        f"gmail-create-{reason};rounds={round_number};complete={complete};"
        f"nextPageToken={scan.next_page_token}"
    )


def gmail_effect_id(action_id: UUID) -> str:
    return hashlib.sha256(f"jarvis-gmail-v1:{action_id}".encode()).hexdigest()


def calendar_event_id(action_id: UUID) -> str:
    return hashlib.sha256(f"jarvis-calendar-v1:{action_id}".encode()).hexdigest()[:32]


def gmail_content_digest(content: GmailContent) -> str:
    value = content.model_dump(mode="json")
    reply = cast("dict[str, object] | None", value["reply_to"])
    if reply is not None:
        reply.pop("parent_message_id")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mailbox(value: Mailbox) -> Address:
    local, _, domain = value.address.rpartition("@")
    return Address(display_name=value.name or "", username=local, domain=domain)


def _gmail_raw(content: GmailContent, effect_id: str) -> str:
    message = EmailMessage(policy=policy.SMTP)
    message["To"] = tuple(_mailbox(item) for item in content.to)
    if content.cc:
        message["Cc"] = tuple(_mailbox(item) for item in content.cc)
    if content.bcc:
        message["Bcc"] = tuple(_mailbox(item) for item in content.bcc)
    message["Subject"] = content.subject
    message["X-Jarvis-Effect-ID"] = effect_id
    if content.reply_to is not None:
        message["In-Reply-To"] = content.reply_to.parent_rfc822_message_id
        message["References"] = content.reply_to.parent_rfc822_message_id
    message["MIME-Version"] = "1.0"
    message["Content-Type"] = "text/plain; charset=utf-8"
    message["Content-Transfer-Encoding"] = "base64"
    message.set_payload(base64.encodebytes(content.body_text.encode()).decode("ascii"))
    return base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")


def _decode_raw(value: str) -> bytes:
    if len(value) > 4 * MAX_PROVIDER_BODY_BYTES // 3 + 4:
        raise ValueError("raw Gmail message is oversized")
    try:
        return base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ValueError("raw Gmail message is malformed") from None


def _parsed_mailboxes(message: EmailMessage, name: str) -> tuple[Mailbox, ...]:
    values = message.get_all(name, [])
    addresses: list[Mailbox] = []
    for value in values:
        for address in value.addresses:
            addresses.append(
                Mailbox(name=address.display_name or None, address=address.addr_spec)
            )
    return tuple(addresses)


def _parse_draft(
    payload: dict[str, object], *, observed_at: datetime
) -> _ObservedDraft:
    draft_id = _string(payload, "id")
    message_value = payload.get("message")
    if not isinstance(message_value, dict):
        raise ValueError("Gmail draft message is malformed")
    message_payload = cast("dict[str, object]", message_value)
    message_id = _string(message_payload, "id")
    thread_id = _string(message_payload, "threadId")
    raw_value = _string(message_payload, "raw")
    parsed = BytesParser(policy=policy.default).parsebytes(_decode_raw(raw_value))
    if parsed.get_content_type() != "text/plain":
        raise ValueError("Gmail draft MIME shape is unsupported")
    effects = parsed.get_all("X-Jarvis-Effect-ID", [])
    if len(effects) != 1:
        raise ValueError("Gmail effect header is absent or duplicated")
    effect = str(effects[0])
    if len(effect) != 64 or any(
        character not in "0123456789abcdef" for character in effect
    ):
        raise ValueError("Gmail effect header is malformed")
    body = parsed.get_payload(decode=True)
    if not isinstance(body, bytes):
        raise ValueError("Gmail draft body is malformed")
    charset = parsed.get_content_charset("utf-8") or "utf-8"
    body_text = body.decode(charset)
    in_reply_to = parsed.get("In-Reply-To")
    reply_to = None
    if in_reply_to is not None:
        from jarvis.write_tools import GmailReplyTo

        reply_to = GmailReplyTo(
            thread_id=thread_id,
            parent_message_id="not-retained-by-gmail",
            parent_rfc822_message_id=str(in_reply_to),
        )
    content = GmailContent(
        to=_parsed_mailboxes(parsed, "To"),
        cc=_parsed_mailboxes(parsed, "Cc"),
        bcc=_parsed_mailboxes(parsed, "Bcc"),
        subject=str(parsed.get("Subject", "")),
        body_text=body_text,
        reply_to=reply_to,
    )
    result = GmailDraftSuccess(
        draft_id=draft_id,
        message_id=message_id,
        thread_id=thread_id,
        jarvis_effect_id=effect,
        content_digest=gmail_content_digest(content),
        observed_at=observed_at,
    )
    return _ObservedDraft(result, content)


def _raw_effect(payload: dict[str, object]) -> str | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Gmail draft message is malformed")
    raw = _decode_raw(_string(cast("dict[str, object]", message), "raw"))
    parsed = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    effects = parsed.get_all("X-Jarvis-Effect-ID", [])
    if not effects:
        return None
    if len(effects) != 1:
        raise ValueError("Gmail effect header is duplicated")
    effect = str(effects[0])
    if len(effect) != 64 or any(
        character not in "0123456789abcdef" for character in effect
    ):
        raise ValueError("Gmail effect header is malformed")
    return effect


def _string(value: dict[str, object], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise ValueError(f"provider field {name} is malformed")
    if len(item.encode()) > 16_384:
        raise ValueError(f"provider field {name} is oversized")
    return item


def _optional_string(value: dict[str, object], name: str) -> str | None:
    item = value.get(name)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError(f"provider field {name} is malformed")
    return item


def _event_time(value: object) -> TimedEventTime | AllDayEventTime:
    if not isinstance(value, dict):
        raise ValueError("Calendar event time is malformed")
    item = cast("dict[str, object]", value)
    date_time = item.get("dateTime")
    if isinstance(date_time, str):
        zone = item.get("timeZone", "UTC")
        if not isinstance(zone, str):
            raise ValueError("Calendar event time zone is malformed")
        return TimedEventTime(
            date_time=datetime.fromisoformat(date_time.replace("Z", "+00:00")),
            time_zone=zone,
        )
    day = item.get("date")
    if isinstance(day, str):
        return AllDayEventTime(date=datetime.strptime(day, "%Y-%m-%d").date())
    raise ValueError("Calendar event time is malformed")


def _calendar_payload(
    value: CalendarWritableEvent, *, event_id: str | None
) -> dict[str, object]:
    def event_time(item: TimedEventTime | AllDayEventTime) -> dict[str, str]:
        if isinstance(item, TimedEventTime):
            return {"dateTime": item.date_time.isoformat(), "timeZone": item.time_zone}
        return {"date": item.date.isoformat()}

    payload: dict[str, object] = {
        "summary": value.summary,
        "description": value.description,
        "location": value.location,
        "start": event_time(value.start),
        "end": event_time(value.end),
        "recurrence": list(value.recurrence),
        "attendees": [{"email": item.address} for item in value.attendees],
        "reminders": {
            "useDefault": value.use_default_reminders,
            "overrides": [item.model_dump(mode="json") for item in value.reminders],
        },
    }
    if event_id is not None:
        payload["id"] = event_id
    return payload


def _calendar_snapshot(
    calendar_id: str, payload: dict[str, object]
) -> CalendarEventSnapshot:
    status = _string(payload, "status")
    if status not in {"confirmed", "tentative"}:
        raise ValueError("Calendar event type is unsupported")
    attendees_value = payload.get("attendees", [])
    if not isinstance(attendees_value, list):
        raise ValueError("Calendar attendees are malformed")
    attendees: list[Mailbox] = []
    for raw in cast("list[object]", attendees_value):
        if not isinstance(raw, dict):
            raise ValueError("Calendar attendee is malformed")
        item = cast("dict[str, object]", raw)
        attendees.append(
            Mailbox(
                name=_optional_string(item, "displayName"),
                address=_string(item, "email"),
            )
        )
    reminders_value = payload.get("reminders", {})
    if not isinstance(reminders_value, dict):
        raise ValueError("Calendar reminders are malformed")
    reminders_payload = cast("dict[str, object]", reminders_value)
    overrides_value = reminders_payload.get("overrides", [])
    if not isinstance(overrides_value, list):
        raise ValueError("Calendar reminder overrides are malformed")
    reminders: list[Reminder] = []
    for raw in cast("list[object]", overrides_value):
        if not isinstance(raw, dict):
            raise ValueError("Calendar reminder is malformed")
        reminder = cast("dict[str, object]", raw)
        method = reminder.get("method")
        minutes = reminder.get("minutes")
        if method not in {"email", "popup"} or type(minutes) is not int:
            raise ValueError("Calendar reminder is malformed")
        reminders.append(
            Reminder(
                method=cast("Literal['email', 'popup']", method),
                minutes=minutes,
            )
        )
    recurrence_value = payload.get("recurrence", [])
    if not isinstance(recurrence_value, list) or any(
        not isinstance(item, str) for item in cast("list[object]", recurrence_value)
    ):
        raise ValueError("Calendar recurrence is malformed")
    organizer_value = payload.get("organizer")
    organizer = None
    if organizer_value is not None:
        if not isinstance(organizer_value, dict):
            raise ValueError("Calendar organizer is malformed")
        organizer_payload = cast("dict[str, object]", organizer_value)
        address = organizer_payload.get("email")
        if address is not None:
            if not isinstance(address, str):
                raise ValueError("Calendar organizer is malformed")
            organizer = Mailbox(
                name=_optional_string(organizer_payload, "displayName"),
                address=address,
            )
    updated = datetime.fromisoformat(_string(payload, "updated").replace("Z", "+00:00"))
    return CalendarEventSnapshot(
        calendar_id=calendar_id,
        event_id=_string(payload, "id"),
        etag=_string(payload, "etag"),
        status=cast("Literal['confirmed', 'tentative']", status),
        writable=CalendarWritableEvent(
            summary=_optional_string(payload, "summary") or "",
            description=_optional_string(payload, "description"),
            location=_optional_string(payload, "location"),
            start=_event_time(payload.get("start")),
            end=_event_time(payload.get("end")),
            recurrence=tuple(cast("list[str]", recurrence_value)),
            attendees=tuple(attendees),
            use_default_reminders=bool(reminders_payload.get("useDefault", False)),
            reminders=tuple(reminders),
        ),
        organizer=organizer,
        updated_at=updated,
    )


def _valid_event(value: CalendarWritableEvent) -> bool:
    if type(value.start) is not type(value.end):
        return False
    if isinstance(value.start, TimedEventTime):
        assert isinstance(value.end, TimedEventTime)
        return value.start.date_time < value.end.date_time
    assert isinstance(value.start, AllDayEventTime)
    assert isinstance(value.end, AllDayEventTime)
    return value.start.date < value.end.date


def _normalized_writable(value: CalendarWritableEvent) -> CalendarWritableEvent:
    return value.model_copy(
        update={
            "attendees": tuple(
                attendee.model_copy(update={"name": None})
                for attendee in value.attendees
            )
        }
    )


class GoogleWriteConnector:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        tokens: GoogleAccessTokens,
        stage_gmail_update_basis: GmailUpdateBasisStager,
        stage_external_attempts: ActionExternalAttemptStager,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._stage_gmail_update_basis = stage_gmail_update_basis
        self._stage_external_attempts = stage_external_attempts
        self._now = now
        self._sleep = sleep

    async def calendar_current_snapshot(
        self, calendar_id: str, event_id: str
    ) -> CalendarCurrentSnapshot:
        try:
            payload, attempts = await self._request_json(
                "GET",
                f"{CALENDAR_API_BASE_URL}/calendars/{quote(calendar_id, safe='')}"
                f"/events/{quote(event_id, safe='')}",
                errors={404: "event_not_found", 429: "rate_limited"},
            )
        except WriteConnectorFailure as exc:
            outcome: Literal["not_found", "unavailable"] = (
                "not_found" if exc.code == "event_not_found" else "unavailable"
            )
            return CalendarCurrentSnapshot(outcome, None, exc.attempts)
        if payload.get("status") == "cancelled":
            return CalendarCurrentSnapshot("unsupported", None, attempts)
        try:
            value = _calendar_snapshot(calendar_id, payload)
        except (TypeError, ValueError, ValidationError):
            return CalendarCurrentSnapshot("unavailable", None, attempts)
        if value.event_id != event_id:
            return CalendarCurrentSnapshot("unavailable", None, attempts)
        return CalendarCurrentSnapshot("found", value, attempts)

    async def gmail_create_draft(
        self,
        value: GmailCreateDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        attempts = await self._validate_parent(
            value.content,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=0,
        )
        jarvis_id = gmail_effect_id(effect_id)
        body: dict[str, object] = {
            "message": {"raw": _gmail_raw(value.content, jarvis_id)}
        }
        if value.content.reply_to is not None:
            cast("dict[str, object]", body["message"])["threadId"] = (
                value.content.reply_to.thread_id
            )
        payload, used = await self._request_json(
            "POST",
            f"{GMAIL_API_BASE_URL}/users/me/drafts",
            body=body,
            mutation=True,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=attempts,
            errors={
                400: "invalid_recipient",
                404: "thread_not_found",
                409: "conflict",
                429: "rate_limited",
            },
        )
        attempts += used
        try:
            result = self._gmail_result(payload, value.content, jarvis_id)
            if (
                value.content.reply_to is not None
                and result.thread_id != value.content.reply_to.thread_id
            ):
                raise ValueError("Gmail returned a different thread")
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Gmail draft creation needs reconciliation") from exc
        return WriteResponse(result, attempts)

    async def gmail_update_draft(
        self,
        value: GmailUpdateDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        observed, attempts = await self._get_draft(
            value.draft_id,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=0,
        )
        if observed.result.content_digest != value.expected_content_digest:
            raise WriteConnectorFailure("draft_changed", attempts=attempts)
        attempts += await self._validate_parent(
            value.replacement,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=attempts,
        )
        jarvis_id = observed.result.jarvis_effect_id
        await self._stage_gmail_update_basis(
            action_id=effect_id,
            draft_id=value.draft_id,
            thread_id=observed.result.thread_id,
            jarvis_effect_id=jarvis_id,
            old_content_digest=observed.result.content_digest,
        )
        message: dict[str, object] = {"raw": _gmail_raw(value.replacement, jarvis_id)}
        if value.replacement.reply_to is not None:
            message["threadId"] = value.replacement.reply_to.thread_id
        payload, used = await self._request_json(
            "PUT",
            f"{GMAIL_API_BASE_URL}/users/me/drafts/{quote(value.draft_id, safe='')}",
            body={"id": value.draft_id, "message": message},
            mutation=True,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=attempts,
            errors={
                400: "thread_mismatch",
                404: "draft_not_found",
                409: "draft_changed",
                412: "draft_changed",
                429: "rate_limited",
            },
        )
        attempts += used
        try:
            result = self._gmail_result(payload, value.replacement, jarvis_id)
            if result.draft_id != value.draft_id:
                raise ValueError("Gmail returned a different draft")
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Gmail draft update needs reconciliation") from exc
        return WriteResponse(result, attempts)

    async def gmail_send_draft(
        self,
        value: GmailSendDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailSendDraftSuccess]:
        observed, attempts = await self._get_draft(
            value.draft_id,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=0,
        )
        if (
            observed.result.draft_id != value.draft_id
            or observed.result.thread_id != value.thread_id
            or observed.result.jarvis_effect_id != value.jarvis_effect_id
            or observed.result.content_digest != gmail_content_digest(value.content)
        ):
            raise WriteConnectorFailure("draft_changed", attempts=attempts)
        payload, used = await self._request_json(
            "POST",
            f"{GMAIL_API_BASE_URL}/users/me/drafts/send",
            body={"id": value.draft_id},
            mutation=True,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=attempts,
            errors={
                400: "invalid_recipient",
                404: "draft_not_found",
                409: "draft_changed",
                429: "rate_limited",
            },
        )
        attempts += used
        try:
            result = GmailSendDraftSuccess(
                sent_message_id=_string(payload, "id"),
                thread_id=_string(payload, "threadId"),
                jarvis_effect_id=value.jarvis_effect_id,
                content_digest=gmail_content_digest(value.content),
                sent_at=self._now_utc(),
            )
            if result.thread_id != value.thread_id:
                raise ValueError("Gmail returned a different thread")
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Gmail draft send needs reconciliation") from exc
        return WriteResponse(result, attempts)

    async def calendar_create_event(
        self,
        value: CalendarCreateEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarCreateEventSuccess]:
        if not _valid_event(value.event):
            raise WriteConnectorFailure("invalid_event", attempts=0)
        event_id = calendar_event_id(effect_id)
        calendar = quote(value.calendar_id, safe="")
        try:
            payload, attempts = await self._request_json(
                "POST",
                f"{CALENDAR_API_BASE_URL}/calendars/{calendar}/events",
                params={"sendUpdates": "all" if value.notify_attendees else "none"},
                body=_calendar_payload(value.event, event_id=event_id),
                mutation=True,
                action_id=effect_id,
                attempt_budget=attempt_budget,
                errors={
                    400: "invalid_event",
                    404: "calendar_not_found",
                    409: "event_id_conflict",
                    429: "rate_limited",
                },
            )
        except WriteConnectorFailure as exc:
            if exc.code == "event_id_conflict":
                raise TimeoutError(
                    "Calendar create conflict needs reconciliation"
                ) from exc
            raise
        try:
            event = _calendar_snapshot(value.calendar_id, payload)
            if event.event_id != event_id or event.writable != _normalized_writable(
                value.event
            ):
                raise ValueError("Calendar returned a conflicting event")
            result = CalendarCreateEventSuccess(event=event, created_at=self._now_utc())
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Calendar create needs reconciliation") from exc
        return WriteResponse(result, attempts)

    async def calendar_update_event(
        self,
        value: CalendarUpdateEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarUpdateEventSuccess]:
        if not _valid_event(value.replacement):
            raise WriteConnectorFailure("invalid_event", attempts=0)
        expected = value.expected
        calendar = quote(expected.calendar_id, safe="")
        event = quote(expected.event_id, safe="")
        payload, attempts = await self._request_json(
            "PATCH",
            f"{CALENDAR_API_BASE_URL}/calendars/{calendar}/events/{event}",
            params={"sendUpdates": "all" if value.notify_attendees else "none"},
            headers={"If-Match": expected.etag},
            body=_calendar_payload(value.replacement, event_id=None),
            mutation=True,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            errors={
                400: "invalid_event",
                404: "event_not_found",
                409: "event_changed",
                412: "event_changed",
                429: "rate_limited",
            },
        )
        try:
            observed = _calendar_snapshot(expected.calendar_id, payload)
            if (
                observed.event_id != expected.event_id
                or observed.writable != _normalized_writable(value.replacement)
            ):
                raise ValueError("Calendar returned a conflicting event")
            result = CalendarUpdateEventSuccess(
                event=observed, updated_at=self._now_utc()
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Calendar update needs reconciliation") from exc
        return WriteResponse(result, attempts)

    async def calendar_delete_event(
        self,
        value: CalendarDeleteEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarDeleteEventSuccess]:
        expected = value.expected
        calendar = quote(expected.calendar_id, safe="")
        event = quote(expected.event_id, safe="")
        attempts = await self._request_empty(
            "DELETE",
            f"{CALENDAR_API_BASE_URL}/calendars/{calendar}/events/{event}",
            params={"sendUpdates": "all" if value.notify_attendees else "none"},
            headers={"If-Match": expected.etag},
            action_id=effect_id,
            attempt_budget=attempt_budget,
            errors={
                404: "event_not_found",
                409: "event_changed",
                412: "event_changed",
                429: "rate_limited",
            },
        )
        return WriteResponse(
            CalendarDeleteEventSuccess(
                calendar_id=expected.calendar_id,
                event_id=expected.event_id,
                prior_etag=expected.etag,
                deleted_at=self._now_utc(),
            ),
            attempts,
        )

    async def reconcile_calendar_create(
        self, value: CalendarCreateEventInput, effect_id: UUID
    ) -> ReconciliationResult[CalendarCreateEventSuccess]:
        event_id = calendar_event_id(effect_id)
        observations = await self._calendar_observations(value.calendar_id, event_id)
        if any(
            isinstance(item, CalendarEventSnapshot)
            and item.writable != _normalized_writable(value.event)
            for item in observations
        ):
            return ReconciliationResult("uncertain", "conflicting-event-at-effect-id")
        if any(isinstance(item, _CancelledCalendarEvent) for item in observations):
            return ReconciliationResult("uncertain", "cancelled-event-at-effect-id")
        matches = [
            item for item in observations if isinstance(item, CalendarEventSnapshot)
        ]
        if matches:
            return ReconciliationResult(
                "succeeded",
                "exact-event-at-effect-id",
                CalendarCreateEventSuccess(
                    event=matches[-1], created_at=self._now_utc()
                ),
            )
        if len(observations) == len(RECONCILIATION_DELAYS_SECONDS):
            return ReconciliationResult("absent", "event-absent-at-all-observations")
        return ReconciliationResult("uncertain", "calendar-observations-incomplete")

    async def reconcile_calendar_update(
        self, value: CalendarUpdateEventInput
    ) -> ReconciliationResult[CalendarUpdateEventSuccess]:
        expected = value.expected
        observations = await self._calendar_observations(
            expected.calendar_id, expected.event_id
        )
        for item in observations:
            if isinstance(
                item, CalendarEventSnapshot
            ) and item.writable == _normalized_writable(value.replacement):
                return ReconciliationResult(
                    "succeeded",
                    "exact-replacement-observed",
                    CalendarUpdateEventSuccess(event=item, updated_at=self._now_utc()),
                )
            if isinstance(item, _CancelledCalendarEvent):
                return ReconciliationResult("uncertain", "event-was-cancelled")
            if isinstance(item, CalendarEventSnapshot) and item != expected:
                return ReconciliationResult("uncertain", "third-event-state-observed")
        if len(observations) == len(RECONCILIATION_DELAYS_SECONDS) and all(
            item == expected for item in observations
        ):
            return ReconciliationResult("absent", "expected-event-remained-unchanged")
        return ReconciliationResult("uncertain", "calendar-observations-incomplete")

    async def reconcile_calendar_delete(
        self, value: CalendarDeleteEventInput
    ) -> ReconciliationResult[CalendarDeleteEventSuccess]:
        expected = value.expected
        observations = await self._calendar_observations(
            expected.calendar_id, expected.event_id
        )
        if observations and (
            observations[-1] is None
            or isinstance(observations[-1], _CancelledCalendarEvent)
        ):
            return ReconciliationResult(
                "succeeded",
                "event-absent",
                CalendarDeleteEventSuccess(
                    calendar_id=expected.calendar_id,
                    event_id=expected.event_id,
                    prior_etag=expected.etag,
                    deleted_at=self._now_utc(),
                ),
            )
        if any(
            isinstance(item, CalendarEventSnapshot) and item != expected
            for item in observations
        ):
            return ReconciliationResult("uncertain", "changed-event-remains")
        if len(observations) == len(RECONCILIATION_DELAYS_SECONDS) and all(
            item == expected for item in observations
        ):
            return ReconciliationResult("absent", "expected-event-remained-unchanged")
        return ReconciliationResult("uncertain", "calendar-observations-incomplete")

    async def reconcile_gmail_create(
        self, value: GmailCreateDraftInput, effect_id: UUID
    ) -> ReconciliationResult[GmailDraftSuccess]:
        jarvis_id = gmail_effect_id(effect_id)
        expected_digest = gmail_content_digest(value.content)
        byte_budget = _ResponseByteBudget(_GMAIL_CREATE_SCAN_MAX_BYTES)
        strongest_reason = "no-match"
        strongest_scan = _GmailDraftScan((), False, "unknown", False)
        rounds_completed = 0
        try:
            async with asyncio.timeout(_GMAIL_CREATE_SCAN_MAX_SECONDS):
                for round_number, delay in enumerate(
                    RECONCILIATION_DELAYS_SECONDS, start=1
                ):
                    rounds_completed = round_number
                    if delay:
                        await self._sleep(delay)
                    try:
                        scan = await self._bounded_draft_scan(
                            jarvis_id, byte_budget=byte_budget
                        )
                    except WriteConnectorFailure:
                        if strongest_reason == "no-match":
                            strongest_reason = "incomplete"
                            strongest_scan = _GmailDraftScan(
                                (), False, "unknown", False
                            )
                        if byte_budget.remaining == 0:
                            break
                        continue
                    exact = [
                        item
                        for item in scan.drafts
                        if item.result.jarvis_effect_id == jarvis_id
                        and item.result.content_digest == expected_digest
                    ]
                    conflicts = [
                        item
                        for item in scan.drafts
                        if item.result.jarvis_effect_id == jarvis_id
                        and item.result.content_digest != expected_digest
                    ]
                    if len(exact) > 1 or conflicts:
                        strongest_reason = "conflicting-matches"
                        strongest_scan = scan
                        continue
                    if strongest_reason != "conflicting-matches" and len(exact) == 1:
                        return ReconciliationResult(
                            "succeeded",
                            _gmail_create_scan_evidence(
                                "one-exact-match", round_number, scan
                            ),
                            exact[0].result,
                        )
                    if strongest_reason == "conflicting-matches":
                        continue
                    if scan.malformed:
                        if strongest_reason != "malformed":
                            strongest_reason = "malformed"
                            strongest_scan = scan
                    elif not scan.complete and strongest_reason == "no-match":
                        strongest_reason = "incomplete"
                        strongest_scan = scan
                    elif strongest_reason == "no-match":
                        strongest_reason = "no-match"
                        strongest_scan = scan
                    if byte_budget.remaining == 0:
                        if strongest_reason == "no-match":
                            strongest_reason = "incomplete"
                            strongest_scan = _GmailDraftScan(
                                scan.drafts,
                                False,
                                scan.next_page_token,
                                scan.malformed,
                            )
                        break
        except TimeoutError:
            return ReconciliationResult(
                "uncertain",
                "gmail-create-timeout;complete=false;nextPageToken=unknown",
            )
        return ReconciliationResult(
            "uncertain",
            _gmail_create_scan_evidence(
                strongest_reason,
                rounds_completed,
                strongest_scan,
            ),
        )

    async def reconcile_gmail_update(
        self,
        value: GmailUpdateDraftInput,
        basis: GmailUpdateReconciliationBasis,
    ) -> ReconciliationResult[GmailDraftSuccess]:
        if (
            basis.type != "gmail_update_reconciliation_v1"
            or basis.draft_id != value.draft_id
            or basis.old_content_digest != value.expected_content_digest
        ):
            raise ValueError("Gmail update reconciliation basis conflicts")
        desired = gmail_content_digest(value.replacement)
        old_observations = 0
        completed = 0
        for delay in RECONCILIATION_DELAYS_SECONDS:
            if delay:
                await self._sleep(delay)
            try:
                observed, _ = await self._get_draft(value.draft_id)
            except WriteConnectorFailure as exc:
                if exc.code == "draft_not_found":
                    completed += 1
                    try:
                        scan = await self._thread_messages(
                            basis.thread_id,
                            basis.jarvis_effect_id,
                            draft_id=basis.draft_id,
                        )
                    except WriteConnectorFailure:
                        continue
                    exact = [
                        item
                        for item in scan.messages
                        if item.result.content_digest == desired
                    ]
                    conflicts = [
                        item
                        for item in scan.messages
                        if item.result.content_digest != desired
                    ]
                    if len(exact) == 1 and not conflicts and scan.bounded_complete:
                        return ReconciliationResult(
                            "succeeded",
                            "one-exact-message-in-known-thread",
                            exact[0].result,
                        )
                    if len(exact) > 1 or conflicts:
                        return ReconciliationResult(
                            "uncertain", "conflicting-known-thread-matches"
                        )
                continue
            completed += 1
            if observed.result.jarvis_effect_id != basis.jarvis_effect_id:
                return ReconciliationResult("uncertain", "draft-effect-header-changed")
            if observed.result.content_digest == desired:
                return ReconciliationResult(
                    "succeeded", "exact-updated-draft", observed.result
                )
            if observed.result.content_digest == basis.old_content_digest:
                old_observations += 1
                continue
            return ReconciliationResult("uncertain", "third-draft-state-observed")
        if completed == 3 and old_observations == 3:
            return ReconciliationResult("absent", "exact-old-draft-remained-unchanged")
        return ReconciliationResult(
            "uncertain", "draft-missing-or-observations-incomplete"
        )

    async def reconcile_gmail_send(
        self, value: GmailSendDraftInput
    ) -> ReconciliationResult[GmailSendDraftSuccess]:
        expected_digest = gmail_content_digest(value.content)
        byte_budget = _ResponseByteBudget(_GMAIL_SEND_MAX_BYTES)
        safe_absence_observations = 0
        completed_observations = 0
        conflicting_evidence = False
        conflicting_draft = False
        try:
            async with asyncio.timeout(_GMAIL_SEND_MAX_SECONDS):
                for delay in RECONCILIATION_DELAYS_SECONDS:
                    if delay:
                        await self._sleep(delay)
                    draft: _ObservedDraft | None = None
                    draft_missing = False
                    try:
                        draft, _ = await self._get_draft(
                            value.draft_id, response_byte_budget=byte_budget
                        )
                    except WriteConnectorFailure as exc:
                        if exc.code == "draft_not_found":
                            draft_missing = True
                    try:
                        scan = await self._thread_messages(
                            value.thread_id,
                            value.jarvis_effect_id,
                            draft_id=value.draft_id,
                            response_byte_budget=byte_budget,
                        )
                    except WriteConnectorFailure:
                        if byte_budget.remaining == 0:
                            break
                        continue
                    completed_observations += 1
                    if draft is not None and (
                        draft.result.draft_id != value.draft_id
                        or draft.result.thread_id != value.thread_id
                        or draft.result.jarvis_effect_id != value.jarvis_effect_id
                        or draft.result.content_digest != expected_digest
                    ):
                        conflicting_draft = True
                    thread_evidence = [
                        item
                        for item in scan.messages
                        if draft is None
                        or item.result.message_id != draft.result.message_id
                    ]
                    conflicts = [
                        item
                        for item in thread_evidence
                        if item.result.content_digest != expected_digest
                        or item.result.thread_id != value.thread_id
                    ]
                    exact = [
                        item
                        for item in thread_evidence
                        if item.result.content_digest == expected_digest
                        and item.result.thread_id == value.thread_id
                    ]
                    if len(exact) > 1 or conflicts:
                        conflicting_evidence = True
                        if byte_budget.remaining == 0:
                            break
                        continue
                    if len(exact) == 1 and scan.bounded_complete:
                        if not conflicting_evidence and not conflicting_draft:
                            match = exact[0].result
                            return ReconciliationResult(
                                "succeeded",
                                "one-exact-message-in-known-thread",
                                GmailSendDraftSuccess(
                                    sent_message_id=match.message_id,
                                    thread_id=match.thread_id,
                                    jarvis_effect_id=match.jarvis_effect_id,
                                    content_digest=match.content_digest,
                                    sent_at=self._now_utc(),
                                ),
                            )
                    if draft is not None and scan.thread_complete and not exact:
                        safe_absence_observations += 1
                    elif draft_missing:
                        safe_absence_observations = -1
                    if byte_budget.remaining == 0:
                        break
        except TimeoutError:
            return ReconciliationResult(
                "uncertain",
                "gmail-send-reconciliation-elapsed-bound-with-incomplete-evidence",
            )
        if conflicting_evidence or conflicting_draft:
            return ReconciliationResult("uncertain", "conflicting-gmail-send-evidence")
        if completed_observations == len(
            RECONCILIATION_DELAYS_SECONDS
        ) and safe_absence_observations == len(RECONCILIATION_DELAYS_SECONDS):
            return ReconciliationResult(
                "absent", "exact-draft-remained-and-complete-known-thread-had-no-send"
            )
        return ReconciliationResult(
            "uncertain", "gmail-send-observations-incomplete-or-draft-missing"
        )

    async def _thread_messages(
        self,
        thread_id: str,
        target_effect_id: str,
        *,
        draft_id: str,
        response_byte_budget: _ResponseByteBudget | None = None,
    ) -> _GmailThreadScan:
        payload, attempts = await self._request_json(
            "GET",
            f"{GMAIL_API_BASE_URL}/users/me/threads/{quote(thread_id, safe='')}",
            params={"format": "minimal"},
            response_byte_budget=response_byte_budget,
            errors={404: "thread_not_found", 429: "rate_limited"},
        )
        if _string(payload, "id") != thread_id:
            raise WriteConnectorFailure("provider_unavailable", attempts=attempts)
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list):
            raise WriteConnectorFailure("provider_unavailable", attempts=attempts)
        raw_messages = cast("list[object]", raw_messages)
        thread_complete = len(raw_messages) <= _MAX_THREAD_MESSAGES
        messages: list[_ObservedDraft] = []
        seen_message_ids: set[str] = set()
        message_ids: list[str] = []
        for raw in raw_messages[:_MAX_THREAD_MESSAGES]:
            if not isinstance(raw, dict):
                return _GmailThreadScan(tuple(messages), False, False)
            item = cast("dict[str, object]", raw)
            try:
                message_id = _string(item, "id")
                if len(message_id.encode()) > 1_024 or message_id in seen_message_ids:
                    raise ValueError("Gmail thread message identity is malformed")
            except ValueError:
                return _GmailThreadScan(tuple(messages), False, False)
            seen_message_ids.add(message_id)
            message_ids.append(message_id)
        for message_id in message_ids:
            try:
                item, _ = await self._request_json(
                    "GET",
                    f"{GMAIL_API_BASE_URL}/users/me/messages/"
                    f"{quote(message_id, safe='')}",
                    params={"format": "raw"},
                    response_byte_budget=response_byte_budget,
                    errors={404: "provider_unavailable", 429: "rate_limited"},
                )
                labels_value = item.get("labelIds")
                if (
                    _string(item, "id") != message_id
                    or _string(item, "threadId") != thread_id
                    or not isinstance(labels_value, list)
                ):
                    raise ValueError("Gmail raw message is malformed")
                labels = cast("list[object]", labels_value)
                if (
                    len(labels) > 100
                    or any(
                        not isinstance(label, str)
                        or not label
                        or len(label.encode()) > 128
                        for label in labels
                    )
                    or len(set(cast("list[str]", labels))) != len(labels)
                ):
                    raise ValueError("Gmail raw message labels are malformed")
                wrapped: dict[str, object] = {"id": draft_id, "message": item}
                if _raw_effect(wrapped) != target_effect_id:
                    continue
                observed = _parse_draft(wrapped, observed_at=self._now_utc())
                messages.append(
                    _ObservedDraft(
                        observed.result,
                        observed.content,
                    )
                )
            except (TypeError, ValueError, ValidationError, WriteConnectorFailure):
                return _GmailThreadScan(tuple(messages), False, False)
        return _GmailThreadScan(tuple(messages), True, thread_complete)

    async def _validate_parent(
        self,
        content: GmailContent,
        *,
        action_id: UUID | None = None,
        attempt_budget: WriteAttemptBudget | None = None,
        prior_attempts: int = 0,
    ) -> int:
        if content.reply_to is None:
            return 0
        reply = content.reply_to
        payload, attempts = await self._request_json(
            "GET",
            f"{GMAIL_API_BASE_URL}/users/me/messages/"
            f"{quote(reply.parent_message_id, safe='')}",
            params={"format": "metadata", "metadataHeaders": "Message-ID"},
            action_id=action_id,
            attempt_budget=attempt_budget,
            prior_attempts=prior_attempts,
            errors={404: "thread_not_found", 429: "rate_limited"},
        )
        if _string(payload, "threadId") != reply.thread_id:
            raise WriteConnectorFailure("thread_mismatch", attempts=attempts)
        headers = payload.get("payload")
        if not isinstance(headers, dict):
            raise WriteConnectorFailure("provider_unavailable", attempts=attempts)
        raw_headers = cast("dict[str, object]", headers).get("headers", [])
        if not isinstance(raw_headers, list):
            raise WriteConnectorFailure("provider_unavailable", attempts=attempts)
        ids: list[object] = []
        for raw in cast("list[object]", raw_headers):
            if not isinstance(raw, dict):
                continue
            item = cast("dict[str, object]", raw)
            if str(item.get("name", "")).lower() == "message-id":
                ids.append(item.get("value"))
        if ids != [reply.parent_rfc822_message_id]:
            raise WriteConnectorFailure("thread_mismatch", attempts=attempts)
        return attempts

    async def _get_draft(
        self,
        draft_id: str,
        *,
        action_id: UUID | None = None,
        attempt_budget: WriteAttemptBudget | None = None,
        prior_attempts: int = 0,
        response_byte_budget: _ResponseByteBudget | None = None,
    ) -> tuple[_ObservedDraft, int]:
        payload, attempts = await self._request_json(
            "GET",
            f"{GMAIL_API_BASE_URL}/users/me/drafts/{quote(draft_id, safe='')}",
            params={"format": "raw"},
            action_id=action_id,
            attempt_budget=attempt_budget,
            prior_attempts=prior_attempts,
            response_byte_budget=response_byte_budget,
            errors={404: "draft_not_found", 429: "rate_limited"},
        )
        try:
            return _parse_draft(payload, observed_at=self._now_utc()), attempts
        except (TypeError, ValueError, ValidationError):
            raise WriteConnectorFailure(
                "provider_unavailable", attempts=attempts
            ) from None

    async def _bounded_draft_scan(
        self,
        target_effect_id: str,
        *,
        byte_budget: _ResponseByteBudget,
    ) -> _GmailDraftScan:
        draft_ids: list[str] = []
        seen_draft_ids: set[str] = set()
        seen_page_tokens: set[str] = set()
        next_page_token: str | None = None
        token_evidence: Literal["absent", "present", "invalid", "unknown"] = "unknown"
        listing_complete = False
        listing_bound_reached = False
        for _ in range(_GMAIL_CREATE_SCAN_MAX_PAGES):
            if byte_budget.remaining == 0:
                break
            params: dict[str, str | int] = {"maxResults": _GMAIL_CREATE_SCAN_PAGE_SIZE}
            if next_page_token is not None:
                params["pageToken"] = next_page_token
            payload, _ = await self._request_json(
                "GET",
                f"{GMAIL_API_BASE_URL}/users/me/drafts",
                params=params,
                response_byte_budget=byte_budget,
                errors={429: "rate_limited"},
            )
            raw_drafts = payload.get("drafts", [])
            if not isinstance(raw_drafts, list):
                return _GmailDraftScan((), False, token_evidence, True)
            raw_token = payload.get("nextPageToken")
            if raw_token is None:
                page_token_evidence: Literal["absent", "present"] = "absent"
            elif isinstance(raw_token, str) and raw_token:
                page_token_evidence = "present"
            else:
                return _GmailDraftScan((), False, "invalid", True)
            for raw_item in cast("list[object]", raw_drafts):
                if not isinstance(raw_item, dict):
                    return _GmailDraftScan((), False, page_token_evidence, True)
                try:
                    draft_id = _string(cast("dict[str, object]", raw_item), "id")
                except ValueError:
                    return _GmailDraftScan((), False, page_token_evidence, True)
                if draft_id not in seen_draft_ids:
                    if len(draft_ids) >= _GMAIL_CREATE_SCAN_MAX_DRAFTS:
                        listing_bound_reached = True
                        token_evidence = page_token_evidence
                        break
                    seen_draft_ids.add(draft_id)
                    draft_ids.append(draft_id)
            if listing_bound_reached:
                break
            if raw_token is None:
                token_evidence = "absent"
                listing_complete = True
                break
            if len(raw_token.encode()) > 16_384 or raw_token in seen_page_tokens:
                return _GmailDraftScan((), False, "invalid", True)
            token_evidence = "present"
            seen_page_tokens.add(raw_token)
            next_page_token = raw_token
        else:
            token_evidence = "present"

        drafts: list[_ObservedDraft] = []
        raw_gets = 0
        for draft_id in sorted(draft_ids):
            if raw_gets >= _GMAIL_CREATE_SCAN_MAX_RAW_GETS:
                return _GmailDraftScan(tuple(drafts), False, token_evidence, False)
            if byte_budget.remaining == 0:
                return _GmailDraftScan(tuple(drafts), False, token_evidence, False)
            raw_gets += 1
            try:
                draft_payload, _ = await self._request_json(
                    "GET",
                    f"{GMAIL_API_BASE_URL}/users/me/drafts/{quote(draft_id, safe='')}",
                    params={"format": "raw"},
                    response_byte_budget=byte_budget,
                    errors={404: "draft_not_found", 429: "rate_limited"},
                )
            except WriteConnectorFailure:
                return _GmailDraftScan(tuple(drafts), False, token_evidence, False)
            try:
                if _raw_effect(draft_payload) != target_effect_id:
                    continue
                drafts.append(_parse_draft(draft_payload, observed_at=self._now_utc()))
            except (TypeError, ValueError, ValidationError):
                return _GmailDraftScan(tuple(drafts), False, token_evidence, True)
        return _GmailDraftScan(tuple(drafts), listing_complete, token_evidence, False)

    async def _calendar_observations(
        self, calendar_id: str, event_id: str
    ) -> list[CalendarEventSnapshot | _CancelledCalendarEvent | None]:
        observations: list[CalendarEventSnapshot | _CancelledCalendarEvent | None] = []
        for delay in RECONCILIATION_DELAYS_SECONDS:
            if delay:
                await self._sleep(delay)
            calendar = quote(calendar_id, safe="")
            event = quote(event_id, safe="")
            try:
                payload, _ = await self._request_json(
                    "GET",
                    f"{CALENDAR_API_BASE_URL}/calendars/{calendar}/events/{event}",
                    errors={404: "event_not_found", 429: "rate_limited"},
                )
                if payload.get("status") == "cancelled":
                    observations.append(_CancelledCalendarEvent())
                else:
                    observations.append(_calendar_snapshot(calendar_id, payload))
            except WriteConnectorFailure as exc:
                if exc.code == "event_not_found":
                    observations.append(None)
            except (TypeError, ValueError, ValidationError):
                pass
        return observations

    def _gmail_result(
        self, payload: dict[str, object], content: GmailContent, effect_id: str
    ) -> GmailDraftSuccess:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Gmail returned a malformed draft")
        item = cast("dict[str, object]", message)
        return GmailDraftSuccess(
            draft_id=_string(payload, "id"),
            message_id=_string(item, "id"),
            thread_id=_string(item, "threadId"),
            jarvis_effect_id=effect_id,
            content_digest=gmail_content_digest(content),
            observed_at=self._now_utc(),
        )

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
        body: dict[str, object] | None = None,
        mutation: bool = False,
        action_id: UUID | None = None,
        attempt_budget: WriteAttemptBudget | None = None,
        prior_attempts: int = 0,
        response_byte_budget: _ResponseByteBudget | None = None,
        errors: Mapping[int, str],
    ) -> tuple[dict[str, object], int]:
        raw, attempts = await self._request(
            method,
            url,
            params=params,
            headers=headers,
            body=body,
            mutation=mutation,
            action_id=action_id,
            attempt_budget=attempt_budget,
            prior_attempts=prior_attempts,
            response_byte_budget=response_byte_budget,
            errors=errors,
        )
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("provider response is malformed")
            return cast("dict[str, object]", payload), attempts
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            if mutation:
                raise TimeoutError("write response needs reconciliation") from exc
            raise WriteConnectorFailure(
                "provider_unavailable", attempts=attempts
            ) from None

    async def _request_empty(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        action_id: UUID,
        attempt_budget: WriteAttemptBudget,
        errors: Mapping[int, str],
    ) -> int:
        raw, attempts = await self._request(
            method,
            url,
            params=params,
            headers=headers,
            body=None,
            mutation=True,
            action_id=action_id,
            attempt_budget=attempt_budget,
            prior_attempts=0,
            response_byte_budget=None,
            errors=errors,
        )
        if raw.strip():
            raise TimeoutError("delete response needs reconciliation")
        return attempts

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        headers: Mapping[str, str] | None,
        body: dict[str, object] | None,
        mutation: bool,
        action_id: UUID | None,
        attempt_budget: WriteAttemptBudget | None,
        prior_attempts: int,
        response_byte_budget: _ResponseByteBudget | None,
        errors: Mapping[int, str],
    ) -> tuple[bytes, int]:
        if type(prior_attempts) is not int or prior_attempts < 0:
            raise ValueError("prior external attempts are invalid")
        if (action_id is None) != (attempt_budget is None):
            raise ValueError("action attempt accounting is incomplete")
        if mutation and action_id is None:
            raise ValueError("mutation attempt accounting is incomplete")
        if attempt_budget is not None and prior_attempts >= attempt_budget.max_attempts:
            raise WriteConnectorFailure("provider_unavailable", attempts=prior_attempts)
        try:
            token, refresh_attempts = await self._tokens.access_token()
        except ConnectorFailure as exc:
            attempts = prior_attempts + exc.attempts if action_id else exc.attempts
            if action_id is not None and attempt_budget is not None and exc.attempts:
                await self._stage_external_attempts(
                    action_id=action_id,
                    actual_external_attempts=(
                        attempt_budget.recovered_attempts + attempts
                    ),
                )
            raise WriteConnectorFailure(exc.code, attempts=attempts) from None
        if action_id is not None and attempt_budget is not None:
            local_attempts = prior_attempts + refresh_attempts
            if refresh_attempts:
                await self._stage_external_attempts(
                    action_id=action_id,
                    actual_external_attempts=(
                        attempt_budget.recovered_attempts + local_attempts
                    ),
                )
            if local_attempts >= attempt_budget.max_attempts:
                raise WriteConnectorFailure(
                    "provider_unavailable", attempts=local_attempts
                )
            await self._stage_external_attempts(
                action_id=action_id,
                actual_external_attempts=(
                    attempt_budget.recovered_attempts + local_attempts + 1
                ),
            )
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **dict(headers or {}),
        }
        try:
            async with (
                asyncio.timeout(8.0),
                self._client.stream(
                    method,
                    url,
                    params=params,
                    headers=request_headers,
                    json=body,
                    follow_redirects=False,
                    timeout=httpx.Timeout(8.0, connect=3.0),
                ) as response,
            ):
                attempts = refresh_attempts + 1
                reported_attempts = (
                    prior_attempts + attempts if action_id is not None else attempts
                )
                code = errors.get(response.status_code)
                if code is not None:
                    raise WriteConnectorFailure(code, attempts=reported_attempts)
                if response.status_code == 401:
                    self._tokens.invalidate_access_token()
                    raise WriteConnectorFailure(
                        "provider_unavailable", attempts=reported_attempts
                    )
                if response.status_code == 403:
                    raise WriteConnectorFailure(
                        "provider_unavailable", attempts=reported_attempts
                    )
                if response.status_code >= 500 and mutation:
                    raise TimeoutError("write request needs reconciliation")
                if response.status_code < 200 or response.status_code >= 300:
                    raise WriteConnectorFailure(
                        "provider_unavailable", attempts=reported_attempts
                    )
                result = bytearray()
                async for chunk in response.aiter_bytes():
                    if (
                        response_byte_budget is not None
                        and not response_byte_budget.consume(len(chunk))
                    ):
                        if mutation:
                            raise TimeoutError("write response needs reconciliation")
                        raise WriteConnectorFailure(
                            "provider_unavailable", attempts=reported_attempts
                        )
                    result.extend(chunk)
                    if len(result) > MAX_PROVIDER_BODY_BYTES:
                        if mutation:
                            raise TimeoutError("write response needs reconciliation")
                        raise WriteConnectorFailure(
                            "provider_unavailable", attempts=reported_attempts
                        )
        except (TimeoutError, httpx.HTTPError) as exc:
            if mutation:
                raise TimeoutError("write request needs reconciliation") from exc
            raise WriteConnectorFailure(
                "provider_unavailable",
                attempts=(
                    prior_attempts + refresh_attempts + 1
                    if action_id is not None
                    else refresh_attempts + 1
                ),
            ) from None
        return bytes(result), attempts

    def _now_utc(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("connector clock must be aware")
        return value.astimezone(UTC)


__all__ = [
    "RECONCILIATION_DELAYS_SECONDS",
    "ActionExternalAttemptStager",
    "CalendarCurrentSnapshot",
    "GmailUpdateBasisStager",
    "GmailUpdateReconciliationBasis",
    "GoogleAccessTokens",
    "GoogleWriteConnector",
    "ReconciliationResult",
    "calendar_event_id",
    "gmail_content_digest",
    "gmail_effect_id",
]

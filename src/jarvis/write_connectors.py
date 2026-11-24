"""Bounded host-owned Google write connectors."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from jarvis.actions import ActionStore, StoredAction
from jarvis.connectors import (
    MAX_PROVIDER_BODY_BYTES,
    google_profile,
)
from jarvis.gmail_drafts import compose_draft, reconcile_draft
from jarvis.gmail_send import gmail_send, reconcile_gmail_send
from jarvis.mail_files import MailFile, MailFileFailure, MailFiles
from jarvis.read_tools import (
    CALENDAR_API_BASE_URL,
    GMAIL_API_BASE_URL,
    ConnectorFailure,
)
from jarvis.write_tools import (
    GMAIL_WRITE_POLICY,
    AllDayEventTime,
    CalendarCreateEventInput,
    CalendarCreateEventSuccess,
    CalendarDeleteEventInput,
    CalendarDeleteEventSuccess,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarUpdateEventSuccess,
    CalendarWritableEvent,
    GmailComposeContract,
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    GmailRevision,
    GmailSendContract,
    GmailSendDraftInput,
    GmailSendDraftSuccess,
    GmailSnapshot,
    GmailUpdateDraftInput,
    Mailbox,
    ReconciliationResult,
    Reminder,
    TimedEventTime,
    WriteAttemptBudget,
    WriteConnectorFailure,
    WriteResponse,
)

RECONCILIATION_DELAYS_SECONDS = (0.0, 2.0, 8.0)


class GoogleAccessTokens(Protocol):
    async def access_token(self) -> tuple[str, int]: ...

    def invalidate_access_token(self, rejected_token: str) -> None: ...


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
class _CancelledCalendarEvent:
    pass


def calendar_event_id(action_id: UUID) -> str:
    return hashlib.sha256(f"jarvis-calendar-v1:{action_id}".encode()).hexdigest()[:32]


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
    attendees_omitted = payload.get("attendeesOmitted", False)
    if type(attendees_omitted) is not bool or attendees_omitted:
        raise ValueError("Calendar attendee observation is incomplete")
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


def _whole_second_time(
    value: TimedEventTime | AllDayEventTime,
) -> TimedEventTime | AllDayEventTime:
    if isinstance(value, TimedEventTime):
        return value.model_copy(
            update={"date_time": value.date_time.replace(microsecond=0)}
        )
    return value


def _normalized_writable(value: CalendarWritableEvent) -> CalendarWritableEvent:
    return value.model_copy(
        update={
            "start": _whole_second_time(value.start),
            "end": _whole_second_time(value.end),
            "attendees": tuple(
                attendee.model_copy(update={"name": None})
                for attendee in value.attendees
            ),
        }
    )


class _GmailOperation:
    """One deadline, one attempt counter and one bounded response stream."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        tokens: GoogleAccessTokens,
        actions: ActionStore,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]],
        action_id: UUID | None,
        budget: WriteAttemptBudget | None,
    ) -> None:
        if (action_id is None) != (budget is None):
            raise ValueError("incomplete Gmail attempt accounting")
        self._client = client
        self._tokens = tokens
        self._actions = actions
        self.now = now
        self._sleep = sleep
        self.deadline = (
            asyncio.get_running_loop().time() + GMAIL_WRITE_POLICY.operation_seconds
        )
        self.attempts = 0
        self._remaining_bytes = GMAIL_WRITE_POLICY.recovery_bytes
        self._action_id = action_id
        self._budget = budget

    async def sleep(self, delay: float) -> None:
        await self._sleep(delay)

    async def account(self) -> str:
        payload = await self.request(
            "GET", "profile", params={"fields": "emailAddress,historyId"}
        )
        assert payload is not None
        try:
            return google_profile(payload).account
        except ValueError:
            raise WriteConnectorFailure(
                "provider_unavailable", attempts=self.attempts
            ) from None

    async def _charge(self, count: int, *, mutation: bool = False) -> None:
        self.attempts += count
        if self._action_id is not None and self._budget is not None and count:
            await self._actions.stage_mail_exchange(
                self._action_id,
                self._budget.recovered_attempts + self.attempts,
                mutation=mutation,
            )

    async def request(
        self,
        method: str,
        route: str,
        *,
        params: Mapping[str, str | int | tuple[str, ...]] | None = None,
        metadata: dict[str, object] | None = None,
        mime: bytes | None = None,
        raw: bool = False,
        errors: Mapping[int, str | None] | None = None,
        account: str = "me",
    ) -> dict[str, object] | None:
        policy = GMAIL_WRITE_POLICY
        mutation = mime is not None
        params = dict(params or {})
        if mutation != (method in {"POST", "PUT"}) or mutation != (
            metadata is not None
        ):
            raise ValueError("Gmail media write is incomplete")
        url = f"{GMAIL_API_BASE_URL}/users/{quote(account, safe='')}/{route}"
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        body = None
        if mime is not None:
            if self._action_id is None:
                raise ValueError("Gmail mutation requires a recorded action")
            assert metadata is not None
            boundary = f"jarvis={uuid4().hex}"
            headers["Content-Type"] = f'multipart/related; boundary="{boundary}"'
            delimiter = f"--{boundary}\r\n".encode()
            body = b"".join(
                (
                    delimiter,
                    b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
                    json.dumps(metadata, separators=(",", ":")).encode(),
                    b"\r\n",
                    delimiter,
                    b"Content-Type: message/rfc822\r\n\r\n",
                    mime,
                    f"\r\n--{boundary}--\r\n".encode(),
                )
            )
            for measure, actual, maximum in (
                ("mime_bytes", len(mime), policy.mime_bytes),
                ("multipart_bytes", len(body), policy.multipart_bytes),
            ):
                if actual > maximum:
                    raise WriteConnectorFailure(
                        "mail_limit",
                        attempts=self.attempts,
                        details={
                            "type": "MailLimit",
                            "measure": measure,
                            "actual": actual,
                            "maximum": maximum,
                        },
                    )
            url = url.replace("/gmail/v1/", "/upload/gmail/v1/", 1)
            params["uploadType"] = "multipart"
        timeout = min(
            policy.exchange_seconds, self.deadline - asyncio.get_running_loop().time()
        )
        if timeout <= 0 or (
            self._budget is not None and self.attempts >= self._budget.max_attempts
        ):
            raise WriteConnectorFailure("provider_unavailable", attempts=self.attempts)
        exchange_deadline = asyncio.get_running_loop().time() + timeout
        entered = False
        try:
            async with asyncio.timeout_at(exchange_deadline):
                try:
                    token, refreshes = await self._tokens.access_token()
                except ConnectorFailure as exc:
                    await self._charge(exc.attempts)
                    raise WriteConnectorFailure(
                        exc.code, attempts=self.attempts
                    ) from None
                await self._charge(refreshes)
                if (
                    self._budget is not None
                    and self.attempts >= self._budget.max_attempts
                ):
                    raise WriteConnectorFailure(
                        "provider_unavailable", attempts=self.attempts
                    )
                if asyncio.get_running_loop().time() >= exchange_deadline:
                    raise TimeoutError("Gmail exchange expired before entry")
                await self._charge(1, mutation=mutation)
                entered = mutation
                if asyncio.get_running_loop().time() >= exchange_deadline:
                    raise TimeoutError("Gmail exchange expired before the request")
                headers["Authorization"] = f"Bearer {token}"
                async with self._client.stream(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    content=body,
                    follow_redirects=False,
                    timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
                ) as response:
                    status = response.status_code
                    if status == 401:
                        self._tokens.invalidate_access_token(token)
                    if not 200 <= status < 300:
                        if status >= 500 and mutation:
                            raise TimeoutError("Gmail write requires reconciliation")
                        if mutation and status in {400, 403}:
                            error_data = await self._read_response(
                                response, policy.metadata_bytes
                            )
                            # badRequest also covers unrelated fields.
                            # Recognize only its explicit content-policy explanation.
                            diagnostic = error_data.lower()
                            if any(
                                phrase in diagnostic
                                for phrase in (
                                    b"content presents a potential security issue",
                                    b"blocked for security reasons",
                                    b"invalid attachment",
                                )
                            ):
                                raise WriteConnectorFailure(
                                    "file_policy", attempts=self.attempts
                                )
                        if errors is not None and status in errors:
                            code = errors[status]
                            if status == 404 and code is None:
                                return None
                            if code is not None:
                                raise WriteConnectorFailure(
                                    code, attempts=self.attempts
                                )
                        raise WriteConnectorFailure(
                            "rate_limited" if status == 429 else "provider_unavailable",
                            attempts=self.attempts,
                        )
                    if mutation:
                        assert self._action_id is not None
                        await self._actions.stage_mail_acknowledgement(self._action_id)
                    data = await self._read_response(
                        response, policy.raw_bytes if raw else policy.metadata_bytes
                    )
                    payload = await asyncio.to_thread(json.loads, data)
                    if not isinstance(payload, dict):
                        raise ValueError("Gmail response must be an object")
                    return cast(dict[str, object], payload)
        except (TimeoutError, httpx.HTTPError, ValueError) as exc:
            if entered:
                raise TimeoutError("Gmail write requires reconciliation") from exc
            raise WriteConnectorFailure(
                "provider_unavailable", attempts=self.attempts
            ) from None

    async def _read_response(self, response: httpx.Response, maximum: int) -> bytearray:
        result = bytearray()
        async for chunk in response.aiter_bytes():
            self._remaining_bytes -= len(chunk)
            if len(result) + len(chunk) > maximum or self._remaining_bytes < 0:
                raise ValueError("Gmail response exceeded its byte budget")
            result.extend(chunk)
        return result


class GoogleWriteConnector:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        tokens: GoogleAccessTokens,
        actions: ActionStore,
        mail_files: MailFiles | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._actions = actions
        self._mail_files = mail_files
        self._now = now
        self._sleep = sleep
        self._verified_account: str | None = None

    async def _account(
        self,
        *,
        action_id: UUID | None = None,
        attempt_budget: WriteAttemptBudget | None = None,
    ) -> tuple[str, int]:
        payload, attempts = await self._request_json(
            "GET",
            f"{GMAIL_API_BASE_URL}/users/me/profile",
            params={"fields": "emailAddress,historyId"},
            action_id=action_id,
            attempt_budget=attempt_budget,
            errors={},
        )
        try:
            account = google_profile(payload).account
            self._verified_account = account
            return account, attempts
        except ValueError:
            raise WriteConnectorFailure(
                "provider_unavailable", attempts=attempts
            ) from None

    def gmail_operation(
        self,
        *,
        action_id: UUID | None = None,
        budget: WriteAttemptBudget | None = None,
    ) -> _GmailOperation:
        return _GmailOperation(
            client=self._client,
            tokens=self._tokens,
            actions=self._actions,
            now=self._now_utc,
            sleep=self._sleep,
            action_id=action_id,
            budget=budget,
        )

    async def gmail_create_draft(
        self,
        value: GmailCreateDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        return await self._compose_gmail(value.content, effect_id, attempt_budget)

    async def gmail_update_draft(
        self,
        value: GmailUpdateDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        return await self._compose_gmail(value.replacement, effect_id, attempt_budget)

    async def _compose_gmail(
        self,
        content: GmailContent,
        action_id: UUID,
        budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        stored = await self._actions.get(action_id)
        if stored is None or self._mail_files is None:
            raise RuntimeError("Gmail compose is missing its action or file store")
        contract = stored.current_execution_contract.mail
        if not isinstance(contract, GmailComposeContract):
            raise RuntimeError("Gmail compose lacks its frozen input")
        files = self._mail_files
        mail = self.gmail_operation(action_id=action_id, budget=budget)

        async def read_part(slot: int, expected: MailFile) -> bytes:
            try:
                return await files.read(action_id, slot, expected)
            except MailFileFailure as exc:
                raise WriteConnectorFailure(
                    "file_unavailable",
                    attempts=mail.attempts,
                    details=exc.error,
                ) from None

        async with asyncio.timeout_at(mail.deadline):
            return await compose_draft(
                mail,
                content,
                contract,
                action_id,
                read_part=read_part,
                stage_basis=lambda basis: self._actions.stage_mail_basis(
                    action_id, basis
                ),
                stage_ack=lambda ack: self._actions.stage_mail_acknowledgement(
                    action_id, ack
                ),
            )

    async def gmail_send_draft(
        self,
        value: GmailSendDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailSendDraftSuccess]:
        stored = await self._actions.get(effect_id)
        contract = None if stored is None else stored.current_execution_contract.mail
        if not isinstance(contract, GmailSendContract):
            raise RuntimeError("Gmail send lacks its approved revision")
        mail = self.gmail_operation(action_id=effect_id, budget=attempt_budget)
        async with asyncio.timeout_at(mail.deadline):
            return await gmail_send(mail, contract)

    async def reconcile_gmail(
        self, stored: StoredAction
    ) -> ReconciliationResult[GmailDraftSuccess | GmailSendDraftSuccess]:
        contract = stored.current_execution_contract.mail
        progress = stored.mail_progress
        if not progress.entered:
            return ReconciliationResult("absent", "gmail-mutation-never-entered")
        mail = self.gmail_operation()
        try:
            async with asyncio.timeout_at(mail.deadline):
                if isinstance(contract, GmailSendContract):
                    result = await reconcile_gmail_send(
                        mail, contract.revision, contract.snapshot
                    )
                    if result.outcome == "absent" and progress.acknowledged:
                        return ReconciliationResult(
                            "uncertain", "gmail-send-acknowledged"
                        )
                    return ReconciliationResult(
                        result.outcome, result.evidence, result.value
                    )
                if (
                    not isinstance(contract, GmailComposeContract)
                    or progress.basis is None
                ):
                    raise RuntimeError(
                        "entered Gmail compose lacks its reconciliation basis"
                    )

                async def observe_sent(
                    revision: GmailRevision,
                    snapshot: GmailSnapshot,
                ) -> ReconciliationResult[GmailSendDraftSuccess]:
                    return await reconcile_gmail_send(mail, revision, snapshot)

                result = await reconcile_draft(
                    mail,
                    stored.id,
                    contract,
                    progress.basis,
                    acknowledged=progress.acknowledged,
                    acknowledgement=progress.ack,
                    observe_sent=observe_sent,
                )
                return ReconciliationResult(
                    result.outcome, result.evidence, result.value
                )
        except TimeoutError:
            return ReconciliationResult("uncertain", "gmail-recovery-deadline")

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

    async def calendar_create_event(
        self,
        value: CalendarCreateEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarCreateEventSuccess]:
        expected = _normalized_writable(value.event)
        if not _valid_event(expected):
            raise WriteConnectorFailure("invalid_event", attempts=0)
        account, profile_attempts = await self._account(
            action_id=effect_id, attempt_budget=attempt_budget
        )
        event_id = calendar_event_id(effect_id)
        calendar = quote(value.calendar_id, safe="")
        try:
            payload, attempts = await self._request_json(
                "POST",
                f"{CALENDAR_API_BASE_URL}/calendars/{calendar}/events",
                params={"sendUpdates": "all" if value.notify_attendees else "none"},
                body=_calendar_payload(expected, event_id=event_id),
                mutation=True,
                action_id=effect_id,
                attempt_budget=attempt_budget,
                prior_attempts=profile_attempts,
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
            if event.event_id != event_id or event.writable != expected:
                raise ValueError("Calendar returned a conflicting event")
            result = CalendarCreateEventSuccess(
                account=account, event=event, created_at=self._now_utc()
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Calendar create needs reconciliation") from exc
        return WriteResponse(result, attempts + profile_attempts)

    async def calendar_update_event(
        self,
        value: CalendarUpdateEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarUpdateEventSuccess]:
        replacement = _normalized_writable(value.replacement)
        if not _valid_event(replacement):
            raise WriteConnectorFailure("invalid_event", attempts=0)
        account, profile_attempts = await self._account(
            action_id=effect_id, attempt_budget=attempt_budget
        )
        expected = value.expected
        calendar = quote(expected.calendar_id, safe="")
        event = quote(expected.event_id, safe="")
        payload, attempts = await self._request_json(
            "PATCH",
            f"{CALENDAR_API_BASE_URL}/calendars/{calendar}/events/{event}",
            params={"sendUpdates": "all" if value.notify_attendees else "none"},
            headers={"If-Match": expected.etag},
            body=_calendar_payload(replacement, event_id=None),
            mutation=True,
            action_id=effect_id,
            attempt_budget=attempt_budget,
            prior_attempts=profile_attempts,
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
                or observed.writable != replacement
            ):
                raise ValueError("Calendar returned a conflicting event")
            result = CalendarUpdateEventSuccess(
                account=account, event=observed, updated_at=self._now_utc()
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise TimeoutError("Calendar update needs reconciliation") from exc
        return WriteResponse(result, attempts + profile_attempts)

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
        account = self._verified_account
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
                    account=account, event=matches[-1], created_at=self._now_utc()
                ),
            )
        if len(observations) == len(RECONCILIATION_DELAYS_SECONDS):
            return ReconciliationResult("absent", "event-absent-at-all-observations")
        return ReconciliationResult("uncertain", "calendar-observations-incomplete")

    async def reconcile_calendar_update(
        self, value: CalendarUpdateEventInput
    ) -> ReconciliationResult[CalendarUpdateEventSuccess]:
        expected = value.expected
        account = self._verified_account
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
                    CalendarUpdateEventSuccess(
                        account=account, event=item, updated_at=self._now_utc()
                    ),
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
                await self._actions.stage_external_attempts(
                    action_id=action_id,
                    actual_external_attempts=(
                        attempt_budget.recovered_attempts + attempts
                    ),
                )
            raise WriteConnectorFailure(exc.code, attempts=attempts) from None
        if action_id is not None and attempt_budget is not None:
            local_attempts = prior_attempts + refresh_attempts
            if refresh_attempts:
                await self._actions.stage_external_attempts(
                    action_id=action_id,
                    actual_external_attempts=(
                        attempt_budget.recovered_attempts + local_attempts
                    ),
                )
            if local_attempts >= attempt_budget.max_attempts:
                raise WriteConnectorFailure(
                    "provider_unavailable", attempts=local_attempts
                )
            await self._actions.stage_external_attempts(
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
                    self._tokens.invalidate_access_token(token)
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
    "CalendarCurrentSnapshot",
    "GoogleAccessTokens",
    "GoogleWriteConnector",
    "ReconciliationResult",
    "calendar_event_id",
]

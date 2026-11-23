"""Bounded Google observations with durable progress owned by EventStore."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from datetime import time as civil_time
from email.utils import parsedate_to_datetime
from typing import Literal, cast
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from llm_tools import canonical_json_bytes
from pydantic import ValidationError

from jarvis.connectors import (
    GoogleCredentialDefect,
    GoogleProfile,
    GoogleReadConnector,
    GoogleReadFailure,
    GoogleTokenManager,
    google_profile,
    parse_calendar_time,
    parse_google_instant,
    provider_array,
    provider_object,
    provider_string,
    provider_text,
)
from jarvis.event_tools import (
    POLL_SECONDS,
    CalendarAttention,
    CalendarChanged,
    EmailAdded,
    EventProjection,
    attention_due,
    calendar_zone,
    provider_id,
)
from jarvis.events import CalendarResource, Cursor, EventStore, Failure, Observation
from jarvis.read_tools import (
    CALENDAR_API_BASE_URL,
    GMAIL_API_BASE_URL,
    AllDayEventTime,
    ConnectorFailure,
    Preview,
    TimedEventTime,
    UnspecifiedEventEnd,
    text_preview,
)
from jarvis.work_schedule import resolve_civil

_LOGGER = logging.getLogger(__name__)
_PAGE_SIZE = 20
_QUANTUM_SECONDS = 30.0

_EVENT_FIELDS = (
    "summary,timeZone,nextPageToken,nextSyncToken,items(id,etag,status,updated,"
    "summary,location,start,end,endTimeUnspecified,recurringEventId,"
    "originalStartTime,eventType)"
)
_HISTORY_FIELDS = (
    "history(id,messagesAdded(message(id,threadId))),nextPageToken,historyId"
)


class _NotAdmitted(Exception):
    pass


class _ReadFailed(Exception):
    def __init__(self, failure: Failure, *, status: int | None = None) -> None:
        self.failure = failure
        self.status = status
        super().__init__(failure.code)


def _optional_id(value: dict[str, object], key: str) -> str | None:
    return None if value.get(key) is None else provider_id(provider_string(value, key))


def _preview(value: object) -> Preview | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("source preview is malformed")
    return text_preview(value)


def _page_token(payload: dict[str, object], name: str = "nextPageToken") -> str | None:
    if payload.get(name) is None:
        return None
    return provider_text(provider_string(payload, name), 8_192)


def _projection(
    raw: object, *, calendar_id: str, name: object, zone: str
) -> EventProjection:
    item = provider_object(raw, "Calendar event")
    sparse_cancelled = set(item) <= {"id", "recurringEventId", "originalStartTime"}
    status = item.get("status", "cancelled" if sparse_cancelled else "confirmed")
    cancelled = status == "cancelled"
    start = parse_calendar_time(item["start"]) if "start" in item else None
    end = (
        UnspecifiedEventEnd()
        if item.get("endTimeUnspecified") is True
        else parse_calendar_time(item["end"])
        if "end" in item
        else None
    )
    if "endTimeUnspecified" in item and type(item["endTimeUnspecified"]) is not bool:
        raise ValueError("Calendar end availability is malformed")
    if not cancelled:
        if type(start) is not type(end) and not isinstance(end, UnspecifiedEventEnd):
            raise ValueError("Calendar time variants disagree")
        if (
            isinstance(start, TimedEventTime)
            and isinstance(end, TimedEventTime)
            and end.date_time <= start.date_time
        ):
            raise ValueError("Calendar event end precedes its start")
        if (
            isinstance(start, AllDayEventTime)
            and isinstance(end, AllDayEventTime)
            and end.date <= start.date
        ):
            raise ValueError("Calendar event end precedes its start")
    return EventProjection(
        calendar_id=calendar_id,
        calendar_name=_preview(name),
        calendar_zone=zone,
        event_id=provider_id(provider_string(item, "id")),
        etag=_page_token(item, "etag"),
        status=cast(Literal["cancelled", "confirmed", "tentative"], status),
        event_type=_optional_id(item, "eventType"),
        updated_at=parse_google_instant(provider_string(item, "updated"))
        if "updated" in item
        else None,
        summary=_preview(item.get("summary")),
        location=_preview(item.get("location")),
        start=start,
        end=end,
        recurring_event_id=_optional_id(item, "recurringEventId"),
        original_start=parse_calendar_time(item["originalStartTime"])
        if "originalStartTime" in item
        else None,
    )


def _time_identity(value: object) -> dict[str, str]:
    if isinstance(value, AllDayEventTime):
        return {"kind": "date", "value": value.date.isoformat()}
    if isinstance(value, TimedEventTime):
        return {"kind": "instant", "value": value.date_time.astimezone(UTC).isoformat()}
    raise ValueError("missing occurrence identity")


def _prefix(candidates: list[tuple[str, str, str | None]], count: int) -> str | None:
    if not count:
        return None
    return hashlib.sha256(
        canonical_json_bytes(
            [[history, message] for history, message, _ in candidates[:count]]
        )
    ).hexdigest()


class EventPoller:
    def __init__(
        self,
        *,
        store: EventStore,
        client: httpx.AsyncClient,
        tokens: GoogleTokenManager,
        owner_zone: str,
        admitted: Callable[[], Awaitable[bool]],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._reads = GoogleReadConnector(client=client, tokens=tokens, now=now)
        self._owner_zone = calendar_zone(owner_zone)
        self._admitted = admitted
        self._now = now
        self._changed = asyncio.Event()
        self._deadline = 0.0
        self._verification_at: datetime | None = None
        self._verification_failures = 0
        self._verification_blocked = False
        self._stop: asyncio.Event | None = None

    def notify_changed(self) -> None:
        self._changed.set()

    async def run(self, stop: asyncio.Event) -> None:
        self._stop = stop
        while not stop.is_set():
            self._changed.clear()
            wait_seconds = float(POLL_SECONDS)
            if await self._admitted():
                if self._store.account is None:
                    if not self._verification_blocked and (
                        self._verification_at is None
                        or self._verification_at <= self._now()
                    ):
                        await self._verify()
                    if self._store.account is None and not self._verification_blocked:
                        due_at = self._verification_at
                        if due_at is not None:
                            wait_seconds = min(
                                float(POLL_SECONDS),
                                max(0.0, (due_at - self._now()).total_seconds()),
                            )
                if self._store.account is not None:
                    cursor = await self._store.select_due(self._now())
                    if cursor is not None:
                        await self.poll(cursor)
                        await asyncio.sleep(0)
                        continue
                    due_at = await self._store.next_due_at()
                    if due_at is not None:
                        wait_seconds = min(
                            float(POLL_SECONDS),
                            max(0.0, (due_at - self._now()).total_seconds()),
                        )
            changed = asyncio.create_task(self._changed.wait())
            stopped = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait(
                    (changed, stopped),
                    timeout=wait_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                changed.cancel()
                stopped.cancel()
                await asyncio.gather(changed, stopped, return_exceptions=True)

    async def _verify(self) -> None:
        self._deadline = time.monotonic() + _QUANTUM_SECONDS
        try:
            profile = await self._profile(None)
            await self._store.initialize(profile.account, profile.history_id)
            self._verification_failures = 0
        except _NotAdmitted:
            return
        except _ReadFailed as exc:
            self._verification_failures = min(5, self._verification_failures + 1)
            delay = (60, 120, 240, 480, 900)[self._verification_failures - 1]
            self._verification_at = max(
                self._now() + timedelta(seconds=delay),
                exc.failure.retry_at or self._now(),
            )
            self._verification_blocked = exc.failure.blocked
            _LOGGER.warning(
                "event source account unavailable code=%s retry_count=%d blocked=%s",
                exc.failure.code,
                self._verification_failures,
                self._verification_blocked,
            )

    async def _before(self, cursor: Cursor | None) -> None:
        # Provider cancellation must join admission SQL, never cancel its owner.
        task = asyncio.create_task(self._check_admission(cursor))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _check_admission(self, cursor: Cursor | None) -> None:
        if time.monotonic() >= self._deadline:
            raise _ReadFailed(Failure("TransportUnavailable"))
        if self._stop is not None and self._stop.is_set():
            raise _NotAdmitted
        if not await self._admitted() or (
            cursor is not None and not await self._store.admission(cursor)
        ):
            raise _NotAdmitted

    async def _read(
        self, cursor: Cursor | None, url: str, params: dict[str, str | int | list[str]]
    ) -> dict[str, object]:
        for attempt in range(2):
            await self._before(cursor)
            try:
                async with asyncio.timeout(
                    max(0.001, self._deadline - time.monotonic())
                ):
                    payload = await self._fetch(cursor, url, params)
                return payload
            except GoogleReadFailure as exc:
                if exc.status == 401 and attempt == 0:
                    continue
                retry_at = None
                if exc.retry_after:
                    try:
                        if exc.retry_after.isdecimal():
                            retry_at = self._now() + timedelta(
                                seconds=int(exc.retry_after)
                            )
                        else:
                            parsed = parsedate_to_datetime(exc.retry_after)
                            if parsed.tzinfo is not None:
                                retry_at = parsed.astimezone(UTC)
                    except (ValueError, TypeError, OverflowError):
                        pass
                if exc.status == 401:
                    failure = Failure("AuthUnavailable", blocked=True, shared_auth=True)
                elif exc.status == 403 and exc.code == "rate_limited":
                    failure = Failure("RateLimited", retry_at=retry_at)
                elif exc.status == 403 and exc.grant_unavailable:
                    failure = Failure("AuthUnavailable", blocked=True, family=True)
                elif exc.status == 403:
                    failure = Failure(
                        "Forbidden",
                        blocked=True,
                        family=cursor is None
                        or cursor.kind in {"gmail", "calendar_list"},
                    )
                elif 200 <= exc.status < 300 or exc.status == 400:
                    failure = Failure("InvalidResponse", blocked=True)
                elif exc.status == 429:
                    failure = Failure("RateLimited", retry_at=retry_at)
                else:
                    failure = Failure("TransportUnavailable", retry_at=retry_at)
                raise _ReadFailed(failure, status=exc.status) from None
            except GoogleCredentialDefect:
                raise _ReadFailed(
                    Failure("AuthUnavailable", blocked=True, shared_auth=True)
                ) from None
            except ConnectorFailure as exc:
                raise _ReadFailed(
                    Failure("ResponseTooLarge", blocked=True)
                    if exc.code == "provider_response_too_large"
                    else Failure("RateLimited")
                    if exc.code == "rate_limited"
                    else Failure("TransportUnavailable")
                ) from None
            except TimeoutError:
                raise _ReadFailed(Failure("TransportUnavailable")) from None
        raise AssertionError("request retry exhausted")

    async def _fetch(
        self,
        cursor: Cursor | None,
        url: str,
        params: dict[str, str | int | list[str]],
    ) -> dict[str, object]:
        request = asyncio.create_task(
            self._reads.get_json(
                url,
                params=params,
                not_found="not_found",
                before_request=lambda: self._before(cursor),
            )
        )
        stopped = (
            asyncio.create_task(self._stop.wait()) if self._stop is not None else None
        )
        try:
            if stopped is not None:
                await asyncio.wait(
                    (request, stopped), return_when=asyncio.FIRST_COMPLETED
                )
                if stopped.done():
                    raise _NotAdmitted
            payload, _ = await request
            return payload
        finally:
            if stopped is not None:
                stopped.cancel()
            request.cancel()
            await asyncio.gather(
                request,
                *(() if stopped is None else (stopped,)),
                return_exceptions=True,
            )

    async def _commit(
        self,
        cursor: Cursor,
        progress: dict[str, object],
        observations: Sequence[Observation] = (),
        *,
        complete: bool = False,
        inventory: Sequence[CalendarResource] = (),
        inventory_complete: bool = False,
        failure: Failure | None = None,
        gap: bool = False,
    ) -> bool:
        if (
            self._stop is not None and self._stop.is_set()
        ) or not await self._admitted():
            return False
        return await self._store.commit_progress(
            cursor,
            progress,
            observations,
            complete=complete,
            inventory=inventory,
            inventory_complete=inventory_complete,
            failure=failure,
            gap=gap,
        )

    async def _profile(self, cursor: Cursor | None) -> GoogleProfile:
        payload = await self._read(
            cursor,
            f"{GMAIL_API_BASE_URL}/users/me/profile",
            {"fields": "emailAddress,historyId"},
        )
        try:
            return google_profile(payload)
        except ValueError:
            raise _ReadFailed(Failure("InvalidResponse", blocked=True)) from None

    async def poll(self, cursor: Cursor) -> None:
        """One bounded page/prefix; all provider calls precede owned publication."""
        self._deadline = time.monotonic() + _QUANTUM_SECONDS
        try:
            if cursor.kind == "gmail":
                await self._gmail(cursor)
            elif cursor.kind == "calendar_list":
                await self._inventory(cursor)
            elif cursor.kind == "calendar_changes":
                await self._changes(cursor)
            else:
                await self._upcoming(cursor)
        except _NotAdmitted:
            return
        except _ReadFailed as exc:
            await self._commit(cursor, cursor.progress, failure=exc.failure)
        except (ValueError, TypeError, ValidationError, OverflowError):
            await self._commit(
                cursor,
                cursor.progress,
                failure=Failure("InvalidResponse", blocked=True),
            )

    async def _gmail(self, cursor: Cursor) -> None:
        progress = dict(cursor.progress)
        if progress["history_id"] is None:
            profile = await self._profile(cursor)
            if profile.account != cursor.account_id:
                raise _ReadFailed(
                    Failure("AuthUnavailable", blocked=True, shared_auth=True)
                )
            progress["history_id"] = profile.history_id
            await self._commit(cursor, progress, complete=True)
            return
        params: dict[str, str | int | list[str]] = {
            "startHistoryId": str(progress["history_id"]),
            "historyTypes": "messageAdded",
            "maxResults": _PAGE_SIZE,
            "fields": _HISTORY_FIELDS,
        }
        if progress["page_token"] is not None:
            params["pageToken"] = str(progress["page_token"])
        try:
            payload = await self._read(
                cursor, f"{GMAIL_API_BASE_URL}/users/me/history", params
            )
        except _ReadFailed as exc:
            if exc.status != 404:
                raise
            await self._commit(
                cursor,
                {
                    "history_id": None,
                    "page_token": None,
                    "consumed": 0,
                    "prefix_sha256": None,
                },
                gap=True,
            )
            return
        high_water = provider_text(provider_string(payload, "historyId"), 8192)
        if not high_water.isascii() or not high_water.isdecimal():
            raise ValueError("invalid Gmail high water")
        candidates: dict[tuple[str, str], str | None] = {}
        for raw in provider_array(payload.get("history", []), "Gmail history"):
            history = provider_object(raw, "Gmail history record")
            history_id = provider_text(provider_string(history, "id"), 8192)
            if not history_id.isascii() or not history_id.isdecimal():
                raise ValueError("invalid history order")
            for raw_added in provider_array(
                history.get("messagesAdded", []), "Gmail additions"
            ):
                item = provider_object(
                    provider_object(raw_added, "Gmail addition").get("message"),
                    "Gmail message",
                )
                message_id = provider_id(provider_string(item, "id"))
                candidates[(history_id, message_id)] = _optional_id(item, "threadId")
        ordered = [
            (history, message, thread)
            for (history, message), thread in sorted(
                candidates.items(), key=lambda entry: (int(entry[0][0]), entry[0][1])
            )
        ]
        consumed = cast("int", progress["consumed"])
        if (
            consumed > len(ordered)
            or _prefix(ordered, consumed) != progress["prefix_sha256"]
        ):
            consumed = 0
        observations: list[Observation] = []
        failure = None
        for _, message_id, thread_id in ordered[consumed : consumed + _PAGE_SIZE]:
            identity = (cursor.account_id, message_id)
            try:
                if not await self._store.is_published(
                    "email_event", identity
                ) and not await self._store.has_echo("gmail", message_id=message_id):
                    observation = await self._mail_metadata(
                        cursor, message_id, thread_id, identity
                    )
                    if observation is not None:
                        observations.append(observation)
            except _ReadFailed as exc:
                failure = exc.failure
                break
            except (ValueError, TypeError, ValidationError, OverflowError):
                failure = Failure("InvalidResponse", blocked=True)
                break
            consumed += 1
        progress["consumed"] = consumed
        progress["prefix_sha256"] = _prefix(ordered, consumed)
        complete = False
        if failure is None and consumed == len(ordered):
            progress["page_token"] = _page_token(payload)
            progress["consumed"] = 0
            progress["prefix_sha256"] = None
            if progress["page_token"] is None:
                progress["history_id"] = high_water
                complete = True
        await self._commit(
            cursor, progress, observations, complete=complete, failure=failure
        )

    async def _mail_metadata(
        self,
        cursor: Cursor,
        message_id: str,
        thread_id: str | None,
        identity: tuple[object, ...],
    ) -> Observation | None:
        try:
            payload = await self._read(
                cursor,
                f"{GMAIL_API_BASE_URL}/users/me/messages/{quote(message_id, safe='')}",
                {
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject"],
                    "fields": "id,threadId,labelIds,internalDate,payload(headers)",
                },
            )
        except _ReadFailed as exc:
            if exc.status != 404:
                raise
            now = self._now()
            return Observation(
                "email_event",
                identity,
                EmailAdded(
                    account=cursor.account_id,
                    observed_at=now,
                    message_id=message_id,
                    thread_id=thread_id,
                    metadata="missing",
                    source_at=None,
                    sender=None,
                    subject=None,
                    inbox=None,
                ),
                now,
            )
        now = self._now()
        if provider_id(provider_string(payload, "id")) != message_id:
            raise ValueError("metadata message identity changed")
        labels = set(provider_array(payload.get("labelIds", []), "Gmail labels"))
        if any(not isinstance(label, str) for label in labels):
            raise ValueError("invalid Gmail label")
        if labels.intersection({"DRAFT", "SPAM", "TRASH"}) or (
            "SENT" in labels and "INBOX" not in labels
        ):
            return None
        metadata = provider_object(payload.get("payload", {}), "Gmail metadata")
        headers: dict[str, str] = {}
        for raw in provider_array(metadata.get("headers", []), "Gmail headers"):
            header = provider_object(raw, "Gmail header")
            name = provider_string(header, "name").lower()
            if name in {"from", "subject"}:
                value = header.get("value")
                if not isinstance(value, str):
                    raise ValueError("invalid Gmail header text")
                headers[name] = value
        source_at = None
        if payload.get("internalDate") is not None:
            raw_date = provider_string(payload, "internalDate")
            if not raw_date.isdecimal():
                raise ValueError("invalid Gmail internal date")
            source_at = datetime.fromtimestamp(int(raw_date) / 1000, UTC)
        event = EmailAdded(
            account=cursor.account_id,
            observed_at=now,
            message_id=message_id,
            thread_id=_optional_id(payload, "threadId") or thread_id,
            metadata="available",
            source_at=source_at,
            sender=_preview(headers.get("from")),
            subject=_preview(headers.get("subject")),
            inbox="INBOX" in labels,
        )
        return Observation("email_event", identity, event, source_at or now)

    async def _inventory(self, cursor: Cursor) -> None:
        progress = dict(cursor.progress)
        if progress["scan_id"] is None:
            progress["scan_id"] = str(uuid4())
            if not await self._commit(cursor, progress):
                return
            return  # persist the scan before its first provider page
        params: dict[str, str | int | list[str]] = {
            "showHidden": "true",
            "showDeleted": "false",
            "minAccessRole": "reader",
            "maxResults": _PAGE_SIZE,
            "fields": "nextPageToken,items(id,accessRole,timeZone)",
        }
        if progress["page_token"] is not None:
            params["pageToken"] = str(progress["page_token"])
        payload = await self._read(
            cursor, f"{CALENDAR_API_BASE_URL}/users/me/calendarList", params
        )
        resources: list[CalendarResource] = []
        resource_ids: set[str] = set()
        for raw in provider_array(payload.get("items", []), "Calendar inventory"):
            item = provider_object(raw, "Calendar inventory entry")
            resource_id = provider_id(provider_string(item, "id"))
            if resource_id in resource_ids:
                raise ValueError("Calendar inventory contains a duplicate identity")
            resource_ids.add(resource_id)
            zone = None
            try:
                provider_id(provider_string(item, "accessRole"))
                zone = calendar_zone(provider_string(item, "timeZone"))
            except ValueError:
                pass
            resources.append(CalendarResource(resource_id, zone))
        progress["page_token"] = _page_token(payload)
        complete = progress["page_token"] is None
        if complete:
            progress["scan_id"] = None
        await self._commit(
            cursor,
            progress,
            complete=complete,
            inventory=resources,
            inventory_complete=complete,
        )

    async def _changes(self, cursor: Cursor) -> None:
        progress = dict(cursor.progress)
        params: dict[str, str | int | list[str]] = {
            "singleEvents": "false",
            "showDeleted": "true",
            "showHiddenInvitations": "true",
            "maxResults": _PAGE_SIZE,
            "fields": _EVENT_FIELDS,
        }
        if progress["sync_token"] is not None:
            params["syncToken"] = str(progress["sync_token"])
        if progress["page_token"] is not None:
            params["pageToken"] = str(progress["page_token"])
        try:
            payload = await self._read(
                cursor,
                (
                    f"{CALENDAR_API_BASE_URL}/calendars/"
                    f"{quote(cursor.resource_id, safe='')}/events"
                ),
                params,
            )
        except _ReadFailed as exc:
            if exc.status != 410:
                raise
            await self._commit(
                cursor, {"sync_token": None, "page_token": None}, gap=True
            )
            return
        rows = provider_array(payload.get("items", []), "Calendar changes")
        next_page = _page_token(payload)
        sync_token = _page_token(payload, "nextSyncToken")
        if next_page is None and sync_token is None:
            raise ValueError("completed Calendar scan lacks sync token")
        observations: list[Observation] = []
        if progress["sync_token"] is not None:
            zone = calendar_zone(provider_string(payload, "timeZone"))
            for raw in rows:
                item = provider_object(raw, "Calendar event")
                event_id = provider_id(provider_string(item, "id"))
                etag = _page_token(item, "etag")
                revision = (
                    {"kind": "etag", "value": etag}
                    if etag is not None
                    else {"kind": "sync_base", "value": progress["sync_token"]}
                )
                identity = (cursor.account_id, cursor.resource_id, event_id, revision)
                if await self._store.is_published("calendar_event", identity):
                    continue
                if etag is not None and await self._store.has_echo(
                    "calendar",
                    calendar_id=cursor.resource_id,
                    event_id=event_id,
                    etag=etag,
                ):
                    continue
                projection = _projection(
                    item,
                    calendar_id=cursor.resource_id,
                    name=payload.get("summary"),
                    zone=zone,
                )
                now = self._now()
                observations.append(
                    Observation(
                        "calendar_event",
                        identity,
                        CalendarChanged(
                            account=cursor.account_id, observed_at=now, event=projection
                        ),
                        projection.updated_at or now,
                    )
                )
        progress["page_token"] = next_page
        if next_page is None:
            progress["sync_token"] = sync_token
        await self._commit(cursor, progress, observations, complete=next_page is None)

    async def _upcoming(self, cursor: Cursor) -> None:
        progress = dict(cursor.progress)
        zone = calendar_zone(str(progress["calendar_zone"]))
        scan = progress["scan"]
        now = self._now()
        owner_date = now.astimezone(ZoneInfo(self._owner_zone)).date()
        if scan is not None and (
            cast("dict[str,object]", scan)["owner_zone"] != self._owner_zone
            or cast("dict[str,object]", scan)["owner_date"] != owner_date.isoformat()
        ):
            progress["scan"] = None
            await self._commit(cursor, progress)
            return
        if scan is None:
            lower = min(now, resolve_civil(owner_date, civil_time.min, ZoneInfo(zone)))
            upper = max(
                now + timedelta(minutes=15),
                resolve_civil(
                    owner_date + timedelta(days=1), civil_time.min, ZoneInfo(zone)
                ),
            )
            progress["scan"] = {
                "as_of": now.isoformat(),
                "owner_zone": self._owner_zone,
                "owner_date": owner_date.isoformat(),
                "time_min": (
                    lower.replace(microsecond=0) - timedelta(seconds=1)
                ).isoformat(),
                "time_max": (
                    upper.replace(microsecond=0) + timedelta(seconds=1)
                ).isoformat(),
                "page_token": None,
            }
            await self._commit(cursor, progress)
            return
        scan = dict(cast("dict[str,object]", scan))
        params: dict[str, str | int | list[str]] = {
            "singleEvents": "true",
            "showDeleted": "false",
            "showHiddenInvitations": "true",
            "maxResults": _PAGE_SIZE,
            "fields": _EVENT_FIELDS,
            "timeMin": str(scan["time_min"]),
            "timeMax": str(scan["time_max"]),
        }
        if scan["page_token"] is not None:
            params["pageToken"] = str(scan["page_token"])
        payload = await self._read(
            cursor,
            (
                f"{CALENDAR_API_BASE_URL}/calendars/"
                f"{quote(cursor.resource_id, safe='')}/events"
            ),
            params,
        )
        response_zone = calendar_zone(provider_string(payload, "timeZone"))
        if response_zone != zone:
            progress["calendar_zone"] = response_zone
            progress["scan"] = None
            await self._commit(cursor, progress)
            return
        observations: list[Observation] = []
        for raw in provider_array(payload.get("items", []), "Calendar attention"):
            item = provider_object(raw, "Calendar attention event")
            if item.get("status") == "cancelled":
                continue
            start_time = parse_calendar_time(item.get("start"))
            logical: object = provider_id(provider_string(item, "id"))
            parent = _optional_id(item, "recurringEventId")
            if parent is not None:
                logical = {
                    "parent": parent,
                    "original_start": _time_identity(
                        parse_calendar_time(item.get("originalStartTime"))
                    ),
                }
            identity: tuple[object, ...] = (
                cursor.account_id,
                cursor.resource_id,
                logical,
                _time_identity(start_time),
            )
            if isinstance(start_time, AllDayEventTime):
                identity = (*identity, self._owner_zone)
            if await self._store.is_published("calendar_attention", identity):
                continue
            event = _projection(
                item,
                calendar_id=cursor.resource_id,
                name=payload.get("summary"),
                zone=zone,
            )
            due = attention_due(event, self._now(), self._owner_zone)
            if due is None:
                continue
            observations.append(
                Observation(
                    "calendar_attention",
                    identity,
                    CalendarAttention(
                        account=cursor.account_id,
                        observed_at=self._now(),
                        event=event,
                        due_at=due,
                        owner_zone=self._owner_zone,
                    ),
                    due,
                )
            )
        scan["page_token"] = _page_token(payload)
        complete = scan["page_token"] is None
        progress["scan"] = None if complete else scan
        await self._commit(cursor, progress, observations, complete=complete)

"""Bounded host-owned Google connector clients for Slice 2 reads."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import math
import re
import secrets
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email import message_from_string, policy
from email.parser import Parser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from llm_tools import canonical_json_bytes
from pydantic import ValidationError

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis.read_tools import (
    CALENDAR_API_BASE_URL,
    CALENDAR_EVENT_CONCURRENCY,
    CALENDAR_EVENT_DEADLINE_SECONDS,
    CALENDAR_EVENT_PAGE_SIZE,
    GMAIL_API_BASE_URL,
    MAX_CALENDAR_EVENT_PAGE_REQUESTS,
    MAX_CALENDAR_EVENTS,
    MAX_CALENDAR_LIST_ENTRIES,
    MAX_CALENDAR_SUCCESS_BYTES,
    PLACE_DETAILS_FIELD_MASK,
    PLACES_API_BASE_URL,
    PLACES_SEARCH_FIELD_MASK,
    ROUTES_API_URL,
    ROUTES_FIELD_MASK,
    AllDayEventTime,
    CalendarCancelledEvent,
    CalendarCoverage,
    CalendarCoverageReason,
    CalendarEventReadFailure,
    CalendarGetEventInput,
    CalendarGetEventSuccess,
    CalendarListCalendarsInput,
    CalendarListCalendarsSuccess,
    CalendarListCancelledEvent,
    CalendarListEventsInput,
    CalendarListEventsSuccess,
    CalendarListNormalEvent,
    CalendarNormalEvent,
    CalendarObservedWritableEvent,
    CalendarParticipant,
    CalendarReference,
    ConnectorFailure,
    Coordinates,
    GmailAttachment,
    GmailMessage,
    GmailReadThreadInput,
    GmailReadThreadSuccess,
    GmailSearchInput,
    GmailSearchSuccess,
    GmailThreadHit,
    Mailbox,
    MapsDirectionsInput,
    MapsDirectionsSuccess,
    MapsGetPlaceInput,
    MapsGetPlaceSuccess,
    MapsSearchPlacesInput,
    MapsSearchPlacesSuccess,
    Place,
    ReadResponse,
    Reminder,
    Route,
    TimedEventTime,
    UnspecifiedEventEnd,
)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_STATE_SCHEMA = "jarvis.google-oauth-state.v1"
GOOGLE_STATE_PROVIDER = "google"
GOOGLE_AAD_NAMESPACE = "jarvis.connector.google"
MAX_PROVIDER_BODY_BYTES = 2 * 1_024 * 1_024
_GOOGLE_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/calendar.acls.readonly",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    }
)
_KEY_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_TOKEN_ENVELOPE_PREFIX = "aesgcm.v1."
_MAX_GOOGLE_TOKEN_BYTES = 16 * 1_024
_MAX_TOKEN_CIPHERTEXT_BYTES = 12 + _MAX_GOOGLE_TOKEN_BYTES + 16
_MAX_TOKEN_ENVELOPE_CHARS = (
    len(_TOKEN_ENVELOPE_PREFIX) + (4 * _MAX_TOKEN_CIPHERTEXT_BYTES + 2) // 3
)
_TokenField = Literal["access_token", "refresh_token"]
type _CalendarFailureType = Literal[
    "CalendarNotFound",
    "InvalidRange",
    "RateLimited",
    "ProviderUnavailable",
    "ProviderResponseTooLarge",
]


class GoogleCredentialDefect(RuntimeError):
    """The host-owned Google credential state is invalid or unusable."""


class _ProviderTooLarge(ValueError):
    pass


class _InertHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"br", "div", "li", "p", "tr"}:
            self.parts.append("\n")


def _b64decode(value: str) -> bytes:
    if not value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise GoogleCredentialDefect("connector encryption material is invalid")
    try:
        return base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise GoogleCredentialDefect(
            "connector encryption material is invalid"
        ) from None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token_bytes(value: str) -> bytes:
    encoded = value.encode()
    if not value or len(encoded) > _MAX_GOOGLE_TOKEN_BYTES:
        raise ValueError("Google token value is malformed")
    return encoded


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} is malformed")
    return cast("dict[str, object]", value)


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} is malformed")
    return cast("list[object]", value)


def _handoff_key(single_secret: str) -> bytes:
    decoded = _b64decode(single_secret)
    return decoded if len(decoded) == 32 else hashlib.sha256(decoded).digest()


class GoogleTokenManager:
    """Decrypt, refresh, and atomically persist the reused Google OAuth grant."""

    def __init__(
        self,
        *,
        state_path: Path,
        client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        active_key_version: str,
        single_secret: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not state_path.is_absolute():
            raise GoogleCredentialDefect("Google state path must be absolute")
        if (
            not client_id
            or not client_secret
            or _KEY_VERSION.fullmatch(active_key_version) is None
        ):
            raise GoogleCredentialDefect(
                "Google credential configuration is incomplete"
            )
        self._state_path = state_path
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._active_key_version = active_key_version
        self._handoff_key = _handoff_key(single_secret)
        self._now = now
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._force_refresh = False

    async def access_token(
        self, *, attempt_started: Callable[[], None] | None = None
    ) -> tuple[str, int]:
        now = self._now()
        if now.tzinfo is None:
            raise RuntimeError("Google credential clock must be aware")
        if (
            self._access_token is not None
            and self._expires_at is not None
            and self._expires_at > now + timedelta(seconds=60)
            and not self._force_refresh
        ):
            return self._access_token, 0
        state = self._load_state()
        encryption = cast("dict[str, object]", state["encryption"])
        key_version = cast("str", encryption["key_version"])
        try:
            expires_at = _instant(_required_string(state, "access_token_expires_at"))
            access_token = self._decrypt(
                _required_string(state, "access_token_enc"),
                field="access_token",
                key_version=key_version,
            )
        except ValueError as exc:
            raise GoogleCredentialDefect(
                "Google credential state is malformed"
            ) from exc
        if expires_at > now + timedelta(seconds=60) and not self._force_refresh:
            self._access_token = access_token
            self._expires_at = expires_at
            return access_token, 0
        try:
            refresh_token = self._decrypt(
                _required_string(state, "refresh_token_enc"),
                field="refresh_token",
                key_version=key_version,
            )
        except ValueError as exc:
            raise GoogleCredentialDefect(
                "Google credential state is malformed"
            ) from exc
        try:
            if attempt_started is not None:
                attempt_started()
            async with (
                asyncio.timeout(4.0),
                self._client.stream(
                    "POST",
                    GOOGLE_TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    headers={"Accept": "application/json"},
                    follow_redirects=False,
                    timeout=httpx.Timeout(5.0, connect=2.0),
                ) as response,
            ):
                if response.status_code == 429:
                    raise ConnectorFailure("rate_limited", attempts=1)
                if response.status_code >= 500:
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                if response.status_code != 200:
                    error_payload = await _json_body(response, attempts=1)
                    if error_payload.get("error") in {
                        "invalid_client",
                        "invalid_grant",
                    }:
                        raise GoogleCredentialDefect("Google OAuth grant is unusable")
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                payload = await _json_body(response, attempts=1)
        except (TimeoutError, httpx.HTTPError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        try:
            token = _required_string(payload, "access_token")
            _token_bytes(token)
            expires_in = payload.get("expires_in")
            if (
                type(expires_in) is not int
                or expires_in <= 60
                or expires_in > 31_536_000
            ):
                raise ValueError("Google OAuth expiry is malformed")
            token_type = payload.get("token_type")
            if not isinstance(token_type, str) or token_type.lower() != "bearer":
                raise ValueError("Google OAuth token type is malformed")
            returned_scope = payload.get("scope")
            if returned_scope is not None:
                if not isinstance(returned_scope, str):
                    raise ValueError("Google OAuth scope is malformed")
                scope_values = returned_scope.split()
                if len(scope_values) != 7 or frozenset(scope_values) != _GOOGLE_SCOPES:
                    raise GoogleCredentialDefect("Google OAuth scope changed")
        except GoogleCredentialDefect:
            raise
        except ValueError:
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        refreshed_at = now.astimezone(UTC)
        refreshed_expiry = refreshed_at + timedelta(seconds=expires_in)
        updated = dict(state)
        updated["access_token_enc"] = self._encrypt(token, field="access_token")
        updated["access_token_expires_at"] = refreshed_expiry.isoformat()
        updated["token_obtained_at"] = refreshed_at.isoformat()
        returned_refresh = payload.get("refresh_token")
        if returned_refresh is not None:
            if not isinstance(returned_refresh, str) or not returned_refresh:
                raise ConnectorFailure("provider_unavailable", attempts=1)
            try:
                _token_bytes(returned_refresh)
            except ValueError:
                raise ConnectorFailure("provider_unavailable", attempts=1) from None
            refresh_token = returned_refresh
        updated["refresh_token_enc"] = self._encrypt(
            refresh_token, field="refresh_token"
        )
        updated["encryption"] = {
            "aad_namespace": f"{GOOGLE_AAD_NAMESPACE}:{self._active_key_version}",
            "algorithm": "AES-256-GCM",
            "key_version": self._active_key_version,
        }
        replace_private_json(self._state_path, updated)
        self._access_token = token
        self._expires_at = refreshed_expiry
        self._force_refresh = False
        return token, 1

    def invalidate_access_token(self) -> None:
        self._access_token = None
        self._expires_at = None
        self._force_refresh = True

    def _load_state(self) -> Mapping[str, object]:
        try:
            state = read_private_json(self._state_path)
        except ValueError as exc:
            raise GoogleCredentialDefect("Google credential state is unsafe") from exc
        if state is None:
            raise GoogleCredentialDefect("Google credential state is absent")
        encryption = state.get("encryption")
        scopes = state.get("granted_scopes")
        encryption_value = (
            cast("dict[str, object]", encryption)
            if isinstance(encryption, dict)
            else {}
        )
        scopes_value = cast("list[object]", scopes) if isinstance(scopes, list) else []
        key_version = encryption_value.get("key_version")
        if (
            state.get("schema") != GOOGLE_STATE_SCHEMA
            or state.get("provider") != GOOGLE_STATE_PROVIDER
            or state.get("status") != "connected"
            or not isinstance(key_version, str)
            or encryption_value.get("algorithm") != "AES-256-GCM"
            or encryption_value.get("aad_namespace")
            != f"{GOOGLE_AAD_NAMESPACE}:{key_version}"
            or len(scopes_value) != 7
            or any(not isinstance(scope, str) for scope in scopes_value)
            or frozenset(cast("list[str]", scopes_value)) != _GOOGLE_SCOPES
        ):
            raise GoogleCredentialDefect("Google credential state contract is invalid")
        return state

    def _decrypt(self, envelope: str, *, field: _TokenField, key_version: str) -> str:
        if len(envelope) > _MAX_TOKEN_ENVELOPE_CHARS or not envelope.startswith(
            _TOKEN_ENVELOPE_PREFIX
        ):
            raise GoogleCredentialDefect("Google token envelope is malformed")
        encoded = envelope.removeprefix(_TOKEN_ENVELOPE_PREFIX)
        combined = _b64decode(encoded)
        if (
            len(combined) < 28
            or len(combined) > _MAX_TOKEN_CIPHERTEXT_BYTES
            or _b64encode(combined) != encoded
        ):
            raise GoogleCredentialDefect("Google token envelope is malformed")
        nonce = combined[:12]
        ciphertext = combined[12:]
        try:
            plaintext = AESGCM(self._handoff_key).decrypt(
                nonce,
                ciphertext,
                f"{GOOGLE_AAD_NAMESPACE}:{key_version}:{field}".encode(),
            )
            value = plaintext.decode()
        except (InvalidTag, UnicodeDecodeError):
            raise GoogleCredentialDefect("Google token decryption failed") from None
        if not value or len(plaintext) > _MAX_GOOGLE_TOKEN_BYTES:
            raise GoogleCredentialDefect("Google token value is malformed")
        return value

    def _encrypt(self, value: str, *, field: _TokenField) -> str:
        version = self._active_key_version
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._handoff_key).encrypt(
            nonce,
            _token_bytes(value),
            f"{GOOGLE_AAD_NAMESPACE}:{version}:{field}".encode(),
        )
        return f"{_TOKEN_ENVELOPE_PREFIX}{_b64encode(nonce + ciphertext)}"


class GoogleReadConnector:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        tokens: GoogleTokenManager,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._now = now

    async def gmail_search(
        self, value: GmailSearchInput
    ) -> ReadResponse[GmailSearchSuccess]:
        if not value.query.strip():
            raise ConnectorFailure("invalid_query", attempts=0)
        payload, attempts = await self._get(
            f"{GMAIL_API_BASE_URL}/users/me/threads",
            params={
                "includeSpamTrash": "false",
                "maxResults": value.max_results,
                "q": value.query,
            },
            invalid_request="invalid_query",
        )
        try:
            raw_threads = _array(payload.get("threads", []), "Gmail threads")
            hits: list[GmailThreadHit] = []
            truncated = _has_next_page(payload) or len(raw_threads) > value.max_results
            for raw in raw_threads[: value.max_results]:
                item = _mapping(raw, "Gmail thread")
                snippet, shortened = _truncate(
                    _optional_string(item, "snippet", ""), 1_000
                )
                hits.append(
                    GmailThreadHit(
                        thread_id=_exact(_required_string(item, "id"), 1_024),
                        snippet=snippet,
                    )
                )
                truncated = truncated or shortened
            result = GmailSearchSuccess(
                threads=tuple(hits),
                truncated=truncated,
                observed_at=self._observed_at(),
            )
        except _ProviderTooLarge as exc:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from exc
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
        return ReadResponse(result, attempts)

    async def gmail_read_thread(
        self, value: GmailReadThreadInput
    ) -> ReadResponse[GmailReadThreadSuccess]:
        path = quote(value.thread_id, safe="")
        payload, attempts = await self._get(
            f"{GMAIL_API_BASE_URL}/users/me/threads/{path}",
            params={"format": "full"},
            not_found="thread_not_found",
        )
        try:
            thread_id = _exact(_required_string(payload, "id"), 1_024)
            if thread_id != value.thread_id:
                raise ValueError("Gmail returned a different thread")
            raw_messages = _array(payload.get("messages", []), "Gmail messages")
            ordered = sorted(raw_messages, key=_gmail_internal_millis)
            selected = ordered[-value.max_messages :]
            messages: list[GmailMessage] = []
            aggregate = 0
            root_truncated = len(ordered) > len(selected)
            for raw in selected:
                message, attachment_cap = _gmail_message(raw)
                if message.thread_id != thread_id:
                    raise ValueError("Gmail message has a different thread")
                remaining = max(0, 65_536 - aggregate)
                bounded, aggregate_cut = _truncate(message.body_text, remaining)
                if aggregate_cut:
                    message = message.model_copy(
                        update={"body_text": bounded, "body_truncated": True}
                    )
                aggregate += len(message.body_text.encode())
                messages.append(message)
                root_truncated = (
                    root_truncated or attachment_cap or message.body_truncated
                )
            result = GmailReadThreadSuccess(
                thread_id=thread_id,
                messages=tuple(messages),
                truncated=root_truncated,
                observed_at=self._observed_at(),
            )
        except _ProviderTooLarge as exc:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from exc
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
        return ReadResponse(result, attempts)

    async def calendar_list_calendars(
        self, value: CalendarListCalendarsInput
    ) -> ReadResponse[CalendarListCalendarsSuccess]:
        del value
        payload, attempts = await self._get(
            f"{CALENDAR_API_BASE_URL}/users/me/calendarList",
            params={
                "maxResults": 50,
                "minAccessRole": "reader",
                "showDeleted": "false",
                "showHidden": "true",
            },
        )
        try:
            calendars, truncated = _calendar_references(payload)
            result = CalendarListCalendarsSuccess(
                calendars=calendars,
                truncated=truncated,
                observed_at=self._observed_at(),
            )
        except _ProviderTooLarge as exc:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from exc
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
        return ReadResponse(result, attempts)

    async def calendar_list_events(
        self, value: CalendarListEventsInput
    ) -> ReadResponse[CalendarListEventsSuccess]:
        try:
            time_min = value.time_min.astimezone(UTC)
            time_max = value.time_max.astimezone(UTC)
        except (OverflowError, ValueError):
            raise ConnectorFailure("invalid_range", attempts=0) from None
        if time_min >= time_max:
            raise ConnectorFailure("invalid_range", attempts=0)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + CALENDAR_EVENT_DEADLINE_SECONDS
        attempts = 0

        def attempted() -> None:
            nonlocal attempts
            attempts += 1

        try:
            list_payload, _ = await asyncio.wait_for(
                self._get(
                    f"{CALENDAR_API_BASE_URL}/users/me/calendarList",
                    params={
                        "maxResults": 50,
                        "minAccessRole": "reader",
                        "showDeleted": "false",
                        "showHidden": "true",
                    },
                    attempt_started=attempted,
                ),
                timeout=max(0.0, deadline - loop.time()),
            )
        except TimeoutError:
            result = CalendarListEventsSuccess(
                calendars=(),
                events=(),
                failures=(),
                coverage=CalendarCoverage(
                    complete=False,
                    reasons=("deadline",),
                    calendars_discovered=0,
                    calendars_completed=0,
                    matched_events=None,
                ),
                observed_at=self._observed_at(),
            )
            return ReadResponse(result, attempts)
        try:
            calendars, calendars_truncated = _calendar_references(list_payload)
        except _ProviderTooLarge as exc:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from exc
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None

        semaphore = asyncio.Semaphore(CALENDAR_EVENT_CONCURRENCY)

        async def read_page(
            calendar: CalendarReference, page_token: str | None
        ) -> tuple[
            tuple[CalendarListNormalEvent | CalendarListCancelledEvent, ...],
            CalendarEventReadFailure | None,
            str | None,
        ]:
            async with semaphore:
                page_attempts = 0

                def page_attempted() -> None:
                    nonlocal page_attempts
                    page_attempts += 1
                    attempted()

                try:
                    params: dict[str, str | int] = {
                        "maxResults": CALENDAR_EVENT_PAGE_SIZE,
                        "orderBy": "startTime",
                        "showDeleted": "true",
                        "singleEvents": "true",
                        "timeMax": _rfc3339(time_max),
                        "timeMin": _rfc3339(time_min),
                        "timeZone": value.time_zone,
                    }
                    if page_token is not None:
                        params["pageToken"] = page_token
                    payload, _ = await self._get(
                        f"{CALENDAR_API_BASE_URL}/calendars/"
                        f"{quote(calendar.calendar_id, safe='')}/events",
                        params=params,
                        not_found="calendar_not_found",
                        invalid_request="invalid_range",
                        attempt_started=page_attempted,
                    )
                    items = _array(payload.get("items", []), "Calendar events")
                    if len(items) > CALENDAR_EVENT_PAGE_SIZE:
                        raise _ProviderTooLarge
                    return (
                        tuple(
                            _calendar_list_event(calendar.calendar_id, item)
                            for item in items
                        ),
                        None,
                        _next_page_token(payload),
                    )
                except _ProviderTooLarge:
                    return (
                        (),
                        CalendarEventReadFailure(
                            calendar_id=calendar.calendar_id,
                            error="ProviderResponseTooLarge",
                        ),
                        None,
                    )
                except ConnectorFailure as exc:
                    for _ in range(max(0, exc.attempts - page_attempts)):
                        attempted()
                    return (
                        (),
                        CalendarEventReadFailure(
                            calendar_id=calendar.calendar_id,
                            error=_calendar_failure_type(exc.code),
                        ),
                        None,
                    )
                except (TypeError, ValueError, ValidationError):
                    return (
                        (),
                        CalendarEventReadFailure(
                            calendar_id=calendar.calendar_id,
                            error="ProviderUnavailable",
                        ),
                        None,
                    )

        all_events: list[CalendarListNormalEvent | CalendarListCancelledEvent] = []
        failures: dict[str, CalendarEventReadFailure] = {}
        completed: set[str] = set()
        pending_pages: list[tuple[CalendarReference, str | None]] = [
            (calendar, None)
            for calendar in sorted(calendars, key=lambda item: item.calendar_id)
        ]
        page_requests = 0
        deadline_reached = False
        page_limit_reached = False

        while pending_pages:
            if loop.time() >= deadline:
                deadline_reached = True
                break
            remaining_requests = MAX_CALENDAR_EVENT_PAGE_REQUESTS - page_requests
            if remaining_requests <= 0:
                page_limit_reached = True
                break
            batch = pending_pages[:remaining_requests]
            if len(batch) != len(pending_pages):
                page_limit_reached = True
            page_requests += len(batch)
            tasks = [
                asyncio.create_task(read_page(calendar, page_token))
                for calendar, page_token in batch
            ]
            try:
                done, waiting = await asyncio.wait(
                    tasks,
                    timeout=max(0.0, deadline - loop.time()),
                )
            except asyncio.CancelledError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            if waiting:
                for task in waiting:
                    task.cancel()
                await asyncio.gather(*waiting, return_exceptions=True)
                deadline_reached = True

            next_round: list[tuple[CalendarReference, str | None]] = []
            for (calendar, _), task in zip(batch, tasks, strict=True):
                if task not in done:
                    continue
                events, failure, page_token = task.result()
                all_events.extend(events)
                if failure is not None:
                    failures[calendar.calendar_id] = failure
                elif page_token is None:
                    completed.add(calendar.calendar_id)
                else:
                    next_round.append((calendar, page_token))
            if loop.time() >= deadline:
                deadline_reached = True
            if deadline_reached or page_limit_reached:
                break
            pending_pages = next_round

        try:
            all_events.sort(
                key=lambda event: _calendar_list_event_sort_key(event, value.time_zone)
            )
            reasons: set[CalendarCoverageReason] = set()
            if calendars_truncated:
                reasons.add("calendar_limit")
            if failures:
                reasons.add("calendar_failure")
            if page_limit_reached:
                reasons.add("event_page_limit")
            if deadline_reached:
                reasons.add("deadline")
            pages_exhausted = (
                not failures
                and not page_limit_reached
                and not deadline_reached
                and len(completed) == len(calendars)
            )
            matched_events = len(all_events) if pages_exhausted else None
            if len(all_events) > MAX_CALENDAR_EVENTS:
                reasons.add("event_limit")
            selected_events = tuple(all_events[:MAX_CALENDAR_EVENTS])
            observed_at = self._observed_at()
            ordered_failures = tuple(
                failures[calendar_id] for calendar_id in sorted(failures)
            )

            def success(
                events: tuple[
                    CalendarListNormalEvent | CalendarListCancelledEvent, ...
                ],
                coverage_reasons: set[CalendarCoverageReason],
            ) -> CalendarListEventsSuccess:
                return CalendarListEventsSuccess(
                    calendars=calendars,
                    events=events,
                    failures=ordered_failures,
                    coverage=CalendarCoverage(
                        complete=not coverage_reasons,
                        reasons=tuple(sorted(coverage_reasons)),
                        calendars_discovered=len(calendars),
                        calendars_completed=len(completed),
                        matched_events=matched_events,
                    ),
                    observed_at=observed_at,
                )

            result = success(selected_events, reasons)
            envelope = {"type": "Success", "value": result.model_dump(mode="json")}
            if len(canonical_json_bytes(envelope)) > MAX_CALENDAR_SUCCESS_BYTES:
                reasons.add("output_byte_limit")
                lower = 0
                upper = len(selected_events)
                fitting: CalendarListEventsSuccess | None = None
                while lower <= upper:
                    event_count = (lower + upper) // 2
                    candidate = success(selected_events[:event_count], reasons)
                    envelope = {
                        "type": "Success",
                        "value": candidate.model_dump(mode="json"),
                    }
                    if (
                        len(canonical_json_bytes(envelope))
                        <= MAX_CALENDAR_SUCCESS_BYTES
                    ):
                        fitting = candidate
                        lower = event_count + 1
                    else:
                        upper = event_count - 1
                if fitting is None:
                    raise _ProviderTooLarge
                result = fitting
        except _ProviderTooLarge as exc:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from exc
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
        return ReadResponse(result, attempts)

    async def calendar_get_event(
        self, value: CalendarGetEventInput
    ) -> ReadResponse[CalendarGetEventSuccess]:
        calendar_id = quote(value.calendar_id, safe="")
        event_id = quote(value.event_id, safe="")
        payload, attempts = await self._get(
            f"{CALENDAR_API_BASE_URL}/calendars/{calendar_id}/events/{event_id}",
            not_found="event_not_found",
        )
        try:
            event = _calendar_event(value.calendar_id, payload)
            if event.event_id != value.event_id:
                raise ValueError("Calendar returned a different event")
            result = CalendarGetEventSuccess(
                event=event,
                observed_at=self._observed_at(),
            )
        except _ProviderTooLarge as exc:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from exc
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
        return ReadResponse(result, attempts)

    async def _get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        not_found: str | None = None,
        invalid_request: str | None = None,
        attempt_started: Callable[[], None] | None = None,
    ) -> tuple[dict[str, object], int]:
        token, refresh_attempts = await self._tokens.access_token(
            attempt_started=attempt_started
        )
        try:
            if attempt_started is not None:
                attempt_started()
            async with (
                asyncio.timeout(8.0),
                self._client.stream(
                    "GET",
                    url,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    follow_redirects=False,
                    timeout=httpx.Timeout(8.0, connect=3.0),
                ) as response,
            ):
                attempts = refresh_attempts + 1
                if response.status_code == 404 and not_found is not None:
                    raise ConnectorFailure(not_found, attempts=attempts)
                if response.status_code == 429:
                    raise ConnectorFailure("rate_limited", attempts=attempts)
                if response.status_code == 403:
                    code = await _google_forbidden_code(response, attempts=attempts)
                    raise ConnectorFailure(code, attempts=attempts)
                if response.status_code == 401:
                    self._tokens.invalidate_access_token()
                    raise ConnectorFailure("provider_unavailable", attempts=attempts)
                if response.status_code == 400:
                    raise ConnectorFailure(
                        invalid_request or "provider_unavailable", attempts=attempts
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise ConnectorFailure("provider_unavailable", attempts=attempts)
                payload = await _json_body(response, attempts=attempts)
        except (TimeoutError, httpx.HTTPError):
            raise ConnectorFailure(
                "provider_unavailable", attempts=refresh_attempts + 1
            ) from None
        return payload, attempts

    def _observed_at(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("connector clock must be aware")
        return value.astimezone(UTC)


class MapsReadConnector:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not api_key:
            raise ValueError("Maps key must not be empty")
        self._client = client
        self._api_key = api_key
        self._now = now

    async def search_places(
        self, value: MapsSearchPlacesInput
    ) -> ReadResponse[MapsSearchPlacesSuccess]:
        if not value.query.strip():
            raise ConnectorFailure("invalid_query", attempts=0)
        body: dict[str, object] = {
            "textQuery": value.query,
            "pageSize": value.max_results,
        }
        if value.location_bias is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": value.location_bias.latitude,
                        "longitude": value.location_bias.longitude,
                    },
                    "radius": value.location_bias.radius_m,
                }
            }
        payload = await self._request(
            "POST",
            f"{PLACES_API_BASE_URL}/places:searchText",
            field_mask=PLACES_SEARCH_FIELD_MASK,
            json_body=body,
            invalid_request="invalid_query",
        )
        try:
            raw_places = _array(payload.get("places", []), "Places results")
            if len(raw_places) > value.max_results:
                raise _ProviderTooLarge
            result = MapsSearchPlacesSuccess(
                places=tuple(_place(item) for item in raw_places),
                observed_at=self._observed_at(),
            )
        except _ProviderTooLarge:
            raise ConnectorFailure("provider_response_too_large", attempts=1) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(result, 1)

    async def get_place(
        self, value: MapsGetPlaceInput
    ) -> ReadResponse[MapsGetPlaceSuccess]:
        payload = await self._request(
            "GET",
            f"{PLACES_API_BASE_URL}/places/{quote(value.place_id, safe='')}",
            field_mask=PLACE_DETAILS_FIELD_MASK,
            not_found="place_not_found",
            invalid_request="place_not_found",
        )
        try:
            place = _place(payload)
            if place.place_id != value.place_id:
                raise ValueError("Places returned a different stable identity")
            result = MapsGetPlaceSuccess(place=place, observed_at=self._observed_at())
        except _ProviderTooLarge:
            raise ConnectorFailure("provider_response_too_large", attempts=1) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(result, 1)

    async def directions(
        self, value: MapsDirectionsInput
    ) -> ReadResponse[MapsDirectionsSuccess]:
        now = self._observed_at()
        departure: datetime | None = None
        if value.departure_at is not None:
            try:
                departure = value.departure_at.astimezone(UTC)
            except (OverflowError, ValueError):
                raise ConnectorFailure("invalid_departure_time", attempts=0) from None
            if departure < now and value.travel_mode != "transit":
                raise ConnectorFailure("invalid_departure_time", attempts=0)
            if value.travel_mode == "transit" and not (
                now - timedelta(days=7) <= departure <= now + timedelta(days=100)
            ):
                raise ConnectorFailure("invalid_departure_time", attempts=0)
        body: dict[str, object] = {
            "origin": _waypoint(value.origin),
            "destination": _waypoint(value.destination),
            "travelMode": {
                "driving": "DRIVE",
                "walking": "WALK",
                "bicycling": "BICYCLE",
                "transit": "TRANSIT",
            }[value.travel_mode],
            "computeAlternativeRoutes": False,
        }
        if departure is not None:
            body["departureTime"] = _rfc3339(departure)
        payload = await self._request(
            "POST",
            ROUTES_API_URL,
            field_mask=ROUTES_FIELD_MASK,
            json_body=body,
            invalid_request="invalid_location",
        )
        try:
            raw_routes = _array(payload.get("routes", []), "Routes results")
            if not raw_routes:
                raise ConnectorFailure("no_route", attempts=1)
            if len(raw_routes) != 1:
                raise _ProviderTooLarge
            raw = _mapping(raw_routes[0], "route")
            warnings = _array(raw.get("warnings", []), "route warnings")
            if len(warnings) > 10:
                raise _ProviderTooLarge
            route = Route(
                distance_meters=_bounded_integer(raw.get("distanceMeters", 0)),
                duration_seconds=_duration(_required_string(raw, "duration")),
                description=_exact_optional(raw, "description", 1_000),
                warnings=tuple(_exact_string(item, 1_000) for item in warnings),
            )
            result = MapsDirectionsSuccess(routes=(route,), observed_at=now)
        except ConnectorFailure:
            raise
        except _ProviderTooLarge:
            raise ConnectorFailure("provider_response_too_large", attempts=1) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(result, 1)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        field_mask: str,
        json_body: Mapping[str, object] | None = None,
        not_found: str | None = None,
        invalid_request: str | None = None,
    ) -> dict[str, object]:
        try:
            headers = {
                "Accept": "application/json",
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": field_mask,
            }
            request_options: dict[str, Any] = {
                "headers": headers,
                "follow_redirects": False,
                "timeout": httpx.Timeout(12.0, connect=5.0),
            }
            if json_body is not None:
                headers["Content-Type"] = "application/json"
                request_options["json"] = json_body
            async with (
                asyncio.timeout(12.0),
                self._client.stream(
                    method,
                    url,
                    **request_options,
                ) as response,
            ):
                if response.status_code == 404 and not_found is not None:
                    raise ConnectorFailure(not_found, attempts=1)
                if response.status_code == 429:
                    raise ConnectorFailure("rate_limited", attempts=1)
                if response.status_code == 400:
                    raise ConnectorFailure(
                        invalid_request or "provider_unavailable", attempts=1
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                payload = await _json_body(response, attempts=1)
        except (TimeoutError, httpx.HTTPError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return payload

    def _observed_at(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("connector clock must be aware")
        return value.astimezone(UTC)


async def _json_body(response: httpx.Response, *, attempts: int) -> dict[str, object]:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > MAX_PROVIDER_BODY_BYTES:
            raise ConnectorFailure("provider_response_too_large", attempts=attempts)
        body.extend(chunk)
    try:
        value: object = json.loads(
            body,
            parse_constant=_reject_constant,
            object_pairs_hook=_strict_object,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ):
        raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
    if not isinstance(value, dict):
        raise ConnectorFailure("provider_unavailable", attempts=attempts)
    return cast("dict[str, object]", value)


def _reject_constant(value: str) -> None:
    del value
    raise ValueError("non-finite JSON number")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate provider JSON key")
        value[key] = item
    return value


async def _google_forbidden_code(response: httpx.Response, *, attempts: int) -> str:
    try:
        payload = await _json_body(response, attempts=attempts)
        error = _mapping(payload.get("error"), "Google error")
        errors = _array(error.get("errors", []), "Google errors")
        reasons: set[str] = set()
        for value in errors:
            reason = _mapping(value, "Google error item").get("reason")
            if not isinstance(reason, str):
                return "provider_unavailable"
            reasons.add(reason)
    except ConnectorFailure as exc:
        if exc.code == "provider_response_too_large":
            raise
        return "provider_unavailable"
    except ValueError:
        return "provider_unavailable"
    if reasons & {
        "dailyLimitExceeded",
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
    }:
        return "rate_limited"
    return "provider_unavailable"


def _has_next_page(value: Mapping[str, object]) -> bool:
    return _next_page_token(value) is not None


def _next_page_token(value: Mapping[str, object]) -> str | None:
    token = value.get("nextPageToken")
    if token is None:
        return None
    if not isinstance(token, str) or not token:
        raise ValueError("provider pagination token is malformed")
    return token


def _provider_boolean(value: Mapping[str, object], key: str, *, default: bool) -> bool:
    result = value.get(key, default)
    if type(result) is not bool:
        raise ValueError(f"provider field {key} is malformed")
    return result


def _calendar_references(
    payload: Mapping[str, object],
) -> tuple[tuple[CalendarReference, ...], bool]:
    items = _array(payload.get("items", []), "Calendar list")
    truncated = _has_next_page(payload) or len(items) > MAX_CALENDAR_LIST_ENTRIES
    calendars: list[CalendarReference] = []
    seen: set[str] = set()
    for raw in items[:MAX_CALENDAR_LIST_ENTRIES]:
        item = _mapping(raw, "Calendar list entry")
        calendar_id = _exact(_required_string(item, "id"), 1_024)
        if calendar_id in seen:
            raise ValueError("Calendar list contains a duplicate identity")
        seen.add(calendar_id)
        display_name = item.get("summaryOverride", item.get("summary"))
        if display_name is not None and not isinstance(display_name, str):
            raise ValueError("Calendar display name is malformed")
        time_zone = item.get("timeZone")
        if time_zone is not None and not isinstance(time_zone, str):
            raise ValueError("Calendar time zone is malformed")
        calendars.append(
            CalendarReference(
                calendar_id=calendar_id,
                display_name=(
                    _exact(display_name, 1_024)
                    if isinstance(display_name, str)
                    else None
                ),
                time_zone=(
                    _exact(time_zone, 255) if isinstance(time_zone, str) else None
                ),
                access_role=cast("Any", _required_string(item, "accessRole")),
                primary=_provider_boolean(item, "primary", default=False),
                hidden=_provider_boolean(item, "hidden", default=False),
                selected=_provider_boolean(item, "selected", default=False),
            )
        )
    return tuple(calendars), truncated


def _calendar_failure_type(code: str) -> _CalendarFailureType:
    failures: dict[str, _CalendarFailureType] = {
        "calendar_not_found": "CalendarNotFound",
        "invalid_range": "InvalidRange",
        "rate_limited": "RateLimited",
        "provider_unavailable": "ProviderUnavailable",
        "provider_response_too_large": "ProviderResponseTooLarge",
    }
    return failures.get(code, "ProviderUnavailable")


def _required_string(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"provider field {key} is missing")
    return result


def _optional_string(value: Mapping[str, object], key: str, default: str) -> str:
    result = value.get(key, default)
    if not isinstance(result, str):
        raise ValueError(f"provider field {key} is malformed")
    return result


def _exact(value: str, maximum: int) -> str:
    if len(value.encode()) > maximum:
        raise _ProviderTooLarge
    return value


def _exact_string(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("provider string is malformed")
    return _exact(value, maximum)


def _exact_optional(value: Mapping[str, object], key: str, maximum: int) -> str | None:
    result = value.get(key)
    if result is None:
        return None
    return _exact_string(result, maximum)


def _truncate(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode()
    if len(encoded) <= maximum:
        return value, False
    return encoded[:maximum].decode("utf-8", errors="ignore"), True


_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _instant(value: str) -> datetime:
    text = _timestamp_text(value)
    if _RFC3339.fullmatch(text) is None:
        raise ValueError("provider timestamp is malformed")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    try:
        return parsed.astimezone(UTC)
    except OverflowError:
        raise _ProviderTooLarge from None


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


_FRACTION = re.compile(r"\.(\d+)(?=Z|[+-]\d\d:\d\d|$)")


def _timestamp_text(value: str) -> str:
    if len(value.encode()) > 64:
        raise _ProviderTooLarge
    match = _FRACTION.search(value)
    if match is None or len(match.group(1)) <= 6:
        return value
    fraction = match.group(1)
    if any(character != "0" for character in fraction[6:]):
        raise _ProviderTooLarge
    return value[: match.start(1)] + fraction[:6] + value[match.end(1) :]


def _gmail_internal_millis(value: object) -> int:
    message = _mapping(value, "Gmail message")
    raw = message.get("internalDate")
    if (
        not isinstance(raw, str)
        or not raw.isascii()
        or re.fullmatch(r"-?\d+", raw) is None
    ):
        raise ValueError("Gmail internal date is malformed")
    if len(raw.removeprefix("-")) > 15:
        raise _ProviderTooLarge
    millis = int(raw)
    if not -62_135_596_800_000 <= millis <= 253_402_300_799_999:
        raise _ProviderTooLarge
    return millis


def _gmail_message(value: object) -> tuple[GmailMessage, bool]:
    message = _mapping(value, "Gmail message")
    payload = _mapping(message.get("payload"), "Gmail payload")
    headers = _array(payload.get("headers", []), "Gmail headers")
    by_name: dict[str, list[str]] = {}
    for header in headers:
        header_value_map = _mapping(header, "Gmail header")
        name = header_value_map.get("name")
        header_value = header_value_map.get("value")
        if not isinstance(name, str) or not isinstance(header_value, str):
            raise ValueError("Gmail header is malformed")
        by_name.setdefault(name.lower(), []).append(header_value)
    plain: list[str] = []
    html_parts: list[str] = []
    attachments: list[GmailAttachment] = []
    attachment_cap, external_body = _walk_gmail_parts(
        payload, plain, html_parts, attachments, depth=0, visited=[0]
    )
    source = "\n".join(plain)
    if not plain and html_parts:
        parser = _InertHtml()
        parser.feed("\n".join(html_parts))
        parser.close()
        source = "".join(parser.parts)
    text, text_truncated = _truncate(source, 16_384)
    sender_values = _mailboxes(", ".join(by_name.get("from", [])))
    if len(sender_values) > 1:
        raise _ProviderTooLarge
    subject = _single_header(by_name, "subject") or ""
    rfc822_message_id = _single_header(by_name, "message-id")
    return (
        GmailMessage(
            message_id=_exact(_required_string(message, "id"), 1_024),
            thread_id=_exact(_required_string(message, "threadId"), 1_024),
            rfc822_message_id=(
                _exact(rfc822_message_id, 998)
                if rfc822_message_id is not None
                else None
            ),
            sender=sender_values[0] if sender_values else None,
            to=_mailboxes(", ".join(by_name.get("to", []))),
            cc=_mailboxes(", ".join(by_name.get("cc", []))),
            bcc=_mailboxes(", ".join(by_name.get("bcc", []))),
            subject=_exact(subject, 998),
            internal_at=datetime(1970, 1, 1, tzinfo=UTC)
            + timedelta(milliseconds=_gmail_internal_millis(message)),
            body_text=text,
            body_truncated=text_truncated or external_body,
            attachments=tuple(attachments[:50]),
        ),
        attachment_cap,
    )


def _walk_gmail_parts(
    part: Mapping[str, object],
    plain: list[str],
    html_parts: list[str],
    attachments: list[GmailAttachment],
    *,
    depth: int,
    visited: list[int],
) -> tuple[bool, bool]:
    visited[0] += 1
    if depth > 20 or visited[0] > 500:
        raise _ProviderTooLarge
    attachment_cap = False
    external_body = False
    mime = part.get("mimeType")
    filename = part.get("filename", "")
    if not isinstance(mime, str) or not mime or not isinstance(filename, str):
        raise ValueError("Gmail MIME part is malformed")
    body = _mapping(part.get("body", {}), "Gmail MIME body")
    attachment_id = body.get("attachmentId")
    if attachment_id is not None and (
        not isinstance(attachment_id, str) or not attachment_id
    ):
        raise ValueError("Gmail attachment ID is malformed")
    media_type, charset, disposition = _gmail_content_headers(part, mime)
    if (
        filename
        or disposition == "attachment"
        or (attachment_id is not None and media_type not in {"text/plain", "text/html"})
    ):
        size = body.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("Gmail attachment size is malformed")
        if size > 26_214_400:
            raise _ProviderTooLarge
        if len(attachments) < 50:
            attachments.append(
                GmailAttachment(
                    filename=_exact(filename, 255),
                    media_type=_exact(mime, 255),
                    size_bytes=size,
                )
            )
        else:
            attachment_cap = True
        return attachment_cap, False
    data = body.get("data")
    if attachment_id is not None:
        external_body = True
        data = None
    if attachment_id is not None:
        return attachment_cap, external_body
    if data is not None:
        if not isinstance(data, str):
            raise ValueError("Gmail MIME data is malformed")
        try:
            decoded_bytes = base64.b64decode(
                (data + "=" * (-len(data) % 4)).encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
            decoded = decoded_bytes.decode(charset)
        except (
            UnicodeEncodeError,
            UnicodeDecodeError,
            LookupError,
            binascii.Error,
            ValueError,
        ) as exc:
            raise ValueError("Gmail MIME data is malformed") from exc
        if media_type == "text/plain":
            plain.append(decoded)
        elif media_type == "text/html":
            html_parts.append(decoded)
    children = _array(part.get("parts", []), "Gmail MIME children")
    for child in children:
        child_attachment_cap, child_external_body = _walk_gmail_parts(
            _mapping(child, "Gmail MIME child"),
            plain,
            html_parts,
            attachments,
            depth=depth + 1,
            visited=visited,
        )
        attachment_cap = attachment_cap or child_attachment_cap
        external_body = external_body or child_external_body
    return attachment_cap, external_body


def _gmail_content_headers(
    part: Mapping[str, object], provider_media_type: str
) -> tuple[str, str, str | None]:
    if len(provider_media_type.encode()) > 255:
        raise _ProviderTooLarge
    headers = _array(part.get("headers", []), "Gmail MIME headers")
    content_types: list[str] = []
    dispositions: list[str] = []
    for value in headers:
        header = _mapping(value, "Gmail MIME header")
        name = header.get("name")
        header_value = header.get("value")
        if not isinstance(name, str) or not isinstance(header_value, str):
            raise ValueError("Gmail MIME header is malformed")
        if name.lower() == "content-type":
            content_types.append(_exact(header_value, 1_024))
        if name.lower() == "content-disposition":
            dispositions.append(_exact(header_value, 1_024))
    if len(content_types) > 1 or len(dispositions) > 1:
        raise _ProviderTooLarge
    raw = content_types[0] if content_types else provider_media_type
    parsed = message_from_string(f"Content-Type: {raw}\n\n")
    media_type = provider_media_type.lower()
    if content_types and parsed.get_content_type().lower() != media_type:
        raise ValueError("Gmail MIME content type is inconsistent")
    charset = parsed.get_content_charset() or "utf-8"
    disposition = None
    if dispositions:
        disposition_message = message_from_string(
            f"Content-Disposition: {dispositions[0]}\n\n"
        )
        disposition = disposition_message.get_content_disposition()
        if disposition is not None and disposition != "inline":
            disposition = "attachment"
    return media_type, charset, disposition


def _single_header(headers: Mapping[str, list[str]], name: str) -> str | None:
    values = headers.get(name, [])
    if len(values) > 1:
        raise _ProviderTooLarge
    return values[0] if values else None


def _mailboxes(value: str) -> tuple[Mailbox, ...]:
    if not value:
        return ()
    if "\r" in value or "\n" in value:
        raise ValueError("mailbox header is malformed")
    try:
        header: Any = Parser(policy=policy.default).parsestr(f"To: {value}\n\n")["To"]
        if header is None or header.defects:
            raise ValueError("mailbox header is malformed")
        addresses = header.addresses
    except Exception:
        raise ValueError("mailbox header is malformed") from None
    if len(addresses) > 50:
        raise _ProviderTooLarge
    mailboxes: list[Mailbox] = []
    for item in addresses:
        name = item.display_name
        address = item.addr_spec
        if not address:
            raise ValueError("mailbox address is absent")
        mailboxes.append(
            Mailbox(
                name=_exact(name, 320) if name else None,
                address=_exact(address, 320),
            )
        )
    return tuple(mailboxes)


def _calendar_event(
    calendar_id: str, value: object
) -> CalendarNormalEvent | CalendarCancelledEvent:
    event = _mapping(value, "Calendar event")
    event_id = _exact(_required_string(event, "id"), 1_024)
    calendar = _exact(calendar_id, 1_024)
    status = event.get("status")
    if status == "cancelled":
        updated = event.get("updated")
        if updated is not None and not isinstance(updated, str):
            raise ValueError("Calendar updated timestamp is malformed")
        return CalendarCancelledEvent(
            calendar_id=calendar,
            event_id=event_id,
            etag=_exact_optional(event, "etag", 1_024),
            updated_at=_instant(updated) if isinstance(updated, str) else None,
        )
    if status not in {"confirmed", "tentative"}:
        raise ValueError("Calendar status is malformed")
    unspecified_end = event.get("endTimeUnspecified", False)
    if type(unspecified_end) is not bool:
        raise ValueError("Calendar end-time state is malformed")
    reminders = _mapping(event.get("reminders", {}), "Calendar reminders")
    overrides = _array(reminders.get("overrides", []), "Calendar reminders")
    if len(overrides) > 10:
        raise _ProviderTooLarge
    attendees = _array(event.get("attendees", []), "Calendar attendees")
    attendees_omitted = event.get("attendeesOmitted", False)
    if type(attendees_omitted) is not bool:
        raise ValueError("Calendar attendeesOmitted is malformed")
    if attendees_omitted:
        raise _ProviderTooLarge
    if len(attendees) > 50:
        raise _ProviderTooLarge
    recurrence = _array(event.get("recurrence", []), "Calendar recurrence")
    if len(recurrence) > 20:
        raise _ProviderTooLarge
    use_default = reminders.get("useDefault", False)
    if type(use_default) is not bool:
        raise ValueError("Calendar default-reminder state is malformed")
    organizer = event.get("organizer")
    if organizer is not None and not isinstance(organizer, dict):
        raise ValueError("Calendar organizer is malformed")
    return CalendarNormalEvent(
        calendar_id=calendar,
        event_id=event_id,
        etag=_exact(_required_string(event, "etag"), 1_024),
        status=cast("Any", status),
        writable=CalendarObservedWritableEvent(
            summary=_exact(_optional_string(event, "summary", ""), 1_024),
            description=_exact_optional(event, "description", 16_384),
            location=_exact_optional(event, "location", 4_096),
            start=_calendar_time(event.get("start")),
            end=(
                UnspecifiedEventEnd()
                if unspecified_end
                else _calendar_time(event.get("end"))
            ),
            recurrence=tuple(_exact_string(item, 1_024) for item in recurrence),
            attendees=tuple(_calendar_participant(item) for item in attendees),
            use_default_reminders=use_default,
            reminders=tuple(_reminder(item) for item in overrides),
        ),
        organizer=(
            _calendar_participant(cast("dict[str, object]", organizer))
            if isinstance(organizer, dict)
            else None
        ),
        updated_at=_instant(_required_string(event, "updated")),
    )


def _calendar_list_event(
    calendar_id: str, value: object
) -> CalendarListNormalEvent | CalendarListCancelledEvent:
    event = _mapping(value, "Calendar event")
    event_id = _exact(_required_string(event, "id"), 1_024)
    calendar = _exact(calendar_id, 1_024)
    status = event.get("status")
    if status == "cancelled":
        return CalendarListCancelledEvent(
            calendar_id=calendar,
            event_id=event_id,
        )
    if status not in {"confirmed", "tentative"}:
        raise ValueError("Calendar status is malformed")
    unspecified_end = event.get("endTimeUnspecified", False)
    if type(unspecified_end) is not bool:
        raise ValueError("Calendar end-time state is malformed")
    return CalendarListNormalEvent(
        calendar_id=calendar,
        event_id=event_id,
        status=cast("Any", status),
        summary=_exact(_optional_string(event, "summary", ""), 1_024),
        start=_calendar_time(event.get("start")),
        end=(
            UnspecifiedEventEnd()
            if unspecified_end
            else _calendar_time(event.get("end"))
        ),
        location=_exact_optional(event, "location", 4_096),
    )


def _calendar_list_event_sort_key(
    event: CalendarListNormalEvent | CalendarListCancelledEvent, time_zone: str
) -> tuple[datetime, str, str]:
    if isinstance(event, CalendarListCancelledEvent):
        return datetime.max.replace(tzinfo=UTC), event.calendar_id, event.event_id
    start = event.start
    if isinstance(start, TimedEventTime):
        instant = start.date_time.astimezone(UTC)
    else:
        instant = datetime.combine(
            start.date,
            datetime.min.time(),
            tzinfo=ZoneInfo(time_zone),
        ).astimezone(UTC)
    return instant, event.calendar_id, event.event_id


def _calendar_time(value: object) -> TimedEventTime | AllDayEventTime:
    event_time = _mapping(value, "Calendar event time")
    has_date = "date" in event_time
    has_date_time = "dateTime" in event_time
    if has_date == has_date_time:
        raise ValueError("Calendar event time variant is malformed")
    if isinstance(event_time.get("date"), str):
        raw_date = cast("str", event_time["date"])
        if len(raw_date.encode()) > 10:
            raise _ProviderTooLarge
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) is None:
            raise ValueError("Calendar date is malformed")
        return AllDayEventTime(date=date.fromisoformat(raw_date))
    raw_instant = _required_string(event_time, "dateTime")
    instant_text = _timestamp_text(raw_instant)
    if (
        _RFC3339.fullmatch(instant_text) is None
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", instant_text)
        is None
    ):
        raise ValueError("Calendar timestamp is malformed")
    parsed = datetime.fromisoformat(instant_text.replace("Z", "+00:00"))
    configured_zone = event_time.get("timeZone")
    if configured_zone is not None and not isinstance(configured_zone, str):
        raise ValueError("Calendar time zone is malformed")
    if parsed.tzinfo is None and configured_zone is None:
        raise ValueError("offset-free Calendar time is missing its time zone")
    zone_value = configured_zone if isinstance(configured_zone, str) else "UTC"
    if len(zone_value.encode()) > 255:
        raise _ProviderTooLarge
    try:
        zone = ZoneInfo(zone_value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Calendar time zone is malformed") from exc
    try:
        if parsed.tzinfo is None:
            parsed = _localize_calendar_time(parsed, zone)
        instant = parsed.astimezone(UTC)
    except OverflowError:
        raise _ProviderTooLarge from None
    return TimedEventTime(date_time=instant, time_zone=zone_value)


def _localize_calendar_time(value: datetime, zone: ZoneInfo) -> datetime:
    first = value.replace(tzinfo=zone, fold=0)
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == value:
        return first
    second = value.replace(tzinfo=zone, fold=1)
    if second.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == value:
        return second
    raise ValueError("Calendar wall time does not exist in its time zone")


def _calendar_participant(value: object) -> CalendarParticipant:
    participant = _mapping(value, "Calendar participant")
    name = participant.get("displayName")
    address = participant.get("email")
    if name is not None and not isinstance(name, str):
        raise ValueError("Calendar participant name is malformed")
    if address is not None and not isinstance(address, str):
        raise ValueError("Calendar participant address is malformed")
    return CalendarParticipant(
        name=_exact(name, 320) if isinstance(name, str) else None,
        address=_exact(address, 320) if isinstance(address, str) else None,
    )


def _reminder(value: object) -> Reminder:
    reminder = _mapping(value, "Calendar reminder")
    method = reminder.get("method")
    minutes = reminder.get("minutes")
    if method not in {"email", "popup"} or type(minutes) is not int:
        raise ValueError("Calendar reminder is malformed")
    if minutes < 0:
        raise ValueError("Calendar reminder is malformed")
    if minutes > 40_320:
        raise _ProviderTooLarge
    return Reminder(
        method=cast("Any", method),
        minutes=minutes,
    )


def _place(value: object) -> Place:
    place = _mapping(value, "Place")
    display = _mapping(place.get("displayName"), "Place display name")
    location_value = place.get("location")
    location: Coordinates | None = None
    if location_value is not None:
        coordinates = _mapping(location_value, "Place location")
        latitude = coordinates.get("latitude", 0)
        longitude = coordinates.get("longitude", 0)
        if (
            isinstance(latitude, bool)
            or not isinstance(latitude, int | float)
            or not math.isfinite(latitude)
            or isinstance(longitude, bool)
            or not isinstance(longitude, int | float)
            or not math.isfinite(longitude)
        ):
            raise ValueError("Place coordinates are malformed")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise _ProviderTooLarge
        location = Coordinates(
            latitude=latitude,
            longitude=longitude,
        )
    types = _array(place.get("types", []), "Place types")
    if len(types) > 32:
        raise _ProviderTooLarge
    links = _mapping(place.get("googleMapsLinks", {}), "Place link")
    uri = links.get("placeUri", place.get("googleMapsUri"))
    if uri is not None and not isinstance(uri, str):
        raise ValueError("Place link is malformed")
    return Place(
        place_id=_exact(_required_string(place, "id"), 1_024),
        display_name=_exact(_required_string(display, "text"), 512),
        formatted_address=_exact_optional(place, "formattedAddress", 1_024),
        location=location,
        types=tuple(_exact_string(item, 128) for item in types),
        maps_uri=_exact(uri, 4_096) if uri is not None else None,
    )


def _waypoint(value: object) -> dict[str, object]:
    if getattr(value, "type", None) == "address":
        return {"address": cast("Any", value).address}
    if getattr(value, "type", None) == "place":
        return {"placeId": cast("Any", value).place_id}
    coordinates = cast("Any", value).coordinates
    return {
        "location": {
            "latLng": {
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
            }
        }
    }


_DURATION = re.compile(r"^(\d+)(?:\.(\d{1,9}))?s$")


def _duration(value: str) -> int:
    match = _DURATION.fullmatch(value)
    if match is None:
        raise ValueError("route duration is malformed")
    try:
        seconds = Decimal(value[:-1])
    except InvalidOperation as exc:
        raise ValueError("route duration is malformed") from exc
    rounded = math.ceil(seconds)
    if rounded > 2_147_483_647:
        raise _ProviderTooLarge
    return rounded


def _bounded_integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("provider integer is malformed")
    if value > 2_147_483_647:
        raise _ProviderTooLarge
    return value


__all__ = [
    "GOOGLE_AAD_NAMESPACE",
    "GOOGLE_STATE_SCHEMA",
    "GOOGLE_TOKEN_URL",
    "MAX_PROVIDER_BODY_BYTES",
    "GoogleCredentialDefect",
    "GoogleReadConnector",
    "GoogleTokenManager",
    "MapsReadConnector",
]

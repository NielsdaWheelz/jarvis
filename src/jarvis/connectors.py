"""Bounded host-owned Google connector clients for Slice 2 reads."""

from __future__ import annotations

import asyncio
import base64
import binascii
import codecs
import hashlib
import json
import math
import re
import secrets
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email import policy
from email.parser import Parser
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from llm_tools import BoundaryFailure, ExecutionContext, canonical_json_bytes
from llm_tools.content import html_visible_text
from llm_tools.schema import JsonObject
from pydantic import TypeAdapter, ValidationError

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis._thread_io import finish_entered, joined_thread
from jarvis.google_content import GoogleCursor, GoogleProjection
from jarvis.read_tools import (
    ATTACHMENT_CONNECT_SECONDS,
    ATTACHMENT_EXTERNAL_JSON_BYTES,
    ATTACHMENT_MAX_BYTES,
    ATTACHMENT_MESSAGE_JSON_BYTES,
    ATTACHMENT_OPERATION_SECONDS,
    CALENDAR_API_BASE_URL,
    CALENDAR_EVENT_PROJECTION,
    CALENDAR_METADATA_PROJECTION,
    GMAIL_API_BASE_URL,
    GOOGLE_DECODED_PROJECTION,
    GOOGLE_MESSAGE_PROJECTION,
    GOOGLE_OUTPUT_BYTES,
    GOOGLE_PAGE_SECONDS,
    GOOGLE_READABLE_PROJECTION,
    GOOGLE_TEXT_SECONDS,
    PLACE_DETAILS_FIELD_MASK,
    PLACES_API_BASE_URL,
    PLACES_SEARCH_FIELD_MASK,
    ROUTES_API_URL,
    ROUTES_FIELD_MASK,
    AllDayEventTime,
    CalendarEventSnapshot,
    CalendarGetEventInput,
    CalendarGetEventSnapshotSuccess,
    CalendarGetEventSuccess,
    CalendarGetEventTextSuccess,
    CalendarListCalendarsInput,
    CalendarListCalendarsSuccess,
    CalendarListCancelledEvent,
    CalendarListEventsInput,
    CalendarListEventsSuccess,
    CalendarListNormalEvent,
    CalendarPreview,
    CalendarReadCalendarInput,
    CalendarReadCalendarSuccess,
    ConnectorFailure,
    Coordinates,
    GmailAttachment,
    GmailListAttachmentsInput,
    GmailListAttachmentsSuccess,
    GmailListThreadMessagesInput,
    GmailListThreadMessagesSuccess,
    GmailMessageReference,
    GmailReadMessageInput,
    GmailReadMessageSuccess,
    GmailSearchInput,
    GmailSearchSuccess,
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
    attachment_media_type,
    display_descriptor,
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


class GoogleCredentialDefect(RuntimeError):
    """The host-owned Google credential state is invalid or unusable."""


class GoogleReadFailure(ConnectorFailure):
    def __init__(
        self,
        code: str,
        *,
        attempts: int,
        status: int,
        retry_after: str | None = None,
        grant_unavailable: bool = False,
    ) -> None:
        super().__init__(code, attempts=attempts)
        self.status = status
        self.retry_after = retry_after
        self.grant_unavailable = grant_unavailable


class _ProviderTooLarge(ValueError):
    pass


class OriginalTooLarge(_ProviderTooLarge):
    """The selected decoded original exceeds its admitted byte bound."""


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


def provider_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} is malformed")
    return cast("dict[str, object]", value)


def provider_array(value: object, name: str) -> list[object]:
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
        self._refresh_lock = asyncio.Lock()

    async def access_token(
        self,
        *,
        attempt_started: Callable[[], None] | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[str, int]:
        async with self._refresh_lock:
            return await self._current_access_token(
                attempt_started=attempt_started, before_request=before_request
            )

    async def _current_access_token(
        self,
        *,
        attempt_started: Callable[[], None] | None,
        before_request: Callable[[], Awaitable[None]] | None,
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
            expires_at = parse_google_instant(
                provider_string(state, "access_token_expires_at")
            )
            access_token = self._decrypt(
                provider_string(state, "access_token_enc"),
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
                provider_string(state, "refresh_token_enc"),
                field="refresh_token",
                key_version=key_version,
            )
        except ValueError as exc:
            raise GoogleCredentialDefect(
                "Google credential state is malformed"
            ) from exc
        try:
            if before_request is not None:
                await before_request()
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
                    raise GoogleReadFailure(
                        "rate_limited",
                        attempts=1,
                        status=429,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code >= 500:
                    raise GoogleReadFailure(
                        "provider_unavailable",
                        attempts=1,
                        status=response.status_code,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code != 200:
                    error_payload = await _json_body(response, attempts=1)
                    if error_payload.get("error") in {
                        "invalid_client",
                        "invalid_grant",
                    }:
                        raise GoogleCredentialDefect("Google OAuth grant is unusable")
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                payload = await _json_body(response, attempts=1)
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        try:
            token = provider_string(payload, "access_token")
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

    def invalidate_access_token(self, rejected_token: str) -> None:
        if self._access_token == rejected_token:
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


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    account: str
    history_id: str


def google_profile(payload: Mapping[str, object]) -> GoogleProfile:
    account = provider_text(provider_string(payload, "emailAddress"), 1_024)
    history_id = provider_text(provider_string(payload, "historyId"), 8_192)
    if (
        "@" not in account
        or "\0" in account
        or any(char.isspace() for char in account)
        or not history_id.isascii()
        or not history_id.isdecimal()
    ):
        raise ValueError("Google profile identity is malformed")
    return GoogleProfile(account, history_id)


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
        self._read_account: str | None = None
        self._projection: GoogleProjection | None = None

    async def aclose(self) -> None:
        if self._projection is not None:
            projection, self._projection = self._projection, None
            await joined_thread(projection.file.close)

    @asynccontextmanager
    async def _operation(
        self,
        seconds: float,
        maximum_attempts: int,
        context: ExecutionContext | None,
    ) -> AsyncIterator[_GoogleOperation]:
        operation = _GoogleOperation(self, seconds, maximum_attempts, context)
        try:
            async with asyncio.timeout(seconds):
                yield operation
        except asyncio.CancelledError:
            if (
                context is not None
                and context.deadline is not None
                and not context.cancellation.cancelled
                and asyncio.get_running_loop().time() >= context.deadline
            ):
                raise BoundaryFailure(
                    "DeadlineExceeded", actual_attempts=operation.attempts
                ) from None
            raise
        except ConnectorFailure as exc:
            raise ConnectorFailure(exc.code, attempts=operation.attempts) from None
        except TimeoutError:
            raise BoundaryFailure(
                "DeadlineExceeded", actual_attempts=operation.attempts
            ) from None
        except (OSError, MemoryError, RecursionError):
            raise ConnectorFailure(
                "resource_unavailable", attempts=operation.attempts
            ) from None
        except (TypeError, ValueError, UnicodeError):
            raise ConnectorFailure(
                "invalid_content", attempts=operation.attempts
            ) from None

    async def _account(self, operation: _GoogleOperation) -> str:
        payload = await operation.get(
            f"{GMAIL_API_BASE_URL}/users/me/profile",
            params={"fields": "emailAddress,historyId"},
        )
        account = google_profile(payload).account
        if self._read_account is None:
            self._read_account = account
        elif self._read_account != account:
            raise ConnectorFailure("account_changed", attempts=operation.attempts)
        return account

    async def _save_projection(
        self,
        key: tuple[str, ...],
        source: JsonObject,
        projection: str,
        value: object,
        *,
        text: bool = False,
    ) -> GoogleProjection:
        await self.aclose()
        entered = asyncio.create_task(
            asyncio.to_thread(
                GoogleProjection.create,
                key,
                source,
                projection,
                self._observed_at(),
                value,
                text=text,
            )
        )
        try:
            created = await asyncio.shield(entered)
        except asyncio.CancelledError as cancellation:
            try:
                created = await finish_entered(entered)
            except BaseException:
                raise cancellation from None
            await joined_thread(created.file.close)
            raise cancellation
        self._projection = created
        return created

    async def _chunk(
        self,
        projection: GoogleProjection,
        offset: int,
        maximum: int,
        expected_digest: str | None,
        operation: _GoogleOperation,
        *,
        nested: bool = False,
    ) -> JsonObject:
        if expected_digest is not None and projection.digest != expected_digest:
            raise ConnectorFailure("source_changed", attempts=operation.attempts)
        try:
            return await joined_thread(
                projection.chunk,
                offset,
                maximum,
                nested=nested,
                max_output_bytes=operation.output_bytes,
            )
        except ValueError:
            raise BoundaryFailure(
                "InvalidInput", actual_attempts=operation.attempts
            ) from None

    async def gmail_profile(
        self,
        *,
        attempt_started: Callable[[], None] | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[GoogleProfile, int]:
        payload, attempts = await self.get_json(
            f"{GMAIL_API_BASE_URL}/users/me/profile",
            params={"fields": "emailAddress,historyId"},
            attempt_started=attempt_started,
            before_request=before_request,
        )
        try:
            return google_profile(payload), attempts
        except ValueError:
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None

    async def gmail_account(
        self,
        *,
        attempt_started: Callable[[], None] | None = None,
    ) -> tuple[str, int]:
        profile, attempts = await self.gmail_profile(attempt_started=attempt_started)
        return profile.account, attempts

    async def gmail_search(
        self,
        value: GmailSearchInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[GmailSearchSuccess]:
        async with self._operation(GOOGLE_PAGE_SECONDS, 4, context) as operation:
            account = await self._account(operation)
            scope = {
                "query": value.query,
                "include_spam_trash": value.include_spam_trash,
            }
            cursor = _google_cursor(
                value.cursor, "gmail.search", account, scope, value.page_size
            )
            params: dict[str, str | int | list[str]] = {
                "includeSpamTrash": str(value.include_spam_trash).lower(),
                "maxResults": value.page_size,
            }
            if value.query is not None:
                params["q"] = value.query
            if cursor.provider_page_token is not None:
                params["pageToken"] = cursor.provider_page_token
            payload = await operation.get(
                f"{GMAIL_API_BASE_URL}/users/me/messages",
                params=params,
                invalid_request="invalid_cursor" if value.cursor else "invalid_query",
                max_response_bytes=None,
            )
            messages = [
                GmailMessageReference(
                    message_id=provider_text(
                        provider_string(provider_object(item, "Gmail message"), "id"),
                        1_024,
                    ),
                    thread_id=provider_text(
                        provider_string(
                            provider_object(item, "Gmail message"), "threadId"
                        ),
                        1_024,
                    ),
                ).model_dump(mode="json")
                for item in provider_array(
                    payload.get("messages", []), "Gmail messages"
                )
            ]
            estimate = payload.get("resultSizeEstimate")
            if estimate is not None and (
                type(estimate) is not int or not 0 <= estimate <= 2**53 - 1
            ):
                raise ValueError("Gmail estimate is malformed")
            result = await joined_thread(
                _google_page,
                cursor,
                messages,
                _next_page_token(payload),
                {
                    "account": account,
                    "query": value.query,
                    "include_spam_trash": value.include_spam_trash,
                    "result_size_estimate": estimate,
                    "observed_at": _rfc3339(self._observed_at()),
                },
                "messages",
                maximum_output_bytes=operation.output_bytes,
            )
            return ReadResponse(
                GmailSearchSuccess.model_validate(result), operation.attempts
            )

    async def gmail_read_message(
        self,
        value: GmailReadMessageInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[GmailReadMessageSuccess]:
        async with self._operation(GOOGLE_TEXT_SECONDS, 6, context) as operation:
            account = await self._account(operation)
            key = (
                account,
                "gmail",
                value.message_id,
                value.section,
                value.part_id or "",
                value.text_view or "",
            )
            projection = self._projection
            if (
                value.expected_digest is None
                or projection is None
                or projection.key != key
            ):
                payload = await operation.get(
                    f"{GMAIL_API_BASE_URL}/users/me/messages/"
                    f"{quote(value.message_id, safe='')}",
                    params={"format": "full"},
                    not_found="message_not_found",
                    max_response_bytes=None,
                )
                if provider_string(payload, "id") != value.message_id:
                    raise ValueError("Gmail returned a different message")
                thread_id = provider_text(provider_string(payload, "threadId"), 1_024)
                root = provider_object(payload.get("payload"), "Gmail payload")
                parts = await joined_thread(gmail_parts, root, attachment_policy=False)
                source: JsonObject = {
                    "account": account,
                    "message_id": value.message_id,
                    "thread_id": thread_id,
                    "section": value.section,
                    "part_id": value.part_id,
                    "text_view": value.text_view,
                }
                if value.section == "message":
                    content = await joined_thread(_gmail_metadata, payload, parts)
                    projection = await self._save_projection(
                        key, source, GOOGLE_MESSAGE_PROJECTION, content
                    )
                else:
                    part = next(
                        (part for part in parts if part.part_id == value.part_id), None
                    )
                    if part is None:
                        raise BoundaryFailure(
                            "InvalidInput", actual_attempts=operation.attempts
                        )
                    if part.reason in {"unsupported_type", "unsupported_charset"}:
                        raise ConnectorFailure(
                            "unsupported_content", attempts=operation.attempts
                        )
                    if part.reason is not None or part.content_kind == "unavailable":
                        raise ConnectorFailure(
                            "invalid_content", attempts=operation.attempts
                        )
                    if part.content_kind not in {"text", "empty"} or not _textual_media(
                        part.media_type
                    ):
                        raise ConnectorFailure(
                            "unsupported_content", attempts=operation.attempts
                        )
                    data = part.data
                    if part.external_id is not None:
                        body = await operation.get(
                            f"{GMAIL_API_BASE_URL}/users/me/messages/"
                            f"{quote(value.message_id, safe='')}/attachments/"
                            f"{quote(part.external_id, safe='')}",
                            not_found="message_not_found",
                            max_response_bytes=None,
                        )
                        data = body.get("data")
                        if not isinstance(data, str):
                            raise ValueError("Gmail external text data is malformed")
                    if data is None:
                        if part.content_kind != "empty":
                            raise ConnectorFailure(
                                "invalid_content", attempts=operation.attempts
                            )
                        data = ""
                    decoded = await joined_thread(_gmail_text, part, data)
                    if value.text_view == "readable" and part.media_type in {
                        "text/html",
                        "application/xhtml+xml",
                    }:
                        decoded, _title = await joined_thread(
                            html_visible_text, decoded
                        )
                    revision = (
                        GOOGLE_DECODED_PROJECTION
                        if value.text_view == "decoded"
                        else GOOGLE_READABLE_PROJECTION
                    )
                    projection = await self._save_projection(
                        key, source, revision, decoded, text=True
                    )
            chunk = await self._chunk(
                projection,
                value.offset,
                value.max_bytes,
                value.expected_digest,
                operation,
            )
            return ReadResponse(
                GmailReadMessageSuccess.model_validate(chunk), operation.attempts
            )

    async def gmail_list_thread_messages(
        self,
        value: GmailListThreadMessagesInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[GmailListThreadMessagesSuccess]:
        account, attempts = await self.gmail_account()
        try:
            payload, observed = await self.get_json(
                f"{GMAIL_API_BASE_URL}/users/me/threads/"
                f"{quote(value.thread_id, safe='')}",
                params={"format": "minimal", "fields": "id,messages(id)"},
                not_found="thread_not_found",
            )
        except ConnectorFailure as exc:
            raise ConnectorFailure(exc.code, attempts=attempts + exc.attempts) from None
        attempts += observed
        try:
            if provider_string(payload, "id") != value.thread_id:
                raise ValueError("Gmail returned a different thread")
            ids = sorted(
                provider_text(
                    provider_string(provider_object(m, "Gmail message"), "id"), 1_024
                )
                for m in provider_array(payload.get("messages", []), "Gmail messages")
            )
            if len(ids) != len(set(ids)):
                raise ValueError("Gmail returned duplicate messages")
            digest = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "account": account,
                        "thread_id": value.thread_id,
                        "message_ids": ids,
                    }
                )
            ).hexdigest()
            if value.expected_digest is not None and value.expected_digest != digest:
                raise ConnectorFailure("source_changed", attempts=attempts)
            selected = ids[value.offset : value.offset + value.limit]
            return ReadResponse(
                GmailListThreadMessagesSuccess(
                    thread_id=value.thread_id,
                    digest=digest,
                    total=len(ids),
                    offset=value.offset,
                    message_ids=tuple(selected),
                    next_offset=value.offset + len(selected)
                    if value.offset + len(selected) < len(ids)
                    else None,
                    observed_at=self._observed_at(),
                ),
                attempts,
            )
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None

    async def gmail_attachment_message(
        self, message_id: str, *, attempt_started: Callable[[], None] | None = None
    ) -> ReadResponse[GmailOriginalMessage]:
        account, attempts = await self.gmail_account(attempt_started=attempt_started)
        try:
            payload, observed = await self.get_json(
                f"{GMAIL_API_BASE_URL}/users/me/messages/{quote(message_id, safe='')}",
                params={"format": "full", "fields": "id,threadId,payload"},
                not_found="message_not_found",
                attempt_started=attempt_started,
                max_response_bytes=ATTACHMENT_MESSAGE_JSON_BYTES,
                deadline_seconds=ATTACHMENT_OPERATION_SECONDS,
            )
        except ConnectorFailure as exc:
            raise ConnectorFailure(exc.code, attempts=attempts + exc.attempts) from None
        attempts += observed
        try:
            if provider_string(payload, "id") != message_id:
                raise ValueError("Gmail returned a different message")
            thread_id = provider_text(provider_string(payload, "threadId"), 1_024)
            parts = await joined_thread(
                gmail_parts, provider_object(payload.get("payload"), "Gmail payload")
            )
            return ReadResponse(
                GmailOriginalMessage(account, message_id, thread_id, parts), attempts
            )
        except _ProviderTooLarge:
            raise ConnectorFailure(
                "provider_response_too_large", attempts=attempts
            ) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None

    async def gmail_list_attachments(
        self,
        value: GmailListAttachmentsInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[GmailListAttachmentsSuccess]:
        response = await self.gmail_attachment_message(value.message_id)
        original = response.value
        files = original.files
        digest = await joined_thread(lambda: original.digest)
        if value.expected_digest is not None and value.expected_digest != digest:
            raise ConnectorFailure("source_changed", attempts=response.attempts)
        selected = files[value.offset : value.offset + value.limit]
        descriptors = await joined_thread(
            lambda: tuple(part.descriptor for part in selected)
        )
        return ReadResponse(
            GmailListAttachmentsSuccess(
                message_id=value.message_id,
                thread_id=original.thread_id,
                digest=digest,
                total=len(files),
                offset=value.offset,
                attachments=descriptors,
                next_offset=value.offset + len(selected)
                if value.offset + len(selected) < len(files)
                else None,
                observed_at=self._observed_at(),
            ),
            response.attempts,
        )

    async def gmail_attachment_body(
        self,
        message_id: str,
        external_id: str,
        *,
        attempt_started: Callable[[], None] | None = None,
    ) -> ReadResponse[bytes]:
        payload, attempts = await self.get_json(
            f"{GMAIL_API_BASE_URL}/users/me/messages/{quote(message_id, safe='')}/"
            f"attachments/{quote(external_id, safe='')}",
            attempt_started=attempt_started,
            max_response_bytes=ATTACHMENT_EXTERNAL_JSON_BYTES,
            deadline_seconds=ATTACHMENT_OPERATION_SECONDS,
            not_found="message_not_found",
        )
        try:
            data = payload.get("data")
            if not isinstance(data, str):
                raise ValueError("Gmail attachment data is malformed")
            value = await joined_thread(decode_gmail_body, data)
        except _ProviderTooLarge:
            raise ConnectorFailure("too_large", attempts=attempts) from None
        except (TypeError, ValueError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
        return ReadResponse(value, attempts)

    async def calendar_list_calendars(
        self,
        value: CalendarListCalendarsInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[CalendarListCalendarsSuccess]:
        async with self._operation(GOOGLE_PAGE_SECONDS, 4, context) as operation:
            account = await self._account(operation)
            scope = {
                "show_deleted": False,
                "show_hidden": True,
                "min_access_role": "reader",
            }
            cursor = _google_cursor(
                value.cursor, "calendar.list_calendars", account, scope, value.page_size
            )
            params: dict[str, str | int | list[str]] = {
                "maxResults": value.page_size,
                "minAccessRole": "reader",
                "showDeleted": "false",
                "showHidden": "true",
            }
            if cursor.provider_page_token is not None:
                params["pageToken"] = cursor.provider_page_token
            payload = await operation.get(
                f"{CALENDAR_API_BASE_URL}/users/me/calendarList",
                params=params,
                invalid_request="invalid_cursor" if value.cursor else None,
                max_response_bytes=None,
            )
            calendars = await joined_thread(
                lambda: [
                    _calendar_preview(provider_object(raw, "Calendar list entry"))
                    for raw in provider_array(payload.get("items", []), "Calendar list")
                    if not _provider_boolean(
                        provider_object(raw, "Calendar list entry"),
                        "deleted",
                        default=False,
                    )
                ]
            )
            result = await joined_thread(
                _google_page,
                cursor,
                calendars,
                _next_page_token(payload),
                {
                    "account": account,
                    "observed_at": _rfc3339(self._observed_at()),
                },
                "calendars",
                maximum_output_bytes=operation.output_bytes,
            )
            return ReadResponse(
                CalendarListCalendarsSuccess.model_validate(result), operation.attempts
            )

    async def calendar_read_calendar(
        self,
        value: CalendarReadCalendarInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[CalendarReadCalendarSuccess]:
        async with self._operation(GOOGLE_TEXT_SECONDS, 4, context) as operation:
            account = await self._account(operation)
            key = (account, "calendar", value.calendar_id)
            projection = self._projection
            if (
                value.expected_digest is None
                or projection is None
                or projection.key != key
            ):
                payload = await operation.get(
                    f"{CALENDAR_API_BASE_URL}/users/me/calendarList/"
                    f"{quote(value.calendar_id, safe='')}",
                    not_found="calendar_not_found",
                    max_response_bytes=None,
                )
                if provider_string(payload, "id") != value.calendar_id:
                    raise ValueError("Calendar returned a different calendar")
                projected = await joined_thread(_calendar_metadata, payload)
                projection = await self._save_projection(
                    key,
                    {"account": account, "calendar_id": value.calendar_id},
                    CALENDAR_METADATA_PROJECTION,
                    projected,
                )
            chunk = await self._chunk(
                projection,
                value.offset,
                value.max_bytes,
                value.expected_digest,
                operation,
            )
            return ReadResponse(
                CalendarReadCalendarSuccess.model_validate(chunk), operation.attempts
            )

    async def calendar_list_events(
        self,
        value: CalendarListEventsInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[CalendarListEventsSuccess]:
        async with self._operation(GOOGLE_PAGE_SECONDS, 4, context) as operation:
            account = await self._account(operation)
            scope = {
                "calendar_id": value.calendar_id,
                "time_min": _rfc3339(value.time_min),
                "time_max": _rfc3339(value.time_max),
                "time_zone": value.time_zone,
                "single_events": True,
                "show_deleted": True,
                "order_by": "startTime",
            }
            cursor = _google_cursor(
                value.cursor, "calendar.list_events", account, scope, value.page_size
            )
            params: dict[str, str | int | list[str]] = {
                "maxResults": value.page_size,
                "timeMin": _rfc3339(value.time_min),
                "timeMax": _rfc3339(value.time_max),
                "timeZone": value.time_zone,
                "singleEvents": "true",
                "showDeleted": "true",
                "orderBy": "startTime",
            }
            if cursor.provider_page_token is not None:
                params["pageToken"] = cursor.provider_page_token
            payload = await operation.get(
                f"{CALENDAR_API_BASE_URL}/calendars/"
                f"{quote(value.calendar_id, safe='')}/events",
                params=params,
                not_found="calendar_not_found",
                invalid_request="invalid_cursor" if value.cursor else "invalid_range",
                max_response_bytes=None,
            )
            events = await joined_thread(
                lambda: [
                    _calendar_list_event(value.calendar_id, item).model_dump(
                        mode="json"
                    )
                    for item in provider_array(
                        payload.get("items", []), "Calendar events"
                    )
                ]
            )
            result = await joined_thread(
                _google_page,
                cursor,
                events,
                _next_page_token(payload),
                {
                    "account": account,
                    "calendar_id": value.calendar_id,
                    "time_min": _rfc3339(value.time_min),
                    "time_max": _rfc3339(value.time_max),
                    "time_zone": value.time_zone,
                    "observed_at": _rfc3339(self._observed_at()),
                },
                "events",
                maximum_output_bytes=operation.output_bytes,
            )
            return ReadResponse(
                CalendarListEventsSuccess.model_validate(result), operation.attempts
            )

    async def calendar_get_event(
        self,
        value: CalendarGetEventInput,
        *,
        context: ExecutionContext | None = None,
    ) -> ReadResponse[CalendarGetEventSuccess]:
        seconds = (
            GOOGLE_PAGE_SECONDS
            if value.projection == "snapshot"
            else GOOGLE_TEXT_SECONDS
        )
        async with self._operation(seconds, 4, context) as operation:
            account = await self._account(operation)
            key = (account, "event", value.calendar_id, value.event_id)
            projection = self._projection
            if (
                value.projection == "snapshot"
                or value.expected_digest is None
                or projection is None
                or projection.key != key
            ):
                payload = await operation.get(
                    f"{CALENDAR_API_BASE_URL}/calendars/"
                    f"{quote(value.calendar_id, safe='')}/events/"
                    f"{quote(value.event_id, safe='')}",
                    not_found="event_not_found",
                    max_response_bytes=None,
                )
                if provider_string(payload, "id") != value.event_id:
                    raise ValueError("Calendar returned a different event")
                if value.projection == "snapshot":
                    omitted = payload.get("attendeesOmitted", False)
                    if type(omitted) is not bool:
                        raise ValueError("Calendar attendee completeness is malformed")
                    if omitted:
                        raise ConnectorFailure(
                            "snapshot_incomplete", attempts=operation.attempts
                        )
                full = await joined_thread(
                    _calendar_event_projection, value.calendar_id, payload
                )
                if value.projection == "snapshot":
                    try:
                        event = TypeAdapter[CalendarEventSnapshot](
                            CalendarEventSnapshot
                        ).validate_python(full["event"])
                        result = CalendarGetEventSnapshotSuccess(
                            event=event, observed_at=self._observed_at()
                        )
                        if (
                            len(
                                canonical_json_bytes(
                                    {
                                        "type": "Success",
                                        "value": result.model_dump(mode="json"),
                                    }
                                )
                            )
                            > operation.output_bytes
                        ):
                            raise _ProviderTooLarge
                    except (ValidationError, _ProviderTooLarge):
                        raise ConnectorFailure(
                            "snapshot_too_large", attempts=operation.attempts
                        ) from None
                    return ReadResponse(result, operation.attempts)
                projection = await self._save_projection(
                    key,
                    {
                        "account": account,
                        "calendar_id": value.calendar_id,
                        "event_id": value.event_id,
                    },
                    CALENDAR_EVENT_PROJECTION,
                    full,
                )
            assert value.offset is not None and value.max_bytes is not None
            chunk = await self._chunk(
                projection,
                value.offset,
                value.max_bytes,
                value.expected_digest,
                operation,
                nested=True,
            )
            return ReadResponse(
                CalendarGetEventTextSuccess.model_validate(chunk), operation.attempts
            )

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int | list[str]] | None = None,
        not_found: str | None = None,
        invalid_request: str | None = None,
        attempt_started: Callable[[], None] | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
        max_response_bytes: int | None = MAX_PROVIDER_BODY_BYTES,
        deadline_seconds: float = 8.0,
    ) -> tuple[dict[str, object], int]:
        token, refresh_attempts = await self._tokens.access_token(
            attempt_started=attempt_started, before_request=before_request
        )
        try:
            if before_request is not None:
                await before_request()
            if attempt_started is not None:
                attempt_started()
            async with (
                asyncio.timeout(deadline_seconds),
                self._client.stream(
                    "GET",
                    url,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    follow_redirects=False,
                    timeout=httpx.Timeout(
                        deadline_seconds,
                        connect=ATTACHMENT_CONNECT_SECONDS
                        if deadline_seconds > 8.0
                        else 3.0,
                        read=min(deadline_seconds, 60.0),
                    ),
                ) as response,
            ):
                attempts = refresh_attempts + 1
                if response.status_code == 404 and not_found is not None:
                    raise GoogleReadFailure(not_found, attempts=attempts, status=404)
                if response.status_code == 429:
                    raise GoogleReadFailure(
                        "rate_limited",
                        attempts=attempts,
                        status=429,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code == 403:
                    code, grant_unavailable = await _google_forbidden(
                        response, attempts=attempts
                    )
                    raise GoogleReadFailure(
                        code,
                        attempts=attempts,
                        status=403,
                        grant_unavailable=grant_unavailable,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code == 401:
                    self._tokens.invalidate_access_token(token)
                    raise GoogleReadFailure(
                        "provider_unavailable",
                        attempts=attempts,
                        status=response.status_code,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code == 400:
                    raise GoogleReadFailure(
                        invalid_request or "provider_unavailable",
                        attempts=attempts,
                        status=400,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise GoogleReadFailure(
                        "provider_unavailable",
                        attempts=attempts,
                        status=response.status_code,
                        retry_after=response.headers.get("Retry-After"),
                    )
                try:
                    payload = await _json_body(
                        response, attempts=attempts, maximum=max_response_bytes
                    )
                except ConnectorFailure as exc:
                    if exc.code == "provider_response_too_large":
                        raise
                    raise GoogleReadFailure(
                        "provider_unavailable", attempts=attempts, status=200
                    ) from None
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure(
                "provider_unavailable", attempts=refresh_attempts + 1
            ) from None
        return payload, attempts

    def _observed_at(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("connector clock must be aware")
        return value.astimezone(UTC)


class _GoogleOperation:
    """One request's shared deadline, cancellation and actual HTTP-entry count."""

    def __init__(
        self,
        connector: GoogleReadConnector,
        seconds: float,
        maximum_attempts: int,
        context: ExecutionContext | None,
    ) -> None:
        self.connector = connector
        self.deadline = asyncio.get_running_loop().time() + (
            seconds
            if context is None
            else min(seconds, context.grant.limits.deadline_seconds)
        )
        if context is not None and context.deadline is not None:
            self.deadline = min(self.deadline, context.deadline)
        self.maximum_attempts = (
            maximum_attempts
            if context is None
            else min(maximum_attempts, context.grant.limits.max_attempts)
        )
        self.output_bytes = (
            GOOGLE_OUTPUT_BYTES
            if context is None
            else min(GOOGLE_OUTPUT_BYTES, context.grant.limits.max_output_bytes)
        )
        self.context = context
        self.attempts = 0

    async def check(self) -> None:
        if self.context is not None and self.context.cancellation.cancelled:
            raise asyncio.CancelledError
        if asyncio.get_running_loop().time() >= self.deadline:
            raise TimeoutError

    def entered(self) -> None:
        if self.attempts >= self.maximum_attempts:
            raise BoundaryFailure("BudgetExceeded", actual_attempts=self.attempts)
        self.attempts += 1

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int | list[str]] | None = None,
        not_found: str | None = None,
        invalid_request: str | None = None,
        max_response_bytes: int | None = MAX_PROVIDER_BODY_BYTES,
    ) -> dict[str, object]:
        for authentication_attempt in range(2):
            await self.check()
            try:
                payload, _attempts = await self.connector.get_json(
                    url,
                    params=params,
                    not_found=not_found,
                    invalid_request=invalid_request,
                    attempt_started=self.entered,
                    before_request=self.check,
                    max_response_bytes=max_response_bytes,
                    deadline_seconds=self.deadline - asyncio.get_running_loop().time(),
                )
                return payload
            except GoogleReadFailure as exc:
                if exc.status != 401 or authentication_attempt:
                    if exc.status == 410 and invalid_request == "invalid_cursor":
                        raise ConnectorFailure(
                            "invalid_cursor", attempts=self.attempts
                        ) from None
                    raise
            except ConnectorFailure:
                await self.check()
                raise
        raise AssertionError("authentication loop must terminate")


def _google_cursor(
    value: str | None,
    tool: str,
    account: str,
    scope: Mapping[str, object],
    page_size: int,
) -> GoogleCursor:
    digest = hashlib.sha256(canonical_json_bytes(scope)).hexdigest()
    if value is None:
        return GoogleCursor(
            version=1,
            tool=tool,
            account=account,
            scope_digest=digest,
            page_size=page_size,
            provider_page_token=None,
            item_offset=0,
            page_digest=None,
        )
    try:
        cursor = GoogleCursor.decode(value)
    except ValueError:
        raise ConnectorFailure("invalid_cursor", attempts=0) from None
    if cursor.account != account:
        raise ConnectorFailure("account_changed", attempts=0)
    if (
        cursor.tool != tool
        or cursor.scope_digest != digest
        or cursor.page_size != page_size
    ):
        raise ConnectorFailure("invalid_cursor", attempts=0)
    return cursor


def _google_page(
    cursor: GoogleCursor,
    items: list[dict[str, Any]],
    next_token: str | None,
    fields: dict[str, Any],
    item_field: str,
    maximum_output_bytes: int = GOOGLE_OUTPUT_BYTES,
) -> dict[str, Any]:
    if next_token is not None and next_token == cursor.provider_page_token:
        raise ValueError("provider page token did not advance")
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "items": items,
                "next_provider_page_token": next_token,
                "metadata": {
                    key: value for key, value in fields.items() if key != "observed_at"
                },
            }
        )
    ).hexdigest()
    if cursor.page_digest is not None and cursor.page_digest != digest:
        raise ConnectorFailure("source_changed", attempts=0)
    if cursor.item_offset > len(items):
        raise ConnectorFailure("invalid_cursor", attempts=0)
    if cursor.item_offset and cursor.item_offset == len(items):
        raise ConnectorFailure("invalid_cursor", attempts=0)
    best: tuple[int, str | None] | None = None
    item_bytes = 0
    for end in range(cursor.item_offset, len(items) + 1):
        count = end - cursor.item_offset
        if count:
            item_bytes += len(canonical_json_bytes(items[end - 1])) + (
                1 if count > 1 else 0
            )
        elif items:
            continue
        try:
            if end < len(items):
                continuation = cursor.model_copy(
                    update={"item_offset": end, "page_digest": digest}
                ).encode()
            elif next_token is not None:
                continuation = cursor.model_copy(
                    update={
                        "provider_page_token": next_token,
                        "item_offset": 0,
                        "page_digest": None,
                    }
                ).encode()
            else:
                continuation = None
        except ValueError:
            continue
        candidate: dict[str, Any] = {
            **fields,
            item_field: [],
            "next_cursor": continuation,
        }
        if (
            len(canonical_json_bytes({"type": "Success", "value": candidate}))
            + item_bytes
            <= maximum_output_bytes
        ):
            best = end, continuation
    if best is None:
        raise ConnectorFailure("resource_unavailable", attempts=0)
    end, continuation = best
    return {
        **fields,
        item_field: items[cursor.item_offset : end],
        "next_cursor": continuation,
    }


def _calendar_metadata(item: Mapping[str, object]) -> dict[str, object]:
    display_name = item.get("summaryOverride", item.get("summary"))
    time_zone = item.get("timeZone")
    if display_name is not None and not isinstance(display_name, str):
        raise ValueError("Calendar display name is malformed")
    if time_zone is not None:
        if not isinstance(time_zone, str):
            raise ValueError("Calendar time zone is malformed")
        provider_text(time_zone, 255)
        ZoneInfo(time_zone)
    access = provider_string(item, "accessRole")
    if access not in {"reader", "writerWithoutPrivateAccess", "writer", "owner"}:
        raise ValueError("Calendar access role is malformed")
    return {
        "calendar_id": provider_text(provider_string(item, "id"), 1_024),
        "display_name": display_name,
        "time_zone": time_zone,
        "access_role": access,
        "primary": _provider_boolean(item, "primary", default=False),
        "hidden": _provider_boolean(item, "hidden", default=False),
        "selected": _provider_boolean(item, "selected", default=False),
    }


def _calendar_preview(item: Mapping[str, object]) -> dict[str, Any]:
    full = _calendar_metadata(item)
    label = full.pop("display_name")
    preview, shortened = (
        _truncate(label, 1_024) if isinstance(label, str) else (None, False)
    )
    return CalendarPreview.model_validate(
        {
            **full,
            "display_name_preview": preview,
            "display_name_truncated": shortened,
        }
    ).model_dump(mode="json")


def _participant_projection(value: object) -> dict[str, object]:
    participant = provider_object(value, "Calendar participant")
    name, address = participant.get("displayName"), participant.get("email")
    if name is not None and not isinstance(name, str):
        raise ValueError("Calendar participant name is malformed")
    if address is not None and (not isinstance(address, str) or not address):
        raise ValueError("Calendar participant address is malformed")
    return {"name": name, "address": address}


def _calendar_event_projection(
    calendar_id: str, event: Mapping[str, object]
) -> dict[str, object]:
    omitted = event.get("attendeesOmitted", False)
    if type(omitted) is not bool:
        raise ValueError("Calendar attendee completeness is malformed")
    identity: dict[str, object] = {
        "calendar_id": provider_text(calendar_id, 1_024),
        "event_id": provider_text(provider_string(event, "id"), 1_024),
    }
    status = event.get("status")
    if status == "cancelled":
        updated = event.get("updated")
        if updated is not None and not isinstance(updated, str):
            raise ValueError("Calendar updated timestamp is malformed")
        return {
            "event": {
                **identity,
                "type": "cancelled",
                "etag": provider_string(event, "etag")
                if event.get("etag") is not None
                else None,
                "updated_at": parse_google_instant(updated).isoformat()
                if isinstance(updated, str)
                else None,
            },
            "attendees_omitted": omitted,
        }
    if status not in {"confirmed", "tentative"}:
        raise ValueError("Calendar status is malformed")
    unspecified = _provider_boolean(event, "endTimeUnspecified", default=False)
    reminders = provider_object(event.get("reminders", {}), "Calendar reminders")
    recurrence = provider_array(event.get("recurrence", []), "Calendar recurrence")
    if any(not isinstance(item, str) for item in recurrence):
        raise ValueError("Calendar recurrence is malformed")
    description, location = event.get("description"), event.get("location")
    if any(
        item is not None and not isinstance(item, str)
        for item in (description, location)
    ):
        raise ValueError("Calendar description/location is malformed")
    organizer = event.get("organizer")
    return {
        "event": {
            **identity,
            "type": "event",
            "etag": provider_string(event, "etag"),
            "status": status,
            "writable": {
                "summary": _optional_string(event, "summary", ""),
                "description": description,
                "location": location,
                "start": parse_calendar_time(event.get("start")).model_dump(
                    mode="json"
                ),
                "end": (
                    {"type": "unspecified"}
                    if unspecified
                    else parse_calendar_time(event.get("end")).model_dump(mode="json")
                ),
                "recurrence": recurrence,
                "attendees": [
                    _participant_projection(item)
                    for item in provider_array(
                        event.get("attendees", []), "Calendar attendees"
                    )
                ],
                "use_default_reminders": _provider_boolean(
                    reminders, "useDefault", default=False
                ),
                "reminders": [
                    _reminder(item).model_dump(mode="json")
                    for item in provider_array(
                        reminders.get("overrides", []), "Calendar reminders"
                    )
                ],
            },
            "organizer": None
            if organizer is None
            else _participant_projection(organizer),
            "updated_at": parse_google_instant(
                provider_string(event, "updated")
            ).isoformat(),
        },
        "attendees_omitted": omitted,
    }


def _raw_gmail_headers(part: Mapping[str, object]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in provider_array(part.get("headers", []), "Gmail headers"):
        header = provider_object(raw, "Gmail header")
        name, value = header.get("name"), header.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("Gmail header is malformed")
        result.append({"name": name, "value": value})
    return result


def _unfold_header(value: str) -> str:
    unfolded = re.sub(r"\r\n(?=[ \t])", "", value)
    if "\r" in unfolded or "\n" in unfolded:
        raise ValueError("header contains invalid line breaks")
    return unfolded


def _reply_to(headers: list[dict[str, str]]) -> dict[str, object]:
    values = [
        header["value"] for header in headers if header["name"].lower() == "reply-to"
    ]
    if not values:
        return {"status": "absent", "addresses": [], "reason": None}
    if len(values) > 1:
        return {"status": "invalid", "addresses": [], "reason": "duplicate"}
    if not values[0].strip():
        return {"status": "invalid", "addresses": [], "reason": "empty"}
    try:
        unfolded = _unfold_header(values[0])
        parsed: Any = Parser(policy=policy.default).parsestr(
            f"Reply-To: {unfolded}\n\n"
        )["Reply-To"]
        if parsed is None or parsed.defects or not parsed.addresses:
            raise ValueError("routing header is malformed")
        addresses: list[dict[str, str | None]] = []
        for address in parsed.addresses:
            if not address.username or not address.domain:
                raise ValueError("routing address is incomplete")
            addresses.append(
                {"name": address.display_name or None, "address": address.addr_spec}
            )
        return {"status": "valid", "addresses": addresses, "reason": None}
    except (ValueError, TypeError, AttributeError, IndexError, RecursionError):
        return {"status": "invalid", "addresses": [], "reason": "parse_error"}


def _gmail_metadata(
    message: Mapping[str, object], parts: tuple[GmailPart, ...]
) -> dict[str, object]:
    root = provider_object(message.get("payload"), "Gmail payload")
    headers = _raw_gmail_headers(root)
    return {
        "message_id": provider_text(provider_string(message, "id"), 1_024),
        "thread_id": provider_text(provider_string(message, "threadId"), 1_024),
        "internal_at": (
            (
                datetime(1970, 1, 1, tzinfo=UTC)
                + timedelta(milliseconds=_gmail_internal_millis(message))
            ).isoformat()
        ),
        "headers": headers,
        "reply_to_addresses": _reply_to(headers),
        "parts": [
            {
                "part_id": part.part_id,
                "filename": part.filename,
                "media_type": part.media_type,
                "charset": part.charset,
                "advertised_size": part.advertised_size,
                "is_file": part.is_file,
                "content_kind": part.content_kind,
                "reason": part.reason,
            }
            for part in parts
        ],
    }


def _textual_media(media: str | None) -> bool:
    return media is not None and (
        media.startswith("text/")
        or media in {"application/json", "application/xml", "application/xhtml+xml"}
    )


def _gmail_text(part: GmailPart, data: str) -> str:
    decoded = decode_gmail_body(data, maximum=None)
    encoding = part.charset
    if part.media_type in {"application/xml", "application/xhtml+xml", "text/xml"}:
        # RFC 7303: a BOM takes precedence over MIME charset and XML declaration.
        if decoded.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            encoding = "utf-32"
        elif decoded.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = "utf-16"
        elif decoded.startswith(codecs.BOM_UTF8):
            encoding = "utf-8-sig"
        elif encoding is None:
            if decoded.startswith(b"\x00\x00\x00<"):
                encoding = "utf-32-be"
            elif decoded.startswith(b"<\x00\x00\x00"):
                encoding = "utf-32-le"
            elif decoded.startswith(b"\x00<\x00?"):
                encoding = "utf-16-be"
            elif decoded.startswith(b"<\x00?\x00"):
                encoding = "utf-16-le"
            else:
                declaration = re.match(
                    rb"<\?xml\s+[^>]*encoding\s*=\s*['\"]([^'\"]+)['\"]", decoded
                )
                encoding = (
                    declaration.group(1).decode("ascii") if declaration else "utf-8"
                )
    elif part.media_type == "application/json":
        encoding = "utf-8"
    elif encoding is None:
        encoding = "us-ascii"
    try:
        codec = codecs.lookup(encoding)
    except LookupError:
        raise ConnectorFailure("unsupported_content", attempts=0) from None
    try:
        return decoded.decode(codec.name, errors="strict")
    except LookupError:
        raise ConnectorFailure("unsupported_content", attempts=0) from None
    except (UnicodeError, ValueError, TypeError):
        raise ConnectorFailure("invalid_content", attempts=0) from None


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
        self, value: MapsSearchPlacesInput, *, context: ExecutionContext | None = None
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
            raw_places = provider_array(payload.get("places", []), "Places results")
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
        self, value: MapsGetPlaceInput, *, context: ExecutionContext | None = None
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
        self, value: MapsDirectionsInput, *, context: ExecutionContext | None = None
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
            raw_routes = provider_array(payload.get("routes", []), "Routes results")
            if not raw_routes:
                raise ConnectorFailure("no_route", attempts=1)
            if len(raw_routes) != 1:
                raise _ProviderTooLarge
            raw = provider_object(raw_routes[0], "route")
            warnings = provider_array(raw.get("warnings", []), "route warnings")
            if len(warnings) > 10:
                raise _ProviderTooLarge
            route = Route(
                distance_meters=_bounded_integer(raw.get("distanceMeters", 0)),
                duration_seconds=_duration(provider_string(raw, "duration")),
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
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return payload

    def _observed_at(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("connector clock must be aware")
        return value.astimezone(UTC)


async def _json_body(
    response: httpx.Response,
    *,
    attempts: int,
    maximum: int | None = MAX_PROVIDER_BODY_BYTES,
) -> dict[str, object]:
    try:
        with tempfile.TemporaryFile() as body:
            count = 0
            async for chunk in response.aiter_bytes(chunk_size=1_024 * 1_024):
                count += len(chunk)
                if maximum is not None and count > maximum:
                    raise ConnectorFailure(
                        "provider_response_too_large", attempts=attempts
                    )
                await joined_thread(body.write, chunk)
            body.seek(0)
            value: object = await joined_thread(
                json.load,
                body,
                parse_constant=_reject_constant,
                object_pairs_hook=_strict_object,
            )
    except (
        OSError,
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


async def _google_forbidden(
    response: httpx.Response, *, attempts: int
) -> tuple[str, bool]:
    try:
        payload = await _json_body(response, attempts=attempts)
        error = provider_object(payload.get("error"), "Google error")
        errors = provider_array(error.get("errors", []), "Google errors")
        reasons: set[str] = set()
        for value in errors:
            reason = provider_object(value, "Google error item").get("reason")
            if not isinstance(reason, str):
                return "provider_unavailable", False
            reasons.add(reason)
    except ConnectorFailure as exc:
        if exc.code == "provider_response_too_large":
            raise
        return "provider_unavailable", False
    except ValueError:
        return "provider_unavailable", False
    if reasons & {
        "dailyLimitExceeded",
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
    }:
        return "rate_limited", False
    return "provider_unavailable", bool(
        reasons & {"insufficientPermissions", "accessNotConfigured"}
    )


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


def provider_string(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"provider field {key} is missing")
    return result


def _optional_string(value: Mapping[str, object], key: str, default: str) -> str:
    result = value.get(key, default)
    if not isinstance(result, str):
        raise ValueError(f"provider field {key} is malformed")
    return result


def provider_text(value: str, maximum: int) -> str:
    if len(value.encode()) > maximum:
        raise _ProviderTooLarge
    return value


def _exact_string(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("provider string is malformed")
    return provider_text(value, maximum)


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


def parse_google_instant(value: str) -> datetime:
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
    message = provider_object(value, "Gmail message")
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


@dataclass(frozen=True, slots=True)
class GmailPart:
    part_id: str
    filename: str | None
    media_type: str | None
    charset: str | None
    advertised_size: int | None
    external_id: str | None
    data: str | None
    is_file: bool
    content_kind: str = "binary"
    reason: str | None = None

    @property
    def descriptor(self) -> GmailAttachment:
        return GmailAttachment.model_validate(
            {
                "part_id": self.part_id,
                **display_descriptor(
                    self.filename or None, self.media_type, self.advertised_size
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class GmailOriginalMessage:
    account: str
    message_id: str
    thread_id: str
    parts: tuple[GmailPart, ...]

    @property
    def files(self) -> tuple[GmailPart, ...]:
        return tuple(
            sorted(
                (part for part in self.parts if part.is_file),
                key=lambda part: part.part_id,
            )
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "account": self.account,
                    "message_id": self.message_id,
                    "thread_id": self.thread_id,
                    "attachments": [
                        {
                            "part_id": part.part_id,
                            "filename": part.filename,
                            "media_type": part.media_type,
                            "advertised_size": part.advertised_size,
                        }
                        for part in self.files
                    ],
                }
            )
        ).hexdigest()


def decode_gmail_body(
    data: str, *, maximum: int | None = ATTACHMENT_MAX_BYTES
) -> bytes:
    if maximum is not None and len(data) > (maximum + 2) // 3 * 4:
        raise OriginalTooLarge
    try:
        decoded = base64.b64decode(
            (data + "=" * (-len(data) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ValueError("Gmail MIME data is malformed") from exc
    if maximum is not None and len(decoded) > maximum:
        raise OriginalTooLarge
    return decoded


def gmail_parts(
    payload: Mapping[str, object], *, attachment_policy: bool = True
) -> tuple[GmailPart, ...]:
    result: list[GmailPart] = []
    seen: set[str] = set()
    pending = [(payload, 0)]
    while pending:
        part, depth = pending.pop()
        if attachment_policy and (depth > 20 or len(seen) >= 500):
            raise _ProviderTooLarge
        identifier = part.get("partId")
        if not isinstance(identifier, str) or (not identifier and depth != 0):
            raise ValueError("Gmail part ID is malformed")
        if identifier:
            provider_text(identifier, 1_024)
        if identifier in seen:
            raise ValueError("Gmail part IDs are duplicated")
        seen.add(identifier)
        children = provider_array(part.get("parts", []), "Gmail MIME children")
        if children:
            pending.extend(
                (provider_object(child, "Gmail MIME child"), depth + 1)
                for child in reversed(children)
            )
            continue
        result.append(_gmail_leaf(part, identifier, attachment_policy))
    return tuple(result)


def _gmail_leaf(
    part: Mapping[str, object], identifier: str, attachment_policy: bool
) -> GmailPart:
    raw_filename = part.get("filename", "" if attachment_policy else None)
    filename = raw_filename if isinstance(raw_filename, str) else None
    invalid = raw_filename is not None and filename is None
    media, charset, disposition = None, None, None
    try:
        mime = provider_string(part, "mimeType")
        media, charset, disposition = _gmail_content_headers(
            part, mime, attachment_policy=attachment_policy
        )
    except (ValueError, _ProviderTooLarge):
        if attachment_policy:
            raise
        invalid = True
    raw_body = part.get("body", {})
    if not isinstance(raw_body, dict):
        invalid = True
        raw_body = {}
    body = cast("dict[str,object]", raw_body)
    raw_size = body.get("size")
    size = (
        raw_size
        if type(raw_size) is int
        and 0 <= raw_size <= (2**63 - 1 if attachment_policy else 2**53 - 1)
        else None
    )
    invalid = invalid or (raw_size is not None and size is None)
    raw_external = body.get("attachmentId")
    external = (
        raw_external
        if isinstance(raw_external, str) and 0 < len(raw_external.encode()) <= 1_024
        else None
    )
    invalid = invalid or (raw_external is not None and external is None)
    raw_data = body.get("data")
    data = raw_data if isinstance(raw_data, str) else None
    invalid = invalid or (raw_data is not None and data is None)
    if attachment_policy and invalid:
        raise ValueError("Gmail leaf metadata is malformed")
    is_file = (
        bool(filename)
        or disposition == "attachment"
        or (
            media not in {"text/plain", "text/html"}
            and (data is not None or external is not None)
        )
    )
    kind, reason = "binary", None
    if invalid:
        kind, reason = "unavailable", "invalid_metadata"
    elif data is None and external is None:
        kind, reason = ("empty", None) if size == 0 else ("unavailable", "missing_body")
    elif _textual_media(media):
        kind = "empty" if data == "" and external is None else "text"
        if charset is not None:
            try:
                b"".decode(charset)
            except LookupError:
                kind, reason = "unsupported", "unsupported_charset"
    return GmailPart(
        identifier,
        filename,
        media,
        charset,
        size,
        external,
        data,
        is_file,
        kind,
        reason,
    )


def _gmail_content_headers(
    part: Mapping[str, object],
    provider_media_type: str,
    *,
    attachment_policy: bool = True,
) -> tuple[str, str | None, str | None]:
    if attachment_policy:
        provider_text(provider_media_type, 255)
        attachment_media_type(provider_media_type)
    elif (
        re.fullmatch(
            r"[!#$%&'*+.^_`|~0-9A-Za-z-]+/[!#$%&'*+.^_`|~0-9A-Za-z-]+",
            provider_media_type,
        )
        is None
    ):
        raise ValueError("Gmail media type is malformed")
    headers = _raw_gmail_headers(part)
    content_types = [
        header["value"]
        for header in headers
        if header["name"].lower() == "content-type"
    ]
    dispositions = [
        header["value"]
        for header in headers
        if header["name"].lower() == "content-disposition"
    ]
    if len(content_types) > 1 or len(dispositions) > 1:
        raise ValueError("Gmail content metadata is duplicated")
    raw = content_types[0] if content_types else provider_media_type
    if attachment_policy:
        provider_text(raw, 1_024)
        for value in dispositions:
            provider_text(value, 1_024)
    raw = _unfold_header(raw)
    parsed: Any = Parser(policy=policy.default).parsestr(f"Content-Type: {raw}\n\n")
    header = parsed["Content-Type"]
    if header is None or header.defects:
        raise ValueError("Gmail content type is malformed")
    media_type = provider_media_type.lower()
    if parsed.get_content_type().lower() != media_type:
        raise ValueError("Gmail MIME content type is inconsistent")
    charset = parsed.get_content_charset()
    disposition = None
    if dispositions:
        disposition_header = _unfold_header(dispositions[0])
        parsed_disposition: Any = Parser(policy=policy.default).parsestr(
            f"Content-Disposition: {disposition_header}\n\n"
        )
        header = parsed_disposition["Content-Disposition"]
        if header is None or header.defects:
            raise ValueError("Gmail disposition is malformed")
        disposition = parsed_disposition.get_content_disposition()
        if disposition is not None and disposition != "inline":
            disposition = "attachment"
    return media_type, charset, disposition


def _calendar_list_event(
    calendar_id: str, value: object
) -> CalendarListNormalEvent | CalendarListCancelledEvent:
    event = provider_object(value, "Calendar event")
    event_id = provider_text(provider_string(event, "id"), 1_024)
    calendar = provider_text(calendar_id, 1_024)
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
    summary, summary_truncated = _truncate(
        _optional_string(event, "summary", ""), 1_024
    )
    location, location_truncated = (
        (None, False)
        if event.get("location") is None
        else _truncate(_optional_string(event, "location", ""), 4_096)
    )
    return CalendarListNormalEvent(
        calendar_id=calendar,
        event_id=event_id,
        status=cast("Any", status),
        summary_preview=summary,
        summary_truncated=summary_truncated,
        start=parse_calendar_time(event.get("start")),
        end=(
            UnspecifiedEventEnd()
            if unspecified_end
            else parse_calendar_time(event.get("end"))
        ),
        location_preview=location,
        location_truncated=location_truncated,
    )


def parse_calendar_time(value: object) -> TimedEventTime | AllDayEventTime:
    event_time = provider_object(value, "Calendar event time")
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
    raw_instant = provider_string(event_time, "dateTime")
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


def _reminder(value: object) -> Reminder:
    reminder = provider_object(value, "Calendar reminder")
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
    place = provider_object(value, "Place")
    display = provider_object(place.get("displayName"), "Place display name")
    location_value = place.get("location")
    location: Coordinates | None = None
    if location_value is not None:
        coordinates = provider_object(location_value, "Place location")
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
    types = provider_array(place.get("types", []), "Place types")
    if len(types) > 32:
        raise _ProviderTooLarge
    links = provider_object(place.get("googleMapsLinks", {}), "Place link")
    uri = links.get("placeUri", place.get("googleMapsUri"))
    if uri is not None and not isinstance(uri, str):
        raise ValueError("Place link is malformed")
    return Place(
        place_id=provider_text(provider_string(place, "id"), 1_024),
        display_name=provider_text(provider_string(display, "text"), 512),
        formatted_address=_exact_optional(place, "formattedAddress", 1_024),
        location=location,
        types=tuple(_exact_string(item, 128) for item in types),
        maps_uri=provider_text(uri, 4_096) if uri is not None else None,
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

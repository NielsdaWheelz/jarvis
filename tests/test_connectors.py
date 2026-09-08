from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import stat
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from llm_tools import canonical_json_bytes

from jarvis.connectors import (
    GOOGLE_AAD_NAMESPACE,
    GOOGLE_STATE_SCHEMA,
    MAX_PROVIDER_BODY_BYTES,
    GoogleCredentialDefect,
    GoogleReadConnector,
    GoogleTokenManager,
    MapsReadConnector,
)
from jarvis.read_tools import (
    PLACE_DETAILS_FIELD_MASK,
    PLACES_SEARCH_FIELD_MASK,
    ROUTES_FIELD_MASK,
    AddressLocation,
    AllDayEventTime,
    CalendarGetEventInput,
    CalendarListCalendarsInput,
    CalendarListCancelledEvent,
    CalendarListEventsInput,
    CalendarListNormalEvent,
    CalendarNormalEvent,
    ConnectorFailure,
    GmailReadThreadInput,
    GmailSearchInput,
    MapsDirectionsInput,
    MapsGetPlaceInput,
    MapsSearchPlacesInput,
    TimedEventTime,
    UnspecifiedEventEnd,
)

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.acls.readonly",
]


class _Tokens:
    async def access_token(
        self, *, attempt_started: Callable[[], None] | None = None
    ) -> tuple[str, int]:
        del attempt_started
        return "host-google-token", 0

    def invalidate_access_token(self) -> None:
        pass


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _encoded(
    key: bytes,
    value: str,
    *,
    field: str,
    version: str = "v2",
) -> str:
    nonce = b"n" * 12
    payload = AESGCM(key).encrypt(
        nonce,
        value.encode(),
        f"{GOOGLE_AAD_NAMESPACE}:{version}:{field}".encode(),
    )
    return f"aesgcm.v1.{_b64url(nonce + payload)}"


def _decrypt_encoded(key: bytes, envelope: str, *, field: str) -> str:
    assert envelope.startswith("aesgcm.v1.")
    encoded = envelope.removeprefix("aesgcm.v1.")
    combined = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    return (
        AESGCM(key)
        .decrypt(
            combined[:12],
            combined[12:],
            f"{GOOGLE_AAD_NAMESPACE}:v2:{field}".encode(),
        )
        .decode()
    )


def _state(
    path: Path,
    *,
    expires_at: datetime,
    material: bytes = b"qualified-single-secret-material-longer-than-32-bytes",
) -> tuple[str, bytes, dict[str, object]]:
    secret = _b64url(material)
    key = material if len(material) == 32 else hashlib.sha256(material).digest()
    value: dict[str, object] = {
        "access_token_enc": _encoded(key, "old-access", field="access_token"),
        "access_token_expires_at": expires_at.isoformat(),
        "account_email": "owner@example.invalid",
        "account_subject": "subject",
        "encryption": {
            "aad_namespace": "jarvis.connector.google:v2",
            "algorithm": "AES-256-GCM",
            "key_version": "v2",
        },
        "granted_scopes": SCOPES,
        "provider": "google",
        "refresh_token_enc": _encoded(key, "refresh", field="refresh_token"),
        "schema": GOOGLE_STATE_SCHEMA,
        "status": "connected",
        "token_obtained_at": (NOW - timedelta(hours=1)).isoformat(),
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return secret, key, value


def _keyring(key: bytes) -> str:
    encoded = base64.urlsafe_b64encode(key).decode().rstrip("=")
    return json.dumps({"v2": encoded})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material",
    [b"k" * 32, b"qualified-single-secret-material-longer-than-32-bytes"],
)
async def test_qualified_google_state_decrypts_without_network(
    tmp_path: Path, material: bytes
) -> None:
    state_path = tmp_path / "google.json"
    secret, _, _ = _state(
        state_path,
        expires_at=NOW + timedelta(hours=1),
        material=material,
    )
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        manager = GoogleTokenManager(
            state_path=state_path,
            client=client,
            client_id="client",
            client_secret="secret",
            active_key_version="v2",
            configured_keys=_keyring(b"r" * 32),
            single_secret=secret,
            now=lambda: NOW,
        )
        assert await manager.access_token() == ("old-access", 0)
    assert calls == 0


@pytest.mark.asyncio
async def test_google_refresh_counts_attempt_and_atomically_reencrypts(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "google.json"
    secret, key, _ = _state(state_path, expires_at=NOW)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://oauth2.googleapis.com/token")
        assert b"refresh_token=refresh" in await request.aread()
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "expires_in": 3600,
                "token_type": "bearer",
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        manager = GoogleTokenManager(
            state_path=state_path,
            client=client,
            client_id="client",
            client_secret="secret",
            active_key_version="v2",
            configured_keys=_keyring(b"r" * 32),
            single_secret=secret,
            now=lambda: NOW,
        )
        assert await manager.access_token() == ("new-access", 1)

    raw = state_path.read_text(encoding="utf-8")
    assert "new-access" not in raw
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    persisted = cast("dict[str, Any]", json.loads(raw))
    assert persisted["encryption"]["aad_namespace"] == "jarvis.connector.google:v2"
    assert (
        _decrypt_encoded(key, persisted["access_token_enc"], field="access_token")
        == "new-access"
    )
    assert (
        _decrypt_encoded(key, persisted["refresh_token_enc"], field="refresh_token")
        == "refresh"
    )


@pytest.mark.asyncio
async def test_google_state_envelope_binds_token_field(tmp_path: Path) -> None:
    state_path = tmp_path / "google.json"
    secret, key, state = _state(state_path, expires_at=NOW + timedelta(hours=1))
    state["access_token_enc"] = _encoded(key, "old-access", field="refresh_token")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    state_path.chmod(0o600)

    async with httpx.AsyncClient(trust_env=False) as client:
        manager = GoogleTokenManager(
            state_path=state_path,
            client=client,
            client_id="client",
            client_secret="secret",
            active_key_version="v2",
            configured_keys=_keyring(b"r" * 32),
            single_secret=secret,
            now=lambda: NOW,
        )
        with pytest.raises(GoogleCredentialDefect, match="decryption failed"):
            await manager.access_token()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "envelope",
    [
        "aeadv1:v2:bm9uY2U:Y2lwaGVydGV4dA",
        "aesgcm.v1.not%base64url",
        "aesgcm.v1." + "A" * 30_000,
    ],
)
async def test_google_state_rejects_malformed_or_oversized_envelope(
    tmp_path: Path, envelope: str
) -> None:
    state_path = tmp_path / "google.json"
    secret, _, state = _state(state_path, expires_at=NOW + timedelta(hours=1))
    state["access_token_enc"] = envelope
    state_path.write_text(json.dumps(state), encoding="utf-8")
    state_path.chmod(0o600)

    async with httpx.AsyncClient(trust_env=False) as client:
        manager = GoogleTokenManager(
            state_path=state_path,
            client=client,
            client_id="client",
            client_secret="secret",
            active_key_version="v2",
            configured_keys=_keyring(b"r" * 32),
            single_secret=secret,
            now=lambda: NOW,
        )
        with pytest.raises(GoogleCredentialDefect):
            await manager.access_token()


@pytest.mark.asyncio
async def test_gmail_search_preserves_query_and_rejects_whitespace_before_io() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"threads": [{"id": "thread", "snippet": "hello"}]},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.gmail_search(
            GmailSearchInput(query='subject:"two  spaces"', max_results=1)
        )
        assert result.attempts == 1
        assert requests[0].url.params["q"] == 'subject:"two  spaces"'
        assert requests[0].headers["authorization"] == "Bearer host-google-token"
        with pytest.raises(ConnectorFailure) as raised:
            await connector.gmail_search(GmailSearchInput(query="   ", max_results=1))
        assert (raised.value.code, raised.value.attempts) == ("invalid_query", 0)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_gmail_thread_is_one_call_bounded_inert_and_chronological() -> None:
    requests: list[httpx.Request] = []
    encoded_html = base64.urlsafe_b64encode(
        b"<p>Hello &amp;amp;</p><script>do_not_execute()</script>tail &amp"
    ).decode()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        messages: list[dict[str, object]] = []
        for number in (2, 1):
            messages.append(
                {
                    "id": f"m{number}",
                    "threadId": "thread/id",
                    "internalDate": str(1_700_000_000_000 + number),
                    "payload": {
                        "mimeType": "multipart/mixed",
                        "headers": [
                            {"name": "Subject", "value": "Synthetic"},
                            {
                                "name": "To",
                                "value": "undisclosed-recipients:;",
                            },
                            {
                                "name": "Message-ID",
                                "value": f"<m{number}@example.invalid>",
                            },
                        ],
                        "body": {},
                        "parts": [
                            {
                                "mimeType": "text/html",
                                "filename": "",
                                "body": {"data": encoded_html},
                            },
                            {
                                "mimeType": "application/pdf",
                                "filename": "file.pdf",
                                "body": {"attachmentId": "not-fetched", "size": 12},
                            },
                        ],
                    },
                }
            )
        return httpx.Response(
            200,
            json={"id": "thread/id", "messages": messages},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.gmail_read_thread(
            GmailReadThreadInput(thread_id="thread/id", max_messages=2)
        )
    assert len(requests) == 1
    assert requests[0].url.raw_path.split(b"?", 1)[0].endswith(b"/threads/thread%2Fid")
    assert [message.message_id for message in result.value.messages] == ["m1", "m2"]
    assert result.value.messages[0].body_text.startswith("\nHello")
    assert "Hello &amp;" in result.value.messages[0].body_text
    assert result.value.messages[0].body_text.endswith("tail &")
    assert result.value.messages[0].to == ()
    assert result.value.messages[0].attachments[0].filename == "file.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ('"', ":;(", "<@[ "))
async def test_malformed_gmail_mailbox_header_is_provider_unavailable(
    header: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "thread",
                "messages": [
                    {
                        "id": "message",
                        "threadId": "thread",
                        "internalDate": "1700000000000",
                        "payload": {
                            "mimeType": "text/plain",
                            "headers": [{"name": "From", "value": header}],
                            "body": {"data": "aGVsbG8="},
                        },
                    }
                ],
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.gmail_read_thread(
                GmailReadThreadInput(thread_id="thread", max_messages=1)
            )
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_calendar_normal_and_sparse_cancelled_normalization() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert await request.aread() == b""
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "primary-id",
                            "summary": "Primary",
                            "accessRole": "owner",
                            "primary": True,
                        }
                    ]
                },
                request=request,
            )
        assert request.url.path == "/calendar/v3/calendars/primary-id/events"
        return httpx.Response(
            200,
            json={
                "items": [
                    {"id": "cancelled", "status": "cancelled"},
                    {
                        "id": "event",
                        "etag": "etag",
                        "status": "confirmed",
                        "summary": "Synthetic",
                        "start": {"dateTime": "2026-09-04T12:00:00Z"},
                        "end": {"dateTime": "2026-09-04T13:00:00Z"},
                        "updated": "2026-09-04T11:00:00Z",
                    },
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="America/Los_Angeles",
            )
        )
    assert result.attempts == 2
    assert result.value.calendars[0].calendar_id == "primary-id"
    assert result.value.failures == ()
    assert result.value.coverage.complete is True
    assert result.value.coverage.matched_events == 2
    normal = result.value.events[0]
    assert isinstance(normal, CalendarListNormalEvent)
    assert isinstance(normal.start, TimedEventTime)
    assert isinstance(normal.end, TimedEventTime)
    assert normal.start.time_zone == "UTC"
    assert isinstance(result.value.events[1], CalendarListCancelledEvent)


@pytest.mark.asyncio
async def test_calendar_compact_list_ignores_full_only_provider_fields() -> None:
    event = {
        "id": "event",
        "status": "confirmed",
        "summary": "Synthetic",
        "start": {"dateTime": "2026-09-04T12:00:00Z"},
        "end": {"dateTime": "2026-09-04T13:00:00Z"},
        "location": "Room",
        "etag": {"malformed": True},
        "updated": {"malformed": True},
        "description": "x" * 20_000,
        "recurrence": {"malformed": True},
        "attendees": {"malformed": True},
        "organizer": "malformed",
        "reminders": "malformed",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={"items": [{"id": "a", "accessRole": "reader"}]},
                request=request,
            )
        if request.url.path == "/calendar/v3/calendars/a/events":
            return httpx.Response(200, json={"items": [event]}, request=request)
        assert request.url.path == "/calendar/v3/calendars/a/events/event"
        return httpx.Response(200, json=event, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        listed = await connector.calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.calendar_get_event(
                CalendarGetEventInput(calendar_id="a", event_id="event")
            )

    assert listed.value.coverage.complete is True
    assert listed.value.events == (
        CalendarListNormalEvent(
            calendar_id="a",
            event_id="event",
            status="confirmed",
            summary="Synthetic",
            start=TimedEventTime(
                date_time=datetime(2026, 9, 4, 12, tzinfo=UTC), time_zone="UTC"
            ),
            end=TimedEventTime(
                date_time=datetime(2026, 9, 4, 13, tzinfo=UTC), time_zone="UTC"
            ),
            location="Room",
        ),
    )
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "compact_field",
    (
        {"summary": "x" * 1_025},
        {"location": "x" * 4_097},
    ),
)
async def test_calendar_compact_list_rejects_oversized_returned_fields_whole(
    compact_field: dict[str, object],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={"items": [{"id": "a", "accessRole": "reader"}]},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "event",
                        "status": "confirmed",
                        "summary": "Synthetic",
                        "start": {"date": "2026-09-08"},
                        "end": {"date": "2026-09-09"},
                        **compact_field,
                    }
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.value.events == ()
    assert result.value.failures[0].error == "ProviderResponseTooLarge"
    assert result.value.coverage.reasons == ("calendar_failure",)
    assert result.value.coverage.matched_events is None


@pytest.mark.asyncio
async def test_calendar_event_attempts_include_each_token_refresh() -> None:
    class RefreshingTokens(_Tokens):
        async def access_token(
            self, *, attempt_started: Callable[[], None] | None = None
        ) -> tuple[str, int]:
            if attempt_started is not None:
                attempt_started()
            return "host-google-token", 1

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={"items": [{"id": "a", "accessRole": "reader"}]},
                request=request,
            )
        return httpx.Response(200, json={"items": []}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", RefreshingTokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.attempts == 4


@pytest.mark.asyncio
async def test_calendar_discovery_includes_hidden_reader_calendars() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/calendar/v3/users/me/calendarList"
        assert dict(request.url.params) == {
            "maxResults": "50",
            "minAccessRole": "reader",
            "showDeleted": "false",
            "showHidden": "true",
        }
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "owner@example.invalid",
                        "summary": "Provider name",
                        "summaryOverride": "Personal",
                        "timeZone": "America/Los_Angeles",
                        "accessRole": "owner",
                        "primary": True,
                        "selected": True,
                    },
                    {
                        "id": "hidden@example.invalid",
                        "summary": "Hidden",
                        "accessRole": "reader",
                        "hidden": True,
                    },
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.calendar_list_calendars(CalendarListCalendarsInput())

    assert result.attempts == 1
    assert result.value.truncated is False
    assert tuple(item.display_name for item in result.value.calendars) == (
        "Personal",
        "Hidden",
    )
    assert result.value.calendars[0].primary is True
    assert result.value.calendars[1].hidden is True


@pytest.mark.asyncio
async def test_calendar_discovery_caps_and_rejects_duplicate_identities() -> None:
    duplicate = False

    async def handler(request: httpx.Request) -> httpx.Response:
        items = [
            {"id": f"calendar-{index}", "accessRole": "reader"} for index in range(51)
        ]
        if duplicate:
            items[1]["id"] = "calendar-0"
        return httpx.Response(200, json={"items": items}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.calendar_list_calendars(CalendarListCalendarsInput())
        assert len(result.value.calendars) == 50
        assert result.value.truncated is True

        duplicate = True
        with pytest.raises(ConnectorFailure) as raised:
            await connector.calendar_list_calendars(CalendarListCalendarsInput())
    assert (raised.value.code, raised.value.attempts) == ("provider_unavailable", 1)


@pytest.mark.asyncio
async def test_calendar_events_aggregate_chronologically_with_partial_failures() -> (
    None
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "a", "summary": "A", "accessRole": "owner"},
                        {"id": "b", "summary": "B", "accessRole": "writer"},
                        {"id": "c", "summary": "C", "accessRole": "reader"},
                    ]
                },
                request=request,
            )
        calendar_id = request.url.path.split("/")[-2]
        if calendar_id == "c":
            return httpx.Response(404, json={}, request=request)
        hour = 14 if calendar_id == "a" else 12
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": f"event-{calendar_id}",
                        "etag": f"etag-{calendar_id}",
                        "status": "confirmed",
                        "summary": calendar_id.upper(),
                        "start": {"dateTime": f"2026-09-04T{hour}:00:00Z"},
                        "end": {"dateTime": f"2026-09-04T{hour + 1}:00:00Z"},
                        "updated": "2026-09-04T11:00:00Z",
                    }
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW - timedelta(days=1),
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.attempts == 4
    assert tuple(item.calendar_id for item in result.value.calendars) == ("a", "b", "c")
    assert tuple(item.calendar_id for item in result.value.events) == ("b", "a")
    assert tuple((item.calendar_id, item.error) for item in result.value.failures) == (
        ("c", "CalendarNotFound"),
    )
    assert result.value.coverage.complete is False
    assert result.value.coverage.reasons == ("calendar_failure",)
    assert result.value.coverage.calendars_discovered == 3
    assert result.value.coverage.calendars_completed == 2
    assert result.value.coverage.matched_events is None


@pytest.mark.asyncio
async def test_calendar_events_complete_35_calendars_and_1170_events() -> None:
    requests: list[tuple[str, str | None]] = []
    active = 0
    maximum_active = 0
    event_counts = {f"c{index:02}": 34 if index < 15 else 33 for index in range(35)}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": f"c{index:02}", "accessRole": "reader"}
                        for index in reversed(range(35))
                    ]
                },
                request=request,
            )
        calendar_id = request.url.path.split("/")[-2]
        page_token = request.url.params.get("pageToken")
        requests.append((calendar_id, page_token))
        assert request.url.params["maxResults"] == "250"
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        calendar_index = int(calendar_id[1:])
        local_indices = (
            range(1) if page_token is None else range(1, event_counts[calendar_id])
        )
        payload: dict[str, object] = {
            "items": [
                {
                    "id": f"event-{local_index * 35 + calendar_index:04}",
                    "status": "confirmed",
                    "summary": calendar_id,
                    "start": {
                        "dateTime": (
                            NOW + timedelta(minutes=local_index * 35 + calendar_index)
                        ).isoformat()
                    },
                    "end": {
                        "dateTime": (
                            NOW
                            + timedelta(minutes=local_index * 35 + calendar_index + 1)
                        ).isoformat()
                    },
                }
                for local_index in reversed(local_indices)
            ],
        }
        if page_token is None:
            payload["nextPageToken"] = "second"
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW - timedelta(days=1),
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.attempts == 71
    assert maximum_active == 10
    assert requests[:35] == [(f"c{index:02}", None) for index in range(35)]
    assert requests[35:] == [(f"c{index:02}", "second") for index in range(35)]
    assert tuple(event.event_id for event in result.value.events) == tuple(
        f"event-{index:04}" for index in range(1_170)
    )
    envelope = {"type": "Success", "value": result.value.model_dump(mode="json")}
    assert len(canonical_json_bytes(envelope)) <= 524_288
    assert result.value.coverage.model_dump(mode="json") == {
        "complete": True,
        "reasons": [],
        "calendars_discovered": 35,
        "calendars_completed": 35,
        "matched_events": 1_170,
    }


@pytest.mark.asyncio
async def test_calendar_events_reports_event_page_limit() -> None:
    page_counts = {"a": 0, "b": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "b", "accessRole": "reader"},
                        {"id": "a", "accessRole": "reader"},
                    ],
                },
                request=request,
            )
        calendar_id = request.url.path.split("/")[-2]
        page_counts[calendar_id] += 1
        return httpx.Response(
            200,
            json={"items": [], "nextPageToken": str(page_counts[calendar_id])},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.attempts == 101
    assert page_counts == {"a": 50, "b": 50}
    assert result.value.coverage.complete is False
    assert result.value.coverage.reasons == ("event_page_limit",)
    assert result.value.coverage.calendars_completed == 0
    assert result.value.coverage.matched_events is None


@pytest.mark.asyncio
async def test_calendar_list_pagination_is_explicitly_partial() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "a", "accessRole": "reader"}],
                    "nextPageToken": "more-calendars",
                },
                request=request,
            )
        return httpx.Response(200, json={"items": []}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.value.coverage.model_dump(mode="json") == {
        "complete": False,
        "reasons": ["calendar_limit"],
        "calendars_discovered": 1,
        "calendars_completed": 1,
        "matched_events": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_count", "location_bytes", "expected_reasons"),
    [
        (1_501, 0, ("event_limit",)),
        (1_500, 4_096, ("output_byte_limit",)),
    ],
)
async def test_calendar_events_reports_event_and_output_byte_clipping(
    event_count: int,
    location_bytes: int,
    expected_reasons: tuple[str, ...],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={"items": [{"id": "a", "accessRole": "reader"}]},
                request=request,
            )
        offset = int(request.url.params.get("pageToken", "0"))
        page_end = min(offset + 250, event_count)
        payload: dict[str, object] = {
            "items": [
                {
                    "id": f"event-{index:04}",
                    "status": "confirmed",
                    "summary": "Synthetic",
                    "location": "x" * location_bytes if location_bytes else None,
                    "start": {"dateTime": (NOW + timedelta(minutes=index)).isoformat()},
                    "end": {
                        "dateTime": (NOW + timedelta(minutes=index + 1)).isoformat()
                    },
                }
                for index in range(offset, page_end)
            ]
        }
        if page_end < event_count:
            payload["nextPageToken"] = str(page_end)
        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    envelope = {
        "type": "Success",
        "value": result.value.model_dump(mode="json"),
    }
    assert len(canonical_json_bytes(envelope)) <= 524_288
    assert 0 < len(result.value.events) <= 1_500
    assert result.value.coverage.reasons == expected_reasons
    assert result.value.coverage.matched_events == event_count
    assert len(result.value.events) < event_count


@pytest.mark.asyncio
async def test_calendar_events_reports_connector_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("jarvis.connectors.CALENDAR_EVENT_DEADLINE_SECONDS", 0.05)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={"items": [{"id": "a", "accessRole": "reader"}]},
                request=request,
            )
        await asyncio.sleep(1)
        return httpx.Response(200, json={"items": []}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        ).calendar_list_events(
            CalendarListEventsInput(
                time_min=NOW,
                time_max=NOW + timedelta(days=1),
                time_zone="UTC",
            )
        )

    assert result.attempts == 2
    assert result.value.coverage.reasons == ("deadline",)
    assert result.value.coverage.calendars_completed == 0
    assert result.value.coverage.matched_events is None


@pytest.mark.asyncio
async def test_calendar_events_propagates_caller_cancellation() -> None:
    page_started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(
                200,
                json={"items": [{"id": "a", "accessRole": "reader"}]},
                request=request,
            )
        page_started.set()
        await asyncio.sleep(10)
        return httpx.Response(200, json={"items": []}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        task = asyncio.create_task(
            GoogleReadConnector(
                client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
            ).calendar_list_events(
                CalendarListEventsInput(
                    time_min=NOW,
                    time_max=NOW + timedelta(days=1),
                    time_zone="UTC",
                )
            )
        )
        await page_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_calendar_participants_and_offset_free_dst_are_deterministic() -> None:
    responses = [
        ("2026-01-15T09:00:00", "2026-01-15T17:00:00+00:00"),
        ("2026-11-01T01:30:00", "2026-11-01T08:30:00+00:00"),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        raw, _ = responses.pop(0)
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "status": "confirmed",
                "start": {"dateTime": raw, "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": raw, "timeZone": "America/Los_Angeles"},
                "attendees": [{}],
                "organizer": {},
                "updated": "2026-09-04T11:00:00Z",
            },
            request=request,
        )

    expected_values = tuple(expected for _, expected in responses)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        for expected in expected_values:
            result = await connector.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="event")
            )
            assert isinstance(result.value.event, CalendarNormalEvent)
            event = result.value.event
            assert isinstance(event.writable.start, TimedEventTime)
            assert isinstance(event.writable.end, TimedEventTime)
            assert event.writable.start.date_time.isoformat() == expected
            assert event.writable.start.time_zone == "America/Los_Angeles"
            assert event.writable.attendees[0].name is None
            assert event.writable.attendees[0].address is None
            assert event.organizer is not None
            assert event.organizer.address is None


@pytest.mark.asyncio
async def test_calendar_nonexistent_offset_free_time_is_malformed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "status": "confirmed",
                "start": {
                    "dateTime": "2026-03-08T02:30:00",
                    "timeZone": "America/Los_Angeles",
                },
                "end": {
                    "dateTime": "2026-03-08T02:30:00",
                    "timeZone": "America/Los_Angeles",
                },
                "updated": "2026-09-04T11:00:00Z",
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="event")
            )
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_unrepresentable_input_instants_fail_before_provider_io() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    too_early = datetime.min.replace(tzinfo=timezone(timedelta(hours=1)))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        google = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as calendar:
            await google.calendar_list_events(
                CalendarListEventsInput(
                    time_min=too_early,
                    time_max=NOW,
                    time_zone="UTC",
                )
            )
        maps = MapsReadConnector(client=client, api_key="maps", now=lambda: NOW)
        with pytest.raises(ConnectorFailure) as directions:
            await maps.directions(
                MapsDirectionsInput(
                    origin=AddressLocation(address="A"),
                    destination=AddressLocation(address="B"),
                    travel_mode="transit",
                    departure_at=too_early,
                )
            )
    assert (calendar.value.code, calendar.value.attempts) == ("invalid_range", 0)
    assert (directions.value.code, directions.value.attempts) == (
        "invalid_departure_time",
        0,
    )
    assert calls == 0


@pytest.mark.asyncio
async def test_unrepresentable_provider_instant_is_declared_too_large() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "status": "confirmed",
                "start": {"dateTime": "2026-09-04T12:00:00Z"},
                "end": {"dateTime": "2026-09-04T13:00:00Z"},
                "updated": "0001-01-01T00:00:00+01:00",
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="event")
            )
    assert raised.value.code == "provider_response_too_large"


@pytest.mark.asyncio
async def test_calendar_normal_event_requires_observed_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "start": {"dateTime": "2026-09-04T12:00:00Z"},
                "end": {"dateTime": "2026-09-04T13:00:00Z"},
                "updated": "2026-09-04T11:00:00Z",
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="event")
            )
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_fields", "expected_end_type"),
    (
        (
            {
                "start": {"dateTime": "2026-09-04T12:00:00Z"},
                "end": {"dateTime": "2026-09-04T13:00:00Z"},
            },
            TimedEventTime,
        ),
        (
            {
                "endTimeUnspecified": False,
                "start": {"date": "2026-09-04"},
                "end": {"date": "2026-09-05"},
            },
            AllDayEventTime,
        ),
        (
            {
                "eventType": "fromGmail",
                "endTimeUnspecified": True,
                "start": {"dateTime": "2026-09-04T12:00:00Z"},
                "end": {"dateTime": 7},
            },
            UnspecifiedEventEnd,
        ),
    ),
)
async def test_calendar_observed_end_normalization(
    event_fields: dict[str, object],
    expected_end_type: (
        type[TimedEventTime] | type[AllDayEventTime] | type[UnspecifiedEventEnd]
    ),
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "status": "confirmed",
                "updated": "2026-09-04T11:00:00Z",
                **event_fields,
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.calendar_get_event(
            CalendarGetEventInput(calendar_id="primary", event_id="event")
        )
    assert isinstance(result.value.event, CalendarNormalEvent)
    event = result.value.event
    assert isinstance(event.writable.end, expected_end_type)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_fields",
    (
        pytest.param(
            {
                "endTimeUnspecified": "false",
                "end": {"dateTime": "2026-09-04T13:00:00Z"},
            },
            id="non-boolean-flag",
        ),
        pytest.param(
            {"endTimeUnspecified": False, "end": {"dateTime": 7}},
            id="false-malformed-end",
        ),
        pytest.param(
            {"end": {"dateTime": 7}},
            id="missing-flag-malformed-end",
        ),
        pytest.param(
            {"endTimeUnspecified": False},
            id="false-absent-end",
        ),
        pytest.param({}, id="missing-flag-absent-end"),
    ),
)
async def test_calendar_malformed_known_end_is_provider_unavailable(
    event_fields: dict[str, object],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "status": "confirmed",
                "start": {"dateTime": "2026-09-04T12:00:00Z"},
                "updated": "2026-09-04T11:00:00Z",
                **event_fields,
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="event")
            )
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_places_and_routes_use_exact_masks_and_no_alternatives() -> None:
    assert PLACES_SEARCH_FIELD_MASK == (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.types,places.googleMapsLinks.placeUri"
    )
    assert PLACE_DETAILS_FIELD_MASK == (
        "id,displayName,formattedAddress,location,types,googleMapsLinks.placeUri"
    )
    assert ROUTES_FIELD_MASK == (
        "routes.distanceMeters,routes.duration,routes.description,routes.warnings"
    )
    assert "polyline" not in ROUTES_FIELD_MASK.lower()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("places:searchText"):
            assert request.headers["x-goog-fieldmask"] == PLACES_SEARCH_FIELD_MASK
            assert json.loads(await request.aread())["pageSize"] == 1
            value = {
                "places": [
                    {
                        "id": "place",
                        "displayName": {"text": "Synthetic Place"},
                        "googleMapsLinks": {"placeUri": "https://maps.example/place"},
                    }
                ]
            }
        else:
            assert request.headers["x-goog-fieldmask"] == ROUTES_FIELD_MASK
            body = json.loads(await request.aread())
            assert body["computeAlternativeRoutes"] is False
            value = {
                "routes": [
                    {
                        "duration": "1.1s",
                        "warnings": ["Display this warning"],
                    }
                ]
            }
        return httpx.Response(200, json=value, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = MapsReadConnector(
            client=client, api_key="maps-key", now=lambda: NOW
        )
        place = await connector.search_places(
            MapsSearchPlacesInput(query="coffee", location_bias=None, max_results=1)
        )
        route = await connector.directions(
            MapsDirectionsInput(
                origin=AddressLocation(address="A"),
                destination=AddressLocation(address="B"),
                travel_mode="walking",
                departure_at=None,
            )
        )
    assert place.value.places[0].maps_uri == "https://maps.example/place"
    assert route.value.routes[0].duration_seconds == 2
    assert route.value.routes[0].distance_meters == 0
    assert route.value.routes[0].warnings == ("Display this warning",)


@pytest.mark.asyncio
async def test_stable_identity_mismatches_and_past_nontransit_fail() -> None:
    async def google_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "different", "status": "cancelled"},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(google_handler), trust_env=False
    ) as client:
        google = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await google.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="wanted")
            )
        assert raised.value.code == "provider_unavailable"

    calls = 0

    async def maps_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(maps_handler), trust_env=False
    ) as client:
        maps = MapsReadConnector(client=client, api_key="maps-key", now=lambda: NOW)
        with pytest.raises(ConnectorFailure) as raised:
            await maps.directions(
                MapsDirectionsInput(
                    origin=AddressLocation(address="A"),
                    destination=AddressLocation(address="B"),
                    travel_mode="driving",
                    departure_at=NOW - timedelta(seconds=1),
                )
            )
        assert (raised.value.code, raised.value.attempts) == (
            "invalid_departure_time",
            0,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_decoded_provider_body_is_rejected_at_stream_bound() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"{" + b" " * MAX_PROVIDER_BODY_BYTES + b"}",
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.gmail_search(GmailSearchInput(query="x", max_results=1))
    assert (raised.value.code, raised.value.attempts) == (
        "provider_response_too_large",
        1,
    )


@pytest.mark.asyncio
async def test_get_place_has_no_request_body_and_exact_identity() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-fieldmask"] == PLACE_DETAILS_FIELD_MASK
        assert await request.aread() == b""
        return httpx.Response(
            200,
            json={"id": "different", "displayName": {"text": "Different"}},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = MapsReadConnector(
            client=client, api_key="maps-key", now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.get_place(MapsGetPlaceInput(place_id="wanted"))
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_gmail_mime_charset_and_unnamed_attachments_are_exact() -> None:
    latin = base64.urlsafe_b64encode("café".encode("iso-8859-1")).decode()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "thread",
                "messages": [
                    {
                        "id": "message",
                        "threadId": "thread",
                        "internalDate": "-1",
                        "payload": {
                            "mimeType": "multipart/related",
                            "filename": "",
                            "headers": [],
                            "body": {},
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "filename": "",
                                    "headers": [
                                        {
                                            "name": "Content-Type",
                                            "value": ("text/plain; charset=iso-8859-1"),
                                        }
                                    ],
                                    "body": {"data": latin},
                                },
                                {
                                    "mimeType": "image/png",
                                    "filename": "",
                                    "headers": [
                                        {
                                            "name": "Content-Disposition",
                                            "value": "inline",
                                        }
                                    ],
                                    "body": {"attachmentId": "cid", "size": 12},
                                },
                                {
                                    "mimeType": "application/pdf",
                                    "filename": "",
                                    "headers": [
                                        {
                                            "name": "Content-Disposition",
                                            "value": "x-provider",
                                        }
                                    ],
                                    "body": {"attachmentId": "pdf", "size": 13},
                                },
                                {
                                    "mimeType": "text/plain",
                                    "filename": "",
                                    "headers": [],
                                    "body": {"attachmentId": "text", "size": 14},
                                },
                            ],
                        },
                    }
                ],
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        result = await connector.gmail_read_thread(
            GmailReadThreadInput(thread_id="thread", max_messages=1)
        )
    message = result.value.messages[0]
    assert message.internal_at == datetime(1969, 12, 31, 23, 59, 59, 999000, UTC)
    assert message.body_text == "café"
    assert message.body_truncated
    assert result.value.truncated
    attachments = [
        (item.filename, item.media_type, item.size_bytes)
        for item in message.attachments
    ]
    assert attachments == [
        ("", "image/png", 12),
        ("", "application/pdf", 13),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"nextPageToken": 1}, "provider_unavailable"),
        ({"duplicate": True}, "provider_unavailable"),
    ],
)
async def test_malformed_google_payload_is_sanitized(
    payload: dict[str, object], expected: str
) -> None:
    private = "private-provider-content-canary"

    async def handler(request: httpx.Request) -> httpx.Response:
        if "nextPageToken" in payload:
            return httpx.Response(
                200,
                json={**payload, "threads": [{"id": private, "snippet": private}]},
                request=request,
            )
        return httpx.Response(
            200,
            content=b'{"threads":[],"private-provider-content-canary":1,'
            b'"private-provider-content-canary":2}',
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            await connector.gmail_search(GmailSearchInput(query="x", max_results=1))
    assert raised.value.code == expected
    assert private not in "".join(traceback.format_exception(raised.value))


@pytest.mark.asyncio
async def test_google_403_quota_and_401_invalidation_are_bounded() -> None:
    class Tokens(_Tokens):
        invalidated = False

        def invalidate_access_token(self) -> None:
            self.invalidated = True

    statuses = [403, 401]
    tokens = Tokens()

    async def handler(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        return httpx.Response(
            status,
            json={"error": {"errors": [{"reason": "quotaExceeded"}]}},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", tokens), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as quota:
            await connector.gmail_search(GmailSearchInput(query="x", max_results=1))
        with pytest.raises(ConnectorFailure) as unauthorized:
            await connector.gmail_search(GmailSearchInput(query="x", max_results=1))
    assert (quota.value.code, quota.value.attempts) == ("rate_limited", 1)
    assert (unauthorized.value.code, unauthorized.value.attempts) == (
        "provider_unavailable",
        1,
    )
    assert tokens.invalidated


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "status", "expected"),
    [
        ("gmail.search", 400, "invalid_query"),
        ("gmail.read_thread", 404, "thread_not_found"),
        ("calendar.get_event", 404, "event_not_found"),
        ("gmail.search", 429, "rate_limited"),
        ("gmail.search", 500, "provider_unavailable"),
        ("gmail.search", None, "provider_unavailable"),
    ],
)
async def test_google_status_and_network_failures_are_declared(
    operation: str,
    status: int | None,
    expected: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if (
            operation == "calendar.list_events"
            and request.url.path == "/calendar/v3/users/me/calendarList"
        ):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "primary-id",
                            "summary": "Primary",
                            "accessRole": "owner",
                        }
                    ]
                },
                request=request,
            )
        if status is None:
            raise httpx.ConnectError("synthetic", request=request)
        return httpx.Response(status, json={}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as raised:
            if operation == "gmail.search":
                await connector.gmail_search(
                    GmailSearchInput(query="synthetic", max_results=1)
                )
            elif operation == "gmail.read_thread":
                await connector.gmail_read_thread(
                    GmailReadThreadInput(thread_id="thread", max_messages=1)
                )
            elif operation == "calendar.list_events":
                await connector.calendar_list_events(
                    CalendarListEventsInput(
                        time_min=NOW,
                        time_max=NOW + timedelta(hours=1),
                        time_zone="UTC",
                    )
                )
            else:
                await connector.calendar_get_event(
                    CalendarGetEventInput(calendar_id="primary", event_id="event")
                )
    assert (raised.value.code, raised.value.attempts) == (expected, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "status", "body", "expected"),
    [
        ("search", 400, {}, "invalid_query"),
        ("get", 400, {}, "place_not_found"),
        ("get", 404, {}, "place_not_found"),
        ("directions", 200, {"routes": []}, "no_route"),
        ("search", 429, {}, "rate_limited"),
        ("search", 500, {}, "provider_unavailable"),
        ("search", None, {}, "provider_unavailable"),
    ],
)
async def test_maps_status_and_network_failures_are_declared(
    operation: str,
    status: int | None,
    body: dict[str, object],
    expected: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise httpx.ConnectError("synthetic", request=request)
        return httpx.Response(status, json=body, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = MapsReadConnector(client=client, api_key="maps", now=lambda: NOW)
        with pytest.raises(ConnectorFailure) as raised:
            if operation == "search":
                await connector.search_places(
                    MapsSearchPlacesInput(
                        query="synthetic",
                        location_bias=None,
                        max_results=1,
                    )
                )
            elif operation == "get":
                await connector.get_place(MapsGetPlaceInput(place_id="place"))
            else:
                await connector.directions(
                    MapsDirectionsInput(
                        origin=AddressLocation(address="A"),
                        destination=AddressLocation(address="B"),
                        travel_mode="walking",
                        departure_at=None,
                    )
                )
    assert (raised.value.code, raised.value.attempts) == (expected, 1)


@pytest.mark.asyncio
async def test_numeric_provider_overbounds_are_declared_too_large() -> None:
    async def calendar_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event",
                "etag": "etag",
                "status": "confirmed",
                "start": {"dateTime": "2026-09-04T12:00:00Z"},
                "end": {"dateTime": "2026-09-04T13:00:00Z"},
                "reminders": {"overrides": [{"method": "popup", "minutes": 40_321}]},
                "updated": "2026-09-04T11:00:00Z",
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(calendar_handler), trust_env=False
    ) as client:
        calendar = GoogleReadConnector(
            client=client, tokens=cast("Any", _Tokens()), now=lambda: NOW
        )
        with pytest.raises(ConnectorFailure) as reminder:
            await calendar.calendar_get_event(
                CalendarGetEventInput(calendar_id="primary", event_id="event")
            )
    assert reminder.value.code == "provider_response_too_large"

    async def maps_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "place",
                        "displayName": {"text": "Place"},
                        "location": {"latitude": 91, "longitude": 0},
                    }
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(maps_handler), trust_env=False
    ) as client:
        maps = MapsReadConnector(client=client, api_key="maps", now=lambda: NOW)
        with pytest.raises(ConnectorFailure) as coordinates:
            await maps.search_places(
                MapsSearchPlacesInput(query="x", location_bias=None, max_results=1)
            )
    assert coordinates.value.code == "provider_response_too_large"


@pytest.mark.asyncio
async def test_places_missing_proto_scalars_normalize_to_zero() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "first",
                        "displayName": {"text": "First"},
                        "location": {"longitude": 2},
                    },
                    {
                        "id": "second",
                        "displayName": {"text": "Second"},
                        "location": {"latitude": 1},
                    },
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        maps = MapsReadConnector(client=client, api_key="maps", now=lambda: NOW)
        result = await maps.search_places(
            MapsSearchPlacesInput(query="x", location_bias=None, max_results=2)
        )
    assert result.value.places[0].location is not None
    assert result.value.places[0].location.latitude == 0
    assert result.value.places[1].location is not None
    assert result.value.places[1].location.longitude == 0


@pytest.mark.asyncio
async def test_route_duration_overflow_is_declared_too_large() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "duration": "2147483647.000000001s",
                        "warnings": [],
                    }
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        maps = MapsReadConnector(client=client, api_key="maps", now=lambda: NOW)
        with pytest.raises(ConnectorFailure) as raised:
            await maps.directions(
                MapsDirectionsInput(
                    origin=AddressLocation(address="A"),
                    destination=AddressLocation(address="B"),
                    travel_mode="walking",
                    departure_at=None,
                )
            )
    assert raised.value.code == "provider_response_too_large"

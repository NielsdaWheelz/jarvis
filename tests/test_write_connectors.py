from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

import jarvis.write_connectors as write_connectors
from jarvis.write_connectors import (
    GmailUpdateReconciliationBasis,
    GoogleWriteConnector,
    calendar_event_id,
    gmail_content_digest,
    gmail_effect_id,
)
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailUpdateDraftInput,
    Mailbox,
    Reminder,
    TimedEventTime,
    WriteAttemptBudget,
    WriteConnectorFailure,
)

ACTION_ID = UUID("12345678-1234-4234-8234-123456789abc")
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
ATTEMPTS = WriteAttemptBudget(0, 4)


class _Tokens:
    async def access_token(self) -> tuple[str, int]:
        return "host-token", 0

    def invalidate_access_token(self) -> None:
        pass


async def _stage(
    *,
    action_id: UUID,
    draft_id: str,
    thread_id: str,
    jarvis_effect_id: str,
    old_content_digest: str,
) -> object:
    del action_id, draft_id, thread_id, jarvis_effect_id, old_content_digest
    return None


async def _stage_attempts(*, action_id: UUID, actual_external_attempts: int) -> object:
    del action_id, actual_external_attempts
    return None


async def _no_sleep(_: float) -> None:
    pass


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _content(*, subject: str = "Synthetic") -> GmailContent:
    return GmailContent(
        to=(Mailbox(name="Owner", address="owner@example.invalid"),),
        cc=(),
        bcc=(),
        subject=subject,
        body_text="Synthetic body without an implicit newline.",
        reply_to=None,
    )


def _event(*, summary: str = "Synthetic event") -> CalendarWritableEvent:
    return CalendarWritableEvent(
        summary=summary,
        description=None,
        location=None,
        start=TimedEventTime(date_time=NOW, time_zone="UTC"),
        end=TimedEventTime(date_time=NOW + timedelta(hours=1), time_zone="UTC"),
        recurrence=(),
        attendees=(),
        use_default_reminders=False,
        reminders=(Reminder(method="popup", minutes=10),),
    )


def _calendar_response(
    *, event_id: str, event: CalendarWritableEvent, etag: str = '"etag"'
) -> dict[str, object]:
    assert isinstance(event.start, TimedEventTime)
    assert isinstance(event.end, TimedEventTime)
    return {
        "id": event_id,
        "etag": etag,
        "status": "confirmed",
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "start": {
            "dateTime": event.start.date_time.isoformat(),
            "timeZone": event.start.time_zone,
        },
        "end": {
            "dateTime": event.end.date_time.isoformat(),
            "timeZone": event.end.time_zone,
        },
        "recurrence": list(event.recurrence),
        "attendees": [],
        "reminders": {
            "useDefault": event.use_default_reminders,
            "overrides": [item.model_dump(mode="json") for item in event.reminders],
        },
        "organizer": {"email": "owner@example.invalid"},
        "updated": NOW.isoformat(),
    }


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


@pytest.mark.asyncio
async def test_gmail_create_is_one_unsent_mutation_with_exact_effect_header() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = cast("dict[str, Any]", json.loads(await request.aread()))
        assert set(body) == {"message"}
        raw = _decode(body["message"]["raw"])
        message = BytesParser(policy=policy.default).parsebytes(raw)
        assert message.get_all("X-Jarvis-Effect-ID") == [gmail_effect_id(ACTION_ID)]
        assert message.get("Bcc") is None
        assert message.get_payload(decode=True) == _content().body_text.encode()
        return httpx.Response(
            200,
            json={"id": "draft", "message": {"id": "message", "threadId": "thread"}},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
        )
        result = await connector.gmail_create_draft(
            GmailCreateDraftInput(content=_content()), ACTION_ID, ATTEMPTS
        )

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path.endswith("/users/me/drafts")
    assert result.value.jarvis_effect_id == gmail_effect_id(ACTION_ID)
    assert result.value.content_digest == gmail_content_digest(_content())


@pytest.mark.asyncio
async def test_gmail_update_preflights_digest_and_preserves_effect_header() -> None:
    initial = _content()
    replacement = _content(subject="Replacement")
    created_raw = ""
    methods: list[str] = []
    staged: list[dict[str, object]] = []

    async def stage(**value: object) -> object:
        staged.append(value)
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created_raw
        methods.append(request.method)
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            created_raw = body["message"]["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {
                        "id": "message",
                        "threadId": "thread",
                        "raw": created_raw,
                    },
                },
                request=request,
            )
        body = cast("dict[str, Any]", json.loads(await request.aread()))
        raw = BytesParser(policy=policy.default).parsebytes(
            _decode(body["message"]["raw"])
        )
        assert raw.get_all("X-Jarvis-Effect-ID") == [gmail_effect_id(ACTION_ID)]
        assert raw.get("Subject") == "Replacement"
        return httpx.Response(
            200,
            json={"id": "draft", "message": {"id": "message", "threadId": "thread"}},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=cast("Any", stage),
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=initial), ACTION_ID, ATTEMPTS
        )
        result = await connector.gmail_update_draft(
            GmailUpdateDraftInput(
                draft_id="draft",
                expected_content_digest=gmail_content_digest(initial),
                replacement=replacement,
            ),
            UUID("22345678-1234-4234-8234-123456789abc"),
            ATTEMPTS,
        )

    assert methods == ["POST", "GET", "PUT"]
    assert staged == [
        {
            "action_id": UUID("22345678-1234-4234-8234-123456789abc"),
            "draft_id": "draft",
            "thread_id": "thread",
            "jarvis_effect_id": gmail_effect_id(ACTION_ID),
            "old_content_digest": gmail_content_digest(initial),
        }
    ]
    assert result.value.jarvis_effect_id == gmail_effect_id(ACTION_ID)
    assert result.value.content_digest == gmail_content_digest(replacement)


@pytest.mark.asyncio
async def test_gmail_update_changed_draft_does_not_mutate() -> None:
    raw_holder = [""]

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw_holder[0] = body["message"]["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {
                    "id": "message",
                    "threadId": "thread",
                    "raw": raw_holder[0],
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=_content()), ACTION_ID, ATTEMPTS
        )
        with pytest.raises(WriteConnectorFailure) as raised:
            await connector.gmail_update_draft(
                GmailUpdateDraftInput(
                    draft_id="draft",
                    expected_content_digest="0" * 64,
                    replacement=_content(subject="Replacement"),
                ),
                ACTION_ID,
                ATTEMPTS,
            )
    assert raised.value.code == "draft_changed"


@pytest.mark.asyncio
async def test_calendar_create_update_delete_use_action_id_and_conditions() -> None:
    original = _event()
    replacement = _event(summary="Replacement")
    expected = _snapshot(original)
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            assert body["id"] == calendar_event_id(ACTION_ID)
            assert request.url.params["sendUpdates"] == "none"
            return httpx.Response(
                200,
                json=_calendar_response(event_id=body["id"], event=original),
                request=request,
            )
        assert request.headers["if-match"] == '"etag"'
        if request.method == "PATCH":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            assert "id" not in body
            return httpx.Response(
                200,
                json=_calendar_response(event_id="event-id", event=replacement),
                request=request,
            )
        return httpx.Response(204, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
        )
        created = await connector.calendar_create_event(
            CalendarCreateEventInput(
                calendar_id="owner@example.invalid",
                event=original,
                notify_attendees=False,
            ),
            ACTION_ID,
            ATTEMPTS,
        )
        updated = await connector.calendar_update_event(
            CalendarUpdateEventInput(
                expected=expected,
                replacement=replacement,
                notify_attendees=False,
            ),
            ACTION_ID,
            ATTEMPTS,
        )
        deleted = await connector.calendar_delete_event(
            CalendarDeleteEventInput(expected=expected, notify_attendees=False),
            ACTION_ID,
            ATTEMPTS,
        )

    assert methods == ["POST", "PATCH", "DELETE"]
    assert created.value.event.event_id == calendar_event_id(ACTION_ID)
    assert updated.value.event.writable == replacement
    assert deleted.value.prior_etag == expected.etag


@pytest.mark.asyncio
async def test_calendar_create_conflict_reconciles_exact_action_event() -> None:
    value = CalendarCreateEventInput(
        calendar_id="owner@example.invalid",
        event=_event(),
        notify_attendees=False,
    )
    event_id = calendar_event_id(ACTION_ID)
    requests: list[httpx.Request] = []
    staged_attempts: list[tuple[UUID, int]] = []

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        staged_attempts.append((action_id, actual_external_attempts))
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            assert body["id"] == event_id
            return httpx.Response(409, request=request)
        assert request.url.path.endswith(f"/events/{event_id}")
        return httpx.Response(
            200,
            json=_calendar_response(event_id=event_id, event=value.event),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        )
        with pytest.raises(TimeoutError, match="conflict needs reconciliation"):
            await connector.calendar_create_event(value, ACTION_ID, ATTEMPTS)
        result = await connector.reconcile_calendar_create(value, ACTION_ID)

    assert [request.method for request in requests] == ["POST", "GET", "GET", "GET"]
    assert staged_attempts == [(ACTION_ID, 1)]
    assert result.outcome == "succeeded"
    assert result.evidence == "exact-event-at-effect-id"
    assert result.value is not None
    assert result.value.event.event_id == event_id
    assert result.value.event.writable == value.event


@pytest.mark.asyncio
async def test_calendar_create_conflict_with_different_event_is_uncertain() -> None:
    value = CalendarCreateEventInput(
        calendar_id="owner@example.invalid",
        event=_event(),
        notify_attendees=False,
    )
    event_id = calendar_event_id(ACTION_ID)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(409, request=request)
        assert request.url.path.endswith(f"/events/{event_id}")
        return httpx.Response(
            200,
            json=_calendar_response(
                event_id=event_id,
                event=_event(summary="Conflicting synthetic event"),
            ),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        )
        with pytest.raises(TimeoutError, match="conflict needs reconciliation"):
            await connector.calendar_create_event(value, ACTION_ID, ATTEMPTS)
        result = await connector.reconcile_calendar_create(value, ACTION_ID)

    assert result.outcome == "uncertain"
    assert result.evidence == "conflicting-event-at-effect-id"
    assert result.value is None


@pytest.mark.asyncio
async def test_calendar_create_conflict_with_incomplete_reads_is_uncertain() -> None:
    value = CalendarCreateEventInput(
        calendar_id="owner@example.invalid",
        event=_event(),
        notify_attendees=False,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(409, request=request)
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        )
        with pytest.raises(TimeoutError, match="conflict needs reconciliation"):
            await connector.calendar_create_event(value, ACTION_ID, ATTEMPTS)
        result = await connector.reconcile_calendar_create(value, ACTION_ID)

    assert result.outcome == "uncertain"
    assert result.evidence == "calendar-observations-incomplete"
    assert result.value is None


@pytest.mark.asyncio
async def test_calendar_current_snapshot_is_one_bounded_non_mutating_read() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=_calendar_response(event_id="event-id", event=_event()),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
        )
        result = await connector.calendar_current_snapshot(
            "owner@example.invalid", "event-id"
        )

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert result.outcome == "found"
    assert result.value == _snapshot(_event())


@pytest.mark.asyncio
async def test_mutation_timeout_and_server_error_require_reconciliation() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
        )
        with pytest.raises(TimeoutError, match="reconciliation"):
            await connector.gmail_create_draft(
                GmailCreateDraftInput(content=_content()), ACTION_ID, ATTEMPTS
            )


@pytest.mark.asyncio
async def test_calendar_create_reconciliation_proves_absence_at_three_points() -> None:
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=sleep,
        )
        result = await connector.reconcile_calendar_create(
            CalendarCreateEventInput(
                calendar_id="owner@example.invalid",
                event=_event(),
                notify_attendees=False,
            ),
            ACTION_ID,
        )

    assert delays == [2.0, 8.0]
    assert result.outcome == "absent"
    assert result.value is None


@pytest.mark.asyncio
async def test_gmail_create_reconciliation_pages_without_search_or_ordering() -> None:
    value = GmailCreateDraftInput(content=_content())
    effect_id = gmail_effect_id(ACTION_ID)
    raw = ""
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls, raw
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw = cast("dict[str, str]", body["message"])["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        if request.url.path.endswith("/drafts"):
            list_calls += 1
            assert "q" not in request.url.params
            assert request.url.params["maxResults"] == "8"
            if list_calls == 1:
                assert "pageToken" not in request.url.params
                return httpx.Response(
                    200,
                    json={"drafts": [], "nextPageToken": "second-page"},
                    request=request,
                )
            assert dict(request.url.params) == {
                "maxResults": "8",
                "pageToken": "second-page",
            }
            return httpx.Response(
                200,
                json={"drafts": [{"id": "draft"}]},
                request=request,
            )
        assert request.url.path.endswith("/drafts/draft")
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {
                    "id": "message",
                    "threadId": "thread",
                    "raw": raw,
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=lambda _: pytest.fail("complete exact match must finish immediately"),
        )
        await connector.gmail_create_draft(value, ACTION_ID, ATTEMPTS)
        result = await connector.reconcile_gmail_create(value, ACTION_ID)

    assert result.outcome == "succeeded"
    assert result.evidence == (
        "gmail-create-one-exact-match;rounds=1;complete=true;nextPageToken=absent"
    )
    assert result.value is not None
    assert result.value.jarvis_effect_id == effect_id
    assert list_calls == 2


@pytest.mark.asyncio
async def test_gmail_create_exact_match_succeeds_after_bounded_incomplete_listing() -> (
    None
):
    value = GmailCreateDraftInput(content=_content())
    raw = ""
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls, raw
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw = cast("dict[str, str]", body["message"])["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        if request.url.path.endswith("/drafts"):
            list_calls += 1
            assert request.url.params["maxResults"] == "8"
            assert "q" not in request.url.params
            if list_calls > 1:
                assert request.url.params["pageToken"] == f"page-{list_calls}"
            return httpx.Response(
                200,
                json={
                    "drafts": ([{"id": "draft"}] if list_calls == 1 else []),
                    "nextPageToken": f"page-{list_calls + 1}",
                },
                request=request,
            )
        assert request.url.path.endswith("/drafts/draft")
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {
                    "id": "message",
                    "threadId": "thread",
                    "raw": raw,
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        )
        await connector.gmail_create_draft(value, ACTION_ID, ATTEMPTS)
        result = await connector.reconcile_gmail_create(value, ACTION_ID)

    assert list_calls == 5
    assert result.outcome == "succeeded"
    assert result.evidence == (
        "gmail-create-one-exact-match;rounds=1;complete=false;nextPageToken=present"
    )
    assert result.value is not None


@pytest.mark.asyncio
async def test_gmail_create_duplicate_exact_matches_are_uncertain() -> None:
    value = GmailCreateDraftInput(content=_content())
    raw = ""
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls, raw
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw = cast("dict[str, str]", body["message"])["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft-one",
                    "message": {"id": "message-one", "threadId": "thread"},
                },
                request=request,
            )
        if request.url.path.endswith("/drafts"):
            list_calls += 1
            return httpx.Response(
                200,
                json={"drafts": [{"id": "draft-one"}, {"id": "draft-two"}]},
                request=request,
            )
        draft_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "id": draft_id,
                "message": {
                    "id": f"message-{draft_id}",
                    "threadId": "thread",
                    "raw": raw,
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        )
        await connector.gmail_create_draft(value, ACTION_ID, ATTEMPTS)
        result = await connector.reconcile_gmail_create(value, ACTION_ID)

    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-conflicting-matches;rounds=3;complete=true;nextPageToken=absent"
    )
    assert result.value is None
    assert list_calls == 3


@pytest.mark.asyncio
async def test_gmail_create_same_effect_with_different_content_is_uncertain() -> None:
    value = GmailCreateDraftInput(content=_content())
    conflicting_raw = ""
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal conflicting_raw, list_calls
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            conflicting_raw = cast("dict[str, str]", body["message"])["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        if request.url.path.endswith("/drafts"):
            list_calls += 1
            return httpx.Response(
                200,
                json={"drafts": [{"id": "draft"}]},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {
                    "id": "message",
                    "threadId": "thread",
                    "raw": conflicting_raw,
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=_content(subject="Conflicting content")),
            ACTION_ID,
            ATTEMPTS,
        )
        result = await connector.reconcile_gmail_create(value, ACTION_ID)

    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-conflicting-matches;rounds=3;complete=true;nextPageToken=absent"
    )
    assert result.value is None
    assert list_calls == 3


@pytest.mark.asyncio
async def test_gmail_create_three_complete_no_matches_are_uncertain() -> None:
    list_calls = 0
    delays: list[float] = []
    staged_attempts: list[tuple[UUID, int]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls
        list_calls += 1
        assert request.url.path.endswith("/drafts")
        return httpx.Response(200, json={"drafts": []}, request=request)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        staged_attempts.append((action_id, actual_external_attempts))
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
            sleep=sleep,
        )
        result = await connector.reconcile_gmail_create(
            GmailCreateDraftInput(content=_content()), ACTION_ID
        )

    assert list_calls == 3
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-no-match;rounds=3;complete=true;nextPageToken=absent"
    )
    assert result.value is None
    assert delays == [2.0, 8.0]
    assert staged_attempts == []


@pytest.mark.asyncio
async def test_gmail_create_page_bound_is_incomplete_with_token_evidence() -> None:
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls
        list_calls += 1
        assert request.url.path.endswith("/drafts")
        assert "q" not in request.url.params
        round_call = (list_calls - 1) % 5
        expected_token = None if round_call == 0 else f"page-{round_call + 1}"
        assert request.url.params.get("pageToken") == expected_token
        next_token = f"page-{round_call + 2}"
        return httpx.Response(
            200,
            json={"drafts": [], "nextPageToken": next_token},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert list_calls == 15
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-incomplete;rounds=3;complete=false;nextPageToken=present"
    )


@pytest.mark.asyncio
async def test_gmail_create_malformed_candidate_and_page_token_are_uncertain() -> None:
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls
        list_calls += 1
        assert request.url.path.endswith("/drafts")
        if list_calls % 2 == 1:
            return httpx.Response(
                200,
                json={"drafts": [], "nextPageToken": "repeated"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"drafts": [{"id": 7}], "nextPageToken": "repeated"},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert list_calls == 6
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-malformed;rounds=3;complete=false;nextPageToken=present"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bound_name",
    ("_GMAIL_CREATE_SCAN_MAX_DRAFTS", "_GMAIL_CREATE_SCAN_MAX_RAW_GETS"),
)
async def test_gmail_create_draft_and_raw_candidate_bounds_are_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    bound_name: str,
) -> None:
    list_calls = 0
    raw_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls, raw_calls
        if request.url.path.endswith("/drafts"):
            list_calls += 1
            return httpx.Response(
                200,
                json={"drafts": [{"id": "draft-b"}, {"id": "draft-a"}]},
                request=request,
            )
        raw_calls += 1
        return httpx.Response(
            200,
            json={
                "id": "draft-a",
                "message": {
                    "id": "message-a",
                    "threadId": "thread",
                    "raw": base64.urlsafe_b64encode(
                        b"Subject: unrelated\r\n\r\nSynthetic"
                    )
                    .decode()
                    .rstrip("="),
                },
            },
            request=request,
        )

    monkeypatch.setattr(write_connectors, bound_name, 1)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert list_calls == 3
    assert raw_calls == 3
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-incomplete;rounds=3;complete=false;nextPageToken=absent"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_raw_get", (False, True))
async def test_gmail_create_transient_listing_or_raw_read_is_uncertain(
    fail_raw_get: bool,
) -> None:
    list_calls = 0
    raw_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls, raw_calls
        if request.url.path.endswith("/drafts"):
            list_calls += 1
            if not fail_raw_get:
                return httpx.Response(503, request=request)
            return httpx.Response(
                200, json={"drafts": [{"id": "draft"}]}, request=request
            )
        raw_calls += 1
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert list_calls == 3
    assert raw_calls == (3 if fail_raw_get else 0)
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-incomplete;rounds=3;complete=false;"
        f"nextPageToken={'absent' if fail_raw_get else 'unknown'}"
    )


@pytest.mark.asyncio
async def test_gmail_create_malformed_raw_candidate_is_uncertain() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/drafts"):
            return httpx.Response(
                200, json={"drafts": [{"id": "draft"}]}, request=request
            )
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {
                    "id": "message",
                    "threadId": "thread",
                    "raw": "not-base64!",
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-malformed;rounds=3;complete=false;nextPageToken=absent"
    )


@pytest.mark.asyncio
async def test_gmail_create_response_byte_bound_spans_all_rereads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"drafts":[]}'
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls
        list_calls += 1
        return httpx.Response(200, content=body, request=request)

    monkeypatch.setattr(write_connectors, "_GMAIL_CREATE_SCAN_MAX_BYTES", len(body) * 2)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=_no_sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert list_calls == 2
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-incomplete;rounds=2;complete=false;nextPageToken=absent"
    )


@pytest.mark.asyncio
async def test_gmail_create_total_elapsed_bound_returns_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal list_calls
        list_calls += 1
        return httpx.Response(200, json={"drafts": []}, request=request)

    async def sleep(_: float) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(write_connectors, "_GMAIL_CREATE_SCAN_MAX_SECONDS", 0.01)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=sleep,
        ).reconcile_gmail_create(GmailCreateDraftInput(content=_content()), ACTION_ID)

    assert list_calls == 1
    assert result.outcome == "uncertain"
    assert result.evidence == (
        "gmail-create-timeout;complete=false;nextPageToken=unknown"
    )


@pytest.mark.asyncio
async def test_gmail_create_declared_rejection_is_not_ambiguous() -> None:
    staged_attempts: list[tuple[UUID, int]] = []

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        staged_attempts.append((action_id, actual_external_attempts))
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
        )
        with pytest.raises(WriteConnectorFailure) as raised:
            await connector.gmail_create_draft(
                GmailCreateDraftInput(content=_content()), ACTION_ID, ATTEMPTS
            )

    assert raised.value.code == "invalid_recipient"
    assert raised.value.attempts == 1
    assert staged_attempts == [(ACTION_ID, 1)]


@pytest.mark.asyncio
async def test_gmail_update_reconciliation_proves_only_exact_old_draft_absent() -> None:
    initial = _content()
    replacement = _content(subject="Replacement")
    raw_holder = [""]
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw_holder[0] = body["message"]["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {
                    "id": "message",
                    "threadId": "thread",
                    "raw": raw_holder[0],
                },
            },
            request=request,
        )

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=sleep,
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=initial), ACTION_ID, ATTEMPTS
        )
        result = await connector.reconcile_gmail_update(
            GmailUpdateDraftInput(
                draft_id="draft",
                expected_content_digest=gmail_content_digest(initial),
                replacement=replacement,
            ),
            GmailUpdateReconciliationBasis(
                type="gmail_update_reconciliation_v1",
                draft_id="draft",
                thread_id="thread",
                jarvis_effect_id=gmail_effect_id(ACTION_ID),
                old_content_digest=gmail_content_digest(initial),
            ),
        )

    assert delays == [2.0, 8.0]
    assert result.outcome == "absent"


@pytest.mark.asyncio
async def test_gmail_update_inspects_known_thread_after_disappearance() -> None:
    initial = _content()
    replacement = _content(subject="Replacement")
    desired_raw = ""
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal desired_raw
        paths.append(request.url.path)
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            desired_raw = body["message"]["raw"]
            return httpx.Response(
                200,
                json={
                    "id": "draft",
                    "message": {"id": "message", "threadId": "thread"},
                },
                request=request,
            )
        if request.url.path.endswith("/drafts/draft"):
            return httpx.Response(404, request=request)
        assert request.url.path.endswith("/threads/thread")
        assert request.url.params["format"] == "raw"
        return httpx.Response(
            200,
            json={
                "id": "thread",
                "messages": [
                    {"id": "sent-message", "threadId": "thread", "raw": desired_raw}
                ],
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage,
            stage_external_attempts=_stage_attempts,
            now=lambda: NOW,
            sleep=lambda _: pytest.fail(
                "exact thread evidence must finish immediately"
            ),
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=replacement), ACTION_ID, ATTEMPTS
        )
        result = await connector.reconcile_gmail_update(
            GmailUpdateDraftInput(
                draft_id="draft",
                expected_content_digest=gmail_content_digest(initial),
                replacement=replacement,
            ),
            GmailUpdateReconciliationBasis(
                type="gmail_update_reconciliation_v1",
                draft_id="draft",
                thread_id="thread",
                jarvis_effect_id=gmail_effect_id(ACTION_ID),
                old_content_digest=gmail_content_digest(initial),
            ),
        )

    assert paths == [
        "/gmail/v1/users/me/drafts",
        "/gmail/v1/users/me/drafts/draft",
        "/gmail/v1/users/me/threads/thread",
    ]
    assert result.outcome == "succeeded"
    assert result.evidence == "one-exact-message-in-known-thread"
    assert result.value is not None
    assert result.value.draft_id == "draft"
    assert result.value.message_id == "sent-message"
    assert result.value.thread_id == "thread"
    assert result.value.jarvis_effect_id == gmail_effect_id(ACTION_ID)
    assert result.value.content_digest == gmail_content_digest(replacement)

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from jarvis.discord import ApprovalComponentDecision, DeliverySucceeded
from jarvis.write_tools import (
    CalendarDeleteEventInput,
    CalendarEventSnapshot,
    CalendarWritableEvent,
    GmailSendDraftSuccess,
    Mailbox,
    TimedEventTime,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qualify_approvals.py"
_QUALIFIER = run_path(str(SCRIPT))
_Artifacts: Any = _QUALIFIER["Artifacts"]
_LostAcceptedSendTransport: Any = _QUALIFIER["LostAcceptedSendTransport"]
_QualificationFailure: Any = _QUALIFIER["QualificationFailure"]
_RecordingApprovalDelivery: Any = _QUALIFIER["_RecordingApprovalDelivery"]
_RecordingOrdinaryDelivery: Any = _QUALIFIER["_RecordingOrdinaryDelivery"]
_cleanup_calendar_with_approvals = _QUALIFIER["_cleanup_calendar_with_approvals"]
_cleanup_discord = _QUALIFIER["_cleanup_discord"]
_delete_drafts = _QUALIFIER["_delete_drafts"]
_verify_one_recipient_copy = _QUALIFIER["_verify_one_recipient_copy"]
_wait_for_sent_cleanup = _QUALIFIER["_wait_for_sent_cleanup"]
assert_sanitized_output = _QUALIFIER["assert_sanitized_output"]
live_arguments = _QUALIFIER["live_arguments"]
main = _QUALIFIER["main"]
validate_result_evidence = _QUALIFIER["validate_result_evidence"]
_DECISIONS = cast("tuple[str, ...]", _QUALIFIER["_DECISIONS"])
_EXPECTED_GIT_PINS = cast("dict[str, str]", _QUALIFIER["EXPECTED_GIT_PINS"])
_EXPECTED_PACKAGE_VERSIONS = cast(
    "dict[str, str]", _QUALIFIER["EXPECTED_PACKAGE_VERSIONS"]
)


class _Tokens:
    calls = 0

    async def access_token(self) -> tuple[str, int]:
        self.calls += 1
        return "synthetic-token", 0


class _OrdinaryDiscord:
    async def create_message(
        self,
        *,
        persisted_message_id: object,
        content: str,
    ) -> DeliverySucceeded:
        del persisted_message_id, content
        return DeliverySucceeded("123456", 1)


class _ApprovalDiscord:
    calls = 0

    async def create_approval_message(self, **values: object) -> DeliverySucceeded:
        self.calls += 1
        assert values["disabled"] is False
        return DeliverySucceeded("654321", 1)


def _environment() -> dict[str, str]:
    return {
        "JARVIS_APPROVALS_LIVE": "1",
        "JARVIS_APPROVALS_IRREVERSIBLE_ACK": (
            "send-real-owner-mail-and-mutate-calendar"
        ),
        "JARVIS_APPROVALS_OWNER_SCOPE_ACK": (
            "recipient-and-calendar-are-owner-controlled"
        ),
        "JARVIS_APPROVALS_MANUAL_GMAIL_CLEANUP": "1",
        "JARVIS_APPROVALS_RECIPIENT": "owner@example.invalid",
        "JARVIS_APPROVALS_CALENDAR_ID": "shared@example.invalid",
        "JARVIS_APPROVALS_WAIT_SECONDS": "60",
        "JARVIS_APPROVALS_CLEANUP_WAIT_SECONDS": "60",
    }


def _evidence() -> dict[str, object]:
    return {
        "actions": {
            "identical_arguments_remained_distinct": True,
            "one_durable_effect_per_approval": True,
            "rows": 12,
        },
        "approvals": {
            "approve": 6,
            "deny": 2,
            "real_owner_components": 8,
        },
        "calendar": {
            "approved_unknown_calendar_create_update_delete": True,
            "denied_actions_had_no_effect": True,
            "exact_render_and_reconciliation": True,
        },
        "cleanup": {
            "calendar": True,
            "discord": True,
            "gmail_drafts": True,
            "gmail_sent": True,
        },
        "dependencies": {**_EXPECTED_GIT_PINS, **_EXPECTED_PACKAGE_VERSIONS},
        "gmail": {
            "accepted_send_lost_response_reconciled_once": True,
            "draft_mismatch_sent_nothing": True,
            "lost_response_exactly_one_recipient_copy": True,
            "normal_send_exactly_one_recipient_copy": True,
            "stable_creation_effect_header": True,
        },
        "implementation": {
            "architecture": "synthetic",
            "lock_sha256": "a" * 64,
            "main_definition_fingerprint": "b" * 64,
            "main_plan_revision": "synthetic-plan",
            "os": "synthetic",
            "session_compatibility_revision": "synthetic-session",
        },
        "status": "passed",
    }


def test_live_arguments_require_every_irreversible_operator_gate() -> None:
    environment = _environment()
    arguments = live_arguments(environment)

    assert arguments.recipient == "owner@example.invalid"
    assert arguments.calendar_id == "shared@example.invalid"
    assert arguments.approval_wait_seconds == 60.0
    assert arguments.cleanup_wait_seconds == 60.0

    for name in (
        "JARVIS_APPROVALS_LIVE",
        "JARVIS_APPROVALS_IRREVERSIBLE_ACK",
        "JARVIS_APPROVALS_OWNER_SCOPE_ACK",
        "JARVIS_APPROVALS_MANUAL_GMAIL_CLEANUP",
        "JARVIS_APPROVALS_RECIPIENT",
        "JARVIS_APPROVALS_CALENDAR_ID",
    ):
        changed = dict(environment)
        changed.pop(name)
        with pytest.raises(ValueError):
            live_arguments(changed)

    for name, value in (
        ("JARVIS_APPROVALS_WAIT_SECONDS", "59"),
        ("JARVIS_APPROVALS_WAIT_SECONDS", "901"),
        ("JARVIS_APPROVALS_CLEANUP_WAIT_SECONDS", "1201"),
        ("JARVIS_APPROVALS_CLEANUP_WAIT_SECONDS", "nan"),
    ):
        changed = dict(environment)
        changed[name] = value
        with pytest.raises(ValueError):
            live_arguments(changed)


def test_live_manifest_requires_eight_real_owner_component_decisions() -> None:
    assert _DECISIONS == (
        "gmail_normal_approve",
        "gmail_lost_response_approve",
        "gmail_mismatch_approve",
        "calendar_first_identical_deny",
        "calendar_second_identical_deny",
        "calendar_create_approve",
        "calendar_update_approve",
        "calendar_delete_approve",
    )
    assert ApprovalComponentDecision.APPROVE.value == "approve"
    assert ApprovalComponentDecision.DENY.value == "deny"


def test_live_workflow_has_no_constructed_or_bypassed_interaction() -> None:
    source = SCRIPT.read_text()

    assert "approval_interaction_sink=session.interaction" in source
    assert source.count("claim_and_acknowledge(") == 1
    assert "DiscordApprovalInteraction(" not in source
    assert "approval_custom_id(" not in source
    assert "parse_approval_custom_id(" not in source
    assert source.index('stage="gmail-mismatch-update"') < source.index(
        "await session.deliver(mismatch_action)"
    )


@pytest.mark.asyncio
async def test_lost_response_transport_loses_one_accepted_send_only() -> None:
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, json={"accepted": True}, request=request)

    transport = _LostAcceptedSendTransport(httpx.MockTransport(respond))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://gmail.googleapis.com",
        trust_env=False,
    ) as client:
        transport.arm()
        with pytest.raises(httpx.ReadTimeout):
            await client.post("/gmail/v1/users/me/drafts/send")
        response = await client.post("/gmail/v1/users/me/drafts/send")
        unrelated = await client.post("/gmail/v1/users/me/drafts")

    assert response.status_code == 200
    assert unrelated.status_code == 200
    assert transport.accepted_losses == 1
    assert transport.send_requests == 2
    assert requests == [
        "/gmail/v1/users/me/drafts/send",
        "/gmail/v1/users/me/drafts/send",
        "/gmail/v1/users/me/drafts",
    ]


@pytest.mark.asyncio
async def test_recording_ordinary_delivery_tracks_discord_cleanup_target() -> None:
    artifacts = _Artifacts()
    delivery = _RecordingOrdinaryDelivery(_OrdinaryDiscord(), artifacts)

    result = await delivery.create_message(
        persisted_message_id="synthetic-message",
        content="Synthetic host resolution.",
    )

    assert result == DeliverySucceeded("123456", 1)
    assert artifacts.discord_message_ids == {"123456"}


@pytest.mark.asyncio
async def test_recording_approval_delivery_tracks_early_cleanup_target() -> None:
    artifacts = _Artifacts()
    discord = _ApprovalDiscord()
    delivery = _RecordingApprovalDelivery(discord, artifacts)

    result = await delivery.create_approval_message(
        action_id=UUID("12345678-1234-4234-8234-123456789abc"),
        approval_message_id=UUID("aaaaaaaa-1234-4234-8234-123456789abc"),
        content="Synthetic approval.",
        attachment_name="synthetic.txt",
        attachment_media_type="text/plain; charset=utf-8",
        attachment_content=b"synthetic",
    )

    assert result == DeliverySucceeded("654321", 1)
    assert discord.calls == 1
    assert artifacts.discord_message_ids == {"654321"}


@pytest.mark.asyncio
async def test_direct_cleanup_is_limited_to_automatic_gmail_drafts() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-token"
        return httpx.Response(204, request=request)

    artifacts = _Artifacts()
    artifacts.gmail_draft_ids.update({"draft/b", "draft/a"})
    tokens = _Tokens()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        trust_env=False,
    ) as client:
        await _delete_drafts(
            client,
            cast("Any", tokens),
            artifacts,
        )

    assert tokens.calls == 2
    assert [request.method for request in requests] == ["DELETE"] * 2
    assert [request.url.path for request in requests] == [
        "/gmail/v1/users/me/drafts/draft/a",
        "/gmail/v1/users/me/drafts/draft/b",
    ]


@pytest.mark.asyncio
async def test_draft_cleanup_attempts_every_target_after_one_failure() -> None:
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        status = 500 if request.url.path.endswith("draft/a") else 204
        return httpx.Response(status, request=request)

    artifacts = _Artifacts()
    artifacts.gmail_draft_ids.update({"draft/b", "draft/a"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        trust_env=False,
    ) as client:
        with pytest.raises(_QualificationFailure) as raised:
            await _delete_drafts(client, cast("Any", _Tokens()), artifacts)

    assert requests == [
        "/gmail/v1/users/me/drafts/draft/a",
        "/gmail/v1/users/me/drafts/draft/b",
    ]
    assert raised.value.reason_code == "gmail_draft_cleanup_failed"


@pytest.mark.asyncio
async def test_sent_cleanup_requires_provider_disappearance() -> None:
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(404, request=request)

    artifacts = _Artifacts()
    artifacts.gmail_sent_message_ids.update({"sent/b", "sent/a"})
    artifacts.gmail_sent_thread_ids.update({"thread/b", "thread/a"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        trust_env=False,
    ) as client:
        await _wait_for_sent_cleanup(
            client,
            cast("Any", _Tokens()),
            artifacts,
            0.0,
        )

    assert requested == [
        "/gmail/v1/users/me/messages/sent/a",
        "/gmail/v1/users/me/messages/sent/b",
        "/gmail/v1/users/me/threads/thread/a",
        "/gmail/v1/users/me/threads/thread/b",
    ]


@pytest.mark.asyncio
async def test_cleanup_does_not_accept_a_remaining_known_thread() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "synthetic-thread"},
            request=request,
        )

    artifacts = _Artifacts()
    artifacts.gmail_sent_thread_ids.add("synthetic-thread")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        trust_env=False,
    ) as client:
        with pytest.raises(_QualificationFailure) as raised:
            await _wait_for_sent_cleanup(
                client,
                cast("Any", _Tokens()),
                artifacts,
                0.0,
            )

    assert raised.value.reason_code == "manual_gmail_cleanup_timeout"


@pytest.mark.asyncio
async def test_failure_cleanup_requires_real_approved_calendar_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 9, 7, 12, tzinfo=UTC)
    snapshot = CalendarEventSnapshot(
        calendar_id="shared@example.invalid",
        event_id="synthetic-event",
        etag='"synthetic-etag"',
        status="confirmed",
        writable=CalendarWritableEvent(
            summary="Synthetic cleanup event",
            description=None,
            location=None,
            start=TimedEventTime(date_time=now, time_zone="UTC"),
            end=TimedEventTime(
                date_time=now + timedelta(minutes=15),
                time_zone="UTC",
            ),
            recurrence=(),
            attendees=(),
            use_default_reminders=True,
            reminders=(),
        ),
        organizer=Mailbox(name=None, address="owner@example.invalid"),
        updated_at=now,
    )
    persisted: list[dict[str, object]] = []
    terminal: list[tuple[object, ...]] = []

    async def persist(**values: object) -> UUID:
        persisted.append(values)
        return UUID("12345678-1234-4234-8234-123456789abc")

    async def require_terminal(*values: object) -> dict[str, object]:
        terminal.append(values)
        return {"type": "Success", "value": {}}

    globals_ = _cleanup_calendar_with_approvals.__globals__
    monkeypatch.setitem(globals_, "_persist_approval", persist)
    monkeypatch.setitem(globals_, "_require_terminal", require_terminal)

    class GoogleWrite:
        snapshot_calls = 0
        reconcile_calls = 0

        async def calendar_current_snapshot(
            self, calendar_id: str, event_id: str
        ) -> object:
            self.snapshot_calls += 1
            assert (calendar_id, event_id) == (
                "shared@example.invalid",
                "synthetic-event",
            )
            return SimpleNamespace(outcome="found", value=snapshot)

        async def reconcile_calendar_delete(self, value: object) -> object:
            self.reconcile_calls += 1
            assert cast("CalendarDeleteEventInput", value).expected == snapshot
            return SimpleNamespace(outcome="succeeded")

    class Session:
        def __init__(self) -> None:
            self.delivered: list[UUID] = []
            self.waited: list[tuple[UUID, ApprovalComponentDecision]] = []
            self.flushed = 0

        async def deliver(self, action_id: UUID) -> None:
            self.delivered.append(action_id)

        async def wait(
            self,
            action_id: UUID,
            decision: ApprovalComponentDecision,
        ) -> object:
            self.waited.append((action_id, decision))
            return SimpleNamespace(completed_in_handler=True)

        async def flush(self) -> None:
            self.flushed += 1

    google = GoogleWrite()
    session = Session()
    actions = object()
    artifacts = _Artifacts()
    artifacts.calendar_event_ids.add("synthetic-event")

    await _cleanup_calendar_with_approvals(
        actions=cast("Any", actions),
        messages=cast("Any", object()),
        composition=cast("Any", SimpleNamespace(google_write=google)),
        plan=object(),
        session=cast("Any", session),
        discord=cast("Any", object()),
        artifacts=artifacts,
        calendar_id="shared@example.invalid",
        conversation_id="synthetic-conversation",
    )

    action_id = UUID("12345678-1234-4234-8234-123456789abc")
    assert len(persisted) == 1
    assert str(persisted[0]["tool_id"]) == "calendar.delete_event"
    assert session.delivered == [action_id]
    assert session.waited == [(action_id, ApprovalComponentDecision.APPROVE)]
    assert terminal == [(actions, action_id, "succeeded")]
    assert google.snapshot_calls == 1
    assert google.reconcile_calls == 1
    assert session.flushed == 1
    assert not artifacts.calendar_event_ids


@pytest.mark.asyncio
async def test_recipient_copy_check_rejects_duplicate_inbox_delivery() -> None:
    result = GmailSendDraftSuccess(
        sent_message_id="sent-message",
        thread_id="known-thread",
        jarvis_effect_id="a" * 64,
        content_digest="b" * 64,
        sent_at=datetime(2026, 9, 7, 12, tzinfo=UTC),
    )

    def one_copy(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "messages": [
                    {"id": "one", "labelIds": ["INBOX", "SENT"]},
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(one_copy), trust_env=False
    ) as client:
        await _verify_one_recipient_copy(
            client,
            cast("Any", _Tokens()),
            result,
        )

    def duplicate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "messages": [
                    {"id": "one", "labelIds": ["INBOX", "SENT"]},
                    {"id": "two", "labelIds": ["INBOX"]},
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(duplicate), trust_env=False
    ) as client:
        with pytest.raises(_QualificationFailure) as raised:
            await _verify_one_recipient_copy(
                client,
                cast("Any", _Tokens()),
                result,
            )

    assert raised.value.reason_code == "recipient_copy_count_changed"


@pytest.mark.asyncio
async def test_discord_cleanup_removes_all_recorded_host_messages() -> None:
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        assert request.headers["authorization"] == "Bot synthetic-bot-token"
        status = 204 if request.url.path.endswith("/101") else 404
        return httpx.Response(status, request=request)

    artifacts = _Artifacts()
    artifacts.discord_message_ids.update({"102", "101"})
    settings = SimpleNamespace(
        discord=SimpleNamespace(
            bot_token=SecretStr("synthetic-bot-token"),
            channel_id=3,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), trust_env=False
    ) as client:
        await _cleanup_discord(client, cast("Any", settings), artifacts)

    assert requested == [
        "/api/v10/channels/3/messages/101",
        "/api/v10/channels/3/messages/102",
    ]


@pytest.mark.asyncio
async def test_discord_cleanup_attempts_every_target_after_transport_failure() -> None:
    requested: list[str] = []
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("/101"):
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(204, request=request)

    artifacts = _Artifacts()
    artifacts.discord_message_ids.update({"102", "101"})
    settings = SimpleNamespace(
        discord=SimpleNamespace(
            bot_token=SecretStr("synthetic-bot-token"),
            channel_id=3,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), trust_env=False
    ) as client:
        with pytest.raises(_QualificationFailure) as raised:
            await _cleanup_discord(
                client,
                cast("Any", settings),
                artifacts,
                sleep=record_sleep,
            )

    assert requested == [
        "/api/v10/channels/3/messages/101",
        "/api/v10/channels/3/messages/101",
        "/api/v10/channels/3/messages/101",
        "/api/v10/channels/3/messages/102",
    ]
    assert sleeps == [1.0, 1.0]
    assert raised.value.reason_code == "discord_cleanup_failed"


@pytest.mark.asyncio
async def test_discord_cleanup_honors_bounded_429_and_transient_delays() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.25"},
                request=request,
            )
        if attempts == 2:
            return httpx.Response(503, request=request)
        return httpx.Response(204, request=request)

    artifacts = _Artifacts()
    artifacts.discord_message_ids.add("101")
    settings = SimpleNamespace(
        discord=SimpleNamespace(
            bot_token=SecretStr("synthetic-bot-token"),
            channel_id=3,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), trust_env=False
    ) as client:
        await _cleanup_discord(
            client,
            cast("Any", settings),
            artifacts,
            sleep=record_sleep,
        )

    assert attempts == 3
    assert sleeps == [0.25, 1.0]


@pytest.mark.asyncio
async def test_discord_cleanup_429_exhaustion_is_exact_and_bounded() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            429,
            json={"retry_after": 0.5},
            request=request,
        )

    artifacts = _Artifacts()
    artifacts.discord_message_ids.add("101")
    settings = SimpleNamespace(
        discord=SimpleNamespace(
            bot_token=SecretStr("synthetic-bot-token"),
            channel_id=3,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), trust_env=False
    ) as client:
        with pytest.raises(_QualificationFailure) as raised:
            await _cleanup_discord(
                client,
                cast("Any", settings),
                artifacts,
                sleep=record_sleep,
            )

    assert attempts == 3
    assert sleeps == [0.5, 0.5]
    assert raised.value.reason_code == "discord_cleanup_failed"


def test_result_gate_and_sanitizer_reject_incomplete_or_private_evidence() -> None:
    evidence = _evidence()
    validate_result_evidence(evidence)
    assert_sanitized_output(evidence, ("synthetic-secret", "external-id"))

    for section, key in (
        ("gmail", "draft_mismatch_sent_nothing"),
        ("calendar", "denied_actions_had_no_effect"),
        ("cleanup", "gmail_sent"),
    ):
        changed = copy.deepcopy(evidence)
        cast("dict[str, object]", changed[section])[key] = False
        with pytest.raises(_QualificationFailure):
            validate_result_evidence(changed)

    with pytest.raises(_QualificationFailure) as raised:
        assert_sanitized_output(
            {"status": "passed", "value": "external-id"},
            ("synthetic-secret", "external-id"),
        )
    assert raised.value.reason_code == "private_value_exposed"


def test_disabled_main_emits_only_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in tuple(_environment()):
        monkeypatch.delenv(name, raising=False)

    assert main() == 1

    assert json.loads(capsys.readouterr().out) == {
        "failure": {
            "reason_code": "unexpected_exception",
            "stage": "setup",
            "type": "ValueError",
        },
        "status": "failed",
    }

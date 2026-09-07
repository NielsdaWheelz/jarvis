from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from llm_agent_kernel import CancellationToken
from llm_tools import (
    CapabilityProfile,
    EffectId,
    ExecutionContext,
    HostTable,
    InvocationPosition,
    ParsedJson,
    Principal,
    ProfileId,
    ReplayPolicy,
    Reservation,
    RunLimits,
    Scope,
    ToolCatalog,
    ToolExecutor,
    ToolGrant,
    ToolPlan,
    canonical_json_bytes,
    raw_input_digest,
)
from llm_tools.testing import (
    InMemoryBudgetState,
    InMemoryPositionRecorder,
    RecordingTelemetry,
)

from jarvis.read_tools import ConnectorFailure
from jarvis.write_connectors import GoogleWriteConnector, gmail_content_digest
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailUpdateDraftInput,
    Mailbox,
    Reminder,
    TimedEventTime,
    WriteAttemptBudget,
    WriteConnectorFailure,
    calendar_write_family,
)

ACTION_ID = UUID("12345678-1234-4234-8234-123456789abc")
UPDATE_ACTION_ID = UUID("22345678-1234-4234-8234-123456789abc")
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


class _Tokens:
    async def access_token(self) -> tuple[str, int]:
        return "host-token", 0

    def invalidate_access_token(self) -> None:
        pass


class _FailingRefresh:
    def __init__(self) -> None:
        self.calls = 0

    async def access_token(self) -> tuple[str, int]:
        self.calls += 1
        raise ConnectorFailure("provider_unavailable", attempts=1)

    def invalidate_access_token(self) -> None:
        pass


async def _stage_basis(
    *,
    action_id: UUID,
    draft_id: str,
    thread_id: str,
    jarvis_effect_id: str,
    old_content_digest: str,
) -> object:
    del action_id, draft_id, thread_id, jarvis_effect_id, old_content_digest
    return None


def _content(*, subject: str = "Synthetic") -> GmailContent:
    return GmailContent(
        to=(Mailbox(name="Owner", address="owner@example.invalid"),),
        cc=(),
        bcc=(),
        subject=subject,
        body_text="Synthetic body",
        reply_to=None,
    )


def _event() -> CalendarWritableEvent:
    return CalendarWritableEvent(
        summary="Synthetic event",
        description=None,
        location=None,
        start=TimedEventTime(date_time=NOW, time_zone="UTC"),
        end=TimedEventTime(
            date_time=datetime(2026, 9, 6, 13, tzinfo=UTC),
            time_zone="UTC",
        ),
        recurrence=(),
        attendees=(),
        use_default_reminders=False,
        reminders=(Reminder(method="popup", minutes=10),),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempt_budget", "expected_staged"),
    (
        (WriteAttemptBudget(0, 2), 1),
        (WriteAttemptBudget(1, 1), 2),
    ),
)
async def test_mutation_stages_lifetime_attempt_before_provider_request(
    attempt_budget: WriteAttemptBudget,
    expected_staged: int,
) -> None:
    timeline: list[tuple[str, object]] = []

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        assert action_id == ACTION_ID
        timeline.append(("stage", actual_external_attempts))
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        timeline.append(("request", request.method))
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {"id": "message", "threadId": "thread"},
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage_basis,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
        )
        result = await connector.gmail_create_draft(
            GmailCreateDraftInput(content=_content()),
            ACTION_ID,
            attempt_budget,
        )

    assert timeline == [("stage", expected_staged), ("request", "POST")]
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_gmail_update_stages_each_preflight_and_mutation_attempt() -> None:
    initial = _content()
    replacement = _content(subject="Replacement")
    raw = ""
    timeline: list[tuple[str, object]] = []

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        timeline.append(("stage", (action_id, actual_external_attempts)))
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal raw
        timeline.append(("request", request.method))
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw = cast("str", cast("dict[str, Any]", body["message"])["raw"])
        if request.method == "GET":
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
        return httpx.Response(
            200,
            json={
                "id": "draft",
                "message": {"id": "message", "threadId": "thread"},
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", _Tokens()),
            stage_gmail_update_basis=_stage_basis,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=initial),
            ACTION_ID,
            WriteAttemptBudget(0, 2),
        )
        timeline.clear()
        result = await connector.gmail_update_draft(
            GmailUpdateDraftInput(
                draft_id="draft",
                expected_content_digest=gmail_content_digest(initial),
                replacement=replacement,
            ),
            UPDATE_ACTION_ID,
            WriteAttemptBudget(0, 2),
        )

    assert timeline == [
        ("stage", (UPDATE_ACTION_ID, 1)),
        ("request", "GET"),
        ("stage", (UPDATE_ACTION_ID, 2)),
        ("request", "PUT"),
    ]
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_recovered_entry_exhausts_remaining_before_mutation() -> None:
    initial = _content()
    raw = ""
    methods: list[str] = []
    staged: list[int] = []

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        assert action_id in {ACTION_ID, UPDATE_ACTION_ID}
        staged.append(actual_external_attempts)
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal raw
        methods.append(request.method)
        if request.method == "POST":
            body = cast("dict[str, Any]", json.loads(await request.aread()))
            raw = cast("str", cast("dict[str, Any]", body["message"])["raw"])
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
            stage_gmail_update_basis=_stage_basis,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
        )
        await connector.gmail_create_draft(
            GmailCreateDraftInput(content=initial),
            ACTION_ID,
            WriteAttemptBudget(0, 2),
        )
        methods.clear()
        staged.clear()
        with pytest.raises(WriteConnectorFailure) as raised:
            await connector.gmail_update_draft(
                GmailUpdateDraftInput(
                    draft_id="draft",
                    expected_content_digest=gmail_content_digest(initial),
                    replacement=_content(subject="Replacement"),
                ),
                UPDATE_ACTION_ID,
                WriteAttemptBudget(1, 1),
            )

    assert raised.value.code == "provider_unavailable"
    assert raised.value.attempts == 1
    assert methods == ["GET"]
    assert staged == [2]


@pytest.mark.asyncio
async def test_refresh_failure_is_staged_and_declared_with_local_count() -> None:
    staged: list[tuple[UUID, int]] = []
    requests: list[httpx.Request] = []

    async def stage_attempts(
        *, action_id: UUID, actual_external_attempts: int
    ) -> object:
        staged.append((action_id, actual_external_attempts))
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("refresh failure must precede the provider request")

    tokens = _FailingRefresh()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        connector = GoogleWriteConnector(
            client=client,
            tokens=cast("Any", tokens),
            stage_gmail_update_basis=_stage_basis,
            stage_external_attempts=stage_attempts,
            now=lambda: NOW,
        )
        family = calendar_write_family(connector)
        binding = family.bindings[0]
        catalog = ToolCatalog.compose((family,))
        run_limits = RunLimits(1, 2, 262_144, 131_072, 1, 20.0)
        profile = CapabilityProfile(
            ProfileId("write_attempt_test"),
            (ToolGrant(binding.spec.id, None),),
            run_limits,
        ).freeze(catalog)
        plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
        budgets = InMemoryBudgetState(run_limits)
        recorder = InMemoryPositionRecorder(durable=True)
        position = InvocationPosition(str(ACTION_ID))
        value = CalendarCreateEventInput(
            calendar_id="owner@example.invalid",
            event=_event(),
            notify_attendees=False,
        )
        raw_value = cast("dict[str, object]", value.model_dump(mode="json"))
        raw_input = ParsedJson(raw_value)
        reservation = Reservation(
            calls=1,
            input_bytes=len(
                canonical_json_bytes({"type": "ParsedJson", "value": raw_value})
            ),
            max_attempts=binding.spec.limits.max_attempts,
            max_output_bytes=binding.spec.limits.max_output_bytes,
        )
        await recorder.occupy(
            position=position,
            tool_id=binding.spec.id,
            tool_contract_revision=binding.spec.tool_contract_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
            input_digest=raw_input_digest(raw_input),
            replay_policy=ReplayPolicy.ReDispatchable,
        )
        assert await recorder.reserve(
            position=position,
            budgets=budgets,
            reservation=reservation,
        )
        await recorder.dispatch_started(
            position=position,
            replay_policy=ReplayPolicy.ReDispatchable,
        )
        await recorder.dispatch_abandoned(
            position=position,
            replay_policy=ReplayPolicy.ReDispatchable,
            actual_attempts=1,
            lease_recovered=True,
        )
        result = await ToolExecutor.execute(
            binding,
            raw_input,
            ExecutionContext(
                plan=plan,
                grant=plan.grant(binding.spec.id),
                catalog_view=plan.catalog_view,
                position=position,
                recorder=recorder,
                effect_id=EffectId(str(ACTION_ID)),
                budgets=budgets,
                principal=Principal("owner"),
                scope=Scope("synthetic"),
                cancellation=CancellationToken(),
                telemetry=RecordingTelemetry(),
            ),
        )

    assert result == {
        "type": "Failure",
        "error": {"type": "ProviderUnavailable"},
    }
    assert tokens.calls == 1
    assert requests == []
    assert staged == [(ACTION_ID, 2)]
    settlement = recorder.record(position).settlement
    assert settlement is not None
    assert settlement.actual_attempts == 2
    assert budgets.actual_external_attempts == 2

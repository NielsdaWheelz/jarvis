from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from llm_agent_kernel import (
    CancellationToken,
    ProviderUsage,
    RunId,
    RunMetrics,
    ThreadNoWork,
)
from llm_tools import (
    CapabilityProfile,
    FrozenToolPlan,
    HostTable,
    ProfileId,
    ReplayPolicy,
    Reservation,
    RunLimits,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolId,
    ToolPlan,
    canonical_json_bytes,
    raw_input_digest,
)
from llm_tools import (
    Settlement as ToolSettlement,
)
from llm_tools.execution import ParsedJson
from llm_tools.testing import InMemoryBudgetState
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    ScheduleStateChanged,
    StoredAction,
)
from jarvis.config import DiscordSettings
from jarvis.db import action, create_engine, message
from jarvis.discord import DeliverySucceeded
from jarvis.messages import (
    MessageStore,
    PersistenceDefect,
    SettlementTrace,
    StoredMessage,
)
from jarvis.proactivity import ProcessLocalWakeTimer
from jarvis.schedule_tools import schedule_family
from jarvis.service import IngressStore, JarvisService, ThreadRunner
from jarvis.settings import Settings
from jarvis.state import PausedState
from jarvis.write_dispatch import ActionRecovery

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
postgres = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://jarvis:secret@db/jarvis"),
        discord=DiscordSettings(
            bot_token=SecretStr("synthetic-token"),
            owner_user_id=11,
            guild_id=22,
            channel_id=33,
        ),
        owner_timezone="America/Los_Angeles",
        codex_profile_key="personal",
        codex_model="gpt-5.6-terra",
        agent_cli_path=tmp_path / "skid",
        agent_client_config_path=tmp_path / "agent-client.json",
        codex_host_config_path=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
        google_oauth_state_path=tmp_path / "google.json",
        google_oauth_client_id=SecretStr("synthetic-google-client"),
        google_oauth_client_secret=SecretStr("synthetic-google-secret"),
        verified_owner_only_calendar_ids=("primary",),
        connector_encryption_key_version="v1",
        connector_encryption_keys=SecretStr("synthetic-keyring"),
        connector_encryption_secret=SecretStr("synthetic-encryption"),
        maps_api_key=SecretStr("synthetic-maps-key"),
        brave_api_key=SecretStr("synthetic-brave-key"),
        embedding_openai_api_key=SecretStr("synthetic-embedding-key"),
    )


class _Ingress:
    async def pending_delivery(self, **_kwargs: object) -> tuple[StoredMessage, ...]:
        return ()

    async def pending_controls(self, **_kwargs: object) -> tuple[()]:
        return ()

    async def circuit_is_open(self) -> bool:
        return False


class _Delivery:
    def __init__(self) -> None:
        self.calls = 0

    async def create_message(self, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("unexpected Discord delivery")


class _Gateway:
    @asynccontextmanager
    async def typing(self):  # type: ignore[no-untyped-def]
        yield


class _Runner:
    def __init__(self) -> None:
        self.calls = 0
        self.called = asyncio.Event()

    async def run(self, cancellation: CancellationToken) -> ThreadNoWork:
        assert not cancellation.cancelled
        self.calls += 1
        self.called.set()
        return ThreadNoWork(
            RunMetrics(RunId("scheduled-test"), 0, ProviderUsage(), 0.0, False)
        )

    async def settle_control(self, *_args: object, **_kwargs: object) -> bool:
        raise AssertionError("control settlement was not expected")

    async def discard_recovered_session_reference(self) -> None:
        raise AssertionError("session recovery was not expected")


class _InspectableService(JarvisService):
    async def drain_once(self) -> None:
        await self._drain()


class _ScheduleSource:
    def __init__(self, due_at: datetime | None) -> None:
        self.due_at = due_at
        self.read = asyncio.Event()
        self.claimed = asyncio.Event()
        self.claims = 0

    async def next_due_at(self) -> datetime | None:
        self.read.set()
        return self.due_at

    async def claim_next_due_schedule(self, **_kwargs: object) -> object | None:
        if self.due_at is None or self.due_at > datetime.now(UTC):
            return None
        self.claims += 1
        self.due_at = None
        self.claimed.set()
        return object()


class _BlockedSleep:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.delay: float | None = None

    async def __call__(self, delay: float) -> None:
        self.delay = delay
        self.started.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class _FailingWakeTimer:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, cancellation: CancellationToken) -> None:
        assert not cancellation.cancelled
        self.calls += 1
        raise RuntimeError("synthetic wake timer failure")

    def notify_changed(self) -> None:
        raise AssertionError("failed wake timer cannot be notified")


def _service(
    tmp_path: Path,
    schedules: _ScheduleSource,
    runner: _Runner,
    delivery: _Delivery,
    timer: ProcessLocalWakeTimer,
    *,
    store: IngressStore | None = None,
    action_recovery: Any | None = None,
) -> _InspectableService:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    catalog = ToolCatalog.compose((schedule_family(cast(Any, schedules)),))
    binding = catalog.binding(ToolId("schedule.wake"))
    profile = CapabilityProfile(
        ProfileId("synthetic_service_schedule"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=store or cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=cast(Any, delivery),
        runner=cast(ThreadRunner, runner),
        scheduled_wakes=cast(Any, schedules),
        action_plan=plan,
        action_recovery=action_recovery,
        gateway=cast(Any, _Gateway()),
    )
    service.bind_wake_timer(timer)
    return service


async def test_wake_timer_failure_fails_the_service_worker(tmp_path: Path) -> None:
    schedules = _ScheduleSource(None)
    runner = _Runner()
    delivery = _Delivery()
    timer = _FailingWakeTimer()
    service = _service(
        tmp_path,
        schedules,
        runner,
        delivery,
        cast("Any", timer),
    )

    with pytest.raises(RuntimeError, match="synthetic wake timer failure"):
        await asyncio.wait_for(service.run_worker(), timeout=1)

    assert timer.calls == 1
    assert runner.calls == 0
    assert delivery.calls == 0


class _ChangedScheduleSource(_ScheduleSource):
    def __init__(self, due_at: datetime) -> None:
        super().__init__(due_at)
        self.changed = ScheduleStateChanged(cast(Any, object()))

    async def claim_next_due_schedule(self, **_kwargs: object) -> object | None:
        if self.due_at is None:
            return None
        self.claims += 1
        self.due_at = None
        return self.changed


class _ResolutionIngress(_Ingress):
    def __init__(self) -> None:
        self.pending: list[StoredMessage] = []
        self.delivered: list[UUID] = []

    async def pending_delivery(self, **_kwargs: object) -> tuple[StoredMessage, ...]:
        return tuple(self.pending)

    async def mark_delivered(self, *, message_id: UUID, source_message_id: str) -> None:
        assert source_message_id == "synthetic-discord-resolution"
        assert self.pending[0].id == message_id
        self.pending.pop(0)
        self.delivered.append(message_id)


class _StateChangeRecovery:
    def __init__(self, store: _ResolutionIngress) -> None:
        self.store = store
        self.modes: list[bool] = []
        self.resolution_id = uuid4()

    async def recover(self, *, allow_queued_execution: bool = True) -> int:
        self.modes.append(allow_queued_execution)
        if (
            not allow_queued_execution
            and not self.store.pending
            and not self.store.delivered
        ):
            self.store.pending.append(
                StoredMessage(
                    id=self.resolution_id,
                    role="assistant",
                    text="Synthetic incompatible schedule resolution.",
                    source="discord",
                    source_conversation_id="33",
                    source_message_id=None,
                    created_at=datetime.now(UTC),
                    processed_at=datetime.now(UTC),
                    processing_attempts=0,
                    processing_parked_at=None,
                    remembered_at=None,
                    trace={},
                )
            )
            return 1
        return 0


class _ResolutionDelivery(_Delivery):
    async def create_message(self, **_kwargs: object) -> object:
        self.calls += 1
        return DeliverySucceeded("synthetic-discord-resolution", 1)


class _NotifyTimer:
    def __init__(self) -> None:
        self.notifications = 0

    def notify_changed(self) -> None:
        self.notifications += 1


async def test_stale_due_state_is_recovered_delivered_and_reloads_timer(
    tmp_path: Path,
) -> None:
    schedules = _ChangedScheduleSource(datetime.now(UTC))
    runner = _Runner()
    delivery = _ResolutionDelivery()
    store = _ResolutionIngress()
    recovery = _StateChangeRecovery(store)
    timer = _NotifyTimer()
    service = _service(
        tmp_path,
        schedules,
        runner,
        delivery,
        cast("Any", timer),
        store=cast(IngressStore, store),
        action_recovery=recovery,
    )

    await service.drain_once()
    await service.drain_once()

    assert schedules.claims == 1
    assert timer.notifications == 1
    assert recovery.modes[:3] == [True, False, True]
    assert recovery.modes.count(False) == 1
    assert store.delivered == [recovery.resolution_id]
    assert delivery.calls == 1


async def test_service_does_not_run_for_a_not_yet_due_wake(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    schedules = _ScheduleSource(now + timedelta(hours=1))
    sleep = _BlockedSleep()
    runner = _Runner()
    delivery = _Delivery()
    timer = ProcessLocalWakeTimer(
        store=schedules,
        on_due=lambda: None,
        clock=lambda: now,
        sleep=sleep,
    )
    service = _service(tmp_path, schedules, runner, delivery, timer)

    worker = asyncio.create_task(service.run_worker())
    await asyncio.wait_for(sleep.started.wait(), timeout=1)
    assert sleep.delay == 3_600
    assert runner.calls == 0
    assert schedules.claims == 0
    assert delivery.calls == 0

    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)
    assert sleep.cancelled.is_set()


async def test_timer_reschedule_preempts_sleep_and_arms_service(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    schedules = _ScheduleSource(now + timedelta(hours=1))
    sleep = _BlockedSleep()
    runner = _Runner()
    delivery = _Delivery()
    service: JarvisService | None = None
    timer = ProcessLocalWakeTimer(
        store=schedules,
        on_due=lambda: cast(JarvisService, service).request_work(),
        clock=lambda: now,
        sleep=sleep,
    )
    service = _service(tmp_path, schedules, runner, delivery, timer)

    worker = asyncio.create_task(service.run_worker())
    await asyncio.wait_for(sleep.started.wait(), timeout=1)
    schedules.due_at = now
    timer.notify_changed()
    await asyncio.wait_for(schedules.claimed.wait(), timeout=1)
    await asyncio.wait_for(runner.called.wait(), timeout=1)

    assert sleep.cancelled.is_set()
    assert schedules.claims == 1
    assert runner.calls == 1
    assert delivery.calls == 0
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)


async def test_overdue_restart_immediately_arms_service(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    schedules = _ScheduleSource(now - timedelta(minutes=5))
    runner = _Runner()
    delivery = _Delivery()
    service: JarvisService | None = None

    async def unexpected_sleep(_delay: float) -> None:
        raise AssertionError("an overdue wake must not sleep")

    timer = ProcessLocalWakeTimer(
        store=schedules,
        on_due=lambda: cast(JarvisService, service).request_work(),
        clock=lambda: now,
        sleep=unexpected_sleep,
    )
    service = _service(tmp_path, schedules, runner, delivery, timer)

    worker = asyncio.create_task(service.run_worker())
    await asyncio.wait_for(schedules.claimed.wait(), timeout=1)
    await asyncio.wait_for(runner.called.wait(), timeout=1)

    assert schedules.claims == 1
    assert runner.calls == 1
    assert delivery.calls == 0
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)


async def _schedule(
    engine: AsyncEngine,
    *,
    due_at: datetime,
    conversation_id: str,
) -> tuple[ActionStore, StoredAction, UUID, FrozenToolPlan]:
    messages = MessageStore(engine)
    origin = await messages.insert_waking(
        role="owner",
        text="Create the synthetic reminder.",
        source="discord",
        source_conversation_id=conversation_id,
        source_message_id=str(uuid4()),
        created_at=due_at - timedelta(minutes=1),
    )
    arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": due_at.isoformat(),
            "instruction": "Synthetic reminder",
        }
    }
    actions = ActionStore(engine)
    family = schedule_family(actions)
    catalog = ToolCatalog.compose((family,))
    binding = catalog.binding(ToolId("schedule.wake"))
    profile = CapabilityProfile(
        ProfileId(f"schedule_runtime_{origin.message.id}"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    contract = ExecutionContract(
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
        tool_effect=ToolEffect.Write,
        replay_policy=ReplayPolicy.ReDispatchable,
        input_digest=raw_input_digest(ParsedJson(arguments)),
        max_attempts=2,
        claim_id=str(uuid4()),
        through_checkpoint=str(origin.message.id),
        model_step_ordinal=1,
        input_message_ids=(str(origin.message.id),),
        write_gate_supporting_owner_message_ids=(str(origin.message.id),),
    )
    stored = await actions.insert_automatic(
        tool_name=ToolId("schedule.wake"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin.message.id,
        execute_after=due_at,
        created_at=due_at - timedelta(seconds=30),
    )
    recorder = ActionPositionRecorder(
        store=actions,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    budgets = InMemoryBudgetState(
        RunLimits(
            max_calls=1,
            max_external_attempts=2,
            max_input_bytes=8_192,
            max_output_bytes=8_192,
            max_in_flight=1,
            max_elapsed_seconds=30.0,
        )
    )
    reservation = Reservation(
        calls=1,
        input_bytes=100,
        max_attempts=2,
        max_output_bytes=4_096,
    )
    await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=reservation,
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    result: dict[str, object] = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "created",
                "action_id": str(stored.id),
                "execute_after": due_at.isoformat(),
                "arguments_digest": contract.input_digest,
                "recorded_at": (due_at - timedelta(seconds=20)).isoformat(),
            }
        },
    }
    await recorder.terminalize_and_settle(
        position=stored.position,
        budgets=budgets,
        result=result,
        settlement=ToolSettlement(
            actual_attempts=1,
            actual_output_bytes=len(canonical_json_bytes(result)),
        ),
    )
    queued = await actions.get(stored.id)
    assert queued is not None
    return actions, queued, origin.message.id, plan


def _schedule_plan(actions: ActionStore, profile_id: str) -> FrozenToolPlan:
    catalog = ToolCatalog.compose((schedule_family(actions),))
    binding = catalog.binding(ToolId("schedule.wake"))
    profile = CapabilityProfile(
        ProfileId(profile_id),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 30.0),
    ).freeze(catalog)
    return ToolPlan(profile.id, HostTable()).freeze(catalog, profile)


@postgres
async def test_exact_due_claim_creates_one_idempotent_host_wake(
    engine: AsyncEngine,
) -> None:
    due_at = datetime.now(UTC) + timedelta(minutes=5)
    conversation_id = f"schedule-exact-{uuid4()}"
    actions, stored, _origin_id, plan = await _schedule(
        engine,
        due_at=due_at,
        conversation_id=conversation_id,
    )

    first = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    second = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    assert first is not None
    assert second is not None

    assert first.action.status == "executing"
    assert first.message_inserted
    assert not second.message_inserted
    assert second.waking_message_id == first.waking_message_id
    async with engine.connect() as connection:
        count = await connection.scalar(
            select(func.count(message.c.id)).where(
                message.c.source == "schedule_wake",
                message.c.source_message_id == str(stored.id),
            )
        )
    assert count == 1
    await actions.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_test_cleanup",
            "recorded_at": (due_at + timedelta(seconds=1)).isoformat(),
        },
    )


@postgres
async def test_due_schedule_with_stale_plan_fails_and_reports_without_waking(
    engine: AsyncEngine,
) -> None:
    due_at = datetime.now(UTC)
    conversation_id = f"schedule-stale-queued-{uuid4()}"
    actions, stored, origin_id, original_plan = await _schedule(
        engine,
        due_at=due_at,
        conversation_id=conversation_id,
    )
    current_plan = _schedule_plan(actions, f"changed_{stored.id}")
    assert current_plan.plan_revision != original_plan.plan_revision

    changed = await actions.claim_next_due_schedule(
        plan=current_plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    assert isinstance(changed, ScheduleStateChanged)
    assert changed.action.id == stored.id
    failed = await actions.get(stored.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.result is not None
    assert stored.result is not None
    assert failed.result["creation_receipt"] == stored.result["creation_receipt"]
    assert failed.result["wake_outcome"] == {
        "type": "failed",
        "reason_code": "incompatible_execution_contract",
        "recorded_at": due_at.isoformat(),
    }
    recovery = ActionRecovery(
        actions=actions,
        google_write=cast(Any, object()),
        plan=current_plan,
        source_conversation_id=conversation_id,
    )
    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    async with engine.connect() as connection:
        wakes = await connection.scalar(
            select(func.count(message.c.id)).where(
                message.c.source == "schedule_wake",
                message.c.source_message_id == str(stored.id),
            )
        )
        resolutions = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{stored.id}:failed",
                    )
                )
            )
            .mappings()
            .all()
        )
        processed_at = await connection.scalar(
            select(message.c.processed_at).where(message.c.id == origin_id)
        )
    assert wakes == 0
    assert len(resolutions) == 1
    assert processed_at is not None


@postgres
async def test_executing_schedule_with_stale_plan_gets_atomic_visible_fallback(
    engine: AsyncEngine,
) -> None:
    due_at = datetime.now(UTC)
    conversation_id = f"schedule-stale-executing-{uuid4()}"
    actions, stored, _origin_id, original_plan = await _schedule(
        engine,
        due_at=due_at,
        conversation_id=conversation_id,
    )
    claim = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=original_plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    assert claim is not None
    current_plan = _schedule_plan(actions, f"changed_{stored.id}")
    recovery = ActionRecovery(
        actions=actions,
        google_write=cast(Any, object()),
        plan=current_plan,
        source_conversation_id=conversation_id,
    )

    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    failed = await actions.get(stored.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.result is not None
    assert stored.result is not None
    assert failed.result["creation_receipt"] == stored.result["creation_receipt"]
    assert (
        cast("dict[str, object]", failed.result["wake_outcome"])["reason_code"]
        == "incompatible_execution_contract"
    )
    async with engine.connect() as connection:
        wake = (
            (
                await connection.execute(
                    select(message).where(message.c.id == claim.waking_message_id)
                )
            )
            .mappings()
            .one()
        )
        fallbacks = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.role == "assistant",
                        message.c.source == "discord",
                        message.c.source_conversation_id == conversation_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        resolutions = await connection.scalar(
            select(func.count(message.c.id)).where(
                message.c.source == "action",
                message.c.source_message_id == f"{stored.id}:failed",
            )
        )
    assert wake["processed_at"] is not None
    settlement = cast("dict[str, object]", wake["trace"])["settlement"]
    assert cast("dict[str, object]", settlement)["outcome"] == "host_fallback"
    assert len(fallbacks) == 1
    assert "was not run" in fallbacks[0]["text"]
    assert len(fallbacks[0]["text"]) <= 2_000
    assert resolutions == 0


@postgres
async def test_new_timer_observes_persisted_overdue_schedule(
    engine: AsyncEngine,
) -> None:
    now = datetime.now(UTC)
    actions, stored, _origin_id, plan = await _schedule(
        engine,
        due_at=now - timedelta(minutes=5),
        conversation_id=f"schedule-overdue-{uuid4()}",
    )
    cancellation = CancellationToken()
    notifications: list[datetime] = []

    def due() -> None:
        notifications.append(now)
        cancellation.cancel()

    await ProcessLocalWakeTimer(
        store=actions,
        on_due=due,
        clock=lambda: now,
    ).run(cancellation)

    assert notifications == [now]
    claim = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id=f"overdue-{stored.id}",
        now=now,
    )
    assert claim is not None
    assert claim.message_inserted
    await actions.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_test_cleanup",
            "recorded_at": now.isoformat(),
        },
    )


@postgres
async def test_visible_settlement_atomically_finishes_schedule(
    engine: AsyncEngine,
) -> None:
    due_at = datetime.now(UTC)
    conversation_id = f"schedule-settlement-{uuid4()}"
    actions, stored, origin_id, plan = await _schedule(
        engine,
        due_at=due_at,
        conversation_id=conversation_id,
    )
    claim = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    assert claim is not None
    conclusion_id = uuid4()
    settled_at = due_at + timedelta(seconds=1)
    messages = MessageStore(engine)
    settlement = await messages.settle(
        consumed_message_ids=(claim.waking_message_id,),
        source_conversation_id=conversation_id,
        trace=SettlementTrace(
            run_id="scheduled-visible-run",
            through_checkpoint=str(claim.waking_message_id),
            conclusion_kind="conversation",
            outcome="answered",
        ),
        conclusion_text="Synthetic visible reminder.",
        conclusion_message_id=conclusion_id,
        settled_at=settled_at,
    )

    assert settlement.conclusion_message is not None
    assert settlement.conclusion_message.id == conclusion_id
    assert settlement.conclusion_message.text == "Synthetic visible reminder."
    finished = await actions.get(stored.id)
    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.result is not None
    assert finished.result["wake_outcome"] == {
        "type": "concluded",
        "conclusion_message_id": str(conclusion_id),
        "recorded_at": settled_at.isoformat(),
    }
    pending = await messages.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(item.id for item in pending) == (conclusion_id,)
    async with engine.connect() as connection:
        message_count = await connection.scalar(
            select(func.count(message.c.id)).where(
                message.c.source_conversation_id == conversation_id
            )
        )
        action_count = await connection.scalar(
            select(func.count(action.c.id)).where(
                action.c.origin_message_id == origin_id
            )
        )
    assert message_count == 3
    assert action_count == 1

    replay = await messages.settle(
        consumed_message_ids=(claim.waking_message_id,),
        source_conversation_id=conversation_id,
        trace=SettlementTrace(
            run_id="scheduled-visible-run",
            through_checkpoint=str(claim.waking_message_id),
            conclusion_kind="conversation",
            outcome="answered",
        ),
        conclusion_text="Synthetic visible reminder.",
        conclusion_message_id=conclusion_id,
        settled_at=settled_at,
    )
    assert replay.already_settled


@postgres
async def test_scheduled_wake_cannot_settle_silently(
    engine: AsyncEngine,
) -> None:
    due_at = datetime.now(UTC)
    conversation_id = f"schedule-visible-{uuid4()}"
    actions, stored, _origin_id, plan = await _schedule(
        engine,
        due_at=due_at,
        conversation_id=conversation_id,
    )
    claim = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    assert claim is not None
    messages = MessageStore(engine)

    with pytest.raises(PersistenceDefect, match="requires one visible conclusion"):
        await messages.settle(
            consumed_message_ids=(claim.waking_message_id,),
            source_conversation_id=conversation_id,
            trace=SettlementTrace(
                run_id="scheduled-silent-run",
                through_checkpoint=str(claim.waking_message_id),
                conclusion_kind="silent",
                outcome="silent",
            ),
            conclusion_text=None,
            settled_at=due_at + timedelta(seconds=1),
        )

    current = await actions.get(stored.id)
    assert current is not None
    assert current.status == "executing"
    async with engine.connect() as connection:
        processed_at = await connection.scalar(
            select(message.c.processed_at).where(
                message.c.id == claim.waking_message_id
            )
        )
    assert processed_at is None
    await actions.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_test_cleanup",
            "recorded_at": (due_at + timedelta(seconds=2)).isoformat(),
        },
    )


@postgres
async def test_schedule_settlement_failure_rolls_back_visible_message(
    engine: AsyncEngine,
) -> None:
    due_at = datetime.now(UTC)
    conversation_id = f"schedule-rollback-{uuid4()}"
    actions, stored, _origin_id, plan = await _schedule(
        engine,
        due_at=due_at,
        conversation_id=conversation_id,
    )
    claim = await actions.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id=conversation_id,
        now=due_at,
    )
    assert claim is not None
    failed_at = due_at + timedelta(seconds=1)
    await actions.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_prior_failure",
            "recorded_at": failed_at.isoformat(),
        },
    )
    conclusion_id = uuid4()
    messages = MessageStore(engine)

    with pytest.raises(ActionPersistenceDefect, match="outcome changed"):
        await messages.settle(
            consumed_message_ids=(claim.waking_message_id,),
            source_conversation_id=conversation_id,
            trace=SettlementTrace(
                run_id="scheduled-rollback-run",
                through_checkpoint=str(claim.waking_message_id),
                conclusion_kind="conversation",
                outcome="answered",
            ),
            conclusion_text="This insertion must roll back.",
            conclusion_message_id=conclusion_id,
            settled_at=failed_at + timedelta(seconds=1),
        )

    async with engine.connect() as connection:
        waking = (
            (
                await connection.execute(
                    select(message).where(message.c.id == claim.waking_message_id)
                )
            )
            .mappings()
            .one()
        )
        conclusion = await connection.scalar(
            select(message.c.id).where(message.c.id == conclusion_id)
        )
    assert waking["processed_at"] is None
    assert conclusion is None
    failed = await actions.get(stored.id)
    assert failed is not None
    assert failed.status == "failed"

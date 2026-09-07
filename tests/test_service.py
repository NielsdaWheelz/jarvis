from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from llm_agent_kernel import (
    CancellationToken,
    InitialReadDispatchLineage,
    ProviderUsage,
    RunId,
    RunMetrics,
    ThreadNoWork,
    ThreadStopKind,
    ThreadStopped,
    ToolDispatchDefect,
)
from pydantic import SecretStr

from jarvis.config import DiscordSettings
from jarvis.discord import (
    ApprovalComponentDecision,
    CatchUpResult,
    Control,
    DeliveryFailed,
    DeliveryFailureKind,
    DeliveryResult,
    DeliverySucceeded,
    DiscordApprovalInteraction,
    DiscordOwnerMessage,
)
from jarvis.messages import InboundInsert, PendingControl, StoredMessage
from jarvis.service import (
    BackgroundDeferred,
    CapturingReadDispatcher,
    IngressStore,
    JarvisService,
    ThreadRunner,
    flush_pending_deliveries,
)
from jarvis.settings import Settings
from jarvis.state import PausedState


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://jarvis:secret@db/jarvis"),
        discord=DiscordSettings(
            bot_token=SecretStr("private-token"),
            owner_user_id=11,
            guild_id=22,
            channel_id=33,
        ),
        owner_timezone="America/Los_Angeles",
        codex_profile_key="jarvis",
        codex_model="gpt-5.6-terra",
        codex_state_root=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
        google_oauth_state_path=tmp_path / "google.json",
        google_oauth_client_id=SecretStr("synthetic-google-client"),
        google_oauth_client_secret=SecretStr("synthetic-google-secret"),
        verified_owner_only_calendar_ids=("primary",),
        connector_encryption_key_version="v2",
        connector_encryption_keys=SecretStr("synthetic-keyring"),
        connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
        maps_api_key=SecretStr("synthetic-maps-key"),
        brave_api_key=SecretStr("synthetic-brave-key"),
        embedding_openai_api_key=SecretStr("synthetic-embedding-key"),
    )


def _stored(text: str, *, identifier: UUID | None = None) -> StoredMessage:
    return StoredMessage(
        id=identifier or uuid4(),
        role="assistant",
        text=text,
        source="discord",
        source_conversation_id="33",
        source_message_id=None,
        created_at=datetime(2026, 9, 3, 18, tzinfo=UTC),
        processed_at=datetime(2026, 9, 3, 18, tzinfo=UTC),
        processing_attempts=0,
        processing_parked_at=None,
        remembered_at=None,
        trace={},
    )


async def test_main_observation_capture_rejects_isolated_lineage() -> None:
    class Delegate:
        def __init__(self) -> None:
            self.called = False

        async def dispatch(self, **kwargs: object) -> object:
            del kwargs
            self.called = True
            raise AssertionError("isolated dispatch must be rejected before delegation")

    delegate = Delegate()
    dispatcher = CapturingReadDispatcher(cast(Any, delegate))
    with pytest.raises(ToolDispatchDefect, match="continuing-thread lineage"):
        await dispatcher.dispatch(
            binding=cast(Any, object()),
            validated_input=object(),
            plan=cast(Any, object()),
            budgets=cast(Any, object()),
            cancellation=CancellationToken(),
            lineage=InitialReadDispatchLineage(RunId("initial-read")),
        )
    assert not delegate.called


class _DeliveryStore:
    def __init__(self, messages: tuple[StoredMessage, ...]) -> None:
        self.messages = messages
        self.marked: list[tuple[UUID, str]] = []

    async def pending_delivery(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        assert source_conversation_id == "33"
        return self.messages[:limit]

    async def mark_delivered(
        self,
        *,
        message_id: UUID,
        source_message_id: str,
    ) -> None:
        self.marked.append((message_id, source_message_id))


class _Delivery:
    def __init__(self, results: list[DeliveryResult]) -> None:
        self.results = results
        self.seen: list[tuple[UUID | str, str]] = []

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult:
        self.seen.append((persisted_message_id, content))
        return self.results.pop(0)


async def test_delivery_flush_marks_successes_and_preserves_order() -> None:
    first = _stored("first")
    second = _stored("second")
    store = _DeliveryStore((first, second))
    delivery = _Delivery([DeliverySucceeded("101", 1), DeliverySucceeded("102", 1)])

    result = await flush_pending_deliveries(
        store=store,
        delivery=delivery,
        source_conversation_id="33",
        limit=20,
    )
    assert result.selected == 2
    assert result.delivered == 2
    assert result.failure is None
    assert delivery.seen == [(first.id, "first"), (second.id, "second")]
    assert store.marked == [(first.id, "101"), (second.id, "102")]


async def test_delivery_flush_stops_at_first_failure() -> None:
    first = _stored("first")
    second = _stored("second")
    store = _DeliveryStore((first, second))
    failure = DeliveryFailed(
        DeliveryFailureKind.TRANSPORT,
        attempts=3,
        retryable=True,
        ambiguous=True,
    )
    delivery = _Delivery([failure, DeliverySucceeded("102", 1)])

    result = await flush_pending_deliveries(
        store=store,
        delivery=delivery,
        source_conversation_id="33",
        limit=20,
    )
    assert result.failure is failure
    assert result.delivered == 0
    assert delivery.seen == [(first.id, "first")]
    assert store.marked == []


class _Ingress(_DeliveryStore):
    def __init__(self) -> None:
        super().__init__(())
        self.inserted: list[DiscordOwnerMessage] = []
        self.controls: list[PendingControl] = []
        self.cursor: str | None = "41"

    async def insert_waking(
        self,
        *,
        role: str,
        text: str,
        source: str,
        source_conversation_id: str,
        source_message_id: str,
        created_at: datetime,
        message_id: UUID | None = None,
    ) -> InboundInsert:
        del role, source, message_id
        incoming = DiscordOwnerMessage(
            source_message_id,
            source_conversation_id,
            text,
            created_at,
            Control(text.strip().casefold())
            if text.strip().casefold() in Control
            else None,
        )
        self.inserted.append(incoming)
        return InboundInsert(
            StoredMessage(
                id=uuid4(),
                role="owner",
                text=text,
                source="discord",
                source_conversation_id=source_conversation_id,
                source_message_id=source_message_id,
                created_at=created_at,
                processed_at=None,
                processing_attempts=0,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            ),
            inserted=True,
        )

    async def latest_discord_owner_source_message_id(
        self,
        *,
        source_conversation_id: str,
    ) -> str | None:
        assert source_conversation_id == "33"
        return self.cursor

    async def pending_controls(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[PendingControl, ...]:
        del source_conversation_id
        return tuple(self.controls[:limit])

    async def circuit_is_open(self) -> bool:
        return False


class _Runner:
    def __init__(self) -> None:
        self.settled: list[tuple[UUID, Control]] = []

    async def run(self, cancellation: CancellationToken) -> object:
        del cancellation
        raise AssertionError("model run was not expected")

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        self.settled.append((message_id, control))
        return True

    async def discard_recovered_session_reference(self) -> None:
        return None


class _PreClaimRunner:
    def __init__(self) -> None:
        self.before_claim = asyncio.Event()
        self.acquire_claim = asyncio.Event()
        self.claim_acquired = False
        self.cancellation_observed = False
        self.provider_turns = 0

    async def run(self, cancellation: CancellationToken) -> ThreadNoWork:
        self.before_claim.set()
        await self.acquire_claim.wait()
        self.claim_acquired = True
        self.cancellation_observed = cancellation.cancelled
        if not cancellation.cancelled:
            self.provider_turns += 1
        return ThreadNoWork(
            RunMetrics(
                RunId("pre-claim-race"),
                self.provider_turns,
                ProviderUsage(),
                0.0,
                False,
            )
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        del message_id, control
        raise AssertionError("control settlement was not expected")

    async def discard_recovered_session_reference(self) -> None:
        raise AssertionError("session-reference discard was not expected")


class _Gateway:
    def __init__(self) -> None:
        self.after: str | None = None

    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult:
        self.after = after_source_message_id
        return CatchUpResult(2, 1, False, "42")

    @asynccontextmanager
    async def typing(self):  # type: ignore[no-untyped-def]
        yield


class _InspectableService(JarvisService):
    async def drain_once(self) -> None:
        await self._drain()

    @asynccontextmanager
    async def hold_execution(self):  # type: ignore[no-untyped-def]
        async with self._execution_mutex:
            yield


class _ApprovalHandler:
    def __init__(self) -> None:
        self.claimed = asyncio.Event()
        self.completed = asyncio.Event()

    async def claim_and_acknowledge(self, event: object, interaction: object) -> object:
        del event, interaction
        self.claimed.set()
        return object()

    async def complete(
        self,
        claimed: object,
        cancellation: CancellationToken,
    ) -> bool:
        del claimed
        assert not cancellation.cancelled
        self.completed.set()
        return True


async def test_approval_acknowledgement_precedes_serial_effect_execution(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    handler = _ApprovalHandler()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _Runner()),
        approval_handler=cast("Any", handler),
        gateway=_Gateway(),
    )
    interaction = DiscordApprovalInteraction(
        action_id=uuid4(),
        approval_message_id=uuid4(),
        decision=ApprovalComponentDecision.APPROVE,
        discord_message_id="123",
    )

    async with service.hold_execution():
        task = asyncio.create_task(
            service.receive_approval_interaction(cast("Any", object()), interaction)
        )
        await asyncio.wait_for(handler.claimed.wait(), timeout=1)
        assert not handler.completed.is_set()

    await asyncio.wait_for(task, timeout=1)
    assert handler.completed.is_set()


class _CancellableApprovalHandler(_ApprovalHandler):
    def __init__(self) -> None:
        super().__init__()
        self.execution_started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancellation_observed = False

    async def complete(
        self,
        claimed: object,
        cancellation: CancellationToken,
    ) -> bool:
        del claimed
        self.execution_started.set()
        await self.release.wait()
        self.cancellation_observed = True
        assert cancellation.cancelled
        return False


async def test_pause_cancels_approved_action_before_external_entry(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    paused = PausedState(paused_path)
    handler = _CancellableApprovalHandler()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=paused,
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _Runner()),
        approval_handler=cast("Any", handler),
        gateway=_Gateway(),
    )
    approval = DiscordApprovalInteraction(
        action_id=uuid4(),
        approval_message_id=uuid4(),
        decision=ApprovalComponentDecision.APPROVE,
        discord_message_id="123",
    )
    task = asyncio.create_task(
        service.receive_approval_interaction(cast("Any", object()), approval)
    )
    await asyncio.wait_for(handler.execution_started.wait(), timeout=1)

    await service.receive_owner_message(
        DiscordOwnerMessage(
            "43",
            "33",
            "pause",
            datetime(2026, 9, 7, 18, tzinfo=UTC),
            Control.PAUSE,
        )
    )
    handler.release.set()
    await asyncio.wait_for(task, timeout=1)

    assert await paused.is_paused()
    assert handler.cancellation_observed
    assert not handler.completed.is_set()


class _NoWorkRunner(_Runner):
    async def run(self, cancellation: CancellationToken) -> ThreadNoWork:
        assert not cancellation.cancelled
        return ThreadNoWork(
            RunMetrics(RunId("no-work"), 0, ProviderUsage(), 0.0, False)
        )


class _BlockingBackground:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def run_one(self, cancellation: CancellationToken) -> bool:
        self.started.set()
        await self.release.wait()
        self.cancelled = cancellation.cancelled
        return False

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        cancellation.cancel()


class _PauseIngress(_Ingress):
    async def insert_waking(self, **kwargs: object) -> InboundInsert:
        inserted = await super().insert_waking(**kwargs)  # type: ignore[arg-type]
        incoming = self.inserted[-1]
        if incoming.control is Control.PAUSE:
            self.controls.append(PendingControl(inserted.message.id, "pause", False))
        return inserted


class _PostActionPauseRunner(_Runner):
    def __init__(self, store: _PauseIngress) -> None:
        super().__init__()
        self._store = store
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.active = False
        self.runs = 0

    async def run(self, cancellation: CancellationToken) -> ThreadStopped:
        self.runs += 1
        self.active = True
        self.started.set()
        await self.release.wait()
        assert cancellation.cancelled
        self.active = False
        return ThreadStopped(
            RunMetrics(RunId("post-action-pause"), 1, ProviderUsage(), 0.01, True),
            ThreadStopKind.preempted,
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        assert control is Control.PAUSE
        assert self._store.controls[0].message_id == message_id
        self._store.controls.pop(0)
        return True


class _PostActionRecovery:
    def __init__(self, runner: _PostActionPauseRunner) -> None:
        self.runner = runner
        self.calls = 0
        self.allow_queued_execution: list[bool] = []

    async def recover(self, *, allow_queued_execution: bool = True) -> int:
        assert not self.runner.active
        self.calls += 1
        self.allow_queued_execution.append(allow_queued_execution)
        return 1 if self.calls == 2 else 0


async def test_pause_after_action_recovers_before_paused_service_returns(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    store = _PauseIngress()
    runner = _PostActionPauseRunner(store)
    recovery = _PostActionRecovery(runner)
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, store),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, runner),
        action_recovery=recovery,
        gateway=_Gateway(),
    )
    drain = asyncio.create_task(service.drain_once())
    await asyncio.wait_for(runner.started.wait(), timeout=1)
    await service.receive_owner_message(
        DiscordOwnerMessage(
            "42",
            "33",
            "pause",
            datetime(2026, 9, 3, 18, tzinfo=UTC),
            Control.PAUSE,
        )
    )
    runner.release.set()
    await asyncio.wait_for(drain, timeout=1)

    assert runner.runs == 1
    assert recovery.calls == 2
    assert recovery.allow_queued_execution == [True, False]
    assert store.controls == []
    assert await PausedState(paused_path).is_paused()


class _CircuitIngress(_Ingress):
    async def circuit_is_open(self) -> bool:
        return True


class _RecoveryModeRecorder:
    def __init__(self) -> None:
        self.allow_queued_execution: list[bool] = []

    async def recover(self, *, allow_queued_execution: bool = True) -> int:
        self.allow_queued_execution.append(allow_queued_execution)
        return 0


async def test_open_circuit_runs_only_reconciliation_recovery(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    recovery = _RecoveryModeRecorder()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _CircuitIngress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _Runner()),
        action_recovery=recovery,
        gateway=_Gateway(),
    )

    await service.drain_once()

    assert recovery.allow_queued_execution == [False]


async def test_gateway_ready_catches_up_after_canonical_watermark(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    gateway = _Gateway()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _Runner()),
        gateway=gateway,
    )
    result = await service.gateway_ready()
    assert gateway.after == "41"
    assert result == CatchUpResult(2, 1, False, "42")


async def test_pause_before_claim_cancels_with_multiple_batches_queued(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    store = _Ingress()
    runner = _PreClaimRunner()
    settings = _settings(tmp_path).model_copy(update={"maximum_batch_size": 1})
    service = _InspectableService(
        settings=settings,
        store=cast(IngressStore, store),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, runner),
        gateway=_Gateway(),
    )
    started_at = datetime(2026, 9, 3, 18, tzinfo=UTC)
    for index in range(2):
        await service.receive_owner_message(
            DiscordOwnerMessage(
                str(40 + index),
                "33",
                f"queued input {index}",
                started_at + timedelta(seconds=index),
                None,
            )
        )

    drain = asyncio.create_task(service.drain_once())
    await asyncio.wait_for(runner.before_claim.wait(), timeout=1)
    assert runner.claim_acquired is False
    await service.receive_owner_message(
        DiscordOwnerMessage(
            "42",
            "33",
            "pause",
            started_at + timedelta(seconds=2),
            Control.PAUSE,
        )
    )
    assert runner.claim_acquired is False
    runner.acquire_claim.set()
    await asyncio.wait_for(drain, timeout=1)

    assert settings.maximum_batch_size == 1
    assert len(store.inserted) == 3
    assert runner.cancellation_observed
    assert runner.provider_turns == 0
    assert await PausedState(paused_path).is_paused() is True


async def test_resume_clears_pause_and_remains_queued_for_ordered_drain(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    paused = PausedState(paused_path)
    await paused.set_paused(True)
    store = _Ingress()
    runner = _Runner()
    service = JarvisService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, store),
        paused=paused,
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, runner),
        gateway=_Gateway(),
    )
    incoming = DiscordOwnerMessage(
        "42",
        "33",
        " \nReSuMe\t",
        datetime(2026, 9, 3, 18, tzinfo=UTC),
        Control.RESUME,
    )
    await service.receive_owner_message(incoming)
    assert await paused.is_paused() is False
    assert store.inserted[0].text == "resume"
    assert runner.settled == []


async def test_owner_arrival_cancels_background_without_cancelling_main(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    background = _BlockingBackground()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _NoWorkRunner()),
        background=background,
        gateway=_Gateway(),
    )
    drain = asyncio.create_task(service.drain_once())
    await asyncio.wait_for(background.started.wait(), timeout=1)

    await service.receive_owner_message(
        DiscordOwnerMessage(
            "42",
            "33",
            "new foreground work",
            datetime(2026, 9, 3, 18, tzinfo=UTC),
            None,
        )
    )
    background.release.set()
    await asyncio.wait_for(drain, timeout=1)

    assert background.cancelled


class _DeferredBackground:
    def __init__(self, until: datetime) -> None:
        self.until = until

    async def run_one(self, cancellation: CancellationToken) -> BackgroundDeferred:
        assert not cancellation.cancelled
        return BackgroundDeferred(self.until)

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        cancellation.cancel()


class _BlockingCommitBackground:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.token: CancellationToken | None = None
        self.in_commit = False
        self.interrupt_pending = False

    async def run_one(self, cancellation: CancellationToken) -> bool:
        self.token = cancellation
        self.in_commit = True
        self.started.set()
        await self.release.wait()
        self.in_commit = False
        if self.interrupt_pending:
            cancellation.cancel()
        return True

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        assert cancellation is self.token
        if self.in_commit:
            self.interrupt_pending = True
        else:
            cancellation.cancel()


class _ControlledSleep:
    def __init__(self) -> None:
        self.seconds: float | None = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, seconds: float) -> None:
        self.seconds = seconds
        self.started.set()
        await self.release.wait()


class _OneShotDreamSleep:
    def __init__(self) -> None:
        self.seconds: float | None = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._subsequent = asyncio.Event()

    async def __call__(self, seconds: float) -> None:
        self.seconds = seconds
        if not self.started.is_set():
            self.started.set()
            await self.release.wait()
            return
        await self._subsequent.wait()


class _RecordingBackground:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls = 0

    async def run_one(self, cancellation: CancellationToken) -> bool:
        assert not cancellation.cancelled
        self.calls += 1
        self.started.set()
        return False

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        cancellation.cancel()


async def test_background_admission_deferral_schedules_silent_reset(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    sleep = _ControlledSleep()
    reset_at = datetime.now(UTC) + timedelta(minutes=2)
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _NoWorkRunner()),
        background=_DeferredBackground(reset_at),
        gateway=_Gateway(),
        sleep=sleep,
    )

    await service.drain_once()
    await asyncio.wait_for(sleep.started.wait(), timeout=1)
    assert sleep.seconds is not None
    assert 0 < sleep.seconds <= 120
    service.request_shutdown()


async def test_shutdown_waits_for_background_atomic_commit_boundary(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    background = _BlockingCommitBackground()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _NoWorkRunner()),
        background=background,
        gateway=_Gateway(),
    )
    drain = asyncio.create_task(service.drain_once())
    await asyncio.wait_for(background.started.wait(), timeout=1)

    service.request_shutdown()

    assert background.token is not None
    assert not background.token.cancelled
    background.release.set()
    await asyncio.wait_for(drain, timeout=1)
    assert background.token.cancelled


async def test_dream_timer_waits_a_full_interval_before_one_silent_run(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    dreamer = _RecordingBackground()
    dream_sleep = _OneShotDreamSleep()
    settings = _settings(tmp_path).model_copy(update={"dream_interval_seconds": 86_400})
    service = JarvisService(
        settings=settings,
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _NoWorkRunner()),
        dreamer=dreamer,
        gateway=_Gateway(),
        dream_sleep=dream_sleep,
    )

    worker = asyncio.create_task(service.run_worker())
    await asyncio.wait_for(dream_sleep.started.wait(), timeout=1)
    assert dream_sleep.seconds == 86_400
    assert dreamer.calls == 0

    dream_sleep.release.set()
    await asyncio.wait_for(dreamer.started.wait(), timeout=1)
    assert dreamer.calls == 1
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)


async def test_restart_does_not_immediately_replay_a_missed_dream(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    dreamer = _RecordingBackground()
    dream_sleep = _OneShotDreamSleep()
    service = JarvisService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _NoWorkRunner()),
        dreamer=dreamer,
        gateway=_Gateway(),
        dream_sleep=dream_sleep,
    )

    worker = asyncio.create_task(service.run_worker())
    await asyncio.wait_for(dream_sleep.started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert dreamer.calls == 0
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)

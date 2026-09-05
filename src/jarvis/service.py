"""Bounded Jarvis host-service composition."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from llm_agent_kernel import (
    CancellationToken,
    OwnerToken,
    RunId,
    ThreadDeferred,
    ThreadId,
    ThreadNoWork,
    ThreadOutcome,
    ThreadStopKind,
    ThreadStopped,
    ToolDispatchPort,
    run_thread,
)

from jarvis.admission import ExactToolBudgetFactory, RollingAdmissionPort
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.context import JarvisContextSource
from jarvis.definitions import Slice1Definitions, Slice2Definitions
from jarvis.discord import (
    CatchUpResult,
    Control,
    DeliveryFailed,
    DeliveryResult,
    DiscordOwnerMessage,
)
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import EmptySlice1Dispatcher, KernelRuntime
from jarvis.messages import InboundInsert, MessageStore, PendingControl, StoredMessage
from jarvis.settings import Settings
from jarvis.state import PausedState

LOGGER = logging.getLogger(__name__)


class PendingDeliveryStore(Protocol):
    async def pending_delivery(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[StoredMessage, ...]: ...

    async def mark_delivered(
        self,
        *,
        message_id: UUID,
        source_message_id: str,
    ) -> None: ...


class CreateMessagePort(Protocol):
    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult: ...


@dataclass(frozen=True, slots=True)
class DeliveryFlushResult:
    selected: int
    delivered: int
    failure: DeliveryFailed | None


async def flush_pending_deliveries(
    *,
    store: PendingDeliveryStore,
    delivery: CreateMessagePort,
    source_conversation_id: str,
    limit: int,
) -> DeliveryFlushResult:
    """Deliver pending assistant rows in order and stop at the first failure."""

    pending = await store.pending_delivery(
        source_conversation_id=source_conversation_id,
        limit=limit,
    )
    delivered = 0
    for message in pending:
        result = await delivery.create_message(
            persisted_message_id=message.id,
            content=message.text,
        )
        if isinstance(result, DeliveryFailed):
            return DeliveryFlushResult(len(pending), delivered, result)
        await store.mark_delivered(
            message_id=message.id,
            source_message_id=result.discord_message_id,
        )
        delivered += 1
    return DeliveryFlushResult(len(pending), delivered, None)


@dataclass(frozen=True, slots=True)
class PreflightDeferred:
    until: datetime


type ServiceRunOutcome = ThreadOutcome | PreflightDeferred


class ThreadRunner(Protocol):
    async def run(self, cancellation: CancellationToken) -> ServiceRunOutcome: ...

    async def settle_control(self, message_id: UUID, control: Control) -> bool: ...

    async def discard_recovered_session_reference(self) -> None: ...


class JarvisThreadRunner:
    """One concrete invocation of the pinned kernel over PostgreSQL ports."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: MessageStore,
        admission: RollingAdmissionPort,
        kernel_runtime: KernelRuntime,
        definitions: Slice1Definitions | Slice2Definitions,
        history: PostgresCanonicalHistory,
        dispatcher_factory: Callable[[], ToolDispatchPort] = EmptySlice1Dispatcher,
    ) -> None:
        self._settings = settings
        self._store = store
        self._admission = admission
        self._kernel_runtime = kernel_runtime
        self._definitions = definitions
        self._history = history
        self._dispatcher_factory = dispatcher_factory
        self._checkpoint_lock = asyncio.Lock()
        self._checkpoint: PostgresInputCheckpoint | None = None

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        """Settle an idle control, or leave an active one for checkpoint polling."""

        value = _control_value(control)
        async with self._checkpoint_lock:
            checkpoint = self._checkpoint
            if checkpoint is None:
                await self._store.settle_control(
                    message_id=message_id,
                    source_conversation_id=str(self._settings.discord.channel_id),
                    control=value,
                )
                return True
            result = await checkpoint.settle_idle_control(
                message_id=message_id,
                control=value,
            )
            return result is not None

    async def discard_recovered_session_reference(self) -> None:
        await self._kernel_runtime.discard_recovered_session_reference(
            ThreadId(str(self._settings.discord.channel_id)),
            self._definitions.main,
        )

    async def run(self, cancellation: CancellationToken) -> ServiceRunOutcome:
        limits = self._definitions.main.limits
        reset_at = await self._admission.preflight(
            maximum_turns=limits.max_provider_turns,
            maximum_input_tokens=limits.max_provider_input_tokens,
            maximum_output_tokens=limits.max_provider_output_tokens,
        )
        if reset_at is not None:
            await self._store.record_admission_deferral(
                source_conversation_id=str(self._settings.discord.channel_id),
                reset_at=reset_at,
            )
            return PreflightDeferred(reset_at)

        run_id = RunId(str(uuid4()))
        thread_id = ThreadId(str(self._settings.discord.channel_id))
        checkpoints = PostgresInputCheckpoint(
            store=self._store,
            thread_id=thread_id,
            run_id=run_id,
            interactive_plan=self._definitions.plans["main"],
            scheduled_wake_plan=self._definitions.plans["scheduled_wake"],
            maximum_batch_size=self._settings.maximum_batch_size,
            maximum_attempts=self._definitions.main.limits.max_no_progress_attempts,
        )
        context = JarvisContextSource(thread_id, self._history)
        async with self._checkpoint_lock:
            if self._checkpoint is not None:
                raise RuntimeError("the Jarvis thread runner is already active")
            self._checkpoint = checkpoints
        try:
            outcome = await run_thread(
                run_id=run_id,
                thread_id=thread_id,
                owner_token=OwnerToken(str(self._settings.discord.owner_user_id)),
                definition=self._definitions.main,
                checkpoints=checkpoints,
                admission=self._admission,
                sessions=self._kernel_runtime.sessions,
                context_source=context,
                dispatcher=self._dispatcher_factory(),
                budget_factory=ExactToolBudgetFactory(),
                cancellation=cancellation,
            )
        finally:
            async with self._checkpoint_lock:
                self._checkpoint = None
        if checkpoints.consumed_message_ids:
            metrics = outcome.metrics
            await self._store.record_run_metrics(
                consumed_message_ids=checkpoints.consumed_message_ids,
                run_id=str(run_id),
                provider_turns=metrics.provider_turns,
                input_tokens=metrics.usage.input_tokens,
                output_tokens=metrics.usage.output_tokens,
                duration_seconds=metrics.duration_seconds,
            )
        return outcome


# Compatibility name for the shipped Slice 1 tests and qualification records.
Slice1ThreadRunner = JarvisThreadRunner


def _control_value(control: Control) -> Literal["stop", "pause", "resume"]:
    return control.value


class DiscordCursorPort(Protocol):
    async def latest_discord_owner_source_message_id(
        self,
        *,
        source_conversation_id: str,
    ) -> str | None: ...


class PendingControlPort(Protocol):
    async def pending_controls(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[PendingControl, ...]: ...


class IngressStore(
    PendingDeliveryStore,
    DiscordCursorPort,
    PendingControlPort,
    Protocol,
):
    async def insert_waking(
        self,
        *,
        role: Literal["owner", "host"],
        text: str,
        source: str,
        source_conversation_id: str,
        source_message_id: str,
        created_at: datetime,
        message_id: UUID | None = None,
    ) -> InboundInsert: ...

    async def circuit_is_open(self) -> bool: ...

    async def settle_recovered_control(
        self,
        *,
        message_id: UUID,
        source_conversation_id: str,
        control: Literal["stop", "pause"],
    ) -> object: ...


class GatewayPort(Protocol):
    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult: ...

    def typing(self) -> AbstractAsyncContextManager[None]: ...


class JarvisService:
    """Serial host coordinator for Gateway ingress, kernel work, and delivery."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: IngressStore,
        paused: PausedState,
        delivery: CreateMessagePort,
        runner: ThreadRunner,
        gateway: GatewayPort | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._store = store
        self._paused = paused
        self._delivery = delivery
        self._runner = runner
        self._gateway = gateway
        self._sleep = sleep
        self._work = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._execution_mutex = asyncio.Lock()
        self._active_lock = asyncio.Lock()
        self._active_cancellation: CancellationToken | None = None
        self._reset_task: asyncio.Task[None] | None = None

    def bind_gateway(self, gateway: GatewayPort) -> None:
        """Resolve the one callback cycle between the service and Gateway."""

        if self._gateway is not None:
            raise RuntimeError("the Discord Gateway is already bound")
        self._gateway = gateway

    async def receive_owner_message(self, incoming: DiscordOwnerMessage) -> None:
        """Persist/deduplicate ingress before applying host control."""

        async with self._active_lock:
            canonical_text = (
                incoming.control.value
                if incoming.control is not None
                else incoming.text
            )
            inserted = await self._store.insert_waking(
                role="owner",
                text=canonical_text,
                source="discord",
                source_conversation_id=incoming.source_conversation_id,
                source_message_id=incoming.source_message_id,
                created_at=incoming.created_at,
            )
            if not inserted.inserted:
                return

            active = self._active_cancellation
            if incoming.control in {Control.STOP, Control.PAUSE}:
                await self._paused.set_paused(True)
                if active is not None:
                    active.cancel()
            elif incoming.control is Control.RESUME:
                await self._paused.set_paused(False)

        self._work.set()

    async def gateway_ready(self) -> CatchUpResult:
        """Boundedly catch up from the canonical Discord watermark."""

        source_conversation_id = str(self._settings.discord.channel_id)
        after = await self._store.latest_discord_owner_source_message_id(
            source_conversation_id=source_conversation_id
        )
        result = await self._require_gateway().catch_up(after)
        self._work.set()
        return result

    async def flush_delivery(self) -> DeliveryFlushResult:
        selected = 0
        delivered = 0
        while True:
            result = await flush_pending_deliveries(
                store=self._store,
                delivery=self._delivery,
                source_conversation_id=str(self._settings.discord.channel_id),
                limit=self._settings.delivery_batch_size,
            )
            selected += result.selected
            delivered += result.delivered
            if result.failure is not None:
                LOGGER.warning(
                    "Discord delivery stopped: kind=%s attempts=%d "
                    "status=%s ambiguous=%s",
                    result.failure.kind.value,
                    result.failure.attempts,
                    result.failure.http_status,
                    result.failure.ambiguous,
                )
                return DeliveryFlushResult(selected, delivered, result.failure)
            if result.selected < self._settings.delivery_batch_size:
                if delivered:
                    LOGGER.info("Discord delivery completed: count=%d", delivered)
                return DeliveryFlushResult(selected, delivered, None)

    async def run_worker(self) -> None:
        """Run until shutdown, draining serial work and pending delivery."""

        while not self._shutdown.is_set():
            await self._work.wait()
            self._work.clear()
            await self._drain()

    def request_work(self) -> None:
        self._work.set()

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._work.set()
        if self._reset_task is not None:
            self._reset_task.cancel()

    async def _drain(self) -> None:
        async with self._execution_mutex:
            await self.flush_delivery()
            while not self._shutdown.is_set():
                controls = await self._store.pending_controls(
                    source_conversation_id=str(self._settings.discord.channel_id),
                    limit=1,
                )
                if controls:
                    pending = controls[0]
                    control = Control(pending.control)
                    if control is Control.RESUME:
                        await self._paused.set_paused(False)
                        if not await self._runner.settle_control(
                            pending.message_id,
                            control,
                        ):
                            return
                        await self.flush_delivery()
                        continue
                    await self._paused.set_paused(True)
                    if pending.requires_recovery_run:
                        await self._runner.discard_recovered_session_reference()
                        await self._store.settle_recovered_control(
                            message_id=pending.message_id,
                            source_conversation_id=str(
                                self._settings.discord.channel_id
                            ),
                            control=cast(
                                Literal["stop", "pause"],
                                pending.control,
                            ),
                        )
                    else:
                        if not await self._runner.settle_control(
                            pending.message_id,
                            control,
                        ):
                            return
                    await self.flush_delivery()
                    continue
                elif (
                    await self._paused.is_paused()
                    or await self._store.circuit_is_open()
                ):
                    return
                cancellation = CancellationToken()
                async with self._active_lock:
                    self._active_cancellation = cancellation
                try:
                    async with self._require_gateway().typing():
                        outcome = await self._runner.run(cancellation)
                finally:
                    async with self._active_lock:
                        self._active_cancellation = None
                await self.flush_delivery()

                if isinstance(outcome, PreflightDeferred):
                    self._schedule_reset(outcome.until)
                    return
                LOGGER.info(
                    "Kernel run completed: type=%s turns=%d consumed=%s",
                    outcome.type,
                    outcome.metrics.provider_turns,
                    outcome.metrics.input_consumed,
                )
                if isinstance(outcome, ThreadDeferred):
                    self._schedule_reset(outcome.until)
                    return
                if isinstance(outcome, ThreadNoWork):
                    return
                if (
                    isinstance(outcome, ThreadStopped)
                    and outcome.type is ThreadStopKind.preempted
                ):
                    continue
                if (
                    isinstance(outcome, ThreadStopped)
                    and not outcome.metrics.input_consumed
                ):
                    return

    def _schedule_reset(self, reset_at: datetime) -> None:
        delay = max(0.0, (reset_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())

        async def signal() -> None:
            await self._sleep(delay)
            self._work.set()

        if self._reset_task is not None:
            self._reset_task.cancel()
        self._reset_task = asyncio.create_task(signal(), name="jarvis-admission-reset")

    def _require_gateway(self) -> GatewayPort:
        if self._gateway is None:
            raise RuntimeError("the Discord Gateway is not bound")
        return self._gateway


__all__ = [
    "DeliveryFlushResult",
    "DiscordCursorPort",
    "JarvisService",
    "JarvisThreadRunner",
    "PendingControlPort",
    "PreflightDeferred",
    "Slice1ThreadRunner",
    "flush_pending_deliveries",
]

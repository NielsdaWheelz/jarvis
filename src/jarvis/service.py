"""Bounded Jarvis host-service composition."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID

import discord
from llm_agent_kernel import (
    CancellationToken,
    ThreadDeferred,
    ThreadNoWork,
    ThreadStopKind,
    ThreadStopped,
)
from llm_tools import FrozenToolPlan

from jarvis import memory_workers
from jarvis.actions import ClaimedSchedule, ScheduleStateChanged
from jarvis.agent_control import AgentController
from jarvis.approval_runtime import ApprovalActionHandler
from jarvis.discord import (
    CatchUpResult,
    Control,
    DeliveryFailed,
    DeliveryResult,
    DiscordApprovalInteraction,
    DiscordOwnerMessage,
)
from jarvis.messages import InboundInsert, PendingControl, StoredMessage
from jarvis.proactivity import ProcessLocalWakeTimer
from jarvis.settings import Settings
from jarvis.state import PausedState
from jarvis.thread_runtime import PreflightDeferred, ServiceRunOutcome

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


class ThreadRunner(Protocol):
    async def run(self, cancellation: CancellationToken) -> ServiceRunOutcome: ...

    async def settle_control(self, message_id: UUID, control: Control) -> bool: ...

    async def discard_recovered_session_reference(self) -> None: ...


class BackgroundWorkerPort(Protocol):
    async def run_one(
        self, cancellation: CancellationToken
    ) -> bool | memory_workers.BackgroundDeferred: ...

    def request_interrupt(self, cancellation: CancellationToken) -> None: ...


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


class ScheduledWakeStore(Protocol):
    async def claim_next_due_schedule(
        self,
        *,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        now: datetime | None = None,
    ) -> ClaimedSchedule | ScheduleStateChanged | None: ...


class ActionRecoveryPort(Protocol):
    async def recover(self, *, allow_queued_execution: bool = True) -> int: ...


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
        background: BackgroundWorkerPort,
        dreamer: BackgroundWorkerPort,
        scheduled_wakes: ScheduledWakeStore,
        action_plan: FrozenToolPlan,
        action_recovery: ActionRecoveryPort,
        agent_waits: AgentController,
        approval_handler: ApprovalActionHandler,
        gateway: GatewayPort | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        dream_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._store = store
        self._paused = paused
        self._delivery = delivery
        self._runner = runner
        self._background = background
        self._dreamer = dreamer
        self._scheduled_wakes = scheduled_wakes
        self._action_plan = action_plan
        self._action_recovery = action_recovery
        self._agent_waits = agent_waits
        self._approval_handler = approval_handler
        self._gateway = gateway
        self._sleep = sleep
        self._dream_sleep = dream_sleep
        self._work = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._execution_mutex = asyncio.Lock()
        self._active_lock = asyncio.Lock()
        self._active_cancellation: CancellationToken | None = None
        self._active_background: BackgroundWorkerPort | None = None
        self._background_cancellation: CancellationToken | None = None
        self._reset_task: asyncio.Task[None] | None = None
        self._dream_timer_task: asyncio.Task[None] | None = None
        self._wake_timer: ProcessLocalWakeTimer | None = None
        self._wake_timer_task: asyncio.Task[None] | None = None
        self._wake_cancellation: CancellationToken | None = None
        self._agent_wait_task: asyncio.Task[None] | None = None
        self._agent_wait_cancellation: CancellationToken | None = None
        self._dream_due = False

    def bind_gateway(self, gateway: GatewayPort) -> None:
        """Resolve the one callback cycle between the service and Gateway."""

        if self._gateway is not None:
            raise RuntimeError("the Discord Gateway is already bound")
        self._gateway = gateway

    def bind_wake_timer(self, timer: ProcessLocalWakeTimer) -> None:
        if self._wake_timer is not None:
            raise RuntimeError("the scheduled-wake timer cannot be bound")
        self._wake_timer = timer

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
            background = self._background_cancellation
            background_worker = self._active_background
            if background is not None and background_worker is not None:
                background_worker.request_interrupt(background)
            if incoming.control in {Control.STOP, Control.PAUSE}:
                await self._paused.set_paused(True)
                if active is not None:
                    active.cancel()
            elif incoming.control is Control.RESUME:
                await self._paused.set_paused(False)

        self._agent_waits.notify_wait_changed()
        self._work.set()

    async def receive_approval_interaction(
        self,
        event: discord.Interaction,
        interaction: DiscordApprovalInteraction,
    ) -> None:
        """Claim one configured component before serial effect execution."""

        if await self._paused.is_paused():
            return
        claimed = await self._approval_handler.claim_and_acknowledge(
            event,
            interaction,
        )
        if claimed is None:
            return
        async with self._execution_mutex:
            cancellation = CancellationToken()
            async with self._active_lock:
                self._active_cancellation = cancellation
                if self._shutdown.is_set() or await self._paused.is_paused():
                    cancellation.cancel()
            if cancellation.cancelled:
                async with self._active_lock:
                    if self._active_cancellation is cancellation:
                        self._active_cancellation = None
                self._work.set()
                return
            try:
                await self._approval_handler.complete(claimed, cancellation)
            finally:
                async with self._active_lock:
                    if self._active_cancellation is cancellation:
                        self._active_cancellation = None
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
        while not self._shutdown.is_set():
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
        return DeliveryFlushResult(selected, delivered, None)

    async def _waits_inactive(self) -> bool:
        return await self._paused.is_paused() or await self._store.circuit_is_open()

    async def run_worker(self) -> None:
        """Run until shutdown, draining serial work and pending delivery."""

        self._dream_timer_task = asyncio.create_task(
            self._dream_timer(),
            name="jarvis-dream-timer",
        )
        if self._wake_timer is not None:
            self._wake_cancellation = CancellationToken()
            self._wake_timer_task = asyncio.create_task(
                self._wake_timer.run(self._wake_cancellation),
                name="jarvis-scheduled-wake-timer",
            )
            self._wake_timer_task.add_done_callback(lambda _task: self._work.set())
        self._agent_wait_cancellation = CancellationToken()
        self._agent_wait_task = asyncio.create_task(
            self._agent_waits.run_waits(
                self._agent_wait_cancellation,
                paused=self._waits_inactive,
                plan=self._action_plan,
                on_event=self.request_work,
            ),
            name="jarvis-agent-waits",
        )
        self._agent_wait_task.add_done_callback(lambda _task: self._work.set())
        try:
            while not self._shutdown.is_set():
                await self._work.wait()
                self._work.clear()
                if self._shutdown.is_set():
                    return
                if self._wake_timer_task is not None and self._wake_timer_task.done():
                    self._wake_timer_task.result()
                    raise RuntimeError("the scheduled-wake timer stopped unexpectedly")
                if self._agent_wait_task.done():
                    self._agent_wait_task.result()
                    raise RuntimeError("agent wait observer stopped unexpectedly")
                await self._drain()
        finally:
            self._agent_wait_cancellation.cancel()
            tasks = [self._agent_wait_task, self._dream_timer_task]
            if self._reset_task is not None:
                self._reset_task.cancel()
                tasks.append(self._reset_task)
            self._dream_timer_task.cancel()
            if self._wake_cancellation is not None:
                self._wake_cancellation.cancel()
            if self._wake_timer_task is not None:
                tasks.append(self._wake_timer_task)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._agent_wait_task = None
            self._agent_wait_cancellation = None
            self._reset_task = None
            self._dream_timer_task = None
            self._wake_timer_task = None
            self._wake_cancellation = None
            for result in results:
                if isinstance(result, Exception):
                    raise result

    def request_work(self) -> None:
        self._work.set()

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._work.set()
        if self._active_cancellation is not None:
            self._active_cancellation.cancel()
        if (
            self._background_cancellation is not None
            and self._active_background is not None
        ):
            self._active_background.request_interrupt(self._background_cancellation)
        if self._reset_task is not None:
            self._reset_task.cancel()
        if self._dream_timer_task is not None:
            self._dream_timer_task.cancel()
        if self._wake_cancellation is not None:
            self._wake_cancellation.cancel()
        if self._agent_wait_cancellation is not None:
            self._agent_wait_cancellation.cancel()

    async def _drain(self) -> None:
        async with self._execution_mutex:
            if self._shutdown.is_set():
                return
            await self.flush_delivery()
            while not self._shutdown.is_set():
                controls = await self._store.pending_controls(
                    source_conversation_id=str(self._settings.discord.channel_id),
                    limit=1,
                )
                if self._shutdown.is_set():
                    return
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
                inactive = (
                    await self._paused.is_paused()
                    or await self._store.circuit_is_open()
                )
                if self._shutdown.is_set():
                    return
                recovered_actions = await self._recover_actions(
                    allow_queued_execution=not inactive
                )
                if inactive or self._shutdown.is_set():
                    return
                if recovered_actions:
                    continue
                claimed = await self._scheduled_wakes.claim_next_due_schedule(
                    plan=self._action_plan,
                    source_conversation_id=str(self._settings.discord.channel_id),
                )
                if claimed is not None:
                    if self._wake_timer is not None:
                        self._wake_timer.notify_changed()
                    if isinstance(claimed, ScheduleStateChanged):
                        await self._recover_actions(allow_queued_execution=False)
                    continue
                cancellation = CancellationToken()
                async with self._active_lock:
                    if self._shutdown.is_set():
                        return
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
                    background = await self._run_background_once(self._background)
                    if isinstance(background, memory_workers.BackgroundDeferred):
                        self._schedule_reset(background.until)
                        return
                    if background:
                        continue
                    if self._work.is_set() or not self._dream_due:
                        return
                    dream = await self._run_background_once(self._dreamer)
                    if isinstance(dream, memory_workers.BackgroundDeferred):
                        self._schedule_reset(dream.until)
                        return
                    self._dream_due = False
                    if dream:
                        continue
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

    async def _recover_actions(self, *, allow_queued_execution: bool) -> int:
        recovered_actions = await self._action_recovery.recover(
            allow_queued_execution=allow_queued_execution
        )
        if recovered_actions:
            LOGGER.warning(
                "Recovered interrupted actions: count=%d",
                recovered_actions,
            )
            await self.flush_delivery()
        return recovered_actions

    async def _run_background_once(
        self,
        worker: BackgroundWorkerPort,
    ) -> bool | memory_workers.BackgroundDeferred:
        if self._work.is_set() or self._shutdown.is_set():
            return False
        cancellation = CancellationToken()
        async with self._active_lock:
            self._active_background = worker
            self._background_cancellation = cancellation
            if self._work.is_set():
                cancellation.cancel()
        try:
            return await worker.run_one(cancellation)
        finally:
            async with self._active_lock:
                if self._background_cancellation is cancellation:
                    self._background_cancellation = None
                    self._active_background = None

    async def _dream_timer(self) -> None:
        while not self._shutdown.is_set():
            await self._dream_sleep(self._settings.dream_interval_seconds)
            if self._shutdown.is_set():
                return
            self._dream_due = True
            self._work.set()

    def _schedule_reset(self, reset_at: datetime) -> None:
        if self._shutdown.is_set():
            return
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
    "ActionRecoveryPort",
    "DeliveryFlushResult",
    "DiscordCursorPort",
    "JarvisService",
    "PendingControlPort",
    "ScheduledWakeStore",
    "flush_pending_deliveries",
]

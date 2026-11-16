"""Bounded Jarvis host-service composition."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from llm_agent_kernel import CancellationToken
from llm_tools import FrozenToolPlan

from jarvis.agent_control import AgentController
from jarvis.discord import (
    CatchUpResult,
    Control,
    DeliveryFailed,
    DeliveryResult,
    DiscordOwnerMessage,
)
from jarvis.event_polling import EventPoller
from jarvis.memory_service import MemoryService
from jarvis.messages import InboundInsert, StoredMessage
from jarvis.native_runtime import NativeRunOutcome
from jarvis.proactivity import WorkWakeTimer
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


class NativeRunnerPort(Protocol):
    notify_delivery: Callable[[], None]
    notify_work: Callable[[], None]

    async def run(self, cancellation: CancellationToken) -> NativeRunOutcome: ...
    async def recover(self) -> None: ...
    async def close(self) -> None: ...


class BackgroundWorkerPort(Protocol):
    async def run_one(self, cancellation: CancellationToken) -> bool: ...

    def request_interrupt(self, cancellation: CancellationToken) -> None: ...


class DiscordCursorPort(Protocol):
    async def latest_discord_owner_source_message_id(
        self,
        *,
        source_conversation_id: str,
    ) -> str | None: ...


class IngressStore(PendingDeliveryStore, DiscordCursorPort, Protocol):
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
        control_kind: Literal["pause", "resume"] | None = None,
    ) -> InboundInsert: ...


class GatewayPort(Protocol):
    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult: ...

    def typing(self) -> AbstractAsyncContextManager[None]: ...


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
        runner: NativeRunnerPort,
        background: BackgroundWorkerPort,
        dreamer: BackgroundWorkerPort,
        action_plan: FrozenToolPlan,
        action_recovery: ActionRecoveryPort,
        agent_waits: AgentController,
        dispatch_lane: asyncio.Lock,
        memory: MemoryService,
        work_timer: WorkWakeTimer,
        event_poller: EventPoller,
        gateway: GatewayPort | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        dream_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._memory = memory
        self._work_timer = work_timer
        self._event_poller = event_poller
        self._event_poll_task: asyncio.Task[None] | None = None
        self._work_timer_task: asyncio.Task[None] | None = None
        self._store = store
        self._paused = paused
        self._delivery = delivery
        self._runner = runner
        self._background = background
        self._dreamer = dreamer
        self._action_plan = action_plan
        self._action_recovery = action_recovery
        self._agent_waits = agent_waits
        self._gateway = gateway
        self._sleep = sleep
        self._dream_sleep = dream_sleep
        self._work = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._dispatch_lane = dispatch_lane
        self._delivery_work = asyncio.Event()
        self._delivery_lock = asyncio.Lock()
        self._delivery_task: asyncio.Task[None] | None = None
        self._runner.notify_delivery = self.request_delivery
        self._runner.notify_work = self.request_work
        self._active_lock = asyncio.Lock()
        self._active_cancellation: CancellationToken | None = None
        self._active_background: BackgroundWorkerPort | None = None
        self._background_cancellation: CancellationToken | None = None
        self._dream_timer_task: asyncio.Task[None] | None = None
        self._agent_wait_task: asyncio.Task[None] | None = None
        self._agent_wait_cancellation: CancellationToken | None = None
        self._dream_due = False
        self._startup_ready = False

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
                control_kind=incoming.control.value
                if incoming.control is not None
                else None,
            )
            if not inserted.inserted:
                return

            active = self._active_cancellation
            background = self._background_cancellation
            background_worker = self._active_background
            if background is not None and background_worker is not None:
                background_worker.request_interrupt(background)
            if incoming.control is Control.PAUSE:
                if active is not None:
                    active.cancel()

        self.request_delivery()
        await self._memory.publish()
        self._agent_waits.notify_wait_changed()
        self._work_timer.notify_changed()
        self._event_poller.notify_changed()
        self._work.set()

    async def gateway_ready(self) -> CatchUpResult:
        """Boundedly catch up from the canonical Discord watermark."""

        source_conversation_id = str(self._settings.discord.channel_id)
        after = await self._store.latest_discord_owner_source_message_id(
            source_conversation_id=source_conversation_id
        )
        result = await self._require_gateway().catch_up(after)
        self._startup_ready = True
        self._event_poller.notify_changed()
        self._work.set()
        return result

    async def flush_delivery(self) -> DeliveryFlushResult:
        async with self._delivery_lock:
            return await self._flush_delivery()

    async def _flush_delivery(self) -> DeliveryFlushResult:
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
        return await self._paused.is_paused()

    def events_publication_allowed(self) -> bool:
        return self._startup_ready and not self._shutdown.is_set()

    async def events_admitted(self) -> bool:
        """Provider work waits for catch-up and current unpaused ownership."""
        if not self.events_publication_allowed():
            return False
        return not await self._paused.is_paused()

    async def run_worker(self) -> None:
        """Run until shutdown, draining serial work and pending delivery."""

        await self._runner.recover()
        self._work_timer.notify_changed()
        self._work_timer_task = asyncio.create_task(
            self._run_work_timer(), name="jarvis-work-timer"
        )
        self._work_timer_task.add_done_callback(self._timer_stopped)
        self._event_poll_task = asyncio.create_task(
            self._run_event_poller(), name="jarvis-event-poller"
        )
        self._event_poll_task.add_done_callback(self._timer_stopped)
        self._delivery_task = asyncio.create_task(
            self._deliver(), name="jarvis-delivery"
        )
        self._delivery_task.add_done_callback(lambda _task: self._work.set())
        self.request_delivery()
        self._dream_timer_task = asyncio.create_task(
            self._dream_timer(),
            name="jarvis-dream-timer",
        )
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
                if self._delivery_task.done():
                    self._delivery_task.result()
                    raise RuntimeError("the Discord delivery task stopped unexpectedly")
                if self._agent_wait_task.done():
                    self._agent_wait_task.result()
                    raise RuntimeError("agent wait observer stopped unexpectedly")
                await self._drain()
        finally:
            self._work_timer_task.cancel()
            self._agent_wait_cancellation.cancel()
            self._delivery_task.cancel()
            self._dream_timer_task.cancel()
            tasks = [
                self._event_poll_task,
                self._work_timer_task,
                self._agent_wait_task,
                self._delivery_task,
                self._dream_timer_task,
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._agent_wait_task = None
            self._agent_wait_cancellation = None
            self._delivery_task = None
            self._event_poll_task = None
            self._work_timer_task = None
            self._dream_timer_task = None
            await self._runner.close()
            for result in results:
                if isinstance(result, Exception):
                    raise result

    def _timer_stopped(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            self.request_shutdown()

    async def _run_event_poller(self) -> None:
        await self._event_poller.run(self._shutdown)
        if not self._shutdown.is_set():
            raise RuntimeError("event poller stopped unexpectedly")

    async def _run_work_timer(self) -> None:
        await self._work_timer.run()
        raise RuntimeError("work timer stopped unexpectedly")

    def request_work(self) -> None:
        if (
            self._active_background is not None
            and self._background_cancellation is not None
        ):
            self._active_background.request_interrupt(self._background_cancellation)
        self._work.set()

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._event_poller.notify_changed()
        self._work.set()
        if self._active_cancellation is not None:
            self._active_cancellation.cancel()
        if (
            self._background_cancellation is not None
            and self._active_background is not None
        ):
            self._active_background.request_interrupt(self._background_cancellation)
        if self._dream_timer_task is not None:
            self._dream_timer_task.cancel()
        if self._agent_wait_cancellation is not None:
            self._agent_wait_cancellation.cancel()

    def request_delivery(self) -> None:
        self._delivery_work.set()

    async def _deliver(self) -> None:
        while not self._shutdown.is_set():
            await self._delivery_work.wait()
            self._delivery_work.clear()
            result = await self.flush_delivery()
            if result.failure is not None and not self._shutdown.is_set():
                await self._sleep(2.0)
                self._delivery_work.set()

    async def _drain(self) -> None:
        if not self._startup_ready:
            return
        while not self._shutdown.is_set():
            inactive = await self._paused.is_paused()
            recovered = await self._recover_actions(allow_queued_execution=not inactive)
            if inactive:
                return
            if recovered:
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
            self.request_delivery()
            LOGGER.info("native main completed: status=%s", outcome.status)
            if outcome.status in {"blocked", "stopped"}:
                return
            if outcome.status != "no_work":
                continue
            if await self._run_background_once(self._background):
                continue
            if self._work.is_set() or not self._dream_due:
                return
            dream = await self._run_background_once(self._dreamer)
            self._dream_due = False
            if not dream:
                return

    async def _recover_actions(self, *, allow_queued_execution: bool) -> int:
        if self._dispatch_lane.locked():
            return 0
        async with self._dispatch_lane:
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
    ) -> bool:
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
            self._dream_due = True
            self._work.set()
            await self._dream_sleep(60)

    def _require_gateway(self) -> GatewayPort:
        if self._gateway is None:
            raise RuntimeError("the Discord Gateway is not bound")
        return self._gateway


__all__ = [
    "ActionRecoveryPort",
    "DeliveryFlushResult",
    "DiscordCursorPort",
    "JarvisService",
    "flush_pending_deliveries",
]

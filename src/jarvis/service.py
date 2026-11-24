"""Bounded Jarvis host-service composition."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Protocol
from uuid import UUID

from llm_agent_kernel import CancellationToken
from llm_tools import FrozenToolPlan

from jarvis.agent_control import AgentController
from jarvis.attachments import AttachmentStore, WebUpload
from jarvis.event_polling import EventPoller
from jarvis.fcm import FcmSender
from jarvis.home_notices import deliver_pending
from jarvis.memory_service import MemoryService
from jarvis.messages import IngressUnavailable, MessageStore
from jarvis.native_runtime import NativeRunOutcome
from jarvis.ownership import Database
from jarvis.phone import PhoneSlot
from jarvis.proactivity import WorkWakeTimer
from jarvis.settings import Settings
from jarvis.state import PausedState

LOGGER = logging.getLogger(__name__)


class NativeRunnerPort(Protocol):
    notify_delivery: Callable[[], None]
    notify_work: Callable[[], None]

    async def run(self, cancellation: CancellationToken) -> NativeRunOutcome: ...
    async def recover_memory(self) -> None: ...
    async def close(self) -> None: ...


class BackgroundWorkerPort(Protocol):
    async def run_one(self, cancellation: CancellationToken) -> bool: ...

    def request_interrupt(self, cancellation: CancellationToken) -> None: ...


class ActionRecoveryPort(Protocol):
    async def recover(self, *, allow_queued_execution: bool = True) -> int: ...


class JarvisService:
    """Coordinate owner submissions, background work and notification delivery."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        paused: PausedState,
        delivery: FcmSender,
        phone: PhoneSlot,
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
        attachments: AttachmentStore,
        dream_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._attachments = attachments
        self._attachment_work = asyncio.Event()
        self._attachment_task: asyncio.Task[None] | None = None
        self._memory = memory
        self._work_timer = work_timer
        self._event_poller = event_poller
        self._event_poll_task: asyncio.Task[None] | None = None
        self._work_timer_task: asyncio.Task[None] | None = None
        self._database = database
        self._store = MessageStore(database)
        self._paused = paused
        self._delivery = delivery
        self._phone = phone
        self._runner = runner
        self._background = background
        self._dreamer = dreamer
        self._action_plan = action_plan
        self._action_recovery = action_recovery
        self._agent_waits = agent_waits
        self._dream_sleep = dream_sleep
        self._work = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._dispatch_lane = dispatch_lane
        self._delivery_work = asyncio.Event()
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

    async def startup(self) -> None:
        await self._attachments.clean_spool()
        await self._runner.recover_memory()
        self._startup_ready = True
        self._event_poller.notify_changed()
        self._work.set()

    async def submit(
        self,
        submission_id: UUID,
        text: str,
        ref: object,
        uploads: tuple[WebUpload, ...],
    ) -> tuple[UUID, bool]:
        async with self._active_lock:
            if not self.events_publication_allowed():
                raise IngressUnavailable("jarvis is offline")
            result = await self._store.submit(
                submission_id,
                text,
                ref,
                uploads,
                scope=self._settings.owner_scope,
                r2_account=self._settings.attachment_r2_account_id,
                bucket=self._settings.attachment_r2_bucket,
            )
            if not result.inserted:
                return result.message.id, False
            if result.message.control_kind == "pause" and self._active_cancellation:
                self._active_cancellation.cancel()
        self._attachment_work.set()
        self.request_work()
        self.request_delivery()
        self._agent_waits.notify_wait_changed()
        self._work_timer.notify_changed()
        self._event_poller.notify_changed()
        return result.message.id, True

    async def _waits_inactive(self) -> bool:
        return await self._paused.is_paused()

    def events_publication_allowed(self) -> bool:
        return self._startup_ready and not self._shutdown.is_set()

    async def events_admitted(self) -> bool:
        """Provider work requires startup recovery and current unpaused ownership."""
        if not self.events_publication_allowed():
            return False
        return not await self._paused.is_paused()

    async def run_worker(self) -> None:
        """Run until shutdown, draining serial work and pending delivery."""

        self._attachment_work.set()
        self._attachment_task = asyncio.create_task(
            self._capture_attachments(), name="jarvis-attachment-capture"
        )
        self._attachment_task.add_done_callback(self._timer_stopped)
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
                    raise RuntimeError("the push delivery task stopped unexpectedly")
                if self._agent_wait_task.done():
                    self._agent_wait_task.result()
                    raise RuntimeError("agent wait observer stopped unexpectedly")
                await self._drain()
        finally:
            self.request_shutdown()
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
                self._attachment_task,
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._agent_wait_task = None
            self._agent_wait_cancellation = None
            self._delivery_task = None
            self._event_poll_task = None
            self._work_timer_task = None
            self._dream_timer_task = None
            self._attachment_task = None
            await self._runner.close()
            for result in results:
                if isinstance(result, Exception):
                    raise result

    async def _capture_attachments(self) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(self._attachment_work.wait(), timeout=30)
            except TimeoutError:
                pass
            self._attachment_work.clear()
            if (
                not self._shutdown.is_set()
                and await self._attachments.capture_pending()
            ):
                self.request_work()

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
        self._attachments.stop_captures()
        self._attachment_work.set()
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
        backoff = 2.0
        while not self._shutdown.is_set():
            await self._delivery_work.wait()
            self._delivery_work.clear()
            failure = await deliver_pending(
                self._database,
                self._delivery,
                self._phone,
                self._settings.delivery_batch_size,
            )
            if failure is None:
                backoff = 2.0
                continue
            delay = (
                max(backoff, failure.retry_after)
                if failure.kind == "temporary"
                else 60.0
            )
            LOGGER.warning(
                "notification pending: kind=%s status=%s retry_in=%ss",
                failure.kind,
                failure.status,
                delay,
            )
            if failure.kind == "temporary":
                backoff = min(backoff * 2, 300)
                await asyncio.sleep(delay)
            else:
                try:
                    await asyncio.wait_for(self._delivery_work.wait(), timeout=delay)
                except TimeoutError:
                    pass
            self.request_delivery()

    async def _drain(self) -> None:
        if not self._startup_ready:
            return
        while not self._shutdown.is_set():
            foreground_started = perf_counter()
            inactive = await self._paused.is_paused()
            recovered = await self._recover_actions(allow_queued_execution=not inactive)
            if inactive:
                await self._memory.publish()
                return
            if recovered:
                LOGGER.info(
                    "foreground action recovery: elapsed_ms=%.3f",
                    (perf_counter() - foreground_started) * 1000,
                )
                continue
            cancellation = CancellationToken()
            async with self._active_lock:
                if self._shutdown.is_set():
                    return
                self._active_cancellation = cancellation
            try:
                outcome = await self._runner.run(cancellation)
            finally:
                async with self._active_lock:
                    self._active_cancellation = None
            self.request_delivery()
            LOGGER.info(
                "native main completed: status=%s elapsed_ms=%.3f",
                outcome.status,
                (perf_counter() - foreground_started) * 1000,
            )
            if outcome.status in {"blocked", "stopped"}:
                return
            if outcome.status != "no_work":
                continue
            if self._work.is_set():
                return
            if self._dream_due:
                dream = await self._run_background_once(self._dreamer)
                self._dream_due = False
                if dream:
                    continue
            if await self._run_background_once(self._background):
                continue
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
            self.request_delivery()
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
            started = perf_counter()
            progressed = await worker.run_one(cancellation)
            LOGGER.info(
                "memory idle opportunity: worker=%s elapsed_ms=%.3f "
                "progressed=%s interrupted=%s",
                "dreamer" if worker is self._dreamer else "compactor",
                (perf_counter() - started) * 1000,
                progressed,
                cancellation.cancelled,
            )
            return progressed
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

"""Publish due todos independently of foreground cognition."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from jarvis.state import PausedState
from jarvis.work import WorkStore

WORK_RESCAN_SECONDS = 60.0


class WorkWakeTimer:
    def __init__(
        self,
        *,
        work: WorkStore,
        paused: PausedState,
        on_event: Callable[[], None],
    ) -> None:
        self._work = work
        self._paused = paused
        self._on_event = on_event
        self._changed = asyncio.Event()

    def notify_changed(self) -> None:
        self._changed.set()

    async def run(self) -> None:
        while True:
            self._changed.clear()
            delay = WORK_RESCAN_SECONDS
            if not await self._paused.is_paused():
                if await self._work.publish_due(datetime.now(UTC)) is not None:
                    self._on_event()
                    await asyncio.sleep(0)
                    continue
                next_due = await self._work.next_due_at()
                if next_due is not None:
                    delay = min(
                        delay, max(0.0, (next_due - datetime.now(UTC)).total_seconds())
                    )
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=delay)
            except TimeoutError:
                pass

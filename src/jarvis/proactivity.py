from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from llm_agent_kernel import CancellationToken

type _WaitResult = Literal["changed", "cancelled", "elapsed"]


class DueWakeStore(Protocol):
    async def next_due_at(self) -> datetime | None: ...


class ProcessLocalWakeTimer:
    """Signal due schedule work; PostgreSQL remains the durable scheduler."""

    def __init__(
        self,
        *,
        store: DueWakeStore,
        on_due: Callable[[], None],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._store = store
        self._on_due = on_due
        self._clock = clock
        self._sleep = sleep
        self._changed = asyncio.Event()

    def notify_changed(self) -> None:
        self._changed.set()

    async def run(self, cancellation: CancellationToken) -> None:
        while not cancellation.cancelled:
            self._changed.clear()
            execute_after = await self._store.next_due_at()
            if execute_after is None:
                if await self._wait(cancellation, None) != "changed":
                    return
                continue
            if execute_after.tzinfo is None or execute_after.utcoffset() is None:
                raise ValueError("scheduled wake timestamp must be timezone-aware")
            observed_at = self._clock()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("scheduled wake clock must be timezone-aware")
            delay = (execute_after - observed_at).total_seconds()
            if delay > 0:
                result = await self._wait(cancellation, delay)
                if result == "cancelled":
                    return
                continue
            if cancellation.cancelled:
                return
            if self._changed.is_set():
                continue
            self._on_due()
            if await self._wait(cancellation, None) != "changed":
                return

    async def _wait(
        self, cancellation: CancellationToken, delay: float | None
    ) -> _WaitResult:
        changed = asyncio.create_task(self._wait_changed())
        cancelled = asyncio.create_task(self._wait_cancelled(cancellation))
        tasks = {changed, cancelled}
        if delay is not None:
            tasks.add(asyncio.create_task(self._wait_elapsed(delay)))
        try:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        results = {task.result() for task in done}
        if "cancelled" in results:
            return "cancelled"
        if "changed" in results:
            return "changed"
        return "elapsed"

    async def _wait_changed(self) -> _WaitResult:
        await self._changed.wait()
        return "changed"

    @staticmethod
    async def _wait_cancelled(cancellation: CancellationToken) -> _WaitResult:
        await cancellation.wait()
        return "cancelled"

    async def _wait_elapsed(self, delay: float) -> _WaitResult:
        await self._sleep(delay)
        return "elapsed"


__all__ = ["DueWakeStore", "ProcessLocalWakeTimer"]

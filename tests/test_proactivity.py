from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from llm_agent_kernel import CancellationToken

from jarvis.proactivity import DueWakeSignal, ProcessLocalWakeTimer

NOW = datetime(2026, 9, 6, 18, tzinfo=UTC)


class _Store:
    def __init__(self, value: datetime | None) -> None:
        self.value = value
        self.reads = 0
        self.read = asyncio.Event()

    async def next_due_at(self) -> datetime | None:
        self.reads += 1
        self.read.set()
        return self.value


async def test_overdue_wake_signals_immediately_and_only_once() -> None:
    store = _Store(NOW - timedelta(seconds=1))
    cancellation = CancellationToken()
    signals: list[DueWakeSignal] = []

    def on_due(signal: DueWakeSignal) -> None:
        signals.append(signal)
        cancellation.cancel()

    timer = ProcessLocalWakeTimer(store=store, on_due=on_due, clock=lambda: NOW)
    await timer.run(cancellation)

    assert signals == [DueWakeSignal(NOW - timedelta(seconds=1), NOW)]
    assert signals[0].overdue
    assert store.reads == 1


async def test_exact_due_time_waits_then_signals() -> None:
    due = NOW + timedelta(seconds=30)
    store = _Store(due)
    current = NOW
    delays: list[float] = []
    cancellation = CancellationToken()
    signals: list[DueWakeSignal] = []

    async def sleep(delay: float) -> None:
        nonlocal current
        delays.append(delay)
        current = due

    def on_due(signal: DueWakeSignal) -> None:
        signals.append(signal)
        cancellation.cancel()

    timer = ProcessLocalWakeTimer(
        store=store,
        on_due=on_due,
        clock=lambda: current,
        sleep=sleep,
    )
    await timer.run(cancellation)

    assert delays == [30.0]
    assert signals == [DueWakeSignal(due, due)]
    assert not signals[0].overdue


async def test_change_preempts_obsolete_sleep() -> None:
    store = _Store(NOW + timedelta(hours=1))
    cancellation = CancellationToken()
    sleeping = asyncio.Event()
    sleep_cancelled = asyncio.Event()
    signals: list[DueWakeSignal] = []

    async def sleep(delay: float) -> None:
        assert delay == 3_600
        sleeping.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            sleep_cancelled.set()
            raise

    def on_due(signal: DueWakeSignal) -> None:
        signals.append(signal)
        cancellation.cancel()

    timer = ProcessLocalWakeTimer(
        store=store,
        on_due=on_due,
        clock=lambda: NOW,
        sleep=sleep,
    )
    task = asyncio.create_task(timer.run(cancellation))
    await sleeping.wait()
    store.value = NOW
    timer.notify_changed()
    await task

    assert sleep_cancelled.is_set()
    assert signals == [DueWakeSignal(NOW, NOW)]


async def test_no_due_wake_waits_for_change_or_cancellation() -> None:
    store = _Store(None)
    cancellation = CancellationToken()
    timer = ProcessLocalWakeTimer(store=store, on_due=lambda _signal: None)
    task = asyncio.create_task(timer.run(cancellation))
    await store.read.wait()
    cancellation.cancel()
    await task

    assert store.reads == 1


async def test_notification_reloads_next_due_wake() -> None:
    store = _Store(None)
    cancellation = CancellationToken()
    signals: list[DueWakeSignal] = []

    def on_due(signal: DueWakeSignal) -> None:
        signals.append(signal)
        cancellation.cancel()

    timer = ProcessLocalWakeTimer(store=store, on_due=on_due, clock=lambda: NOW)
    task = asyncio.create_task(timer.run(cancellation))
    await store.read.wait()
    store.value = NOW
    timer.notify_changed()
    await task

    assert store.reads == 2
    assert signals == [DueWakeSignal(NOW, NOW)]


async def test_timer_rejects_naive_store_and_clock_timestamps() -> None:
    cancellation = CancellationToken()
    naive = datetime(2026, 9, 6, 18)
    with pytest.raises(ValueError, match="timestamp must be timezone-aware"):
        await ProcessLocalWakeTimer(
            store=_Store(naive), on_due=lambda _signal: None
        ).run(cancellation)
    with pytest.raises(ValueError, match="clock must be timezone-aware"):
        await ProcessLocalWakeTimer(
            store=_Store(NOW),
            on_due=lambda _signal: None,
            clock=lambda: naive,
        ).run(cancellation)

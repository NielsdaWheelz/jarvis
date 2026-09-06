from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from llm_agent_kernel import (
    CancellationToken,
    OneShotCompleted,
    OneShotStopped,
    ProviderUsage,
    RunId,
    RunMetrics,
    ThreadStopKind,
)
from test_dreamer_role import build_test_slice4_definitions

from jarvis.definitions import DreamResult
from jarvis.memory import (
    StoredMemorySummary,
    SummaryInsertionCandidate,
    SummaryMutationBatch,
    SummaryMutationCommit,
)
from jarvis.memory_dispatch import MemoryDispatchEvidence
from jarvis.service import BackgroundDeferred, DreamerRunCompleted, DreamerWorker

NOW = datetime(2026, 9, 5, 19, tzinfo=UTC)
RESET_AT = NOW + timedelta(minutes=10)
RAW_ID = UUID("00000000-0000-4000-8000-000000000001")
CONTRADICTING_RAW_ID = UUID("00000000-0000-4000-8000-000000000004")
REMOVED_ID = UUID("00000000-0000-4000-8000-000000000002")
CREATED_ID = UUID("00000000-0000-4000-8000-000000000003")


class _Admission:
    def __init__(self, reset_at: datetime | None = None) -> None:
        self.reset_at = reset_at
        self.calls: list[tuple[int, int, int]] = []

    async def preflight_background(
        self,
        *,
        maximum_turns: int,
        maximum_input_tokens: int,
        maximum_output_tokens: int,
    ) -> datetime | None:
        self.calls.append((maximum_turns, maximum_input_tokens, maximum_output_tokens))
        return self.reset_at


class _Dispatcher:
    def __init__(self, search_calls: int = 1) -> None:
        self.evidence = MemoryDispatchEvidence((), (), search_calls)

    async def dispatch(self, **kwargs: object) -> object:
        del kwargs
        raise AssertionError("scripted worker tests do not dispatch")


class _Memory:
    def __init__(self, *, raw_count: int = 1, block_commit: bool = False) -> None:
        self.raw_count = raw_count
        self.raw_count_calls = 0
        self.batches: list[SummaryMutationBatch] = []
        self.commit_started = asyncio.Event()
        self.commit_release = asyncio.Event()
        if not block_commit:
            self.commit_release.set()

    async def raw_memory_count(self) -> int:
        self.raw_count_calls += 1
        return self.raw_count

    async def apply_summary_mutations(
        self, *, batch: SummaryMutationBatch
    ) -> SummaryMutationCommit:
        self.batches.append(batch)
        self.commit_started.set()
        await self.commit_release.wait()
        created = tuple(
            StoredMemorySummary(
                CREATED_ID,
                insertion.text,
                insertion.source_memory_ids,
                NOW,
                None,
            )
            for insertion in batch.insertions
        )
        return SummaryMutationCommit(created, batch.remove_summary_ids, NOW)


async def _worker(
    tmp_path: Path,
    *,
    memory: _Memory,
    admission: _Admission | None = None,
    search_calls: int = 1,
) -> tuple[DreamerWorker, Any]:
    definitions, _ = await build_test_slice4_definitions(tmp_path)
    return (
        DreamerWorker(
            definition=definitions.dreamer,
            plan=definitions.plans["dreamer"],
            admission=cast(Any, admission or _Admission()),
            provider=cast(Any, object()),
            dispatcher_factory=lambda: cast(Any, _Dispatcher(search_calls)),
            memory=cast(Any, memory),
        ),
        definitions,
    )


def _completed(result: dict[str, object]) -> OneShotCompleted:
    return OneShotCompleted(
        RunMetrics(RunId("dream"), 3, ProviderUsage(100, 20), 0.5, False),
        result,
    )


async def test_zero_raw_memory_skips_admission_and_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory(raw_count=0)
    admission = _Admission()
    worker, _ = await _worker(tmp_path, memory=memory, admission=admission)

    async def provider_not_called(**kwargs: object) -> object:
        del kwargs
        raise AssertionError("zero-memory dream invoked the provider")

    monkeypatch.setattr("jarvis.service.run_one_shot", provider_not_called)

    assert await worker.run_at(as_of=NOW, cancellation=CancellationToken()) is None
    assert memory.raw_count_calls == 1
    assert admission.calls == []
    assert memory.batches == []


async def test_completed_result_maps_once_to_the_atomic_host_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory()
    admission = _Admission()
    worker, definitions = await _worker(tmp_path, memory=memory, admission=admission)
    observed: dict[str, object] = {}
    result = DreamResult.model_validate(
        {
            "insertions": [
                {
                    "text": "Synthetic grounded summary.",
                    "source_memory_ids": [str(RAW_ID)],
                }
            ],
            "remove_summary_ids": [str(REMOVED_ID)],
        }
    )

    async def completed(**kwargs: object) -> OneShotCompleted:
        observed.update(kwargs)
        return _completed(result.model_dump(mode="json"))

    monkeypatch.setattr("jarvis.service.run_one_shot", completed)

    outcome = await worker.run_at(as_of=NOW, cancellation=CancellationToken())

    assert isinstance(outcome, DreamerRunCompleted)
    assert outcome.created_summary_ids == (CREATED_ID,)
    assert outcome.removed_summary_ids == (REMOVED_ID,)
    assert outcome.metrics.provider_turns == 3
    assert memory.batches == [
        SummaryMutationBatch(
            (
                SummaryInsertionCandidate(
                    "Synthetic grounded summary.",
                    (RAW_ID,),
                ),
            ),
            (REMOVED_ID,),
        )
    ]
    assert admission.calls == [(10, 160_000, 16_000)]
    assert observed["definition"] == definitions.dreamer
    assert observed["plan"] == definitions.plans["dreamer"]
    inputs = cast("tuple[Any, ...]", observed["inputs"])
    assert len(inputs) == 1
    assert inputs[0].source_timestamp == NOW
    assert inputs[0].sections.sections[0].kind == "dream_job"
    assert inputs[0].sections.sections[0].body.text == (
        "Run one bounded memory-summary maintenance pass."
    )
    assert observed["as_of"] == NOW
    assert not cast(Any, observed["source_sections"]).sections
    assert observed["admission"] is admission
    assert "messages" not in inspect.signature(DreamerWorker).parameters
    assert "actions" not in inspect.signature(DreamerWorker).parameters


async def test_completed_result_retains_contradiction_and_both_raw_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory()
    worker, _ = await _worker(tmp_path, memory=memory)
    contradictory_text = (
        "Synthetic raw memories disagree: one records the Ember review as approved; "
        "the other records it as unresolved. The current status is uncertain."
    )

    async def completed(**kwargs: object) -> OneShotCompleted:
        del kwargs
        return _completed(
            {
                "insertions": [
                    {
                        "text": contradictory_text,
                        "source_memory_ids": [
                            str(RAW_ID),
                            str(CONTRADICTING_RAW_ID),
                        ],
                    }
                ],
                "remove_summary_ids": [],
            }
        )

    monkeypatch.setattr("jarvis.service.run_one_shot", completed)

    outcome = await worker.run_at(as_of=NOW, cancellation=CancellationToken())

    assert isinstance(outcome, DreamerRunCompleted)
    assert memory.batches == [
        SummaryMutationBatch(
            (
                SummaryInsertionCandidate(
                    contradictory_text,
                    (RAW_ID, CONTRADICTING_RAW_ID),
                ),
            ),
            (),
        )
    ]


@pytest.mark.parametrize("kind", ("invalid", "failed", "exception", "cancelled"))
async def test_invalid_failed_or_cancelled_run_applies_no_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
) -> None:
    memory = _Memory()
    worker, _ = await _worker(tmp_path, memory=memory)
    cancellation = CancellationToken()

    async def result(**kwargs: object) -> OneShotCompleted | OneShotStopped:
        del kwargs
        if kind == "invalid":
            return _completed({"insertions": "not-an-array", "remove_summary_ids": []})
        if kind == "failed":
            return OneShotStopped(
                RunMetrics(RunId("dream"), 1, ProviderUsage(), 0.1, False),
                ThreadStopKind.provider_error,
            )
        if kind == "exception":
            raise RuntimeError("synthetic provider failure")
        cancellation.cancel()
        return _completed({"insertions": [], "remove_summary_ids": []})

    monkeypatch.setattr("jarvis.service.run_one_shot", result)

    assert await worker.run_at(as_of=NOW, cancellation=cancellation) is None
    assert memory.batches == []


async def test_background_preflight_defers_without_provider_or_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory()
    admission = _Admission(RESET_AT)
    worker, _ = await _worker(tmp_path, memory=memory, admission=admission)

    async def provider_not_called(**kwargs: object) -> object:
        del kwargs
        raise AssertionError("deferred dream invoked the provider")

    monkeypatch.setattr("jarvis.service.run_one_shot", provider_not_called)

    outcome = await worker.run_at(as_of=NOW, cancellation=CancellationToken())

    assert outcome == BackgroundDeferred(RESET_AT)
    assert admission.calls == [(10, 160_000, 16_000)]
    assert memory.batches == []


async def test_completed_result_without_authoritative_search_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory()
    worker, _ = await _worker(tmp_path, memory=memory, search_calls=0)

    async def completed(**kwargs: object) -> OneShotCompleted:
        del kwargs
        return _completed({"insertions": [], "remove_summary_ids": []})

    monkeypatch.setattr("jarvis.service.run_one_shot", completed)

    assert await worker.run_at(as_of=NOW, cancellation=CancellationToken()) is None
    assert memory.batches == []


async def test_foreground_interrupt_before_commit_discards_the_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory()
    worker, _ = await _worker(tmp_path, memory=memory)
    provider_started = asyncio.Event()
    provider_release = asyncio.Event()
    cancellation = CancellationToken()

    async def completed(**kwargs: object) -> OneShotCompleted:
        del kwargs
        provider_started.set()
        await provider_release.wait()
        return _completed({"insertions": [], "remove_summary_ids": []})

    monkeypatch.setattr("jarvis.service.run_one_shot", completed)
    running = asyncio.create_task(worker.run_at(as_of=NOW, cancellation=cancellation))
    await asyncio.wait_for(provider_started.wait(), timeout=1)

    worker.request_interrupt(cancellation)
    assert cancellation.cancelled
    provider_release.set()

    assert await asyncio.wait_for(running, timeout=1) is None
    assert memory.batches == []


async def test_foreground_interrupt_waits_for_atomic_commit_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory = _Memory(block_commit=True)
    worker, _ = await _worker(tmp_path, memory=memory)
    cancellation = CancellationToken()

    async def completed(**kwargs: object) -> OneShotCompleted:
        del kwargs
        return _completed(
            {
                "insertions": [
                    {
                        "text": "Synthetic grounded summary.",
                        "source_memory_ids": [str(RAW_ID)],
                    }
                ],
                "remove_summary_ids": [],
            }
        )

    monkeypatch.setattr("jarvis.service.run_one_shot", completed)
    running = asyncio.create_task(worker.run_at(as_of=NOW, cancellation=cancellation))
    await asyncio.wait_for(memory.commit_started.wait(), timeout=1)

    worker.request_interrupt(cancellation)
    assert not cancellation.cancelled
    memory.commit_release.set()

    outcome = await asyncio.wait_for(running, timeout=1)
    assert isinstance(outcome, DreamerRunCompleted)
    assert cancellation.cancelled
    assert len(memory.batches) == 1

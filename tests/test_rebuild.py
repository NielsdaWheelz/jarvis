from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest

from jarvis.memory import (
    DerivedMemoryWipe,
    MemoryIdentity,
    StoredMemory,
    StoredMemorySummary,
    StoredRawMemory,
)
from jarvis.rebuild import (
    DerivedMemoryRebuildDefect,
    DreamMutationProgress,
    RawMemorySnapshot,
    RecallQualityRegression,
    corpus_rebuild_admission_limits,
    rebuild_admission_limits,
    rebuild_derived_memory,
    rebuild_memory_corpus,
)
from jarvis.recall_evaluation import (
    SEEDED_S01_ID,
    CaseScore,
    PostRebuildSummary,
    RecallCase,
    RecallScore,
    load_recall_set,
)

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "eval" / "recall-memories.jsonl"
CASES = ROOT / "eval" / "recall.jsonl"
M11 = UUID("00000000-0000-4000-8000-000000000011")
M12 = UUID("00000000-0000-4000-8000-000000000012")
REGENERATED = UUID("20000000-0000-4000-8000-000000000001")
CREATED_AT = datetime(2026, 9, 5, 12, tzinfo=UTC)


def test_rebuild_admission_exactly_bounds_both_recall_passes_and_one_dream() -> None:
    limits = rebuild_admission_limits(17)

    assert limits.serial_child_turns == 35 * 10
    assert limits.serial_child_input_tokens == 35 * (160_000 + 32_768)
    assert limits.serial_child_output_tokens == 35 * (16_000 + 8_192)
    assert limits.max_turns == 1 + limits.serial_child_turns
    assert limits.max_input_tokens == (1 + 32_768 + limits.serial_child_input_tokens)
    assert limits.max_output_tokens == (1 + 8_192 + limits.serial_child_output_tokens)


def test_production_corpus_rebuild_admission_bounds_one_dream() -> None:
    limits = corpus_rebuild_admission_limits()

    assert limits.serial_child_turns == 10
    assert limits.serial_child_input_tokens == 160_000 + 32_768
    assert limits.serial_child_output_tokens == 16_000 + 8_192
    assert limits.max_turns == 11


def _score(cases: tuple[RecallCase, ...], passed: bool = True) -> RecallScore:
    values = tuple(
        CaseScore(
            id=case.id,
            selected_pass=passed,
            opened_pass=passed,
            search_pass=passed,
            duplicate_selected_ids=False,
            duplicate_opened_ids=False,
            passed=passed,
        )
        for case in cases
    )
    count = len(values) if passed else 0
    return RecallScore(
        cases=values,
        selected_passed=count,
        opened_passed=count,
        search_passed=count,
        passed=count,
        total=len(values),
    )


class _Embedder:
    async def embed(
        self,
        inputs: Sequence[str],
    ) -> tuple[tuple[float, ...], ...]:
        vector = (1.0, *([0.0] * 1535))
        return tuple(vector for _ in inputs)


class _Store:
    def __init__(self) -> None:
        self.raw = [
            StoredRawMemory(M11, "Synthetic Ember source one.", CREATED_AT, (1.0,)),
            StoredRawMemory(M12, "Synthetic Ember source two.", CREATED_AT, (1.0,)),
        ]
        self.summaries = [
            StoredMemorySummary(
                SEEDED_S01_ID,
                "Synthetic seeded S01.",
                (M11, M12),
                CREATED_AT,
                (1.0,),
            )
        ]
        self.lexical = True

    async def raw_snapshot(self, maximum_rows: int) -> RawMemorySnapshot:
        assert maximum_rows >= len(self.raw)
        return RawMemorySnapshot(
            len(self.raw),
            repr(tuple((item.id, item.text, item.created_at) for item in self.raw)),
        )

    async def wipe_derived_memory(self) -> DerivedMemoryWipe:
        raw_count = sum(item.embedding is not None for item in self.raw)
        summary_count = sum(item.embedding is not None for item in self.summaries)
        deleted = len(self.summaries)
        self.raw = [replace(item, embedding=None) for item in self.raw]
        self.summaries = []
        return DerivedMemoryWipe(raw_count, summary_count, deleted)

    async def prove_raw_lexical_recall(self) -> bool:
        return self.lexical

    async def select_null_embedding_candidates(
        self,
        *,
        maximum_rows: int,
    ) -> tuple[StoredMemory, ...]:
        values = [
            *[item for item in self.raw if item.embedding is None],
            *[item for item in self.summaries if item.embedding is None],
        ]
        return tuple(values[:maximum_rows])

    async def update_embedding(
        self,
        *,
        identity: MemoryIdentity,
        embedding: Sequence[float],
    ) -> StoredMemory:
        if identity.table_kind == "memory_log":
            for index, item in enumerate(self.raw):
                if item.id == identity.id:
                    self.raw[index] = replace(item, embedding=tuple(embedding))
                    return self.raw[index]
        else:
            for index, item in enumerate(self.summaries):
                if item.id == identity.id:
                    self.summaries[index] = replace(
                        item,
                        embedding=tuple(embedding),
                    )
                    return self.summaries[index]
        raise AssertionError("unknown fake memory")

    async def summary_count(self) -> int:
        return len(self.summaries)

    async def post_rebuild_summaries(
        self,
        maximum_rows: int,
    ) -> tuple[PostRebuildSummary, ...]:
        assert len(self.summaries) <= maximum_rows
        return tuple(
            PostRebuildSummary(
                id=item.id,
                source_memory_ids=item.source_memory_ids,
            )
            for item in self.summaries
        )


class _UpdateFailureStore(_Store):
    def __init__(self, table_kind: Literal["memory_log", "memory_summary"]) -> None:
        super().__init__()
        self.table_kind = table_kind
        self.update_count = 0
        self.failed = False

    async def update_embedding(
        self,
        *,
        identity: MemoryIdentity,
        embedding: Sequence[float],
    ) -> StoredMemory:
        if identity.table_kind == self.table_kind:
            self.update_count += 1
            if self.update_count == 2 and not self.failed:
                self.failed = True
                raise RuntimeError("synthetic partial embedding interruption")
        return await super().update_embedding(identity=identity, embedding=embedding)


def _raw_canonical_rows(
    store: _Store,
) -> tuple[tuple[UUID, str, datetime], ...]:
    return tuple((item.id, item.text, item.created_at) for item in store.raw)


def _assert_unique_raw_summary_lineage(store: _Store) -> None:
    raw_ids = {item.id for item in store.raw}
    lineages = tuple(frozenset(item.source_memory_ids) for item in store.summaries)
    assert all(lineage and lineage <= raw_ids for lineage in lineages)
    assert len(lineages) == len(set(lineages))
    assert lineages.count(frozenset((M11, M12))) == 1


async def test_complete_rebuild_binds_regenerated_s01_and_uses_one_as_of() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()
    evaluated: list[tuple[RecallCase, ...]] = []
    recorded: list[tuple[str, int]] = []
    dream_times: list[datetime] = []
    as_of = datetime(2026, 9, 5, 15, tzinfo=UTC)

    async def evaluate(selected: tuple[RecallCase, ...]) -> RecallScore:
        evaluated.append(selected)
        return _score(selected)

    async def dream(job_as_of: datetime) -> DreamMutationProgress:
        dream_times.append(job_as_of)
        store.summaries.append(
            StoredMemorySummary(
                REGENERATED,
                "Regenerated synthetic Ember summary.",
                (M12, M11),
                CREATED_AT,
                None,
            )
        )
        return DreamMutationProgress(1, 0)

    def record(
        phase: Literal["pre_rebuild", "post_rebuild"],
        score: RecallScore,
    ) -> None:
        recorded.append((phase, score.passed))

    result = await rebuild_derived_memory(
        store=store,
        embedder=_Embedder(),
        cases=cases,
        evaluate=evaluate,
        dream_once=dream,
        record_score=record,
        maximum_memory_rows=100,
        as_of=as_of,
    )

    assert result.pre_score.passed == 17
    assert result.post_score.passed == 17
    assert result.raw_embeddings_written == 2
    assert result.summary_embeddings_written == 1
    assert result.dreamer_runs == 1
    assert dream_times == [as_of]
    assert recorded == [("pre_rebuild", 17), ("post_rebuild", 17)]
    assert all(item.embedding is not None for item in store.raw + store.summaries)
    assert any(REGENERATED in case.must_select_ids for case in evaluated[1])
    assert all(SEEDED_S01_ID not in case.must_select_ids for case in evaluated[1])


async def test_production_corpus_rebuild_has_no_synthetic_evaluator_dependency() -> (
    None
):
    store = _Store()
    calls: list[datetime] = []

    async def dream(as_of: datetime) -> DreamMutationProgress:
        calls.append(as_of)
        store.summaries.append(
            StoredMemorySummary(
                UUID("30000000-0000-4000-8000-000000000001"),
                "Synthetic production-corpus summary.",
                (M11,),
                CREATED_AT,
                None,
            )
        )
        return DreamMutationProgress(1, 0)

    rebuilt = await rebuild_memory_corpus(
        store=store,
        embedder=_Embedder(),
        dream_once=dream,
        maximum_memory_rows=100,
        as_of=CREATED_AT,
    )

    assert rebuilt.raw_memory_count == 2
    assert rebuilt.summaries_after == 1
    assert rebuilt.dreamer_runs == 1
    assert calls == [CREATED_AT]


async def test_rebuild_records_baseline_before_a_failed_destructive_phase() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()
    store.lexical = False
    recorded: list[str] = []

    def record(
        phase: Literal["pre_rebuild", "post_rebuild"],
        score: RecallScore,
    ) -> None:
        del score
        recorded.append(phase)

    with pytest.raises(DerivedMemoryRebuildDefect, match="lexical recall"):
        await rebuild_derived_memory(
            store=store,
            embedder=_Embedder(),
            cases=cases,
            evaluate=_async_score,
            dream_once=_unexpected_dream,
            record_score=record,
            maximum_memory_rows=100,
        )

    assert recorded == ["pre_rebuild"]
    assert store.summaries == []
    assert all(item.embedding is None for item in store.raw)


async def test_rebuild_rejects_zero_or_multiple_s01_lineage_summaries() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    for count in (0, 2):
        store = _Store()

        with pytest.raises(ValueError, match="exactly one summary"):
            await rebuild_derived_memory(
                store=store,
                embedder=_Embedder(),
                cases=cases,
                evaluate=_async_score,
                dream_once=_lineage_dream(store, count),
                record_score=_record_nothing,
                maximum_memory_rows=100,
            )


async def test_rebuild_rejects_quality_regression() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()
    evaluations = 0

    async def evaluate(selected: tuple[RecallCase, ...]) -> RecallScore:
        nonlocal evaluations
        evaluations += 1
        return _score(selected, passed=evaluations == 1)

    async def dream(as_of: datetime) -> DreamMutationProgress:
        del as_of
        if not store.summaries:
            store.summaries.append(
                StoredMemorySummary(
                    REGENERATED,
                    "Synthetic regenerated summary.",
                    (M11, M12),
                    CREATED_AT,
                    None,
                )
            )
            return DreamMutationProgress(1, 0)
        return DreamMutationProgress(0, 0)

    with pytest.raises(RecallQualityRegression):
        await rebuild_derived_memory(
            store=store,
            embedder=_Embedder(),
            cases=cases,
            evaluate=evaluate,
            dream_once=dream,
            record_score=_record_nothing,
            maximum_memory_rows=100,
        )


async def test_rebuild_rejects_case_regression_hidden_by_equal_aggregates() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()
    evaluations = 0

    async def evaluate(selected: tuple[RecallCase, ...]) -> RecallScore:
        nonlocal evaluations
        failed_index = 1 if evaluations == 0 else 0
        evaluations += 1
        scored = tuple(
            CaseScore(
                id=case.id,
                selected_pass=index != failed_index,
                opened_pass=True,
                search_pass=True,
                duplicate_selected_ids=False,
                duplicate_opened_ids=False,
                passed=index != failed_index,
            )
            for index, case in enumerate(selected)
        )
        return RecallScore(
            cases=scored,
            selected_passed=len(scored) - 1,
            opened_passed=len(scored),
            search_passed=len(scored),
            passed=len(scored) - 1,
            total=len(scored),
        )

    async def dream(as_of: datetime) -> DreamMutationProgress:
        del as_of
        store.summaries.append(
            StoredMemorySummary(
                REGENERATED,
                "Synthetic regenerated summary.",
                (M11, M12),
                CREATED_AT,
                None,
            )
        )
        return DreamMutationProgress(1, 0)

    with pytest.raises(RecallQualityRegression):
        await rebuild_derived_memory(
            store=store,
            embedder=_Embedder(),
            cases=cases,
            evaluate=evaluate,
            dream_once=dream,
            record_score=_record_nothing,
            maximum_memory_rows=100,
        )


async def test_rebuild_rejects_raw_canonical_mutation_during_dreaming() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()

    async def dream(as_of: datetime) -> DreamMutationProgress:
        del as_of
        store.raw[0] = replace(store.raw[0], text="Synthetic illicit mutation.")
        return DreamMutationProgress(0, 0)

    with pytest.raises(DerivedMemoryRebuildDefect, match="raw memory identity"):
        await rebuild_derived_memory(
            store=store,
            embedder=_Embedder(),
            cases=cases,
            evaluate=_async_score,
            dream_once=dream,
            record_score=_record_nothing,
            maximum_memory_rows=100,
        )


async def test_rebuild_runs_the_dreamer_exactly_once() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()
    calls = 0

    async def dream(as_of: datetime) -> DreamMutationProgress:
        nonlocal calls
        del as_of
        calls += 1
        store.summaries.append(
            StoredMemorySummary(
                REGENERATED,
                "Synthetic regenerated summary.",
                (M11, M12),
                CREATED_AT,
                None,
            )
        )
        return DreamMutationProgress(1, 0)

    result = await rebuild_derived_memory(
        store=store,
        embedder=_Embedder(),
        cases=cases,
        evaluate=_async_score,
        dream_once=dream,
        record_score=_record_nothing,
        maximum_memory_rows=100,
    )

    assert result.dreamer_runs == 1
    assert calls == 1


async def test_interrupted_rebuild_is_safe_to_rerun_from_same_raw_rows() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    store = _Store()
    store.lexical = False

    with pytest.raises(DerivedMemoryRebuildDefect, match="lexical recall"):
        await rebuild_derived_memory(
            store=store,
            embedder=_Embedder(),
            cases=cases,
            evaluate=_async_score,
            dream_once=_unexpected_dream,
            record_score=_record_nothing,
            maximum_memory_rows=100,
        )

    store.lexical = True
    calls = 0

    async def dream(as_of: datetime) -> DreamMutationProgress:
        nonlocal calls
        del as_of
        calls += 1
        store.summaries.append(
            StoredMemorySummary(
                REGENERATED,
                "Synthetic regenerated summary.",
                (M11, M12),
                CREATED_AT,
                None,
            )
        )
        return DreamMutationProgress(1, 0)

    rebuilt = await rebuild_derived_memory(
        store=store,
        embedder=_Embedder(),
        cases=cases,
        evaluate=_async_score,
        dream_once=dream,
        record_score=_record_nothing,
        maximum_memory_rows=100,
    )

    assert rebuilt.post_score.passed == 17
    assert all(item.embedding is not None for item in store.raw + store.summaries)


async def test_partial_raw_embedding_failure_is_safe_to_rerun() -> None:
    store = _UpdateFailureStore("memory_log")
    raw_before = _raw_canonical_rows(store)
    dream_calls = 0

    async def dream(as_of: datetime) -> DreamMutationProgress:
        nonlocal dream_calls
        del as_of
        dream_calls += 1
        store.summaries.append(
            StoredMemorySummary(
                REGENERATED,
                "Synthetic regenerated summary.",
                (M11, M12),
                CREATED_AT,
                None,
            )
        )
        return DreamMutationProgress(1, 0)

    with pytest.raises(RuntimeError, match="partial embedding interruption"):
        await rebuild_memory_corpus(
            store=store,
            embedder=_Embedder(),
            dream_once=dream,
            maximum_memory_rows=100,
        )

    assert dream_calls == 0
    assert [item.embedding is not None for item in store.raw] == [True, False]
    assert store.summaries == []
    assert _raw_canonical_rows(store) == raw_before

    rebuilt = await rebuild_memory_corpus(
        store=store,
        embedder=_Embedder(),
        dream_once=dream,
        maximum_memory_rows=100,
    )

    assert rebuilt.raw_embeddings_written == 2
    assert rebuilt.summary_embeddings_written == 1
    assert dream_calls == 1
    assert all(item.embedding is not None for item in store.raw + store.summaries)
    assert _raw_canonical_rows(store) == raw_before
    _assert_unique_raw_summary_lineage(store)


async def test_interruption_after_dreamer_commit_is_safe_to_rerun() -> None:
    store = _Store()
    raw_before = _raw_canonical_rows(store)
    dream_calls = 0

    async def dream(as_of: datetime) -> DreamMutationProgress:
        nonlocal dream_calls
        del as_of
        dream_calls += 1
        store.summaries.append(
            StoredMemorySummary(
                UUID(f"20000000-0000-4000-8000-{dream_calls:012d}"),
                "Synthetic regenerated summary.",
                (M11, M12),
                CREATED_AT,
                None,
            )
        )
        if dream_calls == 1:
            raise asyncio.CancelledError
        return DreamMutationProgress(1, 0)

    with pytest.raises(asyncio.CancelledError):
        await rebuild_memory_corpus(
            store=store,
            embedder=_Embedder(),
            dream_once=dream,
            maximum_memory_rows=100,
        )

    assert len(store.summaries) == 1
    assert store.summaries[0].embedding is None
    assert all(item.embedding is not None for item in store.raw)
    assert _raw_canonical_rows(store) == raw_before
    _assert_unique_raw_summary_lineage(store)

    rebuilt = await rebuild_memory_corpus(
        store=store,
        embedder=_Embedder(),
        dream_once=dream,
        maximum_memory_rows=100,
    )

    assert rebuilt.wipe.summaries_deleted == 1
    assert rebuilt.summaries_after == 1
    assert dream_calls == 2
    assert all(item.embedding is not None for item in store.raw + store.summaries)
    assert _raw_canonical_rows(store) == raw_before
    _assert_unique_raw_summary_lineage(store)


async def test_partial_summary_embedding_failure_is_safe_to_rerun() -> None:
    store = _UpdateFailureStore("memory_summary")
    raw_before = _raw_canonical_rows(store)
    dream_calls = 0

    async def dream(as_of: datetime) -> DreamMutationProgress:
        nonlocal dream_calls
        del as_of
        dream_calls += 1
        store.summaries.extend(
            (
                StoredMemorySummary(
                    UUID(f"30000000-0000-4000-8000-{dream_calls:012d}"),
                    "Synthetic regenerated Ember summary.",
                    (M11, M12),
                    CREATED_AT,
                    None,
                ),
                StoredMemorySummary(
                    UUID(f"40000000-0000-4000-8000-{dream_calls:012d}"),
                    "Synthetic regenerated source summary.",
                    (M11,),
                    CREATED_AT,
                    None,
                ),
            )
        )
        return DreamMutationProgress(2, 0)

    with pytest.raises(RuntimeError, match="partial embedding interruption"):
        await rebuild_memory_corpus(
            store=store,
            embedder=_Embedder(),
            dream_once=dream,
            maximum_memory_rows=100,
        )

    assert [item.embedding is not None for item in store.summaries] == [True, False]
    assert all(item.embedding is not None for item in store.raw)
    assert _raw_canonical_rows(store) == raw_before
    _assert_unique_raw_summary_lineage(store)

    rebuilt = await rebuild_memory_corpus(
        store=store,
        embedder=_Embedder(),
        dream_once=dream,
        maximum_memory_rows=100,
    )

    assert rebuilt.wipe.summaries_deleted == 2
    assert rebuilt.summaries_after == 2
    assert rebuilt.summary_embeddings_written == 2
    assert dream_calls == 2
    assert all(item.embedding is not None for item in store.raw + store.summaries)
    assert _raw_canonical_rows(store) == raw_before
    _assert_unique_raw_summary_lineage(store)


async def _async_score(cases: tuple[RecallCase, ...]) -> RecallScore:
    return _score(cases)


async def _unexpected_dream(as_of: datetime) -> DreamMutationProgress:
    del as_of
    raise AssertionError("dreamer should not run")


def _record_nothing(
    phase: Literal["pre_rebuild", "post_rebuild"],
    score: RecallScore,
) -> None:
    del phase, score


def _lineage_dream(
    store: _Store,
    count: int,
) -> Callable[[datetime], Awaitable[DreamMutationProgress]]:
    calls = 0

    async def dream(as_of: datetime) -> DreamMutationProgress:
        nonlocal calls
        del as_of
        calls += 1
        if calls == 1:
            store.summaries.extend(
                StoredMemorySummary(
                    UUID(f"20000000-0000-4000-8000-{index:012d}"),
                    "Synthetic regenerated summary.",
                    (M11, M12),
                    CREATED_AT,
                    None,
                )
                for index in range(1, count + 1)
            )
            return DreamMutationProgress(count, 0)
        return DreamMutationProgress(0, 0)

    return dream

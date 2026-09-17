"""Stopped, bounded reconstruction of all derived memory state."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from sqlalchemy import select, text

from jarvis.admission import RollingAdmissionLimits
from jarvis.db import memory_log, memory_summary
from jarvis.definitions import (
    DREAMER_KERNEL_LIMITS,
    RECALLER_KERNEL_LIMITS,
)
from jarvis.embeddings import MAX_EMBEDDING_BATCH_SIZE
from jarvis.memory import (
    DerivedMemoryWipe,
    MemoryIdentity,
    MemoryStore,
    StoredMemory,
)
from jarvis.memory_retrieval import MemoryEmbedder
from jarvis.ownership import Database
from jarvis.recall_evaluation import (
    PostRebuildSummary,
    RecallCase,
    RecallScore,
    bind_post_rebuild_s01,
)
from jarvis.settings import EMBEDDING_DIMENSION

type RecallEvaluator = Callable[[tuple[RecallCase, ...]], Awaitable[RecallScore]]
type ScoreRecorder = Callable[
    [Literal["pre_rebuild", "post_rebuild"], RecallScore], None
]
type DreamOnce = Callable[[datetime], Awaitable[DreamMutationProgress]]

_INPUT_TOKEN_OVERSHOOT = 32_768
_OUTPUT_TOKEN_OVERSHOOT = 8_192


class DerivedMemoryRebuildDefect(RuntimeError):
    """The stopped rebuild could not establish a complete derived corpus."""


class RecallQualityRegression(DerivedMemoryRebuildDefect):
    """The post-rebuild frozen recall result is worse than its baseline."""

    def __init__(self, pre_score: RecallScore, post_score: RecallScore) -> None:
        super().__init__("post-rebuild recall score is worse than its baseline")
        self.pre_score = pre_score
        self.post_score = post_score


@dataclass(frozen=True, slots=True)
class DreamMutationProgress:
    inserted: int
    removed: int

    def __post_init__(self) -> None:
        if (
            type(self.inserted) is not int
            or self.inserted < 0
            or type(self.removed) is not int
            or self.removed < 0
        ):
            raise ValueError("dream mutation counts must be non-negative integers")


@dataclass(frozen=True, slots=True)
class RawMemorySnapshot:
    count: int
    digest: str


@dataclass(frozen=True, slots=True)
class DerivedMemoryCorpusRebuild:
    as_of: datetime
    raw_memory_count: int
    wipe: DerivedMemoryWipe
    lexical_raw_recall_proved: bool
    raw_embeddings_written: int
    dreamer_runs: int
    summaries_inserted: int
    summaries_removed: int
    summaries_after: int
    summary_embeddings_written: int


@dataclass(frozen=True, slots=True)
class DerivedMemoryRebuild(DerivedMemoryCorpusRebuild):
    pre_score: RecallScore
    post_score: RecallScore


class _RebuildStore(Protocol):
    async def raw_snapshot(self, maximum_rows: int) -> RawMemorySnapshot: ...

    async def wipe_derived_memory(self) -> DerivedMemoryWipe: ...

    async def prove_raw_lexical_recall(self) -> bool: ...

    async def select_null_embedding_candidates(
        self, *, maximum_rows: int
    ) -> tuple[StoredMemory, ...]: ...

    async def update_embedding(
        self, *, identity: MemoryIdentity, embedding: Sequence[float]
    ) -> StoredMemory: ...

    async def summary_count(self) -> int: ...

    async def post_rebuild_summaries(
        self, maximum_rows: int
    ) -> tuple[PostRebuildSummary, ...]: ...


class PostgresRebuildStore:
    def __init__(self, engine: Database) -> None:
        self._engine = engine
        self._memory = MemoryStore(engine)

    async def raw_snapshot(self, maximum_rows: int) -> RawMemorySnapshot:
        rows = ()
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        memory_log.c.id,
                        memory_log.c.text,
                        memory_log.c.created_at,
                    )
                    .order_by(memory_log.c.id)
                    .limit(maximum_rows + 1)
                )
            ).all()
        if len(rows) > maximum_rows:
            raise DerivedMemoryRebuildDefect(
                "raw memory exceeds the configured rebuild bound"
            )
        digest = hashlib.sha256()
        for row in rows:
            created_at = cast(datetime, row.created_at)
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise DerivedMemoryRebuildDefect(
                    "raw memory contains a non-aware creation time"
                )
            for part in (
                row.id.bytes,
                cast(str, row.text).encode(),
                created_at.astimezone(UTC).isoformat(timespec="microseconds").encode(),
            ):
                digest.update(len(part).to_bytes(8, byteorder="big"))
                digest.update(part)
        return RawMemorySnapshot(len(rows), digest.hexdigest())

    async def wipe_derived_memory(self) -> DerivedMemoryWipe:
        return await self._memory.wipe_derived_memory()

    async def prove_raw_lexical_recall(self) -> bool:
        async with self._engine.connect() as connection:
            witness = (
                await connection.execute(
                    text(
                        "SELECT id, "
                        "(tsvector_to_array(to_tsvector("
                        "'simple'::regconfig, text)))[1] "
                        "AS lexeme FROM memory_log "
                        "WHERE cardinality(tsvector_to_array("
                        "to_tsvector('simple'::regconfig, text))) > 0 "
                        "ORDER BY id LIMIT 1"
                    )
                )
            ).one_or_none()
            if witness is None:
                return False
            return bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM memory_log "
                        "WHERE id = :memory_id AND "
                        "to_tsvector('simple'::regconfig, text) @@ "
                        "plainto_tsquery('simple'::regconfig, :lexeme))"
                    ),
                    {"memory_id": witness.id, "lexeme": witness.lexeme},
                )
            )

    async def select_null_embedding_candidates(
        self, *, maximum_rows: int
    ) -> tuple[StoredMemory, ...]:
        return await self._memory.select_null_embedding_candidates(
            maximum_rows=maximum_rows
        )

    async def update_embedding(
        self, *, identity: MemoryIdentity, embedding: Sequence[float]
    ) -> StoredMemory:
        return await self._memory.update_embedding(
            identity=identity,
            embedding=embedding,
        )

    async def summary_count(self) -> int:
        return await self._memory.summary_count()

    async def post_rebuild_summaries(
        self, maximum_rows: int
    ) -> tuple[PostRebuildSummary, ...]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        memory_summary.c.id,
                        memory_summary.c.source_memory_ids,
                    )
                    .order_by(memory_summary.c.id)
                    .limit(maximum_rows + 1)
                )
            ).all()
        if len(rows) > maximum_rows:
            raise DerivedMemoryRebuildDefect(
                "summary memory exceeds the configured rebuild bound"
            )
        return tuple(
            PostRebuildSummary(
                id=row.id,
                source_memory_ids=tuple(row.source_memory_ids),
            )
            for row in rows
        )


def rebuild_admission_limits(
    case_count: int,
) -> RollingAdmissionLimits:
    """Reserve two recall passes and one serial Dreamer run under one root."""
    _positive(case_count, "rebuild recall case count")
    recall_runs = case_count * 2
    serial_turns = (
        recall_runs * RECALLER_KERNEL_LIMITS.max_provider_turns
        + DREAMER_KERNEL_LIMITS.max_provider_turns
    )
    serial_input = recall_runs * (
        RECALLER_KERNEL_LIMITS.max_provider_input_tokens + _INPUT_TOKEN_OVERSHOOT
    ) + (DREAMER_KERNEL_LIMITS.max_provider_input_tokens + _INPUT_TOKEN_OVERSHOOT)
    serial_output = recall_runs * (
        RECALLER_KERNEL_LIMITS.max_provider_output_tokens + _OUTPUT_TOKEN_OVERSHOOT
    ) + (DREAMER_KERNEL_LIMITS.max_provider_output_tokens + _OUTPUT_TOKEN_OVERSHOOT)
    return RollingAdmissionLimits(
        max_turns=1 + serial_turns,
        max_input_tokens=1 + _INPUT_TOKEN_OVERSHOOT + serial_input,
        max_output_tokens=1 + _OUTPUT_TOKEN_OVERSHOOT + serial_output,
        serial_child_turns=serial_turns,
        serial_child_input_tokens=serial_input,
        serial_child_output_tokens=serial_output,
    )


def corpus_rebuild_admission_limits() -> RollingAdmissionLimits:
    """Reserve one stopped production rebuild and its one Dreamer child."""
    serial_turns = DREAMER_KERNEL_LIMITS.max_provider_turns
    serial_input = (
        DREAMER_KERNEL_LIMITS.max_provider_input_tokens + _INPUT_TOKEN_OVERSHOOT
    )
    serial_output = (
        DREAMER_KERNEL_LIMITS.max_provider_output_tokens + _OUTPUT_TOKEN_OVERSHOOT
    )
    return RollingAdmissionLimits(
        max_turns=1 + serial_turns,
        max_input_tokens=1 + _INPUT_TOKEN_OVERSHOOT + serial_input,
        max_output_tokens=1 + _OUTPUT_TOKEN_OVERSHOOT + serial_output,
        serial_child_turns=serial_turns,
        serial_child_input_tokens=serial_input,
        serial_child_output_tokens=serial_output,
    )


async def rebuild_derived_memory(
    *,
    store: _RebuildStore,
    embedder: MemoryEmbedder,
    cases: tuple[RecallCase, ...],
    evaluate: RecallEvaluator,
    dream_once: DreamOnce,
    record_score: ScoreRecorder,
    maximum_memory_rows: int,
    as_of: datetime | None = None,
) -> DerivedMemoryRebuild:
    """Rebuild one frozen qualification corpus and enforce its recall gate."""
    _positive(maximum_memory_rows, "maximum rebuild memory rows")
    job_as_of = as_of or datetime.now(UTC)
    if job_as_of.tzinfo is None or job_as_of.utcoffset() is None:
        raise ValueError("rebuild as_of must be timezone-aware")

    pre_score = await evaluate(cases)
    _validate_score(cases, pre_score)
    record_score("pre_rebuild", pre_score)
    raw_before = await store.raw_snapshot(maximum_memory_rows)

    rebuilt = await rebuild_memory_corpus(
        store=store,
        embedder=embedder,
        dream_once=dream_once,
        maximum_memory_rows=maximum_memory_rows,
        as_of=job_as_of,
    )

    summaries = await store.post_rebuild_summaries(maximum_memory_rows)
    post_cases = bind_post_rebuild_s01(cases, summaries)
    post_score = await evaluate(post_cases)
    _validate_score(post_cases, post_score)
    record_score("post_rebuild", post_score)
    await _require_raw_unchanged(store, raw_before, maximum_memory_rows)
    aggregate_regression = any(
        getattr(post_score, field) < getattr(pre_score, field)
        for field in ("selected_passed", "opened_passed", "search_passed", "passed")
    )
    case_regression = any(
        getattr(pre_case, field) and not getattr(post_case, field)
        for pre_case, post_case in zip(
            pre_score.cases,
            post_score.cases,
            strict=True,
        )
        for field in ("selected_pass", "opened_pass", "search_pass", "passed")
    )
    if aggregate_regression or case_regression:
        raise RecallQualityRegression(pre_score, post_score)

    return DerivedMemoryRebuild(
        as_of=rebuilt.as_of,
        raw_memory_count=rebuilt.raw_memory_count,
        wipe=rebuilt.wipe,
        lexical_raw_recall_proved=rebuilt.lexical_raw_recall_proved,
        raw_embeddings_written=rebuilt.raw_embeddings_written,
        dreamer_runs=rebuilt.dreamer_runs,
        summaries_inserted=rebuilt.summaries_inserted,
        summaries_removed=rebuilt.summaries_removed,
        summaries_after=rebuilt.summaries_after,
        summary_embeddings_written=rebuilt.summary_embeddings_written,
        pre_score=pre_score,
        post_score=post_score,
    )


async def rebuild_memory_corpus(
    *,
    store: _RebuildStore,
    embedder: MemoryEmbedder,
    dream_once: DreamOnce,
    maximum_memory_rows: int,
    as_of: datetime | None = None,
) -> DerivedMemoryCorpusRebuild:
    """Rebuild one real corpus while the caller holds deployment ownership."""
    _positive(maximum_memory_rows, "maximum rebuild memory rows")
    job_as_of = as_of or datetime.now(UTC)
    if job_as_of.tzinfo is None or job_as_of.utcoffset() is None:
        raise ValueError("rebuild as_of must be timezone-aware")

    raw_before = await store.raw_snapshot(maximum_memory_rows)
    if raw_before.count == 0:
        raise DerivedMemoryRebuildDefect(
            "a full recall-qualified rebuild requires raw memory"
        )
    wipe = await store.wipe_derived_memory()
    await _require_raw_unchanged(store, raw_before, maximum_memory_rows)
    if not await store.prove_raw_lexical_recall():
        raise DerivedMemoryRebuildDefect(
            "raw lexical recall did not survive the derived-memory wipe"
        )

    raw_embeddings_written = await _embed_all_null(
        store=store,
        embedder=embedder,
        expected_table_kind="memory_log",
        maximum_rows=maximum_memory_rows,
    )
    if raw_embeddings_written != raw_before.count:
        raise DerivedMemoryRebuildDefect(
            "raw embedding rebuild did not cover every raw memory"
        )
    await _require_raw_unchanged(store, raw_before, maximum_memory_rows)

    progress = await dream_once(job_as_of)
    await _require_raw_unchanged(store, raw_before, maximum_memory_rows)
    if await store.summary_count() > maximum_memory_rows:
        raise DerivedMemoryRebuildDefect(
            "summary memory exceeds the configured rebuild bound"
        )

    summaries = await store.post_rebuild_summaries(maximum_memory_rows)
    summary_embeddings_written = await _embed_all_null(
        store=store,
        embedder=embedder,
        expected_table_kind="memory_summary",
        maximum_rows=maximum_memory_rows,
    )
    if summary_embeddings_written != len(summaries):
        raise DerivedMemoryRebuildDefect(
            "summary embedding rebuild did not cover every regenerated summary"
        )
    await _require_raw_unchanged(store, raw_before, maximum_memory_rows)

    return DerivedMemoryCorpusRebuild(
        as_of=job_as_of,
        raw_memory_count=raw_before.count,
        wipe=wipe,
        lexical_raw_recall_proved=True,
        raw_embeddings_written=raw_embeddings_written,
        dreamer_runs=1,
        summaries_inserted=progress.inserted,
        summaries_removed=progress.removed,
        summaries_after=len(summaries),
        summary_embeddings_written=summary_embeddings_written,
    )


async def _embed_all_null(
    *,
    store: _RebuildStore,
    embedder: MemoryEmbedder,
    expected_table_kind: Literal["memory_log", "memory_summary"],
    maximum_rows: int,
) -> int:
    written = 0
    while True:
        remaining = maximum_rows - written
        rows = await store.select_null_embedding_candidates(
            maximum_rows=min(MAX_EMBEDDING_BATCH_SIZE, max(1, remaining))
        )
        if not rows:
            return written
        if remaining <= 0 or len(rows) > remaining:
            raise DerivedMemoryRebuildDefect(
                "null embeddings exceed the configured rebuild bound"
            )
        if any(row.identity.table_kind != expected_table_kind for row in rows):
            raise DerivedMemoryRebuildDefect(
                "embedding rebuild phases contain inconsistent memory kinds"
            )
        vectors = await embedder.embed(tuple(row.text for row in rows))
        if len(vectors) != len(rows) or any(
            len(vector) != EMBEDDING_DIMENSION
            or not all(math.isfinite(component) for component in vector)
            or not any(component != 0.0 for component in vector)
            for vector in vectors
        ):
            raise DerivedMemoryRebuildDefect(
                "embedding provider returned invalid rebuild vectors"
            )
        for row, vector in zip(rows, vectors, strict=True):
            await store.update_embedding(identity=row.identity, embedding=vector)
        written += len(rows)


async def _require_raw_unchanged(
    store: _RebuildStore,
    expected: RawMemorySnapshot,
    maximum_rows: int,
) -> None:
    if await store.raw_snapshot(maximum_rows) != expected:
        raise DerivedMemoryRebuildDefect(
            "raw memory identity, text, or creation time changed during rebuild"
        )


def _validate_score(cases: tuple[RecallCase, ...], score: RecallScore) -> None:
    expected_ids = tuple(case.id for case in cases)
    if tuple(item.id for item in score.cases) != expected_ids or score.total != len(
        cases
    ):
        raise DerivedMemoryRebuildDefect(
            "recall evaluator did not return the complete frozen case set"
        )
    actual = (
        sum(item.selected_pass for item in score.cases),
        sum(item.opened_pass for item in score.cases),
        sum(item.search_pass for item in score.cases),
        sum(item.passed for item in score.cases),
    )
    reported = (
        score.selected_passed,
        score.opened_passed,
        score.search_passed,
        score.passed,
    )
    if reported != actual:
        raise DerivedMemoryRebuildDefect(
            "recall evaluator returned inconsistent aggregate counts"
        )


def _positive(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


__all__ = [
    "DerivedMemoryCorpusRebuild",
    "DerivedMemoryRebuild",
    "DerivedMemoryRebuildDefect",
    "DreamMutationProgress",
    "PostgresRebuildStore",
    "RawMemorySnapshot",
    "RecallEvaluator",
    "RecallQualityRegression",
    "ScoreRecorder",
    "corpus_rebuild_admission_limits",
    "rebuild_admission_limits",
    "rebuild_derived_memory",
    "rebuild_memory_corpus",
]

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import action, create_engine, memory_log, memory_summary, message
from jarvis.memory import (
    MemoryPersistenceDefect,
    MemoryStore,
    SummaryInsertionCandidate,
    SummaryMutationBatch,
)

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
MIGRATION_DATABASE_URL = os.environ.get("JARVIS_TEST_MIGRATION_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="JARVIS_TEST_DATABASE_URL is not configured",
    ),
]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


async def _raw(
    engine: AsyncEngine,
    marker: str,
    *,
    embedded: bool = False,
) -> UUID:
    identifier = uuid4()
    values: dict[str, object] = {
        "id": identifier,
        "text": f"Synthetic raw memory {marker} {identifier}.",
    }
    if embedded:
        values["embedding"] = [1.0, *([0.0] * 1535)]
    async with engine.begin() as connection:
        await connection.execute(insert(memory_log).values(**values))
    return identifier


async def _counts(engine: AsyncEngine) -> tuple[int, int, int, int]:
    async with engine.connect() as connection:
        values = [
            await connection.scalar(select(func.count()).select_from(table))
            for table in (memory_log, memory_summary, message, action)
        ]
    assert all(value is not None for value in values)
    return cast(tuple[int, int, int, int], tuple(values))


def _candidate(marker: str, *source_ids: UUID) -> SummaryInsertionCandidate:
    return SummaryInsertionCandidate(
        text=f"Synthetic summary {marker} {uuid4()}.",
        source_memory_ids=tuple(source_ids),
    )


async def test_empty_batch_is_a_valid_atomic_noop(engine: AsyncEngine) -> None:
    store = MemoryStore(engine)
    before = await _counts(engine)
    committed_at = datetime(2026, 9, 5, 12, tzinfo=UTC)

    result = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((), ()),
        committed_at=committed_at,
    )

    assert result.created == ()
    assert result.removed_summary_ids == ()
    assert result.committed_at == committed_at
    assert await _counts(engine) == before


async def test_insertion_only_persists_raw_lineage_and_null_embedding(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    first = await _raw(engine, "insertion-first")
    second = await _raw(engine, "insertion-second")
    committed_at = datetime(2026, 9, 5, 13, tzinfo=UTC)
    before = await _counts(engine)
    candidate = _candidate("insertion-only", first, second)

    result = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((candidate,), ()),
        committed_at=committed_at,
    )

    assert len(result.created) == 1
    assert result.created[0].text == candidate.text
    assert result.created[0].source_memory_ids == tuple(sorted((first, second)))
    assert result.created[0].created_at == committed_at
    assert result.created[0].embedding is None
    assert await _counts(engine) == (
        before[0],
        before[1] + 1,
        before[2],
        before[3],
    )


async def test_removal_only_deletes_summary_and_preserves_raw_memory(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "removal-only")
    created = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("removed", raw_id),), ()),
    )
    summary_id = created.created[0].id

    result = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((), (summary_id,))
    )

    assert result.created == ()
    assert result.removed_summary_ids == (summary_id,)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                select(memory_summary.c.id).where(memory_summary.c.id == summary_id)
            )
            is None
        )
        assert (
            await connection.scalar(
                select(memory_log.c.id).where(memory_log.c.id == raw_id)
            )
            == raw_id
        )


async def test_replacement_and_mixed_batch_commit_as_one_change(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_ids = tuple([await _raw(engine, f"mixed-{index}") for index in range(3)])
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch(
            (
                _candidate("existing-one", raw_ids[0]),
                _candidate("existing-two", raw_ids[1]),
            ),
            (),
        )
    )
    replacement = _candidate("replacement", raw_ids[0], raw_ids[1])
    additional = _candidate("additional", raw_ids[2])

    result = await store.apply_summary_mutations(
        batch=SummaryMutationBatch(
            (replacement, additional),
            (existing.created[0].id, existing.created[1].id),
        )
    )

    assert result.removed_summary_ids == tuple(item.id for item in existing.created)
    assert tuple(item.text for item in result.created) == (
        replacement.text,
        additional.text,
    )
    async with engine.connect() as connection:
        stored = (
            (
                await connection.execute(
                    select(memory_summary).where(
                        memory_summary.c.id.in_(
                            (
                                *result.removed_summary_ids,
                                *(item.id for item in result.created),
                            )
                        )
                    )
                )
            )
            .mappings()
            .all()
        )
    assert {row.id for row in stored} == {item.id for item in result.created}
    async with engine.connect() as connection:
        preserved_raw_ids = set(
            (
                await connection.execute(
                    select(memory_log.c.id).where(memory_log.c.id.in_(raw_ids))
                )
            ).scalars()
        )
    assert preserved_raw_ids == set(raw_ids)


async def test_invalid_batch_is_rejected_whole(engine: AsyncEngine) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "invalid-batch")
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("invalid-existing", raw_id),), ())
    )
    summary_id = existing.created[0].id
    before = await _counts(engine)

    invalid_batches = (
        SummaryMutationBatch((SummaryInsertionCandidate(" ", (raw_id,)),), ()),
        SummaryMutationBatch((SummaryInsertionCandidate("x" * 8_001, (raw_id,)),), ()),
        SummaryMutationBatch((SummaryInsertionCandidate("é" * 4_001, (raw_id,)),), ()),
        SummaryMutationBatch((SummaryInsertionCandidate("empty lineage", ()),), ()),
        SummaryMutationBatch(
            (SummaryInsertionCandidate("duplicate lineage", (raw_id, raw_id)),), ()
        ),
        SummaryMutationBatch(
            (
                SummaryInsertionCandidate("duplicate summary", (raw_id,)),
                SummaryInsertionCandidate("duplicate summary", (raw_id,)),
            ),
            (),
        ),
        SummaryMutationBatch(
            (
                SummaryInsertionCandidate(
                    "malformed lineage",
                    cast(tuple[UUID, ...], ("not-a-uuid",)),
                ),
            ),
            (),
        ),
        SummaryMutationBatch(
            (),
            cast(tuple[UUID, ...], ("not-a-uuid",)),
        ),
        SummaryMutationBatch((), (summary_id, summary_id)),
        SummaryMutationBatch(
            tuple(
                SummaryInsertionCandidate(f"bounded summary {index}", (raw_id,))
                for index in range(51)
            ),
            (),
        ),
        SummaryMutationBatch(
            (
                SummaryInsertionCandidate(
                    "over-bound lineage",
                    tuple(uuid4() for _ in range(101)),
                ),
            ),
            (),
        ),
        SummaryMutationBatch((), tuple(uuid4() for _ in range(101))),
    )
    for batch in invalid_batches:
        with pytest.raises(ValueError):
            await store.apply_summary_mutations(batch=batch)
    assert await _counts(engine) == before


async def test_summary_valued_missing_and_stale_lineage_are_rejected_whole(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "lineage")
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("lineage-existing", raw_id),), ())
    )
    summary_id = existing.created[0].id
    before = await _counts(engine)

    with pytest.raises(MemoryPersistenceDefect, match="summary identity"):
        await store.apply_summary_mutations(
            batch=SummaryMutationBatch(
                (_candidate("summary-valued", summary_id),),
                (summary_id,),
            )
        )
    with pytest.raises(MemoryPersistenceDefect, match="missing memory lineage"):
        await store.apply_summary_mutations(
            batch=SummaryMutationBatch(
                (_candidate("missing-lineage", uuid4()),),
                (summary_id,),
            )
        )
    with pytest.raises(MemoryPersistenceDefect, match="stale summary removal"):
        await store.apply_summary_mutations(
            batch=SummaryMutationBatch((_candidate("valid", raw_id),), (uuid4(),))
        )
    assert await _counts(engine) == before
    assert await store.summary_count() >= 1


async def test_duplicate_existing_summary_and_secret_reject_without_leakage(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "secret")
    safe = _candidate("duplicate-existing", raw_id)
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((safe,), ())
    )
    before = await _counts(engine)

    with pytest.raises(MemoryPersistenceDefect, match="duplicates existing"):
        await store.apply_summary_mutations(
            batch=SummaryMutationBatch(
                (SummaryInsertionCandidate(safe.text, (raw_id,)),), ()
            )
        )

    secrets = (
        "-----BEGIN " + "PRIVATE KEY-----\nsynthetic-value\n-----END",
        "sk-" + "A" * 24,
    )
    for secret in secrets:
        with pytest.raises(ValueError) as raised:
            await store.apply_summary_mutations(
                batch=SummaryMutationBatch(
                    (
                        _candidate("safe-sibling", raw_id),
                        SummaryInsertionCandidate(secret, (raw_id,)),
                    ),
                    (existing.created[0].id,),
                )
            )
        assert secret not in str(raised.value)
    assert await _counts(engine) == before


async def test_exact_lineage_duplicates_reject_whole_and_replacement_succeeds(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    first = await _raw(engine, "duplicate-lineage-first")
    second = await _raw(engine, "duplicate-lineage-second")
    third = await _raw(engine, "duplicate-lineage-third")
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("existing-lineage", second, first),), ())
    )
    existing_id = existing.created[0].id
    before = await _counts(engine)

    with pytest.raises(ValueError, match="duplicate summary lineage"):
        await store.apply_summary_mutations(
            batch=SummaryMutationBatch(
                (
                    _candidate("batch-lineage-one", first, second),
                    _candidate("batch-lineage-two", second, first),
                ),
                (existing_id,),
            )
        )
    with pytest.raises(MemoryPersistenceDefect, match="existing summary lineage"):
        await store.apply_summary_mutations(
            batch=SummaryMutationBatch(
                (
                    _candidate("existing-lineage-copy", first, second),
                    _candidate("novel-lineage", third),
                ),
                (),
            )
        )
    assert await _counts(engine) == before

    replacement = _candidate("replacement-lineage", first, second)
    committed = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((replacement,), (existing_id,))
    )

    assert committed.removed_summary_ids == (existing_id,)
    assert len(committed.created) == 1
    assert committed.created[0].source_memory_ids == tuple(sorted((first, second)))
    assert await _counts(engine) == before


async def test_database_failure_after_delete_rolls_back_the_complete_batch(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "rollback")
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("rollback-existing", raw_id),), ())
    )
    summary_id = existing.created[0].id
    before = await _counts(engine)
    candidate = _candidate("rollback-new", raw_id)

    original_execute = cast(Any, engine.sync_engine.dialect.do_execute)

    def interrupted_execute(
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any = None,
    ) -> None:
        if statement.startswith("INSERT INTO memory_summary"):
            raise RuntimeError("synthetic insertion interruption")
        original_execute(cursor, statement, parameters, context)

    engine.sync_engine.dialect.do_execute = interrupted_execute
    try:
        with pytest.raises(RuntimeError, match="synthetic insertion interruption"):
            await store.apply_summary_mutations(
                batch=SummaryMutationBatch((candidate,), (summary_id,))
            )
    finally:
        engine.sync_engine.dialect.do_execute = original_execute

    assert await _counts(engine) == before
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                select(memory_summary.c.id).where(memory_summary.c.id == summary_id)
            )
            == summary_id
        )


async def test_cancelled_database_statement_rolls_back_replacement(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "cancel")
    existing = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("cancel-existing", raw_id),), ())
    )
    summary_id = existing.created[0].id
    original_execute = cast(Any, engine.sync_engine.dialect.do_execute)

    def cancelled_execute(
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any = None,
    ) -> None:
        if statement.startswith("INSERT INTO memory_summary"):
            raise asyncio.CancelledError
        original_execute(cursor, statement, parameters, context)

    engine.sync_engine.dialect.do_execute = cancelled_execute
    try:
        with pytest.raises(asyncio.CancelledError):
            await store.apply_summary_mutations(
                batch=SummaryMutationBatch(
                    (_candidate("cancel-new", raw_id),),
                    (summary_id,),
                )
            )
    finally:
        engine.sync_engine.dialect.do_execute = original_execute

    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                select(memory_summary.c.id).where(memory_summary.c.id == summary_id)
            )
            == summary_id
        )


@pytest.mark.parametrize(
    "failed_statement",
    (
        "UPDATE memory_summary SET embedding",
        "UPDATE memory_log SET embedding",
        "DELETE FROM memory_summary",
    ),
)
async def test_wipe_failure_at_each_mutation_boundary_rolls_back_everything(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    failed_statement: str,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, f"wipe-rollback-{failed_statement}", embedded=True)
    created = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((_candidate("wipe-rollback", raw_id),), ())
    )
    summary_id = created.created[0].id
    await store.update_embedding(
        identity=created.created[0].identity,
        embedding=[1.0, *([0.0] * 1535)],
    )
    original_execute = cast(Any, engine.sync_engine.dialect.do_execute)

    def interrupted_execute(
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any = None,
    ) -> None:
        if statement.startswith(failed_statement):
            raise RuntimeError("synthetic wipe interruption")
        original_execute(cursor, statement, parameters, context)

    monkeypatch.setattr(engine.sync_engine.dialect, "do_execute", interrupted_execute)
    with pytest.raises(RuntimeError, match="synthetic wipe interruption"):
        await store.wipe_derived_memory()

    async with engine.connect() as connection:
        raw_embedding = await connection.scalar(
            select(memory_log.c.embedding).where(memory_log.c.id == raw_id)
        )
        summary_embedding = await connection.scalar(
            select(memory_summary.c.embedding).where(memory_summary.c.id == summary_id)
        )
        stored_summary_id = await connection.scalar(
            select(memory_summary.c.id).where(memory_summary.c.id == summary_id)
        )
    assert raw_embedding is not None
    assert summary_embedding is not None
    assert stored_summary_id == summary_id


async def test_wipe_clears_derived_state_without_mutating_raw_canonical_fields(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    raw_id = await _raw(engine, "wipe", embedded=True)
    async with engine.connect() as connection:
        raw_before = (
            (
                await connection.execute(
                    select(memory_log).where(memory_log.c.id == raw_id)
                )
            )
            .mappings()
            .one()
        )
    candidate = _candidate("wipe", raw_id)
    created = await store.apply_summary_mutations(
        batch=SummaryMutationBatch((candidate,), ())
    )
    await store.update_embedding(
        identity=created.created[0].identity,
        embedding=[1.0, *([0.0] * 1535)],
    )

    result = await store.wipe_derived_memory()

    assert result.raw_embeddings_cleared >= 1
    assert result.summary_embeddings_cleared >= 1
    assert result.summaries_deleted >= 1
    assert await store.summary_count() == 0
    assert await store.raw_memory_count() >= 1
    async with engine.connect() as connection:
        raw_after = (
            (
                await connection.execute(
                    select(memory_log).where(memory_log.c.id == raw_id)
                )
            )
            .mappings()
            .one()
        )
    assert raw_after.id == raw_id
    assert raw_after.text == raw_before.text
    assert raw_after.created_at == raw_before.created_at
    assert raw_after.embedding is None

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from llm_agent_kernel import (
    CancellationToken,
    OneShotCompleted,
    ProviderUsage,
    RunId,
    RunMetrics,
)
from llm_tools import PromptSections
from provider_fixture import frozen_provider, model_journal
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import ColumnElement, FromClause

import jarvis.memory as memory_module
from jarvis.admission import (
    RollingAdmissionLimits,
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
)
from jarvis.db import action, create_engine, memory_log, memory_summary, message
from jarvis.definitions import RememberResult, build_slice1_definitions
from jarvis.embeddings import EmbeddingFailure
from jarvis.memory import (
    MemoryIdentity,
    MemoryPersistenceDefect,
    MemoryStore,
    RemembererRunSummary,
    StoredMemorySummary,
    StoredRawMemory,
)
from jarvis.memory_dispatch import MemoryDispatchEvidence
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore
from jarvis.service import RemembererWorker
from jarvis.settings import MAXIMUM_BATCH_SIZE

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
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


def _settlement(run_id: str, checkpoint: UUID) -> dict[str, object]:
    return {
        "run_id": run_id,
        "through_checkpoint": str(checkpoint),
        "conclusion_message_id": str(uuid4()),
        "conclusion_kind": "conversation",
        "outcome": "answered",
        "provider_turns": 1,
    }


async def _stored_message(
    engine: AsyncEngine,
    *,
    role: str,
    created_at: datetime,
    settlement: dict[str, object] | None,
    processed: bool = True,
    remembered: bool = False,
) -> UUID:
    identifier = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=identifier,
                role=role,
                text=f"synthetic {role} memory input",
                source="discord" if role == "owner" else "action",
                source_conversation_id="memory-test-channel",
                source_message_id=str(uuid4()),
                created_at=created_at,
                processed_at=created_at if processed else None,
                processing_attempts=0,
                processing_parked_at=None,
                remembered_at=created_at if remembered else None,
                trace={"settlement": settlement} if settlement is not None else {},
            )
        )
    return identifier


def _run(run_id: str = "rememberer-test-run") -> RemembererRunSummary:
    return RemembererRunSummary(
        run_id=run_id,
        provider_turns=2,
        provider_trace_ids=("provider-trace-1",),
        input_tokens=120,
        output_tokens=30,
        duration_ms=450,
    )


async def test_commit_appends_raw_memory_and_all_owner_watermarks_atomically(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    started_at = datetime(2026, 9, 4, 10, tzinfo=UTC)
    checkpoint = uuid4()
    settlement = _settlement("shared-memory-run", checkpoint)
    first_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at,
        settlement=settlement,
    )
    second_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=1),
        settlement=settlement,
    )
    host_id = await _stored_message(
        engine,
        role="host",
        created_at=started_at + timedelta(seconds=2),
        settlement=settlement,
    )
    group = await store.prepare_rememberer_group(
        owner_message_ids=(first_id, second_id)
    )
    before_actions = await _row_count(engine, action)
    completed_at = started_at + timedelta(minutes=1)

    result = await store.commit_rememberer_result(
        group=group,
        memory_texts=("The owner prefers concise synthetic test answers.",),
        run=_run(),
        remembered_at=completed_at,
    )

    assert len(result.created) == 1
    assert result.created[0].text == (
        "The owner prefers concise synthetic test answers."
    )
    assert result.created[0].embedding is None
    assert result.rejected == ()
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.id, message.c.remembered_at, message.c.trace).where(
                    message.c.id.in_((first_id, second_id, host_id))
                )
            )
        ).all()
    by_id = {row.id: row for row in rows}
    assert by_id[first_id].remembered_at == completed_at
    assert by_id[second_id].remembered_at == completed_at
    assert by_id[host_id].remembered_at is None
    assert by_id[first_id].trace["rememberer"] == by_id[second_id].trace["rememberer"]
    assert by_id[first_id].trace["rememberer"] == {
        "created_memory_ids": [str(result.created[0].id)],
        "run": {
            "run_id": "rememberer-test-run",
            "provider_turns": 2,
            "provider_trace_ids": ["provider-trace-1"],
            "input_tokens": 120,
            "output_tokens": 30,
            "duration_ms": 450,
            "terminal_outcome": "completed",
        },
    }
    encoded_trace = json.dumps(by_id[first_id].trace)
    assert result.created[0].text not in encoded_trace
    assert await _row_count(engine, action) == before_actions
    with pytest.raises(MemoryPersistenceDefect, match="already watermarked"):
        await store.commit_rememberer_result(
            group=group,
            memory_texts=("The owner prefers concise synthetic test answers.",),
            run=_run(),
        )
    assert (
        await _row_count(engine, memory_log, memory_log.c.id == result.created[0].id)
        == 1
    )


async def test_zero_memory_result_advances_the_complete_group(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    started_at = datetime(2026, 9, 4, 11, tzinfo=UTC)
    checkpoint = uuid4()
    settlement = _settlement("zero-memory-run", checkpoint)
    ids = (
        await _stored_message(
            engine,
            role="owner",
            created_at=started_at,
            settlement=settlement,
        ),
        await _stored_message(
            engine,
            role="owner",
            created_at=started_at + timedelta(seconds=1),
            settlement=settlement,
        ),
    )
    group = await store.prepare_rememberer_group(owner_message_ids=ids)
    before = await _row_count(engine, memory_log)

    result = await store.commit_rememberer_result(
        group=group,
        memory_texts=(),
        run=_run("zero-memory-rememberer"),
    )

    assert result.created == ()
    assert await _row_count(engine, memory_log) == before
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.remembered_at, message.c.trace).where(
                    message.c.id.in_(ids)
                )
            )
        ).all()
    assert all(row.remembered_at is not None for row in rows)
    assert all(row.trace["rememberer"]["created_memory_ids"] == [] for row in rows)


async def test_worker_embedding_failure_preserves_committed_lexical_memory(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started_at = datetime(2026, 9, 4, 11, 30, tzinfo=UTC)
    settlement = _settlement("embedding-failure-run", uuid4())
    settlement["conclusion_message_id"] = None
    owner_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at,
        settlement=settlement,
    )
    before_actions = await _row_count(engine, action)
    memory_text = "The owner prefers tangerine ceramic mugs for synthetic tests."

    async def completed(**kwargs: object) -> OneShotCompleted:
        del kwargs
        return OneShotCompleted(
            RunMetrics(
                RunId("embedding-failure-rememberer"),
                1,
                ProviderUsage(input_tokens=20, output_tokens=5),
                0.1,
                False,
            ),
            RememberResult(memories=[memory_text]).model_dump(mode="json"),
        )

    class Dispatcher:
        evidence = MemoryDispatchEvidence((), (), 0)

        async def dispatch(self, **kwargs: object) -> object:
            del kwargs
            raise AssertionError("the scripted rememberer does not dispatch")

    class FailedEmbedder:
        async def embed(self, inputs: tuple[str, ...]) -> object:
            assert inputs == (memory_text,)
            raise EmbeddingFailure("embedding provider call failed")

    monkeypatch.setattr("jarvis.service.run_one_shot", completed)
    admission_path = tmp_path / "embedding-failure-admission.json"
    limits = RollingAdmissionLimits()
    RollingAdmissionPort.initialize(admission_path, limits)
    definitions = build_slice1_definitions(
        provider=frozen_provider("test", "gpt-5.6-terra", "high"), owner_timezone="UTC"
    )
    memory = MemoryStore(engine)
    worker = RemembererWorker(
        model_decisions=model_journal,
        definition=definitions.rememberer,
        plan=definitions.plans["rememberer"],
        admission=RootTrackingAdmissionPort(
            RollingAdmissionPort(admission_path, limits)
        ),
        provider=cast(Any, object()),
        dispatcher_factory=lambda: cast(Any, Dispatcher()),
        memory=memory,
        messages=MessageStore(engine),
        embedder=cast(Any, FailedEmbedder()),
        maximum_messages_per_group=20,
    )
    worker.enqueue((owner_id,), PromptSections(()))

    assert await worker.run_one(CancellationToken()) is True

    async with engine.connect() as connection:
        raw = (
            (
                await connection.execute(
                    select(memory_log).where(memory_log.c.text == memory_text)
                )
            )
            .mappings()
            .one()
        )
        remembered_at = await connection.scalar(
            select(message.c.remembered_at).where(message.c.id == owner_id)
        )
    assert raw.embedding is None
    assert remembered_at is not None
    found = await PostgresMemoryRepository(engine).search(
        "tangerine ceramic",
        lexical_limit=5,
        semantic_limit=0,
        query_embedding=None,
    )
    assert raw.id in {item.id for item in found}
    assert await _row_count(engine, action) == before_actions


async def test_failed_rememberer_attempt_records_no_memory_or_watermark(
    engine: AsyncEngine,
) -> None:
    settlement = _settlement("failed-attempt-run", uuid4())
    settlement["conclusion_message_id"] = None
    started_at = datetime(2026, 9, 4, 11, 45, tzinfo=UTC)
    owner_ids = tuple(
        [
            await _stored_message(
                engine,
                role="owner",
                created_at=started_at + timedelta(milliseconds=index),
                settlement=settlement,
            )
            for index in range(100)
        ]
    )
    memory_count = await _row_count(engine, memory_log)
    action_count = await _row_count(engine, action)

    await MessageStore(engine).record_rememberer_attempt(
        message_ids=owner_ids,
        run_id="failed-rememberer",
        terminal_outcome="provider_error",
        provider_turns=1,
        input_tokens=10,
        output_tokens=0,
        duration_seconds=0.25,
    )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.remembered_at, message.c.trace).where(
                    message.c.id.in_(owner_ids)
                )
            )
        ).all()
    expected_trace: dict[str, object] = {
        "created_memory_ids": [],
        "run": {
            "run_id": "failed-rememberer",
            "terminal_outcome": "provider_error",
            "provider_turns": 1,
            "input_tokens": 10,
            "output_tokens": 0,
            "duration_ms": 250,
        },
    }
    assert len(rows) == 100
    assert all(row.remembered_at is None for row in rows)
    assert all(row.trace["rememberer"] == expected_trace for row in rows)
    assert await _row_count(engine, memory_log) == memory_count
    assert await _row_count(engine, action) == action_count


async def test_secret_candidates_are_dropped_without_secret_diagnostics(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    started_at = datetime(2026, 9, 4, 12, tzinfo=UTC)
    owner_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at,
        settlement=_settlement("secret-filter-run", uuid4()),
    )
    group = await store.prepare_rememberer_group(owner_message_ids=(owner_id,))
    private_key = "-----BEGIN " + "PRIVATE KEY-----\nsynthetic-fixture\n-----END"
    known_token = "sk-" + "A" * 24

    result = await store.commit_rememberer_result(
        group=group,
        memory_texts=(
            private_key,
            "The owner selected a safe synthetic preference.",
            known_token,
        ),
        run=_run("secret-filter-rememberer"),
    )

    assert tuple(item.reason_code for item in result.rejected) == (
        "private_key",
        "known_token_prefix",
    )
    assert tuple(item.candidate_index for item in result.rejected) == (0, 2)
    assert tuple(item.text for item in result.created) == (
        "The owner selected a safe synthetic preference.",
    )
    diagnostics = repr(result.rejected)
    assert private_key not in diagnostics
    assert known_token not in diagnostics
    async with engine.connect() as connection:
        stored_texts = set(
            (
                await connection.execute(
                    select(memory_log.c.text).where(
                        memory_log.c.id.in_(tuple(item.id for item in result.created))
                    )
                )
            ).scalars()
        )
    assert stored_texts == {"The owner selected a safe synthetic preference."}


async def test_sweep_groups_shared_settlement_and_falls_back_per_damaged_row(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    started_at = datetime(2026, 9, 4, 13, tzinfo=UTC)
    settlement = _settlement("sweep-shared-run", uuid4())
    grouped_ids = (
        await _stored_message(
            engine,
            role="owner",
            created_at=started_at,
            settlement=settlement,
        ),
        await _stored_message(
            engine,
            role="owner",
            created_at=started_at + timedelta(seconds=1),
            settlement=settlement,
        ),
    )
    damaged_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=2),
        settlement=None,
    )
    host_id = await _stored_message(
        engine,
        role="host",
        created_at=started_at + timedelta(seconds=3),
        settlement=settlement,
    )
    unprocessed_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=4),
        settlement=_settlement("unprocessed-run", uuid4()),
        processed=False,
    )
    remembered_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=5),
        settlement=_settlement("remembered-run", uuid4()),
        remembered=True,
    )

    groups = await store.select_pending_rememberer_groups(
        maximum_groups=20,
        maximum_messages_per_group=MAXIMUM_BATCH_SIZE,
    )
    relevant = [
        group
        for group in groups
        if any(target.id in {*grouped_ids, damaged_id} for target in group.targets)
    ]

    assert len(relevant) == 2
    shared = next(group for group in relevant if not group.per_row_fallback)
    fallback = next(group for group in relevant if group.per_row_fallback)
    assert tuple(target.id for target in shared.targets) == grouped_ids
    assert tuple(target.id for target in fallback.targets) == (damaged_id,)
    selected_ids = {target.id for group in groups for target in group.targets}
    assert host_id not in selected_ids
    assert unprocessed_id not in selected_ids
    assert remembered_id not in selected_ids


async def test_sweep_includes_every_structured_owner_terminal_and_excludes_controls(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    started_at = datetime(2026, 9, 4, 13, 30, tzinfo=UTC)
    eligible_ids: list[UUID] = []
    for index, outcome in enumerate(
        (
            "answered",
            "partial",
            "needs_input",
            "failed",
            "host_fallback",
            "silent",
        )
    ):
        eligible = _settlement(f"eligible-{outcome}-run", uuid4())
        eligible["conclusion_kind"] = (
            "silent" if outcome == "silent" else "conversation"
        )
        eligible["outcome"] = outcome
        eligible_ids.append(
            await _stored_message(
                engine,
                role="owner",
                created_at=started_at + timedelta(seconds=index),
                settlement=eligible,
            )
        )
    stopped = _settlement("stopped-run", uuid4())
    stopped["conclusion_kind"] = "stopped"
    stopped["outcome"] = "cancelled"
    stopped_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=6),
        settlement=stopped,
    )
    control = _settlement("control-run", uuid4())
    control["conclusion_kind"] = "control"
    control["outcome"] = "pause"
    control_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=7),
        settlement=control,
    )

    groups = await store.select_pending_rememberer_groups(
        maximum_groups=20,
        maximum_messages_per_group=MAXIMUM_BATCH_SIZE,
    )
    selected_ids = {target.id for group in groups for target in group.targets}

    assert set(eligible_ids) <= selected_ids
    assert stopped_id not in selected_ids
    assert control_id not in selected_ids
    with pytest.raises(MemoryPersistenceDefect, match="eligible conclusion"):
        await store.prepare_rememberer_group(owner_message_ids=(stopped_id,))


async def test_restart_sweep_falls_back_for_a_malformed_settlement_object(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    await _stored_message(
        engine,
        role="owner",
        created_at=datetime(1999, 1, 1, tzinfo=UTC),
        settlement={
            "run_id": "valid-but-ineligible",
            "through_checkpoint": str(uuid4()),
            "conclusion_message_id": None,
            "conclusion_kind": "stopped",
            "outcome": "cancelled",
        },
    )
    damaged_id = await _stored_message(
        engine,
        role="owner",
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        settlement={"run_id": 7},
    )

    groups = await store.select_pending_rememberer_groups(
        maximum_groups=1,
        maximum_messages_per_group=1,
    )

    assert len(groups) == 1
    assert groups[0].per_row_fallback
    assert tuple(target.id for target in groups[0].targets) == (damaged_id,)
    await store.commit_rememberer_result(
        group=groups[0],
        memory_texts=(),
        run=_run("damaged-object-restart-sweep"),
    )
    async with engine.connect() as connection:
        remembered_at = await connection.scalar(
            select(message.c.remembered_at).where(message.c.id == damaged_id)
        )
    assert remembered_at is not None


async def test_group_validation_rejects_omissions_and_invalid_targets(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    started_at = datetime(2026, 9, 4, 14, tzinfo=UTC)
    settlement = _settlement("group-validation-run", uuid4())
    first_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at,
        settlement=settlement,
    )
    await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=1),
        settlement=settlement,
    )
    host_id = await _stored_message(
        engine,
        role="host",
        created_at=started_at + timedelta(seconds=2),
        settlement=settlement,
    )
    unprocessed_id = await _stored_message(
        engine,
        role="owner",
        created_at=started_at + timedelta(seconds=3),
        settlement=_settlement("unfinished-validation-run", uuid4()),
        processed=False,
    )

    with pytest.raises(MemoryPersistenceDefect, match="settled owner group"):
        await store.prepare_rememberer_group(owner_message_ids=(first_id,))
    with pytest.raises(MemoryPersistenceDefect, match="owner messages"):
        await store.prepare_rememberer_group(owner_message_ids=(host_id,))
    with pytest.raises(MemoryPersistenceDefect, match="completed messages"):
        await store.prepare_rememberer_group(owner_message_ids=(unprocessed_id,))


async def test_invalid_result_rolls_back_without_memory_or_watermark(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    owner_id = await _stored_message(
        engine,
        role="owner",
        created_at=datetime(2026, 9, 4, 15, tzinfo=UTC),
        settlement=_settlement("invalid-result-run", uuid4()),
    )
    group = await store.prepare_rememberer_group(owner_message_ids=(owner_id,))
    before = await _row_count(engine, memory_log)

    with pytest.raises(ValueError, match="duplicate memory text"):
        await store.commit_rememberer_result(
            group=group,
            memory_texts=("Exact duplicate.", "Exact duplicate."),
            run=_run(),
        )
    with pytest.raises(ValueError, match="8000-byte"):
        await store.commit_rememberer_result(
            group=group,
            memory_texts=("é" * 4_001,),
            run=_run(),
        )
    with pytest.raises(ValueError, match="closed memory bound"):
        await store.commit_rememberer_result(
            group=group,
            memory_texts=tuple(f"Synthetic memory {index}" for index in range(21)),
            run=_run(),
        )

    async with engine.connect() as connection:
        remembered_at = await connection.scalar(
            select(message.c.remembered_at).where(message.c.id == owner_id)
        )
    assert remembered_at is None
    assert await _row_count(engine, memory_log) == before


async def test_database_failure_rolls_back_memory_and_watermark(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore(engine)
    owner_id = await _stored_message(
        engine,
        role="owner",
        created_at=datetime(2026, 9, 4, 15, 30, tzinfo=UTC),
        settlement=_settlement("atomic-failure-run", uuid4()),
    )
    group = await store.prepare_rememberer_group(owner_message_ids=(owner_id,))
    colliding_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(
                id=colliding_id,
                text="Existing synthetic memory identity.",
            )
        )
    monkeypatch.setattr(memory_module, "uuid4", lambda: colliding_id)

    with pytest.raises(IntegrityError):
        await store.commit_rememberer_result(
            group=group,
            memory_texts=("This insert must roll back atomically.",),
            run=_run("atomic-failure-rememberer"),
        )

    async with engine.connect() as connection:
        remembered_at = await connection.scalar(
            select(message.c.remembered_at).where(message.c.id == owner_id)
        )
        memories = (
            await connection.execute(
                select(memory_log.c.text).where(memory_log.c.id == colliding_id)
            )
        ).scalars()
    assert remembered_at is None
    assert tuple(memories) == ("Existing synthetic memory identity.",)


async def test_typed_open_identity_dedup_and_embedding_backfill(
    engine: AsyncEngine,
) -> None:
    store = MemoryStore(engine)
    owner_id = await _stored_message(
        engine,
        role="owner",
        created_at=datetime(2026, 9, 4, 16, tzinfo=UTC),
        settlement=_settlement("embedding-run", uuid4()),
    )
    group = await store.prepare_rememberer_group(owner_message_ids=(owner_id,))
    committed = await store.commit_rememberer_result(
        group=group,
        memory_texts=("Synthetic raw memory for exact open.",),
        run=_run("embedding-rememberer"),
    )
    raw = committed.created[0]
    summary_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="Synthetic derived summary.",
                source_memory_ids=[raw.id],
            )
        )
    candidates = await store.select_null_embedding_candidates(maximum_rows=500)
    candidate_ids = {item.identity for item in candidates}
    assert raw.identity in candidate_ids
    assert MemoryIdentity("memory_summary", summary_id) in candidate_ids

    raw_updated = await store.update_embedding(
        identity=raw.identity,
        embedding=[1.0, *([0.0] * 1535)],
    )
    summary_updated = await store.update_embedding(
        identity=MemoryIdentity("memory_summary", summary_id),
        embedding=[1.0] * 1536,
    )
    opened = await store.open_memories(
        identities=(
            raw.identity,
            raw.identity,
            MemoryIdentity("memory_summary", summary_id),
        ),
        maximum_rows=2,
    )

    assert isinstance(raw_updated, StoredRawMemory)
    assert raw_updated.embedding == (1.0, *([0.0] * 1535))
    assert isinstance(summary_updated, StoredMemorySummary)
    assert summary_updated.embedding == (1.0,) * 1536
    assert len(opened) == 2
    assert opened[0].identity == raw.identity
    assert opened[1].identity == MemoryIdentity("memory_summary", summary_id)
    assert isinstance(opened[1], StoredMemorySummary)
    assert opened[1].source_memory_ids == (raw.id,)
    with pytest.raises(ValueError, match="exactly 1536"):
        await store.update_embedding(identity=raw.identity, embedding=[0.0])
    with pytest.raises(ValueError, match="finite"):
        await store.update_embedding(
            identity=raw.identity,
            embedding=[float("nan")] * 1536,
        )
    with pytest.raises(ValueError, match="non-zero L2 norm"):
        await store.update_embedding(
            identity=raw.identity,
            embedding=[0.0] * 1536,
        )


async def _row_count(
    engine: AsyncEngine,
    table: FromClause,
    predicate: ColumnElement[bool] | None = None,
) -> int:
    statement = select(func.count()).select_from(table)
    if predicate is not None:
        statement = statement.where(predicate)
    async with engine.connect() as connection:
        return int(await connection.scalar(statement) or 0)

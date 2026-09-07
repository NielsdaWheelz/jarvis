from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InitialReadDispatchLineage,
    InputId,
    IsolatedDispatchLineage,
    RunId,
    ToolDispatchDefect,
)
from llm_tools import (
    CapabilityProfile,
    HostTable,
    InvocationPosition,
    ProfileId,
    Reservation,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolId,
    ToolPlan,
    canonical_json_bytes,
)
from llm_tools.schema import SchemaDecodeError, strict_decode
from llm_tools.testing import InMemoryBudgetState
from pydantic import ValidationError

from jarvis.embeddings import EmbeddingFailure
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import (
    MemoryIdentity,
    OpenedMemory,
    RetrievedMemory,
)
from jarvis.memory_tools import (
    MAX_MEMORY_READ_OUTPUT_BYTES,
    MAX_OPEN_IDENTITIES,
    MAX_SEARCH_LANE_RESULTS,
    MEMORY_OPEN_SPEC,
    MEMORY_SEARCH_SPEC,
    MEMORY_TOOL_IDS,
    MEMORY_TOOL_RUN_LIMITS,
    MemoryOpenInput,
    MemoryRowIdentity,
    MemorySearchInput,
    compose_memory_catalog,
)
from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL


class _Embedder:
    def __init__(
        self,
        *,
        failure: Exception | None = None,
        vector: tuple[float, ...] | None = None,
    ) -> None:
        self.failure = failure
        self.vector = vector
        self.calls: list[tuple[str, ...]] = []

    async def embed(
        self,
        inputs: Sequence[str],
    ) -> tuple[tuple[float, ...], ...]:
        values = tuple(inputs)
        self.calls.append(values)
        if self.failure is not None:
            raise self.failure
        if self.vector is not None:
            return (self.vector,)
        return ((1.0, *([0.0] * (EMBEDDING_DIMENSION - 1))),)


class _CapturingBudget(InMemoryBudgetState):
    def __init__(self) -> None:
        super().__init__(MEMORY_TOOL_RUN_LIMITS)
        self.positions: list[InvocationPosition] = []

    async def reserve(
        self, position: InvocationPosition, reservation: Reservation
    ) -> bool:
        self.positions.append(position)
        return await super().reserve(position, reservation)


class _Repository:
    def __init__(self, row: RetrievedMemory) -> None:
        self.row = row
        self.search_embeddings: list[Sequence[float] | None] = []
        self.opened: list[tuple[MemoryIdentity, ...]] = []
        self.missing: tuple[MemoryIdentity, ...] = ()

    async def search(
        self,
        query: str,
        *,
        lexical_limit: int,
        semantic_limit: int,
        query_embedding: Sequence[float] | None,
    ) -> tuple[RetrievedMemory, ...]:
        assert query == "synthetic query"
        assert lexical_limit == 5
        assert semantic_limit == 5
        self.search_embeddings.append(query_embedding)
        return (self.row,)

    async def open(
        self,
        identities: Sequence[MemoryIdentity],
    ) -> OpenedMemory:
        values = tuple(dict.fromkeys(identities))
        self.opened.append(values)
        return OpenedMemory((self.row,), self.missing)


class _MaximumRepository:
    def __init__(self) -> None:
        source_memory_ids = tuple(UUID(int=index + 100) for index in range(100))
        self.rows = tuple(
            RetrievedMemory(
                table_kind="memory_summary",
                id=UUID(int=index + 1),
                text="\x01" * 8_000,
                created_at=datetime.max.replace(tzinfo=UTC),
                source_memory_ids=source_memory_ids,
                lexical_rank=float(index + 1),
                semantic_distance=float(index) / 20,
            )
            for index in range(20)
        )

    async def search(
        self,
        query: str,
        *,
        lexical_limit: int,
        semantic_limit: int,
        query_embedding: Sequence[float] | None,
    ) -> tuple[RetrievedMemory, ...]:
        del query, lexical_limit, semantic_limit, query_embedding
        return self.rows

    async def open(
        self,
        identities: Sequence[MemoryIdentity],
    ) -> OpenedMemory:
        del identities
        return OpenedMemory(self.rows, ())


def _row() -> RetrievedMemory:
    return RetrievedMemory(
        table_kind="memory_log",
        id=uuid4(),
        text="Synthetic durable preference.",
        created_at=datetime(2026, 9, 4, 12, tzinfo=UTC),
        source_memory_ids=(),
        lexical_rank=0.5,
        semantic_distance=0.125,
    )


def _catalog_and_plan(
    repository: Any,
    embedder: _Embedder,
) -> tuple[ToolCatalog, Any]:
    catalog = compose_memory_catalog(repository, embedder)
    profile = CapabilityProfile(
        ProfileId("memory_role_test"),
        tuple(ToolGrant(tool_id, None) for tool_id in MEMORY_TOOL_IDS),
        MEMORY_TOOL_RUN_LIMITS,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    return catalog, plan


def _assert_closed(value: object) -> None:
    if isinstance(value, dict):
        values = cast("dict[object, object]", value)
        if values.get("type") == "object":
            assert values.get("additionalProperties") is False
        for item in values.values():
            _assert_closed(item)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            _assert_closed(item)


def test_memory_catalog_contract_and_policy_are_exact() -> None:
    repository = _Repository(_row())
    catalog, plan = _catalog_and_plan(repository, _Embedder())

    assert frozenset(catalog.tool_ids) == MEMORY_TOOL_IDS
    assert plan.profile.run_limits == MEMORY_TOOL_RUN_LIMITS
    assert MEMORY_TOOL_RUN_LIMITS.max_in_flight == 1
    assert MAX_SEARCH_LANE_RESULTS == 10
    assert MAX_OPEN_IDENTITIES == 20
    assert MAX_MEMORY_READ_OUTPUT_BYTES == 1_048_576
    assert MEMORY_TOOL_RUN_LIMITS.max_output_bytes == (8 * MAX_MEMORY_READ_OUTPUT_BYTES)
    for tool_id in MEMORY_TOOL_IDS:
        spec = catalog.spec(tool_id)
        assert spec.effect is ToolEffect.Read
        _assert_closed(spec.input_schema.semantic)
        _assert_closed(spec.success_schema.semantic)
        binding = catalog.binding(tool_id)
        assert binding.implementation_revision == (
            f"jarvis-{str(tool_id).replace('.', '-')}-v1"
        )
    search_binding = catalog.binding(ToolId("memory.search"))
    assert search_binding.policy_inputs["semantic"] == {
        "distance": "cosine",
        "index": None,
        "operator": "<=>",
        "scan": "exact",
    }
    assert search_binding.policy_inputs["embedding_model"] == EMBEDDING_MODEL
    assert search_binding.policy_inputs["embedding_dimension"] == EMBEDDING_DIMENSION
    assert search_binding.policy_inputs["deduplication"] == (
        "exact-table-kind-and-id-only"
    )
    assert search_binding.policy_inputs["lexical"] == (
        "greatest-ts_rank_cd-expression-english-simple"
    )
    assert catalog.binding(ToolId("memory.open")).policy_inputs["max_identities"] == 20


async def test_maximum_search_and_open_results_fit_their_declared_limits() -> None:
    repository = _MaximumRepository()
    catalog, plan = _catalog_and_plan(repository, _Embedder())
    dispatcher = MemoryToolDispatcher()
    budgets = InMemoryBudgetState(plan.profile.run_limits)

    searched = await dispatcher.dispatch(
        binding=catalog.binding(MEMORY_SEARCH_SPEC.id),
        validated_input=MemorySearchInput(
            query="synthetic query",
            lexical_limit=10,
            semantic_limit=10,
        ),
        plan=plan,
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=IsolatedDispatchLineage(RunId("maximum-memory-run"), 1),
    )
    opened = await dispatcher.dispatch(
        binding=catalog.binding(MEMORY_OPEN_SPEC.id),
        validated_input=MemoryOpenInput(
            identities=tuple(
                MemoryRowIdentity(table_kind=row.table_kind, id=row.id)
                for row in repository.rows
            )
        ),
        plan=plan,
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=IsolatedDispatchLineage(RunId("maximum-memory-run"), 2),
    )

    assert len(searched.result["value"]["candidates"]) == 20
    assert len(opened.result["value"]["memories"]) == 20
    for completed in (searched, opened):
        size = len(canonical_json_bytes(cast("Any", completed.result)))
        assert 32_768 < size <= MAX_MEMORY_READ_OUTPUT_BYTES


async def test_initial_read_forwards_the_kernel_owned_invocation_position() -> None:
    repository = _Repository(_row())
    catalog, plan = _catalog_and_plan(repository, _Embedder())
    dispatcher = MemoryToolDispatcher()
    budgets = _CapturingBudget()
    lineage = InitialReadDispatchLineage(RunId("initial-memory-run"))

    completed = await dispatcher.dispatch(
        binding=catalog.binding(MEMORY_SEARCH_SPEC.id),
        validated_input=MemorySearchInput(
            query="synthetic query",
            lexical_limit=5,
            semantic_limit=5,
        ),
        plan=plan,
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=lineage,
    )

    assert completed.result["type"] == "Success"
    assert budgets.positions == [lineage.position]
    assert dispatcher.evidence.search_calls == 1


async def test_search_embedding_failure_falls_back_to_lexical_success() -> None:
    repository = _Repository(_row())
    embedder = _Embedder(failure=EmbeddingFailure("synthetic embedding failure"))
    catalog, plan = _catalog_and_plan(repository, embedder)
    dispatcher = MemoryToolDispatcher()
    budgets = InMemoryBudgetState(plan.profile.run_limits)

    for ordinal in (1, 2):
        completed = await dispatcher.dispatch(
            binding=catalog.binding(MEMORY_SEARCH_SPEC.id),
            validated_input=MemorySearchInput(
                query="synthetic query",
                lexical_limit=5,
                semantic_limit=5,
            ),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=IsolatedDispatchLineage(RunId("memory-run"), ordinal),
        )
        assert completed.result["type"] == "Success"

    assert repository.search_embeddings == [None, None]
    assert embedder.calls == [("synthetic query",), ("synthetic query",)]
    assert budgets.actual_external_attempts == 2
    assert dispatcher.recorder.position_count == 2
    assert dispatcher.recorder.terminal_count == 2
    assert dispatcher.evidence.candidate_ids == (
        MemoryIdentity("memory_log", repository.row.id),
    )
    assert dispatcher.evidence.search_calls == 2
    evidence_text = repr(dispatcher.evidence)
    assert "synthetic query" not in evidence_text
    assert repository.row.text not in evidence_text


async def test_unexpected_embedding_defect_fails_dispatch() -> None:
    repository = _Repository(_row())
    catalog, plan = _catalog_and_plan(
        repository,
        _Embedder(failure=ValueError("synthetic programming defect")),
    )
    dispatcher = MemoryToolDispatcher()

    with pytest.raises(ToolDispatchDefect, match="memory read dispatch failed"):
        await dispatcher.dispatch(
            binding=catalog.binding(MEMORY_SEARCH_SPEC.id),
            validated_input=MemorySearchInput(
                query="synthetic query",
                lexical_limit=5,
                semantic_limit=5,
            ),
            plan=plan,
            budgets=InMemoryBudgetState(plan.profile.run_limits),
            cancellation=CancellationToken(),
            lineage=IsolatedDispatchLineage(RunId("memory-defect-run"), 1),
        )

    assert repository.search_embeddings == []
    assert dispatcher.evidence.search_calls == 0
    assert dispatcher.evidence.candidate_ids == ()
    assert dispatcher.recorder.uncertain_count == 1


async def test_zero_query_embedding_fails_dispatch() -> None:
    repository = _Repository(_row())
    catalog, plan = _catalog_and_plan(
        repository,
        _Embedder(vector=(0.0,) * EMBEDDING_DIMENSION),
    )
    dispatcher = MemoryToolDispatcher()

    with pytest.raises(ToolDispatchDefect, match="memory read dispatch failed"):
        await dispatcher.dispatch(
            binding=catalog.binding(MEMORY_SEARCH_SPEC.id),
            validated_input=MemorySearchInput(
                query="synthetic query",
                lexical_limit=5,
                semantic_limit=5,
            ),
            plan=plan,
            budgets=InMemoryBudgetState(plan.profile.run_limits),
            cancellation=CancellationToken(),
            lineage=IsolatedDispatchLineage(RunId("zero-vector-run"), 1),
        )

    assert repository.search_embeddings == []
    assert dispatcher.recorder.uncertain_count == 1


async def test_open_deduplicates_inputs_and_returns_typed_not_found() -> None:
    row = _row()
    repository = _Repository(row)
    missing = MemoryIdentity("memory_summary", uuid4())
    repository.missing = (missing,)
    catalog, plan = _catalog_and_plan(repository, _Embedder())
    dispatcher = MemoryToolDispatcher()
    identity = MemoryRowIdentity(table_kind=row.table_kind, id=row.id)

    completed = await dispatcher.dispatch(
        binding=catalog.binding(MEMORY_OPEN_SPEC.id),
        validated_input=MemoryOpenInput(
            identities=(
                identity,
                identity,
                MemoryRowIdentity(table_kind=missing.table_kind, id=missing.id),
            )
        ),
        plan=plan,
        budgets=InMemoryBudgetState(plan.profile.run_limits),
        cancellation=CancellationToken(),
        lineage=IsolatedDispatchLineage(RunId("memory-open-run"), 1),
    )

    assert completed.result == {
        "type": "Failure",
        "error": {"type": "MemoryNotFound"},
    }
    assert repository.opened == [
        (
            MemoryIdentity("memory_log", row.id),
            missing,
        )
    ]
    assert dispatcher.evidence.opened_ids == ()


async def test_dispatch_evidence_preserves_successful_open_occurrences_only() -> None:
    row = _row()
    repository = _Repository(row)
    catalog, plan = _catalog_and_plan(repository, _Embedder())
    dispatcher = MemoryToolDispatcher()
    budgets = InMemoryBudgetState(plan.profile.run_limits)
    value = MemoryOpenInput(
        identities=(
            MemoryRowIdentity(table_kind="memory_log", id=row.id),
            MemoryRowIdentity(table_kind="memory_log", id=row.id),
        )
    )

    for ordinal in (1, 2):
        completed = await dispatcher.dispatch(
            binding=catalog.binding(MEMORY_OPEN_SPEC.id),
            validated_input=value,
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=IsolatedDispatchLineage(RunId("memory-open-run"), ordinal),
        )
        assert completed.result["type"] == "Success"

    identity = MemoryIdentity("memory_log", row.id)
    assert dispatcher.evidence.opened_ids == (identity, identity)
    assert dispatcher.evidence.candidate_ids == ()
    assert dispatcher.evidence.search_calls == 0
    evidence_text = repr(dispatcher.evidence)
    assert row.text not in evidence_text
    assert "identities" not in evidence_text


async def test_dispatch_rejects_nonisolated_lineage_before_mutation() -> None:
    repository = _Repository(_row())
    catalog, plan = _catalog_and_plan(repository, _Embedder())
    dispatcher = MemoryToolDispatcher()
    budgets = InMemoryBudgetState(plan.profile.run_limits)

    with pytest.raises(ToolDispatchDefect, match="isolated"):
        await dispatcher.dispatch(
            binding=catalog.binding(MEMORY_SEARCH_SPEC.id),
            validated_input=MemorySearchInput(
                query="synthetic query",
                lexical_limit=5,
                semantic_limit=5,
            ),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("claim"),
                Checkpoint("checkpoint"),
                (InputId("input"),),
                1,
            ),
        )
    assert dispatcher.recorder.position_count == 0
    assert budgets.actual_calls == 0


@pytest.mark.parametrize("mutation", ("implementation", "effect"))
async def test_dispatch_rejects_frozen_binding_substitution_before_mutation(
    mutation: str,
) -> None:
    repository = _Repository(_row())
    catalog, plan = _catalog_and_plan(repository, _Embedder())
    binding = catalog.binding(MEMORY_SEARCH_SPEC.id)
    policy_inputs = {
        **binding.policy_inputs,
        "semantic": dict(cast("dict[str, object]", binding.policy_inputs["semantic"])),
    }
    if mutation == "implementation":
        changed = replace(
            binding,
            implementation_revision="substituted",
            policy_inputs=policy_inputs,
        )
    else:
        changed_spec = replace(binding.spec, effect=ToolEffect.Write)
        changed = replace(binding, spec=changed_spec, policy_inputs=policy_inputs)
    dispatcher = MemoryToolDispatcher()
    budgets = InMemoryBudgetState(plan.profile.run_limits)

    with pytest.raises(ToolDispatchDefect):
        await dispatcher.dispatch(
            binding=changed,
            validated_input=MemorySearchInput(
                query="synthetic query",
                lexical_limit=5,
                semantic_limit=5,
            ),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=IsolatedDispatchLineage(RunId("memory-run"), 1),
        )
    assert dispatcher.recorder.position_count == 0
    assert budgets.actual_calls == 0


def test_memory_inputs_reject_unknown_or_unbounded_values() -> None:
    with pytest.raises(SchemaDecodeError):
        strict_decode(
            MemorySearchInput,
            MEMORY_SEARCH_SPEC.input_schema,
            {
                "query": "synthetic",
                "lexical_limit": 0,
                "semantic_limit": 0,
                "unknown": True,
            },
        )
    with pytest.raises(ValidationError):
        MemoryOpenInput(
            identities=tuple(
                MemoryRowIdentity(table_kind="memory_log", id=UUID(int=index + 1))
                for index in range(MAX_OPEN_IDENTITIES + 1)
            )
        )

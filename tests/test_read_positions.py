from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from llm_tools import (
    InvocationPosition,
    ReplayPolicy,
    Reservation,
    RunLimits,
    Settlement,
    ToolId,
)
from llm_tools.testing import InMemoryBudgetState
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import create_engine
from jarvis.read_positions import PostgresReadRecorder

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        DATABASE_URL is None, reason="test PostgreSQL is not configured"
    ),
]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    yield engine
    await engine.dispose()


async def _occupy(recorder: PostgresReadRecorder, position: InvocationPosition):
    return await recorder.occupy(
        position=position,
        tool_id=ToolId("maps.get_place"),
        tool_contract_revision="tool-v1",
        policy_revision="policy-v1",
        plan_revision="plan-v1",
        input_digest="a" * 64,
        replay_policy=ReplayPolicy.BilledOnce,
    )


async def test_dispatched_paid_read_is_uncertain_after_process_reopen(
    engine: AsyncEngine,
) -> None:
    position = InvocationPosition(str(uuid4()))
    recorder = PostgresReadRecorder(engine)
    assert not (await _occupy(recorder, position)).uncertain
    budgets = InMemoryBudgetState(RunLimits(1, 1, 100, 1_000, 1, 30.0))
    assert await recorder.reserve(
        position=position, budgets=budgets, reservation=Reservation(1, 5, 1, 1_000)
    )
    assert not (
        await recorder.dispatch_started(
            position=position, replay_policy=ReplayPolicy.BilledOnce
        )
    ).uncertain
    reopened = PostgresReadRecorder(engine)
    assert (await _occupy(reopened, position)).uncertain
    assert (
        await reopened.dispatch_started(
            position=position, replay_policy=ReplayPolicy.BilledOnce
        )
    ).uncertain


async def test_original_paid_result_replays_and_changed_identity_is_rejected(
    engine: AsyncEngine,
) -> None:
    position = InvocationPosition(str(uuid4()))
    recorder = PostgresReadRecorder(engine)
    await _occupy(recorder, position)
    budgets = InMemoryBudgetState(RunLimits(1, 1, 100, 1_000, 1, 30.0))
    assert await recorder.reserve(
        position=position, budgets=budgets, reservation=Reservation(1, 5, 1, 1_000)
    )
    await recorder.dispatch_started(
        position=position, replay_policy=ReplayPolicy.BilledOnce
    )
    result = {"type": "Success", "value": {"place": "original"}}
    assert (
        await recorder.terminalize_and_settle(
            position=position,
            budgets=budgets,
            result=result,
            settlement=Settlement(1, 50),
        )
        == result
    )
    reopened = PostgresReadRecorder(engine)
    state = await _occupy(reopened, position)
    assert state.terminal_result == result and not state.uncertain
    with pytest.raises(ValueError):
        await reopened.occupy(
            position=position,
            tool_id=ToolId("maps.get_place"),
            tool_contract_revision="changed",
            policy_revision="policy-v1",
            plan_revision="plan-v1",
            input_digest="a" * 64,
            replay_policy=ReplayPolicy.BilledOnce,
        )


@pytest.mark.parametrize("lose_result", [False, True])
async def test_executor_reopen_never_repeats_a_paid_handler(
    engine: AsyncEngine, lose_result: bool
) -> None:
    from llm_agent_kernel import CancellationToken
    from llm_tools import (
        Available,
        CapabilityProfile,
        ExecutionContext,
        HandlerSuccess,
        HostTable,
        ParsedJson,
        PolicyEpoch,
        Principal,
        ProfileId,
        RecoveryRequired,
        Scope,
        ToolBinding,
        ToolCatalog,
        ToolExecutor,
        ToolFamily,
        ToolGrant,
        ToolPlan,
    )
    from llm_tools.testing import RecordingTelemetry

    from jarvis.memory_tools import (
        MEMORY_SEARCH_SPEC,
        MemorySearchInput,
        MemorySearchSuccess,
    )

    calls = 0

    async def search(
        value: MemorySearchInput, context: ExecutionContext
    ) -> HandlerSuccess[MemorySearchSuccess]:
        nonlocal calls
        del value, context
        calls += 1
        if lose_result:
            raise ConnectionError("paid search returned no accepted result")
        return HandlerSuccess(MemorySearchSuccess(candidates=()), actual_attempts=1)

    binding = ToolBinding(
        spec=MEMORY_SEARCH_SPEC,
        execute=Available(search),
        replay_policy=ReplayPolicy.BilledOnce,
        implementation_revision="paid-search-test",
        policy_epoch=PolicyEpoch("test-policy"),
        policy_inputs={},
    )
    catalog = ToolCatalog.compose(
        (
            ToolFamily(
                namespace="memory",
                declarations=(MEMORY_SEARCH_SPEC,),
                bindings=(binding,),
            ),
        )
    )
    profile = CapabilityProfile(
        ProfileId("paid-read-proof"),
        (ToolGrant(MEMORY_SEARCH_SPEC.id, None),),
        RunLimits(1, 1, 8_192, 1_048_576, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    position = InvocationPosition(str(uuid4()))

    async def execute() -> object:
        return await ToolExecutor.execute(
            binding,
            ParsedJson({"query": "original", "lexical_limit": 1, "semantic_limit": 1}),
            ExecutionContext(
                plan,
                plan.grant(binding.spec.id),
                plan.catalog_view,
                position,
                PostgresReadRecorder(engine),
                None,
                InMemoryBudgetState(plan.profile.run_limits),
                Principal("test-owner"),
                Scope("test-paid-read"),
                CancellationToken(),
                RecordingTelemetry(),
            ),
        )

    if lose_result:
        with pytest.raises(RecoveryRequired):
            await execute()
        with pytest.raises(RecoveryRequired):
            await execute()
    else:
        first = await execute()
        assert first == {"type": "Success", "value": {"candidates": []}}
        assert await execute() == first
    assert calls == 1


@pytest.mark.parametrize("initial_read", [False, True])
async def test_recovered_scope_restores_paid_read_budget_before_new_work(
    engine: AsyncEngine, initial_read: bool
) -> None:
    from datetime import UTC, datetime

    from llm_agent_kernel import (
        InitialReadDispatchLineage,
        IsolatedDecisionScope,
        IsolatedDispatchLineage,
        ModelDecisionRequest,
        RunId,
    )
    from provider_runtime.agent_runtime import AgentSessionRef, AgentTerminal

    from jarvis.decisions import PostgresModelDecisionJournal

    scope = IsolatedDecisionScope(str(uuid4()))
    request = ModelDecisionRequest(
        scope=scope,
        ordinal=1,
        definition_fingerprint="a" * 64,
        plan_revision="plan-v1",
        input_ids=(),
        through_checkpoint=None,
        as_of=datetime.now(UTC),
        model_step_ordinal_before=0,
        protocol_repairs=0,
        canonical_content=("original",),
        submitted_content=("original",),
    )
    journal = PostgresModelDecisionJournal(engine)
    await journal.arm(request)
    await journal.complete(
        request,
        AgentTerminal(
            status="succeeded",
            final_text="original",
            failure=None,
            session_ref=AgentSessionRef(
                "agent-session-ref.v1",
                "codex",
                "sdk",
                "original",
                "test",
                "a" * 64,
                "b" * 64,
            ),
        ),
    )
    lineage = IsolatedDispatchLineage(RunId("original"), 1, request.decision_id)
    position = (
        InitialReadDispatchLineage(RunId("original"), scope.operation_id).position
        if initial_read
        else lineage.position
    )
    limits = RunLimits(1, 1, 100, 1_000, 1, 30.0)
    original_budget = InMemoryBudgetState(limits)
    recorder = PostgresReadRecorder(engine)
    await _occupy(recorder, position)
    reservation = Reservation(1, 5, 1, 1_000)
    assert await recorder.reserve(
        position=position, budgets=original_budget, reservation=reservation
    )
    await recorder.dispatch_started(
        position=position, replay_policy=ReplayPolicy.BilledOnce
    )
    await recorder.terminalize_and_settle(
        position=position,
        budgets=original_budget,
        result={"type": "Success", "value": {"paid": "original"}},
        settlement=Settlement(1, 50),
    )
    recovered_budget = InMemoryBudgetState(limits)
    reopened = PostgresReadRecorder(engine)
    await reopened.recover_budget(lineage=lineage, budgets=recovered_budget)
    await reopened.recover_budget(lineage=lineage, budgets=recovered_budget)
    assert recovered_budget.actual_calls == 1
    assert recovered_budget.actual_external_attempts == 1
    assert recovered_budget.actual_input_bytes == 5
    assert recovered_budget.actual_output_bytes == 50
    assert not await recovered_budget.reserve(
        InvocationPosition("forbidden-new-call"), reservation
    )

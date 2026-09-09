from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from llm_agent_kernel import Checkpoint, InputId, ThreadId
from llm_agent_kernel.decisions import (
    ModelDecisionArmed,
    ModelDecisionCompleted,
    ModelDecisionDefect,
    ModelDecisionRequest,
    ModelDecisionScope,
)
from provider_runtime.agent_runtime import (
    AgentSessionRef,
    AgentTerminal,
    freeze_json_value,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import create_engine
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.messages import ClaimedMessages, MessageStore

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
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


async def _request(engine: AsyncEngine) -> ModelDecisionRequest:
    store = MessageStore(engine)
    thread = str(uuid4())
    now = datetime.now(UTC)
    inserted = await store.insert_waking(
        role="owner",
        text="original owner input",
        source="discord",
        source_conversation_id=thread,
        source_message_id=str(uuid4()),
        created_at=now,
    )
    identifier = InputId(str(inserted.message.id))
    return ModelDecisionRequest(
        scope=ModelDecisionScope(ThreadId(thread), identifier),
        ordinal=1,
        definition_fingerprint="a" * 64,
        plan_revision="frozen-plan",
        input_ids=(identifier,),
        through_checkpoint=Checkpoint(str(identifier)),
        as_of=now,
        model_step_ordinal_before=0,
        protocol_repairs=0,
        canonical_content=("original complete context",),
        submitted_content=("original submitted context",),
    )


def _terminal() -> AgentTerminal:
    return AgentTerminal(
        status="succeeded",
        failure=None,
        final_text='{"kind":"complete"}',
        session_ref=AgentSessionRef(
            "agent-session-ref.v1",
            "codex",
            "sdk",
            "original-session",
            "jarvis-test",
            "a" * 64,
            "b" * 64,
        ),
        structured_output=freeze_json_value({"kind": "complete", "nested": [1, True]}),
    )


async def test_original_paid_decision_survives_reopen_and_cannot_be_overwritten(
    engine: AsyncEngine,
) -> None:
    request = await _request(engine)
    journal = PostgresModelDecisionJournal(engine)
    assert await journal.latest(request.scope) is None
    await journal.arm(request)
    reopened = PostgresModelDecisionJournal(engine)
    assert await reopened.latest(request.scope) == ModelDecisionArmed(request)
    with pytest.raises(ModelDecisionDefect):
        await reopened.arm(request)
    with pytest.raises(ModelDecisionDefect):
        await reopened.arm(replace(request, ordinal=2))
    with pytest.raises(ModelDecisionDefect):
        await reopened.complete(
            replace(request, submitted_content=("changed",)), _terminal()
        )
    completed = await reopened.complete(request, _terminal())
    assert completed == ModelDecisionCompleted(request, _terminal())
    assert await PostgresModelDecisionJournal(engine).latest(request.scope) == completed
    with pytest.raises(ModelDecisionDefect):
        await reopened.complete(request, replace(_terminal(), final_text="changed"))
    with pytest.raises(ModelDecisionDefect):
        await reopened.release_undispatched(request)


async def test_proven_undispatched_request_alone_can_release_its_identity(
    engine: AsyncEngine,
) -> None:
    request = await _request(engine)
    journal = PostgresModelDecisionJournal(engine)
    await journal.arm(request)
    with pytest.raises(ModelDecisionDefect):
        await journal.release_undispatched(replace(request, plan_revision="changed"))
    await journal.release_undispatched(request)
    assert await journal.latest(request.scope) is None
    await journal.arm(request)
    assert await journal.latest(request.scope) == ModelDecisionArmed(request)


@pytest.mark.parametrize("completed", [False, True])
async def test_claim_restores_original_paid_input_before_poison_or_new_batch(
    engine: AsyncEngine, completed: bool
) -> None:
    request = await _request(engine)
    assert isinstance(request.scope, ModelDecisionScope)
    store = MessageStore(engine)
    original = await store.claim(
        source_conversation_id=str(request.scope.thread_id),
        maximum_batch_size=10,
        maximum_attempts=1,
        as_of=request.as_of,
    )
    assert isinstance(original, ClaimedMessages)
    journal = PostgresModelDecisionJournal(engine)
    await journal.arm(request)
    if completed:
        await journal.complete(request, _terminal())
    await store.insert_waking(
        role="owner",
        text="later input",
        source="discord",
        source_conversation_id=str(request.scope.thread_id),
        source_message_id=str(uuid4()),
        created_at=request.as_of + timedelta(seconds=1),
    )
    recovered = await store.claim(
        source_conversation_id=str(request.scope.thread_id),
        maximum_batch_size=10,
        maximum_attempts=1,
    )
    assert isinstance(recovered, ClaimedMessages)
    assert tuple(row.id for row in recovered.messages) == (
        UUID(str(request.scope.first_input_id)),
    )
    assert recovered.as_of == request.as_of
    assert recovered.through_checkpoint == str(request.through_checkpoint)
    assert recovered.attempt_number == original.attempt_number


async def test_paid_terminal_restores_original_validation_evidence_atomically(
    engine: AsyncEngine,
) -> None:
    from jarvis.memory_dispatch import MemoryToolDispatcher
    from jarvis.read_dispatch import RunReadRecorder

    request = await _request(engine)
    identity = uuid4()
    original = MemoryToolDispatcher(recorder=RunReadRecorder())
    original.restore_model_evidence(
        {
            "kind": "jarvis-memory-evidence.v1",
            "candidate_ids": [{"table_kind": "memory_log", "id": str(identity)}],
            "opened_ids": [{"table_kind": "memory_log", "id": str(identity)}],
            "search_calls": 1,
        }
    )
    journal = PostgresModelDecisionJournal(engine, evidence=original)
    await journal.arm(request)
    completed = await journal.complete(request, _terminal())
    restored = MemoryToolDispatcher(recorder=RunReadRecorder())
    reopened = PostgresModelDecisionJournal(engine, evidence=restored)
    assert await reopened.latest(request.scope) == completed
    assert restored.evidence == original.evidence
    with pytest.raises(ModelDecisionDefect, match="evidence owner"):
        await PostgresModelDecisionJournal(engine).latest(request.scope)


@pytest.mark.parametrize("unknown_work", ["initial_read", "model", "model_read"])
async def test_unknown_recall_parks_original_input_before_poison_admission(
    engine: AsyncEngine, unknown_work: str
) -> None:
    from llm_agent_kernel import (
        InitialReadDispatchLineage,
        IsolatedDecisionScope,
        RunId,
    )
    from llm_tools import (
        InvocationPosition,
        ReplayPolicy,
        Reservation,
        RunLimits,
        ToolId,
    )
    from llm_tools.testing import InMemoryBudgetState

    from jarvis.messages import CircuitOpen
    from jarvis.read_positions import PostgresReadRecorder

    request = await _request(engine)
    assert isinstance(request.scope, ModelDecisionScope)
    store = MessageStore(engine)
    original = await store.claim(
        source_conversation_id=str(request.scope.thread_id),
        maximum_batch_size=10,
        maximum_attempts=1,
        as_of=request.as_of,
    )
    assert isinstance(original, ClaimedMessages)
    operation_id = f"jarvis-recall:{request.input_ids[0]}"
    recall_request = replace(
        request, scope=IsolatedDecisionScope(operation_id), through_checkpoint=None
    )
    if unknown_work != "initial_read":
        journal = PostgresModelDecisionJournal(engine)
        await journal.arm(recall_request)
        if unknown_work == "model_read":
            await journal.complete(recall_request, _terminal())
    if unknown_work != "model":
        recorder = PostgresReadRecorder(engine)
        position = (
            InitialReadDispatchLineage(RunId("original"), operation_id).position
            if unknown_work == "initial_read"
            else InvocationPosition("model-decision:" + recall_request.decision_id)
        )
        await recorder.occupy(
            position=position,
            tool_id=ToolId("memory.search"),
            tool_contract_revision="tool-v1",
            policy_revision="policy-v1",
            plan_revision="plan-v1",
            input_digest="a" * 64,
            replay_policy=ReplayPolicy.BilledOnce,
        )
        assert await recorder.reserve(
            position=position,
            budgets=InMemoryBudgetState(RunLimits(1, 1, 100, 1_000, 1, 30.0)),
            reservation=Reservation(1, 5, 1, 1_000),
        )
        await recorder.dispatch_started(
            position=position, replay_policy=ReplayPolicy.BilledOnce
        )
    assert isinstance(
        await store.claim(
            source_conversation_id=str(request.scope.thread_id),
            maximum_batch_size=10,
            maximum_attempts=1,
        ),
        CircuitOpen,
    )
    restored = await store.message_by_id(UUID(str(request.input_ids[0])))
    assert restored is not None
    assert restored.processed_at is None
    assert restored.processing_parked_at is not None
    assert restored.processing_attempts == 1

    await store.clear_parked(message_ids=(UUID(str(request.input_ids[0])),))

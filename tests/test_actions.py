from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from llm_tools import (
    CapabilityProfile,
    HostTable,
    InvocationPosition,
    ProfileId,
    ReplayPolicy,
    Reservation,
    RunLimits,
    Settlement,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolId,
    ToolPlan,
    canonical_json_bytes,
    raw_input_digest,
)
from llm_tools.execution import ParsedJson
from llm_tools.testing import InMemoryBudgetState
from pydantic import ValidationError
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
)
from jarvis.db import action, create_engine, message
from jarvis.messages import MessageStore, SettlementTrace
from jarvis.schedule_tools import (
    SCHEDULE_WAKE_SPEC,
    ScheduleTarget,
    schedule_family,
)

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
postgres = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


def _contract(
    arguments: Mapping[str, object],
    input_ids: tuple[UUID, ...],
    *,
    implementation_revision: str = "jarvis.synthetic-write.v1",
    tool_contract_revision: str = "1" * 64,
    policy_revision: str = "2" * 64,
    plan_revision: str = "3" * 64,
) -> ExecutionContract:
    return ExecutionContract(
        tool_contract_revision=tool_contract_revision,
        implementation_revision=implementation_revision,
        policy_revision=policy_revision,
        plan_revision=plan_revision,
        tool_effect=ToolEffect.Write,
        replay_policy=ReplayPolicy.ReDispatchable,
        input_digest=raw_input_digest(ParsedJson(dict(arguments))),
        max_attempts=2,
        claim_id=str(uuid4()),
        through_checkpoint=str(input_ids[-1]),
        model_step_ordinal=1,
        input_message_ids=tuple(map(str, input_ids)),
        write_gate_supporting_owner_message_ids=(str(input_ids[-1]),),
    )


async def _origin(
    engine: AsyncEngine,
    *,
    source_conversation_id: str | None = None,
) -> UUID:
    identifier = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=identifier,
                role="owner",
                text="synthetic owner request",
                source="discord",
                source_conversation_id=(
                    source_conversation_id or f"synthetic-actions-{identifier}"
                ),
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                processed_at=None,
                processing_attempts=1,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )
    return identifier


def _budgets(max_attempts: int = 2) -> InMemoryBudgetState:
    return InMemoryBudgetState(
        RunLimits(
            max_calls=1,
            max_external_attempts=max_attempts,
            max_input_bytes=8_192,
            max_output_bytes=8_192,
            max_in_flight=1,
            max_elapsed_seconds=30.0,
        )
    )


def _reservation(max_attempts: int = 2) -> Reservation:
    return Reservation(
        calls=1,
        input_bytes=100,
        max_attempts=max_attempts,
        max_output_bytes=4_096,
    )


def _settlement(result: dict[str, object], attempts: int = 1) -> Settlement:
    return Settlement(
        actual_attempts=attempts,
        actual_output_bytes=len(canonical_json_bytes(result)),
    )


def test_execution_contract_is_closed_and_requires_exact_lineage() -> None:
    first = uuid4()
    second = uuid4()
    arguments = {"value": "synthetic"}
    contract = _contract(arguments, (first, second))

    assert contract.max_attempts == 2
    assert contract.tool_effect is ToolEffect.Write
    assert contract.replay_policy is ReplayPolicy.ReDispatchable
    assert set(contract.as_json()) == {
        "tool_contract_revision",
        "implementation_revision",
        "policy_revision",
        "plan_revision",
        "tool_effect",
        "replay_policy",
        "input_digest",
        "max_attempts",
        "claim_id",
        "through_checkpoint",
        "model_step_ordinal",
        "input_message_ids",
        "write_gate_supporting_owner_message_ids",
    }

    invalid = contract.as_json()
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        ExecutionContract.model_validate(invalid)

    invalid = contract.as_json()
    invalid["through_checkpoint"] = str(first)
    with pytest.raises(ValidationError):
        ExecutionContract.model_validate(invalid)

    invalid = contract.as_json()
    invalid["write_gate_supporting_owner_message_ids"] = [str(uuid4())]
    with pytest.raises(ValidationError):
        ExecutionContract.model_validate(invalid)

    invalid = contract.as_json()
    invalid["max_attempts"] = 3
    with pytest.raises(ValidationError):
        ExecutionContract.model_validate(invalid)


class _ScheduleTargets:
    async def schedule_target(self, action_id: UUID) -> ScheduleTarget:
        del action_id
        return ScheduleTarget(exists=False, is_schedule_create=False, status=None)


def test_schedule_contract_uses_corrected_canonical_identity() -> None:
    family = schedule_family(_ScheduleTargets())

    assert SCHEDULE_WAKE_SPEC.id == ToolId("schedule.wake")
    assert family.namespace == "schedule"
    assert family.bindings[0].implementation_revision == "jarvis-schedule-wake-v1"
    assert SCHEDULE_WAKE_SPEC.success_schema.semantic["type"] == "object"
    assert set(SCHEDULE_WAKE_SPEC.success_schema.semantic["properties"]) == {"receipt"}


@postgres
async def test_action_identity_is_immutable_and_idempotent(
    engine: AsyncEngine,
) -> None:
    origin = await _origin(engine)
    arguments = {"value": "synthetic"}
    contract = _contract(arguments, (origin,))
    identifier = uuid4()
    created_at = datetime.now(UTC)
    store = ActionStore(engine)

    first = await store.insert_automatic(
        tool_name=ToolId("synthetic.write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        action_id=identifier,
        created_at=created_at,
    )
    second = await store.insert_automatic(
        tool_name=ToolId("synthetic.write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        action_id=identifier,
        created_at=created_at,
    )

    assert first == second
    assert first.position == InvocationPosition(str(identifier))
    with pytest.raises(ActionPersistenceDefect):
        await store.insert_automatic(
            tool_name=ToolId("synthetic.write"),
            arguments={"value": "different"},
            execution_contract=_contract({"value": "different"}, (origin,)),
            origin_message_id=origin,
            action_id=identifier,
            created_at=created_at,
        )

    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            await connection.execute(
                update(action)
                .where(action.c.id == identifier)
                .values(arguments={"value": "mutated"})
            )
    await store.cancel_nonexecuting(
        action_id=identifier,
        result={"type": "test_cleanup_v1", "reason_code": "synthetic"},
    )


@postgres
async def test_approval_action_and_message_insert_atomically_and_idempotently(
    engine: AsyncEngine,
) -> None:
    conversation_id = f"synthetic-approval-{uuid4()}"
    origin = await _origin(engine, source_conversation_id=conversation_id)
    arguments = {"value": "synthetic approval"}
    contract = _contract(arguments, (origin,))
    action_id = uuid4()
    created_at = datetime.now(UTC)
    store = ActionStore(engine)

    first = await store.insert_awaiting_approval(
        tool_name=ToolId("synthetic.approval_write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        approval_text="Approve the complete synthetic payload?",
        source_conversation_id=conversation_id,
        action_id=action_id,
        created_at=created_at,
    )
    assert first.action_inserted
    assert first.message_inserted
    assert first.action.status == "awaiting_approval"
    assert first.action.approval_message_id == first.message_id
    async with engine.connect() as connection:
        approval = (
            (
                await connection.execute(
                    select(message).where(message.c.id == first.message_id)
                )
            )
            .mappings()
            .one()
        )
    assert approval["role"] == "assistant"
    assert approval["source"] == "discord"
    assert approval["source_conversation_id"] == conversation_id
    assert approval["source_message_id"] is None
    assert approval["processed_at"] == created_at
    assert await store.get_by_approval_message(first.message_id) == first.action
    assert await store.get_by_approval_message(uuid4()) is None

    await MessageStore(engine).mark_delivered(
        message_id=first.message_id,
        source_message_id="synthetic-discord-approval",
    )
    second = await store.insert_awaiting_approval(
        tool_name=ToolId("synthetic.approval_write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        approval_text="Approve the complete synthetic payload?",
        source_conversation_id=conversation_id,
        action_id=action_id,
        created_at=created_at,
    )
    assert second.action == first.action
    assert not second.action_inserted
    assert not second.message_inserted

    with pytest.raises(ActionPersistenceDefect):
        await store.insert_awaiting_approval(
            tool_name=ToolId("synthetic.approval_write"),
            arguments=arguments,
            execution_contract=contract,
            origin_message_id=origin,
            approval_text="Different synthetic approval text.",
            source_conversation_id=conversation_id,
            action_id=action_id,
            created_at=created_at,
        )


@postgres
async def test_failed_approval_insert_rolls_back_its_message(
    engine: AsyncEngine,
) -> None:
    conversation_id = f"synthetic-approval-rollback-{uuid4()}"
    origin = await _origin(engine, source_conversation_id=conversation_id)
    arguments = {"value": "automatic"}
    contract = _contract(arguments, (origin,))
    action_id = uuid4()
    created_at = datetime.now(UTC)
    store = ActionStore(engine)
    await store.insert_automatic(
        tool_name=ToolId("synthetic.write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        action_id=action_id,
        created_at=created_at,
    )

    with pytest.raises(ActionPersistenceDefect):
        await store.insert_awaiting_approval(
            tool_name=ToolId("synthetic.write"),
            arguments=arguments,
            execution_contract=contract,
            origin_message_id=origin,
            approval_text="Synthetic approval that must roll back.",
            source_conversation_id=conversation_id,
            action_id=action_id,
            created_at=created_at,
        )
    async with engine.connect() as connection:
        count = await connection.scalar(
            select(func.count())
            .select_from(message)
            .where(message.c.text == "Synthetic approval that must roll back.")
        )
    assert count == 0


@postgres
async def test_approval_claim_is_exact_and_executor_entry_is_separate(
    engine: AsyncEngine,
) -> None:
    conversation_id = f"synthetic-approval-claim-{uuid4()}"
    origin = await _origin(engine, source_conversation_id=conversation_id)
    arguments = {"value": "synthetic approval"}
    contract = _contract(arguments, (origin,))
    store = ActionStore(engine)
    inserted = await store.insert_awaiting_approval(
        tool_name=ToolId("synthetic.approval_write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        approval_text="Approve the synthetic effect?",
        source_conversation_id=conversation_id,
    )
    assert await store.pending_approvals(source_conversation_id=conversation_id) == (
        inserted.action,
    )

    with pytest.raises(ActionPersistenceDefect):
        await store.claim_approval(
            action_id=inserted.action.id,
            approval_message_id=inserted.message_id,
            discord_message_id="not-delivered",
            source_conversation_id=conversation_id,
        )
    await MessageStore(engine).mark_delivered(
        message_id=inserted.message_id,
        source_message_id="synthetic-discord-claim",
    )
    with pytest.raises(ActionPersistenceDefect):
        await store.claim_approval(
            action_id=inserted.action.id,
            approval_message_id=uuid4(),
            discord_message_id="synthetic-discord-claim",
            source_conversation_id=conversation_id,
        )
    with pytest.raises(ActionPersistenceDefect):
        await store.claim_approval(
            action_id=inserted.action.id,
            approval_message_id=inserted.message_id,
            discord_message_id="synthetic-discord-claim",
            source_conversation_id="different-channel",
        )

    decided_at = datetime.now(UTC)
    claimed = await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id="synthetic-discord-claim",
        source_conversation_id=conversation_id,
        decided_at=decided_at,
    )
    assert claimed.applied
    assert claimed.action.status == "executing"
    assert claimed.action.decided_at == decided_at
    assert claimed.action.attempts == 0
    duplicate = await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id="synthetic-discord-claim",
        source_conversation_id=conversation_id,
    )
    assert not duplicate.applied
    assert duplicate.action == claimed.action
    assert await store.pending_approvals(source_conversation_id=conversation_id) == ()
    assert await store.approved_not_entered() == (claimed.action,)

    recorder = ActionPositionRecorder(
        store=store,
        action_id=claimed.action.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
        preclaimed_approval=True,
    )
    recovered = ActionPositionRecorder(
        store=store,
        action_id=claimed.action.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    recovered_position = await recovered.occupy(
        position=claimed.action.position,
        tool_id=claimed.action.tool_name,
        tool_contract_revision=contract.tool_contract_revision,
        policy_revision=contract.policy_revision,
        plan_revision=contract.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=contract.replay_policy,
    )
    assert recovered_position.uncertain
    occupied = await recorder.occupy(
        position=claimed.action.position,
        tool_id=claimed.action.tool_name,
        tool_contract_revision=contract.tool_contract_revision,
        policy_revision=contract.policy_revision,
        plan_revision=contract.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=contract.replay_policy,
    )
    assert not occupied.uncertain
    await recorder.dispatch_started(
        position=claimed.action.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    entered = await store.get(claimed.action.id)
    assert entered is not None
    assert entered.status == "executing"
    assert entered.attempts == 1
    assert await store.approved_not_entered() == ()
    await store.resolve_reconciliation(
        action_id=entered.id,
        status="failed",
        result={"type": "Failure", "error": {"type": "SyntheticCleanup"}},
    )


@postgres
async def test_deny_is_safe_and_approve_deny_race_has_one_winner(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    conversation_id = f"synthetic-deny-{uuid4()}"
    origin = await _origin(engine, source_conversation_id=conversation_id)
    arguments = {"value": "deny synthetic approval"}
    denied = await store.insert_awaiting_approval(
        tool_name=ToolId("synthetic.approval_write"),
        arguments=arguments,
        execution_contract=_contract(arguments, (origin,)),
        origin_message_id=origin,
        approval_text="Deny the synthetic effect.",
        source_conversation_id=conversation_id,
    )
    await MessageStore(engine).mark_delivered(
        message_id=denied.message_id,
        source_message_id="synthetic-discord-deny",
    )
    decision = await store.deny_approval(
        action_id=denied.action.id,
        approval_message_id=denied.message_id,
        discord_message_id="synthetic-discord-deny",
        source_conversation_id=conversation_id,
    )
    assert decision.applied
    assert decision.action.status == "cancelled"
    assert decision.action.attempts == 0
    assert decision.action.completed_at == decision.action.decided_at
    assert decision.action.result == {
        "type": "approval_denied_v1",
        "reason_code": "owner_denied",
    }
    duplicate = await store.deny_approval(
        action_id=denied.action.id,
        approval_message_id=denied.message_id,
        discord_message_id="synthetic-discord-deny",
        source_conversation_id=conversation_id,
    )
    assert not duplicate.applied

    race_conversation = f"synthetic-approval-race-{uuid4()}"
    race_origin = await _origin(
        engine,
        source_conversation_id=race_conversation,
    )
    race_arguments = {"value": "race synthetic approval"}
    racing = await store.insert_awaiting_approval(
        tool_name=ToolId("synthetic.approval_write"),
        arguments=race_arguments,
        execution_contract=_contract(race_arguments, (race_origin,)),
        origin_message_id=race_origin,
        approval_text="Resolve the synthetic race.",
        source_conversation_id=race_conversation,
    )
    await MessageStore(engine).mark_delivered(
        message_id=racing.message_id,
        source_message_id="synthetic-discord-race",
    )
    approve, deny = await asyncio.gather(
        store.claim_approval(
            action_id=racing.action.id,
            approval_message_id=racing.message_id,
            discord_message_id="synthetic-discord-race",
            source_conversation_id=race_conversation,
        ),
        store.deny_approval(
            action_id=racing.action.id,
            approval_message_id=racing.message_id,
            discord_message_id="synthetic-discord-race",
            source_conversation_id=race_conversation,
        ),
    )
    assert sum(value.applied for value in (approve, deny)) == 1
    final = await store.get(racing.action.id)
    assert final is not None
    assert final.status in {"executing", "cancelled"}
    if final.status == "executing":
        await store.resolve_reconciliation(
            action_id=final.id,
            status="failed",
            result={"type": "Failure", "error": {"type": "SyntheticCleanup"}},
        )


@postgres
async def test_user_suspended_approval_lineage_is_repairable(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    conversation_id = f"synthetic-approval-repair-{uuid4()}"
    origin = await _origin(engine, source_conversation_id=conversation_id)
    arguments = {"value": "repair synthetic approval"}
    inserted = await store.insert_awaiting_approval(
        tool_name=ToolId("synthetic.approval_write"),
        arguments=arguments,
        execution_contract=_contract(arguments, (origin,)),
        origin_message_id=origin,
        approval_text="Approve or deny the synthetic repair action.",
        source_conversation_id=conversation_id,
    )
    await MessageStore(engine).mark_delivered(
        message_id=inserted.message_id,
        source_message_id="synthetic-discord-repair",
    )
    denied = await store.deny_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id="synthetic-discord-repair",
        source_conversation_id=conversation_id,
    )
    settlement = SettlementTrace(
        run_id=f"approval:{denied.action.execution_contract.claim_id}",
        through_checkpoint=str(origin),
        conclusion_kind="suspension",
        outcome="user",
    ).as_json(inserted.message_id)
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(message.c.id == origin)
            .values(processed_at=datetime.now(UTC), trace={"settlement": settlement})
        )

    assert await store.unreported_terminal(source_conversation_id=conversation_id) == (
        denied.action,
    )
    repaired = await store.finish_recovered_origin(
        action_id=denied.action.id,
        source_conversation_id=conversation_id,
        text="Synthetic approval was denied.",
    )
    assert repaired.inserted


@postgres
async def test_position_recorder_counts_entry_commits_and_replays(
    engine: AsyncEngine,
) -> None:
    origin = await _origin(engine)
    arguments = {"value": "synthetic"}
    contract = _contract(arguments, (origin,))
    store = ActionStore(engine)
    stored = await store.insert_automatic(
        tool_name=ToolId("synthetic.write"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    budgets = _budgets()

    occupied = await recorder.occupy(
        position=stored.position,
        tool_id=stored.tool_name,
        tool_contract_revision=contract.tool_contract_revision,
        policy_revision=contract.policy_revision,
        plan_revision=contract.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=contract.replay_policy,
    )
    assert occupied.terminal_result is None
    assert occupied.actual_attempts == 0
    assert not occupied.uncertain
    assert await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=_reservation(),
    )
    started = await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    assert started.actual_attempts == 0
    executing = await store.get(stored.id)
    assert executing is not None
    assert executing.status == "executing"
    assert executing.attempts == 1

    result: dict[str, object] = {
        "type": "Success",
        "value": {"provider_id": "synthetic-provider-id"},
    }
    committed = await recorder.terminalize_and_settle(
        position=stored.position,
        budgets=budgets,
        result=result,
        settlement=_settlement(result),
    )
    assert committed == result
    completed = await store.get(stored.id)
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.attempts == 1
    assert completed.result == result

    recovered = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    replay = await recovered.occupy(
        position=stored.position,
        tool_id=stored.tool_name,
        tool_contract_revision=contract.tool_contract_revision,
        policy_revision=contract.policy_revision,
        plan_revision=contract.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=contract.replay_policy,
    )
    assert replay.terminal_result == result
    with pytest.raises(ValueError):
        await recovered.occupy(
            position=InvocationPosition(str(uuid4())),
            tool_id=stored.tool_name,
            tool_contract_revision=contract.tool_contract_revision,
            policy_revision=contract.policy_revision,
            plan_revision=contract.plan_revision,
            input_digest=contract.input_digest,
            replay_policy=contract.replay_policy,
        )


@postgres
async def test_recovery_requires_proof_and_never_exceeds_two_entries(
    engine: AsyncEngine,
) -> None:
    origin = await _origin(engine)
    arguments = {"value": "synthetic"}
    contract = _contract(arguments, (origin,))
    store = ActionStore(engine)
    stored = await store.insert_automatic(
        tool_name=ToolId("gmail.update_draft"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=4,
    )
    budgets = _budgets(4)
    await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=_reservation(4),
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    await store.stage_gmail_update_basis(
        action_id=stored.id,
        draft_id="synthetic-draft",
        thread_id="synthetic-thread",
        jarvis_effect_id="a" * 64,
        old_content_digest="b" * 64,
    )
    with pytest.raises(ValueError):
        await recorder.dispatch_abandoned(
            position=stored.position,
            replay_policy=ReplayPolicy.ReDispatchable,
            actual_attempts=3,
            lease_recovered=False,
        )
    assert (await store.get(stored.id)).status == "executing"  # type: ignore[union-attr]

    await recorder.dispatch_abandoned(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
        actual_attempts=3,
        lease_recovered=True,
    )
    readmitted = await store.get(stored.id)
    assert readmitted is not None
    assert readmitted.attempts == 1
    assert readmitted.result == {
        "type": "action_recovery_v1",
        "actual_external_attempts": 3,
        "reconciliation_basis": {
            "type": "gmail_update_reconciliation_v1",
            "draft_id": "synthetic-draft",
            "thread_id": "synthetic-thread",
            "jarvis_effect_id": "a" * 64,
            "old_content_digest": "b" * 64,
        },
    }
    recovered = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=4,
    )
    occupied = await recovered.occupy(
        position=stored.position,
        tool_id=stored.tool_name,
        tool_contract_revision=contract.tool_contract_revision,
        policy_revision=contract.policy_revision,
        plan_revision=contract.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=contract.replay_policy,
    )
    assert occupied.actual_attempts == 3
    await recovered.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    exhausted = await store.get(stored.id)
    assert exhausted is not None
    assert exhausted.attempts == 2
    with pytest.raises(ActionPersistenceDefect):
        await recovered.dispatch_abandoned(
            position=stored.position,
            replay_policy=ReplayPolicy.ReDispatchable,
            actual_attempts=1,
            lease_recovered=True,
        )

    failure = {"type": "Failure", "error": {"type": "ProvedAbsentAtCeiling"}}
    resolved = await store.resolve_reconciliation(
        action_id=stored.id,
        status="failed",
        result=failure,
    )
    assert resolved.status == "failed"
    assert resolved.attempts == 2


@postgres
async def test_schedule_receipt_survives_due_lifecycle_and_replays(
    engine: AsyncEngine,
) -> None:
    origin = await _origin(engine)
    due = datetime.now(UTC) + timedelta(minutes=10)
    arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": due.isoformat(),
            "instruction": "Synthetic reminder",
        }
    }
    store = ActionStore(engine)
    family = schedule_family(store)
    catalog = ToolCatalog.compose((family,))
    binding = catalog.binding(ToolId("schedule.wake"))
    profile = CapabilityProfile(
        ProfileId("action_schedule_claim"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 5.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    contract = _contract(
        arguments,
        (origin,),
        implementation_revision=binding.implementation_revision,
        tool_contract_revision=binding.spec.tool_contract_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=ToolId("schedule.wake"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin,
        execute_after=due,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    budgets = _budgets()
    await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=_reservation(),
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    recorded_at = datetime.now(UTC)
    created: dict[str, object] = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "created",
                "action_id": str(stored.id),
                "execute_after": due.isoformat().replace("+00:00", "Z"),
                "arguments_digest": contract.input_digest,
                "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
            }
        },
    }
    await recorder.terminalize_and_settle(
        position=stored.position,
        budgets=budgets,
        result=created,
        settlement=_settlement(created),
    )
    queued = await store.get(stored.id)
    assert queued is not None
    assert queued.status == "queued"
    assert queued.completed_at is None
    assert queued.result is not None
    assert queued.result["wake_outcome"] is None
    next_due = await store.next_due_at()
    assert next_due is not None and next_due <= due

    claim = await store.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id="synthetic-channel",
        now=due,
    )
    assert claim is not None
    assert claim.action.status == "executing"
    assert claim.message_inserted
    repeated_claim = await store.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id="synthetic-channel",
        now=due,
    )
    assert repeated_claim is not None
    assert repeated_claim.waking_message_id == claim.waking_message_id
    assert not repeated_claim.message_inserted
    assert await store.next_due_at() != due
    async with engine.connect() as connection:
        waking = (
            (
                await connection.execute(
                    select(message).where(message.c.id == claim.waking_message_id)
                )
            )
            .mappings()
            .one()
        )
    assert waking["role"] == "host"
    assert waking["source"] == "schedule_wake"
    assert waking["source_message_id"] == str(stored.id)
    assert due.isoformat() in waking["text"]
    assert "Synthetic reminder" in waking["text"]
    conclusion_message_id = uuid4()
    finished_at = due + timedelta(seconds=1)
    finished = await store.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "concluded",
            "conclusion_message_id": str(conclusion_message_id),
            "recorded_at": finished_at.isoformat(),
        },
    )
    assert finished.status == "succeeded"
    assert finished.completed_at == finished_at

    recovered = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    replay = await recovered.occupy(
        position=stored.position,
        tool_id=ToolId("schedule.wake"),
        tool_contract_revision=contract.tool_contract_revision,
        policy_revision=contract.policy_revision,
        plan_revision=contract.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=contract.replay_policy,
    )
    assert replay.terminal_result == created


@postgres
async def test_schedule_cancellation_is_one_atomic_transaction(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    origin = await _origin(engine)
    due = datetime.now(UTC) + timedelta(hours=1)
    create_arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": due.isoformat(),
            "instruction": "Synthetic reminder",
        }
    }
    create_contract = _contract(create_arguments, (origin,))
    scheduled = await store.insert_automatic(
        tool_name=ToolId("schedule.wake"),
        arguments=create_arguments,
        execution_contract=create_contract,
        origin_message_id=origin,
        execute_after=due,
    )
    create_recorder = ActionPositionRecorder(
        store=store,
        action_id=scheduled.id,
        implementation_revision=create_contract.implementation_revision,
        max_external_attempts=2,
    )
    create_budgets = _budgets()
    await create_recorder.reserve(
        position=scheduled.position,
        budgets=create_budgets,
        reservation=_reservation(),
    )
    await create_recorder.dispatch_started(
        position=scheduled.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    creation_result: dict[str, object] = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "created",
                "action_id": str(scheduled.id),
                "execute_after": due.isoformat(),
                "arguments_digest": create_contract.input_digest,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        },
    }
    await create_recorder.terminalize_and_settle(
        position=scheduled.position,
        budgets=create_budgets,
        result=creation_result,
        settlement=_settlement(creation_result),
    )

    cancel_origin = await _origin(engine)
    cancel_arguments: dict[str, object] = {
        "request": {"type": "cancel", "target_action_id": str(scheduled.id)}
    }
    cancel_contract = _contract(cancel_arguments, (cancel_origin,))
    cancellation = await store.insert_automatic(
        tool_name=ToolId("schedule.wake"),
        arguments=cancel_arguments,
        execution_contract=cancel_contract,
        origin_message_id=cancel_origin,
    )
    cancel_recorder = ActionPositionRecorder(
        store=store,
        action_id=cancellation.id,
        implementation_revision=cancel_contract.implementation_revision,
        max_external_attempts=2,
    )
    cancel_budgets = _budgets()
    await cancel_recorder.reserve(
        position=cancellation.position,
        budgets=cancel_budgets,
        reservation=_reservation(),
    )
    await cancel_recorder.dispatch_started(
        position=cancellation.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    cancelled_at = datetime.now(UTC)
    cancellation_result: dict[str, object] = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "cancelled",
                "target_action_id": str(scheduled.id),
                "recorded_at": cancelled_at.isoformat(),
            }
        },
    }
    await cancel_recorder.terminalize_and_settle(
        position=cancellation.position,
        budgets=cancel_budgets,
        result=cancellation_result,
        settlement=_settlement(cancellation_result),
    )

    target = await store.get(scheduled.id)
    cancel = await store.get(cancellation.id)
    assert target is not None and cancel is not None
    assert target.status == "cancelled"
    assert target.result is not None
    assert target.result["wake_outcome"] == {
        "type": "cancelled",
        "cancellation_action_id": str(cancellation.id),
        "recorded_at": cancelled_at.isoformat(),
    }
    assert cancel.status == "succeeded"
    assert cancel.result == cancellation_result


@postgres
async def test_failed_schedule_cancel_rolls_back_both_rows(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    target_origin = await _origin(engine)
    target_arguments = {"value": "not a schedule"}
    target = await store.insert_automatic(
        tool_name=ToolId("synthetic.write"),
        arguments=target_arguments,
        execution_contract=_contract(target_arguments, (target_origin,)),
        origin_message_id=target_origin,
    )
    cancel_origin = await _origin(engine)
    arguments: dict[str, object] = {
        "request": {"type": "cancel", "target_action_id": str(target.id)}
    }
    contract = _contract(arguments, (cancel_origin,))
    cancellation = await store.insert_automatic(
        tool_name=ToolId("schedule.wake"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=cancel_origin,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=cancellation.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    )
    budgets = _budgets()
    await recorder.reserve(
        position=cancellation.position,
        budgets=budgets,
        reservation=_reservation(),
    )
    await recorder.dispatch_started(
        position=cancellation.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    result: dict[str, object] = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "cancelled",
                "target_action_id": str(target.id),
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        },
    }
    with pytest.raises(ActionPersistenceDefect):
        await recorder.terminalize_and_settle(
            position=cancellation.position,
            budgets=budgets,
            result=result,
            settlement=_settlement(result),
        )
    unchanged_target = await store.get(target.id)
    unchanged_cancel = await store.get(cancellation.id)
    assert unchanged_target is not None and unchanged_target.status == "queued"
    assert unchanged_cancel is not None and unchanged_cancel.status == "executing"
    await store.resolve_reconciliation(
        action_id=cancellation.id,
        status="failed",
        result={"type": "Failure", "error": {"type": "BudgetExceeded"}},
    )
    await store.cancel_nonexecuting(
        action_id=target.id,
        result={"type": "test_cleanup_v1", "reason_code": "synthetic"},
    )


@postgres
async def test_resolution_messages_are_per_state_and_idempotent(
    engine: AsyncEngine,
) -> None:
    origin = await _origin(engine)
    arguments = {"value": "synthetic"}
    store = ActionStore(engine)
    stored = await store.insert_automatic(
        tool_name=ToolId("synthetic.write"),
        arguments=arguments,
        execution_contract=_contract(arguments, (origin,)),
        origin_message_id=origin,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=stored.execution_contract.implementation_revision,
        max_external_attempts=2,
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    uncertain = await store.resolve_reconciliation(
        action_id=stored.id,
        status="uncertain",
        result={
            "type": "action_uncertainty_v1",
            "evidence_code": "synthetic-bounded-evidence",
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )
    assert uncertain.status == "uncertain"
    timestamp = datetime.now(UTC)
    first = await store.insert_resolution_message(
        action_id=stored.id,
        source_conversation_id="synthetic-channel",
        text="Synthetic action outcome is uncertain; inspect provider state.",
        created_at=timestamp,
    )
    second = await store.insert_resolution_message(
        action_id=stored.id,
        source_conversation_id="synthetic-channel",
        text="Synthetic action outcome is uncertain; inspect provider state.",
        created_at=timestamp,
    )
    assert first.inserted
    assert not second.inserted
    assert first.message_id == second.message_id

    success: dict[str, object] = {
        "type": "Success",
        "value": {"provider_id": "synthetic"},
    }
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="succeeded",
        result=success,
    )
    later = await store.insert_resolution_message(
        action_id=stored.id,
        source_conversation_id="synthetic-channel",
        text="Synthetic action was later confirmed successful.",
    )
    assert later.inserted
    assert later.message_id != first.message_id

    async with engine.connect() as connection:
        source_ids = tuple(
            (
                await connection.execute(
                    select(message.c.source_message_id)
                    .where(message.c.id.in_((first.message_id, later.message_id)))
                    .order_by(message.c.source_message_id)
                )
            ).scalars()
        )
    assert source_ids == (
        f"{stored.id}:succeeded",
        f"{stored.id}:uncertain",
    )

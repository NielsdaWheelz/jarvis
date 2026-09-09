from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from llm_tools import ReplayPolicy, ToolEffect, ToolId, raw_input_digest
from llm_tools.execution import ParsedJson

from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
    codex_uncertainty_result,
)
from jarvis.codex_tools import (
    CodexActionEvidence,
    CodexStartInput,
    CodexThreadPrefix,
    CodexThreadTarget,
)
from jarvis.db import create_engine
from jarvis.messages import ACTION_MODEL_CONTEXT_SEPARATOR, MessageStore
from jarvis.write_dispatch import action_resolution_text
from jarvis.write_policy import classify_write, write_effect_descriptor


def test_codex_owner_write_has_closed_authority_projection_without_prompt() -> None:
    value = CodexStartInput(
        profile="work",
        cwd="/synthetic/work",
        name="review",
        prompt="Synthetic worker instruction.",
    )
    assert (
        classify_write(
            ToolId("codex.start"), value, verified_owner_only_calendar_ids=()
        )
        == "automatic"
    )
    descriptor = write_effect_descriptor(ToolId("codex.start"), value)
    assert descriptor.operation == "start"
    assert {(item.kind, item.value) for item in descriptor.targets} == {
        ("profile", "work"),
        ("cwd", "/synthetic/work"),
        ("terminal_name", "review"),
    }
    assert value.prompt not in descriptor.model_dump_json()


def _contract(*, billed_once: bool = False) -> ExecutionContract:
    origin = str(uuid4())
    return ExecutionContract.model_validate(
        {
            "tool_contract_revision": "synthetic-control-contract",
            "implementation_revision": "jarvis.codex.start.v1",
            "policy_revision": "synthetic-policy",
            "plan_revision": "synthetic-plan",
            "tool_effect": ToolEffect.Write,
            "replay_policy": (
                ReplayPolicy.BilledOnce if billed_once else ReplayPolicy.ReDispatchable
            ),
            "input_digest": raw_input_digest(ParsedJson({"profile": "work"})),
            "max_attempts": 1 if billed_once else 2,
            "claim_id": str(uuid4()),
            "through_checkpoint": origin,
            "model_step_ordinal": 1,
            "input_message_ids": [origin],
            "write_gate_supporting_owner_message_ids": [origin],
        }
    )


def test_codex_action_contract_accepts_exactly_one_billed_once_entry() -> None:
    contract = _contract(billed_once=True)
    assert contract.replay_policy is ReplayPolicy.BilledOnce
    assert contract.max_attempts == 1


def test_failed_launch_resolution_preserves_surviving_thread_prefix() -> None:
    contract = _contract(billed_once=True)
    prefix = {
        "type": "thread",
        "thread": {
            "profile": "work",
            "thread_handle": "12345678-1234-4234-8234-123456789abc",
        },
    }
    result: dict[str, object] = {
        "type": "Failure",
        "error": {"type": "Partial", "stage": "terminal", "prefix": prefix},
    }
    now = datetime.now(UTC)
    action = StoredAction(
        id=uuid4(),
        tool_name=ToolId("codex.start"),
        arguments={"profile": "work"},
        execution_contract=contract,
        status="failed",
        attempts=1,
        execute_after=None,
        origin_message_id=UUID(contract.input_message_ids[0]),
        approval_message_id=None,
        created_at=now,
        decided_at=None,
        completed_at=now,
        result=result,
    )
    text = action_resolution_text(action)
    safe_text, encoded_context = text.split(ACTION_MODEL_CONTEXT_SEPARATOR)
    context = json.loads(encoded_context)
    assert context["result"] == result, (
        "recovery must retain the exact surviving prefix"
    )
    assert "12345678-1234-4234-8234-123456789abc" in safe_text
    assert "terminal" in safe_text


def test_unknown_resolution_preserves_confirmed_prefix_without_claiming_failure() -> (
    None
):
    from dataclasses import replace

    contract = _contract(billed_once=True)
    now = datetime.now(UTC)
    evidence = CodexActionEvidence(
        stage="terminal",
        prefix=CodexThreadPrefix(
            thread=CodexThreadTarget(
                profile="work", thread_handle="12345678-1234-4234-8234-123456789abc"
            )
        ),
    )
    entered = StoredAction(
        id=uuid4(),
        tool_name=ToolId("codex.start"),
        arguments={"profile": "work"},
        execution_contract=contract,
        status="executing",
        attempts=1,
        execute_after=None,
        origin_message_id=UUID(contract.input_message_ids[0]),
        approval_message_id=None,
        created_at=now,
        decided_at=None,
        completed_at=None,
        result=evidence.model_dump(mode="json"),
    )
    result = codex_uncertainty_result(entered)
    uncertain = replace(entered, status="uncertain", result=result, completed_at=now)
    assert codex_uncertainty_result(uncertain) == result
    text = action_resolution_text(uncertain)
    context = json.loads(text.split(ACTION_MODEL_CONTEXT_SEPARATOR)[1])
    assert context["result"]["error"] == {
        "type": "Unknown",
        "stage": "terminal",
        "prefix": evidence.prefix.model_dump(mode="json"),
    }


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("JARVIS_TEST_DATABASE_URL"),
    reason="requires the disposable PostgreSQL action boundary",
)
async def test_uncertain_codex_action_survives_restart_without_reentry() -> None:
    contract = _contract(billed_once=True)
    origin = UUID(contract.input_message_ids[0])
    channel = f"synthetic-codex-{origin}"
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    try:
        messages = MessageStore(engine)
        await messages.insert_waking(
            role="owner",
            text="Synthetic current owner launch request.",
            source="discord",
            source_conversation_id=channel,
            source_message_id=str(origin),
            created_at=datetime.now(UTC),
            message_id=origin,
        )
        actions = ActionStore(engine)
        action = await actions.insert_automatic(
            tool_name=ToolId("codex.start"),
            arguments={"profile": "work"},
            execution_contract=contract,
            origin_message_id=origin,
        )

        def recorder() -> ActionPositionRecorder:
            return ActionPositionRecorder(
                store=ActionStore(engine),
                action_id=action.id,
                implementation_revision=contract.implementation_revision,
                max_external_attempts=8,
            )

        first = recorder()
        await first.dispatch_started(
            position=action.position, replay_policy=ReplayPolicy.BilledOnce
        )
        evidence = CodexActionEvidence(
            stage="terminal",
            prefix=CodexThreadPrefix(
                thread=CodexThreadTarget(
                    profile="work", thread_handle="12345678-1234-4234-8234-123456789abc"
                )
            ),
        )
        await actions.stage_codex_control(action_id=action.id, evidence=evidence)
        await first.uncertain(position=action.position)

        restarted = recorder()
        observed = await restarted.occupy(
            position=action.position,
            tool_id=action.tool_name,
            tool_contract_revision=contract.tool_contract_revision,
            policy_revision=contract.policy_revision,
            plan_revision=contract.plan_revision,
            input_digest=contract.input_digest,
            replay_policy=ReplayPolicy.BilledOnce,
        )
        assert observed.uncertain
        with pytest.raises((ActionPersistenceDefect, ValueError)):
            await actions.requeue_after_proved_absence(
                action.id, actual_external_attempts=0, max_external_attempts=8
            )
        stored = await actions.get(action.id)
        assert stored is not None
        assert stored.status == "uncertain"
        assert stored.attempts == 1
        assert stored.result is not None
        assert stored.result["control"] == evidence.model_dump(mode="json")
        first_resolution = await actions.finish_recovered_origin(
            action_id=action.id,
            source_conversation_id=channel,
            text=action_resolution_text(stored),
        )
        repeated_resolution = await actions.finish_recovered_origin(
            action_id=action.id,
            source_conversation_id=channel,
            text=action_resolution_text(stored),
        )
        assert first_resolution.inserted
        assert not repeated_resolution.inserted
        assert first_resolution.message_id == repeated_resolution.message_id
        consumed = await messages.message_by_id(origin)
        assert consumed is not None and consumed.processed_at is not None
    finally:
        await engine.dispose()

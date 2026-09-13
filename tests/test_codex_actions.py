from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from llm_agent_kernel import Checkpoint, InputId, ThreadId
from llm_agent_kernel.decisions import ModelDecisionRequest, ModelDecisionScope
from llm_tools import ReplayPolicy, ToolEffect, ToolId, raw_input_digest
from llm_tools.execution import ParsedJson
from provider_fixture import frozen_provider
from provider_runtime.agent_runtime import AgentSessionRef, AgentTerminal

from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
    agent_uncertainty_result,
)
from jarvis.agent_tools import AgentActionEvidence, AgentStartInput, AgentStopResult
from jarvis.codex_history import (
    CodexActionEvidence,
    CodexThreadPrefix,
    CodexThreadTarget,
)
from jarvis.connectors import GoogleTokenManager
from jarvis.db import create_engine
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.definitions import build_slice1_definitions
from jarvis.messages import (
    ACTION_MODEL_CONTEXT_SEPARATOR,
    ClaimedMessages,
    MessageStore,
)
from jarvis.ownership import deployment_ownership
from jarvis.write_connectors import GoogleWriteConnector
from jarvis.write_dispatch import ActionRecovery, action_resolution_text
from jarvis.write_policy import classify_write, write_effect_descriptor


def test_agent_start_has_closed_authority_projection() -> None:
    value = AgentStartInput(
        machine="devbox",
        profile="work",
        cwd="/synthetic/work",
        name="review",
    )
    assert (
        classify_write(
            ToolId("agent.start"), value, verified_owner_only_calendar_ids=()
        )
        == "automatic"
    )
    descriptor = write_effect_descriptor(ToolId("agent.start"), value)
    assert descriptor.operation == "start"
    assert {(item.kind, item.value) for item in descriptor.targets} == {
        ("machine", "devbox"),
        ("profile", "work"),
        ("cwd", "/synthetic/work"),
        ("terminal_name", "review"),
    }
    assert descriptor.omitted_freeform == ()


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
    result = {
        "type": "codex_uncertainty_v1",
        "evidence_code": "native-control-outcome-unconfirmed-no-repeat",
        "recorded_at": now.isoformat(),
        "control": evidence.model_dump(mode="json"),
    }
    uncertain = replace(entered, status="uncertain", result=result, completed_at=now)
    from jarvis.actions import (
        _validate_stored_action,  # pyright: ignore[reportPrivateUsage]
    )

    _validate_stored_action(uncertain)
    assert agent_uncertainty_result(uncertain) == result
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
async def test_uncertain_agent_action_survives_restart_without_reentry(
    tmp_path: Path,
) -> None:
    contract = _contract(billed_once=True)
    origin = UUID(contract.input_message_ids[0])
    channel = f"synthetic-codex-{origin}"
    now = datetime.now(UTC)
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            messages = MessageStore(database)
            await messages.insert_waking(
                role="owner",
                text="Synthetic current owner launch request.",
                source="discord",
                source_conversation_id=channel,
                source_message_id=str(origin),
                created_at=now,
                message_id=origin,
            )
            request = ModelDecisionRequest(
                scope=ModelDecisionScope(ThreadId(channel), InputId(str(origin))),
                ordinal=1,
                definition_fingerprint="a" * 64,
                plan_revision=contract.plan_revision,
                input_ids=(InputId(str(origin)),),
                through_checkpoint=Checkpoint(str(origin)),
                as_of=now,
                model_step_ordinal_before=0,
                protocol_repairs=0,
                canonical_content=("Synthetic original context.",),
                submitted_content=("Synthetic original context.",),
            )
            journal = PostgresModelDecisionJournal(database)
            await journal.arm(request)
            completed = await journal.complete(
                request,
                AgentTerminal(
                    status="succeeded",
                    failure=None,
                    final_text='{"kind":"call_tool","call_tool":{"tool_id":"agent.start",'
                    '"arguments":{"profile":"work"}},"finish":null}',
                    session_ref=AgentSessionRef(
                        "agent-session-ref.v1",
                        "codex",
                        "sdk",
                        "original-session",
                        "personal",
                        "a" * 64,
                        "b" * 64,
                    ),
                ),
            )
            actions = ActionStore(database)
            action = await actions.insert_automatic(
                tool_name=ToolId("agent.start"),
                arguments={"profile": "work"},
                execution_contract=contract,
                origin_message_id=origin,
            )
            first = ActionPositionRecorder(
                store=actions,
                action_id=action.id,
                implementation_revision=contract.implementation_revision,
                max_external_attempts=8,
            )
            await first.dispatch_started(
                position=action.position, replay_policy=ReplayPolicy.BilledOnce
            )
            evidence = AgentActionEvidence(
                observed=AgentStopResult(agent="unconfirmed", terminal="closed")
            )
            await actions.stage_agent_control(action_id=action.id, evidence=evidence)

        async with deployment_ownership(engine) as database:
            actions = ActionStore(database)
            restarted = ActionPositionRecorder(
                store=actions,
                action_id=action.id,
                implementation_revision=contract.implementation_revision,
                max_external_attempts=8,
            )
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

            def unexpected_request(request: httpx.Request) -> httpx.Response:
                raise AssertionError(f"recovery attempted external {request.method}")

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(unexpected_request), trust_env=False
            ) as client:
                recovery = ActionRecovery(
                    actions=actions,
                    google_write=GoogleWriteConnector(
                        client=client,
                        tokens=GoogleTokenManager(
                            state_path=tmp_path / "unused-google-state",
                            client=client,
                            client_id="synthetic",
                            client_secret="synthetic",
                            active_key_version="derived",
                            configured_keys=None,
                            single_secret="c3ludGhldGlj",
                        ),
                        stage_gmail_update_basis=actions.stage_gmail_update_basis,
                        stage_external_attempts=actions.stage_external_attempts,
                    ),
                    plan=build_slice1_definitions(
                        provider=frozen_provider(), owner_timezone="UTC"
                    ).plans["main"],
                    source_conversation_id=channel,
                )
                assert await recovery.recover(allow_queued_execution=False) == 1
                assert await recovery.recover(allow_queued_execution=False) == 0

            stored = await actions.get(action.id)
            assert stored is not None and stored.status == "uncertain"
            assert stored.attempts == 1
            assert stored.result is not None
            assert stored.result["control"] == evidence.model_dump(mode="json")
            messages = MessageStore(database)
            consumed = await messages.message_by_id(origin)
            assert consumed is not None and consumed.processed_at is not None
            assert (
                await PostgresModelDecisionJournal(database).latest(request.scope)
                == completed
            )
            claimed = await messages.claim(
                source_conversation_id=channel,
                maximum_batch_size=10,
                maximum_attempts=3,
            )
            assert isinstance(claimed, ClaimedMessages)
            assert len(claimed.messages) == 1
            resolution = claimed.messages[0]
            assert resolution.id != origin
            assert resolution.role == "host" and resolution.source == "action"
    finally:
        await engine.dispose()

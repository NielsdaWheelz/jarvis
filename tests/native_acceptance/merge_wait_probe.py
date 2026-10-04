"""Temporary real-Postgres worker/native merge proof; no provider or skid I/O.

Run with PYTHONPATH=src JARVIS_PROOF_DATABASE_URL pointing at the isolated
jarvis_native_merge database, then .venv/bin/python this file.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AgentRole,
    CancellationToken,
    Checkpoint,
    InputId,
    NativeDefect,
    NativeDefinition,
    NativeDelivery,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import (
    CapabilityProfile,
    EffectId,
    ExecutionContext,
    Native,
    ParsedJson,
    Principal,
    ProfileId,
    PromptSections,
    RunBudgetState,
    RunLimits,
    Scope,
    ToolCatalog,
    ToolEffect,
    ToolExecutor,
    ToolGrant,
    ToolId,
    ToolPlan,
    raw_input_digest,
)
from provider_runtime.agent_runtime import (
    AgentAccepted,
    AgentAttempt,
    AgentSessionRef,
    AgentTerminal,
    AgentTurnRef,
    CredentialRef,
    JsonSchemaAgentOutput,
    NativeTerminalEvidence,
    RawAgentOutput,
    freeze_json_value,
)
from sqlalchemy import select

from jarvis.action_requests import bind_action_requests
from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    agent_wait_state,
)
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.agent_tools import (
    AgentTarget,
    AgentWaitOutcome,
    AgentWriteTarget,
    WireFailure,
    agent_family,
)
from jarvis.db import create_engine, message, native_attempt
from jarvis.messages import MessageStore
from jarvis.native_journal import (
    PostgresNativeJournal,
    commit_product,
    recover_sealed_turn,
)
from jarvis.ownership import deployment_ownership
from jarvis.terminal import JarvisTerminal, TurnEvidence
from jarvis.write_dispatch import NoTelemetry


async def main() -> None:
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    checks: dict[str, bool] = {}
    try:
        async with deployment_ownership(engine) as database:
            conversation = "merge-proof-" + str(uuid4())
            owner = JarvisOwner(database, conversation)
            store = MessageStore(database)
            actions = ActionStore(database)
            agents = AgentController(
                cli_path=Path("/nonexistent/skid"),
                client_config_path=Path("/nonexistent/client"),
                actions=actions,
                source_conversation_id=conversation,
            )
            family = bind_action_requests(agent_family(agents))
            catalog = ToolCatalog.compose((family,))
            maximum = CapabilityProfile(
                ProfileId("merge-proof"),
                tuple(ToolGrant(spec.id, None) for spec in family.declarations),
                RunLimits(None, None, None, None, 1, None),
            ).freeze(catalog)
            plan = ToolPlan(maximum.id, Native()).freeze(catalog, maximum)
            definition = NativeDefinition(
                ProviderConfiguration(
                    CredentialRef("local_account", "proof"),
                    "proof",
                    "high",
                    "one",
                    "a" * 64,
                ),
                AgentRole("proof", PromptSections(())),
                JsonSchemaAgentOutput(
                    "jarvis_main", JarvisTerminal.model_json_schema()
                ),
                maximum,
                "one",
            )
            ref = AgentSessionRef(
                "agent-session-ref.v1",
                "codex",
                "sdk",
                "proof",
                "proof",
                "a" * 64,
                "b" * 64,
            )
            target = AgentTarget(machine="macbook", handle="t-0000000000000001")
            captured = AgentWriteTarget(target=target, ref="original-worker-ref")

            async def input_row(text: str):
                result = await store.insert_waking(
                    role="owner",
                    text=text,
                    source="merge_proof",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                )
                return result.message.id

            async def execute(
                identifier: UUID,
                tool: str,
                payload: dict[str, object],
                *,
                replay_id: UUID | None = None,
            ):
                binding = plan.catalog_view.binding(ToolId(tool))
                arguments = binding.spec.input_type.model_validate(
                    {
                        "request_ref": str(identifier),
                        "existing_action_ref": None,
                        "arguments": payload,
                    }
                ).model_dump(mode="json")
                action_id = replay_id or uuid4()
                if replay_id is None:
                    contract = ExecutionContract(
                        tool_contract_revision=binding.spec.tool_contract_revision,
                        implementation_revision=binding.implementation_revision,
                        policy_revision=binding.policy_revision,
                        plan_revision=plan.plan_revision,
                        tool_effect=ToolEffect.Write,
                        replay_policy=binding.replay_policy,
                        input_digest=raw_input_digest(ParsedJson(arguments)),
                        max_attempts=2,
                        claim_id=str(uuid4()),
                        through_checkpoint=str(identifier),
                        model_step_ordinal=1,
                        input_message_ids=(str(identifier),),
                        write_gate_supporting_owner_message_ids=(str(identifier),),
                        agent_target=captured if tool == "agent.wait" else None,
                    )
                    await actions.insert_automatic(
                        tool_name=ToolId(tool),
                        arguments=arguments,
                        execution_contract=contract,
                        origin_message_id=identifier,
                        action_id=action_id,
                    )
                recorder = ActionPositionRecorder(
                    store=actions,
                    action_id=action_id,
                    implementation_revision=binding.implementation_revision,
                    max_external_attempts=1,
                )
                result = await ToolExecutor.execute(
                    binding,
                    ParsedJson(arguments),
                    ExecutionContext(
                        plan=plan,
                        grant=plan.grant(binding.spec.id),
                        catalog_view=plan.catalog_view,
                        position=recorder.position,
                        recorder=recorder,
                        effect_id=EffectId(str(action_id)),
                        budgets=RunBudgetState(plan.profile.run_limits),
                        principal=Principal("proof"),
                        scope=Scope("proof"),
                        cancellation=CancellationToken(),
                        telemetry=NoTelemetry(),
                    ),
                )
                return action_id, result

            async def sealed(ids: tuple[UUID, ...], final: JarvisTerminal):
                attempt_id = str(uuid4())
                request = NativeRequest(
                    attempt_id,
                    owner.permit("jarvis-native:" + attempt_id),
                    "thread",
                    tuple(InputId(str(value)) for value in ids),
                    PromptSections(()),
                    PromptSections(()),
                    plan,
                    "restart_reasoning",
                    None,
                    Checkpoint(str(ids[-1])),
                )
                journal = PostgresNativeJournal(
                    database, definition=definition, plan=plan, owner=owner
                )
                prepared = AgentAttempt(attempt_id, "a" * 64)
                await journal.arm(
                    request,
                    prepared,
                    definition_fingerprint=definition.session_fingerprint(plan),
                    submitted_request=freeze_json_value({"prepared": attempt_id}),
                )
                turn = AgentTurnRef(ref, "turn-" + attempt_id)
                await journal.bind(attempt_id, turn)
                await journal.record_delivery(
                    NativeDelivery(
                        attempt_id,
                        "initial-" + attempt_id,
                        request.input_ids,
                        "initial",
                        "prepared",
                        None,
                    )
                )
                await journal.record_delivery(
                    NativeDelivery(
                        attempt_id,
                        "initial-" + attempt_id,
                        request.input_ids,
                        "initial",
                        "sent",
                        AgentAccepted(prepared, turn),
                    )
                )
                document = final.model_dump(mode="json")
                terminal = AgentTerminal(
                    "succeeded",
                    None,
                    json.dumps(document),
                    ref,
                    NativeTerminalEvidence(prepared, turn, "codex-turn-completed.v1"),
                    RawAgentOutput(freeze_json_value(document)),
                )
                await journal.record_outcome(attempt_id, terminal)
                result = await recover_sealed_turn(database, owner, attempt_id)
                assert result is not None
                return result

            origin = await input_row("watch this worker; retain the original receipt")
            payload = {"target": target.model_dump(mode="json")}
            action_id, receipt = await execute(origin, "agent.wait", payload)
            stored = await actions.get(action_id)
            assert stored is not None
            state = agent_wait_state(stored)
            checks["wrapped-registration-original-capture"] = (
                stored.status == "queued"
                and state.registration_receipt.arguments_digest
                == stored.execution_contract.input_digest
                and stored.execution_contract.agent_target == captured
                and receipt["type"] == "Success"
            )
            final = JarvisTerminal.model_validate(
                {
                    "response": {
                        "type": "answered",
                        "text": (
                            "observation is registered; completion is unconfirmed."
                        ),
                    },
                    "input_outcomes": [
                        {
                            "input_id": str(origin),
                            "disposition": "complete",
                            "wait_reason": None,
                            "action_refs": [],
                        }
                    ],
                }
            )
            turn = await sealed((origin,), final)
            try:
                await commit_product(database, owner, turn, final, TurnEvidence())
                checks["registered-wait-allows-owner-completion"] = True
            except NativeDefect as error:
                checks["registered-wait-allows-owner-completion"] = False
                print("RED", str(error))
                async with database.begin() as connection:
                    from sqlalchemy import update

                    await connection.execute(
                        update(native_attempt)
                        .where(native_attempt.c.id == UUID(turn.attempt_id))
                        .values(fenced_at=datetime.now(UTC))
                    )
            assert await actions.finish_agent_wait(
                action_id,
                AgentWaitOutcome(
                    target=target, outcome="timeout", recorded_at=datetime.now(UTC)
                ),
                source_conversation_id=conversation,
            )
            _, replay = await execute(
                origin, "agent.wait", payload, replay_id=action_id
            )
            checks["replay-original-registration-after-outcome"] = replay == receipt
            async with database.connect() as connection:
                event = (
                    (
                        await connection.execute(
                            select(message).where(
                                message.c.source == "action",
                                message.c.source_message_id
                                == str(action_id) + ":succeeded",
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
            silent = JarvisTerminal.model_validate(
                {
                    "response": {"type": "silent", "reason": "owner_needs_no_response"},
                    "input_outcomes": [],
                }
            )
            turn = await sealed((event["id"],), silent)
            try:
                await commit_product(database, owner, turn, silent, TurnEvidence())
                async with database.connect() as connection:
                    row = (
                        (
                            await connection.execute(
                                select(message).where(message.c.id == event["id"])
                            )
                        )
                        .mappings()
                        .one()
                    )
                    attempt = (
                        (
                            await connection.execute(
                                select(native_attempt).where(
                                    native_attempt.c.id == UUID(turn.attempt_id)
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                checks["unmixed-wait-event-silent-without-invented-outbox"] = (
                    row["processed_at"] is not None
                    and row["trace"].get("conclusion_message_id") is None
                    and attempt["product_outcome"]["response_id"] is None
                )
            except NativeDefect as error:
                checks["unmixed-wait-event-silent-without-invented-outbox"] = False
                print("RED", str(error))
                async with database.begin() as connection:
                    from sqlalchemy import update

                    await connection.execute(
                        update(native_attempt)
                        .where(native_attempt.c.id == UUID(turn.attempt_id))
                        .values(fenced_at=datetime.now(UTC))
                    )

            mixed_owner = await input_row(
                "owner input requires a useful visible result"
            )
            turn = await sealed((event["id"], mixed_owner), silent)
            try:
                await commit_product(database, owner, turn, silent, TurnEvidence())
            except NativeDefect as error:
                assert str(error) == "host events require a visible response"
                checks["mixed-owner-wait-event-retains-notice-barrier"] = True
                async with database.begin() as connection:
                    from sqlalchemy import update

                    await connection.execute(
                        update(native_attempt)
                        .where(native_attempt.c.id == UUID(turn.attempt_id))
                        .values(fenced_at=datetime.now(UTC))
                    )
            else:
                checks["mixed-owner-wait-event-retains-notice-barrier"] = False

            watched_origin = await input_row("watch without blocking later ingress")
            watched_id, _ = await execute(watched_origin, "agent.wait", payload)
            observed = asyncio.Event()
            release = asyncio.Event()
            notified = asyncio.Event()

            class ControlledObservation(AgentController):
                async def _call(self, argv, model, **kwargs):
                    assert argv[:3] == ["wait", "--ref", captured.ref]
                    observed.set()
                    await release.wait()
                    return WireFailure(code="unavailable", dispatch="not_sent")

            observer = ControlledObservation(
                cli_path=agents.cli_path,
                client_config_path=agents.client_config_path,
                actions=actions,
                source_conversation_id=conversation,
            )
            token = CancellationToken()

            async def active():
                return False

            task = asyncio.create_task(
                observer.run_waits(
                    token, paused=active, plan=plan, on_event=notified.set
                )
            )
            try:
                await asyncio.wait_for(observed.wait(), 2)
                later = await asyncio.wait_for(
                    input_row("later owner input is admitted while observation blocks"),
                    2,
                )
                async with database.connect() as connection:
                    checks["watcher-does-not-block-owner-ingress"] = (
                        await connection.scalar(
                            select(message.c.request_state).where(message.c.id == later)
                        )
                        == "pending"
                    )
                release.set()
                await asyncio.wait_for(notified.wait(), 2)
                watched = await actions.get(watched_id)
                assert watched is not None
                checks["watcher-original-ref-settlement"] = (
                    agent_wait_state(watched).wait_outcome.outcome == "unavailable"
                )
            finally:
                token.cancel()
                await asyncio.wait_for(task, 2)

            next_origin = await input_row("watch and then cancel observation")
            waiting_id, watching = await execute(next_origin, "agent.wait", payload)
            _, cancelled = await execute(
                next_origin, "agent.cancel_wait", {"action_id": str(waiting_id)}
            )
            assert cancelled["type"] == "Success"
            waiting = await actions.get(waiting_id)
            assert waiting is not None
            checks["cancel-keeps-registration-and-settles-once"] = (
                agent_wait_state(waiting).registration_receipt.model_dump(mode="json")
                == watching["value"]
                and agent_wait_state(waiting).wait_outcome.outcome == "cancelled"
            )
            stopped_origin = await input_row(
                "this pending wait must not enter after stop"
            )
            await store.insert_waking(
                role="owner",
                text="stop",
                source="merge_proof",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                control_kind="stop",
            )
            try:
                await execute(stopped_origin, "agent.wait", payload)
            except ActionPersistenceDefect:
                checks["stopped-owner-grants-no-new-entry"] = True
            else:
                checks["stopped-owner-grants-no-new-entry"] = False
    finally:
        await engine.dispose()
    artifact = (
        Path(tempfile.mkdtemp(prefix="jarvis-native-merge-wait-")) / "receipt.json"
    )
    artifact.write_text(
        json.dumps(
            {
                "kind": "actual-postgres-controlled-native-evidence",
                "provider_calls": 0,
                "skid_calls": 0,
                "checks": checks,
                "source_sha256": {
                    str(path): sha256(path.read_bytes()).hexdigest()
                    for path in Path("src/jarvis").glob("*.py")
                },
            },
            indent=2,
        )
    )
    print(artifact, json.dumps(checks))
    assert all(checks.values()), checks


asyncio.run(main())

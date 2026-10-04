"""Temporary real-PG native callback dispatch/reply/replay; controlled gate/worker.

PYTHONPATH=src JARVIS_PROOF_DATABASE_URL=... .venv/bin/python this-file
No provider, private connector or real worker calls are permitted.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AgentRole,
    CancellationToken,
    Checkpoint,
    DispatchCompleted,
    InputId,
    NativeDefect,
    NativeDefinition,
    NativeDelivery,
    NativeDispatchLineage,
    NativeInvocationProposal,
    NativeReply,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import (
    CapabilityProfile,
    Native,
    ParsedJson,
    ProfileId,
    PromptSections,
    RunBudgetState,
    RunLimits,
    ToolCatalog,
    ToolGrant,
    ToolId,
    ToolPlan,
    raw_input_digest,
)
from provider_runtime.agent_runtime import (
    AgentAccepted,
    AgentAttempt,
    AgentInputRecorded,
    AgentSessionRef,
    AgentTurnRef,
    CredentialRef,
    JsonSchemaAgentOutput,
    freeze_json_value,
)
from sqlalchemy import func, select

from jarvis.action_requests import bind_action_requests
from jarvis.actions import ActionStore, agent_wait_state
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.agent_tools import (
    AgentTarget,
    AgentWaitOutcome,
    AgentWriteTarget,
    WireFailure,
    agent_family,
)
from jarvis.db import action, create_engine, native_invocation
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.native_runtime import NativeInputs
from jarvis.ownership import deployment_ownership
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.schedule_tools import schedule_family
from jarvis.terminal import JarvisTerminal
from jarvis.write_dispatch import WriteToolDispatcher
from jarvis.write_gate import WriteGateDecision


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    checks = {}
    failures = {}
    try:
        async with deployment_ownership(engine) as database:
            actions = ActionStore(database)
            store = MessageStore(database)
            target = AgentTarget(machine="macbook", handle="t-0000000000000001")
            captured = AgentWriteTarget(target=target, ref="original-controlled-ref")
            worker_calls = []

            class ControlledWorker(AgentController):
                async def locate(self, tool_id, value):
                    assert value.target == target
                    return captured

                async def _call(self, argv, model, **kwargs):
                    worker_calls.append(argv)
                    assert argv[1:3] == ["--ref", captured.ref]
                    return WireFailure(code="unavailable", dispatch="not_sent")

            class ControlledGate:
                async def evaluate(self, owner_inputs, **kwargs):
                    return WriteGateDecision(
                        "allow",
                        tuple(value.message_id for value in owner_inputs),
                        None,
                        "controlled_allow",
                        None,
                    )

            agents = ControlledWorker(
                cli_path=Path("/nonexistent/skid"),
                client_config_path=Path("/nonexistent/client"),
                actions=actions,
                source_conversation_id="controlled",
            )
            families = (
                bind_action_requests(agent_family(agents)),
                bind_action_requests(schedule_family(actions)),
            )
            catalog = ToolCatalog.compose(families)
            maximum = CapabilityProfile(
                ProfileId("native-reply-proof"),
                tuple(
                    ToolGrant(spec.id, None)
                    for family in families
                    for spec in family.declarations
                ),
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
            for tool, payload in (
                ("agent.wait", {"target": target.model_dump(mode="json")}),
                (
                    "agent.send",
                    {
                        "target": target.model_dump(mode="json"),
                        "text": "continue the original task",
                    },
                ),
                (
                    "schedule.wake",
                    {
                        "request": {
                            "type": "create",
                            "execute_after": (
                                datetime.now(UTC) + timedelta(hours=1)
                            ).isoformat(),
                            "instruction": "remind me of the original task",
                        }
                    },
                ),
            ):
                conversation = "native-reply-proof-" + str(uuid4())
                owner = JarvisOwner(database, conversation)
                origin = (
                    await store.insert_waking(
                        role="owner",
                        text="controlled original intent",
                        source="native_reply_probe",
                        source_conversation_id=conversation,
                        source_message_id=str(uuid4()),
                        created_at=datetime.now(UTC),
                    )
                ).message.id
                attempt_id = str(uuid4())
                request = NativeRequest(
                    attempt_id,
                    owner.permit("jarvis-native:" + attempt_id),
                    "thread",
                    (InputId(str(origin)),),
                    PromptSections(()),
                    PromptSections(()),
                    plan,
                    "restart_reasoning",
                    None,
                    Checkpoint(str(origin)),
                )
                journal = PostgresNativeJournal(
                    database, definition=definition, plan=plan, owner=owner
                )
                prepared = AgentAttempt(attempt_id, "a" * 64)
                turn = AgentTurnRef(ref, "controlled-turn-" + attempt_id)
                await journal.arm(
                    request,
                    prepared,
                    definition_fingerprint=definition.session_fingerprint(plan),
                    submitted_request=freeze_json_value({"prepared": attempt_id}),
                )
                await journal.bind(attempt_id, turn)
                delivery_id = "initial-" + attempt_id
                await journal.record_delivery(
                    NativeDelivery(
                        attempt_id,
                        delivery_id,
                        request.input_ids,
                        "initial",
                        "prepared",
                        None,
                    )
                )
                await journal.record_delivery(
                    NativeDelivery(
                        attempt_id,
                        delivery_id,
                        request.input_ids,
                        "initial",
                        "sent",
                        AgentAccepted(prepared, turn),
                    )
                )
                await journal.record_delivery(
                    NativeDelivery(
                        attempt_id,
                        delivery_id,
                        request.input_ids,
                        "initial",
                        "recorded",
                        AgentInputRecorded(
                            turn, delivery_id, "controlled-item-" + attempt_id
                        ),
                    )
                )
                inputs = NativeInputs(
                    owner=owner,
                    store=store,
                    plan=plan,
                    context=SimpleNamespace(),
                    cancellation=CancellationToken(),
                    maximum_batch_size=20,
                )
                dispatcher = WriteToolDispatcher(
                    checkpoint=inputs,
                    gate=ControlledGate(),
                    actions=actions,
                    google_write=SimpleNamespace(),
                    agents=agents,
                    read=ReadToolDispatcher(
                        host_secrets=(), recorder=PostgresReadRecorder(database)
                    ),
                    owner_timezone="UTC",
                    source_conversation_id=conversation,
                    verified_owner_only_calendar_ids=(),
                    host_secrets=(),
                    schedule_changed=lambda: None,
                    dispatch_lane=asyncio.Lock(),
                )
                binding = plan.catalog_view.binding(ToolId(tool))
                arguments = binding.spec.input_type.model_validate(
                    {
                        "request_ref": str(origin),
                        "existing_action_ref": None,
                        "arguments": payload,
                    }
                )
                document = arguments.model_dump(mode="json")
                proposal = NativeInvocationProposal(
                    attempt_id,
                    "controlled-call-" + str(uuid4()),
                    binding.spec.id,
                    freeze_json_value(document),
                    raw_input_digest(ParsedJson(document)),
                    plan.plan_revision,
                    binding.spec.tool_contract_revision,
                    binding.implementation_revision,
                    binding.policy_revision,
                    request.input_ids,
                    request.through_checkpoint,
                    None,
                )
                invoked = await journal.record_invocation(proposal)
                lineage = NativeDispatchLineage(
                    attempt_id,
                    invoked.invocation_id,
                    invoked.ordinal,
                    request.permit,
                    request.input_ids,
                    request.through_checkpoint,
                    definition.session_fingerprint(plan),
                )
                checks[tool + ":initial-dispatch-reply"] = False
                try:
                    dispatched = await dispatcher.dispatch(
                        binding=binding,
                        validated_input=arguments,
                        plan=plan,
                        budgets=RunBudgetState(plan.profile.run_limits),
                        cancellation=CancellationToken(),
                        lineage=lineage,
                    )
                    assert isinstance(dispatched, DispatchCompleted)
                    receipt = NativeReply(
                        dispatched.model_text,
                        dispatched.result["type"] == "Success",
                        dispatched,
                    )
                    await journal.record_reply(invoked.invocation_id, receipt)
                    replayed = await journal.record_invocation(proposal)
                    assert replayed.reply == receipt
                    assert replayed.invocation_id == invoked.invocation_id
                    action_id = UUID(str(dispatched.host_ref))
                    stored = await actions.get(action_id)
                    assert stored is not None
                    if tool == "agent.wait":
                        assert (
                            agent_wait_state(stored).registration_receipt.model_dump(
                                mode="json"
                            )
                            == dispatched.result["value"]
                        )
                    if tool == "agent.send":
                        assert set(stored.result) == {"tool_result", "control"}
                    checks[tool + ":initial-dispatch-reply"] = True
                    replay_arguments = arguments.model_copy(
                        update={"existing_action_ref": str(action_id)}
                    )
                    replay_document = replay_arguments.model_dump(mode="json")
                    next_proposal = replace(
                        proposal,
                        call_id="controlled-replay-" + str(uuid4()),
                        arguments=freeze_json_value(replay_document),
                        proposal_digest=raw_input_digest(ParsedJson(replay_document)),
                    )
                    next_invocation = await journal.record_invocation(next_proposal)
                    next_lineage = replace(
                        lineage,
                        invocation_id=next_invocation.invocation_id,
                        ordinal=next_invocation.ordinal,
                    )
                    before = len(worker_calls)
                    replay_dispatch = await dispatcher.dispatch(
                        binding=binding,
                        validated_input=replay_arguments,
                        plan=plan,
                        budgets=RunBudgetState(plan.profile.run_limits),
                        cancellation=CancellationToken(),
                        lineage=next_lineage,
                    )
                    assert isinstance(replay_dispatch, DispatchCompleted)
                    assert replay_dispatch == dispatched
                    assert len(worker_calls) == before
                    await journal.record_reply(next_invocation.invocation_id, receipt)
                    next_replayed = await journal.record_invocation(next_proposal)
                    assert next_replayed.reply == receipt
                    after = await actions.get(action_id)
                    assert after is not None and after == stored
                    async with database.connect() as connection:
                        assert (
                            await connection.scalar(
                                select(action.c.id).where(action.c.id == action_id)
                            )
                            == action_id
                        )
                        assert (
                            await connection.scalar(
                                select(native_invocation.c.action_id).where(
                                    native_invocation.c.id
                                    == UUID(invoked.invocation_id)
                                )
                            )
                            == action_id
                        )
                        assert (
                            await connection.scalar(
                                select(func.count())
                                .select_from(action)
                                .where(action.c.origin_message_id == origin)
                            )
                            == 1
                        )
                    checks[tool + ":existing-action-replay-no-redispatch"] = True
                    try:
                        await journal.record_reply(
                            invoked.invocation_id,
                            NativeReply("changed reply", receipt.success, dispatched),
                        )
                    except NativeDefect:
                        assert (
                            await journal.record_invocation(proposal)
                        ).reply == receipt
                    else:
                        raise AssertionError("changed durable reply was accepted")
                    checks[tool + ":changed-reply-rejected"] = True
                    if tool == "agent.wait":
                        await actions.finish_agent_wait(
                            action_id,
                            AgentWaitOutcome(
                                target=target,
                                outcome="unavailable",
                                recorded_at=datetime.now(UTC),
                            ),
                            source_conversation_id=conversation,
                        )
                        assert (
                            await journal.record_invocation(proposal)
                        ).reply == receipt
                        assert (
                            await journal.record_invocation(next_proposal)
                        ).reply == receipt
                        checks[tool + ":outcome-preserves-original-callback"] = True
                except Exception as error:
                    failures[tool] = {
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                    print("RED", tool, type(error).__name__, str(error))
                finally:
                    try:
                        await dispatcher.close()
                    except Exception as error:
                        failures[tool + ":close"] = {
                            "type": type(error).__name__,
                            "message": str(error),
                        }
                    await journal.fence(attempt_id, "controlled_probe_finished")
    finally:
        await engine.dispose()
    artifact = Path(tempfile.mkdtemp(prefix="jarvis-native-reply-")) / "receipt.json"
    artifact.write_text(
        json.dumps(
            {
                "kind": "actual-postgres-controlled-native-reply-replay",
                "provider_calls": 0,
                "skid_calls": 0,
                "controlled_worker_calls": len(worker_calls),
                "checks": checks,
                "failures": failures,
                "source_sha256": {
                    str(path): sha256(path.read_bytes()).hexdigest()
                    for path in Path("src/jarvis").glob("*.py")
                },
            },
            indent=2,
        )
    )
    print(artifact, json.dumps(checks))
    assert all(checks.values()), failures


asyncio.run(main())

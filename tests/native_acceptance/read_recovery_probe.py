"""Temporary real-store proof; controlled handler, no actual research claim."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AgentRole,
    CancellationToken,
    Checkpoint,
    DispatchCompleted,
    InputId,
    NativeDefinition,
    NativeDispatchLineage,
    NativeInvocationProposal,
    NativeReply,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import (
    Available,
    CapabilityProfile,
    HandlerSuccess,
    Native,
    NoDeclaredError,
    PolicyEpoch,
    ProfileId,
    PromptDocument,
    PromptSections,
    ReplayPolicy,
    RunBudgetState,
    RunLimits,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    ToolGrant,
    ToolId,
    ToolLimits,
    ToolPlan,
    ToolSpec,
)
from provider_runtime.agent_runtime import (
    AgentAttempt,
    AgentSessionRef,
    AgentTurnRef,
    CredentialRef,
    JsonSchemaAgentOutput,
    freeze_json_value,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from jarvis.admission import JarvisOwner
from jarvis.db import create_engine, native_invocation, read_position
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.ownership import DeploymentOwnershipDefect, deployment_ownership
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    calls = 0

    async def handler(value, context):
        nonlocal calls
        calls += 1
        return HandlerSuccess(Output(text="original paid observation"), 1)

    try:
        async with deployment_ownership(engine) as database:
            conversation = "read-proof-" + str(uuid4())
            store = MessageStore(database)
            owner = JarvisOwner(database, conversation)
            first = await store.insert_waking(
                role="owner",
                text="research",
                source="proof",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            input_id = InputId(str(first.message.id))
            spec = ToolSpec(
                ToolId("web.search"),
                "controlled paid read",
                PromptDocument("return a bounded observation"),
                Input,
                Output,
                NoDeclaredError,
                ToolEffect.Read,
                ToolLimits(1024, 4096, 1, 5),
            )
            binding = ToolBinding(
                spec,
                Available(handler),
                ReplayPolicy.BilledOnce,
                "one",
                PolicyEpoch("one"),
                {},
            )
            catalog = ToolCatalog.compose((ToolFamily("web", (spec,), (binding,)),))
            maximum = CapabilityProfile(
                ProfileId("proof"),
                (ToolGrant(spec.id, None),),
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
                    "proof", {"type": "object", "additionalProperties": False}
                ),
                maximum,
                "one",
            )
            journal = PostgresNativeJournal(
                database, definition=definition, plan=plan, owner=owner
            )
            recorder = PostgresReadRecorder(database)
            dispatcher = ReadToolDispatcher(host_secrets=(), recorder=recorder)
            ref = AgentSessionRef(
                "agent-session-ref.v1",
                "codex",
                "sdk",
                "proof",
                "proof",
                "a" * 64,
                "b" * 64,
            )

            async def invocation(ids, query="original"):
                attempt_id = str(uuid4())
                request = NativeRequest(
                    attempt_id,
                    owner.permit("jarvis-native:" + attempt_id),
                    "thread",
                    ids,
                    PromptSections(()),
                    PromptSections(()),
                    plan,
                    "restart_reasoning",
                    None,
                    Checkpoint(str(first.message.id)),
                )
                await journal.arm(
                    request,
                    AgentAttempt(attempt_id, "a" * 64),
                    definition_fingerprint=definition.session_fingerprint(plan),
                    submitted_request={
                        "method": "turn/start",
                        "params": {"threadId": "proof"},
                    },
                )
                await journal.bind(attempt_id, AgentTurnRef(ref, attempt_id))
                proposal = NativeInvocationProposal(
                    attempt_id,
                    str(uuid4()),
                    spec.id,
                    freeze_json_value({"query": query}),
                    "a" * 64,
                    plan.plan_revision,
                    spec.tool_contract_revision,
                    binding.implementation_revision,
                    binding.policy_revision,
                    ids,
                    request.through_checkpoint,
                    None,
                )
                record = await journal.record_invocation(proposal)
                return request, NativeDispatchLineage(
                    attempt_id,
                    record.invocation_id,
                    record.ordinal,
                    request.permit,
                    ids,
                    request.through_checkpoint,
                    definition.session_fingerprint(plan),
                )

            request, first_lineage = await invocation((input_id,))
            original = await dispatcher.dispatch(
                binding=binding,
                validated_input=Input(query="original"),
                plan=plan,
                budgets=RunBudgetState(plan.profile.run_limits),
                cancellation=CancellationToken(),
                lineage=first_lineage,
            )
            assert calls == 1
            model_text = "authoritative cited projection [7]"
            receipt = NativeReply(
                model_text, True, DispatchCompleted(original.result, model_text)
            )
            await journal.record_reply(first_lineage.invocation_id, receipt)
            async with database.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(native_invocation).where(
                                native_invocation.c.id
                                == UUID(first_lineage.invocation_id)
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                reopened = await journal._reply(connection, row)
                assert reopened == receipt
                assert isinstance(reopened.result, DispatchCompleted)
                assert reopened.result.model_text == model_text
            await journal.fence(request.attempt_id, "lost connection")
            appended = await store.insert_waking(
                role="owner",
                text="a new topic",
                source="proof",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            second_request, replay_lineage = await invocation(
                (input_id, InputId(str(appended.message.id)))
            )
            replay = await dispatcher.dispatch(
                binding=binding,
                validated_input=Input(query="original"),
                plan=plan,
                budgets=RunBudgetState(plan.profile.run_limits),
                cancellation=CancellationToken(),
                lineage=replay_lineage,
            )
            assert calls == 1, "fresh callback repeated original paid read"
            assert replay.result == original.result
            assert str(replay.host_ref) == str(first_lineage.position)
            async with database.connect() as connection:
                assert (
                    await connection.scalar(
                        select(read_position.c.position).where(
                            read_position.c.position == str(replay_lineage.position)
                        )
                    )
                    is None
                )
            await journal.fence(second_request.attempt_id, "lost connection")
            async with database.begin() as connection:
                await connection.execute(
                    update(read_position)
                    .where(read_position.c.position == str(first_lineage.position))
                    .values(state="uncertain", result=None, settlement=None)
                )
            third_request, unknown_lineage = await invocation(
                (input_id, InputId(str(appended.message.id)))
            )
            denied = await dispatcher.dispatch(
                binding=binding,
                validated_input=Input(query="original"),
                plan=plan,
                budgets=RunBudgetState(plan.profile.run_limits),
                cancellation=CancellationToken(),
                lineage=unknown_lineage,
            )
            assert calls == 1
            assert denied.result["error"]["code"] == "paid_read_outcome_unknown"
            assert str(denied.host_ref) == str(first_lineage.position)
            await journal.fence(third_request.attempt_id, "contract changed")
            binding = ToolBinding(
                spec,
                Available(handler),
                ReplayPolicy.BilledOnce,
                "two",
                PolicyEpoch("one"),
                {},
            )
            catalog = ToolCatalog.compose((ToolFamily("web", (spec,), (binding,)),))
            maximum = CapabilityProfile(
                ProfileId("proof"),
                (ToolGrant(spec.id, None),),
                RunLimits(None, None, None, None, 1, None),
            ).freeze(catalog)
            plan = ToolPlan(maximum.id, Native()).freeze(catalog, maximum)
            definition = NativeDefinition(
                definition.provider, definition.role, definition.output, maximum, "one"
            )
            journal = PostgresNativeJournal(
                database, definition=definition, plan=plan, owner=owner
            )
            fourth_request, changed_lineage = await invocation(
                (input_id, InputId(str(appended.message.id)))
            )
            changed = await dispatcher.dispatch(
                binding=binding,
                validated_input=Input(query="original"),
                plan=plan,
                budgets=RunBudgetState(plan.profile.run_limits),
                cancellation=CancellationToken(),
                lineage=changed_lineage,
            )
            assert calls == 1
            assert changed.result["error"]["code"] == "paid_read_contract_changed"
            await journal.fence(fourth_request.attempt_id, "prepare stop race")
            final_request, stopped_lineage = await invocation(
                (input_id, InputId(str(appended.message.id))),
                query="different observation",
            )
            await store.insert_waking(
                role="owner",
                text="stop",
                source="proof",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                control_kind="stop",
            )
            try:
                await dispatcher.dispatch(
                    binding=binding,
                    validated_input=Input(query="different observation"),
                    plan=plan,
                    budgets=RunBudgetState(plan.profile.run_limits),
                    cancellation=CancellationToken(),
                    lineage=stopped_lineage,
                )
            except DeploymentOwnershipDefect:
                pass
            else:
                raise AssertionError("stopped read reached executor")
            assert calls == 1
            print(
                "original read replay, appended-topic/contract barriers, "
                "stop before dispatch: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

"""Real-store unfinished action must survive the recent-native-context window."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from calendar_fixture import calendar_input, calendar_plan
from llm_agent_kernel import (
    AgentRole,
    Checkpoint,
    InputId,
    NativeDefect,
    NativeDefinition,
    NativeInvocationProposal,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import (
    ParsedJson,
    PromptSections,
    ReplayPolicy,
    ToolEffect,
    raw_input_digest,
    render_prompt,
)
from provider_runtime.agent_runtime import (
    AgentAttempt,
    CredentialRef,
    JsonSchemaAgentOutput,
    freeze_json_value,
)

from jarvis.actions import ActionStore, ExecutionContract
from jarvis.admission import JarvisOwner
from jarvis.approval import render_approval
from jarvis.db import create_engine
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.native_runtime import NativeRunner
from jarvis.ownership import deployment_ownership
from jarvis.terminal import JarvisTerminal


async def main():
    async def unused_handler(value, context):
        raise AssertionError("no remote action is dispatched by context creation")

    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            scope = "action-context-" + str(uuid4())
            owner, store = JarvisOwner(database, scope), MessageStore(database)
            item = await store.insert_waking(
                role="owner",
                text="retain the pending event",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            plan = calendar_plan(unused_handler)
            binding = plan.catalog_view.binding("calendar.create_event")
            definition = NativeDefinition(
                ProviderConfiguration(
                    CredentialRef("local_account", "proof"),
                    "proof",
                    "high",
                    "one",
                    "a" * 64,
                ),
                AgentRole("proof", PromptSections(())),
                JsonSchemaAgentOutput("main", JarvisTerminal.model_json_schema()),
                plan.profile,
                "one",
            )
            attempt = str(uuid4())
            request = NativeRequest(
                attempt,
                owner.permit("jarvis-native:" + attempt),
                "thread",
                (InputId(str(item.message.id)),),
                PromptSections(()),
                PromptSections(()),
                plan,
                "restart_reasoning",
                None,
                Checkpoint(str(item.message.id)),
            )
            journal = PostgresNativeJournal(
                database, definition=definition, plan=plan, owner=owner
            )
            await journal.arm(
                request,
                AgentAttempt(attempt, "a" * 64),
                definition_fingerprint=definition.session_fingerprint(plan),
                submitted_request=freeze_json_value({"controlled": attempt}),
            )
            payload = calendar_input()
            arguments = {
                "request_ref": str(item.message.id),
                "existing_action_ref": None,
                "arguments": payload.model_dump(mode="json"),
            }

            def proposal(call_id):
                return NativeInvocationProposal(
                    attempt,
                    call_id,
                    binding.spec.id,
                    freeze_json_value(arguments),
                    "a" * 64,
                    plan.plan_revision,
                    binding.spec.tool_contract_revision,
                    binding.implementation_revision,
                    binding.policy_revision,
                    request.input_ids,
                    request.through_checkpoint,
                    None,
                )

            first = await journal.record_invocation(proposal("first"))
            topic = await store.insert_waking(
                role="owner",
                text="a separate topic during the callback",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            duplicate = await journal.record_invocation(
                replace(
                    first.proposal,
                    input_ids=(*request.input_ids, InputId(str(topic.message.id))),
                    through_checkpoint=Checkpoint(str(topic.message.id)),
                )
            )
            assert duplicate.invocation_id == first.invocation_id
            assert duplicate.proposal == first.proposal
            try:
                await journal.record_invocation(
                    replace(
                        first.proposal,
                        arguments=freeze_json_value(
                            {**arguments, "existing_action_ref": str(uuid4())}
                        ),
                    )
                )
            except NativeDefect:
                pass
            else:
                raise AssertionError(
                    "duplicate native call accepted changed immutable arguments"
                )
            contract = ExecutionContract(
                tool_contract_revision=binding.spec.tool_contract_revision,
                implementation_revision=binding.implementation_revision,
                policy_revision=binding.policy_revision,
                plan_revision=plan.plan_revision,
                tool_effect=ToolEffect.Write,
                replay_policy=ReplayPolicy.ReDispatchable,
                input_digest=raw_input_digest(ParsedJson(arguments)),
                max_attempts=2,
                claim_id=attempt,
                through_checkpoint=str(item.message.id),
                model_step_ordinal=first.ordinal,
                input_message_ids=(str(item.message.id),),
                write_gate_supporting_owner_message_ids=(str(item.message.id),),
            )
            identifier = uuid4()
            pending = await ActionStore(database).insert_awaiting_approval(
                tool_name=binding.spec.id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=item.message.id,
                approval_text=render_approval(
                    identifier, binding.spec.id, payload
                ).content,
                source_conversation_id=scope,
                action_id=identifier,
                invocation_id=__import__("uuid").UUID(first.invocation_id),
            )
            for ordinal in range(105):
                await journal.record_invocation(proposal("later-" + str(ordinal)))
            runner = NativeRunner(
                settings=None,
                store=store,
                owner=owner,
                kernel_runtime=None,
                definitions=None,
                history=None,
                dispatcher_factory=None,
                memory_repository=None,
                memory_dispatcher_factory=None,
                model_decisions=None,
                rememberer=None,
                actions=ActionStore(database),
            )
            context = render_prompt(await runner._receipt_context())
            assert str(pending.action.id) in context, (
                "fresh reasoning lost authoritative pending action "
                "reference behind recent callback window"
            )
            assert "awaiting_approval" in context and str(item.message.id) in context
            print(
                "all unfinished owner action references survive recent "
                "callback context window: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

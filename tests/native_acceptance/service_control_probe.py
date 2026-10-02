"""Real host service/DB/executor with controlled reasoning and mutation peers."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from calendar_fixture import calendar_input, calendar_plan, calendar_success
from llm_agent_kernel import (
    AgentRole,
    Checkpoint,
    InputId,
    NativeDefinition,
    NativeDelivery,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import (
    HandlerSuccess,
    ParsedJson,
    ReplayPolicy,
    ToolEffect,
    raw_input_digest,
)
from provider_runtime.agent_runtime import (
    AgentAttempt,
    AgentMessage,
    AgentSessionRef,
    AgentTurnRef,
    CredentialRef,
    JsonSchemaAgentOutput,
    freeze_json_value,
)

from jarvis.actions import ActionStore, ExecutionContract
from jarvis.admission import JarvisOwner
from jarvis.approval import render_approval
from jarvis.approval_runtime import ApprovalActionHandler
from jarvis.db import create_engine
from jarvis.discord import (
    ApprovalComponentDecision,
    Control,
    DeliverySucceeded,
    DiscordApprovalInteraction,
    DiscordOwnerMessage,
)
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.native_runtime import NativeRunOutcome
from jarvis.ownership import deployment_ownership
from jarvis.service import JarvisService
from jarvis.state import PausedState
from jarvis.terminal import JarvisTerminal


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    release, entered, reasoning = asyncio.Event(), asyncio.Event(), asyncio.Event()
    try:
        async with deployment_ownership(engine) as database:
            scope = "service-proof-" + str(uuid4())
            messages, actions = MessageStore(database), ActionStore(database)
            owner = JarvisOwner(database, scope)
            calls = 0

            async def handler(value, context):
                nonlocal calls
                calls += 1
                entered.set()
                await release.wait()
                return HandlerSuccess(calendar_success(value), 1)

            plan = calendar_plan(handler)
            definition = NativeDefinition(
                ProviderConfiguration(
                    CredentialRef("local_account", "proof"),
                    "proof",
                    "high",
                    "one",
                    "a" * 64,
                ),
                AgentRole("proof", __import__("llm_tools").PromptSections(())),
                JsonSchemaAgentOutput(
                    "jarvis_main", JarvisTerminal.model_json_schema()
                ),
                plan.profile,
                "one",
            )
            first = await messages.insert_waking(
                role="owner",
                text="create this shared Calendar event",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            value = calendar_input()
            arguments = {
                "request_ref": str(first.message.id),
                "existing_action_ref": None,
                "arguments": value.model_dump(mode="json"),
            }
            binding = plan.catalog_view.binding("calendar.create_event")
            contract = ExecutionContract(
                tool_contract_revision=binding.spec.tool_contract_revision,
                implementation_revision=binding.implementation_revision,
                policy_revision=binding.policy_revision,
                plan_revision=plan.plan_revision,
                tool_effect=ToolEffect.Write,
                replay_policy=ReplayPolicy.ReDispatchable,
                input_digest=raw_input_digest(ParsedJson(arguments)),
                max_attempts=2,
                claim_id=str(uuid4()),
                through_checkpoint=str(first.message.id),
                model_step_ordinal=1,
                input_message_ids=(str(first.message.id),),
                write_gate_supporting_owner_message_ids=(str(first.message.id),),
            )
            identifier = uuid4()
            pending = await actions.insert_awaiting_approval(
                tool_name=binding.spec.id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=first.message.id,
                approval_text=render_approval(
                    identifier, binding.spec.id, value
                ).content,
                source_conversation_id=scope,
                action_id=identifier,
            )
            delivered, disabled, steered = {}, [], []

            class Delivery:
                async def create_message(self, *, persisted_message_id, content):
                    result = "controlled-discord-" + str(persisted_message_id)
                    delivered[str(persisted_message_id)] = (content, result)
                    return DeliverySucceeded(result, 1)

            class HeldReasoning:
                def notify_delivery(self):
                    return None

                def notify_work(self):
                    return None

                async def recover(self):
                    pass

                async def refresh_stopped_approvals(self):
                    pass

                async def close(self):
                    pass

                async def run(self, cancellation):
                    attempt = str(uuid4())
                    request = NativeRequest(
                        attempt,
                        owner.permit("jarvis-native:" + attempt),
                        "thread",
                        (InputId(str(first.message.id)),),
                        __import__("llm_tools").PromptSections(()),
                        __import__("llm_tools").PromptSections(()),
                        plan,
                        "restart_reasoning",
                        None,
                        Checkpoint(str(first.message.id)),
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
                    turn = AgentTurnRef(
                        AgentSessionRef(
                            "agent-session-ref.v1",
                            "codex",
                            "sdk",
                            "proof",
                            "proof",
                            "a" * 64,
                            "b" * 64,
                        ),
                        "controlled-" + attempt,
                    )
                    await journal.bind(attempt, turn)
                    await journal.record_delivery(
                        NativeDelivery(
                            attempt,
                            "controlled-initial",
                            request.input_ids,
                            "initial",
                            "sent",
                            None,
                        )
                    )
                    await journal.record(
                        attempt,
                        AgentMessage(
                            turn=turn,
                            phase="commentary",
                            message_id="controlled-progress",
                            text=(
                                "the event is waiting for approval; i can "
                                "handle the next request meanwhile."
                            ),
                        ),
                    )
                    self.notify_delivery()
                    reasoning.set()
                    while not cancellation.cancelled:
                        values = await messages.pending_inputs(
                            source_conversation_id=scope,
                            limit=20,
                            exclude_ids=(first.message.id,),
                            scheduled=False,
                        )
                        steered.extend(
                            item.id for item in values if item.id not in steered
                        )
                        try:
                            await asyncio.wait_for(cancellation.wait(), 0.01)
                        except TimeoutError:
                            pass
                    return NativeRunOutcome("stopped")

            class NoBackground:
                async def run_one(self, cancellation):
                    return False

                def request_interrupt(self, cancellation):
                    cancellation.cancel()

            class NoRecovery:
                async def recover(self, **kwargs):
                    return 0

            class Gateway:
                @asynccontextmanager
                async def typing(self):
                    yield

            async def disable():
                disabled.extend(
                    item.id
                    for item in await actions.pending_approvals(
                        source_conversation_id=scope
                    )
                )

            response = SimpleNamespace(is_done=lambda: False)

            async def edit_message(**kwargs):
                assert all(child.disabled for child in kwargs["view"].children)

            response.edit_message = edit_message
            service = JarvisService(
                settings=SimpleNamespace(
                    discord=SimpleNamespace(channel_id=scope),
                    delivery_batch_size=20,
                    dream_interval_seconds=60,
                ),
                store=messages,
                paused=PausedState(messages, scope),
                delivery=Delivery(),
                runner=HeldReasoning(),
                background=NoBackground(),
                dreamer=NoBackground(),
                scheduled_wakes=actions,
                action_plan=plan,
                action_recovery=NoRecovery(),
                approval_handler=ApprovalActionHandler(
                    actions=actions, plan=plan, source_conversation_id=scope
                ),
                dispatch_lane=asyncio.Lock(),
                disable_stopped_approvals=disable,
                gateway=Gateway(),
            )
            task = asyncio.create_task(service.run_worker())
            service.request_work()
            try:
                await asyncio.wait_for(reasoning.wait(), 3)
                for _ in range(200):
                    if str(pending.message_id) in delivered and any(
                        "waiting for approval" in item[0] for item in delivered.values()
                    ):
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("outbox starved while reasoning stayed open")
                new_id = str(uuid4())
                await service.receive_owner_message(
                    DiscordOwnerMessage(
                        new_id, scope, "a different request", datetime.now(UTC), None
                    )
                )
                for _ in range(200):
                    if steered:
                        break
                    await asyncio.sleep(0.01)
                assert (
                    steered
                    and (await messages.message_by_id(first.message.id)).request_state
                    == "pending"
                )
                interaction = DiscordApprovalInteraction(
                    identifier,
                    pending.message_id,
                    ApprovalComponentDecision.APPROVE,
                    delivered[str(pending.message_id)][1],
                )
                clicked = asyncio.create_task(
                    service.receive_approval_interaction(
                        SimpleNamespace(response=response), interaction
                    )
                )
                await asyncio.wait_for(entered.wait(), 3)
                assert not clicked.done(), (
                    "controlled external effect should remain entered"
                )
                await service.receive_owner_message(
                    DiscordOwnerMessage(
                        str(uuid4()), scope, "stop", datetime.now(UTC), Control.STOP
                    )
                )
                for _ in range(200):
                    if any("stopped" in item[0] for item in delivered.values()):
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError(
                        "visible stop waited for blocked external effect"
                    )
                assert calls == 1 and not clicked.done()
                entered_action = await actions.get(identifier)
                assert (
                    entered_action.status == "executing"
                    and entered_action.attempts == 1
                )
                release.set()
                await asyncio.wait_for(clicked, 3)
                assert (await actions.get(identifier)).status == "succeeded"
                assert (
                    await messages.message_by_id(first.message.id)
                ).request_state == "stopped"
                assert calls == 1
            finally:
                release.set()
                service.request_shutdown()
                await asyncio.wait_for(task, 3)
            print(
                "live outbox/ingress, approval during reasoning, prompt "
                "stop and retained entered-effect settlement: GREEN "
                "(controlled peers)"
            )
            detached_entered, detached_release = asyncio.Event(), asyncio.Event()

            class FatalApproval:
                async def claim_and_acknowledge(self, event, interaction):
                    return SimpleNamespace(action=SimpleNamespace(id=uuid4()))

                async def complete(self, claimed, cancellation):
                    detached_entered.set()
                    await detached_release.wait()
                    raise RuntimeError("controlled detached approval failure")

            class HeldUntilShutdown(HeldReasoning):
                async def run(self, cancellation):
                    await cancellation.wait()
                    return NativeRunOutcome("stopped")

            fatal_scope = scope + "-detached"
            fatal_service = JarvisService(
                settings=SimpleNamespace(
                    discord=SimpleNamespace(channel_id=fatal_scope),
                    delivery_batch_size=20,
                    dream_interval_seconds=60,
                ),
                store=messages,
                paused=PausedState(messages, fatal_scope),
                delivery=Delivery(),
                runner=HeldUntilShutdown(),
                background=NoBackground(),
                dreamer=NoBackground(),
                scheduled_wakes=actions,
                action_plan=plan,
                action_recovery=NoRecovery(),
                approval_handler=FatalApproval(),
                dispatch_lane=asyncio.Lock(),
                disable_stopped_approvals=disable,
                gateway=Gateway(),
            )
            fatal_worker = asyncio.create_task(fatal_service.run_worker())
            fatal_service.request_work()
            detached_waiter = asyncio.create_task(
                fatal_service.receive_approval_interaction(
                    SimpleNamespace(response=response), interaction
                )
            )
            try:
                await asyncio.wait_for(detached_entered.wait(), 3)
                detached_waiter.cancel()
                await asyncio.gather(detached_waiter, return_exceptions=True)
                detached_release.set()
                try:
                    await asyncio.wait_for(asyncio.shield(fatal_worker), 1)
                except RuntimeError as error:
                    assert "controlled detached approval failure" in str(error)
                except TimeoutError:
                    raise AssertionError(
                        "detached approval failure was silently lost"
                    ) from None
                else:
                    raise AssertionError(
                        "detached approval failure did not reach service owner"
                    )
            finally:
                detached_release.set()
                fatal_service.request_shutdown()
                await asyncio.gather(fatal_worker, return_exceptions=True)
            print(
                "detached approval failure reaches service owner after "
                "caller cancellation: GREEN (controlled failure peer)"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

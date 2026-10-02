"""Temporary real-store stop/approval/entry authority proof."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from calendar_fixture import calendar_input, calendar_plan
from llm_tools import ParsedJson, ReplayPolicy, ToolEffect, raw_input_digest

from jarvis.actions import ActionPositionRecorder, ActionStore, ExecutionContract
from jarvis.admission import JarvisOwner
from jarvis.db import create_engine
from jarvis.messages import MessageStore
from jarvis.native_runtime import NativeRunner
from jarvis.ownership import deployment_ownership


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            scope = "control-proof-" + str(uuid4())
            messages, actions = MessageStore(database), ActionStore(database)
            owner = await messages.insert_waking(
                role="owner",
                text="send this draft",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )

            async def unused_handler(value, context):
                raise AssertionError("the authority proof does not mutate Calendar")

            plan = calendar_plan(unused_handler)
            binding = plan.catalog_view.binding("calendar.create_event")
            arguments = {
                "request_ref": str(owner.message.id),
                "existing_action_ref": None,
                "arguments": calendar_input().model_dump(mode="json"),
            }
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
                through_checkpoint=str(owner.message.id),
                model_step_ordinal=1,
                input_message_ids=(str(owner.message.id),),
                write_gate_supporting_owner_message_ids=(str(owner.message.id),),
            )
            pending = await actions.insert_awaiting_approval(
                tool_name=binding.spec.id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=owner.message.id,
                approval_text="approve the exact draft",
                source_conversation_id=scope,
            )
            discord_id = "proof-" + str(uuid4())
            await messages.mark_delivered(
                message_id=pending.message_id, source_message_id=discord_id
            )
            await messages.insert_waking(
                role="owner",
                text="stop",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                control_kind="stop",
            )
            stopped = await actions.get(pending.action.id)
            assert stopped.status == "cancelled" and stopped.attempts == 0
            claim = await actions.claim_approval(
                action_id=pending.action.id,
                approval_message_id=pending.message_id,
                discord_message_id=discord_id,
                source_conversation_id=scope,
            )
            assert not claim.applied
            assert await messages.paused(scope)
            await messages.insert_waking(
                role="owner",
                text="resume",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                control_kind="resume",
            )
            assert not await messages.paused(scope)
            assert (
                await messages.message_by_id(owner.message.id)
            ).request_state == "pending"
            runner = NativeRunner(
                settings=None,
                store=messages,
                owner=JarvisOwner(database, scope),
                kernel_runtime=None,
                definitions=SimpleNamespace(plans={"main": plan}),
                history=None,
                dispatcher_factory=None,
                memory_repository=None,
                memory_dispatcher_factory=None,
                model_decisions=None,
                rememberer=None,
                actions=actions,
            )
            await runner.refresh_stopped_approvals()
            await runner.refresh_stopped_approvals()
            successors = await actions.pending_approvals(source_conversation_id=scope)
            assert len(successors) == 1
            assert successors[0].supersedes_action_id == pending.action.id
            assert successors[0].id != pending.action.id
            assert successors[0].arguments == arguments and successors[0].attempts == 0
            assert not (
                await actions.claim_approval(
                    action_id=pending.action.id,
                    approval_message_id=pending.message_id,
                    discord_message_id=discord_id,
                    source_conversation_id=scope,
                )
            ).applied
            fresh = await actions.insert_automatic(
                tool_name=binding.spec.id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=owner.message.id,
            )
            recorder = ActionPositionRecorder(
                store=actions,
                action_id=fresh.id,
                implementation_revision=binding.implementation_revision,
                max_external_attempts=1,
            )
            await recorder.dispatch_started(
                position=recorder.position, replay_policy=ReplayPolicy.ReDispatchable
            )
            await messages.insert_waking(
                role="owner",
                text="stop",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                control_kind="stop",
            )
            entered = await actions.get(fresh.id)
            assert entered.status == "executing" and entered.attempts == 1
            await messages.insert_waking(
                role="owner",
                text="resume",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                control_kind="resume",
            )
            await runner.refresh_stopped_approvals()
            renewed = await actions.pending_approvals(source_conversation_id=scope)
            assert (
                len(renewed) == 1
                and renewed[0].supersedes_action_id == successors[0].id
            )
            assert (await actions.get(fresh.id)).attempts == 1
            assert all(item.supersedes_action_id != fresh.id for item in renewed)
            print(
                "stop/entry both orders, fresh resume consent and "
                "entered-effect identity preserved: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

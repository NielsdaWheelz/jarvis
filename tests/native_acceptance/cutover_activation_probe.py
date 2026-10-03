"""Actual stopped PostgreSQL cutover/activation; controlled catalog, no provider."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from calendar_fixture import calendar_input, calendar_plan
from llm_tools import ParsedJson, ReplayPolicy, ToolEffect, raw_input_digest
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from jarvis import cli
from jarvis.actions import ActionStore, ExecutionContract
from jarvis.db import action, create_engine, message
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.state import PausedState
from jarvis.write_dispatch import ActionRecovery


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    calls = 0

    async def handler(*args):
        nonlocal calls
        calls += 1
        raise AssertionError("paused cutover entered the controlled handler")

    plan = calendar_plan(handler)

    class NoRuntime:
        async def close(self):
            pass

    async def composition(**kwargs):
        return None, SimpleNamespace(plans={"main": plan}), None

    try:
        with tempfile.TemporaryDirectory(
            prefix="jarvis-native-activation-"
        ) as temporary:
            directory = Path(temporary)
            scope = str(9_000_000_000_000 + int(uuid4().hex[:9], 16))
            settings = SimpleNamespace(
                database_url=SecretStr(os.environ["JARVIS_PROOF_DATABASE_URL"]),
                runtime_state_directory=directory,
                discord=SimpleNamespace(channel_id=int(scope)),
                embedding_openai_api_key=SecretStr("unused-controlled-credential"),
            )
            host = SimpleNamespace(endpoints={})
            value = calendar_input().model_dump(mode="json")
            async with deployment_ownership(engine) as database:
                store = MessageStore(database)
                owner = await store.insert_waking(
                    role="owner",
                    text="create exact fixture",
                    source="proof",
                    source_conversation_id=scope,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                )
                contract = ExecutionContract(
                    tool_contract_revision="old-tool",
                    implementation_revision="old-handler",
                    policy_revision="old-policy",
                    plan_revision="old-plan",
                    tool_effect=ToolEffect.Write,
                    replay_policy=ReplayPolicy.ReDispatchable,
                    input_digest=raw_input_digest(ParsedJson(value)),
                    max_attempts=2,
                    claim_id=str(uuid4()),
                    through_checkpoint=str(owner.message.id),
                    model_step_ordinal=1,
                    input_message_ids=(str(owner.message.id),),
                    write_gate_supporting_owner_message_ids=(str(owner.message.id),),
                )
                original_id, old_approval_id = uuid4(), uuid4()
                now = datetime.now(UTC)
                async with database.begin() as connection:
                    await connection.execute(
                        insert(message).values(
                            id=old_approval_id,
                            role="assistant",
                            text="old controlled approval",
                            source="discord",
                            source_conversation_id=scope,
                            source_message_id="delivered-controlled-" + str(uuid4()),
                            created_at=now,
                            processed_at=now,
                        )
                    )
                    await connection.execute(
                        insert(action).values(
                            id=original_id,
                            tool_name="calendar.create_event",
                            arguments=value,
                            execution_contract=contract.as_json(),
                            status="awaiting_approval",
                            attempts=0,
                            origin_message_id=owner.message.id,
                            approval_message_id=old_approval_id,
                            created_at=now,
                        )
                    )
            pause = directory / "paused.json"
            pause.write_text(
                json.dumps({"paused": True, "schema_version": "jarvis-paused.v1"})
            )
            pause.chmod(0o600)
            with (
                patch.object(cli, "_validate_runtime_layout"),
                patch.object(cli, "_compose_main", composition),
                patch.object(cli, "build_agent_runtime", return_value=NoRuntime()),
            ):
                assert await cli.stopped_native_cutover(settings, host) == 1
                verdicts = await cli.check_activation(settings, host)
                assert all(verdict == "compatible" for *_, verdict in verdicts), (
                    verdicts
                )
            async with deployment_ownership(engine) as database:
                actions = ActionStore(database)
                original = await actions.get(original_id)
                assert (
                    original.arguments == value
                    and original.execution_contract == contract
                )
                assert original.status == "cancelled" and original.attempts == 0
                pending = await actions.pending_approvals(
                    source_conversation_id=scope, limit=100
                )
                assert (
                    len(pending) == 1 and pending[0].supersedes_action_id == original_id
                )
                assert pending[0].arguments == {
                    "request_ref": str(owner.message.id),
                    "existing_action_ref": None,
                    "arguments": value,
                }

                async def no_disable(stored):
                    pass

                recovery = ActionRecovery(
                    actions=actions,
                    google_write=None,
                    plan=plan,
                    source_conversation_id=scope,
                    schedule_changed=lambda: None,
                    approval_disabler=no_disable,
                )
                assert (
                    await cli.recover_startup_actions(
                        action_recovery=recovery,
                        paused=PausedState(MessageStore(database), scope),
                        messages=MessageStore(database),
                    )
                    >= 0
                )
                assert calls == 0
                assert not await actions.unreported_terminal(
                    source_conversation_id=scope
                )
                async with database.connect() as connection:
                    rows = (
                        await connection.execute(
                            select(message.c.role, message.c.text).where(
                                message.c.source_conversation_id == scope,
                                message.c.source_message_id.is_(None),
                            )
                        )
                    ).all()
                    assert any(role == "assistant" for role, _ in rows)
                # Historical bytes stay opaque. A genuinely entered unknown old
                # effect still refuses the target before provider composition.
                async with database.begin() as connection:
                    await connection.execute(
                        update(action)
                        .where(action.c.id == original_id)
                        .values(status="uncertain", attempts=1)
                    )
            with (
                patch.object(cli, "_compose_main", composition),
                patch.object(cli, "build_agent_runtime", return_value=NoRuntime()),
            ):
                try:
                    await cli.check_activation(settings, host)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("unknown old entered effect passed activation")
            async with deployment_ownership(engine) as database:
                async with database.begin() as connection:
                    await connection.execute(
                        update(action)
                        .where(action.c.id == original_id)
                        .values(status="cancelled", attempts=0)
                    )
            print(
                "stopped cutover → activation → paused recovery/outbox load; "
                "unknown old effect refusal: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

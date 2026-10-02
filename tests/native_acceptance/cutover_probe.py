"""Temporary real PostgreSQL stopped migration and approval rotation proof."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4, uuid5

from calendar_fixture import calendar_input, calendar_plan
from llm_tools import ParsedJson, ReplayPolicy, ToolEffect, raw_input_digest
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from jarvis.actions import ExecutionContract
from jarvis.approval import render_approval
from jarvis.db import action, create_engine, message, model_decision, read_position
from jarvis.messages import MessageStore
from jarvis.native_cutover import (
    cutover_native,
    require_native_data,
    require_native_files,
)
from jarvis.ownership import deployment_ownership


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])

    async def unreachable(*args):
        raise AssertionError("migration must not enter any handler")

    plan = calendar_plan(unreachable)
    try:
        async with deployment_ownership(engine) as database:
            scope = "migration-proof-" + str(uuid4())
            store = MessageStore(database)
            owner = await store.insert_waking(
                role="owner",
                text="create the exact shared Calendar event",
                source="proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            value = calendar_input()
            old = value.model_dump(mode="json")
            contract = ExecutionContract(
                tool_contract_revision="old-tool",
                implementation_revision="old-handler",
                policy_revision="old-policy",
                plan_revision="old-plan",
                tool_effect=ToolEffect.Write,
                replay_policy=ReplayPolicy.ReDispatchable,
                input_digest=raw_input_digest(ParsedJson(old)),
                max_attempts=2,
                claim_id=str(uuid4()),
                through_checkpoint=str(owner.message.id),
                model_step_ordinal=1,
                input_message_ids=(str(owner.message.id),),
                write_gate_supporting_owner_message_ids=(str(owner.message.id),),
            )
            identifier, approval_id = uuid4(), uuid4()
            now = datetime.now(UTC)
            preview = render_approval(
                identifier, "calendar.create_event", value
            ).content
            async with database.begin() as connection:
                await connection.execute(
                    insert(message).values(
                        id=approval_id,
                        role="assistant",
                        text=preview,
                        source="proof",
                        source_conversation_id=scope,
                        created_at=now,
                        processed_at=now,
                    )
                )
                await connection.execute(
                    insert(action).values(
                        id=identifier,
                        tool_name="calendar.create_event",
                        arguments=old,
                        execution_contract=contract.as_json(),
                        status="awaiting_approval",
                        attempts=0,
                        origin_message_id=owner.message.id,
                        approval_message_id=approval_id,
                        created_at=now,
                    )
                )
            with tempfile.TemporaryDirectory(
                prefix="jarvis-stopped-cutover-"
            ) as directory_name:
                directory = Path(directory_name)
                pause = directory / "paused.json"
                pause.write_text(
                    json.dumps({"schema_version": "jarvis-paused.v1", "paused": True})
                )
                pause.chmod(0o600)
                (directory / "admission.json").write_text(
                    "old accounting, no longer authority"
                )
                decision_id = uuid4().hex + uuid4().hex
                position = "model-decision:" + decision_id
                old_read = {
                    "type": "Success",
                    "value": {"controlled": "original recorded observation"},
                }
                async with database.begin() as connection:
                    await connection.execute(
                        insert(model_decision).values(
                            decision_id=decision_id,
                            scope_key="old-main:" + scope,
                            thread_id=scope,
                            first_input_id=owner.message.id,
                            ordinal=1,
                            request_fingerprint="a" * 64,
                            request={
                                "schema_version": "jarvis-model-decision.v1",
                                "input_ids": [str(owner.message.id)],
                            },
                        )
                    )
                    await connection.execute(
                        insert(read_position).values(
                            position=position,
                            state="uncertain",
                            contract={
                                "tool_id": "web.search",
                                "tool_contract_revision": "old",
                                "policy_revision": "old",
                                "plan_revision": "old",
                                "input_digest": "b" * 64,
                                "replay_policy": "BilledOnce",
                            },
                        )
                    )
                try:
                    await require_native_data(database, conversation_id=scope)
                except RuntimeError as error:
                    assert "read" in str(error)
                else:
                    raise AssertionError(
                        "activation bypassed an old main unknown paid read"
                    )
                try:
                    await cutover_native(
                        database, directory=directory, conversation_id=scope, plan=plan
                    )
                except RuntimeError as error:
                    assert "read" in str(error)
                else:
                    raise AssertionError(
                        "cutover lost the old main unknown paid-read barrier"
                    )
                assert pause.exists() and (directory / "admission.json").exists()
                async with database.begin() as connection:
                    assert (
                        await connection.scalar(
                            select(action.c.status).where(action.c.id == identifier)
                        )
                        == "awaiting_approval"
                    )
                    await connection.execute(
                        update(read_position)
                        .where(read_position.c.position == position)
                        .values(
                            state="completed",
                            result=old_read,
                            settlement={"actual_attempts": 1, "actual_output_bytes": 1},
                        )
                    )
                try:
                    await require_native_data(database, conversation_id=scope)
                except RuntimeError as error:
                    assert "action" in str(error)
                else:
                    raise AssertionError(
                        "activation bypassed an unresolved legacy action"
                    )
                async with database.begin() as connection:
                    await connection.execute(
                        update(action)
                        .where(action.c.id == identifier)
                        .values(status="executing", attempts=1)
                    )
                try:
                    await cutover_native(
                        database, directory=directory, conversation_id=scope, plan=plan
                    )
                except RuntimeError as error:
                    assert "effect" in str(error)
                else:
                    raise AssertionError(
                        "cutover converted an already-entered legacy effect"
                    )
                assert pause.exists() and (directory / "admission.json").exists()
                async with database.begin() as connection:
                    retained = (
                        (
                            await connection.execute(
                                select(action).where(action.c.id == identifier)
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert (
                        retained["status"] == "executing" and retained["attempts"] == 1
                    )
                    assert (
                        retained["arguments"] == old
                        and retained["execution_contract"] == contract.as_json()
                    )
                    await connection.execute(
                        update(action)
                        .where(action.c.id == identifier)
                        .values(status="awaiting_approval", attempts=0)
                    )
                try:
                    require_native_files(directory)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("activation admitted an old file writer")
                assert (
                    await cutover_native(
                        database, directory=directory, conversation_id=scope, plan=plan
                    )
                    == 1
                )
                require_native_files(directory)
                await require_native_data(database, conversation_id=scope)
                assert await store.paused(scope)
                async with database.connect() as connection:
                    retained = (
                        (
                            await connection.execute(
                                select(action).where(action.c.id == identifier)
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert retained["arguments"] == old
                    assert retained["execution_contract"] == contract.as_json()
                    assert (
                        retained["status"] == "cancelled" and retained["attempts"] == 0
                    )
                    successor = (
                        (
                            await connection.execute(
                                select(action).where(
                                    action.c.supersedes_action_id == identifier
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert successor["id"] == uuid5(identifier, "native-approval")
                    assert (
                        successor["status"] == "awaiting_approval"
                        and successor["attempts"] == 0
                    )
                    assert successor["arguments"] == {
                        "request_ref": str(owner.message.id),
                        "existing_action_ref": None,
                        "arguments": old,
                    }
                    assert (
                        await connection.scalar(
                            select(message.c.request_state).where(
                                message.c.id == owner.message.id
                            )
                        )
                        == "pending"
                    )
                    assert (
                        await connection.scalar(
                            select(read_position.c.result).where(
                                read_position.c.position == position
                            )
                        )
                        == old_read
                    )
                assert (
                    await cutover_native(
                        database, directory=directory, conversation_id=scope, plan=plan
                    )
                    == 0
                )
            print(
                "stopped conversion, immutable legacy bytes, fresh consent "
                "and pause import: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

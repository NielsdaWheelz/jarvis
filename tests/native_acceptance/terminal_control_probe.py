"""Temporary real-store terminal recovery and control-race proof."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

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
    CapabilityProfile,
    Native,
    ProfileId,
    PromptSections,
    RunLimits,
    ToolCatalog,
    ToolPlan,
)
from provider_runtime.agent_runtime import (
    AgentAttempt,
    AgentSessionRef,
    AgentTerminal,
    AgentTurnRef,
    CredentialRef,
    JsonSchemaAgentOutput,
    NativeTerminalEvidence,
    RawAgentOutput,
    freeze_json_value,
    terminal_to_json,
)
from sqlalchemy import select

from jarvis.actions import ActionStore
from jarvis.admission import JarvisOwner
from jarvis.db import create_engine, message, native_attempt
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.native_runtime import NativeRunner
from jarvis.ownership import deployment_ownership
from jarvis.terminal import JarvisTerminal


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            conversation = "terminal-proof-" + str(uuid4())
            owner = JarvisOwner(database, conversation)
            store = MessageStore(database)
            catalog = ToolCatalog.compose(())
            maximum = CapabilityProfile(
                ProfileId("proof"), (), RunLimits(None, None, None, None, 1, None)
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
            remembered = []
            runner = NativeRunner(
                settings=None,
                store=store,
                owner=owner,
                kernel_runtime=SimpleNamespace(provider=SimpleNamespace()),
                definitions=SimpleNamespace(main=definition, plans={"main": plan}),
                history=None,
                dispatcher_factory=None,
                memory_repository=None,
                memory_dispatcher_factory=None,
                model_decisions=None,
                rememberer=SimpleNamespace(
                    enqueue=lambda ids, context: remembered.extend(ids)
                ),
                actions=ActionStore(database),
            )

            async def arm(text):
                item = await store.insert_waking(
                    role="owner",
                    text=text,
                    source="proof",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                )
                attempt_id = str(uuid4())
                request = NativeRequest(
                    attempt_id,
                    owner.permit("jarvis-native:" + attempt_id),
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
                        "sent",
                        None,
                    )
                )
                final = {
                    "response": {
                        "type": "answered",
                        "text": "the original answer is ready.",
                    },
                    "input_outcomes": [
                        {
                            "input_id": str(item.message.id),
                            "disposition": "complete",
                            "wait_reason": None,
                            "action_refs": [],
                        }
                    ],
                }
                terminal = AgentTerminal(
                    "succeeded",
                    None,
                    json.dumps(final),
                    ref,
                    NativeTerminalEvidence(prepared, turn, "codex-turn-completed.v1"),
                    RawAgentOutput(freeze_json_value(final)),
                )
                return item.message.id, request, journal, terminal

            first, request, journal, terminal = await arm(
                "recover this completed native turn"
            )
            await journal.record_outcome(request.attempt_id, terminal)
            # A fresh owner's local recovery needs no provider/session method at all.
            fresh = JarvisOwner(database, conversation)
            runner.owner = fresh
            await runner.recover()
            async with database.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(native_attempt).where(
                                native_attempt.c.id == UUID(request.attempt_id)
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["terminal"] == terminal_to_json(terminal)
                assert row["product_outcome"]["status"] == "committed"
                assert (
                    await connection.scalar(
                        select(message.c.request_state).where(message.c.id == first)
                    )
                    == "completed"
                )
            assert remembered == [first]
            await runner.recover()
            assert remembered == [first]

            owner = fresh
            second, request, journal, terminal = await arm(
                "retain terminal across stop then resume"
            )
            await journal.record_outcome(request.attempt_id, terminal)
            for kind in ("stop", "resume"):
                await store.insert_waking(
                    role="owner",
                    text=kind,
                    source="proof",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                    control_kind=kind,
                )
            await runner.recover()
            async with database.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(native_attempt).where(
                                native_attempt.c.id == UUID(request.attempt_id)
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["terminal"] == terminal_to_json(terminal)
                assert row["product_outcome"]["status"] == "stale"
                assert (
                    await connection.scalar(
                        select(message.c.request_state).where(message.c.id == second)
                    )
                    == "pending"
                )
                assert not tuple(
                    (
                        await connection.execute(
                            select(message.c.id).where(
                                message.c.source == "native_final",
                                message.c.trace["native_attempt_id"].as_string()
                                == request.attempt_id,
                            )
                        )
                    ).scalars()
                )

            third, request, journal, original = await arm(
                "invalid structured output cannot become success"
            )
            terminal = AgentTerminal(
                "succeeded",
                None,
                original.final_text,
                ref,
                original.evidence,
                RawAgentOutput(freeze_json_value({"wrong": "shape"})),
            )
            await journal.record_outcome(request.attempt_id, terminal)
            await runner.recover()
            async with database.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(native_attempt).where(
                                native_attempt.c.id == UUID(request.attempt_id)
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["terminal"] == terminal_to_json(terminal)
                assert row["product_outcome"]["status"] == "failed"
                request_row = (
                    (
                        await connection.execute(
                            select(message).where(message.c.id == third)
                        )
                    )
                    .mappings()
                    .one()
                )
                assert (request_row["request_state"], request_row["wait_reason"]) == (
                    "waiting",
                    "configuration",
                )

            fourth, request, journal, original = await arm(
                "old malformed output must not overwrite resumed work"
            )
            terminal = AgentTerminal(
                "succeeded",
                None,
                original.final_text,
                ref,
                original.evidence,
                RawAgentOutput(freeze_json_value({"wrong": "shape"})),
            )
            await journal.record_outcome(request.attempt_id, terminal)
            for kind in ("stop", "resume"):
                await store.insert_waking(
                    role="owner",
                    text=kind,
                    source="proof",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                    control_kind=kind,
                )
            await runner.recover()
            async with database.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(native_attempt).where(
                                native_attempt.c.id == UUID(request.attempt_id)
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["terminal"] == terminal_to_json(terminal)
                assert row["product_outcome"]["status"] == "stale"
                assert (
                    await connection.scalar(
                        select(message.c.request_state).where(message.c.id == fourth)
                    )
                    == "pending"
                )
            print(
                "sealed local terminal replay, invalid-raw preservation, "
                "stop/resume settlement race: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

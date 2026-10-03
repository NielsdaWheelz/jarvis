"""Temporary real-store terminal recovery and control-race proof."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
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
from sqlalchemy import select, update

from jarvis.actions import ActionStore
from jarvis.admission import JarvisOwner
from jarvis.db import create_engine, message, native_attempt
from jarvis.memory import MemoryStore
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

            async def arm(text, extra_ids=()):
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
                    (
                        InputId(str(item.message.id)),
                        *(InputId(str(identifier)) for identifier in extra_ids),
                    ),
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
                            "input_id": str(identifier),
                            "disposition": "complete",
                            "wait_reason": None,
                            "action_refs": [],
                        }
                        for identifier in request.input_ids
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
            fifth, request, journal, terminal = await arm(
                "settle original inference after containment and tools rotate"
            )
            await journal.record_outcome(request.attempt_id, terminal)
            rotated_maximum = CapabilityProfile(
                ProfileId("rotated-proof"),
                (),
                RunLimits(None, None, None, None, 1, None),
            ).freeze(catalog)
            rotated_plan = ToolPlan(rotated_maximum.id, Native()).freeze(
                catalog, rotated_maximum
            )
            rotated_definition = replace(
                definition,
                maximum_profile=rotated_maximum,
                compatibility_revision="rotated-containment-and-handler",
                output=JsonSchemaAgentOutput(
                    "new-schema",
                    {
                        "type": "object",
                        "properties": {"new_field": {"type": "string"}},
                        "required": ["new_field"],
                        "additionalProperties": False,
                    },
                ),
            )
            runner.definitions = SimpleNamespace(
                main=rotated_definition, plans={"main": rotated_plan}
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
                assert row["product_outcome"]["status"] == "committed", row
                assert (
                    await connection.scalar(
                        select(message.c.request_state).where(message.c.id == fifth)
                    )
                    == "completed"
                )
                try:
                    PostgresNativeJournal(
                        database,
                        definition=rotated_definition,
                        plan=rotated_plan,
                        owner=fresh,
                    ).restore_request(row)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("active plan compatibility was weakened")

            class NoCurrentDefinition:
                def __getattr__(self, name):
                    raise AssertionError("local sealed settlement rebuilt " + name)

            runner.definitions = NoCurrentDefinition()
            runner.kernel = NoCurrentDefinition()
            sixth, request, journal, terminal = await arm(
                "settle without current provider or catalogue"
            )
            await journal.record_outcome(request.attempt_id, terminal)
            await runner.recover()
            assert sixth in remembered
            seventh, request, journal, terminal = await arm(
                "old accepted records lacking a schema must refuse local success"
            )
            await journal.record_outcome(request.attempt_id, terminal)
            async with database.begin() as connection:
                document = dict(
                    await connection.scalar(
                        select(native_attempt.c.request).where(
                            native_attempt.c.id == UUID(request.attempt_id)
                        )
                    )
                )
                document.pop("output", None)
                await connection.execute(
                    update(native_attempt)
                    .where(native_attempt.c.id == UUID(request.attempt_id))
                    .values(request=document)
                )
            await runner.recover()
            async with database.connect() as connection:
                outcome = await connection.scalar(
                    select(native_attempt.c.product_outcome).where(
                        native_attempt.c.id == UUID(request.attempt_id)
                    )
                )
                assert outcome["status"] == "failed", outcome
                assert (
                    await connection.scalar(
                        select(message.c.request_state).where(message.c.id == seventh)
                    )
                    == "waiting"
                )
            assert seventh not in remembered
            extra = await store.insert_waking(
                role="owner",
                text="complete this independent appended request too",
                source="proof",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            eighth, request, journal, terminal = await arm(
                "complete independent owner requests in one turn",
                (extra.message.id,),
            )
            await journal.record_outcome(request.attempt_id, terminal)
            await runner.recover()
            for identifier in (eighth, extra.message.id):
                group = await MemoryStore(database).prepare_rememberer_group(
                    owner_message_ids=(identifier,)
                )
                assert not group.per_row_fallback and group.settlement is not None
                assert group.settlement.through_checkpoint == str(identifier)
                assert identifier in remembered
            print(
                "sealed local terminal replay, invalid-raw preservation, "
                "stop/resume settlement race, rotation/provider traps and "
                "missing-schema refusal: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())

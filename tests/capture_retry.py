"""Run against an explicitly supplied disposable database already at migration head."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AgentRole,
    HostRef,
    InputId,
    NativeDefect,
    NativeDefinition,
    NativeInvocationProposal,
    NativeRejected,
    NativeReply,
    ProviderConfiguration,
)
from llm_tools import (
    CapabilityProfile,
    HostTable,
    InvocationPosition,
    ParsedJson,
    ProfileId,
    PromptJson,
    PromptSections,
    Reservation,
    RunBudgetState,
    RunLimits,
    Settlement,
    ToolGrant,
    ToolPlan,
    canonical_json_bytes,
    raw_input_digest,
)
from provider_runtime.agent_runtime import (
    CredentialRef,
    TextAgentOutput,
    freeze_json_value,
)
from sqlalchemy import func, insert, select
from universal_memory import MemoryError, MemoryStore, NoteReceipt
from universal_memory.schema import memory_leaf, memory_log, source_record
from universal_memory.tools import MEMORY_SAVE_NOTE_SPEC

from jarvis.admission import JarvisOwner
from jarvis.db import (
    action,
    create_engine,
    native_attempt,
    native_invocation,
    read_position,
)
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import compose_memory_catalog
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.native_runtime import (
    _recover_native_note_saves,  # pyright: ignore[reportPrivateUsage]
    native_receipt_context,
    recover_native_products,
)
from jarvis.ownership import deployment_ownership
from jarvis.read_positions import PostgresReadRecorder
from jarvis.tool_results import (
    completed_tool_result,
    memory_result_size,
    memory_view_size,
)


class NoEmbedding:
    async def embed(self, inputs: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        raise AssertionError("capture and local recovery must not enter inference")


async def check(url: str) -> None:
    engine, reads = create_engine(url), create_engine(url, memory_reads=True)
    try:
        async with deployment_ownership(engine, memory_admitted=True) as database:
            channel = uuid4().int >> 80
            owner = JarvisOwner(database, str(channel))
            library = MemoryStore(
                reads, result_size=memory_result_size, view_size=memory_view_size
            )
            memory = MemoryService(
                library=library,
                database=database,
                embedder=NoEmbedding(),
                admitted_lanes=frozenset({("devbox", "jarvis")}),
                guild_id=1,
                channel_id=channel,
            )
            store = MessageStore(database)
            text = "synthetic capture/retry request"
            external_id, created_at = str(uuid4()), datetime.now(UTC)
            before = await library.cutoff()
            original = await store.insert_waking(
                role="owner",
                text=text,
                source="discord",
                source_conversation_id=owner.scope_id,
                source_message_id=external_id,
                created_at=created_at,
            )
            with patch.object(
                library, "append_events", side_effect=MemoryError("unavailable")
            ):
                await memory.publish()
            retained = await store.message_by_id(original.message.id)
            assert retained is not None and retained.memory_admitted
            assert retained.text == text
            assert await library.cutoff() == before
            frozen = await memory.pending_publication()
            assert len(frozen) == 1
            await memory.project_pending()
            assert await memory.project_pending(frozen) == 1
            retry = await store.insert_waking(
                role="owner",
                text=text,
                source="discord",
                source_conversation_id=owner.scope_id,
                source_message_id=external_id,
                created_at=created_at,
            )
            assert not retry.inserted and retry.message.id == original.message.id
            assert await memory.project_pending() == 0
            assert await library.cutoff() == before + 1

            catalog = compose_memory_catalog(memory)
            limits = RunLimits(8, 0, 32_768, 8 * 65_536, 1, 300)
            profile = CapabilityProfile(
                ProfileId("capture-retry"),
                tuple(ToolGrant(identifier, None) for identifier in catalog.tool_ids),
                limits,
            ).freeze(catalog)
            plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
            binding = catalog.binding(MEMORY_SAVE_NOTE_SPEC.id)
            definition = NativeDefinition(
                ProviderConfiguration(
                    CredentialRef("local_account", "synthetic"),
                    "synthetic-model",
                    "high",
                    "synthetic-catalog",
                    "a" * 64,
                ),
                AgentRole("capture-retry", PromptSections(())),
                TextAgentOutput(),
                profile,
                "capture-retry-v1",
            )
            journal = PostgresNativeJournal(
                database, definition=definition, plan=plan, owner=owner, memory=memory
            )
            attempt = uuid4()
            async with database.begin() as connection:
                await connection.execute(
                    insert(native_attempt).values(
                        id=attempt,
                        conversation_id=owner.scope_id,
                        attempt_seq=1,
                        owner_epoch=str(owner.token),
                        request_fingerprint="a" * 64,
                        request={},
                        armed_at=datetime.now(UTC),
                        memory_admitted=True,
                    )
                )
            receipts: list[tuple[UUID, InvocationPosition, NoteReceipt | None]] = []
            arguments = {"text": "synthetic\x00callback"}
            rejected = NativeRejected("invalid_arguments", "invalid tool arguments")
            proposal = NativeInvocationProposal(
                str(attempt),
                str(uuid4()),
                binding.spec.id,
                freeze_json_value(arguments),
                raw_input_digest(ParsedJson(arguments)),
                plan.plan_revision,
                binding.spec.tool_contract_revision,
                binding.implementation_revision,
                binding.policy_revision,
                (InputId(str(original.message.id)),),
                None,
                rejected,
            )
            try:
                await journal.record_invocation(proposal)
            except NativeDefect as error:
                assert str(error) == "native callback evidence contains nul"
            else:
                raise AssertionError("nul callback entered the canonical journal")
            async with database.connect() as connection:
                assert not await connection.scalar(
                    select(func.count())
                    .select_from(native_invocation)
                    .where(native_invocation.c.attempt_id == attempt)
                )
            for ordinal, committed in ((1, True), (2, True), (3, False)):
                invocation = uuid4()
                arguments = {"text": f"synthetic local note {invocation}"}
                contract = {
                    "plan_revision": plan.plan_revision,
                    "tool_contract_revision": binding.spec.tool_contract_revision,
                    "implementation_revision": binding.implementation_revision,
                    "policy_revision": binding.policy_revision,
                    "effect": "Write",
                }
                async with database.begin() as connection:
                    await connection.execute(
                        insert(native_invocation).values(
                            id=invocation,
                            attempt_id=attempt,
                            ordinal=ordinal,
                            native_call_id=str(invocation),
                            tool_id="memory.save_note",
                            proposal_digest="b" * 64,
                            proposal={
                                "arguments": arguments,
                                "input_ids": [str(original.message.id)],
                            },
                            frozen_contract=contract,
                            validation="accepted",
                        )
                    )
                position = InvocationPosition("native-invocation:" + str(invocation))
                recorder = PostgresReadRecorder(database)
                budgets = RunBudgetState(limits)
                await recorder.occupy(
                    position=position,
                    tool_id=binding.spec.id,
                    tool_contract_revision=binding.spec.tool_contract_revision,
                    policy_revision=binding.policy_revision,
                    plan_revision=plan.plan_revision,
                    input_digest=raw_input_digest(ParsedJson(arguments)),
                    replay_policy=binding.replay_policy,
                )
                assert await recorder.reserve(
                    position=position,
                    budgets=budgets,
                    reservation=Reservation(
                        1,
                        len(
                            canonical_json_bytes(
                                {"type": "ParsedJson", "value": arguments}
                            )
                        ),
                        0,
                        65_536,
                    ),
                )
                await recorder.dispatch_started(
                    position=position, replay_policy=binding.replay_policy
                )
                note = (
                    await memory.save_main_note(arguments["text"], str(position))
                    if committed
                    else None
                )
                receipts.append((invocation, position, note))
                if ordinal == 1:
                    assert note is not None
                    result = {"type": "Success", "value": note.model_dump(mode="json")}
                    await recorder.terminalize_and_settle(
                        position=position,
                        result=result,
                        budgets=budgets,
                        settlement=Settlement(0, len(canonical_json_bytes(result))),
                    )
                    completed = completed_tool_result(result, HostRef(str(position)))
                    reply = NativeReply(completed.model_text, True, completed)
                    with patch.object(
                        library, "append_events", side_effect=MemoryError("unavailable")
                    ):
                        await journal.record_reply(str(invocation), reply)
                    async with database.connect() as connection:
                        saved = await connection.scalar(
                            select(native_invocation.c.reply_receipt).where(
                                native_invocation.c.id == invocation
                            )
                        )
                    assert saved is not None
                    assert saved["wire_text"] == completed.model_text
                    await memory.project_pending()
                    await journal.record_reply(str(invocation), reply)
                    assert await memory.project_pending() == 0

            arguments = {"text": r"synthetic literal \u0000", "extra": True}
            record = await journal.record_invocation(
                replace(
                    proposal,
                    arguments=freeze_json_value(arguments),
                    proposal_digest=raw_input_digest(ParsedJson(arguments)),
                )
            )
            await journal.record_reply(
                record.invocation_id,
                NativeReply("invalid tool arguments", False, rejected),
            )
            async with database.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(native_invocation).where(
                                native_invocation.c.id == UUID(record.invocation_id)
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["proposal"]["arguments"] == arguments
                assert row["validation"] == "rejected"
                assert row["reply_receipt"] is not None

            revoked = MemoryService(
                library=library,
                database=database,
                embedder=NoEmbedding(),
                admitted_lanes=frozenset(),
                guild_id=1,
                channel_id=channel,
            )
            async with database.connect() as connection:
                counts = [
                    await connection.scalar(select(func.count()).select_from(table))
                    for table in (memory_log, memory_leaf, action)
                ]
            await recover_native_products(owner)
            await _recover_native_note_saves(owner, revoked)
            await _recover_native_note_saves(owner, revoked)
            context = await native_receipt_context(
                owner,
                input_ids=(InputId(str(original.message.id)),),
                fits=lambda _: True,
            )
            assert context is not None
            body = context.sections[0].body
            assert isinstance(body, PromptJson)
            records = cast(list[dict[str, Any]], body.value)
            async with database.connect() as connection:
                assert counts == [
                    await connection.scalar(select(func.count()).select_from(table))
                    for table in (memory_log, memory_leaf, action)
                ]
                for invocation, position, note in receipts:
                    row = (
                        (
                            await connection.execute(
                                select(native_invocation).where(
                                    native_invocation.c.id == invocation
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                    original_position = (
                        (
                            await connection.execute(
                                select(read_position).where(
                                    read_position.c.position == str(position)
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert original_position["reservation"]["calls"] == 1
                    if note is None:
                        assert (
                            row["reply_receipt"] is None
                            and row["read_position"] is None
                        )
                        assert original_position["state"] == "dispatched"
                    else:
                        assert row["read_position"] == str(position)
                        assert original_position["state"] == "completed"
                        recorded = next(
                            item
                            for item in records
                            if item["invocation_id"] == str(invocation)
                        )
                        assert json.loads(recorded["reply"]["wire_text"])["result"] == {
                            "type": "Success",
                            "value": note.model_dump(mode="json"),
                        }
                assert (
                    await connection.scalar(
                        select(func.count())
                        .select_from(source_record)
                        .where(
                            source_record.c.native_event_id
                            == "message:" + str(original.message.id)
                        )
                    )
                    == 1
                )
    finally:
        await reads.dispose()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable-database-url", required=True)
    asyncio.run(check(parser.parse_args().disposable_database_url))

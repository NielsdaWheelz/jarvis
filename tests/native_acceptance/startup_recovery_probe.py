"""Actual owner-lock startup recovery with controlled provider/catalogue failure."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from calendar_fixture import calendar_plan
from llm_agent_kernel import (
    AgentRole,
    Checkpoint,
    InputId,
    NativeDefinition,
    NativeDelivery,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import PromptSections, render_prompt
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
from pydantic import SecretStr
from sqlalchemy import select

from jarvis import cli
from jarvis.admission import JarvisOwner
from jarvis.db import create_engine, message, native_attempt
from jarvis.memory import MemoryStore, RemembererRunSummary
from jarvis.memory_workers import RemembererWorker
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.ownership import deployment_ownership
from jarvis.terminal import JarvisTerminal


class CatalogUnavailable(RuntimeError):
    pass


class NoRuntime:
    async def close(self):
        pass


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])

    async def forbidden_handler(*args):
        raise AssertionError("sealed recovery entered a tool")

    plan = calendar_plan(forbidden_handler)
    definition = NativeDefinition(
        ProviderConfiguration(
            CredentialRef("local_account", "proof"), "proof", "high", "one", "a" * 64
        ),
        AgentRole("proof", PromptSections(())),
        JsonSchemaAgentOutput("jarvis_main", JarvisTerminal.model_json_schema()),
        plan.profile,
        "original-schema",
    )
    try:
        for boundary in ("provider", "catalogue"):
            with tempfile.TemporaryDirectory(
                prefix="jarvis-startup-recovery-"
            ) as value:
                directory = Path(value)
                scope = str(9_000_000_000_000 + int(uuid4().hex[:9], 16))
                async with deployment_ownership(engine) as database:
                    owner = JarvisOwner(database, scope)
                    item = await MessageStore(database).insert_waking(
                        role="owner",
                        text="retain this original sealed answer",
                        source="proof",
                        source_conversation_id=scope,
                        source_message_id=str(uuid4()),
                        created_at=datetime.now(UTC),
                    )
                    attempt_id = str(uuid4())
                    request = NativeRequest(
                        attempt_id,
                        owner.permit("original:" + attempt_id),
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
                        submitted_request=freeze_json_value({"controlled": attempt_id}),
                    )
                    ref = AgentSessionRef(
                        "agent-session-ref.v1",
                        "codex",
                        "sdk",
                        "proof",
                        "original",
                        "a" * 64,
                        "b" * 64,
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
                        "response": {"type": "answered", "text": "original answer"},
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
                        NativeTerminalEvidence(
                            prepared, turn, "codex-turn-completed.v1"
                        ),
                        RawAgentOutput(freeze_json_value(final)),
                    )
                    await journal.record_outcome(attempt_id, terminal)
                settings = SimpleNamespace(
                    database_url=SecretStr(os.environ["JARVIS_PROOF_DATABASE_URL"]),
                    runtime_state_directory=directory,
                    discord=SimpleNamespace(channel_id=int(scope)),
                    embedding_openai_api_key=SecretStr("unused-controlled-credential"),
                )

                async def unavailable(*, failure=boundary, **kwargs):
                    raise CatalogUnavailable(failure)

                with (
                    patch.object(cli, "_validate_runtime_layout"),
                    patch.object(cli, "_compose_main", unavailable),
                    patch.object(
                        cli,
                        "build_agent_runtime",
                        side_effect=(
                            CatalogUnavailable(boundary)
                            if boundary == "provider"
                            else None
                        ),
                        return_value=NoRuntime(),
                    ),
                ):
                    try:
                        await cli.serve(settings, SimpleNamespace(endpoints={}))
                    except CatalogUnavailable:
                        pass
                    else:
                        raise AssertionError("current composition trap was skipped")
                async with deployment_ownership(engine) as database:
                    async with database.connect() as connection:
                        row = (
                            (
                                await connection.execute(
                                    select(native_attempt).where(
                                        native_attempt.c.id == UUID(attempt_id)
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
                                select(message.c.request_state).where(
                                    message.c.id == item.message.id
                                )
                            )
                            == "completed"
                        )
                        assert (
                            await connection.scalar(
                                select(message.c.text).where(
                                    message.c.source == "native_final",
                                    message.c.trace["native_attempt_id"].as_string()
                                    == attempt_id,
                                )
                            )
                            == "original answer"
                        )
                    memory = MemoryStore(database)
                    groups = await memory.select_pending_rememberer_groups(
                        maximum_groups=100, maximum_messages_per_group=10
                    )
                    group = next(
                        group
                        for group in groups
                        if any(target.id == item.message.id for target in group.targets)
                    )
                    assert not group.per_row_fallback
                    assert group.settlement is not None
                    worker = RemembererWorker(
                        definition=None,
                        plan=None,
                        owner=JarvisOwner(database, scope),
                        provider=None,
                        model_decisions=None,
                        dispatcher_factory=None,
                        memory=memory,
                        messages=MessageStore(database),
                        embedder=None,
                        maximum_messages_per_group=10,
                    )
                    material = await worker._rememberer_source(
                        group, PromptSections(())
                    )
                    assert "original answer" in render_prompt(material)
                    # Only the content decision is controlled. Selection, original
                    # conclusion recovery, memory commit and watermark are actual.
                    result = await memory.commit_rememberer_result(
                        group=group,
                        memory_texts=("controlled remembered fact after " + boundary,),
                        run=RemembererRunSummary("controlled-" + str(uuid4()), 1),
                    )
                    assert len(result.created) == 1
                    async with database.connect() as connection:
                        assert (
                            await connection.scalar(
                                select(message.c.remembered_at).where(
                                    message.c.id == item.message.id
                                )
                            )
                            is not None
                        )
                print(
                    boundary + " unavailable: original local startup settlement GREEN"
                )
    finally:
        await engine.dispose()


asyncio.run(main())

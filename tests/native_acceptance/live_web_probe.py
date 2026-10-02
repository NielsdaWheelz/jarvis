"""Temporary actual main/model/web proof, isolated from private connectors.

The empty saved recall and rememberer queue are controlled boundaries. This
qualifies actual main reasoning, provider callbacks and public research only.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
from llm_agent_kernel import CancellationToken, CodexProvider
from llm_tools import CapabilityProfile, Native, ProfileId, ToolGrant, ToolId, ToolPlan
from provider_runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from pydantic import SecretStr
from sqlalchemy import select

from jarvis.actions import ActionStore
from jarvis.admission import JarvisOwner
from jarvis.cli import _compose_main
from jarvis.config import DiscordSettings
from jarvis.db import (
    create_engine,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    read_position,
)
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.embeddings import OpenAIEmbedder
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import KernelRuntime
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore
from jarvis.native_runtime import NativeRunner
from jarvis.ownership import deployment_ownership
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.settings import Settings
from jarvis.write_dispatch import WriteToolDispatcher
from jarvis.write_gate import AutomaticWriteGate


async def main():
    private = Path(tempfile.mkdtemp(prefix="jarvis-native-web-"))
    os.chmod(private, 0o700)
    provider_state = private / "provider-state"
    provider_state.mkdir(mode=0o700)
    brave_key = None
    for line in (
        Path("/Users/nnandal/Documents/code/nexus-web/.env").read_text().splitlines()
    ):
        name, separator, value = line.partition("=")
        if separator and name.strip() == "BRAVE_SEARCH_API_KEY":
            brave_key = shlex.split(value)[0]
    assert brave_key
    conversation = os.environ.get("JARVIS_PROOF_CONVERSATION") or str(
        9_000_000_000_000 + int(uuid4().hex[:9], 16)
    )
    settings = Settings(
        database_url=SecretStr(os.environ["JARVIS_PROOF_DATABASE_URL"]),
        discord=DiscordSettings(
            bot_token=SecretStr("unused-discord-credential"),
            owner_user_id=1,
            guild_id=1,
            channel_id=int(conversation),
        ),
        owner_timezone="America/Los_Angeles",
        codex_profile_key="personal",
        codex_model="gpt-5.6-terra",
        codex_host_config_path=private / "unused-host.json",
        agent_cli_path=private / "unused-agent",
        agent_client_config_path=private / "unused-agent.json",
        runtime_state_directory=provider_state,
        google_oauth_state_path=private / "unused-google.json",
        google_oauth_client_id=SecretStr("unused-google-id"),
        google_oauth_client_secret=SecretStr("unused-google-secret"),
        connector_encryption_key_version="proof",
        connector_encryption_secret=SecretStr(
            base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        ),
        maps_api_key=SecretStr("unused-maps-key"),
        brave_api_key=SecretStr(brave_key),
        embedding_openai_api_key=SecretStr("unused-embedding-key"),
        verified_owner_only_calendar_ids=("unused-calendar",),
    )
    engine = create_engine(settings.database_url.get_secret_value())
    runtime = AgentRuntime(
        AgentRuntimeConfig(
            state_root_base=provider_state,
            codex_endpoints={"personal": Path(os.environ["JARVIS_PROOF_CODEX_SOCKET"])},
            max_turn_seconds=300,
        )
    )
    provider = CodexProvider(
        runtime, cwd_parent=Path(os.environ["JARVIS_PROOF_CWD_PARENT"])
    )
    kernel = KernelRuntime(runtime, provider)
    try:
        async with (
            deployment_ownership(engine) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            actions = ActionStore(database)
            store = MessageStore(database)
            owner = JarvisOwner(database, conversation)
            memories = PostgresMemoryRepository(database)
            composition, definitions, agents = await _compose_main(
                settings=settings,
                agent_runtime=runtime,
                actions=actions,
                memory_repository=memories,
                embedder=OpenAIEmbedder(
                    settings.embedding_openai_api_key, http_client=http
                ),
                google_oauth_http=http,
                google_api_http=http,
                maps_http=http,
                brave_http=http,
            )
            full_plan = definitions.plans["main"]
            profile = CapabilityProfile(
                ProfileId("slice6_main"),
                tuple(
                    ToolGrant(ToolId(tool), full_plan.grant(ToolId(tool)).limits)
                    for tool in ("web.search", "web.read")
                ),
                full_plan.profile.run_limits,
            ).freeze(composition.catalog)
            plan = ToolPlan(profile.id, Native()).freeze(composition.catalog, profile)
            definitions = replace(
                definitions, plans={**definitions.plans, "main": plan}
            )

            def journal_factory(evidence):
                return PostgresModelDecisionJournal(database, evidence=evidence)

            gate = AutomaticWriteGate(
                definition=definitions.automatic_write_gate,
                plan=definitions.plans["automatic_write_gate"],
                owner=owner,
                provider=provider,
                model_decisions=journal_factory,
            )
            lane = asyncio.Lock()
            remembered = []
            runner = NativeRunner(
                settings=settings,
                store=store,
                owner=owner,
                kernel_runtime=kernel,
                definitions=definitions,
                history=PostgresCanonicalHistory(database),
                dispatcher_factory=lambda checkpoint: WriteToolDispatcher(
                    checkpoint=checkpoint,
                    gate=gate,
                    actions=actions,
                    google_write=composition.google_write,
                    agents=agents,
                    read=ReadToolDispatcher(
                        host_secrets=settings.host_secrets,
                        recorder=PostgresReadRecorder(database),
                    ),
                    owner_timezone=settings.owner_timezone,
                    source_conversation_id=conversation,
                    verified_owner_only_calendar_ids=settings.verified_owner_only_calendar_ids,
                    host_secrets=settings.host_secrets,
                    schedule_changed=lambda: None,
                    dispatch_lane=lane,
                ),
                memory_repository=memories,
                memory_dispatcher_factory=lambda: MemoryToolDispatcher(
                    PostgresReadRecorder(database)
                ),
                model_decisions=journal_factory,
                rememberer=SimpleNamespace(
                    enqueue=lambda ids, context: remembered.extend(ids)
                ),
                actions=actions,
            )
            controls = os.environ.get("JARVIS_PROOF_MODE") == "controls"
            restarting = os.environ.get("JARVIS_PROOF_MODE") == "restart"
            killing = os.environ.get("JARVIS_PROOF_MODE") == "kill"
            if restarting:
                existing = await store.message_by_id(
                    UUID(os.environ["JARVIS_PROOF_INPUT_ID"])
                )
                assert existing is not None and existing.request_state == "pending"
                item = SimpleNamespace(message=existing)
            else:
                item = await store.insert_waking(
                    role="owner",
                    source="actual_native_web_proof",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                    text=(
                        (
                            "give a brief progress update, then prove that the "
                            "square root of two is irrational. think through "
                            "all logical steps and give the complete concise "
                            "proof. do not use tools."
                        )
                        if killing
                        else (
                            "please read "
                            "https://docs.python.org/3.12/library/asyncio-task.html"
                            " using web.read (the exact official URL is "
                            "supplied, so search is unnecessary). briefly "
                            "report progress before reading. explain in one "
                            "sentence what TaskGroup does when a task raises an"
                            " exception. retain any different request arriving "
                            "while you work."
                        )
                        if controls
                        else (
                            "please search the web for the official python 3.12"
                            " asyncio taskgroup documentation, then read the "
                            "official page returned by search. explain in one "
                            "sentence what happens when a task raises an "
                            "exception. use both web.search and web.read "
                            "successfully before your final answer. briefly "
                            "tell me when you find the official source."
                        )
                    ),
                )
                await store.record_recall(
                    message_id=item.message.id,
                    candidate_identities=(),
                    selected_identities=(),
                    run_id="controlled-empty-recall-" + str(uuid4()),
                    terminal_outcome="controlled_empty_selection",
                    provider_turns=0,
                    input_tokens=None,
                    output_tokens=None,
                    duration_seconds=0,
                )
            print(
                json.dumps(
                    {
                        "phase": "running",
                        "selected_model": definitions.main.provider.model_key,
                        "reasoning": definitions.main.provider.reasoning,
                        "conversation": conversation,
                        "receipt_directory": str(private),
                    }
                ),
                flush=True,
            )
            try:
                async with asyncio.timeout(300):
                    work = asyncio.create_task(runner.run(CancellationToken()))
                    second = None
                    if killing:
                        while not work.done():
                            async with database.connect() as connection:
                                current = (
                                    (
                                        await connection.execute(
                                            select(native_attempt).where(
                                                native_attempt.c.conversation_id
                                                == conversation
                                            )
                                        )
                                    )
                                    .mappings()
                                    .one_or_none()
                                )
                            if (
                                current is not None
                                and current["native_binding"] is not None
                            ):
                                ready = Path(os.environ["JARVIS_PROOF_KILL_READY"])
                                ready.write_text(
                                    json.dumps(
                                        {
                                            "worker_pid": os.getpid(),
                                            "conversation": conversation,
                                            "input_id": str(item.message.id),
                                            "attempt_id": str(current["id"]),
                                            "native_binding": current["native_binding"],
                                        },
                                        default=str,
                                    )
                                )
                                os.chmod(ready, 0o600)
                                break
                            await asyncio.sleep(0.02)
                    if controls:
                        while not work.done():
                            async with database.connect() as connection:
                                bound = await connection.scalar(
                                    select(native_attempt.c.native_binding).where(
                                        native_attempt.c.conversation_id == conversation
                                    )
                                )
                            if bound is not None:
                                second = await store.insert_waking(
                                    role="owner",
                                    source="actual_native_new_topic",
                                    source_conversation_id=conversation,
                                    source_message_id=str(uuid4()),
                                    created_at=datetime.now(UTC),
                                    text=(
                                        "also answer this separate request now:"
                                        " what is 17 + 25? retain and finish "
                                        "the documentation request too."
                                    ),
                                )
                                await store.record_recall(
                                    message_id=second.message.id,
                                    candidate_identities=(),
                                    selected_identities=(),
                                    run_id="controlled-empty-recall-" + str(uuid4()),
                                    terminal_outcome="controlled_empty_selection",
                                    provider_turns=0,
                                    input_tokens=None,
                                    output_tokens=None,
                                    duration_seconds=0,
                                )
                                break
                            await asyncio.sleep(0.05)
                    outcome = await work
                    if controls:
                        assert second is not None, (
                            "new input must arrive during actual native reasoning"
                        )
                        if (
                            await store.message_by_id(second.message.id)
                        ).request_state == "pending":
                            await runner.run(CancellationToken())
                        async with database.connect() as connection:
                            before_stop = (
                                (
                                    await connection.execute(
                                        select(native_attempt.c.id).where(
                                            native_attempt.c.conversation_id
                                            == conversation
                                        )
                                    )
                                )
                                .scalars()
                                .all()
                            )
                            progress = await connection.scalar(
                                select(message.c.id).where(
                                    message.c.source_conversation_id == conversation,
                                    message.c.source == "native_progress",
                                )
                            )
                            delivered = await connection.scalar(
                                select(native_input_delivery.c.state).where(
                                    native_input_delivery.c.message_id
                                    == second.message.id
                                )
                            )
                        assert progress is not None, (
                            "actual public progress must reach the canonical outbox"
                        )
                        assert delivered in {"sent", "queued", "recorded"}, (
                            "new topic needs a native delivery receipt"
                        )
                        assert (
                            await store.message_by_id(item.message.id)
                        ).request_state == "completed"
                        assert (
                            await store.message_by_id(second.message.id)
                        ).request_state == "completed"
                        stopping = await store.insert_waking(
                            role="owner",
                            source="actual_native_stop_proof",
                            source_conversation_id=conversation,
                            source_message_id=str(uuid4()),
                            created_at=datetime.now(UTC),
                            text=(
                                "please read the official Python 3.12 asyncio "
                                "docs, then read "
                                "https://docs.python.org/3.12/library/asyncio-sync.html"
                                " and "
                                "https://docs.python.org/3.12/library/asyncio-queue.html."
                                " compare their rules carefully; provide "
                                "progress between the reads."
                            ),
                        )
                        await store.record_recall(
                            message_id=stopping.message.id,
                            candidate_identities=(),
                            selected_identities=(),
                            run_id="controlled-empty-recall-" + str(uuid4()),
                            terminal_outcome="controlled_empty_selection",
                            provider_turns=0,
                            input_tokens=None,
                            output_tokens=None,
                            duration_seconds=0,
                        )
                        active = asyncio.create_task(runner.run(CancellationToken()))
                        while not active.done():
                            async with database.connect() as connection:
                                bound = await connection.scalar(
                                    select(native_attempt.c.native_binding).where(
                                        native_attempt.c.conversation_id
                                        == conversation,
                                        native_attempt.c.id.not_in(before_stop),
                                    )
                                )
                            if bound is not None:
                                break
                            await asyncio.sleep(0.05)
                        assert not active.done(), (
                            "stop must interrupt actual accepted native reasoning"
                        )
                        stopped = await store.insert_waking(
                            role="owner",
                            source="actual_native_stop_proof",
                            source_conversation_id=conversation,
                            source_message_id=str(uuid4()),
                            created_at=datetime.now(UTC),
                            text="stop",
                            control_kind="stop",
                        )
                        assert (
                            await store.message_by_id(stopping.message.id)
                        ).request_state == "stopped"
                        async with asyncio.timeout(20):
                            assert (await active).status == "stopped"
                        assert await store.paused(conversation)
                        print(
                            json.dumps(
                                {
                                    "phase": "actual_controls_green",
                                    "native_input_delivery": delivered,
                                    "stop_control": str(stopped.message.id),
                                }
                            ),
                            flush=True,
                        )
            finally:
                await runner.close()
            async with database.connect() as connection:
                attempts = (
                    (
                        await connection.execute(
                            select(native_attempt).where(
                                native_attempt.c.conversation_id == conversation
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                invocations = (
                    (
                        await connection.execute(
                            select(
                                native_invocation,
                                read_position.c.result.label("recorded_result"),
                            )
                            .join(
                                native_attempt,
                                native_attempt.c.id == native_invocation.c.attempt_id,
                            )
                            .outerjoin(
                                read_position,
                                read_position.c.position
                                == native_invocation.c.read_position,
                            )
                            .where(native_attempt.c.conversation_id == conversation)
                            .order_by(native_invocation.c.ordinal)
                        )
                    )
                    .mappings()
                    .all()
                )
                messages = (
                    (
                        await connection.execute(
                            select(message)
                            .where(message.c.source_conversation_id == conversation)
                            .order_by(message.c.created_at)
                        )
                    )
                    .mappings()
                    .all()
                )
            receipt = {
                "kind": "actual_jarvis_native_restart"
                if restarting
                else "actual_jarvis_native_controls"
                if controls
                else "actual_jarvis_main_public_research",
                "source_overlay": True,
                "selected_model": definitions.main.provider.model_key,
                "selected_reasoning": definitions.main.provider.reasoning,
                "controlled_boundaries": [
                    "empty saved recall",
                    "rememberer queue",
                    "unused private connectors",
                    "discord outbox inspection",
                ],
                "conversation": conversation,
                "outcome": outcome.status,
                "attempts": [dict(row) for row in attempts],
                "invocations": [dict(row) for row in invocations],
                "messages": [dict(row) for row in messages],
            }
            receipt_path = private / "actual-jarvis-main-web.json"
            receipt_path.write_text(json.dumps(receipt, default=str, indent=2) + "\n")
            os.chmod(receipt_path, 0o600)
            successes = {
                row["tool_id"]
                for row in invocations
                if row["recorded_result"] is not None
                and row["recorded_result"].get("type") == "Success"
            }
            print(
                json.dumps(
                    {
                        "phase": "settled",
                        "status": outcome.status,
                        "successful_tools": sorted(successes),
                        "receipt": str(receipt_path),
                    }
                ),
                flush=True,
            )
            assert successes == (
                set()
                if restarting or killing
                else {"web.read"}
                if controls
                else {"web.search", "web.read"}
            ), "real selected research tools must succeed"
            if restarting:
                assert len(attempts) == 2
                attempts = sorted(attempts, key=lambda row: row["attempt_seq"])
                assert (
                    attempts[0]["terminal"] is None
                    and attempts[0]["fenced_at"] is not None
                )
                assert (
                    attempts[0]["native_binding"]["session_ref"]["native_session_id"]
                    != attempts[1]["native_binding"]["session_ref"]["native_session_id"]
                )
            completed = [
                row
                for row in attempts
                if row["product_outcome"] is not None
                and row["product_outcome"].get("status") == "committed"
            ]
            assert completed and all(row["terminal"] is not None for row in completed)
            if restarting:
                assert attempts[-1] in completed
            assert (
                next(row for row in messages if row["id"] == item.message.id)[
                    "request_state"
                ]
                == "completed"
            )
            assert item.message.id in remembered
            print(
                (
                    "actual Jarvis selected model/high + automatic fresh-thread"
                    " recovery: GREEN"
                )
                if restarting
                else (
                    "actual Jarvis selected model/high + strict terminal + "
                    "actual controls/read: GREEN"
                )
                if controls
                else (
                    "actual Jarvis selected model/high + strict terminal + "
                    "successful public search/read: GREEN"
                ),
                flush=True,
            )
    finally:
        await kernel.close()
        await engine.dispose()


asyncio.run(main())

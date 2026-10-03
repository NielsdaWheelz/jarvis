"""Actual killed worker and PostgreSQL connection loss; controlled model/read.

The process and DB boundaries are real. These peers do not qualify research.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AgentRole,
    CancellationToken,
    Checkpoint,
    InputId,
    NativeDefinition,
    NativeDelivery,
    NativeDispatchLineage,
    NativeInvocationProposal,
    NativeRequest,
    ProviderConfiguration,
)
from llm_tools import (
    Available,
    CapabilityProfile,
    HandlerSuccess,
    Native,
    NoDeclaredError,
    PolicyEpoch,
    ProfileId,
    PromptDocument,
    PromptSections,
    ReplayPolicy,
    RunBudgetState,
    RunLimits,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    ToolGrant,
    ToolId,
    ToolLimits,
    ToolPlan,
    ToolSpec,
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
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text

from jarvis.actions import ActionStore
from jarvis.admission import JarvisOwner
from jarvis.db import create_engine, native_attempt
from jarvis.messages import MessageStore
from jarvis.native_journal import PostgresNativeJournal
from jarvis.native_runtime import NativeRunner
from jarvis.ownership import DeploymentOwnershipDefect, deployment_ownership
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.terminal import JarvisTerminal


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str


def fixture(handler):
    spec = ToolSpec(
        ToolId("web.search"),
        "controlled entered read",
        PromptDocument("bounded controlled read"),
        Input,
        Output,
        NoDeclaredError,
        ToolEffect.Read,
        ToolLimits(1024, 4096, 1, 360),
    )
    binding = ToolBinding(
        spec, Available(handler), ReplayPolicy.BilledOnce, "one", PolicyEpoch("one"), {}
    )
    catalog = ToolCatalog.compose((ToolFamily("web", (spec,), (binding,)),))
    maximum = CapabilityProfile(
        ProfileId("proof"),
        (ToolGrant(spec.id, None),),
        RunLimits(None, None, None, None, 1, None),
    ).freeze(catalog)
    plan = ToolPlan(maximum.id, Native()).freeze(catalog, maximum)
    definition = NativeDefinition(
        ProviderConfiguration(
            CredentialRef("local_account", "proof"), "proof", "high", "one", "a" * 64
        ),
        AgentRole("proof", PromptSections(())),
        JsonSchemaAgentOutput("jarvis_main", JarvisTerminal.model_json_schema()),
        maximum,
        "one",
    )
    return definition, plan, binding


async def arm(database, owner, journal, definition, plan, binding, input_id):
    attempt = str(uuid4())
    request = NativeRequest(
        attempt,
        owner.permit("jarvis-native:" + attempt),
        "thread",
        (InputId(str(input_id)),),
        PromptSections(()),
        PromptSections(()),
        plan,
        "restart_reasoning",
        None,
        Checkpoint(str(input_id)),
    )
    prepared = AgentAttempt(attempt, "a" * 64)
    await journal.arm(
        request,
        prepared,
        definition_fingerprint=definition.session_fingerprint(plan),
        submitted_request=freeze_json_value({"controlled": attempt}),
    )
    ref = AgentSessionRef(
        "agent-session-ref.v1", "codex", "sdk", "proof", "proof", "a" * 64, "b" * 64
    )
    turn = AgentTurnRef(ref, "controlled-" + attempt)
    await journal.bind(attempt, turn)
    await journal.record_delivery(
        NativeDelivery(
            attempt, "initial-" + attempt, request.input_ids, "initial", "sent", None
        )
    )
    proposal = NativeInvocationProposal(
        attempt,
        str(uuid4()),
        binding.spec.id,
        freeze_json_value({"query": "original"}),
        "a" * 64,
        plan.plan_revision,
        binding.spec.tool_contract_revision,
        binding.implementation_revision,
        binding.policy_revision,
        request.input_ids,
        request.through_checkpoint,
        None,
    )
    return request, prepared, turn, proposal


async def child(mode, ready):
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            scope = "process-proof-" + str(uuid4())
            owner, store = JarvisOwner(database, scope), MessageStore(database)
            item = await store.insert_waking(
                role="owner",
                text="retain this process-owned work",
                source="controlled_process_proof",
                source_conversation_id=scope,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            async with database.connect() as connection:
                backend_pid = await connection.scalar(text("select pg_backend_pid()"))
            state = {
                "mode": mode,
                "scope": scope,
                "input_id": str(item.message.id),
                "backend_pid": backend_pid,
                "worker_pid": os.getpid(),
            }

            async def handler(value, context):
                ready.write_text(json.dumps({**state, "phase": "entered_read"}))
                await asyncio.Event().wait()
                return HandlerSuccess(Output(text="unreachable"), 1)

            definition, plan, binding = fixture(handler)
            journal = PostgresNativeJournal(
                database, definition=definition, plan=plan, owner=owner
            )
            request, prepared, turn, proposal = await arm(
                database, owner, journal, definition, plan, binding, item.message.id
            )
            state["attempt_id"] = request.attempt_id
            state["call_id"] = proposal.call_id
            if mode == "sealed":
                final = {
                    "response": {
                        "type": "answered",
                        "text": "sealed before process death",
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
                    turn.session_ref,
                    NativeTerminalEvidence(prepared, turn, "codex-turn-completed.v1"),
                    RawAgentOutput(freeze_json_value(final)),
                )
                await journal.record_outcome(request.attempt_id, terminal)
                ready.write_text(
                    json.dumps(
                        {
                            **state,
                            "phase": "sealed",
                            "original_terminal": terminal_to_json(terminal),
                        }
                    )
                )
                await asyncio.Event().wait()
            else:
                record = await journal.record_invocation(proposal)
                state["invocation_id"] = record.invocation_id
                lineage = NativeDispatchLineage(
                    request.attempt_id,
                    record.invocation_id,
                    record.ordinal,
                    request.permit,
                    request.input_ids,
                    request.through_checkpoint,
                    definition.session_fingerprint(plan),
                )
                work = asyncio.create_task(
                    ReadToolDispatcher(
                        host_secrets=(), recorder=PostgresReadRecorder(database)
                    ).dispatch(
                        binding=binding,
                        validated_input=Input(query="original"),
                        plan=plan,
                        budgets=RunBudgetState(plan.profile.run_limits),
                        cancellation=CancellationToken(),
                        lineage=lineage,
                    )
                )

                async def heartbeat():
                    while True:
                        await owner.require_current(request.permit)
                        await asyncio.sleep(0.05)

                heartbeat_task = asyncio.create_task(heartbeat())
                try:
                    done, _ = await asyncio.wait(
                        (work, heartbeat_task), return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
                finally:
                    work.cancel()
                    heartbeat_task.cancel()
                    await asyncio.gather(work, heartbeat_task, return_exceptions=True)
    except DeploymentOwnershipDefect:
        ready.with_suffix(".lost").write_text(
            json.dumps({"phase": "ownership_lost", "worker_pid": os.getpid()})
        )
    finally:
        await engine.dispose()


async def parent():
    private = Path(tempfile.mkdtemp(prefix="jarvis-native-process-proof-"))
    os.chmod(private, 0o700)
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    calls = 0

    async def handler(value, context):
        nonlocal calls
        calls += 1
        return HandlerSuccess(Output(text="forbidden repeat"), 1)

    definition, plan, binding = fixture(handler)
    try:
        for mode in ("sealed", "entered", "connection"):
            ready = private / (mode + ".json")
            worker = await asyncio.create_subprocess_exec(
                sys.executable,
                __file__,
                "child",
                mode,
                str(ready),
                env=os.environ.copy(),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                async with asyncio.timeout(15):
                    while not ready.exists():
                        if worker.returncode is not None:
                            assert worker.stderr is not None
                            raise AssertionError(
                                "worker failed before ready: "
                                + (await worker.stderr.read()).decode()[-2000:]
                            )
                        await asyncio.sleep(0.03)
                state = json.loads(ready.read_text())
                assert state["worker_pid"] == worker.pid
                if mode == "connection":
                    async with engine.begin() as connection:
                        assert (
                            await connection.scalar(
                                text(
                                    "select pg_terminate_backend(:pid) from"
                                    " pg_stat_activity where pid=:pid and "
                                    "datname=current_database()"
                                ),
                                {"pid": state["backend_pid"]},
                            )
                            is True
                        )
                    async with asyncio.timeout(10):
                        await worker.wait()
                    assert ready.with_suffix(".lost").exists(), (
                        "lost owner connection must fence the real process"
                    )
                else:
                    worker.kill()
                    await worker.wait()
                    assert worker.returncode < 0
                async with deployment_ownership(engine) as database:
                    owner, store = (
                        JarvisOwner(database, state["scope"]),
                        MessageStore(database),
                    )
                    remembered = []
                    runner = NativeRunner(
                        settings=None,
                        store=store,
                        owner=owner,
                        kernel_runtime=SimpleNamespace(provider=SimpleNamespace()),
                        definitions=SimpleNamespace(
                            main=definition, plans={"main": plan}
                        ),
                        history=None,
                        dispatcher_factory=None,
                        memory_repository=None,
                        memory_dispatcher_factory=None,
                        model_decisions=None,
                        rememberer=SimpleNamespace(
                            enqueue=lambda ids,
                            context,
                            receipts=remembered: receipts.extend(ids)
                        ),
                        actions=ActionStore(database),
                    )
                    await runner.recover()
                    async with database.connect() as connection:
                        old = (
                            (
                                await connection.execute(
                                    select(native_attempt).where(
                                        native_attempt.c.id == UUID(state["attempt_id"])
                                    )
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert old["fenced_at"] is not None
                    if mode == "sealed":
                        assert old["terminal"] == state["original_terminal"]
                        assert old["product_outcome"]["status"] == "committed"
                        assert (
                            await store.message_by_id(UUID(state["input_id"]))
                        ).request_state == "completed"
                        assert remembered == [UUID(state["input_id"])]
                        continue
                    assert old["terminal"] is None and old["product_outcome"] is None
                    journal = PostgresNativeJournal(
                        database, definition=definition, plan=plan, owner=owner
                    )
                    request, _, _, proposal = await arm(
                        database,
                        owner,
                        journal,
                        definition,
                        plan,
                        binding,
                        UUID(state["input_id"]),
                    )
                    record = await journal.record_invocation(proposal)
                    lineage = NativeDispatchLineage(
                        request.attempt_id,
                        record.invocation_id,
                        record.ordinal,
                        request.permit,
                        request.input_ids,
                        request.through_checkpoint,
                        definition.session_fingerprint(plan),
                    )
                    result = await ReadToolDispatcher(
                        host_secrets=(), recorder=PostgresReadRecorder(database)
                    ).dispatch(
                        binding=binding,
                        validated_input=Input(query="original"),
                        plan=plan,
                        budgets=RunBudgetState(plan.profile.run_limits),
                        cancellation=CancellationToken(),
                        lineage=lineage,
                    )
                    assert result.result["error"]["code"] == "paid_read_outcome_unknown"
                    assert (
                        str(result.host_ref)
                        == "native-invocation:" + state["invocation_id"]
                    )
                    assert calls == 0, (
                        "fresh reasoning repeated an entered paid read "
                        "after process/connection death"
                    )
                    await journal.fence(request.attempt_id, "proof completed")
                    print(
                        mode
                        + ": actual owner loss and retained unknown-read barrier GREEN",
                        flush=True,
                    )
            finally:
                if worker.returncode is None:
                    worker.kill()
                    await worker.wait()
        print(
            (
                "actual process kill, owner connection loss, fresh local "
                "terminal recovery and no read redispatch: GREEN"
            ),
            flush=True,
        )
    finally:
        await engine.dispose()


asyncio.run(child(sys.argv[2], Path(sys.argv[3])) if len(sys.argv) > 1 else parent())

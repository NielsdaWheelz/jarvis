from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from llm_agent_kernel import (
    AdmissionRequest,
    AdmissionResult,
    AdmissionStateDefect,
    AppendInputs,
    CancellationToken,
    Checkpoint,
    CheckpointStateDefect,
    ClaimAcquired,
    ClaimId,
    CodexProvider,
    HostInput,
    InMemoryInputCheckpointPort,
    InputClaim,
    InputId,
    NoNewInput,
    OwnerToken,
    Preempt,
    RunId,
    SessionCoordinator,
    SettleMoreInput,
    StoppedConclusion,
    StopReason,
    ThreadCompleted,
    ThreadId,
    ThreadStopKind,
    ThreadStopped,
    run_thread,
)
from llm_tools import (
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    RunLimits,
)
from provider_runtime.agent_runtime import (
    AgentEvent,
    AgentRuntime,
    AgentSession,
    AgentSessionRef,
    AgentSessionRequest,
    AgentTerminal,
    NewSession,
    ResumeSession,
    SessionUnavailable,
    TextContent,
    TurnRequest,
    freeze_json_object,
)
from provider_runtime.types import Absent, CancelSignal
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.admission import (
    ExactToolBudgetFactory,
    InProcessBudgetState,
    RollingAdmissionLimits,
    RollingAdmissionPort,
)
from jarvis.config import DiscordSettings
from jarvis.context import CanonicalMessage, JarvisContextSource
from jarvis.db import create_engine, message
from jarvis.definitions import SLICE1_KERNEL_LIMITS, build_slice1_definitions
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import EmptySlice1Dispatcher, KernelRuntime
from jarvis.messages import MessageStore, SettlementTrace
from jarvis.messages import Settlement as MessageSettlement
from jarvis.service import Slice1ThreadRunner
from jarvis.session import AtomicSessionRefPort
from jarvis.settings import Settings

AS_OF = datetime(2026, 9, 3, 12, tzinfo=UTC)
THREAD_ID = ThreadId("discord-channel-1")
OWNER_TOKEN = OwnerToken("deployment-owner")
DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")


def _sections(text: str) -> PromptSections:
    return PromptSections(
        (PromptSection(PromptSectionKind("owner_input"), (), PromptText(text)),)
    )


def _input(name: str, text: str) -> HostInput:
    return HostInput(InputId(name), _sections(text), AS_OF)


def _claim(
    plan: Any,
    *,
    name: str = "one",
    text: str = "hello",
    attempt: int = 1,
) -> InputClaim:
    return InputClaim(
        ClaimId(f"claim-{name}"),
        (_input(f"input-{name}", text),),
        Checkpoint(f"checkpoint-{name}"),
        AS_OF,
        plan,
        attempt,
    )


class _History:
    def __init__(self, messages: tuple[CanonicalMessage, ...] = ()) -> None:
        self.messages = messages

    async def completed_history(
        self,
        thread_id: ThreadId,
        *,
        exclude_input_ids: tuple[InputId, ...],
        limit: int,
    ) -> tuple[CanonicalMessage, ...]:
        del thread_id, exclude_input_ids, limit
        return self.messages


class _Runtime:
    def __init__(
        self,
        steps: list[dict[str, object]],
        *,
        reject_next_stream: bool = False,
        on_stream: Any | None = None,
    ) -> None:
        self.steps = deque(steps)
        self.reject_next_stream = reject_next_stream
        self.on_stream = on_stream
        self.opens: list[AgentSessionRequest] = []
        self.turns: list[TurnRequest] = []
        self.closed: list[AgentSession] = []
        self.run_turn_calls = 0
        self._sessions = 0

    async def open_session(self, request: AgentSessionRequest) -> AgentSession:
        self.opens.append(request)
        self._sessions += 1
        ref = (
            request.open.ref
            if isinstance(request.open, ResumeSession)
            else self._ref(request)
        )
        return AgentSession(ref)

    def _ref(self, request: AgentSessionRequest) -> AgentSessionRef:
        return AgentSessionRef(
            "agent-session-ref.v1",
            "codex",
            "sdk",
            f"session-{self._sessions}",
            request.auth.profile_key,
            "1" * 64,
            "2" * 64,
        )

    async def stream_turn(
        self,
        session: AgentSession,
        request: TurnRequest,
        *,
        approvals: object | None = None,
        cancel: CancelSignal | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        del approvals, cancel
        self.turns.append(request)
        if self.reject_next_stream:
            self.reject_next_stream = False
            raise SessionUnavailable("scripted live session loss")
        if self.on_stream is not None:
            self.on_stream()
        yield AgentTerminal(
            status="succeeded",
            failure=None,
            final_text="untrusted provider projection",
            session_ref=session.ref,
            structured_output=freeze_json_object(_wire_step(self.steps.popleft())),
            usage=Absent(),
        )

    async def run_turn(self, *_args: object, **_kwargs: object) -> AgentTerminal:
        self.run_turn_calls += 1
        raise AssertionError("Jarvis must consume the observed event stream")

    async def close_session(self, session: AgentSession) -> None:
        self.closed.append(session)


def _wire_step(value: dict[str, object]) -> dict[str, object]:
    """Build only the provider fake's kernel-owned transport fixture."""
    step_type = value.get("type")
    wire: dict[str, object] = {
        "type": step_type,
        "say": None,
        "call_tool": None,
        "finish": None,
    }
    if step_type == "say":
        wire["say"] = {key: child for key, child in value.items() if key != "type"}
    elif step_type == "call_tool":
        payload = {key: child for key, child in value.items() if key != "type"}
        if "arguments" in payload:
            payload["arguments"] = json.dumps(
                payload["arguments"], separators=(",", ":")
            )
        wire["call_tool"] = payload
    elif step_type == "finish":
        payload = {key: child for key, child in value.items() if key != "type"}
        payload.setdefault("reason", None)
        wire["finish"] = payload
    return wire


def test_provider_terminal_fake_uses_json_string_tool_arguments() -> None:
    wire = _wire_step(
        {"type": "call_tool", "tool_id": "test.echo", "arguments": {"value": "exact"}}
    )

    assert wire == {
        "type": "call_tool",
        "say": None,
        "call_tool": {
            "tool_id": "test.echo",
            "arguments": '{"value":"exact"}',
        },
        "finish": None,
    }


class _Crash(BaseException):
    pass


class _CrashOnFirstSettlementStore(MessageStore):
    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self.settlement_calls = 0

    async def settle(
        self,
        *,
        consumed_message_ids: tuple[UUID, ...],
        source_conversation_id: str,
        trace: SettlementTrace,
        conclusion_text: str | None,
        conclusion_message_id: UUID | None = None,
        settled_at: datetime | None = None,
    ) -> MessageSettlement:
        self.settlement_calls += 1
        if self.settlement_calls == 1:
            raise _Crash
        return await super().settle(
            consumed_message_ids=consumed_message_ids,
            source_conversation_id=source_conversation_id,
            trace=trace,
            conclusion_text=conclusion_text,
            conclusion_message_id=conclusion_message_id,
            settled_at=settled_at,
        )


class _ReserveStateDefect(RollingAdmissionPort):
    async def reserve(self, request: AdmissionRequest) -> AdmissionResult:
        del request
        raise AdmissionStateDefect("injected post-preflight inconsistency")


class _CrashAfterSessionCas(InMemoryInputCheckpointPort):
    async def settle(self, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        raise _Crash


class _WrongBudgetFactory:
    def create(self, plan: Any) -> InProcessBudgetState:
        del plan
        return InProcessBudgetState(RunLimits(2, 0, 4_096, 4_096, 1, 30.0))


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _definitions() -> Any:
    return build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.4",
        owner_timezone="America/Los_Angeles",
    )


def _admission(tmp_path: Path, name: str) -> RollingAdmissionPort:
    path = tmp_path / f"{name}-admission.json"
    limits = RollingAdmissionLimits()
    RollingAdmissionPort.initialize(path, limits)
    return RollingAdmissionPort(path, limits, clock=lambda: AS_OF)


async def _run(
    *,
    run_id: str,
    definition: Any,
    checkpoints: InMemoryInputCheckpointPort,
    admission: RollingAdmissionPort,
    sessions: SessionCoordinator,
    context_source: Any,
    cancellation: CancellationToken | None = None,
    budget_factory: Any = None,
    clock: Any = None,
) -> Any:
    await admission.preflight(
        maximum_turns=definition.limits.max_provider_turns,
        maximum_input_tokens=definition.limits.max_provider_input_tokens,
        maximum_output_tokens=definition.limits.max_provider_output_tokens,
    )
    return await run_thread(
        run_id=RunId(run_id),
        thread_id=THREAD_ID,
        owner_token=OWNER_TOKEN,
        definition=definition,
        checkpoints=checkpoints,
        admission=admission,
        sessions=sessions,
        context_source=context_source,
        dispatcher=EmptySlice1Dispatcher(),
        budget_factory=budget_factory or ExactToolBudgetFactory(),
        cancellation=cancellation,
        clock=clock or time.monotonic,
    )


async def test_run_thread_continues_then_cold_reconstructs_after_session_loss(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    first = _claim(definitions.plans["main"], name="first")
    second = _claim(definitions.plans["main"], name="second")
    checkpoints = InMemoryInputCheckpointPort(
        (ClaimAcquired(first), ClaimAcquired(second))
    )
    references = AtomicSessionRefPort(tmp_path / "session.json", max_generations=32)
    history = JarvisContextSource(
        THREAD_ID,
        _History((CanonicalMessage("prior", "assistant", "earlier", AS_OF),)),
    )

    first_runtime = _Runtime([{"type": "say", "text": "first answer"}])
    first_provider = CodexProvider(
        cast(AgentRuntime, first_runtime), cwd_parent=tmp_path, cache_continuing=False
    )
    try:
        first_outcome = await _run(
            run_id="run-first",
            definition=definitions.main,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "resume"),
            sessions=SessionCoordinator(first_provider, references),
            context_source=history,
        )
    finally:
        await first_provider.shutdown()

    second_runtime = _Runtime(
        [{"type": "say", "text": "reconstructed answer"}], reject_next_stream=True
    )
    second_provider = CodexProvider(
        cast(AgentRuntime, second_runtime), cwd_parent=tmp_path, cache_continuing=False
    )
    try:
        second_outcome = await _run(
            run_id="run-second",
            definition=definitions.main,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "fallback"),
            sessions=SessionCoordinator(second_provider, references),
            context_source=history,
        )
    finally:
        await second_provider.shutdown()

    assert first_outcome.type == "completed"
    assert second_outcome.type == "completed"
    assert isinstance(second_runtime.opens[0].open, ResumeSession)
    assert isinstance(second_runtime.opens[1].open, NewSession)
    rendered = "\n".join(
        part.text
        for part in second_runtime.turns[1].input
        if isinstance(part, TextContent)
    )
    assert "earlier" in rendered
    assert second_runtime.run_turn_calls == 0


async def test_invalid_protocol_repairs_are_bounded_and_poison_is_consumed(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    claim = _claim(definitions.plans["main"], name="poison")
    checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(claim),))
    runtime = _Runtime(
        [
            {"type": "say", "text": "", "unexpected": True},
            {"type": "say", "text": "", "unexpected": True},
            {"type": "say", "text": "", "unexpected": True},
        ]
    )
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    try:
        outcome = await _run(
            run_id="run-poison",
            definition=definitions.main,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "poison"),
            sessions=SessionCoordinator(
                provider,
                AtomicSessionRefPort(
                    tmp_path / "poison-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await provider.shutdown()

    assert outcome.type is ThreadStopKind.protocol_error
    assert outcome.metrics.input_consumed is True
    assert len(runtime.turns) == 3
    assert checkpoints.settlements[0].conclusion == StoppedConclusion(
        StopReason.protocol_error
    )
    assert checkpoints.release_reasons == []


async def test_cancellation_and_host_stop_preempt_before_provider_io(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    cancelled_claim = _claim(definitions.plans["main"], name="cancelled")
    cancelled_checkpoints = InMemoryInputCheckpointPort(
        (ClaimAcquired(cancelled_claim),)
    )
    cancelled_runtime = _Runtime([])
    cancelled_provider = CodexProvider(
        cast(AgentRuntime, cancelled_runtime), cwd_parent=tmp_path
    )
    cancellation = CancellationToken()
    cancellation.cancel()
    try:
        cancelled = await _run(
            run_id="run-cancelled",
            definition=definitions.main,
            checkpoints=cancelled_checkpoints,
            admission=_admission(tmp_path, "cancelled"),
            sessions=SessionCoordinator(
                cancelled_provider,
                AtomicSessionRefPort(
                    tmp_path / "cancelled-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
            cancellation=cancellation,
        )
    finally:
        await cancelled_provider.shutdown()

    stopped_claim = _claim(definitions.plans["main"], name="stopped")
    stopped_checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(stopped_claim),))
    stopped_checkpoints.queue_poll(stopped_claim.claim_id, Preempt("owner stop"))
    stopped_runtime = _Runtime([])
    stopped_provider = CodexProvider(
        cast(AgentRuntime, stopped_runtime), cwd_parent=tmp_path
    )
    try:
        stopped = await _run(
            run_id="run-stopped",
            definition=definitions.main,
            checkpoints=stopped_checkpoints,
            admission=_admission(tmp_path, "stopped"),
            sessions=SessionCoordinator(
                stopped_provider,
                AtomicSessionRefPort(
                    tmp_path / "stopped-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await stopped_provider.shutdown()

    assert cancelled.type is ThreadStopKind.cancelled
    assert cancelled.metrics.input_consumed is True
    assert stopped.type is ThreadStopKind.preempted
    assert stopped.metrics.input_consumed is False
    assert cancelled_runtime.opens == []
    assert stopped_runtime.turns == []
    assert stopped_checkpoints.release_reasons == [
        (stopped_claim.claim_id, "preempted by host policy")
    ]


async def test_crash_after_session_ref_cas_forces_cold_recovery(tmp_path: Path) -> None:
    definitions = _definitions()
    references = AtomicSessionRefPort(
        tmp_path / "crash-session.json", max_generations=32
    )
    crashed_claim = _claim(definitions.plans["main"], name="crashed")
    crashed_checkpoints = _CrashAfterSessionCas((ClaimAcquired(crashed_claim),))
    runtime = _Runtime(
        [
            {"type": "say", "text": "speculative"},
            {"type": "say", "text": "recovered"},
        ]
    )
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    sessions = SessionCoordinator(provider, references)
    with pytest.raises(_Crash):
        await _run(
            run_id="run-crashed",
            definition=definitions.main,
            checkpoints=crashed_checkpoints,
            admission=_admission(tmp_path, "crashed"),
            sessions=sessions,
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    assert await references.load(THREAD_ID, definitions.main.fingerprint) is not None

    recovery_claim = _claim(
        definitions.plans["main"], name="recovery", text="hello", attempt=2
    )
    recovery_checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(recovery_claim),))
    try:
        recovered = await _run(
            run_id="run-recovery",
            definition=definitions.main,
            checkpoints=recovery_checkpoints,
            admission=_admission(tmp_path, "recovery"),
            sessions=sessions,
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await provider.shutdown()

    assert recovered.type == "completed"
    assert len(runtime.opens) == 2
    assert all(isinstance(request.open, NewSession) for request in runtime.opens)
    assert runtime.closed


@pytest.mark.postgres
@pytest.mark.skipif(
    DATABASE_URL is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
async def test_postgres_composition_cold_recovers_crash_after_session_cas(
    tmp_path: Path,
) -> None:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    engine = create_engine(DATABASE_URL)
    state = tmp_path / "runtime"
    state.mkdir(mode=0o700)
    conversation_id = uuid4().int % 900_000_000_000_000_000 + 1
    settings = Settings(
        database_url=SecretStr(DATABASE_URL),
        discord=DiscordSettings(
            bot_token=SecretStr("qualification-placeholder"),
            owner_user_id=1,
            guild_id=2,
            channel_id=conversation_id,
        ),
        owner_timezone="UTC",
        codex_profile_key="jarvis-test",
        codex_model="gpt-5.4",
        codex_state_root=tmp_path,
        runtime_state_directory=state,
    )
    admission_limits = RollingAdmissionLimits()
    RollingAdmissionPort.initialize(settings.admission_journal_path, admission_limits)
    definitions = build_slice1_definitions(
        profile_key=settings.codex_profile_key,
        model=settings.codex_model,
        owner_timezone=settings.owner_timezone,
    )
    references = AtomicSessionRefPort(
        settings.session_reference_path,
        max_generations=32,
    )
    crash_store = _CrashOnFirstSettlementStore(engine)
    inserted = await crash_store.insert_waking(
        role="owner",
        text="Recover this synthetic effect-free turn.",
        source="qualification",
        source_conversation_id=str(conversation_id),
        source_message_id=f"qualification-{uuid4()}",
        created_at=datetime.now(UTC),
    )
    history = PostgresCanonicalHistory(engine)

    first_runtime = _Runtime([{"type": "say", "text": "speculative answer"}])
    first_provider = CodexProvider(
        cast(AgentRuntime, first_runtime),
        cwd_parent=tmp_path,
        cache_continuing=False,
    )
    first_bundle = KernelRuntime(
        cast(AgentRuntime, first_runtime),
        first_provider,
        SessionCoordinator(first_provider, references),
        references,
    )
    try:
        with pytest.raises(_Crash):
            await Slice1ThreadRunner(
                settings=settings,
                store=crash_store,
                admission=RollingAdmissionPort(
                    settings.admission_journal_path,
                    admission_limits,
                ),
                kernel_runtime=first_bundle,
                definitions=definitions,
                history=history,
            ).run(CancellationToken())
    finally:
        await first_provider.shutdown()

    speculative = await references.load(
        ThreadId(str(conversation_id)),
        definitions.main.fingerprint,
    )
    assert speculative is not None
    async with engine.connect() as connection:
        attempt, processed_at = (
            await connection.execute(
                select(
                    message.c.processing_attempts,
                    message.c.processed_at,
                ).where(message.c.id == inserted.message.id)
            )
        ).one()
    assert attempt == 1
    assert processed_at is None

    second_runtime = _Runtime([{"type": "say", "text": "recovered answer"}])
    second_provider = CodexProvider(
        cast(AgentRuntime, second_runtime),
        cwd_parent=tmp_path,
        cache_continuing=False,
    )
    second_bundle = KernelRuntime(
        cast(AgentRuntime, second_runtime),
        second_provider,
        SessionCoordinator(second_provider, references),
        references,
    )
    store = MessageStore(engine)
    try:
        recovered = await Slice1ThreadRunner(
            settings=settings,
            store=store,
            admission=RollingAdmissionPort(
                settings.admission_journal_path,
                admission_limits,
            ),
            kernel_runtime=second_bundle,
            definitions=definitions,
            history=history,
        ).run(CancellationToken())
    finally:
        await second_provider.shutdown()

    assert isinstance(recovered, ThreadCompleted)
    assert isinstance(second_runtime.opens[0].open, NewSession)
    async with engine.connect() as connection:
        attempt, processed_at, trace = (
            await connection.execute(
                select(
                    message.c.processing_attempts,
                    message.c.processed_at,
                    message.c.trace,
                ).where(message.c.id == inserted.message.id)
            )
        ).one()
    assert attempt == 2
    assert processed_at is not None
    assert "settlement" in trace
    pending = await store.pending_delivery(
        source_conversation_id=str(conversation_id),
        limit=10,
    )
    assert len(pending) == 1
    assert crash_store.settlement_calls == 1
    await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(
    DATABASE_URL is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
async def test_postgres_claim_parks_post_preflight_admission_inconsistency(
    tmp_path: Path,
) -> None:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    engine = create_engine(DATABASE_URL)
    state = tmp_path / "park-runtime"
    state.mkdir(mode=0o700)
    conversation_id = uuid4().int % 900_000_000_000_000_000 + 1
    settings = Settings(
        database_url=SecretStr(DATABASE_URL),
        discord=DiscordSettings(
            bot_token=SecretStr("qualification-placeholder"),
            owner_user_id=1,
            guild_id=2,
            channel_id=conversation_id,
        ),
        owner_timezone="UTC",
        codex_profile_key="jarvis-test",
        codex_model="gpt-5.4",
        codex_state_root=tmp_path,
        runtime_state_directory=state,
    )
    limits = RollingAdmissionLimits()
    RollingAdmissionPort.initialize(settings.admission_journal_path, limits)
    definitions = build_slice1_definitions(
        profile_key=settings.codex_profile_key,
        model=settings.codex_model,
        owner_timezone=settings.owner_timezone,
    )
    store = MessageStore(engine)
    inserted = await store.insert_waking(
        role="owner",
        text="Synthetic admission consistency input.",
        source="qualification",
        source_conversation_id=str(conversation_id),
        source_message_id=f"qualification-{uuid4()}",
        created_at=datetime.now(UTC),
    )
    references = AtomicSessionRefPort(
        settings.session_reference_path,
        max_generations=4,
    )
    runtime = _Runtime([])
    provider = CodexProvider(
        cast(AgentRuntime, runtime),
        cwd_parent=tmp_path,
        cache_continuing=False,
    )
    bundle = KernelRuntime(
        cast(AgentRuntime, runtime),
        provider,
        SessionCoordinator(provider, references),
        references,
    )
    admission = _ReserveStateDefect(
        settings.admission_journal_path,
        limits,
    )
    try:
        outcome = await Slice1ThreadRunner(
            settings=settings,
            store=store,
            admission=admission,
            kernel_runtime=bundle,
            definitions=definitions,
            history=PostgresCanonicalHistory(engine),
        ).run(CancellationToken())

        assert isinstance(outcome, ThreadStopped)
        assert outcome.type is ThreadStopKind.configuration_error
        assert outcome.metrics.provider_turns == 0
        assert runtime.opens == []
        async with engine.connect() as connection:
            attempts, processed_at, parked_at, trace = (
                await connection.execute(
                    select(
                        message.c.processing_attempts,
                        message.c.processed_at,
                        message.c.processing_parked_at,
                        message.c.trace,
                    ).where(message.c.id == inserted.message.id)
                )
            ).one()
        assert attempts == 1
        assert processed_at is None
        assert parked_at is not None
        assert trace["parking"]["reason_code"] == "admission_state_defect"

        restarted_runtime = _Runtime([])
        restarted_provider = CodexProvider(
            cast(AgentRuntime, restarted_runtime),
            cwd_parent=tmp_path,
            cache_continuing=False,
        )
        restarted_bundle = KernelRuntime(
            cast(AgentRuntime, restarted_runtime),
            restarted_provider,
            SessionCoordinator(restarted_provider, references),
            references,
        )
        try:
            with pytest.raises(
                CheckpointStateDefect,
                match="cognitive circuit is parked",
            ):
                await Slice1ThreadRunner(
                    settings=settings,
                    store=store,
                    admission=RollingAdmissionPort(
                        settings.admission_journal_path,
                        limits,
                    ),
                    kernel_runtime=restarted_bundle,
                    definitions=definitions,
                    history=PostgresCanonicalHistory(engine),
                ).run(CancellationToken())
        finally:
            await restarted_provider.shutdown()
        assert restarted_runtime.opens == []
    finally:
        await provider.shutdown()
        async with engine.connect() as connection:
            parked_at = await connection.scalar(
                select(message.c.processing_parked_at).where(
                    message.c.id == inserted.message.id
                )
            )
        if parked_at is not None:
            await store.clear_parked(message_ids=(inserted.message.id,))
        assert not await store.circuit_is_open()
        await engine.dispose()


async def test_mid_loop_append_is_admitted_and_final_settlement_race_stays_next(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    first = _claim(definitions.plans["main"], name="append", text="first")
    appended = _input("input-appended", "second")
    checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(first),))
    checkpoints.queue_poll(
        first.claim_id,
        AppendInputs((appended,), Checkpoint("checkpoint-appended"), AS_OF),
    )
    runtime = _Runtime([{"type": "say", "text": "both"}])
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    try:
        outcome = await _run(
            run_id="run-append",
            definition=definitions.main,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "append"),
            sessions=SessionCoordinator(
                provider,
                AtomicSessionRefPort(
                    tmp_path / "append-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await provider.shutdown()

    assert outcome.type == "completed"
    assert checkpoints.settlements[0].through_checkpoint == Checkpoint(
        "checkpoint-appended"
    )
    rendered = "\n".join(
        part.text for part in runtime.turns[0].input if isinstance(part, TextContent)
    )
    assert rendered.count("first") == 1
    assert rendered.count("second") == 1

    race_claim = _claim(definitions.plans["main"], name="race")
    racing = _input("input-racing", "late follow-up")
    race_checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(race_claim),))
    race_checkpoints.queue_poll(
        race_claim.claim_id,
        NoNewInput(),
        # Initial turn poll, then an append observed only at the final settlement poll.
        # The old answer remains valid; the durable adapter reports more work next.
        AppendInputs((racing,), Checkpoint("checkpoint-racing"), AS_OF),
    )
    race_checkpoints.settle_results.append(SettleMoreInput())
    race_runtime = _Runtime([{"type": "say", "text": "answer before race"}])
    race_provider = CodexProvider(cast(AgentRuntime, race_runtime), cwd_parent=tmp_path)
    try:
        raced = await _run(
            run_id="run-race",
            definition=definitions.main,
            checkpoints=race_checkpoints,
            admission=_admission(tmp_path, "race"),
            sessions=SessionCoordinator(
                race_provider,
                AtomicSessionRefPort(
                    tmp_path / "race-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await race_provider.shutdown()

    assert raced.type == "completed"
    assert (
        race_checkpoints.settlements[0].through_checkpoint
        == race_claim.through_checkpoint
    )


async def test_attempt_ceiling_and_plan_budget_defect_are_deterministic(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    poison = _claim(definitions.plans["main"], name="attempt", attempt=4)
    poison_checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(poison),))
    runtime = _Runtime([])
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    try:
        stopped = await _run(
            run_id="run-attempt",
            definition=definitions.main,
            checkpoints=poison_checkpoints,
            admission=_admission(tmp_path, "attempt"),
            sessions=SessionCoordinator(
                provider,
                AtomicSessionRefPort(
                    tmp_path / "attempt-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await provider.shutdown()

    assert stopped.type is ThreadStopKind.provider_error
    assert stopped.metrics.input_consumed is True
    assert poison_checkpoints.settlements[0].conclusion == StoppedConclusion(
        StopReason.provider_error
    )

    defective = _claim(definitions.plans["main"], name="budget")
    defect_checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(defective),))
    defect_runtime = _Runtime([])
    defect_provider = CodexProvider(
        cast(AgentRuntime, defect_runtime), cwd_parent=tmp_path
    )
    try:
        parked = await _run(
            run_id="run-budget-defect",
            definition=definitions.main,
            checkpoints=defect_checkpoints,
            admission=_admission(tmp_path, "budget"),
            sessions=SessionCoordinator(
                defect_provider,
                AtomicSessionRefPort(
                    tmp_path / "budget-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
            budget_factory=_WrongBudgetFactory(),
        )
    finally:
        await defect_provider.shutdown()

    assert parked.type is ThreadStopKind.configuration_error
    assert parked.metrics.input_consumed is False
    assert defect_checkpoints.park_reasons == [
        (defective.claim_id, "invalid frozen tool budget")
    ]
    assert runtime.opens == []
    assert defect_runtime.opens == []


async def test_compatibility_change_rotates_without_resuming_old_session(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    old = definitions.main
    rotated = replace(
        old,
        session_compatibility_revision=f"{old.session_compatibility_revision}-rotated",
    )
    references = AtomicSessionRefPort(
        tmp_path / "rotation-session.json", max_generations=32
    )
    first = _claim(definitions.plans["main"], name="old")
    second = _claim(definitions.plans["main"], name="new")
    checkpoints = InMemoryInputCheckpointPort(
        (ClaimAcquired(first), ClaimAcquired(second))
    )
    runtime = _Runtime(
        [
            {"type": "say", "text": "old"},
            {"type": "say", "text": "new"},
        ]
    )
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    sessions = SessionCoordinator(provider, references)
    try:
        await _run(
            run_id="run-old",
            definition=old,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "old"),
            sessions=sessions,
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
        await _run(
            run_id="run-new",
            definition=rotated,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "new"),
            sessions=sessions,
            context_source=JarvisContextSource(THREAD_ID, _History()),
        )
    finally:
        await provider.shutdown()

    assert old.fingerprint != rotated.fingerprint
    assert all(isinstance(request.open, NewSession) for request in runtime.opens)


async def test_cooperative_deadline_allows_one_finite_provider_turn_overshoot(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    definition = replace(
        definitions.main,
        limits=replace(SLICE1_KERNEL_LIMITS, max_cooperative_seconds=1.0),
    )
    clock = _Clock()
    runtime = _Runtime(
        [{"type": "say", "text": "too late"}],
        on_stream=lambda: setattr(clock, "value", 2.0),
    )
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    claim = _claim(definitions.plans["main"], name="deadline")
    checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(claim),))
    try:
        outcome = await _run(
            run_id="run-deadline",
            definition=definition,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "deadline"),
            sessions=SessionCoordinator(
                provider,
                AtomicSessionRefPort(
                    tmp_path / "deadline-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, _History()),
            clock=clock,
        )
    finally:
        await provider.shutdown()

    assert outcome.type is ThreadStopKind.budget_exhausted
    assert outcome.metrics.provider_turns == 1
    assert outcome.metrics.duration_seconds == 2.0
    assert runtime.turns[0].timeout_seconds == 1.0
    assert checkpoints.settlements[0].conclusion == StoppedConclusion(
        StopReason.budget_exhausted
    )
    state = json.loads(
        (tmp_path / "deadline-admission.json").read_text(encoding="utf-8")
    )
    assert state["reservations"][0]["actual_turns"] == 1


async def test_exhausted_cooperative_deadline_stops_at_next_safe_boundary(
    tmp_path: Path,
) -> None:
    definitions = _definitions()
    definition = replace(
        definitions.main,
        limits=replace(SLICE1_KERNEL_LIMITS, max_cooperative_seconds=1.0),
    )
    clock = _Clock()

    class SlowHistory(_History):
        async def completed_history(
            self,
            thread_id: ThreadId,
            *,
            exclude_input_ids: tuple[InputId, ...],
            limit: int,
        ) -> tuple[CanonicalMessage, ...]:
            result = await super().completed_history(
                thread_id,
                exclude_input_ids=exclude_input_ids,
                limit=limit,
            )
            clock.value = 2.0
            return result

    runtime = _Runtime([])
    provider = CodexProvider(cast(AgentRuntime, runtime), cwd_parent=tmp_path)
    claim = _claim(definitions.plans["main"], name="already-exhausted")
    checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(claim),))
    try:
        outcome = await _run(
            run_id="run-already-exhausted",
            definition=definition,
            checkpoints=checkpoints,
            admission=_admission(tmp_path, "already-exhausted"),
            sessions=SessionCoordinator(
                provider,
                AtomicSessionRefPort(
                    tmp_path / "already-exhausted-session.json", max_generations=32
                ),
            ),
            context_source=JarvisContextSource(THREAD_ID, SlowHistory()),
            clock=clock,
        )
    finally:
        await provider.shutdown()

    assert outcome.type is ThreadStopKind.budget_exhausted
    assert outcome.metrics.provider_turns == 0
    assert outcome.metrics.duration_seconds == 2.0
    assert runtime.turns == []

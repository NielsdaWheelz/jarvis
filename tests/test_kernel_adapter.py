from __future__ import annotations

import stat
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimAcquired,
    ClaimId,
    HostInput,
    InMemoryInputCheckpointPort,
    InputClaim,
    InputId,
    OwnerToken,
    RunId,
    ThreadCompleted,
    ThreadId,
    ToolDispatchPort,
    run_thread,
)
from llm_tools import PromptSection, PromptSectionKind, PromptSections, PromptText
from provider_runtime.agent_runtime import (
    AgentEvent,
    AgentRuntimeConfig,
    AgentSession,
    AgentSessionRef,
    AgentSessionRequest,
    AgentTerminal,
    CodexNativeOptions,
    TurnRequest,
    freeze_json_object,
)
from provider_runtime.types import Absent, CancelSignal

from jarvis.admission import (
    ExactToolBudgetFactory,
    RollingAdmissionLimits,
    RollingAdmissionPort,
)
from jarvis.context import CanonicalMessage, JarvisContextSource
from jarvis.definitions import build_slice1_definitions, verify_runtime_dependencies
from jarvis.kernel import EmptySlice1Dispatcher, build_kernel_runtime

AS_OF = datetime(2026, 9, 3, 12, tzinfo=UTC)


class _EmptyHistory:
    async def completed_history(
        self,
        thread_id: ThreadId,
        *,
        exclude_input_ids: tuple[InputId, ...],
        limit: int,
    ) -> tuple[CanonicalMessage, ...]:
        del thread_id, exclude_input_ids, limit
        return ()


class _RecordingRuntime:
    def __init__(self, config: AgentRuntimeConfig) -> None:
        self.config = config
        self.requests: list[AgentSessionRequest] = []
        self.cwd_checks: list[tuple[bool, bool, int]] = []
        self.closed = False

    async def open_session(self, request: AgentSessionRequest) -> AgentSession:
        self.requests.append(request)
        cwd = Path(request.cwd)
        self.cwd_checks.append(
            (
                cwd.is_absolute(),
                list(cwd.iterdir()) == [],
                stat.S_IMODE(cwd.stat().st_mode),
            )
        )
        return AgentSession(
            AgentSessionRef(
                "agent-session-ref.v1",
                "codex",
                "sdk",
                "contained-session",
                request.auth.profile_key,
                "1" * 64,
                "2" * 64,
            )
        )

    async def stream_turn(
        self,
        session: AgentSession,
        request: TurnRequest,
        *,
        approvals: object | None = None,
        cancel: CancelSignal | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        del request, approvals, cancel
        yield AgentTerminal(
            status="succeeded",
            failure=None,
            final_text="untrusted projection",
            session_ref=session.ref,
            structured_output=freeze_json_object(
                {
                    "type": "say",
                    "say": {"text": "contained response"},
                    "call_tool": None,
                    "finish": None,
                }
            ),
            usage=Absent(),
        )

    async def run_turn(self, *_args: object, **_kwargs: object) -> AgentTerminal:
        raise AssertionError("production Jarvis must use stream_turn")

    async def close_session(self, session: AgentSession) -> None:
        del session

    async def close(self) -> None:
        self.closed = True


def test_installed_runtime_dependencies_match_qualified_pins() -> None:
    verify_runtime_dependencies()


async def test_runtime_bundle_uses_production_contained_provider(
    tmp_path: Path,
) -> None:
    provider_state = tmp_path / "provider"
    provider_state.mkdir(mode=0o700)
    cwd_parent = tmp_path / "cwd"
    cwd_parent.mkdir(mode=0o700)
    session_path = tmp_path / "session.json"

    bundle = build_kernel_runtime(
        provider_state_root=provider_state,
        private_cwd_parent=cwd_parent,
        session_ref_path=session_path,
        model="gpt-5.4",
    )
    try:
        assert bundle.runtime.config.state_root_base == provider_state
        assert bundle.runtime.config.max_turn_seconds == 300.0
    finally:
        await bundle.close()


def test_slice1_dispatcher_satisfies_kernel_port() -> None:
    dispatcher: ToolDispatchPort = EmptySlice1Dispatcher()
    assert isinstance(dispatcher, EmptySlice1Dispatcher)


async def test_production_builder_excludes_ambient_credentials_from_real_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinels: list[str] = []
    for name in (
        "JARVIS_DISCORD_BOT_TOKEN",
        "JARVIS_DATABASE_URL",
        "JARVIS_GMAIL_CREDENTIAL",
        "JARVIS_CALENDAR_CREDENTIAL",
        "JARVIS_MAPS_CREDENTIAL",
        "BRAVE_API_KEY",
        "OPENAI_API_KEY",
        "JARVIS_EMBEDDING_CREDENTIAL",
    ):
        sentinel = f"synthetic-{name.lower()}"
        sentinels.append(sentinel)
        monkeypatch.setenv(name, sentinel)

    provider_state = tmp_path / "provider"
    provider_state.mkdir(mode=0o700)
    cwd_parent = tmp_path / "cwd"
    cwd_parent.mkdir(mode=0o700)
    recorded: list[_RecordingRuntime] = []

    def runtime_factory(config: AgentRuntimeConfig) -> _RecordingRuntime:
        runtime = _RecordingRuntime(config)
        recorded.append(runtime)
        return runtime

    monkeypatch.setattr("jarvis.kernel.AgentRuntime", runtime_factory)
    bundle = build_kernel_runtime(
        provider_state_root=provider_state,
        private_cwd_parent=cwd_parent,
        session_ref_path=tmp_path / "session.json",
        model="gpt-5.4",
        verify_dependencies=False,
    )
    definitions = build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.4",
        owner_timezone="UTC",
    )
    plan = definitions.plans["main"]
    sections = PromptSections(
        (
            PromptSection(
                PromptSectionKind("owner_input"),
                (),
                PromptText("synthetic containment input"),
            ),
        )
    )
    claim = InputClaim(
        ClaimId("claim-contained"),
        (HostInput(InputId("input-contained"), sections, AS_OF),),
        Checkpoint("checkpoint-contained"),
        AS_OF,
        plan,
        1,
    )
    checkpoints = InMemoryInputCheckpointPort((ClaimAcquired(claim),))
    admission_limits = RollingAdmissionLimits()
    admission_path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(admission_path, admission_limits)
    discarded: list[AgentSessionRef] = []
    original_discard = bundle.provider.discard_reference

    async def record_discard(
        definition_fingerprint: str,
        ref: AgentSessionRef,
    ) -> None:
        discarded.append(ref)
        await original_discard(definition_fingerprint, ref)

    monkeypatch.setattr(bundle.provider, "discard_reference", record_discard)
    try:
        outcome = await run_thread(
            run_id=RunId("run-contained"),
            thread_id=ThreadId("thread-contained"),
            owner_token=OwnerToken("owner-contained"),
            definition=definitions.main,
            checkpoints=checkpoints,
            admission=RollingAdmissionPort(admission_path, admission_limits),
            sessions=bundle.sessions,
            context_source=JarvisContextSource(
                ThreadId("thread-contained"),
                _EmptyHistory(),
            ),
            dispatcher=EmptySlice1Dispatcher(),
            budget_factory=ExactToolBudgetFactory(),
            cancellation=CancellationToken(),
        )
        stored = await bundle.references.load_for_discard(
            ThreadId("thread-contained"),
            definitions.main.fingerprint,
        )
        assert stored is not None
        await bundle.discard_recovered_session_reference(
            ThreadId("thread-contained"),
            definitions.main,
        )
        assert discarded == [stored.ref]
        assert (
            await bundle.references.load_for_discard(
                ThreadId("thread-contained"),
                definitions.main.fingerprint,
            )
            is None
        )
    finally:
        await bundle.close()

    assert isinstance(outcome, ThreadCompleted)
    assert len(recorded) == 1
    request = recorded[0].requests[0]
    assert all(sentinel not in repr(request) for sentinel in sentinels)
    assert request.auth.kind == "local_account"
    assert request.policy.filesystem == "read_only"
    assert request.policy.network == "disabled"
    assert request.policy.approval == "deny"
    assert request.policy.environment == ()
    assert request.additional_dirs == ()
    assert request.mcp_servers == ()
    assert isinstance(request.native, CodexNativeOptions)
    assert request.native.web_search is False
    assert request.native.builtin_tools == "disabled"
    assert recorded[0].cwd_checks == [(True, True, stat.S_IRUSR | stat.S_IXUSR)]
    assert recorded[0].closed is True

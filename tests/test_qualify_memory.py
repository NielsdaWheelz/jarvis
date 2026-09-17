from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import pytest
from llm_agent_kernel import (
    AdmissionGranted,
    AdmissionRequest,
    AdmissionUsage,
    ProviderUsage,
    RunId,
    SessionMode,
    StructuredOutput,
    ThreadId,
    require_host_plan,
)
from llm_tools import PromptSections, ToolEffect, ToolId
from provider_fixture import frozen_provider
from provider_runtime.agent_runtime import (
    AgentFailure,
    AgentQuotaExhausted,
    AgentSessionRef,
    AgentTerminal,
)
from provider_runtime.errors import CredentialRejected
from pydantic import SecretStr

from jarvis.admission import RollingAdmissionPort
from jarvis.context import RecallEvidence
from jarvis.definitions import RECALLER_KERNEL_LIMITS, REMEMBERER_KERNEL_LIMITS
from jarvis.memory import MemoryIdentity, MemoryTableKind
from jarvis.recall_evaluation import RecallCase, load_recall_set
from jarvis.settings import EMBEDDING_DIMENSION

ROOT = Path(__file__).resolve().parents[1]
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_memory.py"))
_fixture_insert_values = _QUALIFIER["fixture_insert_values"]
_observe_recall_cases = _QUALIFIER["observe_recall_cases"]
_populate_fixture_embeddings = _QUALIFIER["populate_fixture_embeddings"]
_verify_embedding_credential_denies_generation = _QUALIFIER[
    "verify_embedding_credential_denies_generation"
]
_verified_zero_memory_result = _QUALIFIER["verified_zero_memory_result"]
_Arguments = _QUALIFIER["Arguments"]
_compose_memory_catalog = _QUALIFIER["compose_memory_catalog"]
_build_recaller = _QUALIFIER["build_recaller"]
_build_rememberer = _QUALIFIER["build_rememberer"]
_NoopRecallTrace = _QUALIFIER["_NoopRecallTrace"]
_ProductionRecallRunner = _QUALIFIER["_ProductionRecallRunner"]
_QualificationProvider = _QUALIFIER["QualificationProvider"]
_RecallCaseFailure = cast("type[Exception]", _QUALIFIER["RecallCaseFailure"])
_failure_evidence = _QUALIFIER["failure_evidence"]
_qualification_failure = _QUALIFIER["qualification_failure"]
_QUALIFIER_GLOBALS = _verify_embedding_credential_denies_generation.__globals__
_ProbeCheckFailed = cast("type[Exception]", _QUALIFIER["ProbeCheckFailed"])

_qualification_admission_limits = _QUALIFIER["qualification_admission_limits"]
_MEMORY_PROBE_ROOT_TURNS = _QUALIFIER["MEMORY_PROBE_ROOT_TURNS"]
_MEMORY_PROBE_ROOT_INPUT_TOKENS = _QUALIFIER["MEMORY_PROBE_ROOT_INPUT_TOKENS"]
_MEMORY_PROBE_ROOT_OUTPUT_TOKENS = _QUALIFIER["MEMORY_PROBE_ROOT_OUTPUT_TOKENS"]


@dataclass(frozen=True, slots=True)
class _Stored:
    identity: MemoryIdentity
    text: str


class _Store:
    def __init__(self, fixtures: tuple[Any, ...]) -> None:
        self.memories = tuple(
            _Stored(MemoryIdentity(item.table_kind, item.id), item.text)
            for item in fixtures
        )
        self.updates: list[tuple[MemoryIdentity, tuple[float, ...]]] = []

    async def open_memories(
        self,
        *,
        identities: tuple[MemoryIdentity, ...],
        maximum_rows: int,
    ) -> tuple[_Stored, ...]:
        assert maximum_rows == len(identities)
        return self.memories

    async def update_embedding(
        self,
        *,
        identity: MemoryIdentity,
        embedding: tuple[float, ...],
    ) -> _Stored:
        self.updates.append((identity, embedding))
        return next(item for item in self.memories if item.identity == identity)


class _Embedder:
    def __init__(self, *, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension
        self.seen: tuple[str, ...] = ()

    async def embed(self, inputs: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.seen = inputs
        return tuple(
            (float(index + 1),) * self.dimension for index, _ in enumerate(inputs)
        )


class _RecallRunner:
    async def observe(self, case: RecallCase) -> RecallEvidence:
        selected = tuple(
            MemoryIdentity(_table_kind(item), item) for item in case.must_select_ids
        )
        opened = tuple(
            MemoryIdentity(_table_kind(item), item) for item in case.must_open_ids
        )
        return RecallEvidence(
            candidate_identities=selected,
            selected_identities=selected,
            opened_identities=opened,
            search_calls=case.min_search_calls,
        )


def test_memory_roles_require_only_the_memory_catalog() -> None:
    catalog = _compose_memory_catalog(object(), _Embedder())
    assert tuple(catalog.tool_ids) == (ToolId("memory.open"), ToolId("memory.search"))
    for build_role in (_build_recaller, _build_rememberer):
        definition, plan = build_role(
            catalog=catalog,
            provider=frozen_provider(),
            owner_timezone="UTC",
        )
        assert definition.session_mode is SessionMode.isolated
        assert isinstance(definition.output_contract, StructuredOutput)
        assert tuple(plan.profile.grants) == catalog.tool_ids
        assert all(
            plan.catalog_view.spec(tool_id).effect is ToolEffect.Read
            for tool_id in plan.profile.grants
        )
        require_host_plan(plan, definition.maximum_profile)
    assert catalog.binding(ToolId("memory.search")).implementation_revision == (
        "jarvis-memory-search-v1"
    )


@pytest.mark.parametrize("timezone", ("UTC", "America/Los_Angeles", "not-a-zone"))
def test_memory_qualification_requires_an_installed_owner_timezone(
    tmp_path: Path, timezone: str
) -> None:
    values = {
        "model": "gpt-5.6-terra",
        "profile": "personal",
        "codex_host_config_path": tmp_path / "codex-profiles.json",
        "runtime_state_directory": tmp_path / "runtime",
        "database_url": "postgresql://synthetic",
        "embedding_api_key": SecretStr("synthetic-embedding-key"),
        "owner_timezone": timezone,
        "reasoning_effort": "high",
    }
    if timezone == "not-a-zone":
        with pytest.raises(ValueError, match="installed IANA timezone"):
            _Arguments(**values)
    else:
        assert _Arguments(**values).owner_timezone == timezone


async def test_noncompleted_recaller_reports_only_validated_terminal_reason() -> None:
    trace = _NoopRecallTrace()

    class _StoppedRecaller:
        last_evidence = None

        async def recall(self, *args: object, **kwargs: object) -> PromptSections:
            del args, kwargs
            trace.terminal_outcome = "protocol_error"
            return PromptSections(())

    _, cases = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )
    with pytest.raises(_ProbeCheckFailed) as failure:
        await _ProductionRecallRunner(_StoppedRecaller(), trace).observe(cases[0])

    assert str(failure.value) == "recaller_terminal_protocol_error"
    trace.terminal_outcome = "private-content-must-not-be-echoed"
    assert trace.failure_reason() == "recaller_terminal_invalid"
    assert "private-content" not in trace.failure_reason()


def test_missing_search_is_a_distinct_noncompleted_recaller_reason() -> None:
    trace = _NoopRecallTrace()
    trace.terminal_outcome = "missing_search"

    assert not trace.completed()
    assert trace.failure_reason() == "recaller_terminal_missing_search"


async def test_recall_failure_reports_only_frozen_case_progress() -> None:
    _, cases = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )

    class _FailSecond:
        def __init__(self) -> None:
            self.calls = 0

        async def observe(self, case: RecallCase) -> RecallEvidence:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("private query, memory, IDs, and payload")
            return await _RecallRunner().observe(case)

    with pytest.raises(_RecallCaseFailure) as stopped:
        await _observe_recall_cases(cases[:2], _FailSecond())

    failure = _qualification_failure("recall", stopped.value)
    evidence = _failure_evidence(failure)
    assert evidence == {
        "case_id": "R02",
        "completed_case_count": 1,
        "provider_terminal": None,
        "reason_code": "unexpected_exception",
        "stage": "recall",
        "type": "RuntimeError",
    }
    assert "private" not in repr(evidence)
    assert set(evidence) == {
        "case_id",
        "completed_case_count",
        "provider_terminal",
        "reason_code",
        "stage",
        "type",
    }


def test_recall_progress_preserves_only_known_probe_reason() -> None:
    stopped = _QUALIFIER["RecallCaseFailure"](
        case_id="R17",
        completed_case_count=16,
        cause=_QUALIFIER["ProbeCheckFailed"](
            "recaller_terminal_provider_error",
            provider_terminal="backend_failed",
        ),
    )

    assert _failure_evidence(_qualification_failure("recall", stopped)) == {
        "case_id": "R17",
        "completed_case_count": 16,
        "provider_terminal": "backend_failed",
        "reason_code": "recaller_terminal_provider_error",
        "stage": "recall",
        "type": "ProbeCheckFailed",
    }


@pytest.mark.parametrize(
    ("status", "failure", "expected"),
    [
        ("failed", AgentFailure("backend_failed"), "backend_failed"),
        (
            "failed",
            AgentFailure("output_schema_violation"),
            "output_schema_violation",
        ),
        ("failed", AgentQuotaExhausted(), "quota_exhausted"),
        ("cancelled", None, "cancelled"),
        ("succeeded", None, "succeeded"),
    ],
)
async def test_qualification_provider_retains_only_closed_terminal_code(
    status: Any,
    failure: Any,
    expected: str,
) -> None:
    terminal = AgentTerminal(
        status=status,
        failure=failure,
        final_text="private provider prose must not be retained",
        session_ref=AgentSessionRef(
            "agent-session-ref.v1",
            "codex",
            "sdk",
            "private-native-session-id",
            "synthetic-profile",
            "0" * 64,
            "1" * 64,
        ),
        diagnostics=("private diagnostic",),
    )

    class _Inner:
        async def run_observed_turn(
            self, *args: object, **kwargs: object
        ) -> AgentTerminal:
            del args, kwargs
            return terminal

    provider = _QualificationProvider(cast("Any", _Inner()))
    returned = await provider.run_observed_turn(
        cast("Any", object()),
        (),
        cast("Any", object()),
    )

    assert returned is terminal
    assert provider.terminal_code == expected
    assert "private" not in provider.terminal_code
    provider.reset_terminal()
    assert provider.terminal_code == "not_observed"


async def test_qualification_provider_does_not_retain_exception_text() -> None:
    class _Inner:
        async def run_observed_turn(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("private provider prose and session identity")

    provider = _QualificationProvider(cast("Any", _Inner()))
    with pytest.raises(RuntimeError, match="private provider prose"):
        await provider.run_observed_turn(
            cast("Any", object()),
            (),
            cast("Any", object()),
        )

    assert provider.terminal_code == "not_observed"
    assert "private" not in provider.terminal_code


def _table_kind(identity: UUID) -> MemoryTableKind:
    return (
        "memory_summary"
        if identity == UUID("10000000-0000-4000-8000-000000000001")
        else "memory_log"
    )


def test_fixture_seed_values_preserve_exact_owner_approved_corpus() -> None:
    fixtures, _ = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )

    raw, summaries = _fixture_insert_values(fixtures)

    assert len(raw) == 12
    assert len(summaries) == 1
    assert summaries[0] == {
        "id": fixtures[-1].id,
        "text": fixtures[-1].text,
        "source_memory_ids": list(fixtures[-1].source_memory_ids),
    }
    assert str(summaries[0]["id"]) == "10000000-0000-4000-8000-000000000001"
    assert tuple(item["text"] for item in (*raw, *summaries)) == tuple(
        item.text for item in fixtures
    )


async def test_fixture_embedding_uses_exact_text_and_updates_every_identity() -> None:
    fixtures, _ = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )
    store = _Store(fixtures)
    embedder = _Embedder()

    result = await _populate_fixture_embeddings(store, embedder, fixtures)

    assert embedder.seen == tuple(item.text for item in fixtures)
    assert tuple(item[0] for item in store.updates) == tuple(
        MemoryIdentity(item.table_kind, item.id) for item in fixtures
    )
    assert {len(item[1]) for item in store.updates} == {EMBEDDING_DIMENSION}
    assert result == {
        "dimension": 1536,
        "embedded": 13,
        "model": "text-embedding-3-small",
        "status": "passed",
    }


async def test_invalid_embedding_shape_commits_no_derived_updates() -> None:
    fixtures, _ = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )
    store = _Store(fixtures)

    with pytest.raises(_ProbeCheckFailed):
        await _populate_fixture_embeddings(store, _Embedder(dimension=2), fixtures)

    assert store.updates == []


async def test_recall_observations_track_only_stable_identity_evidence() -> None:
    _, cases = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )

    observations, evidence = await _observe_recall_cases(cases, _RecallRunner())

    assert len(observations) == 17
    assert observations[15].search_calls == 2
    assert evidence[0] == {
        "candidate_memory_ids": [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "table_kind": "memory_log",
            }
        ],
        "id": "R01",
        "opened_memory_ids": [],
        "search_calls": 1,
        "selected_memory_ids": [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "table_kind": "memory_log",
            }
        ],
    }
    serialized = repr(evidence)
    assert cases[0].query not in serialized
    assert "prompt" not in serialized
    assert "session" not in serialized
    assert "run_id" not in serialized
    assert evidence[12]["selected_memory_ids"] == [
        {
            "id": "10000000-0000-4000-8000-000000000001",
            "table_kind": "memory_summary",
        }
    ]


async def test_generation_denial_accepts_only_credential_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-live-qualification-secret-value"

    class _DeniedRuntime:
        def __init__(
            self, credentials: object, *, retry: object, http_client: object
        ) -> None:
            del credentials, retry, http_client

        async def generate(self, intent: object) -> None:
            del intent
            raise CredentialRejected(message="qualification credential rejected")

    monkeypatch.setitem(_QUALIFIER_GLOBALS, "ProviderRuntime", _DeniedRuntime)

    await _verify_embedding_credential_denies_generation(SecretStr(secret))


async def test_generation_success_fails_without_exposing_provider_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnsafeRuntime:
        def __init__(
            self, credentials: object, *, retry: object, http_client: object
        ) -> None:
            del credentials, retry, http_client

        async def generate(self, intent: object) -> object:
            del intent
            return object()

    monkeypatch.setitem(_QUALIFIER_GLOBALS, "ProviderRuntime", _UnsafeRuntime)

    with pytest.raises(_ProbeCheckFailed) as failure:
        await _verify_embedding_credential_denies_generation(
            SecretStr("sk-live-do-not-emit-this-secret")
        )

    assert str(failure.value) == "embedding_credential_generated_content"
    assert "sk-live" not in str(failure.value)


def test_zero_memory_rememberer_evidence_is_bounded_and_content_free() -> None:
    result = _verified_zero_memory_result(
        before=(12, 1, 0),
        after=(12, 1, 0),
        remembered_at=object(),
        trace={
            "settlement": {"private": "not emitted"},
            "rememberer": {
                "created_memory_ids": [],
                "run": {
                    "duration_ms": 250,
                    "input_tokens": 40,
                    "output_tokens": 8,
                    "provider_turns": 1,
                    "run_id": "must-not-be-emitted",
                    "terminal_outcome": "completed",
                },
            },
        },
    )

    assert result == {
        "action_rows_added": 0,
        "memory_log_rows_added": 0,
        "memory_summary_rows_added": 0,
        "status": "passed",
        "usage": {
            "duration_ms": 250,
            "input_tokens": 40,
            "output_tokens": 8,
            "provider_turns": 1,
        },
        "watermark_advanced": True,
    }
    assert "private" not in repr(result)
    assert "run_id" not in repr(result)


def test_zero_memory_rememberer_rejects_any_durable_row_addition() -> None:
    with pytest.raises(_ProbeCheckFailed) as failure:
        _verified_zero_memory_result(
            before=(12, 1, 0),
            after=(13, 1, 0),
            remembered_at=object(),
            trace={
                "rememberer": {
                    "created_memory_ids": ["00000000-0000-4000-8000-000000000001"],
                    "run": {"terminal_outcome": "completed"},
                }
            },
        )

    assert str(failure.value) == "rememberer_zero_memory_changed_durable_rows"


def test_qualification_capacity_reserves_one_recaller_per_maximum_owner_input() -> None:
    selected = _qualification_admission_limits(20)
    assert selected.serial_child_turns == 200
    assert selected.serial_child_input_tokens == 3_855_360
    assert selected.serial_child_output_tokens == 483_840


async def test_qualification_capacity_fits_worst_foreground_then_background_rememberer(
    tmp_path: Path,
) -> None:
    maximum_owner_inputs = 20
    selected = _qualification_admission_limits(maximum_owner_inputs)
    path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(path, selected)
    port = RollingAdmissionPort(
        path,
        selected,
        clock=lambda: datetime(2026, 9, 4, tzinfo=UTC),
    )
    foreground = await port.reserve(
        AdmissionRequest(
            RunId("foreground"),
            ThreadId("channel"),
            1,
            _MEMORY_PROBE_ROOT_TURNS,
            _MEMORY_PROBE_ROOT_INPUT_TOKENS,
            _MEMORY_PROBE_ROOT_OUTPUT_TOKENS,
        )
    )
    assert isinstance(foreground, AdmissionGranted)
    recall = RECALLER_KERNEL_LIMITS
    for index in range(maximum_owner_inputs):
        child = await port.reserve(
            AdmissionRequest(
                RunId(f"recaller-{index}"),
                None,
                None,
                recall.max_provider_turns,
                recall.max_provider_input_tokens,
                recall.max_provider_output_tokens,
                foreground.token,
            )
        )
        assert isinstance(child, AdmissionGranted)
        await port.settle(
            child.token,
            AdmissionUsage(
                recall.max_provider_turns,
                ProviderUsage(input_tokens=None, output_tokens=None),
                60.0,
            ),
        )
    await port.settle(
        foreground.token,
        AdmissionUsage(
            _MEMORY_PROBE_ROOT_TURNS,
            ProviderUsage(input_tokens=None, output_tokens=None),
            300.0,
        ),
    )

    remember = REMEMBERER_KERNEL_LIMITS
    background = await port.reserve(
        AdmissionRequest(
            RunId("rememberer"),
            None,
            None,
            remember.max_provider_turns,
            remember.max_provider_input_tokens,
            remember.max_provider_output_tokens,
        )
    )
    assert isinstance(background, AdmissionGranted)
    assert background.token.reserved_turns == remember.max_provider_turns
    assert background.token.reserved_input_tokens == (
        remember.max_provider_input_tokens + selected.root_input_token_overshoot
    )
    assert background.token.reserved_output_tokens == (
        remember.max_provider_output_tokens + selected.root_output_token_overshoot
    )

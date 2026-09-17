#!/usr/bin/env python3
"""Run current memory-role qualification with sanitized output."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from llm_agent_kernel import (
    AdmissionGranted,
    AdmissionRequest,
    AdmissionUsage,
    AgentDefinition,
    CancellationToken,
    HostInput,
    InputId,
    ProviderSessionLease,
    ProviderSessionPort,
    ProviderUsage,
    RunId,
    ThreadId,
    ThreadStopKind,
)
from llm_tools import (
    FrozenToolPlan,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
)
from provider_runtime import (
    Credentials,
    GenerateIntent,
    Present,
    PromptBlock,
    ProviderRuntime,
    ProviderTarget,
    TextOutput,
    UserMessage,
)
from provider_runtime.agent_runtime import (
    AgentFailure,
    AgentQuotaExhausted,
    AgentSessionRef,
    AgentTerminal,
    ContentPart,
)
from provider_runtime.errors import CredentialRejected
from provider_runtime.types import CancelSignal, RetryPolicy
from pydantic import SecretStr
from sqlalchemy import func, insert, select, text

from jarvis.admission import (
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
    slice3_admission_limits,
)
from jarvis.codex_config import CodexHostConfig
from jarvis.context import IsolatedRecaller, RecallEvidence
from jarvis.db import (
    action,
    create_engine,
    memory_log,
    memory_summary,
    message,
    model_decision,
    read_position,
)
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    SLICE2_KERNEL_LIMITS,
    build_recaller,
    build_rememberer,
    verify_runtime_dependencies,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.kernel import (
    build_agent_runtime,
    build_kernel_runtime,
    resolve_provider_configuration,
)
from jarvis.memory import MemoryIdentity, MemoryStore
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.memory_tools import compose_memory_catalog
from jarvis.memory_workers import RemembererWorker
from jarvis.messages import MessageStore
from jarvis.ownership import Database, deployment_ownership
from jarvis.read_positions import PostgresReadRecorder
from jarvis.recall_evaluation import (
    RecallCase,
    RecallFixture,
    RecallObservation,
    load_recall_set,
    score_recall,
)
from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "eval" / "recall-memories.jsonl"
CASES = ROOT / "eval" / "recall.jsonl"
SEEDED_SUMMARY_ID = UUID("10000000-0000-4000-8000-000000000001")
_SUPPORTED_ROUTES = frozenset(("gpt-5.6-terra",))
_RECALL_TERMINAL_OUTCOMES = frozenset(
    (
        *(item.value for item in ThreadStopKind),
        "completed",
        "invalid_result",
        "invalid_selection",
        "missing_search",
        "missing_selection",
    )
)
_FROZEN_RECALL_CASE_IDS = frozenset(f"R{index:02d}" for index in range(1, 18))
_MAX_RECALL_CASES = len(_FROZEN_RECALL_CASE_IDS)
_PROVIDER_TERMINAL_CODES = frozenset(
    (
        "approval_unanswered",
        "backend_failed",
        "cancelled",
        "not_observed",
        "output_limit_exceeded",
        "output_schema_violation",
        "quota_exhausted",
        "succeeded",
        "turn_timeout",
    )
)


class QualificationFailure(RuntimeError):
    def __init__(
        self,
        stage: str,
        cause_type: str,
        reason_code: str,
        *,
        case_id: str | None = None,
        completed_case_count: int | None = None,
        provider_terminal: str | None = None,
    ) -> None:
        if (case_id is None) != (completed_case_count is None):
            raise ValueError("recall failure progress must be complete or absent")
        if case_id is not None and (
            case_id not in _FROZEN_RECALL_CASE_IDS
            or type(completed_case_count) is not int
            or not 0 <= completed_case_count < _MAX_RECALL_CASES
        ):
            raise ValueError("recall failure progress is invalid")
        if provider_terminal is not None and (
            case_id is None or provider_terminal not in _PROVIDER_TERMINAL_CODES
        ):
            raise ValueError("provider terminal evidence is invalid")
        super().__init__(reason_code)
        self.stage = stage
        self.cause_type = cause_type
        self.reason_code = reason_code
        self.case_id = case_id
        self.completed_case_count = completed_case_count
        self.provider_terminal = provider_terminal


class ProbeCheckFailed(RuntimeError):
    def __init__(
        self, reason_code: str, *, provider_terminal: str | None = None
    ) -> None:
        if (
            provider_terminal is not None
            and provider_terminal not in _PROVIDER_TERMINAL_CODES
        ):
            raise ValueError("provider terminal evidence is invalid")
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.provider_terminal = provider_terminal


class RecallCaseFailure(RuntimeError):
    def __init__(
        self,
        *,
        case_id: str,
        completed_case_count: int,
        cause: BaseException,
    ) -> None:
        if (
            case_id not in _FROZEN_RECALL_CASE_IDS
            or type(completed_case_count) is not int
            or not 0 <= completed_case_count < _MAX_RECALL_CASES
        ):
            raise ValueError("recall case progress is invalid")
        super().__init__("recall_case_failed")
        self.case_id = case_id
        self.completed_case_count = completed_case_count
        self.cause = cause


class QualificationProvider:
    """Delegate the provider lifecycle while retaining one closed terminal code."""

    def __init__(self, inner: ProviderSessionPort) -> None:
        self._inner = inner
        self._terminal_code = "not_observed"

    @property
    def terminal_code(self) -> str:
        return self._terminal_code

    def reset_terminal(self) -> None:
        self._terminal_code = "not_observed"

    async def acquire_continuing(
        self,
        definition: AgentDefinition,
        saved_ref: AgentSessionRef | None,
    ) -> ProviderSessionLease:
        return await self._inner.acquire_continuing(definition, saved_ref)

    async def open_isolated(self, definition: AgentDefinition) -> ProviderSessionLease:
        return await self._inner.open_isolated(definition)

    async def run_observed_turn(
        self,
        lease: ProviderSessionLease,
        content: tuple[ContentPart, ...],
        cancellation: CancelSignal,
        *,
        timeout_seconds: float | None = None,
    ) -> AgentTerminal:
        self._terminal_code = "not_observed"
        terminal = await self._inner.run_observed_turn(
            lease,
            content,
            cancellation,
            timeout_seconds=timeout_seconds,
        )
        if terminal.status == "succeeded":
            self._terminal_code = "succeeded"
        elif terminal.status == "cancelled":
            self._terminal_code = "cancelled"
        elif isinstance(terminal.failure, AgentQuotaExhausted):
            self._terminal_code = "quota_exhausted"
        elif isinstance(terminal.failure, AgentFailure):
            self._terminal_code = terminal.failure.cause
        return terminal

    async def accumulated_usage(self, lease: ProviderSessionLease) -> ProviderUsage:
        return await self._inner.accumulated_usage(lease)

    async def release(self, lease: ProviderSessionLease) -> None:
        await self._inner.release(lease)

    async def discard(self, lease: ProviderSessionLease) -> None:
        await self._inner.discard(lease)

    async def close(self, lease: ProviderSessionLease) -> None:
        await self._inner.close(lease)

    async def discard_reference(
        self,
        definition_fingerprint: str,
        ref: AgentSessionRef,
    ) -> None:
        await self._inner.discard_reference(definition_fingerprint, ref)


class _Embedder(Protocol):
    async def embed(self, inputs: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class _EmbeddingStore(Protocol):
    async def open_memories(
        self,
        *,
        identities: tuple[MemoryIdentity, ...],
        maximum_rows: int,
    ) -> tuple[object, ...]: ...

    async def update_embedding(
        self,
        *,
        identity: MemoryIdentity,
        embedding: Sequence[float],
    ) -> object: ...


class _RecallRunner(Protocol):
    async def observe(self, case: RecallCase) -> RecallEvidence: ...


@dataclass(frozen=True, slots=True)
class Arguments:
    model: str
    profile: Literal["personal"]
    codex_host_config_path: Path
    runtime_state_directory: Path
    database_url: str
    embedding_api_key: SecretStr
    owner_timezone: str
    reasoning_effort: str

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.owner_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                "owner timezone must be an installed IANA timezone"
            ) from error


class _NoopRecallTrace:
    def __init__(self) -> None:
        self.terminal_outcome: str | None = None

    def completed(self) -> bool:
        return self.terminal_outcome == "completed"

    def failure_reason(self) -> str:
        outcome = self.terminal_outcome
        if outcome is None:
            return "recaller_terminal_missing"
        if outcome not in _RECALL_TERMINAL_OUTCOMES:
            return "recaller_terminal_invalid"
        return f"recaller_terminal_{outcome}"

    async def record_recall(
        self,
        *,
        message_id: UUID,
        candidate_identities: tuple[MemoryIdentity, ...],
        selected_identities: tuple[MemoryIdentity, ...],
        run_id: str,
        terminal_outcome: str,
        provider_turns: int,
        input_tokens: int | None,
        output_tokens: int | None,
        duration_seconds: float,
    ) -> None:
        del (
            message_id,
            candidate_identities,
            selected_identities,
            run_id,
            provider_turns,
            input_tokens,
            output_tokens,
            duration_seconds,
        )
        self.terminal_outcome = terminal_outcome


class _ProductionRecallRunner:
    def __init__(
        self,
        recaller: IsolatedRecaller,
        trace: _NoopRecallTrace,
        provider: QualificationProvider | None = None,
    ) -> None:
        self._recaller = recaller
        self._trace = trace
        self._provider = provider

    async def observe(self, case: RecallCase) -> RecallEvidence:
        now = datetime.now(UTC)
        self._trace.terminal_outcome = None
        if self._provider is not None:
            self._provider.reset_terminal()
        await self._recaller.recall(
            HostInput(
                InputId(str(uuid4())),
                PromptSections(
                    (
                        PromptSection(
                            PromptSectionKind("owner_input"),
                            (),
                            PromptText(case.query),
                        ),
                    )
                ),
                now,
            ),
            as_of=now,
            recent_context=PromptSections(()),
            cancellation=CancellationToken(),
        )
        if not self._trace.completed():
            raise ProbeCheckFailed(
                self._trace.failure_reason(),
                provider_terminal=(
                    None if self._provider is None else self._provider.terminal_code
                ),
            )
        evidence = self._recaller.last_evidence
        if evidence is None:
            raise ProbeCheckFailed("recaller_evidence_missing")
        return evidence


async def seed_recall_fixtures(
    engine: Database,
    fixtures: tuple[RecallFixture, ...],
) -> dict[str, object]:
    """Seed an empty migrated qualification database without transforming text."""
    raw_values, summary_values = fixture_insert_values(fixtures)
    raw_fixtures = tuple(item for item in fixtures if item.table_kind == "memory_log")
    summary_fixtures = tuple(
        item for item in fixtures if item.table_kind == "memory_summary"
    )
    by_id = {fixture.id: fixture for fixture in fixtures}
    summary = by_id.get(SEEDED_SUMMARY_ID)
    if summary is None or summary.table_kind != "memory_summary":
        raise ProbeCheckFailed("seeded_summary_fixture_missing")
    async with engine.begin() as connection:
        await connection.execute(select(memory_log.c.embedding).limit(0))
        await connection.execute(select(memory_summary.c.embedding).limit(0))
        index_rows = (
            await connection.execute(
                text(
                    "SELECT tablename, indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND tablename IN ('memory_log', 'memory_summary') "
                    "AND indexname IN ("
                    "'ix_memory_log_search_english', "
                    "'ix_memory_log_search_simple', "
                    "'ix_memory_summary_search_english', "
                    "'ix_memory_summary_search_simple')"
                )
            )
        ).all()
        indexes = {(row.tablename, row.indexname): row.indexdef for row in index_rows}
        for table_name in ("memory_log", "memory_summary"):
            for representation in ("english", "simple"):
                definition = indexes.get(
                    (table_name, f"ix_{table_name}_search_{representation}")
                )
                if definition is None or (
                    f" USING gin (to_tsvector('{representation}'::regconfig, text))"
                    not in definition
                ):
                    raise ProbeCheckFailed("memory_search_index_invalid")
        counts = [
            cast(int, await connection.scalar(select(func.count()).select_from(table)))
            for table in (
                message,
                memory_log,
                memory_summary,
                action,
                model_decision,
                read_position,
            )
        ]
        if any(counts):
            raise ProbeCheckFailed("database_not_empty")
        if raw_values:
            await connection.execute(insert(memory_log), list(raw_values))
        if summary_values:
            await connection.execute(insert(memory_summary), list(summary_values))
        raw_rows = (
            await connection.execute(select(memory_log.c.id, memory_log.c.text))
        ).all()
        summary_rows = (
            await connection.execute(
                select(
                    memory_summary.c.id,
                    memory_summary.c.text,
                    memory_summary.c.source_memory_ids,
                )
            )
        ).all()
        if {row.id: row.text for row in raw_rows} != {
            item.id: item.text for item in raw_fixtures
        }:
            raise ProbeCheckFailed("raw_fixture_round_trip_failed")
        if {
            row.id: (row.text, tuple(row.source_memory_ids)) for row in summary_rows
        } != {
            item.id: (item.text, item.source_memory_ids) for item in summary_fixtures
        }:
            raise ProbeCheckFailed("summary_fixture_round_trip_failed")
    return {
        "fixtures": len(fixtures),
        "raw": len(raw_values),
        "summaries": len(summary_values),
        "seeded_summary_id": str(SEEDED_SUMMARY_ID),
        "status": "passed",
    }


def fixture_insert_values(
    fixtures: tuple[RecallFixture, ...],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    raw: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for item in fixtures:
        if item.table_kind == "memory_log":
            raw.append({"id": item.id, "text": item.text})
        else:
            summaries.append(
                {
                    "id": item.id,
                    "text": item.text,
                    "source_memory_ids": list(item.source_memory_ids),
                }
            )
    return tuple(raw), tuple(summaries)


async def populate_fixture_embeddings(
    store: _EmbeddingStore,
    embedder: _Embedder,
    fixtures: tuple[RecallFixture, ...],
) -> dict[str, object]:
    identities = tuple(MemoryIdentity(item.table_kind, item.id) for item in fixtures)
    memories = await store.open_memories(
        identities=identities,
        maximum_rows=len(identities),
    )
    if len(memories) != len(fixtures):
        raise ProbeCheckFailed("fixture_memory_missing")
    texts: list[str] = []
    for memory, identity in zip(memories, identities, strict=True):
        if getattr(memory, "identity", None) != identity:
            raise ProbeCheckFailed("fixture_memory_order_changed")
        text = getattr(memory, "text", None)
        if type(text) is not str:
            raise ProbeCheckFailed("fixture_memory_text_invalid")
        texts.append(text)
    vectors = await embedder.embed(tuple(texts))
    if len(vectors) != len(identities) or any(
        len(vector) != EMBEDDING_DIMENSION for vector in vectors
    ):
        raise ProbeCheckFailed("fixture_embedding_shape_invalid")
    for identity, vector in zip(identities, vectors, strict=True):
        await store.update_embedding(identity=identity, embedding=vector)
    return {
        "dimension": EMBEDDING_DIMENSION,
        "embedded": len(vectors),
        "model": EMBEDDING_MODEL,
        "status": "passed",
    }


async def observe_recall_cases(
    cases: tuple[RecallCase, ...],
    runner: _RecallRunner,
) -> tuple[tuple[RecallObservation, ...], tuple[dict[str, object], ...]]:
    observations: list[RecallObservation] = []
    evidence_rows: list[dict[str, object]] = []
    for case in cases:
        try:
            evidence = await runner.observe(case)
        except BaseException as error:
            raise RecallCaseFailure(
                case_id=case.id,
                completed_case_count=len(observations),
                cause=error,
            ) from error
        observation = RecallObservation(
            id=case.id,
            selected_ids=tuple(item.id for item in evidence.selected_identities),
            opened_ids=tuple(item.id for item in evidence.opened_identities),
            search_calls=evidence.search_calls,
        )
        observations.append(observation)
        evidence_rows.append(
            {
                "candidate_memory_ids": [
                    {"id": str(item.id), "table_kind": item.table_kind}
                    for item in evidence.candidate_identities
                ],
                "id": case.id,
                "opened_memory_ids": [
                    {"id": str(item.id), "table_kind": item.table_kind}
                    for item in evidence.opened_identities
                ],
                "search_calls": evidence.search_calls,
                "selected_memory_ids": [
                    {"id": str(item.id), "table_kind": item.table_kind}
                    for item in evidence.selected_identities
                ],
            }
        )
    return tuple(observations), tuple(evidence_rows)


async def verify_embedding_credential_denies_generation(api_key: SecretStr) -> None:
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        runtime = ProviderRuntime(
            Credentials(openai=api_key.get_secret_value()),
            retry=RetryPolicy(1, 0.0, 0.0, 0.0, Present(30.0)),
            http_client=http,
        )
        try:
            await runtime.generate(
                GenerateIntent(
                    target=ProviderTarget("openai", "gpt-5.6-terra"),
                    messages=(
                        UserMessage(
                            (PromptBlock("Return the single word qualification."),)
                        ),
                    ),
                    max_output_tokens=8,
                    reasoning="none",
                    tools=(),
                    tool_choice="none",
                    output=TextOutput(),
                )
            )
        except CredentialRejected:
            return
        except BaseException as error:
            raise ProbeCheckFailed("generation_denial_not_proven") from error
    raise ProbeCheckFailed("embedding_credential_generated_content")


def _identity_observations(
    observations: tuple[RecallObservation, ...],
) -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "opened_ids": list(map(str, item.opened_ids)),
            "search_calls": item.search_calls,
            "selected_ids": list(map(str, item.selected_ids)),
        }
        for item in observations
    ]


def qualification_failure(stage: str, error: BaseException) -> QualificationFailure:
    case_id = None
    completed_case_count = None
    cause = error
    if isinstance(error, RecallCaseFailure):
        case_id = error.case_id
        completed_case_count = error.completed_case_count
        cause = error.cause
    reason_code = (
        cause.reason_code
        if isinstance(cause, ProbeCheckFailed)
        else "unexpected_exception"
    )
    provider_terminal = (
        cause.provider_terminal
        if case_id is not None and isinstance(cause, ProbeCheckFailed)
        else None
    )
    return QualificationFailure(
        stage,
        type(cause).__name__,
        reason_code,
        case_id=case_id,
        completed_case_count=completed_case_count,
        provider_terminal=provider_terminal,
    )


def failure_evidence(error: QualificationFailure) -> dict[str, object]:
    return {
        "case_id": error.case_id,
        "completed_case_count": error.completed_case_count,
        "provider_terminal": error.provider_terminal,
        "reason_code": error.reason_code,
        "stage": error.stage,
        "type": error.cause_type,
    }


async def _run(arguments: Arguments) -> dict[str, object]:
    verify_runtime_dependencies()
    _validate_directories(arguments)
    host = CodexHostConfig.load(arguments.codex_host_config_path)
    shared_cwd_parent = Path(host.cognition_cwd_parent)
    if (
        not shared_cwd_parent.is_dir()
        or stat.S_IMODE(shared_cwd_parent.stat().st_mode) != 0o2750
    ):
        raise ValueError("cognition cwd parent must be a mode-02750 directory")
    arguments.runtime_state_directory.mkdir(mode=0o700)
    fixtures, cases = load_recall_set(MEMORIES, CASES)
    raw_engine = create_engine(arguments.database_url)
    async with AsyncExitStack() as database_lifetime:
        database_lifetime.push_async_callback(raw_engine.dispose)
        engine = await database_lifetime.enter_async_context(
            deployment_ownership(raw_engine)
        )
        stage = "seed"
        try:
            seed = await seed_recall_fixtures(engine, fixtures)
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
            ) as embedding_http:
                embedder = OpenAIEmbedder(
                    arguments.embedding_api_key,
                    http_client=embedding_http,
                )
                stage = "embedding"
                embedding = await populate_fixture_embeddings(
                    MemoryStore(engine), embedder, fixtures
                )
                stage = "generation_denial"
                await verify_embedding_credential_denies_generation(
                    arguments.embedding_api_key
                )
                stage = "recall"
                (
                    observations,
                    evidence,
                    rememberer,
                ) = await _run_production_roles(
                    arguments, host, engine, embedder, cases
                )
                score = score_recall(cases, observations)
        except BaseException as error:
            raise qualification_failure(stage, error) from error
        status = "passed" if score.passed == score.total else "failed"
        return {
            "embedding": embedding,
            "embedding_credential_generation": {"status": "denied"},
            "evaluation": {
                "evidence": list(evidence),
                "observations": _identity_observations(observations),
                "score": score.model_dump(mode="json"),
                "status": status,
            },
            "rememberer": rememberer,
            "revisions": dict(EXPECTED_GIT_PINS),
            "route": arguments.model,
            "seed": seed,
            "status": status,
        }


async def _run_production_roles(
    arguments: Arguments,
    host: CodexHostConfig,
    engine: Database,
    embedder: OpenAIEmbedder,
    cases: tuple[RecallCase, ...],
) -> tuple[
    tuple[RecallObservation, ...],
    tuple[dict[str, object], ...],
    dict[str, object],
]:
    async with build_agent_runtime(
        provider_state_root=arguments.runtime_state_directory,
        codex_endpoints=host.endpoints,
    ) as agent_runtime:
        catalog = compose_memory_catalog(PostgresMemoryRepository(engine), embedder)
        provider_configuration = await resolve_provider_configuration(
            runtime=agent_runtime,
            profile_key=arguments.profile,
            model_key=arguments.model,
            reasoning=arguments.reasoning_effort,
        )
        recaller_definition, recaller_plan = build_recaller(
            catalog=catalog,
            provider=provider_configuration,
            owner_timezone=arguments.owner_timezone,
        )
        rememberer_definition, rememberer_plan = build_rememberer(
            catalog=catalog,
            provider=provider_configuration,
            owner_timezone=arguments.owner_timezone,
        )
        limits = slice3_admission_limits(len(cases))
        RollingAdmissionPort.initialize(
            arguments.runtime_state_directory / "admission.json", limits
        )
        admission = RootTrackingAdmissionPort(
            RollingAdmissionPort(
                arguments.runtime_state_directory / "admission.json", limits
            )
        )
        runtime = build_kernel_runtime(
            runtime=agent_runtime,
            shared_cwd_parent=Path(host.cognition_cwd_parent),
            session_ref_path=arguments.runtime_state_directory / "session-ref.json",
        )
        provider = QualificationProvider(runtime.provider)
        try:
            root = await admission.reserve(
                AdmissionRequest(
                    RunId(str(uuid4())),
                    ThreadId("slice-3-recall-qualification"),
                    1,
                    SLICE2_KERNEL_LIMITS.max_provider_turns,
                    SLICE2_KERNEL_LIMITS.max_provider_input_tokens,
                    SLICE2_KERNEL_LIMITS.max_provider_output_tokens,
                )
            )
            if not isinstance(root, AdmissionGranted):
                raise ProbeCheckFailed("qualification_root_admission_denied")
            trace = _NoopRecallTrace()
            recaller = IsolatedRecaller(
                model_decisions=lambda evidence: PostgresModelDecisionJournal(
                    engine, evidence=evidence
                ),
                definition=recaller_definition,
                plan=recaller_plan,
                admission=admission,
                provider=provider,
                dispatcher_factory=lambda: MemoryToolDispatcher(
                    recorder=PostgresReadRecorder(engine)
                ),
                memory=MemoryStore(engine),
                trace=trace,
            )
            try:
                observations = await observe_recall_cases(
                    cases, _ProductionRecallRunner(recaller, trace, provider)
                )
            finally:
                await admission.settle(
                    root.token,
                    AdmissionUsage(0, ProviderUsage(), 0.0),
                )
            rememberer = await _run_zero_memory_rememberer(
                engine=engine,
                definition=rememberer_definition,
                plan=rememberer_plan,
                admission=admission,
                provider=provider,
                embedder=embedder,
            )
            return (*observations, rememberer)
        finally:
            await runtime.close()


async def _run_zero_memory_rememberer(
    *,
    engine: Database,
    definition: AgentDefinition,
    plan: FrozenToolPlan,
    admission: RootTrackingAdmissionPort,
    provider: QualificationProvider,
    embedder: OpenAIEmbedder,
) -> dict[str, object]:
    owner_id = uuid4()
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        before = [
            cast(int, await connection.scalar(select(func.count()).select_from(table)))
            for table in (memory_log, memory_summary, action)
        ]
        await connection.execute(
            insert(message).values(
                id=owner_id,
                role="owner",
                text="Hello!",
                source="qualification",
                source_conversation_id="slice-3-memory-qualification",
                source_message_id="rememberer-zero-memory",
                created_at=now,
                processed_at=now,
                processing_attempts=1,
                trace={
                    "settlement": {
                        "conclusion_kind": "silent",
                        "conclusion_message_id": None,
                        "outcome": "silent",
                        "run_id": "qualification-settled-owner-input",
                        "through_checkpoint": str(owner_id),
                    }
                },
            )
        )
    provider.reset_terminal()
    worker = RemembererWorker(
        model_decisions=lambda evidence: PostgresModelDecisionJournal(
            engine, evidence=evidence
        ),
        definition=definition,
        plan=plan,
        admission=admission,
        provider=provider,
        dispatcher_factory=lambda: MemoryToolDispatcher(
            recorder=PostgresReadRecorder(engine)
        ),
        memory=MemoryStore(engine),
        messages=MessageStore(engine),
        embedder=embedder,
        maximum_messages_per_group=1,
    )
    if not await worker.run_one(CancellationToken()):
        raise ProbeCheckFailed("rememberer_did_not_complete")
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    select(message.c.remembered_at, message.c.trace).where(
                        message.c.id == owner_id
                    )
                )
            )
            .mappings()
            .one()
        )
        after = [
            cast(int, await connection.scalar(select(func.count()).select_from(table)))
            for table in (memory_log, memory_summary, action)
        ]
    return verified_zero_memory_result(
        before=(before[0], before[1], before[2]),
        after=(after[0], after[1], after[2]),
        remembered_at=row["remembered_at"],
        trace=row["trace"],
    )


def verified_zero_memory_result(
    *,
    before: tuple[int, int, int],
    after: tuple[int, int, int],
    remembered_at: object,
    trace: object,
) -> dict[str, object]:
    if remembered_at is None:
        raise ProbeCheckFailed("rememberer_watermark_missing")
    if not isinstance(trace, dict):
        raise ProbeCheckFailed("rememberer_trace_invalid")
    remembered = cast("dict[str, object]", trace).get("rememberer")
    if not isinstance(remembered, dict):
        raise ProbeCheckFailed("rememberer_trace_missing")
    value = cast("dict[str, object]", remembered)
    if value.get("created_memory_ids") != [] or after != before:
        raise ProbeCheckFailed("rememberer_zero_memory_changed_durable_rows")
    run = value.get("run")
    if not isinstance(run, dict):
        raise ProbeCheckFailed("rememberer_run_summary_missing")
    metrics = cast("dict[str, object]", run)
    if metrics.get("terminal_outcome") != "completed":
        raise ProbeCheckFailed("rememberer_run_summary_invalid")
    usage: dict[str, int | None] = {}
    for name in ("provider_turns", "input_tokens", "output_tokens", "duration_ms"):
        metric = metrics.get(name)
        if metric is not None and (type(metric) is not int or metric < 0):
            raise ProbeCheckFailed("rememberer_run_metrics_invalid")
        usage[name] = metric
    if not usage["provider_turns"]:
        raise ProbeCheckFailed("rememberer_provider_turn_missing")
    return {
        "action_rows_added": after[2] - before[2],
        "memory_log_rows_added": after[0] - before[0],
        "memory_summary_rows_added": after[1] - before[1],
        "status": "passed",
        "usage": usage,
        "watermark_advanced": True,
    }


def _validate_directories(arguments: Arguments) -> None:
    if not arguments.codex_host_config_path.is_absolute():
        raise ValueError("Codex host config path must be absolute")
    runtime = arguments.runtime_state_directory
    if not runtime.is_absolute() or runtime.exists() or not runtime.parent.is_dir():
        raise ValueError(
            "runtime state must be an unused absolute path with an existing parent"
        )
    if stat.S_IMODE(runtime.parent.stat().st_mode) & 0o077:
        raise ValueError("runtime-state parent must be private")


def _required(values: Mapping[str, object], name: str) -> str:
    value = values.get(name)
    if type(value) is not str or not value:
        raise ValueError(f"missing qualification setting: {name}")
    return value


def _parse_arguments(argv: Sequence[str] | None = None) -> Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("JARVIS_CODEX_MODEL"))
    parser.add_argument("--profile", default=os.environ.get("JARVIS_CODEX_PROFILE_KEY"))
    parser.add_argument(
        "--codex-host-config",
        default=os.environ.get("JARVIS_CODEX_HOST_CONFIG_PATH"),
    )
    parser.add_argument(
        "--runtime-state-directory",
        default=os.environ.get("JARVIS_LIVE_RUNTIME_STATE_DIRECTORY"),
    )
    parser.add_argument(
        "--database-url", default=os.environ.get("JARVIS_LIVE_DATABASE_URL")
    )
    parser.add_argument(
        "--owner-timezone", default=os.environ.get("JARVIS_OWNER_TIMEZONE")
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.environ.get("JARVIS_CODEX_REASONING_EFFORT", "high"),
    )
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        default=os.environ.get("JARVIS_MEMORY_LIVE") == "1",
    )
    values = cast("dict[str, object]", vars(parser.parse_args(argv)))
    if values["confirm_paid"] is not True:
        raise ValueError(
            "paid qualification requires --confirm-paid or JARVIS_MEMORY_LIVE=1"
        )
    model = _required(values, "model")
    if model not in _SUPPORTED_ROUTES:
        raise ValueError("model must be a qualified local-account route")
    profile = _required(values, "profile")
    if profile != "personal":
        raise ValueError("profile must be the Jarvis Personal route")
    return Arguments(
        model=model,
        profile="personal",
        codex_host_config_path=Path(_required(values, "codex_host_config")),
        runtime_state_directory=Path(_required(values, "runtime_state_directory")),
        database_url=_required(values, "database_url"),
        embedding_api_key=SecretStr(
            _required(os.environ, "JARVIS_EMBEDDING_OPENAI_API_KEY")
        ),
        owner_timezone=_required(values, "owner_timezone"),
        reasoning_effort=_required(values, "reasoning_effort"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    try:
        arguments = _parse_arguments(argv)
        route = arguments.model
        result = asyncio.run(_run(arguments))
    except QualificationFailure as error:
        result = {
            "failure": failure_evidence(error),
            "revisions": dict(EXPECTED_GIT_PINS),
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "status": "failed",
        }
    except BaseException as error:
        result = {
            "failure": {
                "case_id": None,
                "completed_case_count": None,
                "provider_terminal": None,
                "reason_code": "unexpected_exception",
                "stage": "setup",
                "type": type(error).__name__,
            },
            "revisions": dict(EXPECTED_GIT_PINS),
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "status": "failed",
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the paid Slice 4 frozen rebuild and Dreamer qualification."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import httpx
from llm_agent_kernel import (
    AdmissionGranted,
    AdmissionRequest,
    AdmissionUsage,
    CancellationToken,
    ProviderUsage,
    RunId,
    ThreadId,
)
from provider_runtime.agent_runtime import AgentSession, AgentSessionRequest
from provider_runtime.agent_runtime.codex_sdk import CodexSdkAdapter
from pydantic import SecretStr
from qualify_memory import (
    Arguments as MemoryArguments,
)
from qualify_memory import (
    populate_fixture_embeddings,
    qualification_settings,
    seed_recall_fixtures,
    verify_embedding_credential_denies_generation,
)

from jarvis._atomic_json import replace_private_json
from jarvis.admission import RollingAdmissionPort, RootTrackingAdmissionPort
from jarvis.codex_config import CodexHostConfig
from jarvis.context import IsolatedRecaller
from jarvis.db import create_engine
from jarvis.decisions import ModelEvidence, PostgresModelDecisionJournal
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    build_slice4_definitions,
    verify_runtime_dependencies,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.kernel import (
    build_agent_runtime,
    build_kernel_runtime,
    resolve_provider_configuration,
)
from jarvis.memory import MemoryStore
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.ownership import deployment_ownership
from jarvis.read_composition import build_slice3_catalog
from jarvis.read_positions import PostgresReadRecorder
from jarvis.rebuild import (
    DreamMutationProgress,
    PostgresRebuildStore,
    rebuild_admission_limits,
    rebuild_derived_memory,
)
from jarvis.recall_evaluation import RecallCase, RecallScore, load_recall_set
from jarvis.recall_probe import RecallProbeResult, RecallProbeTrace, run_recall_probe
from jarvis.service import DreamerRunCompleted, DreamerWorker
from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "eval" / "recall-memories.jsonl"
CASES = ROOT / "eval" / "recall.jsonl"
MAXIMUM_REBUILD_MEMORY_ROWS = 10_000
SUPPORTED_ROUTES = frozenset(("gpt-5.6-terra",))
PHASE_EVIDENCE_FILENAME = "recall-phase-evidence.json"


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, cause: BaseException) -> None:
        super().__init__(stage)
        self.stage = stage
        self.cause_type = type(cause).__name__


def _required(values: Mapping[str, object], name: str) -> str:
    value = values.get(name)
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"missing qualification setting: {name}")
    return value


def _arguments(argv: Sequence[str] | None) -> MemoryArguments:
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
        "--database-url",
        default=os.environ.get("JARVIS_LIVE_DATABASE_URL"),
    )
    parser.add_argument(
        "--owner-timezone",
        default=os.environ.get("JARVIS_OWNER_TIMEZONE"),
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.environ.get("JARVIS_CODEX_REASONING_EFFORT", "high"),
    )
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        default=os.environ.get("JARVIS_DREAMING_LIVE") == "1",
    )
    values = cast("dict[str, object]", vars(parser.parse_args(argv)))
    if values["confirm_paid"] is not True:
        raise ValueError("paid qualification requires --confirm-paid")
    model = _required(values, "model")
    if model not in SUPPORTED_ROUTES:
        raise ValueError("model must be a qualified local-account route")
    profile = _required(values, "profile")
    if profile != "personal":
        raise ValueError("profile must be the Jarvis Personal route")
    arguments = MemoryArguments(
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
    if not arguments.codex_host_config_path.is_absolute():
        raise ValueError("Codex host config path must be absolute")
    runtime = arguments.runtime_state_directory
    if not runtime.is_absolute() or runtime.exists() or not runtime.parent.is_dir():
        raise ValueError("runtime state must be a fresh absolute path")
    if stat.S_IMODE(runtime.parent.stat().st_mode) & 0o077:
        raise ValueError("runtime-state parent must be private")
    return arguments


def _usage(result: RecallProbeResult) -> dict[str, int]:
    return {
        "duration_ms": sum(item.duration_ms for item in result.usages),
        "input_tokens": sum(item.input_tokens or 0 for item in result.usages),
        "output_tokens": sum(item.output_tokens or 0 for item in result.usages),
        "provider_turns": sum(item.provider_turns for item in result.usages),
    }


def embedding_credential_absent(
    environment: Mapping[str, str],
    embedding_key: str,
) -> bool:
    return (
        "JARVIS_EMBEDDING_OPENAI_API_KEY" not in environment
        and embedding_key not in environment.values()
    )


def record_phase_evidence(
    path: Path,
    records: list[dict[str, object]],
    phase: Literal["pre_rebuild", "post_rebuild"],
    score: RecallScore,
) -> None:
    if len(score.cases) > 100 or score.total != len(score.cases):
        raise ValueError("recall phase score is not bounded and internally consistent")
    counts = (
        score.selected_passed,
        score.opened_passed,
        score.search_passed,
        score.passed,
    )
    if any(type(value) is not int or not 0 <= value <= score.total for value in counts):
        raise ValueError("recall phase aggregate is invalid")
    if any(
        len(item.id) != 3 or item.id[0] != "R" or not item.id[1:].isdigit()
        for item in score.cases
    ):
        raise ValueError("recall phase case identity is invalid")
    expected_counts = (
        sum(item.selected_pass for item in score.cases),
        sum(item.opened_pass for item in score.cases),
        sum(item.search_pass for item in score.cases),
        sum(item.passed for item in score.cases),
    )
    if counts != expected_counts:
        raise ValueError("recall phase aggregate does not match its cases")
    expected_phase = "pre_rebuild" if not records else "post_rebuild"
    if phase != expected_phase or len(records) >= 2:
        raise ValueError("recall phase score order is invalid")
    record: dict[str, object] = {
        "aggregate": {
            "opened_passed": score.opened_passed,
            "passed": score.passed,
            "search_passed": score.search_passed,
            "selected_passed": score.selected_passed,
            "total": score.total,
        },
        "cases": [
            {
                "id": item.id,
                "opened_pass": item.opened_pass,
                "passed": item.passed,
                "search_pass": item.search_pass,
                "selected_pass": item.selected_pass,
            }
            for item in score.cases
        ],
        "phase": phase,
    }
    records.append(record)
    try:
        replace_private_json(
            path,
            {
                "phases": records,
                "schema_version": "jarvis-slice-4-recall-phase-evidence.v1",
            },
        )
    except BaseException:
        records.pop()
        raise


async def _run(arguments: MemoryArguments) -> dict[str, object]:
    verify_runtime_dependencies()
    host = CodexHostConfig.load(arguments.codex_host_config_path)
    shared_cwd_parent = Path(host.cognition_cwd_parent)
    if (
        not shared_cwd_parent.is_dir()
        or stat.S_IMODE(shared_cwd_parent.stat().st_mode) != 0o2750
    ):
        raise ValueError("cognition cwd parent must be a mode-02750 directory")
    arguments.runtime_state_directory.mkdir(mode=0o700)
    phase_evidence_path = arguments.runtime_state_directory / PHASE_EVIDENCE_FILENAME
    fixtures, cases = load_recall_set(MEMORIES, CASES)
    settings = qualification_settings(arguments)
    raw_engine = create_engine(arguments.database_url)
    async with AsyncExitStack() as database_lifetime:
        database_lifetime.push_async_callback(raw_engine.dispose)
        engine = await database_lifetime.enter_async_context(
            deployment_ownership(raw_engine)
        )
        agent_runtime = build_agent_runtime(
            provider_state_root=arguments.runtime_state_directory,
            codex_endpoints=host.endpoints,
        )
        database_lifetime.push_async_callback(agent_runtime.close)
        original_open_session = CodexSdkAdapter.open_session
        child_environment_observations: list[bool] = []

        async def observed_open_session(
            self: CodexSdkAdapter,
            request: AgentSessionRequest,
            *,
            environment: Mapping[str, str],
        ) -> AgentSession:
            absent = embedding_credential_absent(
                environment,
                arguments.embedding_api_key.get_secret_value(),
            )
            child_environment_observations.append(absent)
            if not absent:
                raise RuntimeError(
                    "embedding credential reached Codex child environment"
                )
            return await original_open_session(
                self,
                request,
                environment=environment,
            )

        CodexSdkAdapter.open_session = observed_open_session
        stage = "database"
        try:
            async with (
                httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                ) as http,
            ):
                embedder = OpenAIEmbedder(
                    arguments.embedding_api_key,
                    http_client=http,
                )
                seed = await seed_recall_fixtures(engine, fixtures)
                initial_embedding = await populate_fixture_embeddings(
                    MemoryStore(engine),
                    embedder,
                    fixtures,
                )
                stage = "credential_containment"
                await verify_embedding_credential_denies_generation(
                    arguments.embedding_api_key
                )
                catalog = build_slice3_catalog(
                    settings=settings,
                    google_oauth_http=http,
                    google_api_http=http,
                    maps_http=http,
                    brave_http=http,
                    memory_repository=PostgresMemoryRepository(engine),
                    memory_embedder=embedder,
                )
                provider_configuration = await resolve_provider_configuration(
                    runtime=agent_runtime,
                    profile_key=arguments.profile,
                    model_key=arguments.model,
                    reasoning=arguments.reasoning_effort,
                )
                definitions = build_slice4_definitions(
                    catalog=catalog,
                    provider=provider_configuration,
                    owner_timezone=arguments.owner_timezone,
                )
                limits = rebuild_admission_limits(len(cases))
                admission_path = arguments.runtime_state_directory / "admission.json"
                RollingAdmissionPort.initialize(admission_path, limits)
                admission = RootTrackingAdmissionPort(
                    RollingAdmissionPort(admission_path, limits)
                )
                root = await admission.reserve(
                    AdmissionRequest(
                        RunId(str(uuid4())),
                        ThreadId("slice-4-rebuild-qualification"),
                        1,
                        1,
                        1,
                        1,
                    )
                )
                if not isinstance(root, AdmissionGranted):
                    raise RuntimeError("qualification root admission was not granted")
                runtime = build_kernel_runtime(
                    runtime=agent_runtime,
                    shared_cwd_parent=shared_cwd_parent,
                    session_ref_path=arguments.runtime_state_directory
                    / "session-ref.json",
                )
                probes: list[RecallProbeResult] = []
                dream_runs: list[DreamerRunCompleted] = []
                try:

                    def recaller_factory(
                        trace: RecallProbeTrace,
                    ) -> IsolatedRecaller:
                        def journals(
                            evidence: ModelEvidence | None,
                        ) -> PostgresModelDecisionJournal:
                            return PostgresModelDecisionJournal(
                                engine, evidence=evidence
                            )

                        return IsolatedRecaller(
                            model_decisions=journals,
                            definition=definitions.recaller,
                            plan=definitions.plans["recaller"],
                            admission=admission,
                            provider=runtime.provider,
                            dispatcher_factory=lambda: MemoryToolDispatcher(
                                recorder=PostgresReadRecorder(engine)
                            ),
                            memory=MemoryStore(engine),
                            trace=trace,
                        )

                    async def evaluate(
                        selected_cases: tuple[RecallCase, ...],
                    ) -> RecallScore:
                        probe = await run_recall_probe(
                            cases=selected_cases,
                            recaller_factory=recaller_factory,
                        )
                        probes.append(probe)
                        return probe.score

                    dreamer = DreamerWorker(
                        model_decisions=lambda evidence: PostgresModelDecisionJournal(
                            engine, evidence=evidence
                        ),
                        definition=definitions.dreamer,
                        plan=definitions.plans["dreamer"],
                        admission=admission,
                        provider=runtime.provider,
                        dispatcher_factory=lambda: MemoryToolDispatcher(
                            recorder=PostgresReadRecorder(engine)
                        ),
                        memory=MemoryStore(engine),
                    )

                    async def dream(job_as_of: datetime) -> DreamMutationProgress:
                        outcome = await dreamer.run_at(
                            as_of=job_as_of,
                            cancellation=CancellationToken(),
                            parent_admission=root.token,
                        )
                        if not isinstance(outcome, DreamerRunCompleted):
                            raise RuntimeError("paid Dreamer did not complete")
                        dream_runs.append(outcome)
                        return DreamMutationProgress(
                            len(outcome.created_summary_ids),
                            len(outcome.removed_summary_ids),
                        )

                    scores: list[tuple[str, int, int]] = []
                    phase_evidence: list[dict[str, object]] = []

                    def record_score(
                        phase: Literal["pre_rebuild", "post_rebuild"],
                        score: RecallScore,
                    ) -> None:
                        record_phase_evidence(
                            phase_evidence_path,
                            phase_evidence,
                            phase,
                            score,
                        )
                        scores.append((phase, score.passed, score.total))

                    stage = "rebuild"
                    rebuilt = await rebuild_derived_memory(
                        store=PostgresRebuildStore(engine),
                        embedder=embedder,
                        cases=cases,
                        evaluate=evaluate,
                        dream_once=dream,
                        record_score=record_score,
                        maximum_memory_rows=MAXIMUM_REBUILD_MEMORY_ROWS,
                        as_of=datetime.now(UTC),
                    )
                finally:
                    try:
                        await admission.settle(
                            root.token,
                            AdmissionUsage(0, ProviderUsage(), 0.0),
                        )
                    finally:
                        await runtime.close()
                if rebuilt.pre_score.passed != 17 or rebuilt.post_score.passed != 17:
                    raise RuntimeError("frozen recall evaluation did not score 17/17")
                if len(probes) != 2:
                    raise RuntimeError("rebuild did not run exactly two recall passes")
                if not child_environment_observations or not all(
                    child_environment_observations
                ):
                    raise RuntimeError(
                        "live Codex child-environment containment was not observed"
                    )
                return {
                    "credential_containment": {
                        "codex_child_environment_observations": len(
                            child_environment_observations
                        ),
                        "embedding_credential_absent": True,
                        "generation_with_embedding_key": "denied",
                    },
                    "dependencies": {
                        **EXPECTED_GIT_PINS,
                    },
                    "dreamer": {
                        "definition_fingerprint": definitions.dreamer.fingerprint,
                        "inserted": rebuilt.summaries_inserted,
                        "plan_revision": definitions.plans["dreamer"].plan_revision,
                        "provider_turns": sum(
                            item.metrics.provider_turns for item in dream_runs
                        ),
                        "input_tokens": sum(
                            item.metrics.usage.input_tokens or 0 for item in dream_runs
                        ),
                        "output_tokens": sum(
                            item.metrics.usage.output_tokens or 0 for item in dream_runs
                        ),
                        "duration_ms": round(
                            sum(item.metrics.duration_seconds for item in dream_runs)
                            * 1_000
                        ),
                        "removed": rebuilt.summaries_removed,
                        "runs": rebuilt.dreamer_runs,
                        "session_compatibility_revision": (
                            definitions.dreamer.session_compatibility_revision
                        ),
                    },
                    "embedding": {
                        "dimension": EMBEDDING_DIMENSION,
                        "initial_rows": initial_embedding["embedded"],
                        "model": EMBEDDING_MODEL,
                        "raw_rebuilt": rebuilt.raw_embeddings_written,
                        "summary_rebuilt": rebuilt.summary_embeddings_written,
                    },
                    "evaluation": {
                        "phase_evidence": PHASE_EVIDENCE_FILENAME,
                        "post": rebuilt.post_score.model_dump(mode="json"),
                        "post_usage": _usage(probes[1]),
                        "pre": rebuilt.pre_score.model_dump(mode="json"),
                        "pre_usage": _usage(probes[0]),
                        "score_records": scores,
                    },
                    "rebuild": {
                        "lexical_raw_recall_after_wipe": True,
                        "raw_memory_count": rebuilt.raw_memory_count,
                        "summaries_after": rebuilt.summaries_after,
                        "wipe": asdict(rebuilt.wipe),
                    },
                    "seed": seed,
                    "status": "passed",
                }
        except BaseException as error:
            raise QualificationFailure(stage, error) from error
        finally:
            CodexSdkAdapter.open_session = original_open_session


def main(argv: Sequence[str] | None = None) -> int:
    route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    try:
        arguments = _arguments(argv)
        route = arguments.model
        result = asyncio.run(_run(arguments))
    except QualificationFailure as error:
        result = {
            "failure": {"stage": error.stage, "type": error.cause_type},
            "route": route if route in SUPPORTED_ROUTES else "unconfigured",
            "status": "failed",
        }
    except BaseException as error:
        result = {
            "failure": {"stage": "setup", "type": type(error).__name__},
            "route": route if route in SUPPORTED_ROUTES else "unconfigured",
            "status": "failed",
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the sanitized paid Slice 4 dreaming-memory end-to-end qualification."""

from __future__ import annotations

import asyncio
import json
import os
import stat
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from llm_agent_kernel import (
    CancellationToken,
    DispatchResult,
    InitialReadDispatchLineage,
    RunId,
    ThreadCompleted,
    ThreadId,
    ToolDispatchLineage,
)
from llm_tools import BudgetState, FrozenToolPlan, ToolBinding, ToolId
from sqlalchemy import func, select

from jarvis.admission import (
    ExactToolBudgetFactory,
    RollingAdmissionLimits,
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
    slice3_admission_limits,
)
from jarvis.codex_control import CodexHostConfig
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
    SLICE4_DREAM_KERNEL_LIMITS,
    Slice4Definitions,
    build_slice4_definitions,
    verify_runtime_dependencies,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import (
    KernelRuntime,
    build_agent_runtime,
    build_kernel_runtime,
    resolve_provider_configuration,
)
from jarvis.memory import MemoryIdentity, MemoryStore, StoredMemory
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore, StoredMessage
from jarvis.ownership import Database, deployment_ownership
from jarvis.read_composition import build_slice3_catalog
from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder
from jarvis.read_positions import PostgresReadRecorder
from jarvis.read_tools import (
    CalendarGetEventInput,
    CalendarGetEventSuccess,
    CalendarListEventsInput,
    CalendarListEventsSuccess,
    CalendarNormalEvent,
    GmailReadThreadInput,
    GmailReadThreadSuccess,
    GmailSearchInput,
    GmailSearchSuccess,
)
from jarvis.service import (
    DreamerRunCompleted,
    DreamerWorker,
    JarvisThreadRunner,
    RemembererWorker,
)
from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL, Settings

_SUPPORTED_ROUTES = frozenset(("gpt-5.6-terra",))
_CALENDAR_WINDOW_DAYS = 366


class QualificationCheckFailed(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, cause_type: str, reason_code: str) -> None:
        super().__init__(reason_code)
        self.stage = stage
        self.cause_type = cause_type
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class LiveResources:
    gmail_thread_id: str = field(repr=False)
    gmail_message_id: str = field(repr=False)
    calendar_id: str = field(repr=False)
    calendar_event_id: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class RawRow:
    id: UUID
    text: str = field(repr=False)
    embedding_dimension: int | None


@dataclass(frozen=True, slots=True)
class SummaryRow:
    id: UUID
    text: str = field(repr=False)
    source_memory_ids: tuple[UUID, ...]
    embedding_dimension: int | None


@dataclass(frozen=True, slots=True)
class MemoryState:
    raw: tuple[RawRow, ...] = field(repr=False)
    summary_count: int
    action_count: int
    summaries: tuple[SummaryRow, ...] = field(default=(), repr=False)


class _RecordingMemoryStore(MemoryStore):
    def __init__(self, engine: Database) -> None:
        super().__init__(engine)
        self.opened_identities: list[MemoryIdentity] = []

    async def open_memories(
        self,
        *,
        identities: tuple[MemoryIdentity, ...],
        maximum_rows: int,
    ) -> tuple[StoredMemory, ...]:
        rows = await super().open_memories(
            identities=identities,
            maximum_rows=maximum_rows,
        )
        self.opened_identities.extend(row.identity for row in rows)
        return rows


class _TargetRecordingDispatcher:
    def __init__(
        self, engine: Database, host_secrets: tuple[str, ...], resources: LiveResources
    ) -> None:
        self._inner = ReadToolDispatcher(
            recorder=PostgresReadRecorder(engine), host_secrets=host_secrets
        )
        self._resources = resources
        self.gmail_reopened = False
        self.calendar_reopened = False
        self.successful_reads = 0

    async def dispatch(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: ToolDispatchLineage,
    ) -> DispatchResult:
        result = await self._inner.dispatch(
            binding=binding,
            validated_input=validated_input,
            plan=plan,
            budgets=budgets,
            cancellation=cancellation,
            lineage=lineage,
        )
        if result.result.get("type") != "Success":
            return result
        self.successful_reads += 1
        value = result.result.get("value")
        if not isinstance(value, dict):
            raise QualificationCheckFailed("read_success_shape_invalid")
        if (
            binding.spec.id == ToolId("gmail.read_thread")
            and isinstance(validated_input, GmailReadThreadInput)
            and validated_input.thread_id == self._resources.gmail_thread_id
        ):
            opened = GmailReadThreadSuccess.model_validate(value)
            self.gmail_reopened = opened.thread_id == self._resources.gmail_thread_id
        elif (
            binding.spec.id == ToolId("calendar.get_event")
            and isinstance(validated_input, CalendarGetEventInput)
            and validated_input.calendar_id == self._resources.calendar_id
            and validated_input.event_id == self._resources.calendar_event_id
        ):
            opened = CalendarGetEventSuccess.model_validate(value).event
            self.calendar_reopened = (
                isinstance(opened, CalendarNormalEvent)
                and opened.calendar_id == self._resources.calendar_id
                and opened.event_id == self._resources.calendar_event_id
            )
        return result


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty without edge whitespace")
    return value


def qualification_admission_limits() -> RollingAdmissionLimits:
    """Bound two foreground memory cycles and one isolated Dreamer run."""
    one_cycle = slice3_admission_limits(1)
    dream_input = SLICE4_DREAM_KERNEL_LIMITS.max_provider_input_tokens
    dream_output = SLICE4_DREAM_KERNEL_LIMITS.max_provider_output_tokens
    return RollingAdmissionLimits(
        window_seconds=one_cycle.window_seconds,
        max_turns=(
            2 * one_cycle.max_turns + SLICE4_DREAM_KERNEL_LIMITS.max_provider_turns
        ),
        max_input_tokens=(
            2 * one_cycle.max_input_tokens
            + dream_input
            + one_cycle.root_input_token_overshoot
        ),
        max_output_tokens=(
            2 * one_cycle.max_output_tokens
            + dream_output
            + one_cycle.root_output_token_overshoot
        ),
        max_no_progress_attempts=one_cycle.max_no_progress_attempts,
        root_input_token_overshoot=one_cycle.root_input_token_overshoot,
        root_output_token_overshoot=one_cycle.root_output_token_overshoot,
        serial_child_turns=one_cycle.serial_child_turns,
        serial_child_input_tokens=one_cycle.serial_child_input_tokens,
        serial_child_output_tokens=one_cycle.serial_child_output_tokens,
    )


def owner_inputs(resources: LiveResources) -> tuple[str, str, tuple[str, str]]:
    gmail_uri = f"gmail://primary/message/{quote(resources.gmail_message_id, safe='')}"
    calendar_uri = (
        f"gcal://{quote(resources.calendar_id, safe='')}/event/"
        f"{quote(resources.calendar_event_id, safe='')}"
    )
    first = (
        "My durable response-format preference is to use exactly three short bullets "
        "headed Decision, Evidence, and Next check for future updates about this "
        "linked matter. Please remember one concise self-contained memory containing "
        "this preference and both references exactly, but do not open the records "
        "now.\n\n"
        "<refs>\n"
        f'  <ref uri="{gmail_uri}">Related email in Gmail thread '
        f"{resources.gmail_thread_id}</ref>\n"
        f'  <ref uri="{calendar_uri}">Related calendar event</ref>\n'
        "</refs>"
    )
    second = (
        "Using my saved response-format preference, update me on the linked matter. "
        "Reopen both linked live records before answering because memory is evidence "
        "and their current Gmail and Calendar state is authoritative."
    )
    return first, second, (gmail_uri, calendar_uri)


def _usage(
    *,
    provider_turns: int,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_seconds: float,
) -> dict[str, int | None]:
    return {
        "duration_ms": round(duration_seconds * 1_000),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "provider_turns": provider_turns,
    }


def cognitive_usage(trace: Mapping[str, object], role: str) -> dict[str, int | None]:
    value = trace.get(role)
    if not isinstance(value, dict):
        raise QualificationCheckFailed(f"{role}_trace_missing")
    run = cast("dict[object, object]", value).get("run")
    if not isinstance(run, dict):
        raise QualificationCheckFailed(f"{role}_run_missing")
    metrics = cast("dict[object, object]", run)
    if metrics.get("terminal_outcome") != "completed":
        raise QualificationCheckFailed(f"{role}_not_completed")
    result: dict[str, int | None] = {}
    for name in ("duration_ms", "input_tokens", "output_tokens", "provider_turns"):
        item = metrics.get(name)
        if item is not None and (type(item) is not int or item < 0):
            raise QualificationCheckFailed(f"{role}_usage_invalid")
        result[name] = item
    if not result["provider_turns"]:
        raise QualificationCheckFailed(f"{role}_provider_turn_missing")
    return result


def selected_memories(trace: Mapping[str, object]) -> tuple[MemoryIdentity, ...]:
    recaller = trace.get("recaller")
    if not isinstance(recaller, dict):
        raise QualificationCheckFailed("recaller_trace_missing")
    selected = cast("dict[object, object]", recaller).get("selected_memory_ids")
    if not isinstance(selected, list):
        raise QualificationCheckFailed("recaller_selected_ids_invalid")
    selected_values = cast("list[object]", selected)
    if len(selected_values) > 20:
        raise QualificationCheckFailed("recaller_selected_ids_invalid")
    identities: list[MemoryIdentity] = []
    try:
        for value in selected_values:
            if not isinstance(value, dict):
                raise ValueError
            item = cast("dict[object, object]", value)
            table_kind = item.get("table_kind")
            identifier = item.get("id")
            if table_kind not in {"memory_log", "memory_summary"} or not isinstance(
                identifier, str
            ):
                raise ValueError
            identities.append(MemoryIdentity(cast("Any", table_kind), UUID(identifier)))
    except (TypeError, ValueError):
        raise QualificationCheckFailed("recaller_selected_ids_invalid") from None
    if len(set(identities)) != len(identities):
        raise QualificationCheckFailed("recaller_selected_ids_invalid")
    return tuple(identities)


def validate_first_phase(
    *,
    before: MemoryState,
    after: MemoryState,
    owner: StoredMessage,
    required_uris: tuple[str, str],
    required_gmail_thread_id: str,
) -> tuple[frozenset[UUID], dict[str, object]]:
    before_ids = {row.id for row in before.raw}
    created = tuple(row for row in after.raw if row.id not in before_ids)
    if len(created) != 1:
        raise QualificationCheckFailed("first_rememberer_created_not_one_memory")
    if owner.remembered_at is None:
        raise QualificationCheckFailed("first_owner_watermark_missing")
    if after.action_count != 0:
        raise QualificationCheckFailed("action_row_created")
    if after.summary_count != 0:
        raise QualificationCheckFailed("summary_row_created")
    if any(row.embedding_dimension != EMBEDDING_DIMENSION for row in created):
        raise QualificationCheckFailed("created_embedding_invalid")
    texts = tuple(row.text for row in after.raw)
    if len(texts) != len(set(texts)):
        raise QualificationCheckFailed("duplicate_memory_text")
    format_fragments = (
        "exactly three short bullets",
        "decision",
        "evidence",
        "next check",
    )
    if not any(
        all(uri in row.text for uri in required_uris)
        and required_gmail_thread_id in row.text
        and all(fragment in row.text.casefold() for fragment in format_fragments)
        for row in created
    ):
        raise QualificationCheckFailed("durable_linked_preference_missing")
    return frozenset(row.id for row in created), {
        "action_rows": after.action_count,
        "created_raw_rows": len(created),
        "duplicate_memory_text": False,
        "linked_preference_stored": True,
        "summary_rows": after.summary_count,
        "vectors_1536": True,
        "watermark_advanced": True,
    }


def new_summaries(before: MemoryState, after: MemoryState) -> tuple[SummaryRow, ...]:
    before_ids = {row.id for row in before.summaries}
    return tuple(row for row in after.summaries if row.id not in before_ids)


async def backfill_dream_summary(
    before: MemoryState, after: MemoryState, rememberer: RemembererWorker
) -> None:
    if len(new_summaries(before, after)) != 1:
        raise QualificationCheckFailed("dreamer_created_not_one_summary")
    if await rememberer.run_one(CancellationToken()) is not True:
        raise QualificationCheckFailed("summary_embedding_backfill_failed")


def validate_dream_phase(
    *,
    before: MemoryState,
    after: MemoryState,
    first_created: frozenset[UUID],
    required_uris: tuple[str, str],
) -> tuple[frozenset[UUID], dict[str, object]]:
    created = new_summaries(before, after)
    if len(created) != 1:
        raise QualificationCheckFailed("dreamer_created_not_one_summary")
    summary = created[0]
    if frozenset(summary.source_memory_ids) != first_created:
        raise QualificationCheckFailed("dreamer_summary_lineage_invalid")
    if summary.embedding_dimension != EMBEDDING_DIMENSION:
        raise QualificationCheckFailed("dreamer_summary_embedding_invalid")
    if not all(uri in summary.text for uri in required_uris):
        raise QualificationCheckFailed("dreamer_summary_missing_linked_matter")
    if after.action_count != 0 or after.raw != before.raw:
        raise QualificationCheckFailed("dreamer_changed_canonical_state")
    return frozenset((summary.id,)), {
        "action_rows": after.action_count,
        "created_summary_rows": 1,
        "flattened_raw_lineage": True,
        "linked_matter_retained": True,
        "raw_memory_unchanged": True,
        "vectors_1536": True,
    }


class ReopenEvidence(Protocol):
    gmail_reopened: bool
    calendar_reopened: bool
    successful_reads: int


def validate_second_phase(
    *,
    after: MemoryState,
    owner: StoredMessage,
    first_created: frozenset[UUID],
    created_summaries: frozenset[UUID],
    selected: tuple[MemoryIdentity, ...],
    opened: tuple[MemoryIdentity, ...],
    answer_text: str,
    dispatcher: ReopenEvidence,
) -> dict[str, object]:
    if not any(
        item.table_kind == "memory_log" and item.id in first_created
        for item in selected
    ):
        raise QualificationCheckFailed("fresh_recall_missed_created_memory")
    if not any(
        item.table_kind == "memory_summary" and item.id in created_summaries
        for item in selected
    ):
        raise QualificationCheckFailed("fresh_recall_missed_created_summary")
    summaries = {row.id: row for row in after.summaries if row.id in created_summaries}
    if set(summaries) != set(created_summaries):
        raise QualificationCheckFailed("created_summary_missing")
    required_opened = {
        MemoryIdentity("memory_summary", summary_id) for summary_id in created_summaries
    }
    required_opened.update(
        MemoryIdentity("memory_log", source_id)
        for summary in summaries.values()
        for source_id in summary.source_memory_ids
    )
    if not required_opened.issubset(set(opened)):
        raise QualificationCheckFailed("summary_raw_sources_not_opened")
    if not dispatcher.gmail_reopened:
        raise QualificationCheckFailed("gmail_thread_not_reopened")
    if not dispatcher.calendar_reopened:
        raise QualificationCheckFailed("calendar_event_not_reopened")
    if owner.remembered_at is None:
        raise QualificationCheckFailed("second_owner_watermark_missing")
    if after.action_count != 0:
        raise QualificationCheckFailed("action_row_created")
    if after.summary_count != len(created_summaries):
        raise QualificationCheckFailed("summary_row_count_changed")
    if any(row.embedding_dimension != EMBEDDING_DIMENSION for row in after.raw):
        raise QualificationCheckFailed("memory_embedding_invalid")
    texts = tuple(row.text for row in after.raw)
    if len(texts) != len(set(texts)):
        raise QualificationCheckFailed("duplicate_memory_text")
    bullet_lines = tuple(
        line.strip()[2:].strip()
        for line in answer_text.splitlines()
        if line.strip().startswith(("- ", "* ", "• "))
    )
    if len(bullet_lines) != 3:
        raise QualificationCheckFailed("owner_answer_preference_not_followed")
    headings: list[str] = []
    for line in bullet_lines:
        heading, separator, body = line.partition(":")
        headings.append(heading.strip().strip("*").casefold())
        if separator != ":" or len(body.split()) < 2:
            raise QualificationCheckFailed("owner_answer_not_useful")
    if headings != ["decision", "evidence", "next check"]:
        raise QualificationCheckFailed("owner_answer_preference_not_followed")
    return {
        "action_rows": after.action_count,
        "calendar_event_reopened": True,
        "duplicate_memory_text": False,
        "fresh_recall_selected_created_raw": True,
        "fresh_recall_selected_created_summary": True,
        "fresh_recall_opened_summary_sources": True,
        "gmail_thread_reopened": True,
        "owner_visible_answer_useful": True,
        "raw_rows": len(after.raw),
        "response_preference_followed": True,
        "successful_main_reads": dispatcher.successful_reads,
        "summary_rows": after.summary_count,
        "vectors_1536": True,
        "watermark_advanced": True,
    }


def assert_sanitized_output(
    result: Mapping[str, object], private_values: Sequence[str]
) -> None:
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if any(value and value in encoded for value in private_values):
        raise QualificationCheckFailed("report_contains_private_value")


def _validate_settings(settings: Settings, host: CodexHostConfig) -> None:
    if settings.codex_model not in _SUPPORTED_ROUTES:
        raise ValueError("model must be the qualified Slice 3 route")
    if settings.maximum_batch_size != 1:
        raise ValueError("memory E2E maximum batch size must be 1")
    if settings.embedding_model != EMBEDDING_MODEL:
        raise ValueError("embedding model differs from the deployment contract")
    if settings.embedding_dimension != EMBEDDING_DIMENSION:
        raise ValueError("embedding dimension differs from the deployment contract")
    runtime_parent = settings.runtime_state_directory.parent
    if not runtime_parent.is_absolute() or not runtime_parent.is_dir():
        raise ValueError("runtime-state parent must be an existing absolute directory")
    if stat.S_IMODE(runtime_parent.stat().st_mode) & 0o077:
        raise ValueError("runtime-state parent must be private")
    cognition_parent = Path(host.cognition_cwd_parent)
    if (
        not cognition_parent.is_dir()
        or stat.S_IMODE(cognition_parent.stat().st_mode) != 0o2750
    ):
        raise ValueError("cognition cwd parent must be a mode-02750 directory")
    if settings.runtime_state_directory.exists():
        raise ValueError("runtime state must be an unused path")


async def _empty_memory_state(engine: Database) -> MemoryState:
    state = await _memory_state(engine)
    async with engine.connect() as connection:
        counts = [
            cast(int, await connection.scalar(select(func.count()).select_from(table)))
            for table in (message, model_decision, read_position)
        ]
    if any(counts) or state.raw or state.summary_count or state.action_count:
        raise QualificationCheckFailed("database_not_empty")
    return state


async def _memory_state(engine: Database) -> MemoryState:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(
                    memory_log.c.id, memory_log.c.text, memory_log.c.embedding
                ).order_by(memory_log.c.created_at, memory_log.c.id)
            )
        ).all()
        summary_count = cast(
            int,
            await connection.scalar(select(func.count()).select_from(memory_summary)),
        )
        summary_rows = (
            await connection.execute(
                select(
                    memory_summary.c.id,
                    memory_summary.c.text,
                    memory_summary.c.source_memory_ids,
                    memory_summary.c.embedding,
                ).order_by(memory_summary.c.created_at, memory_summary.c.id)
            )
        ).all()
        action_count = cast(
            int, await connection.scalar(select(func.count()).select_from(action))
        )
    return MemoryState(
        raw=tuple(
            RawRow(
                id=cast(UUID, row.id),
                text=cast(str, row.text),
                embedding_dimension=(
                    None
                    if row.embedding is None
                    else len(cast("Sequence[float]", row.embedding))
                ),
            )
            for row in rows
        ),
        summary_count=summary_count,
        action_count=action_count,
        summaries=tuple(
            SummaryRow(
                id=cast(UUID, row.id),
                text=cast(str, row.text),
                source_memory_ids=tuple(cast("Sequence[UUID]", row.source_memory_ids)),
                embedding_dimension=(
                    None
                    if row.embedding is None
                    else len(cast("Sequence[float]", row.embedding))
                ),
            )
            for row in summary_rows
        ),
    )


async def _dispatch_read(
    *,
    dispatcher: ReadToolDispatcher[RunReadRecorder],
    definitions: Slice4Definitions,
    budgets: BudgetState,
    tool_id: str,
    validated_input: object,
    run_id: RunId,
    ordinal: int,
) -> dict[str, object]:
    binding = definitions.plans["main"].catalog_view.binding(ToolId(tool_id))
    result = await dispatcher.dispatch(
        binding=binding,
        validated_input=validated_input,
        plan=definitions.plans["main"],
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=InitialReadDispatchLineage(
            run_id, f"qualification-resource:{run_id}:{ordinal}"
        ),
    )
    if result.result.get("type") != "Success":
        raise QualificationCheckFailed(f"{tool_id.replace('.', '_')}_failed")
    value = result.result.get("value")
    if not isinstance(value, dict):
        raise QualificationCheckFailed("read_success_shape_invalid")
    return cast("dict[str, object]", value)


async def _select_live_resources(
    *,
    definitions: Slice4Definitions,
    host_secrets: tuple[str, ...],
    gmail_query: str,
    owner_timezone: str,
) -> LiveResources:
    dispatcher = ReadToolDispatcher(
        recorder=RunReadRecorder(), host_secrets=host_secrets
    )
    budgets = ExactToolBudgetFactory().create(definitions.plans["main"])
    run_id = RunId(str(uuid4()))
    searched = GmailSearchSuccess.model_validate(
        await _dispatch_read(
            dispatcher=dispatcher,
            definitions=definitions,
            budgets=budgets,
            tool_id="gmail.search",
            validated_input=GmailSearchInput(query=gmail_query, max_results=1),
            run_id=run_id,
            ordinal=1,
        )
    )
    if not searched.threads:
        raise QualificationCheckFailed("gmail_query_matched_no_thread")
    gmail_thread_id = searched.threads[0].thread_id
    opened_thread = GmailReadThreadSuccess.model_validate(
        await _dispatch_read(
            dispatcher=dispatcher,
            definitions=definitions,
            budgets=budgets,
            tool_id="gmail.read_thread",
            validated_input=GmailReadThreadInput(
                thread_id=gmail_thread_id, max_messages=50
            ),
            run_id=run_id,
            ordinal=2,
        )
    )
    if opened_thread.thread_id != gmail_thread_id or not opened_thread.messages:
        raise QualificationCheckFailed("gmail_thread_invalid")
    now = datetime.now(UTC)
    listed = CalendarListEventsSuccess.model_validate(
        await _dispatch_read(
            dispatcher=dispatcher,
            definitions=definitions,
            budgets=budgets,
            tool_id="calendar.list_events",
            validated_input=CalendarListEventsInput(
                time_min=now - timedelta(days=_CALENDAR_WINDOW_DAYS),
                time_max=now + timedelta(days=_CALENDAR_WINDOW_DAYS),
                time_zone=owner_timezone,
            ),
            run_id=run_id,
            ordinal=3,
        )
    )
    event = next(
        (item for item in listed.events if isinstance(item, CalendarNormalEvent)), None
    )
    if event is None:
        raise QualificationCheckFailed("calendar_has_no_normal_event")
    opened_event = CalendarGetEventSuccess.model_validate(
        await _dispatch_read(
            dispatcher=dispatcher,
            definitions=definitions,
            budgets=budgets,
            tool_id="calendar.get_event",
            validated_input=CalendarGetEventInput(
                calendar_id=event.calendar_id, event_id=event.event_id
            ),
            run_id=run_id,
            ordinal=4,
        )
    ).event
    if (
        not isinstance(opened_event, CalendarNormalEvent)
        or opened_event.calendar_id != event.calendar_id
        or opened_event.event_id != event.event_id
    ):
        raise QualificationCheckFailed("calendar_event_invalid")
    return LiveResources(
        gmail_thread_id=gmail_thread_id,
        gmail_message_id=opened_thread.messages[-1].message_id,
        calendar_id=event.calendar_id,
        calendar_event_id=event.event_id,
    )


def _build_roles(
    *,
    settings: Settings,
    engine: Database,
    definitions: Slice4Definitions,
    runtime: KernelRuntime,
    embedder: OpenAIEmbedder,
    resources: LiveResources,
    dispatchers: list[_TargetRecordingDispatcher],
) -> tuple[JarvisThreadRunner, RemembererWorker, _RecordingMemoryStore]:
    admission = RootTrackingAdmissionPort(
        RollingAdmissionPort(
            settings.admission_journal_path, qualification_admission_limits()
        )
    )
    memory = _RecordingMemoryStore(engine)
    messages = MessageStore(engine)
    rememberer = RemembererWorker(
        model_decisions=lambda evidence: PostgresModelDecisionJournal(
            engine, evidence=evidence
        ),
        definition=definitions.rememberer,
        plan=definitions.plans["rememberer"],
        admission=admission,
        provider=runtime.provider,
        dispatcher_factory=lambda: MemoryToolDispatcher(
            recorder=PostgresReadRecorder(engine)
        ),
        memory=memory,
        messages=messages,
        embedder=embedder,
        maximum_messages_per_group=1,
    )

    def dispatcher_factory() -> _TargetRecordingDispatcher:
        dispatcher = _TargetRecordingDispatcher(
            engine, settings.host_secrets, resources
        )
        dispatchers.append(dispatcher)
        return dispatcher

    return (
        JarvisThreadRunner(
            model_decisions=lambda evidence: PostgresModelDecisionJournal(
                engine, evidence=evidence
            ),
            settings=settings,
            store=messages,
            admission=admission,
            kernel_runtime=runtime,
            definitions=definitions,
            history=PostgresCanonicalHistory(engine),
            dispatcher_factory=dispatcher_factory,
            memory=memory,
            memory_dispatcher_factory=lambda: MemoryToolDispatcher(
                recorder=PostgresReadRecorder(engine)
            ),
            rememberer=rememberer,
        ),
        rememberer,
        memory,
    )


async def _owner_conclusion(
    store: MessageStore,
    owner: StoredMessage,
) -> StoredMessage:
    settlement = owner.trace.get("settlement")
    if not isinstance(settlement, dict):
        raise QualificationCheckFailed("owner_settlement_missing")
    identifier = cast("dict[object, object]", settlement).get("conclusion_message_id")
    try:
        message_id = UUID(cast(str, identifier))
    except (TypeError, ValueError):
        raise QualificationCheckFailed("owner_conclusion_missing") from None
    conclusion = await store.message_by_id(message_id)
    if (
        conclusion is None
        or conclusion.role != "assistant"
        or conclusion.source_conversation_id != owner.source_conversation_id
    ):
        raise QualificationCheckFailed("owner_conclusion_missing")
    return conclusion


async def _discard_main_reference(
    *,
    settings: Settings,
    definitions: Slice4Definitions,
    runtime: KernelRuntime,
    runner: JarvisThreadRunner,
    require_present: bool,
) -> None:
    thread_id = ThreadId(str(settings.discord.channel_id))
    stored = await runtime.references.load(thread_id, definitions.main.fingerprint)
    if stored is None and require_present:
        raise QualificationCheckFailed("main_session_reference_missing")
    if stored is not None:
        await runner.discard_recovered_session_reference()
    remaining = await runtime.references.load(thread_id, definitions.main.fingerprint)
    if remaining is not None:
        raise QualificationCheckFailed("main_session_reference_not_discarded")


async def cleanup_cycle_runtime(
    *,
    settings: Settings,
    definitions: Slice4Definitions,
    runtime: KernelRuntime,
    runner: JarvisThreadRunner | None,
    primary_error: BaseException | None,
) -> None:
    cleanup_error: BaseException | None = None
    if runner is not None:
        try:
            await _discard_main_reference(
                settings=settings,
                definitions=definitions,
                runtime=runtime,
                runner=runner,
                require_present=False,
            )
        except BaseException as error:
            cleanup_error = error
    try:
        await runtime.close()
    except BaseException as error:
        if cleanup_error is None:
            cleanup_error = error
    if primary_error is None and cleanup_error is not None:
        raise QualificationCheckFailed(
            "cycle_runtime_cleanup_failed"
        ) from cleanup_error


async def _run(settings: Settings, gmail_query: str) -> dict[str, object]:
    verify_runtime_dependencies()
    host = settings.codex_host_config
    _validate_settings(settings, host)
    settings.runtime_state_directory.mkdir(mode=0o700)
    limits = qualification_admission_limits()
    RollingAdmissionPort.initialize(settings.admission_journal_path, limits)
    raw_engine = create_engine(settings.database_url.get_secret_value())
    async with AsyncExitStack() as database_lifetime:
        database_lifetime.push_async_callback(raw_engine.dispose)
        engine = await database_lifetime.enter_async_context(
            deployment_ownership(raw_engine)
        )
        stage = "database"
        try:
            before = await _empty_memory_state(engine)
            async with AsyncExitStack() as clients:
                google_oauth_http = await clients.enter_async_context(
                    httpx.AsyncClient(trust_env=False, follow_redirects=False)
                )
                google_api_http = await clients.enter_async_context(
                    httpx.AsyncClient(trust_env=False, follow_redirects=False)
                )
                maps_http = await clients.enter_async_context(
                    httpx.AsyncClient(trust_env=False, follow_redirects=False)
                )
                brave_http = await clients.enter_async_context(
                    httpx.AsyncClient(trust_env=False, follow_redirects=False)
                )
                embedding_http = await clients.enter_async_context(
                    httpx.AsyncClient(trust_env=False, follow_redirects=False)
                )
                embedder = OpenAIEmbedder(
                    settings.embedding_openai_api_key,
                    http_client=embedding_http,
                )
                catalog = build_slice3_catalog(
                    settings=settings,
                    google_oauth_http=google_oauth_http,
                    google_api_http=google_api_http,
                    maps_http=maps_http,
                    brave_http=brave_http,
                    memory_repository=PostgresMemoryRepository(engine),
                    memory_embedder=embedder,
                )
                first_agent_runtime = build_agent_runtime(
                    provider_state_root=settings.runtime_state_directory,
                    codex_endpoints=host.endpoints,
                )
                clients.push_async_callback(first_agent_runtime.close)
                provider_configuration = await resolve_provider_configuration(
                    runtime=first_agent_runtime,
                    profile_key=settings.codex_profile_key,
                    model_key=settings.codex_model,
                )
                definitions = build_slice4_definitions(
                    catalog=catalog,
                    provider=provider_configuration,
                    owner_timezone=settings.owner_timezone,
                )

                stage = "resource_selection"
                resources = await _select_live_resources(
                    definitions=definitions,
                    host_secrets=settings.host_secrets,
                    gmail_query=gmail_query,
                    owner_timezone=settings.owner_timezone,
                )
                first_input, second_input, required_uris = owner_inputs(resources)
                store = MessageStore(engine)

                stage = "first_cycle"
                first_runtime = build_kernel_runtime(
                    runtime=first_agent_runtime,
                    shared_cwd_parent=Path(host.cognition_cwd_parent),
                    session_ref_path=settings.session_reference_path,
                )
                first_dispatchers: list[_TargetRecordingDispatcher] = []
                first_runner: JarvisThreadRunner | None = None
                first_error: BaseException | None = None
                try:
                    first_runner, first_rememberer, _first_memory = _build_roles(
                        settings=settings,
                        engine=engine,
                        definitions=definitions,
                        runtime=first_runtime,
                        embedder=embedder,
                        resources=resources,
                        dispatchers=first_dispatchers,
                    )
                    inserted = await store.insert_waking(
                        role="owner",
                        text=first_input,
                        source="qualification",
                        source_conversation_id=str(settings.discord.channel_id),
                        source_message_id=f"slice4-memory-e2e-{uuid4()}-1",
                        created_at=datetime.now(UTC),
                    )
                    first_outcome = await first_runner.run(CancellationToken())
                    if not isinstance(first_outcome, ThreadCompleted):
                        raise QualificationCheckFailed("first_thread_not_completed")
                    if await first_rememberer.run_one(CancellationToken()) is not True:
                        raise QualificationCheckFailed("first_rememberer_not_completed")
                    first_owner = await store.message_by_id(inserted.message.id)
                    if first_owner is None:
                        raise QualificationCheckFailed("first_owner_missing")
                    first_created, first_report = validate_first_phase(
                        before=before,
                        after=await _memory_state(engine),
                        owner=first_owner,
                        required_uris=required_uris,
                        required_gmail_thread_id=resources.gmail_thread_id,
                    )
                    first_report["main_usage"] = _usage(
                        provider_turns=first_outcome.metrics.provider_turns,
                        input_tokens=first_outcome.metrics.usage.input_tokens,
                        output_tokens=first_outcome.metrics.usage.output_tokens,
                        duration_seconds=first_outcome.metrics.duration_seconds,
                    )
                    first_report["recaller_usage"] = cognitive_usage(
                        first_owner.trace, "recaller"
                    )
                    first_report["rememberer_usage"] = cognitive_usage(
                        first_owner.trace, "rememberer"
                    )
                    await _discard_main_reference(
                        settings=settings,
                        definitions=definitions,
                        runtime=first_runtime,
                        runner=first_runner,
                        require_present=True,
                    )
                except BaseException as error:
                    first_error = error
                    raise
                finally:
                    await cleanup_cycle_runtime(
                        settings=settings,
                        definitions=definitions,
                        runtime=first_runtime,
                        runner=first_runner,
                        primary_error=first_error,
                    )

                stage = "dream"
                dream_agent_runtime = build_agent_runtime(
                    provider_state_root=settings.runtime_state_directory,
                    codex_endpoints=host.endpoints,
                )
                clients.push_async_callback(dream_agent_runtime.close)
                dream_runtime = build_kernel_runtime(
                    runtime=dream_agent_runtime,
                    shared_cwd_parent=Path(host.cognition_cwd_parent),
                    session_ref_path=settings.session_reference_path,
                )
                dream_before = await _memory_state(engine)
                dream_error: BaseException | None = None
                try:
                    dreamer = DreamerWorker(
                        model_decisions=lambda evidence: PostgresModelDecisionJournal(
                            engine, evidence=evidence
                        ),
                        definition=definitions.dreamer,
                        plan=definitions.plans["dreamer"],
                        admission=RootTrackingAdmissionPort(
                            RollingAdmissionPort(
                                settings.admission_journal_path,
                                qualification_admission_limits(),
                            )
                        ),
                        provider=dream_runtime.provider,
                        dispatcher_factory=lambda: MemoryToolDispatcher(
                            recorder=PostgresReadRecorder(engine)
                        ),
                        memory=MemoryStore(engine),
                    )
                    dream_outcome = await dreamer.run_at(
                        as_of=datetime.now(UTC),
                        cancellation=CancellationToken(),
                    )
                    if not isinstance(dream_outcome, DreamerRunCompleted):
                        raise QualificationCheckFailed("dreamer_not_completed")
                    dream_generated = await _memory_state(engine)
                    await backfill_dream_summary(
                        dream_before, dream_generated, first_rememberer
                    )
                    created_summaries, dream_report = validate_dream_phase(
                        before=dream_before,
                        after=await _memory_state(engine),
                        first_created=first_created,
                        required_uris=required_uris,
                    )
                    dream_report["embedding_backfill"] = (
                        "rememberer_bounded_null_vector_sweep"
                    )
                    dream_report["usage"] = _usage(
                        provider_turns=dream_outcome.metrics.provider_turns,
                        input_tokens=dream_outcome.metrics.usage.input_tokens,
                        output_tokens=dream_outcome.metrics.usage.output_tokens,
                        duration_seconds=dream_outcome.metrics.duration_seconds,
                    )
                except BaseException as error:
                    dream_error = error
                    raise
                finally:
                    try:
                        await dream_runtime.close()
                    except BaseException as error:
                        if dream_error is None:
                            raise QualificationCheckFailed(
                                "dream_runtime_cleanup_failed"
                            ) from error

                stage = "second_cycle"
                second_agent_runtime = build_agent_runtime(
                    provider_state_root=settings.runtime_state_directory,
                    codex_endpoints=host.endpoints,
                )
                clients.push_async_callback(second_agent_runtime.close)
                second_runtime = build_kernel_runtime(
                    runtime=second_agent_runtime,
                    shared_cwd_parent=Path(host.cognition_cwd_parent),
                    session_ref_path=settings.session_reference_path,
                )
                second_dispatchers: list[_TargetRecordingDispatcher] = []
                second_runner: JarvisThreadRunner | None = None
                second_error: BaseException | None = None
                try:
                    second_runner, second_rememberer, second_memory = _build_roles(
                        settings=settings,
                        engine=engine,
                        definitions=definitions,
                        runtime=second_runtime,
                        embedder=embedder,
                        resources=resources,
                        dispatchers=second_dispatchers,
                    )
                    inserted = await store.insert_waking(
                        role="owner",
                        text=second_input,
                        source="qualification",
                        source_conversation_id=str(settings.discord.channel_id),
                        source_message_id=f"slice4-memory-e2e-{uuid4()}-2",
                        created_at=datetime.now(UTC),
                    )
                    second_outcome = await second_runner.run(CancellationToken())
                    if not isinstance(second_outcome, ThreadCompleted):
                        raise QualificationCheckFailed("second_thread_not_completed")
                    if len(second_dispatchers) != 1:
                        raise QualificationCheckFailed("main_dispatcher_count_invalid")
                    recaller_opened = tuple(second_memory.opened_identities)
                    if await second_rememberer.run_one(CancellationToken()) is not True:
                        raise QualificationCheckFailed(
                            "second_rememberer_not_completed"
                        )
                    second_owner = await store.message_by_id(inserted.message.id)
                    if second_owner is None:
                        raise QualificationCheckFailed("second_owner_missing")
                    second_answer = await _owner_conclusion(store, second_owner)
                    second_report = validate_second_phase(
                        after=await _memory_state(engine),
                        owner=second_owner,
                        first_created=first_created,
                        created_summaries=created_summaries,
                        selected=selected_memories(second_owner.trace),
                        opened=recaller_opened,
                        answer_text=second_answer.text,
                        dispatcher=second_dispatchers[0],
                    )
                    second_report["main_usage"] = _usage(
                        provider_turns=second_outcome.metrics.provider_turns,
                        input_tokens=second_outcome.metrics.usage.input_tokens,
                        output_tokens=second_outcome.metrics.usage.output_tokens,
                        duration_seconds=second_outcome.metrics.duration_seconds,
                    )
                    second_report["recaller_usage"] = cognitive_usage(
                        second_owner.trace, "recaller"
                    )
                    second_report["rememberer_usage"] = cognitive_usage(
                        second_owner.trace, "rememberer"
                    )
                    await _discard_main_reference(
                        settings=settings,
                        definitions=definitions,
                        runtime=second_runtime,
                        runner=second_runner,
                        require_present=False,
                    )
                except BaseException as error:
                    second_error = error
                    raise
                finally:
                    await cleanup_cycle_runtime(
                        settings=settings,
                        definitions=definitions,
                        runtime=second_runtime,
                        runner=second_runner,
                        primary_error=second_error,
                    )

                result: dict[str, object] = {
                    "admission_cycle_capacity": {
                        "dreamer_runs": 1,
                        "foreground_cycles": 2,
                    },
                    "dream": dream_report,
                    "embedding": {
                        "dimension": EMBEDDING_DIMENSION,
                        "model": EMBEDDING_MODEL,
                    },
                    "first_cycle": first_report,
                    "resources": {
                        "calendar_normal_event_selected": True,
                        "gmail_thread_selected": True,
                    },
                    "revisions": {
                        "dependencies": {
                            **EXPECTED_GIT_PINS,
                        },
                        "roles": {
                            "main": definitions.main.session_compatibility_revision,
                            "recaller": (
                                definitions.recaller.session_compatibility_revision
                            ),
                            "rememberer": (
                                definitions.rememberer.session_compatibility_revision
                            ),
                            "dreamer": (
                                definitions.dreamer.session_compatibility_revision
                            ),
                        },
                        "tools": {
                            name: catalog.binding(ToolId(name)).implementation_revision
                            for name in (
                                "calendar.get_event",
                                "gmail.read_thread",
                                "memory.open",
                                "memory.search",
                            )
                        },
                    },
                    "route": settings.codex_model,
                    "runtime": {
                        "first_reference_discarded": True,
                        "fresh_runtime_rebuilt": True,
                        "second_reference_absent": True,
                    },
                    "second_cycle": second_report,
                    "status": "passed",
                }
                assert_sanitized_output(
                    result,
                    (
                        *settings.host_secrets,
                        gmail_query,
                        resources.gmail_thread_id,
                        resources.gmail_message_id,
                        resources.calendar_event_id,
                        first_input,
                        second_input,
                        *required_uris,
                    ),
                )
                return result
        except BaseException as error:
            reason_code = (
                error.reason_code
                if isinstance(error, QualificationCheckFailed)
                else "unexpected_exception"
            )
            raise QualificationFailure(
                stage, type(error).__name__, reason_code
            ) from error
        finally:
            pass


def main() -> int:
    route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    try:
        if os.environ.get("JARVIS_MEMORY_E2E_LIVE") != "1":
            raise ValueError("live qualification requires JARVIS_MEMORY_E2E_LIVE=1")
        settings = Settings.from_env()
        gmail_query = _required("JARVIS_MEMORY_E2E_GMAIL_QUERY")
        result = asyncio.run(_run(settings, gmail_query))
    except QualificationFailure as error:
        result = {
            "failure": {
                "reason_code": error.reason_code,
                "stage": error.stage,
                "type": error.cause_type,
            },
            "revisions": dict(EXPECTED_GIT_PINS),
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "status": "failed",
        }
    except BaseException as error:
        result = {
            "failure": {
                "reason_code": "unexpected_exception",
                "stage": "setup",
                "type": type(error).__name__,
            },
            "revisions": dict(EXPECTED_GIT_PINS),
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

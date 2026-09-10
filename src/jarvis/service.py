"""Bounded Jarvis host-service composition."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import discord
from llm_agent_kernel import (
    AdmissionToken,
    AgentDefinition,
    CancellationToken,
    DispatchCompleted,
    DispatchLineage,
    DispatchResult,
    HostInput,
    InputId,
    OneShotCompleted,
    OwnerToken,
    ProviderSessionPort,
    RunId,
    RunMetrics,
    ThreadDeferred,
    ThreadId,
    ThreadNoWork,
    ThreadOutcome,
    ThreadStopKind,
    ThreadStopped,
    ToolDispatchDefect,
    ToolDispatchLineage,
    ToolDispatchPort,
    run_one_shot,
    run_thread,
)
from llm_tools import (
    BudgetState,
    FrozenToolPlan,
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ToolBinding,
    canonical_json_bytes,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from jarvis.actions import ClaimedSchedule, ScheduleStateChanged
from jarvis.admission import (
    ExactToolBudgetFactory,
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
)
from jarvis.approval_runtime import ApprovalActionHandler
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.context import (
    IsolatedRecaller,
    JarvisContextSource,
    MemoryReadDispatcherPort,
)
from jarvis.decisions import ModelJournalFactory, isolated_decisions
from jarvis.definitions import (
    SLICE6_TOOL_LIMITS,
    DreamResult,
    RememberResult,
    Slice1Definitions,
    Slice2Definitions,
    Slice3Definitions,
    Slice4Definitions,
    Slice5Definitions,
    Slice6Definitions,
)
from jarvis.discord import (
    CatchUpResult,
    Control,
    DeliveryFailed,
    DeliveryResult,
    DiscordApprovalInteraction,
    DiscordOwnerMessage,
)
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import EmptySlice1Dispatcher, KernelRuntime
from jarvis.memory import (
    MemoryStore,
    RemembererGroup,
    RemembererRunSummary,
    StoredRawMemory,
    SummaryInsertionCandidate,
    SummaryMutationBatch,
)
from jarvis.messages import InboundInsert, MessageStore, PendingControl, StoredMessage
from jarvis.proactivity import ProcessLocalWakeTimer
from jarvis.read_tools import CalendarListEventsSuccess
from jarvis.settings import Settings
from jarvis.state import PausedState
from jarvis.terminal import TurnEvidence

LOGGER = logging.getLogger(__name__)

_MAX_MATERIAL_CONTEXT_BYTES = 180_000


class PendingDeliveryStore(Protocol):
    async def pending_delivery(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[StoredMessage, ...]: ...

    async def mark_delivered(
        self,
        *,
        message_id: UUID,
        source_message_id: str,
    ) -> None: ...


class CreateMessagePort(Protocol):
    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult: ...


@dataclass(frozen=True, slots=True)
class DeliveryFlushResult:
    selected: int
    delivered: int
    failure: DeliveryFailed | None


async def flush_pending_deliveries(
    *,
    store: PendingDeliveryStore,
    delivery: CreateMessagePort,
    source_conversation_id: str,
    limit: int,
) -> DeliveryFlushResult:
    """Deliver pending assistant rows in order and stop at the first failure."""

    pending = await store.pending_delivery(
        source_conversation_id=source_conversation_id,
        limit=limit,
    )
    delivered = 0
    for message in pending:
        result = await delivery.create_message(
            persisted_message_id=message.id,
            content=message.text,
        )
        if isinstance(result, DeliveryFailed):
            return DeliveryFlushResult(len(pending), delivered, result)
        await store.mark_delivered(
            message_id=message.id,
            source_message_id=result.discord_message_id,
        )
        delivered += 1
    return DeliveryFlushResult(len(pending), delivered, None)


@dataclass(frozen=True, slots=True)
class PreflightDeferred:
    until: datetime


type ServiceRunOutcome = ThreadOutcome | PreflightDeferred


@dataclass(frozen=True, slots=True)
class BackgroundDeferred:
    until: datetime


class EmbeddingPort(Protocol):
    async def embed(self, inputs: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class _StoredObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    tool_id: Annotated[str, Field(min_length=1, max_length=128)]
    ordinal: Annotated[int, Field(ge=1)]
    result: dict[str, JsonValue]


class _StoredMainEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["jarvis-main-evidence.v1"]
    observations: Annotated[
        tuple[_StoredObservation, ...], Field(max_length=SLICE6_TOOL_LIMITS.max_calls)
    ]


class CapturingReadDispatcher:
    """Capture bounded Main observations and terminal evidence."""

    def __init__(self, delegate: ToolDispatchPort, evidence: TurnEvidence) -> None:
        self._delegate = delegate
        self._evidence = evidence
        self._observations: list[tuple[str, int, object]] = []

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
        if not isinstance(lineage, DispatchLineage):
            raise ToolDispatchDefect(
                "main observation capture requires continuing-thread lineage"
            )
        result = await self._delegate.dispatch(
            binding=binding,
            validated_input=validated_input,
            plan=plan,
            budgets=budgets,
            cancellation=cancellation,
            lineage=lineage,
        )
        if isinstance(result, DispatchCompleted):
            self._record_observation(
                str(binding.spec.id), lineage.model_step_ordinal, result.result
            )
        return result

    def _record_observation(
        self, tool_id: str, ordinal: int, result: Mapping[str, object]
    ) -> None:
        if tool_id == "calendar.list_events" and result.get("type") == "Success":
            calendar = CalendarListEventsSuccess.model_validate(result.get("value"))
            coverage = calendar.coverage
            self._evidence.record_calendar_incompleteness(
                reasons=coverage.reasons,
                calendars_discovered=coverage.calendars_discovered,
                calendars_completed=coverage.calendars_completed,
                matched_events=coverage.matched_events,
            )
        self._observations.append((tool_id, ordinal, result))

    def snapshot_model_evidence(self) -> dict[str, object]:
        value = {
            "kind": "jarvis-main-evidence.v1",
            "observations": [
                {"tool_id": tool_id, "ordinal": ordinal, "result": result}
                for tool_id, ordinal, result in self._observations
            ],
        }
        encoded = canonical_json_bytes(value)
        if len(encoded) > SLICE6_TOOL_LIMITS.max_output_bytes + 16_384:
            raise ValueError("Main model evidence exceeds its frozen tool output bound")
        return _StoredMainEvidence.model_validate_json(encoded).model_dump(mode="json")

    def restore_model_evidence(self, value: object) -> None:
        stored = _StoredMainEvidence.model_validate_json(canonical_json_bytes(value))
        self._observations.clear()
        self._evidence.calendar_incompleteness = ()
        for observation in stored.observations:
            self._record_observation(
                observation.tool_id, observation.ordinal, observation.result
            )

    def material_sections(self) -> PromptSections:
        selected: list[PromptSection] = []
        used = 0
        for tool_id, ordinal, result in reversed(self._observations):
            encoded = canonical_json_bytes(result)
            if used + len(encoded) > _MAX_MATERIAL_CONTEXT_BYTES:
                continue
            selected.append(
                PromptSection(
                    PromptSectionKind("material_tool_observation"),
                    (
                        PromptAttribute(PromptAttributeName("tool_id"), tool_id),
                        PromptAttribute(
                            PromptAttributeName("model_step_ordinal"), str(ordinal)
                        ),
                    ),
                    PromptText(encoded.decode()),
                )
            )
            used += len(encoded)
        selected.reverse()
        return PromptSections(tuple(selected))

    def take_material_sections(self) -> PromptSections:
        sections = self.material_sections()
        self._observations.clear()
        return sections


@dataclass(frozen=True, slots=True)
class _ImmediateRemembererWork:
    owner_message_ids: tuple[UUID, ...]
    material_context: PromptSections


class RemembererWorker:
    """Run one bounded isolated rememberer or embedding unit at a time."""

    def __init__(
        self,
        *,
        definition: AgentDefinition,
        plan: FrozenToolPlan,
        admission: RootTrackingAdmissionPort,
        provider: ProviderSessionPort,
        model_decisions: ModelJournalFactory,
        dispatcher_factory: Callable[[], MemoryReadDispatcherPort],
        memory: MemoryStore,
        messages: MessageStore,
        embedder: EmbeddingPort,
        maximum_messages_per_group: int,
    ) -> None:
        if (
            type(maximum_messages_per_group) is not int
            or maximum_messages_per_group <= 0
        ):
            raise ValueError("rememberer group bound must be a positive integer")
        self._definition = definition
        self._plan = plan
        self._admission = admission
        self._provider = provider
        self._model_decisions = model_decisions
        self._dispatcher_factory = dispatcher_factory
        self._memory = memory
        self._messages = messages
        self._embedder = embedder
        self._maximum_messages_per_group = maximum_messages_per_group
        self._immediate: list[_ImmediateRemembererWork] = []
        self._commit_in_progress = False
        self._foreground_waiting = False

    def enqueue(
        self,
        owner_message_ids: tuple[UUID, ...],
        material_context: PromptSections,
    ) -> None:
        if not owner_message_ids or len(set(owner_message_ids)) != len(
            owner_message_ids
        ):
            raise ValueError("rememberer owner IDs must be non-empty and unique")
        self._immediate.append(
            _ImmediateRemembererWork(owner_message_ids, material_context)
        )

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        if self._commit_in_progress:
            self._foreground_waiting = True
        else:
            cancellation.cancel()

    async def run_one(
        self, cancellation: CancellationToken
    ) -> bool | BackgroundDeferred:
        if cancellation.cancelled:
            return False
        immediate = self._immediate[0] if self._immediate else None
        if immediate is None:
            groups = await self._memory.select_pending_rememberer_groups(
                maximum_groups=1,
                maximum_messages_per_group=self._maximum_messages_per_group,
            )
            if not groups:
                return await self._backfill(cancellation)
            group = groups[0]
            material_context = PromptSections(())
        else:
            try:
                group = await self._memory.prepare_rememberer_group(
                    owner_message_ids=immediate.owner_message_ids,
                )
            except Exception:
                self._immediate.pop(0)
                return False
            material_context = immediate.material_context
        limits = self._definition.limits
        reset_at = await self._admission.preflight_background(
            maximum_turns=limits.max_provider_turns,
            maximum_input_tokens=limits.max_provider_input_tokens,
            maximum_output_tokens=limits.max_provider_output_tokens,
        )
        if reset_at is not None:
            return BackgroundDeferred(reset_at)
        completed = await self._remember(group, material_context, cancellation)
        if completed and immediate is not None:
            self._immediate.pop(0)
        return completed

    async def _remember(
        self,
        group: RemembererGroup,
        material_context: PromptSections,
        cancellation: CancellationToken,
    ) -> bool:
        inputs = tuple(
            HostInput(
                InputId(str(target.id)),
                PromptSections(
                    (
                        PromptSection(
                            PromptSectionKind("settled_owner_input"),
                            (
                                PromptAttribute(
                                    PromptAttributeName("source"), target.source
                                ),
                            ),
                            PromptText(target.text),
                        ),
                    )
                ),
                target.created_at,
            )
            for target in group.targets
        )

        source = await self._rememberer_source(group, material_context)
        dispatcher = self._dispatcher_factory()
        operation_id = "jarvis-remember:" + ":".join(
            str(target.id) for target in group.targets
        )
        decisions, as_of = await isolated_decisions(
            self._model_decisions, dispatcher, operation_id, datetime.now(UTC)
        )
        run_id = RunId(str(uuid4()))
        try:
            outcome = await run_one_shot(
                run_id=run_id,
                definition=self._definition,
                inputs=inputs,
                as_of=as_of,
                decisions=decisions,
                plan=self._plan,
                source_sections=source,
                admission=self._admission,
                provider=self._provider,
                dispatcher=dispatcher,
                budget_factory=ExactToolBudgetFactory(),
                cancellation=cancellation,
            )
        except Exception:
            await self._record_attempt(
                group,
                run_id,
                "configuration_error",
                None,
            )
            return False
        if not isinstance(outcome, OneShotCompleted):
            await self._record_attempt(
                group,
                run_id,
                outcome.type.value,
                outcome.metrics,
            )
            return False
        if cancellation.cancelled:
            await self._record_attempt(
                group,
                run_id,
                "cancelled",
                outcome.metrics,
            )
            return False
        try:
            result = RememberResult.model_validate(outcome.result)
        except (TypeError, ValueError):
            await self._record_attempt(
                group,
                run_id,
                "invalid_result",
                outcome.metrics,
            )
            return False
        metrics = outcome.metrics
        if cancellation.cancelled:
            await self._record_attempt(
                group,
                run_id,
                "cancelled",
                metrics,
            )
            return False
        self._commit_in_progress = True
        self._foreground_waiting = False
        commit = None
        try:
            commit = await self._memory.commit_rememberer_result(
                group=group,
                memory_texts=tuple(result.memories),
                run=RemembererRunSummary(
                    run_id=str(run_id),
                    provider_turns=metrics.provider_turns,
                    input_tokens=metrics.usage.input_tokens,
                    output_tokens=metrics.usage.output_tokens,
                    duration_ms=round(metrics.duration_seconds * 1_000),
                ),
            )
        except Exception:
            pass
        finally:
            self._commit_in_progress = False
            if self._foreground_waiting:
                cancellation.cancel()
            self._foreground_waiting = False
        if commit is None:
            await self._record_attempt(
                group,
                run_id,
                "commit_failure",
                metrics,
            )
            return False
        if cancellation.cancelled or not commit.created:
            return True
        await self._embed_created(commit.created, cancellation)
        return True

    async def _record_attempt(
        self,
        group: RemembererGroup,
        run_id: RunId,
        terminal_outcome: str,
        metrics: RunMetrics | None,
    ) -> None:
        try:
            await self._messages.record_rememberer_attempt(
                message_ids=tuple(target.id for target in group.targets),
                run_id=str(run_id),
                terminal_outcome=terminal_outcome,
                provider_turns=None if metrics is None else metrics.provider_turns,
                input_tokens=None if metrics is None else metrics.usage.input_tokens,
                output_tokens=None if metrics is None else metrics.usage.output_tokens,
                duration_seconds=None if metrics is None else metrics.duration_seconds,
            )
        except Exception:
            return

    async def _rememberer_source(
        self,
        group: RemembererGroup,
        material_context: PromptSections,
    ) -> PromptSections:
        sections: list[PromptSection] = list(material_context.sections)
        settlement = group.settlement
        if settlement is not None:
            body = None
            if settlement.conclusion_message_id is not None:
                conclusion = await self._messages.message_by_id(
                    UUID(settlement.conclusion_message_id)
                )
                if conclusion is None or conclusion.role != "assistant":
                    raise RuntimeError("rememberer conclusion is missing")
                body = PromptText(conclusion.text)
            sections.append(
                PromptSection(
                    PromptSectionKind("persisted_conclusion"),
                    (
                        PromptAttribute(
                            PromptAttributeName("conclusion_kind"),
                            settlement.conclusion_kind,
                        ),
                        PromptAttribute(
                            PromptAttributeName("outcome"), settlement.outcome
                        ),
                    ),
                    body,
                )
            )
        recalled = _recalled_id_sections(group)
        sections.extend(recalled.sections)
        return PromptSections(tuple(sections))

    async def _embed_created(
        self,
        rows: tuple[StoredRawMemory, ...],
        cancellation: CancellationToken,
    ) -> None:
        vectors = await self._embedding_vectors(
            tuple(row.text for row in rows), cancellation
        )
        if vectors is None:
            return
        if cancellation.cancelled or len(vectors) != len(rows):
            return
        for row, vector in zip(rows, vectors, strict=True):
            if cancellation.cancelled:
                return
            try:
                await self._memory.update_embedding(
                    identity=row.identity,
                    embedding=vector,
                )
            except Exception:
                return

    async def _backfill(self, cancellation: CancellationToken) -> bool:
        rows = await self._memory.select_null_embedding_candidates(maximum_rows=32)
        if not rows or cancellation.cancelled:
            return False
        vectors = await self._embedding_vectors(
            tuple(row.text for row in rows), cancellation
        )
        if vectors is None:
            return False
        if cancellation.cancelled or len(vectors) != len(rows):
            return False
        updated = False
        for row, vector in zip(rows, vectors, strict=True):
            if cancellation.cancelled:
                break
            try:
                await self._memory.update_embedding(
                    identity=row.identity,
                    embedding=vector,
                )
            except Exception:
                break
            updated = True
        return updated

    async def _embedding_vectors(
        self,
        texts: tuple[str, ...],
        cancellation: CancellationToken,
    ) -> tuple[tuple[float, ...], ...] | None:
        embedding = asyncio.create_task(self._embedder.embed(texts))
        cancelled = asyncio.create_task(cancellation.wait())
        try:
            done, _pending = await asyncio.wait(
                (embedding, cancelled),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancelled in done:
                embedding.cancel()
                await asyncio.gather(embedding, return_exceptions=True)
                return None
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
            return embedding.result()
        except Exception:
            return None
        finally:
            if not embedding.done():
                embedding.cancel()
            if not cancelled.done():
                cancelled.cancel()
            await asyncio.gather(embedding, cancelled, return_exceptions=True)


@dataclass(frozen=True, slots=True)
class DreamerRunCompleted:
    run_id: RunId
    created_summary_ids: tuple[UUID, ...]
    removed_summary_ids: tuple[UUID, ...]
    metrics: RunMetrics


type DreamerRunOutcome = DreamerRunCompleted | BackgroundDeferred | None


class DreamerWorker:
    """Run one isolated summary mutation with a cancellable reasoning boundary."""

    def __init__(
        self,
        *,
        definition: AgentDefinition,
        plan: FrozenToolPlan,
        admission: RootTrackingAdmissionPort,
        provider: ProviderSessionPort,
        model_decisions: ModelJournalFactory,
        dispatcher_factory: Callable[[], MemoryReadDispatcherPort],
        memory: MemoryStore,
    ) -> None:
        self._definition = definition
        self._plan = plan
        self._admission = admission
        self._provider = provider
        self._model_decisions = model_decisions
        self._dispatcher_factory = dispatcher_factory
        self._memory = memory
        self._commit_in_progress = False
        self._foreground_waiting = False

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        if self._commit_in_progress:
            self._foreground_waiting = True
        else:
            cancellation.cancel()

    async def run_one(
        self,
        cancellation: CancellationToken,
    ) -> bool | BackgroundDeferred:
        outcome = await self.run_at(
            as_of=datetime.now(UTC),
            cancellation=cancellation,
        )
        if isinstance(outcome, BackgroundDeferred):
            return outcome
        return isinstance(outcome, DreamerRunCompleted)

    async def run_at(
        self,
        *,
        as_of: datetime,
        cancellation: CancellationToken,
        parent_admission: AdmissionToken | None = None,
    ) -> DreamerRunOutcome:
        if cancellation.cancelled or await self._memory.raw_memory_count() == 0:
            return None
        limits = self._definition.limits
        if parent_admission is None:
            reset_at = await self._admission.preflight_background(
                maximum_turns=limits.max_provider_turns,
                maximum_input_tokens=limits.max_provider_input_tokens,
                maximum_output_tokens=limits.max_provider_output_tokens,
            )
            if reset_at is not None:
                return BackgroundDeferred(reset_at)
        run_id = RunId(str(uuid4()))
        operation_id = "jarvis-dream:" + await self._memory.snapshot_revision()
        dispatcher = self._dispatcher_factory()
        decisions, as_of = await isolated_decisions(
            self._model_decisions, dispatcher, operation_id, as_of
        )
        job_input = HostInput(
            InputId(str(uuid5(NAMESPACE_URL, operation_id))),
            PromptSections(
                (
                    PromptSection(
                        PromptSectionKind("dream_job"),
                        (),
                        PromptText("Run one bounded memory-summary maintenance pass."),
                    ),
                )
            ),
            as_of,
        )
        try:
            outcome = await run_one_shot(
                decisions=decisions,
                run_id=run_id,
                definition=self._definition,
                inputs=(job_input,),
                as_of=as_of,
                plan=self._plan,
                source_sections=PromptSections(()),
                admission=self._admission,
                provider=self._provider,
                dispatcher=dispatcher,
                budget_factory=ExactToolBudgetFactory(),
                parent_admission=parent_admission,
                cancellation=cancellation,
            )
        except Exception:
            return None
        if (
            not isinstance(outcome, OneShotCompleted)
            or cancellation.cancelled
            or dispatcher.evidence.search_calls == 0
        ):
            return None
        try:
            result = DreamResult.model_validate(outcome.result)
            batch = SummaryMutationBatch(
                insertions=tuple(
                    SummaryInsertionCandidate(
                        text=item.text,
                        source_memory_ids=tuple(
                            UUID(identity) for identity in item.source_memory_ids
                        ),
                    )
                    for item in result.insertions
                ),
                remove_summary_ids=tuple(
                    UUID(identity) for identity in result.remove_summary_ids
                ),
            )
        except (TypeError, ValueError):
            return None
        if cancellation.cancelled:
            return None
        self._commit_in_progress = True
        self._foreground_waiting = False
        commit = None
        try:
            commit = await self._memory.apply_summary_mutations(batch=batch)
        except Exception:
            pass
        finally:
            self._commit_in_progress = False
            if self._foreground_waiting:
                cancellation.cancel()
            self._foreground_waiting = False
        if commit is None:
            return None
        completed = DreamerRunCompleted(
            run_id=run_id,
            created_summary_ids=tuple(item.id for item in commit.created),
            removed_summary_ids=commit.removed_summary_ids,
            metrics=outcome.metrics,
        )
        LOGGER.info(
            "Dreamer completed: turns=%d inserted=%d removed=%d",
            completed.metrics.provider_turns,
            len(completed.created_summary_ids),
            len(completed.removed_summary_ids),
        )
        return completed


def _recalled_id_sections(group: RemembererGroup) -> PromptSections:
    identities: list[dict[str, str]] = []
    for target in group.targets:
        recaller = target.trace.get("recaller")
        if not isinstance(recaller, dict):
            continue
        selected = cast("dict[str, object]", recaller).get("selected_memory_ids")
        if not isinstance(selected, list):
            continue
        for value in cast("list[object]", selected):
            if not isinstance(value, dict):
                continue
            item = cast("dict[str, object]", value)
            table_kind = item.get("table_kind")
            identifier = item.get("id")
            if not isinstance(table_kind, str) or not isinstance(identifier, str):
                continue
            identity = {"table_kind": table_kind, "id": identifier}
            if identity not in identities:
                identities.append(identity)
    if not identities:
        return PromptSections(())
    return PromptSections(
        (
            PromptSection(
                PromptSectionKind("recalled_memory_identities"),
                (),
                PromptText(json.dumps(identities, separators=(",", ":"))),
            ),
        )
    )


class ThreadRunner(Protocol):
    async def run(self, cancellation: CancellationToken) -> ServiceRunOutcome: ...

    async def settle_control(self, message_id: UUID, control: Control) -> bool: ...

    async def discard_recovered_session_reference(self) -> None: ...


class BackgroundWorkerPort(Protocol):
    async def run_one(
        self, cancellation: CancellationToken
    ) -> bool | BackgroundDeferred: ...

    def request_interrupt(self, cancellation: CancellationToken) -> None: ...


class JarvisThreadRunner:
    """One concrete invocation of the pinned kernel over PostgreSQL ports."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: MessageStore,
        admission: RollingAdmissionPort | RootTrackingAdmissionPort,
        kernel_runtime: KernelRuntime,
        model_decisions: ModelJournalFactory,
        definitions: (
            Slice1Definitions
            | Slice2Definitions
            | Slice3Definitions
            | Slice4Definitions
            | Slice5Definitions
            | Slice6Definitions
        ),
        history: PostgresCanonicalHistory,
        dispatcher_factory: Callable[[], ToolDispatchPort] = EmptySlice1Dispatcher,
        checkpoint_dispatcher_factory: Callable[
            [PostgresInputCheckpoint], ToolDispatchPort
        ]
        | None = None,
        memory: MemoryStore | None = None,
        memory_dispatcher_factory: Callable[[], MemoryReadDispatcherPort] | None = None,
        rememberer: RemembererWorker | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._admission = admission
        self._kernel_runtime = kernel_runtime
        self._model_decisions = model_decisions
        self._definitions = definitions
        self._history = history
        self._dispatcher_factory = dispatcher_factory
        self._checkpoint_dispatcher_factory = checkpoint_dispatcher_factory
        self._memory = memory
        self._memory_dispatcher_factory = memory_dispatcher_factory
        self._rememberer = rememberer
        if isinstance(
            definitions,
            (
                Slice3Definitions
                | Slice4Definitions
                | Slice5Definitions
                | Slice6Definitions
            ),
        ) and (
            not isinstance(admission, RootTrackingAdmissionPort)
            or memory is None
            or memory_dispatcher_factory is None
            or rememberer is None
        ):
            raise ValueError(
                "memory-enabled runner requires complete isolated memory composition"
            )
        self._checkpoint_lock = asyncio.Lock()
        self._checkpoint: PostgresInputCheckpoint | None = None

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        """Settle an idle control, or leave an active one for checkpoint polling."""

        value = _control_value(control)
        async with self._checkpoint_lock:
            checkpoint = self._checkpoint
            if checkpoint is None:
                await self._store.settle_control(
                    message_id=message_id,
                    source_conversation_id=str(self._settings.discord.channel_id),
                    control=value,
                )
                return True
            result = await checkpoint.settle_idle_control(
                message_id=message_id,
                control=value,
            )
            return result is not None

    async def discard_recovered_session_reference(self) -> None:
        await self._kernel_runtime.discard_recovered_session_reference(
            ThreadId(str(self._settings.discord.channel_id)),
            self._definitions.main,
        )

    async def run(self, cancellation: CancellationToken) -> ServiceRunOutcome:
        limits = self._definitions.main.limits
        reset_at = await self._admission.preflight(
            maximum_turns=limits.max_provider_turns,
            maximum_input_tokens=limits.max_provider_input_tokens,
            maximum_output_tokens=limits.max_provider_output_tokens,
        )
        if reset_at is not None:
            await self._store.record_admission_deferral(
                source_conversation_id=str(self._settings.discord.channel_id),
                reset_at=reset_at,
            )
            return PreflightDeferred(reset_at)

        run_id = RunId(str(uuid4()))
        thread_id = ThreadId(str(self._settings.discord.channel_id))
        turn_evidence = TurnEvidence()
        dispatcher: CapturingReadDispatcher | None = None

        def on_settlement(owner_message_ids: tuple[UUID, ...]) -> None:
            assert dispatcher is not None
            material_context = dispatcher.take_material_sections()
            if owner_message_ids and self._rememberer is not None:
                self._rememberer.enqueue(owner_message_ids, material_context)

        checkpoints = PostgresInputCheckpoint(
            store=self._store,
            thread_id=thread_id,
            run_id=run_id,
            interactive_plan=self._definitions.plans["main"],
            scheduled_wake_plan=self._definitions.plans["scheduled_wake"],
            maximum_batch_size=self._settings.maximum_batch_size,
            maximum_attempts=self._definitions.main.limits.max_no_progress_attempts,
            turn_evidence=turn_evidence,
            on_settlement=on_settlement,
        )
        dispatcher = CapturingReadDispatcher(
            self._checkpoint_dispatcher_factory(checkpoints)
            if self._checkpoint_dispatcher_factory is not None
            else self._dispatcher_factory(),
            turn_evidence,
        )
        recaller = None
        if isinstance(
            self._definitions,
            (
                Slice3Definitions
                | Slice4Definitions
                | Slice5Definitions
                | Slice6Definitions
            ),
        ):
            assert isinstance(self._admission, RootTrackingAdmissionPort)
            assert self._memory is not None
            assert self._memory_dispatcher_factory is not None
            recaller = IsolatedRecaller(
                definition=self._definitions.recaller,
                plan=self._definitions.plans["recaller"],
                admission=self._admission,
                provider=self._kernel_runtime.provider,
                dispatcher_factory=self._memory_dispatcher_factory,
                memory=self._memory,
                trace=self._store,
                model_decisions=self._model_decisions,
            )
        context = JarvisContextSource(
            thread_id,
            self._history,
            recaller=recaller,
            cancellation=cancellation,
            batch_clock=checkpoints if recaller is not None else None,
        )
        async with self._checkpoint_lock:
            if self._checkpoint is not None:
                raise RuntimeError("the Jarvis thread runner is already active")
            self._checkpoint = checkpoints
        try:
            outcome = await run_thread(
                decisions=self._model_decisions(dispatcher),
                run_id=run_id,
                thread_id=thread_id,
                owner_token=OwnerToken(str(self._settings.discord.owner_user_id)),
                definition=self._definitions.main,
                checkpoints=checkpoints,
                admission=self._admission,
                sessions=self._kernel_runtime.sessions,
                context_source=context,
                dispatcher=dispatcher,
                budget_factory=ExactToolBudgetFactory(),
                cancellation=cancellation,
            )
        finally:
            async with self._checkpoint_lock:
                self._checkpoint = None
        if checkpoints.consumed_message_ids:
            metrics = outcome.metrics
            await self._store.record_run_metrics(
                consumed_message_ids=checkpoints.consumed_message_ids,
                run_id=str(run_id),
                provider_turns=metrics.provider_turns,
                input_tokens=metrics.usage.input_tokens,
                output_tokens=metrics.usage.output_tokens,
                duration_seconds=metrics.duration_seconds,
            )
        return outcome


def _control_value(control: Control) -> Literal["stop", "pause", "resume"]:
    return control.value


class DiscordCursorPort(Protocol):
    async def latest_discord_owner_source_message_id(
        self,
        *,
        source_conversation_id: str,
    ) -> str | None: ...


class PendingControlPort(Protocol):
    async def pending_controls(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[PendingControl, ...]: ...


class IngressStore(
    PendingDeliveryStore,
    DiscordCursorPort,
    PendingControlPort,
    Protocol,
):
    async def insert_waking(
        self,
        *,
        role: Literal["owner", "host"],
        text: str,
        source: str,
        source_conversation_id: str,
        source_message_id: str,
        created_at: datetime,
        message_id: UUID | None = None,
    ) -> InboundInsert: ...

    async def circuit_is_open(self) -> bool: ...

    async def settle_recovered_control(
        self,
        *,
        message_id: UUID,
        source_conversation_id: str,
        control: Literal["stop", "pause"],
    ) -> object: ...


class GatewayPort(Protocol):
    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult: ...

    def typing(self) -> AbstractAsyncContextManager[None]: ...


class ScheduledWakeStore(Protocol):
    async def claim_next_due_schedule(
        self,
        *,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        now: datetime | None = None,
    ) -> ClaimedSchedule | ScheduleStateChanged | None: ...


class ActionRecoveryPort(Protocol):
    async def recover(self, *, allow_queued_execution: bool = True) -> int: ...


class JarvisService:
    """Serial host coordinator for Gateway ingress, kernel work, and delivery."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: IngressStore,
        paused: PausedState,
        delivery: CreateMessagePort,
        runner: ThreadRunner,
        background: BackgroundWorkerPort | None = None,
        dreamer: BackgroundWorkerPort | None = None,
        scheduled_wakes: ScheduledWakeStore | None = None,
        action_plan: FrozenToolPlan | None = None,
        action_recovery: ActionRecoveryPort | None = None,
        approval_handler: ApprovalActionHandler | None = None,
        gateway: GatewayPort | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        dream_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._store = store
        self._paused = paused
        self._delivery = delivery
        self._runner = runner
        self._background = background
        self._dreamer = dreamer
        self._scheduled_wakes = scheduled_wakes
        if (scheduled_wakes is None) != (action_plan is None):
            raise ValueError("scheduled wakes require exactly one current action plan")
        self._action_plan = action_plan
        self._action_recovery = action_recovery
        self._approval_handler = approval_handler
        self._gateway = gateway
        self._sleep = sleep
        self._dream_sleep = dream_sleep
        self._work = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._execution_mutex = asyncio.Lock()
        self._active_lock = asyncio.Lock()
        self._active_cancellation: CancellationToken | None = None
        self._active_background: BackgroundWorkerPort | None = None
        self._background_cancellation: CancellationToken | None = None
        self._reset_task: asyncio.Task[None] | None = None
        self._dream_timer_task: asyncio.Task[None] | None = None
        self._wake_timer: ProcessLocalWakeTimer | None = None
        self._wake_timer_task: asyncio.Task[None] | None = None
        self._wake_cancellation: CancellationToken | None = None
        self._dream_due = False

    def bind_gateway(self, gateway: GatewayPort) -> None:
        """Resolve the one callback cycle between the service and Gateway."""

        if self._gateway is not None:
            raise RuntimeError("the Discord Gateway is already bound")
        self._gateway = gateway

    def bind_wake_timer(self, timer: ProcessLocalWakeTimer) -> None:
        if self._wake_timer is not None or self._scheduled_wakes is None:
            raise RuntimeError("the scheduled-wake timer cannot be bound")
        self._wake_timer = timer

    async def receive_owner_message(self, incoming: DiscordOwnerMessage) -> None:
        """Persist/deduplicate ingress before applying host control."""

        async with self._active_lock:
            canonical_text = (
                incoming.control.value
                if incoming.control is not None
                else incoming.text
            )
            inserted = await self._store.insert_waking(
                role="owner",
                text=canonical_text,
                source="discord",
                source_conversation_id=incoming.source_conversation_id,
                source_message_id=incoming.source_message_id,
                created_at=incoming.created_at,
            )
            if not inserted.inserted:
                return

            active = self._active_cancellation
            background = self._background_cancellation
            background_worker = self._active_background
            if background is not None and background_worker is not None:
                background_worker.request_interrupt(background)
            if incoming.control in {Control.STOP, Control.PAUSE}:
                await self._paused.set_paused(True)
                if active is not None:
                    active.cancel()
            elif incoming.control is Control.RESUME:
                await self._paused.set_paused(False)

        self._work.set()

    async def receive_approval_interaction(
        self,
        event: discord.Interaction,
        interaction: DiscordApprovalInteraction,
    ) -> None:
        """Claim one configured component before serial effect execution."""

        if self._approval_handler is None or await self._paused.is_paused():
            return
        claimed = await self._approval_handler.claim_and_acknowledge(
            event,
            interaction,
        )
        if claimed is None:
            return
        async with self._execution_mutex:
            cancellation = CancellationToken()
            async with self._active_lock:
                self._active_cancellation = cancellation
                if await self._paused.is_paused():
                    cancellation.cancel()
            if cancellation.cancelled:
                async with self._active_lock:
                    if self._active_cancellation is cancellation:
                        self._active_cancellation = None
                self._work.set()
                return
            try:
                await self._approval_handler.complete(claimed, cancellation)
            finally:
                async with self._active_lock:
                    if self._active_cancellation is cancellation:
                        self._active_cancellation = None
            self._work.set()

    async def gateway_ready(self) -> CatchUpResult:
        """Boundedly catch up from the canonical Discord watermark."""

        source_conversation_id = str(self._settings.discord.channel_id)
        after = await self._store.latest_discord_owner_source_message_id(
            source_conversation_id=source_conversation_id
        )
        result = await self._require_gateway().catch_up(after)
        self._work.set()
        return result

    async def flush_delivery(self) -> DeliveryFlushResult:
        selected = 0
        delivered = 0
        while True:
            result = await flush_pending_deliveries(
                store=self._store,
                delivery=self._delivery,
                source_conversation_id=str(self._settings.discord.channel_id),
                limit=self._settings.delivery_batch_size,
            )
            selected += result.selected
            delivered += result.delivered
            if result.failure is not None:
                LOGGER.warning(
                    "Discord delivery stopped: kind=%s attempts=%d "
                    "status=%s ambiguous=%s",
                    result.failure.kind.value,
                    result.failure.attempts,
                    result.failure.http_status,
                    result.failure.ambiguous,
                )
                return DeliveryFlushResult(selected, delivered, result.failure)
            if result.selected < self._settings.delivery_batch_size:
                if delivered:
                    LOGGER.info("Discord delivery completed: count=%d", delivered)
                return DeliveryFlushResult(selected, delivered, None)

    async def run_worker(self) -> None:
        """Run until shutdown, draining serial work and pending delivery."""

        if self._dreamer is not None:
            self._dream_timer_task = asyncio.create_task(
                self._dream_timer(),
                name="jarvis-dream-timer",
            )
        if self._wake_timer is not None:
            self._wake_cancellation = CancellationToken()
            self._wake_timer_task = asyncio.create_task(
                self._wake_timer.run(self._wake_cancellation),
                name="jarvis-scheduled-wake-timer",
            )
            self._wake_timer_task.add_done_callback(lambda _task: self._work.set())
        try:
            while not self._shutdown.is_set():
                await self._work.wait()
                self._work.clear()
                if self._wake_timer_task is not None and self._wake_timer_task.done():
                    self._wake_timer_task.result()
                    raise RuntimeError("the scheduled-wake timer stopped unexpectedly")
                await self._drain()
        finally:
            if self._dream_timer_task is not None:
                self._dream_timer_task.cancel()
                await asyncio.gather(
                    self._dream_timer_task,
                    return_exceptions=True,
                )
                self._dream_timer_task = None
            if self._wake_cancellation is not None:
                self._wake_cancellation.cancel()
            if self._wake_timer_task is not None:
                await asyncio.gather(self._wake_timer_task, return_exceptions=True)
                self._wake_timer_task = None
                self._wake_cancellation = None

    def request_work(self) -> None:
        self._work.set()

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._work.set()
        if (
            self._background_cancellation is not None
            and self._active_background is not None
        ):
            self._active_background.request_interrupt(self._background_cancellation)
        if self._reset_task is not None:
            self._reset_task.cancel()
        if self._dream_timer_task is not None:
            self._dream_timer_task.cancel()
        if self._wake_cancellation is not None:
            self._wake_cancellation.cancel()

    async def _drain(self) -> None:
        async with self._execution_mutex:
            await self.flush_delivery()
            while not self._shutdown.is_set():
                controls = await self._store.pending_controls(
                    source_conversation_id=str(self._settings.discord.channel_id),
                    limit=1,
                )
                if controls:
                    pending = controls[0]
                    control = Control(pending.control)
                    if control is Control.RESUME:
                        await self._paused.set_paused(False)
                        if not await self._runner.settle_control(
                            pending.message_id,
                            control,
                        ):
                            return
                        await self.flush_delivery()
                        continue
                    await self._paused.set_paused(True)
                    if pending.requires_recovery_run:
                        await self._runner.discard_recovered_session_reference()
                        await self._store.settle_recovered_control(
                            message_id=pending.message_id,
                            source_conversation_id=str(
                                self._settings.discord.channel_id
                            ),
                            control=cast(
                                Literal["stop", "pause"],
                                pending.control,
                            ),
                        )
                    else:
                        if not await self._runner.settle_control(
                            pending.message_id,
                            control,
                        ):
                            return
                    await self.flush_delivery()
                    continue
                inactive = (
                    await self._paused.is_paused()
                    or await self._store.circuit_is_open()
                )
                recovered_actions = await self._recover_actions(
                    allow_queued_execution=not inactive
                )
                if inactive:
                    return
                if recovered_actions:
                    continue
                if self._scheduled_wakes is not None:
                    assert self._action_plan is not None
                    claimed = await self._scheduled_wakes.claim_next_due_schedule(
                        plan=self._action_plan,
                        source_conversation_id=str(self._settings.discord.channel_id),
                    )
                    if claimed is not None:
                        if self._wake_timer is not None:
                            self._wake_timer.notify_changed()
                        if isinstance(claimed, ScheduleStateChanged):
                            await self._recover_actions(allow_queued_execution=False)
                        continue
                cancellation = CancellationToken()
                async with self._active_lock:
                    self._active_cancellation = cancellation
                try:
                    async with self._require_gateway().typing():
                        outcome = await self._runner.run(cancellation)
                finally:
                    async with self._active_lock:
                        self._active_cancellation = None
                await self.flush_delivery()

                if isinstance(outcome, PreflightDeferred):
                    self._schedule_reset(outcome.until)
                    return
                LOGGER.info(
                    "Kernel run completed: type=%s turns=%d consumed=%s",
                    outcome.type,
                    outcome.metrics.provider_turns,
                    outcome.metrics.input_consumed,
                )
                if isinstance(outcome, ThreadDeferred):
                    self._schedule_reset(outcome.until)
                    return
                if isinstance(outcome, ThreadNoWork):
                    background = await self._run_background_once(self._background)
                    if isinstance(background, BackgroundDeferred):
                        self._schedule_reset(background.until)
                        return
                    if background:
                        continue
                    if self._work.is_set() or not self._dream_due:
                        return
                    dream = await self._run_background_once(self._dreamer)
                    if isinstance(dream, BackgroundDeferred):
                        self._schedule_reset(dream.until)
                        return
                    self._dream_due = False
                    if dream:
                        continue
                    return
                if (
                    isinstance(outcome, ThreadStopped)
                    and outcome.type is ThreadStopKind.preempted
                ):
                    continue
                if (
                    isinstance(outcome, ThreadStopped)
                    and not outcome.metrics.input_consumed
                ):
                    return

    async def _recover_actions(self, *, allow_queued_execution: bool) -> int:
        if self._action_recovery is None:
            return 0
        recovered_actions = await self._action_recovery.recover(
            allow_queued_execution=allow_queued_execution
        )
        if recovered_actions:
            LOGGER.warning(
                "Recovered interrupted actions: count=%d",
                recovered_actions,
            )
            await self.flush_delivery()
        return recovered_actions

    async def _run_background_once(
        self,
        worker: BackgroundWorkerPort | None,
    ) -> bool | BackgroundDeferred:
        if worker is None or self._work.is_set():
            return False
        cancellation = CancellationToken()
        async with self._active_lock:
            self._active_background = worker
            self._background_cancellation = cancellation
            if self._work.is_set():
                cancellation.cancel()
        try:
            try:
                return await worker.run_one(cancellation)
            except Exception:
                return False
        finally:
            async with self._active_lock:
                if self._background_cancellation is cancellation:
                    self._background_cancellation = None
                    self._active_background = None

    async def _dream_timer(self) -> None:
        while not self._shutdown.is_set():
            await self._dream_sleep(self._settings.dream_interval_seconds)
            if self._shutdown.is_set():
                return
            self._dream_due = True
            self._work.set()

    def _schedule_reset(self, reset_at: datetime) -> None:
        delay = max(0.0, (reset_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())

        async def signal() -> None:
            await self._sleep(delay)
            self._work.set()

        if self._reset_task is not None:
            self._reset_task.cancel()
        self._reset_task = asyncio.create_task(signal(), name="jarvis-admission-reset")

    def _require_gateway(self) -> GatewayPort:
        if self._gateway is None:
            raise RuntimeError("the Discord Gateway is not bound")
        return self._gateway


__all__ = [
    "ActionRecoveryPort",
    "BackgroundDeferred",
    "DeliveryFlushResult",
    "DiscordCursorPort",
    "DreamerRunCompleted",
    "DreamerWorker",
    "JarvisService",
    "JarvisThreadRunner",
    "PendingControlPort",
    "PreflightDeferred",
    "RemembererWorker",
    "ScheduledWakeStore",
    "flush_pending_deliveries",
]

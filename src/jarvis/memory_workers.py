"""Isolated memory workers and their transactional commit boundaries."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from llm_agent_kernel import (
    AdmissionToken,
    AgentDefinition,
    CancellationToken,
    HostInput,
    InputId,
    OneShotCompleted,
    ProviderSessionPort,
    RunId,
    RunMetrics,
    run_one_shot,
)
from llm_tools import (
    FrozenToolPlan,
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
)

from jarvis.admission import ExactToolBudgetFactory, RootTrackingAdmissionPort
from jarvis.context import MemoryReadDispatcherPort
from jarvis.decisions import ModelJournalFactory, isolated_decisions
from jarvis.definitions import DreamResult, RememberResult
from jarvis.memory import (
    MemoryStore,
    RemembererGroup,
    RemembererRunSummary,
    StoredMemory,
    SummaryInsertionCandidate,
    SummaryMutationBatch,
)
from jarvis.messages import MessageStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackgroundDeferred:
    until: datetime


class EmbeddingPort(Protocol):
    async def embed(self, inputs: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


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
                rows = await self._memory.select_null_embedding_candidates(
                    maximum_rows=32
                )
                if not rows or cancellation.cancelled:
                    return False
                return await self._embed_rows(rows, cancellation)
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
        await self._embed_rows(commit.created, cancellation)
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

    async def _embed_rows(
        self,
        rows: tuple[StoredMemory, ...],
        cancellation: CancellationToken,
    ) -> bool:
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

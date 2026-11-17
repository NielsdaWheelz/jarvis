"""Serial chronological compression, indexing and quiet disposable dreaming."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from llm_agent_kernel import (
    AgentDefinition,
    CancellationToken,
    ContextLimitExceeded,
    HostInput,
    InputId,
    OneShotCompleted,
    OneShotStopKind,
    ProviderSessionPort,
    RunId,
    TransientModelDecisions,
    bootstrap_context,
    run_one_shot,
)
from llm_agent_kernel.events import EventKind, KernelEvent
from llm_tools import (
    FrozenToolPlan,
    PromptJson,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    canonical_json_bytes,
)
from provider_runtime.agent_runtime import thaw_json_value
from pydantic import JsonValue, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import (
    CompactionTask,
    DreamResult,
    MemoryError,
    Node,
    render_dream_view,
)
from universal_memory.policy import (
    COMPACTION_CALLS,
    COMPACTION_FAILURES,
    COMPACTION_RETRY_SECONDS,
    NODE_HARD_BYTES,
    NODE_TARGET_BYTES,
    clip_utf8,
)

from jarvis.admission import ExactToolBudgetFactory, JarvisOwner
from jarvis.db import message
from jarvis.definitions import CompactionResult
from jarvis.embeddings import MAX_EMBEDDING_BATCH_SIZE, EmbeddingBusy, EmbeddingFailure
from jarvis.kernel import EmptyToolDispatcher
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_service import MemoryService

LOGGER = logging.getLogger(__name__)


class _CompactionFailureEvents:
    def emit(self, event: KernelEvent) -> None:
        attributes = {
            item.name: item.value
            for item in event.attributes
            if item.name
            in {
                "failure_site",
                "failure_kind",
                "failure_code",
                "failure_frame_count",
                "failure_module_0",
                "failure_function_0",
                "failure_line_0",
                "failure_module_1",
                "failure_function_1",
                "failure_line_1",
            }
        }
        if event.kind is EventKind.outcome and attributes.get("failure_site") in {
            "bootstrap_context",
            "provider_configuration",
            "kernel_configuration",
        }:
            LOGGER.warning(
                "compaction kernel failure %s",
                canonical_json_bytes(
                    {"run_id": str(event.run_id), **attributes}
                ).decode("utf-8"),
            )


class MemoryWorker:
    def __init__(
        self,
        *,
        definition: AgentDefinition,
        plan: FrozenToolPlan,
        owner: JarvisOwner,
        provider: ProviderSessionPort,
        memory: MemoryService,
    ) -> None:
        self.definition, self.plan = definition, plan
        self.owner, self.provider, self.memory = owner, provider, memory

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        cancellation.cancel()

    async def ensure_ready(self, cutoff: int, cancellation: CancellationToken) -> None:
        while not cancellation.cancelled:
            try:
                await self.memory.library.main_view(cutoff)
                return
            except MemoryError as error:
                if error.code != "unavailable":
                    raise
            if not await self.compact_one(cancellation, cutoff=cutoff):
                if not cancellation.cancelled:
                    raise MemoryError("compaction_blocked")
                return

    async def compact_one(
        self, cancellation: CancellationToken, *, cutoff: int | None = None
    ) -> bool:
        async with self.memory.database.begin() as connection:
            batch = await self.memory.library.next_compaction(connection, cutoff=cutoff)
            control = await connection.scalar(
                select(func.max(message.c.control_sequence)).where(
                    message.c.source_conversation_id == self.owner.scope_id
                )
            )
        if batch is None or cancellation.cancelled:
            return False
        pending: list[CompactionTask] = list(batch.tasks)
        calls = {(task.start, task.count): 0 for task in pending}
        failures = {(task.start, task.count): 0 for task in pending}
        completed: dict[tuple[int, int], str] = {}
        feedback: dict[str, JsonValue] = {}
        failed: CompactionTask | None = None
        failure = "invalid_completion"
        permit = self.owner.permit("jarvis-compaction:" + str(uuid4()))
        as_of = datetime.now(UTC)
        while pending:
            if cancellation.cancelled:
                return False
            await self.owner.require_current(permit)
            run_id = RunId(str(uuid4()))
            inputs = (HostInput(InputId(str(run_id)), PromptSections(()), as_of),)
            selected: list[CompactionTask] = []
            source = None
            for task in pending:
                trial: list[CompactionTask] = [*selected, task]
                addressed = {
                    f"{item.start}+{item.count}": feedback[f"{item.start}+{item.count}"]
                    for item in trial
                    if f"{item.start}+{item.count}" in feedback
                }
                request = batch.model_copy(update={"tasks": tuple(trial), "copies": ()})
                proposed = PromptSections(
                    (
                        PromptSection(
                            PromptSectionKind("historical_memory_view"),
                            (),
                            PromptText(batch.context),
                        ),
                        PromptSection(
                            PromptSectionKind("compaction_source"),
                            (),
                            PromptJson(request.model_input(addressed)),
                        ),
                    )
                )
                try:
                    bootstrap_context(
                        self.definition, inputs, as_of, self.plan, proposed
                    )
                except ContextLimitExceeded:
                    break
                selected, source = trial, proposed
            if source is None:
                raise MemoryError("compaction_blocked")
            for task in selected:
                calls[task.start, task.count] += 1
            outcome = await run_one_shot(
                decisions=TransientModelDecisions(),
                run_id=run_id,
                definition=self.definition,
                inputs=inputs,
                as_of=as_of,
                plan=self.plan,
                source_sections=source,
                owner=self.owner,
                permit=permit,
                provider=self.provider,
                dispatcher=EmptyToolDispatcher(),
                budget_factory=ExactToolBudgetFactory(),
                cancellation=cancellation,
                event_sink=_CompactionFailureEvents(),
            )
            if cancellation.cancelled:
                return False
            transient = not isinstance(outcome, OneShotCompleted)
            if not isinstance(outcome, OneShotCompleted):
                if outcome.type is OneShotStopKind.cancelled:
                    return False
                if outcome.type not in {
                    OneShotStopKind.provider_error,
                    OneShotStopKind.model_decision_uncertain,
                }:
                    failed = selected[0]
                    LOGGER.warning(
                        "compaction rejected: run_id=%s start=%s count=%s "
                        "reason=kernel_stopped stop_kind=%s",
                        run_id,
                        failed.start,
                        failed.count,
                        outcome.type.value,
                    )
                    break
                for task in selected:
                    address = (task.start, task.count)
                    failures[address] += 1
                    if failures[address] >= COMPACTION_FAILURES:
                        failed, failure = task, "inference_failed"
                        break
            else:
                try:
                    result = CompactionResult.model_validate_json(
                        canonical_json_bytes(thaw_json_value(outcome.result))
                    )
                except ValueError:
                    failed = selected[0]
                    LOGGER.warning(
                        "compaction rejected: run_id=%s start=%s count=%s "
                        "reason=result_schema",
                        run_id,
                        failed.start,
                        failed.count,
                    )
                    break
                addresses = {(node.start, node.count) for node in result.nodes}
                if len(addresses) != len(result.nodes) or addresses != {
                    (task.start, task.count) for task in selected
                }:
                    failed = selected[0]
                    LOGGER.warning(
                        "compaction rejected: run_id=%s start=%s count=%s reason=%s",
                        run_id,
                        failed.start,
                        failed.count,
                        "address_duplicate"
                        if len(addresses) != len(result.nodes)
                        else "address_set_mismatch",
                    )
                    break
                for node in result.nodes:
                    address = (node.start, node.count)
                    value = node.text.strip()
                    size = len(value.encode())
                    if size <= NODE_HARD_BYTES:
                        completed[address] = value
                    else:
                        feedback[f"{node.start}+{node.count}"] = {
                            "measured_bytes": size,
                            "candidate": value,
                            "target_cut": clip_utf8(value, NODE_TARGET_BYTES),
                        }
            if failed is not None:
                break
            for task in selected:
                address = (task.start, task.count)
                if address not in completed and calls[address] >= COMPACTION_CALLS:
                    failed = task
                    failure = "inference_failed" if transient else "candidate_too_large"
                    break
            if failed is not None:
                break
            pending = [
                task for task in pending if (task.start, task.count) not in completed
            ]
            if transient and pending:
                try:
                    await asyncio.wait_for(
                        cancellation.wait(), COMPACTION_RETRY_SECONDS
                    )
                    return False
                except TimeoutError:
                    pass
        await self.owner.require_current(permit)
        async with self.memory.database.begin() as connection:
            latest = await connection.scalar(
                select(func.max(message.c.control_sequence)).where(
                    message.c.source_conversation_id == self.owner.scope_id
                )
            )
            if cancellation.cancelled or latest != control:
                return False
            if failed is not None:
                await self.memory.library.park_compaction(connection, failed, failure)
                return False
            await self.memory.library.complete_compaction(
                connection,
                batch,
                tuple(
                    Node(
                        start=task.start,
                        count=task.count,
                        text=completed[task.start, task.count],
                    )
                    for task in batch.tasks
                ),
            )
        return True

    async def run_one(self, cancellation: CancellationToken) -> bool:
        try:
            if cancellation.cancelled:
                return False
            if await self.memory.project_pending():
                return True
            if await self.compact_one(cancellation):
                return True
            if cancellation.cancelled:
                return False
            return await self.index_one(cancellation)
        except (MemoryError, SQLAlchemyError) as error:
            LOGGER.warning(
                "memory background did not complete: type=%s", type(error).__name__
            )
            return False

    async def index_one(self, cancellation: CancellationToken) -> bool:
        rows = await self.memory.library.embedding_candidates(MAX_EMBEDDING_BATCH_SIZE)
        if not rows or cancellation.cancelled:
            return False
        permit = self.owner.permit("jarvis-memory-index:" + str(uuid4()))
        await self.owner.require_current(permit)
        try:
            vectors = await self.memory.embedder.embed(tuple(row.text for row in rows))
        except (EmbeddingBusy, EmbeddingFailure):
            return False
        if len(vectors) != len(rows):
            raise EmbeddingFailure("embedding result count differs")
        if cancellation.cancelled:
            return False
        await self.owner.require_current(permit)
        async with self.memory.database.begin() as connection:
            if cancellation.cancelled:
                return False
            for row, vector in zip(rows, vectors, strict=True):
                await self.memory.library.update_embedding(
                    connection, row.reference, vector
                )
        return True


@dataclass(frozen=True, slots=True)
class DreamerRunCompleted:
    run_id: str
    created_note_ids: tuple[UUID, ...]
    seed_start: int
    seed_end: int
    provider_turns: int


class DreamerWorker:
    def __init__(
        self,
        *,
        definition: AgentDefinition,
        plan: FrozenToolPlan,
        owner: JarvisOwner,
        provider: ProviderSessionPort,
        memory: MemoryService,
        compactor: MemoryWorker,
        owner_timezone: str,
        nightly_time: time,
    ) -> None:
        self.definition, self.plan = definition, plan
        self.owner, self.provider, self.memory = owner, provider, memory
        self.compactor = compactor
        self.timezone, self.nightly_time = ZoneInfo(owner_timezone), nightly_time

    def request_interrupt(self, cancellation: CancellationToken) -> None:
        cancellation.cancel()

    async def run_one(self, cancellation: CancellationToken) -> bool:
        try:
            completed = await self.run_at(
                as_of=datetime.now(UTC), cancellation=cancellation, nightly=True
            )
        except (MemoryError, SQLAlchemyError) as error:
            LOGGER.warning("dream did not complete: type=%s", type(error).__name__)
            return False
        return completed is not None

    async def run_at(
        self,
        *,
        as_of: datetime,
        cancellation: CancellationToken,
        nightly: bool = False,
    ) -> DreamerRunCompleted | None:
        if cancellation.cancelled:
            return None
        run_id = str(uuid4())
        permit = self.owner.permit("jarvis-dream:" + run_id)
        await self.owner.require_current(permit)
        async with self.memory.database.begin() as connection:
            control = await connection.scalar(
                select(func.max(message.c.control_sequence)).where(
                    message.c.source_conversation_id == self.owner.scope_id
                )
            )
            if nightly:
                local = as_of.astimezone(self.timezone)
                occurrence = datetime.combine(
                    local.date(), self.nightly_time, self.timezone
                )
                if occurrence > local:
                    occurrence = datetime.combine(
                        local.date() - timedelta(days=1),
                        self.nightly_time,
                        self.timezone,
                    )
                if not await self.memory.library.claim_nightly(
                    connection, occurrence, attempted_at=as_of
                ):
                    return None
        pending = await self.memory.pending_publication()
        await self.memory.project_pending(pending)
        cutoff = await self.memory.library.cutoff()
        await self.compactor.ensure_ready(cutoff, cancellation)
        if cancellation.cancelled:
            return None
        seed = await self.memory.library.dream_input(cutoff)
        if seed.seed_start == seed.seed_end:
            return DreamerRunCompleted(run_id, (), seed.seed_start, seed.seed_end, 0)
        result, turns = DreamResult(notes=()), 0
        dispatcher = MemoryToolDispatcher(cutoff=cutoff)
        if seed.nodes:
            sections = [
                PromptSection(
                    PromptSectionKind("historical_memory_view"),
                    (),
                    PromptText(
                        render_dream_view(seed.nodes, seed.seed_start, seed.seed_end)
                    ),
                )
            ]
            if seed.sample:
                sections.append(
                    PromptSection(
                        PromptSectionKind("historical_memory_view"),
                        (),
                        PromptJson(
                            [item.model_dump(mode="json") for item in seed.sample]
                        ),
                    )
                )
            source = PromptSections(tuple(sections))
            outcome = await run_one_shot(
                decisions=TransientModelDecisions(),
                run_id=RunId(run_id),
                definition=self.definition,
                inputs=(HostInput(InputId(run_id), PromptSections(()), as_of),),
                as_of=as_of,
                plan=self.plan,
                source_sections=source,
                owner=self.owner,
                permit=permit,
                provider=self.provider,
                dispatcher=dispatcher,
                budget_factory=ExactToolBudgetFactory(),
                cancellation=cancellation,
            )
            if not isinstance(outcome, OneShotCompleted) or cancellation.cancelled:
                return None
            try:
                result = DreamResult.model_validate_json(
                    canonical_json_bytes(thaw_json_value(outcome.result))
                )
            except ValidationError:
                LOGGER.warning("dream did not complete: code=invalid_result")
                return None
            turns = outcome.metrics.provider_turns
        await self.owner.require_current(permit)
        async with self.memory.database.begin() as connection:
            latest = await connection.scalar(
                select(func.max(message.c.control_sequence)).where(
                    message.c.source_conversation_id == self.owner.scope_id
                )
            )
            if cancellation.cancelled or latest != control:
                return None
            identifiers = await self.memory.library.complete_dream(
                connection,
                seed,
                result,
                dispatcher.references,
            )
        return DreamerRunCompleted(
            run_id,
            tuple(item.id for item in identifiers),
            seed.seed_start,
            seed.seed_end,
            turns,
        )

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
    HostInput,
    InputId,
    OneShotCompleted,
    OneShotStopKind,
    ProviderSessionPort,
    RunId,
    TransientModelDecisions,
    run_one_shot,
)
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
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import DreamResult, MemoryError, render_dream_view
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
            task = await self.memory.library.next_compaction(connection, cutoff=cutoff)
            control = await connection.scalar(
                select(func.max(message.c.control_sequence)).where(
                    message.c.source_conversation_id == self.owner.scope_id
                )
            )
        if task is None or cancellation.cancelled:
            return False
        candidate = task.free_text
        failure = "invalid_completion"
        permit = self.owner.permit("jarvis-compaction:" + str(uuid4()))
        as_of = datetime.now(UTC)
        if candidate is None:
            shortest: str | None = None
            feedback: dict[str, object] = {}
            failures = 0
            for _ in range(COMPACTION_CALLS):
                if cancellation.cancelled:
                    return False
                await self.owner.require_current(permit)
                run_id = RunId(str(uuid4()))
                source = PromptSections(
                    (
                        PromptSection(
                            PromptSectionKind("compaction_source"),
                            (),
                            PromptJson(
                                {
                                    "start": task.start,
                                    "count": task.count,
                                    "source": task.source,
                                    "ruler": task.ruler,
                                    "size_feedback": feedback,
                                }
                            ),
                        ),
                        PromptSection(
                            PromptSectionKind("historical_memory_view"),
                            (),
                            PromptText(task.context),
                        ),
                    )
                )
                outcome = await run_one_shot(
                    decisions=TransientModelDecisions(),
                    run_id=run_id,
                    definition=self.definition,
                    inputs=(
                        HostInput(InputId(str(run_id)), PromptSections(()), as_of),
                    ),
                    as_of=as_of,
                    plan=self.plan,
                    source_sections=source,
                    owner=self.owner,
                    permit=permit,
                    provider=self.provider,
                    dispatcher=EmptyToolDispatcher(),
                    budget_factory=ExactToolBudgetFactory(),
                    cancellation=cancellation,
                )
                if cancellation.cancelled:
                    return False
                if not isinstance(outcome, OneShotCompleted):
                    if outcome.type is OneShotStopKind.cancelled:
                        return False
                    if outcome.type not in {
                        OneShotStopKind.provider_error,
                        OneShotStopKind.model_decision_uncertain,
                    }:
                        shortest = None
                        failure = "invalid_completion"
                        break
                    failures += 1
                    failure = "inference_failed"
                    if failures >= COMPACTION_FAILURES:
                        shortest = None
                        break
                    try:
                        await asyncio.wait_for(
                            cancellation.wait(), COMPACTION_RETRY_SECONDS
                        )
                        return False
                    except TimeoutError:
                        continue
                try:
                    value = CompactionResult.model_validate_json(
                        canonical_json_bytes(thaw_json_value(outcome.result))
                    ).text.strip()
                except ValidationError:
                    shortest = None
                    failure = "invalid_completion"
                    break
                size = len(value.encode())
                if shortest is None or size < len(shortest.encode()):
                    shortest = value
                if size <= NODE_TARGET_BYTES:
                    break
                feedback = {
                    "measured_bytes": size,
                    "candidate": value,
                    "target_cut": clip_utf8(value, NODE_TARGET_BYTES),
                }
                failure = "candidate_too_large"
            candidate = (
                shortest
                if shortest is not None and len(shortest.encode()) <= NODE_HARD_BYTES
                else None
            )
        await self.owner.require_current(permit)
        async with self.memory.database.begin() as connection:
            latest = await connection.scalar(
                select(func.max(message.c.control_sequence)).where(
                    message.c.source_conversation_id == self.owner.scope_id
                )
            )
            if cancellation.cancelled or latest != control:
                return False
            if candidate is None:
                await self.memory.library.park_compaction(connection, task, failure)
                return False
            await self.memory.library.complete_compaction(connection, task, candidate)
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
                        PromptText(
                            canonical_json_bytes(
                                [item.model_dump(mode="json") for item in seed.sample]
                            ).decode()
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

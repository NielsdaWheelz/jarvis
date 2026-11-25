"""Serial chronological compression and quiet disposable dreaming."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from time import perf_counter
from typing import cast
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
from universal_memory.schema import memory_state

from jarvis.admission import ExactToolBudgetFactory, JarvisOwner
from jarvis.db import message
from jarvis.definitions import COMPACTION_FIELDS
from jarvis.kernel import CodexBlocked, CodexStandby, EmptyToolDispatcher
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_service import MemoryService
from jarvis.messages import latest_control

LOGGER = logging.getLogger(__name__)


class _MemoryFailureEvents:
    def __init__(self, slots: tuple[tuple[str, CompactionTask], ...] = ()) -> None:
        self.slots = slots

    def emit(self, event: KernelEvent) -> None:
        if event.kind is EventKind.validation and self.slots:
            validation = {item.name: item.value for item in event.attributes}
            if validation.get("valid") is not False:
                return
            fields: list[JsonValue] = []
            for index, (name, task) in enumerate(self.slots):
                code = validation.get(f"field_{index}")
                if code is not None:
                    fields.append(
                        {
                            "field": name,
                            "start": task.start,
                            "count": task.count,
                            "code": code,
                        }
                    )
            data = {
                key: validation[key]
                for key in ("failure_stage", "extra_fields", "unmapped")
                if key in validation
            }
            LOGGER.warning(
                "compaction invalid form %s",
                canonical_json_bytes(
                    {"run_id": str(event.run_id), **data, "fields": fields}
                ).decode("utf-8"),
            )
            return
        if event.kind is not EventKind.outcome:
            return
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
        if attributes.get("failure_site") not in {
            "bootstrap_context",
            "provider_configuration",
            "kernel_configuration",
        }:
            budget_limit = next(
                (
                    item.value
                    for item in event.attributes
                    if item.name == "budget_limit"
                ),
                None,
            )
            if budget_limit not in {
                "provider_turns",
                "cooperative_seconds",
                "provider_input_tokens",
                "provider_output_tokens",
                "native_turn_timeout",
            }:
                return
            attributes = {"budget_limit": budget_limit}
        LOGGER.warning(
            "memory kernel failure %s",
            canonical_json_bytes({"run_id": str(event.run_id), **attributes}).decode(
                "utf-8"
            ),
        )


class MemoryWorker:
    def __init__(
        self,
        *,
        definitions: tuple[AgentDefinition, ...],
        plan: FrozenToolPlan,
        owner: JarvisOwner,
        provider: ProviderSessionPort,
        memory: MemoryService,
        standby: CodexStandby,
    ) -> None:
        self.definitions, self.plan = definitions, plan
        self.owner, self.provider, self.memory = owner, provider, memory
        self.standby = standby

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
        control_sequence = latest_control(self.owner.scope_id).with_only_columns(
            message.c.control_sequence
        )
        prepare_requested = perf_counter()
        async with self.memory.database.begin() as connection:
            prepare_started = perf_counter()
            batch = await self.memory.library.next_compaction(connection, cutoff=cutoff)
            control = await connection.scalar(control_sequence)
        if batch is None or cancellation.cancelled:
            return False
        prepare_finished = perf_counter()
        free_leaves = sum(copy.count == 1 for copy in batch.copies)
        inferred_leaves = sum(task.count == 1 for task in batch.tasks)
        counts = (
            f"free_leaves={free_leaves} free_parents={len(batch.copies) - free_leaves} "
            f"inferred_leaves={inferred_leaves} "
            f"inferred_parents={len(batch.tasks) - inferred_leaves}"
        )
        LOGGER.info(
            "compaction prepared: writer_wait_ms=%.3f elapsed_ms=%.3f %s",
            (prepare_started - prepare_requested) * 1000,
            (prepare_finished - prepare_started) * 1000,
            counts,
        )
        pending: tuple[CompactionTask, ...] = batch.tasks
        calls = {(task.start, task.count): 0 for task in pending}
        failures = {(task.start, task.count): 0 for task in pending}
        completed: dict[tuple[int, int], str] = {}
        feedback: dict[tuple[int, int], JsonValue] = {}
        park: tuple[CompactionTask, str] | None = None
        correction_spent = False
        permit = self.owner.permit("jarvis-compaction:" + str(uuid4()))
        as_of = datetime.now(UTC)
        if batch.copies:
            await self.owner.require_current(permit)
            async with self.memory.database.begin() as connection:
                latest = await connection.scalar(control_sequence)
                if cancellation.cancelled or latest != control:
                    return False
                await self.memory.library.complete_compaction(
                    connection, batch.model_copy(update={"tasks": ()}), ()
                )
                if cancellation.cancelled:
                    await connection.rollback()
                    return False
            if not pending:
                return True
            batch = batch.model_copy(update={"copies": ()})
        selected = await self.standby.choose_codex("compactor")
        if isinstance(selected, CodexBlocked):
            return False
        while pending:
            if cancellation.cancelled:
                return False
            run_id = RunId(str(uuid4()))
            inputs = (HostInput(InputId(str(run_id)), PromptSections(()), as_of),)
            packet = None
            for arity in range(1, len(pending) + 1):
                definition = replace(
                    self.definitions[arity - 1], provider=selected.provider
                )
                slots = tuple(
                    zip(COMPACTION_FIELDS[:arity], pending[:arity], strict=True)
                )
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
                            PromptJson(
                                {
                                    "sources": {
                                        name: task.source for name, task in slots
                                    },
                                    "ruler": "-" * NODE_TARGET_BYTES,
                                    "target_bytes": NODE_TARGET_BYTES,
                                    "size_feedback": {
                                        name: feedback[task.start, task.count]
                                        for name, task in slots
                                        if (task.start, task.count) in feedback
                                    },
                                }
                            ),
                        ),
                    )
                )
                try:
                    bootstrap_context(definition, inputs, as_of, self.plan, proposed)
                except ContextLimitExceeded:
                    break
                packet = definition, slots, proposed
            if packet is None:
                raise MemoryError("compaction_blocked")
            definition, slots, source = packet
            first_task = slots[0][1]
            while True:
                if cancellation.cancelled:
                    return False
                await self.owner.require_current(permit)
                async with self.memory.database.connect() as connection:
                    latest = await connection.scalar(control_sequence)
                if cancellation.cancelled or latest != control:
                    return False
                for _, task in slots:
                    calls[task.start, task.count] += 1
                inference_started = perf_counter()
                outcome = await run_one_shot(
                    decisions=TransientModelDecisions(),
                    run_id=run_id,
                    definition=definition,
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
                    field_diagnostics=True,
                    event_sink=_MemoryFailureEvents(slots),
                )
                LOGGER.info(
                    "compaction inference: run_id=%s elapsed_ms=%.3f tasks=%s "
                    "retry_tasks=%s provider_turns=%s input_tokens=%s output_tokens=%s "
                    "outcome=%s interrupted=%s",
                    run_id,
                    (perf_counter() - inference_started) * 1000,
                    len(slots),
                    sum(calls[task.start, task.count] > 1 for _, task in slots),
                    outcome.metrics.provider_turns,
                    outcome.metrics.usage.input_tokens,
                    outcome.metrics.usage.output_tokens,
                    outcome.type,
                    cancellation.cancelled,
                )
                if cancellation.cancelled or outcome.type is OneShotStopKind.cancelled:
                    return False
                if outcome.type is OneShotStopKind.quota_exhausted:
                    evidence = await self.standby.observe(selected.profile)
                    if (
                        not isinstance(evidence, CodexBlocked)
                        and evidence.state == "included_exhausted"
                    ):
                        return False
                if outcome.type is not OneShotStopKind.protocol_error:
                    break
                if correction_spent or any(
                    calls[task.start, task.count] >= COMPACTION_CALLS
                    for _, task in slots
                ):
                    break
                correction_spent = True
                run_id = RunId(str(uuid4()))
            transient = outcome.type in {
                OneShotStopKind.provider_error,
                OneShotStopKind.model_decision_uncertain,
            }
            if isinstance(outcome, OneShotCompleted):
                result = cast(Mapping[str, str], outcome.result)
                for name, task in slots:
                    address = (task.start, task.count)
                    value = result[name].strip()
                    size = len(value.encode())
                    if size <= NODE_HARD_BYTES:
                        completed[address] = value
                    else:
                        feedback[address] = {
                            "measured_bytes": size,
                            "candidate": value,
                            "target_cut": clip_utf8(value, NODE_TARGET_BYTES),
                        }
            elif transient:
                for _, task in slots:
                    address = (task.start, task.count)
                    failures[address] += 1
                    if failures[address] >= COMPACTION_FAILURES:
                        park = task, "inference_failed"
                        break
            else:
                park = first_task, "invalid_completion"
                LOGGER.warning(
                    "compaction rejected: run_id=%s start=%s count=%s "
                    "reason=kernel_stopped stop_kind=%s",
                    run_id,
                    first_task.start,
                    first_task.count,
                    outcome.type.value,
                )
                break
            if park is not None:
                break
            for _, task in slots:
                address = (task.start, task.count)
                if address not in completed and calls[address] >= COMPACTION_CALLS:
                    park = (
                        task,
                        "inference_failed" if transient else "candidate_too_large",
                    )
                    break
            if park is not None:
                break
            pending = tuple(
                task for task in pending if (task.start, task.count) not in completed
            )
            if transient:
                try:
                    await asyncio.wait_for(
                        cancellation.wait(), COMPACTION_RETRY_SECONDS
                    )
                    return False
                except TimeoutError:
                    pass
        await self.owner.require_current(permit)
        commit_requested = perf_counter()
        async with self.memory.database.begin() as connection:
            commit_started = perf_counter()
            latest = await connection.scalar(control_sequence)
            if cancellation.cancelled or latest != control:
                return False
            if park is not None:
                await self.memory.library.park_compaction(connection, *park)
            else:
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
            if cancellation.cancelled:
                await connection.rollback()
                return False
        if park is not None:
            return False
        LOGGER.info(
            "compaction committed: writer_wait_ms=%.3f elapsed_ms=%.3f %s",
            (commit_started - commit_requested) * 1000,
            (perf_counter() - commit_started) * 1000,
            counts,
        )
        return True

    async def run_one(self, cancellation: CancellationToken) -> bool:
        try:
            if cancellation.cancelled:
                return False
            if await self.memory.project_pending():
                return True
            return await self.compact_one(cancellation)
        except (MemoryError, SQLAlchemyError) as error:
            LOGGER.warning(
                "memory background did not complete: type=%s", type(error).__name__
            )
            return False


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
        standby: CodexStandby,
        owner_timezone: str,
        nightly_time: time,
    ) -> None:
        self.definition, self.plan = definition, plan
        self.owner, self.provider, self.memory = owner, provider, memory
        self.standby = standby
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
        return completed is not None and completed.seed_end > completed.seed_start

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
        control_query = select(func.max(message.c.control_sequence)).where(
            message.c.source_conversation_id == self.owner.scope_id
        )
        occurrence = None
        if nightly:
            local = as_of.astimezone(self.timezone)
            occurrence = datetime.combine(
                local.date(), self.nightly_time, self.timezone
            )
            if occurrence > local:
                occurrence = datetime.combine(
                    local.date() - timedelta(days=1), self.nightly_time, self.timezone
                )
        async with self.memory.database.connect() as connection:
            control = await connection.scalar(control_query)
            if occurrence is not None:
                previous = await connection.scalar(
                    select(memory_state.c.last_nightly_attempt_at)
                )
                if previous is not None and previous >= occurrence:
                    return None
        pending = await self.memory.pending_publication()
        await self.memory.project_pending(pending)
        cutoff = await self.memory.library.cutoff()
        if cancellation.cancelled:
            return None
        seed = await self.memory.library.dream_input(cutoff)
        selected = None
        if seed.nodes:
            selected = await self.standby.choose_codex("dreamer")
            if isinstance(selected, CodexBlocked):
                return None
        await self.owner.require_current(permit)
        async with self.memory.database.begin() as connection:
            latest = await connection.scalar(control_query)
            if cancellation.cancelled or latest != control:
                return None
            if occurrence is not None and not await self.memory.library.claim_nightly(
                connection, occurrence, attempted_at=as_of
            ):
                return None
        if seed.seed_start == seed.seed_end:
            return DreamerRunCompleted(run_id, (), seed.seed_start, seed.seed_end, 0)
        result, turns = DreamResult(notes=()), 0
        dispatcher = MemoryToolDispatcher(cutoff=cutoff)
        if selected is not None:
            sections = [
                PromptSection(
                    PromptSectionKind("historical_memory_view"),
                    (),
                    PromptText(
                        render_dream_view(
                            seed.nodes,
                            seed.seed_start,
                            seed.seed_end,
                            generation=seed.generation,
                        )
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
                definition=replace(self.definition, provider=selected.provider),
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
                event_sink=_MemoryFailureEvents(),
            )
            if not isinstance(outcome, OneShotCompleted):
                if (
                    not cancellation.cancelled
                    and outcome.type is OneShotStopKind.quota_exhausted
                ):
                    await self.standby.observe(selected.profile)
                LOGGER.warning(
                    "dream stopped %s",
                    canonical_json_bytes(
                        {
                            "run_id": run_id,
                            "stop_kind": outcome.type.value,
                            "provider_turns": outcome.metrics.provider_turns,
                            "input_tokens": outcome.metrics.usage.input_tokens,
                            "output_tokens": outcome.metrics.usage.output_tokens,
                            "duration_seconds": outcome.metrics.duration_seconds,
                        }
                    ).decode("utf-8"),
                )
                return None
            if cancellation.cancelled:
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
            latest = await connection.scalar(control_query)
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

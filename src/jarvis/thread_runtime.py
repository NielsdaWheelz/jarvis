"""Main cognitive-run construction and observation evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    DispatchLineage,
    DispatchResult,
    OwnerToken,
    RunId,
    ThreadId,
    ThreadOutcome,
    ToolDispatchDefect,
    ToolDispatchLineage,
    ToolDispatchPort,
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

from jarvis import memory_workers
from jarvis.admission import (
    ExactToolBudgetFactory,
    RootTrackingAdmissionPort,
)
from jarvis.agent_tools import AgentListResult
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.context import (
    IsolatedRecaller,
    JarvisContextSource,
    MemoryReadDispatcherPort,
)
from jarvis.decisions import ModelJournalFactory
from jarvis.definitions import (
    MAIN_MAXIMUM_TOOL_LIMITS,
    RoleDefinitions,
)
from jarvis.discord import Control
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import KernelRuntime
from jarvis.memory_retrieval import MemoryRepository
from jarvis.messages import MessageStore
from jarvis.read_tools import CalendarListEventsSuccess
from jarvis.settings import Settings
from jarvis.terminal import TurnEvidence

_MAX_MATERIAL_CONTEXT_BYTES = 180_000


@dataclass(frozen=True, slots=True)
class PreflightDeferred:
    until: datetime


type ServiceRunOutcome = ThreadOutcome | PreflightDeferred


class _StoredObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    tool_id: Annotated[str, Field(min_length=1, max_length=128)]
    ordinal: Annotated[int, Field(ge=1)]
    result: dict[str, JsonValue]


class _StoredMainEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["jarvis-main-evidence.v1"]
    observations: Annotated[
        tuple[_StoredObservation, ...],
        Field(max_length=MAIN_MAXIMUM_TOOL_LIMITS.max_calls),
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
        if tool_id == "agent.list" and result.get("type") == "Success":
            inventory = AgentListResult.model_validate(result.get("value"))
            if inventory.partial:
                self._evidence.record_agent_inventory_incompleteness(
                    unavailable_machines=sum(not item.ok for item in inventory.peers)
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
        if len(encoded) > MAIN_MAXIMUM_TOOL_LIMITS.max_output_bytes + 16_384:
            raise ValueError("Main model evidence exceeds its frozen tool output bound")
        return _StoredMainEvidence.model_validate_json(encoded).model_dump(mode="json")

    def restore_model_evidence(self, value: object) -> None:
        stored = _StoredMainEvidence.model_validate_json(canonical_json_bytes(value))
        self._observations.clear()
        self._evidence.calendar_incompleteness = ()
        self._evidence.agent_inventory_incompleteness = ()
        for observation in stored.observations:
            self._record_observation(
                observation.tool_id, observation.ordinal, observation.result
            )

    def take_material_sections(self) -> PromptSections:
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
        sections = PromptSections(tuple(selected))
        self._observations.clear()
        return sections


class JarvisThreadRunner:
    """One concrete invocation of the pinned kernel over PostgreSQL ports."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: MessageStore,
        admission: RootTrackingAdmissionPort,
        kernel_runtime: KernelRuntime,
        model_decisions: ModelJournalFactory,
        definitions: RoleDefinitions,
        history: PostgresCanonicalHistory,
        dispatcher_factory: Callable[[PostgresInputCheckpoint], ToolDispatchPort],
        memory_repository: MemoryRepository,
        memory_dispatcher_factory: Callable[[], MemoryReadDispatcherPort],
        rememberer: memory_workers.RemembererWorker,
    ) -> None:
        self._settings = settings
        self._store = store
        self._admission = admission
        self._kernel_runtime = kernel_runtime
        self._model_decisions = model_decisions
        self._definitions = definitions
        self._history = history
        self._dispatcher_factory = dispatcher_factory
        self._memory_repository = memory_repository
        self._memory_dispatcher_factory = memory_dispatcher_factory
        self._rememberer = rememberer
        self._checkpoint_lock = asyncio.Lock()
        self._checkpoint: PostgresInputCheckpoint | None = None

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        """Settle an idle control, or leave an active one for checkpoint polling."""

        value = control.value
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
            if owner_message_ids:
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
            self._dispatcher_factory(checkpoints),
            turn_evidence,
        )
        recaller = IsolatedRecaller(
            definition=self._definitions.recaller,
            plan=self._definitions.plans["recaller"],
            admission=self._admission,
            provider=self._kernel_runtime.provider,
            dispatcher_factory=self._memory_dispatcher_factory,
            memory_repository=self._memory_repository,
            trace=self._store,
            model_decisions=self._model_decisions,
        )
        context = JarvisContextSource(
            thread_id,
            self._history,
            recaller=recaller,
            cancellation=cancellation,
            batch_clock=checkpoints,
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


__all__ = ["JarvisThreadRunner", "PreflightDeferred", "ServiceRunOutcome"]

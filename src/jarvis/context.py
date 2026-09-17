from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Literal, Protocol
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AgentDefinition,
    CancellationToken,
    Checkpoint,
    ContextSourceDefect,
    HostInput,
    InitialReadCall,
    InputClaim,
    InputId,
    OneShotCompleted,
    ProviderSessionPort,
    RunId,
    ThreadId,
    ThreadStopKind,
    ToolDispatchPort,
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
    ToolId,
    render_prompt,
)

from jarvis.admission import ExactToolBudgetFactory, RootTrackingAdmissionPort
from jarvis.decisions import ModelJournalFactory, isolated_decisions
from jarvis.definitions import RecallResult
from jarvis.memory import MemoryIdentity
from jarvis.memory_dispatch import MemoryDispatchEvidence
from jarvis.memory_retrieval import MemoryRepository, RetrievedMemory
from jarvis.memory_tools import MemorySearchInput


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    message_id: str
    role: Literal["owner", "assistant", "host"]
    text: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.message_id:
            raise ValueError("canonical message id must not be empty")
        if self.role not in ("owner", "assistant", "host"):
            raise ValueError("canonical message role is invalid")
        if not self.text:
            raise ValueError("canonical message text must not be empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("canonical message timestamp must be timezone-aware")


class CanonicalHistoryPort(Protocol):
    async def completed_history(
        self,
        thread_id: ThreadId,
        *,
        exclude_input_ids: tuple[InputId, ...],
        limit: int,
    ) -> tuple[CanonicalMessage, ...]: ...


class BatchClockPort(Protocol):
    async def as_of_for_inputs(self, inputs: tuple[HostInput, ...]) -> datetime: ...


class RecallTracePort(Protocol):
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
    ) -> None: ...


class MemoryReadDispatcherPort(ToolDispatchPort, Protocol):
    @property
    def evidence(self) -> MemoryDispatchEvidence: ...

    def snapshot_model_evidence(self) -> dict[str, object]: ...

    def restore_model_evidence(self, value: object) -> None: ...


class IsolatedRecaller:
    def __init__(
        self,
        *,
        definition: AgentDefinition,
        plan: FrozenToolPlan,
        admission: RootTrackingAdmissionPort,
        provider: ProviderSessionPort,
        dispatcher_factory: Callable[[], MemoryReadDispatcherPort],
        memory_repository: MemoryRepository,
        trace: RecallTracePort,
        model_decisions: ModelJournalFactory,
    ) -> None:
        self._definition = definition
        self._plan = plan
        self._admission = admission
        self._provider = provider
        self._dispatcher_factory = dispatcher_factory
        self._memory_repository = memory_repository
        self._trace = trace
        self._model_decisions = model_decisions

    async def recall(
        self,
        owner_input: HostInput,
        *,
        as_of: datetime,
        recent_context: PromptSections,
        cancellation: CancellationToken,
    ) -> PromptSections:
        try:
            message_id = UUID(str(owner_input.input_id))
        except ValueError as error:
            raise ContextSourceDefect("owner input ID is not a UUID") from error
        dispatcher = self._dispatcher_factory()
        run_id = RunId(str(uuid4()))
        decisions, as_of = await isolated_decisions(
            self._model_decisions, dispatcher, f"jarvis-recall:{message_id}", as_of
        )
        outcome = await run_one_shot(
            decisions=decisions,
            run_id=run_id,
            definition=self._definition,
            inputs=(owner_input,),
            as_of=as_of,
            plan=self._plan,
            source_sections=recent_context,
            admission=self._admission,
            provider=self._provider,
            dispatcher=dispatcher,
            budget_factory=ExactToolBudgetFactory(),
            initial_read=InitialReadCall(
                ToolId("memory.search"),
                MemorySearchInput(
                    query=_initial_recall_query(owner_input),
                    lexical_limit=10,
                    semantic_limit=10,
                ).model_dump(mode="json"),
            ),
            parent_admission=await self._admission.active_root(),
            cancellation=cancellation,
        )
        candidates = _normalized_identities(
            dispatcher.evidence.candidate_ids,
            deduplicate=True,
        )
        opened = _normalized_identities(
            dispatcher.evidence.opened_ids,
            deduplicate=False,
        )
        search_calls = dispatcher.evidence.search_calls
        if type(search_calls) is not int or not 0 <= search_calls <= 8:
            raise ContextSourceDefect(
                "memory dispatcher search-call evidence is invalid"
            )
        selected: tuple[MemoryIdentity, ...] = ()
        memories: tuple[RetrievedMemory, ...] = ()
        terminal_outcome = (
            "completed" if isinstance(outcome, OneShotCompleted) else outcome.type.value
        )
        if isinstance(outcome, OneShotCompleted) and search_calls == 0:
            terminal_outcome = "missing_search"
        elif isinstance(outcome, OneShotCompleted):
            try:
                result = RecallResult.model_validate(outcome.result)
            except (TypeError, ValueError):
                terminal_outcome = "invalid_result"
            else:
                selected = tuple(
                    MemoryIdentity(item.table_kind, UUID(item.id))
                    for item in result.memories
                )
                if len(selected) != len(set(selected)) or any(
                    item not in (*candidates, *opened) for item in selected
                ):
                    terminal_outcome = "invalid_selection"
                    selected = ()
                else:
                    memories = (await self._memory_repository.open(selected)).rows
                    if (
                        tuple(
                            MemoryIdentity(item.table_kind, item.id)
                            for item in memories
                        )
                        != selected
                    ):
                        terminal_outcome = "missing_selection"
                        memories = ()
        metrics = outcome.metrics
        await self._trace.record_recall(
            message_id=message_id,
            candidate_identities=candidates,
            selected_identities=selected,
            run_id=str(run_id),
            terminal_outcome=terminal_outcome,
            provider_turns=metrics.provider_turns,
            input_tokens=metrics.usage.input_tokens,
            output_tokens=metrics.usage.output_tokens,
            duration_seconds=metrics.duration_seconds,
        )
        if (
            not isinstance(outcome, OneShotCompleted)
            and outcome.type is ThreadStopKind.configuration_error
        ):
            raise ContextSourceDefect("isolated recaller configuration defect")
        return _memory_sections(memories)


class JarvisContextSource:
    def __init__(
        self,
        thread_id: ThreadId,
        history: CanonicalHistoryPort,
        *,
        recaller: IsolatedRecaller,
        cancellation: CancellationToken,
        batch_clock: BatchClockPort,
        history_limit: int = 100,
        history_max_bytes: int = 65_536,
    ) -> None:
        if type(history_limit) is not int or history_limit <= 0:
            raise ValueError("history limit must be a positive integer")
        if type(history_max_bytes) is not int or history_max_bytes <= 0:
            raise ValueError("history byte limit must be a positive integer")
        self._thread_id = thread_id
        self._history = history
        self._history_limit = history_limit
        self._history_max_bytes = history_max_bytes
        self._recaller = recaller
        self._cancellation = cancellation
        self._batch_clock = batch_clock
        self._recall_cache: dict[InputId, PromptSections] = {}

    async def bootstrap(
        self, definition: AgentDefinition, claim: InputClaim
    ) -> PromptSections:
        del definition
        excluded = tuple(item.input_id for item in claim.inputs)
        messages = await self._completed_history(excluded)
        history_sections = self._history_sections(messages)
        recall = await self._recall_sections(
            claim.inputs,
            as_of=claim.as_of,
            recent_context=history_sections,
        )
        return PromptSections((*history_sections.sections, *recall.sections))

    async def continuation(
        self,
        definition: AgentDefinition,
        claim: InputClaim,
        inputs: tuple[HostInput, ...],
        through_checkpoint: Checkpoint,
    ) -> PromptSections:
        del definition, through_checkpoint
        if not inputs or not any(_is_owner_input(item) for item in inputs):
            return PromptSections(())
        excluded = tuple(
            dict.fromkeys(item.input_id for item in (*claim.inputs, *inputs))
        )
        history = self._history_sections(await self._completed_history(excluded))
        return await self._recall_sections(
            inputs,
            as_of=await self._batch_clock.as_of_for_inputs(inputs),
            recent_context=history,
        )

    async def _completed_history(
        self, excluded: tuple[InputId, ...]
    ) -> tuple[CanonicalMessage, ...]:
        messages = await self._history.completed_history(
            self._thread_id,
            exclude_input_ids=excluded,
            limit=self._history_limit,
        )
        if type(messages) is not tuple:
            raise ContextSourceDefect("canonical history returned invalid values")
        if len(messages) > self._history_limit:
            raise ContextSourceDefect("canonical history exceeded its row bound")
        if {message.message_id for message in messages}.intersection(
            map(str, excluded)
        ):
            raise ContextSourceDefect("canonical history included current input")
        if any(
            left.created_at > right.created_at for left, right in pairwise(messages)
        ):
            raise ContextSourceDefect("canonical history is not chronological")
        return messages

    def _history_sections(
        self, messages: tuple[CanonicalMessage, ...]
    ) -> PromptSections:
        selected: list[PromptSection] = []
        used = 0
        for message in reversed(messages):
            section = _message_section(message)
            size = len(render_prompt(section).encode())
            if size > self._history_max_bytes and not selected:
                raise ContextSourceDefect(
                    "newest canonical history row exceeds its byte bound"
                )
            if used + size > self._history_max_bytes:
                break
            selected.append(section)
            used += size
        selected.reverse()
        if not selected:
            return PromptSections(())
        return PromptSections(
            (
                PromptSection(
                    PromptSectionKind("canonical_history"),
                    (),
                    PromptSections(tuple(selected)),
                ),
            )
        )

    async def _recall_sections(
        self,
        inputs: tuple[HostInput, ...],
        *,
        as_of: datetime,
        recent_context: PromptSections,
    ) -> PromptSections:
        recalled: list[PromptSection] = []
        for item in inputs:
            if not _is_owner_input(item):
                continue
            sections = self._recall_cache.get(item.input_id)
            if sections is None:
                sections = await self._recaller.recall(
                    item,
                    as_of=as_of,
                    recent_context=recent_context,
                    cancellation=self._cancellation,
                )
                self._recall_cache[item.input_id] = sections
            recalled.extend(sections.sections)
        if not recalled:
            return PromptSections(())
        return PromptSections(
            (
                PromptSection(
                    PromptSectionKind("recalled_memory_bundle"),
                    (),
                    PromptSections(tuple(recalled)),
                ),
            )
        )


def _message_section(message: CanonicalMessage) -> PromptSection:
    return PromptSection(
        PromptSectionKind("canonical_message"),
        (
            PromptAttribute(PromptAttributeName("message_id"), message.message_id),
            PromptAttribute(PromptAttributeName("role"), message.role),
            PromptAttribute(
                PromptAttributeName("source_timestamp"), message.created_at.isoformat()
            ),
        ),
        PromptText(message.text),
    )


def _is_owner_input(value: HostInput) -> bool:
    return any(
        str(section.kind) == "owner_input" for section in value.sections.sections
    )


def _initial_recall_query(owner_input: HostInput) -> str:
    owner_sections = tuple(
        section
        for section in owner_input.sections.sections
        if str(section.kind) == "owner_input"
    )
    if (
        len(owner_sections) != 1
        or not isinstance(owner_sections[0].body, PromptText)
        or not owner_sections[0].body.text.strip()
    ):
        raise ContextSourceDefect("owner input has no canonical text for recall")
    text = owner_sections[0].body.text.strip()
    if len(text) <= 2_048 and len(text.encode()) <= 4_096:
        return text
    marker = " ... "
    if len(text) > 2_048:
        prefix = text[:1_022]
        suffix = text[-1_021:]
    else:
        split = len(text) // 2
        prefix = text[:split]
        suffix = text[split:]
    while (
        len(prefix) + len(marker) + len(suffix) > 2_048
        or len((prefix + marker + suffix).encode()) > 4_096
    ):
        if len(prefix.encode()) >= len(suffix.encode()):
            prefix = prefix[:-1]
        else:
            suffix = suffix[1:]
    return prefix + marker + suffix


def _memory_sections(memories: tuple[RetrievedMemory, ...]) -> PromptSections:
    sections: list[PromptSection] = []
    for value in memories:
        attributes = [
            PromptAttribute(PromptAttributeName("table_kind"), value.table_kind),
            PromptAttribute(PromptAttributeName("memory_id"), str(value.id)),
            PromptAttribute(
                PromptAttributeName("source_timestamp"), value.created_at.isoformat()
            ),
        ]
        if value.table_kind == "memory_summary":
            attributes.append(
                PromptAttribute(
                    PromptAttributeName("source_memory_ids"),
                    ",".join(map(str, value.source_memory_ids)),
                )
            )
        sections.append(
            PromptSection(
                PromptSectionKind("recalled_memory"),
                tuple(attributes),
                PromptText(value.text),
            )
        )
    return PromptSections(tuple(sections))


def _normalized_identities(
    values: tuple[MemoryIdentity, ...],
    *,
    deduplicate: bool,
) -> tuple[MemoryIdentity, ...]:
    identities: list[MemoryIdentity] = []
    try:
        for value in values:
            identity = MemoryIdentity(value.table_kind, UUID(str(value.id)))
            if not deduplicate or identity not in identities:
                identities.append(identity)
    except (AttributeError, TypeError, ValueError) as error:
        raise ContextSourceDefect(
            "memory dispatcher identity evidence is invalid"
        ) from error
    return tuple(identities)


__all__ = [
    "BatchClockPort",
    "CanonicalHistoryPort",
    "CanonicalMessage",
    "IsolatedRecaller",
    "JarvisContextSource",
    "MemoryReadDispatcherPort",
    "RecallTracePort",
]

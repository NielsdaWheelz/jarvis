"""Bounded execution of the version-controlled recall cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from llm_agent_kernel import CancellationToken, HostInput, InputId
from llm_tools import (
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
)

from jarvis.context import IsolatedRecaller, RecallEvidence
from jarvis.memory import MemoryIdentity
from jarvis.recall_evaluation import (
    RecallCase,
    RecallObservation,
    RecallScore,
    score_recall,
)


class RecallProbeDefect(RuntimeError):
    """A production recaller run did not yield valid evaluation evidence."""


@dataclass(frozen=True, slots=True)
class RecallProbeResult:
    observations: tuple[RecallObservation, ...]
    score: RecallScore
    usages: tuple[RecallProbeUsage, ...]


@dataclass(frozen=True, slots=True)
class RecallProbeUsage:
    case_id: str
    provider_turns: int
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int


class RecallProbeTrace:
    def __init__(self) -> None:
        self.terminal_outcome: str | None = None
        self.provider_turns: int | None = None
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.duration_ms: int | None = None

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
        )
        self.terminal_outcome = terminal_outcome
        self.provider_turns = provider_turns
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.duration_ms = round(duration_seconds * 1_000)


async def run_recall_probe(
    *,
    cases: tuple[RecallCase, ...],
    recaller_factory: Callable[[RecallProbeTrace], IsolatedRecaller],
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RecallProbeResult:
    """Run every case once, with no retry or fallback."""
    observations: list[RecallObservation] = []
    usages: list[RecallProbeUsage] = []
    for case in cases:
        trace = RecallProbeTrace()
        recaller = recaller_factory(trace)
        as_of = clock()
        await recaller.recall(
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
                as_of,
            ),
            as_of=as_of,
            recent_context=PromptSections(()),
            cancellation=CancellationToken(),
        )
        evidence: RecallEvidence | None = recaller.last_evidence
        if trace.terminal_outcome != "completed" or evidence is None:
            raise RecallProbeDefect(
                f"recall case {case.id} did not complete with valid evidence"
            )
        if trace.provider_turns is None or trace.duration_ms is None:
            raise RecallProbeDefect(f"recall case {case.id} has missing usage")
        observations.append(
            RecallObservation(
                id=case.id,
                selected_ids=tuple(item.id for item in evidence.selected_identities),
                opened_ids=tuple(item.id for item in evidence.opened_identities),
                search_calls=evidence.search_calls,
            )
        )
        usages.append(
            RecallProbeUsage(
                case_id=case.id,
                provider_turns=trace.provider_turns,
                input_tokens=trace.input_tokens,
                output_tokens=trace.output_tokens,
                duration_ms=trace.duration_ms,
            )
        )
    values = tuple(observations)
    return RecallProbeResult(values, score_recall(cases, values), tuple(usages))


__all__ = [
    "RecallProbeDefect",
    "RecallProbeResult",
    "RecallProbeTrace",
    "RecallProbeUsage",
    "run_recall_probe",
]

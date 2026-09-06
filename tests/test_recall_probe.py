from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from llm_agent_kernel import CancellationToken, HostInput
from llm_tools import PromptSections

from jarvis.context import IsolatedRecaller, RecallEvidence
from jarvis.memory import MemoryIdentity
from jarvis.recall_evaluation import RecallCase
from jarvis.recall_probe import (
    RecallProbeDefect,
    RecallProbeTrace,
    run_recall_probe,
)

MEMORY_ID = UUID("00000000-0000-4000-8000-000000000001")
AS_OF = datetime(2026, 9, 5, 18, tzinfo=UTC)


def _case(*, empty: bool = False) -> RecallCase:
    return RecallCase(
        id="R01",
        provenance="owner-approved",
        lane="empty" if empty else "lexical",
        query="Synthetic recall query?",
        must_select_ids=() if empty else (MEMORY_ID,),
        must_open_ids=(),
        max_selected=0 if empty else 1,
        max_opened=0,
        min_search_calls=1,
    )


class _Recaller:
    def __init__(
        self,
        trace: RecallProbeTrace,
        *,
        terminal: str = "completed",
        evidence: RecallEvidence | None = None,
    ) -> None:
        self.trace = trace
        self.terminal = terminal
        self.calls = 0
        self.inputs: list[HostInput] = []
        self.times: list[datetime] = []
        self._last_evidence = (
            evidence
            if evidence is not None
            else RecallEvidence(
                candidate_identities=(MemoryIdentity("memory_log", MEMORY_ID),),
                selected_identities=(MemoryIdentity("memory_log", MEMORY_ID),),
                opened_identities=(),
                search_calls=1,
            )
        )

    @property
    def last_evidence(self) -> RecallEvidence:
        return self._last_evidence

    async def recall(
        self,
        owner_input: HostInput,
        *,
        as_of: datetime,
        recent_context: PromptSections,
        cancellation: CancellationToken,
    ) -> PromptSections:
        assert recent_context == PromptSections(())
        assert not cancellation.cancelled
        self.calls += 1
        self.inputs.append(owner_input)
        self.times.append(as_of)
        await self.trace.record_recall(
            message_id=UUID(str(owner_input.input_id)),
            candidate_identities=self._last_evidence.candidate_identities,
            selected_identities=self._last_evidence.selected_identities,
            run_id="synthetic-run",
            terminal_outcome=self.terminal,
            provider_turns=1,
            input_tokens=1,
            output_tokens=1,
            duration_seconds=0.1,
        )
        return PromptSections(())


async def test_recall_probe_runs_each_case_once_with_fresh_as_of() -> None:
    recaller_runs: list[_Recaller] = []

    def factory(trace: RecallProbeTrace) -> IsolatedRecaller:
        recaller = _Recaller(trace)
        recaller_runs.append(recaller)
        return cast(IsolatedRecaller, recaller)

    result = await run_recall_probe(
        cases=(_case(),),
        recaller_factory=factory,
        clock=lambda: AS_OF,
    )

    assert result.score.passed == 1
    assert result.observations[0].selected_ids == (MEMORY_ID,)
    assert result.observations[0].opened_ids == ()
    assert result.observations[0].search_calls == 1
    assert result.usages[0].case_id == "R01"
    assert result.usages[0].provider_turns == 1
    assert result.usages[0].duration_ms == 100
    assert len(recaller_runs) == 1
    assert recaller_runs[0].calls == 1
    assert recaller_runs[0].times == [AS_OF]
    assert recaller_runs[0].inputs[0].source_timestamp == AS_OF


async def test_invalid_terminal_cannot_falsely_pass_an_empty_case() -> None:
    created: list[_Recaller] = []

    def factory(trace: RecallProbeTrace) -> IsolatedRecaller:
        recaller = _Recaller(
            trace,
            terminal="invalid_result",
            evidence=RecallEvidence((), (), (), 1),
        )
        created.append(recaller)
        return cast(IsolatedRecaller, recaller)

    with pytest.raises(RecallProbeDefect, match="R01"):
        await run_recall_probe(
            cases=(_case(empty=True),),
            recaller_factory=factory,
            clock=lambda: AS_OF,
        )

    assert len(created) == 1
    assert created[0].calls == 1

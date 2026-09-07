"""Isolated-only serial dispatch for Slice 3 memory reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    InitialReadDispatchLineage,
    IsolatedDispatchLineage,
    ToolDispatchDefect,
    ToolDispatchLineage,
)
from llm_tools import (
    BudgetState,
    ExecutionContext,
    FrozenToolPlan,
    ParsedJson,
    Principal,
    Scope,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    ToolId,
)

from jarvis.memory_retrieval import MemoryIdentity
from jarvis.memory_tools import MEMORY_TOOL_IDS
from jarvis.read_dispatch import RunReadRecorder


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


@dataclass(frozen=True, slots=True)
class MemoryDispatchEvidence:
    candidate_ids: tuple[MemoryIdentity, ...]
    opened_ids: tuple[MemoryIdentity, ...]
    search_calls: int


class MemoryToolDispatcher:
    """Execute only exact frozen memory reads from an isolated role run."""

    def __init__(self) -> None:
        self._recorder = RunReadRecorder()
        self._candidate_ids: list[MemoryIdentity] = []
        self._candidate_id_set: set[MemoryIdentity] = set()
        self._opened_ids: list[MemoryIdentity] = []
        self._search_calls = 0

    @property
    def recorder(self) -> RunReadRecorder:
        return self._recorder

    @property
    def evidence(self) -> MemoryDispatchEvidence:
        return MemoryDispatchEvidence(
            tuple(self._candidate_ids),
            tuple(self._opened_ids),
            self._search_calls,
        )

    async def dispatch(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: ToolDispatchLineage,
    ) -> DispatchCompleted:
        if not isinstance(
            lineage, IsolatedDispatchLineage | InitialReadDispatchLineage
        ):
            raise ToolDispatchDefect("memory tools require isolated dispatch lineage")
        tool_id = binding.spec.id
        if tool_id not in MEMORY_TOOL_IDS or binding.spec.effect is not ToolEffect.Read:
            raise ToolDispatchDefect(
                "dispatcher received authority outside Slice 3 memory reads"
            )
        try:
            planned_binding = plan.catalog_view.binding(tool_id)
        except KeyError as exc:
            raise ToolDispatchDefect("dispatcher tool is absent from the plan") from exc
        if planned_binding is not binding:
            raise ToolDispatchDefect("dispatcher binding differs from the frozen plan")
        if not hasattr(validated_input, "model_dump"):
            raise ToolDispatchDefect("kernel supplied an invalid decoded tool input")
        value = cast("Any", validated_input).model_dump(mode="json")
        try:
            result = await ToolExecutor.execute(
                binding,
                ParsedJson(value),
                ExecutionContext(
                    plan=plan,
                    grant=plan.grant(tool_id),
                    catalog_view=plan.catalog_view,
                    position=lineage.position,
                    recorder=self._recorder,
                    effect_id=None,
                    budgets=budgets,
                    principal=Principal("jarvis-memory-role"),
                    scope=Scope("memory-read"),
                    cancellation=cancellation,
                    telemetry=_NoTelemetry(),
                ),
            )
        except Exception as exc:
            raise ToolDispatchDefect("memory read dispatch failed") from exc
        if tool_id == ToolId("memory.search"):
            self._search_calls += 1
            if result["type"] == "Success":
                for item in cast(
                    "list[dict[str, object]]", result["value"]["candidates"]
                ):
                    identity = MemoryIdentity(
                        cast("Any", item["table_kind"]),
                        UUID(cast(str, item["id"])),
                    )
                    if identity not in self._candidate_id_set:
                        self._candidate_id_set.add(identity)
                        self._candidate_ids.append(identity)
        elif result["type"] == "Success":
            for item in cast("list[dict[str, object]]", result["value"]["memories"]):
                self._opened_ids.append(
                    MemoryIdentity(
                        cast("Any", item["table_kind"]),
                        UUID(cast(str, item["id"])),
                    )
                )
        return DispatchCompleted(result)


__all__ = ["MemoryDispatchEvidence", "MemoryToolDispatcher"]

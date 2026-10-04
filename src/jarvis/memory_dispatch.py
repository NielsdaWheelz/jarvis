"""Isolated-only serial dispatch for Slice 3 memory reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, cast
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
    canonical_json_bytes,
)
from pydantic import BaseModel, ConfigDict, Field

from jarvis.memory_retrieval import MemoryIdentity
from jarvis.memory_tools import MEMORY_TOOL_IDS, MemoryRowIdentity
from jarvis.ownership import DeploymentOwnershipDefect
from jarvis.read_dispatch import ReadRecorder
from jarvis.tool_results import completed_tool_result


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


@dataclass(frozen=True, slots=True)
class MemoryDispatchEvidence:
    candidate_ids: tuple[MemoryIdentity, ...]
    opened_ids: tuple[MemoryIdentity, ...]
    search_calls: int


class _StoredMemoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["jarvis-memory-evidence.v1"]
    candidate_ids: Annotated[tuple[MemoryRowIdentity, ...], Field(max_length=160)]
    opened_ids: Annotated[tuple[MemoryRowIdentity, ...], Field(max_length=160)]
    search_calls: Annotated[int, Field(ge=0, le=8)]


class MemoryToolDispatcher:
    """Execute only exact frozen memory reads from an isolated role run."""

    def __init__(self, recorder: ReadRecorder) -> None:
        self._recorder = recorder
        self._candidate_ids: list[MemoryIdentity] = []
        self._candidate_id_set: set[MemoryIdentity] = set()
        self._opened_ids: list[MemoryIdentity] = []
        self._search_calls = 0

    @property
    def evidence(self) -> MemoryDispatchEvidence:
        return MemoryDispatchEvidence(
            tuple(self._candidate_ids),
            tuple(self._opened_ids),
            self._search_calls,
        )

    def snapshot_model_evidence(self) -> dict[str, object]:
        return _StoredMemoryEvidence(
            kind="jarvis-memory-evidence.v1",
            candidate_ids=tuple(
                MemoryRowIdentity(table_kind=value.table_kind, id=value.id)
                for value in self._candidate_ids
            ),
            opened_ids=tuple(
                MemoryRowIdentity(table_kind=value.table_kind, id=value.id)
                for value in self._opened_ids
            ),
            search_calls=self._search_calls,
        ).model_dump(mode="json")

    def restore_model_evidence(self, value: object) -> None:
        stored = _StoredMemoryEvidence.model_validate_json(canonical_json_bytes(value))
        self._candidate_ids = [
            MemoryIdentity(row.table_kind, row.id) for row in stored.candidate_ids
        ]
        self._candidate_id_set = set(self._candidate_ids)
        if len(self._candidate_ids) != len(self._candidate_id_set):
            raise ValueError("stored memory candidate evidence is duplicated")
        self._opened_ids = [
            MemoryIdentity(row.table_kind, row.id) for row in stored.opened_ids
        ]
        self._search_calls = stored.search_calls

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
            await self._recorder.recover_budget(lineage=lineage, budgets=budgets)
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
        except DeploymentOwnershipDefect:
            raise
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
        return completed_tool_result(result)


__all__ = ["MemoryDispatchEvidence", "MemoryToolDispatcher"]

"""One disposable dream run's serial reads and supporting references."""

from __future__ import annotations

from typing import Any, cast

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    IsolatedDispatchLineage,
    ToolDispatchDefect,
    ToolDispatchLineage,
)
from llm_tools import (
    BudgetState,
    ExecutionContext,
    ExecutorConfigurationDefect,
    FrozenToolPlan,
    ParsedJson,
    PositionConflictDefect,
    Principal,
    RecoveryRequired,
    Scope,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    TransientPositionRecorder,
    canonical_json_bytes,
)
from universal_memory import RangeReference, RecordReference, Reference
from universal_memory.tools import MEMORY_READ_IDS

from jarvis.tool_results import NoTelemetry, completed_tool_result


class MemoryToolDispatcher:
    def __init__(self, *, cutoff: int) -> None:
        self._cutoff = cutoff
        self._recorder = TransientPositionRecorder()
        self._references: dict[RecordReference | RangeReference, None] = {}

    @property
    def references(self) -> tuple[Reference, ...]:
        return tuple(self._references)

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
        if not isinstance(lineage, IsolatedDispatchLineage):
            raise ToolDispatchDefect("dream reads require isolated invocation lineage")
        tool_id = binding.spec.id
        if tool_id not in MEMORY_READ_IDS or binding.spec.effect is not ToolEffect.Read:
            raise ToolDispatchDefect("dream dispatch requires a granted memory read")
        if plan.catalog_view.binding(tool_id) is not binding:
            raise ToolDispatchDefect("memory binding differs from its frozen plan")
        if not hasattr(validated_input, "model_dump"):
            raise ToolDispatchDefect("memory dispatch requires decoded input")
        value = cast(Any, validated_input).model_dump(mode="json")
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
                    principal=Principal("jarvis-dreamer"),
                    scope=Scope(f"memory-through:{self._cutoff}"),
                    cancellation=cancellation,
                    telemetry=NoTelemetry(),
                ),
            )
        except (
            ExecutorConfigurationDefect,
            PositionConflictDefect,
            RecoveryRequired,
        ) as exc:
            raise ToolDispatchDefect("memory read dispatch failed") from exc
        if result["type"] == "Success":
            output = cast(dict[str, Any], result["value"])
            for row in output.get("records", ()):
                if "error" not in row:
                    reference = RecordReference.model_validate_json(
                        canonical_json_bytes(
                            {"kind": "record", "store": row["store"], "id": row["id"]}
                        )
                    )
                    self._references[reference] = None
            for node in output.get("nodes", ()):
                reference = RangeReference(start=node["start"], count=node["count"])
                self._references[reference] = None
            if output.get("record") is not None:
                row = output["record"]
                reference = RecordReference.model_validate_json(
                    canonical_json_bytes(
                        {"kind": "record", "store": row["store"], "id": row["id"]}
                    )
                )
                self._references[reference] = None
        return completed_tool_result(result)


__all__ = ["MemoryToolDispatcher"]

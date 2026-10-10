"""Serial Slice 2 read dispatch with pre-execution Web secret rejection."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import unquote, unquote_plus

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    NativeDispatchLineage,
    ToolDispatchDefect,
    ToolDispatchLineage,
    ToolDispatchPort,
)
from llm_tools import (
    BudgetState,
    EffectId,
    ExecutionContext,
    ExecutorConfigurationDefect,
    FrozenToolPlan,
    ParsedJson,
    PositionConflictDefect,
    PositionRecorder,
    Principal,
    RecoveryRequired,
    ReplayPolicy,
    Scope,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    ToolResult,
)
from universal_memory.tools import MEMORY_READ_IDS, MEMORY_SAVE_NOTE_SPEC, SaveNoteInput

from jarvis.agent_tools import AGENT_READ_IDS
from jarvis.read_tools import AUTOMATIC_READ_TOOL_IDS
from jarvis.tool_results import NoTelemetry, completed_tool_result

if TYPE_CHECKING:
    from jarvis.memory_service import MemoryService

_SECRET_PATTERN = re.compile(
    r"(?:"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|password|secret)"
    r"\s*[=:]\s*\S+"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"
    r"|\b(?:sk|gh[opusr]|xox[baprs])[-_][A-Za-z0-9_-]{16,}"
    r"|\bAIza[A-Za-z0-9_-]{20,}"
    r"|\bjmem_[A-Za-z0-9_-]{16,}"
    r"|\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"
    r")",
    re.IGNORECASE,
)
_INVALID_INPUT: ToolResult = {"type": "Failure", "error": {"type": "InvalidInput"}}


class ReadDispatchPort(ToolDispatchPort, Protocol):
    async def save_note(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: NativeDispatchLineage,
    ) -> DispatchCompleted: ...

    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None: ...


class ReadRecorder(PositionRecorder, Protocol):
    async def recover_note_save(
        self,
        *,
        lineage: NativeDispatchLineage,
        binding: ToolBinding[Any, Any, Any],
        plan: FrozenToolPlan,
        arguments: dict[str, Any],
        budgets: BudgetState,
        memory: MemoryService,
    ) -> DispatchCompleted | None: ...

    async def recover_native_read(
        self,
        *,
        lineage: NativeDispatchLineage,
        binding: ToolBinding[Any, Any, Any],
        plan: FrozenToolPlan,
        arguments: dict[str, Any],
    ) -> DispatchCompleted | None: ...

    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None: ...


class ReadToolDispatcher:
    """Execute only the automatic Slice 2 reads through llm-tools."""

    def __init__(
        self,
        *,
        host_secrets: tuple[str, ...],
        recorder: ReadRecorder,
        memory: MemoryService,
        cutoff: int,
    ) -> None:
        self._host_secrets = tuple(value for value in host_secrets if value)
        self._recorder = recorder
        self._memory = memory
        self._cutoff = cutoff

    async def save_note(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: NativeDispatchLineage,
    ) -> DispatchCompleted:
        if (
            binding.spec.id != MEMORY_SAVE_NOTE_SPEC.id
            or binding.spec.effect is not ToolEffect.Write
            or binding.replay_policy is not ReplayPolicy.ReDispatchable
            or not isinstance(validated_input, SaveNoteInput)
            or plan.catalog_view.binding(binding.spec.id) is not binding
        ):
            raise ToolDispatchDefect(
                "local save requires its exact native note contract"
            )
        arguments = validated_input.model_dump(mode="json")
        recovered = await self._recorder.recover_note_save(
            lineage=lineage,
            binding=binding,
            plan=plan,
            arguments=arguments,
            budgets=budgets,
            memory=self._memory,
        )
        if recovered is not None:
            return recovered
        await self.recover_budget(lineage=lineage, budgets=budgets)
        result = await ToolExecutor.execute(
            binding,
            ParsedJson(arguments),
            ExecutionContext(
                plan=plan,
                grant=plan.grant(binding.spec.id),
                catalog_view=plan.catalog_view,
                position=lineage.position,
                recorder=self._recorder,
                effect_id=EffectId(str(lineage.position)),
                budgets=budgets,
                principal=Principal("jarvis-owner"),
                scope=Scope(f"memory-through:{self._cutoff}"),
                cancellation=cancellation,
                telemetry=NoTelemetry(),
            ),
        )
        return completed_tool_result(result)

    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None:
        await self._recorder.recover_budget(lineage=lineage, budgets=budgets)

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
        tool_id = binding.spec.id
        if (
            tool_id not in (*AUTOMATIC_READ_TOOL_IDS, *AGENT_READ_IDS, *MEMORY_READ_IDS)
            or binding.spec.effect is not ToolEffect.Read
        ):
            raise ToolDispatchDefect(
                "dispatcher received authority outside Slice 2 reads"
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
        if str(tool_id).startswith("web.") and contains_secret(
            value, self._host_secrets
        ):
            return completed_tool_result(dict(_INVALID_INPUT))
        position = lineage.position
        try:
            if isinstance(lineage, NativeDispatchLineage):
                recorded = await self._recorder.recover_native_read(
                    lineage=lineage, binding=binding, plan=plan, arguments=value
                )
                if recorded is not None:
                    return recorded
            await self.recover_budget(lineage=lineage, budgets=budgets)
            result = await ToolExecutor.execute(
                binding,
                ParsedJson(value),
                ExecutionContext(
                    plan=plan,
                    grant=plan.grant(tool_id),
                    catalog_view=plan.catalog_view,
                    position=position,
                    recorder=self._recorder,
                    effect_id=None,
                    budgets=budgets,
                    principal=Principal("jarvis-owner"),
                    scope=Scope(f"memory-through:{self._cutoff}")
                    if tool_id in MEMORY_READ_IDS
                    else Scope("automatic-read"),
                    cancellation=cancellation,
                    telemetry=NoTelemetry(),
                ),
            )
        except (
            ExecutorConfigurationDefect,
            PositionConflictDefect,
            RecoveryRequired,
        ) as exc:
            raise ToolDispatchDefect("automatic read dispatch failed") from exc
        return completed_tool_result(result)


def contains_secret(value: object, host_secrets: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        pending = [value]
        seen: set[str] = set()
        while pending:
            candidate = pending.pop()
            if candidate in seen:
                continue
            seen.add(candidate)
            if any(secret and secret in candidate for secret in host_secrets):
                return True
            if _SECRET_PATTERN.search(candidate) is not None:
                return True
            pending.extend((unquote(candidate), unquote_plus(candidate)))
        return False
    if isinstance(value, dict):
        return any(
            contains_secret(item, host_secrets)
            for item in cast("dict[object, object]", value).values()
        )
    if isinstance(value, list):
        return any(
            contains_secret(item, host_secrets) for item in cast("list[object]", value)
        )
    return False


__all__ = ["ReadToolDispatcher", "contains_secret"]

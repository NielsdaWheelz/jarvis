"""Serial Slice 2 read dispatch with pre-execution Web secret rejection."""

from __future__ import annotations

import re
from typing import Any, Protocol, cast
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
    ExecutionContext,
    FrozenToolPlan,
    ParsedJson,
    PositionRecorder,
    Principal,
    Scope,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    ToolResult,
)

from jarvis.agent_tools import AGENT_READ_IDS
from jarvis.ownership import DeploymentOwnershipDefect
from jarvis.read_tools import AUTOMATIC_READ_TOOL_IDS

_SECRET_PATTERN = re.compile(
    r"(?:"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|password|secret)"
    r"\s*[=:]\s*\S+"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"
    r"|\b(?:sk|gh[opusr]|xox[baprs])[-_][A-Za-z0-9_-]{16,}"
    r"|\bAIza[A-Za-z0-9_-]{20,}"
    r"|\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"
    r")",
    re.IGNORECASE,
)
_INVALID_INPUT: ToolResult = {"type": "Failure", "error": {"type": "InvalidInput"}}


class ReadDispatchPort(ToolDispatchPort, Protocol):
    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None: ...


class ReadRecorder(PositionRecorder, Protocol):
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


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


class ReadToolDispatcher:
    """Execute only the automatic Slice 2 reads through llm-tools."""

    def __init__(
        self, *, host_secrets: tuple[str, ...], recorder: ReadRecorder
    ) -> None:
        self._host_secrets = tuple(value for value in host_secrets if value)
        self._recorder = recorder

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
            tool_id not in (*AUTOMATIC_READ_TOOL_IDS, *AGENT_READ_IDS)
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
            return DispatchCompleted(dict(_INVALID_INPUT))
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
                    scope=Scope("automatic-read"),
                    cancellation=cancellation,
                    telemetry=_NoTelemetry(),
                ),
            )
        except DeploymentOwnershipDefect:
            raise
        except Exception as exc:
            raise ToolDispatchDefect("automatic read dispatch failed") from exc
        return DispatchCompleted(result)


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

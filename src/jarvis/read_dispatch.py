"""Serial Slice 2 read dispatch with pre-execution Web secret rejection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import unquote, unquote_plus

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    ToolDispatchDefect,
    ToolDispatchLineage,
    ToolDispatchPort,
)
from llm_tools import (
    BudgetState,
    ExecutionContext,
    FrozenToolPlan,
    InvocationPosition,
    ParsedJson,
    PositionRecorder,
    PositionState,
    Principal,
    ReplayPolicy,
    Reservation,
    Scope,
    Settlement,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    ToolId,
    ToolResult,
)

from jarvis.agent_tools import AGENT_READ_IDS
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


@dataclass(slots=True)
class _Record:
    tool_id: ToolId
    tool_contract_revision: str
    policy_revision: str
    plan_revision: str
    input_digest: str
    replay_policy: ReplayPolicy
    reservation: Reservation | None = None
    reservation_accepted: bool | None = None
    terminal_result: ToolResult | None = None
    settlement: Settlement | None = None
    in_flight: bool = False
    uncertain: bool = False


class ReadDispatchPort(ToolDispatchPort, Protocol):
    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None: ...


class ReadRecorder(PositionRecorder, Protocol):
    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None: ...


class RunReadRecorder:
    """Non-durable invocation state owned by one kernel run."""

    def __init__(self) -> None:
        self._records: dict[InvocationPosition, _Record] = {}

    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None:
        del lineage, budgets

    @property
    def durable(self) -> bool:
        return False

    @property
    def position_count(self) -> int:
        return len(self._records)

    @property
    def terminal_count(self) -> int:
        return sum(
            record.terminal_result is not None for record in self._records.values()
        )

    @property
    def uncertain_count(self) -> int:
        return sum(record.uncertain for record in self._records.values())

    async def occupy(
        self,
        *,
        position: InvocationPosition,
        tool_id: ToolId,
        tool_contract_revision: str,
        policy_revision: str,
        plan_revision: str,
        input_digest: str,
        replay_policy: ReplayPolicy,
    ) -> PositionState:
        record = self._records.get(position)
        if record is None:
            record = _Record(
                tool_id,
                tool_contract_revision,
                policy_revision,
                plan_revision,
                input_digest,
                replay_policy,
            )
            self._records[position] = record
        elif (
            record.tool_id != tool_id
            or record.tool_contract_revision != tool_contract_revision
            or record.policy_revision != policy_revision
            or record.plan_revision != plan_revision
            or record.input_digest != input_digest
            or record.replay_policy is not replay_policy
        ):
            raise ValueError("read invocation position was reused inconsistently")
        return PositionState(record.terminal_result, record.uncertain, 0)

    async def reserve(
        self,
        *,
        position: InvocationPosition,
        budgets: BudgetState,
        reservation: Reservation,
    ) -> bool:
        record = self._records[position]
        if record.reservation is not None:
            if record.reservation != reservation:
                raise ValueError("read invocation reservation changed")
            assert record.reservation_accepted is not None
            return record.reservation_accepted
        accepted = await budgets.reserve(position, reservation)
        record.reservation = reservation
        record.reservation_accepted = accepted
        return accepted

    async def dispatch_started(
        self,
        *,
        position: InvocationPosition,
        replay_policy: ReplayPolicy,
    ) -> PositionState:
        record = self._records[position]
        if record.replay_policy is not replay_policy:
            raise ValueError("read invocation replay policy changed")
        if record.terminal_result is not None:
            return PositionState(record.terminal_result, False, 0)
        if record.uncertain:
            return PositionState(None, True, 0)
        if record.in_flight:
            return PositionState(None, True, 0)
        record.in_flight = True
        return PositionState(None, False, 0)

    async def dispatch_abandoned(
        self,
        *,
        position: InvocationPosition,
        replay_policy: ReplayPolicy,
        actual_attempts: int,
        lease_recovered: bool,
    ) -> None:
        del position, replay_policy, actual_attempts, lease_recovered
        raise ValueError("process-local read dispatch cannot be recovered")

    async def uncertain(self, *, position: InvocationPosition) -> None:
        record = self._records[position]
        if record.terminal_result is not None:
            raise ValueError("terminal read invocation cannot become uncertain")
        record.uncertain = True
        record.in_flight = False

    async def terminalize_and_settle(
        self,
        *,
        position: InvocationPosition,
        budgets: BudgetState,
        result: ToolResult,
        settlement: Settlement,
    ) -> ToolResult:
        record = self._records[position]
        if record.uncertain:
            raise ValueError("uncertain read invocation cannot terminalize")
        if record.terminal_result is not None:
            if record.terminal_result != result or record.settlement != settlement:
                raise ValueError("read invocation terminal result changed")
            return record.terminal_result
        if record.reservation_accepted:
            await budgets.settle(position, settlement)
        record.terminal_result = result
        record.settlement = settlement
        record.in_flight = False
        return result


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


class ReadToolDispatcher[RecorderT: ReadRecorder]:
    """Execute only the automatic Slice 2 reads through llm-tools."""

    def __init__(self, *, host_secrets: tuple[str, ...], recorder: RecorderT) -> None:
        self._host_secrets = tuple(value for value in host_secrets if value)
        self._recorder = recorder

    @property
    def recorder(self) -> RecorderT:
        return self._recorder

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


__all__ = ["ReadToolDispatcher", "RunReadRecorder", "contains_secret"]

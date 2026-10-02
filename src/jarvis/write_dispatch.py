"""Gate, classify, persist, execute, and reconcile durable Writes."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    DispatchResult,
    DispatchSuspended,
    HostInput,
    HostRef,
    NativeDispatchLineage,
    ToolDispatchDefect,
    ToolDispatchLineage,
    WaitingFor,
)
from llm_tools import (
    BudgetState,
    EffectId,
    ExecutionContext,
    FrozenToolPlan,
    ParsedJson,
    Principal,
    PromptText,
    RecoveryRequired,
    ReplayPolicy,
    Scope,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    ToolId,
    ToolResult,
    raw_input_digest,
)
from pydantic import BaseModel

from jarvis.action_requests import ActionRequest
from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
    agent_uncertainty_result,
    archived_worker_action,
    retired_worker_action,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.agent_control import AgentController
from jarvis.agent_tools import (
    AGENT_SUCCESS_TYPES,
    AGENT_WRITE_IDS,
    AgentCloseInput,
    AgentError,
    AgentKeysInput,
    AgentSendInput,
    AgentStopInput,
    validate_agent_evidence,
    validate_agent_failure,
)
from jarvis.approval import ApprovalRenderError, render_approval
from jarvis.messages import ACTION_MODEL_CONTEXT_SEPARATOR
from jarvis.ownership import DeploymentOwnershipDefect
from jarvis.read_dispatch import ReadDispatchPort, contains_secret
from jarvis.schedule_tools import ScheduleCreateRequest, ScheduleWakeInput
from jarvis.tool_results import completed_tool_result
from jarvis.write_connectors import (
    GmailUpdateReconciliationBasis,
    GoogleWriteConnector,
    ReconciliationResult,
    gmail_effect_id,
)
from jarvis.write_gate import AutomaticWriteGate, GateOwnerInput
from jarvis.write_policy import classify_write, write_effect_descriptor
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarUpdateEventInput,
    GmailCreateDraftInput,
    GmailSendDraftInput,
    GmailUpdateDraftInput,
)

_INVALID_INPUT: ToolResult = {"type": "Failure", "error": {"type": "InvalidInput"}}
_UNAVAILABLE: ToolResult = {
    "type": "Failure",
    "error": {"type": "ToolUnavailable"},
}
LOGGER = logging.getLogger(__name__)


class ScheduleChanged(Protocol):
    def __call__(self) -> None: ...


class ApprovalDisabler(Protocol):
    async def __call__(self, action: StoredAction) -> None: ...


class NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


class WriteAuthority(Protocol):
    async def automatic_write_gate_inputs(
        self,
        lineage: NativeDispatchLineage,
        request_ref: UUID,
    ) -> tuple[tuple[HostInput, ...], datetime]: ...


class WriteToolDispatcher:
    """One run-local dispatcher with durable positions for Writes only."""

    def __init__(
        self,
        *,
        checkpoint: WriteAuthority,
        gate: AutomaticWriteGate,
        actions: ActionStore,
        google_write: GoogleWriteConnector,
        agents: AgentController,
        read: ReadDispatchPort,
        owner_timezone: str,
        source_conversation_id: str,
        verified_owner_only_calendar_ids: tuple[str, ...],
        host_secrets: tuple[str, ...],
        schedule_changed: ScheduleChanged,
        dispatch_lane: asyncio.Lock,
    ) -> None:
        self._checkpoint = checkpoint
        self._gate = gate
        self._actions = actions
        self._google_write = google_write
        self._agents = agents
        self._read = read
        self._owner_timezone = owner_timezone
        self._source_conversation_id = source_conversation_id
        self._verified_calendar_ids = verified_owner_only_calendar_ids
        self._host_secrets = host_secrets
        self._schedule_changed = schedule_changed
        self._dispatch_lane = dispatch_lane
        self._effects: set[asyncio.Task[DispatchResult]] = set()
        self.on_effect_settled: Callable[[], None] = lambda: None

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
        if binding.spec.effect is ToolEffect.Read:
            async with self._dispatch_lane:
                return await self._read.dispatch(
                    binding=binding,
                    validated_input=validated_input,
                    plan=plan,
                    budgets=budgets,
                    cancellation=cancellation,
                    lineage=lineage,
                )
        if (
            binding.spec.effect is not ToolEffect.Write
            or not isinstance(lineage, NativeDispatchLineage)
            or not isinstance(validated_input, ActionRequest)
        ):
            raise ToolDispatchDefect(
                "Write requires a native invocation and ActionRequest"
            )
        if plan.catalog_view.binding(binding.spec.id) is not binding:
            raise ToolDispatchDefect("Write binding differs from its frozen plan")
        if binding.replay_policy not in {
            ReplayPolicy.BilledOnce,
            ReplayPolicy.ReDispatchable,
        }:
            raise ToolDispatchDefect(
                "Write replay policy cannot create a durable action"
            )
        validated_input = cast(ActionRequest[BaseModel], validated_input)
        await self._read.recover_budget(lineage=lineage, budgets=budgets)
        request_id = UUID(validated_input.request_ref)
        payload = validated_input.arguments
        arguments = validated_input.model_dump(mode="json")
        previous, recovered = await self._actions.accepted_actions(
            request_id, UUID(lineage.attempt_id)
        )
        selected = None
        if validated_input.existing_action_ref is not None:
            selected = next(
                (
                    item
                    for item in previous
                    if str(item.id) == validated_input.existing_action_ref
                ),
                None,
            )
            if selected is None:
                return _host_rejected("action_reference_outside_request")
        else:
            selected = next(
                (
                    item
                    for item in previous
                    if item.tool_name == binding.spec.id
                    and item.execution_contract.policy_revision
                    == binding.policy_revision
                    and item.payload == payload.model_dump(mode="json")
                ),
                None,
            )
        if selected is not None:
            contract = selected.execution_contract
            if (
                selected.tool_name != binding.spec.id
                or contract.tool_contract_revision
                != binding.spec.tool_contract_revision
                or contract.implementation_revision != binding.implementation_revision
                or contract.policy_revision != binding.policy_revision
                or selected.payload != payload.model_dump(mode="json")
            ):
                return _host_rejected("action_reference_contract_changed")
            if selected.status == "awaiting_approval":
                return DispatchSuspended(HostRef(str(selected.id)), WaitingFor.user)
            if (
                selected.tool_name == ToolId("schedule.wake")
                and selected.result is not None
                and "creation_receipt" in selected.result
            ):
                return completed_tool_result(
                    cast(ToolResult, selected.result["creation_receipt"]),
                    HostRef(str(selected.id)),
                )
            if (
                selected.status in {"queued", "executing", "uncertain"}
                and selected.result is None
            ):
                return DispatchSuspended(HostRef(str(selected.id)), WaitingFor.system)
            if (
                selected.status in {"succeeded", "failed"}
                and selected.result is not None
            ):
                return completed_tool_result(selected.result, HostRef(str(selected.id)))
            if selected.status == "uncertain":
                return DispatchSuspended(HostRef(str(selected.id)), WaitingFor.system)
            return _host_rejected("action_was_cancelled", HostRef(str(selected.id)))
        if recovered:
            return _host_rejected("recovery_requires_action_reference")
        tool_id = binding.spec.id
        try:
            owners, as_of = await self._checkpoint.automatic_write_gate_inputs(
                lineage, request_id
            )
            owner_inputs = _gate_owner_inputs(owners)
            target = None
            if tool_id in AGENT_WRITE_IDS and isinstance(
                payload,
                AgentSendInput | AgentKeysInput | AgentStopInput | AgentCloseInput,
            ):
                target = await self._agents.locate(tool_id, payload)
            gate = await self._gate.evaluate(
                owner_inputs,
                operation_id=f"jarvis-write-gate:{lineage.invocation_id}",
                parent_invocation_id=lineage.invocation_id,
                tool_id=tool_id,
                descriptor=write_effect_descriptor(tool_id, payload, target=target),
                owner_timezone=self._owner_timezone,
                as_of=as_of,
                cancellation=cancellation,
            )
        except (asyncio.CancelledError, DeploymentOwnershipDefect):
            raise
        except Exception as error:
            LOGGER.warning(
                "write gate unavailable: tool=%s invocation=%s exception=%s",
                tool_id,
                lineage.invocation_id,
                type(error).__name__,
            )
            return _write_check_failure(tool_id, "write_check_unavailable")
        if not gate.allowed:
            return _write_check_failure(tool_id, "policy_denied")
        if contains_secret(arguments, self._host_secrets):
            return completed_tool_result(dict(_INVALID_INPUT))
        if isinstance(
            payload, GmailSendDraftInput
        ) and not await gmail_send_basis_is_current(self._actions, payload):
            return completed_tool_result(dict(_UNAVAILABLE))
        live_event = None
        if isinstance(payload, CalendarUpdateEventInput | CalendarDeleteEventInput):
            observed = await self._google_write.calendar_current_snapshot(
                payload.expected.calendar_id, payload.expected.event_id
            )
            if observed.outcome != "found":
                return completed_tool_result(dict(_UNAVAILABLE))
            live_event = observed.value
        authority = classify_write(
            tool_id,
            payload,
            verified_owner_only_calendar_ids=self._verified_calendar_ids,
            live_calendar_event=live_event,
        )
        if authority == "rejected":
            return completed_tool_result(dict(_UNAVAILABLE))
        if cancellation.cancelled:
            raise asyncio.CancelledError
        action_id = uuid4()
        contract = ExecutionContract(
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
            tool_effect=ToolEffect.Write,
            replay_policy=cast(
                Literal[ReplayPolicy.ReDispatchable, ReplayPolicy.BilledOnce],
                binding.replay_policy,
            ),
            input_digest=raw_input_digest(ParsedJson(arguments)),
            max_attempts=1
            if binding.replay_policy is ReplayPolicy.BilledOnce
            else ACTION_MAX_ATTEMPTS,
            claim_id=lineage.attempt_id,
            through_checkpoint=str(lineage.through_checkpoint),
            model_step_ordinal=lineage.ordinal,
            input_message_ids=tuple(map(str, lineage.input_ids)),
            write_gate_supporting_owner_message_ids=tuple(
                map(str, gate.supporting_owner_message_ids)
            ),
        )
        if authority == "approval_required":
            try:
                presentation = render_approval(action_id, tool_id, payload)
            except ApprovalRenderError:
                return completed_tool_result(dict(_UNAVAILABLE))
            await self._actions.insert_awaiting_approval(
                tool_name=tool_id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=request_id,
                approval_text=presentation.content,
                source_conversation_id=self._source_conversation_id,
                action_id=action_id,
                invocation_id=UUID(lineage.invocation_id),
            )
            return DispatchSuspended(HostRef(str(action_id)), WaitingFor.user)
        execute_after = (
            payload.request.execute_after
            if isinstance(payload, ScheduleWakeInput)
            and isinstance(payload.request, ScheduleCreateRequest)
            else None
        )
        await self._actions.insert_automatic(
            tool_name=tool_id,
            arguments=arguments,
            execution_contract=contract,
            origin_message_id=request_id,
            execute_after=execute_after,
            action_id=action_id,
            invocation_id=UUID(lineage.invocation_id),
        )
        detached = False

        async def execute() -> DispatchResult:
            async with self._dispatch_lane:
                grant = plan.grant(tool_id)
                recorder = ActionPositionRecorder(
                    store=self._actions,
                    action_id=action_id,
                    implementation_revision=binding.implementation_revision,
                    max_external_attempts=grant.limits.max_attempts,
                )
                try:
                    result = await ToolExecutor.execute(
                        binding,
                        ParsedJson(arguments),
                        ExecutionContext(
                            plan=plan,
                            grant=grant,
                            catalog_view=plan.catalog_view,
                            position=recorder.position,
                            recorder=recorder,
                            effect_id=EffectId(str(action_id)),
                            budgets=budgets,
                            principal=Principal("jarvis-owner"),
                            scope=Scope("automatic-write"),
                            cancellation=CancellationToken(),
                            telemetry=NoTelemetry(),
                        ),
                    )
                except RecoveryRequired:
                    return DispatchSuspended(HostRef(str(action_id)), WaitingFor.system)
                if tool_id == ToolId("schedule.wake") and result["type"] == "Success":
                    self._schedule_changed()
                if detached:
                    stored = await self._actions.get(action_id)
                    if stored is not None and stored.status in {
                        "succeeded",
                        "failed",
                        "uncertain",
                        "cancelled",
                    }:
                        await self._actions.finish_recovered_origins(
                            reports=((action_id, action_resolution_text(stored)),),
                            source_conversation_id=self._source_conversation_id,
                        )
                return completed_tool_result(result, HostRef(str(action_id)))

        task = asyncio.create_task(execute(), name=f"jarvis-action:{action_id}")
        self._effects.add(task)
        task.add_done_callback(lambda _task: self.on_effect_settled())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            detached = True
            raise

    async def close(self) -> None:
        if self._effects:
            await asyncio.gather(*self._effects)

    def check_effects(self) -> bool:
        for task in tuple(self._effects):
            if task.done():
                task.result()
                self._effects.remove(task)
        return bool(self._effects)


def _host_rejected(code: str, reference: HostRef | None = None) -> DispatchCompleted:
    # Host authority failures are not executor observations and occupy no position.
    return completed_tool_result(
        {"type": "Failure", "error": {"type": "HostRejected", "code": code}}, reference
    )


class ActionRecovery:
    """Bounded startup recovery using only each tool's exact evidence procedure."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        google_write: GoogleWriteConnector,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        schedule_changed: ScheduleChanged,
        approval_disabler: ApprovalDisabler,
    ) -> None:
        self._actions = actions
        self._google_write = google_write
        self._plan = plan
        self._source_conversation_id = source_conversation_id
        self._schedule_changed = schedule_changed
        self._approval_disabler = approval_disabler

    async def recover(self, *, allow_queued_execution: bool = True) -> int:
        if type(allow_queued_execution) is not bool:
            raise ValueError("queued recovery selection must be boolean")
        recovered: set[UUID] = set()
        for pending in await self._actions.pending_approvals(
            source_conversation_id=self._source_conversation_id,
            limit=100,
        ):
            compatible = True
            try:
                binding = self._binding(pending)
                value = binding.spec.input_type.model_validate(
                    pending.arguments
                ).arguments
                render_approval(pending.id, pending.tool_name, value)
                if isinstance(value, GmailSendDraftInput):
                    compatible = await gmail_send_basis_is_current(self._actions, value)
            except DeploymentOwnershipDefect:
                raise
            except (ApprovalRenderError, RuntimeError, ValueError):
                compatible = False
            if compatible:
                continue
            discord_message_id = (
                await self._actions.approval_discord_message_id_or_none(pending.id)
            )
            if discord_message_id is not None:
                await self._approval_disabler(pending)
            await self._actions.cancel_nonexecuting(
                action_id=pending.id,
                result={
                    "type": "action_cancelled_v1",
                    "reason_code": "incompatible_execution_contract",
                },
            )
            recovered.add(pending.id)
        for scheduled in await self._actions.executing_schedule_receipts(limit=100):
            try:
                self._binding(scheduled)
            except RuntimeError:
                await self._actions.fail_incompatible_schedule(
                    action_id=scheduled.id,
                    source_conversation_id=self._source_conversation_id,
                )
                self._schedule_changed()
                recovered.add(scheduled.id)
        while candidates := await self._actions.recovery_candidates(
            include_queued=allow_queued_execution,
            limit=100,
        ):
            for candidate in candidates:
                await self._recover_one(
                    candidate,
                    allow_queued_execution=allow_queued_execution,
                )
                current = await self._require(candidate.id)
                if current != candidate:
                    recovered.add(candidate.id)
            if not allow_queued_execution:
                break
        while terminals := await self._actions.unreported_terminal(
            source_conversation_id=self._source_conversation_id, limit=100
        ):
            groups: dict[str, list[StoredAction]] = {}
            for terminal in terminals:
                groups.setdefault(terminal.execution_contract.claim_id, []).append(
                    terminal
                )
            for group in groups.values():
                ordered = sorted(
                    group,
                    key=lambda value: value.execution_contract.model_step_ordinal,
                )
                for value in ordered:
                    if (
                        value.approval_message_id is not None
                        and value.status == "cancelled"
                        and value.result
                        == {
                            "type": "approval_denied_v1",
                            "reason_code": "owner_denied",
                        }
                    ):
                        await self._approval_disabler(value)
                await self._actions.finish_recovered_origins(
                    reports=tuple(
                        (value.id, action_resolution_text(value)) for value in ordered
                    ),
                    source_conversation_id=self._source_conversation_id,
                )
                recovered.update(value.id for value in ordered)
        return len(recovered)

    async def _recover_one(
        self,
        stored: StoredAction,
        *,
        allow_queued_execution: bool,
    ) -> None:
        if retired_worker_action(stored):
            raise RuntimeError("retired unfinished worker action blocks activation")
        if (
            stored.execution_contract.replay_policy is ReplayPolicy.BilledOnce
            and stored.status == "executing"
        ):
            # Reporting an entered one-shot command never requires the new
            # deployment to retain its old executable/profile configuration.
            await self._actions.resolve_reconciliation(
                action_id=stored.id,
                status="uncertain",
                result=agent_uncertainty_result(stored),
            )
            return
        try:
            binding = self._binding(stored)
        except RuntimeError:
            current = await self._require(stored.id)
            if current.status != "queued":
                raise
            await self._actions.cancel_nonexecuting(
                action_id=current.id,
                result={
                    "type": "action_cancelled_v1",
                    "reason_code": "incompatible_execution_contract",
                },
            )
            return
        value = binding.spec.input_type.model_validate(stored.arguments).arguments
        if isinstance(value, GmailSendDraftInput) and not (
            await gmail_send_basis_is_current(self._actions, value)
        ):
            current = await self._require(stored.id)
            if current.status != "queued":
                raise RuntimeError("executing Gmail send lost its creation basis")
            await self._actions.cancel_nonexecuting(
                action_id=current.id,
                result={
                    "type": "action_cancelled_v1",
                    "reason_code": "invalid_gmail_send_creation_basis",
                },
            )
            return
        maximum_transitions = stored.execution_contract.max_attempts * 2 + 1
        for _ in range(maximum_transitions):
            current = await self._require(stored.id)
            if current.status in {"succeeded", "failed", "uncertain", "cancelled"}:
                return
            if current.execution_contract.replay_policy is ReplayPolicy.BilledOnce:
                if current.status == "queued" and current.attempts == 0:
                    if not allow_queued_execution:
                        return
                    await self._execute(current.id, binding)
                else:
                    await self._actions.resolve_reconciliation(
                        action_id=current.id,
                        status="uncertain",
                        result=agent_uncertainty_result(current),
                    )
                continue
            if (
                current.status == "executing"
                and current.approval_message_id is not None
                and current.decided_at is not None
                and current.attempts == 0
            ):
                await self._approval_disabler(current)
                if not allow_queued_execution:
                    return
            if str(current.tool_name) == "schedule.wake":
                if current.result is not None:
                    if (
                        current.status == "executing"
                        and current.execute_after is not None
                        and current.execute_after <= datetime.now(UTC)
                    ):
                        await self._actions.claim_due_schedule(
                            action_id=current.id,
                            plan=self._plan,
                            source_conversation_id=self._source_conversation_id,
                        )
                    return
                if current.status == "executing":
                    if current.attempts >= current.execution_contract.max_attempts:
                        await self._actions.resolve_reconciliation(
                            action_id=current.id,
                            status="failed",
                            result={
                                "type": "Failure",
                                "error": {"type": "BudgetExceeded"},
                            },
                        )
                        continue
                    if not allow_queued_execution:
                        return
                    await self._actions.requeue_local_schedule(current.id)
                if not allow_queued_execution:
                    return
                await self._execute(current.id, binding)
                continue
            if current.status == "queued":
                if not allow_queued_execution:
                    return
                await self._execute(current.id, binding)
                continue
            if current.recovered_external_attempts == 0:
                if current.attempts >= current.execution_contract.max_attempts:
                    await self._actions.resolve_reconciliation(
                        action_id=current.id,
                        status="failed",
                        result={
                            "type": "Failure",
                            "error": {"type": "BudgetExceeded"},
                        },
                    )
                    continue
                if not allow_queued_execution:
                    return
                await self._actions.requeue_after_proved_absence(
                    current.id,
                    actual_external_attempts=0,
                    max_external_attempts=self._plan.grant(
                        current.tool_name
                    ).limits.max_attempts,
                )
                continue
            if (
                str(current.tool_name) == "gmail.update_draft"
                and current.reconciliation_basis is None
            ):
                if (
                    current.attempts < current.execution_contract.max_attempts
                    and current.recovered_external_attempts
                    < self._plan.grant(current.tool_name).limits.max_attempts
                ):
                    if not allow_queued_execution:
                        return
                    await self._actions.requeue_after_proved_absence(
                        current.id,
                        actual_external_attempts=0,
                        max_external_attempts=self._plan.grant(
                            current.tool_name
                        ).limits.max_attempts,
                    )
                else:
                    await self._actions.resolve_reconciliation(
                        action_id=current.id,
                        status="failed",
                        result={
                            "type": "Failure",
                            "error": {"type": "BudgetExceeded"},
                        },
                    )
                continue
            reconciliation = await self._reconcile(current, binding)
            if reconciliation.outcome == "succeeded":
                assert reconciliation.value is not None
                await self._actions.resolve_reconciliation(
                    action_id=current.id,
                    status="succeeded",
                    result={
                        "type": "Success",
                        "value": reconciliation.value.model_dump(mode="json"),
                    },
                )
                continue
            if (
                current.tool_name == ToolId("gmail.create_draft")
                and reconciliation.outcome == "absent"
            ):
                await self._actions.resolve_reconciliation(
                    action_id=current.id,
                    status="uncertain",
                    result={
                        "type": "action_uncertainty_v1",
                        "evidence_code": "gmail-create-absence-is-not-repeat-safe",
                        "recorded_at": datetime.now(UTC).isoformat(),
                    },
                )
                continue
            if reconciliation.outcome == "absent" and (
                current.attempts < current.execution_contract.max_attempts
                and current.recovered_external_attempts
                < self._plan.grant(current.tool_name).limits.max_attempts
            ):
                if not allow_queued_execution:
                    return
                await self._actions.requeue_after_proved_absence(
                    current.id,
                    actual_external_attempts=0,
                    max_external_attempts=self._plan.grant(
                        current.tool_name
                    ).limits.max_attempts,
                )
                continue
            if reconciliation.outcome == "absent":
                await self._actions.resolve_reconciliation(
                    action_id=current.id,
                    status="failed",
                    result={"type": "Failure", "error": {"type": "BudgetExceeded"}},
                )
                continue
            await self._actions.resolve_reconciliation(
                action_id=current.id,
                status="uncertain",
                result={
                    "type": "action_uncertainty_v1",
                    "evidence_code": reconciliation.evidence,
                    "recorded_at": datetime.now(UTC).isoformat(),
                },
            )
        current = await self._require(stored.id)
        if current.status not in {"succeeded", "failed", "uncertain", "cancelled"}:
            raise RuntimeError("bounded action recovery did not reach a safe state")

    async def _execute(
        self, action_id: UUID, binding: ToolBinding[Any, Any, Any]
    ) -> None:
        current = await self._require(action_id)
        grant = self._plan.grant(current.tool_name)
        recorder = ActionPositionRecorder(
            store=self._actions,
            action_id=action_id,
            implementation_revision=binding.implementation_revision,
            max_external_attempts=grant.limits.max_attempts,
        )
        try:
            result = await ToolExecutor.execute(
                binding,
                ParsedJson(current.arguments),
                ExecutionContext(
                    plan=self._plan,
                    grant=grant,
                    catalog_view=self._plan.catalog_view,
                    position=recorder.position,
                    recorder=recorder,
                    effect_id=EffectId(str(action_id)),
                    budgets=ExactToolBudgetFactory().create(self._plan),
                    principal=Principal("jarvis-owner"),
                    scope=Scope("automatic-write-recovery"),
                    cancellation=CancellationToken(),
                    telemetry=NoTelemetry(),
                ),
            )
        except RecoveryRequired:
            return
        if current.tool_name == ToolId("schedule.wake") and result["type"] == "Success":
            self._schedule_changed()

    async def _reconcile(
        self,
        stored: StoredAction,
        binding: ToolBinding[Any, Any, Any],
    ) -> ReconciliationResult[Any]:
        value = binding.spec.input_type.model_validate(stored.arguments).arguments
        if isinstance(value, GmailCreateDraftInput):
            return await self._google_write.reconcile_gmail_create(value, stored.id)
        if isinstance(value, GmailUpdateDraftInput):
            basis = stored.reconciliation_basis
            if basis is None:
                raise RuntimeError("mutating Gmail update lacks reconciliation basis")
            if basis.get("type") != "gmail_update_reconciliation_v1" or any(
                not isinstance(basis.get(name), str)
                for name in (
                    "draft_id",
                    "thread_id",
                    "jarvis_effect_id",
                    "old_content_digest",
                )
            ):
                raise RuntimeError("Gmail reconciliation basis is malformed")
            return await self._google_write.reconcile_gmail_update(
                value,
                GmailUpdateReconciliationBasis(
                    type="gmail_update_reconciliation_v1",
                    draft_id=cast(str, basis["draft_id"]),
                    thread_id=cast(str, basis["thread_id"]),
                    jarvis_effect_id=cast(str, basis["jarvis_effect_id"]),
                    old_content_digest=cast(str, basis["old_content_digest"]),
                ),
            )
        if isinstance(value, GmailSendDraftInput):
            return await self._google_write.reconcile_gmail_send(value)
        if isinstance(value, CalendarCreateEventInput):
            return await self._google_write.reconcile_calendar_create(value, stored.id)
        if isinstance(value, CalendarUpdateEventInput):
            return await self._google_write.reconcile_calendar_update(value)
        if isinstance(value, CalendarDeleteEventInput):
            return await self._google_write.reconcile_calendar_delete(value)
        raise RuntimeError("action has no reconciliation procedure")

    def _binding(self, stored: StoredAction) -> ToolBinding[Any, Any, Any]:
        return require_current_action_binding(stored, self._plan)

    async def _require(self, action_id: UUID) -> StoredAction:
        stored = await self._actions.get(action_id)
        if stored is None:
            raise RuntimeError("recovering action disappeared")
        return stored


def _write_check_failure(
    tool_id: ToolId,
    code: Literal["policy_denied", "write_check_unavailable"],
) -> DispatchCompleted:
    if tool_id not in AGENT_WRITE_IDS:
        return completed_tool_result(dict(_UNAVAILABLE))
    return completed_tool_result(
        {
            "type": "Failure",
            "error": AgentError(code=code, dispatch="not_sent").model_dump(mode="json"),
        }
    )


def _gate_owner_inputs(values: tuple[HostInput, ...]) -> tuple[GateOwnerInput, ...]:
    result: list[GateOwnerInput] = []
    for value in values:
        sections = value.sections.sections
        if len(sections) != 1 or str(sections[0].kind) != "owner_input":
            raise ToolDispatchDefect("write gate received a non-owner projection")
        body = sections[0].body
        if not isinstance(body, PromptText):
            raise ToolDispatchDefect("write gate owner projection is malformed")
        result.append(
            GateOwnerInput(
                message_id=UUID(str(value.input_id)),
                text=body.text,
                created_at=value.source_timestamp,
            )
        )
    return tuple(result)


def action_resolution_text(stored: StoredAction) -> str:
    if set(stored.arguments) != {"request_ref", "existing_action_ref", "arguments"}:
        return (
            f"historical action {stored.id}; tool: {stored.tool_name}; "
            f"recorded status: {stored.status}; "
            "original arguments and receipt retained."
        )
    if archived_worker_action(stored):
        return (
            f"archived action {stored.id}; tool: {stored.tool_name}; "
            f"recorded status: {stored.status}; "
            "receipt details unavailable after cutover"
        )
    evidence = "Validated provider or local success receipt recorded."
    instruction = ""
    if stored.status == "queued" and stored.tool_name == ToolId("schedule.wake"):
        evidence = (
            "Durable schedule creation receipt recorded; the wake remains queued."
        )
    elif stored.status == "uncertain":
        assert stored.result is not None
        evidence_code = stored.result.get("evidence_code")
        if not isinstance(evidence_code, str):
            raise RuntimeError("uncertain action lacks safe reconciliation evidence")
        evidence = evidence_code
        instruction = (
            "\nOwner action: inspect current state; this action will not be repeated "
            "automatically."
        )
    elif stored.status == "failed":
        assert stored.result is not None
        error = stored.result.get("error")
        error_type = (
            cast("dict[str, object]", error).get("type")
            if isinstance(error, dict)
            else None
        )
        evidence = (
            f"Validated failure receipt recorded: {error_type}."
            if isinstance(error_type, str)
            else "Validated failure receipt recorded."
        )
        if error_type == "AgentFailure" and stored.tool_name in AGENT_WRITE_IDS:
            dispatch = _agent_failure(stored, stored.result["error"])["dispatch"]
            if dispatch == "sent":
                evidence = (
                    "Validated failure receipt recorded: AgentFailure, sent; failed "
                    "does not mean no effect."
                )
            elif dispatch == "not_sent":
                evidence = "Validated failure receipt recorded: AgentFailure, not sent."
    elif stored.status == "cancelled":
        assert stored.result is not None
        reason = stored.result.get("reason_code")
        evidence = (
            f"Host cancellation recorded: {reason}."
            if isinstance(reason, str)
            and reason
            and len(reason) <= 64
            and all(character.isalnum() or character in "_.-" for character in reason)
            else "Host cancellation recorded."
        )
    safe_result = json.dumps(
        _safe_fallback_result(stored),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    safe_prefix = (
        f"Action ID: {stored.id}\n"
        f"Tool: {stored.tool_name}\n"
        f"Status: {stored.status}\n"
        f"Evidence: {evidence}\n"
        f"Safe result: {safe_result}"
        f"{instruction}"
    )
    if len(safe_prefix) > 1_024 or len(safe_prefix.encode("utf-8")) > 1_024:
        raise RuntimeError("safe action resolution exceeds its character bound")
    model_context = {
        "type": "action_resolution_context_v1",
        "action_id": str(stored.id),
        "tool_name": str(stored.tool_name),
        "arguments": stored.arguments,
        "status": stored.status,
        "result": _safe_resolution_result(stored),
    }
    return (
        safe_prefix
        + ACTION_MODEL_CONTEXT_SEPARATOR
        + json.dumps(
            model_context,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def require_current_action_binding(
    stored: StoredAction,
    plan: FrozenToolPlan,
) -> ToolBinding[Any, Any, Any]:
    """Revalidate one immutable stored invocation against the current plan."""

    if retired_worker_action(stored):
        raise RuntimeError("archived worker action has no current binding")
    try:
        binding = plan.catalog_view.binding(stored.tool_name)
        plan.grant(stored.tool_name)
        binding.spec.input_type.model_validate(stored.arguments)
    except (KeyError, ValueError) as exc:
        raise RuntimeError("stored action tool is no longer selectable") from exc
    contract = stored.execution_contract
    if (
        binding.spec.effect is not ToolEffect.Write
        or binding.spec.tool_contract_revision != contract.tool_contract_revision
        or binding.implementation_revision != contract.implementation_revision
        or binding.policy_revision != contract.policy_revision
        or plan.plan_revision != contract.plan_revision
        or binding.replay_policy is not contract.replay_policy
        or raw_input_digest(ParsedJson(stored.arguments)) != contract.input_digest
    ):
        raise RuntimeError("stored action execution contract is incompatible")
    return binding


async def gmail_send_basis_is_current(
    actions: ActionStore,
    value: GmailSendDraftInput,
) -> bool:
    """Require the send header and thread to originate at Jarvis draft creation."""

    creation_id = await actions.gmail_draft_creation_action(
        draft_id=value.draft_id,
        thread_id=value.thread_id,
        jarvis_effect_id=value.jarvis_effect_id,
    )
    return creation_id is not None and gmail_effect_id(creation_id) == (
        value.jarvis_effect_id
    )


def _safe_resolution_result(stored: StoredAction) -> dict[str, object]:
    if stored.result is None:
        raise RuntimeError("resolved action has no durable result")
    if (
        stored.status == "uncertain"
        and stored.result.get("type") == "agent_uncertainty_v1"
    ):
        control = _agent_control(stored, stored.result.get("control"))
        return {
            "type": "Failure",
            "error": {"type": "Unknown", "observed": control["observed"]},
        }
    if (
        stored.tool_name in AGENT_WRITE_IDS
        and stored.status == "failed"
        and stored.result.get("type") == "Failure"
    ):
        error = stored.result.get("error")
        if (
            isinstance(error, dict)
            and cast(dict[str, object], error).get("type") == "AgentFailure"
        ):
            return {
                "type": "Failure",
                "error": _agent_failure(stored, stored.result["error"]),
            }
    if stored.status == "failed" and stored.result.get("type") == "Failure":
        error = stored.result.get("error")
        error_type = (
            cast("dict[str, object]", error).get("type")
            if isinstance(error, dict)
            else None
        )
        return {
            "type": "Failure",
            "error": {
                "type": error_type
                if isinstance(error_type, str)
                and error_type
                and len(error_type) <= 128
                and all(
                    character.isalnum() or character in "_.-"
                    for character in error_type
                )
                else "UnknownFailure"
            },
        }
    if stored.status == "cancelled" and stored.tool_name != ToolId("schedule.wake"):
        reason = stored.result.get("reason_code")
        return {
            "type": "action_cancelled_v1",
            "reason_code": reason
            if isinstance(reason, str)
            and reason
            and len(reason) <= 64
            and all(character.isalnum() or character in "_.-" for character in reason)
            else "cancelled",
        }
    return stored.result


def _safe_fallback_result(stored: StoredAction) -> dict[str, object]:
    if stored.status == "uncertain":
        assert stored.result is not None
        result = stored.result
        safe: dict[str, object] = {
            "type": "uncertain",
            "evidence_code": _safe_atom(result.get("evidence_code"), 256),
            "recorded_at": _safe_atom(result.get("recorded_at"), 64),
        }
        if result.get("type") == "agent_uncertainty_v1":
            control = _agent_control(stored, result.get("control"))
            observed = control["observed"]
            safe["control"] = {
                "type": control["type"],
                "observed": None
                if observed is None
                else _bounded_agent_observation(cast(dict[str, object], observed)),
            }
        return safe
    result = _safe_resolution_result(stored)
    if result.get("type") == "Failure":
        error = result.get("error")
        if not isinstance(error, dict):
            raise RuntimeError("failed action has malformed safe evidence")
        safe_error = cast("dict[str, object]", error)
        if (
            stored.tool_name in AGENT_WRITE_IDS
            and safe_error.get("type") == "AgentFailure"
        ):
            return {"type": "failure", "error": _bounded_agent_failure(safe_error)}
        return {
            "type": "failure",
            "error_type": _safe_atom(safe_error.get("type"), 128),
        }
    if stored.status == "cancelled" and stored.tool_name != ToolId("schedule.wake"):
        return {
            "type": "cancelled",
            "reason_code": _safe_atom(result.get("reason_code"), 64),
        }
    tool_name = str(stored.tool_name)
    if stored.tool_name in AGENT_WRITE_IDS:
        receipt = _agent_success(stored, _success_result_value(result))
        if tool_name != "agent.start":
            return _bounded_agent_receipt(receipt)
        created = cast(
            dict[str, object], receipt.get("terminal", receipt.get("session"))
        )
        agent = created.get("agent")
        name = created.get("name") or (
            cast(dict[str, object], agent).get("name")
            if isinstance(agent, dict)
            else None
        )
        return {
            "type": "agent_started",
            **{
                key: _safe_atom(value, 96)
                for key, value in (
                    ("observedAt", receipt.get("observedAt")),
                    ("name", name),
                    ("pane", created.get("pane")),
                    ("launch", receipt.get("launch")),
                )
                if value is not None
            },
        }
    if tool_name in {"gmail.create_draft", "gmail.update_draft"}:
        value = _success_result_value(result)
        return {
            "type": "gmail_draft",
            **_safe_fields(
                value,
                (
                    "draft_id",
                    "message_id",
                    "thread_id",
                    "jarvis_effect_id",
                    "content_digest",
                    "observed_at",
                ),
            ),
        }
    if tool_name == "gmail.send_draft":
        value = _success_result_value(result)
        return {
            "type": "gmail_sent",
            **_safe_fields(
                value,
                (
                    "sent_message_id",
                    "thread_id",
                    "jarvis_effect_id",
                    "content_digest",
                    "sent_at",
                ),
            ),
        }
    if tool_name in {"calendar.create_event", "calendar.update_event"}:
        value = _success_result_value(result)
        event = value.get("event")
        if not isinstance(event, dict):
            raise RuntimeError("calendar result lacks an event snapshot")
        safe_event = cast("dict[str, object]", event)
        recorded_key = (
            "created_at" if tool_name.endswith("create_event") else "updated_at"
        )
        return {
            "type": "calendar_event",
            **_safe_fields(
                safe_event,
                ("calendar_id", "event_id", "etag", "status", "updated_at"),
            ),
            recorded_key: _safe_atom(value.get(recorded_key), 64),
        }
    if tool_name == "calendar.delete_event":
        value = _success_result_value(result)
        return {
            "type": "calendar_event_deleted",
            **_safe_fields(
                value,
                ("calendar_id", "event_id", "prior_etag", "deleted_at"),
            ),
        }
    if tool_name == "schedule.wake":
        return _safe_schedule_result(result)
    raise RuntimeError("action has no safe deterministic result renderer")


def _agent_success(stored: StoredAction, value: object) -> dict[str, object]:
    return (
        AGENT_SUCCESS_TYPES[str(stored.tool_name).removeprefix("agent.")]
        .model_validate(value)
        .model_dump(mode="json")
    )


def _agent_failure(stored: StoredAction, error: object) -> dict[str, object]:
    return validate_agent_failure(
        str(stored.tool_name).removeprefix("agent."), error
    ).model_dump(mode="json")


def _agent_control(stored: StoredAction, control: object) -> dict[str, object]:
    return validate_agent_evidence(
        str(stored.tool_name).removeprefix("agent."), control
    ).model_dump(mode="json")


def _bounded_agent_receipt(receipt: dict[str, object]) -> dict[str, object]:
    return {
        name: _safe_atom(value, 96)
        for name, value in receipt.items()
        if name not in {"label", "machine"} and value is not None
    }


def _bounded_agent_failure(error: dict[str, object]) -> dict[str, object]:
    bounded: dict[str, object] = {
        "type": "AgentFailure",
        "code": _safe_atom(error.get("code"), 128),
        "dispatch": _safe_atom(error.get("dispatch"), 16),
    }
    conversation = error.get("conversation")
    if isinstance(conversation, dict):
        bounded["conversation_id"] = _safe_atom(
            cast(dict[str, object], conversation).get("conversationId"), 96
        )
    return bounded


def _bounded_agent_observation(observed: dict[str, object]) -> dict[str, object]:
    if observed.get("type") == "AgentFailure":
        return _bounded_agent_failure(observed)
    return _bounded_agent_receipt(observed)


def _success_result_value(result: dict[str, object]) -> dict[str, object]:
    value = result.get("value")
    if result.get("type") != "Success" or not isinstance(value, dict):
        raise RuntimeError("successful action lacks a validated result value")
    return cast("dict[str, object]", value)


def _safe_schedule_result(result: dict[str, object]) -> dict[str, object]:
    if "creation_receipt" in result:
        receipt = result.get("creation_receipt")
        if not isinstance(receipt, dict):
            raise RuntimeError("schedule result lacks its creation receipt")
        safe_receipt = cast("dict[str, object]", receipt)
        safe: dict[str, object] = {
            "type": "schedule",
            "creation_receipt": _safe_fields(
                safe_receipt,
                ("action_id", "execute_after", "arguments_digest", "recorded_at"),
            ),
        }
        wake_outcome = result.get("wake_outcome")
        if wake_outcome is None:
            safe["wake_outcome"] = None
        elif isinstance(wake_outcome, dict):
            safe_wake_outcome = cast("dict[str, object]", wake_outcome)
            outcome_type = _safe_atom(safe_wake_outcome.get("type"), 32)
            outcome_fields = {
                "concluded": ("conclusion_message_id", "recorded_at"),
                "cancelled": ("cancellation_action_id", "recorded_at"),
                "failed": ("reason_code", "recorded_at"),
            }.get(outcome_type)
            if outcome_fields is None:
                raise RuntimeError("schedule result has an invalid wake outcome")
            safe["wake_outcome"] = {
                "type": outcome_type,
                **_safe_fields(safe_wake_outcome, outcome_fields),
            }
        else:
            raise RuntimeError("schedule result has an invalid wake outcome")
        return safe
    value = _success_result_value(result)
    receipt = value.get("receipt")
    if not isinstance(receipt, dict):
        raise RuntimeError("schedule operation lacks its receipt")
    safe_receipt = cast("dict[str, object]", receipt)
    receipt_type = _safe_atom(safe_receipt.get("type"), 32)
    fields = {
        "created": ("action_id", "execute_after", "arguments_digest", "recorded_at"),
        "cancelled": ("target_action_id", "recorded_at"),
    }.get(receipt_type)
    if fields is None:
        raise RuntimeError("schedule operation has an invalid receipt")
    return {
        "type": "schedule_operation",
        "receipt": {"type": receipt_type, **_safe_fields(safe_receipt, fields)},
    }


def _safe_fields(value: dict[str, object], names: tuple[str, ...]) -> dict[str, object]:
    return {name: _safe_atom(value.get(name), 96) for name in names}


def _safe_atom(value: object, maximum_bytes: int) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError("durable result lacks safe normalized evidence")
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return value
    digest = sha256(encoded).hexdigest()[:16]
    prefix = value
    prefix_bound = maximum_bytes - len(f"…#{digest}".encode())
    while len(prefix.encode("utf-8")) > prefix_bound:
        prefix = prefix[:-1]
    return f"{prefix}…#{digest}"


__all__ = [
    "ActionRecovery",
    "NoTelemetry",
    "WriteToolDispatcher",
    "action_resolution_text",
    "gmail_send_basis_is_current",
    "require_current_action_binding",
]

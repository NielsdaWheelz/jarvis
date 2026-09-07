"""Gate, classify, persist, execute, and reconcile durable Writes."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from llm_agent_kernel import (
    CancellationToken,
    DispatchCompleted,
    DispatchLineage,
    DispatchResult,
    DispatchSuspended,
    HostRef,
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

from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.approval import ApprovalRenderError, render_approval
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.messages import ACTION_MODEL_CONTEXT_SEPARATOR
from jarvis.read_dispatch import ReadToolDispatcher, contains_secret
from jarvis.schedule_tools import ScheduleCreateRequest, ScheduleWakeInput
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


class ScheduleChanged(Protocol):
    def __call__(self) -> None: ...


class ApprovalDisabler(Protocol):
    async def __call__(self, action: StoredAction) -> None: ...


class NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


class WriteToolDispatcher:
    """One run-local dispatcher with durable positions for Writes only."""

    def __init__(
        self,
        *,
        checkpoint: PostgresInputCheckpoint,
        gate: AutomaticWriteGate,
        actions: ActionStore,
        google_write: GoogleWriteConnector,
        read: ReadToolDispatcher,
        owner_timezone: str,
        source_conversation_id: str,
        verified_owner_only_calendar_ids: tuple[str, ...],
        host_secrets: tuple[str, ...],
        schedule_changed: ScheduleChanged = lambda: None,
    ) -> None:
        self._checkpoint = checkpoint
        self._gate = gate
        self._actions = actions
        self._google_write = google_write
        self._read = read
        self._owner_timezone = owner_timezone
        self._source_conversation_id = source_conversation_id
        self._verified_calendar_ids = verified_owner_only_calendar_ids
        self._host_secrets = host_secrets
        self._schedule_changed = schedule_changed

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
            or binding.replay_policy is not ReplayPolicy.ReDispatchable
            or not isinstance(lineage, DispatchLineage)
        ):
            raise ToolDispatchDefect("Write lacks thread lineage")
        tool_id = binding.spec.id
        try:
            if plan.catalog_view.binding(tool_id) is not binding:
                raise ToolDispatchDefect("Write binding differs from the frozen plan")
            grant = plan.grant(tool_id)
        except KeyError as exc:
            raise ToolDispatchDefect("Write is absent from the frozen plan") from exc
        if not hasattr(validated_input, "model_dump"):
            raise ToolDispatchDefect("kernel supplied an invalid Write input")
        arguments = cast("Any", validated_input).model_dump(mode="json")
        try:
            owners, as_of = await self._checkpoint.automatic_write_gate_inputs(lineage)
            gate = await self._gate.evaluate(
                _gate_owner_inputs(owners),
                tool_id=tool_id,
                descriptor=write_effect_descriptor(tool_id, validated_input),
                owner_timezone=self._owner_timezone,
                as_of=as_of,
                cancellation=cancellation,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return DispatchCompleted(dict(_UNAVAILABLE))
        if not gate.allowed:
            return DispatchCompleted(dict(_UNAVAILABLE))
        if contains_secret(arguments, self._host_secrets):
            return DispatchCompleted(dict(_INVALID_INPUT))

        if isinstance(validated_input, GmailSendDraftInput) and not (
            await gmail_send_basis_is_current(self._actions, validated_input)
        ):
            return DispatchCompleted(dict(_UNAVAILABLE))

        live_event = None
        if isinstance(
            validated_input, CalendarUpdateEventInput | CalendarDeleteEventInput
        ):
            expected = validated_input.expected
            observed = await self._google_write.calendar_current_snapshot(
                expected.calendar_id, expected.event_id
            )
            if observed.outcome != "found":
                return DispatchCompleted(dict(_UNAVAILABLE))
            live_event = observed.value
        authority = classify_write(
            tool_id,
            validated_input,
            verified_owner_only_calendar_ids=self._verified_calendar_ids,
            live_calendar_event=live_event,
        )
        if authority == "rejected":
            return DispatchCompleted(dict(_UNAVAILABLE))
        if cancellation.cancelled:
            raise asyncio.CancelledError

        action_id = uuid4()
        contract = ExecutionContract(
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
            tool_effect=ToolEffect.Write,
            replay_policy=binding.replay_policy,
            input_digest=raw_input_digest(ParsedJson(arguments)),
            max_attempts=ACTION_MAX_ATTEMPTS,
            claim_id=str(lineage.claim_id),
            through_checkpoint=str(lineage.through_checkpoint),
            model_step_ordinal=lineage.model_step_ordinal,
            input_message_ids=tuple(map(str, lineage.input_ids)),
            write_gate_supporting_owner_message_ids=tuple(
                map(str, gate.supporting_owner_message_ids)
            ),
        )
        if authority == "approval_required":
            try:
                presentation = render_approval(action_id, tool_id, validated_input)
            except ApprovalRenderError:
                return DispatchCompleted(dict(_UNAVAILABLE))
            await self._actions.insert_awaiting_approval(
                tool_name=tool_id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=UUID(str(lineage.input_ids[0])),
                approval_text=presentation.content,
                source_conversation_id=self._source_conversation_id,
                action_id=action_id,
            )
            return DispatchSuspended(HostRef(str(action_id)), WaitingFor.user)

        execute_after = None
        if isinstance(validated_input, ScheduleWakeInput) and isinstance(
            validated_input.request, ScheduleCreateRequest
        ):
            execute_after = validated_input.request.execute_after
        await self._actions.insert_automatic(
            tool_name=tool_id,
            arguments=arguments,
            execution_contract=contract,
            origin_message_id=UUID(str(lineage.input_ids[0])),
            execute_after=execute_after,
            action_id=action_id,
        )
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
                    cancellation=cancellation,
                    telemetry=NoTelemetry(),
                ),
            )
        except (RecoveryRequired, asyncio.CancelledError):
            return DispatchSuspended(HostRef(str(action_id)), WaitingFor.system)
        if tool_id == ToolId("schedule.wake") and result["type"] == "Success":
            self._schedule_changed()
        return DispatchCompleted(result)


class ActionRecovery:
    """Bounded startup recovery using only each tool's exact evidence procedure."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        google_write: GoogleWriteConnector,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        schedule_changed: ScheduleChanged = lambda: None,
        approval_disabler: ApprovalDisabler | None = None,
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
                value = binding.spec.input_type.model_validate(pending.arguments)
                render_approval(pending.id, pending.tool_name, value)
                if isinstance(value, GmailSendDraftInput):
                    compatible = await gmail_send_basis_is_current(self._actions, value)
            except (ApprovalRenderError, RuntimeError, ValueError):
                compatible = False
            if compatible:
                continue
            discord_message_id = (
                await self._actions.approval_discord_message_id_or_none(pending.id)
            )
            if discord_message_id is not None:
                if self._approval_disabler is None:
                    raise RuntimeError(
                        "delivered incompatible approval requires a component disabler"
                    )
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
                        if self._approval_disabler is None:
                            raise RuntimeError(
                                "denied recovery requires a Discord component disabler"
                            )
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
        value = binding.spec.input_type.model_validate(stored.arguments)
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
            if (
                current.status == "executing"
                and current.approval_message_id is not None
                and current.decided_at is not None
                and current.attempts == 0
            ):
                if self._approval_disabler is None:
                    raise RuntimeError(
                        "approved recovery requires a Discord component disabler"
                    )
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
        value = binding.spec.input_type.model_validate(stored.arguments)
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


def _gate_owner_inputs(values: tuple[Any, ...]) -> tuple[GateOwnerInput, ...]:
    result: list[GateOwnerInput] = []
    for value in values:
        sections = value.sections.sections
        if len(sections) != 1 or str(sections[0].kind) != "owner_input":
            raise ToolDispatchDefect("write gate received a non-owner projection")
        body = sections[0].body
        if body is None or not hasattr(body, "text"):
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
            "\nOwner action: inspect the current provider state before retrying or "
            "taking further action."
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
    result = _safe_resolution_result(stored)
    if stored.status == "uncertain":
        return {
            "type": "uncertain",
            "evidence_code": _safe_atom(result.get("evidence_code"), 256),
            "recorded_at": _safe_atom(result.get("recorded_at"), 64),
        }
    if result.get("type") == "Failure":
        error = result.get("error")
        if not isinstance(error, dict):
            raise RuntimeError("failed action has malformed safe evidence")
        safe_error = cast("dict[str, object]", error)
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

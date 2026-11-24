"""Classify, persist, execute, and reconcile durable application writes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from llm_agent_kernel import (
    CancellationToken,
    DispatchResult,
    DispatchSuspended,
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
from sqlalchemy.exc import IntegrityError
from universal_memory.tools import MEMORY_SAVE_NOTE_SPEC

from jarvis._secrets import contains_secret
from jarvis.action_requests import ActionRequest
from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    GMAIL_WRITE_NAMES,
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
    action_replay_result,
    retired_worker_action,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.agent_control import AgentController
from jarvis.agent_tools import (
    AGENT_LOCAL_IDS,
    AGENT_WRITE_IDS,
    AgentTargetInput,
)
from jarvis.approval_tools import APPROVAL_RESPOND_SPEC, ApprovalRespondInput
from jarvis.attachment_tools import ATTACHMENT_WRITE_IDS
from jarvis.attachments import AttachmentStore
from jarvis.event_tools import EVENT_MUTATION_IDS
from jarvis.events import EventStore
from jarvis.gmail_drafts import compose_snapshot, content_digest, gmail_effect_id
from jarvis.mail_files import MailFileFailure, MailFiles
from jarvis.native_journal import PostgresNativeJournal
from jarvis.read_dispatch import ReadDispatchPort
from jarvis.tool_results import NoTelemetry, completed_tool_result, host_rejected
from jarvis.work import WorkStore
from jarvis.work_tools import WORK_MUTATION_IDS
from jarvis.write_connectors import GoogleWriteConnector
from jarvis.write_policy import classify_write
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarDeleteEventInput,
    CalendarUpdateEventInput,
    ExistingMailPart,
    GmailComposeContract,
    GmailCreateDraftInput,
    GmailCurrentDraft,
    GmailRetainedPart,
    GmailSendContract,
    GmailSendDraftInput,
    GmailStagedPart,
    GmailUpdateDraftInput,
    ReconciliationResult,
)

_INVALID_INPUT: ToolResult = {"type": "Failure", "error": {"type": "InvalidInput"}}
_UNAVAILABLE: ToolResult = {
    "type": "Failure",
    "error": {"type": "ToolUnavailable"},
}
LOGGER = logging.getLogger(__name__)


class WriteAuthority(Protocol):
    async def require_live_request(
        self, lineage: NativeDispatchLineage, request_ref: UUID
    ) -> None: ...


class WriteToolDispatcher:
    """Serialize admitted callbacks and retain entered effects until settlement."""

    def __init__(
        self,
        *,
        checkpoint: WriteAuthority,
        journal: PostgresNativeJournal,
        actions: ActionStore,
        google_write: GoogleWriteConnector,
        work: WorkStore,
        events: EventStore,
        attachments: AttachmentStore,
        mail_files: MailFiles,
        agents: AgentController,
        read: ReadDispatchPort,
        source_conversation_id: str,
        verified_owner_only_calendar_ids: tuple[str, ...],
        host_secrets: tuple[str, ...],
        dispatch_lane: asyncio.Lock,
    ) -> None:
        self._checkpoint = checkpoint
        self._journal = journal
        self._actions = actions
        self._google_write = google_write
        self._work = work
        self._events = events
        self._attachments = attachments
        self._mail_files = mail_files
        self._agents = agents
        self._read = read
        self._source_conversation_id = source_conversation_id
        self._verified_calendar_ids = verified_owner_only_calendar_ids
        self._host_secrets = host_secrets
        self._dispatch_lane = dispatch_lane
        self._effects: set[asyncio.Task[DispatchResult]] = set()
        self._closing = False
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
        if plan.catalog_view.binding(binding.spec.id) is not binding:
            raise ToolDispatchDefect("binding differs from its frozen plan")
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
        if binding.spec.effect is not ToolEffect.Write or not isinstance(
            lineage, NativeDispatchLineage
        ):
            raise ToolDispatchDefect("a write requires its native invocation")
        detached = False

        async def invoke() -> DispatchResult:
            async with self._dispatch_lane:
                if binding.spec.id == MEMORY_SAVE_NOTE_SPEC.id:
                    return await self._read.save_note(
                        binding=binding,
                        validated_input=validated_input,
                        plan=plan,
                        budgets=budgets,
                        cancellation=cancellation,
                        lineage=lineage,
                    )
                if binding.spec.id == APPROVAL_RESPOND_SPEC.id:
                    if not isinstance(validated_input, ApprovalRespondInput):
                        raise ToolDispatchDefect("approval decision input is invalid")
                    result = await self._journal.respond_approval(
                        lineage.invocation_id, validated_input
                    )
                    if result.result["type"] == "Success":
                        task = asyncio.create_task(
                            self._finish_decision(
                                UUID(validated_input.action_id), plan, cancellation
                            ),
                            name=f"jarvis-decision:{validated_input.action_id}",
                        )
                        self._effects.add(task)
                        task.add_done_callback(lambda _task: self.on_effect_settled())
                    return result
                if not isinstance(validated_input, ActionRequest):
                    raise ToolDispatchDefect("application write needs ActionRequest")
                result = await self._dispatch_action(
                    binding=binding,
                    request=cast(ActionRequest[BaseModel], validated_input),
                    plan=plan,
                    budgets=budgets,
                    cancellation=cancellation,
                    lineage=lineage,
                )
                if detached and result.host_ref is not None:
                    await self._publish_outcome(UUID(result.host_ref))
                return result

        task = asyncio.create_task(
            invoke(), name=f"jarvis-write:{lineage.invocation_id}"
        )
        self._effects.add(task)
        task.add_done_callback(lambda _task: self.on_effect_settled())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            detached = True
            raise

    async def _dispatch_action(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        request: ActionRequest[BaseModel],
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: NativeDispatchLineage,
    ) -> DispatchResult:
        request_id = UUID(request.request_ref)
        await self._checkpoint.require_live_request(lineage, request_id)
        await self._read.recover_budget(lineage=lineage, budgets=budgets)
        previous, blocked = await self._actions.accepted_actions(request_id)
        payload = request.arguments
        if request.existing_action_ref is not None:
            selected = next(
                (
                    item
                    for item in previous
                    if str(item.id) == request.existing_action_ref
                ),
                None,
            )
            if selected is None:
                return host_rejected("action_reference_outside_request")
            try:
                require_current_action_binding(selected, plan)
            except RuntimeError:
                return host_rejected("action_reference_contract_changed")
            if (
                selected.tool_name != binding.spec.id
                or selected.payload != payload.model_dump(mode="json")
            ):
                return host_rejected("action_reference_contract_changed")
            reference = HostRef(str(selected.id))
            if selected.status == "awaiting_approval":
                return DispatchSuspended(reference, WaitingFor.user)
            recorded = action_replay_result(selected)
            if recorded is not None:
                return completed_tool_result(recorded, reference)
            if selected.status in {"queued", "executing", "uncertain"}:
                return DispatchSuspended(reference, WaitingFor.system)
            return host_rejected("action_was_cancelled", reference)
        if blocked and binding.spec.id not in (*WORK_MUTATION_IDS, *EVENT_MUTATION_IDS):
            return host_rejected("effect_outcome_unknown")
        if binding.replay_policy not in {
            ReplayPolicy.BilledOnce,
            ReplayPolicy.ReDispatchable,
        }:
            raise ToolDispatchDefect("write replay policy has no action contract")
        arguments = request.model_dump(mode="json")
        if contains_secret(arguments, self._host_secrets):
            return completed_tool_result(dict(_INVALID_INPUT))
        tool_id = binding.spec.id
        target = None
        if tool_id in AGENT_WRITE_IDS and isinstance(payload, AgentTargetInput):
            target = await self._agents.locate(tool_id, payload)
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

        def check_admitted() -> None:
            if cancellation.cancelled or self._closing:
                raise asyncio.CancelledError

        check_admitted()
        action_id = uuid4()
        mail = None
        if isinstance(
            payload, GmailCreateDraftInput | GmailUpdateDraftInput | GmailSendDraftInput
        ):
            try:
                mail = await self._freeze_mail(action_id, payload)
            except MailFileFailure as exc:
                return completed_tool_result({"type": "Failure", "error": exc.error})
            if mail is None:
                return completed_tool_result(
                    {"type": "Failure", "error": {"type": "DraftChanged"}}
                )

        contract = ExecutionContract(
            schema_version="jarvis.action.v2",
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
            agent_target=target,
            mail=mail,
        )
        insert = (
            self._actions.insert_awaiting_approval
            if authority == "approval_required"
            else self._actions.insert_automatic
        )
        try:
            stored = await insert(
                tool_name=tool_id,
                arguments=arguments,
                execution_contract=contract,
                origin_message_id=request_id,
                action_id=action_id,
                invocation_id=UUID(lineage.invocation_id),
                check_admitted=check_admitted,
            )
        except (ActionPersistenceDefect, IntegrityError, asyncio.CancelledError):
            if (
                isinstance(mail, GmailComposeContract)
                and await self._actions.get(action_id) is None
            ):
                await _discard_mail_stage(self._mail_files, action_id)
            raise
        if authority == "approval_required":
            reference = HostRef(str(stored.id))
            if stored.status == "awaiting_approval":
                return DispatchSuspended(reference, WaitingFor.user)
            recorded = action_replay_result(stored)
            if recorded is not None:
                return completed_tool_result(recorded, reference)
            return DispatchSuspended(reference, WaitingFor.system)
        result = await execute_recorded_action(
            self._actions,
            action_id=action_id,
            binding=binding,
            plan=plan,
            budgets=budgets,
        )
        if isinstance(mail, GmailComposeContract) and not isinstance(
            result, DispatchSuspended
        ):
            await _discard_mail_stage(self._mail_files, action_id)
        self._agents.notify_wait_changed()
        return result

    async def _freeze_mail(
        self,
        action_id: UUID,
        payload: GmailCreateDraftInput | GmailUpdateDraftInput | GmailSendDraftInput,
    ) -> GmailComposeContract | GmailSendContract | None:
        creation_id = action_id
        revision = None
        old_files = ()
        if isinstance(payload, GmailCreateDraftInput):
            requested = payload.files
        else:
            source = await self._actions.get(payload.draft_ref)
            if source is None or not isinstance(
                source.execution_contract, ExecutionContract
            ):
                return None
            authority = source.execution_contract.mail
            receipt = action_replay_result(source)
            if (
                not isinstance(authority, GmailComposeContract)
                or receipt is None
                or (
                    receipt["type"] != "Success"
                    or not isinstance(receipt["value"], dict)
                    or cast(dict[str, object], receipt["value"]).get("state") != "draft"
                )
            ):
                return None
            base = GmailCurrentDraft.model_validate(receipt["value"])
            revision = base.revision
            creation_id = authority.creation_id
            if (
                base.draft_ref != source.id
                or gmail_effect_id(creation_id) != revision.jarvis_effect_id
            ):
                raise ActionPersistenceDefect(
                    "draft receipt has a different creation identity"
                )
            content = (
                GmailCreateDraftInput.model_validate(source.payload).content
                if source.tool_name == ToolId("gmail.create_draft")
                else GmailUpdateDraftInput.model_validate(source.payload).replacement
            )
            snapshot = compose_snapshot(
                content,
                revision.account,
                base.files,
                base.in_reply_to,
                base.references,
            )
            if content_digest(snapshot) != revision.content_digest:
                raise ActionPersistenceDefect(
                    "verified draft content changed in the ledger"
                )
            if isinstance(payload, GmailSendDraftInput):
                return GmailSendContract(
                    creation_id=creation_id,
                    revision=revision,
                    snapshot=snapshot,
                )
            if payload.replacement.reply_to != content.reply_to:
                return None
            old_files = base.files
            requested = (
                tuple(
                    ExistingMailPart(kind="existing", existing_part=number)
                    for number in range(1, len(old_files) + 1)
                )
                if payload.files is None
                else payload.files
            )

        positions = tuple(
            item.existing_part
            for item in requested
            if isinstance(item, ExistingMailPart)
        )
        if len(positions) != len(set(positions)) or any(
            number > len(old_files) for number in positions
        ):
            return None
        files = await self._mail_files.stage(
            action_id,
            tuple(
                old_files[item.existing_part - 1]
                if isinstance(item, ExistingMailPart)
                else item
                for item in requested
            ),
        )
        return GmailComposeContract(
            creation_id=creation_id,
            base_revision=revision,
            parts=tuple(
                GmailRetainedPart(existing_part=item.existing_part, file=file)
                if isinstance(item, ExistingMailPart)
                else GmailStagedPart(slot=slot, file=file)
                for slot, (item, file) in enumerate(
                    zip(requested, files, strict=True), 1
                )
            ),
        )

    async def _finish_decision(
        self, action_id: UUID, plan: FrozenToolPlan, cancellation: CancellationToken
    ) -> DispatchResult:
        async with self._dispatch_lane:
            stored = await self._actions.get(action_id)
            if stored is None:
                raise ToolDispatchDefect("decided action disappeared")
            if stored.status in {"queued", "executing"}:
                await ActionRecovery(
                    actions=self._actions,
                    google_write=self._google_write,
                    work=self._work,
                    events=self._events,
                    attachments=self._attachments,
                    mail_files=self._mail_files,
                    plan=plan,
                    source_conversation_id=self._source_conversation_id,
                    wait_changed=self._agents.notify_wait_changed,
                ).recover_action(
                    action_id,
                    allow_queued_execution=not cancellation.cancelled
                    and not self._closing,
                )
            await self._publish_outcome(action_id)
            stored = await self._actions.get(action_id)
            if stored is None:
                raise ToolDispatchDefect("decided action disappeared")
            result = action_replay_result(stored)
            return (
                completed_tool_result(result, HostRef(str(action_id)))
                if result is not None
                else DispatchSuspended(HostRef(str(action_id)), WaitingFor.system)
            )

    async def _publish_outcome(self, action_id: UUID) -> None:
        stored = await self._actions.get(action_id)
        if stored is not None and stored.status in {
            "succeeded",
            "failed",
            "uncertain",
            "cancelled",
        }:
            await self._actions.publish_outcomes(
                action_ids=(action_id,),
                source_conversation_id=self._source_conversation_id,
            )

    async def close(self) -> None:
        self._closing = True
        if self._effects:
            await asyncio.gather(*self._effects)

    def check_effects(self) -> bool:
        for task in tuple(self._effects):
            if task.done():
                task.result()
                self._effects.remove(task)
        return bool(self._effects)


async def execute_recorded_action(
    actions: ActionStore,
    *,
    action_id: UUID,
    binding: ToolBinding[Any, Any, Any],
    plan: FrozenToolPlan,
    budgets: BudgetState,
) -> DispatchResult:
    """Enter the same durable position for immediate, approved and recovered work."""
    stored = await actions.get(action_id)
    if stored is None:
        raise ToolDispatchDefect("recorded action disappeared")
    require_current_action_binding(stored, plan)
    grant = plan.grant(binding.spec.id)
    recorder = ActionPositionRecorder(
        store=actions,
        action_id=action_id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=grant.limits.max_attempts,
    )
    try:
        result = await ToolExecutor.execute(
            binding,
            ParsedJson(stored.arguments),
            ExecutionContext(
                plan=plan,
                grant=grant,
                catalog_view=plan.catalog_view,
                position=recorder.position,
                recorder=recorder,
                effect_id=EffectId(str(action_id)),
                budgets=budgets,
                principal=Principal("jarvis-owner"),
                scope=Scope("recorded-action"),
                cancellation=CancellationToken(),
                telemetry=NoTelemetry(),
            ),
        )
    except RecoveryRequired:
        return DispatchSuspended(HostRef(str(action_id)), WaitingFor.system)
    return completed_tool_result(result, HostRef(str(action_id)))


class ActionRecovery:
    """Bounded action recovery using only each tool's exact evidence procedure."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        google_write: GoogleWriteConnector,
        work: WorkStore,
        events: EventStore,
        attachments: AttachmentStore,
        mail_files: MailFiles,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        wait_changed: Callable[[], None],
    ) -> None:
        self._actions = actions
        self._google_write = google_write
        self._work = work
        self._events = events
        self._attachments = attachments
        self._mail_files = mail_files
        self._plan = plan
        self._source_conversation_id = source_conversation_id
        self._wait_changed = wait_changed

    async def recover(self, *, allow_queued_execution: bool = True) -> int:
        if type(allow_queued_execution) is not bool:
            raise ValueError("queued recovery selection must be boolean")
        recovered: set[UUID] = set()
        while candidates := await self._actions.recovery_candidates(
            include_queued=allow_queued_execution,
            limit=100,
        ):
            changed = False
            for candidate in candidates:
                await self.recover_action(
                    candidate.id,
                    allow_queued_execution=allow_queued_execution,
                )
                current = await self._require(candidate.id)
                if current != candidate:
                    changed = True
                    recovered.add(candidate.id)
            if not allow_queued_execution or not changed:
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
                published = await self._actions.publish_outcomes(
                    action_ids=tuple(value.id for value in ordered),
                    source_conversation_id=self._source_conversation_id,
                )
                recovered.update(
                    value.id
                    for value, receipt in zip(ordered, published, strict=True)
                    if receipt.inserted
                )
        return len(recovered)

    async def recover_action(
        self,
        action_id: UUID,
        *,
        allow_queued_execution: bool,
    ) -> None:
        """Settle one recorded action without sweeping unrelated work."""
        stored = await self._require(action_id)
        if retired_worker_action(stored):
            raise RuntimeError("retired unfinished worker action blocks activation")
        if (
            stored.execution_contract.replay_policy is ReplayPolicy.BilledOnce
            and stored.status == "executing"
        ):
            # Reporting an entered one-shot command never requires the new
            # deployment to retain its old executable/profile configuration.
            await self._actions.reconcile_agent_receipt(stored.id)
            return
        binding = self._binding(stored)
        maximum_transitions = stored.execution_contract.max_attempts * 2 + 1
        for _ in range(maximum_transitions):
            current = await self._require(stored.id)
            if current.status in {"succeeded", "failed", "uncertain", "cancelled"}:
                if isinstance(
                    current.current_execution_contract.mail, GmailComposeContract
                ):
                    await _discard_mail_stage(self._mail_files, current.id)
                return
            if current.tool_name in ATTACHMENT_WRITE_IDS:
                recovered = await self._attachments.recover_action(current.id)
                if recovered is not None:
                    return
                current = await self._require(current.id)
                if current.status == "executing":
                    if current.attempts >= current.execution_contract.max_attempts:
                        raise RuntimeError(
                            "attachment recovery left an exhausted entry"
                        )
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
                if not allow_queued_execution:
                    return
                if not await self._execute(current.id, binding):
                    return
                continue
            if current.execution_contract.replay_policy is ReplayPolicy.BilledOnce:
                if current.status == "queued" and current.attempts == 0:
                    if not allow_queued_execution:
                        return
                    if not await self._execute(current.id, binding):
                        return
                else:
                    await self._actions.reconcile_agent_receipt(current.id)
                continue
            if current.tool_name in WORK_MUTATION_IDS:
                if await self._work.recover_mutation(current.id) is not None:
                    return
            if current.tool_name in EVENT_MUTATION_IDS:
                if await self._events.recover_mutation(current.id) is not None:
                    return
            if current.tool_name in (
                *AGENT_LOCAL_IDS,
                *WORK_MUTATION_IDS,
                *EVENT_MUTATION_IDS,
            ):
                if action_replay_result(current) is not None:
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
                    await self._actions.requeue_after_proved_absence(
                        current.id, actual_external_attempts=0, max_external_attempts=0
                    )
                if not allow_queued_execution:
                    return
                if not await self._execute(current.id, binding):
                    return
                continue
            if current.status == "queued":
                if not allow_queued_execution:
                    return
                if not await self._execute(current.id, binding):
                    return
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
                and current.mail_progress.entered
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
                    **(
                        {
                            "reconciliation_basis": current.mail_progress.model_dump(
                                mode="json"
                            )
                        }
                        if str(current.tool_name) in GMAIL_WRITE_NAMES
                        else {}
                    ),
                },
            )
        current = await self._require(stored.id)
        if current.status not in {"succeeded", "failed", "uncertain", "cancelled"}:
            raise RuntimeError("bounded action recovery did not reach a safe state")

    async def _execute(
        self, action_id: UUID, binding: ToolBinding[Any, Any, Any]
    ) -> bool:
        """Return false when current admission leaves the action queued."""
        result = await execute_recorded_action(
            self._actions,
            action_id=action_id,
            binding=binding,
            plan=self._plan,
            budgets=ExactToolBudgetFactory().create(self._plan),
        )
        self._wait_changed()
        return (
            not isinstance(result, DispatchSuspended)
            or (await self._require(action_id)).status != "queued"
        )

    async def _reconcile(
        self,
        stored: StoredAction,
        binding: ToolBinding[Any, Any, Any],
    ) -> ReconciliationResult[Any]:
        value = binding.spec.input_type.model_validate(stored.arguments).arguments
        if stored.current_execution_contract.mail is not None:
            return await self._google_write.reconcile_gmail(stored)
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
    contract = stored.current_execution_contract
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


async def _discard_mail_stage(mail_files: MailFiles, action_id: UUID) -> None:
    try:
        await mail_files.discard(action_id)
    except OSError:
        LOGGER.warning("gmail stage cleanup deferred for %s", action_id)


__all__ = [
    "ActionRecovery",
    "NoTelemetry",
    "WriteToolDispatcher",
    "require_current_action_binding",
]

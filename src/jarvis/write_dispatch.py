"""Classify, persist, execute, and reconcile durable application writes."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from hashlib import sha256
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
    canonical_json_bytes,
    raw_input_digest,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection
from universal_memory.tools import MEMORY_SAVE_NOTE_SPEC

from jarvis._secrets import contains_secret
from jarvis.action_requests import ActionRequest
from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
    action_replay_result,
    followup_placement,
    retired_worker_action,
    workspace_owner_live,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.agent_control import AgentController
from jarvis.agent_tools import (
    AGENT_DELEGATE_ID,
    AGENT_WRITE_IDS,
    AgentDelegateInput,
    AgentError,
    AgentStartInput,
    AgentTargetInput,
)
from jarvis.approval_tools import APPROVAL_RESPOND_SPEC, ApprovalRespondInput
from jarvis.attachment_tools import ATTACHMENT_WRITE_IDS, AttachmentRetainInput
from jarvis.attachments import AttachmentStore
from jarvis.event_tools import EVENT_MUTATION_IDS
from jarvis.events import EventStore
from jarvis.mail_files import MailFileFailure, MailFiles
from jarvis.native_journal import PostgresNativeJournal
from jarvis.read_dispatch import ReadDispatchPort
from jarvis.tool_results import NoTelemetry, completed_tool_result, host_rejected
from jarvis.work import WorkStore
from jarvis.work_tools import WORK_MUTATION_IDS
from jarvis.workspace_enrollment import WorkspaceEnrollment
from jarvis.workspace_host import NativeWorkspaceRead, bind_workspace_read
from jarvis.workspace_mcp import HUMAN_WAIT_SECONDS, WorkspaceError, workspace_attempts
from jarvis.workspace_write_models import (
    DiscardDraft,
    FrozenCompose,
    workspace_write_arguments,
)
from jarvis.workspace_writes import WorkspaceWrites
from jarvis.write_connectors import WorkspaceWriteEntry, workspace_failure
from jarvis.write_policy import classify_write
from jarvis.write_tools import GMAIL_WRITE_POLICY, WRITE_TOOL_IDS

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
        workspace_writes: WorkspaceWrites,
        workspace_grant: Callable[[], WorkspaceEnrollment | None],
        work: WorkStore,
        events: EventStore,
        attachments: AttachmentStore,
        mail_files: MailFiles,
        agents: AgentController,
        read: ReadDispatchPort,
        source_conversation_id: str,
        host_secrets: tuple[str, ...],
        dispatch_lane: asyncio.Lock,
    ) -> None:
        self._checkpoint = checkpoint
        self._journal = journal
        self._actions = actions
        self._workspace_writes = workspace_writes
        self._workspace_grant = workspace_grant
        self._work = work
        self._events = events
        self._attachments = attachments
        self._mail_files = mail_files
        self._agents = agents
        self._read = read
        self._source_conversation_id = source_conversation_id
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
                if await self._actions.is_standing_check(UUID(lineage.input_ids[-1])):
                    return host_rejected("workspace_check_read_only")
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
                        lineage.invocation_id,
                        validated_input,
                        workspace_grant=self._workspace_grant,
                    )
                    if result.result["type"] == "Success":
                        task = asyncio.create_task(
                            self._finish_decision(
                                validated_input, plan, cancellation, lineage
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
        tool_id = binding.spec.id
        payload = request.arguments
        if await self._actions.is_standing_check(request_id):
            return host_rejected("workspace_check_read_only")
        arguments = request.model_dump(mode="json")
        if tool_id in AGENT_WRITE_IDS and request.existing_action_ref is None:
            linked = await self._actions.action_for_invocation(
                UUID(lineage.invocation_id)
            )
            if linked is not None:
                require_current_action_binding(linked, plan)
                if (
                    linked.tool_name != tool_id
                    or linked.origin_message_id != request_id
                    or linked.arguments != arguments
                ):
                    raise ToolDispatchDefect("linked worker action changed its request")
                if linked.status == "queued" and linked.attempts == 0:
                    if cancellation.cancelled or self._closing:
                        raise asyncio.CancelledError
                    result = await execute_recorded_action(
                        self._actions,
                        action_id=linked.id,
                        binding=binding,
                        plan=plan,
                        budgets=budgets,
                        source_conversation_id=self._source_conversation_id,
                    )
                    self._agents.delegations.notify_changed()
                    return result
                return _existing_action_result(linked)
        grant = (
            self._workspace_grant()
            if tool_id in WRITE_TOOL_IDS
            or tool_id in {"work.create", "work.update", "attachment.retain"}
            else None
        )
        authorize = None
        retention = None
        if tool_id in WRITE_TOOL_IDS or tool_id == "attachment.retain":
            if grant is None:
                return host_rejected("workspace_grant_unavailable")
            authorize = self._workspace_authority(
                lineage,
                request_id,
                tool_id,
                grant.grant_id,
                grant.account,
                cancellation,
            )
            try:
                await authorize(None)
            except WorkspaceError as exc:
                return host_rejected(exc.kind)
            if tool_id == "attachment.retain":
                if not isinstance(payload, AttachmentRetainInput):
                    raise ToolDispatchDefect("retain requires its exact file source")
                source = payload.source.model_dump(mode="json")
                if not await self._attachments.workspace_source_observed(
                    source, account=grant.account, grant_id=grant.grant_id
                ):
                    return host_rejected("workspace_file_not_observed")
                retention = self._retention_access(lineage, source, grant, authorize)
        previous, blocked = await self._actions.accepted_actions(request_id)
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
            return _existing_action_result(selected)
        replacement = None
        if (
            isinstance(payload, DiscardDraft)
            and payload.target.verified_replacement_action_id is not None
        ):
            assert grant is not None and authorize is not None
            try:
                replacement, prior = await self._actions.replacement_for_discard(
                    payload.target.verified_replacement_action_id,
                    request_id,
                    UUID(lineage.invocation_id),
                    grant.grant_id,
                    grant.account,
                    self._source_conversation_id,
                    authorize,
                )
            except WorkspaceError as exc:
                return host_rejected(exc.kind)
            if prior is not None:
                return _existing_action_result(prior)
        if blocked and binding.spec.id not in (*WORK_MUTATION_IDS, *EVENT_MUTATION_IDS):
            return host_rejected("effect_outcome_unknown")
        if binding.replay_policy not in {
            ReplayPolicy.BilledOnce,
            ReplayPolicy.ReDispatchable,
        }:
            raise ToolDispatchDefect("write replay policy has no action contract")
        if contains_secret(arguments, self._host_secrets):
            return completed_tool_result(dict(_INVALID_INPUT))
        authority = classify_write(tool_id, payload)
        if authority == "rejected":
            return completed_tool_result(dict(_UNAVAILABLE))
        target = None
        placement = None
        if tool_id in AGENT_WRITE_IDS and isinstance(payload, AgentTargetInput):
            target = await self._agents.locate(tool_id, payload)
        elif isinstance(payload, AgentDelegateInput | AgentStartInput):
            if isinstance(payload, AgentDelegateInput) and payload.after is not None:
                prior = next(
                    (item for item in previous if item.id == payload.after), None
                )
                placement = None if prior is None else followup_placement(prior)
                if placement is None:
                    placement = AgentError(code="job_not_found", dispatch="not_sent")
            else:
                assert payload.machine is not None
                placement = await self._agents.resolve_machine(payload.machine)
            if isinstance(placement, AgentError):
                return completed_tool_result(
                    {
                        "type": "Failure",
                        "error": placement.model_dump(mode="json", exclude_none=True),
                    }
                )

        async def check_admitted(connection: AsyncConnection) -> None:
            if authorize is not None:
                await authorize(connection)
            if cancellation.cancelled or self._closing:
                raise asyncio.CancelledError

        if cancellation.cancelled or self._closing:
            raise asyncio.CancelledError
        action_id = uuid4()
        frozen = None
        prepare_attempts = 0
        prepare_seconds = 0.0
        prepare_human_elapsed = 0.0
        prepare_consent_rounds = 0
        staging = tool_id in {"gmail.create_draft", "gmail.prepare_replacement"}
        if tool_id in WRITE_TOOL_IDS and grant is not None and authorize is not None:

            async def before_prepare() -> None:
                await authorize(None)

            try:
                limits = plan.grant(tool_id).limits
                with workspace_attempts(
                    GMAIL_WRITE_POLICY.max_attempts,
                    seconds=limits.deadline_seconds - HUMAN_WAIT_SECONDS,
                ) as meter:
                    async with asyncio.timeout(limits.deadline_seconds):
                        frozen = await self._workspace_writes.prepare(
                            str(tool_id),
                            workspace_write_arguments(payload),
                            action_id=action_id,
                            grant_id=grant.grant_id,
                            account=grant.account,
                            invocation_id=lineage.invocation_id,
                            before_send=before_prepare,
                            replacement=replacement,
                        )
                prepare_attempts, prepare_seconds = meter.attempts, meter.elapsed
                prepare_human_elapsed = meter.human_elapsed
                prepare_consent_rounds = meter.consent_rounds
                if (frozen.action_id, frozen.tool, frozen.grant_id, frozen.account) != (
                    action_id,
                    tool_id,
                    grant.grant_id,
                    grant.account,
                ):
                    raise ToolDispatchDefect(
                        "workspace preparation changed its action identity"
                    )
            except (WorkspaceError, MailFileFailure, TimeoutError) as exc:
                if staging:
                    await _discard_mail_stage(self._mail_files, action_id)
                detail = (
                    exc.error
                    if isinstance(exc, MailFileFailure)
                    else workspace_failure(
                        WorkspaceError("temporary")
                        if isinstance(exc, TimeoutError)
                        else exc
                    ).model_dump(mode="json")
                )
                return completed_tool_result({"type": "Failure", "error": detail})
            except BaseException:
                if staging:
                    await _discard_mail_stage(self._mail_files, action_id)
                raise

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
            agent_placement=placement,
            workspace=frozen,
            workspace_prepare_attempts=prepare_attempts,
            workspace_prepare_seconds=prepare_seconds,
            workspace_prepare_human_elapsed=prepare_human_elapsed,
            workspace_prepare_consent_rounds=prepare_consent_rounds,
            workspace_grant_id=grant.grant_id
            if grant is not None
            and tool_id in {"work.create", "work.update", "attachment.retain"}
            else None,
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
        except BaseException as exc:
            if staging and await self._actions.get(action_id) is None:
                await _discard_mail_stage(self._mail_files, action_id)
            if isinstance(exc, WorkspaceError):
                return host_rejected(exc.kind)
            raise
        if authority == "approval_required":
            return _existing_action_result(stored)
        entry = (
            WorkspaceWriteEntry(
                frozen,
                UUID(lineage.invocation_id),
                authorize,
                prepare_attempts,
                prepare_seconds,
                prepare_human_elapsed,
                prepare_consent_rounds,
            )
            if frozen is not None and authorize is not None
            else None
        )
        with bind_workspace_read(retention) if retention is not None else nullcontext():
            result = await execute_recorded_action(
                self._actions,
                action_id=stored.id,
                binding=binding,
                plan=plan,
                budgets=budgets,
                source_conversation_id=self._source_conversation_id,
                workspace_entry=entry,
            )
        if staging and not isinstance(result, DispatchSuspended):
            await _discard_mail_stage(self._mail_files, action_id)
        self._agents.delegations.notify_changed()
        return result

    def _retention_access(
        self,
        lineage: NativeDispatchLineage,
        source: dict[str, object],
        grant: WorkspaceEnrollment,
        authorize: Callable[[AsyncConnection | None], Awaitable[None]],
    ) -> NativeWorkspaceRead:
        async def require_current(connection: AsyncConnection | None) -> None:
            await authorize(connection)
            if not await self._attachments.workspace_source_observed(
                source, account=grant.account, grant_id=grant.grant_id
            ):
                raise WorkspaceError("workspace_file_not_observed")

        async def before_send(
            public: str,
            selectors: dict[str, object],
            product: str,
            operation: str,
            wire: dict[str, object],
        ) -> None:
            if (
                public != "attachment.retain"
                or selectors != {"source": source}
                or product != "gmail"
            ):
                raise WorkspaceError("source_changed")
            if operation == "get_message":
                exact = not str(source["part_id"]).startswith("mime1.d") and wire == {
                    "messageId": source["message_id"],
                    "messageFormat": "RAW",
                }
            elif operation == "get_draft" and isinstance(wire.get("draftId"), str):
                draft = str(wire["draftId"])
                tag = base64.urlsafe_b64encode(draft.encode()).decode().rstrip("=")
                exact = wire == {"draftId": draft, "messageFormat": "RAW"} and str(
                    source["part_id"]
                ).startswith(f"mime1.d{tag}.")
            else:
                exact = False
            if not exact:
                raise WorkspaceError("source_changed")
            await require_current(None)

        return NativeWorkspaceRead(
            invocation_id=lineage.invocation_id,
            background=False,
            before_send=before_send,
            grant_id=grant.grant_id,
            source_digest=sha256(
                canonical_json_bytes(
                    [str(grant.grant_id), "attachment.retain", source, None]
                )
            ).hexdigest(),
            require_current=require_current,
        )

    def _workspace_authority(
        self,
        lineage: NativeDispatchLineage,
        owner_id: UUID,
        tool: ToolId,
        grant_id: UUID,
        account: str,
        cancellation: CancellationToken,
        *,
        decision_for: UUID | None = None,
    ) -> Callable[[AsyncConnection | None], Awaitable[None]]:
        async def authorize(connection: AsyncConnection | None) -> None:
            if connection is None:
                async with self._actions.engine.connect() as local:
                    await authorize(local)
                return
            if (
                lineage.permit.scope_id != self._source_conversation_id
                or lineage.permit.owner_token != self._journal.owner.token
                or not await workspace_owner_live(
                    connection,
                    lineage,
                    owner_id,
                    APPROVAL_RESPOND_SPEC.id if decision_for else tool,
                    decision_for=decision_for,
                )
            ):
                raise WorkspaceError("owner_required")
            current = self._workspace_grant()
            if current is None or (current.grant_id, current.account) != (
                grant_id,
                account,
            ):
                raise WorkspaceError("grant_unavailable")
            if tool in {"gmail.prepare_replacement", "gmail.discard_draft"} and (
                "https://www.googleapis.com/auth/gmail.messages.delete"
                not in current.scopes
            ):
                raise WorkspaceError("scope_missing")
            if cancellation.cancelled or self._closing:
                raise WorkspaceError("cancelled")

        return authorize

    async def _finish_decision(
        self,
        decision: ApprovalRespondInput,
        plan: FrozenToolPlan,
        cancellation: CancellationToken,
        lineage: NativeDispatchLineage,
    ) -> DispatchResult:
        action_id = UUID(decision.action_id)
        async with self._dispatch_lane:
            stored = await self._actions.get(action_id)
            if stored is None:
                raise ToolDispatchDefect("decided action disappeared")
            if stored.tool_name in WRITE_TOOL_IDS and stored.status == "queued":
                contract = stored.current_execution_contract
                frozen = contract.workspace
                if frozen is None or decision.decision != "approve":
                    raise ToolDispatchDefect(
                        "decided workspace action lacks its exact effect"
                    )
                entry = WorkspaceWriteEntry(
                    frozen,
                    await self._actions.original_invocation(stored),
                    self._workspace_authority(
                        lineage,
                        UUID(decision.owner_message_id),
                        stored.tool_name,
                        frozen.grant_id,
                        frozen.account,
                        cancellation,
                        decision_for=action_id,
                    ),
                    contract.workspace_prepare_attempts,
                    contract.workspace_prepare_seconds,
                    contract.workspace_prepare_human_elapsed,
                    contract.workspace_prepare_consent_rounds,
                )
                await execute_recorded_action(
                    self._actions,
                    action_id=action_id,
                    binding=require_current_action_binding(stored, plan),
                    plan=plan,
                    budgets=ExactToolBudgetFactory().create(plan),
                    source_conversation_id=self._source_conversation_id,
                    workspace_entry=entry,
                )
            elif stored.status in {"queued", "executing"}:
                await ActionRecovery(
                    actions=self._actions,
                    work=self._work,
                    events=self._events,
                    attachments=self._attachments,
                    mail_files=self._mail_files,
                    plan=plan,
                    source_conversation_id=self._source_conversation_id,
                    delegation_changed=self._agents.delegations.notify_changed,
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


def _existing_action_result(stored: StoredAction) -> DispatchResult:
    reference = HostRef(str(stored.id))
    if stored.status == "awaiting_approval":
        return DispatchSuspended(reference, WaitingFor.user)
    recorded = action_replay_result(stored)
    if recorded is not None:
        return completed_tool_result(recorded, reference)
    if stored.status in {"queued", "executing", "uncertain"}:
        return DispatchSuspended(reference, WaitingFor.system)
    return host_rejected("action_was_cancelled", reference)


async def execute_recorded_action(
    actions: ActionStore,
    *,
    action_id: UUID,
    binding: ToolBinding[Any, Any, Any],
    plan: FrozenToolPlan,
    budgets: BudgetState,
    source_conversation_id: str,
    workspace_entry: WorkspaceWriteEntry | None = None,
) -> DispatchResult:
    """Enter the same durable position for immediate, approved and recovered work."""
    stored = await actions.get(action_id, source_conversation_id=source_conversation_id)
    if stored is None:
        raise ToolDispatchDefect("recorded action is unavailable in the owner's scope")
    require_current_action_binding(stored, plan)
    grant = plan.grant(binding.spec.id)
    recorder = ActionPositionRecorder(
        store=actions,
        action_id=action_id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=grant.limits.max_attempts,
        source_conversation_id=source_conversation_id,
        workspace_entry=workspace_entry,
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


# These are the durable actions with an original settlement path below.
RECOVERABLE_ACTION_IDS = WRITE_TOOL_IDS.union(
    ATTACHMENT_WRITE_IDS, AGENT_WRITE_IDS, WORK_MUTATION_IDS, EVENT_MUTATION_IDS
)


class ActionRecovery:
    """Bounded action recovery using only each tool's exact evidence procedure."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        work: WorkStore,
        events: EventStore,
        attachments: AttachmentStore,
        mail_files: MailFiles,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        delegation_changed: Callable[[], None],
    ) -> None:
        self._actions = actions
        self._work = work
        self._events = events
        self._attachments = attachments
        self._mail_files = mail_files
        self._plan = plan
        self._source_conversation_id = source_conversation_id
        self._delegation_changed = delegation_changed

    async def recover(self, *, allow_queued_execution: bool = True) -> int:
        if type(allow_queued_execution) is not bool:
            raise ValueError("queued recovery selection must be boolean")
        recovered: set[UUID] = set()
        while candidates := await self._actions.recovery_candidates(
            source_conversation_id=self._source_conversation_id,
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
            stored.status == "executing"
            and stored.tool_name not in RECOVERABLE_ACTION_IDS
        ):
            raise RuntimeError(
                "entered action has no supported reconciliation procedure"
            )
        if stored.tool_name in WRITE_TOOL_IDS:
            self._binding(stored)
            if stored.status == "executing":
                await self._actions.mark_workspace_uncertain(stored.id)
            elif stored.status == "queued":
                if not allow_queued_execution:
                    return
                await self._actions.cancel_nonexecuting(
                    action_id=stored.id,
                    result={
                        "type": "workspace_cancelled_v1",
                        "reason_code": "fresh_owner_required",
                    },
                )
            elif stored.status == "awaiting_approval":
                return
            frozen = stored.current_execution_contract.workspace
            if frozen is not None and isinstance(frozen.effect, FrozenCompose):
                await _discard_mail_stage(self._mail_files, stored.id)
            return
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
                return
            if current.tool_name in ATTACHMENT_WRITE_IDS:
                if (
                    current.tool_name == "attachment.retain"
                    and current.status == "queued"
                ):
                    if allow_queued_execution:
                        await self._actions.cancel_nonexecuting(
                            action_id=current.id,
                            result={
                                "type": "workspace_cancelled_v1",
                                "reason_code": "fresh_owner_required",
                            },
                        )
                    return
                recovered = await self._attachments.recover_action(current.id)
                if recovered is not None:
                    return
                current = await self._require(current.id)
                if current.tool_name == "attachment.retain":
                    # No original put entered. New source bytes need a new owner.
                    await self._actions.resolve_reconciliation(
                        action_id=current.id,
                        status="failed",
                        result={
                            "type": "Failure",
                            "error": {"type": "Unavailable", "id": None},
                        },
                    )
                    return
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
                AGENT_DELEGATE_ID,
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
            raise RuntimeError("action has no supported recovery procedure")
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
            source_conversation_id=self._source_conversation_id,
        )
        self._delegation_changed()
        return (
            not isinstance(result, DispatchSuspended)
            or (await self._require(action_id)).status != "queued"
        )

    def _binding(self, stored: StoredAction) -> ToolBinding[Any, Any, Any]:
        return require_current_action_binding(stored, self._plan)

    async def _require(self, action_id: UUID) -> StoredAction:
        stored = await self._actions.get(
            action_id, source_conversation_id=self._source_conversation_id
        )
        if stored is None:
            raise RuntimeError("recovering action is unavailable in the owner's scope")
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
    "RECOVERABLE_ACTION_IDS",
    "ActionRecovery",
    "NoTelemetry",
    "WriteToolDispatcher",
    "require_current_action_binding",
]

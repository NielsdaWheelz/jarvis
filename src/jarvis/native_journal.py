"""Native attempt evidence and callback receipts; effects stay in existing stores."""

from __future__ import annotations

import json
import logging
from asyncio import to_thread
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from llm_agent_kernel import (
    Checkpoint,
    DispatchCompleted,
    DispatchSuspended,
    HostRef,
    InputId,
    InvocationRecord,
    NativeDefect,
    NativeDefinition,
    NativeDelivery,
    NativeInvocationProposal,
    NativeRecovery,
    NativeRejected,
    NativeReply,
    NativeRequest,
    WaitingFor,
)
from llm_tools import (
    FrozenToolPlan,
    PromptAttribute,
    PromptAttributeName,
    PromptJson,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ToolEffect,
    ToolResult,
    canonical_json_bytes,
)
from provider_runtime.agent_runtime import (
    AgentAccepted,
    AgentAttempt,
    AgentChildObserved,
    AgentControlReceipt,
    AgentFailure,
    AgentMessage,
    AgentNotSubmitted,
    AgentQuotaExhausted,
    AgentSubmission,
    AgentSubmissionRejected,
    AgentTerminal,
    AgentTerminalFailure,
    AgentTurnRef,
    AntigravityLease,
    FrozenJsonDict,
    JsonObject,
    JsonSchemaAgentOutput,
    NativeTerminalEvidence,
    codex_wire_request_fit,
    decode_agent_output,
    ref_to_json,
    terminal_from_json,
    terminal_to_json,
    thaw_json_value,
)
from provider_runtime.agent_runtime.neon_control import NeonControlError
from pydantic import ValidationError
from sqlalchemy import ColumnElement, RowMapping, case, func, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.selectable import CTE

from jarvis.actions import (
    ActionPersistenceDefect,
    current_workspace_owner_delivery,
    recorded_action_result,
    require_locked_action,
    standing_workspace_input,
)
from jarvis.admission import JarvisOwner
from jarvis.agent_tools import AGENT_DELEGATE_ID
from jarvis.approval_tools import (
    APPROVAL_RESPOND_SPEC,
    ApprovalRespondInput,
    ApprovalRespondResult,
)
from jarvis.codex_config import NATIVE_ROUTES, PAID_ROUTES
from jarvis.db import (
    action,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
    read_position,
    work,
)
from jarvis.home_notices import enqueue_notice
from jarvis.home_pages import DEFAULT_EXPORT, HomePages
from jarvis.home_reads import draft_for_request, proposal_presented, reference_context
from jarvis.home_refs import DraftPresentationRef, ViewRef
from jarvis.mail_revisions import VerifiedWorkspaceDraft
from jarvis.memory_service import MemoryService
from jarvis.messages import (
    CATCHUP_SOURCE,
    MAX_TRACE_BYTES,
    cancel_unentered_actions,
    causal_component_ids,
    current_native_retry,
    latest_control,
    native_fault_retry_used,
    native_recovery_input,
    native_retry_evidence,
    native_retry_pin,
    queue_native_retry,
)
from jarvis.native_failure_notice import record_parking_notice
from jarvis.native_protocol import (
    FOREGROUND_RECOVERY_PROFILE,
    NATIVE_OUTPUT_NAME,
    NATIVE_REQUEST_SCHEMA,
    JarvisNativeMessage,
    JarvisTerminal,
)
from jarvis.ownership import (
    Database,
    DeploymentOwnershipDefect,
    lock_conversation,
    memory_is_admitted,
)
from jarvis.terminal import (
    Answered,
    Partial,
    Presentation,
    Progress,
    RenderedTerminal,
    Silent,
)
from jarvis.tool_results import completed_tool_result, host_rejected
from jarvis.work_tools import WORK_CREATE_SPEC
from jarvis.workspace_checks import WorkspaceOccurrence, WorkspaceResult
from jarvis.workspace_enrollment import WorkspaceEnrollment
from jarvis.workspace_host import WorkspaceHost, check_observations, is_workspace_wake
from jarvis.write_tools import WORKSPACE_MAIL_IMPLEMENTATION, WRITE_TOOL_IDS

if TYPE_CHECKING:
    from provider_runtime.agent_runtime.neon_control import (
        NeonChildFacts,
        NeonControl,
        NeonFirstSampleRefusal,
        NeonLease,
    )

LOGGER = logging.getLogger(__name__)
NEON_REFILL_INTERVAL = timedelta(seconds=60)
_ACTIVE_REQUEST = native_attempt.c.request["schema_version"].as_string() == (
    NATIVE_REQUEST_SCHEMA
)
_ACTIVE_ROUTE = case((_ACTIVE_REQUEST, native_attempt.c.request["route"].as_string()))


def _neon_capacity(
    status: str, retry_after: float | None, now: datetime
) -> dict[str, object]:
    return {
        "status": status,
        "requires_billing_probe": status == "prepaid_depleted",
        "check_after": (
            now + max(NEON_REFILL_INTERVAL, timedelta(seconds=retry_after or 0))
        ).isoformat(),
    }


def _contains_nul(value: object) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str) and "\x00" in current:
            return True
        if isinstance(current, dict):
            for key, item in cast(dict[str, object], current).items():
                pending.extend((key, item))
        elif isinstance(current, list):
            pending.extend(cast(list[object], current))
    return False


def _sections_json(sections: PromptSections) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for section in sections.sections:
        body = section.body
        values.append(
            {
                "kind": str(section.kind),
                "attributes": [
                    {"name": str(item.name), "value": item.value}
                    for item in section.attributes
                ],
                "body": None
                if body is None
                else {"text": body.text}
                if isinstance(body, PromptText)
                else {"json": body.value}
                if isinstance(body, PromptJson)
                else {"sections": _sections_json(body)},
            }
        )
    return values


def _sections(value: Any) -> PromptSections:
    return PromptSections(
        PromptSection(
            PromptSectionKind(item["kind"]),
            tuple(
                PromptAttribute(
                    PromptAttributeName(attribute["name"]), attribute["value"]
                )
                for attribute in item["attributes"]
            ),
            None
            if item["body"] is None
            else PromptText(item["body"]["text"])
            if "text" in item["body"]
            else PromptJson(item["body"]["json"])
            if "json" in item["body"]
            else _sections(item["body"]["sections"]),
        )
        for item in value
    )


@dataclass(frozen=True, slots=True)
class _SealedNativeTurn:
    attempt_id: str
    input_ids: tuple[InputId, ...]
    output: JsonSchemaAgentOutput
    terminal: AgentTerminal
    initial_delivery_proven: bool

    def decode_final(self) -> JarvisTerminal:
        value = decode_agent_output(self.output, self.terminal)
        return JarvisTerminal.from_seal(self.output.name, thaw_json_value(value))


@dataclass(frozen=True, slots=True)
class ProductSettlement:
    """The disposition written by this transaction, if any."""

    status: Literal["committed", "failed", "stale"] | None = None
    completed: tuple[UUID, ...] = ()
    eligibility_changed: bool = False
    workspace_match: WorkspaceOccurrence | None = None


class NeonOpeningUnavailable(NativeDefect):
    """The host could not arm the tree before preparing a stock request."""


class NativeContentDefect(NativeDefect):
    """A well-formed final response contradicts its delivered inputs or actions."""


class StaleNativeProduct(NativeDefect):
    """The original delivery no longer has product settlement authority."""


class StaleCatchupInventory(StaleNativeProduct):
    """The exact authorized historical inventory no longer matches."""


async def recover_sealed_turn(
    connection: AsyncConnection, scope: str, attempt_id: str
) -> _SealedNativeTurn | None:
    """Reopen inference facts without current provider or execution authority."""
    row = (
        (
            await connection.execute(
                select(
                    native_attempt.c.conversation_id,
                    native_attempt.c.terminal,
                    native_attempt.c.request["provider_attempt"].label(
                        "provider_attempt"
                    ),
                    native_attempt.c.request["output"].label("output"),
                    native_attempt.c.request["input_ids"].label("input_ids"),
                    native_attempt.c.request["route"].as_string().label("route"),
                    native_attempt.c.request["schema_version"]
                    .as_string()
                    .label("request_schema"),
                    native_attempt.c.native_binding,
                ).where(native_attempt.c.id == UUID(attempt_id))
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["terminal"] is None:
        return None
    if row["conversation_id"] != scope:
        raise NativeDefect("sealed inference is outside this conversation")
    output: dict[str, Any] = row["output"]
    if row["request_schema"] != NATIVE_REQUEST_SCHEMA or output != {
        "name": NATIVE_OUTPUT_NAME,
        "schema": JarvisNativeMessage.model_json_schema(),
    }:
        raise NativeDefect(
            "retired native contract requires original-release settlement"
        )
    terminal = terminal_from_json(row["terminal"])
    prepared = AgentAttempt(**row["provider_attempt"])
    if (
        not isinstance(terminal.evidence, NativeTerminalEvidence)
        or terminal.evidence.attempt != prepared
        or prepared.attempt_id != attempt_id
    ):
        raise NativeDefect("product recovery requires original sealed native evidence")
    binding = row["native_binding"]
    ref = terminal.evidence.native_ref
    route = row["route"]
    if (
        route not in NATIVE_ROUTES
        or not isinstance(ref, AgentTurnRef)
        or ref.session_ref.profile_key != route
        or binding != _turn_binding(ref)
    ):
        raise NativeDefect("native terminal changed the prepared account or binding")
    return _SealedNativeTurn(
        attempt_id,
        tuple(map(InputId, row["input_ids"])),
        JsonSchemaAgentOutput(output["name"], output["schema"]),
        terminal,
        True,
    )


def _turn_binding(turn: AgentTurnRef) -> dict[str, object]:
    return {
        "session_ref": thaw_json_value(ref_to_json(turn.session_ref)),
        "native_turn_id": turn.native_turn_id,
    }


def _recovery_grant(grant: WorkspaceEnrollment | None) -> dict[str, str] | None:
    return (
        {"account": grant.account, "grant_id": str(grant.grant_id)} if grant else None
    )


def _provider_binding(definition: NativeDefinition) -> dict[str, str]:
    provider = definition.provider
    return {
        "backend": provider.backend,
        "transport": provider.transport,
        "model": provider.model_key,
        "effort": provider.reasoning,
    }


def _route_request_fingerprint(
    request: NativeRequest, document: dict[str, object]
) -> str:
    return sha256(
        canonical_json_bytes(
            {
                "request": request.fingerprint,
                "route": document["route"],
                "provider": document["provider"],
                "definition_fingerprint": document["definition_fingerprint"],
                "provider_attempt": document["provider_attempt"],
            }
        )
    ).hexdigest()


class PostgresNativeJournal:
    def __init__(
        self,
        database: Database,
        *,
        definition: NativeDefinition,
        plan: FrozenToolPlan,
        owner: JarvisOwner,
        memory: MemoryService,
        neon_control: NeonControl | None = None,
        antigravity: AntigravityLease | None = None,
        workspace_grant: WorkspaceEnrollment | None = None,
    ) -> None:
        self.database = database
        self.definition = definition
        self.plan = plan
        self.owner = owner
        self.memory = memory
        self.neon_control = neon_control
        self.antigravity = antigravity
        self.workspace_grant = workspace_grant
        self.neon_lease: NeonLease | None = None
        self.sdk_upstream_entries: int | None = None

    async def recover(self, attempt_id: str) -> NativeRecovery | None:
        async with self.database.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(
                            native_attempt.c.id,
                            native_attempt.c.request,
                            native_attempt.c.request_fingerprint,
                            native_attempt.c.terminal,
                        ).where(
                            native_attempt.c.id == UUID(attempt_id),
                            native_attempt.c.terminal_at.is_not(None),
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["terminal"] is None:
            return None
        request = self.restore_request(row)
        document = row["request"]
        return NativeRecovery(
            request,
            document["definition_fingerprint"],
            AgentAttempt(**document["provider_attempt"]),
            terminal_from_json(row["terminal"]),
        )

    def restore_request(self, row: RowMapping) -> NativeRequest:
        value = row["request"]
        if (
            value.get("schema_version") != NATIVE_REQUEST_SCHEMA
            or value.get("route") != self.definition.provider.auth.profile_key
            or value["route"] not in NATIVE_ROUTES
            or value.get("provider") != _provider_binding(self.definition)
            or value["definition_fingerprint"]
            != self.definition.session_fingerprint(self.plan)
            or value["plan_revision"] != self.plan.plan_revision
        ):
            raise NativeDefect("native recovery contract changed")
        request = NativeRequest(
            attempt_id=str(row["id"]),
            permit=self.owner.permit(
                value["operation_id"], value["parent_invocation_id"]
            ),
            scope=value["scope"],
            input_ids=tuple(map(InputId, value["input_ids"])),
            canonical_sections=_sections(value["canonical_sections"]),
            submitted_sections=_sections(value["submitted_sections"]),
            plan=self.plan,
            recovery_policy=value["recovery_policy"],
            deadline_at=None
            if value["deadline_at"] is None
            else datetime.fromisoformat(value["deadline_at"]),
            through_checkpoint=None
            if value["through_checkpoint"] is None
            else Checkpoint(value["through_checkpoint"]),
        )
        if _route_request_fingerprint(request, value) != row["request_fingerprint"]:
            raise NativeDefect("native recovery request bytes changed")
        return request

    async def arm(
        self,
        request: NativeRequest,
        provider_attempt: AgentAttempt,
        *,
        definition_fingerprint: str,
        submitted_request: JsonObject,
    ) -> None:
        if provider_attempt.attempt_id != request.attempt_id:
            raise NativeDefect("prepared provider identity differs from native request")
        await self.owner.require_current(request.permit)
        if not isinstance(self.definition.output, JsonSchemaAgentOutput):
            raise NativeDefect(
                "Jarvis main requires an original structured output contract"
            )
        route = self.definition.provider.auth.profile_key
        if route not in NATIVE_ROUTES:
            raise NativeDefect("native request has an unknown route")
        restricted = request.plan.profile.id == FOREGROUND_RECOVERY_PROFILE
        document: dict[str, Any] = {
            "schema_version": NATIVE_REQUEST_SCHEMA,
            "route": route,
            "provider": _provider_binding(self.definition),
            "output": {
                "name": self.definition.output.name,
                "schema": thaw_json_value(self.definition.output.schema),
            },
            "definition_fingerprint": definition_fingerprint,
            "provider_attempt": asdict(provider_attempt),
            "submitted_request": thaw_json_value(submitted_request),
            "operation_id": request.permit.operation_id,
            "parent_invocation_id": request.permit.parent_invocation_id,
            "scope": request.scope,
            "input_ids": list(request.input_ids),
            "canonical_sections": _sections_json(request.canonical_sections),
            "submitted_sections": _sections_json(request.submitted_sections),
            "plan_revision": request.plan.plan_revision,
            "recovery_policy": request.recovery_policy,
            "deadline_at": None
            if request.deadline_at is None
            else request.deadline_at.isoformat(),
            "through_checkpoint": request.through_checkpoint,
        }
        canonical_json_bytes(document)
        if route in PAID_ROUTES:
            params = submitted_request.get("params")
            root = (
                submitted_request.get("root")
                if route == "agy_neon"
                else (
                    params.get("threadId")
                    if isinstance(params, FrozenJsonDict)
                    else None
                )
            )
            if self.neon_control is None or not isinstance(root, str) or not root:
                raise NativeDefect("paid native request lacks its control lease")
            document["native_root"] = root
            sdk = self.antigravity
            try:
                if route == "agy_neon":
                    sdk_text = submitted_request.get("text")
                    if (
                        sdk is None
                        or sdk.turn.session_ref.native_session_id != root
                        or sdk.turn.native_turn_id != submitted_request.get("turn")
                        or not isinstance(sdk_text, str)
                    ):
                        raise NativeDefect(
                            "Antigravity paid authorization changed its prepared turn"
                        )
                    encoded = sdk_text.encode("utf-8")
                    self.neon_lease = await self.neon_control.arm_sdk(
                        attempt_id=request.attempt_id,
                        owner_epoch=str(request.permit.owner_token),
                        root_thread_id=root,
                        generation=request.attempt_id,
                        turn_id=sdk.turn.native_turn_id,
                        bearer=sdk.bearer,
                        input_bytes=len(encoded),
                        input_sha256=sha256(encoded).hexdigest(),
                        on_delivery=lambda turn_id: self._record_neon_delivery(
                            request, turn_id
                        ),
                    )
                else:
                    self.neon_lease = await self.neon_control.arm(
                        attempt_id=request.attempt_id,
                        owner_epoch=str(request.permit.owner_token),
                        root_thread_id=root,
                        generation=request.attempt_id,
                        on_delivery=lambda turn_id: self._record_neon_delivery(
                            request, turn_id
                        ),
                        on_child=lambda child: self.record_neon_child(request, child),
                    )
            except (OSError, NeonControlError) as error:
                raise NeonOpeningUnavailable(
                    "paid native control unavailable"
                ) from error
        async with self.database.begin() as connection:
            await lock_conversation(connection, request.permit.scope_id)
            if (
                await connection.scalar(latest_control(request.permit.scope_id))
                == "pause"
            ):
                raise NativeDefect("native opening lost active owner control")
            admitted = (
                await connection.execute(
                    select(message.c.id, message.c.source, message.c.trace)
                    .where(
                        message.c.id.in_(tuple(map(UUID, request.input_ids))),
                        message.c.source_conversation_id == request.permit.scope_id,
                        message.c.role.in_(("owner", "host")),
                        message.c.control_kind.is_(None),
                        message.c.request_state.in_(("pending", "waiting")),
                        message.c.processing_parked_at.is_(None),
                        native_recovery_input == restricted,
                        message.c.request_state == "pending" if restricted else true(),
                        message.c.native_retry_after.is_(None)
                        | (message.c.native_retry_after <= func.now()),
                        message.c.native_retry_after.is_(None)
                        | (
                            current_native_retry()
                            & (native_retry_pin.is_(None) | (native_retry_pin == route))
                        ),
                    )
                    .order_by(message.c.id)
                    .with_for_update()
                )
            ).all()
            if len(admitted) != len(request.input_ids):
                raise NativeDefect("native input authority is no longer live")
            existing = await connection.scalar(
                select(native_attempt.c.id).where(
                    native_attempt.c.conversation_id == request.permit.scope_id,
                    native_attempt.c.fenced_at.is_(None),
                    native_attempt.c.product_outcome.is_(None),
                )
            )
            if existing is not None:
                raise NativeDefect(
                    "another native attempt still owns this conversation"
                )
            seq = (
                await connection.scalar(
                    select(func.max(native_attempt.c.attempt_seq)).where(
                        native_attempt.c.conversation_id == request.permit.scope_id
                    )
                )
                or 0
            ) + 1
            document["control_sequence"] = (
                await connection.scalar(
                    select(func.max(message.c.control_sequence)).where(
                        message.c.source_conversation_id == request.permit.scope_id
                    )
                )
                or 0
            )
            if restricted:
                catchup = [row.id for row in admitted if row.source == CATCHUP_SOURCE]
                if catchup:
                    if len(admitted) != 1:
                        raise NativeDefect("mail catch-up must open alone")
                    from jarvis.recovery_catchup import CatchupStale, validate_catchup

                    try:
                        await validate_catchup(
                            connection,
                            request.permit.scope_id,
                            catchup[0],
                            document["control_sequence"],
                        )
                    except CatchupStale as error:
                        raise StaleCatchupInventory(
                            "mail catch-up lost its source"
                        ) from error
                document["recovery_origins"] = {
                    str(row.id): native_retry_evidence(row.trace).get(
                        "origin_attempt_id"
                    )
                    for row in admitted
                }
                document["recovery_retries"] = {
                    str(row.id): native_retry_evidence(row.trace).get("attempt_id")
                    for row in admitted
                }
                document["recovery_grant"] = _recovery_grant(self.workspace_grant)
                if any(
                    origin is None and UUID(identifier) not in catchup
                    for identifier, origin in document["recovery_origins"].items()
                ):
                    raise NativeDefect(
                        "restricted opening lacks original retry evidence"
                    )
            await connection.execute(
                insert(native_attempt).values(
                    id=UUID(request.attempt_id),
                    conversation_id=request.permit.scope_id,
                    attempt_seq=seq,
                    owner_epoch=str(request.permit.owner_token),
                    memory_admitted=memory_is_admitted(connection),
                    stock_observations_pending=(
                        memory_is_admitted(connection) and self.memory.jarvis_admitted
                    ),
                    request_fingerprint=_route_request_fingerprint(request, document),
                    request=document,
                    armed_at=datetime.now(UTC),
                    recovery_pending=True,
                )
            )

    async def close_neon(self, attempt_id: str) -> NeonFirstSampleRefusal | None:
        lease, self.neon_lease = self.neon_lease, None
        if lease is None:
            return None
        try:
            await lease.close()
        except DeploymentOwnershipDefect:
            raise
        except Exception as error:
            LOGGER.warning(
                "paid control ended without proof: attempt=%s type=%s",
                attempt_id,
                type(error).__name__,
            )
            return None
        self.sdk_upstream_entries = lease.sdk_upstream_entries
        capacity = lease.capacity
        if capacity is not None:
            await self.owner.require_current(
                self.owner.permit("jarvis-product:" + attempt_id)
            )
            async with self.database.begin() as connection:
                row = await _locked_attempt(
                    connection,
                    self.owner,
                    attempt_id,
                    native_attempt.c.local_outcome,
                    live=False,
                )
                await connection.execute(
                    update(native_attempt)
                    .where(native_attempt.c.id == row["id"])
                    .values(
                        local_outcome={
                            **(row["local_outcome"] or {}),
                            "neon_capacity": _neon_capacity(
                                capacity.status, capacity.retry_after, datetime.now(UTC)
                            ),
                        }
                    )
                )
        return lease.first_sample_refusal

    async def record_neon_child(
        self, request: NativeRequest, child: NeonChildFacts | AgentChildObserved
    ) -> None:
        if isinstance(child, AgentChildObserved):
            if self.antigravity is None or child.turn != self.antigravity.turn:
                raise NativeDefect("Antigravity child changed its prepared root turn")
            child_id, parent_id = child.child_id, child.parent_id
        else:
            child_id, parent_id = child.thread_id, child.parent_thread_id
        await self.owner.require_current(request.permit)
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                request.attempt_id,
                native_attempt.c.local_outcome,
            )
            local: dict[str, Any] = row["local_outcome"]
            if not local or local.get("neon_may_have_delivered") is None:
                raise NativeDefect("paid child preceded the durable delivery boundary")
            children: dict[str, object] = local.get("neon_children", {})
            facts = {
                "parent_thread_id": parent_id,
                "requested_model": self.definition.provider.model_key,
                "model_version": child.model_version,
                "effort": child.effort,
            }
            previous = children.get(child_id)
            if previous == facts:
                return
            if previous is not None:
                raise NativeDefect("paid child changed its observed provider facts")
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(
                    local_outcome={
                        **local,
                        "neon_children": {**children, child_id: facts},
                    }
                )
            )

    async def _record_neon_delivery(self, request: NativeRequest, turn_id: str) -> None:
        await self.owner.require_current(request.permit)
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                request.attempt_id,
                native_attempt.c.local_outcome,
            )
            local: dict[str, Any] = row["local_outcome"] or {
                "terminal": None,
                "control_receipts": {},
                "fence_reason": None,
            }
            if local.get("neon_refusal") is not None:
                raise NativeDefect("paid delivery follows a recorded refusal")
            if local.get("neon_may_have_delivered") is None:
                await connection.execute(
                    update(native_attempt)
                    .where(native_attempt.c.id == row["id"])
                    .values(local_outcome={**local, "neon_may_have_delivered": turn_id})
                )

    async def bind(self, attempt_id: str, native_turn: AgentTurnRef) -> None:
        if (
            native_turn.session_ref.profile_key
            != self.definition.provider.auth.profile_key
            or native_turn.session_ref.backend != self.definition.provider.backend
            or native_turn.session_ref.transport != self.definition.provider.transport
            or (self.antigravity is not None and self.antigravity.turn != native_turn)
        ):
            raise NativeDefect("native turn binding changed the prepared account")
        binding = _turn_binding(native_turn)
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                attempt_id,
                native_attempt.c.native_binding,
                native_attempt.c.submission_evidence,
                native_attempt.c.request["provider_attempt"].label("provider_attempt"),
                live=False,
            )
            accepted = _evidence(
                AgentAccepted(AgentAttempt(**row["provider_attempt"]), native_turn)
            )
            if row["native_binding"] is not None and row["native_binding"] != binding:
                raise NativeDefect("native turn binding changed")
            if row["submission_evidence"] not in (None, accepted):
                raise NativeDefect(
                    "native turn contradicts its original submission evidence"
                )
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(native_binding=binding, submission_evidence=accepted)
            )

    async def record_invocation(
        self, proposal: NativeInvocationProposal
    ) -> InvocationRecord:
        arguments = thaw_json_value(proposal.arguments)
        if _contains_nul(arguments):
            raise NativeDefect("native callback evidence contains nul")
        binding = self.plan.catalog_view.binding(proposal.tool_id)
        accepted = proposal.validation_error is None
        request_id = (
            UUID(cast(dict[str, Any], arguments)["request_ref"])
            if accepted
            and binding.spec.effect is ToolEffect.Write
            and str(binding.spec.id) not in {"memory.save_note", "approval.respond"}
            else None
        )
        document = {
            "arguments": arguments,
            "input_ids": list(proposal.input_ids),
            "through_checkpoint": proposal.through_checkpoint,
        }
        contract = {
            "plan_revision": proposal.plan_revision,
            "tool_contract_revision": proposal.tool_contract_revision,
            "implementation_revision": proposal.implementation_revision,
            "policy_revision": proposal.policy_revision,
            "effect": binding.spec.effect.value,
        }
        async with self.database.begin() as connection:
            await lock_conversation(connection, self.owner.scope_id)
            owner_input = None
            if request_id is not None:
                owner_input = (
                    (
                        await connection.execute(
                            select(message)
                            .where(message.c.id == request_id)
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            await _locked_attempt(connection, self.owner, proposal.attempt_id)
            old = (
                (
                    await connection.execute(
                        select(native_invocation)
                        .where(
                            native_invocation.c.attempt_id == UUID(proposal.attempt_id),
                            native_invocation.c.native_call_id == proposal.call_id,
                        )
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if old is not None:
                if (
                    old["proposal_digest"] != proposal.proposal_digest
                    or old["proposal"]["arguments"] != arguments
                    or old["frozen_contract"] != contract
                    or old["validation_error"]
                    != (
                        None
                        if accepted
                        else asdict(cast(NativeRejected, proposal.validation_error))
                    )
                ):
                    raise NativeDefect("native callback identity changed")
                original = replace(
                    proposal,
                    input_ids=tuple(
                        InputId(value) for value in old["proposal"]["input_ids"]
                    ),
                    through_checkpoint=(
                        Checkpoint(old["proposal"]["through_checkpoint"])
                        if old["proposal"]["through_checkpoint"] is not None
                        else None
                    ),
                )
                return InvocationRecord(
                    str(old["id"]),
                    old["ordinal"],
                    original,
                    await self._reply(connection, old),
                )
            if request_id is not None:
                delivered = await connection.scalar(
                    select(native_input_delivery.c.message_id).where(
                        native_input_delivery.c.attempt_id == UUID(proposal.attempt_id),
                        native_input_delivery.c.message_id == request_id,
                        proven_native_delivery,
                    )
                )
                if (
                    owner_input is None
                    or owner_input["role"] not in {"owner", "host"}
                    or owner_input["source_conversation_id"] != self.owner.scope_id
                    or owner_input["request_state"] not in {"pending", "waiting"}
                    or owner_input["processing_parked_at"] is not None
                    or owner_input["control_kind"] is not None
                    or str(request_id) not in proposal.input_ids
                    or delivered is None
                ):
                    raise NativeDefect(
                        "accepted Write request_ref has no live delivered input"
                    )
            ordinal = (
                await connection.scalar(
                    select(func.max(native_invocation.c.ordinal)).where(
                        native_invocation.c.attempt_id == UUID(proposal.attempt_id)
                    )
                )
                or 0
            ) + 1
            identifier = uuid4()
            await connection.execute(
                insert(native_invocation).values(
                    id=identifier,
                    attempt_id=UUID(proposal.attempt_id),
                    ordinal=ordinal,
                    native_call_id=proposal.call_id,
                    request_message_id=request_id,
                    tool_id=str(proposal.tool_id),
                    proposal_digest=proposal.proposal_digest,
                    proposal=document,
                    frozen_contract=contract,
                    validation="accepted" if accepted else "rejected",
                    validation_error=None
                    if accepted
                    else asdict(cast(NativeRejected, proposal.validation_error)),
                )
            )
        await self.memory.publish()
        return InvocationRecord(str(identifier), ordinal, proposal, None)

    async def _reply(
        self, connection: AsyncConnection, row: RowMapping
    ) -> NativeReply | None:
        value = row["reply_receipt"]
        if value is None:
            return None
        if value["type"] == "tool_result_ref":
            if row["action_id"] is not None:
                result = await recorded_action_result(connection, row["action_id"])
            else:
                result = await connection.scalar(
                    select(read_position.c.result).where(
                        read_position.c.position == row["read_position"]
                    )
                )
            if result is None:
                raise NativeDefect("callback result reference has no recorded result")
            dispatch = DispatchCompleted(
                cast(ToolResult, result),
                value["wire_text"],
                HostRef(value["host_ref"])
                if value.get("host_ref") is not None
                else None,
            )
        elif value["type"] == "local_result":
            dispatch = DispatchCompleted(
                value["result"],
                value["wire_text"],
                HostRef(value["host_ref"])
                if value.get("host_ref") is not None
                else None,
            )
        elif value["type"] in {"pending_action", "recovery_required"}:
            dispatch = DispatchSuspended(
                HostRef(str(row["action_id"])), WaitingFor(value["waiting_for"])
            )
        elif value.get("kind") == "host":
            dispatch = DispatchCompleted(
                value["rejection"],
                value["wire_text"],
                HostRef(value["host_ref"]) if value["host_ref"] else None,
            )
        else:
            dispatch = NativeRejected(value["code"], value["text"])
        return NativeReply(value["wire_text"], value["success"], dispatch)

    async def record_reply(self, invocation_id: str, receipt: NativeReply) -> None:
        async with self.database.begin() as connection:
            current = (
                (
                    await connection.execute(
                        select(native_invocation).where(
                            native_invocation.c.id == UUID(invocation_id)
                        )
                    )
                )
                .mappings()
                .one()
            )
            await _locked_attempt(
                connection, self.owner, str(current["attempt_id"]), live=False
            )
            row = (
                (
                    await connection.execute(
                        select(native_invocation)
                        .where(native_invocation.c.id == UUID(invocation_id))
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if (
                row["reply_receipt"] is not None
                and row["reply_receipt"]["type"] == "local_result"
            ):
                if await self._reply(connection, row) != receipt:
                    raise NativeDefect(
                        "callback reply changed after durable acceptance"
                    )
                return
            result = receipt.result
            value: dict[str, object] = {
                "wire_text": receipt.text,
                "success": receipt.success,
            }
            links: dict[str, object] = {}
            if isinstance(result, NativeRejected):
                value.update(type="rejected", code=result.code, text=result.text)
            elif isinstance(result, DispatchSuspended):
                links["action_id"] = UUID(str(result.host_ref))
                value.update(
                    type="pending_action"
                    if result.waiting_for is WaitingFor.user
                    else "recovery_required",
                    waiting_for=result.waiting_for.value,
                )
            elif (
                isinstance(result.result.get("error"), dict)
                and result.result["error"].get("type") == "HostRejected"
            ):
                value.update(
                    type="rejected",
                    kind="host",
                    rejection=result.result,
                    host_ref=None if result.host_ref is None else str(result.host_ref),
                )
            elif row["tool_id"] == "web.search" and result.result == {
                "type": "Failure",
                "error": {"type": "InvalidCursor"},
            }:
                value.update(type="local_result", result=result.result, host_ref=None)
            elif (
                result.host_ref is None
                and result.result["type"] == "Failure"
                and (
                    row["tool_id"] in WRITE_TOOL_IDS
                    or (
                        row["tool_id"] in {"agent.start", AGENT_DELEGATE_ID}
                        and result.result["error"].get("type") == "AgentFailure"
                    )
                )
            ):
                # Preparation and placement can refuse before an action exists.
                value.update(type="local_result", result=result.result, host_ref=None)
            elif result.host_ref is not None:
                reference = str(result.host_ref)
                if reference.startswith("native-invocation:"):
                    recorded = await connection.scalar(
                        select(read_position.c.result).where(
                            read_position.c.position == reference
                        )
                    )
                    if recorded != result.result:
                        raise NativeDefect(
                            "replayed read differs from its original recorder result"
                        )
                    links["read_position"] = reference
                else:
                    identifier = UUID(reference)
                    recorded = await recorded_action_result(connection, identifier)
                    if (
                        row["tool_id"] in WRITE_TOOL_IDS
                        and result.result["type"] == "Failure"
                        and result.result["error"].get("code") == "uncertain"
                        and row["action_id"] == identifier
                    ):
                        # A later acknowledgement can advance the action.
                        if recorded != result.result:
                            earlier = await connection.scalar(
                                select(message.c.id).where(
                                    message.c.source == "action",
                                    message.c.source_conversation_id
                                    == self.owner.scope_id,
                                    message.c.source_message_id
                                    == f"{identifier}:uncertain",
                                    message.c.trace["action_id"].as_string()
                                    == reference,
                                )
                            )
                            if earlier is None:
                                raise NativeDefect(
                                    "workspace uncertainty lacks original evidence"
                                )
                        recorded = result.result
                        value.update(
                            type="local_result", result=recorded, host_ref=reference
                        )
                    if recorded != result.result:
                        raise NativeDefect(
                            "replayed action differs from its original recorder result"
                        )
                    links["action_id"] = identifier
                if value.get("type") != "local_result":
                    value.update(
                        type="tool_result_ref", result_ref=reference, host_ref=reference
                    )
            else:
                position = "native-invocation:" + invocation_id
                recorded = await connection.scalar(
                    select(read_position.c.result).where(
                        read_position.c.position == position
                    )
                )
                if recorded == result.result:
                    links["read_position"] = position
                    value.update(type="tool_result_ref", result_ref=position)
                else:
                    # Host rejections do not enter the executor or create an action.
                    value.update(
                        type="rejected", code="invalid_arguments", text=receipt.text
                    )
            if row["reply_receipt"] is not None:
                if row["reply_receipt"] != value:
                    raise NativeDefect(
                        "callback reply changed after durable acceptance"
                    )
                return
            await connection.execute(
                update(native_invocation)
                .where(native_invocation.c.id == row["id"])
                .values(
                    **links, reply_receipt=value, reply_recorded_at=datetime.now(UTC)
                )
            )

        await self.memory.publish()

    async def respond_approval(
        self,
        invocation_id: str,
        arguments: ApprovalRespondInput,
        *,
        workspace_grant: Callable[[], WorkspaceEnrollment | None] | None = None,
    ) -> DispatchCompleted:
        """The decision and its original reply have one commit boundary."""
        await self.owner.require_current(
            self.owner.permit(
                "jarvis-approval:" + invocation_id,
                invocation_id,
            )
        )
        binding = self.plan.catalog_view.binding(APPROVAL_RESPOND_SPEC.id)
        self.plan.grant(binding.spec.id)
        if binding.spec != APPROVAL_RESPOND_SPEC:
            raise NativeDefect(
                "approval binding differs from its declared local contract"
            )
        identifier = UUID(invocation_id)
        target_id = UUID(arguments.action_id)
        async with self.database.begin() as connection:
            await lock_conversation(connection, self.owner.scope_id)
            invocation = (
                (
                    await connection.execute(
                        select(native_invocation).where(
                            native_invocation.c.id == identifier
                        )
                    )
                )
                .mappings()
                .one()
            )
            if (
                invocation["frozen_contract"]
                != {
                    "plan_revision": self.plan.plan_revision,
                    "tool_contract_revision": binding.spec.tool_contract_revision,
                    "implementation_revision": binding.implementation_revision,
                    "policy_revision": binding.policy_revision,
                    "effect": ToolEffect.Write.value,
                }
                or invocation["tool_id"] != "approval.respond"
                or invocation["validation"] != "accepted"
                or invocation["proposal"]["arguments"]
                != arguments.model_dump(mode="json")
            ):
                raise NativeDefect(
                    "local decision differs from its admitted invocation"
                )
            input_ids = tuple(map(UUID, invocation["proposal"]["input_ids"]))
            if invocation["reply_receipt"] is None:
                live = await connection.scalar(
                    select(message.c.id)
                    .join(
                        native_input_delivery,
                        native_input_delivery.c.message_id == message.c.id,
                    )
                    .where(
                        native_input_delivery.c.attempt_id == invocation["attempt_id"],
                        proven_native_delivery,
                        message.c.id.in_(input_ids),
                        message.c.source_conversation_id == self.owner.scope_id,
                        message.c.role.in_(("owner", "host")),
                        message.c.control_kind.is_(None),
                        message.c.request_state.in_(("pending", "waiting")),
                        message.c.processing_parked_at.is_(None),
                    )
                    .limit(1)
                )
                if live is None:
                    return host_rejected("approval_owner_required")
            target = (
                (
                    await connection.execute(
                        select(action).where(action.c.id == target_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
            request_ids = set(input_ids) | {UUID(arguments.owner_message_id)}
            if target is not None:
                request_ids.add(target["origin_message_id"])
            inputs = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(request_ids))
                        .order_by(message.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            await _locked_attempt(connection, self.owner, str(invocation["attempt_id"]))
            invocation = (
                (
                    await connection.execute(
                        select(native_invocation)
                        .where(native_invocation.c.id == identifier)
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if invocation["reply_receipt"] is not None:
                reply = await self._reply(connection, invocation)
                if reply is None or not isinstance(reply.result, DispatchCompleted):
                    raise NativeDefect("local decision has an invalid original receipt")
                return reply.result
            owner_message = next(
                (
                    item
                    for item in inputs
                    if item["id"] == UUID(arguments.owner_message_id)
                ),
                None,
            )
            if (
                owner_message is None
                or owner_message["role"] != "owner"
                or owner_message["source"] == "initialize_state"
                or owner_message["source_conversation_id"] != self.owner.scope_id
            ):
                return host_rejected("approval_owner_required")
            if target is None:
                return host_rejected("approval_target_missing")
            if (
                any(
                    item["id"] in input_ids and standing_workspace_input(item)
                    for item in inputs
                )
                or target["tool_name"] in WRITE_TOOL_IDS
            ):
                if (
                    not await current_workspace_owner_delivery(
                        connection,
                        invocation["attempt_id"],
                        input_ids,
                        owner_message["id"],
                    )
                    or owner_message["control_kind"] is not None
                    or standing_workspace_input(owner_message)
                    or owner_message["request_state"] not in {"pending", "waiting"}
                    or owner_message["processing_parked_at"] is not None
                ):
                    return host_rejected("approval_owner_required")
            if target["tool_name"] in WRITE_TOOL_IDS:
                from jarvis.write_dispatch import require_current_action_binding

                stored = await require_locked_action(connection, target_id)
                try:
                    require_current_action_binding(stored, self.plan)
                except RuntimeError:
                    return host_rejected("approval_ineligible")
                frozen = stored.current_execution_contract.workspace
                if arguments.decision == "approve":
                    current = workspace_grant() if workspace_grant is not None else None
                    if (
                        current is None
                        or frozen is None
                        or (current.grant_id, current.account)
                        != (frozen.grant_id, frozen.account)
                    ):
                        return host_rejected("workspace_grant_unavailable")
            elif target["tool_name"] in {"gmail.send_draft", "gmail.update_draft"}:
                return host_rejected("approval_ineligible")
            origin = next(
                (item for item in inputs if item["id"] == target["origin_message_id"]),
                None,
            )
            if (
                origin is None
                or origin["source_conversation_id"] != self.owner.scope_id
            ):
                return host_rejected("approval_target_foreign")
            target = (
                (
                    await connection.execute(
                        select(action).where(action.c.id == target_id).with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            previous = (
                await connection.execute(
                    select(native_invocation.c.reply_receipt)
                    .where(
                        native_invocation.c.action_id == target_id,
                        native_invocation.c.tool_id == "approval.respond",
                        native_invocation.c.reply_receipt["type"].as_string()
                        == "local_result",
                        native_invocation.c.reply_receipt["success"]
                        .as_boolean()
                        .is_(True),
                    )
                    .order_by(
                        native_invocation.c.reply_recorded_at, native_invocation.c.id
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            receipt: dict[str, Any]
            if previous is not None:
                if previous["result"]["value"]["decision"] != arguments.decision:
                    return host_rejected("approval_conflict")
                receipt = previous
            else:
                if (
                    origin["request_state"] not in {"pending", "waiting"}
                    or origin["processing_parked_at"] is not None
                    or target["status"] != "awaiting_approval"
                ):
                    return host_rejected("approval_ineligible")
                timestamp = datetime.now(UTC)
                changes: dict[str, object] = {
                    "status": "queued",
                    "decided_at": timestamp,
                }
                if arguments.decision == "deny":
                    changes.update(
                        status="cancelled",
                        completed_at=timestamp,
                        result={
                            "type": "approval_denied_v1",
                            "reason_code": "owner_denied",
                        },
                    )
                await connection.execute(
                    update(action).where(action.c.id == target_id).values(**changes)
                )
                result: ToolResult = {
                    "type": "Success",
                    "value": ApprovalRespondResult(
                        **arguments.model_dump(), decided_at=timestamp
                    ).model_dump(mode="json"),
                }
                completed = completed_tool_result(result)
                if (
                    len(completed.model_text.encode())
                    > APPROVAL_RESPOND_SPEC.limits.max_output_bytes
                ):
                    raise NativeDefect("approval result exceeds its declared bound")
                receipt = {
                    "type": "local_result",
                    "wire_text": completed.model_text,
                    "success": True,
                    "result": result,
                }
            await connection.execute(
                update(native_invocation)
                .where(native_invocation.c.id == identifier)
                .values(
                    action_id=target_id,
                    reply_receipt=receipt,
                    reply_recorded_at=datetime.now(UTC),
                )
            )
            return DispatchCompleted(receipt["result"], receipt["wire_text"], None)

    async def record_delivery(self, delivery: NativeDelivery) -> None:
        evidence = None if delivery.evidence is None else _evidence(delivery.evidence)
        if (delivery.state == "prepared") != (evidence is None):
            raise NativeDefect("native delivery state requires its original evidence")
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                delivery.attempt_id,
                native_attempt.c.native_binding,
                native_attempt.c.request["provider_attempt"].label("provider_attempt"),
                native_attempt.c.request["recovery_origins"].label("recovery_origins"),
                live=delivery.state == "prepared",
            )
            if delivery.mode == "steer" and row["recovery_origins"] is not None:
                raise NativeDefect("restricted opening cannot accept new inputs")
            if evidence is not None and (
                evidence.get("turn") not in (None, row["native_binding"])
                or (
                    "input_id" in evidence
                    and evidence["input_id"] != delivery.delivery_id
                )
                or (
                    "attempt" in evidence
                    and evidence["attempt"] != row["provider_attempt"]
                )
            ):
                raise NativeDefect(
                    "native delivery evidence changed its original identity"
                )
            for input_id in delivery.input_ids:
                old = (
                    (
                        await connection.execute(
                            select(native_input_delivery)
                            .where(
                                native_input_delivery.c.attempt_id
                                == UUID(delivery.attempt_id),
                                native_input_delivery.c.message_id == UUID(input_id),
                            )
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if old is None:
                    if delivery.state != "prepared":
                        raise NativeDefect(
                            "native delivery lacks an original prepared input"
                        )
                    admitted = await connection.scalar(
                        select(message.c.request_state)
                        .where(
                            message.c.id == UUID(input_id),
                            message.c.source_conversation_id == self.owner.scope_id,
                            message.c.role.in_(("owner", "host")),
                            message.c.control_kind.is_(None),
                            message.c.processing_parked_at.is_(None),
                            (
                                message.c.native_retry_after.is_(None)
                                & ~native_recovery_input
                            )
                            if delivery.mode == "steer"
                            else (
                                message.c.native_retry_after.is_(None)
                                | (message.c.native_retry_after <= func.now())
                            ),
                        )
                        .with_for_update()
                    )
                    if admitted not in {"pending", "waiting"}:
                        raise NativeDefect("native delivery is no longer eligible")
                    ordinal = (
                        await connection.scalar(
                            select(func.max(native_input_delivery.c.ordinal)).where(
                                native_input_delivery.c.attempt_id
                                == UUID(delivery.attempt_id)
                            )
                        )
                        or 0
                    ) + 1
                    await connection.execute(
                        insert(native_input_delivery).values(
                            attempt_id=UUID(delivery.attempt_id),
                            message_id=UUID(input_id),
                            ordinal=ordinal,
                            delivery_id=delivery.delivery_id,
                            mode=delivery.mode,
                            was_waking=admitted == "pending",
                            state=delivery.state,
                            provider_evidence=evidence,
                        )
                    )
                else:
                    if (
                        old["delivery_id"] != delivery.delivery_id
                        or old["mode"] != delivery.mode
                    ):
                        raise NativeDefect("native input delivery identity changed")
                    if old["state"] in {"recorded", "rejected"}:
                        if (
                            old["state"] != delivery.state
                            or old["provider_evidence"] != evidence
                        ):
                            raise NativeDefect("final input delivery evidence changed")
                        continue
                    await connection.execute(
                        update(native_input_delivery)
                        .where(
                            native_input_delivery.c.attempt_id == old["attempt_id"],
                            native_input_delivery.c.message_id == old["message_id"],
                        )
                        .values(
                            state=delivery.state,
                            provider_evidence=evidence,
                            updated_at=datetime.now(UTC),
                        )
                    )

    async def record_outcome(
        self,
        attempt_id: str,
        evidence: AgentSubmission | AgentTerminal | AgentControlReceipt,
    ) -> None:
        async with self.database.begin() as connection:
            column = "submission_evidence"
            if isinstance(evidence, AgentControlReceipt):
                column = "local_outcome"
            elif isinstance(evidence, AgentTerminal):
                column = (
                    "terminal"
                    if isinstance(evidence.evidence, NativeTerminalEvidence)
                    else "local_outcome"
                )
            row = await _locked_attempt(
                connection,
                self.owner,
                attempt_id,
                native_attempt.c.request["provider_attempt"].label("provider_attempt"),
                native_attempt.c.native_binding,
                native_attempt.c[column],
                live=False,
            )
            prepared = AgentAttempt(**row["provider_attempt"])
            if isinstance(evidence, AgentControlReceipt):
                local: dict[str, Any] = row["local_outcome"] or {
                    "terminal": None,
                    "control_receipts": {},
                    "fence_reason": None,
                }
                value = _evidence(evidence)
                previous = local["control_receipts"].get(evidence.request_id)
                if previous is not None and previous != value:
                    raise NativeDefect("native control receipt identity changed")
                await connection.execute(
                    update(native_attempt)
                    .where(native_attempt.c.id == row["id"])
                    .values(
                        local_outcome={
                            **local,
                            "control_receipts": {
                                **local["control_receipts"],
                                evidence.request_id: value,
                            },
                        },
                    )
                )
                return
            if isinstance(evidence, AgentTerminal):
                value = terminal_to_json(evidence)
                if isinstance(evidence.evidence, NativeTerminalEvidence):
                    ref = evidence.evidence.native_ref
                    if (
                        evidence.evidence.attempt != prepared
                        or not isinstance(ref, AgentTurnRef)
                        or ref.session_ref.profile_key
                        != self.definition.provider.auth.profile_key
                        or ref.session_ref.backend != self.definition.provider.backend
                        or ref.session_ref.transport
                        != self.definition.provider.transport
                        or (
                            self.antigravity is not None
                            and self.antigravity.turn != ref
                        )
                    ):
                        raise NativeDefect(
                            "native terminal changed the prepared attempt or account"
                        )
                    binding = _turn_binding(ref)
                    if row["native_binding"] not in (None, binding):
                        raise NativeDefect(
                            "native terminal changed the original binding"
                        )
                    changes: dict[str, Any] = {
                        column: value,
                        "terminal_at": datetime.now(UTC),
                        "native_binding": binding,
                    }
                else:
                    local = cast(
                        dict[str, Any],
                        row["local_outcome"]
                        or {
                            "terminal": None,
                            "control_receipts": {},
                            "fence_reason": None,
                        },
                    )
                    if local["terminal"] is not None:
                        if local["terminal"] != value:
                            raise NativeDefect("local terminal evidence changed")
                        return
                    changes = {column: {**local, "terminal": value}}
            else:
                if evidence.attempt != prepared:
                    raise NativeDefect("submission evidence belongs to another attempt")
                value = _evidence(evidence)
                changes = {column: value}
                if isinstance(evidence, AgentNotSubmitted | AgentSubmissionRejected):
                    changes["fenced_at"] = datetime.now(UTC)
            if column != "local_outcome" and row[column] is not None:
                if row[column] != value:
                    raise NativeDefect("native outcome evidence changed")
                return
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(**changes)
            )

    async def record_protocol_fault(
        self,
        attempt_id: str,
        reason: Literal["native_protocol_fault", "NativeSubmissionConflict"],
        seal: AgentTerminal | None,
    ) -> None:
        """Quarantine the fault and preserve its original seal in one commit."""
        if self.neon_lease is not None:
            self.neon_lease.request_disarm()
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                attempt_id,
                native_attempt.c.local_outcome,
                native_attempt.c.terminal,
                native_attempt.c.request["provider_attempt"].label("provider_attempt"),
                live=False,
            )
            local: dict[str, Any] = row["local_outcome"] or {
                "terminal": None,
                "control_receipts": {},
            }
            changes: dict[str, Any] = {
                "fenced_at": func.coalesce(native_attempt.c.fenced_at, func.now()),
                "local_outcome": {
                    **local,
                    "fence_reason": (
                        "NativeSubmissionConflict"
                        if local.get("fence_reason") == "NativeSubmissionConflict"
                        else reason
                    ),
                },
            }
            if seal is not None:
                if not isinstance(seal.evidence, NativeTerminalEvidence) or (
                    seal.evidence.attempt != AgentAttempt(**row["provider_attempt"])
                ):
                    raise NativeDefect("conflicting seal belongs to another attempt")
                value = terminal_to_json(seal)
                if row["terminal"] is not None and row["terminal"] != value:
                    raise NativeDefect("original conflicting seal changed")
                if row["terminal"] is None:
                    changes.update(terminal=value, terminal_at=func.now())
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == UUID(attempt_id))
                .values(**changes)
            )

    async def fence(self, attempt_id: str, reason: str) -> None:
        if self.neon_lease is not None:
            self.neon_lease.request_disarm()
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                attempt_id,
                native_attempt.c.local_outcome,
                live=False,
            )
            local: dict[str, Any] = row["local_outcome"] or {
                "terminal": None,
                "control_receipts": {},
                "fence_reason": None,
            }
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(
                    fenced_at=row["fenced_at"] or datetime.now(UTC),
                    local_outcome={
                        **local,
                        "fence_reason": (
                            "native_protocol_fault"
                            if reason == "native_protocol_fault"
                            and local["fence_reason"] != "NativeSubmissionConflict"
                            else local["fence_reason"] or reason
                        ),
                    },
                )
            )

    async def record(self, attempt_id: str, progress: AgentMessage) -> None:
        identifier = uuid5(UUID(attempt_id), progress.message_id)
        async with self.database.begin() as connection:
            row = await _locked_attempt(connection, self.owner, attempt_id, live=False)
            if (
                row["fenced_at"] is not None
                or row["terminal_at"] is not None
                or row["settled"]
                or row["owner_epoch"] != str(self.owner.token)
            ):
                return
            if progress.phase != "commentary":
                raise NativeDefect("public progress requires native commentary")
            try:
                value = JarvisNativeMessage.model_validate_json(progress.text)
            except ValidationError as exc:
                raise NativeDefect(
                    "public progress violates its message contract"
                ) from exc
            if not isinstance(value.response, Progress):
                raise NativeDefect("native commentary requires a progress response")
            values = {
                "id": identifier,
                "role": "assistant",
                "text": value.response.text,
                "source": "native_progress",
                "memory_admitted": memory_is_admitted(connection),
                "source_conversation_id": row["conversation_id"],
                "source_message_id": None,
                "processed_at": datetime.now(UTC),
                "trace": {
                    "native_attempt_id": attempt_id,
                    "native_item_id": progress.message_id,
                    "native_message_sha256": sha256(
                        progress.text.encode("utf-8")
                    ).hexdigest(),
                },
            }
            existing = (
                (
                    await connection.execute(
                        select(message).where(message.c.id == identifier)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is None:
                home = await _delivery_home(
                    connection,
                    self.owner.scope_id,
                    row["id"],
                    value.response.present,
                    value.response.artifact_links,
                    drive_subject=(
                        None
                        if self.workspace_grant is None
                        else self.workspace_grant.subject
                    ),
                )
                await connection.execute(insert(message).values(**values, home=home))
            elif (
                existing["text"] != value.response.text
                or existing["trace"] != values["trace"]
            ):
                raise NativeDefect("public progress identity changed")


async def _locked_attempt(
    connection: AsyncConnection,
    owner: JarvisOwner,
    attempt_id: str,
    *evidence_columns: ColumnElement[Any],
    live: bool = True,
) -> RowMapping:
    await lock_conversation(connection, owner.scope_id)
    row = (
        (
            await connection.execute(
                select(
                    native_attempt.c.id,
                    native_attempt.c.conversation_id,
                    native_attempt.c.owner_epoch,
                    native_attempt.c.fenced_at,
                    native_attempt.c.terminal_at,
                    native_attempt.c.product_outcome.is_not(None).label("settled"),
                    *evidence_columns,
                )
                .where(native_attempt.c.id == UUID(attempt_id))
                .with_for_update()
            )
        )
        .mappings()
        .one()
    )
    if row["conversation_id"] != owner.scope_id:
        raise NativeDefect("native attempt is outside this conversation")
    paused = (
        None
        if not live
        else await connection.scalar(
            select(message.c.control_kind)
            .where(
                message.c.source_conversation_id == owner.scope_id,
                message.c.control_kind.is_not(None),
            )
            .order_by(message.c.control_sequence.desc())
            .limit(1)
        )
    )
    if live and (
        paused == "pause"
        or row["fenced_at"] is not None
        or row["terminal_at"] is not None
        or row["settled"]
        or row["owner_epoch"] != str(owner.token)
    ):
        raise NativeDefect("native attempt authority is stale")
    return row


def _request_ancestors(scope: str, attempt_id: UUID, stopping: tuple[UUID, ...]) -> CTE:
    """Keep each proven delivery attached to its unstopped, owner-scoped path."""
    eligible = (
        (message.c.source_conversation_id == scope)
        & message.c.request_state.in_(("pending", "waiting", "completed"))
        & message.c.control_kind.is_(None)
    )
    if stopping:
        eligible &= message.c.id.not_in(stopping)
    ancestors = (
        select(
            message.c.id,
            message.c.parent_request_id,
            native_input_delivery.c.message_id.label("input_id"),
        )
        .join(native_input_delivery, native_input_delivery.c.message_id == message.c.id)
        .where(
            eligible,
            native_input_delivery.c.attempt_id == attempt_id,
            proven_native_delivery,
        )
        .cte("ancestors", recursive=True)
    )
    return ancestors.union(
        select(message.c.id, message.c.parent_request_id, ancestors.c.input_id)
        .join(ancestors, message.c.id == ancestors.c.parent_request_id)
        .where(eligible)
    )


async def _delivery_home(
    connection: AsyncConnection,
    scope: str,
    attempt_id: UUID,
    present: Presentation | None,
    artifact_links: list[ViewRef],
    stopping: tuple[UUID, ...] = (),
    *,
    drive_subject: str | None = None,
) -> dict[str, object]:
    refs = artifact_links
    if present is not None and isinstance(present.ref, ViewRef):
        refs = [*refs, present.ref]
    admitted: list[ViewRef] = []
    if refs:
        catalog = await to_thread(HomePages(DEFAULT_EXPORT).snapshot)
        for ref in dict.fromkeys(refs):
            if catalog.view(ref.slug, ref.rev) is None:
                LOGGER.warning(
                    "native artifact link omitted: attempt=%s slug=%s rev=%s "
                    "reason=unpublished",
                    attempt_id,
                    ref.slug,
                    ref.rev,
                )
            else:
                admitted.append(ref)
    home: dict[str, object] = {
        "artifact_links": [ref.model_dump(mode="json") for ref in admitted]
    }
    if present is None:
        return home
    ancestors = _request_ancestors(scope, attempt_id, stopping)
    request = await connection.scalar(
        select(message.c.id)
        .join(ancestors, ancestors.c.id == message.c.id)
        .where(
            message.c.id == UUID(present.request_id),
            message.c.role == "owner",
            message.c.source == "web",
        )
    )
    if request is None:
        reason = "unproven_lineage"
    elif (
        present.ref in admitted
        if isinstance(present.ref, ViewRef)
        else await reference_context(
            connection,
            scope,
            present.ref.model_dump(mode="json"),
            DEFAULT_EXPORT,
            drive_subject=drive_subject,
        )
        is not None
    ):
        home["present"] = present.model_dump(mode="json")
        return home
    else:
        reason = "unavailable_target"
    LOGGER.warning(
        "native presentation omitted: attempt=%s reason=%s", attempt_id, reason
    )
    return home


async def _todo_result_home(
    connection: AsyncConnection,
    scope: str,
    attempt_id: UUID,
    response: Answered | Partial,
    named: tuple[UUID, ...],
    stopping: tuple[UUID, ...],
    *,
    drive_subject: str | None,
) -> dict[str, object] | None:
    target = response.todo_result
    if target is None or not named:
        return None
    request_id = UUID(target.request_id)
    todo_id = UUID(target.todo_id)
    ancestors = _request_ancestors(scope, attempt_id, stopping)
    matching = (
        select(func.count())
        .select_from(ancestors)
        .where(ancestors.c.id == request_id, ancestors.c.input_id.in_(named))
        .scalar_subquery()
    )
    origin = (
        (
            await connection.execute(
                select(
                    message.c.role, message.c.source, message.c.text, message.c.home
                ).where(
                    message.c.id == request_id,
                    matching == len(named),
                    select(work.c.id).where(work.c.id == todo_id).exists(),
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if origin is None:
        return None
    typed_ref = origin["role"] == "owner" and cast(
        dict[str, object], origin["home"] or {}
    ).get("ref") == {"kind": "todo", "id": target.todo_id}
    from_wake = False
    if origin["role"] == "host" and origin["source"] == "work_wake":
        try:
            from_wake = json.loads(origin["text"])["record"]["id"] == target.todo_id
        except (ValueError, KeyError, TypeError):
            pass
    if not (typed_ref or from_wake):
        created = await connection.scalar(
            select(action.c.id).where(
                action.c.id == todo_id,
                action.c.origin_message_id == request_id,
                action.c.tool_name == str(WORK_CREATE_SPEC.id),
                action.c.status == "succeeded",
                action.c.result.contains(
                    {
                        "type": "Success",
                        "value": {"id": target.todo_id, "operation": "created"},
                    }
                ),
            )
        )
        if created is None:
            return None

    related: dict[str, object] = {"draft_ref": None}
    if target.file_ref is not None and target.file_ref.subject == drive_subject:
        related["file_ref"] = target.file_ref.model_dump(mode="json")
    if target.draft_ref is not None:
        try:
            saved = await draft_for_request(
                connection, request_id, UUID(target.draft_ref)
            )
        except ActionPersistenceDefect:
            LOGGER.error(
                "saved draft receipt failed integrity checks: attempt=%s", attempt_id
            )
            related["draft_error"] = "integrity"
        else:
            if saved is not None:
                related["draft_ref"] = target.draft_ref
    label = next(
        (line.strip()[:120] for line in response.text.splitlines() if line.strip()), ""
    )
    return {
        "todo_id": target.todo_id,
        "request_id": target.request_id,
        "label": label,
        **related,
    }


async def _draft_result_home(
    connection: AsyncConnection,
    scope: str,
    attempt_id: UUID,
    named: tuple[UUID, ...],
    stopping: tuple[UUID, ...],
    explicit: Presentation | None,
) -> dict[str, object] | None:
    if not named:
        return None
    ancestors = _request_ancestors(scope, attempt_id, stopping)
    rows = (
        await connection.execute(
            select(
                action.c.id,
                native_invocation.c.request_message_id,
                message.c.role,
                message.c.source,
            )
            .join(native_invocation, native_invocation.c.action_id == action.c.id)
            .join(message, message.c.id == native_invocation.c.request_message_id)
            .where(
                native_invocation.c.attempt_id == attempt_id,
                native_invocation.c.validation == "accepted",
                native_invocation.c.tool_id == "gmail.create_draft",
                action.c.origin_message_id == message.c.id,
                action.c.execution_contract["claim_id"].as_string() == str(attempt_id),
                action.c.tool_name == "gmail.create_draft",
                action.c.status == "succeeded",
                action.c.execution_contract["implementation_revision"].as_string()
                == WORKSPACE_MAIL_IMPLEMENTATION,
                native_invocation.c.ordinal
                == action.c.execution_contract["model_step_ordinal"].as_integer(),
                select(ancestors.c.id)
                .where(ancestors.c.id == message.c.id, ancestors.c.input_id.in_(named))
                .exists(),
            )
            .order_by(action.c.created_at, action.c.id)
        )
    ).all()
    drafts: list[dict[str, str]] = []
    web_request = False
    seen: set[UUID] = set()
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        try:
            evidence = await draft_for_request(
                connection, row.request_message_id, row.id
            )
        except ActionPersistenceDefect:
            LOGGER.error("draft presentation lacks exact evidence: action=%s", row.id)
            continue
        if not isinstance(evidence, VerifiedWorkspaceDraft):
            continue
        drafts.append(
            {
                "request_id": str(row.request_message_id),
                "create_action_id": str(row.id),
                "subject": evidence.compose.content.subject,
            }
        )
        web_request = (
            row.role == "owner"
            and row.source == "web"
            and evidence.compose.editor is not None
        )
    if not drafts:
        return None
    result: dict[str, object] = {"drafts": drafts}
    if explicit is None and len(drafts) == 1 and web_request:
        draft = drafts[0]
        ref = DraftPresentationRef(
            request_id=draft["request_id"], create_action_id=draft["create_action_id"]
        )
        result["present"] = {
            "request_id": ref.request_id,
            "ref": ref.model_dump(mode="json"),
        }
    return result


async def yield_workspace_input(
    owner: JarvisOwner, request: NativeRequest, owner_input: UUID
) -> bool:
    """Close the scoped input and leave the owner's new request pending."""
    if len(request.input_ids) != 1:
        raise NativeDefect("a scoped native session requires a single opening input")
    origin_id = UUID(request.input_ids[0])
    async with owner.database.begin() as connection:
        attempt = await _locked_attempt(
            connection, owner, request.attempt_id, live=False
        )
        if (
            attempt["fenced_at"]
            or attempt["settled"]
            or attempt["terminal_at"]
            or attempt["owner_epoch"] != str(owner.token)
        ):
            return False
        pending = await connection.scalar(
            select(message.c.id).where(
                message.c.id == owner_input,
                message.c.source_conversation_id == owner.scope_id,
                message.c.role == "owner",
                message.c.control_kind.is_(None),
                message.c.request_state == "pending",
                message.c.processing_parked_at.is_(None),
            )
        )
        origin = (
            (
                await connection.execute(
                    select(message)
                    .where(
                        message.c.id == origin_id,
                        message.c.source_conversation_id == owner.scope_id,
                        message.c.request_state.in_(("pending", "waiting")),
                        message.c.processing_parked_at.is_(None),
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if pending is None or origin is None or owner_input == origin_id:
            return False
        home = cast(dict[str, Any], origin["home"] or {})
        refresh = home.get("workspace_refresh")
        if refresh is not None:
            todo = refresh["todo_id"]
        elif is_workspace_wake(origin["source"], origin["text"]):
            todo = json.loads(origin["text"])["record"]["id"]
        else:
            raise NativeDefect("only a workspace input can yield its scoped session")
        timestamp = datetime.now(UTC)
        identifier = uuid5(UUID(request.attempt_id), "product-conclusion")
        content = "check inconclusive. a new owner request interrupted the check."
        link: dict[str, object] = {
            "todo_result": {
                "todo_id": todo,
                "request_id": str(origin_id),
                "label": content,
                "draft_ref": None,
            }
        }
        if refresh is None:
            link["workspace_result"] = {
                "occurrence_id": str(origin_id),
                "outcome": "inconclusive",
                "evidence": [],
            }
        await connection.execute(
            insert(message).values(
                id=identifier,
                role="assistant",
                source="native_final",
                text=content,
                home=link,
                source_conversation_id=owner.scope_id,
                memory_admitted=memory_is_admitted(connection),
                processed_at=timestamp,
                trace={
                    "native_attempt_id": request.attempt_id,
                    "workspace_interrupted_by": str(owner_input),
                },
            )
        )
        await connection.execute(
            update(message)
            .where(message.c.id == origin_id)
            .values(
                request_state="completed",
                processed_at=timestamp,
                wait_reason=None,
                native_retry_after=None,
                trace={
                    **origin["trace"],
                    "native_attempt_id": request.attempt_id,
                    "settlement": {
                        "run_id": request.attempt_id,
                        "through_checkpoint": str(origin_id),
                        "conclusion_message_id": str(identifier),
                        "conclusion_kind": "conversation",
                        "outcome": "partial",
                    },
                },
            )
        )
        if refresh is not None:
            await enqueue_notice(connection, identifier)
    return True


async def commit_product(
    database: Database,
    owner: JarvisOwner,
    turn: _SealedNativeTurn,
    final: JarvisTerminal,
    rendered: RenderedTerminal,
    *,
    recovering: bool = False,
    workspace: WorkspaceHost | None = None,
) -> ProductSettlement:
    await owner.require_current(owner.permit("jarvis-product:" + turn.attempt_id))
    conclusion_id = uuid5(UUID(turn.attempt_id), "product-conclusion")
    completed: list[UUID] = []
    async with database.begin() as connection:
        attempt, inputs = await _product_inputs(connection, owner, turn.attempt_id)
        if attempt is None or attempt["terminal_at"] is None:
            raise NativeDefect("product settlement lacks a native terminal")
        if attempt["settled"]:
            return ProductSettlement()
        delivered_count = await connection.scalar(
            select(func.count())
            .select_from(native_input_delivery)
            .where(
                native_input_delivery.c.attempt_id == attempt["id"],
                proven_native_delivery,
            )
        )
        if not inputs or len(inputs) != delivered_count:
            raise StaleNativeProduct(
                "original input lifecycle invalidates this terminal"
            )
        if not recovering and (
            attempt["fenced_at"] is not None
            or attempt["owner_epoch"] != str(owner.token)
        ):
            # Fencing ends live authority. Recovery can still settle this seal.
            return ProductSettlement()
        statuses = {UUID(item.input_id): item for item in final.input_outcomes}
        if not set(statuses).issubset(inputs):
            raise NativeContentDefect(
                "final dispositions name input without live delivered authority"
            )
        recovery_origins = attempt["recovery_origins"]
        restricted = recovery_origins is not None
        grant = workspace.enrollment() if workspace is not None else None
        catchup_result = None
        timestamp = datetime.now(UTC)
        if restricted:
            if (
                recovery_origins
                != {
                    str(identifier): native_retry_evidence(row["trace"]).get(
                        "origin_attempt_id"
                    )
                    for identifier, row in inputs.items()
                }
                or attempt["recovery_retries"]
                != {
                    str(identifier): native_retry_evidence(row["trace"]).get(
                        "attempt_id"
                    )
                    for identifier, row in inputs.items()
                }
                or await connection.scalar(latest_control(owner.scope_id)) == "pause"
            ):
                raise StaleNativeProduct(
                    "restricted result lost its original authority"
                )
            if attempt["recovery_grant"] != _recovery_grant(grant):
                return await _hold_restricted_result(
                    connection,
                    owner,
                    attempt,
                    inputs,
                    timestamp,
                    "workspace_recovery_grant_changed",
                )
            if (
                set(statuses) != set(inputs)
                or final.workspace_result is not None
                or any(status.disposition == "stop" for status in statuses.values())
                or (
                    rendered.content is None
                    and any(row["role"] == "owner" for row in inputs.values())
                )
            ):
                raise NativeContentDefect(
                    "restricted result requires dispositions without stop authority"
                )
            if rendered.outcome == "answered" and any(
                status.disposition != "complete" for status in statuses.values()
            ):
                rendered = replace(rendered, outcome="partial")
            if len(inputs) == 1:
                identifier, origin = next(iter(inputs.items()))
                if origin["role"] == "host" and origin["source"] == CATCHUP_SOURCE:
                    if (
                        grant is None
                        or statuses[identifier].disposition
                        not in {"continue", "complete"}
                        or not isinstance(final.response, Answered | Partial)
                    ):
                        raise NativeContentDefect(
                            "mail catch-up requires a visible report and live grant"
                        )
                    from jarvis.recovery_catchup import CatchupStale, settle_catchup

                    try:
                        coverage = await settle_catchup(
                            connection,
                            owner.scope_id,
                            identifier,
                            attempt["id"],
                            attempt["control_sequence"],
                            account=grant.account,
                            grant_id=grant.grant_id,
                            conclusion_id=conclusion_id,
                            timestamp=timestamp,
                            allow_retry=not native_fault_retry_used(origin),
                        )
                    except CatchupStale:
                        return await _hold_restricted_result(
                            connection,
                            owner,
                            attempt,
                            inputs,
                            timestamp,
                            "mail_catchup_inventory_changed",
                        )
                    if (
                        statuses[identifier].disposition != "complete"
                        and not coverage.quota_wait
                    ):
                        raise NativeContentDefect(
                            "an unfinished mail catch-up requires a proven quota wait"
                        )
                    if coverage.retry_after is not None:
                        await queue_native_retry(
                            connection,
                            origin,
                            attempt_id=turn.attempt_id,
                            route=attempt["route"],
                            selection="pinned",
                            reason="mail_catchup_retry",
                            read_only=True,
                            fault_retry_used=native_fault_retry_used(origin)
                            or not coverage.quota_wait,
                            retry_at=coverage.retry_after,
                        )
                        await connection.execute(
                            update(native_attempt)
                            .where(native_attempt.c.id == attempt["id"])
                            .values(
                                recovery_pending=False,
                                fenced_at=attempt["fenced_at"] or timestamp,
                                product_outcome={
                                    "status": "committed",
                                    "response_id": None,
                                    "input_outcomes": [],
                                },
                            )
                        )
                        return ProductSettlement("committed")
                    catchup_result = {
                        "observed": coverage.observed,
                        "unavailable": coverage.unavailable,
                        "pending": coverage.pending,
                    }
                    rendered = RenderedTerminal(
                        "partial" if coverage.pending else rendered.outcome,
                        "conversation",
                        f"mail catch-up covered {coverage.observed} messages. "
                        f"{coverage.unavailable} unavailable, "
                        f"{coverage.pending} outstanding."
                        f"\n\n{rendered.content}",
                    )
        stopping = tuple(
            key for key, item in statuses.items() if item.disposition == "stop"
        )
        enrollment = None if workspace is None else workspace.enrollment()
        drive_subject = None if enrollment is None else enrollment.subject
        home: dict[str, object] = {}
        if rendered.content is not None and not isinstance(final.response, Silent):
            home = await _delivery_home(
                connection,
                owner.scope_id,
                attempt["id"],
                final.response.present,
                final.response.artifact_links,
                stopping,
                drive_subject=drive_subject,
            )
        if catchup_result is not None:
            home["recovery_catchup"] = catchup_result
        occurrence = None
        if len(inputs) == 1:
            origin = next(iter(inputs.values()))
            if origin["role"] == "host" and origin["source"] == "work_wake":
                occurrence = WorkspaceOccurrence.from_wake(
                    origin["id"],
                    origin["wake_text"],
                    workspace.owner_zone if workspace else ZoneInfo("UTC"),
                    attempt["armed_at"],
                )
        workspace_match = None
        checked = None
        if occurrence is not None:
            current = workspace is not None and await workspace.occurrence_current(
                connection, occurrence, attempt["control_sequence"]
            )
            reads = (
                await check_observations(connection, attempt["id"], occurrence)
                if current
                else []
            )
            proposed = final.workspace_result
            disposition = statuses.get(occurrence.occurrence_id)
            outcome = occurrence.settle(proposed, reads)
            if (
                not current
                or disposition is None
                or disposition.disposition != "complete"
                or rendered.outcome not in {"answered", "partial"}
            ):
                outcome = "inconclusive"
            accepted = {str(read.invocation_id) for read in reads}
            checked = WorkspaceResult(
                occurrence_id=str(occurrence.occurrence_id),
                outcome=outcome,
                evidence=[ref for ref in proposed.evidence if ref in accepted]
                if proposed
                else [],
            ).model_dump(mode="json")
            if (
                not current
                or proposed is None
                or proposed.outcome != outcome
                or rendered.content is None
                or proposed.occurrence_id != str(occurrence.occurrence_id)
            ):
                if occurrence.check.expired(timestamp, occurrence.owner_zone):
                    reason = "the standing check expired."
                elif not current:
                    reason = "the original check is no longer authorized."
                else:
                    reason = (
                        "the recorded reads did not establish the result. "
                        "open this todo in chat to check again."
                    )
                local_time = timestamp.astimezone(occurrence.owner_zone)
                rendered = RenderedTerminal(
                    "partial",
                    "conversation",
                    f"check inconclusive at {local_time:%Y-%m-%d %H:%M %Z}. {reason}",
                )
            if not recovering and outcome == "match":
                workspace_match = occurrence
            home = {
                **home,
                "workspace_result": checked,
                "todo_result": {
                    "todo_id": str(occurrence.work_id),
                    "request_id": str(occurrence.occurrence_id),
                    "label": (rendered.content or "check inconclusive").splitlines()[0][
                        :120
                    ],
                    "draft_ref": None,
                },
            }
        elif isinstance(final.response, Answered | Partial):
            link = await _todo_result_home(
                connection,
                owner.scope_id,
                attempt["id"],
                final.response,
                tuple(statuses),
                stopping,
                drive_subject=drive_subject,
            )
            if link is not None:
                home["todo_result"] = link
        if rendered.content is not None and not restricted:
            drafts = await _draft_result_home(
                connection,
                owner.scope_id,
                attempt["id"],
                tuple(statuses),
                stopping,
                None if isinstance(final.response, Silent) else final.response.present,
            )
            if drafts is not None:
                home.update(drafts)
        if stopping:
            await cancel_unentered_actions(connection, stopping, timestamp)
        owned: set[UUID] = set()
        approval_refs: set[UUID] = set()
        settled_outcomes: list[dict[str, object]] = []
        for identifier, disposition in statuses.items():
            target = inputs[identifier]
            component = await causal_component_ids(connection, (identifier,))
            actions = (
                (
                    await connection.execute(
                        select(action)
                        .where(action.c.origin_message_id.in_(component))
                        .order_by(action.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            own_blockers = [
                item
                for item in actions
                if item["origin_message_id"] == identifier
                and item["status"]
                in {"queued", "awaiting_approval", "executing", "uncertain"}
                and not (
                    item["tool_name"] == "agent.delegate"
                    and item["status"] == "queued"
                    and item["result"] is not None
                    and "registration_receipt" in item["result"]
                )
            ]
            owned.update(
                item["id"]
                for item in own_blockers
                if item["status"] == "awaiting_approval"
            )
            if disposition.disposition == "complete" and own_blockers:
                raise NativeContentDefect(
                    "request completion would hide unresolved actions"
                )
            state = {
                "complete": "completed",
                "continue": "pending",
                "waiting": "waiting",
                "stop": "stopped",
            }[disposition.disposition]
            refs: set[UUID] = set(map(UUID, disposition.action_refs))
            wait_reason = disposition.wait_reason
            if restricted and state == "pending":
                state = "waiting"
                wait_reason = "configuration"
            if wait_reason in {"approval", "external_reconciliation"}:
                by_id = {item["id"]: item for item in actions}
                if not refs or not refs.issubset(by_id):
                    raise NativeContentDefect(
                        "waiting disposition named a foreign action"
                    )
                expected = (
                    {"awaiting_approval"}
                    if disposition.wait_reason == "approval"
                    else {"queued", "executing", "uncertain"}
                )
                for ref in refs:
                    blocker = by_id[ref]
                    if blocker["status"] == "uncertain":
                        unresolved_notice = await connection.scalar(
                            select(message.c.id).where(
                                message.c.source == "action",
                                message.c.source_message_id == f"{ref}:uncertain",
                                message.c.trace["action_id"].as_string() == str(ref),
                                message.c.id.not_in(
                                    select(native_input_delivery.c.message_id).where(
                                        native_input_delivery.c.attempt_id
                                        == attempt["id"],
                                        proven_native_delivery,
                                    )
                                ),
                            )
                        )
                        if unresolved_notice is not None and not restricted:
                            state = "pending"
                    if blocker["status"] not in expected:
                        if blocker["status"] not in {
                            "succeeded",
                            "failed",
                            "cancelled",
                        } and not (
                            disposition.wait_reason == "approval"
                            and blocker["decided_at"] is not None
                        ):
                            raise NativeContentDefect(
                                "waiting disposition fabricated its action blocker"
                            )
                        state = "waiting" if restricted else "pending"
                        if restricted:
                            wait_reason = "configuration"
                            refs = set()
                            break
            if state == "waiting" and wait_reason == "approval":
                approval_refs.update(refs)
            trace = {**target["trace"], "native_attempt_id": turn.attempt_id}
            if not restricted or state == "completed":
                trace.pop("native_context_retry", None)
                trace.pop("native_retry", None)
            trace.pop("waiting_action_ids", None)
            if state == "waiting" and refs:
                trace["waiting_action_ids"] = sorted(map(str, refs))
            if state in {"completed", "stopped"}:
                trace["settlement"] = {
                    "run_id": turn.attempt_id,
                    "through_checkpoint": str(identifier),
                    "conclusion_message_id": str(conclusion_id)
                    if rendered.content is not None
                    else None,
                    "conclusion_kind": rendered.conclusion_kind,
                    "outcome": rendered.outcome,
                }
            if len(canonical_json_bytes(trace)) > MAX_TRACE_BYTES:
                raise NativeContentDefect("request settlement trace exceeds its bound")
            await connection.execute(
                update(message)
                .where(message.c.id == identifier)
                .values(
                    request_state=state,
                    native_retry_after=(
                        target["native_retry_after"]
                        if restricted and state == "waiting"
                        else None
                    ),
                    wait_reason=wait_reason if state == "waiting" else None,
                    processed_at=timestamp
                    if state in {"completed", "stopped"}
                    else None,
                    trace=trace,
                )
            )
            if state in {"completed", "stopped"}:
                completed.append(identifier)
            settled_outcomes.append(
                {
                    "input_id": str(identifier),
                    "disposition": {
                        "completed": "complete",
                        "stopped": "stop",
                        "pending": "continue",
                        "waiting": "waiting",
                    }[state],
                    "wait_reason": wait_reason if state == "waiting" else None,
                    "action_refs": sorted(map(str, refs)) if state == "waiting" else [],
                }
                if restricted
                else disposition.model_dump(mode="json")
            )
        # A write can commit before its callback reply, or before its origin
        # receives any disposition. The original invocation still owns its action.
        created = select(native_invocation.c.action_id).where(
            native_invocation.c.attempt_id == attempt["id"],
            native_invocation.c.request_message_id.is_not(None),
            native_invocation.c.proposal["arguments"]["existing_action_ref"]
            .as_string()
            .is_(None),
        )
        unseen = tuple(
            await connection.scalars(
                select(action.c.id)
                .where(
                    action.c.status == "awaiting_approval",
                    or_(
                        action.c.id.in_(created), action.c.id.in_(owned | approval_refs)
                    ),
                    ~proposal_presented(owner.scope_id),
                )
                .order_by(action.c.created_at, action.c.id)
            )
        )
        if unseen:
            if not final.has_question or not approval_refs.issuperset(unseen):
                raise NativeContentDefect(
                    "unseen proposals require an approval wait and question"
                )
            home["proposal_ids"] = list(map(str, unseen))
        if rendered.content is not None:
            await connection.execute(
                insert(message).values(
                    id=conclusion_id,
                    role="assistant",
                    text=rendered.content,
                    source="native_final",
                    home=home,
                    memory_admitted=memory_is_admitted(connection),
                    source_conversation_id=owner.scope_id,
                    processed_at=timestamp,
                    trace={"native_attempt_id": turn.attempt_id},
                )
            )
            if occurrence is None:
                await enqueue_notice(
                    connection,
                    conclusion_id,
                    kind="question"
                    if rendered.outcome == "needs_input"
                    or (final.has_question and (final.waits_for_owner or approval_refs))
                    else "reply",
                )
        await connection.execute(
            update(native_attempt)
            .where(native_attempt.c.id == attempt["id"])
            .values(
                recovery_pending=False,
                product_outcome={
                    "status": "committed",
                    **({"workspace_result": checked} if checked is not None else {}),
                    "response_id": str(conclusion_id)
                    if rendered.content is not None
                    else None,
                    "input_outcomes": settled_outcomes,
                },
            )
        )
    return ProductSettlement(
        "committed", tuple(completed), workspace_match=workspace_match
    )


async def _product_inputs(
    connection: AsyncConnection,
    owner: JarvisOwner,
    attempt_id: str,
    *,
    delivery: ColumnElement[bool] = proven_native_delivery,
    fallback_input_ids: tuple[InputId, ...] = (),
) -> tuple[RowMapping | None, dict[UUID, RowMapping]]:
    await lock_conversation(connection, owner.scope_id)
    delivered = tuple(
        (
            await connection.execute(
                select(native_input_delivery.c.message_id).where(
                    native_input_delivery.c.attempt_id == UUID(attempt_id),
                    delivery,
                )
            )
        ).scalars()
    )
    rows = (
        (
            await connection.execute(
                select(
                    message.c.id,
                    message.c.source_conversation_id,
                    message.c.role,
                    message.c.source,
                    message.c.home,
                    case((message.c.source == "work_wake", message.c.text)).label(
                        "wake_text"
                    ),
                    message.c.request_state,
                    message.c.processing_parked_at,
                    message.c.native_retry_after,
                    message.c.trace,
                )
                .where(
                    message.c.id.in_(delivered or tuple(map(UUID, fallback_input_ids)))
                )
                .order_by(message.c.id)
                .with_for_update()
            )
        )
        .mappings()
        .all()
    )
    attempt = (
        (
            await connection.execute(
                select(
                    native_attempt.c.id,
                    native_attempt.c.conversation_id,
                    native_attempt.c.attempt_seq,
                    native_attempt.c.armed_at,
                    native_attempt.c.terminal_at,
                    native_attempt.c.fenced_at,
                    native_attempt.c.recovery_pending,
                    native_attempt.c.owner_epoch,
                    native_attempt.c.product_outcome.is_not(None).label("settled"),
                    _ACTIVE_ROUTE.label("route"),
                    native_attempt.c.request["recovery_origins"].label(
                        "recovery_origins"
                    ),
                    native_attempt.c.request["recovery_retries"].label(
                        "recovery_retries"
                    ),
                    native_attempt.c.request["recovery_grant"].label("recovery_grant"),
                    native_attempt.c.request["control_sequence"]
                    .as_integer()
                    .label("control_sequence"),
                )
                .where(native_attempt.c.id == UUID(attempt_id))
                .with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    if attempt is not None and attempt["conversation_id"] != owner.scope_id:
        raise NativeDefect("product settlement is outside this conversation")
    inputs: dict[UUID, RowMapping] = {}
    for row in rows:
        if (
            row["source_conversation_id"] != owner.scope_id
            or row["role"] not in {"owner", "host"}
            or row["processing_parked_at"] is not None
            or row["request_state"] not in {"pending", "waiting"}
            or (
                attempt is not None
                and attempt["attempt_seq"]
                <= row["trace"].get("released_through_native_attempt", 0)
            )
        ):
            continue
        controlled = (
            None
            if attempt is None
            else await connection.scalar(
                select(message.c.id)
                .where(
                    message.c.source_conversation_id == owner.scope_id,
                    message.c.control_sequence > attempt["control_sequence"],
                    message.c.control_targets.contains([row["id"]]),
                )
                .limit(1)
            )
        )
        previous_id = row["trace"].get("native_attempt_id")
        superseded = False
        if (
            attempt is not None
            and previous_id is not None
            and previous_id != attempt_id
        ):
            previous_sequence = await connection.scalar(
                select(native_attempt.c.attempt_seq).where(
                    native_attempt.c.id == UUID(previous_id)
                )
            )
            superseded = (
                previous_sequence is not None
                and previous_sequence > attempt["attempt_seq"]
            )
        if attempt is not None and controlled is None and not superseded:
            # Prepared may have reached the wire, even before confirmed delivery.
            superseded = bool(
                await connection.scalar(
                    select(native_input_delivery.c.attempt_id)
                    .join(
                        native_attempt,
                        native_attempt.c.id == native_input_delivery.c.attempt_id,
                    )
                    .where(
                        native_input_delivery.c.message_id == row["id"],
                        native_input_delivery.c.state != "rejected",
                        native_attempt.c.conversation_id == owner.scope_id,
                        native_attempt.c.attempt_seq > attempt["attempt_seq"],
                    )
                    .limit(1)
                )
            )
        if controlled is None and not superseded:
            inputs[row["id"]] = row
    return attempt, inputs


async def _fail_inputs(
    connection: AsyncConnection,
    owner: JarvisOwner,
    inputs: dict[UUID, RowMapping],
    reason: str,
    *,
    attempt_id: str | None,
    route: str | None = None,
    continuation: Literal["capacity", "full", "read_only"] | None = None,
) -> None:
    """Reserve one new execution, or wait for capacity without taking it."""
    parked: dict[UUID, RowMapping] = {}
    retry_at = (
        (await connection.execute(select(func.now()))).scalar_one()
        + timedelta(seconds=0 if reason == "agy_before_activity" else 30)
        if continuation is not None
        else None
    )
    for identifier, row in inputs.items():
        previous = native_retry_evidence(row["trace"])
        fault_used = continuation is not None and native_fault_retry_used(row)
        if (
            continuation is None
            or attempt_id is None
            or route not in NATIVE_ROUTES
            or retry_at is None
            or (continuation != "capacity" and fault_used)
            or (
                continuation == "read_only"
                and row["source"] not in {"email_event", CATCHUP_SOURCE}
                and (
                    row["role"] != "owner"
                    or (
                        row["home"] is not None
                        and row["home"].get("workspace_refresh") is not None
                    )
                )
            )
        ):
            parked[identifier] = row
            continue
        read_only = (
            continuation == "read_only"
            or previous.get("kind") == "read_only"
            or row["source"] == CATCHUP_SOURCE
        )
        await queue_native_retry(
            connection,
            row,
            attempt_id=attempt_id,
            route=route,
            selection=(
                "pinned"
                if continuation == "read_only" or previous.get("selection") == "pinned"
                else "fresh"
            ),
            reason=reason,
            read_only=read_only,
            fault_retry_used=fault_used or continuation != "capacity",
            retry_at=retry_at,
        )
    if not parked:
        return
    timestamp = datetime.now(UTC)
    for identifier, row in parked.items():
        if reason == "context_window_exceeded":
            failure = "the model reached its context limit while retrying"
        else:
            failure = reason
        trace = {**row["trace"], "failure_code": failure}
        if attempt_id is not None:
            trace["native_attempt_id"] = attempt_id
        trace.pop("waiting_action_ids", None)
        await connection.execute(
            update(message)
            .where(message.c.id == identifier)
            .values(
                request_state="waiting",
                wait_reason="configuration",
                processed_at=None,
                processing_parked_at=timestamp,
                trace=trace,
            )
        )
    await record_parking_notice(
        connection,
        scope=owner.scope_id,
        origins=tuple(parked),
        reason=reason,
        timestamp=timestamp,
        attempt_id=attempt_id,
    )


async def settle_undispatched_antigravity(
    owner: JarvisOwner, request: NativeRequest
) -> bool:
    """Consume the retry for a joined host and zero upstream entries."""
    identifier = UUID(request.attempt_id)
    await owner.require_current(owner.permit("jarvis-product:" + request.attempt_id))
    async with owner.database.begin() as connection:
        row = await _locked_attempt(
            connection,
            owner,
            request.attempt_id,
            _ACTIVE_ROUTE.label("route"),
            native_attempt.c.recovery_pending,
            native_attempt.c.local_outcome,
            native_attempt.c.submission_evidence["type"]
            .as_string()
            .label("submission"),
            live=False,
        )
        local: dict[str, Any] = row["local_outcome"] or {}
        if (
            row["route"] != "agy_neon"
            or row["owner_epoch"] != str(owner.token)
            or row["settled"]
            or not row["recovery_pending"]
            or row["fenced_at"] is None
            or row["terminal_at"] is not None
            or row["submission"] != "AgentNotSubmitted"
            or local.get("neon_may_have_delivered") is not None
            or local.get("neon_children")
            or local.get("control_receipts")
            or await connection.scalar(
                select(native_invocation.c.id)
                .where(native_invocation.c.attempt_id == identifier)
                .limit(1)
            )
            or await connection.scalar(
                select(native_input_delivery.c.attempt_id)
                .where(
                    native_input_delivery.c.attempt_id == identifier,
                    or_(
                        native_input_delivery.c.mode == "steer", proven_native_delivery
                    ),
                )
                .limit(1)
            )
        ):
            return False
        _, inputs = await _product_inputs(
            connection, owner, request.attempt_id, fallback_input_ids=request.input_ids
        )
        if set(inputs) != set(map(UUID, request.input_ids)) or not all(
            not native_fault_retry_used(value) for value in inputs.values()
        ):
            return False
        await _fail_inputs(
            connection,
            owner,
            inputs,
            "agy_before_activity",
            attempt_id=request.attempt_id,
            route="agy_neon",
            continuation="full",
        )
        await connection.execute(
            update(native_attempt)
            .where(native_attempt.c.id == identifier)
            .values(
                recovery_pending=False,
                local_outcome={
                    **local,
                    "sdk_no_entry": {"joined": True, "upstream_entries": 0},
                },
            )
        )
        return True


async def _hold_restricted_result(
    connection: AsyncConnection,
    owner: JarvisOwner,
    attempt: RowMapping,
    inputs: dict[UUID, RowMapping],
    timestamp: datetime,
    reason: str,
) -> ProductSettlement:
    await _fail_inputs(connection, owner, inputs, reason, attempt_id=str(attempt["id"]))
    await connection.execute(
        update(native_attempt)
        .where(native_attempt.c.id == attempt["id"])
        .values(
            recovery_pending=False,
            fenced_at=attempt["fenced_at"] or timestamp,
            product_outcome={"status": "stale", "reason": reason},
        )
    )
    return ProductSettlement("stale", eligibility_changed=True)


async def defer_first_sample_refusal(
    owner: JarvisOwner, attempt_id: str, refusal: NeonFirstSampleRefusal
) -> ProductSettlement | None:
    """Atomically retain a fenced adapter refusal and its pending input disposition."""
    await owner.require_current(owner.permit("jarvis-product:" + attempt_id))
    identifier = UUID(attempt_id)
    async with owner.database.begin() as connection:
        row = await _locked_attempt(
            connection,
            owner,
            attempt_id,
            _ACTIVE_ROUTE.label("route"),
            native_attempt.c.local_outcome,
            native_attempt.c.native_binding,
            native_attempt.c.request["native_root"].as_string().label("root"),
            native_attempt.c.submission_evidence["type"]
            .as_string()
            .label("submission"),
            native_attempt.c.terminal["status"].as_string().label("terminal_status"),
            live=False,
        )
        local: dict[str, Any] = row["local_outcome"] or {}
        binding: dict[str, Any] = row["native_binding"] or {}
        if (
            row["route"] not in PAID_ROUTES
            or row["owner_epoch"] != str(owner.token)
            or row["settled"]
            or row["fenced_at"] is None
            or row["submission"] != "AgentAccepted"
            or row["terminal_status"] == "succeeded"
            or binding.get("native_turn_id") != refusal.turn_id
            or binding.get("session_ref", {}).get("native_session_id") != row["root"]
            or local.get("neon_may_have_delivered") is not None
            or local.get("neon_refusal") is not None
            or local.get("neon_children")
            or local.get("fence_reason") in {"owner_stop", "cancelled"}
            or await connection.scalar(
                select(native_invocation.c.id)
                .where(native_invocation.c.attempt_id == identifier)
                .limit(1)
            )
            or await connection.scalar(
                select(native_input_delivery.c.attempt_id)
                .where(
                    native_input_delivery.c.attempt_id == identifier,
                    native_input_delivery.c.mode == "steer",
                    native_input_delivery.c.state != "rejected",
                )
                .limit(1)
            )
        ):
            return None
        _, inputs = await _product_inputs(
            connection,
            owner,
            attempt_id,
            delivery=(
                native_input_delivery.c.was_waking
                & (native_input_delivery.c.mode == "initial")
                & (native_input_delivery.c.state != "rejected")
            ),
        )
        observed = datetime.now(UTC)
        reason = "neon_" + refusal.reason
        for item in inputs.values():
            previous = native_retry_evidence(item["trace"])
            await queue_native_retry(
                connection,
                item,
                attempt_id=attempt_id,
                route=row["route"],
                selection="pinned"
                if previous.get("selection") == "pinned"
                else "fresh",
                reason=reason,
                read_only=(
                    previous.get("kind") == "read_only"
                    or item["source"] == CATCHUP_SOURCE
                ),
                fault_retry_used=native_fault_retry_used(item),
                retry_at=observed,
            )
        outcome: dict[str, Any] = {
            "local_outcome": {
                **local,
                "neon_refusal": asdict(refusal),
                "neon_capacity": _neon_capacity(
                    refusal.reason, refusal.retry_after, observed
                ),
            },
            "recovery_pending": False,
        }
        if row["terminal_at"] is not None:
            outcome["product_outcome"] = {
                "status": "failed" if inputs else "stale",
                "reason": reason,
            }
        await connection.execute(
            update(native_attempt)
            .where(native_attempt.c.id == identifier)
            .values(**outcome)
        )
        # A capacity wait is not foreground progress. Let the normal wake recheck.
        return ProductSettlement("failed" if row["terminal_at"] is not None else None)


async def park_unadmitted_input(
    owner: JarvisOwner, identifier: UUID, reason: str
) -> bool:
    await owner.require_current(owner.permit("jarvis-hold:" + str(identifier)))
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        if await connection.scalar(latest_control(owner.scope_id)) == "pause":
            return False
        row = (
            (
                await connection.execute(
                    select(message.c.id, message.c.trace)
                    .where(
                        message.c.id == identifier,
                        message.c.source_conversation_id == owner.scope_id,
                        message.c.request_state == "pending",
                        message.c.processing_parked_at.is_(None),
                        message.c.native_retry_after.is_(None)
                        | (message.c.native_retry_after <= func.now()),
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return False
        await _fail_inputs(
            connection, owner, {identifier: row}, reason, attempt_id=None
        )
        return True


# Inspect the status only when the kernel actually solicited an interruption.
_fence_reason = native_attempt.c.local_outcome["fence_reason"].as_string()
native_loss_product = case(
    (
        _fence_reason.in_(("cancelled", "owner_stop")),
        native_attempt.c.terminal["status"].as_string() == "cancelled",
    ),
    else_=_fence_reason.in_(("native_protocol_fault", "NativeSubmissionConflict")),
)
never_submitted = _ACTIVE_REQUEST & (
    native_attempt.c.submission_evidence["type"].as_string() == "AgentNotSubmitted"
)


async def consume_fenced_losses(
    owner: JarvisOwner,
    *,
    attempt_id: UUID | None = None,
    confirmed_unsubmitted_quota: frozenset[UUID] | None = None,
) -> ProductSettlement:
    """Consume prepared waking deliveries once, under their original authority."""
    status: Literal["failed", "stale"] | None = None
    changed = False
    work = native_attempt.c.recovery_pending & native_attempt.c.terminal_at.is_(None)
    if confirmed_unsubmitted_quota is None:
        work &= ~func.coalesce(never_submitted, False)
    if attempt_id is not None:
        work = (native_attempt.c.id == attempt_id) & (
            work
            | (
                native_attempt.c.terminal_at.is_not(None)
                & native_attempt.c.product_outcome.is_(None)
                & native_loss_product
            )
        )
    while True:
        async with owner.database.begin() as connection:
            await lock_conversation(connection, owner.scope_id)
            pending = (
                (
                    await connection.execute(
                        select(
                            native_attempt.c.id,
                            native_attempt.c.submission_evidence,
                            native_attempt.c.terminal_at,
                            native_attempt.c.recovery_pending,
                            _ACTIVE_ROUTE.label("route"),
                            native_attempt.c.local_outcome["control_receipts"].label(
                                "controls"
                            ),
                            _fence_reason.label("fence_reason"),
                        )
                        .where(
                            native_attempt.c.conversation_id == owner.scope_id,
                            native_attempt.c.fenced_at.is_not(None),
                            work,
                        )
                        .order_by(native_attempt.c.attempt_seq)
                        .limit(1)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if pending is None:
                return ProductSettlement(status, eligibility_changed=changed)
            identifier = str(pending["id"])
            affected = False
            if pending["recovery_pending"]:
                controls: dict[str, dict[str, str]] = pending["controls"] or {}
                unsent = tuple(
                    receipt["input_id"]
                    for receipt in controls.values()
                    if receipt["operation"] == "steer"
                    and receipt["disposition"] in {"rejected", "not_sent"}
                )
                _, inputs = await _product_inputs(
                    connection,
                    owner,
                    identifier,
                    delivery=(
                        native_input_delivery.c.was_waking
                        & (native_input_delivery.c.state != "rejected")
                        & native_input_delivery.c.delivery_id.not_in(unsent)
                    ),
                )
                affected = bool(inputs)
                evidence: dict[str, object] = pending["submission_evidence"] or {}
                continuation: Literal["capacity", "full", "read_only"] | None = None
                if pending["fence_reason"] == "NativeSubmissionConflict":
                    reason = "the model protocol needs repair"
                elif pending["fence_reason"] == "native_protocol_fault":
                    reason = "the model protocol needs repair"
                    if pending["route"] != "agy_neon":
                        continuation = "read_only"
                elif evidence.get("type") == "AgentSubmissionRejected":
                    submitted = (
                        await connection.execute(
                            select(native_attempt.c.request["submitted_request"]).where(
                                native_attempt.c.id == pending["id"]
                            )
                        )
                    ).scalar_one()
                    measured = codex_wire_request_fit(submitted)
                    LOGGER.error(
                        "native start size mismatch: attempt=%s "
                        "fitted=%s/%s stock=%s/%s characters",
                        identifier,
                        measured.actual_chars,
                        measured.max_chars,
                        evidence["actual_chars"],
                        evidence["max_chars"],
                    )
                    reason = (
                        f"jarvis measured {measured.actual_chars} of "
                        f"{measured.max_chars} characters. the model host refused "
                        f"{evidence['actual_chars']} of {evidence['max_chars']} "
                        "characters"
                    )
                elif evidence.get("type") == "AgentNotSubmitted":
                    if (
                        confirmed_unsubmitted_quota is not None
                        and pending["id"] in confirmed_unsubmitted_quota
                    ):
                        reason = "codex_quota_before_activity"
                        continuation = "capacity"
                    elif pending["route"] == "agy_neon":
                        reason = "native_effects_uncertain"
                    else:
                        reason = "the model request was not submitted"
                        continuation = "full"
                else:
                    reason = "native_effects_uncertain"
                    if pending["route"] != "agy_neon":
                        continuation = "read_only"
                await _fail_inputs(
                    connection,
                    owner,
                    inputs,
                    reason,
                    attempt_id=identifier,
                    route=pending["route"],
                    continuation=continuation,
                )
                changed |= affected
            changes: dict[str, Any] = {"recovery_pending": False}
            if pending["terminal_at"] is not None:
                status = "failed" if affected else "stale"
                changes["product_outcome"] = {
                    "status": status,
                    "reason": pending["fence_reason"],
                }
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == pending["id"])
                .values(**changes)
            )


async def fail_native_product(
    owner: JarvisOwner,
    attempt_id: str,
    input_ids: tuple[InputId, ...],
    failure: AgentTerminalFailure | str | None,
    *,
    initial_delivery_proven: bool = False,
) -> ProductSettlement:
    """Settle the original failure under the affected inputs' current authority."""
    await owner.require_current(owner.permit("jarvis-product:" + attempt_id))
    timestamp = datetime.now(UTC)
    reason = (
        "context_window_exceeded"
        if isinstance(failure, AgentFailure)
        and failure.cause == "context_window_exceeded"
        else "codex_limit_uncertain_effects"
        if isinstance(failure, AgentQuotaExhausted)
        else failure
        if isinstance(failure, str)
        else "the native provider did not complete this turn"
    )
    delivery = proven_native_delivery
    if initial_delivery_proven:
        # An accepted seal proves the opening, never a later steer.
        delivery |= (native_input_delivery.c.mode == "initial") & (
            native_input_delivery.c.state == "prepared"
        )
    delivery &= native_input_delivery.c.was_waking
    async with owner.database.begin() as connection:
        fallback = ()
        if isinstance(failure, str) and not await connection.scalar(
            select(native_attempt.c.id).where(native_attempt.c.id == UUID(attempt_id))
        ):
            fallback = input_ids
        attempt, inputs = await _product_inputs(
            connection,
            owner,
            attempt_id,
            delivery=delivery,
            fallback_input_ids=fallback,
        )
        if attempt is not None and attempt["settled"]:
            return ProductSettlement()
        if not isinstance(failure, str) and (
            attempt is None or attempt["terminal_at"] is None
        ):
            raise NativeDefect("provider failure settlement requires its original seal")
        route = None if attempt is None else attempt["route"]
        already_charged = attempt is not None and not attempt["recovery_pending"]
        if not already_charged:
            await _fail_inputs(
                connection,
                owner,
                inputs,
                reason,
                attempt_id=attempt_id,
                route=route,
                continuation="read_only" if attempt is not None else None,
            )
        status: Literal["failed", "stale"] | None = None
        if attempt is not None:
            changes: dict[str, object] = {
                "fenced_at": attempt["fenced_at"] or timestamp,
                "recovery_pending": False,
            }
            if attempt["terminal_at"] is not None:
                status = "failed" if inputs else "stale"
                changes["product_outcome"] = {
                    "status": status,
                    "reason": reason,
                }
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == attempt["id"])
                .values(**changes)
            )
        return ProductSettlement(
            status,
            eligibility_changed=bool(inputs) and not already_charged,
        )


def _evidence(value: object) -> dict[str, object]:
    if isinstance(value, AgentTerminal):
        return terminal_to_json(value)
    if not is_dataclass(value) or isinstance(value, type):
        raise NativeDefect("native evidence must be a typed provider value")
    document = {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "turn"
    }
    attempt = getattr(value, "attempt", None)
    if attempt is not None:
        document["attempt"] = asdict(attempt)
    turn = getattr(value, "turn", None)
    if turn is not None:
        document["turn"] = {
            "session_ref": thaw_json_value(ref_to_json(turn.session_ref)),
            "native_turn_id": turn.native_turn_id,
        }
    document["type"] = type(value).__name__
    return cast(dict[str, object], document)

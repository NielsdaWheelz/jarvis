"""Native attempt evidence and callback receipts; effects stay in existing stores."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, cast
from uuid import UUID, uuid4, uuid5

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
    AgentAttempt,
    AgentControlReceipt,
    AgentFailure,
    AgentMessage,
    AgentNotSubmitted,
    AgentSubmission,
    AgentSubmissionRejected,
    AgentTerminal,
    AgentTerminalFailure,
    AgentTurnRef,
    JsonObject,
    JsonSchemaAgentOutput,
    NativeTerminalEvidence,
    codex_wire_request_fit,
    ref_to_json,
    terminal_from_json,
    terminal_to_json,
    thaw_json_value,
)
from pydantic import ValidationError
from sqlalchemy import ColumnElement, RowMapping, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.actions import (
    attachment_uncertainty_receipt,
    recorded_action_result,
    require_locked_action,
)
from jarvis.admission import JarvisOwner
from jarvis.approval_tools import (
    APPROVAL_RESPOND_SPEC,
    ApprovalRespondInput,
    ApprovalRespondResult,
)
from jarvis.db import (
    action,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
    read_position,
)
from jarvis.home_notices import enqueue_notice
from jarvis.home_pages import DEFAULT_EXPORT
from jarvis.home_reads import proposal_presented, reference_context
from jarvis.memory_service import MemoryService
from jarvis.messages import (
    MAX_TRACE_BYTES,
    cancel_unentered_actions,
    causal_component_ids,
)
from jarvis.ownership import Database, lock_conversation, memory_is_admitted
from jarvis.terminal import (
    JarvisNativeMessage,
    JarvisTerminal,
    Presentation,
    Progress,
    RenderedTerminal,
    Silent,
)
from jarvis.tool_results import completed_tool_result, host_rejected

LOGGER = logging.getLogger(__name__)


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
    output: JsonSchemaAgentOutput | None
    terminal: AgentTerminal


@dataclass(frozen=True, slots=True)
class ProductSettlement:
    """The disposition written by this transaction, if any."""

    status: Literal["committed", "failed", "stale"] | None = None
    completed: tuple[UUID, ...] = ()
    eligibility_changed: bool = False


class NativeContentDefect(NativeDefect):
    """A well-formed final response contradicts its delivered inputs or actions."""


class StaleNativeProduct(NativeDefect):
    """The original delivery no longer has product settlement authority."""


async def recover_sealed_turn(
    database: Database, owner: JarvisOwner, attempt_id: str
) -> _SealedNativeTurn | None:
    """Reopen inference facts without current provider or execution authority."""
    async with database.connect() as connection:
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
                    ).where(native_attempt.c.id == UUID(attempt_id))
                )
            )
            .mappings()
            .one_or_none()
        )
    if row is None or row["terminal"] is None:
        return None
    if row["conversation_id"] != owner.scope_id:
        raise NativeDefect("sealed inference is outside this conversation")
    terminal = terminal_from_json(row["terminal"])
    prepared = AgentAttempt(**row["provider_attempt"])
    if (
        not isinstance(terminal.evidence, NativeTerminalEvidence)
        or terminal.evidence.attempt != prepared
        or prepared.attempt_id != attempt_id
    ):
        raise NativeDefect("product recovery requires original sealed native evidence")
    output = row["output"]
    return _SealedNativeTurn(
        attempt_id,
        tuple(map(InputId, row["input_ids"])),
        None
        if output is None
        else JsonSchemaAgentOutput(output["name"], output["schema"]),
        terminal,
    )


class PostgresNativeJournal:
    def __init__(
        self,
        database: Database,
        *,
        definition: NativeDefinition,
        plan: FrozenToolPlan,
        owner: JarvisOwner,
        memory: MemoryService,
    ) -> None:
        self.database = database
        self.definition = definition
        self.plan = plan
        self.owner = owner
        self.memory = memory

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
            value["definition_fingerprint"]
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
        if request.fingerprint != row["request_fingerprint"]:
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
        document: dict[str, Any] = {
            "schema_version": "jarvis-native-request.v2",
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
        async with self.database.begin() as connection:
            await lock_conversation(connection, request.permit.scope_id)
            admitted = (
                await connection.execute(
                    select(message.c.id)
                    .where(
                        message.c.id.in_(tuple(map(UUID, request.input_ids))),
                        message.c.source_conversation_id == request.permit.scope_id,
                        message.c.role.in_(("owner", "host")),
                        message.c.control_kind.is_(None),
                        message.c.request_state.in_(("pending", "waiting")),
                        message.c.processing_parked_at.is_(None),
                        message.c.native_retry_after.is_(None)
                        | (message.c.native_retry_after <= func.now()),
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
            await connection.execute(
                insert(native_attempt).values(
                    id=UUID(request.attempt_id),
                    conversation_id=request.permit.scope_id,
                    attempt_seq=seq,
                    owner_epoch=str(request.permit.owner_token),
                    memory_admitted=memory_is_admitted(connection),
                    request_fingerprint=request.fingerprint,
                    request=document,
                    armed_at=datetime.now(UTC),
                    recovery_pending=True,
                )
            )

    async def bind(self, attempt_id: str, native_turn: AgentTurnRef) -> None:
        binding = {
            "session_ref": thaw_json_value(ref_to_json(native_turn.session_ref)),
            "native_turn_id": native_turn.native_turn_id,
        }
        async with self.database.begin() as connection:
            row = await _locked_attempt(
                connection,
                self.owner,
                attempt_id,
                native_attempt.c.native_binding,
                live=False,
            )
            if row["native_binding"] is not None and row["native_binding"] != binding:
                raise NativeDefect("native turn binding changed")
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(native_binding=binding)
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
                    if recorded is None:
                        stored = await require_locked_action(connection, identifier)
                        if (
                            row["action_id"] != identifier
                            or row["tool_id"] != stored.tool_name
                        ):
                            raise NativeDefect(
                                "attachment receipt changed invocation lineage"
                            )
                        recorded = await attachment_uncertainty_receipt(
                            connection, stored
                        )
                        if recorded == result.result:
                            # Current action evidence can advance later; this callback
                            # keeps its exact original failure and host reference.
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
        self, invocation_id: str, arguments: ApprovalRespondInput
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
                live=delivery.state == "prepared",
            )
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
                            message.c.native_retry_after.is_(None)
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
                native = isinstance(evidence.evidence, NativeTerminalEvidence)
                if (
                    isinstance(evidence.evidence, NativeTerminalEvidence)
                    and evidence.evidence.attempt != prepared
                ):
                    raise NativeDefect(
                        "native terminal belongs to another prepared attempt"
                    )
                if not native:
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
                    value = {**local, "terminal": value}
                changes: dict[str, Any] = {column: value}
                if native:
                    changes["terminal_at"] = datetime.now(UTC)
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
                home = await _presentation_home(
                    connection, self.owner.scope_id, row["id"], value.response.present
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


async def _presentation_home(
    connection: AsyncConnection,
    scope: str,
    attempt_id: UUID,
    present: Presentation | None,
    stopping: tuple[UUID, ...] = (),
) -> dict[str, object] | None:
    """Walk only proven deliveries' parent chains under the conversation lock."""
    if present is None:
        return None
    eligible = (
        (message.c.source_conversation_id == scope)
        & message.c.request_state.in_(("pending", "waiting", "completed"))
        & message.c.control_kind.is_(None)
    )
    if stopping:
        eligible &= message.c.id.not_in(stopping)
    delivered = select(native_input_delivery.c.message_id).where(
        native_input_delivery.c.attempt_id == attempt_id, proven_native_delivery
    )
    ancestors = (
        select(message.c.id, message.c.parent_request_id)
        .where(eligible, message.c.id.in_(delivered))
        .cte("ancestors", recursive=True)
    )
    ancestors = ancestors.union(
        select(message.c.id, message.c.parent_request_id)
        .join(ancestors, message.c.id == ancestors.c.parent_request_id)
        .where(eligible)
    )
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
    elif await reference_context(
        connection, scope, present.ref.model_dump(mode="json"), DEFAULT_EXPORT
    ):
        return {"present": present.model_dump(mode="json")}
    else:
        reason = "unavailable_target"
    LOGGER.warning(
        "native presentation omitted: attempt=%s reason=%s", attempt_id, reason
    )
    return None


async def commit_product(
    database: Database,
    owner: JarvisOwner,
    turn: _SealedNativeTurn,
    final: JarvisTerminal,
    rendered: RenderedTerminal,
    *,
    recovering: bool = False,
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
        stopping = tuple(
            key for key, item in statuses.items() if item.disposition == "stop"
        )
        home = await _presentation_home(
            connection,
            owner.scope_id,
            attempt["id"],
            None if isinstance(final.response, Silent) else final.response.present,
            stopping,
        )
        timestamp = datetime.now(UTC)
        if stopping:
            await cancel_unentered_actions(connection, stopping, timestamp)
        owned: set[UUID] = set()
        approval_refs: set[UUID] = set()
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
                    item["tool_name"] == "agent.wait"
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
            refs = set(map(UUID, disposition.action_refs))
            if disposition.wait_reason in {"approval", "external_reconciliation"}:
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
                        if unresolved_notice is not None:
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
                        state = "pending"
            if state == "waiting" and disposition.wait_reason == "approval":
                approval_refs.update(refs)
            trace = {**target["trace"], "native_attempt_id": turn.attempt_id}
            trace.pop("native_context_retry", None)
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
                    native_retry_after=None,
                    wait_reason=disposition.wait_reason if state == "waiting" else None,
                    processed_at=timestamp
                    if state in {"completed", "stopped"}
                    else None,
                    trace=trace,
                )
            )
            if state in {"completed", "stopped"}:
                completed.append(identifier)
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
            home = {**(home or {}), "proposal_ids": list(map(str, unseen))}
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
            await enqueue_notice(connection, conclusion_id)
        await connection.execute(
            update(native_attempt)
            .where(native_attempt.c.id == attempt["id"])
            .values(
                recovery_pending=False,
                product_outcome={
                    "status": "committed",
                    "response_id": str(conclusion_id)
                    if rendered.content is not None
                    else None,
                    "input_outcomes": [
                        item.model_dump(mode="json") for item in final.input_outcomes
                    ],
                },
            )
        )
    return ProductSettlement("committed", tuple(completed))


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
                    native_attempt.c.terminal_at,
                    native_attempt.c.fenced_at,
                    native_attempt.c.recovery_pending,
                    native_attempt.c.owner_epoch,
                    native_attempt.c.product_outcome.is_not(None).label("settled"),
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
) -> None:
    """A waking input shares one fresh opening across contact and context failures."""
    if reason in {"lost_contact", "context_window_exceeded"}:
        unused = {
            key for key, row in inputs.items() if row["native_retry_after"] is None
        }
        if unused:
            schedule = (
                update(message)
                .where(message.c.id.in_(unused))
                .values(native_retry_after=func.now() + timedelta(seconds=30))
            )
            if reason == "context_window_exceeded":
                schedule = schedule.values(
                    trace=message.c.trace.op("||")({"native_context_retry": True})
                )
            await connection.execute(schedule)
            inputs = {key: row for key, row in inputs.items() if key not in unused}
    timestamp = datetime.now(UTC)
    for identifier, row in inputs.items():
        if reason == "context_window_exceeded":
            failure = "the model reached its context limit while retrying"
        elif reason == "lost_contact":
            failure = (
                "i lost contact with the model while retrying"
                if row["trace"].get("native_context_retry") is True
                else "i lost contact with the model twice"
            )
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
        failure_id = uuid4()
        pending = tuple(
            await connection.scalars(
                select(action.c.id)
                .where(
                    action.c.origin_message_id == identifier,
                    action.c.status == "awaiting_approval",
                )
                .order_by(action.c.created_at, action.c.id)
            )
        )
        repair = (
            " its pending proposals need this repair before a decision."
            if pending
            else ""
        )
        await connection.execute(
            insert(message).values(
                id=failure_id,
                role="assistant",
                text=(
                    f"{failure} on request {identifier}. "
                    f"its actions and reads are recorded.{repair} "
                    "to resume, stop jarvis, "
                    f"run `jarvis release-parked {identifier}`, then start jarvis."
                ),
                source="native_failure",
                home={"proposal_ids": list(map(str, pending))} if pending else None,
                source_conversation_id=owner.scope_id,
                memory_admitted=memory_is_admitted(connection),
                processed_at=timestamp,
                trace={"native_attempt_id": attempt_id}
                if attempt_id is not None
                else {},
            )
        )
        await enqueue_notice(connection, failure_id)


async def park_oversized_input(
    owner: JarvisOwner, identifier: UUID, reason: str
) -> bool:
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
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


async def consume_fenced_losses(
    owner: JarvisOwner, *, attempt_id: UUID | None = None
) -> ProductSettlement:
    """Consume prepared waking deliveries once, under their original authority."""
    status: Literal["failed", "stale"] | None = None
    changed = False
    work = native_attempt.c.recovery_pending & native_attempt.c.terminal_at.is_(None)
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
                if pending["fence_reason"] in {
                    "native_protocol_fault",
                    "NativeSubmissionConflict",
                }:
                    reason = "the model protocol needs repair"
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
                    reason = "the model request was not submitted"
                else:
                    reason = "lost_contact"
                await _fail_inputs(
                    connection, owner, inputs, reason, attempt_id=identifier
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
) -> ProductSettlement:
    """Settle the original failure under the affected inputs' current authority."""
    await owner.require_current(owner.permit("jarvis-product:" + attempt_id))
    timestamp = datetime.now(UTC)
    context_exhausted = (
        isinstance(failure, AgentFailure) and failure.cause == "context_window_exceeded"
    )
    reason = (
        failure
        if isinstance(failure, str)
        else "the native provider did not complete this turn"
    )
    if context_exhausted:
        reason = "context_window_exceeded"
    async with owner.database.begin() as connection:
        attempt, inputs = await _product_inputs(
            connection,
            owner,
            attempt_id,
            delivery=(native_input_delivery.c.was_waking & proven_native_delivery)
            if context_exhausted
            else proven_native_delivery,
            fallback_input_ids=() if context_exhausted else input_ids,
        )
        if attempt is not None and attempt["settled"]:
            return ProductSettlement()
        if not isinstance(failure, str) and (
            attempt is None or attempt["terminal_at"] is None
        ):
            raise NativeDefect("provider failure settlement requires its original seal")
        already_charged = (
            not isinstance(failure, str)
            and attempt is not None
            and not attempt["recovery_pending"]
        )
        if context_exhausted and already_charged:
            # A late seal refines the cause of this still-outstanding retry.
            inputs = {
                key: row
                for key, row in inputs.items()
                if row["native_retry_after"] is not None
            }
            if inputs:
                await connection.execute(
                    update(message)
                    .where(message.c.id.in_(inputs))
                    .values(
                        trace=message.c.trace.op("||")({"native_context_retry": True})
                    )
                )
        elif not already_charged:
            await _fail_inputs(connection, owner, inputs, reason, attempt_id=attempt_id)
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
            status, eligibility_changed=bool(inputs) and not already_charged
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

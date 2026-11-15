"""Native attempt evidence and callback receipts; effects stay in existing stores."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
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
    AgentMessage,
    AgentNotSubmitted,
    AgentSubmission,
    AgentTerminal,
    AgentTurnRef,
    JsonObject,
    JsonSchemaAgentOutput,
    NativeTerminalEvidence,
    ref_to_json,
    terminal_from_json,
    terminal_to_json,
    thaw_json_value,
)
from pydantic import ValidationError
from sqlalchemy import RowMapping, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.actions import recorded_action_result
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
    read_position,
)
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
    Progress,
    render_terminal,
)
from jarvis.tool_results import completed_tool_result, host_rejected


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


async def recover_sealed_turn(
    database: Database, owner: JarvisOwner, attempt_id: str
) -> _SealedNativeTurn | None:
    """Reopen inference facts without current provider or execution authority."""
    async with database.connect() as connection:
        row = (
            (
                await connection.execute(
                    select(native_attempt).where(
                        native_attempt.c.id == UUID(attempt_id)
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
    if row is None or row["terminal"] is None:
        return None
    if row["conversation_id"] != owner.scope_id:
        raise NativeDefect("sealed inference is outside this conversation")
    value = row["request"]
    terminal = terminal_from_json(row["terminal"])
    prepared = AgentAttempt(**value["provider_attempt"])
    if (
        not isinstance(terminal.evidence, NativeTerminalEvidence)
        or terminal.evidence.attempt != prepared
        or prepared.attempt_id != attempt_id
    ):
        raise NativeDefect("product recovery requires original sealed native evidence")
    output = value.get("output")
    return _SealedNativeTurn(
        attempt_id,
        tuple(map(InputId, value["input_ids"])),
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
                        select(native_attempt).where(
                            native_attempt.c.id == UUID(attempt_id)
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
            inputs = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(tuple(map(UUID, request.input_ids))))
                        .order_by(message.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(inputs) != len(request.input_ids) or any(
                row["source_conversation_id"] != request.permit.scope_id
                or row["request_state"] in {"stopped", "completed"}
                for row in inputs
            ):
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
                )
            )

    async def bind(self, attempt_id: str, native_turn: AgentTurnRef) -> None:
        binding = {
            "session_ref": thaw_json_value(ref_to_json(native_turn.session_ref)),
            "native_turn_id": native_turn.native_turn_id,
        }
        async with self.database.begin() as connection:
            row = await _locked_attempt(connection, self.owner, attempt_id, live=False)
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
                        native_input_delivery.c.state.in_(
                            ("sent", "queued", "recorded")
                        ),
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
            dispatch = DispatchCompleted(value["result"], value["wire_text"], None)
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
                    if recorded != result.result:
                        raise NativeDefect(
                            "replayed action differs from its original recorder result"
                        )
                    links["action_id"] = identifier
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
                        native_input_delivery.c.state.in_(
                            ("sent", "queued", "recorded")
                        ),
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
                    and evidence["attempt"] != row["request"]["provider_attempt"]
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
            row = await _locked_attempt(connection, self.owner, attempt_id, live=False)
            prepared = AgentAttempt(**row["request"]["provider_attempt"])
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
                column = "terminal" if native else "local_outcome"
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
                    if local["terminal"] is not None and local["terminal"] != value:
                        raise NativeDefect("local terminal evidence changed")
                    value = {**local, "terminal": value}
                changes: dict[str, Any] = {column: value}
                if native:
                    changes["terminal_at"] = datetime.now(UTC)
            else:
                if evidence.attempt != prepared:
                    raise NativeDefect("submission evidence belongs to another attempt")
                value = _evidence(evidence)
                column = "submission_evidence"
                changes = {column: value}
                if isinstance(evidence, AgentNotSubmitted):
                    changes["fenced_at"] = datetime.now(UTC)
            if row[column] is not None:
                if row[column] != value:
                    raise NativeDefect("native outcome evidence changed")
                return
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(**changes)
            )

    async def fence(self, attempt_id: str, reason: str) -> None:
        async with self.database.begin() as connection:
            row = await _locked_attempt(connection, self.owner, attempt_id, live=False)
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
                        "fence_reason": local["fence_reason"] or reason,
                    },
                )
            )

    async def record(self, attempt_id: str, progress: AgentMessage) -> None:
        identifier = uuid5(UUID(attempt_id), progress.message_id)
        async with self.database.begin() as connection:
            row = await _locked_attempt(connection, self.owner, attempt_id, live=False)
            if (
                row["fenced_at"] is not None
                or row["terminal"] is not None
                or row["product_outcome"] is not None
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
                await connection.execute(insert(message).values(**values))
            elif (
                existing["text"] != value.response.text
                or existing["trace"] != values["trace"]
            ):
                raise NativeDefect("public progress identity changed")


async def _locked_attempt(
    connection: AsyncConnection,
    owner: JarvisOwner,
    attempt_id: str,
    *,
    live: bool = True,
) -> RowMapping:
    await lock_conversation(connection, owner.scope_id)
    row = (
        (
            await connection.execute(
                select(native_attempt)
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
        or row["terminal"] is not None
        or row["product_outcome"] is not None
        or row["owner_epoch"] != str(owner.token)
    ):
        raise NativeDefect("native attempt authority is stale")
    return row


async def commit_product(
    database: Database,
    owner: JarvisOwner,
    turn: _SealedNativeTurn,
    final: JarvisTerminal,
    *,
    recovering: bool = False,
) -> tuple[UUID, ...]:
    await owner.require_current(owner.permit("jarvis-product:" + turn.attempt_id))
    rendered = render_terminal(final)
    conclusion_id = uuid5(UUID(turn.attempt_id), "product-conclusion")
    completed: list[UUID] = []
    async with database.begin() as connection:
        attempt, inputs = await _product_inputs(
            connection, owner, turn.attempt_id, turn.input_ids
        )
        if attempt is None or attempt["terminal"] is None:
            raise NativeDefect("product settlement lacks a native terminal")
        if attempt["product_outcome"] is not None:
            return ()
        delivered_count = await connection.scalar(
            select(func.count())
            .select_from(native_input_delivery)
            .where(
                native_input_delivery.c.attempt_id == attempt["id"],
                native_input_delivery.c.state.in_(("sent", "queued", "recorded")),
            )
        )
        if not inputs or len(inputs) != delivered_count:
            raise NativeDefect("original input lifecycle invalidates this terminal")
        if not recovering and (
            attempt["fenced_at"] is not None
            or attempt["owner_epoch"] != str(owner.token)
        ):
            raise NativeDefect("native attempt authority is stale")
        statuses = {UUID(item.input_id): item for item in final.input_outcomes}
        if not set(statuses).issubset(inputs):
            raise NativeDefect(
                "final dispositions name input without live delivered authority"
            )
        timestamp = datetime.now(UTC)
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
            if disposition.disposition == "complete" and own_blockers:
                raise NativeDefect("request completion would hide unresolved actions")
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
                    raise NativeDefect("waiting disposition named a foreign action")
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
                                        native_input_delivery.c.state.in_(
                                            ("sent", "queued", "recorded")
                                        ),
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
                            raise NativeDefect(
                                "waiting disposition fabricated its action blocker"
                            )
                        state = "pending"
            if state == "stopped":
                await cancel_unentered_actions(connection, (identifier,), timestamp)
            trace = {**target["trace"], "native_attempt_id": turn.attempt_id}
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
                raise NativeDefect("request settlement trace exceeds its bound")
            await connection.execute(
                update(message)
                .where(message.c.id == identifier)
                .values(
                    request_state=state,
                    wait_reason=disposition.wait_reason if state == "waiting" else None,
                    processed_at=timestamp
                    if state in {"completed", "stopped"}
                    else None,
                    trace=trace,
                )
            )
            if state in {"completed", "stopped"}:
                completed.append(identifier)
        if rendered.content is not None:
            await connection.execute(
                insert(message).values(
                    id=conclusion_id,
                    role="assistant",
                    text=rendered.content,
                    source="native_final",
                    memory_admitted=memory_is_admitted(connection),
                    source_conversation_id=owner.scope_id,
                    processed_at=timestamp,
                    trace={"native_attempt_id": turn.attempt_id},
                )
            )
        await connection.execute(
            update(native_attempt)
            .where(native_attempt.c.id == attempt["id"])
            .values(
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
    return tuple(completed)


async def _product_inputs(
    connection: AsyncConnection,
    owner: JarvisOwner,
    attempt_id: str,
    input_ids: tuple[InputId, ...],
    *,
    failed: bool = False,
) -> tuple[RowMapping | None, dict[UUID, RowMapping]]:
    await lock_conversation(connection, owner.scope_id)
    delivered = tuple(
        (
            await connection.execute(
                select(native_input_delivery.c.message_id).where(
                    native_input_delivery.c.attempt_id == UUID(attempt_id),
                    native_input_delivery.c.state.in_(("sent", "queued", "recorded")),
                )
            )
        ).scalars()
    )
    rows = (
        (
            await connection.execute(
                select(message)
                .where(
                    message.c.id.in_(
                        delivered or (tuple(map(UUID, input_ids)) if failed else ())
                    )
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
                select(native_attempt)
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
            or row["request_state"] not in {"pending", "waiting"}
        ):
            continue
        controlled = (
            None
            if attempt is None
            else await connection.scalar(
                select(message.c.id)
                .where(
                    message.c.source_conversation_id == owner.scope_id,
                    message.c.control_sequence > attempt["request"]["control_sequence"],
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
        if controlled is None and not superseded:
            inputs[row["id"]] = row
    return attempt, inputs


async def park_product(
    database: Database,
    owner: JarvisOwner,
    attempt_id: str,
    input_ids: tuple[InputId, ...],
    reason: str,
) -> None:
    """Preserve the original seal and atomically quarantine every affected input."""
    await owner.require_current(owner.permit("jarvis-product:" + attempt_id))
    timestamp = datetime.now(UTC)
    conclusion_id = uuid5(UUID(attempt_id), "product-failure")
    async with database.begin() as connection:
        attempt, inputs = await _product_inputs(
            connection, owner, attempt_id, input_ids, failed=True
        )
        if attempt is not None and attempt["product_outcome"] is not None:
            return
        for identifier, row in inputs.items():
            trace = {
                **row["trace"],
                "native_attempt_id": attempt_id,
                "failure_code": reason,
            }
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
        if inputs:
            await connection.execute(
                insert(message)
                .values(
                    id=conclusion_id,
                    role="assistant",
                    text=(
                        "i couldn't finish processing these requests. "
                        "they remain unfinished and need repair."
                    ),
                    source="native_failure",
                    source_conversation_id=owner.scope_id,
                    memory_admitted=memory_is_admitted(connection),
                    processed_at=timestamp,
                    trace={"native_attempt_id": attempt_id},
                )
                .on_conflict_do_nothing(index_elements=(message.c.id,))
            )
        if attempt is not None:
            changes: dict[str, object] = {
                "fenced_at": attempt["fenced_at"] or timestamp
            }
            if attempt["terminal"] is not None:
                changes["product_outcome"] = {
                    "status": "failed" if inputs else "stale",
                    "reason": reason,
                }
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == attempt["id"])
                .values(**changes)
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

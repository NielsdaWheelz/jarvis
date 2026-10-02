"""Native attempt evidence and callback receipts; effects stay in existing stores."""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass, replace
from datetime import UTC, datetime
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
    NativeTerminalEvidence,
    ref_to_json,
    terminal_from_json,
    terminal_to_json,
    thaw_json_value,
)
from sqlalchemy import RowMapping, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.admission import JarvisOwner
from jarvis.db import (
    action,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    read_position,
)
from jarvis.ownership import Database, lock_conversation
from jarvis.terminal import JarvisTerminal, TurnEvidence, render_terminal


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


class PostgresNativeJournal:
    def __init__(
        self,
        database: Database,
        *,
        definition: NativeDefinition,
        plan: FrozenToolPlan,
        owner: JarvisOwner,
    ) -> None:
        self.database = database
        self.definition = definition
        self.plan = plan
        self.owner = owner

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
        document: dict[str, Any] = {
            "schema_version": "jarvis-native-request.v1",
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
                    request_fingerprint=request.fingerprint,
                    request=document,
                    armed_at=datetime.now(UTC),
                )
            )

    async def _locked_attempt(
        self, connection: AsyncConnection, attempt_id: str, *, live: bool = True
    ) -> RowMapping:
        await lock_conversation(connection, self.owner.scope_id)
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
        if row["conversation_id"] != self.owner.scope_id:
            raise NativeDefect("native attempt is outside this conversation")
        if live and (
            row["fenced_at"] is not None
            or row["product_outcome"] is not None
            or row["owner_epoch"] != str(self.owner.token)
        ):
            raise NativeDefect("native attempt authority is stale")
        return row

    async def bind(self, attempt_id: str, native_turn: AgentTurnRef) -> None:
        binding = {
            "session_ref": thaw_json_value(ref_to_json(native_turn.session_ref)),
            "native_turn_id": native_turn.native_turn_id,
        }
        async with self.database.begin() as connection:
            row = await self._locked_attempt(connection, attempt_id)
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
        binding = self.plan.catalog_view.binding(proposal.tool_id)
        accepted = proposal.validation_error is None
        request_id = (
            UUID(cast(dict[str, Any], arguments)["request_ref"])
            if accepted and binding.spec.effect is ToolEffect.Write
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
                if (
                    owner_input is None
                    or owner_input["role"] != "owner"
                    or owner_input["request_state"] not in {"pending", "waiting"}
                    or str(request_id) not in proposal.input_ids
                ):
                    raise NativeDefect(
                        "accepted Write request_ref has no current owner intent"
                    )
            await self._locked_attempt(connection, proposal.attempt_id)
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
        return InvocationRecord(str(identifier), ordinal, proposal, None)

    async def _reply(
        self, connection: AsyncConnection, row: RowMapping
    ) -> NativeReply | None:
        value = row["reply_receipt"]
        if value is None:
            return None
        if value["type"] == "tool_result_ref":
            if row["action_id"] is not None:
                result = await connection.scalar(
                    select(action.c.result).where(action.c.id == row["action_id"])
                )
                if isinstance(result, dict) and "creation_receipt" in result:
                    result = cast(dict[str, Any], result)["creation_receipt"]
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
            await self._locked_attempt(connection, str(current["attempt_id"]))
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
                    recorded = await connection.scalar(
                        select(action.c.result).where(action.c.id == identifier)
                    )
                    if isinstance(recorded, dict) and "creation_receipt" in recorded:
                        recorded = cast(dict[str, Any], recorded)["creation_receipt"]
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

    async def record_delivery(self, delivery: NativeDelivery) -> None:
        evidence = None if delivery.evidence is None else _evidence(delivery.evidence)
        async with self.database.begin() as connection:
            await self._locked_attempt(connection, delivery.attempt_id)
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
            row = await self._locked_attempt(connection, attempt_id, live=False)
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
            row = await self._locked_attempt(connection, attempt_id, live=False)
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
        if (
            progress.phase != "commentary"
            or not progress.text
            or len(progress.text) > 2_000
        ):
            raise NativeDefect(
                "public progress is outside the Discord content contract"
            )
        identifier = uuid5(UUID(attempt_id), progress.message_id)
        async with self.database.begin() as connection:
            row = await self._locked_attempt(connection, attempt_id)
            values = {
                "id": identifier,
                "role": "assistant",
                "text": progress.text,
                "source": "native_progress",
                "source_conversation_id": row["conversation_id"],
                "source_message_id": None,
                "processed_at": datetime.now(UTC),
                "trace": {
                    "native_attempt_id": attempt_id,
                    "native_item_id": progress.message_id,
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
                existing["text"] != progress.text
                or existing["trace"] != values["trace"]
            ):
                raise NativeDefect("public progress identity changed")

    async def commit_product(
        self,
        request: NativeRequest,
        final: JarvisTerminal,
        evidence: TurnEvidence,
        *,
        recovering: bool = False,
    ) -> tuple[UUID, ...]:
        await self.owner.require_current(
            self.owner.permit("jarvis-product:" + request.attempt_id)
            if recovering
            else request.permit
        )
        rendered = render_terminal(final, evidence)
        completed: list[UUID] = []
        async with self.database.begin() as connection:
            await lock_conversation(connection, self.owner.scope_id)
            delivered = set(
                (
                    await connection.execute(
                        select(native_input_delivery.c.message_id).where(
                            native_input_delivery.c.attempt_id
                            == UUID(request.attempt_id),
                            native_input_delivery.c.state.in_(
                                ("sent", "queued", "recorded")
                            ),
                        )
                    )
                ).scalars()
            )
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(delivered))
                        .order_by(message.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            row = await self._locked_attempt(
                connection, request.attempt_id, live=not recovering
            )
            if row["product_outcome"] is not None:
                return ()
            if row["terminal"] is None:
                raise NativeDefect("product settlement lacks a native terminal")
            self.restore_request(row)
            intervening = await connection.scalar(
                select(message.c.id)
                .where(
                    message.c.source_conversation_id == self.owner.scope_id,
                    message.c.control_sequence > row["request"]["control_sequence"],
                    message.c.control_targets.overlap(list(delivered)),
                )
                .limit(1)
            )
            if intervening is not None:
                raise NativeDefect(
                    "owner control changed this attempt's request lifecycle"
                )
            inputs = {item["id"]: item for item in rows}
            statuses = {UUID(item.input_id): item for item in final.input_outcomes}
            if not set(statuses).issubset(delivered):
                raise NativeDefect("final dispositions name undelivered input")
            if rendered.content is None and any(
                item["role"] == "host" for item in rows
            ):
                raise NativeDefect("host events require a visible response")
            for identifier, disposition in statuses.items():
                target = inputs.get(identifier)
                if (
                    target is None
                    or target["role"] != "owner"
                    or target["request_state"] not in {"pending", "waiting"}
                ):
                    raise NativeDefect("final input authority changed")
                actions = (
                    (
                        await connection.execute(
                            select(action)
                            .where(action.c.origin_message_id == identifier)
                            .order_by(action.c.id)
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .all()
                )
                blockers = {
                    item["id"]: item
                    for item in actions
                    if item["status"]
                    in {"queued", "awaiting_approval", "executing", "uncertain"}
                    and not (
                        item["tool_name"] == "schedule.wake"
                        and item["result"] is not None
                        and "creation_receipt" in item["result"]
                    )
                }
                refs = set(map(UUID, disposition.action_refs))
                if disposition.disposition == "complete" and blockers:
                    raise NativeDefect(
                        "request completion would hide unresolved actions"
                    )
                if disposition.wait_reason in {"approval", "external_reconciliation"}:
                    expected = (
                        {"awaiting_approval"}
                        if disposition.wait_reason == "approval"
                        else {"queued", "executing", "uncertain"}
                    )
                    if not refs or any(
                        ref not in blockers or blockers[ref]["status"] not in expected
                        for ref in refs
                    ):
                        raise NativeDefect(
                            "waiting disposition fabricated its action blocker"
                        )
                state = (
                    "completed"
                    if disposition.disposition == "complete"
                    else "pending"
                    if disposition.disposition == "continue"
                    else "waiting"
                )
                await connection.execute(
                    update(message)
                    .where(message.c.id == identifier)
                    .values(
                        request_state=state,
                        wait_reason=disposition.wait_reason,
                        processed_at=datetime.now(UTC)
                        if state == "completed"
                        else None,
                        trace={
                            **target["trace"],
                            "native_attempt_id": request.attempt_id,
                        },
                    )
                )
                if state == "completed":
                    completed.append(identifier)
            conclusion_id = uuid5(UUID(request.attempt_id), "product-conclusion")
            if rendered.content is not None:
                await connection.execute(
                    insert(message).values(
                        id=conclusion_id,
                        role="assistant",
                        text=rendered.content,
                        source="native_final",
                        source_conversation_id=self.owner.scope_id,
                        processed_at=datetime.now(UTC),
                        trace={"native_attempt_id": request.attempt_id},
                    )
                )
            for target in rows:
                if target["role"] == "host":
                    await connection.execute(
                        update(message)
                        .where(message.c.id == target["id"])
                        .values(
                            processed_at=datetime.now(UTC),
                            trace={
                                **target["trace"],
                                "conclusion_message_id": str(conclusion_id),
                            },
                        )
                    )
                    await connection.execute(
                        update(message)
                        .where(
                            message.c.id == target["trace"].get("origin_request_id"),
                            message.c.request_state == "waiting",
                        )
                        .values(request_state="pending", wait_reason=None)
                    )
                    if target["source"] == "schedule_wake":
                        from jarvis.actions import finish_schedule_conclusion

                        await finish_schedule_conclusion(
                            connection,
                            action_id=UUID(target["source_message_id"]),
                            conclusion_message_id=conclusion_id,
                            recorded_at=datetime.now(UTC),
                        )
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(
                    product_outcome={
                        "status": "committed",
                        "response_id": str(conclusion_id),
                        "input_outcomes": [
                            item.model_dump(mode="json")
                            for item in final.input_outcomes
                        ],
                    },
                )
            )
        return tuple(completed)


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

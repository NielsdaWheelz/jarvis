"""Durable action state and the llm-tools write-position recorder."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from llm_tools import (
    BudgetState,
    InvocationPosition,
    PositionState,
    RecoveryRequired,
    ReplayPolicy,
    Reservation,
    Settlement,
    ToolEffect,
    ToolId,
    ToolResult,
    canonical_json_bytes,
    raw_input_digest,
)
from llm_tools.execution import ParsedJson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    ColumnElement,
    RowMapping,
    Text,
    and_,
    func,
    literal,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.agent_control import classify_agent_receipt
from jarvis.agent_tools import (
    AGENT_IMPLEMENTATION_REVISION,
    AGENT_INPUT_TYPES,
    AGENT_LOCAL_IDS,
    AGENT_WRITE_IDS,
    AgentActionEvidence,
    AgentCancelWaitResult,
    AgentCloseReceipt,
    AgentError,
    AgentStartInput,
    AgentTargetInput,
    AgentWaitInput,
    AgentWaitOutcome,
    AgentWaitReceipt,
    AgentWaitState,
    AgentWriteResult,
    AgentWriteTarget,
    WireFailure,
    WireStartResult,
    validate_agent_evidence,
    validate_agent_failure,
    validate_agent_success,
)
from jarvis.attachment_tools import AttachmentDeleteResult
from jarvis.db import (
    action,
    attachment,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
)
from jarvis.event_tools import EVENT_MUTATION_IDS, validate_event_result
from jarvis.home_notices import enqueue_notice
from jarvis.messages import (
    append_waking_input,
    causal_component_ids,
    rearm_action_waiters,
)
from jarvis.ownership import Database, lock_conversation
from jarvis.work_tools import WORK_MUTATION_IDS, validate_work_result

ActionStatus = Literal[
    "queued",
    "awaiting_approval",
    "executing",
    "succeeded",
    "failed",
    "uncertain",
    "cancelled",
]
TerminalActionStatus = Literal["succeeded", "failed", "uncertain", "cancelled"]

ACTION_MAX_ATTEMPTS = 2
_MAX_CONTRACT_TEXT = 256
_MAX_RESOLUTION_TEXT_BYTES = 262_144
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RETIRED_AGENT_REVISIONS = (
    "jarvis-agent-control-v1",
    "jarvis-agent-control-v2",
    "jarvis-agent-control-v3",
    "jarvis-agent-control-v4",
    "jarvis-agent-control-v5",
    "jarvis-agent-control-v6",
    "jarvis-agent-control-v7",
    "jarvis-agent-control-v8",
    "jarvis-agent-control-v9",
    "jarvis-agent-control-v10",
)
_RETIRED_CODEX_REVISIONS = ("jarvis-codex-control-v1", "jarvis-codex-control-v2")


class ActionPersistenceDefect(RuntimeError):
    """The durable action ledger is absent, stale, or internally inconsistent."""


class _ExecutionEnvelope(BaseModel):
    """common immutable evidence, without interpreting a retired target."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    tool_contract_revision: Annotated[str, Field(min_length=1, max_length=256)]
    implementation_revision: Annotated[str, Field(min_length=1, max_length=256)]
    policy_revision: Annotated[str, Field(min_length=1, max_length=256)]
    plan_revision: Annotated[str, Field(min_length=1, max_length=256)]
    tool_effect: Literal[ToolEffect.Write]
    replay_policy: Literal[ReplayPolicy.ReDispatchable, ReplayPolicy.BilledOnce]
    input_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    max_attempts: Literal[1, 2]
    claim_id: Annotated[str, Field(min_length=1, max_length=256)]
    through_checkpoint: Annotated[str, Field(min_length=1, max_length=36)]
    model_step_ordinal: Annotated[int, Field(ge=1)]
    input_message_ids: Annotated[tuple[str, ...], Field(min_length=1)]

    @field_validator(
        "tool_contract_revision",
        "implementation_revision",
        "policy_revision",
        "plan_revision",
        "claim_id",
    )
    @classmethod
    def canonical_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("execution-contract text must be canonical")
        if len(value.encode("utf-8")) > _MAX_CONTRACT_TEXT:
            raise ValueError("execution-contract text exceeds its UTF-8 bound")
        return value

    @field_validator("through_checkpoint")
    @classmethod
    def canonical_checkpoint(cls, value: str) -> str:
        return _canonical_uuid(value, "through checkpoint")

    @field_validator("input_message_ids")
    @classmethod
    def canonical_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(_canonical_uuid(value, "message") for value in values)
        if len(canonical) != len(set(canonical)):
            raise ValueError("execution-contract message IDs must be unique")
        return canonical

    @model_validator(mode="after")
    def consistent_lineage(self) -> _ExecutionEnvelope:
        expected_attempts = (
            1 if self.replay_policy is ReplayPolicy.BilledOnce else ACTION_MAX_ATTEMPTS
        )
        if self.max_attempts != expected_attempts:
            raise ValueError("action attempt ceiling disagrees with its replay policy")
        if self.through_checkpoint != self.input_message_ids[-1]:
            raise ValueError("through checkpoint must be the final admitted input")
        return self

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], self.model_dump(mode="json", exclude_unset=True))


class ExecutionContract(_ExecutionEnvelope):
    """current execution authority always has the current target schema."""

    schema_version: Literal["jarvis.action.v2"]
    agent_target: AgentWriteTarget | None = None

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], self.model_dump(mode="json"))


class _ArchivedExecutionContract(_ExecutionEnvelope):
    model_config = ConfigDict(extra="allow", frozen=True, hide_input_in_errors=True)


def _common_execution_envelope(value: object) -> _ExecutionEnvelope:
    if not isinstance(value, dict):
        raise ValueError("stored execution contract must be an object")
    fields = _json_object(cast(dict[str, object], value), "stored execution contract")
    return _ExecutionEnvelope.model_validate(
        {key: fields[key] for key in _ExecutionEnvelope.model_fields if key in fields}
    )


@dataclass(frozen=True, slots=True)
class StoredAction:
    id: UUID
    tool_name: ToolId
    arguments: dict[str, object]
    execution_contract: _ExecutionEnvelope
    status: ActionStatus
    attempts: int
    execute_after: datetime | None
    origin_message_id: UUID
    approval_message_id: UUID | None
    created_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    result: dict[str, object] | None
    supersedes_action_id: UUID | None

    @property
    def payload(self) -> dict[str, object]:
        value = self.arguments["arguments"]
        if not isinstance(value, dict):
            raise ActionPersistenceDefect(
                "action input lacks its closed operation payload"
            )
        return cast(dict[str, object], value)

    @property
    def position(self) -> InvocationPosition:
        return InvocationPosition(str(self.id))

    @property
    def current_execution_contract(self) -> ExecutionContract:
        if not isinstance(self.execution_contract, ExecutionContract):
            raise ActionPersistenceDefect("archived action has no execution authority")
        return self.execution_contract

    @property
    def agent_target(self) -> AgentWriteTarget | None:
        return self.current_execution_contract.agent_target

    @property
    def recovered_external_attempts(self) -> int:
        return _recovery_external_attempts(self)

    @property
    def reconciliation_basis(self) -> dict[str, object] | None:
        return _reconciliation_basis(self.result)


@dataclass(frozen=True, slots=True)
class ResolutionInsert:
    message_id: UUID
    inserted: bool


class ActionStore:
    """Explicit PostgreSQL transactions over the existing action table."""

    def __init__(self, engine: Database) -> None:
        self.engine = engine

    async def insert_automatic(
        self,
        *,
        tool_name: ToolId,
        arguments: Mapping[str, object],
        execution_contract: ExecutionContract,
        origin_message_id: UUID,
        action_id: UUID | None = None,
        created_at: datetime | None = None,
        invocation_id: UUID,
    ) -> StoredAction:
        return await self._insert(
            tool_name,
            arguments,
            execution_contract,
            origin_message_id,
            "queued",
            action_id,
            created_at,
            invocation_id,
        )

    async def insert_awaiting_approval(
        self,
        *,
        tool_name: ToolId,
        arguments: Mapping[str, object],
        execution_contract: ExecutionContract,
        origin_message_id: UUID,
        action_id: UUID | None = None,
        created_at: datetime | None = None,
        invocation_id: UUID,
    ) -> StoredAction:
        return await self._insert(
            tool_name,
            arguments,
            execution_contract,
            origin_message_id,
            "awaiting_approval",
            action_id,
            created_at,
            invocation_id,
        )

    async def _insert(
        self,
        tool_name: ToolId,
        arguments: Mapping[str, object],
        execution_contract: ExecutionContract,
        origin_message_id: UUID,
        status: Literal["queued", "awaiting_approval"],
        action_id: UUID | None,
        created_at: datetime | None,
        invocation_id: UUID,
    ) -> StoredAction:
        identifier = action_id or uuid4()
        timestamp = created_at or datetime.now(UTC)
        _aware(timestamp, "action creation time")
        canonical_arguments = _json_object(dict(arguments), "action arguments")
        _validate_new_action(
            tool_name, canonical_arguments, execution_contract, origin_message_id
        )
        async with self.engine.begin() as connection:
            await _lock_new_action(
                connection,
                origin_message_id,
                execution_contract,
                invocation_id,
                tool_name,
            )
            row = (
                (
                    await connection.execute(
                        postgresql_insert(action)
                        .values(
                            id=identifier,
                            tool_name=str(tool_name),
                            arguments=canonical_arguments,
                            execution_contract=execution_contract.as_json(),
                            status=status,
                            origin_message_id=origin_message_id,
                            created_at=timestamp,
                        )
                        .on_conflict_do_nothing(index_elements=(action.c.id,))
                        .returning(*action.c)
                    )
                )
                .mappings()
                .one_or_none()
            )
            stored = (
                _stored_action(row)
                if row is not None
                else await require_locked_action(connection, identifier)
            )
            if _action_identity(stored) != (
                tool_name,
                canonical_arguments,
                execution_contract,
                origin_message_id,
                None,
                timestamp,
            ):
                raise ActionPersistenceDefect(
                    "action identity was reused for a different invocation"
                )
            if row is not None and status == "awaiting_approval":
                await enqueue_notice(connection, "approval", identifier)
            await _link_native_action(connection, invocation_id, identifier)
            return stored

    async def accepted_actions(
        self, request_id: UUID
    ) -> tuple[tuple[StoredAction, ...], bool]:
        async with self.engine.connect() as connection:
            ids = await causal_component_ids(connection, (request_id,))
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(action.c.origin_message_id.in_(ids))
                        .order_by(action.c.created_at, action.c.id)
                    )
                )
                .mappings()
                .all()
            )
        actions = tuple(map(_stored_action, rows))
        unknown = any(
            stored.status == "uncertain"
            or (
                stored.attempts > 0
                and stored.status == "executing"
                and action_replay_result(stored) is None
            )
            for stored in actions
        )
        return actions, unknown

    async def get(self, action_id: UUID) -> StoredAction | None:
        async with self.engine.connect() as connection:
            return await recorded_action(connection, action_id)

    async def gmail_draft_creation_action(
        self,
        *,
        draft_id: str,
        thread_id: str,
        jarvis_effect_id: str,
    ) -> UUID | None:
        """Resolve the unique successful Jarvis creation behind a send snapshot."""

        if (
            any(
                not value or len(value.encode("utf-8")) > 1_024
                for value in (draft_id, thread_id)
            )
            or _HEX_DIGEST.fullmatch(jarvis_effect_id) is None
        ):
            raise ValueError("Gmail draft creation identity is invalid")
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action.c.id)
                        .where(
                            action.c.tool_name == "gmail.create_draft",
                            action.c.status == "succeeded",
                            action.c.result["type"].as_string() == "Success",
                            action.c.result["value"]["draft_id"].as_string()
                            == draft_id,
                            action.c.result["value"]["thread_id"].as_string()
                            == thread_id,
                            action.c.result["value"]["jarvis_effect_id"].as_string()
                            == jarvis_effect_id,
                        )
                        .order_by(action.c.id)
                        .limit(2)
                    )
                )
                .scalars()
                .all()
            )
        if len(rows) > 1:
            raise ActionPersistenceDefect(
                "Gmail draft maps to multiple creation actions"
            )
        return None if not rows else cast(UUID, rows[0])

    async def recovery_candidates(
        self, *, include_queued: bool = True, limit: int = 100
    ) -> tuple[StoredAction, ...]:
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            or_(
                                action.c.status == "executing",
                                and_(
                                    literal(include_queued),
                                    action.c.status == "queued",
                                    action.c.origin_message_id.in_(
                                        select(message.c.id).where(
                                            message.c.request_state.in_(
                                                ("pending", "waiting")
                                            ),
                                            message.c.processing_parked_at.is_(None),
                                        )
                                    ),
                                ),
                            ),
                            ~(
                                (action.c.tool_name == "agent.wait")
                                & action.c.result.is_not(None)
                                & action.c.result.op("?")("registration_receipt")
                            ),
                        )
                        .order_by(action.c.created_at, action.c.id)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_action, rows))

    async def unreported_terminal(
        self,
        *,
        source_conversation_id: str,
        limit: int = 100,
        retired_only: bool = False,
    ) -> tuple[StoredAction, ...]:
        if type(limit) is not int or limit <= 0:
            raise ValueError("action report limit must be a positive integer")
        eligible = and_(
            action.c.origin_message_id.in_(
                select(message.c.id).where(
                    message.c.source_conversation_id == source_conversation_id,
                )
            ),
            action.c.status.in_(("succeeded", "failed", "uncertain", "cancelled")),
            text(
                "NOT EXISTS (SELECT 1 FROM message AS resolution "
                "WHERE resolution.source = 'action' AND resolution.source_message_id "
                "= action.id::text || ':' || action.status)"
            ),
            text(
                "NOT EXISTS (SELECT 1 FROM native_invocation AS invocation "
                "WHERE invocation.action_id = action.id AND "
                "invocation.reply_receipt->>'type' = 'tool_result_ref')"
            ),
        )
        revision = action.c.execution_contract["implementation_revision"].as_string()
        retired_worker = retired_worker_predicate(action.c.tool_name, revision)
        if retired_only:
            eligible = and_(
                eligible,
                or_(
                    action.c.execution_contract["schema_version"].as_string().is_(None),
                    retired_worker,
                ),
            )
        async with self.engine.connect() as connection:
            delivered = await _delivered_archived_actions(
                connection, source_conversation_id, and_(eligible, retired_worker)
            )
            if delivered:
                eligible = and_(eligible, action.c.id.not_in(delivered))
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(eligible)
                        .order_by(action.c.completed_at, action.c.id)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_action, rows))

    async def stage_gmail_update_basis(
        self,
        *,
        action_id: UUID,
        draft_id: str,
        thread_id: str,
        jarvis_effect_id: str,
        old_content_digest: str,
    ) -> StoredAction:
        basis = _gmail_update_basis(
            {
                "type": "gmail_update_reconciliation_v1",
                "draft_id": draft_id,
                "thread_id": thread_id,
                "jarvis_effect_id": jarvis_effect_id,
                "old_content_digest": old_content_digest,
            }
        )
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if stored.tool_name != ToolId("gmail.update_draft"):
                raise ActionPersistenceDefect(
                    "reconciliation basis belongs only to Gmail draft update"
                )
            if stored.status != "executing":
                raise ActionPersistenceDefect(
                    "reconciliation basis requires an executing action"
                )
            if stored.result is not None:
                existing_basis = _reconciliation_basis(stored.result)
                if existing_basis == basis:
                    return stored
                if stored.result.get("type") == "action_recovery_v1" and (
                    existing_basis is None
                ):
                    recovery = _recovery_state(stored.result)
                    recovery["reconciliation_basis"] = basis
                    return await _update_action(
                        connection,
                        action_id,
                        result=recovery,
                    )
                if existing_basis != basis:
                    raise ActionPersistenceDefect(
                        "Gmail update reconciliation basis changed"
                    )
            return await _update_action(connection, action_id, result=basis)

    async def stage_agent_control(
        self, *, action_id: UUID, evidence: AgentActionEvidence
    ) -> StoredAction:
        """Retain the observed partial result of one non-repeatable agent command."""

        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if (
                stored.status != "executing"
                or stored.execution_contract.replay_policy
                is not ReplayPolicy.BilledOnce
                or stored.attempts != 1
            ):
                raise ActionPersistenceDefect(
                    "Agent evidence requires one active entry"
                )
            staged = evidence.model_dump(mode="json", exclude_none=True)
            _agent_evidence(stored, staged)
            return await _update_action(connection, action_id, result=staged)

    async def stage_external_attempts(
        self,
        *,
        action_id: UUID,
        actual_external_attempts: int,
    ) -> StoredAction:
        """Persist the exact cumulative count before an external mutation attempt."""

        if type(actual_external_attempts) is not int or actual_external_attempts <= 0:
            raise ValueError("external attempt count must be a positive integer")
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if stored.execution_contract.replay_policy is ReplayPolicy.BilledOnce:
                raise ActionPersistenceDefect("BilledOnce work is never readmitted")
            if stored.status != "executing":
                raise ActionPersistenceDefect(
                    "external attempts require an executing action"
                )
            prior = _recovery_external_attempts(stored)
            if actual_external_attempts < prior:
                raise ActionPersistenceDefect("external attempt count moved backwards")
            if actual_external_attempts == prior:
                return stored
            return await _update_action(
                connection,
                action_id,
                result={
                    "type": "action_recovery_v1",
                    "actual_external_attempts": actual_external_attempts,
                    "reconciliation_basis": _reconciliation_basis(stored.result),
                },
            )

    async def requeue_after_proved_absence(
        self,
        action_id: UUID,
        *,
        actual_external_attempts: int,
        max_external_attempts: int,
    ) -> StoredAction:
        """Readmit one reconciled dispatch; the caller owns absence/safety proof."""

        if (
            type(actual_external_attempts) is not int
            or actual_external_attempts < 0
            or type(max_external_attempts) is not int
            or max_external_attempts < 0
        ):
            raise ValueError("external attempt accounting is invalid")
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if stored.execution_contract.replay_policy is ReplayPolicy.BilledOnce:
                raise ActionPersistenceDefect("BilledOnce work is never readmitted")
            if max_external_attempts == 0 and (
                stored.tool_name
                not in (*AGENT_LOCAL_IDS, *WORK_MUTATION_IDS, *EVENT_MUTATION_IDS)
                or action_replay_result(stored) is not None
            ):
                raise ActionPersistenceDefect(
                    "zero-attempt recovery requires an absent local receipt"
                )
            if stored.status != "executing":
                raise ActionPersistenceDefect(
                    "only an executing action can be reconciled for repeat"
                )
            if stored.attempts >= stored.execution_contract.max_attempts:
                raise ActionPersistenceDefect(
                    "action attempt ceiling forbids another executor entry"
                )
            cumulative_attempts = (
                _recovery_external_attempts(stored) + actual_external_attempts
            )
            if cumulative_attempts > max_external_attempts:
                raise ActionPersistenceDefect(
                    "external attempts exceed the frozen tool reservation"
                )
            return await _update_action(
                connection,
                action_id,
                status="queued",
                completed_at=None,
                result={
                    "type": "action_recovery_v1",
                    "actual_external_attempts": cumulative_attempts,
                    "reconciliation_basis": _reconciliation_basis(stored.result),
                },
            )

    async def resolve_reconciliation(
        self,
        *,
        action_id: UUID,
        status: Literal["succeeded", "failed", "uncertain"],
        result: Mapping[str, object],
        resolved_at: datetime | None = None,
    ) -> StoredAction:
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            return await resolve_reconciliation_in_transaction(
                connection,
                stored,
                status=status,
                result=result,
                resolved_at=resolved_at or datetime.now(UTC),
                source_conversation_id=None,
            )

    async def reconcile_agent_receipt(self, action_id: UUID) -> StoredAction:
        """Settle an entered worker command without another executor entry."""

        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if stored.status in {"succeeded", "failed", "uncertain"}:
                return stored
            if (
                stored.status != "executing"
                or stored.execution_contract.replay_policy
                is not ReplayPolicy.BilledOnce
            ):
                raise ActionPersistenceDefect("worker receipt requires entered work")
            status, result = _agent_receipt_resolution(stored)
            return await _update_action(
                connection,
                action_id,
                status=status,
                completed_at=datetime.now(UTC),
                result=result,
            )

    async def cancel_nonexecuting(
        self,
        *,
        action_id: UUID,
        result: Mapping[str, object],
        decided_at: datetime | None = None,
    ) -> StoredAction:
        timestamp = decided_at or datetime.now(UTC)
        _aware(timestamp, "action cancellation time")
        canonical_result = _json_object(dict(result), "action cancellation result")
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if stored.status == "cancelled":
                if stored.result != canonical_result:
                    raise ActionPersistenceDefect("cancelled action result changed")
                return stored
            if stored.status not in {"queued", "awaiting_approval"}:
                raise ActionPersistenceDefect("action is no longer cancellable")
            return await _update_action(
                connection,
                action_id,
                status="cancelled",
                decided_at=timestamp,
                completed_at=timestamp,
                result=canonical_result,
            )

    async def publish_outcomes(
        self,
        *,
        action_ids: tuple[UUID, ...],
        source_conversation_id: str,
    ) -> tuple[ResolutionInsert, ...]:
        """Publish durable outcomes without settling requests."""
        if (
            not action_ids
            or len(action_ids) > 100
            or len(set(action_ids)) != len(action_ids)
        ):
            raise ValueError("action resolution batch must be unique and bounded")
        results: list[ResolutionInsert] = []
        async with self.engine.begin() as connection:
            await lock_conversation(connection, source_conversation_id)
            for identifier in action_ids:
                stored = await require_locked_action(connection, identifier)
                results.append(
                    await _publish_action_outcome(
                        connection, stored, source_conversation_id
                    )
                )
        return tuple(results)

    async def active_agent_waits(self) -> tuple[StoredAction, ...]:
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            action.c.tool_name == "agent.wait",
                            action.c.status == "queued",
                            action.c.result.op("?")("registration_receipt"),
                        )
                        .order_by(action.c.created_at, action.c.id)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_action, rows))

    async def finish_agent_wait(
        self, action_id: UUID, outcome: AgentWaitOutcome, *, source_conversation_id: str
    ) -> bool:
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            state = agent_wait_state(stored)
            if state.wait_outcome is not None:
                return False
            if (
                stored.status != "queued"
                or outcome.target != state.registration_receipt.target
            ):
                raise ActionPersistenceDefect(
                    "wait outcome substituted its registration"
                )
            updated = state.model_copy(update={"wait_outcome": outcome})
            settled = await _update_action(
                connection,
                action_id,
                status="cancelled" if outcome.outcome == "cancelled" else "succeeded",
                completed_at=outcome.recorded_at,
                result=updated.model_dump(mode="json"),
            )
            await _publish_action_outcome(connection, settled, source_conversation_id)
            return True

    async def cancel_agent_wait(
        self,
        action_id: UUID,
        *,
        cancellation_action_id: UUID,
        source_conversation_id: str,
    ) -> bool:
        async with self.engine.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if (
                stored.tool_name != ToolId("agent.wait")
                or stored.result is None
                or "registration_receipt" not in stored.result
            ):
                raise ValueError("wait is not registered")
            state = agent_wait_state(stored)
            cancellation = await require_locked_action(
                connection, cancellation_action_id
            )
            if cancellation.tool_name != ToolId(
                "agent.cancel_wait"
            ) or cancellation.payload.get("action_id") != str(action_id):
                raise ActionPersistenceDefect("cancellation substituted its target")
            if state.wait_outcome is not None:
                cancelled = (
                    state.wait_outcome.cancellation_action_id == cancellation_action_id
                )
                receipt = AgentCancelWaitResult(
                    action_id=action_id,
                    outcome="cancelled" if cancelled else "already_settled",
                )
                await _update_action(
                    connection,
                    cancellation_action_id,
                    status="succeeded",
                    completed_at=datetime.now(UTC),
                    result={
                        "type": "Success",
                        "value": receipt.model_dump(mode="json"),
                    },
                )
                return cancelled
            now = datetime.now(UTC)
            outcome = AgentWaitOutcome(
                target=state.registration_receipt.target,
                outcome="cancelled",
                recorded_at=now,
                cancellation_action_id=cancellation_action_id,
            )
            updated = state.model_copy(update={"wait_outcome": outcome})
            settled = await _update_action(
                connection,
                action_id,
                status="cancelled",
                completed_at=now,
                result=updated.model_dump(mode="json"),
            )
            await _publish_action_outcome(connection, settled, source_conversation_id)
            receipt = AgentCancelWaitResult(action_id=action_id, outcome="cancelled")
            await _update_action(
                connection,
                cancellation_action_id,
                status="succeeded",
                completed_at=now,
                result={"type": "Success", "value": receipt.model_dump(mode="json")},
            )
            return True

    async def publish_agent_wait_events(self, *, source_conversation_id: str) -> int:
        async with self.engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            action.c.tool_name == "agent.wait",
                            action.c.status.in_(("succeeded", "cancelled")),
                            action.c.result.op("?")("registration_receipt"),
                            text(
                                "NOT EXISTS (SELECT 1 FROM message AS event WHERE "
                                "event.source = 'action' AND event.source_message_id "
                                "= action.id::text || ':' || action.status)"
                            ),
                        )
                        .order_by(action.c.completed_at, action.c.id)
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                await _publish_action_outcome(
                    connection, _stored_action(row), source_conversation_id
                )
            return len(rows)


class ActionPositionRecorder:
    """Action-backed PositionRecorder for one declared durable Write."""

    def __init__(
        self,
        *,
        store: ActionStore,
        action_id: UUID,
        implementation_revision: str,
        max_external_attempts: int,
    ) -> None:
        if not implementation_revision:
            raise ValueError("implementation revision must not be empty")
        if type(max_external_attempts) is not int or max_external_attempts < 0:
            raise ValueError("maximum external attempts must be a nonnegative integer")
        self._store = store
        self._action_id = action_id
        self._implementation_revision = implementation_revision
        self._max_external_attempts = max_external_attempts
        self._reservation: Reservation | None = None
        self._reservation_accepted: bool | None = None
        self._settlement: Settlement | None = None

    @property
    def durable(self) -> bool:
        return True

    @property
    def position(self) -> InvocationPosition:
        return InvocationPosition(str(self._action_id))

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
        stored = await self._matching_action(
            position=position,
            tool_id=tool_id,
            tool_contract_revision=tool_contract_revision,
            policy_revision=policy_revision,
            plan_revision=plan_revision,
            input_digest=input_digest,
            replay_policy=replay_policy,
        )
        replay = action_replay_result(stored)
        if replay is None and stored.status == "uncertain":
            async with self._store.engine.connect() as connection:
                replay = await attachment_uncertainty_receipt(connection, stored)
        if replay is not None:
            return PositionState(
                replay,
                False,
                _recovery_external_attempts(stored),
            )
        return PositionState(
            None,
            stored.status in {"executing", "uncertain"},
            _recovery_external_attempts(stored),
        )

    async def reserve(
        self,
        *,
        position: InvocationPosition,
        budgets: BudgetState,
        reservation: Reservation,
    ) -> bool:
        self._require_position(position)
        await self._require_action()
        if (
            reservation.calls != 1
            or reservation.max_attempts != self._max_external_attempts
        ):
            raise ValueError("write reservation differs from the frozen tool grant")
        if self._reservation is not None:
            if self._reservation != reservation:
                raise ValueError("write position reservation changed")
            assert self._reservation_accepted is not None
            if not self._reservation_accepted:
                return False
            return await budgets.reserve(position, reservation)
        accepted = await budgets.reserve(position, reservation)
        self._reservation = reservation
        self._reservation_accepted = accepted
        return accepted

    async def dispatch_started(
        self,
        *,
        position: InvocationPosition,
        replay_policy: ReplayPolicy,
    ) -> PositionState:
        self._require_position(position)
        async with self._store.engine.begin() as connection:
            stored = await require_locked_action(connection, self._action_id)
            self._require_contract(stored)
            if replay_policy is not stored.execution_contract.replay_policy:
                raise ValueError("action replay policy changed")
            replay = action_replay_result(stored)
            if replay is None:
                replay = await attachment_uncertainty_receipt(connection, stored)
            if replay is not None:
                return PositionState(
                    replay,
                    False,
                    _recovery_external_attempts(stored),
                )
            if stored.status in {"executing", "uncertain"}:
                return PositionState(None, True, _recovery_external_attempts(stored))
            if stored.status != "queued":
                raise ValueError("action is not eligible for executor entry")
            origin = (
                (
                    await connection.execute(
                        select(message).where(message.c.id == stored.origin_message_id)
                    )
                )
                .mappings()
                .one()
            )
            paused = await connection.scalar(
                select(message.c.control_kind)
                .where(
                    message.c.source_conversation_id
                    == origin["source_conversation_id"],
                    message.c.control_kind.is_not(None),
                )
                .order_by(message.c.control_sequence.desc())
                .limit(1)
            )
            if (
                origin["role"] not in {"owner", "host"}
                or origin["control_kind"] is not None
                or origin["request_state"] not in {"pending", "waiting"}
                or origin["processing_parked_at"] is not None
                or paused == "pause"
            ):
                raise RecoveryRequired(
                    "originating request no longer authorizes action entry"
                )
            if stored.attempts >= stored.execution_contract.max_attempts:
                raise ValueError("action attempt ceiling is exhausted")
            await _update_action(
                connection,
                stored.id,
                status="executing",
                attempts=stored.attempts + 1,
            )
            return PositionState(
                None,
                False,
                _recovery_external_attempts(stored),
            )

    async def dispatch_abandoned(
        self,
        *,
        position: InvocationPosition,
        replay_policy: ReplayPolicy,
        actual_attempts: int,
        lease_recovered: bool,
    ) -> None:
        self._require_position(position)
        if replay_policy is not ReplayPolicy.ReDispatchable:
            raise ValueError("only ReDispatchable actions can be readmitted")
        if not lease_recovered:
            raise ValueError("action requires fenced reconciliation evidence")
        if type(actual_attempts) is not int or actual_attempts < 0:
            raise ValueError("abandoned action attempts must be non-negative")
        await self._store.requeue_after_proved_absence(
            self._action_id,
            actual_external_attempts=actual_attempts,
            max_external_attempts=self._max_external_attempts,
        )

    async def uncertain(self, *, position: InvocationPosition) -> None:
        self._require_position(position)
        stored = await self._require_action()
        if stored.execution_contract.replay_policy is not ReplayPolicy.BilledOnce:
            raise ValueError(
                "ReDispatchable writes require tool-specific reconciliation"
            )
        if stored.status == "uncertain":
            return
        await self._store.reconcile_agent_receipt(stored.id)

    async def terminalize_and_settle(
        self,
        *,
        position: InvocationPosition,
        budgets: BudgetState,
        result: ToolResult,
        settlement: Settlement,
    ) -> ToolResult:
        self._require_position(position)
        canonical_result = _tool_result(result)
        if self._reservation is None or not self._reservation_accepted:
            zero_attempts = Settlement(
                actual_attempts=0,
                actual_output_bytes=len(canonical_json_bytes(canonical_result)),
            )
            if settlement != zero_attempts:
                raise ValueError(
                    "unreserved write settlement is not a zero-attempt result"
                )
        else:
            if (
                settlement.actual_attempts > self._reservation.max_attempts
                or settlement.actual_output_bytes > self._reservation.max_output_bytes
            ):
                raise ValueError("write settlement exceeds its reservation")
        if self._settlement is not None and self._settlement != settlement:
            raise ValueError("write position settlement changed")

        async with self._store.engine.begin() as connection:
            stored = await require_locked_action(connection, self._action_id)
            self._require_contract(stored)
            prior_external_attempts = _recovery_external_attempts(stored)
            if settlement.actual_attempts < prior_external_attempts:
                raise ValueError("write settlement lost recovered attempt accounting")
            replay = action_replay_result(stored)
            if replay is not None:
                if replay != canonical_result:
                    raise ValueError("terminal write result changed")
                if self._reservation_accepted:
                    await budgets.settle(position, settlement)
                self._settlement = settlement
                return replay
            if stored.status == "uncertain":
                receipt = await attachment_uncertainty_receipt(connection, stored)
                if receipt is None or receipt != canonical_result:
                    raise ValueError("uncertain action requires reconciliation")
                if self._reservation_accepted:
                    await budgets.settle(position, settlement)
                self._settlement = settlement
                return receipt
            if stored.status not in {"queued", "executing"}:
                raise ValueError("action cannot accept a terminal tool result")
            if self._reservation_accepted:
                await budgets.settle(position, settlement)

            ambiguous_boundary_failure = (
                stored.execution_contract.replay_policy is ReplayPolicy.BilledOnce
                and stored.attempts > 0
                and canonical_result["type"] == "Failure"
                and canonical_result["error"].get("type")
                in {"BudgetExceeded", "DeadlineExceeded"}
            )
            if ambiguous_boundary_failure:
                status, receipt_result = _agent_receipt_resolution(stored)
                await _update_action(
                    connection,
                    stored.id,
                    status=status,
                    completed_at=datetime.now(UTC),
                    result=receipt_result,
                )
            elif (
                stored.tool_name == ToolId("agent.wait")
                and canonical_result["type"] == "Success"
            ):
                receipt = AgentWaitReceipt.model_validate(canonical_result["value"])
                if (
                    receipt.action_id != stored.id
                    or receipt.arguments_digest
                    != stored.execution_contract.input_digest
                ):
                    raise ValueError("wait registration identity changed")
                request = AgentWaitInput.model_validate(stored.payload)
                if (
                    receipt.target != request.target
                    or receipt.state != request.state
                    or (receipt.deadline - receipt.recorded_at).total_seconds()
                    != request.timeout_seconds
                ):
                    raise ValueError("wait registration differs from admitted request")
                await _update_action(
                    connection,
                    stored.id,
                    status="queued",
                    completed_at=None,
                    result=AgentWaitState(registration_receipt=receipt).model_dump(
                        mode="json"
                    ),
                )
            else:
                await _update_action(
                    connection,
                    stored.id,
                    status=(
                        "succeeded"
                        if canonical_result["type"] == "Success"
                        else "failed"
                    ),
                    completed_at=datetime.now(UTC),
                    result={"tool_result": canonical_result, "control": stored.result}
                    if stored.result is not None
                    and stored.result.get("type") == "agent_control_v5"
                    else canonical_result,
                )
            self._settlement = settlement
        if ambiguous_boundary_failure:
            raise RecoveryRequired("entered worker control requires durable reporting")
        return canonical_result

    async def _matching_action(
        self,
        *,
        position: InvocationPosition,
        tool_id: ToolId,
        tool_contract_revision: str,
        policy_revision: str,
        plan_revision: str,
        input_digest: str,
        replay_policy: ReplayPolicy,
    ) -> StoredAction:
        self._require_position(position)
        stored = await self._require_action()
        contract = stored.execution_contract
        if (
            stored.tool_name != tool_id
            or contract.tool_contract_revision != tool_contract_revision
            or contract.implementation_revision != self._implementation_revision
            or contract.policy_revision != policy_revision
            or contract.plan_revision != plan_revision
            or contract.input_digest != input_digest
            or contract.replay_policy is not replay_policy
            or contract.tool_effect is not ToolEffect.Write
        ):
            raise ValueError("occupied action invocation changed")
        return stored

    async def _require_action(self) -> StoredAction:
        stored = await self._store.get(self._action_id)
        if stored is None:
            raise ValueError("occupied action is missing")
        self._require_contract(stored)
        return stored

    def _require_contract(self, stored: StoredAction) -> None:
        if (
            stored.execution_contract.implementation_revision
            != self._implementation_revision
        ):
            raise ValueError("occupied action implementation changed")

    def _require_position(self, position: InvocationPosition) -> None:
        if position != self.position:
            raise ValueError("action ID must be the exact invocation position")


async def _locked_action(
    connection: AsyncConnection, action_id: UUID
) -> StoredAction | None:
    origin = (
        await connection.execute(
            select(
                message.c.source_conversation_id,
                action.c.origin_message_id,
                action.c.execution_contract,
            )
            .join(action, message.c.id == action.c.origin_message_id)
            .where(action.c.id == action_id)
        )
    ).one_or_none()
    if origin is None:
        return None
    await lock_conversation(connection, origin.source_conversation_id)
    contract = _common_execution_envelope(origin.execution_contract)
    await connection.execute(
        select(message.c.id)
        .where(
            or_(
                message.c.id.in_(tuple(map(UUID, contract.input_message_ids))),
                message.c.trace["waiting_action_ids"].contains([str(action_id)]),
            )
        )
        .order_by(message.c.id)
        .with_for_update()
    )
    invocations = (
        await connection.execute(
            select(native_invocation.c.id, native_invocation.c.attempt_id)
            .where(native_invocation.c.action_id == action_id)
            .order_by(native_invocation.c.id)
        )
    ).all()
    if invocations:
        await connection.execute(
            select(native_attempt.c.id)
            .where(native_attempt.c.id.in_({item.attempt_id for item in invocations}))
            .order_by(native_attempt.c.id)
            .with_for_update()
        )
        await connection.execute(
            select(native_invocation.c.id)
            .where(native_invocation.c.id.in_(tuple(item.id for item in invocations)))
            .order_by(native_invocation.c.id)
            .with_for_update()
        )
    row = (
        (
            await connection.execute(
                select(action).where(action.c.id == action_id).with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _stored_action(row)


async def _lock_new_action(
    connection: AsyncConnection,
    origin_id: UUID,
    contract: ExecutionContract,
    invocation_id: UUID,
    tool_name: ToolId,
) -> None:
    scope = await connection.scalar(
        select(message.c.source_conversation_id).where(message.c.id == origin_id)
    )
    if scope is None:
        raise ActionPersistenceDefect("action origin is missing")
    await lock_conversation(connection, scope)
    inputs = (
        (
            await connection.execute(
                select(message)
                .where(message.c.id.in_(tuple(map(UUID, contract.input_message_ids))))
                .order_by(message.c.id)
                .with_for_update()
            )
        )
        .mappings()
        .all()
    )
    origin = next((row for row in inputs if row["id"] == origin_id), None)
    if (
        origin is None
        or origin["role"] not in {"owner", "host"}
        or origin["request_state"] not in {"pending", "waiting"}
        or origin["processing_parked_at"] is not None
        or origin["control_kind"] is not None
    ):
        raise ActionPersistenceDefect(
            "action origin is no longer a live waking request"
        )
    if len(inputs) != len(contract.input_message_ids) or any(
        row["source_conversation_id"] != scope for row in inputs
    ):
        raise ActionPersistenceDefect("action input scope changed")
    paused = await connection.scalar(
        select(message.c.control_kind)
        .where(
            message.c.source_conversation_id == scope,
            message.c.control_kind.is_not(None),
        )
        .order_by(message.c.control_sequence.desc())
        .limit(1)
    )
    if paused == "pause":
        raise ActionPersistenceDefect("paused conversation cannot admit actions")
    component = await causal_component_ids(connection, (origin_id,))
    unknown = await connection.scalar(
        select(action.c.id)
        .where(
            action.c.origin_message_id.in_(component),
            or_(
                action.c.status == "uncertain",
                and_(
                    action.c.status == "executing",
                    action.c.attempts > 0,
                    ~(
                        (action.c.tool_name == "agent.wait")
                        & action.c.result.is_not(None)
                        & action.c.result.op("?")("registration_receipt")
                    ),
                ),
            ),
        )
        .limit(1)
    )
    if unknown is not None and tool_name not in (
        *WORK_MUTATION_IDS,
        *EVENT_MUTATION_IDS,
    ):
        raise ActionPersistenceDefect("causal component has an unknown effect")
    attempt_id = await connection.scalar(
        select(native_invocation.c.attempt_id).where(
            native_invocation.c.id == invocation_id
        )
    )
    attempt = (
        (
            await connection.execute(
                select(
                    native_attempt.c.fenced_at,
                    native_attempt.c.terminal_at,
                    native_attempt.c.product_outcome.is_not(None).label("settled"),
                )
                .where(native_attempt.c.id == attempt_id)
                .with_for_update()
            )
        )
        .mappings()
        .one()
    )
    invocation = (
        (
            await connection.execute(
                select(native_invocation)
                .where(native_invocation.c.id == invocation_id)
                .with_for_update()
            )
        )
        .mappings()
        .one()
    )
    if (
        attempt["fenced_at"] is not None
        or attempt["terminal_at"] is not None
        or attempt["settled"]
        or invocation["request_message_id"] != origin_id
        or contract.claim_id != str(attempt_id)
        or contract.model_step_ordinal != invocation["ordinal"]
        or invocation["validation"] != "accepted"
        or tuple(invocation["proposal"]["input_ids"]) != contract.input_message_ids
    ):
        raise ActionPersistenceDefect(
            "native callback lost action acceptance authority"
        )
    delivered = await connection.scalar(
        select(native_input_delivery.c.message_id).where(
            native_input_delivery.c.attempt_id == attempt_id,
            native_input_delivery.c.message_id == origin_id,
            proven_native_delivery,
        )
    )
    if delivered is None:
        raise ActionPersistenceDefect(
            "action origin was not delivered to its native attempt"
        )


async def _link_native_action(
    connection: AsyncConnection, invocation_id: UUID, action_id: UUID
) -> None:
    previous = await connection.scalar(
        select(native_invocation.c.action_id).where(
            native_invocation.c.id == invocation_id
        )
    )
    if previous is not None and previous != action_id:
        raise ActionPersistenceDefect("native invocation action reference changed")
    await connection.execute(
        update(native_invocation)
        .where(native_invocation.c.id == invocation_id)
        .values(action_id=action_id)
    )


async def require_locked_action(
    connection: AsyncConnection, action_id: UUID
) -> StoredAction:
    stored = await _locked_action(connection, action_id)
    if stored is None:
        raise ActionPersistenceDefect("action does not exist")
    return stored


async def attachment_manual_cleanup_reported(
    connection: AsyncConnection, attachment_id: UUID, action_id: UUID | None
) -> bool:
    """Bind an operator's factual cleanup to the affected original/action."""
    affected = message.c.trace["affected_action_id"].as_string()
    reported = await connection.scalar(
        select(message.c.id)
        .where(
            message.c.source == "attachment",
            message.c.trace["attachment_id"].as_string() == str(attachment_id),
            affected.is_(None) if action_id is None else affected == str(action_id),
            message.c.trace["after_manual_cleanup"].as_boolean().is_(True),
        )
        .limit(1)
    )
    return reported is not None


async def attachment_uncertainty_receipt(
    connection: AsyncConnection, stored: StoredAction
) -> ToolResult | None:
    """Recover a typed callback failure without changing its action uncertainty."""
    if stored.status != "uncertain" or stored.tool_name not in {
        ToolId("attachment.retain"),
        ToolId("attachment.delete"),
    }:
        return None
    retaining = stored.tool_name == ToolId("attachment.retain")
    row = (
        (
            await connection.execute(
                select(attachment).where(
                    (
                        attachment.c.capture_action_id
                        if retaining
                        else attachment.c.delete_action_id
                    )
                    == stored.id
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is not None and row["state"] == ("ready" if retaining else "deleted"):
        if await attachment_manual_cleanup_reported(connection, row["id"], stored.id):
            # Factual cleanup is no receipt for the original action. The
            # uncertain position remains suspended, with no executor entry.
            return None
    if (
        row is None
        or row["state"] != ("pending" if retaining else "deleting")
        or (
            row["error"]
            not in (
                {"CaptureUnresolved", "StorageConflict"}
                if retaining
                else {"StorageConflict", "DeleteUnresolved"}
            )
        )
    ):
        raise ActionPersistenceDefect("attachment uncertainty lost its exact evidence")
    if retaining:
        requested = stored.payload["source"]
        if not isinstance(requested, dict) or any(
            row["source"].get(key) != value
            for key, value in cast(dict[str, object], requested).items()
        ):
            raise ActionPersistenceDefect("attachment capture receipt changed source")
    elif stored.payload["id"] != str(row["id"]):
        raise ActionPersistenceDefect("attachment deletion receipt changed identity")
    return {"type": "Failure", "error": {"type": row["error"], "id": str(row["id"])}}


async def resolve_reconciliation_in_transaction(
    connection: AsyncConnection,
    stored: StoredAction,
    *,
    status: Literal["succeeded", "failed", "uncertain"],
    result: Mapping[str, object],
    resolved_at: datetime,
    source_conversation_id: str | None,
) -> StoredAction:
    """Resolve current evidence with caller-owned state and optional publication."""
    _aware(resolved_at, "action reconciliation time")
    canonical = _json_object(dict(result), "action result")
    if status == "uncertain":
        canonical = _uncertainty_result(stored, canonical)
    else:
        tool_result = _tool_result(canonical)
        if (status == "succeeded") != (tool_result["type"] == "Success"):
            raise ValueError("action status disagrees with its tool result")
    if stored.status in {"succeeded", "failed"} or (
        stored.status == "uncertain" and status == "uncertain"
    ):
        if stored.status != status or stored.result != canonical:
            raise ActionPersistenceDefect("terminal action resolution changed")
        settled = stored
    else:
        if stored.status == "queued":
            if stored.tool_name != ToolId("attachment.delete") or stored.attempts < 1:
                raise ActionPersistenceDefect("queued work has no entered deletion")
            original = (
                (
                    await connection.execute(
                        select(attachment)
                        .where(
                            attachment.c.id == UUID(str(stored.payload["id"])),
                            attachment.c.delete_action_id == stored.id,
                        )
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                original is None
                or original["state"] not in {"deleting", "deleted"}
                or original["put_entered_at"] is None
                or original["stored_at"] is None
            ):
                raise ActionPersistenceDefect("queued deletion lost its exact original")
            if stored.recovered_external_attempts == 0:
                if original["state"] == "deleting" and original["error"] in {
                    "StorageConflict",
                    "Unavailable",
                }:
                    expected_error = original["error"]
                elif original[
                    "state"
                ] == "deleted" and await attachment_manual_cleanup_reported(
                    connection, original["id"], stored.id
                ):
                    expected_error = "Deleted"
                else:
                    raise ActionPersistenceDefect(
                        "unentered deletion has no proved failure"
                    )
                if status != "failed" or canonical != {
                    "type": "Failure",
                    "error": {"type": expected_error, "id": str(original["id"])},
                }:
                    raise ActionPersistenceDefect("unentered deletion failure changed")
            elif status == "succeeded":
                if original["state"] != "deleted" or canonical != {
                    "type": "Success",
                    "value": AttachmentDeleteResult(
                        id=str(original["id"]),
                        deleted_at=original["deleted_at"],
                        scope="original_and_cache",
                    ).model_dump(mode="json"),
                }:
                    raise ActionPersistenceDefect(
                        "queued deletion has no proved receipt"
                    )
            elif status == "failed":
                if (
                    original["state"] != "deleting"
                    or original["error"] != "CacheCleanupFailed"
                    or canonical
                    != {
                        "type": "Failure",
                        "error": {
                            "type": "CacheCleanupFailed",
                            "id": str(original["id"]),
                        },
                    }
                ):
                    raise ActionPersistenceDefect(
                        "queued deletion has no proved local cleanup failure"
                    )
            elif status != "uncertain" or canonical["evidence_code"] not in {
                "StorageConflict",
                "DeleteUnresolved",
            }:
                raise ActionPersistenceDefect("queued deletion uncertainty is invalid")
        elif stored.status not in {"executing", "uncertain"}:
            raise ActionPersistenceDefect(
                "only executing or uncertain work can be reconciled"
            )
        settled = await _update_action(
            connection,
            stored.id,
            status=status,
            completed_at=resolved_at,
            result=canonical,
        )
    if source_conversation_id is not None:
        await _publish_action_outcome(connection, settled, source_conversation_id)
    return settled


async def complete_local_action(
    connection: AsyncConnection,
    stored: StoredAction,
    result: ToolResult,
    completed_at: datetime,
) -> None:
    """Commit local state and its exact terminal tool receipt in one transaction."""
    if stored.status != "executing" or stored.attempts < 1:
        raise ActionPersistenceDefect("local mutation has no executor entry")
    canonical = _tool_result(dict(result))
    await _update_action(
        connection,
        stored.id,
        status="succeeded" if canonical["type"] == "Success" else "failed",
        completed_at=completed_at,
        result=canonical,
    )


async def _update_action(
    connection: AsyncConnection,
    action_id: UUID,
    **values: object,
) -> StoredAction:
    row = (
        (
            await connection.execute(
                update(action)
                .where(action.c.id == action_id)
                .values(**values)
                .returning(*action.c)
            )
        )
        .mappings()
        .one()
    )
    return _stored_action(row)


def _stored_action(row: RowMapping) -> StoredAction:
    try:
        status = cast(ActionStatus, row["status"])
        if status not in {
            "queued",
            "awaiting_approval",
            "executing",
            "succeeded",
            "failed",
            "uncertain",
            "cancelled",
        }:
            raise ValueError("action status is invalid")
        envelope = _common_execution_envelope(row["execution_contract"])
        if row["execution_contract"].get(
            "schema_version"
        ) is None or retired_worker_revision(
            str(row["tool_name"]), envelope.implementation_revision
        ):
            if status not in {"succeeded", "failed", "uncertain", "cancelled"}:
                raise ValueError("retired action must drain before activation")
            contract = _ArchivedExecutionContract.model_validate(
                row["execution_contract"]
            )
        else:
            contract = ExecutionContract.model_validate(row["execution_contract"])
        attempts = cast(int, row["attempts"])
        if type(attempts) is not int or not 0 <= attempts <= contract.max_attempts:
            raise ValueError("action attempts violate the execution contract")
        result = cast(dict[str, object] | None, row["result"])
        if result is not None:
            result = _json_object(result, "stored action result")
        stored = StoredAction(
            id=cast(UUID, row["id"]),
            tool_name=ToolId(cast(str, row["tool_name"])),
            arguments=_json_object(
                cast(dict[str, object], row["arguments"]), "stored action arguments"
            ),
            execution_contract=contract,
            status=status,
            attempts=attempts,
            execute_after=cast(datetime | None, row["execute_after"]),
            origin_message_id=cast(UUID, row["origin_message_id"]),
            approval_message_id=cast(UUID | None, row["approval_message_id"]),
            created_at=cast(datetime, row["created_at"]),
            decided_at=cast(datetime | None, row["decided_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
            result=result,
            supersedes_action_id=row["supersedes_action_id"],
        )
        _validate_stored_action(stored)
        return stored
    except (TypeError, ValueError) as exc:
        raise ActionPersistenceDefect("stored action is invalid") from exc


def _validate_new_action(
    tool_name: ToolId,
    arguments: dict[str, object],
    contract: _ExecutionEnvelope,
    origin_message_id: UUID,
    *,
    historical: bool = False,
) -> None:
    ToolId(str(tool_name))
    if not historical and not isinstance(contract, ExecutionContract):
        raise ValueError("archived action has no execution authority")
    if contract.tool_effect is not ToolEffect.Write:
        raise ValueError("actions require the Write effect")
    if not historical and (
        tool_name in AGENT_WRITE_IDS and tool_name not in AGENT_LOCAL_IDS
    ) != (contract.replay_policy is ReplayPolicy.BilledOnce):
        raise ValueError("write action replay policy differs from its tool family")
    if raw_input_digest(ParsedJson(arguments)) != contract.input_digest:
        raise ValueError("execution contract has a different input digest")
    if str(origin_message_id) not in contract.input_message_ids:
        raise ValueError("origin request must be delivered in this attempt")
    if not historical and arguments.get("request_ref") != str(origin_message_id):
        raise ValueError("origin request differs from the exact ActionRequest")


def _validate_stored_action(stored: StoredAction) -> None:
    _validate_new_action(
        stored.tool_name,
        stored.arguments,
        stored.execution_contract,
        stored.origin_message_id,
        historical=True,
    )
    _aware(stored.created_at, "stored action creation time")
    if stored.execute_after is not None:
        _aware(stored.execute_after, "stored action execute_after")
    terminal = stored.status in {"succeeded", "failed", "uncertain", "cancelled"}
    if terminal != (stored.completed_at is not None):
        raise ValueError("stored action terminal timestamp is inconsistent")
    if stored.decided_at is not None:
        _aware(stored.decided_at, "stored action decision time")
    if stored.completed_at is not None:
        _aware(stored.completed_at, "stored action completion time")
    if stored.status == "awaiting_approval" and (
        stored.attempts != 0
        or stored.decided_at is not None
        or stored.result is not None
    ):
        raise ValueError("pending approval has invalid execution state")
    if (
        stored.approval_message_id is not None
        and stored.status != "awaiting_approval"
        and stored.decided_at is None
    ):
        raise ValueError("decided approval action is missing its decision time")
    if stored.status in {"succeeded", "failed", "uncertain"} and stored.result is None:
        raise ValueError("resolved action is missing its result")
    if isinstance(stored.execution_contract, _ArchivedExecutionContract):
        return
    worker = str(stored.tool_name).startswith(("agent.", "codex."))
    if worker and (
        stored.tool_name not in AGENT_WRITE_IDS
        or stored.execution_contract.implementation_revision
        != AGENT_IMPLEMENTATION_REVISION
        or set(stored.arguments) != {"request_ref", "existing_action_ref", "arguments"}
    ):
        raise ValueError("current worker contract is invalid")
    if set(stored.arguments) != {"request_ref", "existing_action_ref", "arguments"}:
        if not terminal:
            raise ValueError("unfinished historical action requires stopped cutover")
        # Original bytes remain audit facts; no current tool interprets them.
        return
    if (
        stored.tool_name in AGENT_WRITE_IDS and stored.tool_name not in AGENT_LOCAL_IDS
    ) != (stored.execution_contract.replay_policy is ReplayPolicy.BilledOnce):
        raise ValueError("write action replay policy differs from its tool family")
    if str(stored.tool_name).startswith("agent."):
        if (
            stored.tool_name not in AGENT_WRITE_IDS
            or stored.execution_contract.implementation_revision
            != AGENT_IMPLEMENTATION_REVISION
            or stored.execution_contract.replay_policy
            is not (
                ReplayPolicy.ReDispatchable
                if stored.tool_name in AGENT_LOCAL_IDS
                else ReplayPolicy.BilledOnce
            )
        ):
            raise ValueError("current worker contract is invalid")
        AGENT_INPUT_TYPES[str(stored.tool_name).removeprefix("agent.")].model_validate(
            stored.payload
        )
        addressed = stored.payload.get("target")
        captured = stored.agent_target
        if addressed is not None:
            requested = AgentTargetInput.model_validate({"target": addressed})
            if captured is None or captured.target != requested.target:
                raise ValueError("addressed action lacks matching immutable capture")
        elif captured is not None:
            raise ValueError("unaddressed action has captured worker authority")
    if stored.result is not None:
        if (
            stored.tool_name == ToolId("agent.wait")
            and "registration_receipt" in stored.result
        ):
            agent_wait_state(stored)
        elif stored.status == "uncertain":
            _uncertainty_result(stored, stored.result)
        elif stored.status in {"succeeded", "failed"}:
            result = _stored_tool_result(stored)
            if "control" in stored.result:
                _agent_evidence(stored, stored.result["control"])
            if (stored.status == "succeeded") != (result["type"] == "Success"):
                raise ValueError("stored action status disagrees with its result")
            if stored.tool_name in AGENT_WRITE_IDS:
                verb = str(stored.tool_name).removeprefix("agent.")
                if stored.status == "succeeded":
                    validate_agent_success(
                        verb, stored.payload, result["value"], require_confirmed=True
                    )
                elif isinstance(result["error"], dict):
                    error = cast(dict[str, object], result["error"])
                    if error.get("type") == "AgentFailure":
                        validate_agent_failure(verb, error)
        elif stored.result.get("type") == "gmail_update_reconciliation_v1":
            _gmail_update_basis(stored.result)
        elif stored.result.get("type") == "action_recovery_v1":
            _recovery_state(stored.result)
        elif stored.result.get("type") in {
            "agent_control_v5",
        }:
            _agent_evidence(stored, stored.result)


def _action_identity(
    stored: StoredAction,
) -> tuple[
    ToolId,
    dict[str, object],
    _ExecutionEnvelope,
    UUID,
    datetime | None,
    datetime,
]:
    return (
        stored.tool_name,
        stored.arguments,
        stored.execution_contract,
        stored.origin_message_id,
        stored.execute_after,
        stored.created_at,
    )


def _stored_tool_result(stored: StoredAction) -> ToolResult:
    if stored.result is None:
        raise ActionPersistenceDefect("action lacks tool result")
    if "tool_result" not in stored.result:
        return _tool_result(stored.result)
    if set(stored.result) != {"tool_result", "control"}:
        raise ActionPersistenceDefect("invalid private worker receipt")
    _agent_evidence(stored, stored.result["control"])
    value = stored.result["tool_result"]
    if not isinstance(value, dict):
        raise ActionPersistenceDefect("invalid private worker receipt")
    return _tool_result(cast(dict[str, object], value))


async def recorded_action(
    connection: AsyncConnection, action_id: UUID
) -> StoredAction | None:
    """Read and validate action evidence within the caller's transaction."""
    row = (
        (await connection.execute(select(action).where(action.c.id == action_id)))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _stored_action(row)


async def recorded_action_result(
    connection: AsyncConnection, action_id: UUID
) -> ToolResult | None:
    """Project the original tool result within the caller's transaction."""
    stored = await recorded_action(connection, action_id)
    if stored is None or isinstance(
        stored.execution_contract, _ArchivedExecutionContract
    ):
        return None
    return action_replay_result(stored)


def action_replay_result(stored: StoredAction) -> ToolResult | None:
    """Return the immutable callback result, independently of later host outcomes."""
    if isinstance(stored.execution_contract, _ArchivedExecutionContract):
        raise ActionPersistenceDefect("archived actions cannot replay")
    if (
        stored.tool_name == ToolId("agent.wait")
        and stored.result is not None
        and "registration_receipt" in stored.result
    ):
        return {
            "type": "Success",
            "value": agent_wait_state(stored).registration_receipt.model_dump(
                mode="json"
            ),
        }
    if stored.status in {"succeeded", "failed"} and stored.result is not None:
        return _stored_tool_result(stored)
    return None


def _recovery_external_attempts(stored: StoredAction) -> int:
    if stored.result is None or stored.result.get("type") != "action_recovery_v1":
        return 0
    recovery = _recovery_state(stored.result)
    return cast(int, recovery["actual_external_attempts"])


def _reconciliation_basis(
    result: dict[str, object] | None,
) -> dict[str, object] | None:
    if result is None:
        return None
    if result.get("type") == "gmail_update_reconciliation_v1":
        return _gmail_update_basis(result)
    if result.get("type") == "action_recovery_v1":
        recovery = _recovery_state(result)
        basis = recovery["reconciliation_basis"]
        return None if basis is None else cast(dict[str, object], basis)
    return None


def _recovery_state(result: dict[str, object]) -> dict[str, object]:
    canonical = _json_object(result, "action recovery state")
    if (
        set(canonical)
        != {
            "type",
            "actual_external_attempts",
            "reconciliation_basis",
        }
        or canonical.get("type") != "action_recovery_v1"
    ):
        raise ActionPersistenceDefect("action recovery state is invalid")
    attempts = canonical["actual_external_attempts"]
    if type(attempts) is not int or attempts < 0:
        raise ActionPersistenceDefect("action recovery attempts are invalid")
    basis = canonical["reconciliation_basis"]
    if basis is not None:
        if not isinstance(basis, dict):
            raise ActionPersistenceDefect("action reconciliation basis is invalid")
        canonical["reconciliation_basis"] = _gmail_update_basis(
            cast(dict[str, object], basis)
        )
    return canonical


def _uncertainty_result(
    stored: StoredAction, result: dict[str, object]
) -> dict[str, object]:
    canonical = _json_object(result, "action uncertainty result")
    keys = {"type", "evidence_code", "recorded_at"}
    if canonical.get("type") == "agent_uncertainty_v1":
        keys.add("control")
        _agent_evidence(stored, canonical.get("control"))
    if set(canonical) != keys or canonical.get("type") not in {
        "action_uncertainty_v1",
        "agent_uncertainty_v1",
    }:
        raise ValueError("action uncertainty result is invalid")
    evidence = canonical["evidence_code"]
    if (
        not isinstance(evidence, str)
        or not evidence
        or evidence != evidence.strip()
        or len(evidence.encode("utf-8")) > 256
    ):
        raise ValueError("action uncertainty evidence is invalid")
    canonical["recorded_at"] = _iso_datetime(
        canonical["recorded_at"], "action uncertainty time"
    ).isoformat()
    return canonical


def agent_uncertainty_result(stored: StoredAction) -> dict[str, object]:
    """An entered agent command has no replay-safe absence proof."""
    if stored.execution_contract.replay_policy is not ReplayPolicy.BilledOnce:
        raise ValueError("agent uncertainty requires a BilledOnce action")
    if stored.status == "uncertain" and stored.result is not None:
        return _uncertainty_result(stored, stored.result)
    if stored.result is None:
        control: dict[str, object] = AgentActionEvidence().model_dump(mode="json")
    else:
        _agent_evidence(stored, stored.result)
        control = stored.result
    return {
        "type": "agent_uncertainty_v1",
        "evidence_code": "agent-control-outcome-unconfirmed-no-repeat",
        "recorded_at": datetime.now(UTC).isoformat(),
        "control": control,
    }


def _agent_receipt_resolution(
    stored: StoredAction,
) -> tuple[Literal["succeeded", "failed", "uncertain"], dict[str, object]]:
    operation = str(stored.tool_name).removeprefix("agent.")
    value = AGENT_INPUT_TYPES[operation].model_validate(stored.payload)
    if not isinstance(value, AgentStartInput | AgentTargetInput):
        raise ActionPersistenceDefect("worker receipt has foreign input")
    control = (
        AgentActionEvidence()
        if stored.result is None
        else validate_agent_evidence(operation, stored.result)
    )
    result = classify_agent_receipt(operation, value, control.observed)
    if result is None:
        return "uncertain", agent_uncertainty_result(stored)
    failed = isinstance(result, AgentError)
    return (
        "failed" if failed else "succeeded",
        {
            "tool_result": {
                "type": "Failure" if failed else "Success",
                "error" if failed else "value": result.model_dump(mode="json"),
            },
            "control": control.model_dump(mode="json", exclude_none=True),
        },
    )


async def _delivered_archived_actions(
    connection: AsyncConnection,
    source_conversation_id: str,
    candidates: ColumnElement[bool],
) -> tuple[UUID, ...]:
    # Archived inline results predate native_invocation. Their canonical
    # conclusion identity binds the original claim and exact delivered
    # text; input completion alone does not prove receipt delivery. This
    # checks host settlement metadata, never retired worker payloads.
    origin = message.alias("origin")
    conclusion = message.alias("conclusion")
    inline = (
        await connection.execute(
            select(
                action,
                origin.c.trace["settlement"]["run_id"].as_string().label("run_id"),
                conclusion.c.id.label("conclusion_id"),
                func.encode(
                    func.sha256(func.convert_to(conclusion.c.text, "UTF8")),
                    "hex",
                ).label("conclusion_digest"),
            )
            .select_from(
                action.join(origin, origin.c.id == action.c.origin_message_id).join(
                    conclusion,
                    conclusion.c.id.cast(Text)
                    == origin.c.trace["settlement"][
                        "conclusion_message_id"
                    ].as_string(),
                )
            )
            .where(
                candidates,
                action.c.status.in_(("succeeded", "failed")),
                action.c.approval_message_id.is_(None),
                origin.c.trace["settlement"]["conclusion_kind"].as_string()
                == "conversation",
                origin.c.trace["settlement"]["outcome"].as_string() == "answered",
                origin.c.trace["settlement"]["through_checkpoint"].as_string()
                == action.c.execution_contract["through_checkpoint"].as_string(),
                func.jsonb_typeof(origin.c.trace["settlement"]["run_id"]) == "string",
                conclusion.c.role == "assistant",
                conclusion.c.source == "discord",
                conclusion.c.source_conversation_id == source_conversation_id,
                conclusion.c.source_message_id.is_not(None),
                conclusion.c.processed_at == conclusion.c.created_at,
                action.c.completed_at <= conclusion.c.created_at,
                text(
                    "NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                    "action.execution_contract->'input_message_ids') "
                    "AS captured(value) "
                    "LEFT JOIN message AS input ON input.id::text = captured.value "
                    "WHERE input.id IS NULL OR input.role NOT IN ('owner', 'host') "
                    "OR input.source_conversation_id <> origin.source_conversation_id "
                    "OR input.processed_at IS DISTINCT FROM conclusion.created_at "
                    "OR input.trace->'settlement' "
                    "IS DISTINCT FROM origin.trace->'settlement')"
                ),
            )
        )
    ).mappings()
    delivered: list[UUID] = []
    for row in inline:
        stored = _stored_action(row)
        identity = json.dumps(
            [
                source_conversation_id,
                row["run_id"],
                stored.execution_contract.claim_id,
                stored.execution_contract.through_checkpoint,
                "conversation",
                "answered",
                row["conclusion_digest"],
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if (
            uuid5(NAMESPACE_URL, f"jarvis-conclusion-v1:{identity}")
            == row["conclusion_id"]
        ):
            delivered.append(stored.id)
    return tuple(delivered)


def retired_worker_predicate(
    tool: ColumnElement[str], revision: ColumnElement[str]
) -> ColumnElement[bool]:
    return or_(
        and_(tool.like("agent.%"), revision.in_(_RETIRED_AGENT_REVISIONS)),
        and_(tool.like("codex.%"), revision.in_(_RETIRED_CODEX_REVISIONS)),
    )


def retired_worker_revision(tool: str, revision: str) -> bool:
    """Identify only the known retired worker bindings, without decoding payloads."""
    return (tool.startswith("codex.") and revision in _RETIRED_CODEX_REVISIONS) or (
        tool.startswith("agent.") and revision in _RETIRED_AGENT_REVISIONS
    )


def retired_worker_action(stored: StoredAction) -> bool:
    """Retired worker records are opaque; current malformed rows stay defects."""
    return retired_worker_revision(
        str(stored.tool_name), stored.execution_contract.implementation_revision
    )


def archived_worker_action(stored: StoredAction) -> bool:
    return retired_worker_action(stored) and stored.status in {
        "succeeded",
        "failed",
        "uncertain",
        "cancelled",
    }


def _agent_evidence(stored: StoredAction, value: object) -> None:
    if retired_worker_action(stored):
        raise ActionPersistenceDefect("retired action must drain before activation")
    operation = str(stored.tool_name).removeprefix("agent.")
    validate_agent_evidence(operation, value)


def _gmail_update_basis(value: dict[str, object]) -> dict[str, object]:
    canonical = _json_object(value, "Gmail update reconciliation basis")
    if (
        set(canonical)
        != {
            "type",
            "draft_id",
            "thread_id",
            "jarvis_effect_id",
            "old_content_digest",
        }
        or canonical.get("type") != "gmail_update_reconciliation_v1"
    ):
        raise ValueError("Gmail update reconciliation basis is invalid")
    for key in ("draft_id", "thread_id"):
        item = canonical[key]
        if not isinstance(item, str) or not item or len(item.encode("utf-8")) > 1_024:
            raise ValueError("Gmail update reconciliation identity is invalid")
    for key in ("jarvis_effect_id", "old_content_digest"):
        item = canonical[key]
        if not isinstance(item, str) or _HEX_DIGEST.fullmatch(item) is None:
            raise ValueError("Gmail update reconciliation digest is invalid")
    return canonical


def agent_wait_state(stored: StoredAction) -> AgentWaitState:
    if stored.tool_name != ToolId("agent.wait"):
        raise ActionPersistenceDefect("action is not a wait")
    state = AgentWaitState.model_validate(stored.result)
    receipt = state.registration_receipt
    request = AgentWaitInput.model_validate(stored.payload)
    if (
        receipt.action_id != stored.id
        or receipt.arguments_digest != stored.execution_contract.input_digest
        or receipt.target != request.target
        or receipt.state != request.state
        or (receipt.deadline - receipt.recorded_at).total_seconds()
        != request.timeout_seconds
    ):
        raise ActionPersistenceDefect("wait registration differs from admitted action")
    if state.wait_outcome is None:
        valid = stored.status == "queued" and stored.completed_at is None
    else:
        expected = (
            "cancelled" if state.wait_outcome.outcome == "cancelled" else "succeeded"
        )
        valid = (
            stored.status == expected
            and stored.completed_at == state.wait_outcome.recorded_at
            and state.wait_outcome.target == receipt.target
        )
    if not valid:
        raise ActionPersistenceDefect("wait lifecycle disagrees with receipt/outcome")
    return state


def action_resolution_text(stored: StoredAction) -> str:
    """Frame the immutable outcome as host evidence, never owner speech."""
    if not isinstance(stored.execution_contract, ExecutionContract):
        return (
            f"historical action {stored.id}; tool: {stored.tool_name}; "
            f"recorded status: {stored.status}; original receipt retained."
        )
    context: dict[str, object] = {
        "type": "action_resolution_context_v2",
        "action_id": str(stored.id),
        "tool_name": str(stored.tool_name),
        "arguments": stored.arguments,
        "status": stored.status,
    }
    if (
        stored.tool_name == ToolId("agent.wait")
        and stored.result is not None
        and "registration_receipt" in stored.result
    ):
        state = agent_wait_state(stored)
        context.update(
            type="agent_wait_event_v1",
            registration=state.registration_receipt.model_dump(mode="json"),
            result=None
            if state.wait_outcome is None
            else state.wait_outcome.model_dump(mode="json"),
        )
    else:
        context["result"] = _safe_resolution_result(stored)
    return json.dumps(
        context, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _safe_resolution_result(stored: StoredAction) -> dict[str, object]:
    if stored.result is None:
        raise RuntimeError("resolved action has no durable result")
    if stored.tool_name in EVENT_MUTATION_IDS and stored.status in {
        "succeeded",
        "failed",
    }:
        result = _stored_tool_result(stored)
        if (
            result["type"] == "Success"
            or result["error"].get("type") == "AccountUnavailable"
        ):
            validate_event_result(stored.tool_name, result)
            return cast(dict[str, object], result)
    if stored.tool_name in WORK_MUTATION_IDS and stored.status in {
        "succeeded",
        "failed",
    }:
        result = _stored_tool_result(stored)
        if result["type"] == "Success" or result["error"].get("type") in {
            "NotFound",
            "NextUpFull",
            "InvalidSchedule",
        }:
            validate_work_result(stored.tool_name, result)
            return cast(dict[str, object], result)
    if stored.tool_name in AGENT_WRITE_IDS and "tool_result" in stored.result:
        result = stored.result["tool_result"]
        if not isinstance(result, dict):
            raise RuntimeError("invalid private action receipt")
        return cast(dict[str, object], result)
    if (
        stored.status == "uncertain"
        and stored.result.get("type") == "agent_uncertainty_v1"
    ):
        control = validate_agent_evidence(
            str(stored.tool_name).removeprefix("agent."), stored.result.get("control")
        )
        return {
            "type": "Failure",
            "error": {
                "type": "Unknown",
                "observed": _compact_agent_observation(control.observed),
            },
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
                "error": validate_agent_failure(
                    str(stored.tool_name).removeprefix("agent."), stored.result["error"]
                ).model_dump(mode="json"),
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
    if stored.status == "cancelled":
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


def _compact_agent_observation(
    value: WireFailure | WireStartResult | AgentWriteResult | AgentCloseReceipt | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, WireStartResult):
        launch = value
        target = (
            None
            if launch.handle is None
            else {"machine": launch.label, "handle": launch.handle}
        )
        return {
            "machine": launch.label,
            "target": target,
            "captured": launch.target is not None,
            "creation": launch.creation,
            "prompt": launch.prompt,
            "failure": None if launch.failure is None else launch.failure.code,
        }
    fields = value.model_dump(mode="json", exclude_none=True)
    return {
        key: fields[key]
        for key in ("code", "dispatch", "method", "outcome", "interrupt", "terminal")
        if key in fields
    }


async def _publish_action_outcome(
    connection: AsyncConnection, stored: StoredAction, source_conversation_id: str
) -> ResolutionInsert:
    if stored.completed_at is None:
        raise ActionPersistenceDefect("action has no terminal outcome")
    timestamp = stored.completed_at
    if (
        stored.tool_name == ToolId("agent.wait")
        and stored.result is not None
        and "registration_receipt" in stored.result
    ):
        state = agent_wait_state(stored)
        if state.wait_outcome is None:
            raise ActionPersistenceDefect("wait event has no outcome")
        timestamp = state.wait_outcome.recorded_at
    content = action_resolution_text(stored)
    if not content or len(content.encode()) > _MAX_RESOLUTION_TEXT_BYTES:
        raise ActionPersistenceDefect("action resolution exceeds its content bound")
    source_id = f"{stored.id}:{stored.status}"
    result = await append_waking_input(
        connection,
        role="host",
        text=content,
        source="action",
        source_conversation_id=source_conversation_id,
        source_message_id=source_id,
        created_at=timestamp,
        parent_request_id=stored.origin_message_id,
        action_id=stored.id,
        message_id=uuid5(NAMESPACE_URL, f"jarvis-action-resolution-v1:{source_id}"),
    )
    if result.inserted:
        await rearm_action_waiters(connection, stored.id)
    return ResolutionInsert(result.message.id, result.inserted)


def _tool_result(value: dict[str, object]) -> ToolResult:
    canonical = _json_object(value, "tool result")
    result_type = canonical.get("type")
    if result_type == "Success":
        if set(canonical) != {"type", "value"} or not isinstance(
            canonical["value"], dict
        ):
            raise ValueError("Success result is malformed")
    elif result_type == "Failure":
        if set(canonical) != {"type", "error"} or not isinstance(
            canonical["error"], dict
        ):
            raise ValueError("Failure result is malformed")
    else:
        raise ValueError("tool result type is invalid")
    return cast(ToolResult, canonical)


def _json_object(value: dict[str, object], name: str) -> dict[str, object]:
    try:
        decoded = json.loads(canonical_json_bytes(value))
    except ValueError as exc:
        raise ValueError(f"{name} is not canonical JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{name} must be a JSON object")
    return cast(dict[str, object], decoded)


def _canonical_uuid(value: str, name: str) -> str:
    try:
        canonical = str(UUID(value))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{name} ID must be a canonical UUID") from exc
    if value != canonical:
        raise ValueError(f"{name} ID must be a canonical UUID")
    return canonical


def _iso_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ActionPersistenceDefect(f"{name} must be an RFC3339 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ActionPersistenceDefect(f"{name} is invalid") from exc
    _aware(parsed, name)
    return parsed


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


__all__ = [
    "ACTION_MAX_ATTEMPTS",
    "ActionPersistenceDefect",
    "ActionPositionRecorder",
    "ActionStatus",
    "ActionStore",
    "ExecutionContract",
    "ResolutionInsert",
    "StoredAction",
    "TerminalActionStatus",
    "action_replay_result",
    "action_resolution_text",
    "agent_uncertainty_result",
    "archived_worker_action",
    "attachment_manual_cleanup_reported",
    "attachment_uncertainty_receipt",
    "complete_local_action",
    "recorded_action",
    "recorded_action_result",
    "require_locked_action",
    "resolve_reconciliation_in_transaction",
    "retired_worker_action",
    "retired_worker_revision",
]

"""Durable action state and the llm-tools write-position recorder."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from llm_tools import (
    BudgetState,
    FrozenToolPlan,
    InvocationPosition,
    PositionState,
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
from sqlalchemy import RowMapping, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from jarvis.db import action, message
from jarvis.messages import (
    MAX_DISCORD_MESSAGE_CHARACTERS,
    MAX_TRACE_BYTES,
    SettlementTrace,
)

if TYPE_CHECKING:
    from jarvis.schedule_tools import ScheduleTarget

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


class ActionPersistenceDefect(RuntimeError):
    """The durable action ledger is absent, stale, or internally inconsistent."""


class ExecutionContract(BaseModel):
    """Closed immutable evidence for one occupied write position."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    tool_contract_revision: Annotated[str, Field(min_length=1, max_length=256)]
    implementation_revision: Annotated[str, Field(min_length=1, max_length=256)]
    policy_revision: Annotated[str, Field(min_length=1, max_length=256)]
    plan_revision: Annotated[str, Field(min_length=1, max_length=256)]
    tool_effect: Literal[ToolEffect.Write]
    replay_policy: Literal[ReplayPolicy.ReDispatchable]
    input_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    max_attempts: Literal[2]
    claim_id: Annotated[str, Field(min_length=1, max_length=256)]
    through_checkpoint: Annotated[str, Field(min_length=1, max_length=36)]
    model_step_ordinal: Annotated[int, Field(ge=1)]
    input_message_ids: Annotated[tuple[str, ...], Field(min_length=1, max_length=100)]
    write_gate_supporting_owner_message_ids: Annotated[
        tuple[str, ...], Field(min_length=1, max_length=100)
    ]

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

    @field_validator(
        "input_message_ids",
        "write_gate_supporting_owner_message_ids",
    )
    @classmethod
    def canonical_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(_canonical_uuid(value, "message") for value in values)
        if len(canonical) != len(set(canonical)):
            raise ValueError("execution-contract message IDs must be unique")
        return canonical

    @model_validator(mode="after")
    def consistent_lineage(self) -> ExecutionContract:
        if self.through_checkpoint != self.input_message_ids[-1]:
            raise ValueError("through checkpoint must be the final admitted input")
        if not set(self.write_gate_supporting_owner_message_ids).issubset(
            self.input_message_ids
        ):
            raise ValueError("write-gate support must be admitted owner input")
        return self

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], self.model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class StoredAction:
    id: UUID
    tool_name: ToolId
    arguments: dict[str, object]
    execution_contract: ExecutionContract
    status: ActionStatus
    attempts: int
    execute_after: datetime | None
    origin_message_id: UUID
    approval_message_id: UUID | None
    created_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    result: dict[str, object] | None

    @property
    def position(self) -> InvocationPosition:
        return InvocationPosition(str(self.id))

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


@dataclass(frozen=True, slots=True)
class ClaimedSchedule:
    action: StoredAction
    waking_message_id: UUID
    message_inserted: bool


@dataclass(frozen=True, slots=True)
class ScheduleStateChanged:
    action: StoredAction


class ActionStore:
    """Explicit PostgreSQL transactions over the existing action table."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def insert_automatic(
        self,
        *,
        tool_name: ToolId,
        arguments: Mapping[str, object],
        execution_contract: ExecutionContract,
        origin_message_id: UUID,
        execute_after: datetime | None = None,
        action_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> StoredAction:
        identifier = action_id or uuid4()
        timestamp = created_at or datetime.now(UTC)
        _aware(timestamp, "action creation time")
        if execute_after is not None:
            _aware(execute_after, "action execute_after")
        canonical_arguments = _json_object(dict(arguments), "action arguments")
        _validate_new_action(
            tool_name,
            canonical_arguments,
            execution_contract,
            origin_message_id,
        )
        values: dict[str, object] = {
            "id": identifier,
            "tool_name": str(tool_name),
            "arguments": canonical_arguments,
            "execution_contract": execution_contract.as_json(),
            "status": "queued",
            "attempts": 0,
            "execute_after": execute_after,
            "origin_message_id": origin_message_id,
            "approval_message_id": None,
            "created_at": timestamp,
            "decided_at": None,
            "completed_at": None,
        }
        async with self.engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        postgresql_insert(action)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=(action.c.id,))
                        .returning(*action.c)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                return _stored_action(row)
            existing = await _locked_action(connection, identifier)
            if existing is None or _action_identity(existing) != (
                tool_name,
                canonical_arguments,
                execution_contract,
                origin_message_id,
                execute_after,
                timestamp,
            ):
                raise ActionPersistenceDefect(
                    "action identity was reused for a different invocation"
                )
            return existing

    async def get(self, action_id: UUID) -> StoredAction | None:
        async with self.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(action).where(action.c.id == action_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _stored_action(row)

    async def executing(self) -> tuple[StoredAction, ...]:
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(action.c.status == "executing")
                        .order_by(action.c.created_at, action.c.id)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_action, rows))

    async def executing_schedule_receipts(
        self, *, limit: int = 100
    ) -> tuple[StoredAction, ...]:
        if type(limit) is not int or limit <= 0:
            raise ValueError("schedule recovery limit must be a positive integer")
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            action.c.tool_name == "schedule.wake",
                            action.c.status == "executing",
                            action.c.result.op("?")("creation_receipt"),
                            action.c.arguments["request"]["type"].as_string()
                            == "create",
                        )
                        .order_by(action.c.execute_after, action.c.id)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_action, rows))

    async def recovery_candidates(
        self, *, include_queued: bool = True, limit: int = 100
    ) -> tuple[StoredAction, ...]:
        if type(include_queued) is not bool:
            raise ValueError("queued recovery selection must be boolean")
        if type(limit) is not int or limit <= 0:
            raise ValueError("action recovery limit must be a positive integer")
        statuses = ("queued", "executing") if include_queued else ("executing",)
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            action.c.status.in_(statuses),
                            or_(
                                action.c.tool_name != "schedule.wake",
                                action.c.result.is_(None),
                                action.c.arguments["request"]["type"].as_string()
                                != "create",
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
    ) -> tuple[StoredAction, ...]:
        if type(limit) is not int or limit <= 0:
            raise ValueError("action report limit must be a positive integer")
        if (
            not source_conversation_id
            or source_conversation_id != source_conversation_id.strip()
        ):
            raise ValueError("source conversation ID must be non-empty and canonical")
        async with self.engine.connect() as connection:
            eligible = and_(
                action.c.origin_message_id.in_(
                    select(message.c.id).where(
                        message.c.source_conversation_id == source_conversation_id
                    )
                ),
                or_(
                    and_(
                        action.c.status.in_(
                            (
                                "succeeded",
                                "failed",
                                "uncertain",
                                "cancelled",
                            )
                        ),
                        or_(
                            action.c.tool_name != "schedule.wake",
                            action.c.arguments["request"]["type"].as_string()
                            != "create",
                            ~action.c.result.op("?")("creation_receipt"),
                            and_(
                                action.c.result["wake_outcome"]["type"].as_string()
                                == "failed",
                                action.c.result["wake_outcome"][
                                    "reason_code"
                                ].as_string()
                                == "incompatible_execution_contract",
                                text(
                                    "NOT EXISTS ("
                                    "SELECT 1 FROM message AS wake "
                                    "WHERE wake.source = 'schedule_wake' "
                                    "AND wake.source_message_id = "
                                    "action.id::text)"
                                ),
                            ),
                        ),
                    ),
                    (
                        (action.c.tool_name == "schedule.wake")
                        & (action.c.status == "queued")
                        & action.c.result.is_not(None)
                        & (
                            action.c.arguments["request"]["type"].as_string()
                            == "create"
                        )
                    ),
                ),
                text(
                    "NOT EXISTS ("
                    "SELECT 1 FROM message AS resolution "
                    "WHERE resolution.source = 'action' "
                    "AND resolution.source_message_id = "
                    "action.id::text || ':' || action.status)"
                ),
                text(
                    "(EXISTS ("
                    "SELECT 1 FROM "
                    "jsonb_array_elements_text("
                    "action.execution_contract->'input_message_ids'"
                    ") AS input_id(value) "
                    "JOIN message AS input_message "
                    "ON input_message.id::text = input_id.value "
                    "WHERE input_message.processed_at IS NULL) "
                    "OR EXISTS ("
                    "SELECT 1 FROM "
                    "jsonb_array_elements_text("
                    "action.execution_contract->'input_message_ids'"
                    ") AS recovered_id(value) "
                    "JOIN message AS recovered_message "
                    "ON recovered_message.id::text = recovered_id.value "
                    "CROSS JOIN LATERAL jsonb_array_elements("
                    "COALESCE(recovered_message.trace"
                    "->'action_recovery'->'resolutions', '[]'::jsonb)"
                    ") AS prior_resolution(value) "
                    "WHERE prior_resolution.value->>'action_id' "
                    "= action.id::text "
                    "AND prior_resolution.value->>'status' = 'uncertain' "
                    "AND action.status IN ('succeeded', 'failed')) "
                    "OR NOT EXISTS ("
                    "SELECT 1 FROM "
                    "jsonb_array_elements_text("
                    "action.execution_contract->'input_message_ids'"
                    ") AS stranded_id(value) "
                    "LEFT JOIN message AS stranded_message "
                    "ON stranded_message.id::text = stranded_id.value "
                    "WHERE stranded_message.id IS NULL "
                    "OR stranded_message.processed_at IS NULL "
                    "OR NOT ("
                    "stranded_message.trace->'settlement'"
                    "->>'conclusion_kind' = 'stopped' "
                    "OR (stranded_message.trace->'settlement'"
                    "->>'conclusion_kind' = 'suspension' "
                    "AND stranded_message.trace->'settlement'"
                    "->>'outcome' = 'system'))))"
                ),
            )
            claim_id = await connection.scalar(
                select(action.c.execution_contract["claim_id"].as_string())
                .where(eligible)
                .order_by(action.c.completed_at.desc(), action.c.id)
                .limit(1)
            )
            if claim_id is None:
                return ()
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            eligible,
                            action.c.execution_contract["claim_id"].as_string()
                            == claim_id,
                        )
                        .order_by(action.c.completed_at.desc(), action.c.id)
                        .limit(limit + 1)
                    )
                )
                .mappings()
                .all()
            )
        if len(rows) > limit:
            raise ActionPersistenceDefect(
                "one recovered claim exceeds the action report bound"
            )
        return tuple(map(_stored_action, rows))

    async def schedule_target(self, action_id: UUID) -> ScheduleTarget:
        from jarvis.schedule_tools import (
            ScheduleCreateRequest,
            ScheduleTarget,
            ScheduleWakeInput,
        )

        stored = await self.get(action_id)
        if stored is None:
            return ScheduleTarget(exists=False, is_schedule_create=False, status=None)
        if str(stored.tool_name) != "schedule.wake":
            return ScheduleTarget(
                exists=True,
                is_schedule_create=False,
                status=stored.status,
            )
        try:
            request = ScheduleWakeInput.model_validate(stored.arguments).request
        except ValueError as exc:
            raise ActionPersistenceDefect(
                "stored schedule arguments are invalid"
            ) from exc
        return ScheduleTarget(
            exists=True,
            is_schedule_create=isinstance(request, ScheduleCreateRequest),
            status=stored.status,
        )

    async def next_due_at(self) -> datetime | None:
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(
                            action.c.tool_name == "schedule.wake",
                            action.c.status == "queued",
                            action.c.execute_after.is_not(None),
                            action.c.result.is_not(None),
                        )
                        .order_by(action.c.execute_after, action.c.id)
                    )
                )
                .mappings()
                .all()
            )
        for row in rows:
            stored = _stored_action(row)
            if _is_schedule_create(stored):
                _schedule_result(stored)
                assert stored.execute_after is not None
                return stored.execute_after
        return None

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
            stored = await _require_locked_action(connection, action_id)
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
            stored = await _require_locked_action(connection, action_id)
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
            or max_external_attempts <= 0
        ):
            raise ValueError("external attempt accounting is invalid")
        async with self.engine.begin() as connection:
            stored = await _require_locked_action(connection, action_id)
            if stored.status != "executing":
                raise ActionPersistenceDefect(
                    "only an executing action can be reconciled for repeat"
                )
            if stored.attempts >= stored.execution_contract.max_attempts:
                raise ActionPersistenceDefect(
                    "action attempt ceiling forbids another executor entry"
                )
            if _is_schedule_create(stored):
                raise ActionPersistenceDefect(
                    "local schedule lifecycle cannot use external readmission"
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

    async def requeue_local_schedule(self, action_id: UUID) -> StoredAction:
        async with self.engine.begin() as connection:
            stored = await _require_locked_action(connection, action_id)
            if str(stored.tool_name) != "schedule.wake":
                raise ActionPersistenceDefect("action is not a local schedule")
            if stored.status != "executing" or stored.result is not None:
                raise ActionPersistenceDefect(
                    "local schedule is not safely re-executable"
                )
            if stored.attempts >= stored.execution_contract.max_attempts:
                raise ActionPersistenceDefect(
                    "local schedule action attempt ceiling is exhausted"
                )
            return await _update_action(connection, action_id, status="queued")

    async def resolve_reconciliation(
        self,
        *,
        action_id: UUID,
        status: Literal["succeeded", "failed", "uncertain"],
        result: Mapping[str, object],
        resolved_at: datetime | None = None,
    ) -> StoredAction:
        timestamp = resolved_at or datetime.now(UTC)
        _aware(timestamp, "action reconciliation time")
        canonical_result = _json_object(dict(result), "action result")
        if status == "uncertain":
            canonical_result = _uncertainty_result(canonical_result)
        else:
            tool_result = _tool_result(canonical_result)
            if (status == "succeeded") != (tool_result["type"] == "Success"):
                raise ValueError("action status disagrees with its tool result")
        async with self.engine.begin() as connection:
            stored = await _require_locked_action(connection, action_id)
            if stored.status in {"succeeded", "failed"}:
                if stored.status != status or stored.result != canonical_result:
                    raise ActionPersistenceDefect("terminal action resolution changed")
                return stored
            if stored.status not in {"executing", "uncertain"}:
                raise ActionPersistenceDefect(
                    "only executing or uncertain work can be reconciled"
                )
            if stored.status == "uncertain" and status == "uncertain":
                if stored.result != canonical_result:
                    raise ActionPersistenceDefect("uncertain evidence changed")
                return stored
            return await _update_action(
                connection,
                action_id,
                status=status,
                completed_at=timestamp,
                result=canonical_result,
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
            stored = await _require_locked_action(connection, action_id)
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

    async def claim_due_schedule(
        self,
        *,
        action_id: UUID,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        now: datetime | None = None,
    ) -> ClaimedSchedule | None:
        timestamp = now or datetime.now(UTC)
        _aware(timestamp, "schedule claim time")
        if (
            not source_conversation_id
            or source_conversation_id != source_conversation_id.strip()
        ):
            raise ValueError("source conversation ID must be non-empty and canonical")
        async with self.engine.begin() as connection:
            stored = await _require_locked_action(connection, action_id)
            _require_schedule_creation(stored)
            if stored.status not in {"queued", "executing"}:
                raise ActionPersistenceDefect("schedule is no longer queued")
            if stored.execute_after is None or stored.execute_after > timestamp:
                raise ActionPersistenceDefect("schedule is not due")
            _schedule_result(stored)
            try:
                _require_current_execution_contract(stored, plan)
            except ActionPersistenceDefect:
                await _fail_incompatible_schedule_in_transaction(
                    connection,
                    stored=stored,
                    source_conversation_id=source_conversation_id,
                    recorded_at=timestamp,
                )
                return None
            request = _schedule_request(stored)
            instruction = request.get("instruction")
            requested = request.get("execute_after")
            if (
                not isinstance(instruction, str)
                or not instruction
                or not isinstance(requested, str)
                or _iso_datetime(requested, "schedule requested instant")
                != stored.execute_after
            ):
                raise ActionPersistenceDefect("schedule creation arguments are invalid")
            waking_text = f"Requested reminder at {requested}: {instruction}"
            waking_id = uuid5(
                NAMESPACE_URL,
                f"jarvis-scheduled-wake-v1:{stored.id}",
            )
            inserted = (
                await connection.execute(
                    postgresql_insert(message)
                    .values(
                        id=waking_id,
                        role="host",
                        text=waking_text,
                        source="schedule_wake",
                        source_conversation_id=source_conversation_id,
                        source_message_id=str(stored.id),
                        created_at=timestamp,
                        processed_at=None,
                        processing_attempts=0,
                        processing_parked_at=None,
                        remembered_at=None,
                        trace={},
                    )
                    .on_conflict_do_nothing(constraint="uq_message_source_identity")
                    .returning(message.c.id)
                )
            ).scalar_one_or_none() is not None
            if not inserted:
                existing = (
                    (
                        await connection.execute(
                            select(message).where(
                                message.c.source == "schedule_wake",
                                message.c.source_message_id == str(stored.id),
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                identity = (
                    existing["id"],
                    existing["role"],
                    existing["text"],
                    existing["source_conversation_id"],
                )
                if identity != (
                    waking_id,
                    "host",
                    waking_text,
                    source_conversation_id,
                ):
                    raise ActionPersistenceDefect(
                        "scheduled-wake identity has different content"
                    )
            if stored.status == "queued":
                stored = await _update_action(
                    connection,
                    action_id,
                    status="executing",
                )
            return ClaimedSchedule(stored, waking_id, inserted)

    async def claim_next_due_schedule(
        self,
        *,
        plan: FrozenToolPlan,
        source_conversation_id: str,
        now: datetime | None = None,
    ) -> ClaimedSchedule | ScheduleStateChanged | None:
        timestamp = now or datetime.now(UTC)
        _aware(timestamp, "schedule selection time")
        async with self.engine.connect() as connection:
            identifiers = tuple(
                (
                    await connection.execute(
                        select(action.c.id)
                        .where(
                            action.c.tool_name == "schedule.wake",
                            action.c.status == "queued",
                            action.c.execute_after <= timestamp,
                            action.c.result.is_not(None),
                        )
                        .order_by(action.c.execute_after, action.c.id)
                        .limit(10)
                    )
                ).scalars()
            )
        for action_id in identifiers:
            stored = await self.get(action_id)
            if stored is not None and _is_schedule_create(stored):
                claimed = await self.claim_due_schedule(
                    action_id=action_id,
                    plan=plan,
                    source_conversation_id=source_conversation_id,
                    now=timestamp,
                )
                if claimed is not None:
                    return claimed
                changed = await self.get(action_id)
                if changed is None or changed.status != "failed":
                    raise ActionPersistenceDefect(
                        "due schedule changed without a durable failure"
                    )
                return ScheduleStateChanged(changed)
        return None

    async def fail_incompatible_schedule(
        self,
        *,
        action_id: UUID,
        source_conversation_id: str,
        recorded_at: datetime | None = None,
    ) -> StoredAction:
        timestamp = recorded_at or datetime.now(UTC)
        _aware(timestamp, "incompatible schedule failure time")
        if (
            not source_conversation_id
            or source_conversation_id != source_conversation_id.strip()
        ):
            raise ValueError("source conversation ID must be non-empty and canonical")
        async with self.engine.begin() as connection:
            stored = await _require_locked_action(connection, action_id)
            return await _fail_incompatible_schedule_in_transaction(
                connection,
                stored=stored,
                source_conversation_id=source_conversation_id,
                recorded_at=timestamp,
            )

    async def finish_schedule(
        self,
        *,
        action_id: UUID,
        wake_outcome: Mapping[str, object],
    ) -> StoredAction:
        outcome = _json_object(dict(wake_outcome), "schedule wake outcome")
        outcome_type, recorded_at = _wake_outcome(outcome)
        if outcome_type == "cancelled":
            raise ValueError("schedule cancellation requires its atomic cancel action")
        status: Literal["succeeded", "failed"] = (
            "succeeded" if outcome_type == "concluded" else "failed"
        )
        async with self.engine.begin() as connection:
            return await _finish_schedule_in_transaction(
                connection,
                action_id=action_id,
                outcome=outcome,
                status=status,
                recorded_at=recorded_at,
            )

    async def insert_resolution_message(
        self,
        *,
        action_id: UUID,
        source_conversation_id: str,
        text: str,
        created_at: datetime | None = None,
    ) -> ResolutionInsert:
        if (
            not source_conversation_id
            or source_conversation_id != source_conversation_id.strip()
        ):
            raise ValueError("source conversation ID must be non-empty and canonical")
        if not text or len(text.encode("utf-8")) > _MAX_RESOLUTION_TEXT_BYTES:
            raise ValueError("action-resolution text must be non-empty and bounded")
        timestamp = created_at or datetime.now(UTC)
        _aware(timestamp, "action-resolution creation time")
        async with self.engine.begin() as connection:
            stored = await _require_locked_action(connection, action_id)
            if stored.status not in {"succeeded", "failed", "uncertain", "cancelled"}:
                raise ActionPersistenceDefect(
                    "action-resolution message requires a resolved action"
                )
            source_message_id = f"{stored.id}:{stored.status}"
            message_id = uuid5(
                NAMESPACE_URL,
                f"jarvis-action-resolution-v1:{source_message_id}",
            )
            row = (
                await connection.execute(
                    postgresql_insert(message)
                    .values(
                        id=message_id,
                        role="host",
                        text=text,
                        source="action",
                        source_conversation_id=source_conversation_id,
                        source_message_id=source_message_id,
                        created_at=timestamp,
                        processed_at=None,
                        processing_attempts=0,
                        processing_parked_at=None,
                        remembered_at=None,
                        trace={},
                    )
                    .on_conflict_do_nothing(constraint="uq_message_source_identity")
                    .returning(message.c.id)
                )
            ).scalar_one_or_none()
            if row is not None:
                return ResolutionInsert(message_id, inserted=True)
            existing = (
                (
                    await connection.execute(
                        select(message).where(
                            message.c.source == "action",
                            message.c.source_message_id == source_message_id,
                        )
                    )
                )
                .mappings()
                .one()
            )
            identity = (
                existing["id"],
                existing["role"],
                existing["text"],
                existing["source_conversation_id"],
            )
            if identity != (message_id, "host", text, source_conversation_id):
                raise ActionPersistenceDefect(
                    "action-resolution identity has different content"
                )
            return ResolutionInsert(message_id, inserted=False)

    async def finish_recovered_origin(
        self,
        *,
        action_id: UUID,
        source_conversation_id: str,
        text: str,
        created_at: datetime | None = None,
    ) -> ResolutionInsert:
        """Atomically consume an interrupted lineage and enqueue its resolution."""

        return (
            await self.finish_recovered_origins(
                reports=((action_id, text),),
                source_conversation_id=source_conversation_id,
                created_at=created_at,
            )
        )[0]

    async def finish_recovered_origins(
        self,
        *,
        reports: tuple[tuple[UUID, str], ...],
        source_conversation_id: str,
        created_at: datetime | None = None,
    ) -> tuple[ResolutionInsert, ...]:
        """Atomically report a recovered run and consume its admitted-input union."""

        if (
            not source_conversation_id
            or source_conversation_id != source_conversation_id.strip()
        ):
            raise ValueError("source conversation ID must be non-empty and canonical")
        action_ids = tuple(action_id for action_id, _ in reports)
        if (
            not reports
            or len(reports) > 16
            or len(action_ids) != len(set(action_ids))
            or any(
                not value or len(value.encode("utf-8")) > _MAX_RESOLUTION_TEXT_BYTES
                for _, value in reports
            )
        ):
            raise ValueError(
                "recovered action batch must be non-empty, unique, and bounded"
            )
        timestamp = created_at or datetime.now(UTC)
        _aware(timestamp, "action-resolution creation time")
        async with self.engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(action)
                        .where(action.c.id.in_(action_ids))
                        .order_by(action.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != len(reports):
                raise ActionPersistenceDefect("recovered action batch is incomplete")
            stored_by_id = {value.id: value for value in map(_stored_action, rows)}
            stored = tuple(stored_by_id[action_id] for action_id in action_ids)
            if any(
                value.status not in {"succeeded", "failed", "uncertain", "cancelled"}
                and not (
                    value.status == "queued"
                    and _is_schedule_create(value)
                    and value.result is not None
                )
                for value in stored
            ):
                raise ActionPersistenceDefect(
                    "recovered action batch requires terminal actions"
                )
            claim_ids = {value.execution_contract.claim_id for value in stored}
            model_steps = tuple(
                value.execution_contract.model_step_ordinal for value in stored
            )
            if len(claim_ids) != 1 or len(model_steps) != len(set(model_steps)):
                raise ActionPersistenceDefect(
                    "recovered action batch has incompatible run lineage"
                )
            longest_lineage = max(
                (value.execution_contract.input_message_ids for value in stored),
                key=len,
            )
            if any(
                longest_lineage[: len(value.execution_contract.input_message_ids)]
                != value.execution_contract.input_message_ids
                for value in stored
            ):
                raise ActionPersistenceDefect(
                    "recovered action batch has incompatible input lineage"
                )
            through_checkpoint = longest_lineage[-1]
            resolutions: list[ResolutionInsert] = []
            trace_resolutions: list[dict[str, str]] = []
            for value, (_, resolution_text) in zip(stored, reports, strict=True):
                source_message_id = f"{value.id}:{value.status}"
                message_id = uuid5(
                    NAMESPACE_URL,
                    f"jarvis-action-resolution-v1:{source_message_id}",
                )
                inserted = (
                    await connection.execute(
                        postgresql_insert(message)
                        .values(
                            id=message_id,
                            role="host",
                            text=resolution_text,
                            source="action",
                            source_conversation_id=source_conversation_id,
                            source_message_id=source_message_id,
                            created_at=timestamp,
                            processed_at=None,
                            processing_attempts=0,
                            processing_parked_at=None,
                            remembered_at=None,
                            trace={},
                        )
                        .on_conflict_do_nothing(constraint="uq_message_source_identity")
                        .returning(message.c.id)
                    )
                ).scalar_one_or_none() is not None
                if not inserted:
                    existing = (
                        (
                            await connection.execute(
                                select(message).where(
                                    message.c.source == "action",
                                    message.c.source_message_id == source_message_id,
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                    identity = (
                        existing["id"],
                        existing["role"],
                        existing["text"],
                        existing["source_conversation_id"],
                    )
                    if identity != (
                        message_id,
                        "host",
                        resolution_text,
                        source_conversation_id,
                    ):
                        raise ActionPersistenceDefect(
                            "action-resolution identity has different content"
                        )
                resolutions.append(ResolutionInsert(message_id, inserted))
                trace_resolutions.append(
                    {
                        "action_id": str(value.id),
                        "status": value.status,
                        "resolution_message_id": str(message_id),
                    }
                )
            input_ids = tuple(
                dict.fromkeys(
                    UUID(input_id)
                    for value in stored
                    for input_id in value.execution_contract.input_message_ids
                )
            )
            inputs = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(input_ids))
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(inputs) != len(input_ids):
                raise ActionPersistenceDefect("action lineage references missing input")
            if any(row["processing_parked_at"] is not None for row in inputs):
                raise ActionPersistenceDefect("action lineage contains a parked input")
            if any(
                row["source_conversation_id"] != source_conversation_id
                for row in inputs
            ):
                raise ActionPersistenceDefect(
                    "action lineage belongs to a different conversation"
                )
            host_inputs = tuple(row for row in inputs if row["role"] == "host")
            if len(host_inputs) > 1:
                raise ActionPersistenceDefect(
                    "recovered action lineage contains multiple host inputs"
                )
            processed = tuple(row["processed_at"] is not None for row in inputs)
            if any(processed) and not all(processed):
                raise ActionPersistenceDefect(
                    "action lineage is only partially settled"
                )
            if all(processed):
                settlements = tuple(row["trace"].get("settlement") for row in inputs)
                if (
                    any(not isinstance(value, dict) for value in settlements)
                    or any(value != settlements[0] for value in settlements[1:])
                    or not _is_stranded_settlement(
                        cast(dict[str, object], settlements[0])
                    )
                ):
                    raise ActionPersistenceDefect(
                        "processed action lineage lacks one stranded settlement"
                    )
                settlement = cast(dict[str, object], settlements[0])
            else:
                settlement = SettlementTrace(
                    run_id=f"action-recovery:{next(iter(claim_ids))}",
                    through_checkpoint=through_checkpoint,
                    conclusion_kind="suspension",
                    outcome="system",
                ).as_json(None)
            recovery_trace = {
                "claim_id": next(iter(claim_ids)),
                "through_checkpoint": through_checkpoint,
                "resolutions": trace_resolutions,
            }
            for row in inputs:
                updated_trace = {
                    **row["trace"],
                    "settlement": settlement,
                    "action_recovery": recovery_trace,
                }
                if len(canonical_json_bytes(updated_trace)) > MAX_TRACE_BYTES:
                    raise ActionPersistenceDefect(
                        "action recovery would exceed the message trace bound"
                    )
            await connection.execute(
                update(message)
                .where(message.c.id.in_(input_ids))
                .values(
                    processed_at=func.coalesce(message.c.processed_at, timestamp),
                    trace=message.c.trace.concat(
                        {
                            "settlement": settlement,
                            "action_recovery": recovery_trace,
                        }
                    ),
                )
            )
            return tuple(resolutions)


class ActionPositionRecorder:
    """Action-backed PositionRecorder for one ReDispatchable Write."""

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
        if type(max_external_attempts) is not int or max_external_attempts <= 0:
            raise ValueError("maximum external attempts must be a positive integer")
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
        replay = _replay_result(stored)
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
            return self._reservation_accepted
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
        if replay_policy is not ReplayPolicy.ReDispatchable:
            raise ValueError("action replay policy changed")
        async with self._store.engine.begin() as connection:
            stored = await _require_locked_action(connection, self._action_id)
            self._require_contract(stored)
            replay = _replay_result(stored)
            if replay is not None:
                return PositionState(
                    replay,
                    False,
                    _recovery_external_attempts(stored),
                )
            if stored.status in {"executing", "uncertain"}:
                return PositionState(
                    None,
                    True,
                    _recovery_external_attempts(stored),
                )
            if stored.status != "queued":
                raise ValueError("action is not eligible for executor entry")
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
        raise ValueError("ReDispatchable writes require tool-specific reconciliation")

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
            stored = await _require_locked_action(connection, self._action_id)
            self._require_contract(stored)
            prior_external_attempts = _recovery_external_attempts(stored)
            if settlement.actual_attempts < prior_external_attempts:
                raise ValueError("write settlement lost recovered attempt accounting")
            replay = _replay_result(stored)
            if replay is not None:
                if replay != canonical_result:
                    raise ValueError("terminal write result changed")
                if self._reservation_accepted:
                    await budgets.settle(position, settlement)
                self._settlement = settlement
                return replay
            if stored.status == "uncertain":
                raise ValueError("uncertain action requires reconciliation")
            if stored.status not in {"queued", "executing"}:
                raise ValueError("action cannot accept a terminal tool result")
            if self._reservation_accepted:
                await budgets.settle(position, settlement)

            if _is_schedule_create(stored) and canonical_result["type"] == "Success":
                await _store_schedule_creation(connection, stored, canonical_result)
            elif _is_schedule_cancel(stored) and canonical_result["type"] == "Success":
                await _store_schedule_cancellation(connection, stored, canonical_result)
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
                    result=canonical_result,
                )
            self._settlement = settlement
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


async def finish_schedule_conclusion(
    connection: AsyncConnection,
    *,
    action_id: UUID,
    conclusion_message_id: UUID,
    recorded_at: datetime,
) -> StoredAction:
    _aware(recorded_at, "schedule conclusion time")
    return await _finish_schedule_in_transaction(
        connection,
        action_id=action_id,
        outcome={
            "type": "concluded",
            "conclusion_message_id": str(conclusion_message_id),
            "recorded_at": recorded_at.isoformat(),
        },
        status="succeeded",
        recorded_at=recorded_at,
    )


async def _finish_schedule_in_transaction(
    connection: AsyncConnection,
    *,
    action_id: UUID,
    outcome: dict[str, object],
    status: Literal["succeeded", "failed"],
    recorded_at: datetime,
) -> StoredAction:
    stored = await _require_locked_action(connection, action_id)
    _require_schedule_creation(stored)
    if stored.status in {"succeeded", "failed"}:
        existing = _schedule_result(stored)
        if stored.status != status or existing["wake_outcome"] != outcome:
            raise ActionPersistenceDefect("schedule outcome changed")
        return stored
    if stored.status != "executing":
        raise ActionPersistenceDefect("only a claimed schedule can finish")
    result = _schedule_result(stored)
    result["wake_outcome"] = outcome
    return await _update_action(
        connection,
        action_id,
        status=status,
        completed_at=recorded_at,
        result=result,
    )


async def _fail_incompatible_schedule_in_transaction(
    connection: AsyncConnection,
    *,
    stored: StoredAction,
    source_conversation_id: str,
    recorded_at: datetime,
) -> StoredAction:
    _require_schedule_creation(stored)
    if stored.status not in {"queued", "executing"}:
        raise ActionPersistenceDefect(
            "only an active schedule can fail compatibility validation"
        )
    result = _schedule_result(stored)
    waking = (
        (
            await connection.execute(
                select(message)
                .where(
                    message.c.source == "schedule_wake",
                    message.c.source_message_id == str(stored.id),
                )
                .with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    if stored.status == "queued":
        if waking is not None:
            raise ActionPersistenceDefect(
                "queued schedule unexpectedly has a waking message"
            )
    else:
        if waking is None:
            raise ActionPersistenceDefect(
                "executing schedule is missing its waking message"
            )
        if (
            waking["role"] != "host"
            or waking["source_conversation_id"] != source_conversation_id
            or waking["processed_at"] is not None
            or waking["processing_parked_at"] is not None
        ):
            raise ActionPersistenceDefect(
                "executing schedule has an incompatible waking message"
            )
        request = _schedule_request(stored)
        requested = request.get("execute_after")
        instruction = request.get("instruction")
        if not isinstance(requested, str) or not isinstance(instruction, str):
            raise ActionPersistenceDefect("schedule creation arguments are invalid")
        prefix = (
            f"Reminder at {requested} was not run because its stored execution "
            "contract is incompatible with this deployment. No stale model or "
            "tool call was made. Requested instruction: "
        )
        available = MAX_DISCORD_MESSAGE_CHARACTERS - len(prefix)
        if available <= 1:
            raise AssertionError("incompatible schedule fallback prefix is too long")
        fallback_text = (
            prefix + instruction
            if len(instruction) <= available
            else prefix + instruction[: available - 1] + "…"
        )
        conclusion_id = uuid5(
            NAMESPACE_URL,
            f"jarvis-incompatible-scheduled-wake-v1:{stored.id}",
        )
        settlement = SettlementTrace(
            run_id=f"schedule-incompatible:{stored.id}",
            through_checkpoint=str(waking["id"]),
            conclusion_kind="conversation",
            outcome="host_fallback",
        ).as_json(conclusion_id)
        if len(canonical_json_bytes({"settlement": settlement})) > MAX_TRACE_BYTES:
            raise ActionPersistenceDefect(
                "incompatible schedule settlement exceeds the trace bound"
            )
        await connection.execute(
            postgresql_insert(message).values(
                id=conclusion_id,
                role="assistant",
                text=fallback_text,
                source="discord",
                source_conversation_id=source_conversation_id,
                source_message_id=None,
                created_at=recorded_at,
                processed_at=recorded_at,
                processing_attempts=0,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )
        await connection.execute(
            update(message)
            .where(message.c.id == waking["id"])
            .values(
                processed_at=recorded_at,
                trace=message.c.trace.concat({"settlement": settlement}),
            )
        )
    result["wake_outcome"] = {
        "type": "failed",
        "reason_code": "incompatible_execution_contract",
        "recorded_at": recorded_at.isoformat(),
    }
    return await _update_action(
        connection,
        stored.id,
        status="failed",
        completed_at=recorded_at,
        result=result,
    )


async def _store_schedule_creation(
    connection: AsyncConnection,
    stored: StoredAction,
    result: ToolResult,
) -> None:
    value = _success_value(result)
    expected = {"type", "action_id", "execute_after", "arguments_digest", "recorded_at"}
    if set(value) != expected or value.get("type") != "created":
        raise ValueError("schedule creation returned an invalid receipt")
    receipt = {key: value[key] for key in expected - {"type"}}
    if _canonical_uuid_value(receipt["action_id"], "schedule action") != str(stored.id):
        raise ValueError("schedule receipt has a different action ID")
    execute_after = _iso_datetime(receipt["execute_after"], "schedule execute_after")
    _iso_datetime(receipt["recorded_at"], "schedule recorded_at")
    if stored.execute_after != execute_after:
        raise ValueError("schedule receipt has a different due time")
    if receipt["arguments_digest"] != stored.execution_contract.input_digest:
        raise ValueError("schedule receipt has a different argument digest")
    await _update_action(
        connection,
        stored.id,
        status="queued",
        completed_at=None,
        result={"creation_receipt": receipt, "wake_outcome": None},
    )


async def _store_schedule_cancellation(
    connection: AsyncConnection,
    cancellation: StoredAction,
    result: ToolResult,
) -> None:
    value = _success_value(result)
    expected = {"type", "target_action_id", "recorded_at"}
    if set(value) != expected or value.get("type") != "cancelled":
        raise ValueError("schedule cancellation returned an invalid receipt")
    request = _schedule_request(cancellation)
    target_id = UUID(
        _canonical_uuid_value(value["target_action_id"], "schedule target")
    )
    if request.get("target_action_id") != str(target_id):
        raise ValueError("schedule cancellation receipt changed its target")
    recorded_at = _iso_datetime(value["recorded_at"], "schedule cancellation time")
    target = await _require_locked_action(connection, target_id)
    _require_schedule_creation(target)
    if target.status != "queued":
        raise ActionPersistenceDefect(
            "schedule cancellation target is no longer queued"
        )
    target_result = _schedule_result(target)
    target_result["wake_outcome"] = {
        "type": "cancelled",
        "cancellation_action_id": str(cancellation.id),
        "recorded_at": recorded_at.isoformat(),
    }
    await _update_action(
        connection,
        target.id,
        status="cancelled",
        decided_at=recorded_at,
        completed_at=recorded_at,
        result=target_result,
    )
    await _update_action(
        connection,
        cancellation.id,
        status="succeeded",
        completed_at=recorded_at,
        result=result,
    )


async def _locked_action(
    connection: AsyncConnection, action_id: UUID
) -> StoredAction | None:
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


async def _require_locked_action(
    connection: AsyncConnection, action_id: UUID
) -> StoredAction:
    stored = await _locked_action(connection, action_id)
    if stored is None:
        raise ActionPersistenceDefect("action does not exist")
    return stored


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
        contract = ExecutionContract.model_validate(row["execution_contract"])
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
        )
        _validate_stored_action(stored)
        return stored
    except (TypeError, ValueError) as exc:
        raise ActionPersistenceDefect("stored action is invalid") from exc


def _validate_new_action(
    tool_name: ToolId,
    arguments: dict[str, object],
    contract: ExecutionContract,
    origin_message_id: UUID,
) -> None:
    ToolId(str(tool_name))
    if contract.tool_effect is not ToolEffect.Write:
        raise ValueError("actions require the Write effect")
    if contract.replay_policy is not ReplayPolicy.ReDispatchable:
        raise ValueError("v1 write actions must be ReDispatchable")
    if contract.max_attempts != ACTION_MAX_ATTEMPTS:
        raise ValueError("v1 write actions require exactly two lifetime entries")
    if raw_input_digest(ParsedJson(arguments)) != contract.input_digest:
        raise ValueError("execution contract has a different input digest")
    if str(origin_message_id) != contract.input_message_ids[0]:
        raise ValueError("origin message must be the first admitted input")


def _require_current_execution_contract(
    stored: StoredAction, plan: FrozenToolPlan
) -> None:
    try:
        binding = plan.catalog_view.binding(stored.tool_name)
        plan.grant(stored.tool_name)
        binding.spec.input_type.model_validate(stored.arguments)
    except (KeyError, ValueError) as exc:
        raise ActionPersistenceDefect(
            "schedule execution contract is no longer selectable"
        ) from exc
    contract = stored.execution_contract
    if (
        binding.spec.effect is not ToolEffect.Write
        or binding.spec.tool_contract_revision != contract.tool_contract_revision
        or binding.implementation_revision != contract.implementation_revision
        or binding.policy_revision != contract.policy_revision
        or binding.replay_policy is not contract.replay_policy
        or plan.plan_revision != contract.plan_revision
        or raw_input_digest(ParsedJson(stored.arguments)) != contract.input_digest
    ):
        raise ActionPersistenceDefect(
            "schedule execution contract is incompatible with the current plan"
        )


def _validate_stored_action(stored: StoredAction) -> None:
    _validate_new_action(
        stored.tool_name,
        stored.arguments,
        stored.execution_contract,
        stored.origin_message_id,
    )
    _aware(stored.created_at, "stored action creation time")
    if stored.execute_after is not None:
        _aware(stored.execute_after, "stored action execute_after")
    terminal = stored.status in {"succeeded", "failed", "uncertain", "cancelled"}
    if terminal != (stored.completed_at is not None):
        raise ValueError("stored action terminal timestamp is inconsistent")
    if stored.status == "awaiting_approval" and stored.approval_message_id is None:
        raise ValueError("approval action is missing its message")
    if stored.status in {"succeeded", "failed", "uncertain"} and stored.result is None:
        raise ValueError("resolved action is missing its result")
    if stored.result is not None:
        if _is_schedule_create(stored) and set(stored.result) == {
            "creation_receipt",
            "wake_outcome",
        }:
            _schedule_result(stored)
        elif stored.status == "uncertain":
            _uncertainty_result(stored.result)
        elif stored.status in {"succeeded", "failed"}:
            result = _tool_result(stored.result)
            if (stored.status == "succeeded") != (result["type"] == "Success"):
                raise ValueError("stored action status disagrees with its result")
        elif stored.result.get("type") == "gmail_update_reconciliation_v1":
            _gmail_update_basis(stored.result)
        elif stored.result.get("type") == "action_recovery_v1":
            _recovery_state(stored.result)


def _action_identity(
    stored: StoredAction,
) -> tuple[
    ToolId,
    dict[str, object],
    ExecutionContract,
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


def _replay_result(stored: StoredAction) -> ToolResult | None:
    if (
        _is_schedule_create(stored)
        and stored.result is not None
        and set(stored.result) == {"creation_receipt", "wake_outcome"}
    ):
        schedule = _schedule_result(stored)
        receipt = cast(dict[str, object], schedule["creation_receipt"])
        return {
            "type": "Success",
            "value": {"receipt": {"type": "created", **receipt}},
        }
    if stored.status in {"succeeded", "failed"} and stored.result is not None:
        return _tool_result(stored.result)
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


def _uncertainty_result(result: dict[str, object]) -> dict[str, object]:
    canonical = _json_object(result, "action uncertainty result")
    if (
        set(canonical) != {"type", "evidence_code", "recorded_at"}
        or canonical.get("type") != "action_uncertainty_v1"
    ):
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


def _schedule_result(stored: StoredAction) -> dict[str, object]:
    if stored.result is None or set(stored.result) != {
        "creation_receipt",
        "wake_outcome",
    }:
        raise ActionPersistenceDefect("schedule creation receipt is missing")
    raw_receipt = stored.result["creation_receipt"]
    if not isinstance(raw_receipt, dict):
        raise ActionPersistenceDefect("schedule creation receipt is invalid")
    receipt = cast(dict[str, object], raw_receipt)
    if set(receipt) != {
        "action_id",
        "execute_after",
        "arguments_digest",
        "recorded_at",
    }:
        raise ActionPersistenceDefect("schedule creation receipt is invalid")
    if _canonical_uuid_value(receipt["action_id"], "schedule action") != str(stored.id):
        raise ActionPersistenceDefect("schedule creation receipt changed action ID")
    execute_after = _iso_datetime(receipt["execute_after"], "schedule execute_after")
    _iso_datetime(receipt["recorded_at"], "schedule recorded_at")
    if stored.execute_after != execute_after:
        raise ActionPersistenceDefect("schedule creation receipt changed due time")
    if receipt["arguments_digest"] != stored.execution_contract.input_digest:
        raise ActionPersistenceDefect("schedule creation receipt changed digest")
    outcome = stored.result["wake_outcome"]
    if outcome is not None:
        if not isinstance(outcome, dict):
            raise ActionPersistenceDefect("schedule wake outcome is invalid")
        outcome_type, _ = _wake_outcome(cast(dict[str, object], outcome))
        expected_status = {
            "concluded": "succeeded",
            "cancelled": "cancelled",
            "failed": "failed",
        }[outcome_type]
        if stored.status != expected_status:
            raise ActionPersistenceDefect("schedule status disagrees with wake outcome")
    elif stored.status not in {"queued", "executing"}:
        raise ActionPersistenceDefect("terminal schedule is missing its wake outcome")
    return _json_object(stored.result, "schedule result")


def _wake_outcome(
    outcome: dict[str, object],
) -> tuple[Literal["concluded", "cancelled", "failed"], datetime]:
    outcome_type = outcome.get("type")
    fields = {
        "concluded": {"type", "conclusion_message_id", "recorded_at"},
        "cancelled": {"type", "cancellation_action_id", "recorded_at"},
        "failed": {"type", "reason_code", "recorded_at"},
    }
    if outcome_type not in fields or set(outcome) != fields[cast(str, outcome_type)]:
        raise ActionPersistenceDefect("schedule wake outcome shape is invalid")
    typed = cast(Literal["concluded", "cancelled", "failed"], outcome_type)
    if typed == "concluded":
        _canonical_uuid_value(outcome["conclusion_message_id"], "conclusion message")
    elif typed == "cancelled":
        _canonical_uuid_value(outcome["cancellation_action_id"], "cancellation action")
    else:
        reason = outcome["reason_code"]
        if not isinstance(reason, str) or not reason or len(reason) > 64:
            raise ActionPersistenceDefect("schedule failure reason is invalid")
    return typed, _iso_datetime(outcome["recorded_at"], "wake outcome time")


def _is_stranded_settlement(value: dict[str, object]) -> bool:
    run_id = value.get("run_id")
    through_checkpoint = value.get("through_checkpoint")
    conclusion_message_id = value.get("conclusion_message_id")
    conclusion_kind = value.get("conclusion_kind")
    outcome = value.get("outcome")
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(through_checkpoint, str)
        or not isinstance(outcome, str)
        or not outcome
        or not (
            conclusion_kind == "stopped"
            or (conclusion_kind == "suspension" and outcome == "system")
        )
        or not (conclusion_message_id is None or isinstance(conclusion_message_id, str))
    ):
        return False
    try:
        _canonical_uuid_value(through_checkpoint, "settlement checkpoint")
        if isinstance(conclusion_message_id, str):
            _canonical_uuid_value(conclusion_message_id, "settlement conclusion")
    except (TypeError, ValueError):
        return False
    return True


def _require_schedule_creation(stored: StoredAction) -> None:
    if not _is_schedule_create(stored):
        raise ActionPersistenceDefect("action is not a schedule creation")


def _is_schedule_create(stored: StoredAction) -> bool:
    return (
        str(stored.tool_name) == "schedule.wake"
        and _schedule_request(stored).get("type") == "create"
    )


def _is_schedule_cancel(stored: StoredAction) -> bool:
    return (
        str(stored.tool_name) == "schedule.wake"
        and _schedule_request(stored).get("type") == "cancel"
    )


def _schedule_request(stored: StoredAction) -> dict[str, object]:
    if str(stored.tool_name) != "schedule.wake":
        return {}
    request = stored.arguments.get("request")
    if not isinstance(request, dict):
        raise ActionPersistenceDefect("schedule action request is invalid")
    return cast(dict[str, object], request)


def _success_value(result: ToolResult) -> dict[str, object]:
    value = result.get("value")
    if result.get("type") != "Success" or not isinstance(value, dict):
        raise ValueError("schedule operation requires a Success object")
    typed_value = cast(dict[str, object], value)
    if set(typed_value) != {"receipt"} or not isinstance(typed_value["receipt"], dict):
        raise ValueError("schedule operation returned an invalid receipt wrapper")
    return cast(dict[str, object], typed_value["receipt"])


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


def _canonical_uuid_value(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ActionPersistenceDefect(f"{name} ID must be a string")
    try:
        return _canonical_uuid(value, name)
    except ValueError as exc:
        raise ActionPersistenceDefect(f"{name} ID is invalid") from exc


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
    "ClaimedSchedule",
    "ExecutionContract",
    "ResolutionInsert",
    "StoredAction",
    "TerminalActionStatus",
    "finish_schedule_conclusion",
]

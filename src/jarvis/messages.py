from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from llm_agent_kernel import InitialReadDispatchLineage, RunId
from llm_tools import canonical_json_bytes
from sqlalchemy import RowMapping, case, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import message, model_decision, read_position
from jarvis.decisions import pending_thread_decision
from jarvis.memory import MemoryIdentity
from jarvis.ownership import Database
from jarvis.settings import MAXIMUM_BATCH_SIZE

MessageRole = Literal["owner", "assistant", "host"]
ClaimRoute = Literal["interactive", "scheduled_wake"]

MAX_TRACE_BYTES = 16_384
MAX_REASON_CODE_LENGTH = 64
MAX_DISCORD_MESSAGE_CHARACTERS = 2_000
ACTION_MODEL_CONTEXT_SEPARATOR = (
    "\n\nOriginal validated arguments for model context only:\n"
)
_REASON_CODE = re.compile(r"^[a-z0-9][a-z0-9_:-]*$")


class PersistenceDefect(RuntimeError):
    """Canonical message state is missing or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: UUID
    role: MessageRole
    text: str
    source: str
    source_conversation_id: str
    source_message_id: str | None
    created_at: datetime
    processed_at: datetime | None
    processing_attempts: int
    processing_parked_at: datetime | None
    remembered_at: datetime | None
    trace: dict[str, object]


@dataclass(frozen=True, slots=True)
class InboundInsert:
    message: StoredMessage
    inserted: bool


@dataclass(frozen=True, slots=True)
class ClaimedMessages:
    claim_id: str
    route: ClaimRoute
    messages: tuple[StoredMessage, ...]
    through_checkpoint: str
    as_of: datetime
    attempt_number: int


@dataclass(frozen=True, slots=True)
class ExhaustedMessage:
    message: StoredMessage


@dataclass(frozen=True, slots=True)
class NoMessages:
    pass


@dataclass(frozen=True, slots=True)
class CircuitOpen:
    pass


type ClaimSelection = ClaimedMessages | ExhaustedMessage | NoMessages | CircuitOpen


@dataclass(frozen=True, slots=True)
class PolledMessages:
    messages: tuple[StoredMessage, ...]
    through_checkpoint: str
    as_of: datetime
    preempt_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SettlementTrace:
    run_id: str
    through_checkpoint: str
    conclusion_kind: str
    outcome: str
    provider_trace_ids: tuple[str, ...] = ()
    provider_turns: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None

    def as_json(self, conclusion_message_id: UUID | None) -> dict[str, object]:
        value: dict[str, object] = {
            "run_id": _nonempty(self.run_id, "run id"),
            "through_checkpoint": _nonempty(
                self.through_checkpoint,
                "through checkpoint",
            ),
            "conclusion_message_id": (
                str(conclusion_message_id)
                if conclusion_message_id is not None
                else None
            ),
            "conclusion_kind": _nonempty(self.conclusion_kind, "conclusion kind"),
            "outcome": _nonempty(self.outcome, "conclusion outcome"),
        }
        if any(not item for item in self.provider_trace_ids):
            msg = "provider trace IDs must not be empty"
            raise ValueError(msg)
        if self.provider_trace_ids:
            value["provider_trace_ids"] = list(self.provider_trace_ids)
        metrics = {
            "provider_turns": self.provider_turns,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_ms": self.duration_ms,
        }
        for name, metric in metrics.items():
            if metric is not None:
                value[name] = _nonnegative(metric, name.replace("_", " "))
        return value


@dataclass(frozen=True, slots=True)
class Settlement:
    conclusion_message: StoredMessage | None
    more_input: bool
    already_settled: bool


@dataclass(frozen=True, slots=True)
class ControlSettlement:
    conclusion_message: StoredMessage | None
    already_processed: bool


@dataclass(frozen=True, slots=True)
class PendingControl:
    message_id: UUID
    control: Literal["stop", "pause", "resume"]
    requires_recovery_run: bool


class MessageStore:
    def __init__(self, engine: Database) -> None:
        self._engine = engine

    async def insert_waking(
        self,
        *,
        role: Literal["owner", "host"],
        text: str,
        source: str,
        source_conversation_id: str,
        source_message_id: str,
        created_at: datetime,
        message_id: UUID | None = None,
    ) -> InboundInsert:
        _nonempty(text, "message text")
        _nonempty(source, "message source")
        _nonempty(source_conversation_id, "source conversation id")
        _nonempty(source_message_id, "source message id")
        _aware(created_at, "message created_at")
        identifier = message_id or uuid4()
        values: dict[str, object] = {
            "id": identifier,
            "role": role,
            "text": text,
            "source": source,
            "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id,
            "created_at": created_at,
            "processed_at": None,
            "processing_attempts": 0,
            "processing_parked_at": None,
            "remembered_at": None,
            "trace": {},
        }
        async with self._engine.begin() as connection:
            result = await connection.execute(
                postgresql_insert(message)
                .values(**values)
                .on_conflict_do_nothing(
                    constraint="uq_message_source_identity",
                )
                .returning(*message.c)
            )
            row = result.mappings().one_or_none()
            if row is not None:
                return InboundInsert(_stored_message(row), inserted=True)
            existing = (
                (
                    await connection.execute(
                        select(message).where(
                            message.c.source == source,
                            message.c.source_message_id == source_message_id,
                        )
                    )
                )
                .mappings()
                .one()
            )
            stored = _stored_message(existing)
            identity_values = (
                stored.role,
                stored.text,
                stored.source_conversation_id,
                stored.created_at,
            )
            if identity_values != (role, text, source_conversation_id, created_at):
                msg = "source identity was reused for different message content"
                raise PersistenceDefect(msg)
            return InboundInsert(stored, inserted=False)

    async def message_by_id(self, message_id: UUID) -> StoredMessage | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(message).where(message.c.id == message_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _stored_message(row)

    async def claim(
        self,
        *,
        source_conversation_id: str,
        maximum_batch_size: int,
        maximum_attempts: int,
        as_of: datetime | None = None,
    ) -> ClaimSelection:
        _nonempty(source_conversation_id, "source conversation id")
        _positive(maximum_batch_size, "maximum batch size")
        _positive(maximum_attempts, "maximum attempts")
        claim_time = as_of or datetime.now(UTC)
        _aware(claim_time, "claim as_of")
        pending = (
            message.c.source_conversation_id == source_conversation_id,
            message.c.role.in_(("owner", "host")),
            message.c.processed_at.is_(None),
            message.c.processing_parked_at.is_(None),
        )
        async with self._engine.begin() as connection:
            parked = await connection.scalar(
                select(func.count())
                .select_from(message)
                .where(
                    message.c.role.in_(("owner", "host")),
                    message.c.processed_at.is_(None),
                    message.c.processing_parked_at.is_not(None),
                )
            )
            if parked:
                return CircuitOpen()

            recorded = await pending_thread_decision(connection, source_conversation_id)
            if recorded is not None:
                original_ids = tuple(UUID(str(value)) for value in recorded.input_ids)
                if len(original_ids) > maximum_batch_size:
                    raise PersistenceDefect(
                        "recorded model input exceeds the current claim bound"
                    )
                original_rows = (
                    (
                        await connection.execute(
                            select(message)
                            .where(message.c.id.in_(original_ids))
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .all()
                )
                by_id = {row["id"]: _stored_message(row) for row in original_rows}
                if set(by_id) != set(original_ids):
                    raise PersistenceDefect("recorded model input is missing")
                original_messages = tuple(by_id[value] for value in original_ids)
                if any(
                    row.source_conversation_id != source_conversation_id
                    or row.role not in {"owner", "host"}
                    or row.processed_at is not None
                    or row.processing_parked_at is not None
                    for row in original_messages
                ):
                    raise PersistenceDefect(
                        "recorded model input is no longer claimable"
                    )
                if str(recorded.through_checkpoint) != str(original_ids[-1]):
                    raise PersistenceDefect(
                        "recorded model checkpoint disagrees with original input"
                    )
                return ClaimedMessages(
                    claim_id=str(uuid4()),
                    route="scheduled_wake"
                    if original_messages[0].source == "schedule_wake"
                    else "interactive",
                    messages=original_messages,
                    through_checkpoint=str(recorded.through_checkpoint),
                    as_of=recorded.as_of,
                    attempt_number=original_messages[0].processing_attempts,
                )

            interactive = (message.c.source != "schedule_wake") & ~(
                (message.c.role == "owner")
                & (message.c.source == "discord")
                & (func.lower(func.btrim(message.c.text)) == "resume")
            )
            selected = (
                (
                    await connection.execute(
                        select(message)
                        .where(*pending, interactive)
                        .order_by(
                            case((message.c.role == "owner", 0), else_=1),
                            message.c.created_at,
                            message.c.id,
                        )
                        .limit(maximum_batch_size)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            route: ClaimRoute = "interactive"
            if not selected:
                selected = (
                    (
                        await connection.execute(
                            select(message)
                            .where(*pending, message.c.source == "schedule_wake")
                            .order_by(message.c.created_at, message.c.id)
                            .limit(1)
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .all()
                )
                route = "scheduled_wake"
            if not selected:
                return NoMessages()

            stored = list(map(_stored_message, selected))
            host_indexes = [
                index for index, value in enumerate(stored) if value.role == "host"
            ]
            if len(host_indexes) > 1:
                stored = stored[: host_indexes[1]]
            owner_ids = tuple(value.id for value in stored if value.role == "owner")
            recall_positions = tuple(
                str(
                    InitialReadDispatchLineage(
                        RunId("claim-recovery"), f"jarvis-recall:{value}"
                    ).position
                )
                for value in owner_ids
            )
            recall_scopes = tuple(
                canonical_json_bytes(
                    {"operation_id": f"jarvis-recall:{value}"}
                ).decode()
                for value in owner_ids
            )
            unknown_read = await connection.scalar(
                select(read_position.c.position)
                .where(
                    read_position.c.position.in_(recall_positions)
                    | read_position.c.position.in_(
                        select("model-decision:" + model_decision.c.decision_id).where(
                            model_decision.c.scope_key.in_(recall_scopes)
                        )
                    ),
                    read_position.c.state.in_(("dispatched", "uncertain")),
                )
                .limit(1)
            )
            unknown_recall = await connection.scalar(
                select(model_decision.c.decision_id)
                .where(
                    model_decision.c.scope_key.in_(recall_scopes),
                    model_decision.c.terminal.is_(None),
                )
                .limit(1)
            )
            if unknown_read is not None or unknown_recall is not None:
                await connection.execute(
                    update(message)
                    .where(message.c.id.in_(owner_ids))
                    .values(
                        processing_parked_at=claim_time,
                        trace=message.c.trace.concat(
                            {
                                "parking": {
                                    "reason_code": "paid_recall_uncertain",
                                    "parked_at": claim_time.isoformat(),
                                }
                            }
                        ),
                    )
                )
                return CircuitOpen()
            first = stored[0]
            if first.processing_attempts >= maximum_attempts:
                return ExhaustedMessage(first)
            attempt_number = cast(
                int,
                await connection.scalar(
                    update(message)
                    .where(message.c.id == first.id)
                    .values(processing_attempts=message.c.processing_attempts + 1)
                    .returning(message.c.processing_attempts)
                ),
            )
            stored[0] = _replace_attempts(stored[0], attempt_number)
            return ClaimedMessages(
                claim_id=str(uuid4()),
                route=route,
                messages=tuple(stored),
                through_checkpoint=str(stored[-1].id),
                as_of=claim_time,
                attempt_number=attempt_number,
            )

    async def poll(
        self,
        *,
        route: ClaimRoute,
        source_conversation_id: str,
        known_message_ids: tuple[UUID, ...],
        maximum_batch_size: int,
        include_host_inputs: bool = True,
        as_of: datetime | None = None,
    ) -> PolledMessages | None:
        if not known_message_ids:
            msg = "poll requires the claim's known message IDs"
            raise ValueError(msg)
        _positive(maximum_batch_size, "maximum batch size")
        poll_time = as_of or datetime.now(UTC)
        _aware(poll_time, "poll as_of")
        normalized = func.lower(func.btrim(message.c.text))
        pending = (
            message.c.source_conversation_id == source_conversation_id,
            message.c.role.in_(("owner", "host")),
            message.c.processed_at.is_(None),
            message.c.processing_parked_at.is_(None),
            message.c.id.not_in(known_message_ids),
            ~(
                (message.c.role == "owner")
                & (message.c.source == "discord")
                & (normalized == "resume")
            ),
        )
        async with self._engine.connect() as connection:
            if route == "scheduled_wake":
                query = select(message).where(
                    *pending,
                    message.c.source != "schedule_wake",
                )
            else:
                query = select(message).where(
                    *pending,
                    message.c.source != "schedule_wake",
                )
                if not include_host_inputs:
                    query = query.where(message.c.role == "owner")
            rows = (
                (
                    await connection.execute(
                        query.order_by(message.c.created_at, message.c.id).limit(
                            maximum_batch_size
                        )
                    )
                )
                .mappings()
                .all()
            )
        if not rows:
            return None
        values = tuple(map(_stored_message, rows))
        control = next(
            (
                value
                for value in values
                if value.role == "owner"
                and value.source == "discord"
                and value.text.strip().casefold() in {"stop", "pause"}
            ),
            None,
        )
        if control is not None:
            through = tuple(
                value
                for value in values[: values.index(control) + 1]
                if value.role == "owner"
            )
            return PolledMessages(
                messages=through,
                through_checkpoint=str(control.id),
                as_of=poll_time,
                preempt_reason=control.text.strip().casefold(),
            )
        if route == "scheduled_wake":
            return PolledMessages(
                messages=values,
                through_checkpoint=str(values[-1].id),
                as_of=poll_time,
                preempt_reason="interactive_input",
            )
        host_indexes = [
            index for index, value in enumerate(values) if value.role == "host"
        ]
        if len(host_indexes) > 1:
            values = values[: host_indexes[1]]
        return PolledMessages(
            messages=values,
            through_checkpoint=str(values[-1].id),
            as_of=poll_time,
        )

    async def settle(
        self,
        *,
        consumed_message_ids: tuple[UUID, ...],
        source_conversation_id: str,
        trace: SettlementTrace,
        conclusion_text: str | None,
        conclusion_message_id: UUID | None = None,
        settled_at: datetime | None = None,
    ) -> Settlement:
        if not consumed_message_ids or len(set(consumed_message_ids)) != len(
            consumed_message_ids
        ):
            msg = "settlement message IDs must be non-empty and unique"
            raise ValueError(msg)
        if conclusion_text is not None:
            _nonempty(conclusion_text, "conclusion text")
        if conclusion_text is None and conclusion_message_id is not None:
            msg = "a silent conclusion cannot have a message ID"
            raise ValueError(msg)
        settlement_time = settled_at or datetime.now(UTC)
        _aware(settlement_time, "settlement time")
        assistant_id = (
            conclusion_message_id or uuid4() if conclusion_text is not None else None
        )
        settlement_trace = trace.as_json(assistant_id)
        _bounded_trace({"settlement": settlement_trace})
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(consumed_message_ids))
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != len(consumed_message_ids):
                msg = "settlement references a missing message"
                raise PersistenceDefect(msg)
            stored_rows = tuple(map(_stored_message, rows))
            processed = [value.processed_at is not None for value in stored_rows]
            if all(processed):
                for value in stored_rows:
                    if value.trace.get("settlement") != settlement_trace:
                        msg = "settlement conflicts with the canonical conclusion"
                        raise PersistenceDefect(msg)
                conclusion = None
                if assistant_id is not None:
                    row = (
                        (
                            await connection.execute(
                                select(message).where(message.c.id == assistant_id)
                            )
                        )
                        .mappings()
                        .one()
                    )
                    conclusion = _stored_message(row)
                return Settlement(
                    conclusion_message=conclusion,
                    more_input=await _has_pending(
                        connection,
                        source_conversation_id,
                    ),
                    already_settled=True,
                )
            if any(processed):
                msg = "a settlement batch is only partly processed"
                raise PersistenceDefect(msg)
            if any(value.processing_parked_at is not None for value in stored_rows):
                msg = "a parked claim cannot be settled without operator repair"
                raise PersistenceDefect(msg)

            conclusion: StoredMessage | None = None
            if conclusion_text is not None:
                if assistant_id is None:
                    raise AssertionError
                result = await connection.execute(
                    insert(message)
                    .values(
                        id=assistant_id,
                        role="assistant",
                        text=conclusion_text,
                        source="discord",
                        source_conversation_id=source_conversation_id,
                        source_message_id=None,
                        created_at=settlement_time,
                        processed_at=settlement_time,
                        processing_attempts=0,
                        processing_parked_at=None,
                        remembered_at=None,
                        trace={},
                    )
                    .returning(*message.c)
                )
                conclusion = _stored_message(result.mappings().one())
            scheduled = tuple(
                value for value in stored_rows if value.source == "schedule_wake"
            )
            if scheduled:
                if len(scheduled) != 1 or assistant_id is None:
                    raise PersistenceDefect(
                        "scheduled wake requires one visible conclusion"
                    )
                source_message_id = scheduled[0].source_message_id
                if source_message_id is None:
                    raise PersistenceDefect("scheduled wake has no action identity")
                try:
                    schedule_action_id = UUID(source_message_id)
                except ValueError as exc:
                    raise PersistenceDefect(
                        "scheduled wake action identity is invalid"
                    ) from exc
                from jarvis.actions import finish_schedule_conclusion

                await finish_schedule_conclusion(
                    connection,
                    action_id=schedule_action_id,
                    conclusion_message_id=assistant_id,
                    recorded_at=settlement_time,
                )
            await connection.execute(
                update(message)
                .where(message.c.id.in_(consumed_message_ids))
                .values(
                    processed_at=settlement_time,
                    trace=message.c.trace.concat({"settlement": settlement_trace}),
                )
            )
            return Settlement(
                conclusion_message=conclusion,
                more_input=await _has_pending(connection, source_conversation_id),
                already_settled=False,
            )

    async def park(
        self,
        *,
        claimed_message_ids: tuple[UUID, ...],
        reason_code: str,
        parked_at: datetime | None = None,
    ) -> bool:
        if not claimed_message_ids or len(set(claimed_message_ids)) != len(
            claimed_message_ids
        ):
            msg = "park message IDs must be non-empty and unique"
            raise ValueError(msg)
        if (
            len(reason_code) > MAX_REASON_CODE_LENGTH
            or _REASON_CODE.fullmatch(reason_code) is None
        ):
            msg = "park reason must be a bounded lowercase reason code"
            raise ValueError(msg)
        park_time = parked_at or datetime.now(UTC)
        _aware(park_time, "park time")
        parking_trace = {
            "reason_code": reason_code,
            "parked_at": park_time.isoformat(),
        }
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(claimed_message_ids))
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != len(claimed_message_ids):
                msg = "park references a missing message"
                raise PersistenceDefect(msg)
            stored_rows = tuple(map(_stored_message, rows))
            if any(value.processed_at is not None for value in stored_rows):
                msg = "a processed message cannot be parked"
                raise PersistenceDefect(msg)
            already_parked = [
                value.processing_parked_at is not None for value in stored_rows
            ]
            if all(already_parked):
                return False
            if any(already_parked):
                msg = "a claim batch is only partly parked"
                raise PersistenceDefect(msg)
            await connection.execute(
                update(message)
                .where(message.c.id.in_(claimed_message_ids))
                .values(
                    processing_parked_at=park_time,
                    trace=message.c.trace.concat({"parking": parking_trace}),
                )
            )
            return True

    async def clear_parked(
        self,
        *,
        message_ids: tuple[UUID, ...],
    ) -> None:
        if not message_ids or len(set(message_ids)) != len(message_ids):
            msg = "operator release IDs must be non-empty and unique"
            raise ValueError(msg)
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    select(message.c.id, message.c.processing_parked_at)
                    .where(message.c.id.in_(message_ids))
                    .with_for_update()
                )
            ).all()
            if len(rows) != len(message_ids):
                msg = "operator release references a missing message"
                raise PersistenceDefect(msg)
            if any(row.processing_parked_at is None for row in rows):
                msg = "operator release references an unparked message"
                raise PersistenceDefect(msg)
            await connection.execute(
                update(message)
                .where(message.c.id.in_(message_ids))
                .values(processing_parked_at=None)
            )

    async def circuit_is_open(self) -> bool:
        async with self._engine.connect() as connection:
            count = await connection.scalar(
                select(func.count())
                .select_from(message)
                .where(
                    message.c.role.in_(("owner", "host")),
                    message.c.processed_at.is_(None),
                    message.c.processing_parked_at.is_not(None),
                )
            )
            return bool(count)

    async def has_pending_work(self, *, source_conversation_id: str) -> bool:
        _nonempty(source_conversation_id, "source conversation id")
        if await self.circuit_is_open():
            return False
        async with self._engine.connect() as connection:
            return await _has_pending(connection, source_conversation_id)

    async def oldest_foreground(
        self,
        *,
        source_conversation_id: str,
    ) -> StoredMessage | None:
        _nonempty(source_conversation_id, "source conversation id")
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(message)
                        .where(
                            message.c.source_conversation_id == source_conversation_id,
                            message.c.role.in_(("owner", "host")),
                            message.c.source != "schedule_wake",
                            message.c.processed_at.is_(None),
                            message.c.processing_parked_at.is_(None),
                        )
                        .order_by(
                            case((message.c.role == "owner", 0), else_=1),
                            message.c.created_at,
                            message.c.id,
                        )
                        .limit(1)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _stored_message(row) if row is not None else None

    async def record_admission_deferral(
        self,
        *,
        source_conversation_id: str,
        reset_at: datetime,
        now: datetime | None = None,
    ) -> StoredMessage | None:
        _nonempty(source_conversation_id, "source conversation id")
        _aware(reset_at, "admission reset time")
        notice_time = now or datetime.now(UTC)
        _aware(notice_time, "admission notice time")
        if (reset_at - notice_time).total_seconds() < 60:
            return None
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(message)
                        .where(
                            message.c.source_conversation_id == source_conversation_id,
                            message.c.role.in_(("owner", "host")),
                            message.c.source != "schedule_wake",
                            message.c.processed_at.is_(None),
                            message.c.processing_parked_at.is_(None),
                        )
                        .order_by(
                            case((message.c.role == "owner", 0), else_=1),
                            message.c.created_at,
                            message.c.id,
                        )
                        .limit(1)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            waking = _stored_message(row)
            canonical_reset = reset_at.astimezone(UTC).isoformat()
            notice_id = uuid5(
                NAMESPACE_URL,
                f"jarvis-admission-delay-v1:{waking.id}:{canonical_reset}",
            )
            notice_text = (
                "Codex capacity is temporarily unavailable. "
                f"I will retry after {canonical_reset}."
            )
            result = await connection.execute(
                postgresql_insert(message)
                .values(
                    id=notice_id,
                    role="assistant",
                    text=notice_text,
                    source="discord",
                    source_conversation_id=source_conversation_id,
                    source_message_id=None,
                    created_at=notice_time,
                    processed_at=notice_time,
                    processing_attempts=0,
                    processing_parked_at=None,
                    remembered_at=None,
                    trace={},
                )
                .on_conflict_do_nothing(index_elements=(message.c.id,))
                .returning(*message.c)
            )
            notice_row = result.mappings().one_or_none()
            if notice_row is None:
                notice_row = (
                    (
                        await connection.execute(
                            select(message).where(message.c.id == notice_id)
                        )
                    )
                    .mappings()
                    .one()
                )
                existing = _stored_message(notice_row)
                if (
                    existing.role != "assistant"
                    or existing.text != notice_text
                    or existing.source_conversation_id != source_conversation_id
                ):
                    msg = "admission notice identity conflicts with canonical state"
                    raise PersistenceDefect(msg)
            metadata = {
                "message_id": str(notice_id),
                "reset_at": canonical_reset,
            }
            _bounded_trace({"admission_delay_notice": metadata})
            await connection.execute(
                update(message)
                .where(message.c.id == waking.id)
                .values(
                    trace=message.c.trace.concat({"admission_delay_notice": metadata})
                )
            )
            return _stored_message(notice_row)

    async def latest_discord_owner_source_message_id(
        self,
        *,
        source_conversation_id: str,
    ) -> str | None:
        _nonempty(source_conversation_id, "source conversation id")
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                select(message.c.source_message_id)
                .where(
                    message.c.role == "owner",
                    message.c.source == "discord",
                    message.c.source_conversation_id == source_conversation_id,
                    message.c.source_message_id.is_not(None),
                )
                .order_by(message.c.created_at.desc(), message.c.id.desc())
                .limit(1)
            )
        return cast(str | None, value)

    async def pending_controls(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[PendingControl, ...]:
        _nonempty(source_conversation_id, "source conversation id")
        _positive(limit, "control limit")
        normalized = func.lower(func.btrim(message.c.text))
        older = message.alias("older_waking_message")
        older_exists = (
            select(1)
            .select_from(older)
            .where(
                older.c.source_conversation_id == message.c.source_conversation_id,
                older.c.role.in_(("owner", "host")),
                older.c.processed_at.is_(None),
                older.c.processing_parked_at.is_(None),
                (older.c.created_at < message.c.created_at)
                | (
                    (older.c.created_at == message.c.created_at)
                    & (older.c.id < message.c.id)
                ),
            )
            .exists()
        )
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        message.c.id,
                        normalized.label("control"),
                        ((message.c.processing_attempts > 0) | older_exists).label(
                            "requires_recovery_run"
                        ),
                    )
                    .where(
                        message.c.role == "owner",
                        message.c.source == "discord",
                        message.c.source_conversation_id == source_conversation_id,
                        message.c.processed_at.is_(None),
                        message.c.processing_parked_at.is_(None),
                        normalized.in_(("stop", "pause", "resume")),
                    )
                    .order_by(message.c.created_at, message.c.id)
                    .limit(limit)
                )
            ).all()
        return tuple(
            PendingControl(
                message_id=cast(UUID, row.id),
                control=cast(Literal["stop", "pause", "resume"], row.control),
                requires_recovery_run=cast(bool, row.requires_recovery_run),
            )
            for row in rows
        )

    async def record_run_metrics(
        self,
        *,
        consumed_message_ids: tuple[UUID, ...],
        run_id: str,
        provider_turns: int,
        input_tokens: int | None,
        output_tokens: int | None,
        duration_seconds: float,
    ) -> None:
        if not consumed_message_ids or len(set(consumed_message_ids)) != len(
            consumed_message_ids
        ):
            msg = "metrics message IDs must be non-empty and unique"
            raise ValueError(msg)
        _nonempty(run_id, "metrics run id")
        metrics: dict[str, object] = {
            "provider_turns": _nonnegative(provider_turns, "provider turns"),
            "duration_ms": _duration_ms(duration_seconds),
        }
        if input_tokens is not None:
            metrics["input_tokens"] = _nonnegative(input_tokens, "input tokens")
        if output_tokens is not None:
            metrics["output_tokens"] = _nonnegative(output_tokens, "output tokens")
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(consumed_message_ids))
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != len(consumed_message_ids):
                msg = "run metrics reference a missing message"
                raise PersistenceDefect(msg)
            stored_rows = tuple(map(_stored_message, rows))
            for value in stored_rows:
                settlement = value.trace.get("settlement")
                if not isinstance(settlement, dict):
                    msg = "run metrics do not match the canonical settlement"
                    raise PersistenceDefect(msg)
                typed_settlement = cast(dict[str, object], settlement)
                if typed_settlement.get("run_id") != run_id:
                    msg = "run metrics do not match the canonical settlement"
                    raise PersistenceDefect(msg)
                present = {name: typed_settlement.get(name) for name in metrics}
                if (
                    any(item is not None for item in present.values())
                    and present != metrics
                ):
                    msg = "run metrics conflict with the canonical settlement"
                    raise PersistenceDefect(msg)
                if present == metrics:
                    continue
                completed = {**typed_settlement, **metrics}
                _bounded_trace({"settlement": completed})
                await connection.execute(
                    update(message)
                    .where(message.c.id == value.id)
                    .values(trace=message.c.trace.concat({"settlement": completed}))
                )

    async def record_recall(
        self,
        *,
        message_id: UUID,
        candidate_identities: tuple[MemoryIdentity, ...],
        selected_identities: tuple[MemoryIdentity, ...],
        run_id: str,
        terminal_outcome: str,
        provider_turns: int,
        input_tokens: int | None,
        output_tokens: int | None,
        duration_seconds: float,
    ) -> None:
        if len(candidate_identities) > 160 or len(set(candidate_identities)) != len(
            candidate_identities
        ):
            raise ValueError("recall candidate IDs must be unique and bounded")
        if len(selected_identities) > 20 or len(set(selected_identities)) != len(
            selected_identities
        ):
            raise ValueError("recall selected IDs must be unique and bounded")
        summary: dict[str, object] = {
            "run_id": _nonempty(run_id, "recall run id"),
            "provider_turns": _nonnegative(provider_turns, "provider turns"),
            "terminal_outcome": _nonempty(
                terminal_outcome,
                "recall terminal outcome",
            ),
            "duration_ms": _duration_ms(duration_seconds),
        }
        if input_tokens is not None:
            summary["input_tokens"] = _nonnegative(input_tokens, "input tokens")
        if output_tokens is not None:
            summary["output_tokens"] = _nonnegative(output_tokens, "output tokens")

        def identities(values: tuple[MemoryIdentity, ...]) -> list[dict[str, str]]:
            return [
                {"table_kind": item.table_kind, "id": str(item.id)} for item in values
            ]

        recall_trace = {
            "candidate_memory_ids": identities(candidate_identities),
            "selected_memory_ids": identities(selected_identities),
            "run": summary,
        }
        _bounded_trace({"recaller": recall_trace})
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id == message_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise PersistenceDefect("recall trace references a missing message")
            stored = _stored_message(row)
            if stored.role != "owner":
                raise PersistenceDefect("recall trace target is not owner-authored")
            updated_trace = {**stored.trace, "recaller": recall_trace}
            _bounded_trace(updated_trace)
            await connection.execute(
                update(message)
                .where(message.c.id == message_id)
                .values(trace=message.c.trace.concat({"recaller": recall_trace}))
            )

    async def record_rememberer_attempt(
        self,
        *,
        message_ids: tuple[UUID, ...],
        run_id: str,
        terminal_outcome: str,
        provider_turns: int | None,
        input_tokens: int | None,
        output_tokens: int | None,
        duration_seconds: float | None,
    ) -> None:
        if (
            not message_ids
            or len(message_ids) > MAXIMUM_BATCH_SIZE
            or len(set(message_ids)) != len(message_ids)
        ):
            raise ValueError("rememberer attempt target IDs must be unique and bounded")
        if len(run_id) > 256:
            raise ValueError("rememberer run id exceeds its bound")
        if (
            len(terminal_outcome) > MAX_REASON_CODE_LENGTH
            or _REASON_CODE.fullmatch(terminal_outcome) is None
        ):
            raise ValueError("rememberer terminal outcome is invalid")
        summary: dict[str, object] = {
            "run_id": _nonempty(run_id, "rememberer run id"),
            "terminal_outcome": terminal_outcome,
        }
        for name, value in (
            ("provider_turns", provider_turns),
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
        ):
            if value is not None:
                summary[name] = _nonnegative(value, name.replace("_", " "))
        if duration_seconds is not None:
            summary["duration_ms"] = _duration_ms(duration_seconds)
        rememberer_trace: dict[str, object] = {
            "created_memory_ids": [],
            "run": summary,
        }
        _bounded_trace({"rememberer": rememberer_trace})

        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(message_ids))
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != len(message_ids):
                raise PersistenceDefect(
                    "rememberer attempt references a missing message"
                )
            for row in rows:
                stored = _stored_message(row)
                if (
                    stored.role != "owner"
                    or stored.processed_at is None
                    or stored.remembered_at is not None
                ):
                    raise PersistenceDefect("rememberer attempt target is ineligible")
                _bounded_trace({**stored.trace, "rememberer": rememberer_trace})
            await connection.execute(
                update(message)
                .where(message.c.id.in_(message_ids))
                .values(trace=message.c.trace.concat({"rememberer": rememberer_trace}))
            )

    async def pending_delivery(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        _positive(limit, "delivery limit")
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(
                            message.c.role == "assistant",
                            message.c.source_conversation_id == source_conversation_id,
                            message.c.source_message_id.is_(None),
                        )
                        .order_by(message.c.created_at, message.c.id)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_message, rows))

    async def mark_delivered(
        self,
        *,
        message_id: UUID,
        source_message_id: str,
    ) -> None:
        _nonempty(source_message_id, "delivered source message id")
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id == message_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                msg = "delivery references a missing message"
                raise PersistenceDefect(msg)
            stored = _stored_message(row)
            if stored.role != "assistant":
                msg = "only assistant messages can be delivered"
                raise PersistenceDefect(msg)
            if stored.source_message_id is not None:
                if stored.source_message_id != source_message_id:
                    msg = "delivery conflicts with the stored source message id"
                    raise PersistenceDefect(msg)
                return
            await connection.execute(
                update(message)
                .where(message.c.id == message_id)
                .values(source_message_id=source_message_id)
            )

    async def settle_recovered_control(
        self,
        *,
        message_id: UUID,
        source_conversation_id: str,
        control: Literal["stop", "pause"],
        settled_at: datetime | None = None,
    ) -> ControlSettlement:
        settlement_time = settled_at or datetime.now(UTC)
        _aware(settlement_time, "recovered control settlement time")
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id == message_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                msg = "recovered control references a missing message"
                raise PersistenceDefect(msg)
            control_message = _stored_message(row)
            if (
                control_message.role != "owner"
                or control_message.source != "discord"
                or control_message.source_conversation_id != source_conversation_id
                or control_message.text.strip().casefold() != control
            ):
                msg = "recovered control does not match canonical owner input"
                raise PersistenceDefect(msg)
            if control_message.processed_at is not None:
                return ControlSettlement(None, already_processed=True)
            if control_message.processing_parked_at is not None:
                msg = "a parked control cannot be host-settled"
                raise PersistenceDefect(msg)

            prefix_rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(
                            message.c.source_conversation_id == source_conversation_id,
                            message.c.role.in_(("owner", "host")),
                            message.c.processed_at.is_(None),
                            message.c.processing_parked_at.is_(None),
                            (message.c.created_at < control_message.created_at)
                            | (
                                (message.c.created_at == control_message.created_at)
                                & (message.c.id <= control_message.id)
                            ),
                        )
                        .order_by(message.c.created_at, message.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            prefix = tuple(map(_stored_message, prefix_rows))
            if not prefix or prefix[-1].id != message_id:
                msg = "recovered control prefix is inconsistent"
                raise PersistenceDefect(msg)
            prefix_ids = tuple(value.id for value in prefix)
            conclusion_id = uuid5(
                NAMESPACE_URL,
                "jarvis-recovered-control-v1:"
                + ",".join(map(str, prefix_ids))
                + f":{control}",
            )
            conclusion_text = "Paused." if control == "pause" else "Stopped."
            settlement = SettlementTrace(
                run_id=f"host-recovered-control-{message_id}",
                through_checkpoint=str(message_id),
                conclusion_kind="stopped",
                outcome=f"owner_{control}",
            ).as_json(conclusion_id)
            host_inputs = tuple(value for value in prefix if value.role == "host")
            for index, waking in enumerate(host_inputs):
                visibility_id = uuid5(
                    NAMESPACE_URL,
                    f"jarvis-recovered-host-v1:{waking.id}:{message_id}:{control}",
                )
                await connection.execute(
                    insert(message).values(
                        id=visibility_id,
                        role="assistant",
                        text=_host_visibility_text(waking),
                        source="discord",
                        source_conversation_id=source_conversation_id,
                        source_message_id=None,
                        created_at=settlement_time + timedelta(microseconds=index),
                        processed_at=settlement_time,
                        processing_attempts=0,
                        processing_parked_at=None,
                        remembered_at=None,
                        trace={},
                    )
                )
                if waking.source == "schedule_wake":
                    if waking.source_message_id is None:
                        raise PersistenceDefect("scheduled wake has no action identity")
                    try:
                        schedule_action_id = UUID(waking.source_message_id)
                    except ValueError as exc:
                        raise PersistenceDefect(
                            "scheduled wake action identity is invalid"
                        ) from exc
                    from jarvis.actions import finish_schedule_conclusion

                    await finish_schedule_conclusion(
                        connection,
                        action_id=schedule_action_id,
                        conclusion_message_id=visibility_id,
                        recorded_at=settlement_time,
                    )
            result = await connection.execute(
                insert(message)
                .values(
                    id=conclusion_id,
                    role="assistant",
                    text=conclusion_text,
                    source="discord",
                    source_conversation_id=source_conversation_id,
                    source_message_id=None,
                    created_at=settlement_time
                    + timedelta(microseconds=len(host_inputs)),
                    processed_at=settlement_time,
                    processing_attempts=0,
                    processing_parked_at=None,
                    remembered_at=None,
                    trace={},
                )
                .returning(*message.c)
            )
            await connection.execute(
                update(message)
                .where(message.c.id.in_(prefix_ids))
                .values(
                    processed_at=settlement_time,
                    trace=message.c.trace.concat({"settlement": settlement}),
                )
            )
            return ControlSettlement(
                _stored_message(result.mappings().one()),
                already_processed=False,
            )

    async def settle_control(
        self,
        *,
        message_id: UUID,
        source_conversation_id: str,
        control: Literal["stop", "pause", "resume"],
        settled_at: datetime | None = None,
    ) -> ControlSettlement:
        settlement_time = settled_at or datetime.now(UTC)
        _aware(settlement_time, "control settlement time")
        conclusion_id = uuid5(
            NAMESPACE_URL,
            f"jarvis-idle-control-v1:{message_id}:{control}",
        )
        conclusion_text = {
            "stop": "Stopped.",
            "pause": "Paused.",
            "resume": "Resumed.",
        }[control]
        settlement = SettlementTrace(
            run_id=f"host-control-{message_id}",
            through_checkpoint=str(message_id),
            conclusion_kind="control",
            outcome=f"owner_{control}",
        ).as_json(conclusion_id)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id == message_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                msg = "control settlement references a missing message"
                raise PersistenceDefect(msg)
            waking = _stored_message(row)
            if (
                waking.role != "owner"
                or waking.source != "discord"
                or waking.source_conversation_id != source_conversation_id
                or waking.text.strip().casefold() != control
            ):
                msg = "control settlement does not match canonical owner input"
                raise PersistenceDefect(msg)
            if waking.processed_at is not None:
                return ControlSettlement(None, already_processed=True)
            result = await connection.execute(
                insert(message)
                .values(
                    id=conclusion_id,
                    role="assistant",
                    text=conclusion_text,
                    source="discord",
                    source_conversation_id=source_conversation_id,
                    source_message_id=None,
                    created_at=settlement_time,
                    processed_at=settlement_time,
                    processing_attempts=0,
                    processing_parked_at=None,
                    remembered_at=None,
                    trace={},
                )
                .returning(*message.c)
            )
            await connection.execute(
                update(message)
                .where(message.c.id == message_id)
                .values(
                    processed_at=settlement_time,
                    trace=message.c.trace.concat({"settlement": settlement}),
                )
            )
            return ControlSettlement(
                _stored_message(result.mappings().one()),
                already_processed=False,
            )


async def _has_pending(
    connection: AsyncConnection,
    source_conversation_id: str,
) -> bool:
    count = await connection.scalar(
        select(func.count())
        .select_from(message)
        .where(
            message.c.source_conversation_id == source_conversation_id,
            message.c.role.in_(("owner", "host")),
            message.c.processed_at.is_(None),
            message.c.processing_parked_at.is_(None),
        )
    )
    return bool(count)


def _stored_message(row: RowMapping) -> StoredMessage:
    return StoredMessage(
        id=cast(UUID, row["id"]),
        role=cast(MessageRole, row["role"]),
        text=cast(str, row["text"]),
        source=cast(str, row["source"]),
        source_conversation_id=cast(str, row["source_conversation_id"]),
        source_message_id=cast(str | None, row["source_message_id"]),
        created_at=cast(datetime, row["created_at"]),
        processed_at=cast(datetime | None, row["processed_at"]),
        processing_attempts=cast(int, row["processing_attempts"]),
        processing_parked_at=cast(datetime | None, row["processing_parked_at"]),
        remembered_at=cast(datetime | None, row["remembered_at"]),
        trace=cast(dict[str, object], row["trace"]),
    )


def _replace_attempts(value: StoredMessage, attempt_number: int) -> StoredMessage:
    return StoredMessage(
        id=value.id,
        role=value.role,
        text=value.text,
        source=value.source,
        source_conversation_id=value.source_conversation_id,
        source_message_id=value.source_message_id,
        created_at=value.created_at,
        processed_at=value.processed_at,
        processing_attempts=attempt_number,
        processing_parked_at=value.processing_parked_at,
        remembered_at=value.remembered_at,
        trace=value.trace,
    )


def _host_visibility_text(waking: StoredMessage) -> str:
    return render_host_fallback(
        source=waking.source,
        text=waking.text,
        maximum_characters=MAX_DISCORD_MESSAGE_CHARACTERS,
    )


def host_safe_text(waking: StoredMessage) -> str:
    if waking.source != "action":
        return waking.text
    return waking.text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)[0]


def render_host_fallback(
    *,
    source: str,
    text: str,
    maximum_characters: int,
    suffix: str | None = None,
) -> str:
    if source not in {"action", "schedule_wake"}:
        raise ValueError("host fallback requires an action or scheduled wake")
    if type(maximum_characters) is not int or maximum_characters <= 0:
        raise ValueError("host fallback bound must be a positive integer")
    safe_text = (
        text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)[0]
        if source == "action"
        else text
    )
    prefix = "Reminder: " if source == "schedule_wake" else "Action update: "
    tail = f"\n{suffix}" if suffix is not None else ""
    available = maximum_characters - len(tail)
    fallback = prefix + safe_text
    if len(fallback) > available:
        fallback = fallback[: max(0, available - 1)] + "…"
    return fallback + tail


def _bounded_trace(value: dict[str, object]) -> None:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(encoded) > MAX_TRACE_BYTES:
        msg = "message trace exceeds its private-data bound"
        raise ValueError(msg)


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{name} must be timezone-aware"
        raise ValueError(msg)


def _nonempty(value: str, name: str) -> str:
    if not value:
        msg = f"{name} must not be empty"
        raise ValueError(msg)
    return value


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        msg = f"{name} must be a positive integer"
        raise ValueError(msg)
    return value


def _nonnegative(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        msg = f"{name} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _duration_ms(value: float) -> int:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        msg = "duration must be a non-negative number"
        raise ValueError(msg)
    return round(value * 1_000)

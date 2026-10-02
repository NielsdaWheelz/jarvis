from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy import RowMapping, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import (
    action,
    control_sequence,
    message,
    native_attempt,
    native_invocation,
)
from jarvis.memory import MemoryIdentity, MemoryTableKind
from jarvis.ownership import Database, lock_conversation
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
    request_state: str | None
    wait_reason: str | None
    control_kind: str | None


@dataclass(frozen=True, slots=True)
class InboundInsert:
    message: StoredMessage
    inserted: bool


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
        control_kind: Literal["stop", "pause", "resume"] | None = None,
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
            "request_state": "pending" if role == "owner" else None,
            "wait_reason": None,
            "trace": {},
        }
        async with self._engine.begin() as connection:
            await lock_conversation(connection, source_conversation_id)
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
                if control_kind is not None:
                    if role != "owner" or text != control_kind:
                        raise PersistenceDefect("control must be exact owner input")
                    await self._apply_control(connection, row, control_kind)
                    row = (
                        (
                            await connection.execute(
                                select(message).where(message.c.id == identifier)
                            )
                        )
                        .mappings()
                        .one()
                    )
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

    async def _apply_control(
        self, connection: AsyncConnection, control: RowMapping, kind: str
    ) -> None:
        scope = control["source_conversation_id"]
        if kind == "resume":
            previous = (
                await connection.execute(
                    select(message.c.control_targets)
                    .where(
                        message.c.source_conversation_id == scope,
                        message.c.control_kind.in_(("stop", "pause")),
                    )
                    .order_by(message.c.control_sequence.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            targets = tuple(previous or ())
        else:
            targets = tuple(
                (
                    await connection.execute(
                        select(message.c.id)
                        .where(
                            message.c.source_conversation_id == scope,
                            message.c.role == "owner",
                            message.c.id != control["id"],
                            message.c.control_kind.is_(None),
                            message.c.request_state.in_(("pending", "waiting")),
                        )
                        .order_by(message.c.id)
                        .with_for_update()
                    )
                ).scalars()
            )
        if targets:
            await connection.execute(
                select(message.c.id)
                .where(message.c.id.in_(targets))
                .order_by(message.c.id)
                .with_for_update()
            )
        attempts = tuple(
            (
                await connection.execute(
                    select(native_attempt.c.id)
                    .where(
                        native_attempt.c.conversation_id == scope,
                        native_attempt.c.product_outcome.is_(None),
                    )
                    .order_by(native_attempt.c.id)
                    .with_for_update()
                )
            ).scalars()
        )
        if attempts:
            await connection.execute(
                select(native_invocation.c.id)
                .where(native_invocation.c.attempt_id.in_(attempts))
                .order_by(native_invocation.c.id)
                .with_for_update()
            )
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id.in_(attempts))
                .values(fenced_at=func.coalesce(native_attempt.c.fenced_at, func.now()))
            )
        timestamp = datetime.now(UTC)
        if kind == "resume":
            if targets:
                await connection.execute(
                    update(message)
                    .where(
                        message.c.id.in_(targets),
                        message.c.request_state == "stopped",
                    )
                    .values(
                        request_state="pending", wait_reason=None, processed_at=None
                    )
                )
            text = (
                "resumed. stopped approvals need fresh approval; "
                "entered actions retain their recorded outcome."
            )
        else:
            if targets:
                await connection.execute(
                    update(message)
                    .where(message.c.id.in_(targets))
                    .values(
                        request_state="stopped",
                        wait_reason=None,
                        processed_at=timestamp,
                    )
                )
                rows = (
                    (
                        await connection.execute(
                            select(action.c.id)
                            .where(
                                action.c.origin_message_id.in_(targets),
                                action.c.attempts == 0,
                                action.c.status.in_(
                                    ("queued", "awaiting_approval", "executing")
                                ),
                            )
                            .order_by(action.c.id)
                            .with_for_update()
                        )
                    )
                    .scalars()
                    .all()
                )
                if rows:
                    await connection.execute(
                        update(action)
                        .where(action.c.id.in_(rows))
                        .values(
                            status="cancelled",
                            completed_at=timestamp,
                            decided_at=func.coalesce(action.c.decided_at, timestamp),
                            result={
                                "type": "action_cancelled_v1",
                                "reason_code": "owner_stopped",
                            },
                        )
                    )
            text = (
                "paused."
                if kind == "pause"
                else "stopped. actions already dispatched may still finish; "
                "their outcomes will be retained."
            )
        sequence = await connection.scalar(control_sequence.next_value())
        await connection.execute(
            update(message)
            .where(message.c.id == control["id"])
            .values(
                control_kind=kind,
                control_sequence=sequence,
                control_targets=list(targets),
                request_state="completed",
                processed_at=timestamp,
            )
        )
        await connection.execute(
            postgresql_insert(message).values(
                id=uuid5(control["id"], "control-conclusion"),
                role="assistant",
                text=text,
                source="native_control",
                source_conversation_id=scope,
                processed_at=timestamp,
                trace={
                    "control_message_id": str(control["id"]),
                    "control_sequence": sequence,
                },
            )
        )

    async def pending_inputs(
        self,
        *,
        source_conversation_id: str,
        limit: int,
        exclude_ids: tuple[UUID, ...] = (),
        scheduled: bool | None = None,
    ) -> tuple[StoredMessage, ...]:
        live = or_(message.c.role == "owner", message.c.role == "host")
        pending = or_(
            message.c.request_state == "pending",
            (message.c.role == "host") & message.c.processed_at.is_(None),
        )
        query = select(message).where(
            message.c.source_conversation_id == source_conversation_id,
            live,
            pending,
            message.c.control_kind.is_(None),
            message.c.processing_parked_at.is_(None),
            message.c.id.not_in(exclude_ids),
        )
        if scheduled is not None:
            query = query.where(
                message.c.source == "schedule_wake"
                if scheduled
                else message.c.source != "schedule_wake"
            )
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        query.order_by(message.c.created_at, message.c.id).limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(map(_stored_message, rows))

    async def paused(self, source_conversation_id: str) -> bool:
        async with self._engine.connect() as connection:
            kind = await connection.scalar(
                select(message.c.control_kind)
                .where(
                    message.c.source_conversation_id == source_conversation_id,
                    message.c.control_kind.is_not(None),
                )
                .order_by(message.c.control_sequence.desc())
                .limit(1)
            )
        return kind in {"stop", "pause"}

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

    async def recall_selection(
        self, message_id: UUID
    ) -> tuple[MemoryIdentity, ...] | None:
        stored = await self.message_by_id(message_id)
        if stored is None or stored.role != "owner":
            raise PersistenceDefect("recall selection references no owner input")
        value = stored.trace.get("recaller")
        if value is None:
            return None
        if not isinstance(value, dict):
            raise PersistenceDefect("recorded recall selection is invalid")
        value = cast(dict[str, object], value)
        identities = value.get("selected_memory_ids")
        if not isinstance(identities, list):
            raise PersistenceDefect("recorded recall selection is invalid")
        selected: list[MemoryIdentity] = []
        for item in cast(list[object], identities):
            if not isinstance(item, dict):
                raise PersistenceDefect("recorded memory identity is invalid")
            item = cast(dict[str, object], item)
            if set(item) != {"table_kind", "id"} or item["table_kind"] not in {
                "memory_log",
                "memory_summary",
            }:
                raise PersistenceDefect("recorded memory identity is invalid")
            selected.append(
                MemoryIdentity(
                    cast(MemoryTableKind, item["table_kind"]),
                    UUID(cast(str, item["id"])),
                )
            )
        return tuple(selected)

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
        request_state=row["request_state"],
        wait_reason=row["wait_reason"],
        control_kind=row["control_kind"],
    )


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

"""Host-owned raw-memory persistence and rememberer retry selection."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, and_, func, insert, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from jarvis.db import memory_log, memory_summary, message

MemoryTableKind = Literal["memory_log", "memory_summary"]

_MAX_TRACE_BYTES = 16_384
_MAX_MEMORY_TEXT_BYTES = 8_000
_MAX_REMEMBERED_MEMORIES = 20
_MAX_RUN_ID_CHARACTERS = 256
_MAX_PROVIDER_TRACE_IDS = 16
_MAX_PROVIDER_TRACE_ID_CHARACTERS = 256
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----",
    re.IGNORECASE,
)
_KNOWN_TOKEN_PREFIX = re.compile(
    r"(?:"
    r"\bsk-[A-Za-z0-9_-]{16,}"
    r"|\b(?:sk|rk)_live_[A-Za-z0-9]{16,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{16,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{16,}"
    r"|\bglpat-[A-Za-z0-9_-]{16,}"
    r"|\bxox[baprs]-[A-Za-z0-9-]{16,}"
    r"|\bAIza[A-Za-z0-9_-]{20,}"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    r")",
)


class MemoryPersistenceDefect(RuntimeError):
    """Canonical memory or rememberer-target state is inconsistent."""


@dataclass(frozen=True, slots=True)
class MemoryIdentity:
    table_kind: MemoryTableKind
    id: UUID

    def __post_init__(self) -> None:
        if self.table_kind not in {"memory_log", "memory_summary"}:
            raise ValueError("memory table kind is not canonical")


@dataclass(frozen=True, slots=True)
class StoredRawMemory:
    id: UUID
    text: str
    created_at: datetime
    embedding: tuple[float, ...] | None

    @property
    def identity(self) -> MemoryIdentity:
        return MemoryIdentity("memory_log", self.id)


@dataclass(frozen=True, slots=True)
class StoredMemorySummary:
    id: UUID
    text: str
    source_memory_ids: tuple[UUID, ...]
    created_at: datetime
    embedding: tuple[float, ...] | None

    @property
    def identity(self) -> MemoryIdentity:
        return MemoryIdentity("memory_summary", self.id)


type StoredMemory = StoredRawMemory | StoredMemorySummary


@dataclass(frozen=True, slots=True)
class SettlementIdentity:
    run_id: str
    through_checkpoint: str
    conclusion_message_id: str | None
    conclusion_kind: str
    outcome: str

    def as_json(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "through_checkpoint": self.through_checkpoint,
            "conclusion_message_id": self.conclusion_message_id,
            "conclusion_kind": self.conclusion_kind,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class RemembererTarget:
    id: UUID
    text: str
    source: str
    source_conversation_id: str
    source_message_id: str | None
    created_at: datetime
    processed_at: datetime
    trace: dict[str, object]


@dataclass(frozen=True, slots=True)
class RemembererGroup:
    targets: tuple[RemembererTarget, ...]
    settlement: SettlementIdentity | None
    per_row_fallback: bool


@dataclass(frozen=True, slots=True)
class RemembererRunSummary:
    run_id: str
    provider_turns: int
    provider_trace_ids: tuple[str, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None

    def as_json(self) -> dict[str, object]:
        value: dict[str, object] = {
            "run_id": _bounded_nonempty(
                self.run_id,
                "rememberer run id",
                _MAX_RUN_ID_CHARACTERS,
            ),
            "provider_turns": _positive(self.provider_turns, "provider turns"),
            "terminal_outcome": "completed",
        }
        if len(self.provider_trace_ids) > _MAX_PROVIDER_TRACE_IDS:
            raise ValueError("too many provider trace IDs")
        if self.provider_trace_ids:
            value["provider_trace_ids"] = [
                _bounded_nonempty(
                    item,
                    "provider trace ID",
                    _MAX_PROVIDER_TRACE_ID_CHARACTERS,
                )
                for item in self.provider_trace_ids
            ]
        for name, item in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
            ("duration_ms", self.duration_ms),
        ):
            if item is not None:
                value[name] = _nonnegative(item, name.replace("_", " "))
        return value


@dataclass(frozen=True, slots=True)
class RejectedMemory:
    candidate_index: int
    reason_code: Literal["private_key", "known_token_prefix"]


@dataclass(frozen=True, slots=True)
class RemembererCommit:
    created: tuple[StoredRawMemory, ...]
    rejected: tuple[RejectedMemory, ...]
    remembered_at: datetime


class MemoryStore:
    """Direct PostgreSQL operations for canonical and derived memory state."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def prepare_rememberer_group(
        self,
        *,
        owner_message_ids: tuple[UUID, ...],
    ) -> RemembererGroup:
        _unique_nonempty_ids(owner_message_ids, "rememberer target")
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message).where(message.c.id.in_(owner_message_ids))
                    )
                )
                .mappings()
                .all()
            )
            return await _prepare_group(
                connection,
                rows,
                expected_ids=owner_message_ids,
                maximum_messages=len(owner_message_ids),
                permit_damaged_single=True,
            )

    async def select_pending_rememberer_groups(
        self,
        *,
        maximum_groups: int,
        maximum_messages_per_group: int,
    ) -> tuple[RemembererGroup, ...]:
        _positive(maximum_groups, "maximum groups")
        _positive(maximum_messages_per_group, "maximum messages per group")
        settlement = message.c.trace["settlement"]
        valid_settlement = and_(
            func.jsonb_typeof(settlement) == "object",
            func.jsonb_typeof(settlement["run_id"]) == "string",
            func.length(settlement["run_id"].as_string()) > 0,
            func.jsonb_typeof(settlement["through_checkpoint"]) == "string",
            func.length(settlement["through_checkpoint"].as_string()) > 0,
            or_(
                settlement["conclusion_message_id"].is_(None),
                func.jsonb_typeof(settlement["conclusion_message_id"]) == "null",
                and_(
                    func.jsonb_typeof(settlement["conclusion_message_id"]) == "string",
                    func.length(settlement["conclusion_message_id"].as_string()) > 0,
                ),
            ),
            func.jsonb_typeof(settlement["conclusion_kind"]) == "string",
            func.length(settlement["conclusion_kind"].as_string()) > 0,
            func.jsonb_typeof(settlement["outcome"]) == "string",
            func.length(settlement["outcome"].as_string()) > 0,
        )
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(
                            message.c.role == "owner",
                            message.c.processed_at.is_not(None),
                            message.c.remembered_at.is_(None),
                            or_(
                                message.c.trace["settlement"].contains(
                                    {
                                        "conclusion_kind": "conversation",
                                        "outcome": "say",
                                    }
                                ),
                                message.c.trace["settlement"].contains(
                                    {
                                        "conclusion_kind": "conversation",
                                        "outcome": "finish",
                                    }
                                ),
                                message.c.trace["settlement"].contains(
                                    {
                                        "conclusion_kind": "conversation",
                                        "outcome": "host_fallback",
                                    }
                                ),
                                message.c.trace["settlement"].contains(
                                    {
                                        "conclusion_kind": "suspension",
                                        "outcome": "user",
                                    }
                                ),
                                not_(func.coalesce(valid_settlement, False)),
                            ),
                        )
                        .order_by(message.c.created_at, message.c.id)
                        .limit(maximum_groups * maximum_messages_per_group)
                    )
                )
                .mappings()
                .all()
            )
            groups: list[RemembererGroup] = []
            seen_ids: set[UUID] = set()
            seen_settlements: set[SettlementIdentity] = set()
            for row in rows:
                row_id = cast(UUID, row["id"])
                if row_id in seen_ids:
                    continue
                identity = _settlement_identity(_trace(row))
                if identity is None:
                    target = _rememberer_target(row)
                    groups.append(
                        RemembererGroup(
                            targets=(target,),
                            settlement=None,
                            per_row_fallback=True,
                        )
                    )
                    seen_ids.add(row_id)
                elif identity not in seen_settlements:
                    grouped_rows = await _rows_for_settlement(
                        connection,
                        identity,
                        limit=maximum_messages_per_group + 1,
                    )
                    if len(grouped_rows) > maximum_messages_per_group:
                        raise MemoryPersistenceDefect(
                            "settled owner group exceeds the configured sweep bound"
                        )
                    group = await _prepare_group(
                        connection,
                        grouped_rows,
                        expected_ids=tuple(
                            cast(UUID, item["id"]) for item in grouped_rows
                        ),
                        maximum_messages=maximum_messages_per_group,
                        permit_damaged_single=False,
                    )
                    groups.append(group)
                    seen_ids.update(target.id for target in group.targets)
                    seen_settlements.add(identity)
                if len(groups) == maximum_groups:
                    break
            return tuple(groups)

    async def commit_rememberer_result(
        self,
        *,
        group: RemembererGroup,
        memory_texts: tuple[str, ...],
        run: RemembererRunSummary,
        remembered_at: datetime | None = None,
    ) -> RemembererCommit:
        target_ids = tuple(target.id for target in group.targets)
        _unique_nonempty_ids(target_ids, "rememberer target")
        if len(memory_texts) > _MAX_REMEMBERED_MEMORIES:
            raise ValueError("rememberer result exceeds the closed memory bound")
        accepted, rejected = _accepted_memories(memory_texts)
        if len(set(accepted)) != len(accepted):
            raise ValueError("rememberer result contains duplicate memory text")
        completed_at = remembered_at or datetime.now(UTC)
        _aware(completed_at, "rememberer completion time")
        memory_ids = tuple(uuid4() for _ in accepted)
        rememberer_trace = {
            "created_memory_ids": [str(item) for item in memory_ids],
            "run": run.as_json(),
        }

        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(message)
                        .where(message.c.id.in_(target_ids))
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            current = await _prepare_group(
                connection,
                rows,
                expected_ids=target_ids,
                maximum_messages=len(target_ids),
                permit_damaged_single=group.per_row_fallback,
            )
            if (
                current.settlement != group.settlement
                or current.per_row_fallback != group.per_row_fallback
            ):
                raise MemoryPersistenceDefect(
                    "rememberer target grouping changed before commit"
                )
            for target in current.targets:
                updated_trace = {**target.trace, "rememberer": rememberer_trace}
                _bounded_trace(updated_trace)

            if accepted:
                await connection.execute(
                    insert(memory_log),
                    [
                        {"id": memory_id, "text": memory_text}
                        for memory_id, memory_text in zip(
                            memory_ids,
                            accepted,
                            strict=True,
                        )
                    ],
                )
            await connection.execute(
                update(message)
                .where(message.c.id.in_(target_ids))
                .values(
                    remembered_at=completed_at,
                    trace=message.c.trace.concat({"rememberer": rememberer_trace}),
                )
            )
            created_rows: Sequence[RowMapping] = (
                (
                    await connection.execute(
                        select(memory_log).where(memory_log.c.id.in_(memory_ids))
                    )
                )
                .mappings()
                .all()
                if memory_ids
                else ()
            )
        by_id = {cast(UUID, row["id"]): _stored_raw_memory(row) for row in created_rows}
        return RemembererCommit(
            created=tuple(by_id[memory_id] for memory_id in memory_ids),
            rejected=rejected,
            remembered_at=completed_at,
        )

    async def open_memories(
        self,
        *,
        identities: tuple[MemoryIdentity, ...],
        maximum_rows: int,
    ) -> tuple[StoredMemory, ...]:
        _positive(maximum_rows, "maximum memory rows")
        deduplicated = tuple(dict.fromkeys(identities))
        if len(deduplicated) > maximum_rows:
            raise ValueError("memory open exceeds the configured row bound")
        raw_ids = tuple(
            item.id for item in deduplicated if item.table_kind == "memory_log"
        )
        summary_ids = tuple(
            item.id for item in deduplicated if item.table_kind == "memory_summary"
        )
        async with self._engine.connect() as connection:
            raw_rows: Sequence[RowMapping] = (
                (
                    await connection.execute(
                        select(memory_log).where(memory_log.c.id.in_(raw_ids))
                    )
                )
                .mappings()
                .all()
                if raw_ids
                else ()
            )
            summary_rows: Sequence[RowMapping] = (
                (
                    await connection.execute(
                        select(memory_summary).where(
                            memory_summary.c.id.in_(summary_ids)
                        )
                    )
                )
                .mappings()
                .all()
                if summary_ids
                else ()
            )
        found: dict[MemoryIdentity, StoredMemory] = {}
        for row in raw_rows:
            stored = _stored_raw_memory(row)
            found[stored.identity] = stored
        for row in summary_rows:
            stored = _stored_memory_summary(row)
            found[stored.identity] = stored
        return tuple(found[item] for item in deduplicated if item in found)

    async def select_null_embedding_candidates(
        self,
        *,
        maximum_rows: int,
    ) -> tuple[StoredMemory, ...]:
        _positive(maximum_rows, "maximum embedding rows")
        async with self._engine.connect() as connection:
            raw_rows = (
                (
                    await connection.execute(
                        select(memory_log)
                        .where(memory_log.c.embedding.is_(None))
                        .order_by(memory_log.c.created_at, memory_log.c.id)
                        .limit(maximum_rows)
                    )
                )
                .mappings()
                .all()
            )
            summary_rows = (
                (
                    await connection.execute(
                        select(memory_summary)
                        .where(memory_summary.c.embedding.is_(None))
                        .order_by(memory_summary.c.created_at, memory_summary.c.id)
                        .limit(maximum_rows)
                    )
                )
                .mappings()
                .all()
            )
        values: list[StoredMemory] = [
            *map(_stored_raw_memory, raw_rows),
            *map(_stored_memory_summary, summary_rows),
        ]
        values.sort(
            key=lambda item: (
                item.created_at,
                item.id,
                item.identity.table_kind,
            )
        )
        return tuple(values[:maximum_rows])

    async def update_embedding(
        self,
        *,
        identity: MemoryIdentity,
        embedding: Sequence[float],
    ) -> StoredMemory:
        value = _validated_embedding(embedding)
        table = memory_log if identity.table_kind == "memory_log" else memory_summary
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        update(table)
                        .where(table.c.id == identity.id)
                        .values(embedding=value)
                        .returning(*table.c)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise MemoryPersistenceDefect("embedding update references missing memory")
        if identity.table_kind == "memory_log":
            return _stored_raw_memory(row)
        return _stored_memory_summary(row)


async def _prepare_group(
    connection: AsyncConnection,
    rows: Sequence[RowMapping],
    *,
    expected_ids: tuple[UUID, ...],
    maximum_messages: int,
    permit_damaged_single: bool,
) -> RemembererGroup:
    if len(rows) != len(expected_ids):
        raise MemoryPersistenceDefect("rememberer target references a missing message")
    by_id = {cast(UUID, row["id"]): row for row in rows}
    if set(by_id) != set(expected_ids):
        raise MemoryPersistenceDefect("rememberer target identity is inconsistent")
    ordered = tuple(by_id[item] for item in expected_ids)
    if any(row["role"] != "owner" for row in ordered):
        raise MemoryPersistenceDefect("rememberer targets must be owner messages")
    if any(row["processed_at"] is None for row in ordered):
        raise MemoryPersistenceDefect("rememberer targets must be completed messages")
    remembered = [row["remembered_at"] is not None for row in ordered]
    if any(remembered):
        if all(remembered):
            raise MemoryPersistenceDefect("rememberer target is already watermarked")
        raise MemoryPersistenceDefect("settled owner group is only partly remembered")

    identities = tuple(_settlement_identity(_trace(row)) for row in ordered)
    if len(ordered) == 1 and identities[0] is None and permit_damaged_single:
        return RemembererGroup(
            targets=(_rememberer_target(ordered[0]),),
            settlement=None,
            per_row_fallback=True,
        )
    if any(identity is None for identity in identities):
        raise MemoryPersistenceDefect("rememberer target has damaged settlement trace")
    identity = cast(SettlementIdentity, identities[0])
    if not _eligible_settlement(identity):
        raise MemoryPersistenceDefect(
            "rememberer target does not have an eligible conclusion"
        )
    if any(item != identity for item in identities[1:]):
        raise MemoryPersistenceDefect("rememberer targets span settled groups")
    grouped_rows = await _rows_for_settlement(
        connection,
        identity,
        limit=maximum_messages + 1,
    )
    if len(grouped_rows) > maximum_messages:
        raise MemoryPersistenceDefect(
            "settled owner group exceeds the configured memory bound"
        )
    grouped_ids = tuple(cast(UUID, row["id"]) for row in grouped_rows)
    if set(grouped_ids) != set(expected_ids):
        raise MemoryPersistenceDefect("rememberer target omits settled owner messages")
    return RemembererGroup(
        targets=tuple(_rememberer_target(row) for row in ordered),
        settlement=identity,
        per_row_fallback=False,
    )


async def _rows_for_settlement(
    connection: AsyncConnection,
    identity: SettlementIdentity,
    *,
    limit: int,
) -> Sequence[RowMapping]:
    return (
        (
            await connection.execute(
                select(message)
                .where(
                    message.c.role == "owner",
                    message.c.processed_at.is_not(None),
                    message.c.trace["settlement"].contains(identity.as_json()),
                )
                .order_by(message.c.created_at, message.c.id)
                .limit(limit)
            )
        )
        .mappings()
        .all()
    )


def _settlement_identity(trace: dict[str, object]) -> SettlementIdentity | None:
    value = trace.get("settlement")
    if not isinstance(value, dict):
        return None
    settlement = cast(dict[object, object], value)
    run_id = settlement.get("run_id")
    through_checkpoint = settlement.get("through_checkpoint")
    conclusion_message_id = settlement.get("conclusion_message_id")
    conclusion_kind = settlement.get("conclusion_kind")
    outcome = settlement.get("outcome")
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(through_checkpoint, str)
        or not through_checkpoint
        or not (
            conclusion_message_id is None
            or (isinstance(conclusion_message_id, str) and bool(conclusion_message_id))
        )
        or not isinstance(conclusion_kind, str)
        or not conclusion_kind
        or not isinstance(outcome, str)
        or not outcome
    ):
        return None
    return SettlementIdentity(
        run_id=run_id,
        through_checkpoint=through_checkpoint,
        conclusion_message_id=conclusion_message_id,
        conclusion_kind=conclusion_kind,
        outcome=outcome,
    )


def _eligible_settlement(identity: SettlementIdentity) -> bool:
    return (
        identity.conclusion_kind == "conversation"
        and identity.outcome in {"say", "finish", "host_fallback"}
    ) or (identity.conclusion_kind == "suspension" and identity.outcome == "user")


def _rememberer_target(row: RowMapping) -> RemembererTarget:
    processed_at = cast(datetime | None, row["processed_at"])
    if processed_at is None:
        raise MemoryPersistenceDefect("rememberer target is not completed")
    return RemembererTarget(
        id=cast(UUID, row["id"]),
        text=cast(str, row["text"]),
        source=cast(str, row["source"]),
        source_conversation_id=cast(str, row["source_conversation_id"]),
        source_message_id=cast(str | None, row["source_message_id"]),
        created_at=cast(datetime, row["created_at"]),
        processed_at=processed_at,
        trace=_trace(row),
    )


def _accepted_memories(
    values: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[RejectedMemory, ...]]:
    accepted: list[str] = []
    rejected: list[RejectedMemory] = []
    for index, value in enumerate(values):
        if not value.strip():
            raise ValueError("memory text must be a non-empty string")
        if _PRIVATE_KEY_BLOCK.search(value) is not None:
            rejected.append(RejectedMemory(index, "private_key"))
        elif _KNOWN_TOKEN_PREFIX.search(value) is not None:
            rejected.append(RejectedMemory(index, "known_token_prefix"))
        else:
            try:
                encoded = value.encode()
            except UnicodeEncodeError:
                raise ValueError("memory text must be valid UTF-8") from None
            if len(encoded) > _MAX_MEMORY_TEXT_BYTES:
                raise ValueError("memory text exceeds the 8000-byte storage bound")
            accepted.append(value)
    return tuple(accepted), tuple(rejected)


def _stored_raw_memory(row: RowMapping) -> StoredRawMemory:
    return StoredRawMemory(
        id=cast(UUID, row["id"]),
        text=cast(str, row["text"]),
        created_at=cast(datetime, row["created_at"]),
        embedding=_stored_embedding(row["embedding"]),
    )


def _stored_memory_summary(row: RowMapping) -> StoredMemorySummary:
    return StoredMemorySummary(
        id=cast(UUID, row["id"]),
        text=cast(str, row["text"]),
        source_memory_ids=tuple(cast(Sequence[UUID], row["source_memory_ids"])),
        created_at=cast(datetime, row["created_at"]),
        embedding=_stored_embedding(row["embedding"]),
    )


def _stored_embedding(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    return tuple(float(item) for item in cast(Iterable[float], value))


def _validated_embedding(value: Sequence[float]) -> list[float]:
    if len(value) != 1536:
        raise ValueError("memory embedding must contain exactly 1536 values")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError("memory embedding values must be finite numbers")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("memory embedding values must be finite numbers")
        result.append(number)
    if not any(number != 0.0 for number in result):
        raise ValueError("memory embedding must have non-zero L2 norm")
    return result


def _trace(row: RowMapping) -> dict[str, object]:
    value = row["trace"]
    if not isinstance(value, dict):
        raise MemoryPersistenceDefect("message trace is not an object")
    return cast(dict[str, object], value)


def _bounded_trace(value: dict[str, object]) -> None:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(encoded) > _MAX_TRACE_BYTES:
        raise MemoryPersistenceDefect("rememberer trace exceeds its storage bound")


def _unique_nonempty_ids(values: tuple[UUID, ...], name: str) -> None:
    if not values or len(set(values)) != len(values):
        raise ValueError(f"{name} IDs must be non-empty and unique")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _bounded_nonempty(value: str, name: str, maximum: int) -> str:
    if not value or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty and at most {maximum} characters")
    return value


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


__all__ = [
    "MemoryIdentity",
    "MemoryPersistenceDefect",
    "MemoryStore",
    "MemoryTableKind",
    "RejectedMemory",
    "RemembererCommit",
    "RemembererGroup",
    "RemembererRunSummary",
    "RemembererTarget",
    "SettlementIdentity",
    "StoredMemory",
    "StoredMemorySummary",
    "StoredRawMemory",
]

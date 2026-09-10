"""Bounded PostgreSQL retrieval over raw and derived memory rows."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import Table, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import memory_log, memory_summary
from jarvis.memory import MemoryIdentity, MemoryTableKind
from jarvis.ownership import Database
from jarvis.settings import EMBEDDING_DIMENSION


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    table_kind: MemoryTableKind
    id: UUID
    text: str
    created_at: datetime
    source_memory_ids: tuple[UUID, ...]
    lexical_rank: float | None = None
    semantic_distance: float | None = None


@dataclass(frozen=True, slots=True)
class OpenedMemory:
    rows: tuple[RetrievedMemory, ...]
    missing: tuple[MemoryIdentity, ...]


class MemoryEmbedder(Protocol):
    async def embed(
        self,
        inputs: Sequence[str],
    ) -> tuple[tuple[float, ...], ...]: ...


class MemoryRepository(Protocol):
    async def search(
        self,
        query: str,
        *,
        lexical_limit: int,
        semantic_limit: int,
        query_embedding: Sequence[float] | None,
    ) -> tuple[RetrievedMemory, ...]: ...

    async def open(
        self,
        identities: Sequence[MemoryIdentity],
    ) -> OpenedMemory: ...


class PostgresMemoryRepository:
    """Search FTS expression indexes and exact pgvector cosine distance."""

    def __init__(self, engine: Database) -> None:
        self._engine = engine

    async def search(
        self,
        query: str,
        *,
        lexical_limit: int,
        semantic_limit: int,
        query_embedding: Sequence[float] | None,
    ) -> tuple[RetrievedMemory, ...]:
        if lexical_limit < 0 or semantic_limit < 0:
            raise ValueError("memory search limits must be non-negative")
        if query_embedding is not None and (
            len(query_embedding) != EMBEDDING_DIMENSION
            or not all(math.isfinite(component) for component in query_embedding)
            or not any(component != 0.0 for component in query_embedding)
        ):
            raise ValueError("query embedding must match the configured vector space")

        async with self._engine.connect() as connection:
            lexical: list[RetrievedMemory] = []
            semantic: list[RetrievedMemory] = []
            for table, table_kind in (
                (memory_log, "memory_log"),
                (memory_summary, "memory_summary"),
            ):
                if lexical_limit:
                    lexical.extend(
                        await self._lexical(
                            connection,
                            table,
                            cast(MemoryTableKind, table_kind),
                            query,
                            lexical_limit,
                        )
                    )
                if semantic_limit and query_embedding is not None:
                    semantic.extend(
                        await self._semantic(
                            connection,
                            table,
                            cast(MemoryTableKind, table_kind),
                            query_embedding,
                            semantic_limit,
                        )
                    )

        lexical.sort(
            key=lambda row: (
                -cast(float, row.lexical_rank),
                -row.created_at.timestamp(),
                row.table_kind,
                str(row.id),
            )
        )
        semantic.sort(
            key=lambda row: (
                cast(float, row.semantic_distance),
                -row.created_at.timestamp(),
                row.table_kind,
                str(row.id),
            )
        )
        selected = lexical[:lexical_limit]
        selected.extend(semantic[:semantic_limit])

        combined: dict[MemoryIdentity, RetrievedMemory] = {}
        for candidate in selected:
            identity = MemoryIdentity(candidate.table_kind, candidate.id)
            previous = combined.get(identity)
            if previous is None:
                combined[identity] = candidate
            elif candidate.lexical_rank is not None:
                combined[identity] = replace(
                    previous,
                    lexical_rank=candidate.lexical_rank,
                )
            else:
                combined[identity] = replace(
                    previous,
                    semantic_distance=candidate.semantic_distance,
                )
        return tuple(combined.values())

    async def open(
        self,
        identities: Sequence[MemoryIdentity],
    ) -> OpenedMemory:
        ordered = tuple(dict.fromkeys(identities))
        raw_ids = tuple(item.id for item in ordered if item.table_kind == "memory_log")
        summary_ids = tuple(
            item.id for item in ordered if item.table_kind == "memory_summary"
        )
        found: dict[MemoryIdentity, RetrievedMemory] = {}
        async with self._engine.connect() as connection:
            if raw_ids:
                rows = (
                    await connection.execute(
                        select(
                            memory_log.c.id,
                            memory_log.c.text,
                            memory_log.c.created_at,
                        ).where(memory_log.c.id.in_(raw_ids))
                    )
                ).all()
                for row in rows:
                    identity = MemoryIdentity("memory_log", row.id)
                    found[identity] = RetrievedMemory(
                        "memory_log",
                        row.id,
                        row.text,
                        row.created_at,
                        (),
                    )
            if summary_ids:
                rows = (
                    await connection.execute(
                        select(
                            memory_summary.c.id,
                            memory_summary.c.text,
                            memory_summary.c.created_at,
                            memory_summary.c.source_memory_ids,
                        ).where(memory_summary.c.id.in_(summary_ids))
                    )
                ).all()
                for row in rows:
                    identity = MemoryIdentity("memory_summary", row.id)
                    found[identity] = RetrievedMemory(
                        "memory_summary",
                        row.id,
                        row.text,
                        row.created_at,
                        tuple(row.source_memory_ids),
                    )
        return OpenedMemory(
            tuple(found[item] for item in ordered if item in found),
            tuple(item for item in ordered if item not in found),
        )

    async def _lexical(
        self,
        connection: AsyncConnection,
        table: Table,
        table_kind: MemoryTableKind,
        query: str,
        limit: int,
    ) -> list[RetrievedMemory]:
        english_query = func.websearch_to_tsquery(
            literal_column("'english'::regconfig"), query
        )
        simple_query = func.websearch_to_tsquery(
            literal_column("'simple'::regconfig"), query
        )
        english_document = func.to_tsvector(
            literal_column("'english'::regconfig"), table.c.text
        )
        simple_document = func.to_tsvector(
            literal_column("'simple'::regconfig"), table.c.text
        )
        rank = func.greatest(
            func.ts_rank_cd(english_document, english_query),
            func.ts_rank_cd(simple_document, simple_query),
        ).label("lexical_rank")
        columns = [table.c.id, table.c.text, table.c.created_at, rank]
        if table_kind == "memory_summary":
            columns.append(table.c.source_memory_ids)
        rows = (
            await connection.execute(
                select(*columns)
                .where(
                    english_document.op("@@")(english_query)
                    | simple_document.op("@@")(simple_query)
                )
                .order_by(rank.desc(), table.c.created_at.desc(), table.c.id)
                .limit(limit)
            )
        ).all()
        return [
            RetrievedMemory(
                table_kind,
                row.id,
                row.text,
                row.created_at,
                (
                    tuple(row.source_memory_ids)
                    if table_kind == "memory_summary"
                    else ()
                ),
                lexical_rank=float(row.lexical_rank),
            )
            for row in rows
        ]

    async def _semantic(
        self,
        connection: AsyncConnection,
        table: Table,
        table_kind: MemoryTableKind,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RetrievedMemory]:
        distance = table.c.embedding.cosine_distance(query_embedding).label(
            "semantic_distance"
        )
        columns = [table.c.id, table.c.text, table.c.created_at, distance]
        if table_kind == "memory_summary":
            columns.append(table.c.source_memory_ids)
        rows = (
            await connection.execute(
                select(*columns)
                .where(
                    table.c.embedding.is_not(None),
                    func.vector_norm(table.c.embedding) > 0,
                )
                .order_by(distance, table.c.created_at.desc(), table.c.id)
                .limit(limit)
            )
        ).all()
        result: list[RetrievedMemory] = []
        for row in rows:
            if row.semantic_distance is None:
                continue
            semantic_distance = float(row.semantic_distance)
            if not math.isfinite(semantic_distance):
                continue
            result.append(
                RetrievedMemory(
                    table_kind,
                    row.id,
                    row.text,
                    row.created_at,
                    (
                        tuple(row.source_memory_ids)
                        if table_kind == "memory_summary"
                        else ()
                    ),
                    semantic_distance=semantic_distance,
                )
            )
        return result


__all__ = [
    "MemoryEmbedder",
    "MemoryIdentity",
    "MemoryRepository",
    "MemoryTableKind",
    "OpenedMemory",
    "PostgresMemoryRepository",
    "RetrievedMemory",
]

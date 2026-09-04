from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from llm_agent_kernel import InputId, ThreadId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.context import CanonicalMessage
from jarvis.db import message


class PostgresCanonicalHistory:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def completed_history(
        self,
        thread_id: ThreadId,
        *,
        exclude_input_ids: tuple[InputId, ...],
        limit: int,
    ) -> tuple[CanonicalMessage, ...]:
        if type(limit) is not int or limit <= 0:
            raise ValueError("history limit must be a positive integer")
        try:
            excluded = tuple(UUID(str(value)) for value in exclude_input_ids)
        except ValueError as error:
            raise ValueError("canonical input IDs must be UUIDs") from error
        query = (
            select(
                message.c.id,
                message.c.role,
                message.c.text,
                message.c.created_at,
            )
            .where(
                message.c.source_conversation_id == str(thread_id),
                message.c.processed_at.is_not(None),
            )
            .order_by(message.c.created_at.desc(), message.c.id.desc())
            .limit(limit)
        )
        if excluded:
            query = query.where(message.c.id.not_in(excluded))
        async with self._engine.connect() as connection:
            rows = (await connection.execute(query)).all()
        return tuple(
            CanonicalMessage(
                message_id=str(row.id),
                role=cast(Literal["owner", "assistant", "host"], row.role),
                text=cast(str, row.text),
                created_at=row.created_at,
            )
            for row in reversed(rows)
        )


__all__ = ["PostgresCanonicalHistory"]

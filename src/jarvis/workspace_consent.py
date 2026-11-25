"""Record the host's account of a Google consent round in canonical history."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import insert, select

from jarvis.db import message, native_attempt, native_invocation
from jarvis.ownership import Database, lock_conversation, memory_is_admitted


async def record_workspace_consent(
    database: Database, scope: str, fact: dict[str, object]
) -> None:
    identifier = UUID(str(fact["invocation_id"]))
    stage = str(fact["stage"])
    stage_key = str(fact["stage_key"])
    async with database.begin() as conn:
        await lock_conversation(conn, scope)
        recorded = await conn.scalar(
            select(native_invocation.c.id)
            .join(native_attempt, native_attempt.c.id == native_invocation.c.attempt_id)
            .where(
                native_invocation.c.id == identifier,
                native_invocation.c.validation == "accepted",
                native_attempt.c.conversation_id == scope,
            )
        )
        if recorded != identifier:
            raise RuntimeError("workspace consent lacks a canonical native invocation")
        observed_at = datetime.now(UTC)
        await conn.execute(
            insert(message).values(
                id=uuid5(identifier, stage_key),
                role="host",
                text=f"google approval {stage} for {fact['operation']}.",
                source="workspace_consent",
                source_conversation_id=scope,
                source_message_id=stage_key,
                created_at=observed_at,
                processed_at=observed_at,
                memory_admitted=memory_is_admitted(conn),
                trace=fact,
            )
        )

"""Stopped inventory and current admission; historical bytes remain evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, or_, select, text

from jarvis._atomic_json import replace_private_json
from jarvis.agent_tools import AGENT_IMPLEMENTATION_REVISION
from jarvis.db import (
    APPLICATION_SCHEMA_REVISION,
    action,
    message,
    model_decision,
    read_position,
)
from jarvis.ownership import Database, lock_conversation


async def require_native_data(database: Database, *, conversation_id: str) -> None:
    async with database.connect() as connection:
        revision = await connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )
        if revision != APPLICATION_SCHEMA_REVISION:
            raise RuntimeError("one main requires the current application schema")
        legacy = await connection.scalar(
            select(action.c.id)
            .join(message, message.c.id == action.c.origin_message_id)
            .where(
                message.c.source_conversation_id == conversation_id,
                or_(
                    action.c.execution_contract["schema_version"]
                    .as_string()
                    .is_distinct_from("jarvis.action.v2"),
                    and_(
                        action.c.tool_name.like("agent.%"),
                        action.c.execution_contract["implementation_revision"]
                        .as_string()
                        .is_distinct_from(AGENT_IMPLEMENTATION_REVISION),
                    ),
                    action.c.tool_name.like("codex.%"),
                ),
                action.c.status.in_(("queued", "awaiting_approval", "executing")),
            )
            .limit(1)
        )
        if legacy is not None:
            raise RuntimeError(
                "unfinished retired action requires original-release "
                "settlement or cancellation"
            )
        unknown = await connection.scalar(
            select(read_position.c.position)
            .where(
                ~read_position.c.position.startswith("native-invocation:"),
                read_position.c.state.in_(("dispatched", "uncertain")),
                read_position.c.contract["replay_policy"].as_string() == "BilledOnce",
            )
            .limit(1)
        )
        if unknown is not None:
            raise RuntimeError("retired paid read requires original-release settlement")
        inference = await connection.scalar(
            select(model_decision.c.decision_id)
            .where(
                model_decision.c.terminal.is_(None),
                model_decision.c.submission.is_(None),
            )
            .limit(1)
        )
        if inference is not None:
            raise RuntimeError(
                "unfinished retired inference requires original-release disposition"
            )


async def cutover_native(
    database: Database,
    *,
    directory: Path,
    conversation_id: str,
) -> int:
    """Retain private obligations before a stopped, explicitly managed cutover."""
    inventory: dict[str, object] = {
        "schema_version": "jarvis-one-main-inventory.v1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "conversation_id": conversation_id,
    }
    async with database.begin() as connection:
        await lock_conversation(connection, conversation_id)
        paused = await connection.scalar(
            select(message.c.control_kind)
            .where(
                message.c.source_conversation_id == conversation_id,
                message.c.control_kind.is_not(None),
            )
            .order_by(message.c.control_sequence.desc())
            .limit(1)
        )
        if paused != "pause":
            raise RuntimeError(
                "cutover inventory requires canonical administrative pause"
            )
        queries = {
            "actions": """SELECT to_jsonb(a) FROM action a JOIN message m
              ON m.id=a.origin_message_id WHERE m.source_conversation_id=:scope
              AND a.status IN ('queued','awaiting_approval','executing','uncertain')
              ORDER BY a.created_at,a.id""",
            "reminders": """SELECT to_jsonb(a) FROM action a JOIN message m
              ON m.id=a.origin_message_id WHERE m.source_conversation_id=:scope
              AND a.tool_name='schedule.wake' ORDER BY a.created_at,a.id""",
            "requests": """SELECT to_jsonb(m) FROM message m
              WHERE m.source_conversation_id=:scope AND m.role IN ('owner','host')
              AND (m.request_state IN ('pending','waiting','stopped')
                OR m.processing_parked_at IS NOT NULL) ORDER BY m.created_at,m.id""",
            "undelivered": """SELECT to_jsonb(m) FROM message m
              WHERE m.source_conversation_id=:scope AND m.role='assistant'
              AND m.source_message_id IS NULL ORDER BY m.created_at,m.id""",
            "unsettled_attempts": """SELECT to_jsonb(a) FROM native_attempt a
              WHERE a.conversation_id=:scope AND a.product_outcome IS NULL
              ORDER BY a.attempt_seq""",
        }
        count = 0
        for name, query in queries.items():
            rows = list(
                (
                    await connection.execute(text(query), {"scope": conversation_id})
                ).scalars()
            )
            inventory[name] = rows
            count += len(rows)
    replace_private_json(directory / "one-main-cutover.json", inventory)
    return count


def require_native_files(directory: Path) -> None:
    if any(
        (directory / name).exists()
        for name in (
            "paused.json",
            "admission.json",
            "session-ref.json",
            "memory-rebuild-admission.json",
        )
    ):
        raise RuntimeError(
            "retired local authority requires stopped original-release disposition"
        )


__all__ = ["cutover_native", "require_native_data", "require_native_files"]

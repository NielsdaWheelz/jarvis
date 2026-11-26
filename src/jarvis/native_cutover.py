"""Stopped inventory and current admission; historical bytes remain evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis._atomic_json import replace_private_json
from jarvis.actions import unfinished_action_or_worker_ack
from jarvis.agent_tools import AGENT_IMPLEMENTATION_REVISION
from jarvis.db import (
    APPLICATION_SCHEMA_REVISION,
    action,
    message,
    model_decision,
    native_attempt,
    native_invocation,
    read_position,
)
from jarvis.messages import causal_component_ids, current_native_retry, latest_control
from jarvis.native_protocol import NATIVE_REQUEST_SCHEMA
from jarvis.ownership import Database, lock_conversation


@dataclass(frozen=True, slots=True)
class OwnerControl:
    id: UUID
    kind: str
    sequence: int
    targets: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class MaintenanceWork:
    control: OwnerControl | None
    resumable: tuple[UUID, ...]
    pending: tuple[UUID, ...]
    unsettled: tuple[UUID, ...]


async def _maintenance_work(connection: AsyncConnection, scope: str) -> MaintenanceWork:
    row = (
        await connection.execute(
            latest_control(scope).add_columns(
                message.c.id, message.c.control_sequence, message.c.control_targets
            )
        )
    ).one_or_none()
    control = (
        OwnerControl(
            row.id, row.control_kind, row.control_sequence, tuple(row.control_targets)
        )
        if row is not None
        else None
    )
    paused_targets = (
        control.targets if control is not None and control.kind == "pause" else ()
    )
    requests = (
        await connection.execute(
            select(
                message.c.id, message.c.request_state, message.c.processing_parked_at
            )
            .where(
                message.c.source_conversation_id == scope,
                message.c.role.in_(("owner", "host")),
                message.c.control_kind.is_(None),
                or_(
                    message.c.request_state.in_(("pending", "waiting")),
                    and_(
                        message.c.request_state == "stopped",
                        message.c.id.in_(paused_targets),
                    ),
                ),
            )
            .order_by(message.c.id)
        )
    ).all()
    unsettled = tuple(
        (
            await connection.scalars(
                select(native_attempt.c.id)
                .where(
                    native_attempt.c.conversation_id == scope,
                    native_attempt.c.product_outcome.is_(None),
                    or_(
                        native_attempt.c.terminal_at.is_not(None),
                        native_attempt.c.recovery_pending,
                    ),
                )
                .order_by(native_attempt.c.attempt_seq)
            )
        ).all()
    )
    return MaintenanceWork(
        control,
        tuple(item.id for item in requests),
        tuple(
            item.id
            for item in requests
            if item.request_state == "pending" and item.processing_parked_at is None
        ),
        unsettled,
    )


async def maintenance_work(database: Database, *, scope: str) -> MaintenanceWork:
    async with database.connect() as connection:
        return await _maintenance_work(connection, scope)


class NativeActivationDefect(RuntimeError):
    def __init__(self, detail: str, identifier: UUID | str | None = None) -> None:
        super().__init__(detail)
        self.identifier = identifier


async def require_native_data(database: Database, *, conversation_id: str) -> None:
    async with database.connect() as connection:
        revision = await connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )
        if revision != APPLICATION_SCHEMA_REVISION:
            raise NativeActivationDefect("target requires its own application schema")
        old_attempt = await connection.scalar(
            select(native_attempt.c.id)
            .where(
                native_attempt.c.conversation_id == conversation_id,
                native_attempt.c.request["schema_version"]
                .as_string()
                .is_distinct_from(NATIVE_REQUEST_SCHEMA),
                native_attempt.c.product_outcome.is_(None),
                or_(
                    native_attempt.c.terminal_at.is_not(None),
                    native_attempt.c.recovery_pending,
                    native_attempt.c.fenced_at.is_(None),
                ),
            )
            .limit(1)
        )
        if old_attempt is not None:
            raise NativeActivationDefect(
                "retired native attempt requires original-release disposition",
                old_attempt,
            )
        old_retry = await connection.scalar(
            select(message.c.id)
            .where(
                message.c.source_conversation_id == conversation_id,
                message.c.native_retry_after.is_not(None),
                message.c.processing_parked_at.is_(None),
                message.c.request_state.in_(("pending", "waiting")),
                current_native_retry().is_not(True),
            )
            .limit(1)
        )
        if old_retry is not None:
            raise NativeActivationDefect(
                "retired native retry requires original-release disposition", old_retry
            )
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
                unfinished_action_or_worker_ack(),
            )
            .limit(1)
        )
        if legacy is not None:
            raise NativeActivationDefect(
                "retired action requires a disposition under the original release",
                legacy,
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
            raise NativeActivationDefect(
                "retired paid read requires a disposition under the original release",
                unknown,
            )
        work = await _maintenance_work(connection, conversation_id)
        component = set(await causal_component_ids(connection, work.resumable))
        if component:
            invocations = (
                (
                    await connection.execute(
                        select(native_invocation)
                        .join(
                            native_attempt,
                            native_attempt.c.id == native_invocation.c.attempt_id,
                        )
                        .where(
                            native_attempt.c.conversation_id == conversation_id,
                            native_invocation.c.tool_id == "web.search",
                            native_invocation.c.validation == "accepted",
                        )
                    )
                )
                .mappings()
                .all()
            )
            positions = tuple(
                row["read_position"] or "native-invocation:" + str(row["id"])
                for row in invocations
                if component.intersection(map(UUID, row["proposal"]["input_ids"]))
            )
            unknown_web = (
                await connection.execute(
                    select(read_position.c.position, read_position.c.contract).where(
                        read_position.c.position.in_(positions),
                        read_position.c.state.in_(("dispatched", "uncertain")),
                        read_position.c.contract["replay_policy"].as_string()
                        == "BilledOnce",
                    )
                )
            ).all()
            for position, contract in unknown_web:
                if "web_source_operation" not in contract:
                    raise NativeActivationDefect(
                        "retired web search requires original-release disposition",
                        position,
                    )
        inference = await connection.scalar(
            select(model_decision.c.decision_id)
            .where(
                model_decision.c.terminal.is_(None),
                model_decision.c.submission.is_(None),
            )
            .limit(1)
        )
        if inference is not None:
            raise NativeActivationDefect(
                "retired inference requires a disposition under the original release",
                inference,
            )


async def cutover_native(
    database: Database,
    *,
    directory: Path,
    conversation_id: str,
) -> int:
    """Retain private obligations before a stopped, explicitly managed cutover."""
    inventory: dict[str, object] = {
        "schema_version": "jarvis-one-main-inventory.v2",
        "recorded_at": datetime.now(UTC).isoformat(),
        "conversation_id": conversation_id,
    }
    async with database.begin() as connection:
        await lock_conversation(connection, conversation_id)
        control = await connection.scalar(
            select(message.c.control_kind)
            .where(
                message.c.source_conversation_id == conversation_id,
                message.c.control_kind.is_not(None),
            )
            .order_by(message.c.control_sequence.desc())
            .limit(1)
        )
        if control not in {"pause", "resume"}:
            raise RuntimeError("cutover inventory requires initialized owner control")
        inventory["owner_control"] = control
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
            "pending_notices": """SELECT to_jsonb(n) FROM home_notice n
              WHERE n.provider_id IS NULL ORDER BY n.created_at,n.id""",
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

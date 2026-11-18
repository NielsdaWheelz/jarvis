"""Stopped inventory and current admission; historical bytes remain evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from llm_agent_kernel import NativeDefinition
from sqlalchemy import and_, or_, select, text

from jarvis._atomic_json import replace_private_json
from jarvis.admission import JarvisOwner
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
from jarvis.memory_service import MemoryService
from jarvis.messages import MessageStore, causal_component_ids
from jarvis.native_runtime import fit_native_inputs, opening_memory_prefix
from jarvis.ownership import Database, lock_conversation
from jarvis.receipt_tools import receipt_scope


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
        resumable = tuple(
            (
                await connection.execute(
                    select(message.c.id).where(
                        message.c.source_conversation_id == conversation_id,
                        message.c.role.in_(("owner", "host")),
                        message.c.control_kind.is_(None),
                        message.c.request_state.in_(("pending", "waiting")),
                    )
                )
            ).scalars()
        )
        component = set(await causal_component_ids(connection, resumable))
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
                    select(read_position.c.contract).where(
                        read_position.c.position.in_(positions),
                        read_position.c.state.in_(("dispatched", "uncertain")),
                        read_position.c.contract["replay_policy"].as_string()
                        == "BilledOnce",
                    )
                )
            ).scalars()
            if any("web_source_operation" not in contract for contract in unknown_web):
                raise RuntimeError(
                    "outstanding retired web search requires "
                    "original-release disposition"
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
            raise RuntimeError(
                "unfinished retired inference requires original-release disposition"
            )


async def check_pending_mail_opening(
    *,
    database: Database,
    scope: str,
    definition: NativeDefinition,
    memory: MemoryService,
    batch_size: int,
    mail_request: UUID,
) -> None:
    """Measure pending incident mail through the live selection and fitter."""
    async with database.connect() as connection:
        state = await connection.scalar(
            select(message.c.request_state).where(
                message.c.id == mail_request,
                message.c.source_conversation_id == scope,
                message.c.role == "owner",
                message.c.control_kind.is_(None),
            )
        )
        if state is None:
            print(f"mail request {mail_request} missing in the configured channel")
            raise RuntimeError("selected mail request is absent")
        print(f"mail_request={mail_request} state={state}")
        if state != "pending":
            return
        component = await causal_component_ids(connection, (mail_request,))
        original = await connection.scalar(
            select(native_invocation.c.id)
            .join(native_attempt, native_attempt.c.id == native_invocation.c.attempt_id)
            .where(
                *receipt_scope(scope, component),
                native_invocation.c.tool_id.in_(("gmail.search", "gmail.read_message")),
                native_invocation.c.validation == "accepted",
            )
            .limit(1)
        )
        if original is None:
            print(f"mail request {mail_request} has no recorded gmail lineage")
            raise RuntimeError("pending mail lineage differs from the incident")
    store = MessageStore(database)
    owner = JarvisOwner(database, scope)
    cutoff, prefix = await opening_memory_prefix(memory)
    as_of = datetime.now(UTC)
    print(f"stopped opening cutoff={cutoff}")
    checked: set[UUID] = set()
    split: set[UUID] = set()
    batch = 0
    while mail_request not in checked:
        pending = await store.pending_inputs(
            source_conversation_id=scope, limit=batch_size, exclude_ids=tuple(checked)
        )
        if not pending:
            print(f"mail request {mail_request} is ineligible for admission")
            raise RuntimeError("pending mail is ineligible for opening")
        inputs, _, size = await fit_native_inputs(
            owner,
            store,
            definition,
            pending,
            as_of,
            prefix=prefix,
            exclude_ids=tuple(checked),
        )
        batch += 1
        selected = {UUID(item.input_id) for item in inputs}
        waking = {item.id for item in pending if item.request_state == "pending"}
        for identifier in sorted(selected & waking):
            verdict = "fits" if size.fits else "would-park"
            if size.fits and identifier in split:
                verdict = "would-split"
            print(
                f"input={identifier} batch={batch} verdict={verdict} "
                f"chars={size.actual_chars}/{size.max_chars} "
                f"wire_bytes={size.wire_bytes}/{size.max_bytes}"
            )
        if mail_request in selected and not size.fits:
            raise RuntimeError("pending mail would park at admission")
        split.update(waking - selected)
        # An earlier batch's eventual answers are unknown. Measure later batches
        # against the same stopped facts, preserving still-waiting context.
        checked.update(selected & waking)


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

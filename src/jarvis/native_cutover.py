"""Stopped data conversion; historical records never become execution routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from llm_tools import (
    FrozenToolPlan,
    ParsedJson,
    ReplayPolicy,
    ToolEffect,
    ToolId,
    raw_input_digest,
)
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis._atomic_json import read_private_json
from jarvis.actions import ACTION_MAX_ATTEMPTS, ExecutionContract
from jarvis.approval import render_approval
from jarvis.db import action, message, model_decision, read_position
from jarvis.ownership import Database, lock_conversation


async def _require_settled_legacy_reads(
    connection: AsyncConnection, conversation_id: str
) -> None:
    unknown = await connection.scalar(
        select(read_position.c.position)
        .join(
            model_decision,
            read_position.c.position
            == "model-decision:" + model_decision.c.decision_id,
        )
        .where(
            model_decision.c.thread_id == conversation_id,
            read_position.c.state.in_(("dispatched", "uncertain")),
            read_position.c.contract["replay_policy"].as_string() == "BilledOnce",
        )
        .limit(1)
    )
    if unknown is not None:
        raise RuntimeError(
            f"legacy paid read {unknown} needs its original "
            "settlement/reconciliation before activation"
        )


async def require_native_data(database: Database, *, conversation_id: str) -> None:
    async with database.connect() as connection:
        await _require_settled_legacy_reads(connection, conversation_id)
        legacy = await connection.scalar(
            select(action.c.id)
            .join(message, message.c.id == action.c.origin_message_id)
            .where(
                message.c.source_conversation_id == conversation_id,
                ~action.c.arguments.has_key("request_ref"),
                action.c.status.in_(
                    ("queued", "awaiting_approval", "executing", "uncertain")
                ),
            )
            .limit(1)
        )
    if legacy is not None:
        raise RuntimeError(
            "unresolved legacy action blocks native activation; "
            "run stopped cutover-native"
        )


async def cutover_native(
    database: Database,
    *,
    directory: Path,
    conversation_id: str,
    plan: FrozenToolPlan,
) -> int:
    """Validate old actions, convert unentered authority, and import pause."""
    paths = tuple(
        directory / name
        for name in (
            "paused.json",
            "admission.json",
            "session-ref.json",
            "memory-rebuild-admission.json",
        )
    )
    paused = read_private_json(paths[0])
    if paused is not None and (
        set(paused) != {"paused", "schema_version"}
        or paused["schema_version"] != "jarvis-paused.v1"
        or type(paused["paused"]) is not bool
    ):
        raise RuntimeError("old pause state is invalid")
    async with database.connect() as connection:
        await _require_settled_legacy_reads(connection, conversation_id)
        legacy = (
            (
                await connection.execute(
                    select(action)
                    .join(message, message.c.id == action.c.origin_message_id)
                    .where(
                        message.c.source_conversation_id == conversation_id,
                        ~action.c.arguments.has_key("request_ref"),
                        action.c.status.in_(
                            ("queued", "awaiting_approval", "executing", "uncertain")
                        ),
                    )
                    .order_by(action.c.id)
                )
            )
            .mappings()
            .all()
        )
    converted: list[tuple[Any, dict[str, object], ExecutionContract, str | None]] = []
    for row in legacy:
        if row["attempts"] != 0 or row["status"] == "uncertain":
            raise RuntimeError(
                f"legacy effect {row['id']} needs its original "
                "settlement/reconciliation before activation"
            )
        original = ExecutionContract.model_validate(row["execution_contract"])
        origin = str(row["origin_message_id"])
        if original.write_gate_supporting_owner_message_ids != (origin,):
            raise RuntimeError(f"legacy action {row['id']} has ambiguous owner intent")
        binding = plan.catalog_view.binding(ToolId(row["tool_name"]))
        if binding.spec.effect is not ToolEffect.Write:
            raise RuntimeError("legacy action is not a current Write")
        value = binding.spec.input_type.model_validate(
            {
                "request_ref": origin,
                "existing_action_ref": None,
                "arguments": row["arguments"],
            }
        )
        arguments = value.model_dump(mode="json")
        contract = ExecutionContract(
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
            tool_effect=ToolEffect.Write,
            replay_policy=cast(Any, binding.replay_policy),
            input_digest=raw_input_digest(ParsedJson(arguments)),
            max_attempts=1
            if binding.replay_policy is ReplayPolicy.BilledOnce
            else ACTION_MAX_ATTEMPTS,
            claim_id=str(uuid5(row["id"], "native-cutover")),
            through_checkpoint=origin,
            model_step_ordinal=1,
            input_message_ids=(origin,),
            write_gate_supporting_owner_message_ids=(origin,),
        )
        preview = None
        if row["approval_message_id"] is not None:
            preview = render_approval(
                uuid5(row["id"], "native-approval"), binding.spec.id, value.arguments
            ).content
        converted.append((row, arguments, contract, preview))
    timestamp = datetime.now(UTC)
    async with database.begin() as connection:
        await lock_conversation(connection, conversation_id)
        origins = tuple(
            sorted({row["origin_message_id"] for row, _, _, _ in converted})
        )
        inputs = (
            (
                await connection.execute(
                    select(message)
                    .where(message.c.id.in_(origins))
                    .order_by(message.c.id)
                    .with_for_update()
                )
            )
            .mappings()
            .all()
        )
        if len(inputs) != len(origins) or any(row["role"] != "owner" for row in inputs):
            raise RuntimeError("legacy action origin is not an owner request")
        for original, _, _, _ in converted:
            current = (
                (
                    await connection.execute(
                        select(action)
                        .where(action.c.id == original["id"])
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if current != original:
                raise RuntimeError("legacy action changed during stopped cutover")
            await connection.execute(
                update(action)
                .where(action.c.id == original["id"])
                .values(
                    status="cancelled",
                    decided_at=func.coalesce(action.c.decided_at, timestamp),
                    completed_at=timestamp,
                    result={
                        "type": "action_cancelled_v1",
                        "reason_code": "native_cutover",
                    },
                )
            )
        for origin in origins:
            await connection.execute(
                update(message)
                .where(message.c.id == origin)
                .values(
                    request_state="pending",
                    wait_reason=None,
                    processed_at=None,
                )
            )
        for row, arguments, contract, preview in converted:
            if preview is None:
                continue
            identifier = uuid5(row["id"], "native-approval")
            approval_id = uuid5(
                NAMESPACE_URL, f"jarvis-action-approval-v1:{identifier}"
            )
            await connection.execute(
                insert(message).values(
                    id=approval_id,
                    role="assistant",
                    text=preview,
                    source="discord",
                    source_conversation_id=conversation_id,
                    created_at=timestamp,
                    processed_at=timestamp,
                )
            )
            await connection.execute(
                insert(action).values(
                    id=identifier,
                    tool_name=row["tool_name"],
                    arguments=arguments,
                    execution_contract=contract.as_json(),
                    status="awaiting_approval",
                    attempts=0,
                    origin_message_id=row["origin_message_id"],
                    approval_message_id=approval_id,
                    created_at=timestamp,
                    supersedes_action_id=row["id"],
                )
            )
        if paused is not None:
            identifier = uuid5(
                NAMESPACE_URL, "jarvis-native-cutover-pause:" + conversation_id
            )
            old = await connection.scalar(
                select(message.c.id).where(message.c.id == identifier)
            )
            if old is None:
                # The old boolean identifies no stopped request set. Import the
                # deployment pause only; preserve each request's canonical state.
                await connection.execute(
                    insert(message).values(
                        id=identifier,
                        role="owner",
                        text="imported deployment pause",
                        source="native_cutover",
                        source_conversation_id=conversation_id,
                        source_message_id=str(identifier),
                        processed_at=timestamp,
                        request_state="completed",
                        control_kind="pause" if paused["paused"] else "resume",
                        control_sequence=text("nextval('message_control_sequence')"),
                        control_targets=[],
                        trace={"pause_import_revision": "jarvis-native-cutover.v1"},
                    )
                )
    # The stopped operator holds deployment ownership throughout. After every
    # database conversion commits, the old files cease to be authorities.
    for path in paths:
        path.unlink(missing_ok=True)
    return len(converted)


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
        raise RuntimeError("run stopped cutover-native before native activation")


__all__ = ["cutover_native", "require_native_data", "require_native_files"]

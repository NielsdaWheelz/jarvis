"""Record a Google choice and its durable owner interaction."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import insert, select, update

from jarvis.db import event_cursor, message, workspace_block
from jarvis.ownership import Database, lock_conversation
from jarvis.workspace_blocks import WorkspaceBlocks, verifying_workspace
from jarvis.workspace_mcp import Product, WorkspaceError


async def record_workspace_consent(
    database: Database, scope: str, fact: dict[str, object], *, blocks: WorkspaceBlocks
) -> None:
    identifier = UUID(str(fact["invocation_id"]))
    stage = str(fact["stage"])
    stage_key = str(fact["stage_key"])
    round_id = str(fact["approval_id"])
    grant_id = UUID(str(fact["grant_id"]))
    key = str(fact["target_key"])
    async with database.begin() as conn:
        await lock_conversation(conn, scope)
        if fact["arrival_episode"] is None:
            origin, origin_id, ref = await blocks.invocation_origin(
                conn, identifier, verification=verifying_workspace.get() is not None
            )
        else:
            origin, origin_id = "source", UUID(str(fact["arrival_episode"]))
            source = (
                await conn.execute(
                    select(
                        event_cursor.c.account_id,
                        event_cursor.c.progress["label_id"].as_string(),
                    ).where(
                        event_cursor.c.enabled,
                        event_cursor.c.progress["grant_id"].as_string()
                        == str(grant_id),
                        event_cursor.c.error["episode_id"].as_string()
                        == str(origin_id),
                    )
                )
            ).one_or_none()
            if source is None:
                raise WorkspaceError("source_changed", known_no_effect=True)
            ref = {"account": source[0], "label_id": source[1]}
            if stage == "presented" and not await blocks.source_attended(
                conn,
                origin_id,
                str(fact["operation"]),
                key,
                source[0],
                {"grant_id": str(grant_id), "label_id": source[1]},
            ):
                raise WorkspaceError("source_changed", known_no_effect=True)
        now = datetime.now(UTC)
        if stage == "presented":
            await blocks.record(
                conn,
                origin=origin,
                origin_id=origin_id,
                ref=ref | {"round_id": round_id},
                product=cast(Product, fact["product"]),
                operation=str(fact["operation"]),
                key=key,
                grant_id=grant_id,
                reason="consent_required",
            )
        elif stage in {"choice", "cancelled", "expired", "interrupted"}:
            denied = stage == "cancelled" or fact.get("choice") == "DENY_ONCE"
            state = (
                "denied"
                if denied
                else "needs_owner"
                if stage in {"expired", "interrupted"}
                else "checking"
            )
            values: dict[str, object] = {
                "state": state,
                "updated_at": now,
                "revision": workspace_block.c.revision + 1,
            }
            if state == "denied":
                values["remedy"] = "none"
            if denied:
                values["reason"] = "denied"
                values["operation_ref"] = workspace_block.c.operation_ref.op("-")(
                    "round_id"
                )
            elif stage in {"expired", "interrupted"}:
                values["reason"] = "consent_expired"
                values["operation_ref"] = workspace_block.c.operation_ref.op("-")(
                    "round_id"
                )
            await conn.execute(
                update(workspace_block)
                .where(
                    workspace_block.c.operation_ref["round_id"].as_string() == round_id
                )
                .values(**values)
            )
        await conn.execute(
            insert(message).values(
                id=uuid5(identifier, stage_key),
                role="host",
                text=f"google approval {stage} for {fact['operation']}.",
                source="workspace_consent",
                source_conversation_id=scope,
                source_message_id=stage_key,
                created_at=now,
                processed_at=now,
                trace={k: v for k, v in fact.items() if k not in {"prompt", "choices"}},
            )
        )
    blocks.notify_delivery()
    blocks.notify_work()

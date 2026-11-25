"""Verify the predecessor's stopped historical-send disposition from local evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

from llm_tools import canonical_json_bytes
from sqlalchemy import RowMapping, select

from jarvis._atomic_json import read_private_json
from jarvis.actions import ActionStore
from jarvis.db import action

CUT_RECEIPT = "gmail-cut-v1.json"


async def historical_mail(actions: ActionStore) -> tuple[RowMapping, ...]:
    async with actions.engine.connect() as conn:
        rows = await conn.execute(
            select(
                action.c.id,
                action.c.tool_name,
                action.c.status,
                action.c.attempts,
                action.c.arguments,
                action.c.result,
            )
            .where(
                action.c.tool_name.in_(
                    ("gmail.create_draft", "gmail.update_draft", "gmail.send_draft")
                ),
                ~action.c.execution_contract.op("?")("mail"),
                ~action.c.execution_contract.op("?")("workspace"),
            )
            .order_by(action.c.created_at, action.c.id)
        )
        return tuple(rows.mappings())


def _digest(history: Sequence[RowMapping]) -> str:
    rows = [{**dict(row), "id": str(row["id"])} for row in history]
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def verified_cut_ids(
    history: Sequence[RowMapping],
    path: Path,
) -> frozenset[UUID] | None:
    if any(
        row["status"] in {"queued", "awaiting_approval", "executing"} for row in history
    ):
        return None
    required = {
        str(row["id"])
        for row in history
        if row["tool_name"] == "gmail.send_draft"
        and row["status"] in {"succeeded", "uncertain"}
    }
    if not required:
        return frozenset()
    receipt = read_private_json(path)
    if receipt is None or receipt.get("inventory_sha256") != _digest(history):
        return None
    if receipt.get("status") != "clear" or not isinstance(receipt.get("actions"), dict):
        return None
    report = cast(dict[str, object], receipt["actions"])
    for identifier in required:
        item = report.get(identifier)
        if not isinstance(item, dict) or cast(dict[str, object], item).get(
            "outcome"
        ) not in ("sent", "absent"):
            return None
    return frozenset(map(UUID, required))

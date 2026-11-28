"""Original Workspace read receipt queries for filing and source citations."""

from typing import Any

from sqlalchemy import Select, String, select
from sqlalchemy import cast as sql_cast

from jarvis.db import native_invocation, read_position


def original_workspace_reads(grant_id: str) -> Select[Any]:
    """Completed original reads, including those with lost replies."""
    return (
        select(
            native_invocation.c.id,
            native_invocation.c.tool_id,
            native_invocation.c.proposal["arguments"].label("arguments"),
            read_position.c.result["value"].label("value"),
        )
        .join(
            read_position,
            read_position.c.position
            == "native-invocation:" + sql_cast(native_invocation.c.id, String),
        )
        .where(
            native_invocation.c.validation == "accepted",
            native_invocation.c.frozen_contract["effect"].as_string() == "Read",
            read_position.c.state == "completed",
            read_position.c.contract["tool_id"].as_string()
            == native_invocation.c.tool_id,
            read_position.c.contract["workspace_grant_id"].as_string() == grant_id,
        )
    )


def workspace_read_receipts(
    grant_id: str, *, require_success: bool = True
) -> Select[Any]:
    """A recorded reply at its own native read position on this grant."""
    receipts = original_workspace_reads(grant_id).where(
        native_invocation.c.reply_recorded_at.is_not(None),
        native_invocation.c.read_position == read_position.c.position,
        native_invocation.c.reply_receipt["type"].as_string() == "tool_result_ref",
        native_invocation.c.reply_receipt["result_ref"].as_string()
        == read_position.c.position,
    )
    if require_success:
        return receipts.where(
            native_invocation.c.reply_receipt["success"].as_boolean().is_(True),
            read_position.c.result["type"].as_string() == "Success",
        )
    return receipts

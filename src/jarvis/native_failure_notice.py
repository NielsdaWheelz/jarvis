"""Private parking copy from canonical requests and action evidence."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from unicodedata import category
from uuid import UUID, uuid4

from llm_tools import ToolId
from pydantic import ValidationError
from sqlalchemy import RowMapping, case, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.action_requests import action_request_spec
from jarvis.actions import ActionPersistenceDefect, recorded_action_result
from jarvis.db import action, message
from jarvis.home_notices import enqueue_notice
from jarvis.ownership import memory_is_admitted
from jarvis.workspace_host import is_workspace_wake
from jarvis.workspace_write_models import CalendarWriteReceipt, DraftWriteReceipt
from jarvis.write_tools import (
    CALENDAR_CREATE_EVENT_SPEC,
    CALENDAR_UPDATE_EVENT_SPEC,
    GMAIL_CREATE_DRAFT_SPEC,
    GMAIL_PREPARE_REPLACEMENT_SPEC,
    HISTORICAL_CALENDAR_CREATE_EVENT_SPEC,
    HISTORICAL_CALENDAR_UPDATE_EVENT_SPEC,
)

_CALENDAR_WRITES = {
    (spec.id, action_request_spec(spec).tool_contract_revision): (
        spec.success_type,
        verb,
    )
    for spec, verb in (
        (CALENDAR_CREATE_EVENT_SPEC, "created"),
        (CALENDAR_UPDATE_EVENT_SPEC, "updated"),
        (HISTORICAL_CALENDAR_CREATE_EVENT_SPEC, "created"),
        (HISTORICAL_CALENDAR_UPDATE_EVENT_SPEC, "updated"),
    )
}
_DRAFT_WRITES = frozenset(
    (spec.id, action_request_spec(spec).tool_contract_revision)
    for spec in (GMAIL_CREATE_DRAFT_SPEC, GMAIL_PREPARE_REPLACEMENT_SPEC)
)
_HOST_SOURCES = {
    "action": "operation update",
    "attachment": "attachment update",
    "email_event": "mail notice",
    "event_status": "event source update",
    "work_wake": "scheduled check",
}
_OPENINGS = {
    "native_effects_uncertain": (
        "i lost contact with the model and can't confirm what it did."
    ),
    "codex_limit_uncertain_effects": (
        "codex hit a usage or run limit before i finished."
    ),
    "codex_quota_before_activity": "codex ran out of usage while retrying.",
    "context_window_exceeded": "the model ran out of room while retrying.",
    "retired_native_retry": (
        "i parked this request for review. the original run can't be retried after "
        "the upgrade."
    ),
    "the final response did not meet its content contract": (
        "the model gave me a final answer i couldn't use."
    ),
    "the model request was not submitted": "i couldn't start the model request.",
    "the native provider did not complete this turn": (
        "the model didn't finish this turn."
    ),
}
_LINK_START = re.compile(r"https?://|attachment:|/[mftv]/", re.IGNORECASE)
# Full-width colon and slash preserve a visible, non-link label.
_LITERAL_LINK = str.maketrans(":/", "\uff1a\uff0f")


def _quote(value: str) -> str | None:
    single_line = " ".join(
        "".join(
            " " if c.isspace() else c
            for c in value
            if c.isspace() or category(c) not in {"Cc", "Cf"}
        ).split()
    )
    if not single_line:
        return None
    excerpt = single_line if len(single_line) <= 80 else single_line[:79] + "…"
    # Both clients link these markers even when preceded by a backslash.
    excerpt = _LINK_START.sub(lambda match: match[0].translate(_LITERAL_LINK), excerpt)
    return "“" + excerpt.replace("“", "'").replace("”", "'") + "”"


def _bounded_list(labels: list[str]) -> str:
    omitted = len(labels) - 3
    return ", ".join(labels[:3] + ([f"{omitted} more"] if omitted > 0 else []))


async def _calendar_operation(
    connection: AsyncConnection, row: RowMapping
) -> tuple[str, str, tuple[str, str, str] | None] | None:
    spec = _CALENDAR_WRITES.get((row["tool_name"], row["tool_contract_revision"]))
    if spec is None or row["status"] != "succeeded":
        return None
    success_type, verb = spec
    try:
        receipt = await recorded_action_result(connection, row["id"])
        if receipt is None or receipt["type"] != "Success":
            return None
        proof = success_type.model_validate(receipt["value"])
    except (ActionPersistenceDefect, ValidationError):
        # Optional copy cannot prevent parking. The recorded status still applies.
        return None
    label = "calendar event"
    if isinstance(proof, CalendarWriteReceipt):
        return label, verb, (proof.account, proof.calendar_id, proof.event_id)
    if title := _quote(proof.event.writable.summary):
        label += " " + title
    key = (
        (proof.account, proof.event.calendar_id, proof.event.event_id)
        if proof.account is not None
        else None
    )
    return label, verb, key


async def record_parking_notice(
    connection: AsyncConnection,
    *,
    scope: str,
    origins: tuple[UUID, ...],
    reason: str,
    timestamp: datetime,
    attempt_id: str | None,
) -> None:
    inputs = (
        (
            await connection.execute(
                select(
                    message.c.id,
                    message.c.source,
                    message.c.text,
                    case((message.c.role == "owner", message.c.text)).label(
                        "owner_text"
                    ),
                )
                .where(
                    message.c.id.in_(origins), message.c.source_conversation_id == scope
                )
                .order_by(message.c.created_at, message.c.id)
            )
        )
        .mappings()
        .all()
    )
    actions = (
        await connection.execute(
            select(
                action.c.id,
                action.c.tool_name,
                action.c.status,
                action.c.execution_contract["tool_contract_revision"]
                .as_string()
                .label("tool_contract_revision"),
            )
            .join(message, message.c.id == action.c.origin_message_id)
            .where(
                action.c.origin_message_id.in_(origins),
                message.c.source_conversation_id == scope,
            )
            .order_by(action.c.created_at, action.c.id)
        )
    ).mappings()

    operations: list[str] = []
    uncertain: list[str] = []
    proposals: list[str] = []
    creates: dict[tuple[str, str, str], int] = {}
    for row in actions:
        status: str = row["status"]
        if status == "awaiting_approval":
            proposals.append(str(row["id"]))
        if calendar := await _calendar_operation(connection, row):
            label, verb, key = calendar
            if key is not None:
                if verb == "created":
                    creates[key] = len(operations)
                elif key in creates:
                    operations[creates.pop(key)] = f"{label} was created and updated"
                    continue
            operations.append(f"{label} was {verb}")
            continue
        if (
            status == "succeeded"
            and (row["tool_name"], row["tool_contract_revision"]) in _DRAFT_WRITES
        ):
            try:
                receipt = await recorded_action_result(connection, row["id"])
                if receipt is not None and receipt["type"] == "Success":
                    proof = DraftWriteReceipt.model_validate(receipt["value"])
                    operations.append(
                        "gmail saved a verified draft"
                        if proof.verification == "verified"
                        else "gmail acknowledged saving a draft"
                    )
                    continue
            except (ActionPersistenceDefect, ValidationError):
                pass
        if status == "uncertain" and row["tool_name"] == CALENDAR_UPDATE_EVENT_SPEC.id:
            uncertain.append("calendar change")
            continue
        try:
            name = ToolId(row["tool_name"])[:80]
        except ValueError:
            name = "recorded operation"
        if status == "uncertain":
            uncertain.append(name)
        else:
            operations.append(f"{name} ({status.replace('_', ' ')})")

    requests: list[str] = []
    host_sources: Counter[str] = Counter()
    for row in inputs:
        if row["owner_text"] is None:
            host_sources[row["source"]] += 1
        else:
            requests.append(_quote(row["owner_text"]) or "request without text")
    sources = [
        f"{count} {_HOST_SOURCES.get(source, 'host update')}{'s' if count > 1 else ''}"
        for source, count in host_sources.items()
    ]

    opening = (
        "this request was too large to open with the model."
        if reason.startswith(("the opening needed ", "jarvis measured "))
        else _OPENINGS.get(reason, "i couldn't deliver the final answer.")
    )
    lines = [opening]
    if operations:
        lines.append(f"recorded operations: {_bounded_list(operations)}.")
    if uncertain:
        lines.append(f"uncertain effects: {_bounded_list(uncertain)}.")
    if requests:
        lines.append(f"still open: {_bounded_list(requests)}.")
    if sources:
        lines.append(f"host updates still open: {_bounded_list(sources)}.")
    if proposals:
        lines.append("pending proposals need repair before a decision.")
    identifier = uuid4()
    home: dict[str, object] = {"proposal_ids": proposals} if proposals else {}
    check_only = len(inputs) == 1 and is_workspace_wake(
        inputs[0]["source"], inputs[0]["text"]
    )
    if check_only:
        home["todo_result"] = {
            "todo_id": json.loads(inputs[0]["text"])["record"]["id"],
            "request_id": str(inputs[0]["id"]),
            "label": "scheduled check did not finish",
        }
    await connection.execute(
        insert(message).values(
            id=identifier,
            role="assistant",
            text=" ".join(lines),
            source="native_failure",
            home=home or None,
            source_conversation_id=scope,
            memory_admitted=memory_is_admitted(connection),
            processed_at=timestamp,
            trace={"native_attempt_id": attempt_id} if attempt_id is not None else {},
        )
    )
    if not check_only:
        await enqueue_notice(connection, identifier)

"""Read owner-visible conversation and resolve references against that same view."""

from __future__ import annotations

from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, Text, select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.concurrency import run_in_threadpool

from jarvis.action_requests import action_request_spec
from jarvis.attachment_tools import ATTACHMENT_DELETE_SPEC
from jarvis.db import action, attachment, message, work
from jarvis.home_pages import HomePages
from jarvis.write_tools import (
    CALENDAR_CREATE_EVENT_SPEC,
    CALENDAR_DELETE_EVENT_SPEC,
    CALENDAR_UPDATE_EVENT_SPEC,
    GMAIL_SEND_DRAFT_SPEC,
)

type Record = dict[str, Any]

# Extract only owner-facing columns. In particular, never load a native request.
_MESSAGES = """
SELECT m.id, m.role, m.source, m.created_at AS at, m.text,
       m.home->'ref' AS ref, m.home->'present' AS present,
       COALESCE((
           SELECT jsonb_agg(jsonb_build_object(
               'id', f.id, 'name', item->>'name', 'state', f.state,
               'media_type', f.media_type, 'unavailable', f.error IS NOT NULL)
             ORDER BY slot)
           FROM jsonb_array_elements(m.trace->'attachment_manifest')
               WITH ORDINALITY AS files(item,slot)
           JOIN attachment f ON f.id = (item->>'id')::uuid
             AND f.origin_message_id = m.id
       ), '[]') AS files
FROM message m
WHERE m.source_conversation_id = :scope AND m.role IN ('assistant','owner')
  AND m.source != 'initialize_state'
"""


def _cursor(before: str) -> tuple[datetime, UUID]:
    stamp, kind, identifier = before.split("~")
    at = datetime.fromisoformat(stamp)
    if at.tzinfo is None or kind != "message":
        raise ValueError("invalid message cursor")
    return at, UUID(identifier)


async def conversation(
    connection: AsyncConnection, scope: str, before: str | None
) -> Record:
    at, identifier = _cursor(before) if before is not None else (None, None)
    result = await connection.execute(
        text(
            _MESSAGES
            + """
          AND (CAST(:at AS timestamptz) IS NULL OR (m.created_at,m.id) < (:at,:id))
          ORDER BY m.created_at DESC, m.id DESC LIMIT 51"""
        ),
        {"scope": scope, "at": at, "id": identifier},
    )
    rows = [dict(row) for row in result.mappings()]
    page = rows[:50]
    before = None
    if len(rows) > 50:
        last = page[-1]
        before = f"{last['at'].isoformat()}~message~{last['id']}"
    proposals = await _proposals(connection, scope, [item["id"] for item in page])
    for item in page:
        item["proposals"] = proposals[item["id"]]
    return {"items": page[::-1], "next_before": before}


async def visible_message(
    connection: AsyncConnection, scope: str, identifier: UUID
) -> Record | None:
    result = await connection.execute(
        text(_MESSAGES + " AND m.id = :id"), {"scope": scope, "id": identifier}
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    proposals = await _proposals(connection, scope, [identifier])
    return {**row, "proposals": proposals[identifier]}


def proposal_presented(scope: str) -> ColumnElement[bool]:
    """The correlated action has a committed consent question in this conversation."""
    return (
        select(message.c.id)
        .where(
            message.c.source_conversation_id == scope,
            message.c.source == "native_final",
            message.c.home["proposal_ids"].op("?")(action.c.id.cast(Text)),
        )
        .correlate(action)
        .exists()
    )


# Project the exact action/message relation. A first decision without a published
# ask belongs to the owner message that supplied it. Matching decision retries
# retain that original receipt, even when their invocation cites a later message.
_PROPOSALS = """
WITH page AS (
    SELECT id,role,source,home FROM message
    WHERE id=ANY(:ids) AND source_conversation_id=:scope
      AND role IN ('owner','assistant') AND source!='initialize_state'
), pairs AS (
    SELECT p.id AS message_id, item::uuid AS action_id
    FROM page p
    CROSS JOIN LATERAL jsonb_array_elements_text(p.home->'proposal_ids') item
    WHERE p.source IN ('native_final','native_failure')
    UNION
    SELECT p.id,i.action_id FROM page p JOIN native_invocation i
      ON i.reply_receipt #>> '{result,value,owner_message_id}'=p.id::text
    WHERE p.role='owner' AND i.tool_id='approval.respond'
      AND i.reply_receipt @> '{"type": "local_result", "success": true}'
      AND NOT EXISTS (SELECT FROM message ask
          WHERE ask.source_conversation_id=:scope AND ask.source='native_final'
            AND ask.home->'proposal_ids' ? i.action_id::text)
)
SELECT p.message_id,a.id AS action_id,a.status,a.tool_name,f.filename,
  a.execution_contract->>'tool_contract_revision' AS contract_revision,
  (a.arguments->'arguments') #- '{content,body_text}' AS args,
  COALESCE(a.result->>'reason_code',a.result #>> '{error,type}') AS reason,
  a.result #>> '{value,sent_message_id}' AS sent_id,
  COALESCE(a.result #>> '{value,event,event_id}',a.result #>> '{value,event_id}')
    AS event_id,
  first.value->>'decision' AS decision,
  first.value->>'owner_message_id' AS owner_message_id
FROM pairs p JOIN action a ON a.id=p.action_id
JOIN message origin ON origin.id=a.origin_message_id
  AND origin.source_conversation_id=:scope
LEFT JOIN attachment f ON a.tool_name='attachment.delete'
  AND f.id::text=a.arguments #>> '{arguments,id}'
LEFT JOIN LATERAL (
    SELECT i.reply_receipt #> '{result,value}' AS value FROM native_invocation i
    WHERE i.action_id=a.id AND i.tool_id='approval.respond'
      AND i.reply_receipt @> '{"type": "local_result", "success": true}'
    ORDER BY i.reply_recorded_at,i.id LIMIT 1
) first ON true
ORDER BY a.created_at,a.id
"""


def _calendar_fields(event: Record) -> dict[str, str]:
    def moment(value: Record) -> str:
        if value.get("date") is not None:
            return value["date"]
        return f"{value['date_time']} ({value['time_zone']})"

    reminders = (
        "calendar defaults"
        if event["use_default_reminders"]
        else ", ".join(
            f"{r['method']} {r['minutes']} min before" for r in event["reminders"]
        )
    )
    return {
        "title": event["summary"] or "untitled",
        "start": moment(event["start"]),
        "end": moment(event["end"]),
        "attendees": ", ".join(p["address"] for p in event["attendees"]) or "none",
        "location": event["location"] or "none",
        "description": event["description"] or "none",
        "recurrence": ", ".join(event["recurrence"]) or "none",
        "reminders": reminders or "none",
    }


@cache
def _proposal_contracts() -> dict[str, str]:
    return {
        str(spec.id): action_request_spec(spec).tool_contract_revision
        for spec in (
            GMAIL_SEND_DRAFT_SPEC,
            CALENDAR_CREATE_EVENT_SPEC,
            CALENDAR_UPDATE_EVENT_SPEC,
            CALENDAR_DELETE_EVENT_SPEC,
            ATTACHMENT_DELETE_SPEC,
        )
    }


def _proposal(row: RowMapping) -> Record:
    tool = row["tool_name"]
    result = {"action_id": row["action_id"], "status": row["status"]}
    if row["decision"] is not None:
        result.update(
            decision=row["decision"], owner_message_id=row["owner_message_id"]
        )
    revision = _proposal_contracts().get(tool)
    if revision is None or revision != row["contract_revision"]:
        if row["status"] not in {
            "succeeded",
            "failed",
            "uncertain",
            "cancelled",
        }:
            raise RuntimeError("unresolved proposal has an unsupported write contract")
        # Status and any first decision remain independent of the retired payload.
        return {**result, "title": tool, "detail": f"action id · {row['action_id']}"}
    args = cast(Record, row["args"])
    detail: list[str] = []
    if tool == "gmail.send_draft":
        content = args["content"]
        title = "send draft · " + (content["subject"] or "untitled")
        for field in ("to", "cc", "bcc"):
            if content[field]:
                detail.append(
                    field + " · " + ", ".join(x["address"] for x in content[field])
                )
    elif tool in {
        "calendar.create_event",
        "calendar.update_event",
        "calendar.delete_event",
    }:
        verb = tool.split(".")[1].split("_")[0]
        expected = cast(Record, args.get("expected") or {})
        old = _calendar_fields(expected["writable"]) if expected else {}
        new_event = args.get("replacement") or args.get("event")
        new = _calendar_fields(new_event) if new_event else {}
        title = f"{verb} event · {(new or old)['title']}"
        detail.append(
            "calendar · " + (args.get("calendar_id") or expected["calendar_id"])
        )
        if expected:
            detail.append("event id · " + expected["event_id"])
        for field, value in (new or old).items():
            if old and new:
                if value != old[field]:
                    detail.append(f"{field} · {old[field]} → {value}")
                elif field == "attendees" and value != "none":
                    detail.append(f"attendees · {value}")
            elif field != "title" and value != "none":
                detail.append(f"{field} · {value}")
        detail.append(
            "notify attendees"
            if args["notify_attendees"]
            else "without attendee notifications"
        )
    elif tool == "attachment.delete":
        title = "delete original · " + (row["filename"] or "unnamed file")
        detail.append(args["id"])
    else:
        raise ValueError(f"unrecognized proposal tool: {tool}")
    if row["reason"]:
        detail.append(f"reason · {row['reason']}")
    if row["sent_id"]:
        detail.append(f"gmail message id · {row['sent_id']}")
    if row["event_id"] and tool == "calendar.create_event":
        detail.append(f"event id · {row['event_id']}")
    return {**result, "title": title, "detail": "\n".join(detail)}


async def _proposals(
    connection: AsyncConnection, scope: str, message_ids: list[UUID]
) -> dict[UUID, list[Record]]:
    by_id: dict[UUID, list[Record]] = {identifier: [] for identifier in message_ids}
    if message_ids:
        result = await connection.execute(
            text(_PROPOSALS), {"scope": scope, "ids": message_ids}
        )
        for row in result.mappings():
            by_id[row["message_id"]].append(_proposal(row))
    return by_id


async def reference_context(
    connection: AsyncConnection, scope: str, ref: Record, pages: Path
) -> Record | None:
    kind = ref["kind"]
    if kind == "proposal":
        identifier = UUID(ref["message_id"])
        proposals = await _proposals(connection, scope, [identifier])
        for proposal in proposals[identifier]:
            if str(proposal["action_id"]) == ref["action_id"]:
                return {"ref": ref, "proposal_title": proposal["title"]}
        return None
    if kind == "view":
        exists = await run_in_threadpool(HomePages(pages).view, ref["slug"], ref["rev"])
        return {"ref": ref} if exists is not None else None
    identifier = UUID(ref["id"])
    if kind == "file":
        query = (
            select(attachment.c.id)
            .join(message, message.c.id == attachment.c.origin_message_id)
            .where(
                attachment.c.id == identifier,
                attachment.c.state == "ready",
                message.c.source_conversation_id == scope,
            )
        )
    elif kind == "todo":
        query = select(work.c.id).where(work.c.id == identifier)
    else:
        return None
    return {"ref": ref} if await connection.scalar(query) is not None else None

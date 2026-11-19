"""Read owner-visible messages, decisions and references."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import RowMapping, select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.concurrency import run_in_threadpool

from jarvis.db import attachment, message, work
from jarvis.home_pages import HomePages

type Record = dict[str, Any]
type DecisionKind = Literal["action", "question"]

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


def _cursor(before: str | None) -> tuple[datetime | None, str, UUID | None]:
    if before is None:
        return None, "", None
    stamp, kind, identifier = before.split("~")
    at = datetime.fromisoformat(stamp)
    if at.tzinfo is None or kind not in {"message", "action", "question"}:
        raise ValueError("invalid cursor")
    return at, kind, UUID(identifier)


def _page(rows: list[Record], *, messages: bool = False) -> Record:
    window = rows[:50]
    cursor = None
    if len(rows) > 50:
        last = window[-1]
        cursor = f"{last['at'].isoformat()}~{last.get('kind', 'message')}~{last['id']}"
    return {"items": window[::-1] if messages else window, "next_before": cursor}


async def conversation(
    connection: AsyncConnection, scope: str, before: str | None
) -> Record:
    at, kind, identifier = _cursor(before)
    if before and kind != "message":
        raise ValueError("invalid message cursor")
    rows = await connection.execute(
        text(
            _MESSAGES
            + """
          AND (CAST(:at AS timestamptz) IS NULL OR (m.created_at,m.id) < (:at,:id))
          ORDER BY m.created_at DESC, m.id DESC LIMIT 51"""
        ),
        {"scope": scope, "at": at, "id": identifier},
    )
    return _page([dict(row) for row in rows.mappings()], messages=True)


async def visible_message(
    connection: AsyncConnection, scope: str, identifier: UUID
) -> Record | None:
    rows = await connection.execute(
        text(_MESSAGES + " AND m.id = :id"), {"scope": scope, "id": identifier}
    )
    row = rows.mappings().one_or_none()
    return dict(row) if row is not None else None


# An open wait belongs to the attempt currently named by its input. A newer wait
# on the same input can never reopen an older question.
_HAS_QUESTION = """
(EXISTS (SELECT FROM home_notice n WHERE n.kind='question' AND n.message_id=q.id)
 OR COALESCE(a.terminal #>> '{raw_structured_output,value,response,question}',
     CASE WHEN pg_input_is_valid(a.terminal->>'final_text','jsonb') THEN
       (a.terminal->>'final_text')::jsonb #>> '{response,question}' END) IS NOT NULL)
"""
_QUESTION = f"""
SELECT DISTINCT ON (COALESCE(q.id,i.id)) COALESCE(q.id,i.id) AS id,
  COALESCE(q.created_at,i.created_at) AS at, q.text, i.id AS origin_message_id
FROM message i
LEFT JOIN native_attempt a ON a.id = (i.trace->>'native_attempt_id')::uuid
  AND a.conversation_id = i.source_conversation_id
  AND a.product_outcome->>'status' = 'committed'
  AND a.product_outcome->'input_outcomes' @> jsonb_build_array(
    jsonb_build_object('input_id',i.id::text,'wait_reason','owner_input'))
LEFT JOIN message q ON q.id = (a.product_outcome->>'response_id')::uuid
  AND q.source_conversation_id = i.source_conversation_id
  AND q.source = 'native_final' AND {_HAS_QUESTION}
WHERE i.source_conversation_id=:scope AND i.request_state='waiting'
  AND i.wait_reason='owner_input'
ORDER BY COALESCE(q.id,i.id), i.created_at, i.id
"""

_ACTION = """
SELECT a.id, a.created_at AS at, a.status, a.tool_name, a.origin_message_id,
  (a.arguments->'arguments') #- '{content,body_text}' AS args,
  COALESCE(a.result->>'reason_code', a.result #>> '{error,type}',
    a.result #>> '{value,sent_message_id}', a.result #>> '{value,event,event_id}',
    a.result #>> '{value,event_id}') AS reason, a.completed_at, f.filename
FROM action a JOIN message m ON m.id=a.origin_message_id
LEFT JOIN attachment f ON a.tool_name='attachment.delete'
  AND f.id::text=a.arguments #>> '{arguments,id}'
WHERE m.source_conversation_id=:scope
"""


def _proposal(row: RowMapping) -> tuple[str, list[str]]:
    tool = row["tool_name"]
    args = cast(Record, row["args"] or {})
    detail: list[str] = []
    title = tool
    if tool == "gmail.send_draft" and (content := args.get("content")):
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
    } and (args.get("event") or args.get("expected")):
        verb = tool.split(".")[1].split("_")[0]
        old = cast(Record, args.get("expected") or {})
        new = args.get("replacement") or args.get("event")
        title = f"{verb} event · {(new or old['writable'])['summary']}"
        detail.append(args.get("calendar_id") or old["calendar_id"])
        for label, item in (("current", old.get("writable")), ("proposed", new)):
            if item is None:
                continue
            times = [
                item[k].get("date_time") or item[k].get("date")
                for k in ("start", "end")
            ]
            people = (
                ", ".join(p["address"] for p in item["attendees"]) or "no attendees"
            )
            detail.append(f"{label} · {times[0]} — {times[1]} · {people}")
        detail.append(
            "notify attendees"
            if args["notify_attendees"]
            else "without attendee notifications"
        )
    elif tool == "attachment.delete" and args.get("id"):
        title = "delete original · " + (row["filename"] or "unnamed file")
        detail.append(args["id"])
    else:
        detail.append("open the conversation for the recorded proposal.")
    return title, detail


def _action_detail(row: RowMapping) -> Record:
    try:
        title, detail = _proposal(row)
    except (KeyError, TypeError, AttributeError):
        # Retired argument shapes remain inspectable by identity and status.
        title, detail = (
            row["tool_name"],
            ["open the conversation for the recorded proposal."],
        )
    if row["reason"]:
        detail.append(row["reason"])
    if row["completed_at"]:
        detail.append(f"recorded {row['completed_at'].isoformat()}")
    return dict(
        kind="action",
        id=row["id"],
        at=row["at"],
        title=title,
        status=row["status"],
        detail="\n".join(detail),
        origin_message_id=row["origin_message_id"],
    )


async def decision(
    connection: AsyncConnection, scope: str, kind: DecisionKind, identifier: UUID
) -> Record | None:
    params = {"scope": scope, "id": identifier}
    if kind == "action":
        result = await connection.execute(
            text(
                _ACTION
                + """
              AND a.id=:id AND (a.status='awaiting_approval' OR a.decided_at IS NOT NULL
                OR a.approval_message_id IS NOT NULL
                OR EXISTS (SELECT FROM home_notice n WHERE n.action_id=a.id))
            """
            ),
            params,
        )
        row = result.mappings().one_or_none()
        return _action_detail(row) if row else None
    result = await connection.execute(
        text(
            """
        SELECT * FROM ("""
            + _QUESTION
            + """) w WHERE id=:id ORDER BY origin_message_id LIMIT 1
    """
        ),
        params,
    )
    row = result.mappings().one_or_none()
    status = "waiting"
    if row is None:
        # Historical question identity survives settlement and input re-use.
        result = await connection.execute(
            text(f"""
              SELECT q.id,q.created_at AS at,q.text,i.id AS origin_message_id
              FROM message q JOIN native_attempt a
                ON a.id=(q.trace->>'native_attempt_id')::uuid
              CROSS JOIN LATERAL jsonb_array_elements(
                a.product_outcome->'input_outcomes') o
              JOIN message i ON i.id=(o->>'input_id')::uuid
              WHERE q.id=:id AND q.source_conversation_id=:scope
                AND q.source='native_final' AND a.conversation_id=:scope
                AND a.product_outcome->>'status'='committed'
                AND a.product_outcome->>'response_id'=q.id::text
                AND o->>'wait_reason'='owner_input' AND i.source_conversation_id=:scope
                AND {_HAS_QUESTION}
              UNION ALL
              SELECT i.id,i.created_at,NULL,i.id FROM message i WHERE i.id=:id
                AND i.source_conversation_id=:scope AND EXISTS (
                  SELECT FROM native_attempt a
                  LEFT JOIN message q ON q.id=(a.product_outcome->>'response_id')::uuid
                    AND q.source_conversation_id=:scope AND q.source='native_final'
                    AND {_HAS_QUESTION}
                  WHERE q.id IS NULL AND a.conversation_id=:scope
                    AND a.product_outcome->>'status'='committed'
                    AND a.product_outcome->'input_outcomes' @> jsonb_build_array(
                      jsonb_build_object('input_id',i.id::text,'wait_reason','owner_input')
                    ))
              ORDER BY origin_message_id LIMIT 1
            """),
            params,
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        status = "settled"
    return _question_detail(row, status)


def _question_detail(row: RowMapping, status: str) -> Record:
    return dict(
        kind="question",
        id=row["id"],
        at=row["at"],
        status=status,
        title="question",
        detail=row["text"] or "no question was recorded for this wait.",
        origin_message_id=row["origin_message_id"],
    )


async def decisions(
    connection: AsyncConnection, scope: str, before: str | None
) -> Record:
    at, kind, identifier = _cursor(before)
    if kind == "message":
        raise ValueError("invalid decision cursor")
    params = {"scope": scope, "at": at, "kind": kind, "id": identifier}
    actions = await connection.execute(
        text(
            _ACTION
            + """
      AND a.status='awaiting_approval' AND (CAST(:at AS timestamptz) IS NULL
        OR (a.created_at,'action'::text,a.id)<(:at,:kind,:id))
      ORDER BY a.created_at DESC,a.id DESC LIMIT 51
    """
        ),
        params,
    )
    questions = await connection.execute(
        text(
            "SELECT * FROM ("
            + _QUESTION
            + """) waits
      WHERE CAST(:at AS timestamptz) IS NULL OR (at,'question'::text,id)<(:at,:kind,:id)
      ORDER BY at DESC,id DESC LIMIT 51
    """
        ),
        params,
    )
    records = [_action_detail(row) for row in actions.mappings()]
    records.extend(_question_detail(row, "waiting") for row in questions.mappings())
    records.sort(key=lambda r: (r["at"], r["kind"], r["id"]), reverse=True)
    return _page(records)


async def reference_exists(
    connection: AsyncConnection, scope: str, ref: Record, pages: Path
) -> bool:
    kind = ref["kind"]
    if kind == "view":
        return (
            await run_in_threadpool(HomePages(pages).view, ref["slug"], ref["rev"])
            is not None
        )
    identifier = UUID(ref["id"])
    if kind == "decision":
        return await decision(connection, scope, ref["type"], identifier) is not None
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
        return False
    return await connection.scalar(query) is not None

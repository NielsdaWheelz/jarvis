"""Read owner-visible conversation and resolve references against that same view."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import ColumnElement, RowMapping, Text, select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.concurrency import run_in_threadpool

from jarvis.action_requests import action_request_spec
from jarvis.actions import ActionPersistenceDefect, recorded_action
from jarvis.attachment_tools import ATTACHMENT_DELETE_SPEC
from jarvis.db import action, attachment, message, work
from jarvis.home_pages import HomePages
from jarvis.mail_revisions import (
    VerifiedCompose,
    inspect_revision,
    integrity_failure,
    verified_compose,
)
from jarvis.write_tools import (
    CALENDAR_CREATE_EVENT_SPEC,
    CALENDAR_DELETE_EVENT_SPEC,
    CALENDAR_UPDATE_EVENT_SPEC,
    GMAIL_DISCARD_DRAFT_SPEC,
    WORKSPACE_MAIL_IMPLEMENTATION,
    GmailSnapshot,
)

type Record = dict[str, Any]

# Extract only owner-facing columns. In particular, never load a native request.
# Older control replies have the transaction's start time. Their receipt records
# when the command was applied.
_MESSAGES = """
SELECT m.id, m.role, m.source,
       CASE WHEN m.source = 'native_control' THEN COALESCE(m.processed_at, m.created_at)
            ELSE m.created_at END AS at, m.text,
       m.home->'ref' AS ref, m.home->'present' AS present,
       saved.id AS draft_revision_id,
       CASE WHEN m.role='assistant' AND m.source IN ('native_final','native_failure')
         THEN CASE WHEN m.home #>> '{todo_result,draft_ref}' IS NOT NULL
                        AND saved.id IS NULL THEN 'integrity'
                   ELSE m.home #>> '{todo_result,draft_error}' END
       END AS draft_revision_error,
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
LEFT JOIN action saved
  ON m.role='assistant' AND m.source IN ('native_final','native_failure')
 AND saved.id=CASE WHEN pg_input_is_valid(m.home #>> '{todo_result,draft_ref}', 'uuid')
                   THEN (m.home #>> '{todo_result,draft_ref}')::uuid END
 AND saved.id::text=m.home #>> '{todo_result,draft_ref}'
 AND saved.status='succeeded'
 AND (
   (saved.tool_name='gmail.create_draft'
    AND saved.execution_contract->>'implementation_revision' IN
        ('jarvis-gmail-create_draft-v2', :mail_implementation))
   OR (saved.tool_name='gmail.update_draft'
       AND saved.execution_contract->>'implementation_revision'
             ='jarvis-gmail-update_draft-v2')
 )
 AND saved.origin_message_id::text=m.home #>> '{todo_result,request_id}'
 AND EXISTS (SELECT FROM message origin WHERE origin.id=saved.origin_message_id
             AND origin.source_conversation_id=m.source_conversation_id)
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
            f"""SELECT * FROM ({_MESSAGES}) AS visible
            WHERE CAST(:at AS timestamptz) IS NULL OR (at,id) < (:at,:id)
            ORDER BY at DESC, id DESC LIMIT 51"""
        ),
        {
            "scope": scope,
            "at": at,
            "id": identifier,
            "mail_implementation": WORKSPACE_MAIL_IMPLEMENTATION,
        },
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


async def todo_results(
    connection: AsyncConnection, scope: str, identifier: UUID, before: str | None
) -> Record | None:
    at, previous = _cursor(before) if before is not None else (None, None)
    result = await connection.execute(
        text("""
            SELECT r.message_id, r.at, r.label FROM work w
            LEFT JOIN LATERAL (
                SELECT m.id AS message_id, m.created_at AS at,
                       m.home #>> '{todo_result,label}' AS label
                FROM message m
                WHERE m.source_conversation_id = :scope
                  AND m.role = 'assistant'
                  AND m.source IN ('native_final','native_failure')
                  AND m.home #>> '{todo_result,todo_id}' = w.id::text
                  AND (CAST(:at AS timestamptz) IS NULL
                       OR (m.created_at,m.id) < (:at,:previous))
                ORDER BY m.created_at DESC, m.id DESC LIMIT 51
            ) r ON TRUE
            WHERE w.id = :identifier
            ORDER BY r.at DESC, r.message_id DESC
        """),
        {"identifier": identifier, "scope": scope, "at": at, "previous": previous},
    )
    rows = result.mappings().all()
    if not rows:
        return None
    items = [dict(row) for row in rows[:50] if row["message_id"] is not None]
    next_before = None
    if len(rows) > 50:
        last = items[-1]
        next_before = f"{last['at'].isoformat()}~message~{last['message_id']}"
    return {"items": items, "next_before": next_before}


async def draft_for_request(
    connection: AsyncConnection, request_id: UUID, draft_ref: UUID
) -> VerifiedCompose | None:
    """Only a successful compose at this already-verified origin can be evidence."""
    candidate = await connection.scalar(
        select(action.c.id).where(
            action.c.id == draft_ref,
            action.c.origin_message_id == request_id,
            action.c.status == "succeeded",
            action.c.tool_name.in_(
                (
                    "gmail.create_draft",
                    "gmail.update_draft",
                )
            ),
        )
    )
    if candidate is None:
        return None
    stored = await recorded_action(connection, candidate)
    if stored is None:
        raise ActionPersistenceDefect("saved draft action disappeared")
    return verified_compose(stored)


async def visible_message(
    connection: AsyncConnection, scope: str, identifier: UUID
) -> Record | None:
    result = await connection.execute(
        text(_MESSAGES + " AND m.id=:id"),
        {
            "scope": scope,
            "id": identifier,
            "mail_implementation": WORKSPACE_MAIL_IMPLEMENTATION,
        },
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
_PROPOSAL_PAIRS = """
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
"""

_PROPOSALS = (
    _PROPOSAL_PAIRS
    + """
SELECT p.message_id,a.id AS action_id,a.status,a.tool_name,f.filename,
  codec.binding,
  CASE WHEN codec.binding IS NOT NULL AND a.tool_name!='gmail.send_draft'
    THEN a.arguments->'arguments' END AS args,
  CASE WHEN codec.binding = 'workspace'
    THEN a.execution_contract #> '{workspace,effect}' END AS workspace_effect,
  CASE WHEN codec.binding = 'historical' AND a.tool_name='gmail.send_draft'
    THEN (a.execution_contract #> '{mail,snapshot}') - 'body_text'
    END AS mail_preview,
  COALESCE(a.result->>'reason_code',a.result #>> '{error,type}') AS reason,
  a.result #>> '{value,sent_message_id}' AS sent_id,
  COALESCE(a.result #>> '{value,event,event_id}',a.result #>> '{value,event_id}')
    AS event_id,
  first.value->>'decision' AS decision,
  first.value->>'owner_message_id' AS owner_message_id
FROM pairs p JOIN action a ON a.id=p.action_id
CROSS JOIN LATERAL (
    SELECT (CAST(:contracts AS jsonb)->a.tool_name)
        ->>(a.execution_contract->>'tool_contract_revision') AS binding
) codec
JOIN message origin ON origin.id=a.origin_message_id
  AND origin.source_conversation_id=:scope
LEFT JOIN attachment f ON codec.binding = 'attachment'
  AND a.tool_name='attachment.delete'
  AND f.id::text=a.arguments #>> '{arguments,id}'
LEFT JOIN LATERAL (
    SELECT i.reply_receipt #> '{result,value}' AS value FROM native_invocation i
    WHERE i.action_id=a.id AND i.tool_id='approval.respond'
      AND i.reply_receipt @> '{"type": "local_result", "success": true}'
    ORDER BY i.reply_recorded_at,i.id LIMIT 1
) first ON true
ORDER BY a.created_at,a.id
"""
)


_REVISION_RELATION = (
    _PROPOSAL_PAIRS
    + """
SELECT false AS saved, NULL::text AS request_id
FROM pairs p JOIN action a ON a.id=p.action_id
JOIN message origin ON origin.id=a.origin_message_id
  AND origin.source_conversation_id=:scope
WHERE p.action_id=:action_id
  AND a.tool_name='gmail.send_draft' AND (CAST(:contracts AS jsonb)->a.tool_name)
    ->>(a.execution_contract->>'tool_contract_revision')='historical'
UNION ALL
SELECT true AS saved, p.home #>> '{todo_result,request_id}'
FROM page p LEFT JOIN action a ON a.id=:action_id
LEFT JOIN message origin ON origin.id=a.origin_message_id
WHERE p.role='assistant' AND p.source IN ('native_final','native_failure')
  AND p.home #>> '{todo_result,draft_ref}'=CAST(:action_id AS uuid)::text
  AND (a.id IS NULL OR origin.source_conversation_id=:scope)
-- A real proposal remains inspectable even if a saved link reused its id.
ORDER BY saved LIMIT 1
"""
)


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
def _proposal_contracts() -> str:
    historical = {
        "gmail.send_draft": (
            "4ebffb8d6ed82661932d49685968712ae828764402ccac680986268762aeabbc"
        ),
        "calendar.create_event": (
            "2857d94f3bf3cfbb502d409c98d8b9ee0afcb9441a3ecb94c027eaa288c2c768"
        ),
        "calendar.update_event": (
            "8e3b990f0d5f258920a3d9a44ebf420a6cdfd80f273f398b63d5a41f0a0e0bdb"
        ),
        "calendar.delete_event": (
            "3c0230b9dc2b9e94080c24d6df117fa439322cbd0266c1746ecf6806e0dbfafe"
        ),
    }
    versions = {name: {rev: "historical"} for name, rev in historical.items()}
    specs = (
        CALENDAR_CREATE_EVENT_SPEC,
        CALENDAR_UPDATE_EVENT_SPEC,
        CALENDAR_DELETE_EVENT_SPEC,
        GMAIL_DISCARD_DRAFT_SPEC,
        ATTACHMENT_DELETE_SPEC,
    )
    for spec in specs:
        revision = action_request_spec(spec).tool_contract_revision
        versions.setdefault(str(spec.id), {})[revision] = (
            "attachment" if spec is ATTACHMENT_DELETE_SPEC else "workspace"
        )
    return json.dumps(versions)


def _proposal(row: RowMapping) -> Record:
    tool = row["tool_name"]
    result = {"action_id": row["action_id"], "status": row["status"]}
    if row["decision"] is not None:
        result.update(
            decision=row["decision"], owner_message_id=row["owner_message_id"]
        )
    if row["binding"] is None:
        if row["status"] not in {
            "succeeded",
            "failed",
            "uncertain",
            "cancelled",
        }:
            raise RuntimeError("unresolved proposal has an unsupported write contract")
        # Status and any first decision remain independent of the retired payload.
        return {**result, "title": tool, "detail": f"action id · {row['action_id']}"}
    if tool == "gmail.send_draft":
        return {**result, **_mail_proposal(row)}
    if row["binding"] == "workspace":
        title, lines = _workspace_proposal(tool, cast(Record, row["workspace_effect"]))
        if row["reason"]:
            lines.append(f"reason · {row['reason']}")
        return {**result, "title": title, "detail": "\n".join(lines)}
    args = cast(Record, row["args"])
    detail: list[str] = []
    if tool in {
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
    if row["event_id"] and tool == "calendar.create_event":
        detail.append(f"event id · {row['event_id']}")
    return {**result, "title": title, "detail": "\n".join(detail)}


def _workspace_proposal(tool: str, effect: Record) -> tuple[str, list[str]]:
    if tool == "gmail.discard_draft":
        old = effect["old"]
        detail = [f"draft id · {old['draft_id']}", f"message id · {old['message_id']}"]
        if replacement := effect["replacement"]:
            detail.append(f"verified replacement draft · {replacement['draft_id']}")
        return f"discard draft · {old['subject'] or 'untitled'}", detail

    prior_observation = cast(Record, effect["prior"] or {})
    before = cast(Record, prior_observation.get("fields", {}))
    after = cast(Record, effect["expected"])
    event = before | after
    verb = tool.partition(".")[2].partition("_")[0]
    title = f"{verb} event · {event.get('summary') or 'untitled'}"
    detail = [f"calendar · {effect['calendar_id']}", f"scope · {effect['scope']}"]
    if effect["event_id"] is not None:
        detail.append(f"event id · {effect['event_id']}")

    def describe(key: str, value: Any) -> str:
        if value is None:
            return "none"
        if key == "attendees":
            return ", ".join(item["address"] for item in value) or "none"
        if key in {"start", "end"}:
            return str(
                value.get("date") or f"{value['date_time']} ({value['time_zone']})"
            )
        if key == "reminders":
            return ", ".join(f"{r['method']} {r['minutes']} min" for r in value)
        if key == "recurrence":
            return ", ".join(value) or "none"
        return str(value)

    for key in (
        "summary",
        "start",
        "end",
        "attendees",
        "location",
        "description",
        "recurrence",
        "reminders",
        "use_default_reminders",
    ):
        prior, next_value = before.get(key), event.get(key)
        if prior == next_value and key not in {"start", "end", "attendees"}:
            continue
        if prior is None and next_value is None:
            continue

        value = describe(key, next_value)
        if before and prior != next_value:
            value = f"{describe(key, prior)} → {value}"
        detail.append(f"{key.replace('_', ' ')} · {value}")
    detail.append(
        "notify attendees" if effect["notify"] else "without attendee notifications"
    )
    return title, detail


def _mail_proposal(row: RowMapping) -> Record:
    status = row["status"]
    label = {
        "queued": "approved · waiting to send",
        "awaiting_approval": "awaiting approval",
        "executing": "sending",
        "succeeded": "sent",
        "failed": "send stopped",
        "uncertain": "unknown whether sent",
        "cancelled": "denied" if row["decision"] == "deny" else "cancelled",
    }[status]
    presentation = {"status_label": label, "draft_revision_id": row["action_id"]}
    preview = row["mail_preview"]
    try:
        snapshot = GmailSnapshot.model_validate(
            {**preview, "body_text": ""} if isinstance(preview, dict) else None
        )
    except ValidationError:
        return {
            **presentation,
            "title": "recorded email send",
            "detail": "the stored email failed its integrity checks.",
        }
    title = "send draft · " + (snapshot.subject or "untitled")
    detail = [
        field + " · " + (", ".join(person.address for person in recipients) or "none")
        for field, recipients in (
            ("to", snapshot.to),
            ("cc", snapshot.cc),
            ("bcc", snapshot.bcc),
        )
    ]
    counts = Counter((file.filename, file.size_bytes) for file in snapshot.files)
    total = 0
    for slot, file in enumerate(snapshot.files, 1):
        name = file.filename
        size = file.size_bytes
        suffix = f" · {file.sha256[-12:]}" if counts[name, size] > 1 else ""
        detail.append(f"{slot}. {name} · {size:,} bytes{suffix}")
        total += size
    detail.append(f"attachments total · {total:,} bytes")
    if status == "uncertain":
        detail.append(
            "gmail didn't confirm whether it sent. check sent mail before trying again."
        )
    elif row["reason"] in {"DraftChanged", "draft_changed"}:
        detail.append(
            "the draft changed in gmail. finish there or ask jarvis for a fresh draft."
        )
    elif row["reason"] in {"FilePolicy", "file_policy"}:
        detail.append("gmail blocked a file in this message.")
    elif row["reason"]:
        detail.append(f"reason · {row['reason']}")
    if row["sent_id"]:
        detail.append(f"gmail message id · {row['sent_id']}")
    return {
        "title": title,
        "detail": "\n".join(detail),
        **presentation,
    }


async def _proposals(
    connection: AsyncConnection,
    scope: str,
    message_ids: list[UUID],
) -> dict[UUID, list[Record]]:
    by_id: dict[UUID, list[Record]] = {identifier: [] for identifier in message_ids}
    if message_ids:
        result = await connection.execute(
            text(_PROPOSALS),
            {
                "scope": scope,
                "ids": message_ids,
                "contracts": _proposal_contracts(),
            },
        )
        for row in result.mappings():
            by_id[row["message_id"]].append(_proposal(row))
    return by_id


async def mail_revision(
    connection: AsyncConnection, scope: str, message_id: UUID, action_id: UUID
) -> Record | None:
    # Check the same proposal membership as the chat card, including prior consent.
    # Saved evidence belongs only to the exact request cited on its visible reply.
    result = await connection.execute(
        text(_REVISION_RELATION),
        {
            "scope": scope,
            "ids": [message_id],
            "action_id": action_id,
            "contracts": _proposal_contracts(),
        },
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    try:
        stored = await recorded_action(
            connection, action_id, source_conversation_id=scope
        )
        if stored is None or (
            row["saved"] and str(stored.origin_message_id) != row["request_id"]
        ):
            raise ActionPersistenceDefect("revision origin differs")
        return inspect_revision(stored, saved=row["saved"])
    except (ActionPersistenceDefect, ValueError):
        return integrity_failure()


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

"""Bind a reply to the original Workspace observations and project one selected item."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from llm_tools import canonical_json_bytes
from llm_tools.content import projection_digest
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import native_attempt, native_invocation, read_position
from jarvis.messages import causal_component_ids
from jarvis.workspace_enrollment import WorkspaceEnrollment
from jarvis.workspace_links import workspace_link
from jarvis.workspace_reads import Chunk, Coverage, EventHit

if TYPE_CHECKING:
    from jarvis.terminal import Source

type Data = dict[str, Any]
type Record = Mapping[str, Any]
MAX_SOURCES = 32
_MAIL_FIELDS = ("from", "to", "cc", "date", "subject", "reply-to")
_SOURCE_TOOLS = (
    "gmail.search",
    "gmail.read_thread",
    "gmail.get_message",
    "calendar.get_event",
    "calendar.list_events",
)


def _utc(value: str) -> str:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("missing observation zone")
    return (
        stamp.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _ranges(
    pieces: list[tuple[int, bytes, str]], total: int
) -> list[tuple[int, bytes, str]]:
    """Merge overlapping/adjacent observations without filling an unread byte."""
    result: list[tuple[int, bytes, str]] = []
    for start, data, stamp in sorted(pieces):
        if not 0 <= start <= start + len(data) <= total:
            raise ValueError("range outside projection")
        if result:
            first, previous, prior_stamp = result[-1]
            overlap = first + len(previous) - start
            if overlap >= 0:
                shared = min(len(data), overlap)
                if previous[start - first : start - first + shared] != data[:shared]:
                    raise ValueError("overlap differs")
                result[-1] = (first, previous + data[shared:], max(stamp, prior_stamp))
                continue
        result.append((start, data, stamp))
    return result


def _time(value: Data) -> str:
    return " ".join(
        x
        for x in (value.get("dateTime") or value.get("date"), value.get("timeZone"))
        if x
    )


def _event(item: str, row: Record, grant: WorkspaceEnrollment) -> Data:
    args, page = row["arguments"], row["value"]
    if row["tool_id"] not in ("calendar.list_events", "calendar.get_event") or (
        row["tool_id"] == "calendar.get_event" and args.get("event_id") != item
    ):
        raise ValueError("wrong event tool or selector")
    matches = [
        e
        for e in page["items"]
        if e.get("kind") == "event" and e.get("event_id") == item
    ]
    if len(matches) != 1:
        raise ValueError("event not unambiguously observed")
    event = EventHit.model_validate(matches[0]).model_dump(exclude_none=True)
    fields: list[Data] = []
    for key, label in (
        ("summary", "title"),
        ("start", "start"),
        ("end", "end"),
        ("status", "status"),
        ("location", "location"),
        ("description", "description"),
        ("attendees", "attendees"),
        ("recurrence", "recurrence"),
        ("recurring_event_id", "recurring event"),
        ("original_start_time", "original start"),
        ("updated", "updated in calendar"),
    ):
        if key not in event:
            continue
        value = event[key]
        if key in ("start", "end", "original_start_time"):
            value = _time(value)
        elif key == "attendees":
            value = "\n".join(
                ", ".join(
                    str(a[k])
                    for k in ("displayName", "email", "responseStatus")
                    if a.get(k)
                )
                + "".join(
                    f" ({flag})"
                    for k, flag in (
                        ("self", "self"),
                        ("organizer", "organizer"),
                        ("optionalAttendee", "optional"),
                    )
                    if a.get(k)
                )
                for a in value
            )
        elif key == "recurrence":
            value = "\n".join(value)
        fields.append({"label": label, "value": value})
    omissions: list[str] = []
    if page["coverage"]["state"] == "partial":
        omissions.append("calendar returned a partial result")
    return dict(
        state="available",
        kind="event",
        observed_at=_utc(page["observed_at"]),
        coverage=dict(kind="event", omissions=omissions, passage="unrequested"),
        fields=fields,
        segments=[],
        focus=None,
        original_url=workspace_link(
            event.get("link"),
            "calendar",
            item,
            args["calendar_id"],
            account=grant.account,
        ),
    )


def project(
    kind: str,
    item: str,
    rows: Sequence[Record],
    grant: WorkspaceEnrollment,
    passage: str | None,
) -> Data:
    """Render observed fields and offsets. Refuse inconsistent evidence."""
    if not rows or not item:
        raise ValueError("no observations")
    if kind == "event":
        if len(rows) != 1 or passage is not None:
            raise ValueError("event requires one observation")
        return _event(item, rows[0], grant)
    if kind != "mail":
        raise ValueError("unrecognized source kind")
    fields: dict[str, list[str]] = defaultdict(list)
    filenames: list[tuple[str, ...]] = []
    groups: dict[
        tuple[str, str | None, str | None, str, int], list[tuple[int, bytes, str]]
    ] = defaultdict(list)
    types: dict[str, str] = {}
    omissions: list[str] = []
    times: list[str] = []
    url = None
    for row in rows:
        tool, args, page = row["tool_id"], row["arguments"], row["value"]
        at = _utc(page["observed_at"])
        times.append(at)
        coverage = Coverage.model_validate(page["coverage"])
        if coverage.state == "partial":
            omissions.append(
                coverage.reason.replace("_", " ")
                if coverage.reason
                else "partial observation"
            )
        if tool == "gmail.search":
            hits = [
                p
                for t in page["items"]
                if t.get("kind") == "thread"
                for p in t["previews"]
                if p["message_id"] == item
            ]
            if len(hits) != 1:
                raise ValueError("missing or ambiguous preview")
            h = hits[0]
            for label, key in (
                ("from", "sender"),
                ("subject", "subject"),
                ("date", "date"),
            ):
                if h.get(key) is not None:
                    fields[label].append(h[key])
            url = (
                workspace_link(h.get("link"), "gmail", item, account=grant.account)
                or url
            )
        elif tool == "gmail.read_thread":
            if not any(
                m.get("kind") == "message" and m["message_id"] == item
                for m in page["items"]
            ):
                raise ValueError("message not in observed thread page")
            omissions.append("only thread membership was observed")
        elif tool == "gmail.get_message":
            mail = page["mail"]
            if (
                args.get("message_id"),
                mail["message_id"],
                mail["account"],
                mail["draft_id"],
            ) != (item, item, grant.account, None):
                raise ValueError("different message or account")
            chunk = Chunk.model_validate(page["chunk"])
            data = chunk.text.encode()
            if (
                chunk.projection != "workspace-raw-mime-v1"
                or chunk.offset != args.get("offset", 0)
                or chunk.end_offset != chunk.offset + len(data)
                or args.get("digest") not in (None, chunk.digest)
            ):
                raise ValueError("invalid observed range")
            key = (
                args.get("section", "message"),
                args.get("part_id"),
                args.get("text_view"),
                chunk.digest,
                chunk.total_bytes,
            )
            groups[key].append((chunk.offset, data, at))
            url = (
                workspace_link(page.get("link"), "gmail", item, account=grant.account)
                or url
            )
        else:
            raise ValueError("wrong mail tool")

    bodies: list[
        tuple[
            str,
            str,
            str,
            list[tuple[int, bytes, str]],
            list[tuple[int, bytes, str]],
            bool,
        ]
    ] = []
    for (section, part, view, digest, total), pieces in groups.items():
        ranges = _ranges(pieces, total)
        complete = len(ranges) == 1 and ranges[0][0] == 0 and len(ranges[0][1]) == total
        if complete:
            source = dict(
                account=grant.account,
                grant_id=str(grant.grant_id),
                message_id=item,
                draft_id=None,
                section=section,
                part_id=part,
                text_view=view,
            )
            if (
                projection_digest(
                    source,
                    "workspace-raw-mime-v1",
                    hashlib.sha256(ranges[0][1]).hexdigest(),
                )
                != digest
            ):
                raise ValueError("complete projection differs from original digest")
        if section == "message":
            if not complete:
                omissions.append("metadata partial")
                continue
            metadata = json.loads(ranges[0][1])
            if metadata["message_id"] != item or metadata["draft_id"] is not None:
                raise ValueError("metadata selector differs")
            for name in _MAIL_FIELDS:
                values = [
                    h["value"] for h in metadata["headers"] if h["name"].lower() == name
                ]
                if values:
                    fields[name].append("\n".join(values))
            filenames.append(
                tuple(
                    p["filename"]
                    for p in metadata["parts"]
                    if p["is_file"] and p.get("filename")
                )
            )
            types.update({p["part_id"]: p["media_type"] for p in metadata["parts"]})
        elif (
            section == "body_part"
            and part
            and view is not None
            and view in ("readable", "decoded")
        ):
            bodies.append((part, view, digest, pieces, ranges, complete))
        else:
            raise ValueError("unknown observed mail section")
    output_fields: list[Data] = []
    for label in _MAIL_FIELDS:
        values = set(fields[label])
        if len(values) == 1:
            output_fields.append(dict(label=label, value=values.pop()))
        elif values:
            omissions.append(f"conflicting {label}")
    if len(set(filenames)) > 1:
        omissions.append("conflicting filenames")
    elif filenames:
        output_fields.extend(dict(label="file", value=f) for f in filenames[0])

    segments: list[Data] = []
    matches: list[Data | None] = []
    needle = passage.encode() if passage else b""
    for part, view, digest, pieces, ranges, complete in bodies:
        if view == "decoded" and any(
            p == part and v == "readable" for p, v, *_ in bodies
        ):
            continue
        if view == "decoded" and types.get(part) in (None, "text/html"):
            omissions.append("decoded source text")
        if not complete:
            omissions.append("some byte ranges were not read")
        # Keep each returned page's time. Trim only overlaps already proved equal.
        through = 0
        for start, data, stamp in sorted(pieces):
            end = start + len(data)
            if end <= through:
                continue
            trim = max(start, through) - start
            data = data[trim:]
            start += trim
            through = end
            segments.append(
                dict(
                    part=part,
                    digest=digest,
                    observed_at=stamp,
                    start=start,
                    end=start + len(data),
                    text=data.decode(),
                )
            )
        for start, data, _ in ranges:
            if needle:
                match = data.find(needle)
                if match >= 0:
                    matches.append(
                        dict(
                            part=part,
                            digest=digest,
                            start=start + match,
                            end=start + match + len(needle),
                        )
                    )
                    if data.find(needle, match + 1) >= 0:
                        matches.append(None)
    if not segments:
        omissions.append("no message body was read")
    if len(set(times)) > 1:
        omissions.append("observations at " + ", ".join(sorted(set(times))))
    focus = matches[0] if len(matches) == 1 else None
    return dict(
        state="available",
        kind="mail",
        observed_at=max(times),
        coverage=dict(
            kind="excerpt" if segments else "preview",
            omissions=list(dict.fromkeys(omissions)),
            passage="matched"
            if focus
            else "missing"
            if passage is not None
            else "unrequested",
        ),
        fields=output_fields,
        segments=segments,
        focus=focus,
        original_url=url,
    )


async def _originals(
    db: AsyncConnection, scope: str, grant: WorkspaceEnrollment, ids: set[UUID]
) -> dict[str, Record]:
    from jarvis.workspace_checks import original_workspace_reads

    n, p = native_invocation.c, read_position.c
    query = (
        original_workspace_reads(str(grant.grant_id))
        .join(native_attempt, native_attempt.c.id == n.attempt_id)
        .where(
            native_attempt.c.conversation_id == scope,
            n.id.in_(ids),
            n.tool_id.in_(_SOURCE_TOOLS),
            n.frozen_contract["implementation_revision"].as_string()
            == "jarvis-" + func.replace(n.tool_id, ".", "-") + "-workspace-v1",
            p.result["type"].as_string() == "Success",
        )
    )
    rows = (await db.execute(query)).mappings()
    return {str(r["id"]): dict(r) for r in rows}


async def _deliveries(
    db: AsyncConnection, attempt: UUID, ids: set[UUID]
) -> list[Record]:
    n, p = native_invocation.c, read_position.c
    originals = ["native-invocation:" + str(i) for i in ids]
    # Most callbacks identify the original directly. A receipt.read result at its
    # own position can instead prove the exact pages reopened on this attempt.
    query = (
        select(
            n.tool_id,
            n.proposal["input_ids"].label("inputs"),
            n.proposal["arguments"].label("args"),
            n.read_position,
            case((n.tool_id == "receipt.read", p.result["value"])).label("value"),
        )
        .select_from(native_invocation)
        .join(read_position, n.read_position == p.position)
        .where(
            n.attempt_id == attempt,
            n.validation == "accepted",
            n.reply_recorded_at.is_not(None),
            n.reply_receipt["type"].as_string() == "tool_result_ref",
            n.reply_receipt["success"].as_boolean().is_(True),
            n.reply_receipt["result_ref"].as_string() == p.position,
            p.state == "completed",
            p.result["type"].as_string() == "Success",
            p.contract["tool_id"].as_string() == n.tool_id,
            or_(
                n.read_position.in_(originals),
                (
                    (n.tool_id == "receipt.read")
                    & (
                        n.frozen_contract["implementation_revision"].as_string()
                        == "jarvis-receipt-read-v3"
                    )
                    & (
                        n.proposal["arguments"]["selection"]["part"].as_string()
                        == "result"
                    )
                    & (
                        n.proposal["arguments"]["selection"]["kind"].as_string()
                        == "open"
                    )
                    & (
                        n.proposal["arguments"]["selection"]["invocation_id"]
                        .as_string()
                        .in_([str(i) for i in ids])
                    )
                ),
            ),
        )
    )
    return [dict(row) for row in (await db.execute(query)).mappings()]


def _observed(
    ids: list[str],
    request: str,
    component: set[str],
    named: set[str],
    stopped: set[str],
    callbacks: Sequence[Record],
    records: Mapping[str, Record],
) -> bool:
    eligible: set[str] = set()
    pages: dict[str, list[Data]] = defaultdict(list)
    for delivery in callbacks:
        inputs = set(delivery["inputs"])
        if (
            inputs.intersection(stopped)
            or not inputs.intersection(component)
            or not (inputs - component) <= named
        ):
            continue
        if delivery["tool_id"] == "receipt.read":
            args = delivery["args"]
            if args.get("request_ref") != request:
                continue
            value = delivery["value"]
            if (
                value.get("kind") == "open"
                and value.get("part") == "result"
                and value.get("invocation_id") == args["selection"].get("invocation_id")
            ):
                pages[value["invocation_id"]].append(value)
        else:
            key = delivery["read_position"].removeprefix("native-invocation:")
            if key in records and records[key]["tool_id"] == delivery["tool_id"]:
                eligible.add(key)
    for identifier in set(ids) - eligible:
        if identifier not in pages or identifier not in records:
            return False
        data = canonical_json_bytes(
            {"type": "Success", "value": records[identifier]["value"]}
        )
        digest = projection_digest(
            {"invocation_id": identifier}, "result", hashlib.sha256(data).hexdigest()
        )
        covered = 0
        for page in sorted(pages[identifier], key=lambda pg: pg["offset"]):
            start, end = page["offset"], page["end"]
            if not (
                page["digest"] == digest
                and page["total_bytes"] == len(data)
                and 0 <= start <= covered
                and start <= end <= len(data)
                and data[start:end] == page["text"].encode()
            ):
                return False
            covered = max(covered, end)
        if covered != len(data):
            return False
    return True


def _fingerprint(rows: Sequence[Record]) -> str:
    return hashlib.sha256(
        canonical_json_bytes([[r["tool_id"], r["arguments"], r["value"]] for r in rows])
    ).hexdigest()


async def bind_sources(
    db: AsyncConnection,
    scope: str,
    attempt: UUID,
    named: set[UUID],
    stopped: set[UUID],
    sources: Sequence[Source],
    grant: WorkspaceEnrollment | None,
) -> list[Data]:
    slots: list[Data] = [dict(state="unavailable", kind=s.kind) for s in sources]
    if not sources or grant is None:
        return slots
    eligible = named - stopped
    candidates = [
        (i, s)
        for i, s in enumerate(sources[:MAX_SOURCES])
        if UUID(s.request_id) in eligible
        and 1 <= len(s.reads) <= 8
        and len(set(s.reads)) == len(s.reads)
        and (s.passage is None or len(s.passage.encode()) <= 512)
    ]
    ids = {UUID(r) for _, s in candidates for r in s.reads}
    if not ids:
        return slots
    records = await _originals(db, scope, grant, ids)
    callbacks = await _deliveries(db, attempt, ids)
    components: dict[str, set[str]] = {}
    for i, s in candidates:
        if s.request_id not in components:
            components[s.request_id] = set(
                map(str, await causal_component_ids(db, (UUID(s.request_id),)))
            )
        try:
            if not _observed(
                s.reads,
                s.request_id,
                components[s.request_id],
                set(map(str, eligible)),
                set(map(str, stopped)),
                callbacks,
                records,
            ):
                continue
            rows = [records[r] for r in s.reads]
            detail = project(s.kind, s.item, rows, grant, s.passage)
            slots[i] = dict(
                state="available",
                kind=s.kind,
                grant_id=str(grant.grant_id),
                subject=grant.subject,
                item=s.item,
                reads=s.reads,
                focus=detail["focus"],
                passage=detail["coverage"]["passage"],
                evidence_digest=_fingerprint(rows),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return slots


def source_is_available(slot: object, grant: WorkspaceEnrollment | None) -> bool:
    if grant is None or not isinstance(slot, dict):
        return False
    entry = cast(Data, slot)
    return entry.get("state") == "available" and (
        entry.get("grant_id"),
        entry.get("subject"),
    ) == (str(grant.grant_id), grant.subject)


async def read_source(
    connection: AsyncConnection,
    scope: str,
    slot: object,
    grant: WorkspaceEnrollment | None,
) -> Data:
    unavailable = {"state": "unavailable"}
    if grant is None or not source_is_available(slot, grant):
        return unavailable
    slot = cast(Data, slot)
    try:
        ids = cast(list[str], slot["reads"])
        if not 1 <= len(ids) <= 8 or len(set(ids)) != len(ids):
            return unavailable
        originals = await _originals(connection, scope, grant, {UUID(r) for r in ids})
        rows = [originals[r] for r in ids]
        if _fingerprint(rows) != slot["evidence_digest"]:
            return unavailable
        detail = project(slot["kind"], slot["item"], rows, grant, None)
        focus = slot["focus"]
        status = slot["passage"]
        if status not in {"unrequested", "matched", "missing"} or (
            status == "matched"
        ) != (focus is not None):
            return unavailable
        if focus:
            begin, end = focus["start"], focus["end"]
            through = begin
            if not isinstance(begin, int) or not isinstance(end, int) or begin >= end:
                return unavailable
            for seg in detail["segments"]:
                if seg["part"] != focus["part"] or seg["digest"] != focus["digest"]:
                    continue
                if seg["start"] <= through < seg["end"]:
                    text = seg["text"].encode()
                    text[
                        through - seg["start"] : min(seg["end"], end) - seg["start"]
                    ].decode()
                    through = min(seg["end"], end)
                if through == end:
                    break
            if through != end:
                return unavailable
        detail["focus"] = focus
        detail["coverage"]["passage"] = status
        return detail
    except (KeyError, IndexError, TypeError, ValueError):
        return unavailable

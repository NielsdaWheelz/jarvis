"""A standing check's owner-selected scope and the host's enrollment binding."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, Literal, Self, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Select, String, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.action_requests import CanonicalUuid
from jarvis.db import native_invocation, read_position


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class CalendarWindow(_Closed):
    ids: Annotated[list[str], Field(min_length=1, max_length=20)]
    days_ahead: Annotated[int, Field(strict=True, ge=1, le=31)]

    @field_validator("ids")
    @classmethod
    def calendar_ids(cls, ids: list[str]) -> list[str]:
        if len(set(ids)) != len(ids) or any(
            not item.strip() or "\0" in item or len(item.encode()) > 1024
            for item in ids
        ):
            raise ValueError("expected distinct observed calendar identifiers")
        return ids

    def interval(
        self, as_of: datetime, owner_zone: ZoneInfo
    ) -> tuple[datetime, datetime]:
        """Use local midnights even across daylight saving changes."""
        if as_of.tzinfo is None:
            raise ValueError("observation time must be timezone aware")
        today = as_of.astimezone(owner_zone).date()
        return (
            datetime.combine(today, time.min, owner_zone).astimezone(UTC),
            datetime.combine(
                today + timedelta(days=self.days_ahead), time.min, owner_zone
            ).astimezone(UTC),
        )


class WorkspaceSelectors(_Closed):
    gmail_query: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    calendar: CalendarWindow | None = None
    until: date | None

    @field_validator("gmail_query")
    @classmethod
    def bounded_query(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip() or "\0" in value or len(value.encode()) > 512
        ):
            raise ValueError("expected a nonblank gmail query within 512 bytes")
        return value

    @model_validator(mode="after")
    def selected(self) -> Self:
        if self.gmail_query is None and self.calendar is None:
            raise ValueError(
                "a standing check needs a gmail query or calendar interval"
            )
        return self

    def expired(self, as_of: datetime, owner_zone: ZoneInfo) -> bool:
        return (
            self.until is not None and as_of.astimezone(owner_zone).date() > self.until
        )


class WorkspaceCheck(WorkspaceSelectors):
    grant_id: CanonicalUuid


class WorkspaceResult(_Closed):
    occurrence_id: CanonicalUuid
    outcome: Literal["match", "no_match", "inconclusive"]
    evidence: Annotated[list[CanonicalUuid], Field(max_length=256)]

    @field_validator("evidence")
    @classmethod
    def unique_receipts(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("evidence must identify distinct invocations")
        return value


def workspace_read_receipts(grant_id: str) -> Select[Any]:
    """A recorded successful reply at its own native read position on this grant."""
    return (
        select(
            native_invocation.c.id,
            native_invocation.c.tool_id,
            native_invocation.c.proposal["arguments"].label("arguments"),
            read_position.c.result["value"].label("value"),
        )
        .join(
            read_position, native_invocation.c.read_position == read_position.c.position
        )
        .where(
            native_invocation.c.validation == "accepted",
            native_invocation.c.reply_recorded_at.is_not(None),
            native_invocation.c.frozen_contract["effect"].as_string() == "Read",
            native_invocation.c.read_position
            == "native-invocation:" + sql_cast(native_invocation.c.id, String),
            native_invocation.c.reply_receipt["type"].as_string() == "tool_result_ref",
            native_invocation.c.reply_receipt["result_ref"].as_string()
            == read_position.c.position,
            native_invocation.c.reply_receipt["success"].as_boolean().is_(True),
            read_position.c.state == "completed",
            read_position.c.contract["tool_id"].as_string()
            == native_invocation.c.tool_id,
            read_position.c.contract["workspace_grant_id"].as_string() == grant_id,
            read_position.c.result["type"].as_string() == "Success",
        )
    )


def completed_workspace_reads(
    attempt_id: UUID, grant_id: str, input_ids: tuple[str, ...]
) -> Select[Any]:
    return workspace_read_receipts(grant_id).where(
        native_invocation.c.attempt_id == attempt_id,
        native_invocation.c.proposal["input_ids"] == list(input_ids),
    )


async def observed_calendar_ids(
    connection: AsyncConnection,
    calendar: CalendarWindow,
    *,
    attempt_id: str,
    grant_id: UUID,
    input_ids: tuple[str, ...],
    before_ordinal: int,
    admitted_at: datetime,
) -> bool:
    try:
        attempt = UUID(attempt_id)
    except ValueError:
        return False
    rows = await connection.execute(
        completed_workspace_reads(attempt, str(grant_id), input_ids).where(
            native_invocation.c.tool_id == "calendar.list_calendars",
            native_invocation.c.ordinal < before_ordinal,
            native_invocation.c.reply_recorded_at <= admitted_at,
        )
    )
    visible = {
        item["calendar_id"]
        for row in rows
        for item in row.value.get("items") or ()
        if item.get("kind") == "calendar"
    }
    return visible.issuperset(calendar.ids)


@dataclass(frozen=True, slots=True)
class CheckRead:
    """One successful, host-decoded read from this attempt."""

    invocation_id: UUID
    tool: str
    arguments: Mapping[str, Any]
    observed_at: datetime
    coverage: Literal["complete", "more", "partial"]
    next_cursor: str | None = None
    next_offset: int | None = None
    thread_ids: tuple[str, ...] = ()
    message_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    next_digest: str | None = None
    has_content: bool = False
    has_chunk: bool = False
    manifest_fragment: str | None = None

    @classmethod
    def from_receipt(
        cls,
        invocation_id: UUID,
        tool: str,
        arguments: Mapping[str, Any],
        value: Mapping[str, Any],
    ) -> Self | None:
        """Decode an already validated, completed B read value from this attempt."""
        if tool not in {
            "gmail.search",
            "gmail.read_thread",
            "gmail.get_message",
            "calendar.list_events",
            "calendar.get_event",
        }:
            return None
        observed = _instant(value.get("observed_at"))
        if observed is None:
            return None
        state = value["coverage"]["state"]
        coverage: Literal["complete", "more", "partial"] = (
            "complete"
            if state == "complete_visible"
            else "more"
            if state == "more"
            else "partial"
        )
        items = value.get("items") or ()
        next_page: Mapping[str, Any] = value.get("next") or {}
        chunk: Mapping[str, Any] = value.get("chunk") or {}
        threads: tuple[str, ...] = ()
        messages: tuple[str, ...] = ()
        events: tuple[str, ...] = ()
        if tool == "gmail.search":
            threads = tuple(item["thread_id"] for item in items)
            messages = tuple(
                p["message_id"] for item in items for p in item["previews"]
            )
        elif tool == "gmail.read_thread":
            messages = tuple(item["message_id"] for item in items)
        elif tool in {"calendar.list_events", "calendar.get_event"}:
            events = tuple(item["event_id"] for item in items)
        return cls(
            invocation_id,
            tool,
            arguments,
            observed,
            coverage,
            next_page.get("cursor"),
            next_page.get("offset"),
            threads,
            messages,
            events,
            next_page.get("digest"),
            bool(chunk.get("text")),
            isinstance(chunk.get("text"), str),
            chunk.get("text")
            if tool == "gmail.get_message"
            and arguments.get("section", "message") == "message"
            else None,
        )


def _complete_pages(
    pages: Sequence[CheckRead], *, offset: bool
) -> list[CheckRead] | None:
    field = "offset" if offset else "cursor"
    first = 0 if offset else None
    steps = {item.arguments.get(field, first): item for item in pages}
    visited: list[CheckRead] = []
    key: object = first
    while (item := steps.pop(key, None)) is not None:
        if item.coverage == "partial":
            return None
        if (
            offset
            and visited
            and item.arguments.get("digest") != visited[-1].next_digest
        ):
            return None
        visited.append(item)
        key = item.next_offset if offset else item.next_cursor
        if key is None:
            return visited if item.coverage == "complete" else None
    return None


def _complete_message(message_id: str, reads: Sequence[CheckRead]) -> bool:
    sections: dict[tuple[object, ...], list[CheckRead]] = {}
    for read in reads:
        if read.arguments.get("message_id") == message_id and read.has_chunk:
            section = (
                read.arguments.get("section", "message"),
                read.arguments.get("part_id"),
                read.arguments.get("text_view"),
            )
            sections.setdefault(section, []).append(read)
    manifest = _complete_pages(sections.get(("message", None, None), ()), offset=True)
    if not manifest or any(page.manifest_fragment is None for page in manifest):
        return False
    # The normalized RAW projection is JSON even when a descriptor spans chunks.
    try:
        data = json.loads("".join(page.manifest_fragment or "" for page in manifest))
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    metadata = cast(dict[str, Any], data)
    parts = metadata.get("parts")
    if (
        metadata.get("message_id") != message_id
        or not isinstance(parts, list)
        or not parts
    ):
        return False
    for descriptor in cast(list[Any], parts):
        if not isinstance(descriptor, dict):
            return False
        part = cast(dict[str, Any], descriptor)
        part_id = part.get("part_id")
        media = part.get("media_type")
        if (
            not isinstance(part_id, str)
            or not part_id
            or not isinstance(media, str)
            or not media.startswith("text/")
            or part.get("issue") is not None
        ):
            return False
        if not any(
            _complete_pages(sections.get(("body_part", part_id, view), ()), offset=True)
            for view in ("decoded", "readable")
        ):
            return False
    return True


def _instant(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC)
    return None


@dataclass(frozen=True, slots=True)
class WorkspaceOccurrence:
    occurrence_id: UUID
    work_id: UUID
    wake_id: UUID
    check: WorkspaceCheck
    due_at: datetime
    owner_zone: ZoneInfo
    calendar_interval: tuple[datetime, datetime] | None

    @classmethod
    def from_wake(
        cls, occurrence_id: UUID, text: str, owner_zone: ZoneInfo, as_of: datetime
    ) -> Self | None:
        """Decode a canonical work_wake using the attempt's admission time."""
        body = json.loads(text)
        record = body["record"]
        if record.get("workspace_check") is None:
            return None
        check = WorkspaceCheck.model_validate(record["workspace_check"])
        due_at = _instant(body["scheduled_for"])
        if due_at is None:
            raise ValueError("invalid standing-check due time")
        return cls(
            occurrence_id,
            UUID(record["id"]),
            UUID(record["wake_id"]),
            check,
            due_at,
            owner_zone,
            check.calendar.interval(as_of, owner_zone) if check.calendar else None,
        )

    def current(
        self, row: Mapping[Any, Any] | None, grant_id: UUID | None, as_of: datetime
    ) -> bool:
        return (
            row is not None
            and row["id"] == self.work_id
            and row["wake_id"] == self.wake_id
            and row["state"] not in ("done", "cancelled")
            and row["repeat"] is not None
            and row["workspace_check"] == self.check.model_dump(mode="json")
            and str(grant_id) == self.check.grant_id
            and not self.check.expired(as_of, self.owner_zone)
        )

    def authorize_read(
        self, tool: str, arguments: Mapping[str, Any], observations: Sequence[CheckRead]
    ) -> bool:
        """Require exact selected scopes and locally observed child ids."""
        observations = [
            item for item in observations if item.observed_at >= self.due_at
        ]
        query, window = self.check.gmail_query, self.check.calendar
        calendar_id = arguments.get("calendar_id")
        if tool == "gmail.search":
            if (
                query is None
                or arguments.get("query") != query
                or arguments.get("include_spam_trash") is True
            ):
                return False
        elif tool == "calendar.list_events":
            if (
                not window
                or calendar_id not in window.ids
                or self.calendar_interval
                != (
                    _instant(arguments.get("time_min")),
                    _instant(arguments.get("time_max")),
                )
            ):
                return False
        elif tool in {"gmail.read_thread", "gmail.get_message"}:
            if query is None:
                return False
            key = "thread_id" if tool == "gmail.read_thread" else "message_id"
            if not any(
                arguments.get(key)
                in (item.thread_ids if key == "thread_id" else item.message_ids)
                for item in observations
            ):
                return False
            if not arguments.get("offset", 0):
                return True
            return any(
                item.tool == tool
                and item.arguments.get(key) == arguments.get(key)
                and all(
                    item.arguments.get(field) == arguments.get(field)
                    for field in ("section", "part_id", "text_view")
                )
                and item.next_offset == arguments["offset"]
                and item.next_digest is not None
                and item.next_digest == arguments.get("digest")
                for item in observations
            )
        elif tool == "calendar.get_event":
            return (
                window is not None
                and calendar_id in window.ids
                and any(
                    item.tool == "calendar.list_events"
                    and item.arguments.get("calendar_id") == calendar_id
                    and arguments.get("event_id") in item.event_ids
                    for item in observations
                )
            )
        else:
            return False
        cursor = arguments.get("cursor")
        return cursor is None or any(
            item.tool == tool
            and item.arguments.get("calendar_id") == calendar_id
            and item.next_cursor == cursor
            for item in observations
        )

    def settle(
        self, result: WorkspaceResult | None, observations: Sequence[CheckRead]
    ) -> Literal["match", "no_match", "inconclusive"]:
        if (
            result is None
            or result.occurrence_id != str(self.occurrence_id)
            or result.outcome == "inconclusive"
        ):
            return "inconclusive"
        valid: list[CheckRead] = []
        for item in observations:
            if item.observed_at >= self.due_at and self.authorize_read(
                item.tool, item.arguments, valid
            ):
                valid.append(item)
        cited = {
            str(item.invocation_id): item
            for item in valid
            if str(item.invocation_id) in result.evidence
        }
        if not cited or len(cited) != len(result.evidence):
            return "inconclusive"
        roots = [("gmail.search", None)] if self.check.gmail_query is not None else []
        if self.check.calendar:
            roots += [
                ("calendar.list_events", identifier)
                for identifier in self.check.calendar.ids
            ]
        for tool, calendar_id in roots:
            pages = [
                item
                for item in cited.values()
                if item.tool == tool
                and item.arguments.get("calendar_id") == calendar_id
            ]
            if not any(item.arguments.get("cursor") is None for item in pages):
                return "inconclusive"
            if (
                result.outcome == "no_match"
                and _complete_pages(pages, offset=False) is None
            ):
                return "inconclusive"
        threads = {
            thread
            for item in cited.values()
            if item.tool == "gmail.search"
            for thread in item.thread_ids
        }
        messages = [item for item in cited.values() if item.tool == "gmail.get_message"]
        if result.outcome == "no_match":
            if any(item.coverage == "partial" for item in cited.values()):
                return "inconclusive"
            # Search previews can omit members. Traverse each returned conversation
            # and inspect each actual message before accepting a negative result.
            for thread in threads:
                pages = _complete_pages(
                    [
                        item
                        for item in cited.values()
                        if item.tool == "gmail.read_thread"
                        and item.arguments.get("thread_id") == thread
                    ],
                    offset=True,
                )
                if pages is None or not any(page.message_ids for page in pages):
                    return "inconclusive"
                if not all(
                    _complete_message(mid, messages)
                    for page in pages
                    for mid in page.message_ids
                ):
                    return "inconclusive"
        elif not any(item.has_content for item in messages) and (
            threads or not any(item.event_ids for item in cited.values())
        ):
            return "inconclusive"
        return result.outcome

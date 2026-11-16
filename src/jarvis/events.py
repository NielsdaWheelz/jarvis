"""Owned source cursors and atomic canonical publication; provider I/O lives outside."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from llm_agent_kernel import input_batch
from llm_tools import (
    PromptSections,
    ToolId,
    ToolResult,
    canonical_json_bytes,
    render_prompt,
)
from pydantic import BaseModel
from sqlalchemy import RowMapping, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.actions import (
    ActionPersistenceDefect,
    action_replay_result,
    complete_local_action,
    require_locked_action,
)
from jarvis.db import action, event_cursor, message
from jarvis.event_tools import (
    EVENT_MUTATION_IDS,
    POLL_SECONDS,
    AccountUnavailable,
    CalendarAttention,
    ChangesProgress,
    EventPayload,
    EventsConfigureInput,
    EventsConfigureSuccess,
    EventsStatusSuccess,
    FailureCode,
    FamilyStatus,
    InventoryProgress,
    MailProgress,
    SourceError,
    SourceStatus,
    SourceStream,
    StreamKind,
    UpcomingProgress,
    attention_due,
    calendar_zone,
    provider_id,
    validate_event_result,
)
from jarvis.input_framing import host_input
from jarvis.messages import append_waking_input
from jarvis.ownership import Database, lock_conversation


@dataclass(frozen=True, slots=True)
class Cursor:
    kind: StreamKind
    account_id: str
    resource_id: str
    enabled: bool | None
    progress: dict[str, object]
    next_poll_at: datetime | None
    last_success_at: datetime | None
    error: dict[str, object] | None
    seen_inventory_scan: UUID | None


@dataclass(frozen=True, slots=True)
class Observation:
    source: str
    identity: tuple[object, ...]
    payload: EventPayload
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarResource:
    resource_id: str
    calendar_zone: str | None


@dataclass(frozen=True, slots=True)
class Failure:
    code: FailureCode
    retry_at: datetime | None = None
    blocked: bool = False
    family: bool = False
    shared_auth: bool = False


def source_identity(identity: tuple[object, ...]) -> str:
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def _progress(kind: str, value: dict[str, object]) -> dict[str, object]:
    if kind == "gmail":
        parsed = MailProgress.model_validate(value)
    elif kind == "calendar_list":
        parsed = InventoryProgress.model_validate(value)
    elif kind == "calendar_changes":
        parsed = ChangesProgress.model_validate(value)
    elif kind == "calendar_upcoming":
        parsed = UpcomingProgress.model_validate(value)
    else:
        raise ValueError("unknown source kind")
    return parsed.model_dump(mode="json")


def _cursor(row: RowMapping) -> Cursor:
    error = row["error"]
    return Cursor(
        kind=cast(StreamKind, row["kind"]),
        account_id=provider_id(row["account_id"]),
        resource_id=row["resource_id"],
        enabled=row["enabled"],
        progress=_progress(row["kind"], row["progress"]),
        next_poll_at=row["next_poll_at"],
        last_success_at=row["last_success_at"],
        error=None
        if error is None
        else SourceError.model_validate(error).model_dump(mode="json"),
        seen_inventory_scan=row["seen_inventory_scan"],
    )


def _root(kind: str) -> str:
    return "gmail" if kind == "gmail" else "calendar_list"


def _where(cursor: Cursor):
    return (
        (event_cursor.c.kind == cursor.kind)
        & (event_cursor.c.account_id == cursor.account_id)
        & (event_cursor.c.resource_id == cursor.resource_id)
    )


class EventStore:
    def __init__(self, database: Database, conversation_id: str) -> None:
        self._database = database
        self._conversation_id = conversation_id
        self.account: str | None = None
        self.notify_changed: Callable[[], None] = lambda: None
        self.notify_input: Callable[[], None] = lambda: None
        self.publication_allowed: Callable[[], bool] = lambda: True

    async def initialize(self, account: str, history_id: str) -> bool:
        account = provider_id(account)
        if self.account is not None and self.account != account:
            raise ValueError("verified source account cannot change during a process")
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            if await self._paused(connection) or not self.publication_allowed():
                return False
            now = datetime.now(UTC)
            for kind, progress in (
                (
                    "gmail",
                    {
                        "history_id": history_id,
                        "page_token": None,
                        "consumed": 0,
                        "prefix_sha256": None,
                    },
                ),
                ("calendar_list", {"scan_id": None, "page_token": None}),
            ):
                await connection.execute(
                    insert(event_cursor)
                    .values(
                        kind=kind,
                        account_id=account,
                        resource_id="",
                        enabled=True,
                        progress=_progress(kind, dict(progress)),
                        next_poll_at=now + timedelta(seconds=POLL_SECONDS)
                        if kind == "gmail"
                        else now,
                        last_success_at=now if kind == "gmail" else None,
                    )
                    .on_conflict_do_nothing()
                )
        self.account = account
        self.notify_changed()
        return True

    async def _paused(self, connection: AsyncConnection) -> bool:
        return (
            await connection.scalar(
                select(message.c.control_kind)
                .where(
                    message.c.source_conversation_id == self._conversation_id,
                    message.c.control_kind.is_not(None),
                )
                .order_by(message.c.control_sequence.desc())
                .limit(1)
            )
            == "pause"
        )

    async def _rows(
        self, connection: AsyncConnection, *, locked: bool = False
    ) -> list[Cursor]:
        statement = (
            select(event_cursor)
            .where(event_cursor.c.account_id == self.account)
            .order_by(
                event_cursor.c.resource_id != "",
                event_cursor.c.kind,
                event_cursor.c.resource_id,
            )
        )
        if locked:
            statement = statement.with_for_update()
        return [
            _cursor(row) for row in (await connection.execute(statement)).mappings()
        ]

    async def select_due(self, now: datetime) -> Cursor | None:
        async with self._database.begin() as connection:
            if self.account is None or await self._paused(connection):
                return None
            rows = await self._rows(connection)
            roots = {row.kind: row for row in rows if row.resource_id == ""}
            due = [
                row
                for row in rows
                if row.next_poll_at is not None
                and row.next_poll_at <= now
                and roots[_root(row.kind)].enabled
                and roots[_root(row.kind)].next_poll_at is not None
            ]
            return (
                min(
                    due,
                    key=lambda row: (
                        cast(datetime, row.next_poll_at),
                        row.kind,
                        row.resource_id,
                    ),
                )
                if due
                else None
            )

    async def next_due_at(self) -> datetime | None:
        async with self._database.begin() as connection:
            if self.account is None or await self._paused(connection):
                return None
            rows = await self._rows(connection)
            roots = {row.kind: row for row in rows if row.resource_id == ""}
            due = [
                row.next_poll_at
                for row in rows
                if row.next_poll_at is not None
                and roots[_root(row.kind)].enabled
                and roots[_root(row.kind)].next_poll_at is not None
            ]
            return min(due) if due else None

    async def admission(self, cursor: Cursor) -> bool:
        async with self._database.begin() as connection:
            if (
                not self.publication_allowed()
                or cursor.account_id != self.account
                or await self._paused(connection)
            ):
                return False
            rows = await self._rows(connection)
            root = next(
                (
                    row
                    for row in rows
                    if row.kind == _root(cursor.kind) and row.resource_id == ""
                ),
                None,
            )
            current = next(
                (
                    row
                    for row in rows
                    if (row.kind, row.resource_id) == (cursor.kind, cursor.resource_id)
                ),
                None,
            )
            return (
                root is not None
                and root.enabled is True
                and root.next_poll_at is not None
                and current is not None
                and current.next_poll_at is not None
                and current.progress == cursor.progress
            )

    async def is_published(self, source: str, identity: tuple[object, ...]) -> bool:
        async with self._database.begin() as connection:
            return (
                await connection.scalar(
                    select(message.c.id).where(
                        message.c.source == source,
                        message.c.source_conversation_id == self._conversation_id,
                        message.c.source_message_id == source_identity(identity),
                    )
                )
                is not None
            )

    async def has_echo(
        self,
        kind: Literal["gmail", "calendar"],
        *,
        message_id: str | None = None,
        calendar_id: str | None = None,
        event_id: str | None = None,
        etag: str | None = None,
    ) -> bool:
        if self.account is None:
            return False
        query = select(action.c.id).where(
            action.c.status == "succeeded",
            action.c.result["type"].as_string() == "Success",
            action.c.result["value"]["account"].as_string() == self.account,
        )
        if kind == "gmail":
            if message_id is None:
                return False
            query = query.where(
                action.c.tool_name == "gmail.send_draft",
                action.c.result["value"]["sent_message_id"].as_string() == message_id,
            )
        else:
            if calendar_id is None or event_id is None or etag is None:
                return False
            query = query.where(
                action.c.tool_name.in_(
                    ("calendar.create_event", "calendar.update_event")
                ),
                action.c.result["value"]["event"]["calendar_id"].as_string()
                == calendar_id,
                action.c.result["value"]["event"]["event_id"].as_string() == event_id,
                action.c.result["value"]["event"]["etag"].as_string() == etag,
            )
        async with self._database.begin() as connection:
            return await connection.scalar(query.limit(1)) is not None

    async def _publish(
        self, connection: AsyncConnection, observation: Observation, now: datetime
    ) -> bool:
        expected = {
            "email_added": "email_event",
            "calendar_changed": "calendar_event",
            "calendar_attention": "calendar_attention",
            "source_status": "event_status",
        }
        if (
            observation.source != expected[observation.payload.kind]
            or observation.payload.account != self.account
        ):
            raise ValueError("source publication has foreign kind or account")
        identity = source_identity(observation.identity)
        if (
            await connection.scalar(
                select(message.c.id).where(
                    message.c.source == observation.source,
                    message.c.source_conversation_id == self._conversation_id,
                    message.c.source_message_id == identity,
                )
            )
            is not None
        ):
            return False
        if isinstance(observation.payload, CalendarAttention):
            due = attention_due(
                observation.payload.event, now, observation.payload.owner_zone
            )
            if due is None or due != observation.payload.due_at:
                return False
        appended = await append_waking_input(
            connection,
            role="host",
            text=canonical_json_bytes(
                observation.payload.model_dump(mode="json")
            ).decode(),
            source=observation.source,
            source_conversation_id=self._conversation_id,
            source_message_id=identity,
            created_at=observation.created_at,
        )
        frame = PromptSections(
            (
                input_batch(
                    (host_input(appended.message),),
                    now,
                    render_source_timestamps=True,
                    render_batch_as_of=True,
                ),
            )
        )
        if len(render_prompt(frame).encode()) > 65536:
            raise ValueError("source input exceeds canonical native frame bound")
        return appended.inserted

    async def _status_fact(
        self,
        connection: AsyncConnection,
        cursor: Cursor,
        phase: Literal["outage", "recovered", "gap", "removed"],
        tag: object,
        now: datetime,
        *,
        error: SourceError | None = None,
    ) -> bool:
        payload = SourceStatus(
            account=cursor.account_id,
            observed_at=now,
            stream=SourceStream(kind=cursor.kind, resource_id=cursor.resource_id),
            phase=phase,
            episode_id=None if error is None else error.episode_id,
            code="CursorExpired"
            if phase == "gap"
            else "NotInReadableInventory"
            if phase == "removed"
            else error.code
            if phase == "outage" and error is not None
            else None,
            last_complete_at=cursor.last_success_at,
            coverage="current_only"
            if phase == "recovered"
            else "unknown_gap"
            if phase == "gap"
            else "unavailable",
        )
        return await self._publish(
            connection,
            Observation(
                "event_status",
                (
                    cursor.account_id,
                    cursor.kind,
                    cursor.resource_id,
                    {"phase": phase, "tag": tag},
                ),
                payload,
                now,
            ),
            now,
        )

    async def commit_progress(
        self,
        cursor: Cursor,
        progress: dict[str, object],
        observations: Sequence[Observation] = (),
        *,
        complete: bool = False,
        inventory: Sequence[CalendarResource] = (),
        inventory_complete: bool = False,
        failure: Failure | None = None,
        gap: bool = False,
    ) -> bool:
        progress = _progress(cursor.kind, progress)
        published = False
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            if (
                not self.publication_allowed()
                or cursor.account_id != self.account
                or await self._paused(connection)
            ):
                return False
            rows = await self._rows(connection, locked=True)
            current = next(
                (
                    row
                    for row in rows
                    if (row.kind, row.resource_id) == (cursor.kind, cursor.resource_id)
                ),
                None,
            )
            root = next(
                (
                    row
                    for row in rows
                    if row.kind == _root(cursor.kind) and row.resource_id == ""
                ),
                None,
            )
            if (
                current is None
                or current.progress != cursor.progress
                or current.next_poll_at is None
                or root is None
                or root.enabled is not True
                or root.next_poll_at is None
                or not self.publication_allowed()
            ):
                return False
            now = datetime.now(UTC)
            if cursor.kind == "calendar_upcoming":
                raw_scan = cursor.progress.get("scan")
                scan = (
                    cast(dict[str, object], raw_scan)
                    if isinstance(raw_scan, dict)
                    else None
                )
                if (
                    isinstance(scan, dict)
                    and scan.get("owner_date")
                    != now.astimezone(ZoneInfo(str(scan["owner_zone"])))
                    .date()
                    .isoformat()
                ):
                    observations = tuple(
                        item
                        for item in observations
                        if not isinstance(item.payload, CalendarAttention)
                        or item.payload.event.start is None
                        or item.payload.event.start.type != "all_day"
                    )
            for observation in observations:
                published = (
                    await self._publish(connection, observation, now) or published
                )
            values: dict[str, object] = {
                "progress": progress,
                "next_poll_at": now + timedelta(seconds=POLL_SECONDS)
                if complete
                else now,
            }
            if complete:
                values["last_success_at"] = now
                values["error"] = None
                if current.error is not None:
                    error = SourceError.model_validate(current.error)
                    published = (
                        await self._status_fact(
                            connection,
                            current,
                            "recovered",
                            str(error.episode_id),
                            now,
                            error=error,
                        )
                        or published
                    )
            if gap:
                expired = (
                    current.progress.get("history_id")
                    if current.kind == "gmail"
                    else current.progress.get("sync_token")
                )
                tag = hashlib.sha256(canonical_json_bytes(expired)).hexdigest()
                published = (
                    await self._status_fact(connection, current, "gap", tag, now)
                    or published
                )
            if inventory or inventory_complete:
                if cursor.kind != "calendar_list":
                    raise ValueError("only calendar inventory can publish membership")
                scan_value = progress.get("scan_id") or current.progress.get("scan_id")
                if scan_value is None:
                    raise ValueError("inventory membership needs a scan identity")
                scan_id = UUID(str(scan_value))
                for calendar in inventory:
                    provider_id(calendar.resource_id)
                    zone = (
                        None
                        if calendar.calendar_zone is None
                        else calendar_zone(calendar.calendar_zone)
                    )
                    for kind, initial in (
                        ("calendar_changes", {"sync_token": None, "page_token": None}),
                        ("calendar_upcoming", {"calendar_zone": zone, "scan": None}),
                    ):
                        child = next(
                            (
                                row
                                for row in rows
                                if row.kind == kind
                                and row.resource_id == calendar.resource_id
                            ),
                            None,
                        )
                        child_values: dict[str, object] = {
                            "seen_inventory_scan": scan_id
                        }
                        if child is None:
                            await connection.execute(
                                insert(event_cursor).values(
                                    kind=kind,
                                    account_id=self.account,
                                    resource_id=calendar.resource_id,
                                    enabled=None,
                                    progress=initial,
                                    next_poll_at=now,
                                    seen_inventory_scan=scan_id,
                                )
                            )
                            child = Cursor(
                                cast(StreamKind, kind),
                                cursor.account_id,
                                calendar.resource_id,
                                None,
                                dict(initial),
                                now,
                                None,
                                None,
                                scan_id,
                            )
                        if (
                            kind == "calendar_upcoming"
                            and child.progress.get("calendar_zone") != zone
                        ):
                            child_values["progress"] = {
                                "calendar_zone": zone,
                                "scan": None,
                            }
                            if zone is not None and child.next_poll_at is not None:
                                child_values["next_poll_at"] = now
                        if zone is None:
                            previous = (
                                None
                                if child.error is None
                                else SourceError.model_validate(child.error)
                            )
                            error = SourceError(
                                episode_id=uuid4()
                                if previous is None
                                else previous.episode_id,
                                code="InvalidResponse",
                                since=now if previous is None else previous.since,
                                retry_count=1
                                if previous is None
                                else previous.retry_count,
                            )
                            child_values["next_poll_at"] = None
                            child_values["error"] = error.model_dump(mode="json")
                            if previous is None:
                                published = (
                                    await self._status_fact(
                                        connection,
                                        child,
                                        "outage",
                                        str(error.episode_id),
                                        now,
                                        error=error,
                                    )
                                    or published
                                )
                        await connection.execute(
                            update(event_cursor)
                            .where(_where(child))
                            .values(**child_values)
                        )
                if inventory_complete:
                    stale = [
                        row
                        for row in rows
                        if row.resource_id
                        and row.seen_inventory_scan != scan_id
                        and row.resource_id
                        not in {item.resource_id for item in inventory}
                    ]
                    for child in stale:
                        if child.kind == "calendar_changes":
                            published = (
                                await self._status_fact(
                                    connection,
                                    child,
                                    "removed",
                                    {
                                        "scan_id": str(scan_id),
                                        "calendar_id": child.resource_id,
                                    },
                                    now,
                                    error=None
                                    if child.error is None
                                    else SourceError.model_validate(child.error),
                                )
                                or published
                            )
                        await connection.execute(
                            delete(event_cursor).where(_where(child))
                        )
            await connection.execute(
                update(event_cursor).where(_where(current)).values(**values)
            )
            if failure is not None:
                targets = [current]
                if failure.shared_auth:
                    targets = [row for row in rows if not row.resource_id]
                elif failure.family:
                    targets = [root]
                for target in targets:
                    previous = (
                        None
                        if target.error is None
                        else SourceError.model_validate(target.error)
                    )
                    count = 1 if previous is None else min(5, previous.retry_count + 1)
                    error = SourceError(
                        episode_id=uuid4() if previous is None else previous.episode_id,
                        code=failure.code,
                        since=now if previous is None else previous.since,
                        retry_count=count,
                    )
                    deadline = (
                        None
                        if failure.blocked
                        else max(
                            now
                            + timedelta(seconds=(60, 120, 240, 480, 900)[count - 1]),
                            failure.retry_at or now,
                        )
                    )
                    await connection.execute(
                        update(event_cursor)
                        .where(_where(target))
                        .values(
                            error=error.model_dump(mode="json"), next_poll_at=deadline
                        )
                    )
                    if previous is None:
                        published = (
                            await self._status_fact(
                                connection,
                                target,
                                "outage",
                                str(error.episode_id),
                                now,
                                error=error,
                            )
                            or published
                        )
        if published:
            self.notify_input()
        self.notify_changed()
        return True

    async def recover_mutation(self, action_id: UUID) -> ToolResult | None:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            stored = await require_locked_action(connection, action_id)
            scope = await connection.scalar(
                select(message.c.source_conversation_id).where(
                    message.c.id == stored.origin_message_id
                )
            )
            if (
                stored.tool_name not in EVENT_MUTATION_IDS
                or scope != self._conversation_id
            ):
                raise ActionPersistenceDefect(
                    "source recovery requires its original local mutation"
                )
            return action_replay_result(stored)

    async def mutate(
        self, action_id: UUID, tool_id: ToolId, arguments: BaseModel
    ) -> ToolResult:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            stored = await require_locked_action(connection, action_id)
            replay = action_replay_result(stored)
            if replay is not None:
                return replay
            scope = await connection.scalar(
                select(message.c.source_conversation_id).where(
                    message.c.id == stored.origin_message_id
                )
            )
            if (
                not isinstance(arguments, EventsConfigureInput)
                or tool_id not in EVENT_MUTATION_IDS
                or stored.tool_name != tool_id
                or stored.payload != arguments.model_dump(mode="json")
                or stored.status != "executing"
                or stored.attempts < 1
                or scope != self._conversation_id
            ):
                raise ActionPersistenceDefect(
                    "source configuration differs from its entered action"
                )
            now = datetime.now(UTC)
            if self.account is None:
                result: ToolResult = {
                    "type": "Failure",
                    "error": AccountUnavailable().model_dump(mode="json"),
                }
            else:
                rows = await self._rows(connection, locked=True)
                root_kind = "gmail" if arguments.source == "email" else "calendar_list"
                for row in rows:
                    if _root(row.kind) != root_kind:
                        continue
                    values: dict[str, object] = {}
                    if not row.resource_id:
                        values["enabled"] = arguments.enabled
                    if arguments.enabled and row.next_poll_at is None:
                        values["next_poll_at"] = now
                    if values:
                        await connection.execute(
                            update(event_cursor).where(_where(row)).values(**values)
                        )
                result = {
                    "type": "Success",
                    "value": EventsConfigureSuccess(
                        source=arguments.source, enabled=arguments.enabled
                    ).model_dump(mode="json"),
                }
            validate_event_result(tool_id, result)
            await complete_local_action(connection, stored, result, now)
        self.notify_changed()
        return result

    async def status(self) -> EventsStatusSuccess:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            now = datetime.now(UTC)
            paused = await self._paused(connection)
            rows = await self._rows(connection) if self.account is not None else []
            families: list[FamilyStatus] = []
            for family in ("email", "calendar"):
                members = [
                    row
                    for row in rows
                    if _root(row.kind)
                    == ("gmail" if family == "email" else "calendar_list")
                ]
                if not members:
                    families.append(
                        FamilyStatus(
                            source=family,
                            enabled=None,
                            state="unverified",
                            last_success_at=None,
                            next_poll_at=None,
                            baselining_streams=0,
                            catching_up_streams=0,
                            blocked_streams=0,
                            failing_streams=0,
                            readable_calendars=None,
                        )
                    )
                    continue
                root = next(row for row in members if not row.resource_id)
                baselining = sum(
                    (row.kind == "gmail" and row.progress["history_id"] is None)
                    or (
                        row.kind == "calendar_changes"
                        and row.progress["sync_token"] is None
                    )
                    or (
                        row.kind in ("calendar_list", "calendar_upcoming")
                        and row.last_success_at is None
                    )
                    for row in members
                )
                catching = sum(
                    (
                        (
                            row.kind == "gmail"
                            and row.progress["history_id"] is not None
                            and (
                                row.progress["page_token"] is not None
                                or row.progress["consumed"] != 0
                            )
                        )
                        or (
                            row.kind == "calendar_changes"
                            and row.progress["sync_token"] is not None
                            and row.progress["page_token"] is not None
                        )
                        or (
                            row.kind == "calendar_list"
                            and row.last_success_at is not None
                            and row.progress["scan_id"] is not None
                        )
                        or (
                            row.kind == "calendar_upcoming"
                            and row.last_success_at is not None
                            and row.progress["scan"] is not None
                        )
                    )
                    for row in members
                )
                blocked = sum(row.next_poll_at is None for row in members)
                failing = sum(row.error is not None for row in members)
                state = (
                    "disabled"
                    if root.enabled is False
                    else "blocked"
                    if root.next_poll_at is None
                    else "degraded"
                    if failing or blocked
                    else "baselining"
                    if baselining
                    else "catching_up"
                    if catching
                    else "healthy"
                )
                completed = [
                    row.last_success_at
                    for row in members
                    if row.last_success_at is not None
                ]
                due = [
                    row.next_poll_at
                    for row in members
                    if row.next_poll_at is not None
                    and root.enabled
                    and root.next_poll_at is not None
                ]
                families.append(
                    FamilyStatus(
                        source=family,
                        enabled=root.enabled,
                        state=state,
                        last_success_at=min(completed)
                        if len(completed) == len(members)
                        else None,
                        next_poll_at=min(due) if due else None,
                        baselining_streams=baselining,
                        catching_up_streams=catching,
                        blocked_streams=blocked,
                        failing_streams=failing,
                        readable_calendars=None
                        if family == "email"
                        else len(
                            {row.resource_id for row in members if row.resource_id}
                        ),
                    )
                )
        return EventsStatusSuccess(
            account=self.account,
            observed_at=now,
            paused=paused,
            families=families,
        )

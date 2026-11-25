"""Gmail cursor state and atomic publication of observations."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from llm_agent_kernel import input_batch
from llm_tools import (
    PromptSections,
    ToolId,
    ToolResult,
    canonical_json_bytes,
    render_prompt,
)
from pydantic import BaseModel
from sqlalchemy import select, update
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
    AckRepair,
    EventPayload,
    EventsConfigureInput,
    EventsConfigureSuccess,
    EventsStatusSuccess,
    FailureCode,
    MailProgress,
    MailResidual,
    RestoredInterval,
    SourceError,
    SourceStatus,
    SourceStream,
    provider_id,
    validate_event_result,
)
from jarvis.input_framing import host_input
from jarvis.messages import append_waking_input
from jarvis.ownership import Database, lock_conversation


@dataclass(frozen=True, slots=True)
class Cursor:
    account_id: str
    enabled: bool
    progress: dict[str, object]
    next_poll_at: datetime | None
    last_success_at: datetime | None
    error: SourceError | None


@dataclass(frozen=True, slots=True)
class Observation:
    source: Literal["email_event", "event_status"]
    identity: tuple[object, ...]
    payload: EventPayload
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Failure:
    code: FailureCode
    retry_at: datetime | None = None
    blocked: bool = False
    poll_again: bool = False


def source_identity(identity: tuple[object, ...]) -> str:
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def _progress(value: dict[str, object]) -> dict[str, object]:
    return MailProgress.model_validate(value).model_dump(mode="json")


def _ack_repair(
    account: str, progress: dict[str, object], error_code: str | None
) -> AckRepair | None:
    if error_code not in {"AuthUnavailable", "AckUncertain"}:
        return None
    marker = MailProgress.model_validate(progress)
    if marker.ack is None or (
        error_code == "AckUncertain" and marker.ack.phase != "entered"
    ):
        return None
    return AckRepair(
        account=account,
        grant_id=marker.grant_id,
        message_id=marker.ack.message_id,
        label_id=marker.label_id,
        event_source_id=source_identity((account, marker.ack.message_id)),
    )


class EventStore:
    def __init__(self, database: Database, conversation_id: str) -> None:
        self._database = database
        self._conversation_id = conversation_id
        self.account: str | None = None
        self.notify_changed: Callable[[], None] = lambda: None
        self.notify_input: Callable[[], None] = lambda: None
        self.publication_allowed: Callable[[], bool] = lambda: True

    async def enroll(
        self,
        account: str,
        grant_id: UUID,
        label_id: str,
        *,
        expected_progress: dict[str, object] | None,
    ) -> None:
        """Stopped operator handoff after an independently verified empty-label cut.

        expected_progress is the exact inventoried predecessor, or None for a
        fresh account. Its retained copy and overlap proof belong to the operator.
        Rebinding cannot discard a ready or entered acknowledgment.
        """
        account = provider_id(account)
        progress = _progress(
            {
                "grant_id": str(grant_id),
                "label_id": label_id,
                "ack": None,
                "residual": None,
            }
        )
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            row = (
                (
                    await connection.execute(
                        select(event_cursor)
                        .where(event_cursor.c.account_id == account)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (row is None) != (expected_progress is None) or (
                row is not None and row["progress"] != expected_progress
            ):
                raise ValueError("enrolled cursor changed since the handoff inventory")
            if row is not None and row["progress"].get("ack") is not None:
                raise ValueError(
                    "outstanding acknowledgment prevents grant replacement"
                )
            now = datetime.now(UTC)
            if row is None:
                await connection.execute(
                    insert(event_cursor).values(
                        account_id=account,
                        enabled=True,
                        progress=progress,
                        next_poll_at=now,
                        last_success_at=None,
                    )
                )
            else:
                await connection.execute(
                    update(event_cursor)
                    .where(event_cursor.c.account_id == account)
                    .values(
                        progress=progress,
                        next_poll_at=now if row["enabled"] else None,
                        last_success_at=None,
                        error=None,
                    )
                )
        self.account = account
        self.notify_changed()

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

    async def _load_cursor(
        self, connection: AsyncConnection, *, locked: bool = False
    ) -> Cursor | None:
        if self.account is None:
            return None
        statement = select(event_cursor).where(
            event_cursor.c.account_id == self.account
        )
        if locked:
            statement = statement.with_for_update()
        row = (await connection.execute(statement)).mappings().one_or_none()
        if row is None or "grant_id" not in row["progress"]:
            return None
        error = row["error"]
        return Cursor(
            account_id=provider_id(row["account_id"]),
            enabled=row["enabled"],
            progress=_progress(row["progress"]),
            next_poll_at=row["next_poll_at"],
            last_success_at=row["last_success_at"],
            error=None if error is None else SourceError.model_validate(error),
        )

    async def poll_cursor(self) -> Cursor | None:
        async with self._database.begin() as connection:
            if await self._paused(connection):
                return None
            cursor = await self._load_cursor(connection)
            return cursor if cursor is not None and cursor.enabled else None

    async def admission(self, cursor: Cursor) -> bool:
        if not self.publication_allowed() or cursor.account_id != self.account:
            return False
        current = await self.poll_cursor()
        return (
            current is not None
            and current.next_poll_at is not None
            and current.progress == cursor.progress
        )

    async def is_email_published(self, identity: tuple[object, ...]) -> bool:
        async with self._database.begin() as connection:
            return (
                await connection.scalar(
                    select(message.c.id).where(
                        message.c.source == "email_event",
                        message.c.source_conversation_id == self._conversation_id,
                        message.c.source_message_id == source_identity(identity),
                    )
                )
                is not None
            )

    async def has_sent_echo(self, message_id: str) -> bool:
        if self.account is None:
            return False
        query = select(action.c.id).where(
            action.c.status == "succeeded",
            action.c.tool_name == "gmail.send_draft",
            action.c.result["type"].as_string() == "Success",
            action.c.result["value"]["account"].as_string() == self.account,
            action.c.result["value"]["sent_message_id"].as_string() == message_id,
        )
        async with self._database.begin() as connection:
            return await connection.scalar(query.limit(1)) is not None

    async def confirm_removed_ack(
        self, account: str, *, grant_id: UUID, label_id: str, message_id: str
    ) -> None:
        """Record explicit stopped-owner verification of the named removal."""
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            row = (
                (
                    await connection.execute(
                        select(event_cursor)
                        .where(event_cursor.c.account_id == account)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueError("missing enrolled cursor")
            progress = row["progress"]
            error_code = row["error"]["code"] if row["error"] is not None else None
            repair = _ack_repair(account, progress, error_code)
            if (
                repair is None
                or repair.grant_id != grant_id
                or repair.label_id != label_id
                or repair.message_id != message_id
            ):
                raise ValueError("verification does not match the outstanding marker")
            published = await connection.scalar(
                select(message.c.id).where(
                    message.c.source == "email_event",
                    message.c.source_conversation_id == self._conversation_id,
                    message.c.source_message_id == repair.event_source_id,
                )
            )
            if published is None:
                raise ValueError("original published event is unavailable")
            await connection.execute(
                update(event_cursor)
                .where(event_cursor.c.account_id == account)
                .values(
                    progress={**progress, "ack": None},
                    next_poll_at=datetime.now(UTC)
                    if row["enabled"] and error_code == "AckUncertain"
                    else None,
                )
            )
        self.notify_changed()

    async def record_restored_interval(
        self, account: str, *, cut_at: datetime, restored_at: datetime
    ) -> bool:
        """Record one local coverage fact during a stopped restore, before resume."""
        if cut_at > restored_at:
            raise ValueError("restore predates its source cut")
        payload = RestoredInterval(
            account=account, cut_at=cut_at, restored_at=restored_at
        )
        identity = (account, "restore_gap", cut_at.isoformat(), restored_at.isoformat())
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            row = await connection.scalar(
                select(event_cursor.c.account_id).where(
                    event_cursor.c.account_id == account
                )
            )
            if row is None:
                raise ValueError("restored source account has no cursor")
            inserted = await self._publish(
                connection,
                Observation("event_status", identity, payload, restored_at),
                restored_at,
                account=account,
            )
        if inserted:
            self.notify_input()
        return inserted

    async def _publish(
        self,
        connection: AsyncConnection,
        observation: Observation,
        now: datetime,
        *,
        account: str | None = None,
    ) -> bool:
        expected = {
            "email_added": "email_event",
            "source_status": "event_status",
            "gmail_restore_interval": "event_status",
        }
        if observation.source != expected[
            observation.payload.kind
        ] or observation.payload.account != (
            self.account if account is None else account
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
        phase: Literal["outage", "recovered", "gap"],
        tag: object,
        now: datetime,
        *,
        error: SourceError | None = None,
    ) -> bool:
        stream = SourceStream()
        payload = SourceStatus(
            account=cursor.account_id,
            observed_at=now,
            stream=stream,
            phase=phase,
            episode_id=None if error is None else error.episode_id,
            code="CursorExpired"
            if phase == "gap"
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
                    stream.kind,
                    stream.resource_id,
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
        failure: Failure | None = None,
    ) -> bool:
        progress = _progress(progress)
        published = False
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            if (
                not self.publication_allowed()
                or cursor.account_id != self.account
                or await self._paused(connection)
            ):
                return False
            current = await self._load_cursor(connection, locked=True)
            if (
                current is None
                or not current.enabled
                or current.progress != cursor.progress
                or current.next_poll_at is None
                or not self.publication_allowed()
            ):
                return False
            now = datetime.now(UTC)
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
                    published = (
                        await self._status_fact(
                            connection,
                            current,
                            "recovered",
                            str(current.error.episode_id),
                            now,
                            error=current.error,
                        )
                        or published
                    )
            if failure is not None:
                previous = current.error
                count = 1 if previous is None else min(5, previous.retry_count + 1)
                error = SourceError(
                    episode_id=uuid4() if previous is None else previous.episode_id,
                    code=failure.code,
                    since=now if previous is None else previous.since,
                    retry_count=count,
                )
                values["error"] = error.model_dump(mode="json")
                values["next_poll_at"] = (
                    None
                    if failure.blocked
                    else now + timedelta(seconds=POLL_SECONDS)
                    if failure.poll_again
                    else max(
                        now + timedelta(seconds=(60, 120, 240, 480, 900)[count - 1]),
                        failure.retry_at or now,
                    )
                )
                if previous is None:
                    published = (
                        await self._status_fact(
                            connection,
                            current,
                            "outage",
                            str(error.episode_id),
                            now,
                            error=error,
                        )
                        or published
                    )
            await connection.execute(
                update(event_cursor)
                .where(event_cursor.c.account_id == current.account_id)
                .values(**values)
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
            current = await self._load_cursor(connection, locked=True)
            if current is None:
                result: ToolResult = {
                    "type": "Failure",
                    "error": AccountUnavailable().model_dump(mode="json"),
                }
            else:
                values: dict[str, object] = {"enabled": arguments.enabled}
                if arguments.enabled and current.next_poll_at is None:
                    values["next_poll_at"] = now
                await connection.execute(
                    update(event_cursor)
                    .where(event_cursor.c.account_id == current.account_id)
                    .values(**values)
                )
                result = {
                    "type": "Success",
                    "value": EventsConfigureSuccess(
                        enabled=arguments.enabled
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
            cursor = await self._load_cursor(connection)
        residual = (
            None
            if cursor is None or cursor.progress["residual"] is None
            else (MailResidual.model_validate(cursor.progress["residual"]))
        )
        catching_up = cursor is not None and cursor.progress["ack"] is not None
        blocked = cursor is not None and cursor.next_poll_at is None
        failing = cursor is not None and cursor.error is not None
        return EventsStatusSuccess(
            account=self.account,
            observed_at=now,
            paused=paused,
            poll_seconds=POLL_SECONDS,
            enabled=None if cursor is None else cursor.enabled,
            state=(
                "unverified"
                if cursor is None
                else "disabled"
                if not cursor.enabled
                else "blocked"
                if blocked
                else "degraded"
                if failing or residual is not None
                else "catching_up"
                if catching_up
                else "healthy"
            ),
            last_success_at=None if cursor is None else cursor.last_success_at,
            next_poll_at=cursor.next_poll_at
            if cursor is not None and cursor.enabled
            else None,
            baselining=False,
            coverage="unavailable"
            if cursor is None or not cursor.enabled or blocked or paused
            else "incomplete"
            if failing
            or residual is not None
            or catching_up
            or cursor.last_success_at is None
            else "visible_labels_only",
            residual=residual,
            ack_repair=_ack_repair(
                cursor.account_id, cursor.progress, cursor.error.code
            )
            if cursor is not None and cursor.error is not None
            else None,
            count_unreported=(
                cursor is not None
                and cursor.error is not None
                and cursor.error.code == "LabelUnavailable"
                and cursor.next_poll_at is not None
            ),
            failure_code=cursor.error.code
            if cursor is not None and cursor.error
            else None,
            catching_up=catching_up,
            blocked=blocked,
            failing=failing,
        )

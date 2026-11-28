from __future__ import annotations

import hashlib
from contextlib import nullcontext, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID, uuid4, uuid5

from llm_tools import canonical_json_bytes
from sqlalchemy import ColumnElement, RowMapping, Text, case, func, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import (
    action,
    active_native_attempt,
    control_sequence,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
)
from jarvis.home_notices import enqueue_notice
from jarvis.home_pages import DEFAULT_EXPORT
from jarvis.home_refs import HOME_REF_ADAPTER
from jarvis.ownership import Database, lock_conversation, memory_is_admitted

if TYPE_CHECKING:
    from jarvis.attachments import WebUpload
    from jarvis.workspace_host import WorkspaceHost

MessageRole = Literal["owner", "assistant", "host"]

pending_input_order = (
    case((message.c.request_state == "pending", 0), else_=1),
    case((message.c.role == "owner", 0), else_=1),
    message.c.created_at,
    message.c.id,
)


# A capacity refusal retains its origin but only explicit pins steer admission.
native_retry_pin = case(
    (
        message.c.trace["native_retry"]["selection"].as_string() == "pinned",
        message.c.trace["native_retry"]["route"].as_string(),
    )
)


def current_native_retry() -> ColumnElement[bool]:
    from jarvis.codex_config import NATIVE_ROUTES
    from jarvis.native_protocol import NATIVE_REQUEST_SCHEMA

    retry = message.c.trace["native_retry"]
    return (
        retry["selection"].as_string().in_(("fresh", "pinned"))
        & retry["route"].as_string().in_(NATIVE_ROUTES)
        & select(native_attempt.c.id)
        .where(
            sql_cast(native_attempt.c.id, Text) == retry["attempt_id"].as_string(),
            native_attempt.c.conversation_id == message.c.source_conversation_id,
            native_attempt.c.fenced_at.is_not(None),
            native_attempt.c.request["schema_version"].as_string()
            == NATIVE_REQUEST_SCHEMA,
            native_attempt.c.request["route"].as_string() == retry["route"].as_string(),
            select(native_input_delivery.c.attempt_id)
            .where(
                native_input_delivery.c.attempt_id == native_attempt.c.id,
                native_input_delivery.c.message_id == message.c.id,
                native_input_delivery.c.was_waking,
                native_input_delivery.c.state != "rejected",
            )
            .correlate(message, native_attempt)
            .exists(),
        )
        .correlate(message)
        .exists()
    )


MAX_TRACE_BYTES = 16_384


class PersistenceDefect(RuntimeError):
    """Canonical message state is missing or internally inconsistent."""


class IngressUnavailable(RuntimeError):
    """The owner listener is starting or shutting down."""


class SubmissionConflict(ValueError):
    """A submission id was reused for a different owner message."""


class InvalidReference(ValueError):
    """The submitted reference is unavailable in this owner conversation."""


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: UUID
    role: MessageRole
    text: str
    source: str
    source_conversation_id: str
    source_message_id: str | None
    created_at: datetime
    parent_request_id: UUID | None
    processed_at: datetime | None
    processing_attempts: int
    processing_parked_at: datetime | None
    memory_admitted: bool
    trace: dict[str, object]
    request_state: str | None
    wait_reason: str | None
    control_kind: str | None
    home: dict[str, object] | None = None
    native_retry_after: datetime | None = None


def native_retry_evidence(trace: dict[str, object]) -> dict[str, object]:
    retry = trace.get("native_retry")
    return cast(dict[str, object], retry) if isinstance(retry, dict) else {}


@dataclass(frozen=True, slots=True)
class InboundInsert:
    message: StoredMessage
    inserted: bool


@dataclass(frozen=True, slots=True)
class ParkedInput:
    id: UUID
    role: str
    source: str
    reason: str | None
    parked_at: datetime
    attempt_id: UUID | None
    claimed_attempt_id: UUID | None
    releasable: bool


_parked_input = message.c.role.in_(("owner", "host")) & (
    message.c.processing_parked_at.is_not(None)
)
_releasable_parked_input = _parked_input & (
    (message.c.request_state == "pending")
    | (
        (message.c.request_state == "waiting")
        & (message.c.wait_reason == "configuration")
    )
)


def native_fault_retry_used(row: RowMapping) -> bool:
    return row["native_retry_after"] is not None and (
        native_retry_evidence(row["trace"]).get("fault_retry_used") is not False
    )


async def queue_native_retry(
    connection: AsyncConnection,
    row: RowMapping,
    *,
    attempt_id: str,
    route: str,
    selection: Literal["fresh", "pinned"],
    reason: str,
    fault_retry_used: bool,
    retry_at: datetime,
) -> None:
    retry: dict[str, object] = {
        "attempt_id": attempt_id,
        "route": route,
        "selection": selection,
        "reason": reason,
        "fault_retry_used": fault_retry_used,
    }
    trace = {**row["trace"], "native_retry": retry}
    if reason == "context_window_exceeded":
        trace["native_context_retry"] = True
    await connection.execute(
        update(message)
        .where(message.c.id == row["id"])
        .values(
            request_state="pending",
            wait_reason=None,
            native_retry_after=retry_at,
            trace=trace,
        )
    )


async def append_waking_input(
    connection: AsyncConnection,
    *,
    role: Literal["owner", "host"],
    text: str,
    source: str,
    source_conversation_id: str,
    source_message_id: str,
    created_at: datetime,
    parent_request_id: UUID | None = None,
    action_id: UUID | None = None,
    message_id: UUID | None = None,
    home: dict[str, object] | None = None,
    attachment_manifest: tuple[dict[str, object], ...] = (),
) -> InboundInsert:
    """Append one source fact within the producer's existing transaction."""
    if role not in {"owner", "host"}:
        raise ValueError("waking input must be owner or host")
    if attachment_manifest:
        if role != "owner" or source != "web":
            raise ValueError("upload manifests require owner web input")
    else:
        _nonempty(text, "message text")
    _nonempty(source, "message source")
    _nonempty(source_conversation_id, "source conversation id")
    _nonempty(source_message_id, "source message id")
    _aware(created_at, "message created_at")
    await lock_conversation(connection, source_conversation_id)
    if parent_request_id is not None:
        parent = (
            (
                await connection.execute(
                    select(message).where(message.c.id == parent_request_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            parent is None
            or parent["role"] not in {"owner", "host"}
            or parent["control_kind"] is not None
            or parent["source_conversation_id"] != source_conversation_id
        ):
            raise PersistenceDefect("event parent is not a waking conversation input")
    if source == "action" or action_id is not None:
        origin = await connection.scalar(
            select(action.c.origin_message_id).where(action.c.id == action_id)
        )
        if (
            role != "host"
            or source != "action"
            or origin is None
            or origin != parent_request_id
        ):
            raise PersistenceDefect("action event must name its original request")
    trace: dict[str, object] = {"observed_at": datetime.now(UTC).isoformat()}
    if action_id is not None:
        trace["action_id"] = str(action_id)
    if attachment_manifest:
        trace["attachment_manifest"] = list(attachment_manifest)
    row = (
        (
            await connection.execute(
                postgresql_insert(message)
                .values(
                    id=message_id or uuid4(),
                    role=role,
                    home=home,
                    text=text,
                    source=source,
                    source_conversation_id=source_conversation_id,
                    source_message_id=source_message_id,
                    created_at=created_at,
                    parent_request_id=parent_request_id,
                    request_state="pending",
                    memory_admitted=memory_is_admitted(connection),
                    trace=trace,
                )
                .on_conflict_do_nothing(constraint="uq_message_source_identity")
                .returning(*message.c)
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        return InboundInsert(_stored_message(row), inserted=True)
    row = (
        (
            await connection.execute(
                select(message).where(
                    message.c.source == source,
                    message.c.source_message_id == source_message_id,
                )
            )
        )
        .mappings()
        .one()
    )
    stored = _stored_message(row)
    if (
        stored.role,
        stored.text,
        stored.source_conversation_id,
        stored.created_at,
        stored.parent_request_id,
        stored.trace.get("action_id"),
    ) != (
        role,
        text,
        source_conversation_id,
        created_at,
        parent_request_id,
        str(action_id) if action_id is not None else None,
    ):
        raise PersistenceDefect(
            "source identity was reused for different message content"
        )
    return InboundInsert(stored, inserted=False)


def latest_control(scope: str):
    return (
        select(message.c.control_kind)
        .where(
            message.c.source_conversation_id == scope,
            message.c.control_kind.is_not(None),
        )
        .order_by(message.c.control_sequence.desc())
        .limit(1)
    )


async def causal_component_ids(
    connection: AsyncConnection, request_ids: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    """Recover complete causal components, including siblings of each input."""
    if not request_ids:
        return ()
    rows = await connection.execute(
        sql_text("""
        WITH RECURSIVE ancestors AS (
          SELECT id, parent_request_id FROM message WHERE id = ANY(:ids)
          UNION
          SELECT parent.id, parent.parent_request_id FROM message parent
          JOIN ancestors child ON child.parent_request_id = parent.id
        ), component AS (
          SELECT id FROM ancestors WHERE parent_request_id IS NULL
          UNION
          SELECT child.id FROM message child
          JOIN component parent ON child.parent_request_id = parent.id
        ) SELECT id FROM component ORDER BY id
        """),
        {"ids": list(request_ids)},
    )
    return tuple(rows.scalars())


async def cancel_unentered_actions(
    connection: AsyncConnection, request_ids: tuple[UUID, ...], timestamp: datetime
) -> None:
    """Cancel only commitments whose executor has never entered."""
    identifiers = tuple(
        (
            await connection.execute(
                select(action.c.id)
                .where(
                    action.c.origin_message_id.in_(request_ids),
                    action.c.attempts == 0,
                    action.c.status.in_(("queued", "executing")),
                )
                .order_by(action.c.id)
                .with_for_update()
            )
        ).scalars()
    )
    if identifiers:
        await connection.execute(
            update(action)
            .where(action.c.id.in_(identifiers))
            .values(
                status="cancelled",
                completed_at=timestamp,
                decided_at=func.coalesce(action.c.decided_at, timestamp),
                result={"type": "action_cancelled_v1", "reason_code": "owner_stopped"},
            )
        )


async def rearm_action_waiters(connection: AsyncConnection, action_id: UUID) -> None:
    await connection.execute(
        update(message)
        .where(
            message.c.request_state == "waiting",
            message.c.wait_reason == "external_reconciliation",
            message.c.processing_parked_at.is_(None),
            message.c.trace["waiting_action_ids"].contains([str(action_id)]),
        )
        .values(
            request_state="pending",
            wait_reason=None,
            trace=message.c.trace.op("-")("waiting_action_ids"),
        )
    )


class MessageStore:
    def __init__(
        self, engine: Database, *, workspace: WorkspaceHost | None = None
    ) -> None:
        self._engine = engine
        self._workspace = workspace

    async def initialize_paused(self, source_conversation_id: str) -> None:
        """Prepare one empty conversation's canonical pause without delivery."""
        _nonempty(source_conversation_id, "source conversation id")
        async with self._engine.begin() as connection:
            await lock_conversation(connection, source_conversation_id)
            existing = await connection.scalar(select(message.c.id).limit(1))
            if existing is not None:
                raise PersistenceDefect("conversation state is already initialized")
            timestamp, identifier = datetime.now(UTC), uuid4()
            sequence = await connection.scalar(control_sequence.next_value())
            await connection.execute(
                postgresql_insert(message).values(
                    id=identifier,
                    role="owner",
                    text="pause",
                    source="initialize_state",
                    source_conversation_id=source_conversation_id,
                    source_message_id=str(identifier),
                    created_at=timestamp,
                    processed_at=timestamp,
                    request_state="completed",
                    control_kind="pause",
                    control_sequence=sequence,
                    control_targets=[],
                )
            )

    async def submit(
        self,
        submission_id: UUID,
        text: str,
        ref: object,
        uploads: tuple[WebUpload, ...],
        *,
        scope: str,
        spool: Path,
        pages: Path = DEFAULT_EXPORT,
    ) -> InboundInsert:
        from jarvis.attachments import ingress_manifest, register_ingress

        try:
            digest = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "text": text,
                        "ref": ref,
                        "files": [
                            [item.filename, item.size, item.sha256] for item in uploads
                        ],
                    }
                )
            ).hexdigest()
        except (ValueError, RecursionError):
            digest = None
        async with self._engine.begin() as connection:
            await lock_conversation(connection, scope)
            existing = (
                (
                    await connection.execute(
                        select(message).where(
                            message.c.source == "web",
                            message.c.source_message_id == str(submission_id),
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                original_home: dict[str, object] = existing["home"] or {}
                if (
                    existing["source_conversation_id"] != scope
                    or existing["role"] != "owner"
                    or original_home.get("request_sha256") != digest
                ):
                    raise SubmissionConflict("submission id is already committed")
                return InboundInsert(_stored_message(existing), False)
            if digest is None:
                raise InvalidReference("invalid reference")
            home: dict[str, object] = {"request_sha256": digest, "ref": None}
            if ref is not None:
                from jarvis.home_reads import reference_context

                try:
                    validated = HOME_REF_ADAPTER.validate_python(ref)
                except ValueError as exc:
                    raise InvalidReference("invalid reference") from exc
                enrollment = (
                    None if self._workspace is None else self._workspace.enrollment()
                )
                context = await reference_context(
                    connection,
                    scope,
                    validated.model_dump(mode="json"),
                    pages,
                    drive_subject=None if enrollment is None else enrollment.subject,
                )
                if context is None:
                    raise InvalidReference("that reference is no longer available")
                home.update(context)
            result = await append_waking_input(
                connection,
                role="owner",
                source="web",
                text=text,
                source_conversation_id=scope,
                source_message_id=str(submission_id),
                created_at=datetime.now(UTC),
                attachment_manifest=ingress_manifest(uploads),
                home=home,
            )
            if uploads:
                await register_ingress(
                    connection,
                    result.message.id,
                    uploads,
                    spool=spool,
                )
            control = text.strip().lower()
            if ref is None and not uploads and control in {"pause", "resume"}:
                await self._apply_control(connection, result.message, control)
                updated = (
                    (
                        await connection.execute(
                            select(message).where(message.c.id == result.message.id)
                        )
                    )
                    .mappings()
                    .one()
                )
                return InboundInsert(_stored_message(updated), True)
            return result

    async def _apply_control(
        self, connection: AsyncConnection, command: StoredMessage, kind: str
    ) -> None:
        scope = command.source_conversation_id
        previous = (
            (
                await connection.execute(
                    latest_control(scope).add_columns(message.c.control_targets)
                )
            )
            .mappings()
            .one_or_none()
        )
        retained = (
            tuple(previous["control_targets"])
            if previous is not None and previous["control_kind"] == "pause"
            else ()
        )
        if kind == "resume":
            targets = retained
        else:
            current = tuple(
                (
                    await connection.execute(
                        select(message.c.id)
                        .where(
                            message.c.source_conversation_id == scope,
                            message.c.role.in_(("owner", "host")),
                            message.c.id != command.id,
                            message.c.control_kind.is_(None),
                            message.c.request_state.in_(("pending", "waiting")),
                        )
                        .order_by(message.c.id)
                        .with_for_update()
                    )
                ).scalars()
            )
            targets = tuple(sorted(set(retained) | set(current)))
        if targets:
            await connection.execute(
                select(message.c.id)
                .where(message.c.id.in_(targets))
                .order_by(message.c.id)
                .with_for_update()
            )
        attempts = tuple(
            (
                await connection.execute(
                    select(native_attempt.c.id)
                    .where(
                        native_attempt.c.conversation_id == scope,
                        active_native_attempt,
                    )
                    .order_by(native_attempt.c.id)
                    .with_for_update()
                )
            ).scalars()
        )
        if attempts:
            await connection.execute(
                select(native_invocation.c.id)
                .where(native_invocation.c.attempt_id.in_(attempts))
                .order_by(native_invocation.c.id)
                .with_for_update()
            )
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id.in_(attempts))
                .values(fenced_at=func.now())
            )
        # The acknowledgement must sort after its command, even on the same clock tick.
        timestamp = max(
            datetime.now(UTC), command.created_at + timedelta(microseconds=1)
        )
        if kind == "resume":
            if targets:
                await connection.execute(
                    update(message)
                    .where(
                        message.c.id.in_(targets),
                        message.c.request_state == "stopped",
                    )
                    .values(
                        request_state="pending",
                        wait_reason=None,
                        processed_at=None,
                        trace=message.c.trace.op("-")("waiting_action_ids"),
                    )
                )
            text = "resumed. entered actions retain their recorded outcome."
        else:
            if targets:
                await connection.execute(
                    update(message)
                    .where(message.c.id.in_(targets))
                    .values(
                        request_state="stopped",
                        native_retry_after=None,
                        wait_reason=None,
                        processed_at=timestamp,
                        trace=message.c.trace.op("-")("waiting_action_ids")
                        .op("-")("native_context_retry")
                        .op("-")("native_retry"),
                    )
                )
                await cancel_unentered_actions(connection, targets, timestamp)
            text = "paused."
        sequence = await connection.scalar(control_sequence.next_value())
        await connection.execute(
            update(message)
            .where(message.c.id == command.id)
            .values(
                control_kind=kind,
                control_sequence=sequence,
                control_targets=list(targets),
                request_state="completed",
                processed_at=timestamp,
            )
        )
        conclusion_id = uuid5(command.id, "control-conclusion")
        await connection.execute(
            postgresql_insert(message).values(
                id=conclusion_id,
                role="assistant",
                text=text,
                source="native_control",
                memory_admitted=memory_is_admitted(connection),
                source_conversation_id=scope,
                created_at=timestamp,
                processed_at=timestamp,
                trace={
                    "control_message_id": str(command.id),
                    "control_sequence": sequence,
                },
            )
        )

        await enqueue_notice(connection, conclusion_id)

    async def pending_inputs(
        self,
        *,
        source_conversation_id: str,
        limit: int,
        steer: bool = False,
        exclude_ids: tuple[UUID, ...] = (),
        exclude_retry_routes: tuple[str | None, ...] = (),
    ) -> tuple[StoredMessage, ...]:
        """Only opening batches may include due retries."""
        _positive(limit, "input limit")
        query = select(message).where(
            message.c.source_conversation_id == source_conversation_id,
            message.c.role.in_(("owner", "host")),
            message.c.request_state.in_(("pending", "waiting")),
            message.c.control_kind.is_(None),
            message.c.native_retry_after.is_(None)
            if steer
            else (
                message.c.native_retry_after.is_(None)
                | (message.c.native_retry_after <= func.now())
            ),
            message.c.native_retry_after.is_(None) | current_native_retry(),
            message.c.processing_parked_at.is_(None),
            message.c.id.not_in(exclude_ids),
            *(
                native_retry_pin.is_distinct_from(route)
                for route in exclude_retry_routes
            ),
        )
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        query.order_by(*pending_input_order).limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        if not rows or rows[0]["request_state"] != "pending":
            return ()
        return tuple(map(_stored_message, rows))

    async def next_native_retry_at(
        self, source_conversation_id: str
    ) -> datetime | None:
        async with self._engine.connect() as connection:
            return await connection.scalar(
                select(func.min(message.c.native_retry_after)).where(
                    message.c.source_conversation_id == source_conversation_id,
                    message.c.role.in_(("owner", "host")),
                    message.c.request_state == "pending",
                    message.c.control_kind.is_(None),
                    message.c.processing_parked_at.is_(None),
                    message.c.native_retry_after > func.now(),
                    current_native_retry(),
                )
            )

    async def waiting_input_count(
        self,
        source_conversation_id: str,
        *,
        exclude_ids: tuple[UUID, ...] = (),
        connection: AsyncConnection | None = None,
    ) -> int:
        async with (
            self._engine.connect()
            if connection is None
            else nullcontext(connection) as snapshot
        ):
            return int(
                await snapshot.scalar(
                    select(func.count())
                    .select_from(message)
                    .where(
                        message.c.source_conversation_id == source_conversation_id,
                        message.c.request_state == "waiting",
                        message.c.processing_parked_at.is_(None),
                        message.c.id.not_in(exclude_ids),
                    )
                )
                or 0
            )

    async def current_control(self, source_conversation_id: str) -> str | None:
        async with self._engine.connect() as connection:
            return await connection.scalar(latest_control(source_conversation_id))

    async def paused(self, source_conversation_id: str) -> bool:
        return await self.current_control(source_conversation_id) == "pause"

    async def message_by_id(self, message_id: UUID) -> StoredMessage | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(message).where(message.c.id == message_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _stored_message(row)

    async def list_parked(self, source_conversation_id: str) -> tuple[ParkedInput, ...]:
        """Read parked inputs and corroborate their attempt in one snapshot."""
        async with self._engine.begin() as connection:
            await connection.execute(
                sql_text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            return await parked_inputs(connection, source_conversation_id)

    async def clear_parked(
        self,
        *,
        source_conversation_id: str,
        message_ids: tuple[UUID, ...],
    ) -> None:
        if not message_ids or len(set(message_ids)) != len(message_ids):
            msg = "operator release IDs must be non-empty and unique"
            raise ValueError(msg)
        async with self._engine.begin() as connection:
            await lock_conversation(connection, source_conversation_id)
            rows = (
                await connection.execute(
                    select(
                        message.c.processing_parked_at,
                        _releasable_parked_input.label("releasable"),
                    )
                    .where(
                        message.c.source_conversation_id == source_conversation_id,
                        message.c.id.in_(message_ids),
                    )
                    .with_for_update()
                )
            ).all()
            if len(rows) != len(message_ids):
                msg = "operator release references a missing or out-of-scope message"
                raise PersistenceDefect(msg)
            if any(row.processing_parked_at is None for row in rows):
                msg = "operator release references an unparked message"
                raise PersistenceDefect(msg)
            if any(not row.releasable for row in rows):
                raise PersistenceDefect(
                    "operator repair requires live configuration-parked input"
                )
            release_cut = (
                select(func.coalesce(func.max(native_attempt.c.attempt_seq), 0))
                .where(native_attempt.c.conversation_id == source_conversation_id)
                .scalar_subquery()
            )
            await connection.execute(
                update(message)
                .where(message.c.id.in_(message_ids))
                .values(
                    processing_parked_at=None,
                    native_retry_after=None,
                    request_state="pending",
                    wait_reason=None,
                    processed_at=None,
                    trace=message.c.trace.op("-")("waiting_action_ids")
                    .op("-")("native_context_retry")
                    .op("-")("native_retry")
                    .op("||")(
                        func.jsonb_build_object(
                            "released_through_native_attempt", release_cut
                        )
                    ),
                )
            )


async def parked_inputs(
    connection: AsyncConnection,
    source_conversation_id: str,
    ids: tuple[UUID, ...] | None = None,
) -> tuple[ParkedInput, ...]:
    """Corroborate current parks inside the caller's snapshot or custody."""
    notice = message.alias("park_notice")
    attempt_ref = message.c.trace["native_attempt_id"].as_string()
    has_delivery = (
        select(native_input_delivery.c.message_id)
        .where(
            native_input_delivery.c.attempt_id == native_attempt.c.id,
            native_input_delivery.c.message_id == message.c.id,
        )
        .exists()
    )
    has_notice = (
        select(notice.c.id)
        .where(
            notice.c.source_conversation_id == message.c.source_conversation_id,
            notice.c.role == "assistant",
            notice.c.source == "native_failure",
            notice.c.processed_at == message.c.processing_parked_at,
            notice.c.trace["native_attempt_id"].as_string() == attempt_ref,
        )
        .exists()
    )
    rows = (
        (
            await connection.execute(
                select(
                    message.c.id,
                    message.c.role,
                    message.c.source,
                    message.c.trace,
                    message.c.processing_parked_at,
                    native_attempt.c.id.label("attempt_id"),
                    native_attempt.c.attempt_seq,
                    _releasable_parked_input.label("releasable"),
                )
                .select_from(message)
                .outerjoin(
                    native_attempt,
                    (native_attempt.c.conversation_id == source_conversation_id)
                    & (sql_cast(native_attempt.c.id, Text) == attempt_ref)
                    & has_delivery
                    & has_notice,
                )
                .where(
                    message.c.source_conversation_id == source_conversation_id,
                    _parked_input,
                    *(() if ids is None else (message.c.id.in_(ids),)),
                )
                .order_by(message.c.processing_parked_at, message.c.id)
            )
        )
        .mappings()
        .all()
    )
    inputs: list[ParkedInput] = []
    for row in rows:
        watermark = row["trace"].get("released_through_native_attempt", 0)
        sequence = row["attempt_seq"]
        reason = row["trace"].get("failure_code")
        claim = row["trace"].get("native_attempt_id")
        claimed_attempt_id = None
        if isinstance(claim, str):
            with suppress(ValueError):
                claimed_attempt_id = UUID(claim)
        inputs.append(
            ParkedInput(
                id=row["id"],
                role=row["role"],
                source=row["source"],
                reason=reason if isinstance(reason, str) else None,
                parked_at=row["processing_parked_at"],
                attempt_id=row["attempt_id"]
                if sequence is not None
                and type(watermark) is int
                and 0 <= watermark < sequence
                else None,
                claimed_attempt_id=claimed_attempt_id,
                releasable=bool(row["releasable"]),
            )
        )
    return tuple(inputs)


def _stored_message(row: RowMapping) -> StoredMessage:
    return StoredMessage(
        id=cast(UUID, row["id"]),
        role=cast(MessageRole, row["role"]),
        text=cast(str, row["text"]),
        source=cast(str, row["source"]),
        source_conversation_id=cast(str, row["source_conversation_id"]),
        source_message_id=cast(str | None, row["source_message_id"]),
        created_at=cast(datetime, row["created_at"]),
        parent_request_id=cast(UUID | None, row["parent_request_id"]),
        processed_at=cast(datetime | None, row["processed_at"]),
        processing_attempts=cast(int, row["processing_attempts"]),
        processing_parked_at=cast(datetime | None, row["processing_parked_at"]),
        memory_admitted=cast(bool, row["memory_admitted"]),
        trace=cast(dict[str, object], row["trace"]),
        request_state=row["request_state"],
        wait_reason=row["wait_reason"],
        control_kind=row["control_kind"],
        home=row["home"],
        native_retry_after=row["native_retry_after"],
    )


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{name} must be timezone-aware"
        raise ValueError(msg)


def _nonempty(value: str, name: str) -> str:
    if not value:
        msg = f"{name} must not be empty"
        raise ValueError(msg)
    return value


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        msg = f"{name} must be a positive integer"
        raise ValueError(msg)
    return value

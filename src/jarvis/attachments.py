"""Custody of submitted bytes until Drive filing is verified or abandoned."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from llm_tools import ToolResult, canonical_json_bytes
from sqlalchemy import RowMapping, Select, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis._thread_io import finish_entered, joined_thread
from jarvis.actions import (
    action_replay_result,
    complete_local_action,
    require_locked_action,
)
from jarvis.db import (
    action,
    attachment,
    message,
    native_attempt,
    native_invocation,
    read_position,
)
from jarvis.ownership import Database
from jarvis.read_tools import ATTACHMENT_MAX_BYTES, ReadResponse, display_descriptor
from jarvis.workspace_checks import workspace_read_receipts
from jarvis.workspace_mcp import WorkspaceError
from jarvis.workspace_reads import observed_workspace_file

SPOOL_MAX_BYTES = 1024 * 1024 * 1024
SCRATCH_MAX_BYTES = 1024 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
_PENDING_STATES = ("staged", "filing", "uncertain", "created")


class SpoolFull(ValueError):
    """Submitted originals exceed the available private staging space."""


class CustodyConflict(ValueError):
    """The submission cannot make the requested filing transition."""


@dataclass(frozen=True, slots=True)
class WebUpload:
    submission_id: UUID
    slot: int
    filename: str
    size: int
    sha256: str
    media_type: str
    body: BinaryIO = field(repr=False, compare=False)

    @property
    def id(self) -> UUID:
        return uuid5(
            NAMESPACE_URL, f"jarvis:web-attachment:{self.submission_id}:{self.slot}"
        )

    @property
    def source(self) -> dict[str, object]:
        return {
            "kind": "web",
            "submission_id": str(self.submission_id),
            "slot": self.slot,
        }


@dataclass(frozen=True, slots=True)
class AttachmentRecord:
    id: UUID
    filename: str | None
    media_type: str | None
    size_bytes: int | None
    sha256: str | None
    created_at: datetime
    state: str
    filing_action_id: UUID | None
    drive_subject: str | None
    drive_file_id: str | None
    disposition: str | None


def _record(row: RowMapping) -> AttachmentRecord:
    return AttachmentRecord(
        id=row["id"],
        filename=row["filename"],
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        created_at=row["created_at"],
        state=row["state"],
        filing_action_id=row["filing_action_id"],
        drive_subject=row["drive_subject"],
        drive_file_id=row["drive_file_id"],
        disposition=row["disposition"],
    )


def upload_spool_name(identifier: UUID, sha256: str) -> str:
    return f"{identifier}.{sha256}"


def ingress_manifest(
    uploads: tuple[WebUpload, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "id": str(upload.id),
            **display_descriptor(upload.filename, upload.media_type, upload.size),
        }
        for upload in uploads
    )


def copy_verified(
    source: BinaryIO, write: Callable[[bytes], int] | None, size: int, sha256: str
) -> None:
    if not 0 <= size <= ATTACHMENT_MAX_BYTES:
        raise OSError("file exceeds the byte bound")
    digest = hashlib.sha256()
    remaining = size
    while chunk := source.read(min(_CHUNK_BYTES, remaining + 1)):
        remaining -= len(chunk)
        if remaining < 0:
            raise OSError("file size changed")
        digest.update(chunk)
        if write is not None:
            write(chunk)
    if remaining or digest.hexdigest() != sha256:
        raise OSError("file bytes changed")
    source.seek(0)


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _persist_uploads(spool: Path, uploads: tuple[WebUpload, ...]) -> None:
    spool.mkdir(mode=0o700, exist_ok=True)
    _sync_directory(spool.parent)
    for upload in uploads:
        with tempfile.NamedTemporaryFile(
            dir=spool, prefix=".incoming-", delete=False
        ) as output:
            temporary = Path(output.name)
            try:
                copy_verified(upload.body, output.write, upload.size, upload.sha256)
                output.flush()
                os.fsync(output.fileno())
                os.replace(
                    temporary, spool / upload_spool_name(upload.id, upload.sha256)
                )
            finally:
                temporary.unlink(missing_ok=True)
    _sync_directory(spool)


async def register_ingress(
    connection: AsyncConnection,
    origin_message_id: UUID,
    uploads: tuple[WebUpload, ...],
    *,
    spool: Path,
) -> None:
    """Caller holds the owner conversation lock and has ruled out equal replay."""
    occupied = await connection.scalar(
        select(func.coalesce(func.sum(attachment.c.size_bytes), 0)).where(
            attachment.c.state.in_(_PENDING_STATES)
        )
    )
    if int(occupied or 0) + sum(upload.size for upload in uploads) > SPOOL_MAX_BYTES:
        raise SpoolFull("uploads waiting on jarvis exceed 1 gib")
    await joined_thread(_persist_uploads, spool, uploads)
    await connection.execute(
        insert(attachment),
        [
            {
                "id": upload.id,
                "source": upload.source,
                "source_key": hashlib.sha256(
                    canonical_json_bytes(upload.source)
                ).hexdigest(),
                "origin_message_id": origin_message_id,
                "filename": upload.filename,
                "media_type": upload.media_type,
                "advertised_size": upload.size,
                "size_bytes": upload.size,
                "sha256": upload.sha256,
                "state": "staged",
                "created_at": datetime.now(UTC),
            }
            for upload in uploads
        ],
    )


class AttachmentStore:
    def __init__(
        self,
        database: Database,
        conversation_id: str,
        *,
        spool_directory: Path,
        scratch_directory: Path,
    ) -> None:
        self._database = database
        self._scope = conversation_id
        self._spool = spool_directory
        self._scratch = scratch_directory
        self._scratch_lock = asyncio.Lock()
        self._scratch_reserved = 0

    def _owned_rows(self) -> Select[tuple[object, ...]]:
        return (
            select(attachment)
            .join(message, message.c.id == attachment.c.origin_message_id)
            .where(message.c.source_conversation_id == self._scope)
        )

    async def _row(
        self, connection: AsyncConnection, identifier: UUID, *, lock: bool = False
    ) -> RowMapping | None:
        query = self._owned_rows().where(attachment.c.id == identifier)
        if lock:
            query = query.with_for_update(of=attachment)
        return (await connection.execute(query)).mappings().one_or_none()

    async def inspect(self, identifier: UUID) -> AttachmentRecord | None:
        async with self._database.connect() as connection:
            row = await self._row(connection, identifier)
        return None if row is None else _record(row)

    async def pending(self) -> tuple[AttachmentRecord, ...]:
        async with self._database.connect() as connection:
            rows = await connection.execute(
                self._owned_rows()
                .where(attachment.c.state.in_(_PENDING_STATES))
                .order_by(attachment.c.created_at, attachment.c.id)
            )
            return tuple(_record(row) for row in rows.mappings())

    async def open_pending(self, identifier: UUID) -> tuple[AttachmentRecord, BinaryIO]:
        """Return the verified open fd while serialized with custody transitions."""
        stream: BinaryIO | None = None
        try:
            async with self._database.connect() as connection:
                row = await self._row(connection, identifier, lock=True)
                if row is None:
                    raise CustodyConflict("NotFound")
                record = _record(row)
                if record.state not in _PENDING_STATES:
                    raise CustodyConflict(
                        "Filed" if record.state == "filed" else "Unavailable"
                    )
                size, digest = record.size_bytes, record.sha256
                if size is None or digest is None:
                    raise CustodyConflict("Unavailable")

                def open_verified() -> BinaryIO:
                    stream = (self._spool / upload_spool_name(identifier, digest)).open(
                        "rb"
                    )
                    try:
                        copy_verified(stream, None, size, digest)
                        return stream
                    except BaseException:
                        stream.close()
                        raise

                entered = asyncio.create_task(asyncio.to_thread(open_verified))
                try:
                    stream = await asyncio.shield(entered)
                except asyncio.CancelledError as cancellation:
                    try:
                        late = await finish_entered(entered)
                        late.close()
                    finally:
                        raise cancellation
        except BaseException:
            if stream is not None:
                stream.close()
            raise
        assert stream is not None
        return record, stream

    def _scratch_available(self, size: int) -> bool:
        named = sum(
            path.stat().st_size for path in self._scratch.iterdir() if path.is_file()
        )
        return named + self._scratch_reserved + size <= SCRATCH_MAX_BYTES

    @asynccontextmanager
    async def transfer_scratch(self, reserved: int) -> AsyncIterator[Path]:
        """Reserve the upper bound for private transport bytes until they close."""
        if reserved < 0:
            raise ValueError("scratch reservation must be nonnegative")
        async with self._scratch_lock:
            if not self._scratch_available(reserved):
                raise WorkspaceError("scratch_full", known_no_effect=True)
            self._scratch_reserved += reserved
        try:
            yield self._scratch
        finally:
            # Same event loop as allocation, with no cancellable release step.
            self._scratch_reserved -= reserved

    async def materialize(self, source: BinaryIO, size: int, digest: str) -> Path:
        """Publish one verified read-only file in the native attempt scratch."""
        async with self._scratch_lock:
            if not self._scratch_available(size):
                raise CustodyConflict("ScratchFull")
            return await joined_thread(self._materialize, source, size, digest)

    def _materialize(self, source: BinaryIO, size: int, digest: str) -> Path:
        with tempfile.NamedTemporaryFile(dir=self._scratch, delete=False) as output:
            path = Path(output.name)
            try:
                copy_verified(source, output.write, size, digest)
                os.fchown(output.fileno(), -1, self._scratch.stat().st_gid)
                os.fchmod(output.fileno(), 0o640)
            except BaseException:
                path.unlink()
                raise
        return path

    async def open(self, identifier: UUID) -> ReadResponse[ToolResult]:
        try:
            row, stream = await self.open_pending(identifier)
            assert row.sha256 is not None and row.size_bytes is not None
            with stream:
                path = await self.materialize(stream, row.size_bytes, row.sha256)
        except OSError:
            return ReadResponse(_failure("Unavailable", identifier), 0)
        except CustodyConflict as exc:
            if str(exc) == "Filed" and (file := await self.inspect(identifier)):
                return ReadResponse(
                    _failure(
                        "Filed",
                        identifier,
                        subject=file.drive_subject,
                        file_id=file.drive_file_id,
                    ),
                    0,
                )
            return ReadResponse(_failure(str(exc), identifier), 0)
        return ReadResponse(
            {
                "type": "Success",
                "value": {
                    "id": str(row.id),
                    "name": display_descriptor(
                        row.filename, row.media_type, row.size_bytes
                    )["name"],
                    "media_type": row.media_type,
                    "size_bytes": row.size_bytes,
                    "sha256": row.sha256,
                    "local_path": str(path),
                },
            },
            0,
        )

    async def reset_scratch(self) -> None:
        """No native attempt may own these disposable paths when clearing them."""

        def reset() -> None:
            for path in self._scratch.iterdir():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

        async with self._scratch_lock:
            if self._scratch_reserved:
                raise CustodyConflict("ScratchInUse")
            await joined_thread(reset)

    async def clean_spool(self) -> None:
        """Reclaim failed ingress and settled bytes before web ingress opens."""
        self._spool.mkdir(mode=0o700, exist_ok=True)
        retained = {
            upload_spool_name(row.id, row.sha256)
            for row in await self.pending()
            if row.sha256 is not None
        }
        for path in self._spool.iterdir():
            if path.name not in retained:
                path.unlink()

    async def bind(
        self, connection: AsyncConnection, identifier: UUID, action_id: UUID
    ) -> None:
        row = await self._row(connection, identifier, lock=True)
        if row is None or row["state"] not in {"staged", "filing"}:
            raise CustodyConflict("SubmissionNotStageable")
        if row["state"] == "filing":
            if row["filing_action_id"] == action_id:
                return
            raise CustodyConflict("SubmissionHasFiling")
        await connection.execute(
            update(attachment)
            .where(attachment.c.id == identifier)
            .values(state="filing", filing_action_id=action_id)
        )

    async def _filing(
        self, connection: AsyncConnection, identifier: UUID, action_id: UUID
    ) -> RowMapping:
        row = await self._row(connection, identifier, lock=True)
        if row is None or row["filing_action_id"] != action_id:
            raise CustodyConflict("FilingChanged")
        return row

    async def acknowledge(
        self, identifier: UUID, action_id: UUID, subject: str, file_id: str
    ) -> None:
        async with self._database.begin() as connection:
            row = await self._filing(connection, identifier, action_id)
            if row["drive_file_id"] is not None:
                if row["drive_subject"] != subject or row["drive_file_id"] != file_id:
                    raise CustodyConflict("DriveIdentityChanged")
                return
            if row["state"] != "filing":
                raise CustodyConflict("FilingChanged")
            await connection.execute(
                update(attachment)
                .where(attachment.c.id == identifier)
                .values(state="created", drive_subject=subject, drive_file_id=file_id)
            )

    async def verify(self, identifier: UUID, action_id: UUID) -> None:
        async with self._database.begin() as connection:
            row = await self._filing(connection, identifier, action_id)
            if row["state"] not in {"created", "filed"}:
                raise CustodyConflict("FilingChanged")
            if row["state"] == "created":
                await connection.execute(
                    update(attachment)
                    .where(attachment.c.id == identifier)
                    .values(state="filed", verified_at=datetime.now(UTC))
                )
        self._drop_original(identifier, row["sha256"])

    async def mark_uncertain(
        self,
        identifier: UUID,
        action_id: UUID,
        *,
        connection: AsyncConnection | None = None,
    ) -> None:
        async with (
            self._database.begin() if connection is None else nullcontext(connection)
        ) as active:
            row = await self._filing(active, identifier, action_id)
            if row["state"] == "filing":
                await active.execute(
                    update(attachment)
                    .where(attachment.c.id == identifier)
                    .values(state="uncertain")
                )

    async def release_unentered(
        self, connection: AsyncConnection, identifier: UUID, action_id: UUID
    ) -> None:
        row = await self._filing(connection, identifier, action_id)
        if row["state"] != "filing":
            raise CustodyConflict("FilingChanged")
        await connection.execute(
            update(attachment)
            .where(attachment.c.id == identifier)
            .values(state="staged", filing_action_id=None)
        )

    async def abandon(
        self, action_id: UUID, identifier: UUID
    ) -> ReadResponse[ToolResult]:
        async with self._database.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            if stored.tool_name != "submission.abandon" or stored.payload.get(
                "id"
            ) != str(identifier):
                raise CustodyConflict("AbandonmentChanged")
            if (replay := action_replay_result(stored)) is not None:
                return ReadResponse(replay, 0)
            row = await self._row(connection, identifier, lock=True)
            filing_status = None
            if row is not None and row["filing_action_id"] is not None:
                filing_status = await connection.scalar(
                    select(action.c.status).where(
                        action.c.id == row["filing_action_id"]
                    )
                )
            if row is None:
                result = _failure("NotFound", identifier)
            elif row["state"] not in _PENDING_STATES:
                result = _failure(
                    "Filed" if row["state"] == "filed" else "Unavailable",
                    identifier,
                    subject=row["drive_subject"] if row["state"] == "filed" else None,
                    file_id=row["drive_file_id"] if row["state"] == "filed" else None,
                )
            elif row["filing_action_id"] is not None and filing_status not in {
                "succeeded",
                "failed",
                "uncertain",
                "cancelled",
            }:
                result = _failure("FilingInProgress", identifier)
            else:
                unknown = row["state"] == "uncertain" or (
                    filing_status == "uncertain" and row["drive_file_id"] is None
                )
                await connection.execute(
                    update(attachment)
                    .where(attachment.c.id == identifier)
                    .values(
                        state="unavailable",
                        disposition="abandoned_uncertain" if unknown else "abandoned",
                    )
                )
                result: ToolResult = {
                    "type": "Success",
                    "value": {
                        "id": str(identifier),
                        "drive_effect_unknown": unknown,
                        "drive_file_id": row["drive_file_id"],
                        "drive_subject": row["drive_subject"],
                    },
                }
            await complete_local_action(
                connection, stored, result=result, completed_at=datetime.now(UTC)
            )
        if result["type"] == "Success" and row is not None:
            self._drop_original(identifier, row["sha256"])
        return ReadResponse(result, 0)

    def _drop_original(self, identifier: UUID, digest: str) -> None:
        path = self._spool / upload_spool_name(identifier, digest)
        try:
            path.unlink(missing_ok=True)
            _sync_directory(self._spool)
        except OSError:
            logging.getLogger(__name__).warning(
                "settled submission %s awaits spool cleanup", identifier
            )

    async def workspace_source_observed(
        self, source: Mapping[str, object], *, account: str, grant_id: UUID
    ) -> bool:
        """Require the exact descriptor from a completed owner-scope Gmail read."""
        message_id, part_id = str(source["message_id"]), str(source["part_id"])
        async with self._database.connect() as connection:
            rows = await connection.execute(
                workspace_read_receipts(str(grant_id))
                .join(
                    native_attempt,
                    native_invocation.c.attempt_id == native_attempt.c.id,
                )
                .where(
                    native_attempt.c.conversation_id == self._scope,
                    native_invocation.c.tool_id.in_(
                        ("gmail.get_message", "gmail.get_draft")
                    ),
                    read_position.c.result["value"]["mail"]["account"].as_string()
                    == account,
                    read_position.c.result["value"]["mail"]["message_id"].as_string()
                    == message_id,
                )
            )
            return any(
                observed_workspace_file(
                    row.tool_id,
                    row.arguments,
                    row.value,
                    account=account,
                    message_id=message_id,
                    part_id=part_id,
                )
                for row in rows
            )


def _failure(
    code: str,
    identifier: UUID,
    *,
    subject: str | None = None,
    file_id: str | None = None,
) -> ToolResult:
    error = {"type": code, "id": str(identifier)}
    if code == "Filed":
        assert subject is not None and file_id is not None
        error.update(drive_subject=subject, drive_file_id=file_id)
    return cast(ToolResult, {"type": "Failure", "error": error})

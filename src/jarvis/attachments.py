"""Private original bytes, immutable attribution, and factual effect recovery."""

from __future__ import annotations

import asyncio
import base64
import grp
import hashlib
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from botocore.exceptions import (  # pyright: ignore[reportMissingTypeStubs]
    BotoCoreError,
    ClientError,
)
from llm_tools import RecoveryRequired, ToolId, ToolResult, canonical_json_bytes
from sqlalchemy import RowMapping, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis._thread_io import joined_thread
from jarvis.actions import (
    ActionPersistenceDefect,
    ActionStore,
    StoredAction,
    action_replay_result,
    attachment_manual_cleanup_reported,
    complete_local_action,
    require_locked_action,
    resolve_reconciliation_in_transaction,
)
from jarvis.attachment_sources import AttachmentSources
from jarvis.attachment_tools import ATTACHMENT_EXTERNAL_ATTEMPTS, AttachmentDeleteResult
from jarvis.db import action, attachment, message
from jarvis.messages import append_waking_input
from jarvis.ownership import Database, lock_conversation
from jarvis.read_tools import (
    ATTACHMENT_MAX_BYTES,
    ATTACHMENT_OPERATION_SECONDS,
    ConnectorFailure,
    ReadResponse,
    display_descriptor,
)

HEAD_BACKOFF_SECONDS = (0.0, 2.0, 8.0)
HEAD_DEADLINE_SECONDS = 10.0


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> Mapping[str, object]: ...
    def head_object(self, **kwargs: object) -> Mapping[str, object]: ...
    def get_object(self, **kwargs: object) -> Mapping[str, object]: ...
    def delete_object(self, **kwargs: object) -> Mapping[str, object]: ...


class _StreamingBody(Protocol):
    def read(self, amount: int) -> bytes: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class WebUpload:
    submission_id: UUID
    slot: int
    filename: str
    size: int
    sha256: str
    media_type: str

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


async def register_ingress(
    connection: AsyncConnection,
    origin_message_id: UUID,
    uploads: tuple[WebUpload, ...],
    *,
    r2_account: str,
    bucket: str,
) -> None:
    if not r2_account or not bucket:
        raise ValueError("attachment storage location is missing")
    for upload in uploads:
        await connection.execute(
            insert(attachment).values(
                id=upload.id,
                source=upload.source,
                source_key=hashlib.sha256(
                    canonical_json_bytes(upload.source)
                ).hexdigest(),
                r2_account=r2_account,
                bucket=bucket,
                origin_message_id=origin_message_id,
                filename=upload.filename,
                media_type=upload.media_type,
                advertised_size=upload.size,
                size_bytes=upload.size,
                sha256=upload.sha256,
                state="pending",
                created_at=datetime.now(UTC),
            )
        )


async def _locked_attachment(
    connection: AsyncConnection, identifier: UUID
) -> RowMapping:
    row = (
        (
            await connection.execute(
                select(attachment)
                .where(attachment.c.id == identifier)
                .with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ActionPersistenceDefect("registered original disappeared")
    return row


def _failure(code: str, identifier: UUID | None = None) -> ToolResult:
    return cast(
        ToolResult,
        {
            "type": "Failure",
            "error": {
                "type": code,
                "id": None if identifier is None else str(identifier),
            },
        },
    )


def _snapshot(row: RowMapping) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        **{
            key: value
            for key, value in display_descriptor(
                row["filename"], row["media_type"], row["advertised_size"]
            ).items()
            if key != "advertised_size"
        },
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
    }


def _deleted(row: RowMapping) -> ToolResult:
    value = AttachmentDeleteResult(
        id=str(row["id"]), deleted_at=row["deleted_at"], scope="original_and_cache"
    ).model_dump(mode="json")
    return {"type": "Success", "value": value}


def _source_error(exc: ConnectorFailure) -> str:
    return {
        "not_found": "NotFound",
        "message_not_found": "NotFound",
        "too_large": "TooLarge",
        "provider_response_too_large": "ProviderResponseTooLarge",
        "source_changed": "SourceChanged",
    }.get(exc.code, "Unavailable")


def _definite_rejection(error: ClientError) -> bool:
    response = cast(dict[str, object], error.response)
    metadata = cast(dict[str, object], response.get("ResponseMetadata", {}))
    details = cast(dict[str, object], response.get("Error", {}))
    return metadata.get("HTTPStatusCode") in {
        400,
        401,
        403,
        404,
        405,
        413,
        422,
        429,
    } and details.get("Code") not in {"RequestTimeout", "InternalError"}


def _byte_facts(path: Path, deadline: float | None = None) -> tuple[int, str, str]:
    size = 0
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("original byte inspection deadline exceeded")
            chunk = stream.read(1_024 * 1_024)
            if not chunk:
                break
            size += len(chunk)
            if size > ATTACHMENT_MAX_BYTES:
                raise ValueError("original exceeds byte bound")
            sha.update(chunk)
            md5.update(chunk)
    return size, sha.hexdigest(), base64.b64encode(md5.digest()).decode("ascii")


class AttachmentStore:
    def __init__(
        self,
        database: Database,
        conversation_id: str,
        *,
        r2_account: str,
        bucket: str,
        cache_directory: Path,
        spool_directory: Path,
        s3_client: S3Client,
        sources: AttachmentSources,
        mutation_admitted: Callable[[], Awaitable[None]],
    ) -> None:
        if (
            not r2_account
            or not bucket
            or not cache_directory.is_absolute()
            or not spool_directory.is_absolute()
        ):
            raise ValueError("attachment storage configuration is invalid")
        self._database = database
        self._actions = ActionStore(database)
        self._conversation_id = conversation_id
        self._account = r2_account
        self._bucket = bucket
        self._spool = spool_directory
        self._cache = cache_directory
        self._s3 = s3_client
        self._sources = sources
        self._mutation_admitted = mutation_admitted
        self._captures_stopped = False

    def stop_captures(self) -> None:
        self._captures_stopped = True

    async def reset_cache(self) -> None:
        await joined_thread(self._reset_cache)

    def _reset_cache(self) -> None:
        self._cache.mkdir(mode=0o750, parents=True, exist_ok=True)
        for child in self._cache.iterdir():
            if child.name != ".staging":
                try:
                    if str(UUID(child.name)) != child.name:
                        continue
                except ValueError:
                    continue
            if child.stat().st_uid == os.getuid() and child.is_dir():
                shutil.rmtree(child)
        staging = self._cache / ".staging"
        staging.mkdir(mode=0o700)
        os.chmod(staging, 0o700)

    def _stage(self) -> Path:
        staging = self._cache / ".staging"
        staging.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(staging, 0o700)
        fd, name = tempfile.mkstemp(dir=staging)
        os.close(fd)
        return Path(name)

    async def _row(self, identifier: UUID) -> RowMapping | None:
        async with self._database.begin() as connection:
            return (
                (
                    await connection.execute(
                        select(attachment).where(attachment.c.id == identifier)
                    )
                )
                .mappings()
                .one_or_none()
            )

    def _check_location(self, row: RowMapping) -> None:
        if row["r2_account"] != self._account or row["bucket"] != self._bucket:
            raise ValueError(
                "configured storage does not match immutable original location"
            )

    async def retain(
        self, action_id: UUID, source: dict[str, object]
    ) -> ReadResponse[ToolResult]:
        async with self._database.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            replay = action_replay_result(stored)
            if replay is not None:
                return ReadResponse(replay, 0)
            owned = (
                (
                    await connection.execute(
                        select(attachment).where(
                            attachment.c.capture_action_id == action_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if owned is not None:
            return await self._capture(owned["id"], action_id)
        source_deadline = time.monotonic() + ATTACHMENT_OPERATION_SECONDS
        try:
            resolved = await self._sources.resolve(source)
        except ConnectorFailure as exc:
            result = _failure(_source_error(exc))
            await self._complete(action_id, result)
            return ReadResponse(result, exc.attempts)
        original = resolved.value
        source_key = hashlib.sha256(canonical_json_bytes(original.source)).hexdigest()
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            stored = await require_locked_action(connection, action_id)
            existing = (
                (
                    await connection.execute(
                        select(attachment)
                        .where(
                            attachment.c.source_key == source_key,
                            attachment.c.state.in_(("pending", "ready", "deleting")),
                        )
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                self._check_location(existing)
                result = (
                    {"type": "Success", "value": _snapshot(existing)}
                    if existing["state"] == "ready"
                    else _failure(
                        "Deleting"
                        if existing["state"] == "deleting"
                        else existing["error"] or "Pending",
                        existing["id"],
                    )
                )
                await complete_local_action(
                    connection, stored, cast(ToolResult, result), datetime.now(UTC)
                )
                return ReadResponse(cast(ToolResult, result), resolved.attempts)
            await connection.execute(
                insert(attachment).values(
                    id=action_id,
                    source=original.source,
                    source_key=source_key,
                    r2_account=self._account,
                    bucket=self._bucket,
                    origin_message_id=stored.origin_message_id,
                    capture_action_id=action_id,
                    filename=original.filename,
                    media_type=original.media_type,
                    advertised_size=original.advertised_size,
                    state="pending",
                    created_at=datetime.now(UTC),
                )
            )
        return await self._capture(
            action_id,
            action_id,
            attempts=resolved.attempts,
            source_deadline=source_deadline,
        )

    async def clean_spool(self) -> None:
        """Remove disposable staging while web ingress and capture are stopped."""
        self._spool.mkdir(mode=0o700, exist_ok=True)
        async with self._database.begin() as connection:
            rows = await connection.execute(
                select(attachment.c.id, attachment.c.sha256).where(
                    attachment.c.source["kind"].as_string() == "web",
                    attachment.c.state.not_in(("ready", "deleted")),
                )
            )
            retain = {
                upload_spool_name(identifier, digest) for identifier, digest in rows
            }
        for path in self._spool.iterdir():
            if path.name not in retain:
                path.unlink()

    async def capture_pending(self) -> bool:
        async with self._database.begin() as connection:
            identifiers = (
                await connection.scalars(
                    select(attachment.c.id)
                    .where(
                        attachment.c.capture_action_id.is_(None),
                        attachment.c.state == "pending",
                        attachment.c.error.is_(None),
                    )
                    .order_by(attachment.c.created_at, attachment.c.id)
                )
            ).all()
        for identifier in identifiers:
            if self._captures_stopped:
                break
            await self._capture(identifier, None)
        return bool(identifiers)

    async def _capture(
        self,
        identifier: UUID,
        action_id: UUID | None,
        *,
        attempts: int = 0,
        source_deadline: float | None = None,
    ) -> ReadResponse[ToolResult]:
        row = await self._row(identifier)
        if row is None:
            raise ActionPersistenceDefect("registered original disappeared")
        self._check_location(row)
        if row["state"] != "pending":
            return ReadResponse(
                {"type": "Success", "value": _snapshot(row)}
                if row["state"] == "ready"
                else _failure(self._unreadable(row), identifier),
                attempts,
            )
        if row["put_entered_at"] is not None:
            result, observed = await self._reconcile_put(row)
            return ReadResponse(result, attempts + observed)
        if (
            row["advertised_size"] is not None
            and row["advertised_size"] > ATTACHMENT_MAX_BYTES
        ):
            result = await self._capture_failed(identifier, action_id, "TooLarge")
            return ReadResponse(result, attempts)
        web = row["source"]["kind"] == "web"
        staging = (
            self._spool / upload_spool_name(identifier, row["sha256"])
            if web
            else self._stage()
        )
        try:
            try:
                deadline = (
                    source_deadline
                    if source_deadline is not None
                    else time.monotonic() + ATTACHMENT_OPERATION_SECONDS
                )
                if time.monotonic() >= deadline:
                    raise TimeoutError("source preparation deadline exceeded")
                async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                    if not web:
                        attempts += await self._sources.download(
                            cast(dict[str, object], row["source"]), staging
                        )
                    size, digest, md5 = await joined_thread(
                        _byte_facts, staging, deadline
                    )
            except ConnectorFailure as exc:
                result = await self._capture_failed(
                    identifier, action_id, _source_error(exc)
                )
                return ReadResponse(result, attempts + exc.attempts)
            except (OSError, ValueError, TimeoutError) as exc:
                if web and isinstance(exc, OSError):
                    return ReadResponse(_failure("Pending", identifier), attempts)
                result = await self._capture_failed(
                    identifier, action_id, "SourceChanged" if web else "Unavailable"
                )
                return ReadResponse(result, attempts)
            if action_id is None and self._captures_stopped:
                return ReadResponse(_failure("Pending", identifier), attempts)
            async with self._database.begin() as connection:
                current = await _locked_attachment(connection, identifier)
                if (
                    current["state"] != "pending"
                    or current["put_entered_at"] is not None
                ):
                    raise ActionPersistenceDefect("original capture entry changed")
                if current["sha256"] is not None and (
                    current["sha256"] != digest or current["size_bytes"] != size
                ):
                    changed = True
                else:
                    changed = False
                    await connection.execute(
                        update(attachment)
                        .where(attachment.c.id == identifier)
                        .values(size_bytes=size, sha256=digest)
                    )
            if changed:
                result = await self._capture_failed(
                    identifier, action_id, "SourceChanged"
                )
                return ReadResponse(result, attempts)
            await self._mutation_admitted()
            if action_id is None and self._captures_stopped:
                return ReadResponse(_failure("Pending", identifier), attempts)
            if action_id is not None:
                stored = await self._actions.get(action_id)
                if stored is None:
                    raise ActionPersistenceDefect("capture action disappeared")
                if (
                    stored.recovered_external_attempts + attempts + 1
                    > ATTACHMENT_EXTERNAL_ATTEMPTS
                ):
                    result = await self._capture_failed(
                        identifier, action_id, "Unavailable"
                    )
                    return ReadResponse(result, attempts)
                await self._actions.stage_external_attempts(
                    action_id=action_id,
                    actual_external_attempts=stored.recovered_external_attempts
                    + attempts
                    + 1,
                )
            async with self._database.begin() as connection:
                current = await _locked_attachment(connection, identifier)
                if action_id is None and self._captures_stopped:
                    return ReadResponse(_failure("Pending", identifier), attempts)
                if current["put_entered_at"] is not None:
                    raise ActionPersistenceDefect("a put has already entered")
                await connection.execute(
                    update(attachment)
                    .where(attachment.c.id == identifier)
                    .values(put_entered_at=datetime.now(UTC))
                )
            attempts += 1
            try:
                with staging.open("rb") as body:
                    response = await joined_thread(
                        self._s3.put_object,
                        Bucket=self._bucket,
                        Key=self._key(identifier),
                        Body=body,
                        IfNoneMatch="*",
                        ContentLength=size,
                        ContentMD5=md5,
                        Metadata={"sha256": digest},
                    )
                metadata = response.get("ResponseMetadata")
                if isinstance(metadata, dict) and cast(dict[str, object], metadata).get(
                    "HTTPStatusCode"
                ) in {200, 204}:
                    result = await self._stored(identifier)
                    return ReadResponse(result, attempts)
            except ClientError as exc:
                if _definite_rejection(exc):
                    result = await self._capture_failed(
                        identifier, action_id, "Unavailable"
                    )
                    return ReadResponse(result, attempts)
            except (BotoCoreError, TimeoutError, OSError):
                pass
            current = await self._row(identifier)
            if current is None:
                raise ActionPersistenceDefect("entered original disappeared")
            result, observed = await self._reconcile_put(current)
            return ReadResponse(result, attempts + observed)
        finally:
            if not web:
                staging.unlink(missing_ok=True)

    @staticmethod
    def _key(identifier: UUID) -> str:
        return f"attachments/{identifier}/original"

    async def _capture_failed(
        self, identifier: UUID, action_id: UUID | None, code: str
    ) -> ToolResult:
        result = _failure(code, identifier)
        async with self._database.begin() as connection:
            row = await _locked_attachment(connection, identifier)
            if row["state"] != "pending":
                raise ActionPersistenceDefect("only pending capture may fail")
            await connection.execute(
                update(attachment)
                .where(attachment.c.id == identifier)
                .values(state="failed", error=code)
            )
            if action_id is not None:
                stored = await require_locked_action(connection, action_id)
                await complete_local_action(
                    connection, stored, result, datetime.now(UTC)
                )
        return result

    async def _complete(self, action_id: UUID, result: ToolResult) -> None:
        async with self._database.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            await complete_local_action(connection, stored, result, datetime.now(UTC))

    async def _head(
        self, row: RowMapping
    ) -> tuple[Literal["matching", "absent", "conflict", "unavailable"], int]:
        self._check_location(row)
        try:
            async with asyncio.timeout(HEAD_DEADLINE_SECONDS):
                result = await asyncio.to_thread(
                    self._s3.head_object, Bucket=self._bucket, Key=self._key(row["id"])
                )
            metadata = result.get("Metadata")
            if (
                result.get("ContentLength") == row["size_bytes"]
                and isinstance(metadata, dict)
                and cast(dict[str, object], metadata).get("sha256") == row["sha256"]
            ):
                return "matching", 1
            return "conflict", 1
        except ClientError as exc:
            status = cast(
                dict[str, object],
                cast(dict[str, object], exc.response).get("ResponseMetadata", {}),
            ).get("HTTPStatusCode")
            return ("absent" if status == 404 else "unavailable"), 1
        except (BotoCoreError, TimeoutError, OSError):
            return "unavailable", 1

    async def _observations(
        self, row: RowMapping, *, deleted: bool = False
    ) -> tuple[str, int]:
        attempts = 0
        last = "unavailable"
        for delay in HEAD_BACKOFF_SECONDS:
            if delay:
                await asyncio.sleep(delay)
            status, used = await self._head(row)
            attempts += used
            if (
                status == "conflict"
                or (deleted and status == "absent")
                or (not deleted and status == "matching")
            ):
                return status, attempts
            last = status
        return last, attempts

    async def _reconcile_put(
        self, row: RowMapping, *, manual: bool = False, publish_fact: bool = False
    ) -> tuple[ToolResult, int]:
        state, attempts = await self._observations(row)
        if state == "matching":
            return await self._stored(
                row["id"], manual=manual, publish_fact=publish_fact
            ), attempts
        code = "StorageConflict" if state == "conflict" else "CaptureUnresolved"
        result = _failure(code, row["id"])
        async with self._database.begin() as connection:
            current = await _locked_attachment(connection, row["id"])
            if current["state"] == "pending":
                await connection.execute(
                    update(attachment)
                    .where(attachment.c.id == row["id"])
                    .values(error=code)
                )
                await self._uncertain(connection, current, code)
        return result, attempts

    async def _stored(
        self, identifier: UUID, *, manual: bool = False, publish_fact: bool = False
    ) -> ToolResult:
        async with self._database.begin() as connection:
            row = await _locked_attachment(connection, identifier)
            if row["state"] not in {"pending", "ready"}:
                raise ActionPersistenceDefect("stored bytes have incompatible state")
            if row["state"] == "pending":
                row = (
                    (
                        await connection.execute(
                            update(attachment)
                            .where(attachment.c.id == identifier)
                            .values(
                                state="ready", stored_at=datetime.now(UTC), error=None
                            )
                            .returning(*attachment.c)
                        )
                    )
                    .mappings()
                    .one()
                )
            result: ToolResult = {"type": "Success", "value": _snapshot(row)}
            await self._settle(
                connection,
                row,
                row["capture_action_id"],
                result,
                manual=manual,
                publish_fact=publish_fact,
            )
        if row["source"]["kind"] == "web":
            try:
                (self._spool / upload_spool_name(identifier, row["sha256"])).unlink(
                    missing_ok=True
                )
            except OSError:
                logging.getLogger(__name__).warning(
                    "stored original %s needs spool cleanup", identifier
                )
        return result

    async def _settle(
        self,
        connection: AsyncConnection,
        row: RowMapping,
        action_id: UUID | None,
        result: ToolResult,
        *,
        manual: bool,
        publish_fact: bool,
    ) -> None:
        stored = (
            None
            if action_id is None
            else await require_locked_action(connection, action_id)
        )
        manual = manual or await attachment_manual_cleanup_reported(
            connection, row["id"], action_id
        )
        if publish_fact and (stored is None or manual or stored.status == "failed"):
            await self._publish_fact(connection, row, manual)
        if stored is None or stored.status == "failed":
            return
        if manual:
            if (
                stored.status == "queued"
                and stored.recovered_external_attempts == 0
                and row["state"] == "deleted"
            ):
                await resolve_reconciliation_in_transaction(
                    connection,
                    stored,
                    status="failed",
                    result=_failure("Deleted", row["id"]),
                    resolved_at=datetime.now(UTC),
                    source_conversation_id=self._conversation_id,
                )
            else:
                await self._uncertain(
                    connection,
                    row,
                    "DeleteUnresolved"
                    if row["delete_action_id"] is not None
                    else "CaptureUnresolved",
                )
        elif stored.status in {"executing", "queued"}:
            if publish_fact or stored.status == "queued":
                await resolve_reconciliation_in_transaction(
                    connection,
                    stored,
                    status="succeeded" if result["type"] == "Success" else "failed",
                    result=result,
                    resolved_at=datetime.now(UTC),
                    source_conversation_id=self._conversation_id,
                )
            else:
                await complete_local_action(
                    connection, stored, result, datetime.now(UTC)
                )
        elif stored.status == "uncertain":
            await resolve_reconciliation_in_transaction(
                connection,
                stored,
                status="succeeded" if result["type"] == "Success" else "failed",
                result=result,
                resolved_at=datetime.now(UTC),
                source_conversation_id=self._conversation_id,
            )

    async def _uncertain(
        self, connection: AsyncConnection, row: RowMapping, code: str
    ) -> None:
        action_id = (
            row["delete_action_id"]
            if row["state"] in {"deleting", "deleted"}
            else row["capture_action_id"]
        )
        if action_id is None:
            return
        stored = await require_locked_action(connection, action_id)
        if stored.status in {"executing", "queued"}:
            now = datetime.now(UTC)
            await resolve_reconciliation_in_transaction(
                connection,
                stored,
                status="uncertain",
                result={
                    "type": "action_uncertainty_v1",
                    "evidence_code": code,
                    "recorded_at": now.isoformat(),
                },
                resolved_at=now,
                source_conversation_id=self._conversation_id,
            )

    async def open(self, identifier: UUID) -> ReadResponse[ToolResult]:
        row = await self._row(identifier)
        if row is None:
            return ReadResponse(_failure("NotFound", identifier), 0)
        self._check_location(row)
        if row["state"] != "ready":
            return ReadResponse(_failure(self._unreadable(row), identifier), 0)
        path = self._cache / str(identifier) / "original"
        staging: Path | None = None
        attempts = 0
        deadline = time.monotonic() + ATTACHMENT_OPERATION_SECONDS
        try:
            async with asyncio.timeout(ATTACHMENT_OPERATION_SECONDS):
                try:
                    if path.is_file():
                        size, digest, _ = await joined_thread(
                            _byte_facts, path, deadline
                        )
                        if size == row["size_bytes"] and digest == row["sha256"]:
                            return await self._opened(row, path, 0)
                except (OSError, ValueError):
                    pass
                staging = self._stage()
                attempts = 1
                await joined_thread(self._download_r2, row, staging, deadline)
                size, digest, _ = await joined_thread(_byte_facts, staging, deadline)
                if size != row["size_bytes"] or digest != row["sha256"]:
                    return ReadResponse(
                        _failure("StorageConflict", identifier), attempts
                    )
                group_id = await joined_thread(self._prepare_cache, staging)
                async with self._database.begin() as connection:
                    current = await _locked_attachment(connection, identifier)
                    if current["state"] != "ready":
                        return ReadResponse(
                            _failure(self._unreadable(current), identifier), attempts
                        )
                    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                    os.chown(path.parent, -1, group_id)
                    os.chmod(path.parent, 0o750)
                    os.replace(staging, path)
                    return ReadResponse(
                        {
                            "type": "Success",
                            "value": {
                                "attachment": _snapshot(current),
                                "source": current["source"],
                                "local_path": str(path),
                            },
                        },
                        attempts,
                    )
        except (BotoCoreError, ClientError, OSError, TimeoutError, ValueError):
            return ReadResponse(_failure("Unavailable", identifier), attempts)
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)

    @staticmethod
    def _prepare_cache(staging: Path) -> int:
        group_id = grp.getgrnam("codex-clients").gr_gid
        os.chown(staging, -1, group_id)
        os.chmod(staging, 0o640)
        return group_id

    def _download_r2(self, row: RowMapping, path: Path, deadline: float) -> None:
        result = self._s3.get_object(Bucket=self._bucket, Key=self._key(row["id"]))
        body = cast(_StreamingBody, result["Body"])
        try:
            count = 0
            with path.open("wb") as output:
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("cache download deadline exceeded")
                    chunk = body.read(1_024 * 1_024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > ATTACHMENT_MAX_BYTES:
                        raise ValueError("stored original exceeds byte bound")
                    output.write(chunk)
        finally:
            body.close()

    async def _opened(
        self, row: RowMapping, path: Path, attempts: int
    ) -> ReadResponse[ToolResult]:
        async with self._database.begin() as connection:
            current = await _locked_attachment(connection, row["id"])
            if current["state"] != "ready":
                return ReadResponse(
                    _failure(self._unreadable(current), row["id"]), attempts
                )
            return ReadResponse(
                {
                    "type": "Success",
                    "value": {
                        "attachment": _snapshot(current),
                        "source": current["source"],
                        "local_path": str(path),
                    },
                },
                attempts,
            )

    @staticmethod
    def _unreadable(row: RowMapping) -> str:
        return {
            "failed": "Unavailable",
            "pending": row["error"] or "Pending",
            "deleting": "Deleting",
            "deleted": "Deleted",
        }[row["state"]]

    async def delete(
        self, action_id: UUID, identifier: UUID
    ) -> ReadResponse[ToolResult]:
        async with self._database.begin() as connection:
            stored = await require_locked_action(connection, action_id)
            replay = action_replay_result(stored)
            if replay is not None:
                return ReadResponse(replay, 0)
            row = (
                (
                    await connection.execute(
                        select(attachment)
                        .where(attachment.c.id == identifier)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                result = _failure("NotFound", identifier)
            elif row["state"] == "deleted":
                result = _deleted(row)
            elif row["state"] not in {"ready", "deleting"}:
                result = _failure(self._unreadable(row), identifier)
            elif row["state"] == "deleting" and row["delete_action_id"] != action_id:
                result = _failure("Deleting", identifier)
            else:
                self._check_location(row)
                result = None
                if row["state"] == "ready":
                    row = (
                        (
                            await connection.execute(
                                update(attachment)
                                .where(attachment.c.id == identifier)
                                .values(state="deleting", delete_action_id=action_id)
                                .returning(*attachment.c)
                            )
                        )
                        .mappings()
                        .one()
                    )
            if result is not None:
                await complete_local_action(
                    connection, stored, result, datetime.now(UTC)
                )
                return ReadResponse(result, 0)
        if row is None:
            raise ActionPersistenceDefect("deletion original disappeared")
        state, attempts = await self._head(row)
        if state == "conflict":
            return await self._delete_unresolved(row, "StorageConflict", attempts)
        if state == "absent":
            return await self._finish_delete(row, attempts)
        if state == "unavailable":
            state, used = await self._observations(row, deleted=True)
            attempts += used
            if state == "absent":
                return await self._finish_delete(row, attempts)
            if state != "matching":
                return await self._delete_unresolved(
                    row,
                    "StorageConflict" if state == "conflict" else "DeleteUnresolved",
                    attempts,
                )
        await self._mutation_admitted()
        stored = await self._actions.get(action_id)
        if stored is None:
            raise ActionPersistenceDefect("delete action disappeared")
        if (
            stored.recovered_external_attempts + attempts + 4
            > ATTACHMENT_EXTERNAL_ATTEMPTS
        ):
            return await self._delete_unresolved(row, "DeleteUnresolved", attempts)
        prior_provider_entry = stored.recovered_external_attempts > 0
        await self._actions.stage_external_attempts(
            action_id=action_id,
            actual_external_attempts=stored.recovered_external_attempts + attempts + 1,
        )
        attempts += 1
        try:
            await joined_thread(
                self._s3.delete_object, Bucket=self._bucket, Key=self._key(identifier)
            )
        except ClientError as exc:
            if _definite_rejection(exc) and not prior_provider_entry:
                async with self._database.begin() as connection:
                    current = await _locked_attachment(connection, identifier)
                    result = await self._fail_delete(connection, current, "Unavailable")
                return ReadResponse(result, attempts)
        except (BotoCoreError, TimeoutError, OSError):
            pass
        state, used = await self._observations(row, deleted=True)
        attempts += used
        if state == "absent":
            return await self._finish_delete(row, attempts)
        if (
            state == "matching"
            and stored.attempts < stored.execution_contract.max_attempts
        ):
            await self._actions.requeue_after_proved_absence(
                action_id,
                actual_external_attempts=used,
                max_external_attempts=ATTACHMENT_EXTERNAL_ATTEMPTS,
            )
            raise RecoveryRequired(
                "attachment deletion may safely enter its remaining executor"
            )
        return await self._delete_unresolved(
            row,
            "StorageConflict" if state == "conflict" else "DeleteUnresolved",
            attempts,
        )

    async def _delete_unresolved(
        self,
        row: RowMapping,
        code: Literal["StorageConflict", "DeleteUnresolved"],
        attempts: int,
    ) -> ReadResponse[ToolResult]:
        async with self._database.begin() as connection:
            current = await _locked_attachment(connection, row["id"])
            stored = await require_locked_action(
                connection, current["delete_action_id"]
            )
            if (
                stored.status in {"executing", "queued"}
                and stored.recovered_external_attempts == 0
            ):
                failure = (
                    "StorageConflict" if code == "StorageConflict" else "Unavailable"
                )
                result = await self._fail_delete(connection, current, failure)
            else:
                await connection.execute(
                    update(attachment)
                    .where(attachment.c.id == row["id"])
                    .values(error=code)
                )
                await self._uncertain(connection, current, code)
                result = _failure(code, row["id"])
        return ReadResponse(result, attempts)

    async def _fail_delete(
        self,
        connection: AsyncConnection,
        row: RowMapping,
        code: Literal["StorageConflict", "Unavailable", "CacheCleanupFailed"],
    ) -> ToolResult:
        result = _failure(code, row["id"])
        await connection.execute(
            update(attachment).where(attachment.c.id == row["id"]).values(error=code)
        )
        await self._settle(
            connection,
            row,
            row["delete_action_id"],
            result,
            manual=False,
            publish_fact=False,
        )
        return result

    async def _finish_delete(
        self, row: RowMapping, attempts: int
    ) -> ReadResponse[ToolResult]:
        try:
            await joined_thread(self._remove_local_original, row)
        except OSError:
            async with self._database.begin() as connection:
                current = await _locked_attachment(connection, row["id"])
                result = await self._fail_delete(
                    connection, current, "CacheCleanupFailed"
                )
            return ReadResponse(result, attempts)
        async with self._database.begin() as connection:
            current = await _locked_attachment(connection, row["id"])
            if current["state"] == "deleting":
                current = (
                    (
                        await connection.execute(
                            update(attachment)
                            .where(attachment.c.id == row["id"])
                            .values(
                                state="deleted",
                                deleted_at=datetime.now(UTC),
                                error=None,
                            )
                            .returning(*attachment.c)
                        )
                    )
                    .mappings()
                    .one()
                )
            result = _deleted(current)
            await self._settle(
                connection,
                current,
                current["delete_action_id"],
                result,
                manual=False,
                publish_fact=False,
            )
            return ReadResponse(result, attempts)

    def _remove_local_original(self, row: RowMapping) -> None:
        if row["source"]["kind"] == "web":
            (self._spool / upload_spool_name(row["id"], row["sha256"])).unlink(
                missing_ok=True
            )
        directory = self._cache / str(row["id"])
        if directory.exists():
            shutil.rmtree(directory)

    async def recover_action(self, action_id: UUID) -> StoredAction | None:
        stored = await self._actions.get(action_id)
        if stored is None:
            raise ActionPersistenceDefect("attachment action disappeared")
        if stored.status in {"succeeded", "failed", "cancelled"}:
            return stored
        async with self._database.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(attachment).where(
                            (attachment.c.capture_action_id == action_id)
                            | (attachment.c.delete_action_id == action_id)
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            if stored.attempts < stored.execution_contract.max_attempts:
                return None
            await self._complete(action_id, _failure("Unavailable"))
            return await self._actions.get(action_id)
        if stored.status == "queued" and stored.tool_name == ToolId(
            "attachment.delete"
        ):
            async with self._database.begin() as connection:
                reported_manual = await attachment_manual_cleanup_reported(
                    connection, row["id"], action_id
                )
                if reported_manual:
                    current = await _locked_attachment(connection, row["id"])
                    if current["state"] == "deleted":
                        await self._settle(
                            connection,
                            current,
                            action_id,
                            _deleted(current),
                            manual=True,
                            publish_fact=False,
                        )
                    elif stored.recovered_external_attempts > 0:
                        await self._uncertain(connection, current, "DeleteUnresolved")
            if reported_manual:
                return await self._actions.get(action_id)
        if stored.tool_name == ToolId("attachment.retain"):
            if row["state"] == "pending" and row["put_entered_at"] is None:
                if stored.attempts < stored.execution_contract.max_attempts:
                    return None
                await self._capture_failed(row["id"], action_id, "Unavailable")
            elif row["state"] == "pending":
                await self._reconcile_put(row)
            elif row["state"] == "ready":
                await self._stored(row["id"])
        elif row["state"] == "deleting":
            state, attempts = await self._observations(row, deleted=True)
            if state == "absent":
                await self._finish_delete(row, attempts)
            elif (
                state == "matching"
                and stored.status != "uncertain"
                and stored.attempts < stored.execution_contract.max_attempts
            ):
                return None
            else:
                await self._delete_unresolved(
                    row,
                    "StorageConflict" if state == "conflict" else "DeleteUnresolved",
                    attempts,
                )
        return await self._actions.get(action_id)

    async def reconcile(
        self, identifier: UUID, *, after_manual_cleanup: bool = False
    ) -> dict[str, object]:
        row = await self._row(identifier)
        if row is None:
            return {"id": str(identifier), "state": "not_found"}
        self._check_location(row)
        if row["state"] == "pending" and row["put_entered_at"] is not None:
            await self._reconcile_put(
                row, manual=after_manual_cleanup, publish_fact=True
            )
        elif row["state"] == "deleting":
            state, _ = await self._observations(row, deleted=True)
            if (
                state == "absent"
                and not (self._cache / str(identifier)).exists()
                and not (
                    row["source"]["kind"] == "web"
                    and (
                        self._spool / upload_spool_name(identifier, row["sha256"])
                    ).exists()
                )
            ):
                async with self._database.begin() as connection:
                    current = await _locked_attachment(connection, identifier)
                    current = (
                        (
                            await connection.execute(
                                update(attachment)
                                .where(attachment.c.id == identifier)
                                .values(
                                    state="deleted",
                                    deleted_at=datetime.now(UTC),
                                    error=None,
                                )
                                .returning(*attachment.c)
                            )
                        )
                        .mappings()
                        .one()
                    )
                    await self._settle(
                        connection,
                        current,
                        current["delete_action_id"],
                        _deleted(current),
                        manual=after_manual_cleanup,
                        publish_fact=True,
                    )
        current = await self._row(identifier)
        if current is None:
            raise ActionPersistenceDefect("reconciled original disappeared")
        if after_manual_cleanup:
            async with self._database.begin() as connection:
                await self._publish_fact(connection, current, True)
        return {
            "id": str(identifier),
            "state": current["state"],
            "error": current["error"],
            "after_manual_cleanup": after_manual_cleanup,
        }

    async def _publish_fact(
        self, connection: AsyncConnection, row: RowMapping, manual: bool
    ) -> None:
        source_id = f"{row['id']}:{row['state']}"
        existing = await connection.scalar(
            select(message.c.id).where(
                message.c.source == "attachment",
                message.c.source_message_id == source_id,
            )
        )
        if existing is not None:
            return
        action_id = (
            row["delete_action_id"]
            if row["state"] in {"deleting", "deleted"}
            else row["capture_action_id"]
        )
        parent_id = row["origin_message_id"]
        if action_id is not None:
            parent_id = await connection.scalar(
                select(action.c.origin_message_id).where(action.c.id == action_id)
            )
        origin = (
            (
                await connection.execute(
                    select(
                        message.c.id, message.c.control_kind, message.c.request_state
                    ).where(message.c.id == parent_id)
                )
            )
            .mappings()
            .one()
        )
        inserted = await append_waking_input(
            connection,
            role="host",
            text=f"attachment:{row['id']} storage observation: {row['state']}. "
            + (
                "manual cleanup was reported; "
                "this does not prove the original action outcome."
                if manual
                else "the registered storage state was observed."
            ),
            source="attachment",
            source_conversation_id=self._conversation_id,
            source_message_id=source_id,
            created_at=datetime.now(UTC),
            parent_request_id=origin["id"]
            if origin["control_kind"] is None and origin["request_state"] is not None
            else None,
        )

        await connection.execute(
            update(message)
            .where(message.c.id == inserted.message.id)
            .values(
                trace={
                    **inserted.message.trace,
                    "attachment_id": str(row["id"]),
                    "origin_message_id": str(row["origin_message_id"]),
                    "affected_action_id": None if action_id is None else str(action_id),
                    "after_manual_cleanup": manual,
                }
            )
        )

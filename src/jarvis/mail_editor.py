"""Owner-operated draft edits. Gmail holds the body, postgres fences each effect."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from llm_tools import canonical_json_bytes
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import mail_editor_operation as operation
from jarvis.mail_files import MAIL_MAX_BYTES, MAIL_MAX_FILES, MailFile
from jarvis.owner_gmail import (
    LiveDraft,
    MailError,
    OwnerDraft,
    OwnerGmail,
    PreparedMail,
    prepare,
)
from jarvis.ownership import Database, DeploymentOwnershipDefect
from jarvis.write_tools import Mailbox


@dataclass(frozen=True, slots=True)
class EditorTarget:
    account: str
    google_sub: str
    draft_id: str
    thread_id: str | None
    epoch: UUID
    quote: str | None
    draft_message_id: str
    draft_raw_digest: str

    def draft(self) -> OwnerDraft:
        return OwnerDraft(
            account=self.account,
            draft_id=self.draft_id,
            thread_id=self.thread_id,
            quote=self.quote,
        )


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


type Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Keep(_Closed):
    keep: Annotated[int, Field(strict=True, ge=1, le=MAIL_MAX_FILES)]
    sha256: Digest


class Upload(_Closed):
    upload: Annotated[int, Field(strict=True, ge=0, lt=MAIL_MAX_FILES)]


class EditCommand(_Closed):
    kind: Literal["save", "send"]
    base: Digest
    to: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    cc: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    bcc: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    subject: Annotated[str, Field(max_length=998)]
    body: Annotated[str, Field(max_length=100_000)]
    files: Annotated[tuple[Keep | Upload, ...], Field(max_length=MAIL_MAX_FILES)]


class ResolveSave(_Closed):
    operation_id: UUID
    version: Digest


type FileParts = tuple[tuple[MailFile, bytes], ...]
type Payload = dict[str, Any]
type Reply = tuple[int, Payload]


class EditorFailure(Exception):
    def __init__(self, status: int, reason: str, **fields: object) -> None:
        self.status = status
        self.body: Payload = {"state": "failed", "reason": reason, **fields}
        super().__init__(reason)


def mail_failure(err: MailError) -> EditorFailure:
    reason = err.reason
    status = {
        "reconnect_required": 403,
        "permission_denied": 403,
        "draft_missing": 410,
        "too_large": 413,
        "rate_limited": 429,
        "temporary": 503,
        "provider_error": 502,
        "draft_changed": 409,
    }.get(reason, 422)
    failure = EditorFailure(status, reason)
    if reason == "reconnect_required":
        failure.body["state"] = reason
    if err.retry_after is not None:
        failure.body["retry_after"] = err.retry_after
    return failure


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _version(
    target: EditorTarget, grant: UUID, generation: int, live: LiveDraft
) -> str:
    return _digest(
        (
            1,
            str(target.epoch),
            target.google_sub,
            target.draft_id,
            str(grant),
            str(live.workspace_grant),
            generation,
            live.message_id,
            live.raw_digest,
        )
    )


def _files(files: tuple[MailFile, ...]) -> list[Payload]:
    return [
        {
            "slot": slot,
            "name": f.filename,
            "type": f.media_type,
            "bytes": f.size_bytes,
            "sha256": f.sha256,
        }
        for slot, f in enumerate(files, 1)
    ]


def _key(target: EditorTarget):
    return and_(
        operation.c.google_sub == target.google_sub,
        operation.c.draft_id == target.draft_id,
    )


async def _row(
    conn: AsyncConnection, target: EditorTarget, *, lock: bool = False
) -> Payload:
    query = select(operation).where(_key(target))
    if lock:
        query = query.with_for_update()
    row = (await conn.execute(query)).mappings().one_or_none()
    if row is None:
        return {"generation": 0, "state": None, "operation_id": None}
    result = dict(row)
    disposition: Payload = result["provider_result"] or {}
    if (
        result["state"] == "save_unknown"
        and disposition.get("reason") == "owner_resolved_save"
    ):
        # The owner released the hold without proving the earlier write's outcome.
        result["state"] = "expired"
    return result


def _receipt(row: Payload) -> Reply:
    if row["state"] == "expired":
        raise EditorFailure(409, "operation_expired")
    result = dict(row.get("provider_result") or {})
    if "ack_id" in result:
        result["acknowledged_message_id"] = result.pop("ack_id")
    state = row["state"]
    return (
        202 if state in ("entered", "save_unknown", "send_unknown") else 200,
        {
            "state": state,
            "operation_id": str(row["operation_id"]),
            "kind": row["kind"],
            **result,
        },
    )


def _prior(row: Payload, identifier: UUID, digest: str) -> Reply | None:
    if row["operation_id"] == identifier:
        if digest != row["request_digest"]:
            raise EditorFailure(409, "operation_changed")
        return _receipt(row)
    if row["state"] in ("entered", "save_unknown", "sent", "send_unknown"):
        _, receipt = _receipt(row)
        receipt.pop("reason", None)
        raise EditorFailure(409, "draft_held", **receipt)
    return None


class MailEditor:
    def __init__(self, database: Database, google: OwnerGmail, *, epoch: UUID | None):
        self.database = database
        self.google = google
        self.epoch = epoch
        self._accepting = False
        self._tasks: set[asyncio.Task[Reply]] = set()
        self._writers: set[UUID] = set()

    async def startup(self) -> None:
        """Called only after acquiring existing exclusive deployment ownership."""
        if self._accepting or self._tasks:
            raise RuntimeError("mail editor already active")
        async with self.database.begin() as conn:
            await conn.execute(
                update(operation)
                .where(operation.c.state == "entered")
                .values(
                    state=case(
                        (operation.c.kind == "save", "save_unknown"),
                        else_="send_unknown",
                    ),
                    updated_at=func.now(),
                )
            )
        self._accepting = True

    async def drain(self) -> None:
        self._accepting = False
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    def _grant(self, target: EditorTarget) -> UUID:
        if not self._accepting:
            raise EditorFailure(503, "unavailable")
        if self.epoch is None or target.epoch != self.epoch:
            raise EditorFailure(409, "editor_epoch_changed")
        enrollment = self.google.identity(target.draft())
        if (enrollment.subject, enrollment.account) != (
            target.google_sub,
            target.account,
        ):
            raise EditorFailure(403, "reconnect_required", state="reconnect_required")
        return enrollment.grant_id

    def _require_current(
        self, target: EditorTarget, grant: UUID, live: LiveDraft
    ) -> None:
        if not self._accepting:
            raise EditorFailure(503, "unavailable")
        self.google.require_current(target.draft(), grant, live.workspace_grant)

    async def _readrow(self, target: EditorTarget) -> Payload:
        async with self.database.connect() as conn:
            return await _row(conn, target)

    async def current(self, target: EditorTarget) -> Payload:
        grant = self._grant(target)
        row = await self._readrow(target)
        if row["state"] in ("sent", "send_unknown", "entered"):
            return {**_receipt(row)[1], "account": target.account}
        live = await self.google.read(target.draft(), grant)
        checked = await self._readrow(target)
        self._require_current(target, grant, live)
        if (
            checked["generation"] != row["generation"]
            or checked["state"] != row["state"]
        ):
            raise EditorFailure(409, "stale_version")
        data = self._current(target, grant, row["generation"], live)
        if row["state"] == "save_unknown":
            data.update(_receipt(row)[1])
            data["desired_observed"] = live.semantic_digest == row["desired_digest"]
        return data

    @staticmethod
    def _current(
        target: EditorTarget, grant: UUID, generation: int, live: LiveDraft
    ) -> Payload:
        return {
            "state": "ready",
            "account": target.account,
            "version": _version(target, grant, generation, live),
            "from": live.sender.model_dump(),
            "to": [m.model_dump() for m in live.to],
            "cc": [m.model_dump() for m in live.cc],
            "bcc": [m.model_dump() for m in live.bcc],
            "subject": live.subject,
            "body": live.body,
            "quote": live.quote,
            "threaded": live.threaded,
            "files": _files(live.files),
            "as_drafted": (
                live.message_id == target.draft_message_id
                and live.raw_digest == target.draft_raw_digest
            ),
        }

    async def file(
        self, target: EditorTarget, version: str, slot: int
    ) -> tuple[MailFile, bytes]:
        grant = self._grant(target)
        row = await self._readrow(target)
        if row["state"] in ("entered", "sent", "send_unknown"):
            raise EditorFailure(409, "stale_version")
        live = await self.google.read(target.draft(), grant)
        current = await self._readrow(target)
        self._require_current(target, grant, live)
        if current["generation"] != row["generation"] or version != _version(
            target, grant, current["generation"], live
        ):
            raise EditorFailure(409, "stale_version")
        if not 1 <= slot <= len(live.files):
            raise EditorFailure(404, "missing_file")
        return live.files[slot - 1], live.parts[slot - 1]

    async def status(self, target: EditorTarget, identifier: UUID) -> Reply:
        self._grant(target)
        row = await self._readrow(target)
        if row["operation_id"] != identifier:
            raise EditorFailure(409 if row["generation"] else 404, "operation_expired")
        return _receipt(row)

    async def submit(
        self,
        target: EditorTarget,
        identifier: UUID,
        cmd: EditCommand,
        uploads: FileParts,
    ) -> Reply:
        grant = self._grant(target)
        task = asyncio.create_task(
            self._submit(target, grant, identifier, cmd, uploads)
        )
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return await asyncio.shield(task)

    def _finished(self, task: asyncio.Task[Reply]) -> None:
        self._tasks.discard(task)
        # Retrieve even when the HTTP caller disconnected.
        if not task.cancelled():
            error = task.exception()
            if error and not isinstance(error, EditorFailure | MailError):
                logging.getLogger(__name__).error(
                    "mail editor task failed: %s", type(error).__name__
                )

    async def _submit(
        self,
        target: EditorTarget,
        grant: UUID,
        identifier: UUID,
        cmd: EditCommand,
        uploads: FileParts,
    ) -> Reply:
        indices = [entry.upload for entry in cmd.files if isinstance(entry, Upload)]
        keep = [entry.keep for entry in cmd.files if isinstance(entry, Keep)]
        if sorted(indices) != list(range(len(uploads))) or len(set(keep)) != len(keep):
            raise EditorFailure(422, "invalid_file")
        digest = _digest(
            (
                1,
                cmd.model_dump(mode="json"),
                [meta.model_dump(mode="json") for meta, _ in uploads],
            )
        )
        row = await self._readrow(target)
        replay = _prior(row, identifier, digest)
        if replay is not None:
            return replay
        draft = target.draft()
        live = await self.google.read(draft, grant)
        if cmd.base != _version(target, grant, row["generation"], live):
            raise EditorFailure(409, "stale_version")
        parts: list[tuple[MailFile, bytes]] = []
        for entry in cmd.files:
            if isinstance(entry, Upload):
                parts.append(uploads[entry.upload])
            else:
                index = entry.keep - 1
                if index >= len(live.files) or live.files[index].sha256 != entry.sha256:
                    raise EditorFailure(409, "stale_file", slot=entry.keep)
                parts.append((live.files[index], live.parts[index]))
        if sum(f.size_bytes for f, _ in parts) > MAIL_MAX_BYTES:
            raise EditorFailure(413, "too_large")
        prepared = await asyncio.to_thread(
            prepare,
            live,
            to=cmd.to,
            cc=cmd.cc,
            bcc=cmd.bcc,
            subject=cmd.subject,
            body=cmd.body,
            files=tuple(parts),
            send=cmd.kind == "send",
        )
        try:
            async with self.database.begin() as conn:
                await conn.execute(
                    insert(operation)
                    .values(google_sub=target.google_sub, draft_id=target.draft_id)
                    .on_conflict_do_nothing()
                )
                locked = await _row(conn, target, lock=True)
                replay = _prior(locked, identifier, digest)
                if replay is not None:
                    return replay
                self._require_current(target, grant, live)
                if locked["generation"] != row["generation"]:
                    raise EditorFailure(409, "stale_version")
                generation = row["generation"] + 1
                await conn.execute(
                    update(operation)
                    .where(_key(target))
                    .values(
                        generation=generation,
                        operation_id=identifier,
                        kind=cmd.kind,
                        request_digest=digest,
                        base_revision=cmd.base,
                        desired_digest=prepared.semantic_digest,
                        state="entered",
                        provider_result=None,
                        updated_at=func.now(),
                    )
                )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise EditorFailure(409, "operation_changed") from None
            raise
        self._writers.add(identifier)
        try:
            return await self._execute(
                target, grant, identifier, generation, cmd.kind, prepared
            )
        finally:
            self._writers.discard(identifier)

    async def _record(
        self,
        target: EditorTarget,
        identifier: UUID,
        generation: int,
        state: str,
        result: Payload,
    ) -> Reply:
        async with self.database.begin() as conn:
            changed = await conn.execute(
                update(operation)
                .where(
                    _key(target),
                    operation.c.operation_id == identifier,
                    operation.c.generation == generation,
                    operation.c.state == "entered",
                )
                .values(state=state, provider_result=result, updated_at=func.now())
                .returning(operation)
            )
            row = changed.mappings().one_or_none()
            if row is not None:
                return _receipt(dict(row))
            latest = await _row(conn, target)
            if latest["operation_id"] == identifier:
                return _receipt(latest)
            raise EditorFailure(409, "operation_expired")

    async def _execute(
        self,
        target: EditorTarget,
        grant: UUID,
        identifier: UUID,
        generation: int,
        kind: Literal["save", "send"],
        prepared: PreparedMail,
    ) -> Reply:
        draft = target.draft()
        uncertain: Payload = {}
        confirmation = "acknowledged"
        acknowledged: str | None = None

        async def record(state: str, result: Payload) -> Reply:
            try:
                return await self._record(target, identifier, generation, state, result)
            except (DBAPIError, DeploymentOwnershipDefect):
                # The entered claim was committed before Google received this write.
                # A DB error cannot certify its settlement, even with Google's reply.
                logging.getLogger(__name__).warning("mail editor receipt unavailable")
                body: Payload = {
                    "state": f"{kind}_unknown",
                    "kind": kind,
                    "operation_id": str(identifier),
                    "reason": "receipt_unavailable",
                }
                if acknowledged is not None:
                    body["acknowledged_message_id"] = acknowledged
                return 202, body

        try:
            message_id = await self.google.write(
                draft, grant, prepared, send=kind == "send"
            )
        except MailError as err:
            uncertain["reason"] = err.reason
            if err.retry_after is not None:
                uncertain["retry_after"] = err.retry_after
            acknowledged = err.acknowledged_id
            if acknowledged:
                uncertain["ack_id"] = acknowledged
            if not err.uncertain:
                return await record("failed", uncertain)
            if kind == "send":
                return await record("send_unknown", uncertain)
            confirmation = "observed_match"
        except Exception:
            return await record(
                "send_unknown" if kind == "send" else "save_unknown",
                {"reason": "interrupted"},
            )
        else:
            acknowledged = message_id
            if kind == "send":
                return await record("sent", {"message_id": message_id})
            uncertain["ack_id"] = message_id
            status = await record("entered", uncertain)
            if status[1]["state"] != "entered":
                return status
        try:
            live = await self.google.read(draft, grant)
            if live.semantic_digest == prepared.semantic_digest:
                if uncertain.get("ack_id") != live.message_id:
                    confirmation = "observed_match"
                result = {
                    "message_id": live.message_id,
                    "version": _version(target, grant, generation, live),
                    "files": _files(live.files),
                    "confirmation": confirmation,
                }
                return await record("saved", result)
            uncertain["reason"] = "readback_changed"
        except MailError as err:
            uncertain["reason"] = err.reason
        except Exception:
            uncertain["reason"] = "readback_failed"
        return await record("save_unknown", uncertain)

    async def resolve_save(
        self, target: EditorTarget, decision: ResolveSave
    ) -> Payload:
        grant = self._grant(target)
        row = await self._readrow(target)
        if (
            row["operation_id"] != decision.operation_id
            or row["state"] != "save_unknown"
            or decision.operation_id in self._writers
        ):
            raise EditorFailure(409, "save_resolution_unavailable")
        live = await self.google.read(target.draft(), grant)
        if decision.version != _version(target, grant, row["generation"], live):
            raise EditorFailure(409, "stale_version")
        async with self.database.begin() as conn:
            self._require_current(target, grant, live)
            next_gen = await conn.scalar(
                update(operation)
                .where(
                    _key(target),
                    operation.c.operation_id == decision.operation_id,
                    operation.c.state == "save_unknown",
                    operation.c.generation == row["generation"],
                )
                .values(
                    generation=row["generation"] + 1,
                    provider_result={
                        **(row.get("provider_result") or {}),
                        "reason": "owner_resolved_save",
                    },
                    updated_at=func.now(),
                )
                .returning(operation.c.generation)
            )
            if next_gen is None:
                raise EditorFailure(409, "stale_version")
        return self._current(target, grant, next_gen, live)

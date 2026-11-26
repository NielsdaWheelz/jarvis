"""Verify upload request framing and serve locally held submissions."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import Response

from jarvis._thread_io import joined_thread
from jarvis.attachments import AttachmentStore, CustodyConflict, WebUpload
from jarvis.home_file_content import file_response, media_type
from jarvis.mail_files import canonical_media_type
from jarvis.read_tools import ATTACHMENT_MAX_BYTES

BODY_LIMIT = 90 * 1024 * 1024
TEXT_LIMIT = 16 * 1024
# A fully escaped 16 kib text and its typed reference fit in this envelope.
MESSAGE_PART_LIMIT = 128 * 1024
FILE_LIMIT = 10
_UPLOAD_LIMIT = "upload exceeds 90 mib"


def _fingerprint(files: list[UploadFile], submission_id: UUID) -> tuple[WebUpload, ...]:
    uploads: list[WebUpload] = []
    for slot, file in enumerate(files):
        digest = hashlib.sha256()
        size = 0
        header = file.file.read(16)
        file.file.seek(0)
        while chunk := file.file.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        file.file.seek(0)
        if size > ATTACHMENT_MAX_BYTES:
            raise HTTPException(413, "file exceeds 100 mib")
        name = file.filename or "original"
        mime = media_type(header)
        if mime == "application/octet-stream":
            declared = canonical_media_type(file.content_type)
            mime = (
                canonical_media_type(mimetypes.guess_type(name)[0])
                if declared == mime
                else declared
            )
        uploads.append(
            WebUpload(
                submission_id,
                slot,
                name,
                size,
                digest.hexdigest(),
                mime,
                file.file,
            )
        )
    return tuple(uploads)


class _Form(MultiPartParser):
    complete = False

    def on_end(self) -> None:
        self.complete = True


@asynccontextmanager
async def read_submission(
    request: Request, submission_id: UUID
) -> AsyncGenerator[tuple[str, object, tuple[WebUpload, ...]]]:
    async def limited() -> AsyncGenerator[bytes]:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if media == "application/json" and size > MESSAGE_PART_LIMIT:
                raise HTTPException(413, "message part is too large")
            if size > BODY_LIMIT:
                if parser is not None:
                    raise MultiPartException(_UPLOAD_LIMIT)
                raise HTTPException(413, _UPLOAD_LIMIT)
            yield chunk
        if parser is not None and not parser.complete:
            raise MultiPartException("incomplete multipart upload")

    media = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    parser: _Form | None = None
    files: list[UploadFile] = []
    form = None
    try:
        try:
            if media == "multipart/form-data":
                parser = _Form(
                    request.headers,
                    limited(),
                    max_files=FILE_LIMIT + 1,
                    max_fields=1,
                    max_part_size=MESSAGE_PART_LIMIT,
                )
                form = await parser.parse()
                messages = form.getlist("message")
                if len(messages) != 1 or set(form) - {"message", "file"}:
                    raise HTTPException(422, "expected one message and ordered files")
                message = messages[0]
                if isinstance(message, UploadFile):
                    if (message.size or 0) > parser.max_part_size:
                        raise HTTPException(413, "message part is too large")
                    message = (await message.read()).decode("utf-8")
                value: object = json.loads(message)
                for part in form.getlist("file"):
                    if (
                        not isinstance(part, UploadFile)
                        or not part.filename
                        or "\0" in part.filename
                    ):
                        raise HTTPException(422, "expected a named upload")
                    files.append(part)
                if len(files) > FILE_LIMIT:
                    raise HTTPException(422, "at most ten files per message")
            elif media == "application/json":
                body = bytearray()
                async for chunk in limited():
                    body.extend(chunk)
                value = json.loads(body.decode("utf-8"))
            else:
                raise HTTPException(422, "expected json or multipart")
            if not isinstance(value, dict):
                raise HTTPException(422, "invalid message")
            fields = cast(dict[str, object], value)
            text, ref = fields.get("text"), fields.get("ref")
            if (
                set(fields) - {"text", "ref"}
                or not isinstance(text, str)
                or "\0" in text
                or (not text.strip() and not files)
            ):
                raise HTTPException(422, "invalid message")
            if len(text.encode()) > TEXT_LIMIT:
                raise HTTPException(413, "text exceeds 16 kib")
            uploads = (
                await joined_thread(_fingerprint, files, submission_id) if files else ()
            )
        except MultiPartException as exc:
            if exc.message == _UPLOAD_LIMIT:
                raise HTTPException(413, _UPLOAD_LIMIT) from exc
            if exc.message.startswith("Part exceeded maximum size"):
                raise HTTPException(413, "message part is too large") from exc
            raise HTTPException(422, "invalid multipart message") from exc
        except ValueError as exc:
            raise HTTPException(422, "invalid message body") from exc
        yield text, ref, uploads
    finally:
        if form is not None:
            await form.close()


async def attachment_response(
    attachments: AttachmentStore, identifier: UUID, *, head: bool = False
) -> Response:
    try:
        row, stream = await attachments.open_pending(identifier)
    except CustodyConflict as exc:
        code = str(exc)
        raise HTTPException(
            {"NotFound": 404, "Unavailable": 410}.get(code, 409),
            code,
            headers={"X-Jarvis-File-State": code},
        ) from exc
    except OSError as exc:
        raise HTTPException(
            503,
            "upload bytes are unavailable",
            headers={"X-Jarvis-File-State": "Unavailable"},
        ) from exc
    try:
        mime = media_type(stream.read(16))
        stream.seek(0)
    except BaseException:
        stream.close()
        raise
    return file_response(stream, row.filename or str(identifier), mime, head=head)

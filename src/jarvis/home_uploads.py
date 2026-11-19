"""Durable browser ingress and verified original downloads."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from jarvis._thread_io import joined_thread
from jarvis.attachments import AttachmentStore, WebUpload

BODY_LIMIT = 90 * 1024 * 1024
TEXT_LIMIT = 16 * 1024
FILE_LIMIT = 10


def _media_type(header: bytes) -> str:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _stage(
    files: list[UploadFile], submission_id: UUID, spool: Path
) -> tuple[WebUpload, ...]:
    spool.mkdir(mode=0o700, exist_ok=True)
    parent = os.open(spool.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    directory = os.open(spool, os.O_RDONLY)
    try:
        uploads: list[WebUpload] = []
        for slot, file in enumerate(files):
            digest = hashlib.sha256()
            size = 0
            header = file.file.read(16)
            file.file.seek(0)
            with tempfile.NamedTemporaryFile(dir=spool, prefix=".incoming-") as output:
                while chunk := file.file.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
                upload = WebUpload(
                    submission_id,
                    slot,
                    file.filename or "original",
                    size,
                    digest.hexdigest(),
                    _media_type(header),
                )
                try:
                    os.link(output.name, spool / f"{upload.id}.{upload.sha256}")
                except FileExistsError:
                    pass
                uploads.append(upload)
        os.fsync(directory)
        return tuple(uploads)
    finally:
        os.close(directory)


class _Form(MultiPartParser):
    complete = False

    def on_end(self) -> None:
        self.complete = True


async def read_submission(
    request: Request, submission_id: UUID, spool: Path
) -> tuple[str, dict[str, object] | None, tuple[WebUpload, ...]]:
    async def limited() -> AsyncGenerator[bytes]:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > BODY_LIMIT:
                raise HTTPException(413, "upload exceeds 90 mib")
            yield chunk
        if parser is not None and not parser.complete:
            raise HTTPException(422, "incomplete multipart upload")

    media = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    parser: _Form | None = None
    files: list[UploadFile] = []
    form = None
    try:
        if media == "multipart/form-data":
            parser = _Form(
                request.headers, limited(), max_files=FILE_LIMIT + 1, max_fields=1
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
            or (ref is not None and not isinstance(ref, dict))
        ):
            raise HTTPException(422, "invalid message")
        if len(text.encode()) > TEXT_LIMIT:
            raise HTTPException(413, "text exceeds 16 kib")
        uploads = (
            await joined_thread(_stage, files, submission_id, spool) if files else ()
        )
        return text, cast(dict[str, object] | None, ref), uploads
    except MultiPartException as exc:
        if exc.message.startswith("Part exceeded maximum size"):
            raise HTTPException(413, "message part is too large") from exc
        raise HTTPException(422, "invalid multipart message") from exc
    except ValueError as exc:
        raise HTTPException(422, "invalid message body") from exc
    finally:
        if form is not None:
            await form.close()


async def attachment_response(
    attachments: AttachmentStore, identifier: UUID, *, head: bool = False
) -> Response:
    result = (await attachments.open(identifier)).value
    if result["type"] == "Failure":
        code = result["error"]["type"]
        raise HTTPException(
            {"NotFound": 404, "Deleted": 410}.get(str(code), 409), str(code)
        )
    value = cast(dict[str, object], result["value"])
    descriptor = cast(dict[str, object], value["attachment"])
    return _original_response(
        Path(str(value["local_path"])), str(descriptor.get("name") or identifier), head
    )


def _original_response(path: Path, name: str, head: bool) -> Response:
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        # A deletion can remove the cache between verification and opening the fd.
        raise HTTPException(409, "original unavailable") from None
    try:
        media_type = _media_type(stream.read(16))
        stream.seek(0)
        filename = name.replace("\\", "/").split("/")[-1]
        filename = (
            "".join(ch for ch in filename if ch.isprintable()).strip() or "original"
        )
        disposition = (
            "attachment" if media_type == "application/octet-stream" else "inline"
        )
        encoded_name = quote(filename, safe="")
        headers = {
            "Content-Disposition": f"{disposition}; filename*=utf-8''{encoded_name}",
            "Content-Length": str(os.fstat(stream.fileno()).st_size),
            "X-Content-Type-Options": "nosniff",
        }
        if head:
            stream.close()
            return Response(media_type=media_type, headers=headers)
        return _FileResponse(stream, media_type, headers)
    except BaseException:
        stream.close()
        raise


class _FileResponse(StreamingResponse):
    """Own the verified fd until ASGI completes or a reader disconnects."""

    def __init__(self, stream: BinaryIO, media: str, headers: dict[str, str]) -> None:
        self.stream = stream
        super().__init__(
            iter(lambda: stream.read(256 * 1024), b""),
            media_type=media,
            headers=headers,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.stream.close()

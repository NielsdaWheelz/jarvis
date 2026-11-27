"""Authenticated home routes for one verified draft handoff."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse, Response

from jarvis.home_file_content import download_headers, media_type
from jarvis.home_uploads import CompleteMultipartParser
from jarvis.mail_editor import (
    EditCommand,
    EditorFailure,
    EditorTarget,
    FileParts,
    MailEditor,
    ResolveSave,
    SendChoice,
    SendReview,
    mail_failure,
)
from jarvis.mail_files import (
    MAIL_MAX_BYTES,
    MAIL_MAX_FILES,
    MailFile,
    canonical_media_type,
)
from jarvis.owner_gmail import MailError

# Includes the escaped JSON envelope. MIME limits apply separately after construction.
_COMMAND_LIMIT = 1024 * 1024
_MULTIPART_LIMIT = MAIL_MAX_BYTES + 2 * _COMMAND_LIMIT


async def _command(request: Request) -> tuple[EditCommand, FileParts]:
    if (
        request.headers.get("content-type", "").partition(";")[0].strip().lower()
        != "multipart/form-data"
    ):
        raise EditorFailure(422, "expected_multipart")

    async def limited() -> AsyncGenerator[bytes]:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > _MULTIPART_LIMIT:
                raise MultiPartException("body too large")
            yield chunk
        if not parser.complete:
            raise MultiPartException("incomplete multipart")

    parser = CompleteMultipartParser(
        request.headers,
        limited(),
        max_files=MAIL_MAX_FILES + 1,
        max_fields=1,
        max_part_size=_COMMAND_LIMIT,
    )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        status = (
            413 if "size" in exc.message or exc.message == "body too large" else 422
        )
        raise EditorFailure(
            status, "too_large" if status == 413 else "invalid_multipart"
        ) from None
    try:
        names = [name for name, _ in form.multi_items()]
        if (
            not names
            or names[0] != "command"
            or any(name != "file" for name in names[1:])
            or len(names) > MAIL_MAX_FILES + 1
        ):
            raise EditorFailure(422, "invalid_multipart")
        raw = form["command"]
        if isinstance(raw, UploadFile):
            raw = (await raw.read(_COMMAND_LIMIT + 1)).decode("utf-8")
        if len(raw.encode()) > _COMMAND_LIMIT:
            raise EditorFailure(413, "too_large")
        command = EditCommand.model_validate_json(raw)
        files: list[tuple[MailFile, bytes]] = []
        total = 0
        for index, part in enumerate(form.getlist("file")):
            if not isinstance(part, UploadFile):
                raise EditorFailure(422, "invalid_file", upload=index)
            body = await part.read(MAIL_MAX_BYTES - total + 1)
            total += len(body)
            if total > MAIL_MAX_BYTES:
                raise EditorFailure(413, "too_large", upload=index)
            try:
                item = MailFile(
                    filename=part.filename or "",
                    media_type=canonical_media_type(part.content_type),
                    size_bytes=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                )
            except ValidationError:
                raise EditorFailure(422, "invalid_file", upload=index) from None
            files.append((item, body))
        return command, tuple(files)
    except (ValidationError, UnicodeError):
        raise EditorFailure(422, "invalid_command") from None
    finally:
        await form.close()


def build_mail_editor_router(
    editor: MailEditor, resolve: Callable[[UUID, UUID], Awaitable[EditorTarget | None]]
) -> APIRouter:
    router = APIRouter(prefix="/api/mail/{message_id}/draft/{create_action_id}")

    async def target(message_id: UUID, create_action_id: UUID) -> EditorTarget:
        value = await resolve(message_id, create_action_id)
        if value is None:
            raise EditorFailure(404, "unknown_draft")
        return value

    def failure(exc: EditorFailure | MailError) -> JSONResponse:
        error = mail_failure(exc) if isinstance(exc, MailError) else exc
        return JSONResponse(error.body, status_code=error.status)

    async def get(message_id: UUID, create_action_id: UUID) -> Response:
        try:
            body = await editor.current(await target(message_id, create_action_id))
            status = (
                202
                if body["state"] in ("entered", "send_unknown", "save_unknown")
                else 200
            )
            return JSONResponse(body, status_code=status)
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    async def file(
        message_id: UUID, create_action_id: UUID, slot: int, version: str
    ) -> Response:
        try:
            item, body = await editor.file(
                await target(message_id, create_action_id), version, slot
            )
            media = media_type(body[:16])
            return Response(
                body,
                media_type=media,
                headers=download_headers(item.filename, media, len(body)),
            )
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    async def put(
        message_id: UUID, create_action_id: UUID, identifier: UUID, request: Request
    ) -> Response:
        try:
            owned = await target(message_id, create_action_id)
            command, files = await _command(request)
            status, body = await editor.submit(owned, identifier, command, files)
            return JSONResponse(body, status_code=status)
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    async def lookup(
        message_id: UUID, create_action_id: UUID, identifier: UUID
    ) -> Response:
        try:
            status, body = await editor.status(
                await target(message_id, create_action_id), identifier
            )
            return JSONResponse(body, status_code=status)
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    async def resolve_save(
        message_id: UUID, create_action_id: UUID, request: Request
    ) -> Response:
        try:
            owned = await target(message_id, create_action_id)
            body = bytearray()
            async for piece in request.stream():
                if len(body) + len(piece) > 2048:
                    raise EditorFailure(413, "too_large")
                body.extend(piece)
            decision = ResolveSave.model_validate_json(body)
            return JSONResponse(await editor.resolve_save(owned, decision))
        except ValidationError:
            return JSONResponse(
                {"state": "failed", "reason": "invalid_decision"}, status_code=422
            )
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    async def send_review(
        message_id: UUID, create_action_id: UUID, review: SendReview
    ) -> Response:
        try:
            return JSONResponse(
                await editor.review_send(
                    await target(message_id, create_action_id), review
                )
            )
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    async def approve_send(
        message_id: UUID, create_action_id: UUID, approval_id: str, _choice: SendChoice
    ) -> Response:
        try:
            status, body = await editor.approve_send(
                await target(message_id, create_action_id), approval_id
            )
            return JSONResponse(body, status_code=status)
        except (EditorFailure, MailError) as exc:
            return failure(exc)

    router.add_api_route("", get, methods=["GET"])
    router.add_api_route("/files/{slot}", file, methods=["GET"])
    router.add_api_route("/operations/{identifier}", put, methods=["PUT"])
    router.add_api_route("/operations/{identifier}", lookup, methods=["GET"])
    router.add_api_route("/resolve-save", resolve_save, methods=["POST"])
    router.add_api_route("/send-approval", send_review, methods=["POST"])
    router.add_api_route("/send-approval/{approval_id}", approve_send, methods=["POST"])
    return router

"""Private, same-origin browser interface to the canonical assistant."""

from __future__ import annotations

import logging
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from llm_tools import DeclaredToolFailure
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from jarvis.attachments import AttachmentStore, WebUpload
from jarvis.db import attachment, message
from jarvis.home_pages import HOME_ORIGIN, PAGE_CSP, HomePages
from jarvis.home_reads import (
    conversation,
    eligible_draft,
    mail_revision,
    todo_results,
    visible_message,
)
from jarvis.home_uploads import attachment_response, read_submission
from jarvis.mail_editor import EditorTarget, MailEditor
from jarvis.mail_editor_http import build_mail_editor_router
from jarvis.messages import (
    IngressUnavailable,
    InvalidReference,
    StaleWorkspaceOccurrence,
    SubmissionConflict,
)
from jarvis.ownership import Database, DeploymentOwnershipDefect
from jarvis.phone import (
    Enrollment,
    InactivePhone,
    PhoneSlot,
    StalePhone,
    canonical_uuid,
)
from jarvis.work import WorkStore
from jarvis.workspace_mcp import WorkspaceApprovals

_STATIC = Path(__file__).parent / "static" / "home"
_PHONE_ROUTE = "/api/push/phone"
_WORKSPACE_APPROVALS = "/api/workspace/approvals"
_SHELL_CSP = (
    "default-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)


class Submit(Protocol):
    async def __call__(
        self,
        submission_id: UUID,
        text: str,
        ref: object,
        uploads: tuple[WebUpload, ...],
        *,
        workspace_occurrence: UUID | None = None,
    ) -> tuple[UUID, bool]: ...


class WorkspaceChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    choice: str | None = Field(max_length=256)


def create_home_app(
    *,
    database: Database,
    scope: str,
    owner_timezone: str,
    work: WorkStore,
    attachments: AttachmentStore,
    submit: Submit,
    spool: Path,
    pages: Path,
    phone: PhoneSlot,
    workspace_approvals: WorkspaceApprovals | None = None,
    mail_editor: MailEditor | None = None,
) -> FastAPI:
    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False
    )
    catalog = HomePages(pages)
    editor_epoch = mail_editor.epoch if mail_editor is not None else None

    async def private(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/api/mail/") and (
            "authorization" in request.headers
            or request.headers.get("sec-fetch-site") != "same-origin"
        ):
            response = JSONResponse({"detail": "browser session required"}, 403)
        elif (
            request.method not in {"GET", "HEAD"}
            and request.headers.get("origin") != HOME_ORIGIN
        ):
            response = JSONResponse({"detail": "invalid origin"}, status_code=400)
        else:
            try:
                response = await call_next(request)
            except (
                OSError,
                JSONDecodeError,
                OperationalError,
                DeploymentOwnershipDefect,
            ) as exc:
                logging.getLogger(__name__).warning(
                    "home request unavailable: %s", type(exc).__name__
                )
                response = JSONResponse({"detail": "unavailable"}, status_code=503)
        cache_control = "private, no-store"
        if request.url.path == _PHONE_ROUTE:
            # Compression can weaken the tag required by the next mutation.
            cache_control += ", no-transform"
        response.headers["Cache-Control"] = cache_control
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def put(submission_id: UUID, request: Request) -> JSONResponse:
        occurrence = None
        headers = request.headers.getlist("x-jarvis-workspace-occurrence")
        if headers:
            media = (
                request.headers.get("content-type", "")
                .partition(";")[0]
                .strip()
                .lower()
            )
            if len(headers) != 1 or media != "application/json":
                raise HTTPException(422, "invalid workspace refresh")
            try:
                occurrence = canonical_uuid(headers[0])
            except ValueError as exc:
                raise HTTPException(422, "invalid workspace occurrence") from exc
        body, raw_ref, uploads = await read_submission(request, submission_id, spool)
        try:
            if occurrence is None:
                identifier, created = await submit(
                    submission_id, body, raw_ref, uploads
                )
            else:
                identifier, created = await submit(
                    submission_id,
                    body,
                    raw_ref,
                    uploads,
                    workspace_occurrence=occurrence,
                )
        except StaleWorkspaceOccurrence as exc:
            raise HTTPException(410, "this check is no longer available") from exc
        except IngressUnavailable as exc:
            raise HTTPException(503, "jarvis is offline") from exc
        except SubmissionConflict as exc:
            raise HTTPException(409, "submission id was already used") from exc
        except InvalidReference as exc:
            raise HTTPException(422, "invalid reference") from exc
        return JSONResponse(
            {"id": str(identifier)}, status_code=201 if created else 200
        )

    async def submission(submission_id: UUID) -> dict[str, UUID]:
        async with database.connect() as conn:
            identifier = await conn.scalar(
                select(message.c.id).where(
                    message.c.source_conversation_id == scope,
                    message.c.role == "owner",
                    message.c.source == "web",
                    message.c.source_message_id == str(submission_id),
                )
            )
        if identifier is None:
            raise HTTPException(404)
        return {"id": identifier}

    async def approvals() -> list[dict[str, object]]:
        return [] if workspace_approvals is None else workspace_approvals.pending()

    async def choose(identifier: UUID, body: WorkspaceChoice) -> Response:
        if workspace_approvals is None:
            return Response(status_code=409)
        return Response(
            status_code=await workspace_approvals.respond(
                identifier, body.choice, scope
            )
        )

    async def history(before: str | None = None) -> dict[str, Any]:
        async with database.connect() as conn:
            try:
                return await conversation(
                    conn, scope, before, editor_epoch=editor_epoch
                )
            except ValueError as exc:
                raise HTTPException(422, "invalid cursor") from exc

    async def one_message(identifier: UUID) -> dict[str, Any]:
        async with database.connect() as conn:
            row = await visible_message(
                conn, scope, identifier, editor_epoch=editor_epoch
            )
        if row is None:
            raise HTTPException(404)
        return row

    async def revision(message_id: UUID, action_id: UUID) -> dict[str, Any]:
        async with database.connect() as conn:
            row = await mail_revision(
                conn, scope, message_id, action_id, editor_epoch=editor_epoch
            )
        if row is None:
            raise HTTPException(404)
        return row

    if mail_editor is not None:

        async def resolve_draft(
            message_id: UUID, create_action_id: UUID
        ) -> EditorTarget | None:
            async with database.connect() as conn:
                draft = await eligible_draft(conn, scope, message_id, create_action_id)
            if draft is None:
                return None
            return EditorTarget(
                account=draft.account,
                google_sub=draft.google_sub,
                draft_id=draft.draft_id,
                draft_message_id=draft.draft_message_id,
                draft_raw_digest=draft.draft_raw_digest,
                thread_id=draft.thread_id,
                epoch=draft.epoch,
                quote=draft.quote,
            )

        app.include_router(build_mail_editor_router(mail_editor, resolve_draft))

    async def todo_list(offset: int = 0) -> dict[str, Any]:
        try:
            return await work.web_list(offset, owner_timezone)
        except ValueError as exc:
            raise HTTPException(422, "invalid offset") from exc

    async def todo(identifier: UUID) -> dict[str, Any]:
        try:
            result = await work.get(identifier)
        except DeclaredToolFailure as exc:
            raise HTTPException(404) from exc
        return {**result.model_dump(mode="json"), "timezone": owner_timezone}

    async def results(identifier: UUID, before: str | None = None) -> dict[str, Any]:
        async with database.connect() as conn:
            try:
                page = await todo_results(conn, scope, identifier, before)
            except ValueError as exc:
                raise HTTPException(422, "invalid cursor") from exc
        if page is None:
            raise HTTPException(404)
        return page

    async def get_phone() -> JSONResponse:
        state = await phone.read()
        return JSONResponse(state.public(), headers={"ETag": state.etag})

    async def change_phone(request: Request) -> JSONResponse:
        tags = request.headers.getlist("If-Match")
        if not tags:
            raise HTTPException(428, "phone generation required")
        tag = tags[0]
        try:
            if len(tags) != 1 or len(tag) != 38 or tag[0] != '"' or tag[-1] != '"':
                raise ValueError()
            generation = canonical_uuid(tag[1:-1])
        except ValueError:
            raise HTTPException(422, "invalid phone generation") from None

        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 25 * 1024 or (
                request.method == "DELETE" and chunk
            ):
                raise HTTPException(422, "invalid enrollment body")
            body.extend(chunk)
        try:
            enrollment = (
                Enrollment.model_validate_json(body)
                if request.method == "PUT"
                else None
            )
        except ValidationError:
            raise HTTPException(422, "invalid enrollment") from None

        try:
            state = await phone.change(generation, enrollment)
        except StalePhone:
            raise HTTPException(412, "phone generation changed") from None
        except InactivePhone:
            raise HTTPException(409, "this phone is not active") from None
        return JSONResponse(state.public(), headers={"ETag": state.etag})

    async def file(identifier: UUID, request: Request) -> Response:
        async with database.connect() as conn:
            in_scope = await conn.scalar(
                select(attachment.c.id)
                .join(message, message.c.id == attachment.c.origin_message_id)
                .where(
                    attachment.c.id == identifier,
                    message.c.source_conversation_id == scope,
                )
            )
        if in_scope is None:
            raise HTTPException(404)
        return await attachment_response(
            attachments, identifier, head=request.method == "HEAD"
        )

    async def home() -> dict[str, dict[str, str] | None]:
        return {"view": await run_in_threadpool(catalog.home)}

    async def view(slug: str, rev: str | None = None) -> dict[str, str]:
        ref = await run_in_threadpool(catalog.view, slug, rev)
        if ref is None:
            raise HTTPException(404)
        return ref

    async def content(slug: str, rev: str) -> Response:
        body = await run_in_threadpool(catalog.content, slug, rev)
        if body is None:
            raise HTTPException(404)
        return Response(
            body, media_type="text/html", headers={"Content-Security-Policy": PAGE_CSP}
        )

    app.mount("/static/home", StaticFiles(directory=_STATIC), name="home-assets")

    async def shell() -> FileResponse:
        return FileResponse(
            _STATIC / "index.html", headers={"Content-Security-Policy": _SHELL_CSP}
        )

    app.middleware("http")(private)
    app.add_api_route("/api/messages/{submission_id}", put, methods=["PUT"])
    app.add_api_route("/api/submissions/{submission_id}", submission, methods=["GET"])
    app.add_api_route("/api/messages", history, methods=["GET"])
    app.add_api_route("/api/messages/{identifier}", one_message, methods=["GET"])
    app.add_api_route(
        "/api/mail/{message_id}/revision/{action_id}", revision, methods=["GET"]
    )
    app.add_api_route("/api/todos", todo_list, methods=["GET"])
    app.add_api_route("/api/todos/{identifier}", todo, methods=["GET"])
    app.add_api_route("/api/todos/{identifier}/results", results, methods=["GET"])
    app.add_api_route("/api/files/{identifier}", file, methods=["GET", "HEAD"])
    app.add_api_route("/api/home", home, methods=["GET"])
    app.add_api_route(_PHONE_ROUTE, get_phone, methods=["GET"])
    app.add_api_route(_PHONE_ROUTE, change_phone, methods=["PUT", "DELETE"])
    app.add_api_route(_WORKSPACE_APPROVALS, approvals, methods=["GET"])
    app.add_api_route(_WORKSPACE_APPROVALS + "/{identifier}", choose, methods=["POST"])
    app.add_api_route("/api/views/{slug}", view, methods=["GET"])
    app.add_api_route("/api/views/{slug}/{rev}", view, methods=["GET"])
    app.add_api_route("/content/{slug}/{rev}", content, methods=["GET"])
    app.add_api_route("/mail/{message_id}/revision/{action_id}", shell, methods=["GET"])
    app.add_api_route(
        "/mail/{message_id}/draft/{create_action_id}", shell, methods=["GET"]
    )
    app.add_api_route("/", shell, methods=["GET"])
    app.add_api_route("/t/{identifier}", shell, methods=["GET"])
    app.add_api_route("/m/{identifier}", shell, methods=["GET"])
    app.add_api_route("/f/{identifier}", shell, methods=["GET"])
    app.add_api_route("/overview", shell, methods=["GET"])
    app.add_api_route("/v/{slug}", shell, methods=["GET"])
    app.add_api_route("/v/{slug}/{rev}", shell, methods=["GET"])
    return app

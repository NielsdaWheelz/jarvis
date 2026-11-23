"""Private, same-origin browser interface to the canonical assistant."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from llm_tools import DeclaredToolFailure
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from jarvis.attachments import AttachmentStore, WebUpload
from jarvis.db import attachment, message
from jarvis.home_pages import HOME_ORIGIN, PAGE_CSP, HomePages
from jarvis.home_reads import conversation, visible_message
from jarvis.home_uploads import attachment_response, read_submission
from jarvis.messages import IngressUnavailable, InvalidReference, SubmissionConflict
from jarvis.ownership import Database, DeploymentOwnershipDefect
from jarvis.work import WorkStore

_STATIC = Path(__file__).parent / "static" / "home"
_SHELL_CSP = (
    "default-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)

type Submit = Callable[
    [UUID, str, object | None, tuple[WebUpload, ...]],
    Awaitable[tuple[UUID, bool]],
]


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
) -> FastAPI:
    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False
    )
    catalog = HomePages(pages)

    async def private(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
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
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def put(submission_id: UUID, request: Request) -> JSONResponse:
        body, raw_ref, uploads = await read_submission(request, submission_id, spool)
        try:
            identifier, created = await submit(submission_id, body, raw_ref, uploads)
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

    async def history(before: str | None = None) -> dict[str, Any]:
        async with database.connect() as conn:
            try:
                return await conversation(conn, scope, before)
            except ValueError as exc:
                raise HTTPException(422, "invalid cursor") from exc

    async def one_message(identifier: UUID) -> dict[str, Any]:
        async with database.connect() as conn:
            row = await visible_message(conn, scope, identifier)
        if row is None:
            raise HTTPException(404)
        return row

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
    app.add_api_route("/api/todos", todo_list, methods=["GET"])
    app.add_api_route("/api/todos/{identifier}", todo, methods=["GET"])
    app.add_api_route("/api/files/{identifier}", file, methods=["GET", "HEAD"])
    app.add_api_route("/api/home", home, methods=["GET"])
    app.add_api_route("/api/views/{slug}", view, methods=["GET"])
    app.add_api_route("/api/views/{slug}/{rev}", view, methods=["GET"])
    app.add_api_route("/content/{slug}/{rev}", content, methods=["GET"])
    app.add_api_route("/", shell, methods=["GET"])
    app.add_api_route("/t/{identifier}", shell, methods=["GET"])
    app.add_api_route("/m/{identifier}", shell, methods=["GET"])
    app.add_api_route("/f/{identifier}", shell, methods=["GET"])
    app.add_api_route("/overview", shell, methods=["GET"])
    app.add_api_route("/v/{slug}", shell, methods=["GET"])
    app.add_api_route("/v/{slug}/{rev}", shell, methods=["GET"])
    return app

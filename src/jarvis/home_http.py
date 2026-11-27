"""Private, same-origin browser interface to the canonical assistant."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from hashlib import sha256
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from llm_tools import DeclaredToolFailure, canonical_json_bytes
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from jarvis.attachments import AttachmentStore, SpoolFull, WebUpload
from jarvis.citation_sources import MAX_SOURCES, read_source, source_is_available
from jarvis.connectors import GoogleCredentialDefect
from jarvis.db import message
from jarvis.home_drive import DriveReader, mount_drive
from jarvis.home_pages import (
    HOME_ORIGIN,
    PAGE_CSP,
    REV_PATTERN,
    SLUG_PATTERN,
    HomePages,
)
from jarvis.home_reads import (
    artifact_discussion,
    clear_shown,
    conversation,
    eligible_draft,
    mail_revision,
    record_shown,
    shown_totals,
    source_slot,
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
    CanonicalUUID,
    Enrollment,
    InactivePhone,
    PhoneSlot,
    StalePhone,
    canonical_uuid,
)
from jarvis.presence import Presence
from jarvis.work import WorkStore
from jarvis.workspace_enrollment import WorkspaceEnrollment
from jarvis.workspace_mcp import WorkspaceApprovals

_STATIC = Path(__file__).parent / "static" / "home"
_PHONE_ROUTE = "/api/push/phone"
_WORKSPACE_APPROVALS = "/api/workspace/approvals"
_SHELL_CSP = (
    "default-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'; img-src 'self' blob:"
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


class _ShownReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    ids: list[CanonicalUUID] = Field(min_length=1, max_length=200)


class _ShownClear(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    through: CanonicalUUID


def create_home_app(
    *,
    database: Database,
    scope: str,
    owner_timezone: str,
    work: WorkStore,
    attachments: AttachmentStore,
    submit: Submit,
    pages: Path,
    phone: PhoneSlot,
    presence: Presence,
    workspace_approvals: WorkspaceApprovals | None = None,
    drive_reader: DriveReader | None = None,
    mail_editor: MailEditor | None = None,
    source_enrollment: Callable[[], WorkspaceEnrollment | None] | None = None,
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
        elif (
            request.url.path
            in {
                "/api/messages",
                "/api/home",
                "/api/artifacts",
                "/api/shown",
                "/api/shown/clear",
            }
            or request.url.path.startswith(
                ("/api/messages/", "/api/submissions/", "/api/artifacts/")
            )
        ) and request.headers.getlist("x-jarvis-viewer-contract") != ["shown-v1"]:
            response = JSONResponse(
                {"detail": "reload the jarvis viewer or update the android app"},
                status_code=426,
            )
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
        if response.status_code in (200, 206, 304) and re.fullmatch(
            r"/static/home/fonts/[^/]+-[a-f0-9]{8}\.woff2", request.url.path
        ):
            cache_control = "private, max-age=31536000, immutable"
        elif request.url.path == _PHONE_ROUTE or "no-transform" in response.headers.get(
            "Cache-Control", ""
        ):
            # Preserve the phone tag and the exact byte count on private streams.
            cache_control += ", no-transform"
        response.headers["Cache-Control"] = cache_control
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def put(
        submission_id: UUID, request: Request, response: Response
    ) -> dict[str, Any]:
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
        try:
            async with read_submission(request, submission_id) as (
                body,
                raw_ref,
                uploads,
            ):
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
        except SpoolFull as exc:
            raise HTTPException(413, "unfiled upload space is full") from exc
        except SubmissionConflict as exc:
            raise HTTPException(409, "submission id was already used") from exc
        except InvalidReference as exc:
            raise HTTPException(422, "invalid reference") from exc
        response.status_code = 201 if created else 200
        async with database.connect() as conn:
            return await receipt(conn, identifier)

    async def submission(submission_id: UUID) -> dict[str, Any]:
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
            return await receipt(conn, identifier)

    async def approvals() -> list[dict[str, object]]:
        return [] if workspace_approvals is None else workspace_approvals.pending()

    async def read_presence(request: Request) -> Response:
        if request.query_params:
            raise HTTPException(422, "presence takes no query")
        as_of, state = await presence.read(workspace_approvals)
        tag = '"' + sha256(canonical_json_bytes(state)).hexdigest() + '"'
        headers = {"ETag": tag}
        if any(
            value.strip().removeprefix("W/") in {tag, "*"}
            for field in request.headers.getlist("If-None-Match")
            for value in field.split(",")
        ):
            return Response(status_code=304, headers=headers)
        return JSONResponse({"as_of": as_of, **state}, headers=headers)

    async def choose(identifier: UUID, body: WorkspaceChoice) -> Response:
        if workspace_approvals is None:
            return Response(status_code=409)
        return Response(
            status_code=await workspace_approvals.respond(
                identifier, body.choice, scope
            )
        )

    async def source_grant() -> WorkspaceEnrollment | None:
        if source_enrollment is None:
            return None
        try:
            return await run_in_threadpool(source_enrollment)
        except (OSError, GoogleCredentialDefect):
            logging.getLogger(__name__).debug("source enrollment unavailable")
            return None

    async def history(before: str | None = None) -> dict[str, Any]:
        async with database.connect() as conn:
            await conn.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            try:
                return await conversation(
                    conn,
                    scope,
                    before,
                    editor_epoch=editor_epoch,
                    source_grant=await source_grant(),
                )
            except ValueError as exc:
                raise HTTPException(422, "invalid cursor") from exc

    async def message_row(
        conn: AsyncConnection, identifier: UUID
    ) -> dict[str, Any] | None:
        return await visible_message(
            conn,
            scope,
            identifier,
            editor_epoch=editor_epoch,
            source_grant=await source_grant(),
        )

    async def receipt(conn: AsyncConnection, identifier: UUID) -> dict[str, Any]:
        row = await message_row(conn, identifier)
        if row is None:
            raise HTTPException(503, "message unavailable")
        return {"id": identifier, "message": row}

    async def shown() -> dict[str, int]:
        async with database.connect() as conn:
            return await shown_totals(conn, scope)

    async def report_shown(body: _ShownReport) -> Response:
        async with database.begin() as conn:
            await record_shown(conn, scope, body.ids)
        return Response(status_code=204)

    async def clear(body: _ShownClear) -> Response:
        async with database.begin() as conn:
            if not await clear_shown(conn, scope, body.through):
                raise HTTPException(422, "clear requires a tracked message")
        return Response(status_code=204)

    async def one_message(identifier: UUID) -> dict[str, Any]:
        async with database.connect() as conn:
            row = await message_row(conn, identifier)
        if row is None:
            raise HTTPException(404)
        return row

    async def evidence(identifier: str, slot: str) -> dict[str, Any]:
        try:
            reply = canonical_uuid(identifier)
        except ValueError as exc:
            raise HTTPException(404) from exc
        if not re.fullmatch(r"[1-9][0-9]?", slot) or int(slot) > MAX_SOURCES:
            raise HTTPException(404)
        grant = await source_grant()
        async with database.connect() as conn:
            locator = await source_slot(conn, scope, reply, int(slot))
            if locator is None:
                raise HTTPException(404)
            if not isinstance(locator, dict):
                logging.getLogger(__name__).debug("source unavailable: invalid_locator")
                return {"state": "unavailable"}
            indexed = cast(dict[str, Any], locator)
            if not source_is_available(indexed, grant):
                reason = (
                    "grant_fenced" if indexed.get("state") == "available" else "unbound"
                )
                logging.getLogger(__name__).debug("source unavailable: %s", reason)
                return {"state": "unavailable"}
            detail = await read_source(conn, scope, indexed, grant)
        if detail["state"] != "available":
            logging.getLogger(__name__).debug("source unavailable: receipt_unavailable")
        elif not source_is_available(indexed, await source_grant()):
            logging.getLogger(__name__).debug("source unavailable: grant_changed")
            return {"state": "unavailable"}
        return detail

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

    async def todo_list(request: Request) -> dict[str, Any]:
        if request.query_params.multi_items() != [("all", "true")]:
            raise HTTPException(422, "expected only all=true")
        return await work.web_list()

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

    async def phone_registration(request: Request) -> JSONResponse:
        if request.method == "GET":
            state = await phone.read()
            return JSONResponse(state.public(), headers={"ETag": state.etag})

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
            if len(body) + len(chunk) > 25 * 1024:
                raise HTTPException(422, "invalid enrollment body")
            body.extend(chunk)
        try:
            enrollment = Enrollment.model_validate_json(body)
        except ValidationError:
            raise HTTPException(422, "invalid enrollment") from None

        try:
            state = await phone.enroll(generation, enrollment)
        except StalePhone:
            raise HTTPException(412, "phone generation changed") from None
        except InactivePhone:
            raise HTTPException(409, "this phone is not active") from None
        return JSONResponse(state.public(), headers={"ETag": state.etag})

    async def file(identifier: UUID, request: Request) -> Response:
        return await attachment_response(
            attachments, identifier, head=request.method == "HEAD"
        )

    async def home() -> dict[str, dict[str, str] | None]:
        snapshot = await run_in_threadpool(catalog.snapshot)
        return {"view": snapshot.home()}

    async def artifacts() -> dict[str, Any]:
        snapshot = await run_in_threadpool(catalog.snapshot)
        return {"items": snapshot.listing(), "timezone": owner_timezone}

    async def artifact(slug: str) -> dict[str, Any]:
        snapshot = await run_in_threadpool(catalog.snapshot)
        item = snapshot.work(slug)
        if item is None:
            raise HTTPException(404)
        return {**item, "timezone": owner_timezone}

    async def discussion(slug: str, rev: str) -> dict[str, UUID | None]:
        snapshot = await run_in_threadpool(catalog.snapshot)
        ref = snapshot.view(slug, rev)
        if ref is None:
            raise HTTPException(404)
        async with database.connect() as conn:
            return {"message_id": await artifact_discussion(conn, scope, ref)}

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

    async def artifact_shell(slug: str, request: Request) -> FileResponse:
        rev = request.path_params.get("rev")
        if (
            len(slug) > 64
            or not re.fullmatch(SLUG_PATTERN, slug)
            or (rev is not None and not re.fullmatch(REV_PATTERN, rev))
        ):
            raise HTTPException(404)
        return await shell()

    app.middleware("http")(private)
    app.add_api_route("/api/messages/{submission_id}", put, methods=["PUT"])
    app.add_api_route("/api/submissions/{submission_id}", submission, methods=["GET"])
    app.add_api_route("/api/messages", history, methods=["GET"])
    app.add_api_route("/api/messages/{identifier}", one_message, methods=["GET"])
    app.add_api_route("/api/shown", shown, methods=["GET"])
    app.add_api_route("/api/shown", report_shown, methods=["POST"], status_code=204)
    app.add_api_route("/api/shown/clear", clear, methods=["POST"], status_code=204)
    app.add_api_route("/api/presence", read_presence, methods=["GET"])
    app.add_api_route(
        "/api/messages/{identifier}/sources/{slot}", evidence, methods=["GET"]
    )
    app.add_api_route(
        "/api/mail/{message_id}/revision/{action_id}", revision, methods=["GET"]
    )
    app.add_api_route("/api/todos", todo_list, methods=["GET"])
    app.add_api_route("/api/todos/{identifier}", todo, methods=["GET"])
    app.add_api_route("/api/todos/{identifier}/results", results, methods=["GET"])
    app.add_api_route(
        "/api/drive/origin/{identifier}/content", file, methods=["GET", "HEAD"]
    )
    mount_drive(app, drive_reader, attachments.pending, attachments.inspect)
    app.add_api_route("/api/home", home, methods=["GET"])
    app.add_api_route(_PHONE_ROUTE, phone_registration, methods=["GET", "PUT"])
    app.add_api_route(_WORKSPACE_APPROVALS, approvals, methods=["GET"])
    app.add_api_route(_WORKSPACE_APPROVALS + "/{identifier}", choose, methods=["POST"])
    app.add_api_route("/api/artifacts", artifacts, methods=["GET"])
    app.add_api_route("/api/artifacts/{slug}", artifact, methods=["GET"])
    app.add_api_route(
        "/api/artifacts/{slug}/{rev}/discussion", discussion, methods=["GET"]
    )
    app.add_api_route("/content/{slug}/{rev}", content, methods=["GET"])
    app.add_api_route("/mail/{message_id}/revision/{action_id}", shell, methods=["GET"])
    app.add_api_route(
        "/mail/{message_id}/draft/{create_action_id}", shell, methods=["GET"]
    )
    app.add_api_route("/", shell, methods=["GET"])
    app.add_api_route("/t/{identifier}", shell, methods=["GET"])
    app.add_api_route("/m/{identifier}", shell, methods=["GET"])
    app.add_api_route("/m/{identifier}/source/{slot}", shell, methods=["GET"])
    app.add_api_route(
        "/m/{identifier}/table/{ordinal}/{digest}", shell, methods=["GET"]
    )
    app.add_api_route("/f/{identifier}", shell, methods=["GET"])
    app.add_api_route("/files", shell, methods=["GET"])
    app.add_api_route("/files/{subject}/{identifier}", shell, methods=["GET"])
    app.add_api_route("/todos", shell, methods=["GET"])
    app.add_api_route("/artifacts", shell, methods=["GET"])
    app.add_api_route("/artifacts/{slug}", artifact_shell, methods=["GET"])
    app.add_api_route("/artifacts/{slug}/{rev}", artifact_shell, methods=["GET"])
    return app

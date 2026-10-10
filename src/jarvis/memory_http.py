"""Private authenticated capture and official streamable-HTTP MCP adapters."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from llm_tools import canonical_json_bytes
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from universal_memory import MemoryError, NexusSubmission, Submission
from universal_memory.archive import conversation_receipt
from universal_memory.policy import BATCH_EVENTS, BODY_BYTES, NOTICE
from universal_memory.schema import memory_lane, source_conversation
from universal_memory.tools import (
    MEMORY_READ_SPECS,
    SAVE_NOTE_GUIDANCE,
    MemoryToolFailure,
    SaveNoteInput,
)
from universal_memory.types import (
    DateInput,
    Lane,
    LaneReceipt,
    OpenInput,
    SearchInput,
    ViewInput,
    ZoomInput,
)

from jarvis.memory_capture import (
    INGEST_REQUEST,
    SYNC_REQUEST,
    Activate,
    CaptureError,
    CaptureLane,
    CaptureLanes,
    CaptureRequest,
    Events,
    SyncResult,
)
from jarvis.memory_config import MemoryClient, MemoryConfig, NexusClient
from jarvis.memory_service import MemoryService
from jarvis.ownership import DeploymentOwnershipDefect

MCP_PROTOCOL_REVISION = "2025-11-25"
_LOG = logging.getLogger(__name__)


class ExternalSaveInput(SaveNoteInput):
    submission_id: UUID
    native_conversation_id: str | None = None


def _http_error(error: MemoryError) -> JSONResponse:
    status = {
        "unauthorized": 401,
        "forbidden": 403,
        "not_found": 404,
        "rate_limited": 429,
        "unavailable": 503,
        "stale_checkpoint": 409,
        "source_conflict": 409,
        "submission_conflict": 409,
        "stale_view": 409,
        "event_too_large": 413,
    }.get(error.code, 422)
    return JSONResponse({"error": {"code": error.code}}, status_code=status)


def _validation_failure(error: ValidationError) -> MemoryError:
    for detail in error.errors(include_input=False):
        cause = detail.get("ctx", {}).get("error")
        if isinstance(cause, MemoryError) and cause.code in {
            "event_too_large",
            "unsupported",
        }:
            return cause
    return MemoryError("invalid_input")


class _MemoryBoundary:
    def __init__(self, app: ASGIApp, config: MemoryConfig) -> None:
        self.app, self.config = app, config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        request_id = str(uuid4())
        status = 500

        async def identified(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            authorization = request.headers.get("authorization", "")
            if not authorization.startswith("Bearer "):
                raise MemoryError("unauthorized")
            bearer = authorization.removeprefix("Bearer ")
            if request.url.path.startswith("/v1/memory/"):
                scope["memory_machine"] = self.config.authenticate_capture(bearer)
            elif request.url.path in ("/v1/mcp", "/v1/mcp/"):
                scope["memory_client"] = self.config.authenticate_client(bearer)
            else:
                raise MemoryError("not_found")
            origin = request.headers.get("origin")
            if origin is not None and origin not in self.config.origins:
                raise MemoryError("forbidden")
            body = bytearray()
            async for part in request.stream():
                if len(body) + len(part) > BODY_BYTES:
                    raise MemoryError("event_too_large")
                body.extend(part)
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, identified)
        except MemoryError as error:
            await _http_error(error)(scope, receive, identified)
        finally:
            _LOG.info("memory request %s %s %s", request_id, request.method, status)


def create_memory_app(memory: MemoryService, config: MemoryConfig) -> FastAPI:
    tools = [
        Tool(
            name=str(spec.id).replace(".", "_"),
            description=spec.summary + "\n" + spec.documentation.text,
            input_schema=spec.input_type.model_json_schema(),
        )
        for spec in MEMORY_READ_SPECS
    ]
    tools.append(
        Tool(
            name="memory_save_note",
            description=SAVE_NOTE_GUIDANCE + " " + NOTICE,
            input_schema=ExternalSaveInput.model_json_schema(),
        )
    )

    async def list_tools(
        context: ServerRequestContext[dict[str, object], Request[dict[str, object]]],
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        del context
        if params is not None and params.cursor is not None:
            raise MCPError(INVALID_PARAMS, "invalid_input")
        return ListToolsResult(tools=tools)

    async def call_tool(
        context: ServerRequestContext[dict[str, object], Request[dict[str, object]]],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        try:
            if context.request is None:
                raise MemoryError("unauthorized")
            client = cast(MemoryClient, context.request.scope["memory_client"])
            arguments = canonical_json_bytes(params.arguments or {})
            if params.name == "memory_save_note":
                if not client.admit or not client.connect:
                    raise MemoryError("forbidden")
                value = ExternalSaveInput.model_validate_json(arguments)
                if isinstance(client, NexusClient):
                    submission = NexusSubmission(
                        kind="nexus",
                        client=client.client,
                        owner_user_id=client.owner_user_id,
                        submission_id=value.submission_id,
                        native_conversation_id=value.native_conversation_id,
                    )
                else:
                    submission = Submission(
                        kind="native",
                        machine=client.machine,
                        account=client.account,
                        provider=client.provider,
                        submission_id=value.submission_id,
                        native_conversation_id=value.native_conversation_id,
                    )
                result = await memory.save_note(
                    value.text,
                    submission,
                )
            else:
                spec = next(
                    (
                        s
                        for s in MEMORY_READ_SPECS
                        if str(s.id).replace(".", "_") == params.name
                    ),
                    None,
                )
                if spec is None or len(arguments) > spec.limits.max_input_bytes:
                    raise MemoryError("invalid_input")
                async with asyncio.timeout(spec.limits.deadline_seconds):
                    match params.name:
                        case "memory_view":
                            value = ViewInput.model_validate_json(arguments)
                            result = await memory.library.view(value.cursor)
                        case "memory_zoom":
                            value = ZoomInput.model_validate_json(arguments)
                            result = await memory.library.zoom(value.start, value.count)
                        case "memory_date":
                            value = DateInput.model_validate_json(arguments)
                            result = await memory.library.date(value.position)
                        case "memory_search":
                            value = SearchInput.model_validate_json(arguments)
                            result = await memory.search(value)
                        case "memory_open":
                            value = OpenInput.model_validate_json(arguments)
                            result = await memory.library.open(value)
                        case _:
                            raise MemoryError("invalid_input")
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=canonical_json_bytes(
                            result.model_dump(mode="json")
                        ).decode(),
                    )
                ]
            )
        except (
            MemoryError,
            ValidationError,
            TimeoutError,
            SQLAlchemyError,
            DeploymentOwnershipDefect,
        ) as error:
            code = (
                error.code
                if isinstance(error, MemoryError)
                else (
                    "invalid_input"
                    if isinstance(error, ValidationError)
                    else "unavailable"
                )
            )
            failure = MemoryToolFailure.model_validate({"code": code})
            return CallToolResult(
                is_error=True,
                content=[
                    TextContent(
                        type="text",
                        text=canonical_json_bytes(
                            failure.model_dump(mode="json")
                        ).decode(),
                    )
                ],
            )

    mcp = Server[dict[str, object]](
        "jarvis-memory",
        version="1",
        instructions=NOTICE,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        max_request_body_size=BODY_BYTES,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                *[urlsplit(origin).netloc for origin in config.origins],
                "127.0.0.1:*",
                "localhost:*",
            ],
            allowed_origins=list(config.origins),
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(_MemoryBoundary, config=config)
    app.mount("/v1/mcp", mcp_app)

    async def memory_failure(request: Request, error: Exception) -> JSONResponse:
        del request
        assert isinstance(error, MemoryError)
        return _http_error(error)

    async def unavailable(request: Request, error: Exception) -> JSONResponse:
        del request, error
        return _http_error(MemoryError("unavailable"))

    def require_capture(request: Request, value: CaptureRequest) -> None:
        if request.scope["memory_machine"] != value.lane.machine:
            raise MemoryError("forbidden")
        lane = config.require_lane(value.lane.machine, value.lane.account, admit=True)
        if lane.provider != value.lane.provider:
            raise MemoryError("forbidden")

    async def lanes(request: Request) -> JSONResponse:
        machine = request.scope["memory_machine"]
        statuses: list[CaptureLane] = []
        async with memory.database.connect() as connection:
            for configured in config.lanes:
                if (
                    configured.machine != machine
                    or not configured.admit
                    or configured.provider == "jarvis"
                ):
                    continue
                lane = Lane(
                    machine=configured.machine,
                    account=configured.account,
                    provider=configured.provider,
                )
                row = (
                    (
                        await connection.execute(
                            select(memory_lane).where(
                                memory_lane.c.machine == lane.machine,
                                memory_lane.c.account == lane.account,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                receipt = (
                    None
                    if row is None
                    else LaneReceipt(
                        lane=lane,
                        activated_at=row["activated_at"],
                        last_inventory_at=row["last_inventory_at"],
                    )
                )
                statuses.append(
                    CaptureLane(
                        lane=lane,
                        status="pending" if receipt is None else "active",
                        receipt=receipt,
                    )
                )
        return JSONResponse(CaptureLanes(lanes=tuple(statuses)).model_dump(mode="json"))

    async def sync(request: Request) -> JSONResponse:
        try:
            value = SYNC_REQUEST.validate_json(await request.body())
        except ValidationError as error:
            raise _validation_failure(error) from None
        require_capture(request, value)
        async with memory.database.begin() as connection:
            if isinstance(value, Activate):
                receipt = await memory.library.activate_lane(
                    connection, value.lane, value.conversations, value.observed_at
                )
            else:
                row = (
                    (
                        await connection.execute(
                            select(memory_lane).where(
                                memory_lane.c.machine == value.lane.machine,
                                memory_lane.c.account == value.lane.account,
                                memory_lane.c.provider == value.lane.provider,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise MemoryError("forbidden")
                receipt = LaneReceipt(
                    lane=value.lane,
                    activated_at=row["activated_at"],
                    last_inventory_at=row["last_inventory_at"],
                )
            returned = await memory.library.sync_conversations(
                connection,
                value.lane,
                value.conversations[:BATCH_EVENTS]
                if isinstance(value, Activate)
                else value.conversations,
                value.observed_at,
                value.complete if not isinstance(value, Activate) else False,
            )
            known_query = select(source_conversation).where(
                source_conversation.c.machine == value.lane.machine,
                source_conversation.c.account == value.lane.account,
            )
            if not isinstance(value, Activate) and value.page is not None:
                known_query = known_query.where(source_conversation.c.id > value.page)
            rows = (
                (
                    await connection.execute(
                        known_query.order_by(source_conversation.c.id).limit(
                            BATCH_EVENTS + 1
                        )
                    )
                )
                .mappings()
                .all()
            )
            more = len(rows) > BATCH_EVENTS
            rows = rows[:BATCH_EVENTS]
            known = {item.id: item for item in returned}
            known.update(
                {row["id"]: conversation_receipt(row, value.lane) for row in rows}
            )
        return JSONResponse(
            SyncResult(
                lane_receipt=receipt,
                conversations=tuple(known.values()),
                next_page=rows[-1]["id"] if more else None,
            ).model_dump(mode="json")
        )

    async def ingest(request: Request) -> JSONResponse:
        try:
            value = INGEST_REQUEST.validate_json(await request.body())
        except ValidationError as error:
            raise _validation_failure(error) from None
        require_capture(request, value)
        async with memory.database.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(source_conversation).where(
                            source_conversation.c.id == value.conversation_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise MemoryError("not_found")
            if (row["machine"], row["account"], row["provider"]) != (
                value.lane.machine,
                value.lane.account,
                value.lane.provider,
            ):
                raise MemoryError("forbidden")
            if isinstance(value, CaptureError):
                await memory.library.park_capture(
                    connection,
                    value.conversation_id,
                    value.expected_checkpoint,
                    value.error,
                )
                response = {"parked": value.error}
            else:
                assert isinstance(value, Events)
                receipt = await memory.library.append_events(
                    connection,
                    value.conversation_id,
                    value.expected_checkpoint,
                    value.checkpoint_native_digest,
                    value.events,
                    value.caught_up,
                    value.observed_at,
                )
                response = receipt.model_dump(mode="json")
        return JSONResponse(response)

    app.add_exception_handler(MemoryError, memory_failure)
    app.add_exception_handler(SQLAlchemyError, unavailable)
    app.add_exception_handler(DeploymentOwnershipDefect, unavailable)
    app.add_api_route("/v1/memory/lanes", lanes, methods=["GET"])
    app.add_api_route("/v1/memory/sync", sync, methods=["POST"])
    app.add_api_route("/v1/memory/ingest", ingest, methods=["POST"])
    return app

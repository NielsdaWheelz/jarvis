"""Owner-scoped nexus exports through the existing private capture boundary."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI, Request
from pydantic import ValidationError
from starlette.responses import JSONResponse
from universal_memory import MemoryError
from universal_memory.nexus import NexusActivate, NexusIngest

from jarvis.memory_config import NexusClient
from jarvis.memory_service import MemoryService


def add_nexus_routes(app: FastAPI, memory: MemoryService) -> None:
    async def state(request: Request) -> JSONResponse:
        client = cast(NexusClient, request.scope["memory_nexus_capture"])
        if await request.body():
            raise MemoryError("invalid_input")
        async with memory.database.connect() as connection:
            result = await memory.library.nexus_capture_state(
                connection, client.owner_user_id
            )
        return JSONResponse(result.model_dump(mode="json"))

    async def activate(request: Request) -> JSONResponse:
        client = cast(NexusClient, request.scope["memory_nexus_capture"])
        try:
            value = NexusActivate.model_validate_json(await request.body())
        except ValidationError:
            raise MemoryError("invalid_input") from None
        if value.owner_user_id != client.owner_user_id:
            raise MemoryError("forbidden")
        async with memory.database.begin() as connection:
            result = await memory.library.register_nexus_source(connection, value)
        return JSONResponse(result.model_dump(mode="json"))

    async def ingest(request: Request) -> JSONResponse:
        client = cast(NexusClient, request.scope["memory_nexus_capture"])
        try:
            value = NexusIngest.model_validate_json(await request.body())
        except ValidationError:
            raise MemoryError("invalid_input") from None
        if value.payload.owner_user_id != client.owner_user_id:
            raise MemoryError("forbidden")
        async with memory.database.begin() as connection:
            result = await memory.library.append_nexus_export(connection, value)
        return JSONResponse(result.model_dump(mode="json"))

    app.add_api_route("/v1/memory/nexus/state", state, methods=["GET"])
    app.add_api_route("/v1/memory/nexus/activate", activate, methods=["POST"])
    app.add_api_route("/v1/memory/nexus/ingest", ingest, methods=["POST"])

"""Private Unix-socket semantic search between the two writer processes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

import httpx
from fastapi import FastAPI, Request
from pydantic import (
    BeforeValidator,
    Field,
    TypeAdapter,
    ValidationError,
)
from starlette.responses import Response
from universal_memory import MemoryError
from universal_memory.tools import MemoryToolFailure
from universal_memory.types import Closed, SearchInput, SearchResult

if TYPE_CHECKING:
    from jarvis.memory_service import MemoryService


class MemoryRequestStopped(Exception):
    """A private requester disconnected or the index writer is stopping."""


class MemoryServiceError(MemoryError):
    def __init__(self, code: str, *, actual_attempts: int = 0) -> None:
        super().__init__(code)
        self.actual_attempts = actual_attempts


class _Search(Closed):
    input: SearchInput
    cutoff: int = Field(ge=0)


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("expected a boolean discriminator")
    return value


class _Found(Closed):
    ok: Annotated[Literal[True], BeforeValidator(_bool)]
    value: SearchResult
    actual_attempts: int = Field(ge=1, le=1)


class _Failure(Closed):
    ok: Annotated[Literal[False], BeforeValidator(_bool)]
    error: MemoryToolFailure
    actual_attempts: int = Field(ge=0, le=1)


_SEARCH_REPLY: TypeAdapter[_Found | _Failure] = TypeAdapter(_Found | _Failure)


def create_internal_app(memory: MemoryService) -> FastAPI:
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    def failure(exc: MemoryServiceError) -> _Failure:
        return _Failure(
            ok=False,
            error=MemoryToolFailure.model_validate({"code": exc.code}),
            actual_attempts=exc.actual_attempts,
        )

    async def search(request: Request) -> _Found | _Failure | Response:
        try:
            query = _Search.model_validate_json(await request.body())
        except ValidationError:
            return failure(MemoryServiceError("invalid_input"))
        try:
            result = await memory.search(
                query.input, cutoff=query.cutoff, stop=request.receive
            )
        except MemoryRequestStopped:
            return Response(status_code=499)
        except MemoryServiceError as exc:
            return failure(exc)
        return _Found(ok=True, value=result, actual_attempts=1)

    app.add_api_route("/search", search, methods=["POST"], response_model=None)
    return app


class MemoryRPC:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def _post(self, path: str, body: dict[str, object]) -> bytes:
        try:
            response = await self.http.post(path, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            # The request never reached the private socket.
            raise MemoryServiceError("unavailable") from None
        # A lost or malformed acknowledgement after transmission has unknown cost.
        # BilledOnce records any such exception before allowing another invocation.
        response.raise_for_status()
        return response.content

    async def search(self, value: SearchInput, *, cutoff: int) -> SearchResult:
        data = await self._post(
            "/search", {"input": value.model_dump(mode="json"), "cutoff": cutoff}
        )
        result = _SEARCH_REPLY.validate_json(data)
        if isinstance(result, _Failure):
            raise MemoryServiceError(
                result.error.code, actual_attempts=result.actual_attempts
            )
        return result.value

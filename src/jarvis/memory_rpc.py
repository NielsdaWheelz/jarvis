"""Private Unix-socket search and index requests between the two writer processes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal, Self

import httpx
from fastapi import FastAPI, Request
from pydantic import (
    BeforeValidator,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from starlette.responses import Response
from universal_memory import MemoryError, RecordReference
from universal_memory.policy import EMBEDDING_DIMENSIONS
from universal_memory.tools import MemoryToolFailure
from universal_memory.types import Closed, SearchInput, SearchResult

from jarvis.embeddings import MAX_EMBEDDING_BATCH_SIZE

if TYPE_CHECKING:
    from jarvis.memory_service import MemoryService


class MemoryRequestStopped(Exception):
    """The private peer disconnected or assistant indexing was preempted."""


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


class EmbeddedRecord(Closed):
    ref: RecordReference
    vector: tuple[Annotated[float, Field(allow_inf_nan=False)], ...] = Field(
        min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS
    )


class IndexBatch(Closed):
    rows: tuple[EmbeddedRecord, ...] = Field(max_length=MAX_EMBEDDING_BATCH_SIZE)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({(row.ref.store, row.ref.id) for row in self.rows}) != len(self.rows):
            raise ValueError("duplicate index candidate")
        return self


_SEARCH_REPLY: TypeAdapter[_Found | _Failure] = TypeAdapter(_Found | _Failure)
_INDEX_REPLY: TypeAdapter[IndexBatch | _Failure] = TypeAdapter(IndexBatch | _Failure)


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

    async def index_batch(request: Request) -> IndexBatch | _Failure | Response:
        try:
            if await request.json() != {}:
                return Response(status_code=422)
        except (ValueError, UnicodeDecodeError):
            return Response(status_code=422)
        try:
            # After consuming the request body, ASGI receive waits for disconnect.
            return await memory.index_batch(stop=request.receive)
        except MemoryRequestStopped:
            return Response(status_code=499)
        except MemoryServiceError as exc:
            return failure(exc)

    app.add_api_route("/search", search, methods=["POST"], response_model=None)
    app.add_api_route(
        "/index_batch", index_batch, methods=["POST"], response_model=None
    )
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

    async def index_batch(self) -> IndexBatch:
        try:
            data = await self._post("/index_batch", {})
            batch = _INDEX_REPLY.validate_json(data)
        except (httpx.HTTPError, ValidationError):
            # Only a complete validated response supplies vectors for a commit.
            raise MemoryServiceError("unavailable") from None
        if isinstance(batch, _Failure):
            raise MemoryServiceError(
                batch.error.code, actual_attempts=batch.actual_attempts
            )
        return batch

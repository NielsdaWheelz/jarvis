"""Host-only OpenAI embedding boundary for derived memory vectors."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Final, Protocol

import httpx
from provider_runtime import (
    Credentials,
    EmbeddingCall,
    Present,
    ProviderCredential,
    ProviderRuntime,
)
from provider_runtime.errors import NonGenerationCallFailed, RuntimeDefect
from provider_runtime.retry import DEFAULT_RETRY
from pydantic import SecretStr

from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL

MAX_EMBEDDING_BATCH_SIZE: Final[int] = 32


class MemoryEmbedder(Protocol):
    async def embed(self, inputs: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class EmbeddingFailure(RuntimeError):
    """A content-free embedding failure safe for ordinary diagnostics."""


class EmbeddingBusy(RuntimeError):
    """No provider attempt entered because the shared inference lane is occupied."""


class OpenAIEmbedder:
    """Call provider-runtime with a credential unavailable to cognitive roles."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        http_client: httpx.AsyncClient,
    ) -> None:
        key = api_key.get_secret_value()
        if not key or key != key.strip():
            raise ValueError(
                "embedding credential must be non-empty without edge whitespace"
            )
        self._runtime = ProviderRuntime(
            Credentials(),
            retry=replace(DEFAULT_RETRY, max_attempts=1),
            http_client=http_client,
        )
        self._credential = ProviderCredential(provider="openai", key=key)
        self._inference = asyncio.Lock()

    async def embed(self, inputs: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Embed one finite non-empty batch in input order."""
        if isinstance(inputs, str) or not 1 <= len(inputs) <= MAX_EMBEDDING_BATCH_SIZE:
            raise ValueError(
                f"embedding batch must contain 1 to {MAX_EMBEDDING_BATCH_SIZE} inputs"
            )
        values = tuple(inputs)
        if any(not value.strip() for value in values):
            raise ValueError("embedding inputs must be non-empty text")

        if self._inference.locked():
            raise EmbeddingBusy("embedding inference is busy")
        async with self._inference:
            try:
                response = await self._runtime.embed(
                    EmbeddingCall(
                        model=EMBEDDING_MODEL,
                        inputs=values,
                        dimensions=Present(EMBEDDING_DIMENSION),
                    ),
                    credential=self._credential,
                )
            except (NonGenerationCallFailed, RuntimeDefect):
                raise EmbeddingFailure("embedding provider call failed") from None

        if len(response.embeddings) != len(values):
            raise EmbeddingFailure("embedding provider returned invalid vectors")
        if any(
            len(vector) != EMBEDDING_DIMENSION
            or not all(math.isfinite(component) for component in vector)
            or not any(component != 0.0 for component in vector)
            for vector in response.embeddings
        ):
            raise EmbeddingFailure("embedding provider returned invalid vectors")
        return response.embeddings


__all__ = [
    "MAX_EMBEDDING_BATCH_SIZE",
    "EmbeddingBusy",
    "EmbeddingFailure",
    "MemoryEmbedder",
    "OpenAIEmbedder",
]

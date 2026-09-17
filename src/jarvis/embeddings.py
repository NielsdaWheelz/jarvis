"""Host-only OpenAI embedding boundary for derived memory vectors."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

import httpx
from provider_runtime import (
    Credentials,
    EmbeddingCall,
    Present,
    ProviderCredential,
    ProviderRuntime,
)
from pydantic import SecretStr

from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL

MAX_EMBEDDING_BATCH_SIZE: Final[int] = 32


class EmbeddingFailure(RuntimeError):
    """A content-free embedding failure safe for ordinary diagnostics."""


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
        self._runtime = ProviderRuntime(Credentials(), http_client=http_client)
        self._credential = ProviderCredential(provider="openai", key=key)

    async def embed(self, inputs: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Embed one finite non-empty batch in input order."""
        if isinstance(inputs, str) or not 1 <= len(inputs) <= MAX_EMBEDDING_BATCH_SIZE:
            raise ValueError(
                f"embedding batch must contain 1 to {MAX_EMBEDDING_BATCH_SIZE} inputs"
            )
        values = tuple(inputs)
        if any(not value.strip() for value in values):
            raise ValueError("embedding inputs must be non-empty text")

        try:
            response = await self._runtime.embed(
                EmbeddingCall(
                    model=EMBEDDING_MODEL,
                    inputs=values,
                    dimensions=Present(EMBEDDING_DIMENSION),
                ),
                credential=self._credential,
            )
        except Exception:
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
    "EmbeddingFailure",
    "OpenAIEmbedder",
]

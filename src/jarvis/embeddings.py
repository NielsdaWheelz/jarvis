"""Host-only OpenAI embedding boundary for derived memory vectors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Literal, Protocol

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
from provider_runtime.types import ProviderContextTooLarge, ProviderRateLimit
from pydantic import SecretStr
from universal_memory.policy import (
    EMBEDDING_BATCH_SIZE,
    RETAINED_TEXT_WHITESPACE,
    MemoryError,
    validate_embedding,
)

from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL

type EmbeddingUse = Literal["search", "index"]
type EmbeddingFailureReason = Literal[
    "invalid_input",
    "context_overflow",
    "unclassified_provider_error",
    "invalid_vector_reply",
    "provider_rate_limited",
    "transient_exhausted",
    "credential_or_quota",
    "provider_defect",
    "database_unavailable",
]


class MemoryEmbedder(Protocol):
    def require_idle(self) -> None: ...

    async def embed(
        self, inputs: Sequence[str], *, use: EmbeddingUse
    ) -> tuple[tuple[float, ...], ...]:
        """Accept one operation or raise EmbeddingBusy before suspending."""
        ...


class EmbeddingFailure(RuntimeError):
    """A content-free embedding failure safe for ordinary diagnostics."""

    def __init__(
        self, reason: EmbeddingFailureReason, *, actual_attempts: Literal[0, 1]
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.actual_attempts = actual_attempts


class EmbeddingBusy(RuntimeError):
    """The other operation already owns the shared inference slot."""

    def __init__(self, owner: EmbeddingUse) -> None:
        super().__init__(owner)
        self.owner = owner


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
        self._active: EmbeddingUse | None = None

    def require_idle(self) -> None:
        if self._active is not None:
            raise EmbeddingBusy(self._active)

    async def embed(
        self, inputs: Sequence[str], *, use: EmbeddingUse
    ) -> tuple[tuple[float, ...], ...]:
        """Embed one finite non-empty batch in input order."""
        if (
            isinstance(inputs, str)
            or not 1 <= len(inputs) <= EMBEDDING_BATCH_SIZE
            or any(not value.strip(RETAINED_TEXT_WHITESPACE) for value in inputs)
        ):
            raise EmbeddingFailure("invalid_input", actual_attempts=0)
        # The service's one event loop serializes this check and assignment.
        self.require_idle()
        self._active = use
        try:
            response = await self._runtime.embed(
                EmbeddingCall(
                    model=EMBEDDING_MODEL,
                    inputs=tuple(inputs),
                    dimensions=Present(EMBEDDING_DIMENSION),
                ),
                credential=self._credential,
            )
        except OverflowError:
            raise EmbeddingFailure("invalid_vector_reply", actual_attempts=1) from None
        except NonGenerationCallFailed as error:
            failure = error.failure
            if isinstance(failure, ProviderContextTooLarge):
                reason = "context_overflow"
            elif isinstance(failure.cause, ProviderRateLimit):
                reason = "provider_rate_limited"
            else:
                reason = "transient_exhausted"
            raise EmbeddingFailure(reason, actual_attempts=1) from None
        except RuntimeDefect as error:
            if error.code in (
                "credential_missing",
                "credential_rejected",
                "quota_exhausted",
            ):
                raise EmbeddingFailure(
                    "credential_or_quota",
                    actual_attempts=0 if error.code == "credential_missing" else 1,
                ) from None
            if error.code == "unclassified_provider_error":
                raise EmbeddingFailure(error.code, actual_attempts=1) from None
            if error.code == "invalid_embedding_response":
                raise EmbeddingFailure(
                    "invalid_vector_reply", actual_attempts=1
                ) from None
            raise EmbeddingFailure(
                "provider_defect",
                actual_attempts=0 if error.code == "invalid_request" else 1,
            ) from None
        finally:
            self._active = None

        if len(response.embeddings) != len(inputs):
            raise EmbeddingFailure("invalid_vector_reply", actual_attempts=1)
        try:
            return tuple(
                tuple(validate_embedding(vector)) for vector in response.embeddings
            )
        except MemoryError:
            raise EmbeddingFailure("invalid_vector_reply", actual_attempts=1) from None


__all__ = [
    "EmbeddingBusy",
    "EmbeddingFailure",
    "MemoryEmbedder",
    "OpenAIEmbedder",
]

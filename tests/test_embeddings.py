from __future__ import annotations

import pytest
from provider_runtime import (
    Absent,
    EmbeddingCall,
    EmbeddingResponse,
    Present,
    ProviderCredential,
)
from pydantic import SecretStr

from jarvis.embeddings import (
    MAX_EMBEDDING_BATCH_SIZE,
    EmbeddingFailure,
    OpenAIEmbedder,
)
from jarvis.settings import EMBEDDING_DIMENSION, EMBEDDING_MODEL

_VECTOR = (1.0, *([0.0] * (EMBEDDING_DIMENSION - 1)))


class _RecordingRuntime:
    def __init__(self, response: EmbeddingResponse) -> None:
        self.response = response
        self.calls: list[tuple[EmbeddingCall, ProviderCredential]] = []

    async def embed(
        self,
        call: EmbeddingCall,
        *,
        credential: ProviderCredential,
    ) -> EmbeddingResponse:
        self.calls.append((call, credential))
        return self.response


class _FailingRuntime:
    async def embed(
        self,
        call: EmbeddingCall,
        *,
        credential: ProviderCredential,
    ) -> EmbeddingResponse:
        raise RuntimeError(f"provider exposed {call.inputs[0]} with {credential.key}")


async def test_embed_uses_exact_provider_runtime_call_and_explicit_credential() -> None:
    runtime = _RecordingRuntime(
        EmbeddingResponse(embeddings=(_VECTOR, _VECTOR), usage=Absent())
    )
    embedder = OpenAIEmbedder(
        SecretStr("synthetic-embedding-key"),
        runtime=runtime,
    )

    assert await embedder.embed(("alpha", "beta")) == (_VECTOR, _VECTOR)
    assert len(runtime.calls) == 1
    call, credential = runtime.calls[0]
    assert call == EmbeddingCall(
        model=EMBEDDING_MODEL,
        inputs=("alpha", "beta"),
        dimensions=Present(EMBEDDING_DIMENSION),
    )
    assert credential.provider == "openai"
    assert credential.key == "synthetic-embedding-key"
    assert "synthetic-embedding-key" not in repr(embedder)
    assert "synthetic-embedding-key" not in repr(credential)


@pytest.mark.parametrize(
    "inputs",
    [(), ("memory",) * (MAX_EMBEDDING_BATCH_SIZE + 1), "not-a-batch"],
)
async def test_embed_rejects_out_of_bounds_batches_without_provider_io(
    inputs: tuple[str, ...] | str,
) -> None:
    runtime = _RecordingRuntime(
        EmbeddingResponse(embeddings=(_VECTOR,), usage=Absent())
    )
    embedder = OpenAIEmbedder(SecretStr("synthetic-key"), runtime=runtime)

    with pytest.raises(ValueError, match="embedding batch must contain"):
        await embedder.embed(inputs)

    assert runtime.calls == []


@pytest.mark.parametrize("inputs", [("",), ("  ",)])
async def test_embed_rejects_empty_text_without_provider_io(
    inputs: tuple[str, ...],
) -> None:
    runtime = _RecordingRuntime(
        EmbeddingResponse(embeddings=(_VECTOR,), usage=Absent())
    )
    embedder = OpenAIEmbedder(SecretStr("synthetic-key"), runtime=runtime)

    with pytest.raises(ValueError, match="embedding inputs must be non-empty text"):
        await embedder.embed(inputs)

    assert runtime.calls == []


@pytest.mark.parametrize(
    "embeddings",
    [
        (),
        ((0.0,) * EMBEDDING_DIMENSION,),
        ((0.0,) * (EMBEDDING_DIMENSION - 1),),
        ((0.0,) * (EMBEDDING_DIMENSION - 1) + (float("nan"),),),
        ((0.0,) * (EMBEDDING_DIMENSION - 1) + (float("inf"),),),
    ],
)
async def test_embed_rejects_invalid_provider_vectors_without_input_content(
    embeddings: tuple[tuple[float, ...], ...],
) -> None:
    private_memory = "private owner memory must not enter diagnostics"
    runtime = _RecordingRuntime(
        EmbeddingResponse(embeddings=embeddings, usage=Absent())
    )
    embedder = OpenAIEmbedder(SecretStr("synthetic-key"), runtime=runtime)

    with pytest.raises(EmbeddingFailure) as exc_info:
        await embedder.embed((private_memory,))

    assert str(exc_info.value) == "embedding provider returned invalid vectors"
    assert private_memory not in repr(exc_info.value)


async def test_embed_sanitizes_provider_failure() -> None:
    private_memory = "private owner memory must not enter diagnostics"
    credential = "synthetic-embedding-key"
    embedder = OpenAIEmbedder(SecretStr(credential), runtime=_FailingRuntime())

    with pytest.raises(EmbeddingFailure) as exc_info:
        await embedder.embed((private_memory,))

    assert str(exc_info.value) == "embedding provider call failed"
    assert private_memory not in repr(exc_info.value)
    assert credential not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize("credential", ["", " synthetic-key", "synthetic-key "])
def test_embedder_rejects_invalid_credential(credential: str) -> None:
    with pytest.raises(ValueError, match="embedding credential must be non-empty"):
        OpenAIEmbedder(SecretStr(credential))


def test_production_embedder_requires_a_host_managed_http_client() -> None:
    with pytest.raises(ValueError, match="managed HTTP client"):
        OpenAIEmbedder(SecretStr("synthetic-key"))

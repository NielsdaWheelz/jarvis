from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import create_engine, memory_log, memory_summary
from jarvis.memory_retrieval import MemoryIdentity, PostgresMemoryRepository
from jarvis.settings import EMBEDDING_DIMENSION

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="JARVIS_TEST_DATABASE_URL is not configured",
    ),
]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


def _vector(first: float, second: float) -> list[float]:
    return [first, second, *([0.0] * (EMBEDDING_DIMENSION - 2))]


async def test_lexical_search_uses_stemming_and_simple_tokens_across_tables(
    engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(
                id=raw_id,
                text="The owner enjoys running beside marker ZephyrR7.",
            )
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="The itinerary was running beside marker XylophoneQ9.",
                source_memory_ids=[raw_id],
            )
        )

    repository = PostgresMemoryRepository(engine)
    stemmed = await repository.search(
        "run",
        lexical_limit=10,
        semantic_limit=0,
        query_embedding=None,
    )
    exact = await repository.search(
        "XylophoneQ9",
        lexical_limit=10,
        semantic_limit=0,
        query_embedding=None,
    )

    assert {(item.table_kind, item.id) for item in stemmed} >= {
        ("memory_log", raw_id),
        ("memory_summary", summary_id),
    }
    assert any(
        item.table_kind == "memory_summary"
        and item.id == summary_id
        and item.source_memory_ids == (raw_id,)
        and item.lexical_rank is not None
        for item in exact
    )


async def test_exact_cosine_search_finds_semantic_rows_and_excludes_null_vectors(
    engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    null_id = uuid4()
    zero_id = uuid4()
    distractor_id = uuid4()
    query_vector = [0.0, 0.0, 1.0, *([0.0] * (EMBEDDING_DIMENSION - 3))]
    summary_vector = [
        0.0,
        0.0,
        0.99,
        0.01,
        *([0.0] * (EMBEDDING_DIMENSION - 4)),
    ]
    distractor_vector = [
        0.0,
        0.0,
        0.0,
        1.0,
        *([0.0] * (EMBEDDING_DIMENSION - 4)),
    ]
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log),
            (
                {
                    "id": raw_id,
                    "text": "An archipelago crossing was discussed.",
                    "embedding": query_vector,
                },
                {
                    "id": null_id,
                    "text": "A null vector row remains lexically available.",
                    "embedding": None,
                },
                {
                    "id": distractor_id,
                    "text": "An unrelated synthetic recollection.",
                    "embedding": distractor_vector,
                },
                {
                    "id": zero_id,
                    "text": "DegenerateVectorMarker remains lexically available.",
                    "embedding": [0.0] * EMBEDDING_DIMENSION,
                },
            ),
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="A sea journey was planned.",
                source_memory_ids=[raw_id],
                embedding=summary_vector,
            )
        )

    repository = PostgresMemoryRepository(engine)
    semantic = await repository.search(
        "transport over water",
        lexical_limit=0,
        semantic_limit=2,
        query_embedding=query_vector,
    )
    lexical = await repository.search(
        "null vector",
        lexical_limit=10,
        semantic_limit=0,
        query_embedding=None,
    )
    mixed = await repository.search(
        "DegenerateVectorMarker",
        lexical_limit=10,
        semantic_limit=10,
        query_embedding=query_vector,
    )

    assert [(item.table_kind, item.id) for item in semantic] == [
        ("memory_log", raw_id),
        ("memory_summary", summary_id),
    ]
    assert all(item.semantic_distance is not None for item in semantic)
    assert ("memory_log", null_id) not in {
        (item.table_kind, item.id) for item in semantic
    }
    assert ("memory_log", null_id) in {(item.table_kind, item.id) for item in lexical}
    zero_candidate = next(item for item in mixed if item.id == zero_id)
    assert zero_candidate.lexical_rank is not None
    assert zero_candidate.semantic_distance is None


async def test_search_rejects_zero_query_embedding(engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="configured vector space"):
        await PostgresMemoryRepository(engine).search(
            "synthetic lexical query",
            lexical_limit=10,
            semantic_limit=10,
            query_embedding=[0.0] * EMBEDDING_DIMENSION,
        )


async def test_search_deduplicates_only_exact_row_identity(
    engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(
                id=raw_id,
                text="Synthetic cobalt preference.",
                embedding=_vector(1.0, 0.0),
            )
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="Synthetic cobalt preference summary.",
                source_memory_ids=[raw_id],
                embedding=_vector(1.0, 0.0),
            )
        )

    candidates = await PostgresMemoryRepository(engine).search(
        "cobalt",
        lexical_limit=10,
        semantic_limit=10,
        query_embedding=_vector(1.0, 0.0),
    )
    relevant = [
        item
        for item in candidates
        if (item.table_kind, item.id)
        in {("memory_log", raw_id), ("memory_summary", summary_id)}
    ]

    assert len(relevant) == 2
    assert all(item.lexical_rank is not None for item in relevant)
    assert all(item.semantic_distance is not None for item in relevant)


async def test_open_preserves_first_input_order_and_reports_missing(
    engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    missing_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(id=raw_id, text="Exact raw memory text.")
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="Exact summary text.",
                source_memory_ids=[raw_id],
            )
        )

    opened = await PostgresMemoryRepository(engine).open(
        (
            MemoryIdentity("memory_summary", summary_id),
            MemoryIdentity("memory_log", raw_id),
            MemoryIdentity("memory_summary", summary_id),
            MemoryIdentity("memory_log", missing_id),
        )
    )

    assert [(item.table_kind, item.id, item.text) for item in opened.rows] == [
        ("memory_summary", summary_id, "Exact summary text."),
        ("memory_log", raw_id, "Exact raw memory text."),
    ]
    assert opened.rows[0].source_memory_ids == (raw_id,)
    assert opened.rows[1].source_memory_ids == ()
    assert opened.missing == (MemoryIdentity("memory_log", missing_id),)

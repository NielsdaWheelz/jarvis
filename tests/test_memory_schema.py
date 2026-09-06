from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, insert, literal_column, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import create_engine, memory_log, memory_summary

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
MIGRATION_DATABASE_URL = os.environ.get("JARVIS_TEST_MIGRATION_DATABASE_URL")
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


@pytest_asyncio.fixture
async def migrator_engine() -> AsyncIterator[AsyncEngine]:
    if MIGRATION_DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_MIGRATION_DATABASE_URL is not configured")
    value = create_engine(MIGRATION_DATABASE_URL)
    yield value
    await value.dispose()


async def test_memory_search_expression_indexes_are_exact(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        generated_columns = (
            await connection.execute(
                text(
                    "SELECT table_name, column_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name IN ('memory_log', 'memory_summary') "
                    "AND is_generated = 'ALWAYS'"
                )
            )
        ).all()
        index_rows = (
            await connection.execute(
                text(
                    "SELECT tablename, indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND tablename IN ('memory_log', 'memory_summary')"
                )
            )
        ).all()

    assert generated_columns == []

    indexes = {(row.tablename, row.indexname): row.indexdef for row in index_rows}
    for table_name in ("memory_log", "memory_summary"):
        for representation in ("english", "simple"):
            index_name = f"ix_{table_name}_search_{representation}"
            definition = indexes[(table_name, index_name)]
            assert " USING gin " in definition
            assert f"(to_tsvector('{representation}'::regconfig, text))" in definition
    assert all("embedding" not in definition for definition in indexes.values())


async def test_both_lexical_representations_search_both_memory_tables(
    engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(
                id=raw_id,
                text="The owner enjoys running near marker ZephyrR7.",
            )
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="The owner was running near marker XylophoneQ9.",
                source_memory_ids=[raw_id],
            )
        )

    async with engine.connect() as connection:
        for table, row_id, marker in (
            (memory_log, raw_id, "ZephyrR7"),
            (memory_summary, summary_id, "XylophoneQ9"),
        ):
            english_id = await connection.scalar(
                select(table.c.id).where(
                    table.c.id == row_id,
                    func.to_tsvector(
                        literal_column("'english'::regconfig"), table.c.text
                    ).op("@@")(text("plainto_tsquery('english', 'run')")),
                )
            )
            simple_id = await connection.scalar(
                select(table.c.id).where(
                    table.c.id == row_id,
                    func.to_tsvector(
                        literal_column("'simple'::regconfig"), table.c.text
                    ).op("@@")(text("plainto_tsquery('simple', :marker)")),
                ),
                {"marker": marker},
            )
            assert english_id == row_id
            assert simple_id == row_id


async def test_runtime_role_raw_memory_privileges_are_exact(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        table_privileges = (
            await connection.execute(
                text(
                    "SELECT privilege_type FROM information_schema.table_privileges "
                    "WHERE table_schema = 'public' AND table_name = 'memory_log' "
                    "AND grantee = current_user"
                )
            )
        ).scalars()
        update_privileges = (
            await connection.execute(
                text(
                    "SELECT column_name FROM information_schema.column_privileges "
                    "WHERE table_schema = 'public' AND table_name = 'memory_log' "
                    "AND grantee = current_user AND privilege_type = 'UPDATE'"
                )
            )
        ).scalars()

    assert set(table_privileges) == {"INSERT", "SELECT"}
    assert set(update_privileges) == {"embedding"}


async def test_runtime_role_can_update_only_raw_embedding(
    engine: AsyncEngine,
    migrator_engine: AsyncEngine,
) -> None:
    memory_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(id=memory_id, text="Synthetic durable memory.")
        )
        await connection.execute(
            update(memory_log)
            .where(memory_log.c.id == memory_id)
            .values(embedding=[0.0] * 1536)
        )

    for statement, parameters in (
        (
            "UPDATE memory_log SET id = :replacement_id WHERE id = :id",
            {"id": memory_id, "replacement_id": uuid4()},
        ),
        (
            "UPDATE memory_log SET text = 'changed' WHERE id = :id",
            {"id": memory_id},
        ),
        (
            "UPDATE memory_log SET created_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": memory_id},
        ),
        ("DELETE FROM memory_log WHERE id = :id", {"id": memory_id}),
        ("TRUNCATE memory_log", {}),
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as connection:
                await connection.execute(text(statement), parameters)

    with pytest.raises(DBAPIError, match="canonical fields are immutable"):
        async with migrator_engine.begin() as connection:
            await connection.execute(
                text("UPDATE memory_log SET text = 'changed' WHERE id = :id"),
                {"id": memory_id},
            )
    with pytest.raises(DBAPIError, match="append-only"):
        async with migrator_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM memory_log WHERE id = :id"),
                {"id": memory_id},
            )
    with pytest.raises(DBAPIError, match="append-only"):
        async with migrator_engine.begin() as connection:
            await connection.execute(text("TRUNCATE memory_log"))


async def test_memory_log_triggers_are_enabled(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        triggers = (
            await connection.execute(
                text(
                    "SELECT tgname, tgenabled FROM pg_trigger "
                    "WHERE tgrelid = 'memory_log'::regclass AND NOT tgisinternal"
                )
            )
        ).all()
    assert set(triggers) == {
        ("memory_log_append_only", "O"),
        ("memory_log_no_truncate", "O"),
    }


async def test_runtime_role_summary_privileges_are_exact(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        table_privileges = set(
            (
                await connection.execute(
                    text(
                        "SELECT privilege_type "
                        "FROM information_schema.table_privileges "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'memory_summary' "
                        "AND grantee = current_user"
                    )
                )
            ).scalars()
        )
        update_privileges = set(
            (
                await connection.execute(
                    text(
                        "SELECT column_name "
                        "FROM information_schema.column_privileges "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'memory_summary' "
                        "AND grantee = current_user "
                        "AND privilege_type = 'UPDATE'"
                    )
                )
            ).scalars()
        )

    assert table_privileges == {"DELETE", "INSERT", "SELECT"}
    assert update_privileges == {"embedding"}


async def test_runtime_role_can_replace_summary_and_update_only_embedding(
    engine: AsyncEngine,
    migrator_engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(id=raw_id, text="Synthetic summary source.")
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="Synthetic replaceable summary.",
                source_memory_ids=[raw_id],
            )
        )
        await connection.execute(
            update(memory_summary)
            .where(memory_summary.c.id == summary_id)
            .values(embedding=[1.0, *([0.0] * 1535)])
        )

    for statement, parameters in (
        (
            "UPDATE memory_summary SET id = :replacement_id WHERE id = :id",
            {"id": summary_id, "replacement_id": uuid4()},
        ),
        (
            "UPDATE memory_summary SET text = 'changed' WHERE id = :id",
            {"id": summary_id},
        ),
        (
            "UPDATE memory_summary SET source_memory_ids = ARRAY[:raw_id]::uuid[] "
            "WHERE id = :id",
            {"id": summary_id, "raw_id": raw_id},
        ),
        (
            "UPDATE memory_summary SET created_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": summary_id},
        ),
        ("TRUNCATE memory_summary", {}),
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as connection:
                await connection.execute(text(statement), parameters)

    with pytest.raises(DBAPIError, match="canonical fields are immutable"):
        async with migrator_engine.begin() as connection:
            await connection.execute(
                text("UPDATE memory_summary SET text = 'changed' WHERE id = :id"),
                {"id": summary_id},
            )
    with pytest.raises(DBAPIError, match="cannot be truncated"):
        async with migrator_engine.begin() as connection:
            await connection.execute(text("TRUNCATE memory_summary"))

    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM memory_summary WHERE id = :id"),
            {"id": summary_id},
        )


async def test_summary_trigger_requires_unique_existing_raw_lineage(
    engine: AsyncEngine,
) -> None:
    raw_id = uuid4()
    summary_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(id=raw_id, text="Synthetic lineage source.")
        )
        await connection.execute(
            insert(memory_summary).values(
                id=summary_id,
                text="Synthetic valid lineage summary.",
                source_memory_ids=[raw_id],
            )
        )

    for source_memory_ids in (
        [raw_id, raw_id],
        [uuid4()],
        [summary_id],
    ):
        with pytest.raises(DBAPIError, match="unique raw IDs"):
            async with engine.begin() as connection:
                await connection.execute(
                    insert(memory_summary).values(
                        id=uuid4(),
                        text=f"Synthetic invalid lineage {uuid4()}.",
                        source_memory_ids=source_memory_ids,
                    )
                )


async def test_summary_lineage_is_canonical_and_globally_unique(
    engine: AsyncEngine,
) -> None:
    first, second = sorted((uuid4(), uuid4()))
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log),
            [
                {"id": first, "text": "Synthetic canonical lineage source one."},
                {"id": second, "text": "Synthetic canonical lineage source two."},
            ],
        )

    with pytest.raises(DBAPIError, match="unique raw IDs"):
        async with engine.begin() as connection:
            await connection.execute(
                insert(memory_summary).values(
                    id=uuid4(),
                    text="Synthetic noncanonical lineage summary.",
                    source_memory_ids=[second, first],
                )
            )

    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_summary).values(
                id=uuid4(),
                text="Synthetic canonical lineage summary.",
                source_memory_ids=[first, second],
            )
        )
    with pytest.raises(DBAPIError, match="uq_memory_summary_source_memory_ids"):
        async with engine.begin() as connection:
            await connection.execute(
                insert(memory_summary).values(
                    id=uuid4(),
                    text="Synthetic duplicate canonical lineage summary.",
                    source_memory_ids=[first, second],
                )
            )


async def test_memory_summary_triggers_are_enabled(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        triggers = (
            await connection.execute(
                text(
                    "SELECT tgname, tgenabled FROM pg_trigger "
                    "WHERE tgrelid = 'memory_summary'::regclass "
                    "AND NOT tgisinternal"
                )
            )
        ).all()
    assert set(triggers) == {
        ("memory_summary_canonical", "O"),
        ("memory_summary_no_truncate", "O"),
    }

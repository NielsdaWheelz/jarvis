from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import action, create_engine, message

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
MIGRATION_DATABASE_URL = os.environ.get("JARVIS_TEST_MIGRATION_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        DATABASE_URL is None or MIGRATION_DATABASE_URL is None,
        reason="runtime and migration test database URLs are required",
    ),
]

ACTION_COLUMNS = {
    "approval_message_id",
    "arguments",
    "attempts",
    "completed_at",
    "created_at",
    "decided_at",
    "execute_after",
    "execution_contract",
    "id",
    "origin_message_id",
    "result",
    "status",
    "tool_name",
}
LIFECYCLE_COLUMNS = {
    "approval_message_id",
    "attempts",
    "completed_at",
    "decided_at",
    "result",
    "status",
}


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert DATABASE_URL is not None
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


@pytest_asyncio.fixture
async def migrator_engine() -> AsyncIterator[AsyncEngine]:
    assert MIGRATION_DATABASE_URL is not None
    value = create_engine(MIGRATION_DATABASE_URL)
    yield value
    await value.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_actions(migrator_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with migrator_engine.begin() as connection:
        await connection.execute(delete(action))
        await connection.execute(delete(message))


async def _insert_action(engine: AsyncEngine) -> tuple[UUID, UUID, UUID]:
    action_id = uuid4()
    origin_id = uuid4()
    approval_id = uuid4()
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(message),
            (
                {
                    "id": origin_id,
                    "role": "owner",
                    "text": "Synthetic owner request.",
                    "source": "discord",
                    "source_conversation_id": str(uuid4()),
                    "source_message_id": str(uuid4()),
                    "created_at": now,
                    "processed_at": None,
                    "processing_attempts": 1,
                    "processing_parked_at": None,
                    "remembered_at": None,
                    "trace": {},
                },
                {
                    "id": approval_id,
                    "role": "host",
                    "text": "Synthetic approval placeholder.",
                    "source": "action",
                    "source_conversation_id": str(uuid4()),
                    "source_message_id": str(uuid4()),
                    "created_at": now,
                    "processed_at": now,
                    "processing_attempts": 0,
                    "processing_parked_at": None,
                    "remembered_at": None,
                    "trace": {},
                },
            ),
        )
        await connection.execute(
            insert(action).values(
                id=action_id,
                tool_name="synthetic.write",
                arguments={"value": "synthetic"},
                execution_contract={"type": "synthetic"},
                status="queued",
                attempts=0,
                execute_after=None,
                origin_message_id=origin_id,
                approval_message_id=None,
                created_at=now,
                decided_at=None,
                completed_at=None,
            )
        )
    return action_id, origin_id, approval_id


async def test_runtime_action_grants_are_exact(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        table_grants = set(
            (
                await connection.execute(
                    text(
                        "SELECT privilege_type "
                        "FROM information_schema.role_table_grants "
                        "WHERE grantee = current_user "
                        "AND table_schema = 'public' "
                        "AND table_name = 'action'"
                    )
                )
            ).scalars()
        )
        column_grants = set(
            (
                await connection.execute(
                    text(
                        "SELECT privilege_type, column_name "
                        "FROM information_schema.column_privileges "
                        "WHERE grantee = current_user "
                        "AND table_schema = 'public' "
                        "AND table_name = 'action'"
                    )
                )
            ).tuples()
        )

    assert table_grants == {"INSERT", "SELECT"}
    assert column_grants == (
        {("INSERT", column) for column in ACTION_COLUMNS}
        | {("SELECT", column) for column in ACTION_COLUMNS}
        | {("UPDATE", column) for column in LIFECYCLE_COLUMNS}
    )


async def test_runtime_can_update_only_action_lifecycle(
    engine: AsyncEngine,
) -> None:
    action_id, _origin_id, approval_id = await _insert_action(engine)
    resolved_at = datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    update(action)
                    .where(action.c.id == action_id)
                    .values(
                        status="succeeded",
                        attempts=1,
                        approval_message_id=approval_id,
                        decided_at=resolved_at,
                        completed_at=resolved_at,
                        result={"type": "synthetic_success"},
                    )
                    .returning(action)
                )
            )
            .mappings()
            .one()
        )

    assert row["status"] == "succeeded"
    assert row["attempts"] == 1
    assert row["approval_message_id"] == approval_id
    assert row["decided_at"] == resolved_at
    assert row["completed_at"] == resolved_at
    assert row["result"] == {"type": "synthetic_success"}


async def test_runtime_cannot_arbitrarily_update_delete_or_truncate(
    engine: AsyncEngine,
) -> None:
    action_id, _origin_id, _approval_id = await _insert_action(engine)

    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(
                update(action)
                .where(action.c.id == action_id)
                .values(execute_after=datetime.now(UTC))
            )
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(delete(action).where(action.c.id == action_id))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE TABLE action"))

    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                select(action.c.status).where(action.c.id == action_id)
            )
            == "queued"
        )


async def test_owner_trigger_rejects_every_action_identity_change(
    engine: AsyncEngine,
    migrator_engine: AsyncEngine,
) -> None:
    action_id, origin_id, _approval_id = await _insert_action(engine)
    replacement_origin_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=replacement_origin_id,
                role="owner",
                text="Synthetic replacement origin.",
                source="discord",
                source_conversation_id=str(uuid4()),
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
                processed_at=None,
                processing_attempts=1,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )

    statements = (
        update(action)
        .where(action.c.id == action_id)
        .values(tool_name="synthetic.changed"),
        update(action)
        .where(action.c.id == action_id)
        .values(arguments={"value": "changed"}),
        update(action)
        .where(action.c.id == action_id)
        .values(execution_contract={"type": "changed"}),
        update(action)
        .where(action.c.id == action_id)
        .values(origin_message_id=replacement_origin_id),
    )
    for statement in statements:
        with pytest.raises(DBAPIError, match="identity fields are immutable"):
            async with migrator_engine.begin() as connection:
                await connection.execute(statement)

    async with engine.connect() as connection:
        stored = (
            (await connection.execute(select(action).where(action.c.id == action_id)))
            .mappings()
            .one()
        )
    assert stored["tool_name"] == "synthetic.write"
    assert stored["arguments"] == {"value": "synthetic"}
    assert stored["execution_contract"] == {"type": "synthetic"}
    assert stored["origin_message_id"] == origin_id

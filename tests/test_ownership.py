from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import create_engine
from jarvis.ownership import (
    DEPLOYMENT_LOCK_KEY,
    DeploymentAlreadyOwned,
    DeploymentOwnershipDefect,
    deployment_ownership,
)


class _Connection:
    def __init__(self, results: list[bool]) -> None:
        self.results = results
        self.parameters: list[dict[str, object] | None] = []

    async def scalar(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> bool:
        del statement
        self.parameters.append(parameters)
        return self.results.pop(0)


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection_value = connection

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_Connection]:
        yield self.connection_value


async def test_deployment_lock_is_held_for_complete_context() -> None:
    connection = _Connection([True, True])
    engine = cast(AsyncEngine, _Engine(connection))
    async with deployment_ownership(engine):
        assert len(connection.parameters) == 1
    assert connection.parameters == [
        {"lock_key": DEPLOYMENT_LOCK_KEY},
        {"lock_key": DEPLOYMENT_LOCK_KEY},
    ]


async def test_second_instance_refuses_to_start() -> None:
    engine = cast(AsyncEngine, _Engine(_Connection([False])))
    with pytest.raises(DeploymentAlreadyOwned):
        async with deployment_ownership(engine):
            raise AssertionError("unreachable")


async def test_lock_releases_when_service_body_fails() -> None:
    connection = _Connection([True, True])
    engine = cast(AsyncEngine, _Engine(connection))
    with pytest.raises(LookupError):
        async with deployment_ownership(engine):
            raise LookupError("service failed")
    assert len(connection.parameters) == 2


async def test_failed_unlock_is_a_host_defect() -> None:
    engine = cast(AsyncEngine, _Engine(_Connection([True, False])))
    with pytest.raises(DeploymentOwnershipDefect):
        async with deployment_ownership(engine):
            pass


@pytest.mark.postgres
@pytest.mark.skipif(
    os.environ.get("JARVIS_TEST_DATABASE_URL") is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
async def test_real_postgres_refuses_second_deployment_owner() -> None:
    database_url = os.environ["JARVIS_TEST_DATABASE_URL"]
    first = create_engine(database_url)
    second = create_engine(database_url)
    try:
        async with deployment_ownership(first):
            with pytest.raises(DeploymentAlreadyOwned):
                async with deployment_ownership(second):
                    raise AssertionError("second owner entered the deployment")
        async with deployment_ownership(second):
            pass
    finally:
        await first.dispose()
        await second.dispose()

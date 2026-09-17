from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from alembic import command
from alembic.config import Config
from composition_fixture import (
    MemoryEmbedderFixture,
    MemoryRepositoryFixture,
    build_test_catalog,
    composition_settings,
)
from llm_tools import ToolCatalog
from provider_fixture import frozen_provider

from jarvis.definitions import RoleDefinitions, build_definitions
from jarvis.memory_retrieval import MemoryEmbedder, MemoryRepository


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    runtime_database_url = os.environ.get("JARVIS_TEST_DATABASE_URL")
    if runtime_database_url is None:
        yield
        return
    migration_database_url = os.environ.get("JARVIS_TEST_MIGRATION_DATABASE_URL")
    if migration_database_url is None:
        raise RuntimeError(
            "JARVIS_TEST_MIGRATION_DATABASE_URL is required with "
            "JARVIS_TEST_DATABASE_URL"
        )

    previous = os.environ.get("JARVIS_MIGRATION_DATABASE_URL")
    os.environ["JARVIS_MIGRATION_DATABASE_URL"] = migration_database_url
    try:
        config = Config("alembic.ini")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield
    finally:
        if previous is None:
            del os.environ["JARVIS_MIGRATION_DATABASE_URL"]
        else:
            os.environ["JARVIS_MIGRATION_DATABASE_URL"] = previous


@pytest.fixture
async def current_catalog(tmp_path: Path) -> AsyncIterator[ToolCatalog]:
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected external request: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(unexpected_request),
        trust_env=False,
        follow_redirects=False,
    ) as http:
        yield build_test_catalog(
            composition_settings(tmp_path),
            http,
            frozen_provider(),
            memory_repository=cast(MemoryRepository, MemoryRepositoryFixture()),
            memory_embedder=cast(MemoryEmbedder, MemoryEmbedderFixture()),
        )


@pytest.fixture
def current_definitions(current_catalog: ToolCatalog) -> RoleDefinitions:
    return build_definitions(
        catalog=current_catalog,
        provider=frozen_provider(),
        owner_timezone="UTC",
    )

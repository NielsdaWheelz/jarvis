from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config


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

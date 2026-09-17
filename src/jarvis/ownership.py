"""Exclusive deployment ownership through one PostgreSQL advisory lock."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

DEPLOYMENT_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"jarvis-deployment-v1").digest()[:8],
    byteorder="big",
    signed=True,
)


class DeploymentAlreadyOwned(RuntimeError):
    """Another Jarvis process owns this deployment."""


class DeploymentOwnershipDefect(RuntimeError):
    """The database could not establish or release deployment ownership."""


class Database(Protocol):
    def begin(self) -> AbstractAsyncContextManager[AsyncConnection]: ...
    def connect(self) -> AbstractAsyncContextManager[AsyncConnection]: ...


class _OwnedDatabase:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()
        self.active = True

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        async with self._lock:
            if (
                not self.active
                or self._connection.closed
                or self._connection.invalidated
            ):
                raise DeploymentOwnershipDefect(
                    "deployment owner connection is no longer usable"
                )
            try:
                async with self._connection.begin():
                    yield self._connection
            except DBAPIError as exc:
                if exc.connection_invalidated:
                    raise DeploymentOwnershipDefect(
                        "deployment owner connection was lost"
                    ) from exc
                raise

    def connect(self) -> AbstractAsyncContextManager[AsyncConnection]:
        return self.begin()


@asynccontextmanager
async def deployment_ownership(engine: AsyncEngine) -> AsyncIterator[Database]:
    """Hold the deployment advisory lock on one dedicated connection."""

    async with engine.connect() as connection:
        try:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": DEPLOYMENT_LOCK_KEY},
            )
        except Exception as exc:
            raise DeploymentOwnershipDefect(
                "deployment lock acquisition failed"
            ) from exc
        if acquired is not True:
            raise DeploymentAlreadyOwned("another Jarvis process owns this deployment")
        await connection.commit()
        database = _OwnedDatabase(connection)
        try:
            yield database
        finally:
            database.active = False
            if connection.closed or connection.invalidated:
                raise DeploymentOwnershipDefect("deployment owner connection was lost")
            try:
                released = await connection.scalar(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": DEPLOYMENT_LOCK_KEY},
                )
            except Exception as exc:
                raise DeploymentOwnershipDefect(
                    "deployment lock release failed"
                ) from exc
            if released is not True:
                raise DeploymentOwnershipDefect("deployment advisory lock was not held")


__all__ = [
    "DEPLOYMENT_LOCK_KEY",
    "Database",
    "DeploymentAlreadyOwned",
    "DeploymentOwnershipDefect",
    "deployment_ownership",
]

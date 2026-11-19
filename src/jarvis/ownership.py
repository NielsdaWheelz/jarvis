"""Fence each writer with session locks on its dedicated PostgreSQL connection."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from universal_memory.policy import READ_STATEMENT_SECONDS

DEPLOYMENT_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"jarvis-deployment-v1").digest()[:8],
    byteorder="big",
    signed=True,
)
MEMORY_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"jarvis-memory-v1").digest()[:8], byteorder="big", signed=True
)


class DeploymentAlreadyOwned(RuntimeError):
    """Another Jarvis process owns this deployment."""


class DeploymentOwnershipDefect(RuntimeError):
    """The database could not establish or release deployment ownership."""


class Database(Protocol):
    def begin(self) -> AbstractAsyncContextManager[AsyncConnection]: ...
    def connect(self) -> AbstractAsyncContextManager[AsyncConnection]: ...


async def lock_conversation(connection: AsyncConnection, conversation_id: str) -> None:
    await connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": "jarvis-native:" + conversation_id},
    )


def memory_is_admitted(connection: AsyncConnection) -> bool:
    """Stamp canonical publication eligibility from the owning host declaration."""
    return connection.info.get("jarvis_memory_admitted") is True


class _OwnedDatabase:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()
        self.active = True

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncConnection]:
        if not self.active or self._connection.closed or self._connection.invalidated:
            raise DeploymentOwnershipDefect("deployment owner connection is unusable")
        try:
            async with self._connection.begin():
                yield self._connection
        except DBAPIError as exc:
            if exc.connection_invalidated:
                self.active = False
                raise DeploymentOwnershipDefect(
                    "deployment owner connection was lost"
                ) from exc
            raise

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        async with self._lock, self._transaction() as connection:
            yield connection

    def connect(self) -> AbstractAsyncContextManager[AsyncConnection]:
        return self.begin()

    async def check_available(self) -> bool:
        """Bound the wait for the writer before dispatching an embedding request."""
        try:
            async with asyncio.timeout(READ_STATEMENT_SECONDS):
                await self._lock.acquire()
        except TimeoutError:
            return False
        try:
            async with self._transaction() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        finally:
            self._lock.release()

    async def wait_for_loss(self, shutdown: asyncio.Event) -> None:
        """Wake an otherwise idle listener when PostgreSQL drops its session."""
        while not shutdown.is_set():
            async with self.begin() as connection:
                await connection.execute(text("SELECT 1"))
            await asyncio.sleep(1)


def deployment_ownership(
    engine: AsyncEngine,
    *,
    lock_key: int = DEPLOYMENT_LOCK_KEY,
    memory_admitted: bool = False,
) -> AbstractAsyncContextManager[_OwnedDatabase]:
    return _ownership(engine, (lock_key,), memory_admitted)


def maintenance_ownership(
    engine: AsyncEngine, *, memory_admitted: bool = False
) -> AbstractAsyncContextManager[_OwnedDatabase]:
    return _ownership(engine, (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY), memory_admitted)


@asynccontextmanager
async def _ownership(
    engine: AsyncEngine, keys: tuple[int, ...], memory_admitted: bool
) -> AsyncIterator[_OwnedDatabase]:
    async with engine.connect() as connection:
        connection.info["jarvis_memory_admitted"] = memory_admitted
        try:
            for key in keys:
                if not await connection.scalar(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
                ):
                    raise DeploymentAlreadyOwned("another process owns this writer")
            await connection.commit()
        except BaseException as exc:
            # Session locks survive rollback. Discard even a partially locked session.
            await connection.invalidate()
            if isinstance(exc, DBAPIError):
                raise DeploymentOwnershipDefect(
                    "writer lock acquisition failed"
                ) from exc
            raise
        database = _OwnedDatabase(connection)
        try:
            yield database
        finally:
            database.active = False
            if connection.closed or connection.invalidated:
                raise DeploymentOwnershipDefect("deployment owner connection was lost")
            try:
                for key in reversed(keys):
                    if not await connection.scalar(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                    ):
                        raise DeploymentOwnershipDefect("writer lock was not held")
            except BaseException as exc:
                await connection.invalidate()
                if isinstance(exc, DBAPIError):
                    raise DeploymentOwnershipDefect(
                        "writer lock release failed"
                    ) from exc
                raise


__all__ = [
    "DEPLOYMENT_LOCK_KEY",
    "MEMORY_LOCK_KEY",
    "Database",
    "DeploymentAlreadyOwned",
    "DeploymentOwnershipDefect",
    "deployment_ownership",
    "maintenance_ownership",
]

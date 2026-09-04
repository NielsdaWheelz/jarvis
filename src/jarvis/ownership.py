"""Exclusive deployment ownership through one PostgreSQL advisory lock."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

DEPLOYMENT_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"jarvis-deployment-v1").digest()[:8],
    byteorder="big",
    signed=True,
)


class DeploymentAlreadyOwned(RuntimeError):
    """Another Jarvis process owns this deployment."""


class DeploymentOwnershipDefect(RuntimeError):
    """The database could not establish or release deployment ownership."""


@asynccontextmanager
async def deployment_ownership(engine: AsyncEngine) -> AsyncIterator[None]:
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
        try:
            yield
        finally:
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
    "DeploymentAlreadyOwned",
    "DeploymentOwnershipDefect",
    "deployment_ownership",
]

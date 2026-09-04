"""Small private host state that does not belong in PostgreSQL."""

from __future__ import annotations

import asyncio
from pathlib import Path

from jarvis._atomic_json import read_private_json, replace_private_json


class PausedStateDefect(RuntimeError):
    """The durable host pause state is missing or corrupt."""


class PausedState:
    """Atomically persisted stop/pause state for the one deployment."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("paused-state path must be absolute")
        self._path = path
        self._lock = asyncio.Lock()

    @classmethod
    def initialize(cls, path: Path, *, replace: bool = False) -> None:
        if path.exists() and not replace:
            raise FileExistsError("paused state already exists")
        replace_private_json(
            path,
            {
                "paused": False,
                "schema_version": "jarvis-paused.v1",
            },
        )

    async def is_paused(self) -> bool:
        async with self._lock:
            return self._read()

    async def set_paused(self, paused: bool) -> bool:
        if type(paused) is not bool:
            raise TypeError("paused must be a boolean")
        async with self._lock:
            previous = self._read()
            if previous == paused:
                return False
            replace_private_json(
                self._path,
                {
                    "paused": paused,
                    "schema_version": "jarvis-paused.v1",
                },
            )
            return True

    def _read(self) -> bool:
        try:
            value = read_private_json(self._path)
            if value is None or set(value) != {"paused", "schema_version"}:
                raise ValueError("paused state has an invalid shape")
            if value["schema_version"] != "jarvis-paused.v1":
                raise ValueError("paused state has an invalid version")
            paused = value["paused"]
            if type(paused) is not bool:
                raise ValueError("paused state value is invalid")
            return paused
        except (OSError, TypeError, ValueError) as exc:
            raise PausedStateDefect("paused state is missing or corrupt") from exc


__all__ = ["PausedState", "PausedStateDefect"]

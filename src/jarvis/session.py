from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from llm_agent_kernel import (
    DiscardedSessionRef,
    SessionRefStateDefect,
    StaleSessionRef,
    StoredSessionRef,
    ThreadId,
)
from provider_runtime.agent_runtime import (
    AgentSessionRef,
    InvalidAgentRequest,
    ref_from_json,
    ref_to_json,
    thaw_json_value,
)

from jarvis._atomic_json import read_private_json, replace_private_json

_FIELDS = {
    "definition_fingerprint",
    "generation",
    "ref",
    "schema_version",
    "thread_id",
}


class AtomicSessionRefPort:
    """One atomically replaced, disposable main-session reference."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("session-reference path must be absolute")
        self._path = path
        self._lock = asyncio.Lock()

    async def load(
        self, thread_id: ThreadId, definition_fingerprint: str
    ) -> StoredSessionRef | None:
        async with self._lock:
            state = self._read()
            if state is None or not _matches(state, thread_id, definition_fingerprint):
                return None
            return StoredSessionRef(
                _reference(state),
                _integer(state, "generation"),
            )

    async def compare_and_set(
        self,
        thread_id: ThreadId,
        definition_fingerprint: str,
        expected_generation: int | None,
        new_ref: AgentSessionRef,
    ) -> StoredSessionRef | StaleSessionRef:
        async with self._lock:
            state = self._read()
            matching = state is not None and _matches(
                state, thread_id, definition_fingerprint
            )
            if expected_generation is None:
                if matching:
                    return StaleSessionRef()
                generation = 1
            else:
                if (
                    type(expected_generation) is not int
                    or expected_generation <= 0
                    or not matching
                ):
                    return StaleSessionRef()
                assert state is not None
                if _integer(state, "generation") != expected_generation:
                    return StaleSessionRef()
                generation = expected_generation + 1
            replace_private_json(
                self._path,
                {
                    "definition_fingerprint": definition_fingerprint,
                    "generation": generation,
                    "ref": thaw_json_value(ref_to_json(new_ref)),
                    "schema_version": "jarvis-session-ref.v1",
                    "thread_id": str(thread_id),
                },
            )
            return StoredSessionRef(new_ref, generation)

    async def discard(
        self,
        thread_id: ThreadId,
        definition_fingerprint: str,
        expected_generation: int | None,
    ) -> DiscardedSessionRef | StaleSessionRef:
        async with self._lock:
            state = self._read()
            if state is None or not _matches(state, thread_id, definition_fingerprint):
                return DiscardedSessionRef()
            if (
                type(expected_generation) is not int
                or expected_generation <= 0
                or _integer(state, "generation") != expected_generation
            ):
                return StaleSessionRef()
            self._path.unlink()
            _sync_directory(self._path.parent)
            return DiscardedSessionRef()

    def _read(self) -> dict[str, object] | None:
        try:
            value = read_private_json(self._path)
            if value is None:
                return None
            if set(value) != _FIELDS:
                raise ValueError("session-reference state has an invalid shape")
            if value["schema_version"] != "jarvis-session-ref.v1":
                raise ValueError("session-reference state has an invalid version")
            thread_id = value["thread_id"]
            fingerprint = value["definition_fingerprint"]
            if type(thread_id) is not str or not thread_id:
                raise ValueError("session-reference thread id is invalid")
            if (
                type(fingerprint) is not str
                or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)
            ):
                raise ValueError("session-reference fingerprint is invalid")
            _integer(value, "generation")
            _reference(value)
            return dict(value)
        except (OSError, InvalidAgentRequest, TypeError, ValueError) as error:
            raise SessionRefStateDefect("session-reference state is corrupt") from error


def _matches(
    state: Mapping[str, object], thread_id: ThreadId, definition_fingerprint: str
) -> bool:
    return (
        state["thread_id"] == str(thread_id)
        and state["definition_fingerprint"] == definition_fingerprint
    )


def _integer(state: Mapping[str, object], name: str) -> int:
    value = state[name]
    if type(value) is not int or value <= 0:
        raise ValueError(f"session-reference {name} is invalid")
    return value


def _reference(state: Mapping[str, object]) -> AgentSessionRef:
    value = state["ref"]
    if not isinstance(value, Mapping):
        raise ValueError("session-reference payload is invalid")
    return ref_from_json(cast("Mapping[str, object]", value))


def _sync_directory(path: Path) -> None:
    import os

    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ["AtomicSessionRefPort"]

"""The shared non-secret Codex host mapping needed by cognition only."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

CODEX_MAX_MESSAGE_BYTES = 65536
type CodexProfile = Literal["personal", "work", "work2"]


def canonical_absolute_path(value: str) -> str:
    if (
        not value.startswith("/")
        or value.startswith("//")
        or value == "/"
        or os.path.normpath(value) != value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or len(value.encode("utf-8")) > 4096
    ):
        raise ValueError("path must be a normalized non-root absolute path")
    return value


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class _Profile(_Closed):
    account_home: str
    endpoint: str


class CodexHostConfig(_Closed):
    """Read-only non-secret host mapping; never credential or worker state."""

    schema_version: Literal[3]
    development_user: str
    jarvis_user: str
    client_group: str
    binary: str
    cognition_cwd_parent: str
    profiles: dict[CodexProfile, _Profile]

    @property
    def endpoints(self) -> dict[str, Path]:
        return {key: Path(row.endpoint[7:]) for key, row in self.profiles.items()}

    @classmethod
    def load(cls, path: Path) -> CodexHostConfig:
        with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_mode & 0o022
            ):
                raise ValueError(
                    "Codex host mapping must be root-owned and not writable by clients"
                )
            encoded = source.read(CODEX_MAX_MESSAGE_BYTES + 1)
        if len(encoded) > CODEX_MAX_MESSAGE_BYTES:
            raise ValueError("Codex host mapping is oversized")
        result = cls.model_validate(_decode(encoded))
        if set(result.profiles) != {"personal", "work", "work2"}:
            raise ValueError("Codex host mapping must declare all three profiles")
        paths = [
            result.binary,
            result.cognition_cwd_parent,
        ]
        for row in result.profiles.values():
            if not row.endpoint.startswith("unix:///"):
                raise ValueError("Codex host endpoint must be a Unix socket")
            paths.extend((row.account_home, row.endpoint[7:]))
        if any(not _absolute(value) for value in paths):
            raise ValueError("Codex host mapping has a noncanonical path")
        if len(set(result.endpoints.values())) != 3:
            raise ValueError("Codex profiles must use distinct endpoints")
        return result


def _absolute(value: str) -> bool:
    try:
        canonical_absolute_path(value)
    except ValueError:
        return False
    return True


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    del value
    raise ValueError("non-JSON constant")


def _decode(encoded: bytes) -> object:
    return json.loads(
        encoded.decode("utf-8"),
        object_pairs_hook=_object,
        parse_constant=_invalid_constant,
    )

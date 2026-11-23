"""The non-secret Codex host mapping and persistent workspace preflight."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from jarvis.config import decode_config_json

CODEX_MAX_MESSAGE_BYTES = 65536
type CodexProfile = Literal["personal"]


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

    schema_version: Literal[5]
    development_user: str
    jarvis_user: str
    client_group: str
    binary: str
    cognition_cwd_parent: str
    notes_repository: str
    profiles: dict[CodexProfile, _Profile]

    @property
    def endpoints(self) -> dict[str, Path]:
        return {key: Path(row.endpoint[7:]) for key, row in self.profiles.items()}

    def verify_notes_repository(self) -> None:
        repository = Path(self.notes_repository)
        metadata = repository / ".git"
        if (
            not repository.is_dir()
            or not metadata.is_dir()
            or metadata.is_symlink()
            or not os.access(repository, os.R_OK | os.X_OK)
            or not os.access(metadata, os.R_OK | os.X_OK)
        ):
            raise ValueError("notes repository must be an accessible ordinary checkout")

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
        result = cls.model_validate(decode_config_json(encoded))
        if set(result.profiles) != {"personal"}:
            raise ValueError(
                "Codex host mapping must declare its contained personal profile"
            )
        paths = [
            result.binary,
            result.cognition_cwd_parent,
            result.notes_repository,
        ]
        for row in result.profiles.values():
            if not row.endpoint.startswith("unix:///"):
                raise ValueError("Codex host endpoint must be a Unix socket")
            paths.extend((row.account_home, row.endpoint[7:]))
        if any(not _absolute(value) for value in paths):
            raise ValueError("Codex host mapping has a noncanonical path")
        return result


def _absolute(value: str) -> bool:
    try:
        canonical_absolute_path(value)
    except ValueError:
        return False
    return True

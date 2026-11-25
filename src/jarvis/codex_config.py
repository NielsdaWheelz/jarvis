"""The root-owned Codex account mapping and persistent workspace preflight."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from jarvis.config import decode_config_json

CODEX_MAX_MESSAGE_BYTES = 65536
type CodexProfile = Literal["personal", "work", "work2"]
CODEX_PROFILES = ("personal", "work", "work2")


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


class CodexAccount(_Closed):
    key: CodexProfile
    account_home: str
    endpoint: str
    host_user: str
    expected_user_id: str
    expected_account_id: str
    expected_plan_type: str

    @property
    def socket(self) -> Path:
        return Path(self.endpoint[7:])

    @property
    def unit(self) -> str:
        suffix = "" if self.key == "personal" else f"-{self.key}"
        return f"jarvis-codex-contained{suffix}.service"


class CodexHostConfig(_Closed):
    """Read-only non-secret host mapping; never credential or worker state."""

    schema_version: Literal[6]
    development_user: str
    jarvis_user: str
    client_group: str
    binary: str
    cognition_cwd_parent: str
    notes_repository: str
    accounts: tuple[CodexAccount, CodexAccount, CodexAccount]

    @property
    def endpoints(self) -> dict[str, Path]:
        return {row.key: row.socket for row in self.accounts}

    @model_validator(mode="after")
    def _validate_accounts(self) -> CodexHostConfig:
        if tuple(account.key for account in self.accounts) != CODEX_PROFILES:
            raise ValueError("expected Codex account order personal, work, work2")
        shared_paths = (Path(self.notes_repository), Path(self.cognition_cwd_parent))
        for path in (self.binary, self.notes_repository, self.cognition_cwd_parent):
            canonical_absolute_path(path)
        for index, account in enumerate(self.accounts):
            if not account.endpoint.startswith("unix:///"):
                raise ValueError("Codex host endpoint must be a Unix socket")
            canonical_absolute_path(account.endpoint[7:])
            home = Path(canonical_absolute_path(account.account_home))
            preceding = self.accounts[:index]
            preceding_homes = tuple(Path(row.account_home) for row in preceding)
            for other in (*shared_paths, *preceding_homes):
                if home.is_relative_to(other) or other.is_relative_to(home):
                    raise ValueError("Codex home overlaps another home or workspace")
            identity = (
                account.expected_user_id,
                account.expected_account_id,
                account.expected_plan_type,
            )
            if any(
                not value or not value.isprintable() or any(c.isspace() for c in value)
                for value in identity
            ):
                raise ValueError("invalid opaque Codex enrollment identity")
        host_users = {account.host_user for account in self.accounts}
        subjects = {
            (account.expected_user_id, account.expected_account_id)
            for account in self.accounts
        }
        if (
            len(set(self.endpoints.values())) != len(self.accounts)
            or len(host_users) != len(self.accounts)
            or self.jarvis_user in host_users
            or len(subjects) != len(self.accounts)
        ):
            raise ValueError("Codex endpoints, hosts and subjects must be distinct")
        return self

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
        return cls.model_validate(decode_config_json(encoded))

"""The root-owned Codex account mapping and persistent workspace preflight."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from jarvis.config import decode_config_json

CODEX_MAX_MESSAGE_BYTES = 65536
type PaidRoute = Literal["agy_neon", "google_neon"]
type NativeRoute = Literal["personal"] | PaidRoute
PAID_ROUTES: tuple[PaidRoute, PaidRoute] = ("agy_neon", "google_neon")
NATIVE_ROUTES = ("personal", *PAID_ROUTES)
NEON_CONTROL_SOCKET = Path("/run/jarvis-neon-adapter/control.sock")
NEON_ADAPTER_USER = "jarvis-neon-adapter"


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
    key: Literal["personal"]
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
    def allow_existing_credits(self) -> bool:
        return self.expected_plan_type in ("plus", "pro", "promax")


class NeonHost(_Closed):
    endpoint: str
    host_user: str
    host_home: str
    adapter_origin: str
    credential_name: str
    project_id: str

    @property
    def socket(self) -> Path:
        return Path(self.endpoint[7:])


class AntigravityHost(_Closed):
    endpoint: str
    host_user: str
    host_home: str
    binary: str

    @property
    def socket(self) -> Path:
        return Path(self.endpoint[7:])


class CodexHostConfig(_Closed):
    """Root-owned mapping of the contained cognition hosts."""

    schema_version: Literal[8]
    development_user: str
    jarvis_user: str
    client_group: str
    binary: str
    cognition_cwd_parent: str
    notes_repository: str
    personal: CodexAccount
    google_neon: NeonHost
    agy_neon: AntigravityHost

    @property
    def endpoints(self) -> dict[str, Path]:
        return {
            "personal": self.personal.socket,
            "google_neon": self.google_neon.socket,
        }

    @model_validator(mode="after")
    def _validate_layout(self) -> CodexHostConfig:
        personal = self.personal
        neon = self.google_neon
        agy = self.agy_neon
        canonical_absolute_path(self.binary)
        canonical_absolute_path(agy.binary)
        shared_paths = (
            Path(canonical_absolute_path(self.notes_repository)),
            Path(canonical_absolute_path(self.cognition_cwd_parent)),
        )
        personal_home = Path(canonical_absolute_path(personal.account_home))
        neon_home = Path(canonical_absolute_path(neon.host_home))
        agy_home = Path(canonical_absolute_path(agy.host_home))
        for home, others in (
            (personal_home, (*shared_paths, neon_home, agy_home)),
            (neon_home, (*shared_paths, agy_home)),
            (agy_home, shared_paths),
        ):
            if any(
                home.is_relative_to(other) or other.is_relative_to(home)
                for other in others
            ):
                raise ValueError("Codex home overlaps another home or workspace")
        for endpoint in (personal.endpoint, neon.endpoint, agy.endpoint):
            if not endpoint.startswith("unix:///"):
                raise ValueError("Codex host endpoint must be a Unix socket")
            canonical_absolute_path(endpoint[7:])
        identity = (
            personal.expected_user_id,
            personal.expected_account_id,
            personal.expected_plan_type,
        )
        if any(
            not value or not value.isprintable() or any(c.isspace() for c in value)
            for value in identity
        ):
            raise ValueError("invalid opaque personal Codex enrollment identity")
        if (
            len({personal.socket, neon.socket, agy.socket}) != 3
            or len(
                {
                    self.jarvis_user,
                    personal.host_user,
                    neon.host_user,
                    agy.host_user,
                    NEON_ADAPTER_USER,
                }
            )
            != 5
            or any(
                not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user)
                for user in (personal.host_user, neon.host_user, agy.host_user)
            )
        ):
            raise ValueError("contained host users and endpoints must be distinct")
        match = re.fullmatch(
            r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", neon.adapter_origin
        )
        if match is None or int(match[1]) > 65535:
            raise ValueError("Neon adapter requires a loopback port")
        if neon.credential_name in {
            "neon-stock-bearer",
            "neon-continuation-key",
        } or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", neon.credential_name):
            raise ValueError("invalid systemd credential name")
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", neon.project_id):
            raise ValueError("invalid Google Cloud project id")
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

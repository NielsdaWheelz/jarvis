"""Top-level host settings."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import time
from pathlib import Path
from typing import Annotated, Final, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)
from universal_memory.policy import EMBEDDING_DIMENSIONS

from jarvis.codex_config import CodexHostConfig
from jarvis.config import ConfigurationError
from jarvis.workspace_enrollment import HELD_PRODUCTION_PROJECT

EMBEDDING_MODEL: Final[Literal["text-embedding-3-small"]] = "text-embedding-3-small"
EMBEDDING_DIMENSION: Final[Literal[1536]] = EMBEDDING_DIMENSIONS
MAXIMUM_BATCH_SIZE: Final[int] = 100


def _absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("configured path must be absolute")
    return path


def _owner_scope(value: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError("owner scope must be the stored decimal channel scope")
    return value


def _owner_archive_key(value: str) -> str:
    if not re.fullmatch(r"discord:[1-9][0-9]*:[1-9][0-9]*", value):
        raise ValueError("owner archive key must be exactly discord:<guild>:<channel>")
    return value


AbsolutePath = Annotated[Path, AfterValidator(_absolute)]
# Immutable installation identities. Changing either would orphan stored owner
# state or republish archived memory; the notice destination is separate.
OwnerScope = Annotated[str, AfterValidator(_owner_scope)]
OwnerArchiveKey = Annotated[str, AfterValidator(_owner_archive_key)]
MEMORY_SOCKET_PATH = Path("/run/jarvis-memory/internal.sock")
HOME_SOCKET_PATH = Path("/run/jarvis-home/http.sock")


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    database_url: SecretStr = Field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
        return cls.model_validate(
            {
                field: source[name]
                for field in cls.model_fields
                if (name := "JARVIS_" + field.upper()) in source
            }
        )

    @field_validator("database_url")
    @classmethod
    def _valid_database_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw or raw != raw.strip():
            raise ValueError("database URL must be non-empty without edge whitespace")
        return value


class SharedMemorySettings(DatabaseSettings):
    memory_config_path: AbsolutePath
    memory_socket_path: AbsolutePath = MEMORY_SOCKET_PATH


class MemoryServerSettings(SharedMemorySettings):
    memory_http_port: int = Field(default=8768, ge=1, le=65535)


class MemoryStatusSettings(DatabaseSettings):
    memory_config_path: AbsolutePath
    owner_scope: OwnerScope
    owner_archive_key: OwnerArchiveKey


class PausedSettings(DatabaseSettings):
    runtime_state_directory: AbsolutePath
    owner_scope: OwnerScope


class NativeStateSettings(PausedSettings):
    codex_host_config_path: AbsolutePath


class CutoverSettings(NativeStateSettings):
    attachment_cache_directory: AbsolutePath


class IsolatedRoleSettings(SharedMemorySettings):
    owner_timezone: str = Field(min_length=1, max_length=255)
    memory_nightly_time: time = time(3)
    codex_host_config_path: AbsolutePath
    runtime_state_directory: AbsolutePath
    attachment_cache_directory: AbsolutePath

    @staticmethod
    def _check_retired_profile(source: Mapping[str, str]) -> None:
        if "JARVIS_CODEX_PROFILE_KEY" in source:
            raise ConfigurationError(
                "remove JARVIS_CODEX_PROFILE_KEY; the release owns route selection"
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
        cls._check_retired_profile(source)
        return super().from_env(source)

    @property
    def codex_host_config(self) -> CodexHostConfig:
        return CodexHostConfig.load(self.codex_host_config_path)

    @field_validator("memory_nightly_time")
    @classmethod
    def _nightly_time(cls, value: time) -> time:
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError("nightly time must be a local hour and minute")
        return value

    @field_validator("owner_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "owner timezone must be an installed IANA timezone"
            ) from exc
        return value


class MemoryJobSettings(IsolatedRoleSettings):
    owner_scope: OwnerScope
    owner_archive_key: OwnerArchiveKey


def embedding_key_from_env(environ: Mapping[str, str] | None = None) -> SecretStr:
    source = os.environ if environ is None else environ
    if source.get("JARVIS_EMBEDDING_MODEL") != EMBEDDING_MODEL or source.get(
        "JARVIS_EMBEDDING_DIMENSION"
    ) != str(EMBEDDING_DIMENSION):
        raise ConfigurationError(
            "embedding settings must match the qualified model and dimension"
        )
    key = source.get("JARVIS_EMBEDDING_OPENAI_API_KEY")
    if not key or key.strip() != key:
        raise ConfigurationError("invalid embedding credential")
    return SecretStr(key)


class Settings(MemoryJobSettings):
    """Assistant runtime configuration."""

    fcm_project: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$"
    )
    home_socket_path: AbsolutePath = HOME_SOCKET_PATH
    agent_cli_path: Path
    agent_state_directory: Path
    workspace_project_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$"
    )
    google_oauth_state_path: Path = Path(
        "/var/lib/jarvis/connectors/google-oauth-state.json"
    )
    google_oauth_client_id: SecretStr = Field(default=SecretStr(""), repr=False)
    google_oauth_client_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    connector_encryption_key_version: str = Field(
        default="v1", min_length=1, max_length=32
    )
    connector_encryption_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    maps_api_key: SecretStr = Field(repr=False)
    brave_api_key: SecretStr = Field(repr=False)
    attachment_r2_account_id: str
    attachment_r2_bucket: str = Field(min_length=1, max_length=63)
    attachment_r2_access_key_id: SecretStr = Field(repr=False)
    attachment_r2_secret_access_key: SecretStr = Field(repr=False)
    maximum_batch_size: int = Field(default=20, ge=1, le=MAXIMUM_BATCH_SIZE)
    delivery_batch_size: int = Field(default=20, ge=1, le=100)

    @field_validator(
        "maps_api_key",
        "brave_api_key",
        "attachment_r2_access_key_id",
        "attachment_r2_secret_access_key",
    )
    @classmethod
    def _nonempty_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw or raw != raw.strip():
            raise ValueError("secret setting must be non-empty without edge whitespace")
        return value

    @field_validator("attachment_r2_account_id")
    @classmethod
    def _r2_account_id(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ValueError(
                "R2 account id must be 32 lowercase hexadecimal characters"
            )
        return value

    @field_validator("attachment_r2_bucket")
    @classmethod
    def _r2_bucket(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", value):
            raise ValueError("R2 bucket must be an ordinary S3 bucket name")
        return value

    @field_validator("connector_encryption_key_version")
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("setting must be non-empty without edge whitespace")
        return value

    @field_validator(
        "agent_cli_path",
        "agent_state_directory",
        "google_oauth_state_path",
    )
    @classmethod
    def _absolute_runtime_directory(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("runtime-state directory must be absolute")
        return value

    @property
    def host_secrets(self) -> tuple[str, ...]:
        values = (
            self.database_url.get_secret_value(),
            self.google_oauth_client_id.get_secret_value(),
            self.google_oauth_client_secret.get_secret_value(),
            self.connector_encryption_secret.get_secret_value(),
            self.maps_api_key.get_secret_value(),
            self.brave_api_key.get_secret_value(),
            self.attachment_r2_access_key_id.get_secret_value(),
            self.attachment_r2_secret_access_key.get_secret_value(),
        )
        return tuple(dict.fromkeys(value for value in values if value))

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
        cls._check_retired_profile(source)
        if "JARVIS_DREAM_INTERVAL_SECONDS" in source:
            raise ConfigurationError(
                "dream intervals are retired; configure JARVIS_MEMORY_NIGHTLY_TIME"
            )
        if "JARVIS_CODEX_MODEL" in source:
            raise ConfigurationError(
                "remove JARVIS_CODEX_MODEL; the release manifest selects each role"
            )
        if "JARVIS_CODEX_STATE_ROOT" in source:
            raise ConfigurationError(
                "private Codex state is retired; configure the host mapping"
            )
        if "JARVIS_MAXIMUM_PROCESSING_ATTEMPTS" in source:
            raise ConfigurationError(
                "JARVIS_MAXIMUM_PROCESSING_ATTEMPTS is fixed by the Slice 1 kernel"
            )

        def required(name: str) -> str:
            value = source.get(name)
            if value is None or not value:
                raise ConfigurationError(f"missing required setting: {name}")
            return value

        def positive_int(name: str, default: int) -> int:
            raw = source.get(name)
            if raw is None:
                return default
            try:
                value = int(raw)
            except ValueError as exc:
                raise ConfigurationError(f"{name} must be a positive integer") from exc
            if value <= 0:
                raise ConfigurationError(f"{name} must be a positive integer")
            return value

        project = source.get("JARVIS_WORKSPACE_PROJECT_ID") or None
        if project == HELD_PRODUCTION_PROJECT:
            project = None

        def workspace_value(name: str, disabled_default: str = "") -> str:
            return required(name) if project is not None else disabled_default

        try:
            return cls(
                database_url=SecretStr(required("JARVIS_DATABASE_URL")),
                fcm_project=source.get("JARVIS_FCM_PROJECT_ID"),
                owner_scope=required("JARVIS_OWNER_SCOPE"),
                owner_archive_key=required("JARVIS_OWNER_ARCHIVE_KEY"),
                home_socket_path=Path(
                    source.get("JARVIS_HOME_SOCKET_PATH", str(HOME_SOCKET_PATH))
                ),
                owner_timezone=required("JARVIS_OWNER_TIMEZONE"),
                agent_cli_path=Path(required("JARVIS_AGENT_CLI_PATH")),
                agent_state_directory=Path(required("JARVIS_AGENT_STATE_DIRECTORY")),
                codex_host_config_path=Path(required("JARVIS_CODEX_HOST_CONFIG_PATH")),
                runtime_state_directory=Path(
                    required("JARVIS_RUNTIME_STATE_DIRECTORY")
                ),
                memory_config_path=Path(required("JARVIS_MEMORY_CONFIG_PATH")),
                memory_socket_path=Path(
                    source.get("JARVIS_MEMORY_SOCKET_PATH", str(MEMORY_SOCKET_PATH))
                ),
                memory_nightly_time=time.fromisoformat(
                    source.get("JARVIS_MEMORY_NIGHTLY_TIME", "03:00")
                ),
                workspace_project_id=project,
                google_oauth_state_path=Path(
                    workspace_value(
                        "JARVIS_GOOGLE_OAUTH_STATE_PATH",
                        "/var/lib/jarvis/connectors/google-oauth-state.json",
                    )
                ),
                google_oauth_client_id=SecretStr(
                    workspace_value("JARVIS_GOOGLE_OAUTH_CLIENT_ID")
                ),
                google_oauth_client_secret=SecretStr(
                    workspace_value("JARVIS_GOOGLE_OAUTH_CLIENT_SECRET")
                ),
                connector_encryption_key_version=workspace_value(
                    "JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION", "v1"
                ),
                connector_encryption_secret=SecretStr(
                    workspace_value("JARVIS_CONNECTOR_ENCRYPTION_SECRET")
                ),
                maps_api_key=SecretStr(required("JARVIS_MAPS_API_KEY")),
                brave_api_key=SecretStr(required("JARVIS_BRAVE_API_KEY")),
                attachment_r2_account_id=required("JARVIS_ATTACHMENT_R2_ACCOUNT_ID"),
                attachment_r2_bucket=required("JARVIS_ATTACHMENT_R2_BUCKET"),
                attachment_r2_access_key_id=SecretStr(
                    required("JARVIS_ATTACHMENT_R2_ACCESS_KEY_ID")
                ),
                attachment_r2_secret_access_key=SecretStr(
                    required("JARVIS_ATTACHMENT_R2_SECRET_ACCESS_KEY")
                ),
                attachment_cache_directory=Path(
                    required("JARVIS_ATTACHMENT_CACHE_DIRECTORY")
                ),
                maximum_batch_size=positive_int("JARVIS_MAXIMUM_BATCH_SIZE", 20),
                delivery_batch_size=positive_int("JARVIS_DELIVERY_BATCH_SIZE", 20),
            )
        except (ValidationError, ValueError) as exc:
            raise ConfigurationError("invalid Jarvis configuration") from exc


__all__ = [
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL",
    "MAXIMUM_BATCH_SIZE",
    "Settings",
]

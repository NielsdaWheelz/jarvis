"""Top-level host settings."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import time
from pathlib import Path
from typing import Annotated, Final, Literal, Self, cast
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
from jarvis.config import ConfigurationError, DiscordSettings
from jarvis.definitions import MAIN_CODEX_MODEL

EMBEDDING_MODEL: Final[Literal["text-embedding-3-small"]] = "text-embedding-3-small"
EMBEDDING_DIMENSION: Final[Literal[1536]] = EMBEDDING_DIMENSIONS
MAXIMUM_BATCH_SIZE: Final[int] = 100


def _absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("configured path must be absolute")
    return path


AbsolutePath = Annotated[Path, AfterValidator(_absolute)]
MEMORY_SOCKET_PATH = Path("/run/jarvis-memory/internal.sock")


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
    discord_guild_id: int = Field(gt=0)
    discord_channel_id: int = Field(gt=0)


class PausedSettings(DatabaseSettings):
    runtime_state_directory: AbsolutePath
    discord_channel_id: int = Field(gt=0)


class NativeStateSettings(PausedSettings):
    codex_host_config_path: AbsolutePath


class CutoverSettings(NativeStateSettings):
    attachment_cache_directory: AbsolutePath


class IsolatedRoleSettings(SharedMemorySettings):
    owner_timezone: str = Field(min_length=1, max_length=255)
    codex_profile_key: Literal["personal"]
    memory_nightly_time: time = time(3)
    codex_host_config_path: AbsolutePath
    runtime_state_directory: AbsolutePath
    attachment_cache_directory: AbsolutePath

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
    discord_guild_id: int = Field(gt=0)
    discord_channel_id: int = Field(gt=0)


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


class Settings(IsolatedRoleSettings):
    """Assistant runtime configuration."""

    discord: DiscordSettings
    codex_model: str = Field(min_length=1, max_length=255)
    agent_cli_path: Path
    agent_state_directory: Path
    google_oauth_state_path: Path
    google_oauth_client_id: SecretStr = Field(repr=False)
    google_oauth_client_secret: SecretStr = Field(repr=False)
    connector_encryption_key_version: str = Field(min_length=1, max_length=32)
    connector_encryption_secret: SecretStr = Field(repr=False)
    maps_api_key: SecretStr = Field(repr=False)
    brave_api_key: SecretStr = Field(repr=False)
    attachment_r2_account_id: str
    attachment_r2_bucket: str = Field(min_length=1, max_length=63)
    attachment_r2_access_key_id: SecretStr = Field(repr=False)
    attachment_r2_secret_access_key: SecretStr = Field(repr=False)
    verified_owner_only_calendar_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=32,
        repr=False,
    )
    maximum_batch_size: int = Field(default=20, ge=1, le=MAXIMUM_BATCH_SIZE)
    delivery_batch_size: int = Field(default=20, ge=1, le=100)

    @field_validator(
        "google_oauth_client_id",
        "google_oauth_client_secret",
        "connector_encryption_secret",
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

    @field_validator("codex_profile_key", "connector_encryption_key_version")
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("setting must be non-empty without edge whitespace")
        return value

    @field_validator("codex_model")
    @classmethod
    def _qualified_codex_model(cls, value: str) -> str:
        del cls
        if value != MAIN_CODEX_MODEL:
            raise ValueError(f"JARVIS_CODEX_MODEL must be {MAIN_CODEX_MODEL}")
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
    def discord_channel_id(self) -> int:
        return self.discord.channel_id

    @property
    def discord_guild_id(self) -> int:
        return self.discord.guild_id

    @property
    def host_secrets(self) -> tuple[str, ...]:
        values = (
            self.database_url.get_secret_value(),
            self.discord.bot_token.get_secret_value(),
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
        if "JARVIS_DREAM_INTERVAL_SECONDS" in source:
            raise ConfigurationError(
                "dream intervals are retired; configure JARVIS_MEMORY_NIGHTLY_TIME"
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

        calendar_ids = tuple(
            value.strip()
            for value in required("JARVIS_VERIFIED_OWNER_ONLY_CALENDAR_IDS").split(",")
        )
        if (
            not calendar_ids
            or any(
                not value or len(value.encode("utf-8")) > 1_024
                for value in calendar_ids
            )
            or len(set(calendar_ids)) != len(calendar_ids)
        ):
            raise ConfigurationError(
                "JARVIS_VERIFIED_OWNER_ONLY_CALENDAR_IDS must be a unique, "
                "non-empty comma-separated list"
            )

        try:
            return cls(
                database_url=SecretStr(required("JARVIS_DATABASE_URL")),
                discord=DiscordSettings.from_env(source),
                owner_timezone=required("JARVIS_OWNER_TIMEZONE"),
                codex_profile_key=cast(
                    Literal["personal"], required("JARVIS_CODEX_PROFILE_KEY")
                ),
                codex_model=required("JARVIS_CODEX_MODEL"),
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
                google_oauth_state_path=Path(
                    required("JARVIS_GOOGLE_OAUTH_STATE_PATH")
                ),
                google_oauth_client_id=SecretStr(
                    required("JARVIS_GOOGLE_OAUTH_CLIENT_ID")
                ),
                google_oauth_client_secret=SecretStr(
                    required("JARVIS_GOOGLE_OAUTH_CLIENT_SECRET")
                ),
                connector_encryption_key_version=required(
                    "JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION"
                ),
                connector_encryption_secret=SecretStr(
                    required("JARVIS_CONNECTOR_ENCRYPTION_SECRET")
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
                verified_owner_only_calendar_ids=calendar_ids,
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

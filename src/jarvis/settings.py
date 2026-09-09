"""Top-level host settings."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal, Self, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from jarvis.codex_control import CodexHostConfig
from jarvis.config import ConfigurationError, DiscordSettings
from jarvis.definitions import QUALIFIED_CODEX_MODELS

EMBEDDING_MODEL: Final[Literal["text-embedding-3-small"]] = "text-embedding-3-small"
EMBEDDING_DIMENSION: Final[Literal[1536]] = 1536
MAXIMUM_BATCH_SIZE: Final[int] = 100
DEFAULT_DREAM_INTERVAL_SECONDS: Final[int] = 86_400


class Settings(BaseModel):
    """Strict application configuration composed with the Discord boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr = Field(repr=False)
    discord: DiscordSettings
    owner_timezone: str = Field(min_length=1, max_length=255)
    codex_profile_key: Literal["personal"]
    codex_model: str = Field(min_length=1, max_length=255)
    codex_host_config_path: Path
    runtime_state_directory: Path
    google_oauth_state_path: Path
    google_oauth_client_id: SecretStr = Field(repr=False)
    google_oauth_client_secret: SecretStr = Field(repr=False)
    connector_encryption_key_version: str = Field(min_length=1, max_length=32)
    connector_encryption_keys: SecretStr = Field(repr=False)
    connector_encryption_secret: SecretStr = Field(repr=False)
    maps_api_key: SecretStr = Field(repr=False)
    brave_api_key: SecretStr = Field(repr=False)
    embedding_openai_api_key: SecretStr = Field(repr=False)
    verified_owner_only_calendar_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=32,
        repr=False,
    )
    embedding_model: Literal["text-embedding-3-small"] = EMBEDDING_MODEL
    embedding_dimension: Literal[1536] = EMBEDDING_DIMENSION
    maximum_batch_size: int = Field(default=20, ge=1, le=MAXIMUM_BATCH_SIZE)
    delivery_batch_size: int = Field(default=20, ge=1, le=100)
    dream_interval_seconds: int = Field(
        default=DEFAULT_DREAM_INTERVAL_SECONDS,
        ge=60,
    )

    @field_validator(
        "database_url",
        "google_oauth_client_id",
        "google_oauth_client_secret",
        "connector_encryption_keys",
        "connector_encryption_secret",
        "maps_api_key",
        "brave_api_key",
        "embedding_openai_api_key",
    )
    @classmethod
    def _nonempty_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw or raw != raw.strip():
            raise ValueError("secret setting must be non-empty without edge whitespace")
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
        if value not in QUALIFIED_CODEX_MODELS:
            raise ValueError("Codex model is not a qualified local-account route")
        return value

    @field_validator(
        "codex_host_config_path", "runtime_state_directory", "google_oauth_state_path"
    )
    @classmethod
    def _absolute_runtime_directory(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("runtime-state directory must be absolute")
        return value

    @property
    def paused_state_path(self) -> Path:
        return self.runtime_state_directory / "paused.json"

    @property
    def admission_journal_path(self) -> Path:
        return self.runtime_state_directory / "admission.json"

    @property
    def session_reference_path(self) -> Path:
        return self.runtime_state_directory / "session-ref.json"

    @property
    def provider_cwd_parent(self) -> Path:
        return Path(self.codex_host_config.cognition_cwd_parent)

    @property
    def codex_host_config(self) -> CodexHostConfig:
        return CodexHostConfig.load(self.codex_host_config_path)

    @property
    def host_secrets(self) -> tuple[str, ...]:
        configured_keys = self.connector_encryption_keys.get_secret_value()
        key_values: list[str] = []
        try:
            parsed: object = json.loads(configured_keys)
        except json.JSONDecodeError:
            key_values.extend(
                item.strip().partition(":")[2].strip()
                for item in configured_keys.split(",")
                if item.strip().partition(":")[2].strip()
            )
        else:
            if isinstance(parsed, dict):
                key_values.extend(
                    value.strip()
                    for value in cast("dict[object, object]", parsed).values()
                    if isinstance(value, str) and value.strip()
                )
        values = (
            self.database_url.get_secret_value(),
            self.discord.bot_token.get_secret_value(),
            self.google_oauth_client_id.get_secret_value(),
            self.google_oauth_client_secret.get_secret_value(),
            self.connector_encryption_keys.get_secret_value(),
            self.connector_encryption_secret.get_secret_value(),
            self.maps_api_key.get_secret_value(),
            self.brave_api_key.get_secret_value(),
            self.embedding_openai_api_key.get_secret_value(),
            *key_values,
        )
        return tuple(dict.fromkeys(value for value in values if value))

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
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

        embedding_model = required("JARVIS_EMBEDDING_MODEL")
        if embedding_model != EMBEDDING_MODEL:
            raise ConfigurationError(
                f"JARVIS_EMBEDDING_MODEL must be {EMBEDDING_MODEL}"
            )
        required("JARVIS_EMBEDDING_DIMENSION")
        embedding_dimension = positive_int(
            "JARVIS_EMBEDDING_DIMENSION", EMBEDDING_DIMENSION
        )
        if embedding_dimension != EMBEDDING_DIMENSION:
            raise ConfigurationError(
                f"JARVIS_EMBEDDING_DIMENSION must be {EMBEDDING_DIMENSION}"
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
                codex_host_config_path=Path(required("JARVIS_CODEX_HOST_CONFIG_PATH")),
                runtime_state_directory=Path(
                    required("JARVIS_RUNTIME_STATE_DIRECTORY")
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
                connector_encryption_keys=SecretStr(
                    required("JARVIS_CONNECTOR_ENCRYPTION_KEYS")
                ),
                connector_encryption_secret=SecretStr(
                    required("JARVIS_CONNECTOR_ENCRYPTION_SECRET")
                ),
                maps_api_key=SecretStr(required("JARVIS_MAPS_API_KEY")),
                brave_api_key=SecretStr(required("JARVIS_BRAVE_API_KEY")),
                embedding_openai_api_key=SecretStr(
                    required("JARVIS_EMBEDDING_OPENAI_API_KEY")
                ),
                verified_owner_only_calendar_ids=calendar_ids,
                embedding_model=EMBEDDING_MODEL,
                embedding_dimension=EMBEDDING_DIMENSION,
                maximum_batch_size=positive_int("JARVIS_MAXIMUM_BATCH_SIZE", 20),
                delivery_batch_size=positive_int("JARVIS_DELIVERY_BATCH_SIZE", 20),
                dream_interval_seconds=positive_int(
                    "JARVIS_DREAM_INTERVAL_SECONDS",
                    DEFAULT_DREAM_INTERVAL_SECONDS,
                ),
            )
        except ValidationError as exc:
            raise ConfigurationError("invalid Jarvis configuration") from exc


__all__ = [
    "DEFAULT_DREAM_INTERVAL_SECONDS",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL",
    "MAXIMUM_BATCH_SIZE",
    "Settings",
]

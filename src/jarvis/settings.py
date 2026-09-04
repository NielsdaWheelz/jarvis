"""Top-level Slice 1 host settings."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from jarvis.config import ConfigurationError, DiscordSettings


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
    codex_profile_key: str = Field(min_length=1, max_length=255)
    codex_model: str = Field(min_length=1, max_length=255)
    codex_state_root: Path
    runtime_state_directory: Path
    maximum_batch_size: int = Field(default=20, ge=1, le=100)
    delivery_batch_size: int = Field(default=20, ge=1, le=100)

    @field_validator("database_url")
    @classmethod
    def _nonempty_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw or raw != raw.strip():
            raise ValueError("database URL must be non-empty without edge whitespace")
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

    @field_validator("codex_profile_key", "codex_model")
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("setting must be non-empty without edge whitespace")
        return value

    @field_validator("codex_state_root", "runtime_state_directory")
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
        return self.runtime_state_directory / "provider-cwd"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
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

        try:
            return cls(
                database_url=SecretStr(required("JARVIS_DATABASE_URL")),
                discord=DiscordSettings.from_env(source),
                owner_timezone=required("JARVIS_OWNER_TIMEZONE"),
                codex_profile_key=required("JARVIS_CODEX_PROFILE_KEY"),
                codex_model=required("JARVIS_CODEX_MODEL"),
                codex_state_root=Path(required("JARVIS_CODEX_STATE_ROOT")),
                runtime_state_directory=Path(
                    required("JARVIS_RUNTIME_STATE_DIRECTORY")
                ),
                maximum_batch_size=positive_int("JARVIS_MAXIMUM_BATCH_SIZE", 20),
                delivery_batch_size=positive_int("JARVIS_DELIVERY_BATCH_SIZE", 20),
            )
        except ValidationError as exc:
            raise ConfigurationError("invalid Jarvis configuration") from exc


__all__ = ["Settings"]

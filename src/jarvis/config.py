"""Strict host configuration."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)


class ConfigurationError(ValueError):
    """A required setting is missing or malformed."""


class DiscordSettings(BaseModel):
    """The complete configuration for the single Discord transport."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    bot_token: SecretStr = Field(repr=False)
    owner_user_id: int = Field(gt=0)
    guild_id: int = Field(gt=0)
    channel_id: int = Field(gt=0)
    catch_up_limit: int = Field(default=100, ge=1, le=1_000)
    request_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    delivery_retry_delays_seconds: tuple[float, ...] = Field(
        default=(0.5, 2.0),
        min_length=1,
        max_length=4,
    )

    @field_validator("bot_token")
    @classmethod
    def _valid_bot_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not token or token != token.strip():
            raise ValueError(
                "bot token must be non-empty and contain no edge whitespace"
            )
        return value

    @field_validator("delivery_retry_delays_seconds")
    @classmethod
    def _valid_retry_delays(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        previous = 0.0
        for delay in value:
            if not math.isfinite(delay) or delay <= previous or delay > 30.0:
                raise ValueError(
                    "retry delays must be finite, strictly increasing, and at most "
                    "30 seconds"
                )
            previous = delay
        return value

    @property
    def delivery_max_attempts(self) -> int:
        """Return the finite attempt count, including the initial request."""

        return len(self.delivery_retry_delays_seconds) + 1

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Load only the explicit Discord settings from an environment mapping."""

        source = os.environ if environ is None else environ

        def required(name: str) -> str:
            value = source.get(name)
            if value is None or not value:
                raise ConfigurationError(f"missing required setting: {name}")
            return value

        def positive_int(name: str, *, default: int | None = None) -> int:
            raw = source.get(name)
            if raw is None:
                if default is None:
                    raise ConfigurationError(f"missing required setting: {name}")
                return default
            try:
                value = int(raw)
            except ValueError as exc:
                raise ConfigurationError(f"{name} must be a positive integer") from exc
            if value <= 0:
                raise ConfigurationError(f"{name} must be a positive integer")
            return value

        def positive_float(name: str, *, default: float) -> float:
            raw = source.get(name)
            if raw is None:
                return default
            try:
                value = float(raw)
            except ValueError as exc:
                raise ConfigurationError(f"{name} must be a positive number") from exc
            if not math.isfinite(value) or value <= 0.0:
                raise ConfigurationError(f"{name} must be a positive finite number")
            return value

        raw_delays = source.get(
            "JARVIS_DISCORD_DELIVERY_RETRY_DELAYS_SECONDS",
            "0.5,2.0",
        )
        try:
            retry_delays = tuple(float(part) for part in raw_delays.split(","))
        except ValueError as exc:
            raise ConfigurationError(
                "JARVIS_DISCORD_DELIVERY_RETRY_DELAYS_SECONDS must be a "
                "comma-separated list of numbers"
            ) from exc

        try:
            return cls(
                bot_token=SecretStr(required("JARVIS_DISCORD_BOT_TOKEN")),
                owner_user_id=positive_int("JARVIS_DISCORD_OWNER_USER_ID"),
                guild_id=positive_int("JARVIS_DISCORD_GUILD_ID"),
                channel_id=positive_int("JARVIS_DISCORD_CHANNEL_ID"),
                catch_up_limit=positive_int(
                    "JARVIS_DISCORD_CATCH_UP_LIMIT",
                    default=100,
                ),
                request_timeout_seconds=positive_float(
                    "JARVIS_DISCORD_REQUEST_TIMEOUT_SECONDS",
                    default=10.0,
                ),
                delivery_retry_delays_seconds=retry_delays,
            )
        except ValidationError as exc:
            raise ConfigurationError("invalid Discord configuration") from exc

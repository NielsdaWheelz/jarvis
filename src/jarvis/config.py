"""Strict host configuration."""

from __future__ import annotations

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
    """The send-only notice destination, independent of owner identity."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    bot_token: SecretStr = Field(repr=False)
    channel_id: int = Field(gt=0)
    # Fixed sender policy, not environment configuration.
    request_timeout_seconds: float = 10.0
    delivery_retry_delays_seconds: tuple[float, ...] = (0.5, 2.0)

    @property
    def delivery_max_attempts(self) -> int:
        """Return the finite attempt count, including the initial request."""

        return len(self.delivery_retry_delays_seconds) + 1

    @field_validator("bot_token")
    @classmethod
    def _valid_bot_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not token or token != token.strip():
            raise ValueError(
                "bot token must be non-empty and contain no edge whitespace"
            )
        return value

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
        token = source.get("JARVIS_DISCORD_BOT_TOKEN")
        channel = source.get("JARVIS_DISCORD_CHANNEL_ID")
        if not token or not channel:
            raise ConfigurationError(
                "missing required setting: JARVIS_DISCORD_BOT_TOKEN and "
                "JARVIS_DISCORD_CHANNEL_ID"
            )
        try:
            return cls(bot_token=SecretStr(token), channel_id=int(channel))
        except (ValidationError, ValueError) as exc:
            raise ConfigurationError("invalid Discord notice configuration") from exc

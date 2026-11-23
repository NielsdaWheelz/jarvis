"""Strict host configuration."""

from __future__ import annotations

import json
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


def decode_config_json(encoded: bytes) -> object:
    """Decode a UTF-8 JSON declaration with unique fields and finite numbers."""
    return json.loads(
        encoded.decode("utf-8"),
        object_pairs_hook=_object,
        parse_constant=_invalid_constant,
    )


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

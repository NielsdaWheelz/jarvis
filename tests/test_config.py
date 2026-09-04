from __future__ import annotations

import pytest

from jarvis.config import ConfigurationError, DiscordSettings


def _environment() -> dict[str, str]:
    return {
        "JARVIS_DISCORD_BOT_TOKEN": "private-token",
        "JARVIS_DISCORD_OWNER_USER_ID": "11",
        "JARVIS_DISCORD_GUILD_ID": "22",
        "JARVIS_DISCORD_CHANNEL_ID": "33",
    }


def test_discord_settings_load_exact_environment_and_redact_secret() -> None:
    settings = DiscordSettings.from_env(_environment())

    assert settings.owner_user_id == 11
    assert settings.guild_id == 22
    assert settings.channel_id == 33
    assert settings.catch_up_limit == 100
    assert settings.delivery_retry_delays_seconds == (0.5, 2.0)
    assert settings.delivery_max_attempts == 3
    assert "private-token" not in repr(settings)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JARVIS_DISCORD_GUILD_ID", "not-a-number"),
        ("JARVIS_DISCORD_CHANNEL_ID", "0"),
        ("JARVIS_DISCORD_CATCH_UP_LIMIT", "1001"),
        ("JARVIS_DISCORD_REQUEST_TIMEOUT_SECONDS", "nan"),
        ("JARVIS_DISCORD_DELIVERY_RETRY_DELAYS_SECONDS", ""),
        ("JARVIS_DISCORD_DELIVERY_RETRY_DELAYS_SECONDS", "2,1"),
    ],
)
def test_discord_settings_reject_invalid_bounds(name: str, value: str) -> None:
    environment = _environment()
    environment[name] = value
    with pytest.raises(ConfigurationError):
        DiscordSettings.from_env(environment)


def test_configuration_errors_never_render_the_token() -> None:
    environment = _environment()
    environment["JARVIS_DISCORD_BOT_TOKEN"] = "private-token "
    with pytest.raises(ConfigurationError) as caught:
        DiscordSettings.from_env(environment)
    assert "private-token" not in str(caught.value)


def test_direct_construction_rejects_unknown_configuration() -> None:
    with pytest.raises(ValueError):
        DiscordSettings.model_validate(
            {
                "bot_token": "token",
                "owner_user_id": 11,
                "guild_id": 22,
                "channel_id": 33,
                "unknown": True,
            }
        )

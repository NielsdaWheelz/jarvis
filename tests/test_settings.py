from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.config import ConfigurationError
from jarvis.settings import Settings


def _environment(tmp_path: Path) -> dict[str, str]:
    return {
        "JARVIS_DATABASE_URL": "postgresql+psycopg://jarvis:secret@db/jarvis",
        "JARVIS_DISCORD_BOT_TOKEN": "private-token",
        "JARVIS_DISCORD_OWNER_USER_ID": "11",
        "JARVIS_DISCORD_GUILD_ID": "22",
        "JARVIS_DISCORD_CHANNEL_ID": "33",
        "JARVIS_OWNER_TIMEZONE": "America/Los_Angeles",
        "JARVIS_CODEX_PROFILE_KEY": "jarvis",
        "JARVIS_CODEX_MODEL": "gpt-5.4",
        "JARVIS_CODEX_STATE_ROOT": str(tmp_path / "codex"),
        "JARVIS_RUNTIME_STATE_DIRECTORY": str(tmp_path / "runtime"),
    }


def test_settings_compose_discord_and_derive_private_paths(tmp_path: Path) -> None:
    settings = Settings.from_env(_environment(tmp_path))

    assert settings.discord.channel_id == 33
    assert settings.paused_state_path == tmp_path / "runtime" / "paused.json"
    assert settings.admission_journal_path == tmp_path / "runtime" / "admission.json"
    assert settings.session_reference_path == tmp_path / "runtime" / "session-ref.json"
    assert settings.provider_cwd_parent == tmp_path / "runtime" / "provider-cwd"
    rendered = repr(settings)
    assert "private-token" not in rendered
    assert "secret" not in rendered


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JARVIS_OWNER_TIMEZONE", "Mars/Olympus_Mons"),
        ("JARVIS_CODEX_MODEL", " "),
        ("JARVIS_RUNTIME_STATE_DIRECTORY", "relative/runtime"),
        ("JARVIS_MAXIMUM_BATCH_SIZE", "101"),
        ("JARVIS_DELIVERY_BATCH_SIZE", "101"),
    ],
)
def test_settings_reject_invalid_host_bounds(
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    environment = _environment(tmp_path)
    environment[name] = value
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)


def test_settings_require_explicit_codex_state_root(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    del environment["JARVIS_CODEX_STATE_ROOT"]
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)


def test_settings_reject_obsolete_processing_attempt_override(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["JARVIS_MAXIMUM_PROCESSING_ATTEMPTS"] = "3"
    with pytest.raises(ConfigurationError, match="fixed by the Slice 1 kernel"):
        Settings.from_env(environment)

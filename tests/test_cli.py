from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from pydantic import SecretStr

from jarvis.cli import StartupDefect, initialize_state, main
from jarvis.config import DiscordSettings
from jarvis.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://jarvis:secret@db/jarvis"),
        discord=DiscordSettings(
            bot_token=SecretStr("private-token"),
            owner_user_id=11,
            guild_id=22,
            channel_id=33,
        ),
        owner_timezone="America/Los_Angeles",
        codex_profile_key="jarvis",
        codex_model="gpt-5.6-terra",
        codex_state_root=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
        google_oauth_state_path=tmp_path / "google.json",
        google_oauth_client_id=SecretStr("synthetic-google-client"),
        google_oauth_client_secret=SecretStr("synthetic-google-secret"),
        connector_encryption_key_version="v2",
        connector_encryption_keys=SecretStr("synthetic-keyring"),
        connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
        maps_api_key=SecretStr("synthetic-maps-key"),
        brave_api_key=SecretStr("synthetic-brave-key"),
    )


def test_initialize_state_creates_private_content_free_host_state(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    initialize_state(settings)

    assert stat.S_IMODE(settings.runtime_state_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(settings.provider_cwd_parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(settings.paused_state_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.admission_journal_path.stat().st_mode) == 0o600
    assert json.loads(settings.paused_state_path.read_text()) == {
        "paused": False,
        "schema_version": "jarvis-paused.v1",
    }
    admission = settings.admission_journal_path.read_text()
    assert "private-token" not in admission
    assert "secret" not in admission


def test_initialize_state_refuses_to_replace_existing_state(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_state(settings)
    with pytest.raises(StartupDefect):
        initialize_state(settings)


def test_initialize_state_rejects_nonprivate_runtime_directory(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.runtime_state_directory.mkdir(mode=0o755)
    settings.runtime_state_directory.chmod(0o755)
    with pytest.raises(StartupDefect):
        initialize_state(settings)


def test_cli_rejects_retired_model_before_serve_or_runtime_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_called = False

    async def serve_spy(settings: Settings) -> None:
        nonlocal serve_called
        del settings
        serve_called = True

    environment = {
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
        "JARVIS_GOOGLE_OAUTH_STATE_PATH": str(tmp_path / "google.json"),
        "JARVIS_GOOGLE_OAUTH_CLIENT_ID": "synthetic-google-client",
        "JARVIS_GOOGLE_OAUTH_CLIENT_SECRET": "synthetic-google-secret",
        "JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION": "v2",
        "JARVIS_CONNECTOR_ENCRYPTION_KEYS": "synthetic-keyring",
        "JARVIS_CONNECTOR_ENCRYPTION_SECRET": "synthetic-encryption-secret",
        "JARVIS_MAPS_API_KEY": "synthetic-maps-key",
        "JARVIS_BRAVE_API_KEY": "synthetic-brave-key",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("JARVIS_MAXIMUM_PROCESSING_ATTEMPTS", raising=False)
    monkeypatch.setattr("jarvis.cli.serve", serve_spy)

    assert main(("serve",)) == 1
    assert not serve_called
    assert not (tmp_path / "runtime").exists()

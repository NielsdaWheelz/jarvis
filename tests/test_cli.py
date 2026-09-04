from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from pydantic import SecretStr

from jarvis.cli import StartupDefect, initialize_state
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
        codex_model="gpt-5.4",
        codex_state_root=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
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

from __future__ import annotations

import grp
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr

from jarvis.cli import (
    StartupDefect,
    initialize_state,
    main,
    recover_startup_actions,
)
from jarvis.codex_control import CodexHostConfig
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
        codex_profile_key="personal",
        codex_model="gpt-5.6-terra",
        codex_host_config_path=tmp_path / "codex-profiles.json",
        runtime_state_directory=tmp_path / "runtime",
        google_oauth_state_path=tmp_path / "google.json",
        google_oauth_client_id=SecretStr("synthetic-google-client"),
        google_oauth_client_secret=SecretStr("synthetic-google-secret"),
        verified_owner_only_calendar_ids=("primary",),
        connector_encryption_key_version="v2",
        connector_encryption_keys=SecretStr("synthetic-keyring"),
        connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
        maps_api_key=SecretStr("synthetic-maps-key"),
        brave_api_key=SecretStr("synthetic-brave-key"),
        embedding_openai_api_key=SecretStr("synthetic-embedding-key"),
    )


def _host(tmp_path: Path) -> CodexHostConfig:
    return CodexHostConfig.model_validate(
        {
            "schema_version": 1,
            "version": "0.153.4",
            "package": {
                "name": "@openai/codex",
                "integrity": "sha512-" + "a" * 86 + "==",
                "shasum": "a" * 40,
            },
            "development_user": "synthetic",
            "jarvis_user": "jarvis",
            "client_group": grp.getgrgid(os.getgid()).gr_name,
            "binary": "/synthetic/codex",
            "tmux": "/synthetic/tmux",
            "cognition_cwd_parent": str(tmp_path / "cognition"),
            "launcher_socket": str(tmp_path / "helper.sock"),
            "profiles": {
                profile: {
                    "account_home": f"/synthetic/{profile}",
                    "endpoint": f"unix://{tmp_path}/{profile}.sock",
                    "work_roots": [str(tmp_path)],
                }
                for profile in ("personal", "work", "work2")
            },
        }
    )


def _create_cognition_parent(host: CodexHostConfig) -> Path:
    path = Path(host.cognition_cwd_parent)
    path.mkdir(mode=0o750)
    path.chmod(0o2750)
    return path


def test_initialize_state_creates_private_content_free_host_state(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    host = _host(tmp_path)
    cognition = _create_cognition_parent(host)
    initialize_state(settings, host)

    assert stat.S_IMODE(settings.runtime_state_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(cognition.stat().st_mode) == 0o2750
    assert list(cognition.iterdir()) == []
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
    host = _host(tmp_path)
    _create_cognition_parent(host)
    initialize_state(settings, host)
    with pytest.raises(StartupDefect):
        initialize_state(settings, host)


def test_initialize_state_rejects_nonprivate_runtime_directory(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    host = _host(tmp_path)
    _create_cognition_parent(host)
    settings.runtime_state_directory.mkdir(mode=0o755)
    settings.runtime_state_directory.chmod(0o755)
    with pytest.raises(StartupDefect):
        initialize_state(settings, host)


def test_initialize_state_rejects_cognition_parent_without_setgid(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    host = _host(tmp_path)
    Path(host.cognition_cwd_parent).mkdir(mode=0o750)

    with pytest.raises(StartupDefect, match="cognition cwd parent"):
        initialize_state(settings, host)

    assert not settings.runtime_state_directory.exists()


def test_initialize_state_rejects_wrong_cognition_parent_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    host = _host(tmp_path)
    _create_cognition_parent(host)

    def wrong_group(_name: str) -> SimpleNamespace:
        return SimpleNamespace(gr_gid=os.getgid() + 1)

    monkeypatch.setattr("jarvis.cli.grp.getgrnam", wrong_group)

    with pytest.raises(StartupDefect, match="cognition cwd parent"):
        initialize_state(settings, host)

    assert not settings.runtime_state_directory.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("paused", "circuit_open", "expected"),
    ((True, False, False), (False, True, False), (False, False, True)),
)
async def test_startup_recovery_enters_queued_writes_only_while_active(
    paused: bool,
    circuit_open: bool,
    expected: bool,
) -> None:
    class _Paused:
        async def is_paused(self) -> bool:
            return paused

    class _Messages:
        async def circuit_is_open(self) -> bool:
            return circuit_open

    class _Recovery:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        async def recover(self, *, allow_queued_execution: bool = True) -> int:
            self.calls.append(allow_queued_execution)
            return 1

    recovery = _Recovery()
    assert (
        await recover_startup_actions(
            action_recovery=cast("Any", recovery),
            paused=cast("Any", _Paused()),
            messages=cast("Any", _Messages()),
        )
        == 1
    )
    assert recovery.calls == [expected]


def test_cli_rejects_retired_model_before_serve_or_runtime_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_called = False

    async def serve_spy(settings: Settings, host: CodexHostConfig) -> None:
        nonlocal serve_called
        del settings, host
        serve_called = True

    environment = {
        "JARVIS_DATABASE_URL": "postgresql+psycopg://jarvis:secret@db/jarvis",
        "JARVIS_DISCORD_BOT_TOKEN": "private-token",
        "JARVIS_DISCORD_OWNER_USER_ID": "11",
        "JARVIS_DISCORD_GUILD_ID": "22",
        "JARVIS_DISCORD_CHANNEL_ID": "33",
        "JARVIS_OWNER_TIMEZONE": "America/Los_Angeles",
        "JARVIS_CODEX_PROFILE_KEY": "personal",
        "JARVIS_CODEX_MODEL": "gpt-5.4",
        "JARVIS_CODEX_HOST_CONFIG_PATH": str(tmp_path / "codex-profiles.json"),
        "JARVIS_RUNTIME_STATE_DIRECTORY": str(tmp_path / "runtime"),
        "JARVIS_GOOGLE_OAUTH_STATE_PATH": str(tmp_path / "google.json"),
        "JARVIS_GOOGLE_OAUTH_CLIENT_ID": "synthetic-google-client",
        "JARVIS_GOOGLE_OAUTH_CLIENT_SECRET": "synthetic-google-secret",
        "JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION": "v2",
        "JARVIS_CONNECTOR_ENCRYPTION_KEYS": "synthetic-keyring",
        "JARVIS_CONNECTOR_ENCRYPTION_SECRET": "synthetic-encryption-secret",
        "JARVIS_MAPS_API_KEY": "synthetic-maps-key",
        "JARVIS_BRAVE_API_KEY": "synthetic-brave-key",
        "JARVIS_EMBEDDING_OPENAI_API_KEY": "synthetic-embedding-key",
        "JARVIS_EMBEDDING_MODEL": "text-embedding-3-small",
        "JARVIS_EMBEDDING_DIMENSION": "1536",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("JARVIS_MAXIMUM_PROCESSING_ATTEMPTS", raising=False)
    monkeypatch.setattr("jarvis.cli.serve", serve_spy)

    assert main(("serve",)) == 1
    assert not serve_called
    assert not (tmp_path / "runtime").exists()


def test_manual_dream_cli_reads_one_host_snapshot_and_reports_only_mutation_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    host = _host(tmp_path)
    host_reads = 0
    created = (UUID(int=1), UUID(int=2))
    removed = (UUID(int=3),)

    def load_host(_settings: Settings) -> CodexHostConfig:
        nonlocal host_reads
        host_reads += 1
        return host

    async def run(selected: Settings, selected_host: CodexHostConfig) -> object:
        assert selected is settings
        assert selected_host is host
        return SimpleNamespace(
            created_summary_ids=created,
            removed_summary_ids=removed,
        )

    monkeypatch.setattr(Settings, "from_env", staticmethod(lambda: settings))
    monkeypatch.setattr(
        Settings,
        "codex_host_config",
        property(load_host),
    )
    monkeypatch.setattr("jarvis.cli.dream_once", run)

    assert main(("dream",)) == 0
    assert host_reads == 1
    assert capsys.readouterr().out == "Dream completed: inserted=2 removed=1.\n"


def test_rebuild_cli_reports_only_production_corpus_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    host = _host(tmp_path)

    async def run(selected: Settings, selected_host: CodexHostConfig) -> object:
        assert selected is settings
        assert selected_host is host
        return SimpleNamespace(
            raw_memory_count=12,
            summaries_after=1,
        )

    monkeypatch.setattr(Settings, "from_env", staticmethod(lambda: settings))
    monkeypatch.setattr(
        Settings,
        "codex_host_config",
        property(lambda _settings: host),
    )
    monkeypatch.setattr("jarvis.cli.rebuild_memory", run)

    assert main(("rebuild-memory",)) == 0
    assert capsys.readouterr().out == (
        "Memory rebuild completed: raw=12 summaries=1.\n"
    )

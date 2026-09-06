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
        "JARVIS_CODEX_MODEL": "gpt-5.6-terra",
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
        "JARVIS_EMBEDDING_OPENAI_API_KEY": "synthetic-embedding-key",
        "JARVIS_EMBEDDING_MODEL": "text-embedding-3-small",
        "JARVIS_EMBEDDING_DIMENSION": "1536",
    }


def test_settings_compose_discord_and_derive_private_paths(tmp_path: Path) -> None:
    settings = Settings.from_env(_environment(tmp_path))

    assert settings.codex_model == "gpt-5.6-terra"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimension == 1536
    assert settings.discord.channel_id == 33
    assert settings.paused_state_path == tmp_path / "runtime" / "paused.json"
    assert settings.admission_journal_path == tmp_path / "runtime" / "admission.json"
    assert settings.session_reference_path == tmp_path / "runtime" / "session-ref.json"
    assert settings.provider_cwd_parent == tmp_path / "runtime" / "provider-cwd"
    assert settings.google_oauth_state_path == tmp_path / "google.json"
    assert "synthetic-maps-key" in settings.host_secrets
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


@pytest.mark.parametrize(
    "name",
    [
        "JARVIS_EMBEDDING_OPENAI_API_KEY",
        "JARVIS_EMBEDDING_MODEL",
        "JARVIS_EMBEDDING_DIMENSION",
    ],
)
def test_settings_require_embedding_configuration(tmp_path: Path, name: str) -> None:
    environment = _environment(tmp_path)
    del environment[name]
    with pytest.raises(ConfigurationError, match=f"missing required setting: {name}"):
        Settings.from_env(environment)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JARVIS_EMBEDDING_MODEL", "text-embedding-3-large"),
        ("JARVIS_EMBEDDING_DIMENSION", "512"),
    ],
)
def test_settings_reject_embedding_identity_drift(
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    environment = _environment(tmp_path)
    environment[name] = value
    with pytest.raises(ConfigurationError, match=f"{name} must be"):
        Settings.from_env(environment)


def test_settings_reject_retired_codex_model_before_state_creation(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    environment["JARVIS_CODEX_MODEL"] = "gpt-5.4"

    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)

    assert not (tmp_path / "runtime").exists()


def test_settings_reject_obsolete_processing_attempt_override(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["JARVIS_MAXIMUM_PROCESSING_ATTEMPTS"] = "3"
    with pytest.raises(ConfigurationError, match="fixed by the Slice 1 kernel"):
        Settings.from_env(environment)


def test_settings_exposes_each_host_secret_without_rendering_it(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["JARVIS_CONNECTOR_ENCRYPTION_KEYS"] = '{"v2":" bare-key-value "}'
    settings = Settings.from_env(environment)

    assert "bare-key-value" in settings.host_secrets
    assert "synthetic-embedding-key" in settings.host_secrets
    assert "bare-key-value" not in repr(settings)
    assert "synthetic-embedding-key" not in repr(settings)

    environment["JARVIS_CONNECTOR_ENCRYPTION_KEYS"] = "v2: version-key-value"
    settings = Settings.from_env(environment)
    assert "version-key-value" in settings.host_secrets

    environment["JARVIS_EMBEDDING_OPENAI_API_KEY"] = " embedding-key"
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)

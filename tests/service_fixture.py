from __future__ import annotations

import asyncio
import grp
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import SecretStr

from jarvis.codex_control import CodexHostConfig
from jarvis.config import DiscordSettings
from jarvis.discord import DiscordGateway
from jarvis.service import JarvisService
from jarvis.settings import Settings


def service_settings(tmp_path: Path) -> Settings:
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


def host_config(tmp_path: Path) -> CodexHostConfig:
    return CodexHostConfig.model_validate(
        {
            "schema_version": 2,
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


class LocalGateway(DiscordGateway):
    """Only the network connection is substituted; ingress/drain stay real."""

    def __init__(self, service: JarvisService, settings: Settings) -> None:
        super().__init__(
            settings.discord,
            service.receive_owner_message,
            approval_interaction_sink=service.receive_approval_interaction,
        )
        self.started = asyncio.Event()
        self.closed = asyncio.Event()
        self.stopped = asyncio.Event()

    def stop_ingress(self) -> None:
        super().stop_ingress()
        self.stopped.set()

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        self.started.set()
        await self.closed.wait()

    async def close(self) -> None:
        self.closed.set()
        await asyncio.sleep(0)

    @asynccontextmanager
    async def typing(self) -> AsyncIterator[None]:
        yield

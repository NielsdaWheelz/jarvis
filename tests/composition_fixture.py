"""Real current tool composition with inert, explicit test ports."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import cast

import httpx
from llm_agent_kernel import ProviderConfiguration
from llm_tools import ToolCatalog, ToolFamily
from pydantic import SecretStr

from jarvis.actions import ActionStore
from jarvis.agent_control import AgentController
from jarvis.config import DiscordSettings
from jarvis.definitions import build_write_gate
from jarvis.memory_retrieval import MemoryEmbedder, MemoryRepository
from jarvis.settings import Settings
from jarvis.tool_composition import build_tool_composition


class ActionsFixture:
    async def stage_gmail_update_basis(self, **values: object) -> object:
        raise AssertionError(values)

    async def schedule_target(self, action_id: object) -> object:
        raise AssertionError(action_id)

    async def stage_external_attempts(self, **values: object) -> object:
        raise AssertionError(values)


class MemoryRepositoryFixture:
    async def search(self, *args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))

    async def open(self, *args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))


class MemoryEmbedderFixture:
    async def embed(self, values: object) -> object:
        raise AssertionError(values)


def composition_settings(tmp_path: Path) -> Settings:
    key = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    return Settings(
        database_url=SecretStr("postgresql://synthetic"),
        discord=DiscordSettings(
            bot_token=SecretStr("synthetic-discord-token"),
            owner_user_id=1,
            guild_id=2,
            channel_id=3,
        ),
        owner_timezone="UTC",
        codex_profile_key="personal",
        codex_model="gpt-5.6-terra",
        agent_cli_path=tmp_path / "skid",
        agent_client_config_path=tmp_path / "agent-client.json",
        codex_host_config_path=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
        google_oauth_state_path=tmp_path / "google.json",
        google_oauth_client_id=SecretStr("synthetic-google-client"),
        google_oauth_client_secret=SecretStr("synthetic-google-secret"),
        connector_encryption_key_version="v2",
        connector_encryption_keys=SecretStr(json.dumps({"v2": key})),
        connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
        maps_api_key=SecretStr("synthetic-maps-key"),
        brave_api_key=SecretStr("synthetic-brave-key"),
        embedding_openai_api_key=SecretStr("synthetic-embedding-key"),
        verified_owner_only_calendar_ids=("owner@example.invalid",),
    )


def build_test_catalog(
    settings: Settings,
    http: httpx.AsyncClient,
    provider: ProviderConfiguration,
    *,
    memory_repository: MemoryRepository,
    memory_embedder: MemoryEmbedder,
) -> ToolCatalog:
    gate, _ = build_write_gate(provider=provider)
    actions = cast(ActionStore, ActionsFixture())
    return build_tool_composition(
        settings=settings,
        google_oauth_http=http,
        google_api_http=http,
        maps_http=http,
        brave_http=http,
        memory_repository=memory_repository,
        memory_embedder=memory_embedder,
        actions=actions,
        agents=AgentController(
            executable=settings.agent_cli_path,
            client_config=settings.agent_client_config_path,
            actions=actions,
        ),
        automatic_write_gate_definition_fingerprint=gate.fingerprint,
    ).catalog


def with_read_bindings(catalog: ToolCatalog, reads: ToolCatalog) -> ToolCatalog:
    replacements = set(reads.tool_ids)
    families: list[ToolFamily] = []
    for namespace in catalog.family_names:
        bindings = tuple(
            (reads if tool_id in replacements else catalog).binding(tool_id)
            for tool_id in catalog.tool_ids
            if str(tool_id).split(".", 1)[0] == namespace
        )
        families.append(
            ToolFamily(namespace, tuple(binding.spec for binding in bindings), bindings)
        )
    return ToolCatalog.compose(families)

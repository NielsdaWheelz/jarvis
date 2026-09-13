from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import httpx
from llm_agent_kernel import SessionMode, StructuredOutput, require_host_plan
from llm_tools import Available, PromptText, ToolId, Unavailable, canonical_json_bytes
from provider_fixture import frozen_provider
from pydantic import SecretStr

from jarvis.actions import ActionStore
from jarvis.agent_control import AgentController
from jarvis.agent_tools import AGENT_TOOL_IDS
from jarvis.config import DiscordSettings
from jarvis.db import create_engine
from jarvis.definitions import (
    SLICE2_READ_IDS,
    SLICE3_MEMORY_READ_IDS,
    SLICE5_KERNEL_LIMITS,
    SLICE5_PLAN_TOOL_LIMITS,
    SLICE5_TOOL_LIMITS,
    SLICE5_WRITE_IDS,
    SLICE6_KERNEL_LIMITS,
    SLICE6_PLAN_TOOL_LIMITS,
    SLICE6_TOOL_LIMITS,
    SLICE6_WRITE_IDS,
    build_slice5_definitions,
    build_slice5_write_gate,
    build_slice6_definitions,
    load_session_manifest,
    session_compatibility_revision,
)
from jarvis.settings import Settings
from jarvis.terminal import JarvisTerminal
from jarvis.write_composition import build_slice5_catalog, build_slice6_catalog


class _Actions:
    async def stage_gmail_update_basis(self, **values: object) -> object:
        raise AssertionError(values)

    async def schedule_target(self, action_id: object) -> object:
        raise AssertionError(action_id)

    async def stage_external_attempts(self, **values: object) -> object:
        raise AssertionError(values)


class _MemoryRepository:
    async def search(self, *args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))

    async def open(self, *args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))


class _MemoryEmbedder:
    async def embed(self, values: object) -> object:
        raise AssertionError(values)


def _settings(tmp_path: Path) -> Settings:
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


async def test_slice5_catalog_has_exact_maximum_surface_and_unavailable_send(
    tmp_path: Path,
) -> None:
    clients = tuple(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            ),
            trust_env=False,
            follow_redirects=False,
        )
        for _ in range(4)
    )
    try:
        catalog = build_slice5_catalog(
            settings=_settings(tmp_path),
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
            memory_repository=cast("Any", _MemoryRepository()),
            memory_embedder=cast("Any", _MemoryEmbedder()),
            actions=cast("Any", _Actions()),
            automatic_write_gate_definition_fingerprint="a" * 64,
        )
        rotated = build_slice5_catalog(
            settings=_settings(tmp_path),
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
            memory_repository=cast("Any", _MemoryRepository()),
            memory_embedder=cast("Any", _MemoryEmbedder()),
            actions=cast("Any", _Actions()),
            automatic_write_gate_definition_fingerprint="b" * 64,
        )
        gate, _ = build_slice5_write_gate(
            provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
        )
        production_catalog = build_slice5_catalog(
            settings=_settings(tmp_path),
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
            memory_repository=cast("Any", _MemoryRepository()),
            memory_embedder=cast("Any", _MemoryEmbedder()),
            actions=cast("Any", _Actions()),
            automatic_write_gate_definition_fingerprint=gate.fingerprint,
        )
    finally:
        for client in clients:
            await client.aclose()

    assert frozenset(catalog.tool_ids) == {
        ToolId("gmail.search"),
        ToolId("gmail.read_thread"),
        ToolId("gmail.create_draft"),
        ToolId("gmail.update_draft"),
        ToolId("gmail.send_draft"),
        ToolId("calendar.list_events"),
        ToolId("calendar.list_calendars"),
        ToolId("calendar.get_event"),
        ToolId("calendar.create_event"),
        ToolId("calendar.update_event"),
        ToolId("calendar.delete_event"),
        ToolId("maps.search_places"),
        ToolId("maps.get_place"),
        ToolId("maps.directions"),
        ToolId("web.search"),
        ToolId("web.read"),
        ToolId("memory.search"),
        ToolId("memory.open"),
        ToolId("schedule.wake"),
    }
    for tool_id in catalog.tool_ids:
        execute = catalog.binding(tool_id).execute
        if tool_id == ToolId("gmail.send_draft"):
            assert isinstance(execute, Unavailable)
        else:
            assert isinstance(execute, Available)
    assert catalog.binding(ToolId("schedule.wake")).implementation_revision == (
        "jarvis-schedule-wake-v1"
    )
    assert catalog.binding(ToolId("calendar.create_event")).implementation_revision == (
        "jarvis-calendar-create_event-v1"
    )
    assert catalog.binding(ToolId("gmail.create_draft")).implementation_revision == (
        "jarvis-gmail-create_draft-v1"
    )
    assert catalog.binding(ToolId("gmail.update_draft")).policy_inputs == {
        "action_max_attempts": 2,
        "authority": "automatic-write-gated",
        "conflict_check": "exact-normalized-content-digest",
        "effect_header": "preserve-X-Jarvis-Effect-ID",
        "reconciliation_max_thread_messages": 100,
        "reconciliation_thread_read": (
            "threads.get(format=minimal)-then-messages.get(format=raw)"
        ),
        "send": False,
        "automatic_write_gate_definition_fingerprint": "a" * 64,
    }
    calendar = catalog.binding(ToolId("calendar.create_event"))
    assert calendar.policy_inputs["verified_owner_calendar_ids_digest"] == (
        hashlib.sha256(canonical_json_bytes(["owner@example.invalid"])).hexdigest()
    )
    assert "owner@example.invalid" not in json.dumps(dict(calendar.policy_inputs))
    assert (
        rotated.binding(ToolId("gmail.create_draft")).policy_revision
        != catalog.binding(ToolId("gmail.create_draft")).policy_revision
    )
    assert (
        rotated.binding(ToolId("gmail.search")).policy_revision
        == catalog.binding(ToolId("gmail.search")).policy_revision
    )

    definitions = build_slice5_definitions(
        catalog=production_catalog,
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
        owner_timezone="UTC",
    )
    assert definitions.main.limits == SLICE5_KERNEL_LIMITS
    assert definitions.main.maximum_profile.run_limits == SLICE5_TOOL_LIMITS
    assert definitions.plans["main"].profile.run_limits == SLICE5_PLAN_TOOL_LIMITS
    assert set(definitions.main.maximum_profile.grants) == set(
        (*SLICE2_READ_IDS, *SLICE5_WRITE_IDS)
    )
    assert set(definitions.plans["main"].profile.grants) == set(catalog.tool_ids) - {
        *SLICE3_MEMORY_READ_IDS,
        ToolId("gmail.send_draft"),
    }
    assert set(definitions.plans["scheduled_wake"].profile.grants) == set(
        SLICE2_READ_IDS
    )
    assert not definitions.automatic_write_gate.maximum_profile.grants
    assert not definitions.plans["automatic_write_gate"].profile.grants
    manifest = load_session_manifest()
    for role in ("main", "recaller", "rememberer", "dreamer", "automatic_write_gate"):
        assert getattr(definitions, role).session_compatibility_revision == (
            session_compatibility_revision(manifest, role)
        )


async def test_slice6_catalog_and_plans_select_every_qualified_binding(
    tmp_path: Path,
) -> None:
    clients = tuple(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            ),
            trust_env=False,
            follow_redirects=False,
        )
        for _ in range(4)
    )
    gate, _ = build_slice5_write_gate(
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
    )
    try:
        catalog = build_slice6_catalog(
            settings=_settings(tmp_path),
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
            memory_repository=cast("Any", _MemoryRepository()),
            memory_embedder=cast("Any", _MemoryEmbedder()),
            actions=cast("Any", _Actions()),
            agents=AgentController(
                executable=tmp_path / "skid",
                client_config=tmp_path / "agent-client.json",
                actions=ActionStore(
                    create_engine(
                        "postgresql+psycopg://unused:unused@127.0.0.1:1/unused"
                    )
                ),
            ),
            automatic_write_gate_definition_fingerprint=gate.fingerprint,
        )
    finally:
        for client in clients:
            await client.aclose()

    assert all(
        isinstance(catalog.binding(tool_id).execute, Available)
        for tool_id in catalog.tool_ids
    )
    assert set(AGENT_TOOL_IDS) <= set(catalog.tool_ids)
    send = catalog.binding(ToolId("gmail.send_draft"))
    assert send.implementation_revision == "jarvis-gmail-send_draft-v1"
    assert send.policy_inputs == {
        "action_max_attempts": 2,
        "authority": "approval-required",
        "automatic_write_gate_definition_fingerprint": gate.fingerprint,
        "effect_header": "preserve-X-Jarvis-Effect-ID",
        "mailbox_search": False,
        "pre_send_check": "exact-normalized-snapshot",
        "reconciliation_backoff_seconds": (0, 2, 8),
        "reconciliation_list_pages": 0,
        "reconciliation_max_elapsed_seconds": 30,
        "reconciliation_max_observations": 3,
        "reconciliation_positive_proof": (
            "one-exact-match-after-bounded-candidates-processed-"
            "with-no-conflicting-evidence"
        ),
        "reconciliation_max_provider_reads_per_observation": 102,
        "reconciliation_max_response_bytes": 16 * 1024 * 1024,
        "reconciliation_max_response_bytes_per_read": 2 * 1024 * 1024,
        "reconciliation_max_thread_messages": 100,
        "reconciliation_thread_minimal_gets_per_observation": 1,
        "reconciliation_thread_raw_message_gets_per_observation": 100,
    }
    definitions = build_slice6_definitions(
        catalog=catalog,
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
        owner_timezone="UTC",
    )
    assert definitions.main.limits == SLICE6_KERNEL_LIMITS
    assert definitions.main.maximum_profile.run_limits == SLICE6_TOOL_LIMITS
    assert definitions.plans["main"].profile.run_limits == SLICE6_PLAN_TOOL_LIMITS
    assert definitions.plans["main"].profile.run_limits.max_external_attempts == sum(
        grant.limits.max_attempts
        for grant in definitions.plans["main"].profile.ordered_grants
    )
    assert definitions.plans["main"].profile.run_limits.max_output_bytes == sum(
        grant.limits.max_output_bytes
        for grant in definitions.plans["main"].profile.ordered_grants
    )
    assert set(definitions.main.maximum_profile.grants) == set(
        (*SLICE2_READ_IDS, *SLICE6_WRITE_IDS, *AGENT_TOOL_IDS)
    )
    assert set(definitions.plans["main"].profile.grants) == set(catalog.tool_ids) - {
        *SLICE3_MEMORY_READ_IDS
    }
    assert set(definitions.plans["scheduled_wake"].profile.grants) == set(
        SLICE2_READ_IDS
    )
    assert not definitions.automatic_write_gate.maximum_profile.grants
    assert not definitions.plans["automatic_write_gate"].profile.grants
    assert definitions.main.session_mode is SessionMode.continuing
    assert isinstance(definitions.main.output_contract, StructuredOutput)
    assert definitions.main.output_contract.name == "jarvis_terminal"
    assert definitions.main.output_contract.result_type is JarvisTerminal
    main_body = definitions.main.role.instructions.sections[0].body
    assert isinstance(main_body, PromptText)
    main_instructions = main_body.text
    assert "write all prose responses in lowercase" in main_instructions
    assert "never use horizontal rules or emojis" in main_instructions
    assert "critique the owner's ideas assertively" in main_instructions
    assert "do not search the public web unless the owner explicitly requests" in (
        main_instructions
    )
    owner_context = definitions.main.stable_context.sections
    assert len(owner_context) == 1
    assert owner_context[0].kind == "owner_context"
    owner_body = owner_context[0].body
    assert isinstance(owner_body, PromptText)
    assert "neuroscientist by training" in owner_body.text
    assert "maintain an accurate view of active commitments" in owner_body.text
    assert "proactively surface what deserves attention" in owner_body.text
    for role in (
        definitions.recaller,
        definitions.rememberer,
        definitions.dreamer,
        definitions.automatic_write_gate,
    ):
        rendered = "\n".join(
            section.body.text if isinstance(section.body, PromptText) else ""
            for sections in (role.role.instructions, role.stable_context)
            for section in sections.sections
        )
        assert "neuroscientist by training" not in rendered
        assert "write all prose responses in lowercase" not in rendered
    assert definitions.main.maximum_profile.run_limits.max_external_attempts == 250
    assert definitions.plans["main"].profile.run_limits.max_external_attempts == 249
    assert (
        definitions.plans["scheduled_wake"].profile.run_limits.max_external_attempts
        == 222
    )
    for role in ("recaller", "rememberer", "dreamer", "automatic_write_gate"):
        assert getattr(definitions, role).session_mode is SessionMode.isolated
    for name in definitions.plans:
        role = "main" if name in {"proactive", "scheduled_wake"} else name
        require_host_plan(
            definitions.plans[name], getattr(definitions, role).maximum_profile
        )
    manifest = load_session_manifest()
    for role in ("main", "recaller", "rememberer", "dreamer", "automatic_write_gate"):
        assert getattr(definitions, role).session_compatibility_revision == (
            session_compatibility_revision(manifest, role)
        )

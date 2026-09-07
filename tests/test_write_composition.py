from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import httpx
from llm_tools import Available, ToolId, Unavailable, canonical_json_bytes
from pydantic import SecretStr

from jarvis.config import DiscordSettings
from jarvis.definitions import (
    SLICE2_READ_IDS,
    SLICE3_MEMORY_READ_IDS,
    SLICE5_KERNEL_LIMITS,
    SLICE5_PLAN_TOOL_LIMITS,
    SLICE5_TOOL_LIMITS,
    SLICE5_WRITE_IDS,
    build_slice5_definitions,
    build_slice5_write_gate,
)
from jarvis.settings import Settings
from jarvis.write_composition import build_slice5_catalog


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
        codex_profile_key="synthetic-profile",
        codex_model="gpt-5.6-terra",
        codex_state_root=tmp_path / "codex",
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
            profile_key="synthetic-profile",
            model="gpt-5.6-terra",
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
        profile_key="synthetic-profile",
        model="gpt-5.6-terra",
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
    assert {
        role: (
            getattr(definitions, role).fingerprint,
            getattr(definitions, role).session_compatibility_revision,
            getattr(definitions, role).maximum_profile.profile_revision,
            definitions.plans[role].profile.profile_revision,
            definitions.plans[role].plan_revision,
        )
        for role in (
            "main",
            "recaller",
            "rememberer",
            "dreamer",
            "automatic_write_gate",
        )
    } == {
        "main": (
            "5785c000e362b2c2dcede24174441203425e1794cee66c39f2c6893ddeaee21d",
            "3cfd944608017249a0e1effbf5cd5fe3b389020a200a217a69c43990173ee6c8",
            "6a8d3701f30f7503eed7f67f2931fbf786faec8b7e19b01c7e7680deff34cb88",
            "882eaa5b077240fdd9c534bc8597c15cce62681eb558f41fe03335392ac9e936",
            "9999bf4578b6736648ea72d3b2610d35b8cdcee1b733241935e336f9c5daf276",
        ),
        "recaller": (
            "da152298a4e9f049f0527bfdce96c9d413f4d4d1f4144813678b8e60e59edad6",
            "0fede7ec8ab388ce3f6105c61a33d46f8a2912b026a9b00e292862615bfa39b3",
            "387ca49d3d87a1a248f55cce95dcb2a30689f51ee5bf7b9ecf682b2851ba606c",
            "dcfa0050e27f642a83528e17adabb9f94c1f5c2046990cf251ee32df661c2d4b",
            "c5d4e2c79f8d3998d152ebfb52ec9a6c2ec89a7158f85ba3f54fc4be71e53762",
        ),
        "rememberer": (
            "1a0205f12021519079521e08427b4d2d9fa884d0fe8991c622961771c8b6d1c9",
            "6a126ce2c500d900291c35d51a44eda4bba24c816383453b5dc1649865e3738b",
            "fe859b737c31f69c6a5d7cd8bcaadcd318c280c311fb5644e0f60320172f9ac0",
            "23193d7294cfc0f72d01363b1083c8649e18ad4e56521174ecddc1b29a7c4573",
            "1cfe0ca344984bc0d3b19fcc22d71a0dd17ca1034d7a289b41566b8dba3f78b9",
        ),
        "dreamer": (
            "c13d4141126aa593e22c353e183ca94d20d1d0c267de0413df265bf965506b42",
            "9a4a5404789ea51172d8cb429e31a875fecad1ced5f7fb39b39f18f872a12122",
            "afdaf4bd040f91b00f71331e61904589513e54d83969b6c3463194de03fde6a9",
            "a0093aafc10503a84df98b86dd3204d4bff30a7e82a0cea5847a6b8c8fd8a596",
            "74067b9fe62110e22487557d816554a8fb355ea173b82051afa6f5dbf032809a",
        ),
        "automatic_write_gate": (
            "233504c37b55dbb86c7b93a8e2366e30e83b8e1231da648ff4babf72aeb06c0e",
            "2c453f5b070233f697387ce2235e2d107566216bd45af11fd659ecb70f330aa4",
            "2e5e7ccf6a3c4aa5b0d5e3deb537c53570f60371e66b35c2d37ffb8f920e0ba8",
            "c5cc8b6e90865e51264587ea43317d7529287e7100c21953250f93ae330ef688",
            "22bc6fcc0399068ad4b83046855b9218a25cb1a424e69f06d50def7f3a70d38a",
        ),
    }
    assert (
        definitions.plans["scheduled_wake"].profile.profile_revision,
        definitions.plans["scheduled_wake"].plan_revision,
    ) == (
        "e978fb5ee1276aef4e5cdf9b57ab6337b6264d75570b480a999a2cce88276f5b",
        "d818b1f8cfad6faaa856fc5baf14a9438d6e8a5cf80b13b63f0bcb5f84ff3897",
    )

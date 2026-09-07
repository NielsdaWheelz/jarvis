from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from llm_tools import ToolEffect, ToolId
from pydantic import SecretStr

from jarvis.config import DiscordSettings
from jarvis.definitions import (
    SLICE2_READ_IDS,
    build_slice5_definitions,
    build_slice5_write_gate,
)
from jarvis.settings import Settings
from jarvis.write_composition import build_slice5_catalog

ROOT = Path(__file__).resolve().parents[1]
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_proactivity.py"))
_RecordingDelivery = _QUALIFIER["_RecordingDelivery"]
assert_sanitized_output = _QUALIFIER["assert_sanitized_output"]
cleanup_discord = _QUALIFIER["_cleanup_discord"]
main = _QUALIFIER["main"]
proactive_plan_evidence = _QUALIFIER["proactive_plan_evidence"]
validate_result_evidence = _QUALIFIER["validate_result_evidence"]


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


async def test_proactivity_qualifier_uses_exact_read_only_plan_without_recall(
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
        gate, _ = build_slice5_write_gate(
            profile_key="synthetic-profile",
            model="gpt-5.6-terra",
        )
        catalog = build_slice5_catalog(
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
        definitions = build_slice5_definitions(
            catalog=catalog,
            profile_key="synthetic-profile",
            model="gpt-5.6-terra",
            owner_timezone="UTC",
        )
    finally:
        for client in clients:
            await client.aclose()

    evidence = proactive_plan_evidence(definitions)

    assert evidence["tool_ids"] == tuple(map(str, SLICE2_READ_IDS))
    assert evidence["read_only"] is True
    assert evidence["recall_available"] is False
    assert definitions.plans["proactive"] is definitions.plans["scheduled_wake"]
    for tool_id in definitions.plans["scheduled_wake"].profile.grants:
        assert not str(tool_id).startswith("memory.")
        assert (
            definitions.plans["scheduled_wake"]
            .catalog_view.binding(tool_id)
            .spec.effect
            is ToolEffect.Read
        )


def _valid_evidence() -> dict[str, object]:
    return {
        "actions": {
            "attempts": 4,
            "cancel": "passed",
            "creation_receipt_replay": "passed",
            "distinct_effects": 4,
            "rows": 4,
        },
        "discord": {
            "delivered": 3,
            "idempotent_resolution": True,
            "removed": 3,
            "visible_fallback": True,
            "visible_model_completion": True,
        },
        "plan": {
            "read_only": True,
            "recall_available": False,
            "tool_ids": tuple(map(str, SLICE2_READ_IDS)),
        },
        "schedule": {
            "exact_due": True,
            "host_wake_count": 2,
            "idempotent_claim": True,
            "overdue_restart": True,
            "wake_outcomes": 2,
        },
        "status": "passed",
        "tool_dispatches": ["web.search"],
    }


def test_qualifier_cannot_report_pass_without_every_schedule_invariant() -> None:
    valid = _valid_evidence()
    validate_result_evidence(valid)
    mutations = (
        ("actions", "attempts", 5),
        ("actions", "cancel", "failed"),
        ("actions", "creation_receipt_replay", "failed"),
        ("actions", "distinct_effects", 3),
        ("actions", "rows", 5),
        ("discord", "delivered", 2),
        ("discord", "idempotent_resolution", False),
        ("discord", "removed", 2),
        ("discord", "visible_fallback", False),
        ("discord", "visible_model_completion", False),
        ("plan", "read_only", False),
        ("plan", "recall_available", True),
        ("schedule", "exact_due", False),
        ("schedule", "host_wake_count", 1),
        ("schedule", "idempotent_claim", False),
        ("schedule", "overdue_restart", False),
        ("schedule", "wake_outcomes", 1),
    )
    for section, key, value in mutations:
        changed = copy.deepcopy(valid)
        cast("dict[str, object]", changed[section])[key] = value
        with pytest.raises(RuntimeError, match="evidence"):
            validate_result_evidence(changed)
    changed = copy.deepcopy(valid)
    cast("dict[str, object]", changed["plan"])["tool_ids"] = (
        *map(str, SLICE2_READ_IDS),
        "memory.search",
    )
    with pytest.raises(RuntimeError, match="evidence"):
        validate_result_evidence(changed)
    changed = copy.deepcopy(valid)
    changed["tool_dispatches"] = ["schedule.wake"]
    with pytest.raises(RuntimeError, match="evidence"):
        validate_result_evidence(changed)


async def test_discord_cleanup_removes_every_recorded_synthetic_message(
    tmp_path: Path,
) -> None:
    deleted: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        deleted.append(request.url.path)
        return httpx.Response(204, request=request)

    settings = _settings(tmp_path)
    delivery = _RecordingDelivery(cast("Any", object()))
    first = uuid4()
    second = uuid4()
    delivery.delivered[first] = ("101", "synthetic one")
    delivery.delivered[second] = ("102", "synthetic two")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        removed = await cleanup_discord(
            delivery=delivery,
            client=client,
            settings=settings,
        )

    assert removed == 2
    assert deleted == [
        "/api/v10/channels/3/messages/101",
        "/api/v10/channels/3/messages/102",
    ]


def test_sanitizer_and_disabled_main_emit_no_private_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(RuntimeError, match="output"):
        assert_sanitized_output(
            {"status": "passed", "value": "synthetic-private-value"},
            ("synthetic-private-value",),
        )
    monkeypatch.delenv("JARVIS_PROACTIVITY_LIVE", raising=False)
    monkeypatch.setenv("JARVIS_CODEX_MODEL", "gpt-5.6-terra")

    assert main() == 1

    value = json.loads(capsys.readouterr().out)
    assert value == {
        "failure": {
            "reason_code": "unexpected_exception",
            "stage": "setup",
            "type": "ValueError",
        },
        "route": "gpt-5.6-terra",
        "status": "failed",
    }
    assert "JARVIS_PROACTIVITY_LIVE" not in json.dumps(value)
    assert ToolId("schedule.wake") not in SLICE2_READ_IDS

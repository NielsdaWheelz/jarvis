"""Production Slice 5 and Slice 6 tool-catalog composition."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx
from llm_tools import (
    BraveSearchProvider,
    SafeWebReader,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    ToolId,
    Unavailable,
    bind_brave_web_search,
    bind_web_read,
    canonical_json_bytes,
    web_family,
)

from jarvis.actions import ActionStore
from jarvis.codex_control import CodexController
from jarvis.codex_tools import codex_family
from jarvis.connectors import GoogleReadConnector, GoogleTokenManager, MapsReadConnector
from jarvis.memory_retrieval import MemoryEmbedder, MemoryRepository
from jarvis.memory_tools import memory_family
from jarvis.read_tools import maps_family
from jarvis.schedule_tools import schedule_family
from jarvis.settings import Settings
from jarvis.write_connectors import GoogleWriteConnector
from jarvis.write_tools import calendar_main_family, gmail_main_family


@dataclass(frozen=True, slots=True)
class Slice5Composition:
    catalog: ToolCatalog
    google_write: GoogleWriteConnector


@dataclass(frozen=True, slots=True)
class Slice6Composition:
    catalog: ToolCatalog
    google_write: GoogleWriteConnector


def build_slice5_composition(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory_repository: MemoryRepository,
    memory_embedder: MemoryEmbedder,
    actions: ActionStore,
    automatic_write_gate_definition_fingerprint: str,
) -> Slice5Composition:
    if (
        not automatic_write_gate_definition_fingerprint
        or automatic_write_gate_definition_fingerprint
        != automatic_write_gate_definition_fingerprint.strip()
        or len(automatic_write_gate_definition_fingerprint.encode("utf-8")) > 256
    ):
        raise ValueError("write-gate definition fingerprint is invalid")
    calendar_ids_digest = hashlib.sha256(
        canonical_json_bytes(sorted(settings.verified_owner_only_calendar_ids))
    ).hexdigest()
    tokens = GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=google_oauth_http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
        configured_keys=settings.connector_encryption_keys.get_secret_value(),
        single_secret=settings.connector_encryption_secret.get_secret_value(),
    )
    google_read = GoogleReadConnector(client=google_api_http, tokens=tokens)
    google_write = GoogleWriteConnector(
        client=google_api_http,
        tokens=tokens,
        stage_gmail_update_basis=actions.stage_gmail_update_basis,
        stage_external_attempts=actions.stage_external_attempts,
    )
    maps = MapsReadConnector(
        client=maps_http,
        api_key=settings.maps_api_key.get_secret_value(),
    )
    brave = BraveSearchProvider(
        brave_http,
        api_key=settings.brave_api_key.get_secret_value(),
        base_url="https://api.search.brave.com/res/v1",
    )
    schedule = schedule_family(actions)
    if schedule.namespace != "schedule" or tuple(
        binding.spec.id for binding in schedule.bindings
    ) != (ToolId("schedule.wake"),):
        raise RuntimeError(
            "schedule family does not use its canonical Slice 5 identity"
        )
    catalog = ToolCatalog.compose(
        (
            _bind_write_policy(
                _slice5_gmail_family(gmail_main_family(google_read, google_write)),
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=None,
            ),
            _bind_write_policy(
                calendar_main_family(google_read, google_write),
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=calendar_ids_digest,
            ),
            maps_family(maps),
            web_family(
                search=bind_brave_web_search(
                    brave,
                    operation_deadline_seconds=12.0,
                ),
                read=bind_web_read(SafeWebReader()),
            ),
            memory_family(memory_repository, memory_embedder),
            _bind_write_policy(
                schedule,
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=None,
            ),
        )
    )
    send = catalog.binding(ToolId("gmail.send_draft"))
    if not isinstance(send.execute, Unavailable):
        raise RuntimeError("Slice 5 Gmail sending must remain unavailable")
    return Slice5Composition(catalog, google_write)


def build_slice6_composition(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory_repository: MemoryRepository,
    memory_embedder: MemoryEmbedder,
    actions: ActionStore,
    codex: CodexController,
    automatic_write_gate_definition_fingerprint: str,
) -> Slice6Composition:
    if (
        not automatic_write_gate_definition_fingerprint
        or automatic_write_gate_definition_fingerprint
        != automatic_write_gate_definition_fingerprint.strip()
        or len(automatic_write_gate_definition_fingerprint.encode("utf-8")) > 256
    ):
        raise ValueError("write-gate definition fingerprint is invalid")
    calendar_ids_digest = hashlib.sha256(
        canonical_json_bytes(sorted(settings.verified_owner_only_calendar_ids))
    ).hexdigest()
    tokens = GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=google_oauth_http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
        configured_keys=settings.connector_encryption_keys.get_secret_value(),
        single_secret=settings.connector_encryption_secret.get_secret_value(),
    )
    google_read = GoogleReadConnector(client=google_api_http, tokens=tokens)
    google_write = GoogleWriteConnector(
        client=google_api_http,
        tokens=tokens,
        stage_gmail_update_basis=actions.stage_gmail_update_basis,
        stage_external_attempts=actions.stage_external_attempts,
    )
    maps = MapsReadConnector(
        client=maps_http,
        api_key=settings.maps_api_key.get_secret_value(),
    )
    brave = BraveSearchProvider(
        brave_http,
        api_key=settings.brave_api_key.get_secret_value(),
        base_url="https://api.search.brave.com/res/v1",
    )
    schedule = schedule_family(actions)
    if schedule.namespace != "schedule" or tuple(
        binding.spec.id for binding in schedule.bindings
    ) != (ToolId("schedule.wake"),):
        raise RuntimeError("schedule family does not use its canonical identity")
    catalog = ToolCatalog.compose(
        (
            _bind_write_policy(
                codex_family(codex),
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=None,
            ),
            _bind_write_policy(
                gmail_main_family(google_read, google_write),
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=None,
            ),
            _bind_write_policy(
                calendar_main_family(google_read, google_write),
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=calendar_ids_digest,
            ),
            maps_family(maps),
            web_family(
                search=bind_brave_web_search(
                    brave,
                    operation_deadline_seconds=12.0,
                ),
                read=bind_web_read(SafeWebReader()),
            ),
            memory_family(memory_repository, memory_embedder),
            _bind_write_policy(
                schedule,
                gate_fingerprint=automatic_write_gate_definition_fingerprint,
                calendar_ids_digest=None,
            ),
        )
    )
    if any(
        isinstance(catalog.binding(tool_id).execute, Unavailable)
        for tool_id in catalog.tool_ids
    ):
        raise RuntimeError("every Slice 6 binding must be available")
    return Slice6Composition(catalog, google_write)


def build_slice6_catalog(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory_repository: MemoryRepository,
    memory_embedder: MemoryEmbedder,
    actions: ActionStore,
    codex: CodexController,
    automatic_write_gate_definition_fingerprint: str,
) -> ToolCatalog:
    return build_slice6_composition(
        settings=settings,
        google_oauth_http=google_oauth_http,
        google_api_http=google_api_http,
        maps_http=maps_http,
        brave_http=brave_http,
        memory_repository=memory_repository,
        memory_embedder=memory_embedder,
        actions=actions,
        codex=codex,
        automatic_write_gate_definition_fingerprint=(
            automatic_write_gate_definition_fingerprint
        ),
    ).catalog


def build_slice5_catalog(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory_repository: MemoryRepository,
    memory_embedder: MemoryEmbedder,
    actions: ActionStore,
    automatic_write_gate_definition_fingerprint: str,
) -> ToolCatalog:
    return build_slice5_composition(
        settings=settings,
        google_oauth_http=google_oauth_http,
        google_api_http=google_api_http,
        maps_http=maps_http,
        brave_http=brave_http,
        memory_repository=memory_repository,
        memory_embedder=memory_embedder,
        actions=actions,
        automatic_write_gate_definition_fingerprint=(
            automatic_write_gate_definition_fingerprint
        ),
    ).catalog


def _bind_write_policy(
    family: ToolFamily,
    *,
    gate_fingerprint: str,
    calendar_ids_digest: str | None,
) -> ToolFamily:
    bindings: list[ToolBinding[object, object, object]] = []
    for binding in family.bindings:
        if binding.spec.effect is not ToolEffect.Write:
            bindings.append(binding)
            continue
        inputs = {
            **binding.policy_inputs,
            "automatic_write_gate_definition_fingerprint": gate_fingerprint,
        }
        if calendar_ids_digest is not None:
            inputs["verified_owner_calendar_ids_digest"] = calendar_ids_digest
        bindings.append(
            ToolBinding(
                spec=binding.spec,
                execute=binding.execute,
                replay_policy=binding.replay_policy,
                implementation_revision=binding.implementation_revision,
                policy_epoch=binding.policy_epoch,
                policy_inputs=inputs,
            )
        )
    return ToolFamily(family.namespace, family.declarations, tuple(bindings))


def _slice5_gmail_family(family: ToolFamily) -> ToolFamily:
    """Keep the shipped Slice 5 catalog identity after Slice 6 enables sending."""

    bindings: list[ToolBinding[object, object, object]] = []
    for binding in family.bindings:
        if binding.spec.id != ToolId("gmail.send_draft"):
            bindings.append(binding)
            continue
        bindings.append(
            ToolBinding(
                spec=binding.spec,
                execute=Unavailable("Slice 6 approval execution is not implemented"),
                replay_policy=binding.replay_policy,
                implementation_revision=binding.implementation_revision,
                policy_epoch=binding.policy_epoch,
                policy_inputs={
                    "action_max_attempts": 2,
                    "authority": "approval-required-unavailable-slice-5",
                    "effect_header": "preserve-X-Jarvis-Effect-ID",
                },
            )
        )
    return ToolFamily(family.namespace, family.declarations, tuple(bindings))


__all__ = [
    "Slice5Composition",
    "Slice6Composition",
    "build_slice5_catalog",
    "build_slice5_composition",
    "build_slice6_catalog",
    "build_slice6_composition",
]

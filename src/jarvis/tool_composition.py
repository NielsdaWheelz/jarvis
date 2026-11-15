"""Production tool-catalog composition."""

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
    Unavailable,
    bind_brave_web_search,
    bind_web_read,
    canonical_json_bytes,
    web_family,
)

from jarvis.action_requests import bind_action_requests
from jarvis.actions import ActionStore
from jarvis.agent_control import AgentController
from jarvis.agent_tools import agent_family
from jarvis.approval_tools import approval_family
from jarvis.connectors import GoogleReadConnector, GoogleTokenManager, MapsReadConnector
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import memory_family
from jarvis.read_tools import maps_family
from jarvis.settings import Settings
from jarvis.work import WorkStore
from jarvis.work_tools import work_family
from jarvis.write_connectors import GoogleWriteConnector
from jarvis.write_tools import calendar_main_family, gmail_main_family


@dataclass(frozen=True, slots=True)
class ToolComposition:
    catalog: ToolCatalog
    google_write: GoogleWriteConnector


def build_tool_composition(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory: MemoryService,
    actions: ActionStore,
    agents: AgentController,
    work: WorkStore,
) -> ToolComposition:
    calendar_ids_digest = hashlib.sha256(
        canonical_json_bytes(sorted(settings.verified_owner_only_calendar_ids))
    ).hexdigest()
    tokens = GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=google_oauth_http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
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
    catalog = ToolCatalog.compose(
        (
            _bind_write_policy(
                agent_family(agents),
                calendar_ids_digest=None,
            ),
            _bind_write_policy(
                gmail_main_family(google_read, google_write),
                calendar_ids_digest=None,
            ),
            _bind_write_policy(
                calendar_main_family(google_read, google_write),
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
            memory_family(memory),
            approval_family(),
            _bind_write_policy(work_family(work), calendar_ids_digest=None),
        )
    )
    if any(
        isinstance(catalog.binding(tool_id).execute, Unavailable)
        for tool_id in catalog.tool_ids
    ):
        raise RuntimeError("every application binding must be available")
    return ToolComposition(catalog, google_write)


def _bind_write_policy(
    family: ToolFamily,
    *,
    calendar_ids_digest: str | None,
) -> ToolFamily:
    bindings: list[ToolBinding[object, object, object]] = []
    for binding in family.bindings:
        if binding.spec.effect is not ToolEffect.Write:
            bindings.append(binding)
            continue
        inputs = {
            **binding.policy_inputs,
            "action_authority": "jarvis.action.v2",
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
    return bind_action_requests(
        ToolFamily(family.namespace, family.declarations, tuple(bindings))
    )


__all__ = ["ToolComposition", "build_tool_composition"]

"""Production tool-catalog composition."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

import boto3  # pyright: ignore[reportMissingTypeStubs]
import httpx
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]
from llm_tools import (
    BraveSearchProvider,
    SafeWebReader,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    Unavailable,
    WebSearchInput,
    WebSearchPolicy,
    bind_brave_web_search,
    bind_web_read,
    canonical_json_bytes,
    web_family,
    web_search_source_operation,
)
from llm_tools.schema import JsonObject
from sqlalchemy import text

from jarvis.action_requests import bind_action_requests
from jarvis.actions import ActionStore
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.agent_tools import agent_family
from jarvis.approval_tools import approval_family
from jarvis.attachment_sources import AttachmentSources
from jarvis.attachment_tools import attachment_family
from jarvis.attachments import AttachmentStore, S3Client
from jarvis.connectors import GoogleReadConnector, GoogleTokenManager, MapsReadConnector
from jarvis.event_polling import EventPoller
from jarvis.event_tools import events_family
from jarvis.events import EventStore
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import memory_family
from jarvis.ownership import Database
from jarvis.read_tools import (
    ATTACHMENT_CONNECT_SECONDS,
    ATTACHMENT_SOCKET_SECONDS,
    maps_family,
)
from jarvis.receipt_tools import receipt_family
from jarvis.settings import Settings
from jarvis.work import WorkStore
from jarvis.work_tools import work_family
from jarvis.write_connectors import GoogleWriteConnector
from jarvis.write_tools import calendar_main_family, gmail_main_family


@dataclass(frozen=True, slots=True)
class ToolComposition:
    catalog: ToolCatalog
    google_write: GoogleWriteConnector
    event_poller: EventPoller
    attachments: AttachmentStore
    google_read: GoogleReadConnector
    web_source_operation: Callable[[WebSearchInput], JsonObject | None]


def build_tool_composition(
    *,
    owner: JarvisOwner,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory: MemoryService,
    actions: ActionStore,
    agents: AgentController,
    work: WorkStore,
    events: EventStore,
    event_admitted: Callable[[], Awaitable[bool]],
) -> ToolComposition:
    calendar_ids_digest = hashlib.sha256(
        canonical_json_bytes(sorted(settings.verified_owner_only_calendar_ids))
    ).hexdigest()
    tokens = google_tokens(settings, google_oauth_http)
    google_read = GoogleReadConnector(client=google_api_http, tokens=tokens)
    google_write = GoogleWriteConnector(
        client=google_api_http,
        tokens=tokens,
        stage_gmail_update_basis=actions.stage_gmail_update_basis,
        stage_external_attempts=actions.stage_external_attempts,
    )
    attachments = build_attachment_store(
        settings=settings,
        database=actions.engine,
        http=google_api_http,
        google=google_read,
    )
    maps = MapsReadConnector(
        client=maps_http,
        api_key=settings.maps_api_key.get_secret_value(),
    )
    search_policy = WebSearchPolicy()
    brave = BraveSearchProvider(
        brave_http,
        api_key=settings.brave_api_key.get_secret_value(),
        policy=search_policy,
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
                    policy=search_policy,
                    operation_deadline_seconds=12.0,
                ),
                read=bind_web_read(SafeWebReader()),
            ),
            memory_family(memory),
            approval_family(),
            receipt_family(owner),
            _bind_write_policy(work_family(work), calendar_ids_digest=None),
            _bind_write_policy(events_family(events), calendar_ids_digest=None),
            _bind_write_policy(
                attachment_family(attachments), calendar_ids_digest=None
            ),
        )
    )
    if any(
        isinstance(catalog.binding(tool_id).execute, Unavailable)
        for tool_id in catalog.tool_ids
    ):
        raise RuntimeError("every application binding must be available")
    event_poller = EventPoller(
        store=events,
        client=google_api_http,
        tokens=tokens,
        owner_zone=settings.owner_timezone,
        admitted=event_admitted,
    )
    events.notify_changed = event_poller.notify_changed
    return ToolComposition(
        catalog,
        google_write,
        event_poller,
        attachments,
        google_read,
        partial(web_search_source_operation, policy=search_policy),
    )


def google_tokens(settings: Settings, http: httpx.AsyncClient) -> GoogleTokenManager:
    return GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
        single_secret=settings.connector_encryption_secret.get_secret_value(),
    )


def build_attachment_store(
    *,
    settings: Settings,
    database: Database,
    http: httpx.AsyncClient,
    google: GoogleReadConnector,
) -> AttachmentStore:
    async def require_owner() -> None:
        async with database.connect() as connection:
            await connection.execute(text("SELECT 1"))

    s3 = cast(
        S3Client,
        boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url=f"https://{settings.attachment_r2_account_id}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=settings.attachment_r2_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.attachment_r2_secret_access_key.get_secret_value(),
            config=Config(
                retries={"total_max_attempts": 1},
                request_checksum_calculation="when_required",
                connect_timeout=ATTACHMENT_CONNECT_SECONDS,
                read_timeout=ATTACHMENT_SOCKET_SECONDS,
            ),
        ),
    )
    return AttachmentStore(
        database,
        str(settings.discord.channel_id),
        r2_account=settings.attachment_r2_account_id,
        bucket=settings.attachment_r2_bucket,
        cache_directory=settings.attachment_cache_directory,
        s3_client=s3,
        sources=AttachmentSources(client=http, google=google, discord=settings.discord),
        mutation_admitted=require_owner,
    )


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


__all__ = [
    "ToolComposition",
    "build_attachment_store",
    "build_tool_composition",
    "google_tokens",
]

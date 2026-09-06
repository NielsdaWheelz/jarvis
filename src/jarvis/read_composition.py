"""Production Slice 2 read-tool composition."""

from __future__ import annotations

import httpx
from llm_tools import (
    BraveSearchProvider,
    SafeWebReader,
    ToolCatalog,
    bind_brave_web_search,
    bind_web_read,
    web_family,
)

from jarvis.connectors import GoogleReadConnector, GoogleTokenManager, MapsReadConnector
from jarvis.memory_retrieval import MemoryEmbedder, MemoryRepository
from jarvis.memory_tools import memory_family
from jarvis.read_tools import (
    calendar_family,
    compose_read_catalog,
    gmail_family,
    maps_family,
)
from jarvis.settings import Settings


def build_read_catalog(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
) -> ToolCatalog:
    tokens = GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=google_oauth_http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
        configured_keys=settings.connector_encryption_keys.get_secret_value(),
        single_secret=settings.connector_encryption_secret.get_secret_value(),
    )
    google = GoogleReadConnector(client=google_api_http, tokens=tokens)
    maps = MapsReadConnector(
        client=maps_http,
        api_key=settings.maps_api_key.get_secret_value(),
    )
    brave = BraveSearchProvider(
        brave_http,
        api_key=settings.brave_api_key.get_secret_value(),
        base_url="https://api.search.brave.com/res/v1",
    )
    return compose_read_catalog(
        google=google,
        maps=maps,
        web=web_family(
            search=bind_brave_web_search(
                brave,
                operation_deadline_seconds=12.0,
            ),
            read=bind_web_read(SafeWebReader()),
        ),
    )


def build_slice3_catalog(
    *,
    settings: Settings,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory_repository: MemoryRepository,
    memory_embedder: MemoryEmbedder,
) -> ToolCatalog:
    tokens = GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=google_oauth_http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
        configured_keys=settings.connector_encryption_keys.get_secret_value(),
        single_secret=settings.connector_encryption_secret.get_secret_value(),
    )
    google = GoogleReadConnector(client=google_api_http, tokens=tokens)
    maps = MapsReadConnector(
        client=maps_http,
        api_key=settings.maps_api_key.get_secret_value(),
    )
    brave = BraveSearchProvider(
        brave_http,
        api_key=settings.brave_api_key.get_secret_value(),
        base_url="https://api.search.brave.com/res/v1",
    )
    return ToolCatalog.compose(
        (
            gmail_family(google),
            calendar_family(google),
            maps_family(maps),
            web_family(
                search=bind_brave_web_search(
                    brave,
                    operation_deadline_seconds=12.0,
                ),
                read=bind_web_read(SafeWebReader()),
            ),
            memory_family(memory_repository, memory_embedder),
        )
    )


__all__ = ["build_read_catalog", "build_slice3_catalog"]

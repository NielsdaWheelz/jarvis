"""Stopped operator custody of the independent owner Drive reader grant."""

from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

from jarvis._atomic_json import read_private_json
from jarvis.connectors import GoogleTokenManager
from jarvis.settings import Settings
from jarvis.workspace_mcp import WorkspaceError


class _DesktopClient(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, strict=True)

    project_id: str = Field(pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
    client_id: str = Field(min_length=1, max_length=1024, repr=False)
    client_secret: str = Field(min_length=1, max_length=1024, repr=False)


def owner_drive_tokens(
    settings: Settings, http: httpx.AsyncClient
) -> GoogleTokenManager:
    directory = settings.owner_gmail_state_directory.resolve()
    if any(
        directory.is_relative_to(path)
        for path in (Path("/var/lib/jarvis"), Path("/etc/jarvis"))
    ):
        raise WorkspaceError("grant_unavailable")
    export = read_private_json(directory / "client.json")
    if export is None or set(export) != {"installed"}:
        raise WorkspaceError("grant_unavailable")
    client = _DesktopClient.model_validate(export["installed"])
    oauth = directory / "drive-oauth.json"
    if (
        client.client_id == settings.google_oauth_client_id.get_secret_value()
        or oauth.resolve() == settings.google_oauth_state_path.resolve()
    ):
        raise WorkspaceError("grant_unavailable")
    return GoogleTokenManager(
        state_path=oauth,
        client=http,
        client_id=client.client_id,
        client_secret=client.client_secret,
        active_key_version=settings.connector_encryption_key_version,
        single_secret=settings.connector_encryption_secret.get_secret_value(),
        project_id=client.project_id,
        human_product="drive",
    )

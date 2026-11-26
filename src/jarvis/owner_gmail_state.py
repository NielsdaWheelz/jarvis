"""Stopped operator custody of the human client and the editor epoch."""

from pathlib import Path
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis.connectors import GoogleTokenManager
from jarvis.settings import Settings
from jarvis.workspace_write_models import DraftEditorStamp


class _DesktopClient(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, strict=True)

    project_id: str = Field(pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
    client_id: str = Field(min_length=1, max_length=1024, repr=False)
    client_secret: str = Field(min_length=1, max_length=1024, repr=False)


def owner_gmail_directory(path: Path) -> Path:
    directory = path.resolve()
    if any(
        directory.is_relative_to(path)
        for path in (Path("/var/lib/jarvis"), Path("/etc/jarvis"))
    ):
        raise ValueError("owner gmail state must be outside both backup sets")
    return directory


def owner_gmail_tokens(
    settings: Settings, directory: Path, http: httpx.AsyncClient
) -> GoogleTokenManager:
    export = read_private_json(directory / "client.json")
    if export is not None and set(export) != {"installed"}:
        raise ValueError("owner gmail requires a desktop oauth client")
    client = _DesktopClient.model_validate(export["installed"]) if export else None
    oauth = directory / "oauth.json"
    if (
        client is not None
        and client.client_id == settings.google_oauth_client_id.get_secret_value()
    ) or oauth.resolve() == settings.google_oauth_state_path.resolve():
        raise ValueError("owner gmail requires a distinct oauth client and token file")
    return GoogleTokenManager(
        state_path=oauth,
        client=http,
        client_id=client.client_id if client else "",
        client_secret=client.client_secret if client else "",
        active_key_version=settings.connector_encryption_key_version,
        single_secret=settings.connector_encryption_secret.get_secret_value(),
        project_id=client.project_id if client else None,
        owner_drafts=True,
    )


def read_editor_stamp(directory: Path) -> DraftEditorStamp | None:
    state = read_private_json(directory / "epoch.json")
    return DraftEditorStamp.model_validate(state) if state else None


def enroll_editor_epoch(directory: Path, subject: str) -> UUID:
    stamp = read_editor_stamp(directory)
    if stamp is not None and stamp.google_sub == subject:
        return stamp.epoch
    stamp = DraftEditorStamp(epoch=uuid4(), google_sub=subject)
    replace_private_json(directory / "epoch.json", stamp.model_dump(mode="json"))
    return stamp.epoch


def invalidate_editor_epoch(directory: Path) -> None:
    # A durable empty record distinguishes restore from ordinary reconnect.
    if directory.exists():
        replace_private_json(directory / "epoch.json", {})

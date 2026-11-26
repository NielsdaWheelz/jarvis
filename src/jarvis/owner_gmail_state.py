"""Stopped operator custody of the human client and the editor epoch."""

from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis.connectors import GoogleTokenManager
from jarvis.home_drive import DriveGrant, DriveReader
from jarvis.settings import Settings
from jarvis.workspace_mcp import WorkspaceError
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


def owner_workspace_tokens(
    settings: Settings,
    directory: Path,
    http: httpx.AsyncClient,
    *,
    product: Literal["gmail", "drive"],
) -> GoogleTokenManager:
    export = read_private_json(directory / "client.json")
    if export is not None and set(export) != {"installed"}:
        raise ValueError("owner workspace access requires a desktop oauth client")
    client = _DesktopClient.model_validate(export["installed"]) if export else None
    oauth = directory / ("oauth.json" if product == "gmail" else "drive-oauth.json")
    if (
        client is not None
        and client.client_id == settings.google_oauth_client_id.get_secret_value()
    ) or oauth.resolve() == settings.google_oauth_state_path.resolve():
        raise ValueError(
            "owner workspace access requires a distinct oauth client and token file"
        )
    return GoogleTokenManager(
        state_path=oauth,
        client=http,
        client_id=client.client_id if client else "",
        client_secret=client.client_secret if client else "",
        active_key_version=settings.connector_encryption_key_version,
        single_secret=settings.connector_encryption_secret.get_secret_value(),
        project_id=client.project_id if client else None,
        human_product=product,
    )


def owner_drive_reader(
    settings: Settings,
    directory: Path,
    agent: GoogleTokenManager,
    oauth: httpx.AsyncClient,
    api: httpx.AsyncClient,
) -> DriveReader:
    """Compose the private viewer without exposing its read grant to agent tools."""
    human = owner_workspace_tokens(settings, directory, oauth, product="drive")

    async def grant() -> DriveGrant | None:
        current = human.enrollment()
        if current is None:
            return None

        def same_subject() -> bool:
            selected = agent.enrollment()
            return selected is None or (
                (selected.subject, selected.account)
                == (current.subject, current.account)
            )

        if not same_subject():
            return None
        try:
            token = await human.credential(current.grant_id, None)
        except WorkspaceError as exc:
            if exc.kind == "grant_unavailable":
                return None
            quota = exc.kind == "rate_limited"
            raise HTTPException(
                429 if quota else 503,
                "drive_rate_limited" if quota else "drive_unavailable",
            ) from exc
        if not same_subject():
            return None
        return DriveGrant(current.subject, str(current.grant_id), token.access_token)

    key = settings.connector_encryption_secret.get_secret_value().encode()
    return DriveReader(
        api, grant, Path(gettempdir()), sha256(key + b"/jarvis-drive-cursor").digest()
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

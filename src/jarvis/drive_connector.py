"""Agent-side Drive resource observations and bound file transfers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import quote

from llm_tools import canonical_json_bytes
from pydantic import BaseModel, ConfigDict

from jarvis.workspace_links import workspace_link
from jarvis.workspace_mcp import Obj, Product, WorkspaceError
from jarvis.workspace_write_models import (
    DriveId,
    DriveMime,
    DrivePermission,
    DriveToken,
)

DriveCall = Callable[[Product, str, Obj], Awaitable[Obj]]
DriveMaterialize = Callable[[BinaryIO, int, str], Awaitable[Path]]
DriveTransfer = Callable[[Obj, BinaryIO, int], Awaitable[Obj]]
NATIVE_MIME = "application/vnd.google-apps."
FOLDER = NATIVE_MIME + "folder"


class DriveFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: DriveId
    name: str
    mime: DriveMime
    parent: DriveId | None
    modified: str | None
    size: int | None
    etag: DriveToken | None
    owner: str | None
    visibility: str | None
    shared_drive: DriveId | None
    inherited_disabled: bool | None
    trashed: bool | None
    capabilities: dict[str, bool] | None
    url: str | None

    @property
    def native(self) -> bool:
        return self.mime.startswith(NATIVE_MIME)

    @classmethod
    def observed(cls, raw: Obj, id: str | None = None) -> DriveFile:
        identified = raw.get("id")
        if not isinstance(identified, str) or (id is not None and identified != id):
            raise ValueError("drive file identity mismatch")
        size = raw.get("fileSize")
        if size is not None and (
            not isinstance(size, str)
            or not size.isascii()
            or not size.isdecimal()
            or len(size) > 19
        ):
            raise ValueError("invalid drive file size")
        name = raw.get("title")
        if not isinstance(name, str) or not 0 < len(name.encode()) <= 4096:
            raise ValueError("invalid drive title")
        return cls.model_validate(
            {
                "id": identified,
                "name": name,
                "mime": raw.get("mimeType"),
                "parent": raw.get("parentId") or None,
                "size": int(size) if size is not None else None,
                "modified": raw.get("modifiedTime"),
                "etag": raw.get("etag") or None,
                "owner": raw.get("owner") or None,
                "visibility": raw.get("visibility") or None,
                "shared_drive": raw.get("sharedDriveId") or None,
                "inherited_disabled": raw.get("inheritedPermissionsDisabled"),
                "trashed": raw.get("trashed"),
                "capabilities": raw.get("capabilities"),
                "url": workspace_link(raw.get("viewUrl"), "drive", identified),
            }
        )


def file_wire(id: str, *, rich: bool = True) -> Obj:
    return {"fileId": id, "excludeContentSnippets": True, "includeRichMetadata": rich}


async def metadata(call: DriveCall, id: str) -> DriveFile:
    item = DriveFile.observed(
        await call("drive", "get_file_metadata", file_wire(id)), id
    )
    if item.trashed is True:
        raise WorkspaceError("not_found")
    return item


class DriveRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    etag: DriveToken | None
    head_revision_id: DriveToken | None


async def drive_revision(call: DriveCall, id: str) -> DriveRevision:
    """Read the exact v2 conditional write token and binary revision identity."""
    observed = await call("drive", "get_file_revision", {"fileId": id})
    if observed.get("id") != id:
        raise WorkspaceError("invalid_response")
    try:
        return DriveRevision.model_validate(
            {
                "etag": observed.get("etag"),
                "head_revision_id": observed.get("headRevisionId"),
            }
        )
    except ValueError:
        raise WorkspaceError("invalid_response") from None


def file_href(subject: str, id: str) -> str:
    return f"/files/{quote(subject, safe='')}/{quote(id, safe='')}"


def permissions(raw: Obj, source: str) -> tuple[DrivePermission, ...]:
    rows = raw.get("permissions")
    if not isinstance(rows, list):
        raise ValueError("invalid drive permission list")
    values: list[DrivePermission] = []
    for permission in cast(list[object], rows):
        if not isinstance(permission, dict):
            raise ValueError("invalid drive permission")
        row = cast(Obj, permission)
        values.append(
            DrivePermission.model_validate(
                {
                    "source": source,
                    "id": row.get("id"),
                    "role": row.get("role"),
                    "type": row.get("type"),
                    "address": row.get("emailAddress"),
                    "domain": row.get("domain"),
                    "view": row.get("view"),
                    "space": row.get("chatSpaceId"),
                    "expires_at": row.get("expirationTime"),
                    "pending_owner": row.get("pendingOwner"),
                },
                strict=True,
            )
        )
    return tuple(sorted(values, key=lambda p: canonical_json_bytes(p.model_dump())))


async def document(call: DriveCall, id: str) -> Obj:
    body = await call("docs", "get_document", {"documentId": id})
    if body.get("documentId") != id:
        raise WorkspaceError("source_changed")
    document_tabs(body)
    return body


def document_tabs(document: Obj) -> dict[str, Obj]:
    raw = document.get("tabs")
    if not isinstance(raw, list) or not raw:
        raise WorkspaceError("document_structure_unavailable")
    tabs: dict[str, Obj] = {}
    pending = list(reversed(cast(list[object], raw)))
    while pending:
        item = pending.pop()
        if not isinstance(item, dict):
            raise WorkspaceError("document_structure_unavailable")
        tab = cast(Obj, item)
        properties = tab.get("tabProperties")
        content = tab.get("documentTab")
        children = tab.get("childTabs", [])
        if (
            not isinstance(properties, dict)
            or not isinstance(content, dict)
            or not isinstance(children, list)
        ):
            raise WorkspaceError("document_structure_unavailable")
        id = cast(Obj, properties).get("tabId")
        data = cast(Obj, content)
        body = data.get("body")
        if (
            not isinstance(id, str)
            or not id
            or id in tabs
            or not isinstance(body, dict)
            or not isinstance(cast(Obj, body).get("content"), list)
        ):
            raise WorkspaceError("document_structure_unavailable")
        tabs[id] = data
        pending.extend(reversed(cast(list[object], children)))
    return tabs


def document_revision(document: Obj, id: str) -> str:
    revision = document.get("revisionId")
    if (
        document.get("documentId") != id
        or not isinstance(revision, str)
        or not (0 < len(revision.encode()) <= 1024)
    ):
        raise WorkspaceError("revision_unavailable")
    return revision


async def fetch_binary(
    call: DriveCall,
    transfer: DriveTransfer,
    id: str,
    export_type: str | None,
    destination: BinaryIO,
    maximum: int,
) -> tuple[DriveFile, int, str]:
    original = await metadata(call, id)
    if original.native and export_type is None:
        raise WorkspaceError("explicit_export_required")
    if not original.native and export_type is not None:
        raise WorkspaceError("export_requires_native_file")
    if original.etag is None:
        raise WorkspaceError("file_revision_unavailable")
    if not original.native and original.size is not None and original.size > maximum:
        raise WorkspaceError("too_large")
    arguments: Obj = {"fileId": id}
    if export_type is not None:
        arguments["exportMimeType"] = export_type
    material = await transfer(arguments, destination, maximum)
    size = material["size"]
    digest = material["sha256"]
    if type(size) is not int or not isinstance(digest, str):
        raise WorkspaceError("invalid_response")
    if (
        material["id"] != id
        or material["mimeType"] != (export_type or original.mime)
        or (export_type is not None and material["title"] != original.name)
    ):
        raise WorkspaceError("source_changed")
    if not original.native and original.size is not None and size != original.size:
        raise WorkspaceError("source_changed")
    current = await metadata(call, id)
    if (
        original.etag != current.etag
        or original.name != current.name
        or original.mime != current.mime
        or original.size != current.size
    ):
        raise WorkspaceError("source_changed")
    return current, size, digest

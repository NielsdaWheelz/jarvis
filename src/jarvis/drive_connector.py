"""Agent-side Drive resource observations and bound file transfers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Literal, cast
from urllib.parse import quote

from llm_tools import canonical_json_bytes
from pydantic import BaseModel, ConfigDict

from jarvis.workspace_links import workspace_link
from jarvis.workspace_mcp import Obj, Product, WorkspaceError
from jarvis.workspace_write_models import (
    DriveAudience,
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


async def audience(call: DriveCall, target: str, account: str) -> DriveAudience:
    current: str | None = target
    seen: set[str] = set()
    evidence: list[object] = []
    identities: list[DrivePermission] = []
    state: Literal["private", "shared", "unknown"] = "private"
    for _ in range(8):
        if current is None:
            break
        if current in seen:
            state = "unknown"
            break
        seen.add(current)
        try:
            file = await metadata(call, current)
            raw = await call("drive", "get_file_permissions", {"fileId": current})
            observed = permissions(raw, current)
        except WorkspaceError as e:
            if e.kind not in {"denied", "not_found", "withheld", "policy_block"}:
                raise
            evidence.append([current, e.kind])
            state = "unknown"
            break
        identities.extend(observed)
        evidence.append(
            [
                current,
                file.parent,
                file.owner,
                file.visibility,
                file.shared_drive,
                file.inherited_disabled,
                [p.model_dump() for p in observed],
            ]
        )
        owner_only = len(observed) == 1 and (
            observed[0].type == "user"
            and observed[0].role == "owner"
            and observed[0].address is not None
            and observed[0].address.casefold() == account.casefold()
            and observed[0].pending_owner is not True
        )
        if raw.get("nextPageToken"):
            state = "unknown"
        elif (
            file.shared_drive
            or file.visibility
            in {"PUBLIC", "UNLISTED", "PUBLIC_TO_DOMAIN", "UNLISTED_TO_DOMAIN"}
            or (file.owner and file.owner.casefold() != account.casefold())
            or (any(p.role and p.role != "owner" and p.type for p in observed))
        ):
            if state == "private":
                state = "shared"
        elif not owner_only or not file.owner or file.visibility != "PRIVATE":
            state = "unknown"
        if file.inherited_disabled is True:
            current = None
        elif file.parent is None:
            # An absent optional parent is not by itself evidence of reaching My Drive.
            try:
                root = DriveFile.observed(
                    await call("drive", "get_file_metadata", file_wire("root"))
                )
                evidence.append(["root", root.id])
            except WorkspaceError as e:
                if e.kind not in {"denied", "not_found", "withheld", "policy_block"}:
                    raise
                evidence.append(["root", e.kind])
                state = "unknown"
            else:
                if root.id != current:
                    state = "unknown"
            current = None
        else:
            current = file.parent
    if current is not None:
        state = "unknown"
    return DriveAudience(
        target=target,
        state=state,
        identities=tuple(identities),
        fingerprint=sha256(canonical_json_bytes(evidence)).hexdigest(),
    )


async def document(call: DriveCall, id: str) -> Obj:
    raw = await call("docs", "read_doc", {"documentId": id, "commentsIncluded": False})
    content = raw.get("content")
    if not isinstance(content, dict):
        raise WorkspaceError("document_structure_unavailable")
    body = cast(Obj, content)
    if body.get("documentId") not in {None, id}:
        raise WorkspaceError("source_changed")
    return body


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
        or material["title"] != original.name
        or material["mimeType"] != (export_type or original.mime)
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

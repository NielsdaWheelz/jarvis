"""The owner-only Drive reader and submission origin resolution."""

from __future__ import annotations

import base64
import binascii
import hmac
import re
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import Response

from jarvis._thread_io import joined_thread
from jarvis.home_file_content import file_response, media_type
from jarvis.home_refs import DRIVE_ID_PATTERN, DriveId
from jarvis.read_tools import ATTACHMENT_MAX_BYTES

_FILES = "https://www.googleapis.com/drive/v3/files"
_FOLDER = "application/vnd.google-apps.folder"
_PREVIEWS = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
)
_FIELDS = (
    "id,name,mimeType,parents,modifiedTime,webViewLink,resourceKey,version,"
    "size,trashed,driveId,capabilities(canDownload)"
)
_ID = re.compile(DRIVE_ID_PATTERN)
_CURSOR_LIMIT = 16 * 1024
_JSON_LIMIT = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DriveGrant:
    subject: str
    generation: str
    access_token: str


class _Origin(Protocol):
    @property
    def id(self) -> UUID: ...
    @property
    def filename(self) -> str | None: ...
    @property
    def media_type(self) -> str | None: ...
    @property
    def size_bytes(self) -> int | None: ...
    @property
    def created_at(self) -> datetime: ...
    @property
    def state(self) -> str: ...
    @property
    def drive_subject(self) -> str | None: ...
    @property
    def drive_file_id(self) -> str | None: ...
    @property
    def disposition(self) -> str | None: ...


class _Capabilities(BaseModel):
    canDownload: bool = False


class _File(BaseModel):
    id: DriveId
    name: Annotated[str, Field(min_length=1, max_length=8192)]
    mimeType: Annotated[str, Field(min_length=1, max_length=255)]
    parents: Annotated[list[DriveId], Field(max_length=1)] = Field(default_factory=list)
    modifiedTime: datetime | None = None
    webViewLink: Annotated[str, Field(max_length=4096)] | None = None
    resourceKey: DriveId | None = None
    version: Annotated[str, Field(pattern=r"^[0-9]{1,32}$")] | None = None
    size: Annotated[str, Field(pattern=r"^[0-9]{1,32}$")] | None = None
    trashed: bool = False
    driveId: DriveId | None = None
    capabilities: _Capabilities | None = None

    @property
    def parent(self) -> str | None:
        return self.parents[0] if self.parents else None

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "mime": self.mimeType,
            "parent": self.parent,
            "modified": self.modifiedTime,
            "url": self._view_url(),
        }

    def _view_url(self) -> str:
        if self.webViewLink and not re.search(r"[\x00-\x20\x7f]", self.webViewLink):
            try:
                url = urlsplit(self.webViewLink)
                parts = url.path.split("/")
                query = parse_qs(url.query, max_num_fields=20)
            except ValueError:
                pass
            else:
                valid_path = (
                    url.netloc == "drive.google.com"
                    and (
                        (parts[:3] == ["", "file", "d"] and parts[3:4] == [self.id])
                        or (
                            parts[:3] == ["", "drive", "folders"]
                            and parts[3:4] == [self.id]
                        )
                        or (url.path == "/open" and query.get("id") == [self.id])
                    )
                ) or (
                    url.netloc == "docs.google.com"
                    and parts[1:2] in (["document"], ["spreadsheets"], ["presentation"])
                    and parts[2:4] == ["d", self.id]
                )
                key_matches = self.resourceKey is None or any(
                    values == [self.resourceKey]
                    for key, values in query.items()
                    if key.lower() == "resourcekey"
                )
                if url.scheme == "https" and valid_path and key_matches:
                    return self.webViewLink
        query = {"id": self.id}
        if self.resourceKey:
            query["resourcekey"] = self.resourceKey
        return "https://drive.google.com/open?" + urlencode(query)


class _List(BaseModel):
    files: Annotated[list[_File], Field(max_length=50)]
    nextPageToken: (
        Annotated[str, Field(min_length=1, max_length=_CURSOR_LIMIT)] | None
    ) = None
    incompleteSearch: bool = False


class _Cursor(BaseModel):
    subject: str
    generation: str
    selector: tuple[str, str]
    token: str


async def _check_response(response: httpx.Response, *, cursor: bool = False) -> None:
    status = response.status_code
    if status == 200:
        return
    if status == 401:
        raise HTTPException(424, "drive_disconnected")
    if status == 400 and cursor:
        raise HTTPException(409, "drive_cursor_stale")
    if status == 403:
        error = await anext(response.aiter_bytes(chunk_size=8192), b"")
        if b"insufficientPermissions" in error:
            raise HTTPException(424, "drive_disconnected")
        reasons = (
            b"rateLimitExceeded",
            b"userRateLimitExceeded",
            b"dailyLimitExceeded",
        )
        status = 429 if any(reason in error for reason in reasons) else 404
    if status == 429:
        retry = response.headers.get("Retry-After")
        headers = {"Retry-After": retry} if retry else None
        raise HTTPException(429, "drive_rate_limited", headers=headers)
    if status in {404, 410}:
        raise HTTPException(404, "drive_inaccessible")
    raise HTTPException(502, "drive_unavailable")


def _headers(grant: DriveGrant, *, item: _File | None = None) -> dict[str, str]:
    result = {
        "Authorization": "Bearer " + grant.access_token,
        "Accept-Encoding": "identity",
    }
    if item and item.resourceKey:
        result["X-Goog-Drive-Resource-Keys"] = item.id + "/" + item.resourceKey
    return result


def _literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", r"\'") + "'"


class DriveReader:
    """Read through the human grant and verify it again before returning results."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        grant: Callable[[], Awaitable[DriveGrant | None]],
        spool: Path,
        cursor_key: bytes,
    ) -> None:
        self._client = client
        self._grant = grant
        self._spool = spool
        self._cursor_key = cursor_key

    async def _authorized(self, subject: str | None = None) -> DriveGrant:
        if (grant := await self._grant()) is None or not _ID.fullmatch(grant.subject):
            raise HTTPException(424, "drive_disconnected")
        if subject is not None and subject != grant.subject:
            raise HTTPException(404, "drive_inaccessible")
        return grant

    async def _check_grant(self, original: DriveGrant) -> None:
        if (await self._authorized(original.subject)).generation != original.generation:
            raise HTTPException(424, "drive_disconnected")

    async def _json[T: BaseModel](
        self,
        model: type[T],
        url: str,
        params: dict[str, str],
        grant: DriveGrant,
        *,
        item: _File | None = None,
    ) -> T:
        data = bytearray()
        try:
            async with self._client.stream(
                "GET",
                url,
                params=params,
                headers=_headers(grant, item=item),
                follow_redirects=False,
            ) as response:
                await _check_response(response, cursor="pageToken" in params)
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(data) + len(chunk) > _JSON_LIMIT:
                        raise HTTPException(502, "drive_unavailable")
                    data.extend(chunk)
            return model.model_validate_json(data)
        except (httpx.HTTPError, ValidationError):
            raise HTTPException(502, "drive_unavailable") from None

    async def _file(
        self, grant: DriveGrant, identifier: str, *, item: _File | None = None
    ) -> _File:
        file = await self._json(
            _File,
            _FILES + "/" + identifier,
            {"supportsAllDrives": "true", "fields": _FIELDS},
            grant,
            item=item,
        )
        if file.trashed or (identifier != "root" and file.id != identifier):
            raise HTTPException(404, "drive_inaccessible")
        return file

    def _cursor(self, cursor: _Cursor) -> str:
        raw = cursor.model_dump_json().encode()
        tag = hmac.digest(self._cursor_key, raw, "sha256")
        return base64.urlsafe_b64encode(raw + tag).decode().rstrip("=")

    def _next_page(
        self,
        token: str,
        grant: DriveGrant,
        selector: tuple[str, str],
    ) -> str:
        if len(token) > _CURSOR_LIMIT:
            raise HTTPException(400, "drive_invalid_input")
        try:
            raw = base64.b64decode(
                token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
            )
            data, tag = raw[:-32], raw[-32:]
            if hmac.compare_digest(hmac.digest(self._cursor_key, data, "sha256"), tag):
                cursor = _Cursor.model_validate_json(data)
                if (cursor.subject, cursor.generation, cursor.selector) == (
                    grant.subject,
                    grant.generation,
                    selector,
                ):
                    return cursor.token
        except (ValidationError, ValueError, binascii.Error):
            pass
        raise HTTPException(409, "drive_cursor_stale")

    async def list(
        self,
        folder: str | None,
        recent: str | None,
        query: str | None,
        cursor: str | None,
    ) -> dict[str, object]:
        if (
            sum(value is not None for value in (folder, recent, query)) != 1
            or (folder is not None and not _ID.fullmatch(folder))
            or recent not in (None, "true")
            or (
                query is not None
                and (
                    not query.strip()
                    or len(query) > 255
                    or any(ord(c) < 32 for c in query)
                )
            )
        ):
            raise HTTPException(400, "drive_invalid_input")
        grant = await self._authorized()
        if folder is not None:
            selector = ("folder", folder)
            condition = _literal(folder) + " in parents"
            order = "folder,name_natural"
        elif query is not None:
            selector = ("q", query)
            condition = "name contains " + _literal(query)
            order = "folder,name_natural"
        else:
            selector = ("recent", "true")
            condition = "viewedByMeTime > '1970-01-01T00:00:00Z'"
            order = "viewedByMeTime desc"

        params = {
            "q": "trashed = false and " + condition,
            "orderBy": order,
            "pageSize": "50",
            "fields": "nextPageToken,incompleteSearch,files(" + _FIELDS + ")",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "corpora": "user" if folder is not None else "allDrives",
        }
        if cursor is not None:
            params["pageToken"] = self._next_page(cursor, grant, selector)
        parent = None
        if folder and folder != "root":
            parent = await self._file(grant, folder)
            if parent.mimeType != _FOLDER:
                raise HTTPException(400, "drive_invalid_input")
            if parent.driveId:
                params.update(corpora="drive", driveId=parent.driveId)
        page = await self._json(_List, _FILES, params, grant, item=parent)
        await self._check_grant(grant)
        items = {file.id: file.public() for file in page.files if not file.trashed}
        next_page = None
        partial = page.incompleteSearch
        if page.nextPageToken:
            token = self._cursor(
                _Cursor(
                    subject=grant.subject,
                    generation=grant.generation,
                    selector=selector,
                    token=page.nextPageToken,
                )
            )
            if token == cursor or len(token) > _CURSOR_LIMIT:
                partial = True
            else:
                next_page = token
        return {
            "subject": grant.subject,
            "items": list(items.values()),
            "next": next_page,
            "coverage": "partial" if partial else "complete",
            "observed_at": datetime.now(UTC),
        }

    async def get(
        self, subject: str, identifier: str, *, trail: bool
    ) -> dict[str, object]:
        if not _ID.fullmatch(identifier) or not _ID.fullmatch(subject):
            raise HTTPException(400, "drive_invalid_input")
        grant = await self._authorized(subject)
        item = await self._file(grant, identifier)
        path: list[dict[str, object]] = []
        path_partial = False
        if (trail or item.mimeType == _FOLDER) and item.parent:
            root = await self._file(grant, "root")
            ids = {item.id}
            parent = item.parent
            for _ in range(100):
                if parent == root.id:
                    break
                if parent in ids:
                    path_partial = True
                    break
                try:
                    ancestor = await self._file(grant, parent)
                except HTTPException as error:
                    if error.status_code != 404:
                        raise
                    path_partial = True
                    break
                path.insert(0, {"id": ancestor.id, "name": ancestor.name})
                ids.add(ancestor.id)
                if not ancestor.parent:
                    break
                parent = ancestor.parent
            else:
                path_partial = True
        await self._check_grant(grant)
        return {
            **item.public(),
            "version": item.version,
            "preview": item.mimeType in _PREVIEWS
            and bool(item.capabilities and item.capabilities.canDownload),
            "trail": path,
            "trail_partial": path_partial,
        }

    async def content(
        self, subject: str, identifier: str, version: str | None
    ) -> Response:
        if (
            not _ID.fullmatch(identifier)
            or not _ID.fullmatch(subject)
            or (version is not None and not re.fullmatch(r"[0-9]{1,32}", version))
        ):
            raise HTTPException(400, "drive_invalid_input")
        grant = await self._authorized(subject)
        item = await self._file(grant, identifier)
        if item.mimeType not in _PREVIEWS or not (
            item.capabilities and item.capabilities.canDownload
        ):
            raise HTTPException(415, "drive_preview_unsupported")
        if item.size is None or item.version is None:
            raise HTTPException(502, "drive_unavailable")
        if version is not None and version != item.version:
            raise HTTPException(409, "drive_version_changed")
        size = int(item.size)
        if size > ATTACHMENT_MAX_BYTES:
            raise HTTPException(413, "drive_preview_too_large")
        stream = tempfile.TemporaryFile(dir=self._spool)
        read = 0
        try:
            async with self._client.stream(
                "GET",
                _FILES + "/" + identifier,
                params={"alt": "media", "supportsAllDrives": "true"},
                headers=_headers(grant, item=item),
                follow_redirects=False,
            ) as response:
                await _check_response(response)
                async for chunk in response.aiter_bytes(chunk_size=256 * 1024):
                    read += len(chunk)
                    if read > size:
                        raise HTTPException(409, "drive_version_changed")
                    await joined_thread(stream.write, chunk)
            after = await self._file(grant, identifier, item=item)
            if not (after.capabilities and after.capabilities.canDownload):
                raise HTTPException(404, "drive_inaccessible")
            if (after.version, after.mimeType, after.size) != (
                item.version,
                item.mimeType,
                item.size,
            ) or read != size:
                raise HTTPException(409, "drive_version_changed")
            await self._check_grant(grant)
            stream.seek(0)
            if media_type(stream.read(16)) != item.mimeType:
                raise HTTPException(415, "drive_preview_unsupported")
            stream.seek(0)
        except httpx.HTTPError:
            stream.close()
            raise HTTPException(502, "drive_unavailable") from None
        except BaseException:
            stream.close()
            raise
        return file_response(stream, item.name, item.mimeType)


def _origin_view(row: _Origin) -> dict[str, object]:
    return {
        "id": str(row.id),
        "name": row.filename,
        "mime": row.media_type,
        "size": row.size_bytes,
        "received_at": row.created_at,
        "state": row.state,
        "subject": row.drive_subject,
        "file_id": row.drive_file_id,
        "disposition": row.disposition,
    }


def mount_drive(
    app: FastAPI,
    reader: DriveReader | None,
    pending: Callable[[], Awaitable[Sequence[_Origin]]],
    origin: Callable[[UUID], Awaitable[_Origin | None]],
) -> None:
    def connected() -> DriveReader:
        if reader is None:
            raise HTTPException(424, "drive_disconnected")
        return reader

    async def files(
        folder: str | None = None,
        recent: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, object]:
        return await connected().list(folder, recent, q, cursor)

    async def pending_files() -> list[dict[str, object]]:
        return [_origin_view(row) for row in await pending()]

    async def origin_file(identifier: UUID) -> dict[str, object]:
        row = await origin(identifier)
        if row is None:
            raise HTTPException(404, "drive_inaccessible")
        return _origin_view(row)

    async def metadata(
        subject: str, identifier: str, trail: bool = False
    ) -> dict[str, object]:
        return await connected().get(subject, identifier, trail=trail)

    async def content(
        subject: str, identifier: str, version: str | None = None
    ) -> Response:
        return await connected().content(subject, identifier, version)

    app.add_api_route("/api/drive/files", files, methods=["GET"])
    app.add_api_route("/api/drive/pending", pending_files, methods=["GET"])
    app.add_api_route("/api/drive/origin/{identifier}", origin_file, methods=["GET"])
    app.add_api_route("/api/drive/{subject}/{identifier}", metadata, methods=["GET"])
    app.add_api_route(
        "/api/drive/{subject}/{identifier}/content", content, methods=["GET"]
    )

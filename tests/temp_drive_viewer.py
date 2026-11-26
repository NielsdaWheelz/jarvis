"""Temporary owner route proof for ADR 0120 (synthetic provider)."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import UUID

import httpx

from jarvis.home_drive import DriveGrant, DriveReader
from jarvis.home_http import create_home_app
from jarvis.home_refs import HOME_REF_ADAPTER


async def main():
    grant = DriveGrant("owner", "grant1", "only-human")
    media = b"%PDF-1.5\nfirst"
    version = "1"
    mode = "normal"
    requests = []
    archive = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    upload = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    row = {
        "filename": "return.pdf",
        "media_type": "application/pdf",
        "size_bytes": len(media),
        "created_at": datetime.now(UTC),
        "disposition": None,
    }
    origins = {
        archive: SimpleNamespace(
            **row, id=archive, state="filed", drive_subject="owner", drive_file_id="return"
        ),
        upload: SimpleNamespace(
            **row, id=upload, state="staged", drive_subject=None, drive_file_id=None
        ),
    }

    async def current():
        return grant

    async def pending():
        return [origins[upload]]

    async def origin(identifier):
        return origins.get(identifier)

    def google(request):
        nonlocal version, grant
        queries = dict(request.url.params)
        identifier = request.url.path.rsplit("/", 1)[-1]
        requests.append((identifier, queries))
        assert request.url.scheme == "https"
        assert request.url.host == "www.googleapis.com"
        assert request.headers["Authorization"] == "Bearer only-human"
        if mode == "quota":
            return httpx.Response(403, json={"reason": "userRateLimitExceeded"}, headers={"Retry-After": "3"})
        if identifier == "files":
            files = [
                {"id": "return", "name": "return.pdf", "parents": ["2026"], "mimeType": "application/pdf"},
                {"id": "copy", "name": "return.pdf", "parents": ["accountant"], "mimeType": "application/pdf"},
            ]
            return httpx.Response(200, json={
                "files": files, "nextPageToken": "token", "incompleteSearch": "pageToken" in queries
            })
        if identifier in ("root", "2026", "taxes", "accountant"):
            return httpx.Response(200, json={
                "id": identifier, "name": identifier, "mimeType": "application/vnd.google-apps.folder",
                "parents": {"2026": ["taxes"], "taxes": ["root"]}.get(identifier, []),
            })
        if identifier == "doc":
            return httpx.Response(200, json={
                "id": "doc", "name": "letter", "mimeType": "application/vnd.google-apps.document",
                "webViewLink": "https://docs.google.com/document/d/doc/edit",
            })
        if identifier != "return" or mode == "revoked":
            return httpx.Response(404)
        if queries.get("alt") == "media":
            assert request.headers.get("X-Goog-Drive-Resource-Keys") == "return/0-key"
            if mode == "raced":
                version = "3"
            if mode == "disconnect":
                grant = None
            if mode == "signature":
                return httpx.Response(200, content=b"<html>" + b"x" * (len(media) - 6))
            return httpx.Response(200, content=media)
        return httpx.Response(200, json={
            "id": "return", "name": "return.pdf", "mimeType": "application/pdf", "parents": ["2026"],
            "version": version, "size": str((1 << 28) if mode == "large" else len(media)),
            "capabilities": {"canDownload": True}, "resourceKey": "0-key",
            "webViewLink": "https://drive.google.com/file/d/return/view?resourcekey=0-key",
        })

    assert HOME_REF_ADAPTER.validate_python(
        {"kind": "drive_file", "subject": "owner", "id": "return", "page": 6}
    ).model_dump(exclude_none=True) == {
        "kind": "drive_file", "subject": "owner", "id": "return", "page": 6
    }

    with TemporaryDirectory() as scratch:
        path = Path(scratch)
        async with httpx.AsyncClient(transport=httpx.MockTransport(google)) as provider:
            app = create_home_app(
                database=None,
                scope="test",
                owner_timezone="UTC",
                work=None,
                attachments=SimpleNamespace(pending=pending, inspect=origin),
                submit=None,
                pages=path,
                phone=None,
                drive_reader=DriveReader(provider, current, path, b"1" * 32),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://owner"
            ) as owner:
                root = await owner.get("/api/drive/files?folder=root")
                assert root.status_code == 200, root.text
                assert root.headers["Cache-Control"] == "private, no-store"
                assert root.headers["X-Content-Type-Options"] == "nosniff"
                assert [item["parent"] for item in root.json()["items"]] == ["2026", "accountant"]
                assert (await owner.get("/api/drive/files")).status_code == 400
                assert (await owner.get("/api/drive/files?folder=root&recent=true")).status_code == 400
                escaped = await owner.get("/api/drive/files", params={"q": "tax's\\draft"})
                assert escaped.status_code == 200
                assert requests[-1][1]["q"] == "trashed = false and name contains 'tax\\'s\\\\draft'"
                cursor = root.json()["next"]
                wrong = await owner.get("/api/drive/files", params={"recent": "true", "cursor": cursor})
                assert wrong.status_code == 409
                more = await owner.get("/api/drive/files", params={"folder": "root", "cursor": cursor})
                assert more.json()["coverage"] == "partial"
                assert more.json()["next"] is None
                grant = replace(grant, generation="grant2")
                wrong = await owner.get("/api/drive/files", params={"folder": "root", "cursor": cursor})
                assert wrong.status_code == 409
                assert (await owner.get("/api/drive/other/return")).status_code == 404
                base = "/api/drive/owner/return"
                meta = await owner.get(base, params={"trail": "true"})
                assert meta.json()["trail"] == [{"id": "taxes", "name": "taxes"}, {"id": "2026", "name": "2026"}]
                assert "?resourcekey=0-key" in meta.json()["url"]
                native = await owner.get("/api/drive/owner/doc")
                assert native.json()["preview"] is False and native.json()["url"].endswith("/doc/edit")
                assert (await owner.get("/api/drive/owner/doc/content")).status_code == 415
                assert (await owner.get(f"/api/drive/origin/{archive}")).json()["file_id"] == "return"
                assert (await owner.get("/api/drive/pending")).json()[0]["id"] == str(upload)
                good = await owner.get(base + "/content", params={"version": "1"})
                assert good.content == media and good.headers["Content-Type"] == "application/pdf"
                assert good.headers["Cache-Control"] == "private, no-store, no-transform"
                version = "2"
                media = b"%PDF-1.5\nother"
                assert (await owner.get(base + "/content", params={"version": "1"})).status_code == 409
                assert (await owner.get(base + "/content")).content == media
                for fault, status in (
                    ("revoked", 404), ("quota", 429), ("large", 413), ("signature", 415),
                    ("raced", 409), ("disconnect", 424),
                ):
                    mode = fault
                    failed = await owner.get(base + "/content")
                    assert failed.status_code == status, (failed.text, fault)
                    if fault == "quota":
                        assert failed.headers["Retry-After"] == "3"
                assert list(path.iterdir()) == []
                assert (await owner.get(base)).status_code == 424


if __name__ == "__main__":
    asyncio.run(main())

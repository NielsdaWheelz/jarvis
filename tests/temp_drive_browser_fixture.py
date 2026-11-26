"""Synthetic Drive transport with the actual Jarvis home routes/assets."""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import UUID

import httpx
from fastapi import FastAPI

from jarvis.home_drive import DriveGrant, DriveReader
from jarvis.home_http import create_home_app

scratch = TemporaryDirectory()
spool = Path(scratch.name)
archive = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
upload = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
mode = "normal"


def pdf(count: int) -> bytes:
    pages = " ".join(f"{i + 4} 0 R" for i in range(count))
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Count {count} /Kids [ {pages} ] >>".encode(),
        3: b"<< /Length 31 >>\nstream\n0.4 0.5 0.6 rg\n0 0 40 60 re f\n\nendstream",
    }
    page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 150] /Resources <<>> /Contents 3 0 R >>"
    for index in range(count):
        objects[index + 4] = page
    content = bytearray(b"%PDF-1.7\n")
    positions = []
    for index, item in objects.items():
        positions.append(len(content))
        content.extend(f"{index} 0 obj\n".encode() + item + b"\nendobj\n")
    xref = len(content)
    data = ["xref", f"0 {len(objects) + 1}", "0000000000 65535 f "]
    data.extend(f"{position:010} 00000 n " for position in positions)
    data.extend(["trailer", f"<< /Root 1 0 R /Size {len(objects) + 1} >>", "startxref", str(xref), "%%EOF"])
    content.extend(("\n".join(data) + "\n").encode())
    return bytes(content)


PDF = "application/pdf"
FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"
image = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fccfc0500f00058301ffed46692b0000000049454e44ae426082"
)
items = {
    "tax": {"name": "tax", "mimeType": FOLDER, "parents": ["root"]},
    "2026": {"name": "2026", "mimeType": FOLDER, "parents": ["tax"]},
    "shares": {"name": "shared / accountant", "mimeType": FOLDER},
    "root": {"name": "my drive", "mimeType": FOLDER},
    "return": {"name": "return.pdf", "mimeType": PDF, "parents": ["2026"]},
    "same": {"name": "return.pdf", "mimeType": PDF, "parents": ["shares"]},
    "letter": {"name": "letter", "mimeType": DOC, "parents": ["root"], "webViewLink": "https://docs.google.com/document/d/letter/edit"},
    "image": {"name": "image.png", "mimeType": "image/png", "parents": ["root"]},
}


def file(identifier: str):
    body = material(identifier)
    return {
        **items[identifier],
        "id": identifier,
        "size": str(len(body)),
        "version": "1" if mode == "normal" else "2",
        "capabilities": {"canDownload": True},
    }


def material(identifier: str) -> bytes:
    if identifier == "image":
        return image
    return pdf(6 if mode == "normal" else 5)


def provider(request: httpx.Request):
    assert request.headers["authorization"] == "Bearer synthetic-human"
    name = request.url.path.rsplit("/", 1)[-1]
    if name == "files":
        query = request.url.params["q"]
        token = request.url.params.get("pageToken")
        if token:
            return httpx.Response(429, headers={"Retry-After": "1"})
        if "name contains" in query or "viewedByMeTime" in query:
            return httpx.Response(200, json={"files": [file("return"), file("same")], "nextPageToken": "more"})
        folder = query.split("'")[1]
        return httpx.Response(200, json={
            "files": [file(identifier) for identifier, record in items.items() if folder in record.get("parents", ())]
        })
    if name not in items or (name == "return" and mode == "denied"):
        return httpx.Response(404)
    if request.url.params.get("alt"):
        return httpx.Response(200, content=material(name))
    return httpx.Response(200, json=file(name))


async def grant():
    return DriveGrant("owner", "g", "synthetic-human")


async def origin(identifier: UUID):
    if identifier not in (upload, archive):
        return None
    filed = identifier == archive
    return SimpleNamespace(
        id=identifier, filename="return.pdf" if filed else "upload.pdf", media_type=PDF,
        size_bytes=100, created_at=datetime(2026, 11, 26, tzinfo=UTC), state="filed" if filed else "staged",
        drive_subject="owner" if filed else None, drive_file_id="return" if filed else None,
        disposition=None,
    )


async def pending():
    return [await origin(upload)]


provider_client = httpx.AsyncClient(transport=httpx.MockTransport(provider))
app = create_home_app(
    database=None, scope="owner", owner_timezone="UTC", work=None,
    attachments=SimpleNamespace(pending=pending, inspect=origin),
    submit=None, spool=spool, pages=spool, phone=None,
    drive_reader=DriveReader(provider_client, grant, spool, b"1" * 32),
)
fixture = FastAPI()


@fixture.get("/state/{value}")
async def change(value: str):
    global mode
    assert value in {"normal", "changed", "denied"}
    mode = value
    return {}


app.mount("/fixture", fixture)

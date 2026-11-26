"""Signature checks and response ownership for private file streams."""

from __future__ import annotations

import os
from typing import BinaryIO
from urllib.parse import quote

from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send


def media_type(header: bytes) -> str:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def download_headers(name: str, mime: str, length: int) -> dict[str, str]:
    filename = name.replace("\\", "/").split("/")[-1]
    filename = "".join(ch for ch in filename if ch.isprintable()).strip() or "file"
    disposition = "attachment" if mime == "application/octet-stream" else "inline"
    encoded = quote(filename, safe="")
    return {
        "Content-Disposition": f"{disposition}; filename*=utf-8''{encoded}",
        "Content-Length": str(length),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store, no-transform",
    }


def file_response(
    stream: BinaryIO,
    name: str,
    mime: str,
    *,
    head: bool = False,
) -> Response:
    try:
        headers = download_headers(name, mime, os.fstat(stream.fileno()).st_size)
        if head:
            stream.close()
            return Response(media_type=mime, headers=headers)
        return _FileResponse(stream, mime, headers)
    except BaseException:
        stream.close()
        raise


class _FileResponse(StreamingResponse):
    """Own the verified fd until ASGI completes or the reader disconnects."""

    def __init__(self, stream: BinaryIO, mime: str, headers: dict[str, str]) -> None:
        self.stream = stream
        super().__init__(
            iter(lambda: stream.read(256 * 1024), b""),
            media_type=mime,
            headers=headers,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.stream.close()

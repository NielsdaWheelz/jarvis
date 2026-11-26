"""Temporary 100 MiB encoded transfer proof using an incremental HTTPX transport."""

import asyncio
import base64
import json
import os
import re
import resource
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from uuid import uuid4

import httpx

from jarvis.read_tools import ATTACHMENT_MAX_BYTES
from jarvis.workspace_mcp import (
    DRIVE_SCOPE,
    WorkspaceApprovals,
    WorkspaceCredential,
    WorkspaceError,
    WorkspaceMcpClient,
)

CAP = ATTACHMENT_MAX_BYTES
BLOCK = bytes(3 * 65_536)
UUID = re.compile(rb'"id":"([a-z0-9-]+)"')


class SyntheticDrive(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        method = request.headers["Mcp-Method"]
        if method != "tools/call":
            wire = json.loads(await request.aread())
            body = json.loads(
                Path(
                    f"{os.environ['JARVIS_DRIVE_CATALOG_DIR']}/jarvis-0120-unit-a-public-drive-{method.replace('/', '-')}.json"
                ).read_text()
            )
            return httpx.Response(200, json=body | {"id": wire["id"]})
        tool = request.headers["Mcp-Name"]
        if tool == "create_file":
            size = 0
            expected = 4 * ((CAP + 2) // 3)
            request_body_bytes = 0
            marker = b'"base64Content":"'
            digest = sha256()
            id = None
            async for chunk in request.stream:
                request_body_bytes += len(chunk)
                if id is None:
                    id = UUID.search(chunk)[1].decode()
                    assert chunk.endswith(marker)
                elif chunk == b'"}}}':
                    assert size == expected
                else:
                    size += len(chunk)
                    digest.update(base64.b64decode(chunk, validate=True))
            assert request_body_bytes == int(request.headers["Content-Length"])
            assert digest.hexdigest() == expected_digest()
            return httpx.Response(
                200,
                json={
                    "id": id,
                    "jsonrpc": "2.0",
                    "result": {
                        "resultType": "complete",
                        "structuredContent": {"id": "bounded"},
                    },
                },
            )
        wire = json.loads(await request.aread())
        if wire["params"]["arguments"]["fileId"] == "error":
            return httpx.Response(
                503,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(CAP),
                },
                stream=DoNotRead(),
            )
        lead = (
            json.dumps({"id": wire["id"], "jsonrpc": "2.0"})[:-1].encode()
            + b',"result":{"resultType":"complete","structuredContent":'
            + b'{"id":"bounded","title":"bound.bin","mimeType":"application/octet-stream","content":"'
        )
        trail = b'"}}}'
        length = CAP if wire["params"]["arguments"]["fileId"] == "bounded" else CAP + 1
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json",
            },
            stream=ZeroReply(lead, trail, length),
        )


class DoNotRead(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("download tried to consume an oversized error body")
        yield b""


class ZeroReply(httpx.AsyncByteStream):
    def __init__(self, prefix, suffix, size):
        self.prefix, self.suffix, self.size = prefix, suffix, size

    async def __aiter__(self):
        yield self.prefix
        complete, tail = divmod(self.size, len(BLOCK))
        for _ in range(complete):
            yield base64.b64encode(BLOCK)
        yield base64.b64encode(BLOCK[:tail])
        yield self.suffix


def expected_digest():
    digest = sha256()
    complete, tail = divmod(CAP, len(BLOCK))
    for _ in range(complete):
        digest.update(BLOCK)
    digest.update(BLOCK[:tail])
    return digest.hexdigest()


async def main():
    grant = uuid4()

    async def credential(*_):
        return WorkspaceCredential("fixture", frozenset({DRIVE_SCOPE}))

    async def no_interaction(*_):
        raise AssertionError("unexpected quota or consent")

    @asynccontextmanager
    async def scratch(reserved):
        assert 0 < reserved < 1024**3
        with TemporaryDirectory(prefix="jarvis-drive-reservation-") as directory:
            yield Path(directory)

    async with httpx.AsyncClient(transport=SyntheticDrive()) as http:
        client = WorkspaceMcpClient(
            http,
            credential=credential,
            debit=no_interaction,
            approvals=WorkspaceApprovals(audit=no_interaction),
            transfer_scratch=scratch,
        )
        settings = dict(grant_id=grant, invocation_id="binary-bound", background=False)
        with TemporaryDirectory(prefix="jarvis-drive-wire-bound-") as directory:
            path = Path(directory) / "upload.bin"
            with path.open("xb") as out:
                out.truncate(CAP)
            result = await client.call(
                "drive",
                "create_file",
                {
                    "title": "bound.bin",
                    "parentId": "private",
                    "contentMimeType": "application/octet-stream",
                    "disableConversionToGoogleType": True,
                },
                **settings,
                upload=(path, CAP),
            )
            assert result["id"] == "bounded"
        with TemporaryFile() as destination:
            data = await client.call(
                "drive",
                "download_file_content",
                {"fileId": "bounded"},
                **settings,
                download=(destination, CAP),
            )
            assert data["size"] == CAP and data["sha256"] == expected_digest()
        with TemporaryFile() as destination:
            try:
                await client.call(
                    "drive",
                    "download_file_content",
                    {"fileId": "above"},
                    **settings,
                    download=(destination, CAP),
                )
            except WorkspaceError as exc:
                assert exc.kind == "too_large"
            else:
                raise AssertionError("oversized transfer accepted")
        with TemporaryFile() as destination:
            try:
                await client.call(
                    "drive",
                    "download_file_content",
                    {"fileId": "error"},
                    **settings,
                    download=(destination, CAP),
                )
            except WorkspaceError as exc:
                assert exc.kind == "partial"
            else:
                raise AssertionError("oversized error body accepted")
    print("100 MiB upload and download verified; rejected 100 MiB + 1")
    print("host process maxrss:", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


if __name__ == "__main__":
    asyncio.run(main())

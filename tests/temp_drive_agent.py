"""Temporary ADR 0120 integration probe. Catalogs are unauthenticated public discovery."""
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx

from jarvis.workspace_mcp import (
    WorkspaceApprovals,
    WorkspaceCredential,
    WorkspaceError,
    WorkspaceMcpClient,
)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


async def main():
    catalogs = {
        (product, method): json.loads(
            Path(f"/tmp/jarvis-0120-unit-a-public-{product}-{method.replace('/', '-')}.json")
            .read_text()
        )
        for product in ("drive", "docs")
        for method in ("server/discover", "tools/list")
    }
    captures = []
    scopes = {DRIVE_SCOPE}

    async def provider(request):
        wire = json.loads(await request.aread())
        product = request.url.host.split("mcp.", 1)[0]
        assert request.url.path == "/mcp/v1"
        assert request.headers["Mcp-Protocol-Version"] == "2026-07-28"
        if wire["method"] in {"server/discover", "tools/list"}:
            body = catalogs[product, wire["method"]]
            return httpx.Response(200, json=body | {"id": wire["id"]})
        captures.append((product, wire["params"]["name"], wire["params"]["arguments"]))
        result = {"resultType": "complete", "structuredContent": {"id": "drive_test"}}
        if wire["params"]["name"] == "create_file":
            result = {"isError": True, "_meta": {"google.com/error": {
                "status": "RESOURCE_EXHAUSTED", "code": 429,
            }}}
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": wire["id"], "result": result},
            headers={"Retry-After": "60"},
        )

    async def credential(grant, _):
        assert grant == grant_id
        return WorkspaceCredential("synthetic", frozenset(scopes))

    async def audit(_):
        raise AssertionError("no interactive form expected")

    async def debit(*_):
        raise AssertionError("Drive must not consume Gmail quota")

    async def expect(kind, fn):
        try:
            await fn
        except WorkspaceError as exc:
            assert exc.kind == kind, (exc.kind, kind)
            assert exc.retry_at is not None if kind == "rate_limited" else True
        else:
            raise AssertionError(f"expected {kind}")

    grant_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        client = WorkspaceMcpClient(
            http,
            credential=credential,
            debit=debit,
            approvals=WorkspaceApprovals(audit=audit),
        )
        identity = dict(grant_id=grant_id, invocation_id="test")
        assert await client.call(
            "drive", "get_file_metadata", {"fileId": "drive_test"},
            **identity, background=False
        ) == {"id": "drive_test"}
        assert await client.call(
            "docs", "read_doc", {"documentId": "drive_test"},
            **identity, background=False
        ) == {"id": "drive_test"}
        await expect("denied", client.call(
            "drive", "create_file", {"title": "x"},
            **identity, background=True
        ))
        await expect("rate_limited", client.call(
            "drive", "create_file", {"title": "x"},
            **identity, background=False
        ))
        scopes.clear()
        await expect("scope_missing", client.call(
            "docs", "read_doc", {"documentId": "drive_test"},
            **identity, background=False
        ))
        assert captures == [
            ("drive", "get_file_metadata", {"fileId": "drive_test"}),
            ("docs", "read_doc", {"documentId": "drive_test"}),
            ("drive", "create_file", {"title": "x"}),
        ]


if __name__ == "__main__":
    asyncio.run(main())

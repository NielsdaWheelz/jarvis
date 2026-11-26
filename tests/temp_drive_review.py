"""Temporary reproductions of the unit A Opus findings."""

import asyncio
import base64
import json
from hashlib import sha256
from tempfile import TemporaryFile
from uuid import uuid4

from jarvis.workspace_mcp import (
    WorkspaceApprovals,
    WorkspaceError,
    WorkspaceMcpClient,
    _download_envelope,
)


def assert_wire(title, data, *, both, escaped=False, sse=False):
    file = {
        "content": base64.b64encode(data).decode(),
        "title": title,
        "id": "source1",
        "mimeType": "application/octet-stream",
    }
    result = {"resultType": "complete", "structuredContent": file}
    block = json.dumps(file)
    if escaped:
        block = block.replace("/", "\\/").replace("=", "\\u003d")
    if both:
        result["content"] = [{"type": "text", "text": block}]
    frame = json.dumps({"jsonrpc": "2.0", "id": "1", "result": result})
    if escaped:
        frame = frame.replace("/", "\\/").replace("=", "\\u003d")
    mime = "application/json"
    if sse:
        frame = "event: message\r\ndata: " + frame + "\r\n\r\n"
        mime = "text/event-stream"
    with TemporaryFile() as wire, TemporaryFile() as output:
        wire.write(frame.encode())
        wire.flush()
        decoded = _download_envelope(wire, mime, "1", output, len(data))
        assert output.read() == data
    assert decoded["result"]["structuredContent"] == {
        k: v for k, v in file.items() if k != "content"
    } | {"size": len(data), "sha256": sha256(data).hexdigest()}


async def cancellation(*, revoked):
    gate = asyncio.Event()

    async def credential(*_):
        raise AssertionError("cancel path must not request a credential")

    async def quiet(*_):
        pass

    client = WorkspaceMcpClient(
        None,
        credential=credential,
        debit=quiet,
        approvals=WorkspaceApprovals(audit=quiet),
    )
    grant = uuid4()

    async def entered(*_, **__):
        gate.set()
        await asyncio.sleep(3600)

    client._rpc = entered
    reading = asyncio.create_task(
        client._read_rpc(grant, "drive", "tools/call", {}, "t", 1)
    )
    await gate.wait()
    if revoked:
        client.invalidate_drive(grant)
    else:
        reading.cancel()
    try:
        await reading
    except asyncio.CancelledError:
        assert not revoked
    except WorkspaceError as exc:
        assert revoked and exc.kind == "scope_missing"
        assert reading.cancelling() == 0
    else:
        raise AssertionError("interrupted Drive read returned a value")


if __name__ == "__main__":
    assert_wire("return.pdf", b"%PDF-1.7 real", both=True)
    assert_wire('x","content":"QUJD', b"%PDF-1.7 real", both=True)
    assert_wire('notes "content":"AA" v2', b"%PDF-1.7 real", both=False)
    assert_wire("🤔 \\ path", b"\xff\xff\xff\xff", both=False, escaped=True)
    assert_wire(
        'large "file" 🤔',
        b"A" * 500_001 + b"\xff\xff\xff\x01",
        both=True,
        escaped=True,
        sse=True,
    )
    asyncio.run(cancellation(revoked=False))
    asyncio.run(cancellation(revoked=True))

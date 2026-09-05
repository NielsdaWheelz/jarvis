from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import pytest
from llm_tools import SafeWebReader, WebReadLimits
from llm_tools.web.contracts import (
    InvalidUpstreamResponse,
    TooLarge,
    UnsafeDestination,
    UnsupportedContent,
    WebReadFailure,
)
from llm_tools.web.reader import ConnectedStream

PUBLIC = "93.184.216.34"


class _Resolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]]) -> None:
        self.addresses = addresses

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        del port
        return self.addresses[hostname]


class _Writer:
    def __init__(self) -> None:
        self.request = b""

    def write(self, data: bytes) -> None:
        self.request += data

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


class _Connector:
    def __init__(self, responses: list[bytes], peers: list[str] | None = None) -> None:
        self.responses = responses
        self.peers = peers or [PUBLIC] * len(responses)
        self.writers: list[_Writer] = []

    async def connect(
        self,
        address: str,
        port: int,
        *,
        hostname: str,
        tls: bool,
        timeout_seconds: float,
    ) -> ConnectedStream:
        del address, port, hostname, tls, timeout_seconds
        reader = asyncio.StreamReader()
        reader.feed_data(self.responses.pop(0))
        reader.feed_eof()
        writer = _Writer()
        self.writers.append(writer)
        return ConnectedStream(
            reader=reader,
            writer=cast(Any, writer),
            peer_address=self.peers.pop(0),
        )


def _response(
    body: bytes,
    *,
    content_type: str = "text/plain",
    status: str = "200 OK",
    headers: tuple[tuple[str, str], ...] = (),
) -> bytes:
    fields = [
        f"HTTP/1.1 {status}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        *(f"{name}: {value}" for name, value in headers),
        "",
        "",
    ]
    return "\r\n".join(fields).encode() + body


async def test_reader_rejects_any_private_dns_answer_before_connect() -> None:
    connector = _Connector([])
    reader = SafeWebReader(
        resolver=_Resolver({"public.example": (PUBLIC, "127.0.0.1")}),
        connector=connector,
    )

    with pytest.raises(WebReadFailure) as raised:
        await reader.read("https://public.example/")

    assert isinstance(raised.value.error, UnsafeDestination)
    assert raised.value.attempts == 0
    assert connector.writers == []


async def test_reader_rejects_rebound_peer_and_private_redirect() -> None:
    rebound = SafeWebReader(
        resolver=_Resolver({"public.example": (PUBLIC,)}),
        connector=_Connector([_response(b"ok")], peers=["127.0.0.1"]),
    )
    with pytest.raises(WebReadFailure) as peer:
        await rebound.read("https://public.example/")
    assert isinstance(peer.value.error, UnsafeDestination)
    assert peer.value.attempts == 1

    connector = _Connector(
        [
            _response(
                b"",
                status="302 Found",
                headers=(("Location", "http://private.example/"),),
            )
        ]
    )
    redirected = SafeWebReader(
        resolver=_Resolver(
            {
                "public.example": (PUBLIC,),
                "private.example": ("169.254.169.254",),
            }
        ),
        connector=connector,
    )
    with pytest.raises(WebReadFailure) as redirect:
        await redirected.read("https://public.example/")
    assert isinstance(redirect.value.error, UnsafeDestination)
    assert redirect.value.attempts == 1
    assert len(connector.writers) == 1


@pytest.mark.parametrize(
    ("response", "limits", "error_type"),
    [
        (
            _response(b"binary", content_type="image/png"),
            WebReadLimits(),
            UnsupportedContent,
        ),
        (
            _response(b"too large"),
            WebReadLimits(max_wire_bytes=4),
            TooLarge,
        ),
        (
            _response(
                b"",
                status="302 Found",
                headers=(("Location", "https://public.example/again"),),
            ),
            WebReadLimits(max_redirects=0),
            InvalidUpstreamResponse,
        ),
    ],
)
async def test_reader_rejects_media_size_and_redirect_overflow(
    response: bytes,
    limits: WebReadLimits,
    error_type: type[object],
) -> None:
    reader = SafeWebReader(
        resolver=_Resolver({"public.example": (PUBLIC,)}),
        connector=_Connector([response]),
        limits=limits,
    )
    with pytest.raises(WebReadFailure) as raised:
        await reader.read("https://public.example/")
    assert isinstance(raised.value.error, error_type)


@pytest.mark.parametrize(
    ("media_type", "body", "extraction", "expected"),
    [
        ("text/plain", b"literal &amp;amp;", "plain-text-v2", "literal &amp;amp;"),
        (
            "text/html",
            (
                b"<title>Visible</title><script>do_not_execute()</script>"
                b"<p>literal &amp;amp;</p><img src='https://sub.example/x'>"
            ),
            "html-visible-text-v2",
            "Visible literal &amp;",
        ),
    ],
)
async def test_reader_sends_no_credentials_or_subrequests_and_extracts_once(
    media_type: str,
    body: bytes,
    extraction: str,
    expected: str,
) -> None:
    connector = _Connector([_response(body, content_type=media_type)])
    reader = SafeWebReader(
        resolver=_Resolver({"public.example": (PUBLIC,)}),
        connector=connector,
    )

    response = await reader.read("https://public.example/")

    assert response.value.text == expected
    locator = cast("dict[str, object]", json.loads(response.value.evidence.locator))
    assert locator["extraction"] == extraction
    assert len(connector.writers) == 1
    request = connector.writers[0].request.lower()
    assert b"cookie:" not in request
    assert b"authorization:" not in request
    assert b"do_not_execute" not in response.value.text.encode()

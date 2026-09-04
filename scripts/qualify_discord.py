#!/usr/bin/env python3
"""Run the paid, content-sanitized Slice 1 Discord qualification."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from uuid import uuid4

import httpx

from jarvis.config import DiscordSettings
from jarvis.discord import (
    DISCORD_API_BASE_URL,
    SUPPRESS_EMBEDS,
    DeliveryFailed,
    DeliverySucceeded,
    DiscordCreateMessageClient,
    DiscordGateway,
    DiscordOwnerMessage,
    gateway_intents,
)


@dataclass(slots=True)
class _LostAcceptedGeneration(httpx.AsyncBaseTransport):
    transport: httpx.AsyncHTTPTransport
    request_controls: list[tuple[str, bool, bool, int]]
    accepted_message_id: str | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.request_controls.append(
            (
                body["nonce"],
                body["enforce_nonce"],
                body["allowed_mentions"] == {"parse": []},
                body["flags"],
            )
        )
        if self.accepted_message_id is None:
            response = await self.transport.handle_async_request(request)
            if response.status_code != 200:
                return response
            payload = json.loads(await response.aread())
            self.accepted_message_id = payload["id"]
            await response.aclose()
        raise httpx.ReadTimeout("injected lost accepted response", request=request)

    async def aclose(self) -> None:
        await self.transport.aclose()


@dataclass(slots=True)
class _RecordingTransport(httpx.AsyncBaseTransport):
    transport: httpx.AsyncHTTPTransport
    request_controls: list[tuple[str, bool, bool, int]]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.request_controls.append(
            (
                body["nonce"],
                body["enforce_nonce"],
                body["allowed_mentions"] == {"parse": []},
                body["flags"],
            )
        )
        return await self.transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self.transport.aclose()


async def _gateway_probe(settings: DiscordSettings) -> tuple[int, int, int]:
    accepted = 0
    completed = asyncio.Event()
    gateway: DiscordGateway

    async def sink(message: DiscordOwnerMessage) -> None:
        nonlocal accepted
        del message
        accepted += 1

    async def ready() -> None:
        await gateway.catch_up(None)
        completed.set()
        await gateway.close()

    gateway = DiscordGateway(settings, sink, ready_handler=ready)
    await asyncio.wait_for(
        gateway.start(settings.bot_token.get_secret_value()),
        timeout=60.0,
    )
    if gateway.event_failed or not completed.is_set():
        raise RuntimeError("Discord Gateway qualification did not complete cleanly")
    intents = gateway_intents()
    enabled_intents = sum(
        int(value)
        for name, value in (
            ("guilds", intents.guilds),
            ("guild_messages", intents.guild_messages),
            ("message_content", intents.message_content),
        )
        if name
    )
    return accepted, enabled_intents, 3


async def _delivery_probe(settings: DiscordSettings) -> tuple[int, int, int]:
    content = f"Jarvis Slice 1 Discord qualification {uuid4()}"
    recorded: list[tuple[str, bool, bool, int]] = []
    first_transport = _LostAcceptedGeneration(httpx.AsyncHTTPTransport(), recorded)
    persisted_message_id = uuid4()
    result: DeliverySucceeded | None = None
    headers = {"Authorization": "Bot " + settings.bot_token.get_secret_value()}
    try:
        async with httpx.AsyncClient(transport=first_transport) as client:
            first = await DiscordCreateMessageClient(settings, client).create_message(
                persisted_message_id=persisted_message_id,
                content=content,
            )
            if not isinstance(first, DeliveryFailed) or first.attempts != 3:
                raise RuntimeError("lost response generation did not exhaust cleanly")

        second_transport = _RecordingTransport(httpx.AsyncHTTPTransport(), recorded)
        async with httpx.AsyncClient(transport=second_transport) as client:
            delivered = await DiscordCreateMessageClient(
                settings, client
            ).create_message(
                persisted_message_id=persisted_message_id,
                content=content,
            )
            if not isinstance(delivered, DeliverySucceeded):
                raise RuntimeError("Discord restart delivery qualification failed")
            result = delivered
        if result.discord_message_id != first_transport.accepted_message_id:
            raise RuntimeError("Discord restart did not return provider identity")
        if len(recorded) != 4 or len({item[0] for item in recorded}) != 1:
            raise RuntimeError("Discord retry did not reuse one nonce")
        if any(
            not enforce or not mentions_suppressed or flags != SUPPRESS_EMBEDS
            for _, enforce, mentions_suppressed, flags in recorded
        ):
            raise RuntimeError("Discord create controls changed across retry")

        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            response = await client.get(
                f"{DISCORD_API_BASE_URL}/channels/{settings.channel_id}/messages",
                params={"limit": 50},
            )
            response.raise_for_status()
            messages = response.json()
            visible = sum(item.get("content") == content for item in messages)
            if visible != 1:
                raise RuntimeError(
                    "lost-ack retry did not leave exactly one visible message"
                )
        return first.attempts, result.attempts, visible
    finally:
        message_id = (
            result.discord_message_id
            if result is not None
            else first_transport.accepted_message_id
        )
        if message_id is not None:
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                response = await client.delete(
                    f"{DISCORD_API_BASE_URL}/channels/{settings.channel_id}/messages/{message_id}"
                )
                if response.status_code not in {204, 404}:
                    raise RuntimeError("Discord qualification cleanup failed")


async def _run() -> dict[str, object]:
    settings = DiscordSettings.from_env()
    accepted, enabled_intents, expected_intents = await _gateway_probe(settings)
    first_attempts, restart_attempts, visible = await _delivery_probe(settings)
    return {
        "catch_up_owner_messages_accepted": accepted,
        "ambiguous_generation_attempts": first_attempts,
        "enabled_required_intents": enabled_intents,
        "expected_required_intents": expected_intents,
        "lost_ack_visible_messages": visible,
        "permissions": "required-present-prohibited-absent",
        "request_controls": "enforced-nonce-empty-mentions-suppress-embeds",
        "restart_generation_attempts": restart_attempts,
        "status": "passed",
        "synthetic_message_removed": True,
    }


def main() -> int:
    try:
        if os.environ.get("JARVIS_DISCORD_LIVE") != "1":
            raise ValueError("live qualification requires JARVIS_DISCORD_LIVE=1")
        result = asyncio.run(_run())
    except BaseException:
        result = {"status": "failed"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Deliver private notification links through Discord REST."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from uuid import UUID

import httpx

from jarvis.config import DiscordSettings

DISCORD_API_BASE_URL = "https://discord.com/api/v10"
DISCORD_MAX_CONTENT_CHARACTERS = 2_000
SUPPRESS_EMBEDS = 1 << 2
MAX_RETRY_AFTER_SLEEP_SECONDS = 30.0


def discord_nonce(message_id: UUID | str) -> str:
    """Derive the exact 20-character v1 Discord nonce from a message UUID."""

    try:
        value = message_id if isinstance(message_id, UUID) else UUID(message_id)
        canonical = str(value).lower()
    except (AttributeError, ValueError) as exc:
        raise ValueError("message_id must be a UUID") from exc
    digest = hashlib.sha256(f"jarvis-discord-v1:{canonical}".encode()).digest()
    return base64.urlsafe_b64encode(digest[:15]).decode("ascii").rstrip("=")


class DeliveryFailureKind(StrEnum):
    """Sanitized transport failure classes suitable for bounded diagnostics."""

    REJECTED = "rejected"
    RATE_LIMITED = "rate_limited"
    TRANSPORT = "transport"
    SERVER = "server"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True, slots=True)
class DeliverySucceeded:
    discord_message_id: str
    attempts: int


@dataclass(frozen=True, slots=True)
class DeliveryFailed:
    kind: DeliveryFailureKind
    attempts: int
    retryable: bool
    ambiguous: bool
    http_status: int | None = None
    retry_after_seconds: float | None = None


type DeliveryResult = DeliverySucceeded | DeliveryFailed


type Sleep = Callable[[float], Awaitable[None]]


def _retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if header is not None:
        try:
            value = float(header)
        except ValueError:
            value = -1.0
        if value >= 0.0:
            return value
    try:
        raw_body = cast(object, response.json())
    except ValueError:
        return None
    if not isinstance(raw_body, dict):
        return None
    body = cast("dict[str, object]", raw_body)
    value = body.get("retry_after")
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


class DiscordCreateMessageClient:
    """Typed direct REST v10 Create Message binding with enforced nonce."""

    def __init__(
        self,
        settings: DiscordSettings,
        http_client: httpx.AsyncClient,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._sleep = sleep

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult:
        """Create or recently deduplicate one persisted assistant message."""

        if not content or len(content) > DISCORD_MAX_CONTENT_CHARACTERS:
            raise ValueError("Discord content must contain 1 to 2000 characters")

        nonce = discord_nonce(persisted_message_id)
        return await self._deliver(
            lambda: self._create_request(
                content=content,
                nonce=nonce,
            )
        )

    async def _deliver(
        self,
        request: Callable[[], Awaitable[httpx.Response]],
    ) -> DeliveryResult:
        """Apply one bounded response and retry policy to host-owned requests."""

        for attempt in range(1, self._settings.delivery_max_attempts + 1):
            try:
                response = await request()
            except httpx.RequestError:
                failure = DeliveryFailed(
                    kind=DeliveryFailureKind.TRANSPORT,
                    attempts=attempt,
                    retryable=True,
                    ambiguous=True,
                )
            else:
                if response.status_code == 200:
                    try:
                        payload = cast(object, response.json())
                    except ValueError:
                        payload = None
                    message_id = (
                        cast("dict[str, object]", payload).get("id")
                        if isinstance(payload, dict)
                        else None
                    )
                    if (
                        isinstance(message_id, str)
                        and message_id.isascii()
                        and message_id.isdecimal()
                        and int(message_id) > 0
                    ):
                        return DeliverySucceeded(message_id, attempt)
                    failure = DeliveryFailed(
                        kind=DeliveryFailureKind.INVALID_RESPONSE,
                        attempts=attempt,
                        retryable=True,
                        ambiguous=True,
                        http_status=response.status_code,
                    )
                elif response.status_code == 429:
                    failure = DeliveryFailed(
                        kind=DeliveryFailureKind.RATE_LIMITED,
                        attempts=attempt,
                        retryable=True,
                        ambiguous=False,
                        http_status=response.status_code,
                        retry_after_seconds=_retry_after_seconds(response),
                    )
                elif response.status_code == 408 or 500 <= response.status_code <= 599:
                    failure = DeliveryFailed(
                        kind=DeliveryFailureKind.SERVER,
                        attempts=attempt,
                        retryable=True,
                        ambiguous=True,
                        http_status=response.status_code,
                    )
                else:
                    failure = DeliveryFailed(
                        kind=DeliveryFailureKind.REJECTED,
                        attempts=attempt,
                        retryable=False,
                        ambiguous=False,
                        http_status=response.status_code,
                    )
            if not failure.retryable or attempt == self._settings.delivery_max_attempts:
                return failure
            delay = self._settings.delivery_retry_delays_seconds[attempt - 1]
            if failure.retry_after_seconds is not None:
                if failure.retry_after_seconds > MAX_RETRY_AFTER_SLEEP_SECONDS:
                    return failure
                delay = max(delay, failure.retry_after_seconds)
            await self._sleep(delay)
        raise AssertionError("delivery policy made no attempt")  # pragma: no cover

    async def _create_request(self, *, content: str, nonce: str) -> httpx.Response:
        return await self._http_client.post(
            f"{DISCORD_API_BASE_URL}/channels/{self._settings.channel_id}/messages",
            headers={
                "Authorization": "Bot " + self._settings.bot_token.get_secret_value(),
                "Content-Type": "application/json",
            },
            json={
                "content": content,
                "nonce": nonce,
                "enforce_nonce": True,
                "allowed_mentions": {"parse": []},
                "flags": SUPPRESS_EMBEDS,
            },
            timeout=self._settings.request_timeout_seconds,
        )

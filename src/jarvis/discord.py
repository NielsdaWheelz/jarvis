"""One-channel Discord ingress and delivery.

Discord is a host transport. Nothing in this module is a model-callable tool.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

import discord
import httpx

from jarvis.attachments import DiscordUpload
from jarvis.config import DiscordSettings

LOGGER = logging.getLogger(__name__)

DISCORD_API_BASE_URL = "https://discord.com/api/v10"
DISCORD_MAX_CONTENT_CHARACTERS = 2_000
SUPPRESS_EMBEDS = 1 << 2
MAX_RETRY_AFTER_SLEEP_SECONDS = 30.0

REQUIRED_CHANNEL_PERMISSIONS = frozenset(
    {"view_channel", "send_messages", "attach_files", "read_message_history"}
)
PROHIBITED_CHANNEL_PERMISSIONS = frozenset(
    {
        "administrator",
        "manage_guild",
        "manage_channels",
        "manage_messages",
        "manage_threads",
        "manage_roles",
        "manage_webhooks",
        "moderate_members",
        "kick_members",
        "ban_members",
    }
)


class DiscordConfigurationError(RuntimeError):
    """The live Discord surface does not match configured authority."""


class Control(StrEnum):
    """Host-owned controls intercepted before model work."""

    PAUSE = "pause"
    RESUME = "resume"


def classify_control(content: str) -> Control | None:
    """Classify only an exact, trimmed, case-insensitive control message."""

    try:
        return Control(content.strip().casefold())
    except ValueError:
        return None


def gateway_intents() -> discord.Intents:
    """Return exactly GUILDS, GUILD_MESSAGES, and MESSAGE_CONTENT."""

    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True
    return intents


@dataclass(frozen=True, slots=True)
class DiscordOwnerMessage:
    """The plain canonical input extracted from an accepted Gateway event."""

    source_message_id: str
    source_conversation_id: str
    text: str
    created_at: datetime
    control: Control | None
    uploads: tuple[DiscordUpload, ...] = ()


def owner_message_from_event(
    message: discord.Message,
    settings: DiscordSettings,
) -> DiscordOwnerMessage | None:
    """Accept owner captions and uploads in the configured guild channel."""

    if message.guild is None or message.guild.id != settings.guild_id:
        return None
    if (
        message.channel.id != settings.channel_id
        or message.channel.type != discord.ChannelType.text
    ):
        return None
    if message.author.id != settings.owner_user_id or message.author.bot:
        return None
    if message.webhook_id is not None:
        return None
    if message.type not in {discord.MessageType.default, discord.MessageType.reply}:
        return None
    if not message.content.strip() and not message.attachments:
        return None
    if message.created_at.tzinfo is None or message.created_at.utcoffset() is None:
        raise DiscordConfigurationError("Discord supplied a naive message timestamp")

    return DiscordOwnerMessage(
        source_message_id=str(message.id),
        source_conversation_id=str(settings.channel_id),
        text=message.content,
        created_at=message.created_at,
        control=classify_control(message.content),
        uploads=tuple(
            DiscordUpload(
                source={
                    "kind": "discord",
                    "guild_id": str(settings.guild_id),
                    "channel_id": str(settings.channel_id),
                    "message_id": str(message.id),
                    "attachment_id": str(upload.id),
                },
                filename=upload.filename,
                media_type=upload.content_type,
                advertised_size=upload.size,
            )
            for upload in message.attachments
        ),
    )


def validate_channel_permissions(permissions: discord.Permissions) -> None:
    """Reject missing operational permissions or prohibited management power."""

    missing = sorted(
        name for name in REQUIRED_CHANNEL_PERMISSIONS if not getattr(permissions, name)
    )
    prohibited = sorted(
        name for name in PROHIBITED_CHANNEL_PERMISSIONS if getattr(permissions, name)
    )
    if missing or prohibited:
        parts: list[str] = []
        if missing:
            parts.append(f"missing required permissions: {', '.join(missing)}")
        if prohibited:
            parts.append(f"prohibited permissions present: {', '.join(prohibited)}")
        raise DiscordConfigurationError("; ".join(parts))


class HistoryChannel(Protocol):
    """The public ``discord.py`` history surface used by bounded catch-up."""

    id: int
    guild: discord.Guild
    type: discord.ChannelType

    def history(
        self,
        *,
        limit: int | None,
        before: discord.abc.Snowflake | datetime | None = None,
        after: discord.abc.Snowflake | datetime | None = None,
        around: discord.abc.Snowflake | datetime | None = None,
        oldest_first: bool | None = None,
    ) -> AsyncIterator[discord.Message]: ...


type OwnerMessageSink = Callable[[DiscordOwnerMessage], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CatchUpResult:
    """A bounded history scan summary without message content."""

    scanned: int
    accepted: int
    reached_scan_limit: bool
    last_scanned_source_message_id: str | None


def _source_snowflake(source_message_id: str | None) -> discord.Object | None:
    if source_message_id is None:
        return None
    if (
        not source_message_id
        or not source_message_id.isascii()
        or not source_message_id.isdecimal()
    ):
        raise DiscordConfigurationError("stored Discord message ID is malformed")
    value = int(source_message_id)
    if value <= 0 or str(value) != source_message_id:
        raise DiscordConfigurationError("stored Discord message ID is malformed")
    return discord.Object(id=value)


async def bounded_catch_up(
    channel: HistoryChannel,
    *,
    settings: DiscordSettings,
    after_source_message_id: str | None,
    sink: OwnerMessageSink,
) -> CatchUpResult:
    """Persist accepted inputs from Discord's newest bounded history page."""

    if (
        channel.guild.id != settings.guild_id
        or channel.id != settings.channel_id
        or channel.type != discord.ChannelType.text
    ):
        raise DiscordConfigurationError("catch-up channel does not match configuration")

    after = _source_snowflake(after_source_message_id)
    events: list[discord.Message] = []
    async for event in channel.history(
        limit=settings.catch_up_limit,
        after=after,
        oldest_first=False,
    ):
        if len(events) >= settings.catch_up_limit:
            break
        events.append(event)
    events.reverse()

    accepted = 0
    last_scanned_source_message_id = None
    for event in events:
        last_scanned_source_message_id = str(event.id)
        message = owner_message_from_event(event, settings)
        if message is not None:
            await sink(message)
            accepted += 1

    return CatchUpResult(
        scanned=len(events),
        accepted=accepted,
        reached_scan_limit=len(events) == settings.catch_up_limit,
        last_scanned_source_message_id=last_scanned_source_message_id,
    )


type ReadyHandler = Callable[[], Awaitable[None]]


class DiscordGateway(discord.Client):
    """The narrow Gateway ingress and typing adapter."""

    def __init__(
        self,
        settings: DiscordSettings,
        owner_message_sink: OwnerMessageSink,
        *,
        ready_handler: ReadyHandler | None = None,
    ) -> None:
        super().__init__(intents=gateway_intents())
        self._settings = settings
        self._owner_message_sink = owner_message_sink
        self._ready_handler = ready_handler
        self._event_failed = False
        self._stopping = False
        self._active_callbacks = 0
        self._callbacks_drained = asyncio.Event()
        self._callbacks_drained.set()

    @property
    def event_failed(self) -> bool:
        return self._event_failed

    def stop_ingress(self) -> None:
        self._stopping = True

    async def drain_callbacks(self) -> None:
        """Join admitted handlers without closing the HTTP client they use."""
        await self._callbacks_drained.wait()

    @contextmanager
    def _admit_callback(self) -> Iterator[bool]:
        if self._stopping:
            yield False
            return
        self._active_callbacks += 1
        self._callbacks_drained.clear()
        try:
            yield True
        finally:
            self._active_callbacks -= 1
            if self._active_callbacks == 0:
                self._callbacks_drained.set()

    async def on_ready(self) -> None:
        with self._admit_callback() as admitted:
            if not admitted:
                return
            await self.validate_live_configuration()
            if self._ready_handler is not None:
                await self._ready_handler()

    async def on_message(self, message: discord.Message) -> None:
        with self._admit_callback() as admitted:
            if not admitted:
                return
            accepted = owner_message_from_event(message, self._settings)
            if accepted is not None:
                await self._owner_message_sink(accepted)

    async def on_error(
        self,
        event_method: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        del args, kwargs
        self._event_failed = True
        LOGGER.error("Discord event failed: event=%s", event_method)
        await self.close()

    async def configured_channel(self) -> discord.TextChannel:
        guild = self.get_guild(self._settings.guild_id)
        if guild is None:
            raise DiscordConfigurationError("configured Discord guild is unavailable")

        channel = guild.get_channel(self._settings.channel_id)
        if channel is None:
            fetched = await self.fetch_channel(self._settings.channel_id)
            if not isinstance(fetched, discord.TextChannel):
                raise DiscordConfigurationError(
                    "configured Discord channel is not a guild text channel"
                )
            channel = fetched
        if (
            not isinstance(channel, discord.TextChannel)
            or channel.type != discord.ChannelType.text
            or channel.guild.id != self._settings.guild_id
        ):
            raise DiscordConfigurationError(
                "configured Discord channel is not a guild text channel"
            )
        return channel

    async def validate_live_configuration(self) -> None:
        channel = await self.configured_channel()
        validate_channel_permissions(channel.permissions_for(channel.guild.me))

    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult:
        channel = await self.configured_channel()
        return await bounded_catch_up(
            cast(HistoryChannel, channel),
            settings=self._settings,
            after_source_message_id=after_source_message_id,
            sink=self._owner_message_sink,
        )

    @asynccontextmanager
    async def typing(self) -> AsyncIterator[None]:
        """Start and maintain the configured channel's typing indicator."""

        channel = await self.configured_channel()
        async with channel.typing():
            yield


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

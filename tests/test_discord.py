from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import discord
import httpx
import pytest

from jarvis.config import DiscordSettings
from jarvis.discord import (
    SUPPRESS_EMBEDS,
    Control,
    DeliveryFailed,
    DeliveryFailureKind,
    DeliverySucceeded,
    DiscordConfigurationError,
    DiscordCreateMessageClient,
    DiscordGateway,
    DiscordOwnerMessage,
    bounded_catch_up,
    classify_control,
    discord_nonce,
    gateway_intents,
    owner_message_from_event,
    validate_channel_permissions,
)


def _settings(**changes: object) -> DiscordSettings:
    values: dict[str, object] = {
        "bot_token": "private-token",
        "owner_user_id": 11,
        "guild_id": 22,
        "channel_id": 33,
        "catch_up_limit": 3,
        "delivery_retry_delays_seconds": (0.01, 0.02),
    }
    values.update(changes)
    return DiscordSettings.model_validate(values)


def _message(**changes: object) -> discord.Message:
    values: dict[str, object] = {
        "id": 44,
        "guild": SimpleNamespace(id=22),
        "channel": SimpleNamespace(id=33, type=discord.ChannelType.text),
        "author": SimpleNamespace(id=11, bot=False),
        "webhook_id": None,
        "type": discord.MessageType.default,
        "content": "hello",
        "created_at": datetime(2026, 9, 3, 18, tzinfo=UTC),
    }
    values.update(changes)
    return cast(discord.Message, SimpleNamespace(**values))


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("stop", Control.STOP),
        ("  PaUsE\n", Control.PAUSE),
        ("RESUME", Control.RESUME),
        ("please stop", None),
        ("stop now", None),
        ("", None),
    ],
)
def test_control_classification_is_exact(
    content: str,
    expected: Control | None,
) -> None:
    assert classify_control(content) is expected


def test_gateway_enables_exactly_the_three_required_intents() -> None:
    intents = gateway_intents()
    expected = discord.Intents.none()
    expected.guilds = True
    expected.guild_messages = True
    expected.message_content = True
    assert intents.value == expected.value


def test_owner_message_is_plain_and_carries_host_control() -> None:
    incoming = owner_message_from_event(_message(content=" PAUSE "), _settings())
    assert incoming is not None
    assert incoming.source_message_id == "44"
    assert incoming.source_conversation_id == "33"
    assert incoming.text == " PAUSE "
    assert incoming.control is Control.PAUSE


@pytest.mark.parametrize(
    "changes",
    [
        {"guild": None},
        {"guild": SimpleNamespace(id=23)},
        {"channel": SimpleNamespace(id=34, type=discord.ChannelType.text)},
        {"channel": SimpleNamespace(id=33, type=discord.ChannelType.public_thread)},
        {"author": SimpleNamespace(id=12, bot=False)},
        {"author": SimpleNamespace(id=11, bot=True)},
        {"webhook_id": 1},
        {"type": discord.MessageType.pins_add},
        {"content": " \n"},
    ],
)
def test_ingress_rejects_everything_outside_the_owner_text_channel(
    changes: dict[str, object],
) -> None:
    assert owner_message_from_event(_message(**changes), _settings()) is None


def test_ingress_rejects_naive_provider_timestamp() -> None:
    with pytest.raises(DiscordConfigurationError):
        owner_message_from_event(
            _message(created_at=datetime(2026, 9, 3, 18)),
            _settings(),
        )


def _operational_permissions() -> discord.Permissions:
    permissions = discord.Permissions.none()
    permissions.update(
        view_channel=True,
        send_messages=True,
        attach_files=True,
        read_message_history=True,
    )
    return permissions


def test_permission_check_accepts_inherited_non_management_permissions() -> None:
    permissions = _operational_permissions()
    permissions.update(add_reactions=True, embed_links=True, mention_everyone=True)
    validate_channel_permissions(permissions)


def test_permission_check_rejects_missing_required_permission() -> None:
    permissions = _operational_permissions()
    permissions.update(attach_files=False)
    with pytest.raises(DiscordConfigurationError, match="attach_files"):
        validate_channel_permissions(permissions)


@pytest.mark.parametrize(
    "permission",
    [
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
    ],
)
def test_permission_check_rejects_prohibited_authority(permission: str) -> None:
    permissions = _operational_permissions()
    permissions.update(**{permission: True})
    with pytest.raises(DiscordConfigurationError, match=permission):
        validate_channel_permissions(permissions)


class _History:
    id = 33
    guild = cast(discord.Guild, SimpleNamespace(id=22))
    type = discord.ChannelType.text

    def __init__(self, messages: list[discord.Message]) -> None:
        self.messages = messages
        self.calls: list[tuple[int | None, int | None, bool | None]] = []

    async def history(
        self,
        *,
        limit: int | None,
        before: discord.abc.Snowflake | datetime | None = None,
        after: discord.abc.Snowflake | datetime | None = None,
        around: discord.abc.Snowflake | datetime | None = None,
        oldest_first: bool | None = None,
    ) -> AsyncIterator[discord.Message]:
        del before, around
        after_id = None
        if after is not None and not isinstance(after, datetime):
            after_id = after.id
        self.calls.append((limit, after_id, oldest_first))
        for message in self.messages:
            yield message


async def test_catch_up_uses_newest_bounded_page_then_persists_oldest_first() -> None:
    history = _History(
        [
            _message(id=47, content="two"),
            _message(id=46, content="ignore", author=SimpleNamespace(id=12, bot=False)),
            _message(id=45, content="one"),
            _message(id=44, content="outside-limit"),
        ]
    )
    accepted: list[str] = []

    async def sink(message: DiscordOwnerMessage) -> None:
        accepted.append(message.text)

    result = await bounded_catch_up(
        history,
        settings=_settings(),
        after_source_message_id="44",
        sink=sink,
    )
    assert history.calls == [(3, 44, False)]
    assert accepted == ["one", "two"]
    assert result.scanned == 3
    assert result.accepted == 2
    assert result.reached_scan_limit is True
    assert result.last_scanned_source_message_id == "47"


async def test_catch_up_reaches_owner_after_an_oldest_page_of_filtered_traffic() -> (
    None
):
    history = _History(
        [
            _message(id=48, content="later owner"),
            _message(id=47, content="bot", author=SimpleNamespace(id=12, bot=True)),
            _message(id=46, content="other", author=SimpleNamespace(id=12, bot=False)),
            _message(id=45, content="other", author=SimpleNamespace(id=13, bot=False)),
        ]
    )
    accepted: list[str] = []

    async def sink(message: DiscordOwnerMessage) -> None:
        accepted.append(message.text)

    result = await bounded_catch_up(
        history,
        settings=_settings(),
        after_source_message_id="44",
        sink=sink,
    )

    assert history.calls == [(3, 44, False)]
    assert accepted == ["later owner"]
    assert result.scanned == 3
    assert result.accepted == 1
    assert result.last_scanned_source_message_id == "48"


async def test_cold_catch_up_persists_newest_page_oldest_first() -> None:
    history = _History([_message(id=47, content="new"), _message(id=46, content="old")])
    accepted: list[str] = []

    async def sink(message: DiscordOwnerMessage) -> None:
        accepted.append(message.text)

    await bounded_catch_up(
        history,
        settings=_settings(),
        after_source_message_id=None,
        sink=sink,
    )
    assert history.calls == [(3, None, False)]
    assert accepted == ["old", "new"]


@pytest.mark.parametrize("cursor", ["", "-1", "01", " 1", "abc"])
async def test_catch_up_rejects_malformed_canonical_cursor(cursor: str) -> None:
    async def unused_sink(_: DiscordOwnerMessage) -> None:
        return None

    with pytest.raises(DiscordConfigurationError):
        await bounded_catch_up(
            _History([]),
            settings=_settings(),
            after_source_message_id=cursor,
            sink=unused_sink,
        )


def test_nonce_matches_the_frozen_derivation() -> None:
    identifier = UUID("12345678-1234-5678-1234-567812345678")
    assert discord_nonce(identifier) == "FqdJdPTjgFIqE0p8B9P7"
    assert discord_nonce(str(identifier).upper()) == "FqdJdPTjgFIqE0p8B9P7"
    assert len(discord_nonce(identifier)) == 20


async def test_create_message_uses_exact_host_controls_and_v10_route() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "987"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(_settings(), client).create_message(
            persisted_message_id="12345678-1234-5678-1234-567812345678",
            content="hello @everyone https://example.com",
        )
    assert result == DeliverySucceeded("987", 1)
    request = requests[0]
    assert str(request.url) == "https://discord.com/api/v10/channels/33/messages"
    assert request.headers["Authorization"] == "Bot private-token"
    body = json.loads(request.content)
    assert body == {
        "content": "hello @everyone https://example.com",
        "nonce": "FqdJdPTjgFIqE0p8B9P7",
        "enforce_nonce": True,
        "allowed_mentions": {"parse": []},
        "flags": SUPPRESS_EMBEDS,
    }


async def test_ambiguous_retries_are_finite_and_reuse_the_exact_nonce() -> None:
    bodies: list[object] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        raise httpx.ReadTimeout("lost acknowledgement", request=request)

    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(
            _settings(),
            client,
            sleep=sleep,
        ).create_message(
            persisted_message_id="12345678-1234-5678-1234-567812345678",
            content="hello",
        )
    assert result == DeliveryFailed(
        kind=DeliveryFailureKind.TRANSPORT,
        attempts=3,
        retryable=True,
        ambiguous=True,
    )
    assert sleeps == [0.01, 0.02]
    assert len(bodies) == 3
    assert bodies[0] == bodies[1] == bodies[2]


async def test_lost_accepted_response_retries_with_provider_identity() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("lost acknowledgement", request=request)
        return httpx.Response(200, json={"id": "987"})

    async def sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(
            _settings(), client, sleep=sleep
        ).create_message(
            persisted_message_id="12345678-1234-5678-1234-567812345678",
            content="hello",
        )
    assert result == DeliverySucceeded("987", 2)


async def test_rate_limit_honors_bounded_retry_after() -> None:
    calls = 0
    sleeps: list[float] = []

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"retry_after": 0.015})
        return httpx.Response(200, json={"id": "987"})

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(
            _settings(), client, sleep=sleep
        ).create_message(
            persisted_message_id="12345678-1234-5678-1234-567812345678",
            content="hello",
        )
    assert result == DeliverySucceeded("987", 2)
    assert sleeps == [0.015]


async def test_unbounded_retry_after_defers_without_sleeping() -> None:
    sleeps: list[float] = []

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "31"})

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(
            _settings(), client, sleep=sleep
        ).create_message(
            persisted_message_id="12345678-1234-5678-1234-567812345678",
            content="hello",
        )
    assert isinstance(result, DeliveryFailed)
    assert result.attempts == 1
    assert result.retry_after_seconds == 31.0
    assert sleeps == []


@pytest.mark.parametrize("content", ["", "x" * 2_001])
async def test_create_rejects_content_outside_discord_bounds(content: str) -> None:
    async with httpx.AsyncClient() as client:
        delivery = DiscordCreateMessageClient(_settings(), client)
        with pytest.raises(ValueError):
            await delivery.create_message(
                persisted_message_id="12345678-1234-5678-1234-567812345678",
                content=content,
            )


def test_gateway_can_be_constructed_with_narrow_intents() -> None:
    async def sink(_: DiscordOwnerMessage) -> None:
        return None

    gateway = DiscordGateway(_settings(), sink)
    assert gateway.intents.value == gateway_intents().value

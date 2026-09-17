from __future__ import annotations

import asyncio
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
    ApprovalComponentDecision,
    Control,
    DeliveryFailed,
    DeliveryFailureKind,
    DeliverySucceeded,
    DiscordConfigurationError,
    DiscordCreateMessageClient,
    DiscordGateway,
    DiscordInteractionRejected,
    DiscordOwnerMessage,
    acknowledge_and_disable_approval,
    approval_components,
    approval_custom_id,
    approval_interaction_from_event,
    bounded_catch_up,
    classify_control,
    discord_nonce,
    gateway_intents,
    owner_message_from_event,
    parse_approval_custom_id,
    validate_approval_interaction_relationship,
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


ACTION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
APPROVAL_MESSAGE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _approval_interaction(**changes: object) -> discord.Interaction:
    values: dict[str, object] = {
        "type": discord.InteractionType.component,
        "data": {
            "component_type": 2,
            "custom_id": approval_custom_id(
                ACTION_ID,
                APPROVAL_MESSAGE_ID,
                ApprovalComponentDecision.APPROVE,
            ),
        },
        "user": SimpleNamespace(id=11, bot=False),
        "guild_id": 22,
        "channel_id": 33,
        "message": SimpleNamespace(id=987),
    }
    values.update(changes)
    return cast(discord.Interaction, SimpleNamespace(**values))


async def test_gateway_routes_only_valid_approval_component_events() -> None:
    owner_messages: list[DiscordOwnerMessage] = []
    interactions: list[object] = []

    async def owner_sink(message: DiscordOwnerMessage) -> None:
        owner_messages.append(message)

    async def interaction_sink(
        event: discord.Interaction,
        accepted: object,
    ) -> None:
        interactions.append((event, accepted))

    gateway = DiscordGateway(
        _settings(),
        owner_sink,
        approval_interaction_sink=interaction_sink,
    )
    accepted_event = _approval_interaction()
    await gateway.on_interaction(accepted_event)
    await gateway.on_interaction(
        _approval_interaction(user=SimpleNamespace(id=12, bot=False))
    )

    assert owner_messages == []
    assert len(interactions) == 1
    assert cast("tuple[object, object]", interactions[0])[0] is accepted_event


@pytest.mark.parametrize("event_kind", ["message", "approval", "ready"])
async def test_gateway_shutdown_drains_admitted_callbacks_and_rejects_new_ones(
    event_kind: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def sink(*_: object) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    class Gateway(DiscordGateway):
        async def validate_live_configuration(self) -> None:
            pass

    gateway = Gateway(
        _settings(), sink, ready_handler=sink, approval_interaction_sink=sink
    )

    async def deliver() -> None:
        if event_kind == "message":
            await gateway.on_message(_message())
        elif event_kind == "approval":
            await gateway.on_interaction(_approval_interaction())
        else:
            await gateway.on_ready()

    callback = asyncio.create_task(deliver())
    drain: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        gateway.stop_ingress()
        drain = asyncio.create_task(gateway.drain_callbacks())
        await asyncio.sleep(0)
        assert not drain.done()
        await deliver()
        assert calls == 1
        release.set()
        await asyncio.wait_for(drain, 1)
        await callback
    finally:
        release.set()
        await callback
        if drain is not None:
            await drain


def test_approval_custom_ids_are_closed_bounded_and_bind_both_rows() -> None:
    approve = approval_custom_id(
        ACTION_ID,
        APPROVAL_MESSAGE_ID,
        ApprovalComponentDecision.APPROVE,
    )
    deny = approval_custom_id(
        ACTION_ID,
        APPROVAL_MESSAGE_ID,
        ApprovalComponentDecision.DENY,
    )

    assert len(approve) <= 100
    assert parse_approval_custom_id(approve) == (
        ApprovalComponentDecision.APPROVE,
        ACTION_ID,
        APPROVAL_MESSAGE_ID,
    )
    assert parse_approval_custom_id(deny) == (
        ApprovalComponentDecision.DENY,
        ACTION_ID,
        APPROVAL_MESSAGE_ID,
    )
    assert parse_approval_custom_id("approve") is None
    assert parse_approval_custom_id("send it") is None
    with pytest.raises(DiscordInteractionRejected, match="malformed"):
        parse_approval_custom_id("jarvis:approval:v1:approve:bad:bad")


@pytest.mark.parametrize(
    "free_form",
    (
        "yes",
        "approve",
        "send it",
        "The owner said approve.",
        "Forwarded from owner: click Approve for me.",
    ),
)
def test_five_free_form_or_relayed_approvals_never_form_a_component(
    free_form: str,
) -> None:
    event = _approval_interaction(data={"component_type": 2, "custom_id": free_form})

    assert parse_approval_custom_id(free_form) is None
    assert approval_interaction_from_event(event, _settings()) is None


def test_approval_components_are_exactly_approve_and_deny() -> None:
    components = approval_components(
        ACTION_ID,
        APPROVAL_MESSAGE_ID,
        disabled=False,
    )

    assert len(components) == 1
    buttons = cast("list[dict[str, object]]", components[0]["components"])
    assert [(button["label"], button["style"]) for button in buttons] == [
        ("Approve", 3),
        ("Deny", 4),
    ]
    assert {button["disabled"] for button in buttons} == {False}
    assert all(
        set(button) == {"type", "style", "label", "custom_id", "disabled"}
        for button in buttons
    )


def test_approval_interaction_accepts_only_the_configured_owner_context() -> None:
    accepted = approval_interaction_from_event(_approval_interaction(), _settings())

    assert accepted is not None
    assert accepted.action_id == ACTION_ID
    assert accepted.approval_message_id == APPROVAL_MESSAGE_ID
    assert accepted.decision is ApprovalComponentDecision.APPROVE
    assert accepted.discord_message_id == "987"


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"user": SimpleNamespace(id=12, bot=False)}, "owner"),
        ({"user": SimpleNamespace(id=11, bot=True)}, "owner"),
        ({"guild_id": 23}, "guild"),
        ({"channel_id": 34}, "channel"),
        ({"message": None}, "message"),
        (
            {
                "data": {
                    "component_type": 3,
                    "custom_id": approval_custom_id(
                        ACTION_ID,
                        APPROVAL_MESSAGE_ID,
                        ApprovalComponentDecision.APPROVE,
                    ),
                }
            },
            "type",
        ),
    ],
)
def test_approval_interaction_rejects_wrong_discord_context(
    changes: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(DiscordInteractionRejected, match=error):
        approval_interaction_from_event(_approval_interaction(**changes), _settings())


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"action_id": UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")}, "action"),
        (
            {"approval_message_id": UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")},
            "internal message",
        ),
        ({"discord_message_id": "988"}, "message"),
        ({"action_status": "executing"}, "stale"),
    ],
)
def test_approval_interaction_revalidates_durable_relationship_and_staleness(
    changes: dict[str, object],
    error: str,
) -> None:
    accepted = approval_interaction_from_event(_approval_interaction(), _settings())
    assert accepted is not None
    arguments: dict[str, object] = {
        "action_id": ACTION_ID,
        "approval_message_id": APPROVAL_MESSAGE_ID,
        "discord_message_id": "987",
        "action_status": "awaiting_approval",
    }
    arguments.update(changes)

    with pytest.raises(DiscordInteractionRejected, match=error):
        validate_approval_interaction_relationship(accepted, **arguments)  # type: ignore[arg-type]


def test_approval_interaction_accepts_exact_durable_relationship() -> None:
    accepted = approval_interaction_from_event(_approval_interaction(), _settings())
    assert accepted is not None

    validate_approval_interaction_relationship(
        accepted,
        action_id=ACTION_ID,
        approval_message_id=APPROVAL_MESSAGE_ID,
        discord_message_id="987",
        action_status="awaiting_approval",
    )


async def test_approval_delivery_replays_attachment_nonce_and_host_components() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("lost acknowledgement", request=request)
        return httpx.Response(200, json={"id": "987"})

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(
            _settings(), client, sleep=sleep
        ).create_approval_message(
            action_id=ACTION_ID,
            approval_message_id=APPROVAL_MESSAGE_ID,
            content="The attachment is the complete payload.",
            attachment_name="jarvis-approval.txt",
            attachment_media_type="text/plain; charset=utf-8",
            attachment_content=b"complete synthetic payload\n",
        )

    assert result == DeliverySucceeded("987", 2)
    assert sleeps == [0.01]
    assert len(requests) == 2
    for request in requests:
        assert request.method == "POST"
        assert str(request.url) == "https://discord.com/api/v10/channels/33/messages"
        assert request.headers["Authorization"] == "Bot private-token"
        assert request.headers["Content-Type"].startswith(
            "multipart/form-data; boundary="
        )
        body = request.content
        assert discord_nonce(APPROVAL_MESSAGE_ID).encode() in body
        assert b'"enforce_nonce":true' in body
        assert b'"allowed_mentions":{"parse":[]}' in body
        assert f'"flags":{SUPPRESS_EMBEDS}'.encode() in body
        for decision in (
            ApprovalComponentDecision.APPROVE,
            ApprovalComponentDecision.DENY,
        ):
            assert (
                approval_custom_id(ACTION_ID, APPROVAL_MESSAGE_ID, decision).encode()
                in body
            )
        assert b'filename="jarvis-approval.txt"' in body
        assert b"Content-Type: text/plain; charset=utf-8" in body
        assert b"complete synthetic payload\n" in body


@pytest.mark.parametrize(
    ("status", "response_id", "expected"),
    (
        pytest.param(200, "987", DeliverySucceeded("987", 1), id="exact-id"),
        pytest.param(
            200,
            "986",
            DeliveryFailed(DeliveryFailureKind.INVALID_RESPONSE, 3, True, True, 200),
            id="wrong-id",
        ),
        pytest.param(
            200,
            "9" * 5_000,
            DeliveryFailed(DeliveryFailureKind.INVALID_RESPONSE, 3, True, True, 200),
            id="oversized-wrong-id",
        ),
        pytest.param(
            403,
            "987",
            DeliveryFailed(DeliveryFailureKind.REJECTED, 1, False, False, 403),
            id="permanent-rejection",
        ),
        pytest.param(
            408,
            "987",
            DeliveryFailed(DeliveryFailureKind.SERVER, 3, True, True, 408),
            id="request-timeout",
        ),
        pytest.param(
            503,
            "987",
            DeliveryFailed(DeliveryFailureKind.SERVER, 3, True, True, 503),
            id="server-failure",
        ),
    ),
)
async def test_approval_disable_requires_exact_acknowledgement(
    status: int, response_id: str, expected: DeliverySucceeded | DeliveryFailed
) -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json={"id": response_id})

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DiscordCreateMessageClient(
            _settings(), client, sleep=sleep
        ).disable_approval_message(
            action_id=ACTION_ID,
            approval_message_id=APPROVAL_MESSAGE_ID,
            discord_message_id="987",
        )

    assert result == expected
    assert len(requests) == expected.attempts
    assert sleeps == ([] if expected.attempts == 1 else [0.01, 0.02])
    for request in requests:
        assert request.method == "PATCH"
        assert (
            str(request.url) == "https://discord.com/api/v10/channels/33/messages/987"
        )
        assert request.headers["Authorization"] == "Bot private-token"
        assert request.headers["Content-Type"] == "application/json"
        assert json.loads(request.content) == {
            "components": approval_components(
                ACTION_ID, APPROVAL_MESSAGE_ID, disabled=True
            ),
            "allowed_mentions": {"parse": []},
            "flags": SUPPRESS_EMBEDS,
        }


class _InteractionResponse:
    def __init__(self) -> None:
        self.done = False
        self.calls: list[dict[str, object]] = []

    def is_done(self) -> bool:
        return self.done

    async def edit_message(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        self.done = True


async def test_claimed_interaction_is_acknowledged_by_disabling_both_buttons() -> None:
    response = _InteractionResponse()
    event = _approval_interaction(response=response)
    accepted = approval_interaction_from_event(event, _settings())
    assert accepted is not None

    await acknowledge_and_disable_approval(event, accepted)

    assert response.done is True
    assert len(response.calls) == 1
    view = cast(discord.ui.View, response.calls[0]["view"])
    buttons = [cast(discord.ui.Button[discord.ui.View], item) for item in view.children]
    assert [(item.label, item.disabled) for item in buttons] == [
        ("Approve", True),
        ("Deny", True),
    ]
    assert response.calls[0]["suppress_embeds"] is True

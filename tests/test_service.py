from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from llm_agent_kernel import CancellationToken
from pydantic import SecretStr

from jarvis.config import DiscordSettings
from jarvis.discord import (
    CatchUpResult,
    Control,
    DeliveryFailed,
    DeliveryFailureKind,
    DeliveryResult,
    DeliverySucceeded,
    DiscordOwnerMessage,
)
from jarvis.messages import InboundInsert, PendingControl, StoredMessage
from jarvis.service import (
    IngressStore,
    JarvisService,
    ThreadRunner,
    flush_pending_deliveries,
)
from jarvis.settings import Settings
from jarvis.state import PausedState


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://jarvis:secret@db/jarvis"),
        discord=DiscordSettings(
            bot_token=SecretStr("private-token"),
            owner_user_id=11,
            guild_id=22,
            channel_id=33,
        ),
        owner_timezone="America/Los_Angeles",
        codex_profile_key="jarvis",
        codex_model="gpt-5.4",
        codex_state_root=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
    )


def _stored(text: str, *, identifier: UUID | None = None) -> StoredMessage:
    return StoredMessage(
        id=identifier or uuid4(),
        role="assistant",
        text=text,
        source="discord",
        source_conversation_id="33",
        source_message_id=None,
        created_at=datetime(2026, 9, 3, 18, tzinfo=UTC),
        processed_at=datetime(2026, 9, 3, 18, tzinfo=UTC),
        processing_attempts=0,
        processing_parked_at=None,
        remembered_at=None,
        trace={},
    )


class _DeliveryStore:
    def __init__(self, messages: tuple[StoredMessage, ...]) -> None:
        self.messages = messages
        self.marked: list[tuple[UUID, str]] = []

    async def pending_delivery(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        assert source_conversation_id == "33"
        return self.messages[:limit]

    async def mark_delivered(
        self,
        *,
        message_id: UUID,
        source_message_id: str,
    ) -> None:
        self.marked.append((message_id, source_message_id))


class _Delivery:
    def __init__(self, results: list[DeliveryResult]) -> None:
        self.results = results
        self.seen: list[tuple[UUID | str, str]] = []

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult:
        self.seen.append((persisted_message_id, content))
        return self.results.pop(0)


async def test_delivery_flush_marks_successes_and_preserves_order() -> None:
    first = _stored("first")
    second = _stored("second")
    store = _DeliveryStore((first, second))
    delivery = _Delivery([DeliverySucceeded("101", 1), DeliverySucceeded("102", 1)])

    result = await flush_pending_deliveries(
        store=store,
        delivery=delivery,
        source_conversation_id="33",
        limit=20,
    )
    assert result.selected == 2
    assert result.delivered == 2
    assert result.failure is None
    assert delivery.seen == [(first.id, "first"), (second.id, "second")]
    assert store.marked == [(first.id, "101"), (second.id, "102")]


async def test_delivery_flush_stops_at_first_failure() -> None:
    first = _stored("first")
    second = _stored("second")
    store = _DeliveryStore((first, second))
    failure = DeliveryFailed(
        DeliveryFailureKind.TRANSPORT,
        attempts=3,
        retryable=True,
        ambiguous=True,
    )
    delivery = _Delivery([failure, DeliverySucceeded("102", 1)])

    result = await flush_pending_deliveries(
        store=store,
        delivery=delivery,
        source_conversation_id="33",
        limit=20,
    )
    assert result.failure is failure
    assert result.delivered == 0
    assert delivery.seen == [(first.id, "first")]
    assert store.marked == []


class _Ingress(_DeliveryStore):
    def __init__(self) -> None:
        super().__init__(())
        self.inserted: list[DiscordOwnerMessage] = []
        self.controls: list[PendingControl] = []
        self.cursor: str | None = "41"

    async def insert_waking(
        self,
        *,
        role: str,
        text: str,
        source: str,
        source_conversation_id: str,
        source_message_id: str,
        created_at: datetime,
        message_id: UUID | None = None,
    ) -> InboundInsert:
        del role, source, message_id
        incoming = DiscordOwnerMessage(
            source_message_id,
            source_conversation_id,
            text,
            created_at,
            Control(text.strip().casefold())
            if text.strip().casefold() in Control
            else None,
        )
        self.inserted.append(incoming)
        return InboundInsert(
            StoredMessage(
                id=uuid4(),
                role="owner",
                text=text,
                source="discord",
                source_conversation_id=source_conversation_id,
                source_message_id=source_message_id,
                created_at=created_at,
                processed_at=None,
                processing_attempts=0,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            ),
            inserted=True,
        )

    async def latest_discord_owner_source_message_id(
        self,
        *,
        source_conversation_id: str,
    ) -> str | None:
        assert source_conversation_id == "33"
        return self.cursor

    async def pending_controls(
        self,
        *,
        source_conversation_id: str,
        limit: int,
    ) -> tuple[PendingControl, ...]:
        del source_conversation_id
        return tuple(self.controls[:limit])

    async def circuit_is_open(self) -> bool:
        return False


class _Runner:
    def __init__(self) -> None:
        self.active = False
        self.settled: list[tuple[UUID, Control]] = []

    async def run(self, cancellation: CancellationToken) -> object:
        del cancellation
        raise AssertionError("model run was not expected")

    async def has_active_claim(self) -> bool:
        return self.active

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        self.settled.append((message_id, control))
        return True

    async def discard_recovered_session_reference(self) -> None:
        return None


class _Gateway:
    def __init__(self) -> None:
        self.after: str | None = None

    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult:
        self.after = after_source_message_id
        return CatchUpResult(2, 1, False, "42")

    @asynccontextmanager
    async def typing(self):  # type: ignore[no-untyped-def]
        yield


class _InspectableService(JarvisService):
    def set_active_cancellation(self, cancellation: CancellationToken) -> None:
        self._active_cancellation = cancellation


async def test_gateway_ready_catches_up_after_canonical_watermark(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    gateway = _Gateway()
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, _Ingress()),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, _Runner()),
        gateway=gateway,
    )
    result = await service.gateway_ready()
    assert gateway.after == "41"
    assert result == CatchUpResult(2, 1, False, "42")


async def test_active_pause_signals_kernel_cancellation_immediately(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    store = _Ingress()
    runner = _Runner()
    runner.active = True
    service = _InspectableService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, store),
        paused=PausedState(paused_path),
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, runner),
        gateway=_Gateway(),
    )
    cancellation = CancellationToken()
    service.set_active_cancellation(cancellation)
    incoming = DiscordOwnerMessage(
        "42",
        "33",
        "pause",
        datetime(2026, 9, 3, 18, tzinfo=UTC),
        Control.PAUSE,
    )
    await service.receive_owner_message(incoming)
    assert cancellation.cancelled
    assert await PausedState(paused_path).is_paused() is True


async def test_resume_clears_pause_and_remains_queued_for_ordered_drain(
    tmp_path: Path,
) -> None:
    paused_path = tmp_path / "paused.json"
    PausedState.initialize(paused_path)
    paused = PausedState(paused_path)
    await paused.set_paused(True)
    store = _Ingress()
    runner = _Runner()
    service = JarvisService(
        settings=_settings(tmp_path),
        store=cast(IngressStore, store),
        paused=paused,
        delivery=_Delivery([]),
        runner=cast(ThreadRunner, runner),
        gateway=_Gateway(),
    )
    incoming = DiscordOwnerMessage(
        "42",
        "33",
        " \nReSuMe\t",
        datetime(2026, 9, 3, 18, tzinfo=UTC),
        Control.RESUME,
    )
    await service.receive_owner_message(incoming)
    assert await paused.is_paused() is False
    assert store.inserted[0].text == "resume"
    assert runner.settled == []

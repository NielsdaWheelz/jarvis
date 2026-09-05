from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from llm_agent_kernel import (
    AlreadyReleased,
    AppendInputs,
    CancellationToken,
    ClaimAcquired,
    ClaimBusy,
    ClaimNoWork,
    ConversationConclusion,
    NoNewInput,
    OwnerToken,
    Parked,
    Preempt,
    ProviderUsage,
    Released,
    RunId,
    RunMetrics,
    SettleMoreInput,
    ThreadCompleted,
    ThreadId,
    ThreadNoWork,
    ThreadStopKind,
    ThreadStopped,
)
from llm_tools import render_prompt
from pydantic import SecretStr
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.config import DiscordSettings
from jarvis.db import action, create_engine, memory_log, message
from jarvis.definitions import build_slice1_definitions
from jarvis.discord import (
    CatchUpResult,
    Control,
    DeliverySucceeded,
    DiscordCreateMessageClient,
    DiscordOwnerMessage,
    discord_nonce,
)
from jarvis.history import PostgresCanonicalHistory
from jarvis.messages import (
    CircuitOpen,
    ClaimedMessages,
    ExhaustedMessage,
    MessageStore,
    PersistenceDefect,
    Settlement,
    SettlementTrace,
)
from jarvis.service import JarvisService, PreflightDeferred, flush_pending_deliveries
from jarvis.settings import Settings
from jarvis.state import PausedState

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
MIGRATION_DATABASE_URL = os.environ.get("JARVIS_TEST_MIGRATION_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="JARVIS_TEST_DATABASE_URL is not configured",
    ),
]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


@pytest_asyncio.fixture
async def migrator_engine() -> AsyncIterator[AsyncEngine]:
    if MIGRATION_DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_MIGRATION_DATABASE_URL is not configured")
    value = create_engine(MIGRATION_DATABASE_URL)
    yield value
    await value.dispose()


class _LostSettlementAcknowledgementStore(MessageStore):
    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self._lose_next_acknowledgement = True

    async def settle(
        self,
        *,
        consumed_message_ids: tuple[UUID, ...],
        source_conversation_id: str,
        trace: SettlementTrace,
        conclusion_text: str | None,
        conclusion_message_id: UUID | None = None,
        settled_at: datetime | None = None,
    ) -> Settlement:
        result = await super().settle(
            consumed_message_ids=consumed_message_ids,
            source_conversation_id=source_conversation_id,
            trace=trace,
            conclusion_text=conclusion_text,
            conclusion_message_id=conclusion_message_id,
            settled_at=settled_at,
        )
        if self._lose_next_acknowledgement:
            self._lose_next_acknowledgement = False
            raise ConnectionError("simulated lost settlement acknowledgement")
        return result


async def _owner(
    store: MessageStore,
    source_message_id: str,
    *,
    source_conversation_id: str,
    text_value: str = "synthetic owner input",
    created_at: datetime | None = None,
) -> UUID:
    result = await store.insert_waking(
        role="owner",
        text=text_value,
        source="discord",
        source_conversation_id=source_conversation_id,
        source_message_id=source_message_id,
        created_at=created_at or datetime.now(UTC),
    )
    return result.message.id


async def test_migration_has_exact_application_schema(
    engine: AsyncEngine,
    migrator_engine: AsyncEngine,
) -> None:
    expected_columns = {
        "message": {
            "id",
            "role",
            "text",
            "source",
            "source_conversation_id",
            "source_message_id",
            "created_at",
            "processed_at",
            "processing_attempts",
            "processing_parked_at",
            "remembered_at",
            "trace",
        },
        "memory_log": {"id", "text", "created_at", "embedding"},
        "memory_summary": {
            "id",
            "text",
            "source_memory_ids",
            "created_at",
            "embedding",
        },
        "action": {
            "id",
            "tool_name",
            "arguments",
            "execution_contract",
            "status",
            "attempts",
            "execute_after",
            "origin_message_id",
            "approval_message_id",
            "created_at",
            "decided_at",
            "completed_at",
            "result",
        },
    }
    async with engine.connect() as connection:
        table_rows = (
            await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            )
        ).scalars()
        tables = set(table_rows)
        assert tables == set(expected_columns)
        for table_name, expected in expected_columns.items():
            rows = (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = :table_name"
                    ),
                    {"table_name": table_name},
                )
            ).scalars()
            assert set(rows) == expected
        vector_dimensions = (
            await connection.execute(
                text(
                    "SELECT table_name, atttypmod FROM information_schema.columns "
                    "JOIN pg_attribute ON attname = column_name "
                    "JOIN pg_class ON pg_class.oid = attrelid AND relname = table_name "
                    "WHERE table_schema = 'public' AND column_name = 'embedding'"
                )
            )
        ).all()
        assert set(vector_dimensions) == {
            ("memory_log", 1536),
            ("memory_summary", 1536),
        }
    async with migrator_engine.connect() as connection:
        owner_tables = set(
            (
                await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' "
                        "AND table_type = 'BASE TABLE'"
                    )
                )
            ).scalars()
        )
    assert owner_tables == set(expected_columns) | {"alembic_version"}


def test_alembic_metadata_has_no_drift() -> None:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    command.check(Config("alembic.ini"))


async def test_runtime_role_has_only_required_table_privileges(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT current_user, "
                    "has_table_privilege(current_user, 'message', 'SELECT'), "
                    "has_table_privilege(current_user, 'message', 'INSERT'), "
                    "has_column_privilege(current_user, 'message', 'trace', 'UPDATE'), "
                    "has_table_privilege(current_user, 'memory_log', 'DELETE'), "
                    "has_table_privilege(current_user, 'memory_log', 'TRUNCATE'), "
                    "has_column_privilege(current_user, 'memory_log', 'text', "
                    "'UPDATE'), has_column_privilege(current_user, 'memory_log', "
                    "'embedding', 'UPDATE')"
                )
            )
        ).one()
    assert tuple(row) == (
        "jarvis_runtime",
        True,
        True,
        True,
        False,
        False,
        False,
        True,
    )


async def test_inbound_source_identity_is_idempotent(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    created_at = datetime(2026, 9, 3, 12, tzinfo=UTC)
    first = await store.insert_waking(
        role="owner",
        text="synthetic idempotent input",
        source="discord",
        source_conversation_id="configured-channel",
        source_message_id="dedupe-1",
        created_at=created_at,
    )
    second = await store.insert_waking(
        role="owner",
        text="synthetic idempotent input",
        source="discord",
        source_conversation_id="configured-channel",
        source_message_id="dedupe-1",
        created_at=created_at,
    )
    assert first.inserted is True
    assert second.inserted is False
    assert second.message == first.message
    with pytest.raises(PersistenceDefect, match="different message content"):
        await store.insert_waking(
            role="owner",
            text="different synthetic input",
            source="discord",
            source_conversation_id="configured-channel",
            source_message_id="dedupe-1",
            created_at=created_at,
        )


async def test_claim_is_ordered_and_counts_crash_attempts(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    conversation_id = "claim-channel"
    start = datetime(2026, 9, 3, 13, tzinfo=UTC)
    first_id = await _owner(
        store,
        "claim-1",
        source_conversation_id=conversation_id,
        created_at=start,
    )
    second_id = await _owner(
        store,
        "claim-2",
        source_conversation_id=conversation_id,
        created_at=start + timedelta(seconds=1),
    )

    first_claim = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=2,
        as_of=start + timedelta(seconds=2),
    )
    assert isinstance(first_claim, ClaimedMessages)
    assert tuple(item.id for item in first_claim.messages) == (first_id, second_id)
    assert first_claim.attempt_number == 1
    assert tuple(item.processing_attempts for item in first_claim.messages) == (1, 0)

    crash_reclaim = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=2,
    )
    assert isinstance(crash_reclaim, ClaimedMessages)
    assert crash_reclaim.attempt_number == 2

    exhausted = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=2,
    )
    assert isinstance(exhausted, ExhaustedMessage)
    assert exhausted.message.id == first_id
    assert exhausted.message.processing_attempts == 2


async def test_park_opens_circuit_and_operator_release_preserves_attempts(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "park-channel"
    first_id = await _owner(
        store,
        "park-1",
        source_conversation_id=conversation_id,
    )
    second_id = await _owner(
        store,
        "park-2",
        source_conversation_id=conversation_id,
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    claim = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=3,
    )
    assert isinstance(claim, ClaimedMessages)
    ids = tuple(item.id for item in claim.messages)
    assert ids == (first_id, second_id)

    assert await store.park(
        claimed_message_ids=ids,
        reason_code="plan_budget_mismatch",
    )
    assert not await store.park(
        claimed_message_ids=ids,
        reason_code="plan_budget_mismatch",
    )
    assert await store.circuit_is_open()
    assert isinstance(
        await store.claim(
            source_conversation_id=conversation_id,
            maximum_batch_size=10,
            maximum_attempts=3,
        ),
        CircuitOpen,
    )

    await store.clear_parked(message_ids=ids)
    assert not await store.circuit_is_open()
    reclaimed = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=3,
    )
    assert isinstance(reclaimed, ClaimedMessages)
    assert reclaimed.attempt_number == 2
    with pytest.raises(PersistenceDefect, match="unparked"):
        await store.clear_parked(message_ids=ids)


async def test_settlement_and_delivery_are_one_way_watermarks(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "settle-channel"
    first_id = await _owner(
        store,
        "settle-1",
        source_conversation_id=conversation_id,
    )
    second_id = await _owner(
        store,
        "settle-2",
        source_conversation_id=conversation_id,
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    claim = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=3,
    )
    assert isinstance(claim, ClaimedMessages)
    conclusion_id = uuid4()
    run_trace = SettlementTrace(
        run_id="run-settlement",
        through_checkpoint=str(second_id),
        conclusion_kind="conversation",
        outcome="say",
        provider_trace_ids=("provider-trace",),
        provider_turns=1,
        input_tokens=12,
        output_tokens=7,
        duration_ms=25,
    )
    settlement = await store.settle(
        consumed_message_ids=(first_id, second_id),
        source_conversation_id=conversation_id,
        trace=run_trace,
        conclusion_text="synthetic assistant response",
        conclusion_message_id=conclusion_id,
    )
    assert settlement.already_settled is False
    assert settlement.more_input is False
    assert settlement.conclusion_message is not None
    assert settlement.conclusion_message.id == conclusion_id

    repeated = await store.settle(
        consumed_message_ids=(first_id, second_id),
        source_conversation_id=conversation_id,
        trace=run_trace,
        conclusion_text="synthetic assistant response",
        conclusion_message_id=conclusion_id,
    )
    assert repeated.already_settled is True
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(item.id for item in pending) == (conclusion_id,)

    await store.mark_delivered(
        message_id=conclusion_id,
        source_message_id="discord-response-1",
    )
    await store.mark_delivered(
        message_id=conclusion_id,
        source_message_id="discord-response-1",
    )
    assert not await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    with pytest.raises(PersistenceDefect, match="conflicts"):
        await store.mark_delivered(
            message_id=conclusion_id,
            source_message_id="discord-response-2",
        )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.processed_at, message.c.trace).where(
                    message.c.id.in_((first_id, second_id))
                )
            )
        ).all()
    assert rows[0].processed_at == rows[1].processed_at
    assert rows[0].trace["settlement"] == rows[1].trace["settlement"]
    assert rows[0].trace["settlement"]["conclusion_message_id"] == str(conclusion_id)


async def test_delayed_restart_delivery_reuses_persisted_identity(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "delayed-restart-delivery-channel"
    await _owner(
        store,
        "delayed-restart-delivery-owner",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "delayed-restart-delivery-run")
    claimed = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("delayed-restart-delivery-token"),
    )
    assert isinstance(claimed, ClaimAcquired)
    await checkpoint.settle(
        claimed.claim,
        claimed.claim.through_checkpoint,
        ConversationConclusion("synthetic delayed-restart answer"),
    )
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert len(pending) == 1
    persisted_id = pending[0].id

    settings = DiscordSettings(
        bot_token=SecretStr("synthetic-token"),
        owner_user_id=11,
        guild_id=22,
        channel_id=33,
        delivery_retry_delays_seconds=(0.001, 0.002),
    )
    provider_messages: dict[str, tuple[str, str]] = {}
    request_nonces: list[str] = []

    async def accepted_without_acknowledgement(
        request: httpx.Request,
    ) -> httpx.Response:
        body = cast(dict[str, object], json.loads(request.content))
        nonce = cast(str, body["nonce"])
        content = cast(str, body["content"])
        request_nonces.append(nonce)
        provider_messages.setdefault(
            nonce,
            ("987654321", content),
        )
        raise httpx.ReadTimeout("synthetic lost acknowledgement", request=request)

    async def no_sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(accepted_without_acknowledgement)
    ) as first_http_client:
        first = await flush_pending_deliveries(
            store=store,
            delivery=DiscordCreateMessageClient(
                settings,
                first_http_client,
                sleep=no_sleep,
            ),
            source_conversation_id=conversation_id,
            limit=10,
        )
    assert first.delivered == 0
    assert first.failure is not None and first.failure.ambiguous
    still_pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.id for value in still_pending) == (persisted_id,)

    async def deduplicate_after_restart(request: httpx.Request) -> httpx.Response:
        body = cast(dict[str, object], json.loads(request.content))
        nonce = cast(str, body["nonce"])
        content = cast(str, body["content"])
        request_nonces.append(nonce)
        provider_id, provider_content = provider_messages[nonce]
        assert content == provider_content
        return httpx.Response(200, json={"id": provider_id})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(deduplicate_after_restart)
    ) as restarted_http_client:
        restarted = await flush_pending_deliveries(
            store=MessageStore(engine),
            delivery=DiscordCreateMessageClient(
                settings,
                restarted_http_client,
                sleep=no_sleep,
            ),
            source_conversation_id=conversation_id,
            limit=10,
        )
    assert restarted.delivered == 1
    assert restarted.failure is None
    assert len(provider_messages) == 1
    assert request_nonces == [discord_nonce(persisted_id)] * 4

    after_restart = MessageStore(engine)
    assert not await after_restart.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(deduplicate_after_restart)
    ) as final_http_client:
        repeated_flush = await flush_pending_deliveries(
            store=after_restart,
            delivery=DiscordCreateMessageClient(
                settings,
                final_http_client,
                sleep=no_sleep,
            ),
            source_conversation_id=conversation_id,
            limit=10,
        )
    assert repeated_flush.selected == 0
    async with engine.connect() as connection:
        source_message_id = await connection.scalar(
            select(message.c.source_message_id).where(message.c.id == persisted_id)
        )
    assert source_message_id == "987654321"


async def test_poll_stop_can_settle_claim_and_control_atomically(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "control-channel"
    initial_id = await _owner(
        store,
        "control-initial",
        source_conversation_id=conversation_id,
    )
    claim = await store.claim(
        source_conversation_id=conversation_id,
        maximum_batch_size=10,
        maximum_attempts=3,
    )
    assert isinstance(claim, ClaimedMessages)
    followup_id = await _owner(
        store,
        "control-followup",
        source_conversation_id=conversation_id,
    )
    stop_id = await _owner(
        store,
        "control-stop",
        source_conversation_id=conversation_id,
        text_value=" STOP ",
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    polled = await store.poll(
        route="interactive",
        source_conversation_id=conversation_id,
        known_message_ids=(initial_id,),
        maximum_batch_size=10,
    )
    assert polled is not None
    assert polled.preempt_reason == "stop"
    assert tuple(item.id for item in polled.messages) == (followup_id, stop_id)

    stopped = await store.settle(
        consumed_message_ids=(initial_id, followup_id, stop_id),
        source_conversation_id=conversation_id,
        trace=SettlementTrace(
            run_id="run-stopped",
            through_checkpoint=str(stop_id),
            conclusion_kind="stopped",
            outcome="owner_stop",
        ),
        conclusion_text="Stopped.",
    )
    assert stopped.more_input is False
    async with engine.connect() as connection:
        traces = (
            await connection.execute(
                select(message.c.trace)
                .where(message.c.id.in_((initial_id, followup_id, stop_id)))
                .order_by(message.c.created_at, message.c.id)
            )
        ).scalars()
    values = list(traces)
    assert len(values) == 3
    assert values[0]["settlement"] == values[1]["settlement"] == values[2]["settlement"]


async def test_database_enforces_raw_memory_append_only(
    engine: AsyncEngine,
    migrator_engine: AsyncEngine,
) -> None:
    memory_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(memory_log).values(
                id=memory_id,
                text="synthetic durable memory",
            )
        )
        await connection.execute(
            update(memory_log)
            .where(memory_log.c.id == memory_id)
            .values(embedding=[0.0] * 1536)
        )

    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(
                update(memory_log)
                .where(memory_log.c.id == memory_id)
                .values(text="changed")
            )
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM memory_log WHERE id = :id"),
                {"id": memory_id},
            )
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE memory_log"))
    with pytest.raises(DBAPIError, match="canonical fields are immutable"):
        async with migrator_engine.begin() as connection:
            await connection.execute(
                update(memory_log)
                .where(memory_log.c.id == memory_id)
                .values(text="owner-side change")
            )
    with pytest.raises(DBAPIError, match="append-only"):
        async with migrator_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM memory_log WHERE id = :id"),
                {"id": memory_id},
            )


async def test_action_constraints_and_identity_immutability(
    engine: AsyncEngine,
    migrator_engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    origin_id = await _owner(
        store,
        "action-origin",
        source_conversation_id="action-channel",
    )
    action_id = uuid4()
    contract = {
        "tool_contract_revision": "test-v1",
        "implementation_revision": "test-v1",
        "policy_revision": "test-v1",
        "plan_revision": "test-v1",
        "effect": "Write",
        "replay_policy": "BilledOnce",
        "input_digest": "synthetic",
        "max_attempts": 1,
        "claim_id": "synthetic-claim",
        "through_checkpoint": str(origin_id),
        "model_step_ordinal": 1,
        "input_message_ids": [str(origin_id)],
        "write_gate_supporting_owner_message_ids": [str(origin_id)],
    }
    async with engine.begin() as connection:
        await connection.execute(
            insert(action).values(
                id=action_id,
                tool_name="test.synthetic_write",
                arguments={"value": "synthetic"},
                execution_contract=contract,
                status="queued",
                attempts=0,
                origin_message_id=origin_id,
            )
        )
        await connection.execute(
            update(action).where(action.c.id == action_id).values(attempts=1)
        )
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(
                update(action)
                .where(action.c.id == action_id)
                .values(arguments={"value": "different"})
            )
    with pytest.raises(DBAPIError, match="identity fields are immutable"):
        async with migrator_engine.begin() as connection:
            await connection.execute(
                update(action)
                .where(action.c.id == action_id)
                .values(arguments={"value": "owner-side change"})
            )
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                update(action).where(action.c.id == action_id).values(attempts=-1)
            )


async def test_admission_deferral_notice_is_content_free_and_idempotent(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "admission-deferral-channel"
    now = datetime(2026, 9, 3, 15, tzinfo=UTC)
    waking_id = await _owner(
        store,
        "discord-cursor-1",
        source_conversation_id=conversation_id,
        created_at=now,
    )
    assert await store.has_pending_work(source_conversation_id=conversation_id)
    oldest = await store.oldest_foreground(source_conversation_id=conversation_id)
    assert oldest is not None and oldest.id == waking_id
    assert (
        await store.latest_discord_owner_source_message_id(
            source_conversation_id=conversation_id
        )
        == "discord-cursor-1"
    )
    reset_at = now + timedelta(minutes=2)
    first = await store.record_admission_deferral(
        source_conversation_id=conversation_id,
        reset_at=reset_at,
        now=now,
    )
    repeated = await store.record_admission_deferral(
        source_conversation_id=conversation_id,
        reset_at=reset_at,
        now=now,
    )
    assert first is not None and repeated is not None
    assert repeated.id == first.id
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.id for value in pending) == (first.id,)
    assert "synthetic owner input" not in first.text
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(message.c.processing_attempts, message.c.trace).where(
                    message.c.id == waking_id
                )
            )
        ).one()
    assert row.processing_attempts == 0
    assert set(row.trace["admission_delay_notice"]) == {"message_id", "reset_at"}


async def test_post_run_metrics_fill_is_idempotent(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    conversation_id = "metrics-channel"
    input_id = await _owner(
        store,
        "metrics-input",
        source_conversation_id=conversation_id,
    )
    await store.settle(
        consumed_message_ids=(input_id,),
        source_conversation_id=conversation_id,
        trace=SettlementTrace(
            run_id="metrics-run",
            through_checkpoint=str(input_id),
            conclusion_kind="conversation",
            outcome="say",
        ),
        conclusion_text="synthetic metrics conclusion",
    )
    await store.record_run_metrics(
        consumed_message_ids=(input_id,),
        run_id="metrics-run",
        provider_turns=2,
        input_tokens=25,
        output_tokens=10,
        duration_seconds=0.125,
    )
    await store.record_run_metrics(
        consumed_message_ids=(input_id,),
        run_id="metrics-run",
        provider_turns=2,
        input_tokens=25,
        output_tokens=10,
        duration_seconds=0.125,
    )
    async with engine.connect() as connection:
        trace = await connection.scalar(
            select(message.c.trace).where(message.c.id == input_id)
        )
    assert isinstance(trace, dict)
    typed_trace = cast(dict[str, object], trace)
    settlement = cast(dict[str, object], typed_trace["settlement"])
    assert settlement == {
        "run_id": "metrics-run",
        "through_checkpoint": str(input_id),
        "conclusion_message_id": settlement["conclusion_message_id"],
        "conclusion_kind": "conversation",
        "outcome": "say",
        "provider_turns": 2,
        "input_tokens": 25,
        "output_tokens": 10,
        "duration_ms": 125,
    }
    with pytest.raises(PersistenceDefect, match="conflict"):
        await store.record_run_metrics(
            consumed_message_ids=(input_id,),
            run_id="metrics-run",
            provider_turns=3,
            input_tokens=25,
            output_tokens=10,
            duration_seconds=0.125,
        )


def _checkpoint(
    engine: AsyncEngine,
    conversation_id: str,
    run_id: str,
    *,
    maximum_attempts: int = 3,
    maximum_batch_size: int = 10,
    store: MessageStore | None = None,
) -> PostgresInputCheckpoint:
    definitions = build_slice1_definitions(
        profile_key="synthetic-profile",
        model="gpt-5.6-terra",
        owner_timezone="America/Los_Angeles",
    )
    return PostgresInputCheckpoint(
        store=store or MessageStore(engine),
        thread_id=ThreadId(conversation_id),
        run_id=RunId(run_id),
        interactive_plan=definitions.plans["main"],
        scheduled_wake_plan=definitions.plans["scheduled_wake"],
        maximum_batch_size=maximum_batch_size,
        maximum_attempts=maximum_attempts,
    )


class _CheckpointServiceRunner:
    def __init__(self, engine: AsyncEngine, conversation_id: str) -> None:
        self._engine = engine
        self._conversation_id = conversation_id
        self._invocations = 0
        self.calls = 0
        self.claimed_input_ids: list[tuple[str, ...]] = []

    async def run(
        self,
        cancellation: CancellationToken,
    ) -> ThreadCompleted | ThreadNoWork:
        del cancellation
        self._invocations += 1
        run_id = f"poison-service-run-{self._invocations}"
        checkpoint = _checkpoint(
            self._engine,
            self._conversation_id,
            run_id,
        )
        result = await checkpoint.claim(
            ThreadId(self._conversation_id),
            OwnerToken(f"poison-service-owner-{self._invocations}"),
        )
        if isinstance(result, ClaimNoWork):
            return ThreadNoWork(
                RunMetrics(
                    RunId(run_id),
                    0,
                    ProviderUsage(),
                    0.0,
                    bool(checkpoint.consumed_message_ids),
                )
            )
        assert isinstance(result, ClaimAcquired)
        self.calls += 1
        self.claimed_input_ids.append(
            tuple(str(value.input_id) for value in result.claim.inputs)
        )
        await checkpoint.settle(
            result.claim,
            result.claim.through_checkpoint,
            ConversationConclusion("synthetic successor answer"),
        )
        return ThreadCompleted(
            RunMetrics(
                RunId(run_id),
                1,
                ProviderUsage(input_tokens=1, output_tokens=1),
                0.001,
                True,
            )
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        del message_id, control
        raise AssertionError("control settlement was not expected")

    async def discard_recovered_session_reference(self) -> None:
        return None


class _NoopGateway:
    async def catch_up(self, after_source_message_id: str | None) -> CatchUpResult:
        del after_source_message_id
        raise AssertionError("catch-up was not expected")

    @asynccontextmanager
    async def typing(self) -> AsyncIterator[None]:
        yield


class _SuccessfulDelivery:
    def __init__(self, starting_id: int = 9_000) -> None:
        self._starting_id = starting_id
        self.delivered: list[tuple[UUID | str, str]] = []
        self.delivered_event = asyncio.Event()
        self.second_delivered_event = asyncio.Event()

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliverySucceeded:
        self.delivered.append((persisted_message_id, content))
        self.delivered_event.set()
        if len(self.delivered) >= 2:
            self.second_delivered_event.set()
        return DeliverySucceeded(str(self._starting_id + len(self.delivered)), 1)


class _OneDrainService(JarvisService):
    async def drain_once(self) -> None:
        await self._drain()


class _NeverRunRunner:
    def __init__(self) -> None:
        self.calls = 0
        self.discard_calls = 0

    async def run(
        self,
        cancellation: CancellationToken,
    ) -> ThreadCompleted | ThreadNoWork:
        del cancellation
        self.calls += 1
        raise AssertionError("provider/admission work was not expected")

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        del message_id, control
        raise AssertionError("single-row control settlement was not expected")

    async def discard_recovered_session_reference(self) -> None:
        self.discard_calls += 1


class _ControlOnlyRunner:
    def __init__(self, store: MessageStore) -> None:
        self._store = store
        self.run_calls = 0
        self.settled_controls: list[Control] = []

    async def run(
        self,
        cancellation: CancellationToken,
    ) -> ThreadNoWork:
        del cancellation
        self.run_calls += 1
        return ThreadNoWork(
            RunMetrics(
                RunId(f"control-only-run-{self.run_calls}"),
                0,
                ProviderUsage(),
                0.0,
                False,
            )
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        await self._store.settle_control(
            message_id=message_id,
            source_conversation_id="33",
            control=control.value,
        )
        self.settled_controls.append(control)
        return True

    async def discard_recovered_session_reference(self) -> None:
        return None


class _ActiveControlRunner:
    def __init__(self, engine: AsyncEngine, store: MessageStore) -> None:
        self._engine = engine
        self._store = store
        self._checkpoint: PostgresInputCheckpoint | None = None
        self.calls = 0
        self.active = asyncio.Event()
        self.continue_after_controls = asyncio.Event()

    async def run(
        self,
        cancellation: CancellationToken,
    ) -> ThreadNoWork | ThreadStopped:
        self.calls += 1
        run_id = RunId(f"active-control-run-{self.calls}")
        checkpoint = _checkpoint(
            self._engine,
            "33",
            str(run_id),
            store=self._store,
        )
        result = await checkpoint.claim(ThreadId("33"), OwnerToken("11"))
        if isinstance(result, ClaimNoWork):
            return ThreadNoWork(RunMetrics(run_id, 0, ProviderUsage(), 0.0, False))
        assert isinstance(result, ClaimAcquired)
        self._checkpoint = checkpoint
        self.active.set()
        await self.continue_after_controls.wait()
        assert cancellation.cancelled
        polled = await checkpoint.poll(result.claim, result.claim.through_checkpoint)
        assert isinstance(polled, Preempt)
        assert polled.reason == "pause"
        released = await checkpoint.release(
            result.claim,
            "preempted by host policy",
        )
        assert isinstance(released, Released)
        self._checkpoint = None
        return ThreadStopped(
            RunMetrics(run_id, 0, ProviderUsage(), 0.001, True),
            ThreadStopKind.preempted,
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        await self._store.settle_control(
            message_id=message_id,
            source_conversation_id="33",
            control=control.value,
        )
        return True

    async def discard_recovered_session_reference(self) -> None:
        raise AssertionError("recovered-session discard was not expected")


class _IdleBoundaryRunner:
    def __init__(self, engine: AsyncEngine, conversation_id: str) -> None:
        self._engine = engine
        self._conversation_id = conversation_id
        self.calls = 0
        self.first_no_work_observed = asyncio.Event()
        self.allow_first_return = asyncio.Event()
        self.input_processed = asyncio.Event()

    async def run(
        self,
        cancellation: CancellationToken,
    ) -> ThreadCompleted | ThreadNoWork:
        del cancellation
        self.calls += 1
        run_id = f"idle-boundary-run-{self.calls}"
        checkpoint = _checkpoint(self._engine, self._conversation_id, run_id)
        result = await checkpoint.claim(
            ThreadId(self._conversation_id),
            OwnerToken(f"idle-boundary-owner-{self.calls}"),
        )
        if isinstance(result, ClaimNoWork):
            if self.calls == 1:
                self.first_no_work_observed.set()
                await self.allow_first_return.wait()
            return ThreadNoWork(
                RunMetrics(
                    RunId(run_id),
                    0,
                    ProviderUsage(),
                    0.0,
                    False,
                )
            )
        assert isinstance(result, ClaimAcquired)
        await checkpoint.settle(
            result.claim,
            result.claim.through_checkpoint,
            ConversationConclusion("synthetic idle-race answer"),
        )
        self.input_processed.set()
        return ThreadCompleted(
            RunMetrics(
                RunId(run_id),
                1,
                ProviderUsage(input_tokens=1, output_tokens=1),
                0.001,
                True,
            )
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        del message_id, control
        raise AssertionError("control settlement was not expected")

    async def discard_recovered_session_reference(self) -> None:
        return None


class _DeferredThenCheckpointRunner:
    def __init__(self, engine: AsyncEngine, store: MessageStore) -> None:
        self._engine = engine
        self._store = store
        self.calls = 0
        self.deferred = asyncio.Event()
        self.input_processed = asyncio.Event()

    async def run(
        self,
        cancellation: CancellationToken,
    ) -> ThreadCompleted | ThreadNoWork | PreflightDeferred:
        del cancellation
        self.calls += 1
        if self.calls == 1:
            reset_at = datetime.now(UTC) + timedelta(minutes=2)
            await self._store.record_admission_deferral(
                source_conversation_id="33",
                reset_at=reset_at,
            )
            self.deferred.set()
            return PreflightDeferred(reset_at)

        run_id = f"reset-retry-run-{self.calls}"
        checkpoint = _checkpoint(self._engine, "33", run_id)
        result = await checkpoint.claim(
            ThreadId("33"),
            OwnerToken(f"reset-retry-owner-{self.calls}"),
        )
        if isinstance(result, ClaimNoWork):
            return ThreadNoWork(
                RunMetrics(RunId(run_id), 0, ProviderUsage(), 0.0, False)
            )
        assert isinstance(result, ClaimAcquired)
        await checkpoint.settle(
            result.claim,
            result.claim.through_checkpoint,
            ConversationConclusion("synthetic answer after capacity reset"),
        )
        self.input_processed.set()
        return ThreadCompleted(
            RunMetrics(
                RunId(run_id),
                1,
                ProviderUsage(input_tokens=1, output_tokens=1),
                0.001,
                True,
            )
        )

    async def settle_control(self, message_id: UUID, control: Control) -> bool:
        del message_id, control
        raise AssertionError("control settlement was not expected")

    async def discard_recovered_session_reference(self) -> None:
        return None


class _ResetSleep:
    def __init__(self) -> None:
        self.delay: float | None = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, delay: float) -> None:
        self.delay = delay
        self.entered.set()
        await self.release.wait()


async def test_service_processes_successor_after_durable_poison_conclusion(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    conversation_id = "33"
    started_at = datetime(2026, 9, 3, 19, tzinfo=UTC)
    exhausted_id = await _owner(
        store,
        "poison-service-exhausted",
        source_conversation_id=conversation_id,
        created_at=started_at,
    )
    successor_id = await _owner(
        store,
        "poison-service-successor",
        source_conversation_id=conversation_id,
        created_at=started_at + timedelta(seconds=1),
    )
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(message.c.id == exhausted_id)
            .values(processing_attempts=3)
        )

    paused_path = tmp_path / "poison-service-paused.json"
    PausedState.initialize(paused_path)
    runner = _CheckpointServiceRunner(engine, conversation_id)
    delivery = _SuccessfulDelivery(starting_id=9_100)
    service = _OneDrainService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=PausedState(paused_path),
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    await service.drain_once()

    assert runner.calls == 1
    assert runner.claimed_input_ids == [(str(successor_id),)]
    assert tuple(text for _, text in delivery.delivered) == (
        "I stopped this message because it reached the configured retry limit.",
        "synthetic successor answer",
    )
    async with engine.connect() as connection:
        owner_rows = (
            await connection.execute(
                select(message.c.id, message.c.processed_at, message.c.trace).where(
                    message.c.id.in_((exhausted_id, successor_id))
                )
            )
        ).all()
    by_id = {cast(UUID, row.id): row for row in owner_rows}
    assert by_id[exhausted_id].processed_at is not None
    assert by_id[successor_id].processed_at is not None
    assert by_id[exhausted_id].trace["settlement"]["outcome"] == "attempts_exhausted"
    assert not await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )


async def test_service_event_preserves_input_arriving_at_idle_boundary(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    conversation_id = "33"
    paused_path = tmp_path / "idle-boundary-paused.json"
    PausedState.initialize(paused_path)
    runner = _IdleBoundaryRunner(engine, conversation_id)
    delivery = _SuccessfulDelivery()
    service = JarvisService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=PausedState(paused_path),
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    worker = asyncio.create_task(service.run_worker())
    service.request_work()
    await asyncio.wait_for(runner.first_no_work_observed.wait(), timeout=1)
    await service.receive_owner_message(
        DiscordOwnerMessage(
            source_message_id="idle-boundary-owner-input",
            source_conversation_id=conversation_id,
            text="synthetic input at idle boundary",
            created_at=datetime.now(UTC),
            control=None,
        )
    )
    runner.allow_first_return.set()
    await asyncio.wait_for(runner.input_processed.wait(), timeout=1)
    await asyncio.wait_for(delivery.delivered_event.wait(), timeout=1)
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)

    assert runner.calls >= 2
    assert tuple(text for _, text in delivery.delivered) == (
        "synthetic idle-race answer",
    )
    assert not await store.has_pending_work(source_conversation_id=conversation_id)


async def test_capacity_reset_timer_retries_untouched_input_without_external_wake(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    input_id = await _owner(
        store,
        "reset-retry-owner-input",
        source_conversation_id="33",
    )
    paused_path = tmp_path / "reset-retry-paused.json"
    PausedState.initialize(paused_path)
    runner = _DeferredThenCheckpointRunner(engine, store)
    delivery = _SuccessfulDelivery(starting_id=9_150)
    sleep = _ResetSleep()
    service = JarvisService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=PausedState(paused_path),
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
        sleep=sleep,
    )
    worker = asyncio.create_task(service.run_worker())
    service.request_work()
    await asyncio.wait_for(runner.deferred.wait(), timeout=1)
    await asyncio.wait_for(delivery.delivered_event.wait(), timeout=1)
    await asyncio.wait_for(sleep.entered.wait(), timeout=1)

    async with engine.connect() as connection:
        before_reset = (
            await connection.execute(
                select(
                    message.c.processed_at,
                    message.c.processing_attempts,
                    message.c.processing_parked_at,
                ).where(message.c.id == input_id)
            )
        ).one()
    assert before_reset.processed_at is None
    assert before_reset.processing_attempts == 0
    assert before_reset.processing_parked_at is None
    assert sleep.delay is not None and sleep.delay >= 60

    sleep.release.set()
    await asyncio.wait_for(runner.input_processed.wait(), timeout=1)
    await asyncio.wait_for(delivery.second_delivered_event.wait(), timeout=1)
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)

    assert runner.calls >= 2
    assert (
        sum(
            "capacity is temporarily unavailable" in text
            for _, text in delivery.delivered
        )
        == 1
    )
    assert tuple(text for _, text in delivery.delivered)[-1] == (
        "synthetic answer after capacity reset"
    )
    async with engine.connect() as connection:
        after_reset = (
            await connection.execute(
                select(message.c.processed_at, message.c.processing_attempts).where(
                    message.c.id == input_id
                )
            )
        ).one()
    assert after_reset.processed_at is not None
    assert after_reset.processing_attempts == 1


async def test_restart_drains_more_than_two_outbox_batches(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    created_at = datetime(2026, 9, 3, 20, tzinfo=UTC)
    async with engine.begin() as connection:
        for index in range(5):
            await connection.execute(
                insert(message).values(
                    id=uuid4(),
                    role="assistant",
                    text=f"synthetic queued response {index}",
                    source="discord",
                    source_conversation_id="33",
                    source_message_id=None,
                    created_at=created_at + timedelta(seconds=index),
                    processed_at=created_at + timedelta(seconds=index),
                    processing_attempts=0,
                    processing_parked_at=None,
                    remembered_at=None,
                    trace={},
                )
            )
    paused_path = tmp_path / "outbox-restart-paused.json"
    PausedState.initialize(paused_path)
    paused = PausedState(paused_path)
    await paused.set_paused(True)
    runner = _NeverRunRunner()
    delivery = _SuccessfulDelivery(starting_id=9_175)
    service = _OneDrainService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
            delivery_batch_size=2,
        ),
        store=store,
        paused=paused,
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    await service.drain_once()

    assert runner.calls == 0
    assert runner.discard_calls == 0
    assert tuple(text for _, text in delivery.delivered) == tuple(
        f"synthetic queued response {index}" for index in range(5)
    )
    assert not await store.pending_delivery(
        source_conversation_id="33",
        limit=10,
    )


async def test_recovered_pause_settles_pending_owner_prefix_without_runner(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    conversation_id = "33"
    started_at = datetime(2026, 9, 3, 20, tzinfo=UTC)
    older_id = await _owner(
        store,
        "recovered-pause-older",
        source_conversation_id=conversation_id,
        created_at=started_at,
    )
    pause_id = await _owner(
        store,
        "recovered-pause-control",
        source_conversation_id=conversation_id,
        text_value="pause",
        created_at=started_at + timedelta(seconds=1),
    )
    controls = await store.pending_controls(
        source_conversation_id=conversation_id,
        limit=1,
    )
    assert len(controls) == 1 and controls[0].requires_recovery_run

    paused_path = tmp_path / "recovered-pause.json"
    PausedState.initialize(paused_path)
    runner = _NeverRunRunner()
    delivery = _SuccessfulDelivery(starting_id=9_200)
    service = _OneDrainService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=PausedState(paused_path),
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    await service.drain_once()

    assert runner.calls == 0
    assert runner.discard_calls == 1
    assert await PausedState(paused_path).is_paused()
    assert tuple(text for _, text in delivery.delivered) == ("Paused.",)
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(
                    message.c.id,
                    message.c.processed_at,
                    message.c.processing_attempts,
                    message.c.trace,
                ).where(message.c.id.in_((older_id, pause_id)))
            )
        ).all()
    assert all(row.processed_at is not None for row in rows)
    assert all(row.processing_attempts == 0 for row in rows)
    assert rows[0].trace["settlement"] == rows[1].trace["settlement"]


async def test_recovered_pause_preserves_host_input_visibility(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    started_at = datetime(2026, 9, 3, 21, tzinfo=UTC)
    host = await store.insert_waking(
        role="host",
        text="synthetic due instruction",
        source="schedule_wake",
        source_conversation_id="33",
        source_message_id="recovered-pause-host",
        created_at=started_at,
    )
    pause_id = await _owner(
        store,
        "recovered-pause-host-control",
        source_conversation_id="33",
        text_value="pause",
        created_at=started_at + timedelta(seconds=1),
    )
    paused_path = tmp_path / "recovered-pause-host.json"
    PausedState.initialize(paused_path)
    runner = _NeverRunRunner()
    delivery = _SuccessfulDelivery(starting_id=9_250)
    service = _OneDrainService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=PausedState(paused_path),
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    await service.drain_once()

    assert runner.calls == 0
    assert runner.discard_calls == 1
    assert tuple(text for _, text in delivery.delivered) == (
        "Reminder: synthetic due instruction",
        "Paused.",
    )
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.id, message.c.processed_at, message.c.trace).where(
                    message.c.id.in_((host.message.id, pause_id))
                )
            )
        ).all()
    assert all(row.processed_at is not None for row in rows)
    assert rows[0].trace["settlement"] == rows[1].trace["settlement"]


async def test_one_signal_drains_queued_pause_then_resume(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    started_at = datetime(2026, 9, 3, 22, tzinfo=UTC)
    paused_path = tmp_path / "queued-pause-resume.json"
    PausedState.initialize(paused_path)
    paused = PausedState(paused_path)
    runner = _ControlOnlyRunner(store)
    delivery = _SuccessfulDelivery(starting_id=9_300)
    service = JarvisService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=paused,
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    await service.receive_owner_message(
        DiscordOwnerMessage(
            "queued-pause",
            "33",
            "pause",
            started_at,
            Control.PAUSE,
        )
    )
    await service.receive_owner_message(
        DiscordOwnerMessage(
            "queued-resume",
            "33",
            "resume",
            started_at + timedelta(seconds=1),
            Control.RESUME,
        )
    )
    worker = asyncio.create_task(service.run_worker())
    await asyncio.wait_for(delivery.second_delivered_event.wait(), timeout=1)
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)

    assert runner.settled_controls == [Control.PAUSE, Control.RESUME]
    assert runner.run_calls <= 1
    assert not await paused.is_paused()
    assert tuple(text for _, text in delivery.delivered) == ("Paused.", "Resumed.")
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.source_message_id, message.c.processed_at)
                .where(
                    message.c.source == "discord",
                    message.c.source_message_id.in_(("queued-pause", "queued-resume")),
                )
                .order_by(message.c.created_at, message.c.id)
            )
        ).all()
    assert [row.source_message_id for row in rows] == [
        "queued-pause",
        "queued-resume",
    ]
    assert all(row.processed_at is not None for row in rows)


async def test_active_pause_then_resume_preserves_canonical_control_order(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    store = MessageStore(engine)
    started_at = datetime(2026, 9, 3, 22, 30, tzinfo=UTC)
    await _owner(
        store,
        "active-control-input",
        source_conversation_id="33",
        created_at=started_at,
    )
    paused_path = tmp_path / "active-pause-resume.json"
    PausedState.initialize(paused_path)
    paused = PausedState(paused_path)
    runner = _ActiveControlRunner(engine, store)
    delivery = _SuccessfulDelivery(starting_id=9_350)
    service = JarvisService(
        settings=Settings(
            database_url=SecretStr("postgresql://synthetic"),
            discord=DiscordSettings(
                bot_token=SecretStr("synthetic-token"),
                owner_user_id=11,
                guild_id=22,
                channel_id=33,
            ),
            owner_timezone="America/Los_Angeles",
            codex_profile_key="synthetic-profile",
            codex_model="gpt-5.6-terra",
            codex_state_root=tmp_path / "codex",
            runtime_state_directory=tmp_path / "runtime",
            google_oauth_state_path=tmp_path / "google.json",
            google_oauth_client_id=SecretStr("synthetic-google-client"),
            google_oauth_client_secret=SecretStr("synthetic-google-secret"),
            connector_encryption_key_version="v2",
            connector_encryption_keys=SecretStr("synthetic-keyring"),
            connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
            maps_api_key=SecretStr("synthetic-maps-key"),
            brave_api_key=SecretStr("synthetic-brave-key"),
        ),
        store=store,
        paused=paused,
        delivery=delivery,
        runner=runner,
        gateway=_NoopGateway(),
    )
    worker = asyncio.create_task(service.run_worker())
    service.request_work()
    await asyncio.wait_for(runner.active.wait(), timeout=1)
    await service.receive_owner_message(
        DiscordOwnerMessage(
            "active-pause",
            "33",
            "pause",
            started_at + timedelta(seconds=1),
            Control.PAUSE,
        )
    )
    await service.receive_owner_message(
        DiscordOwnerMessage(
            "active-resume",
            "33",
            "resume",
            started_at + timedelta(seconds=2),
            Control.RESUME,
        )
    )
    runner.continue_after_controls.set()
    await asyncio.wait_for(delivery.second_delivered_event.wait(), timeout=1)
    service.request_shutdown()
    await asyncio.wait_for(worker, timeout=1)

    assert tuple(text for _, text in delivery.delivered) == ("Paused.", "Resumed.")
    assert not await paused.is_paused()
    async with engine.connect() as connection:
        controls = (
            await connection.execute(
                select(message.c.source_message_id, message.c.processed_at)
                .where(
                    message.c.source == "discord",
                    message.c.source_message_id.in_(("active-pause", "active-resume")),
                )
                .order_by(message.c.created_at, message.c.id)
            )
        ).all()
    assert [row.source_message_id for row in controls] == [
        "active-pause",
        "active-resume",
    ]
    assert all(row.processed_at is not None for row in controls)


async def test_checkpoint_settlement_retry_reuses_conclusion_identity(
    engine: AsyncEngine,
) -> None:
    store = _LostSettlementAcknowledgementStore(engine)
    conversation_id = "settlement-ack-loss-channel"
    first_id = await _owner(
        store,
        "settlement-ack-loss-1",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(
        engine,
        conversation_id,
        "settlement-ack-loss-run",
        store=store,
    )
    claimed = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("settlement-ack-loss-owner"),
    )
    assert isinstance(claimed, ClaimAcquired)
    conclusion = ConversationConclusion("synthetic durable answer")

    with pytest.raises(ConnectionError, match="lost settlement acknowledgement"):
        await checkpoint.settle(
            claimed.claim,
            claimed.claim.through_checkpoint,
            conclusion,
        )

    later_id = await _owner(
        store,
        "settlement-ack-loss-2",
        source_conversation_id=conversation_id,
        text_value="ordinary synthetic follow-up",
    )
    repeated = await checkpoint.settle(
        claimed.claim,
        claimed.claim.through_checkpoint,
        conclusion,
    )
    assert isinstance(repeated, SettleMoreInput)

    async with engine.connect() as connection:
        assistant_rows = (
            await connection.execute(
                select(message.c.id, message.c.text).where(
                    message.c.source_conversation_id == conversation_id,
                    message.c.role == "assistant",
                )
            )
        ).all()
        processed_rows = (
            await connection.execute(
                select(message.c.id, message.c.processed_at).where(
                    message.c.id.in_((first_id, later_id))
                )
            )
        ).all()
        processed = {
            cast(UUID, row.id): cast(datetime | None, row.processed_at)
            for row in processed_rows
        }
    assert len(assistant_rows) == 1
    assert assistant_rows[0].text == "synthetic durable answer"
    assert processed[first_id] is not None
    assert processed[later_id] is None

    next_claim = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("settlement-ack-loss-next-owner"),
    )
    assert isinstance(next_claim, ClaimAcquired)
    assert tuple(value.input_id for value in next_claim.claim.inputs) == (
        str(later_id),
    )


async def test_kernel_checkpoint_claim_poll_settle_and_history(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "kernel-checkpoint-channel"
    started_at = datetime.now(UTC) - timedelta(seconds=2)
    first_id = await _owner(
        store,
        "kernel-input-1",
        source_conversation_id=conversation_id,
        text_value="current synthetic owner input",
        created_at=started_at,
    )
    checkpoint = _checkpoint(engine, conversation_id, "kernel-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("kernel-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    claim = result.claim
    assert (
        render_prompt(claim.inputs[0].sections).count("current synthetic owner input")
        == 1
    )
    assert str(claim.plan.profile.id) == "slice1_main"
    assert isinstance(
        await checkpoint.claim(
            ThreadId(conversation_id),
            OwnerToken("other-owner"),
        ),
        ClaimBusy,
    )

    second_id = await _owner(
        store,
        "kernel-input-2",
        source_conversation_id=conversation_id,
        text_value="compatible synthetic follow-up",
        created_at=started_at + timedelta(seconds=1),
    )
    polled = await checkpoint.poll(claim, claim.through_checkpoint)
    assert isinstance(polled, AppendInputs)
    assert tuple(value.input_id for value in polled.inputs) == (str(second_id),)
    settled = await checkpoint.settle(
        claim,
        polled.new_checkpoint,
        ConversationConclusion("synthetic answer"),
    )
    assert checkpoint.consumed_message_ids == (first_id, second_id)
    assert settled.type == "idle"

    history = await PostgresCanonicalHistory(engine).completed_history(
        ThreadId(conversation_id),
        exclude_input_ids=(),
        limit=10,
    )
    assert tuple(value.role for value in history) == ("owner", "owner", "assistant")
    assert tuple(value.text for value in history) == (
        "current synthetic owner input",
        "compatible synthetic follow-up",
        "synthetic answer",
    )


async def test_active_poll_host_settles_resume_overflow_without_model_input(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "resume-overflow-channel"
    await _owner(
        store,
        "resume-overflow-initial",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(
        engine,
        conversation_id,
        "resume-overflow-run",
        maximum_batch_size=1,
    )
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("resume-overflow-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    resume_ids = (
        await _owner(
            store,
            "resume-overflow-1",
            source_conversation_id=conversation_id,
            text_value="resume",
        ),
        await _owner(
            store,
            "resume-overflow-2",
            source_conversation_id=conversation_id,
            text_value="resume",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        ),
    )

    polled = await checkpoint.poll(result.claim, result.claim.through_checkpoint)

    assert isinstance(polled, NoNewInput)
    async with engine.connect() as connection:
        processed = (
            await connection.execute(
                select(message.c.processed_at).where(message.c.id.in_(resume_ids))
            )
        ).scalars()
    assert all(value is not None for value in processed)
    assert tuple(
        value.text
        for value in await store.pending_delivery(
            source_conversation_id=conversation_id,
            limit=10,
        )
    ) == ("Resumed.", "Resumed.")


async def test_kernel_stop_poll_settles_before_release(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    conversation_id = "kernel-stop-channel"
    initial_id = await _owner(
        store,
        "kernel-stop-initial",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "kernel-stop-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("kernel-stop-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    claim = result.claim
    stop_id = await _owner(
        store,
        "kernel-stop-control",
        source_conversation_id=conversation_id,
        text_value="stop",
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    poll = await checkpoint.poll(claim, claim.through_checkpoint)
    assert isinstance(poll, Preempt)
    assert checkpoint.consumed_message_ids == ()
    assert await store.has_pending_work(source_conversation_id=conversation_id)
    assert isinstance(
        await checkpoint.release(claim, "preempted by host policy"),
        Released,
    )
    assert checkpoint.consumed_message_ids == (initial_id, stop_id)
    assert isinstance(await checkpoint.release(claim, "cleanup"), AlreadyReleased)


@pytest.mark.parametrize(
    ("source", "control", "host_text", "expected"),
    [
        (
            "action",
            "stop",
            "synthetic action resolved",
            "Action update: synthetic action resolved\nStopped.",
        ),
        (
            "schedule_wake",
            "pause",
            "synthetic scheduled instruction",
            "Reminder: synthetic scheduled instruction\nPaused.",
        ),
    ],
)
async def test_host_input_remains_visible_when_polled_control_preempts(
    engine: AsyncEngine,
    source: str,
    control: str,
    host_text: str,
    expected: str,
) -> None:
    store = MessageStore(engine)
    conversation_id = f"host-control-{source}-{control}"
    host = await store.insert_waking(
        role="host",
        text=host_text,
        source=source,
        source_conversation_id=conversation_id,
        source_message_id=f"host-control-source-{source}-{control}",
        created_at=datetime.now(UTC),
    )
    checkpoint = _checkpoint(engine, conversation_id, f"host-control-run-{source}")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken(f"host-control-owner-{source}"),
    )
    assert isinstance(result, ClaimAcquired)
    control_id = await _owner(
        store,
        f"host-control-owner-source-{source}-{control}",
        source_conversation_id=conversation_id,
        text_value=control,
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    polled = await checkpoint.poll(result.claim, result.claim.through_checkpoint)
    assert isinstance(polled, Preempt)
    assert polled.reason == control
    assert isinstance(
        await checkpoint.release(result.claim, "preempted by host policy"),
        Released,
    )
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.text for value in pending) == (expected,)
    async with engine.connect() as connection:
        processed = (
            await connection.execute(
                select(message.c.id, message.c.processed_at).where(
                    message.c.id.in_((host.message.id, control_id))
                )
            )
        ).all()
    assert all(row.processed_at is not None for row in processed)
    assert not await store.has_pending_work(source_conversation_id=conversation_id)


async def test_idle_control_and_exhausted_input_are_host_settled(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    control_conversation = "idle-control-channel"
    resume_id = await _owner(
        store,
        "idle-resume",
        source_conversation_id=control_conversation,
        text_value=" ReSuMe ",
    )
    controls = await store.pending_controls(
        source_conversation_id=control_conversation,
        limit=10,
    )
    assert tuple(
        (value.message_id, value.control, value.requires_recovery_run)
        for value in controls
    ) == ((resume_id, "resume", False),)
    control_checkpoint = _checkpoint(engine, control_conversation, "idle-control-run")
    settled = await control_checkpoint.settle_idle_control(
        message_id=resume_id,
        control="resume",
    )
    assert settled is not None
    assert settled.already_processed is False
    repeated = await control_checkpoint.settle_idle_control(
        message_id=resume_id,
        control="resume",
    )
    assert repeated is not None and repeated.already_processed is True

    exhausted_conversation = "exhausted-channel"
    exhausted_id = await _owner(
        store,
        "exhausted-input",
        source_conversation_id=exhausted_conversation,
    )
    for attempt in range(1, 4):
        interrupted = _checkpoint(
            engine,
            exhausted_conversation,
            f"exhausted-run-{attempt}",
        )
        claim = await interrupted.claim(
            ThreadId(exhausted_conversation),
            OwnerToken(f"exhausted-owner-{attempt}"),
        )
        assert isinstance(claim, ClaimAcquired)
        await interrupted.release(claim.claim, "synthetic process interruption")
    recovery_checkpoint = _checkpoint(
        engine,
        exhausted_conversation,
        "exhausted-run-4",
    )
    recovered = await recovery_checkpoint.claim(
        ThreadId(exhausted_conversation),
        OwnerToken("exhausted-owner-4"),
    )
    assert isinstance(recovered, ClaimNoWork)
    assert recovery_checkpoint.consumed_message_ids == (exhausted_id,)
    await store.record_run_metrics(
        consumed_message_ids=recovery_checkpoint.consumed_message_ids,
        run_id="exhausted-run-4",
        provider_turns=0,
        input_tokens=None,
        output_tokens=None,
        duration_seconds=0.0,
    )
    pending = await store.pending_delivery(
        source_conversation_id=exhausted_conversation,
        limit=10,
    )
    assert tuple(value.text for value in pending) == (
        "I stopped this message because it reached the configured retry limit.",
    )


async def test_claimed_durable_stop_preempts_before_provider_and_truncates_batch(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "durable-stop-recovery-channel"
    started_at = datetime.now(UTC) - timedelta(seconds=3)
    initial_id = await _owner(
        store,
        "durable-stop-initial",
        source_conversation_id=conversation_id,
        created_at=started_at,
    )
    stop_id = await _owner(
        store,
        "durable-stop-control",
        source_conversation_id=conversation_id,
        text_value=" PaUsE ",
        created_at=started_at + timedelta(seconds=1),
    )
    later_id = await _owner(
        store,
        "durable-stop-later",
        source_conversation_id=conversation_id,
        created_at=started_at + timedelta(seconds=2),
    )
    pending_controls = await store.pending_controls(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.message_id for value in pending_controls) == (stop_id,)
    assert pending_controls[0].requires_recovery_run is True
    checkpoint = _checkpoint(engine, conversation_id, "durable-stop-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("durable-stop-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    assert tuple(value.input_id for value in result.claim.inputs) == (
        str(initial_id),
        str(stop_id),
    )
    assert str(result.claim.through_checkpoint) == str(stop_id)
    poll = await checkpoint.poll(result.claim, result.claim.through_checkpoint)
    assert isinstance(poll, Preempt)

    async with engine.connect() as connection:
        rows_before_release = (
            await connection.execute(
                select(message.c.id, message.c.processed_at).where(
                    message.c.id.in_((initial_id, stop_id, later_id))
                )
            )
        ).all()
    assert all(row.processed_at is None for row in rows_before_release)

    assert isinstance(
        await checkpoint.release(result.claim, "preempted by host policy"),
        Released,
    )
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.id, message.c.processed_at).where(
                    message.c.id.in_((initial_id, stop_id, later_id))
                )
            )
        ).all()
    processed = {
        cast(UUID, row.id): cast(datetime | None, row.processed_at) for row in rows
    }
    assert processed[initial_id] is not None
    assert processed[stop_id] is not None
    assert processed[later_id] is None


async def test_final_poll_append_is_left_for_next_run(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    conversation_id = "final-poll-race-channel"
    first_id = await _owner(
        store,
        "final-poll-first",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "final-poll-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("final-poll-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    later_id = await _owner(
        store,
        "final-poll-later",
        source_conversation_id=conversation_id,
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    final_poll = await checkpoint.poll(result.claim, result.claim.through_checkpoint)
    assert isinstance(final_poll, AppendInputs)
    settlement = await checkpoint.settle(
        result.claim,
        result.claim.through_checkpoint,
        ConversationConclusion("valid answer before the raced input"),
    )
    assert isinstance(settlement, SettleMoreInput)
    assert checkpoint.consumed_message_ids == (first_id,)
    async with engine.connect() as connection:
        later_processed = await connection.scalar(
            select(message.c.processed_at).where(message.c.id == later_id)
        )
    assert later_processed is None


async def test_resume_arriving_during_claim_is_host_settled_not_appended(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "active-resume-channel"
    await _owner(
        store,
        "active-resume-initial",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "active-resume-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("active-resume-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    resume_id = await _owner(
        store,
        "active-resume-control",
        source_conversation_id=conversation_id,
        text_value="resume",
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    poll = await checkpoint.poll(result.claim, result.claim.through_checkpoint)
    assert isinstance(poll, NoNewInput)
    await checkpoint.settle(
        result.claim,
        result.claim.through_checkpoint,
        ConversationConclusion("synthetic answer"),
    )
    history = await PostgresCanonicalHistory(engine).completed_history(
        ThreadId(conversation_id),
        exclude_input_ids=(),
        limit=10,
    )
    assert any(value.message_id == str(resume_id) for value in history)
    assert all(
        "\nresume\n" not in render_prompt(value.sections)
        for value in result.claim.inputs
    )


async def test_kernel_park_is_durable_and_release_does_not_rearm(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "kernel-park-channel"
    waking_id = await _owner(
        store,
        "kernel-park-input",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "kernel-park-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("kernel-park-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    assert isinstance(
        await checkpoint.park(result.claim, "provider configuration defect"),
        Parked,
    )
    assert isinstance(
        await checkpoint.release(result.claim, "kernel cleanup"),
        AlreadyReleased,
    )
    assert await store.circuit_is_open()
    await store.clear_parked(message_ids=(waking_id,))


async def test_checkpoint_maps_undeliverable_response_to_short_conclusion(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "long-response-channel"
    waking_id = await _owner(
        store,
        "long-response-input",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "long-response-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("long-response-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    await checkpoint.settle(
        result.claim,
        result.claim.through_checkpoint,
        ConversationConclusion("x" * 2_001),
    )
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.text for value in pending) == (
        "I stopped because the response exceeded Discord's message limit.",
    )
    async with engine.connect() as connection:
        trace = await connection.scalar(
            select(message.c.trace).where(message.c.id == waking_id)
        )
    assert isinstance(trace, dict)
    typed_trace = cast(dict[str, object], trace)
    settlement = cast(dict[str, object], typed_trace["settlement"])
    assert settlement["outcome"] == "response_too_long"


async def test_scheduled_wake_claim_selects_proactive_plan(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    conversation_id = "scheduled-plan-channel"
    inserted = await store.insert_waking(
        role="host",
        text="synthetic scheduled wake",
        source="schedule_wake",
        source_conversation_id=conversation_id,
        source_message_id="synthetic-schedule-id",
        created_at=datetime.now(UTC),
    )
    checkpoint = _checkpoint(engine, conversation_id, "scheduled-plan-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("scheduled-plan-owner"),
    )
    assert isinstance(result, ClaimAcquired)
    assert str(result.claim.plan.profile.id) == "slice1_scheduled_wake"
    await checkpoint.settle(
        result.claim,
        result.claim.through_checkpoint,
        ConversationConclusion(None),
    )
    assert checkpoint.consumed_message_ids == (inserted.message.id,)
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.text for value in pending) == (
        "Reminder: synthetic scheduled wake",
    )


async def test_promoted_action_host_finish_gets_visible_fallback_and_one_host_per_run(
    engine: AsyncEngine,
) -> None:
    store = MessageStore(engine)
    conversation_id = "action-fallback-channel"
    await _owner(
        store,
        "action-fallback-owner",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "action-fallback-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("action-fallback-owner-token"),
    )
    assert isinstance(result, ClaimAcquired)
    first_host = await store.insert_waking(
        role="host",
        text="synthetic action succeeded",
        source="action",
        source_conversation_id=conversation_id,
        source_message_id="synthetic-action-1:succeeded",
        created_at=datetime.now(UTC),
    )
    second_host = await store.insert_waking(
        role="host",
        text="second synthetic action succeeded",
        source="action",
        source_conversation_id=conversation_id,
        source_message_id="synthetic-action-2:succeeded",
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    polled = await checkpoint.poll(result.claim, result.claim.through_checkpoint)
    assert isinstance(polled, AppendInputs)
    assert tuple(value.input_id for value in polled.inputs) == (
        str(first_host.message.id),
    )

    settled = await checkpoint.settle(
        result.claim,
        polled.new_checkpoint,
        ConversationConclusion(None),
    )
    assert isinstance(settled, SettleMoreInput)
    pending = await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert tuple(value.text for value in pending) == (
        "Action update: synthetic action succeeded",
    )

    next_checkpoint = _checkpoint(engine, conversation_id, "second-action-fallback-run")
    next_result = await next_checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("second-action-fallback-owner-token"),
    )
    assert isinstance(next_result, ClaimAcquired)
    assert tuple(value.input_id for value in next_result.claim.inputs) == (
        str(second_host.message.id),
    )


async def test_owner_only_finish_remains_silent(engine: AsyncEngine) -> None:
    store = MessageStore(engine)
    conversation_id = "owner-silent-finish-channel"
    await _owner(
        store,
        "owner-silent-finish",
        source_conversation_id=conversation_id,
    )
    checkpoint = _checkpoint(engine, conversation_id, "owner-silent-finish-run")
    result = await checkpoint.claim(
        ThreadId(conversation_id),
        OwnerToken("owner-silent-finish-token"),
    )
    assert isinstance(result, ClaimAcquired)
    await checkpoint.settle(
        result.claim,
        result.claim.through_checkpoint,
        ConversationConclusion(None),
    )
    assert not await store.pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.db import create_engine
from jarvis.ownership import (
    DEPLOYMENT_LOCK_KEY,
    Database,
    DeploymentAlreadyOwned,
    DeploymentOwnershipDefect,
    deployment_ownership,
)


class _Connection:
    def __init__(self, results: list[bool]) -> None:
        self.results = results
        self.parameters: list[dict[str, object] | None] = []
        self.closed = False
        self.invalidated = False

    async def commit(self) -> None:
        pass

    async def scalar(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> bool:
        del statement
        self.parameters.append(parameters)
        return self.results.pop(0)


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection_value = connection

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_Connection]:
        yield self.connection_value


async def test_deployment_lock_is_held_for_complete_context() -> None:
    connection = _Connection([True, True])
    engine = cast(AsyncEngine, _Engine(connection))
    async with deployment_ownership(engine):
        assert len(connection.parameters) == 1
    assert connection.parameters == [
        {"lock_key": DEPLOYMENT_LOCK_KEY},
        {"lock_key": DEPLOYMENT_LOCK_KEY},
    ]


async def test_second_instance_refuses_to_start() -> None:
    engine = cast(AsyncEngine, _Engine(_Connection([False])))
    with pytest.raises(DeploymentAlreadyOwned):
        async with deployment_ownership(engine):
            raise AssertionError("unreachable")


async def test_lock_releases_when_service_body_fails() -> None:
    connection = _Connection([True, True])
    engine = cast(AsyncEngine, _Engine(connection))
    with pytest.raises(LookupError):
        async with deployment_ownership(engine):
            raise LookupError("service failed")
    assert len(connection.parameters) == 2


async def test_failed_unlock_is_a_host_defect() -> None:
    engine = cast(AsyncEngine, _Engine(_Connection([True, False])))
    with pytest.raises(DeploymentOwnershipDefect):
        async with deployment_ownership(engine):
            pass


@pytest.mark.postgres
@pytest.mark.skipif(
    os.environ.get("JARVIS_TEST_DATABASE_URL") is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
async def test_real_postgres_refuses_second_deployment_owner() -> None:
    database_url = os.environ["JARVIS_TEST_DATABASE_URL"]
    first = create_engine(database_url)
    second = create_engine(database_url)
    try:
        async with deployment_ownership(first):
            with pytest.raises(DeploymentAlreadyOwned):
                async with deployment_ownership(second):
                    raise AssertionError("second owner entered the deployment")
        async with deployment_ownership(second):
            pass
    finally:
        await first.dispose()
        await second.dispose()


async def test_lost_owner_connection_refuses_mutation_without_reconnect() -> None:
    connection = _Connection([True])
    engine = cast(AsyncEngine, _Engine(connection))
    database: Database | None = None
    with pytest.raises(DeploymentOwnershipDefect, match="owner connection was lost"):
        async with deployment_ownership(engine) as database:
            connection.invalidated = True
            with pytest.raises(DeploymentOwnershipDefect):
                async with database.begin():
                    raise AssertionError("lost owner accepted a transaction")
    assert database is not None
    with pytest.raises(DeploymentOwnershipDefect):
        async with database.begin():
            raise AssertionError("released owner accepted a transaction")
    assert len(connection.parameters) == 1


async def test_lost_owner_blocks_paid_dispatch_action_acceptance_and_publication() -> (
    None
):
    from datetime import UTC, datetime
    from uuid import uuid4

    from llm_agent_kernel import Checkpoint, InputId, ThreadId
    from llm_agent_kernel.decisions import ModelDecisionRequest, ModelDecisionScope
    from llm_tools import (
        InvocationPosition,
        ReplayPolicy,
        ToolEffect,
        ToolId,
        raw_input_digest,
    )
    from llm_tools.execution import ParsedJson

    from jarvis.actions import ActionStore, ExecutionContract
    from jarvis.decisions import PostgresModelDecisionJournal
    from jarvis.messages import MessageStore, SettlementTrace
    from jarvis.read_positions import PostgresReadRecorder

    identifier = uuid4()
    request = ModelDecisionRequest(
        scope=ModelDecisionScope(ThreadId("owner-thread"), InputId(str(identifier))),
        ordinal=1,
        definition_fingerprint="a" * 64,
        plan_revision="plan-v1",
        input_ids=(InputId(str(identifier)),),
        through_checkpoint=Checkpoint(str(identifier)),
        as_of=datetime.now(UTC),
        model_step_ordinal_before=0,
        protocol_repairs=0,
        canonical_content=("original context",),
        submitted_content=("original input",),
    )
    contract = ExecutionContract(
        tool_contract_revision="tool-v1",
        implementation_revision="implementation-v1",
        policy_revision="policy-v1",
        plan_revision="plan-v1",
        tool_effect=ToolEffect.Write,
        replay_policy=ReplayPolicy.ReDispatchable,
        input_digest=raw_input_digest(ParsedJson({})),
        max_attempts=2,
        claim_id=str(uuid4()),
        through_checkpoint=str(identifier),
        model_step_ordinal=1,
        input_message_ids=(str(identifier),),
        write_gate_supporting_owner_message_ids=(str(identifier),),
    )
    connection = _Connection([True])
    with pytest.raises(DeploymentOwnershipDefect, match="owner connection was lost"):
        async with deployment_ownership(
            cast(AsyncEngine, _Engine(connection))
        ) as database:
            connection.invalidated = True
            with pytest.raises(DeploymentOwnershipDefect):
                await PostgresModelDecisionJournal(database).arm(request)
            with pytest.raises(DeploymentOwnershipDefect):
                await PostgresReadRecorder(database).dispatch_started(
                    position=InvocationPosition("original-read"),
                    replay_policy=ReplayPolicy.BilledOnce,
                )
            with pytest.raises(DeploymentOwnershipDefect):
                await ActionStore(database).insert_automatic(
                    tool_name=ToolId("calendar.create_event"),
                    arguments={},
                    execution_contract=contract,
                    origin_message_id=identifier,
                )
            with pytest.raises(DeploymentOwnershipDefect):
                await MessageStore(database).settle(
                    consumed_message_ids=(identifier,),
                    source_conversation_id="owner-thread",
                    trace=SettlementTrace(
                        "original-run", str(identifier), "conversation", "answered"
                    ),
                    conclusion_text="must not publish",
                )
    assert len(connection.parameters) == 1


@pytest.mark.postgres
@pytest.mark.skipif(
    os.environ.get("JARVIS_TEST_DATABASE_URL") is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
async def test_real_lost_owner_cannot_reconnect_to_publish() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from jarvis.messages import MessageStore, SettlementTrace

    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    conversation = f"lost-owner-{uuid4()}"
    original = None
    try:
        with pytest.raises(DeploymentOwnershipDefect):
            async with deployment_ownership(engine) as database:
                messages = MessageStore(database)
                original = await messages.insert_waking(
                    role="owner",
                    text="Original input remains unconsumed after owner loss.",
                    source="qualification",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=datetime.now(UTC),
                )
                async with database.connect() as owner_connection:
                    pass
                await owner_connection.invalidate()
                with pytest.raises(DeploymentOwnershipDefect):
                    await messages.settle(
                        consumed_message_ids=(original.message.id,),
                        source_conversation_id=conversation,
                        trace=SettlementTrace(
                            "lost-owner",
                            str(original.message.id),
                            "conversation",
                            "answered",
                        ),
                        conclusion_text="Forbidden publication after owner loss.",
                    )
        assert original is not None
        surviving_store = MessageStore(engine)
        persisted = await surviving_store.message_by_id(original.message.id)
        assert persisted is not None and persisted.processed_at is None
        assert (
            await surviving_store.pending_delivery(
                source_conversation_id=conversation, limit=10
            )
            == ()
        )
    finally:
        await engine.dispose()

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Never, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from llm_agent_kernel import (
    ClaimAcquired,
    HostRef,
    OwnerToken,
    RunId,
    SuspensionConclusion,
    ThreadId,
    WaitingFor,
)
from llm_tools import (
    CapabilityProfile,
    FrozenToolPlan,
    HostTable,
    ProfileId,
    ReplayPolicy,
    Reservation,
    RunLimits,
    Settlement,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolId,
    ToolPlan,
    canonical_json_bytes,
    raw_input_digest,
)
from llm_tools.execution import ParsedJson
from llm_tools.testing import InMemoryBudgetState
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
)
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.db import action, create_engine, message
from jarvis.messages import (
    ACTION_MODEL_CONTEXT_SEPARATOR,
    MessageStore,
    SettlementTrace,
    host_safe_text,
)
from jarvis.schedule_tools import schedule_family
from jarvis.terminal import TurnEvidence
from jarvis.write_connectors import (
    GmailUpdateReconciliationBasis,
    ReconciliationResult,
    gmail_content_digest,
)
from jarvis.write_dispatch import ActionRecovery
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    GmailUpdateDraftInput,
    Mailbox,
    TimedEventTime,
    WriteAttemptBudget,
    WriteResponse,
    calendar_write_family,
    gmail_write_family,
)

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
postgres = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


async def _owner(
    engine: AsyncEngine,
    *,
    created_at: datetime = NOW,
    processed_at: datetime | None = None,
    text: str = "Synthetic owner request.",
    source_conversation_id: str = "synthetic-recovery-channel",
) -> UUID:
    identifier = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=identifier,
                role="owner",
                text=text,
                source="discord",
                source_conversation_id=source_conversation_id,
                source_message_id=str(uuid4()),
                created_at=created_at,
                processed_at=processed_at,
                processing_attempts=1,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )
    return identifier


def _contract(
    arguments: Mapping[str, object],
    input_ids: tuple[UUID, ...],
    *,
    supporting_owner_ids: tuple[UUID, ...] | None = None,
    claim_id: str | None = None,
    model_step_ordinal: int = 1,
    tool_contract_revision: str = "1" * 64,
    implementation_revision: str = "jarvis-synthetic-write-v1",
    policy_revision: str = "2" * 64,
    plan_revision: str = "3" * 64,
) -> ExecutionContract:
    return ExecutionContract(
        tool_contract_revision=tool_contract_revision,
        implementation_revision=implementation_revision,
        policy_revision=policy_revision,
        plan_revision=plan_revision,
        tool_effect=ToolEffect.Write,
        replay_policy=ReplayPolicy.ReDispatchable,
        input_digest=raw_input_digest(ParsedJson(dict(arguments))),
        max_attempts=2,
        claim_id=claim_id or str(uuid4()),
        through_checkpoint=str(input_ids[-1]),
        model_step_ordinal=model_step_ordinal,
        input_message_ids=tuple(map(str, input_ids)),
        write_gate_supporting_owner_message_ids=tuple(
            map(str, supporting_owner_ids or (input_ids[-1],))
        ),
    )


class _NeverWriteProvider:
    async def gmail_create_draft(self, *args: object) -> Never:
        raise AssertionError(args)

    async def gmail_update_draft(self, *args: object) -> Never:
        raise AssertionError(args)

    async def gmail_send_draft(self, *args: object) -> Never:
        raise AssertionError(args)

    async def calendar_create_event(self, *args: object) -> Never:
        raise AssertionError(args)

    async def calendar_update_event(self, *args: object) -> Never:
        raise AssertionError(args)

    async def calendar_delete_event(self, *args: object) -> Never:
        raise AssertionError(args)


class _AlwaysAmbiguousProvider(_NeverWriteProvider):
    def __init__(self, store: ActionStore) -> None:
        self.store = store
        self.effects: list[UUID] = []
        self.budgets: list[WriteAttemptBudget] = []

    async def gmail_create_draft(self, *args: object) -> Never:
        if len(args) != 3:
            raise AssertionError(args)
        value, effect_id, attempts = args
        if (
            not isinstance(value, GmailCreateDraftInput)
            or not isinstance(effect_id, UUID)
            or not isinstance(attempts, WriteAttemptBudget)
        ):
            raise AssertionError(args)
        self.effects.append(effect_id)
        self.budgets.append(attempts)
        await self.store.stage_external_attempts(
            action_id=effect_id,
            actual_external_attempts=attempts.recovered_attempts + 1,
        )
        raise TimeoutError


class _SuccessfulUpdateProvider:
    def __init__(self) -> None:
        self.effects: list[UUID] = []
        self.budgets: list[WriteAttemptBudget] = []

    async def gmail_create_draft(self, *args: object) -> Never:
        raise AssertionError(args)

    async def gmail_send_draft(self, *args: object) -> Never:
        raise AssertionError(args)

    async def gmail_update_draft(
        self,
        value: GmailUpdateDraftInput,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        self.effects.append(effect_id)
        self.budgets.append(attempts)
        return WriteResponse(
            GmailDraftSuccess(
                draft_id=value.draft_id,
                message_id="synthetic-updated-message",
                thread_id="synthetic-thread",
                jarvis_effect_id="a" * 64,
                content_digest=gmail_content_digest(value.replacement),
                observed_at=NOW,
            ),
            1,
        )


class _AbsentUpdateReconciler:
    def __init__(self) -> None:
        self.calls = 0

    async def reconcile_gmail_update(
        self,
        value: GmailUpdateDraftInput,
        basis: GmailUpdateReconciliationBasis,
    ) -> ReconciliationResult[GmailDraftSuccess]:
        del value, basis
        self.calls += 1
        return ReconciliationResult("absent", "exact-old-draft-remained-unchanged")


def _gmail_plan() -> tuple[ToolBinding[Any, Any, Any], FrozenToolPlan]:
    catalog = ToolCatalog.compose(
        (gmail_write_family(cast("Any", _NeverWriteProvider())),)
    )
    tool_id = ToolId("gmail.create_draft")
    profile = CapabilityProfile(
        ProfileId("action_recovery_gmail_create"),
        (ToolGrant(tool_id, None),),
        RunLimits(1, 4, 524_288, 131_072, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    return catalog.binding(tool_id), plan


def _pending_calendar_approval(
    owner: UUID,
) -> tuple[StoredAction, FrozenToolPlan]:
    catalog = ToolCatalog.compose(
        (calendar_write_family(cast("Any", _NeverWriteProvider())),)
    )
    tool_id = ToolId("calendar.create_event")
    profile = CapabilityProfile(
        ProfileId("pending_approval_recovery"),
        (ToolGrant(tool_id, None),),
        RunLimits(1, 8, 1_048_576, 1_048_576, 1, 60.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    binding = catalog.binding(tool_id)
    arguments = CalendarCreateEventInput(
        calendar_id="shared@example.invalid",
        event=CalendarWritableEvent(
            summary="Synthetic approval recovery",
            description=None,
            location=None,
            start=TimedEventTime(date_time=NOW, time_zone="UTC"),
            end=TimedEventTime(date_time=NOW + timedelta(hours=1), time_zone="UTC"),
            recurrence=(),
            attendees=(),
            use_default_reminders=True,
            reminders=(),
        ),
        notify_attendees=False,
    ).model_dump(mode="json")
    return StoredAction(
        id=uuid4(),
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=_contract(
            arguments,
            (owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        ),
        status="awaiting_approval",
        attempts=0,
        execute_after=None,
        origin_message_id=owner,
        approval_message_id=uuid4(),
        created_at=NOW,
        decided_at=None,
        completed_at=None,
        result=None,
    ), plan


async def test_pending_approval_recovery_closes_original_input_before_main() -> None:
    pending, plan = _pending_calendar_approval(uuid4())

    class Store:
        def __init__(self) -> None:
            self.input_pending = True
            self.recovered: list[UUID] = []

        async def pending_approvals(self, **kwargs: object) -> tuple[StoredAction, ...]:
            return (pending,)

        async def recover_pending_approval_origin(
            self, *, action_id: UUID, source_conversation_id: str
        ) -> bool:
            assert source_conversation_id == "approval-recovery"
            assert action_id == pending.id
            if not self.input_pending:
                return False
            self.input_pending = False
            self.recovered.append(action_id)
            return True

        async def executing_schedule_receipts(self, **kwargs: object) -> tuple[()]:
            return ()

        async def recovery_candidates(self, **kwargs: object) -> tuple[()]:
            return ()

        async def unreported_terminal(self, **kwargs: object) -> tuple[()]:
            return ()

    store = Store()
    recovery = ActionRecovery(
        actions=cast("Any", store),
        google_write=cast("Any", _NeverWriteProvider()),
        plan=plan,
        source_conversation_id="approval-recovery",
    )
    assert await recovery.recover() == 1
    assert not store.input_pending
    assert store.recovered == [pending.id]
    assert await recovery.recover() == 0


@postgres
@pytest.mark.parametrize("with_host_input", (False, True))
async def test_committed_pending_approval_blocks_completed_model_replay(
    engine: AsyncEngine,
    with_host_input: bool,
) -> None:
    from llm_agent_kernel import Checkpoint, InputId
    from llm_agent_kernel.decisions import ModelDecisionRequest, ModelDecisionScope
    from provider_runtime.agent_runtime import AgentSessionRef, AgentTerminal

    from jarvis.decisions import PostgresModelDecisionJournal
    from jarvis.messages import NoMessages
    from jarvis.ownership import deployment_ownership

    async with deployment_ownership(engine) as database:
        conversation = f"approval-crash-{uuid4()}"
        messages = MessageStore(database)
        owner = (
            await messages.insert_waking(
                role="owner",
                text="Create this event after my approval.",
                source="discord",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=NOW,
            )
        ).message.id
        pending, plan = _pending_calendar_approval(owner)
        original_inputs = (owner,)
        if with_host_input:
            host = (
                await messages.insert_waking(
                    role="host",
                    text=(
                        "The previous event was created."
                        + ACTION_MODEL_CONTEXT_SEPARATOR
                        + "private model-only evidence"
                    ),
                    source="action",
                    source_conversation_id=conversation,
                    source_message_id=str(uuid4()),
                    created_at=NOW - timedelta(seconds=1),
                )
            ).message.id
            original_inputs = (host, owner)
            pending = replace(
                pending,
                execution_contract=ExecutionContract.model_validate(
                    {
                        **pending.execution_contract.as_json(),
                        "input_message_ids": list(map(str, original_inputs)),
                    }
                ),
            )
        actions = ActionStore(database)
        approval = await actions.insert_awaiting_approval(
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            execution_contract=pending.execution_contract,
            origin_message_id=owner,
            approval_text="Original persisted approval",
            source_conversation_id=conversation,
            action_id=pending.id,
            created_at=NOW,
        )
        request = ModelDecisionRequest(
            scope=ModelDecisionScope(
                ThreadId(conversation), InputId(str(original_inputs[0]))
            ),
            ordinal=1,
            definition_fingerprint="f" * 64,
            plan_revision=plan.plan_revision,
            input_ids=tuple(InputId(str(value)) for value in original_inputs),
            through_checkpoint=Checkpoint(str(owner)),
            as_of=NOW,
            model_step_ordinal_before=0,
            protocol_repairs=0,
            canonical_content=("original request",),
            submitted_content=("original request",),
        )
        journal = PostgresModelDecisionJournal(database)
        await journal.arm(request)
        await journal.complete(
            request,
            AgentTerminal(
                status="succeeded",
                failure=None,
                final_text="accepted original write",
                session_ref=AgentSessionRef(
                    "agent-session-ref.v1",
                    "codex",
                    "sdk",
                    "original-session",
                    "approval-test",
                    "f" * 64,
                    "a" * 64,
                ),
            ),
        )
        original = await messages.message_by_id(owner)
        assert original is not None and original.processed_at is None
        recovery = ActionRecovery(
            actions=actions,
            google_write=cast("Any", _NeverWriteProvider()),
            plan=plan,
            source_conversation_id=conversation,
        )
        assert await recovery.recover() == 1
        assert isinstance(
            await messages.claim(
                source_conversation_id=conversation,
                maximum_batch_size=1,
                maximum_attempts=1,
            ),
            NoMessages,
        )
        assert await actions.get(pending.id) == approval.action
        settled = await messages.message_by_id(owner)
        assert settled is not None and settled.processed_at is not None
        settlement = settled.trace["settlement"]
        assert isinstance(settlement, dict)
        settlement = cast("dict[str, object]", settlement)
        if with_host_input:
            visibility_id = settlement["conclusion_message_id"]
            assert isinstance(visibility_id, str)
            visibility = await messages.message_by_id(UUID(visibility_id))
            assert visibility is not None
            assert visibility.id != approval.message_id
            assert visibility.text == "Action update: The previous event was created."
            host_message = await messages.message_by_id(original_inputs[0])
            assert host_message is not None and host_message.processed_at is not None
            assert host_message.trace["settlement"] == settlement
        else:
            assert settlement["conclusion_message_id"] == str(approval.message_id)
        assert await recovery.recover() == 0
        async with database.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(action)
                    .where(action.c.origin_message_id == owner)
                )
                == 1
            )
            assert await connection.scalar(
                select(func.count())
                .select_from(message)
                .where(
                    message.c.source_conversation_id == conversation,
                    message.c.role == "assistant",
                )
            ) == 1 + int(with_host_input)


def _gmail_arguments() -> dict[str, object]:
    return GmailCreateDraftInput(
        content=GmailContent(
            to=(Mailbox(name=None, address="owner@example.invalid"),),
            cc=(),
            bcc=(),
            subject="Synthetic recovery draft",
            body_text="Synthetic recovery body",
            reply_to=None,
        )
    ).model_dump(mode="json")


def _gmail_success() -> GmailDraftSuccess:
    return GmailDraftSuccess(
        draft_id="synthetic-draft",
        message_id="synthetic-message",
        thread_id="synthetic-thread",
        jarvis_effect_id="a" * 64,
        content_digest="b" * 64,
        observed_at=NOW,
    )


def _resolution_context(text: str) -> dict[str, object]:
    _safe, separator, encoded = text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)
    assert separator == ACTION_MODEL_CONTEXT_SEPARATOR
    value = json.loads(encoded)
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


async def _executing_gmail_action(
    store: ActionStore,
    binding: ToolBinding[Any, Any, Any],
    plan: FrozenToolPlan,
    input_ids: tuple[UUID, ...],
    *,
    claim_id: str | None = None,
    model_step_ordinal: int = 1,
) -> StoredAction:
    arguments = _gmail_arguments()
    contract = _contract(
        arguments,
        input_ids,
        claim_id=claim_id,
        model_step_ordinal=model_step_ordinal,
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=input_ids[0],
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=4,
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    return await store.stage_external_attempts(
        action_id=stored.id,
        actual_external_attempts=1,
    )


class _GoogleReconciler:
    def __init__(
        self,
        result: ReconciliationResult[GmailDraftSuccess],
        *,
        engine: AsyncEngine | None = None,
        pending_input_ids: tuple[UUID, ...] = (),
    ) -> None:
        self.result = result
        self.engine = engine
        self.pending_input_ids = pending_input_ids
        self.calls: list[UUID] = []

    async def reconcile_gmail_create(
        self, value: GmailCreateDraftInput, action_id: UUID
    ) -> ReconciliationResult[GmailDraftSuccess]:
        del value
        self.calls.append(action_id)
        if len(self.calls) == 2 and self.engine is not None:
            async with self.engine.connect() as connection:
                processed = tuple(
                    (
                        await connection.execute(
                            select(message.c.processed_at).where(
                                message.c.id.in_(self.pending_input_ids)
                            )
                        )
                    ).scalars()
                )
                resolution_count = (
                    await connection.execute(
                        select(func.count())
                        .select_from(message)
                        .where(
                            message.c.source == "action",
                            message.c.source_message_id.in_(
                                tuple(
                                    f"{identifier}:succeeded"
                                    for identifier in self.calls
                                )
                            ),
                        )
                    )
                ).scalar_one()
            assert processed and all(value is None for value in processed)
            assert resolution_count == 0
        return self.result


class _SequenceGoogleReconciler:
    def __init__(
        self, results: tuple[ReconciliationResult[GmailDraftSuccess], ...]
    ) -> None:
        self.results = list(results)
        self.calls: list[UUID] = []

    async def reconcile_gmail_create(
        self, value: GmailCreateDraftInput, action_id: UUID
    ) -> ReconciliationResult[GmailDraftSuccess]:
        del value
        self.calls.append(action_id)
        if not self.results:
            raise AssertionError("unexpected extra reconciliation")
        return self.results.pop(0)


async def _mark_resolution_processed(
    engine: AsyncEngine, action_ids: tuple[UUID, ...]
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(
                message.c.source == "action",
                message.c.source_message_id.in_(
                    tuple(
                        f"{action_id}:{status}"
                        for action_id in action_ids
                        for status in (
                            "queued",
                            "succeeded",
                            "failed",
                            "uncertain",
                            "cancelled",
                        )
                    )
                ),
            )
            .values(processed_at=datetime.now(UTC))
        )


@postgres
async def test_future_schedule_page_does_not_starve_executing_recovery(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    origin = await _owner(engine)
    created_at = datetime.now(UTC) - timedelta(days=1)
    due = datetime.now(UTC) + timedelta(days=365)
    rows: list[dict[str, object]] = []
    future_ids: list[UUID] = []
    for ordinal in range(101):
        identifier = uuid4()
        future_ids.append(identifier)
        arguments: dict[str, object] = {
            "request": {
                "type": "create",
                "execute_after": due.isoformat(),
                "instruction": f"Synthetic future reminder {ordinal}",
            }
        }
        contract = _contract(arguments, (origin,))
        rows.append(
            {
                "id": identifier,
                "tool_name": "schedule.wake",
                "arguments": arguments,
                "execution_contract": contract.as_json(),
                "status": "queued",
                "attempts": 1,
                "execute_after": due,
                "origin_message_id": origin,
                "approval_message_id": None,
                "created_at": created_at + timedelta(seconds=ordinal),
                "decided_at": None,
                "completed_at": None,
                "result": {
                    "creation_receipt": {
                        "action_id": str(identifier),
                        "execute_after": due.isoformat(),
                        "arguments_digest": contract.input_digest,
                        "recorded_at": created_at.isoformat(),
                    },
                    "wake_outcome": None,
                },
            }
        )
    executing_id = uuid4()
    arguments = {"value": "synthetic interrupted effect"}
    contract = _contract(arguments, (origin,))
    rows.append(
        {
            "id": executing_id,
            "tool_name": "synthetic.write",
            "arguments": arguments,
            "execution_contract": contract.as_json(),
            "status": "executing",
            "attempts": 1,
            "execute_after": None,
            "origin_message_id": origin,
            "approval_message_id": None,
            "created_at": created_at + timedelta(seconds=102),
            "decided_at": None,
            "completed_at": None,
            "result": {
                "type": "action_recovery_v1",
                "actual_external_attempts": 1,
                "reconciliation_basis": None,
            },
        }
    )
    async with engine.begin() as connection:
        await connection.execute(insert(action), rows)

    candidates = await store.recovery_candidates(limit=1)

    assert tuple(value.id for value in candidates) == (executing_id,)
    resolved_at = datetime.now(UTC)
    async with engine.begin() as connection:
        for row in rows[:-1]:
            result = cast(dict[str, object], row["result"])
            result["wake_outcome"] = {
                "type": "failed",
                "reason_code": "synthetic_cleanup",
                "recorded_at": resolved_at.isoformat(),
            }
        await connection.execute(
            update(action)
            .where(action.c.id.in_(future_ids))
            .values(
                status="failed",
                completed_at=resolved_at,
                result=action.c.result.op("||")(
                    {
                        "wake_outcome": {
                            "type": "failed",
                            "reason_code": "synthetic_cleanup",
                            "recorded_at": resolved_at.isoformat(),
                        }
                    }
                ),
            )
        )
        await connection.execute(
            insert(message),
            tuple(
                {
                    "id": uuid4(),
                    "role": "host",
                    "text": "Synthetic completed schedule.",
                    "source": "action",
                    "source_conversation_id": "synthetic-recovery-channel",
                    "source_message_id": f"{identifier}:failed",
                    "created_at": resolved_at,
                    "processed_at": resolved_at,
                    "processing_attempts": 0,
                    "processing_parked_at": None,
                    "remembered_at": None,
                    "trace": {},
                }
                for identifier in future_ids
            ),
        )
    await store.resolve_reconciliation(
        action_id=executing_id,
        status="failed",
        result={"type": "Failure", "error": {"type": "BudgetExceeded"}},
    )
    await store.finish_recovered_origin(
        action_id=executing_id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic interrupted effect failed.",
    )
    await _mark_resolution_processed(engine, (executing_id,))


@postgres
async def test_reported_terminal_page_does_not_starve_older_unreported_action(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    origin = await _owner(engine)
    base = datetime(2099, 1, 1, tzinfo=UTC)
    failure = {"type": "Failure", "error": {"type": "BudgetExceeded"}}
    rows: list[dict[str, object]] = []
    unreported_id = uuid4()
    arguments = {"value": "old unreported"}
    rows.append(
        {
            "id": unreported_id,
            "tool_name": "synthetic.write",
            "arguments": arguments,
            "execution_contract": _contract(arguments, (origin,)).as_json(),
            "status": "failed",
            "attempts": 1,
            "execute_after": None,
            "origin_message_id": origin,
            "approval_message_id": None,
            "created_at": base - timedelta(seconds=1),
            "decided_at": None,
            "completed_at": base,
            "result": failure,
        }
    )
    reported_ids: list[UUID] = []
    for ordinal in range(101):
        identifier = uuid4()
        reported_ids.append(identifier)
        item_arguments = {"value": f"reported {ordinal}"}
        rows.append(
            {
                "id": identifier,
                "tool_name": "synthetic.write",
                "arguments": item_arguments,
                "execution_contract": _contract(item_arguments, (origin,)).as_json(),
                "status": "failed",
                "attempts": 1,
                "execute_after": None,
                "origin_message_id": origin,
                "approval_message_id": None,
                "created_at": base + timedelta(seconds=ordinal + 1),
                "decided_at": None,
                "completed_at": base + timedelta(seconds=ordinal + 2),
                "result": failure,
            }
        )
    async with engine.begin() as connection:
        await connection.execute(insert(action), rows)
        await connection.execute(
            insert(message),
            tuple(
                {
                    "id": uuid4(),
                    "role": "host",
                    "text": "Synthetic action already reported.",
                    "source": "action",
                    "source_conversation_id": "synthetic-recovery-channel",
                    "source_message_id": f"{identifier}:failed",
                    "created_at": base,
                    "processed_at": base,
                    "processing_attempts": 0,
                    "processing_parked_at": None,
                    "remembered_at": None,
                    "trace": {},
                }
                for identifier in reported_ids
            ),
        )

    terminals = await store.unreported_terminal(
        source_conversation_id="synthetic-recovery-channel",
        limit=1,
    )

    assert tuple(value.id for value in terminals) == (unreported_id,)
    await store.finish_recovered_origin(
        action_id=unreported_id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic old action failed.",
    )
    await _mark_resolution_processed(engine, (unreported_id,))


@postgres
async def test_same_claim_actions_reconcile_before_atomic_union_settlement(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    first_input = await _owner(engine, created_at=NOW)
    second_input = await _owner(engine, created_at=NOW + timedelta(seconds=1))
    claim_id = "synthetic-shared-claim"
    binding, plan = _gmail_plan()
    first = await _executing_gmail_action(
        store,
        binding,
        plan,
        (first_input,),
        claim_id=claim_id,
        model_step_ordinal=1,
    )
    second = await _executing_gmail_action(
        store,
        binding,
        plan,
        (first_input, second_input),
        claim_id=claim_id,
        model_step_ordinal=2,
    )
    google = _GoogleReconciler(
        ReconciliationResult("succeeded", "synthetic exact match", _gmail_success()),
        engine=engine,
        pending_input_ids=(first_input, second_input),
    )

    recovered = await ActionRecovery(
        actions=store,
        google_write=cast("Any", google),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    ).recover()

    assert recovered == 2
    assert set(google.calls) == {first.id, second.id}
    async with engine.connect() as connection:
        inputs = (
            (
                await connection.execute(
                    select(message).where(message.c.id.in_((first_input, second_input)))
                )
            )
            .mappings()
            .all()
        )
        resolutions = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id.in_(
                            (f"{first.id}:succeeded", f"{second.id}:succeeded")
                        ),
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(resolutions) == 2
    expected = {
        (str(first.id), "succeeded"),
        (str(second.id), "succeeded"),
    }
    for row in inputs:
        assert row["processed_at"] is not None
        assert row["trace"]["settlement"] == {
            "run_id": f"action-recovery:{claim_id}",
            "through_checkpoint": str(second_input),
            "conclusion_message_id": None,
            "conclusion_kind": "suspension",
            "outcome": "system",
        }
        traced = row["trace"]["action_recovery"]["resolutions"]
        assert {(item["action_id"], item["status"]) for item in traced} == expected
        assert row["trace"]["action_recovery"]["claim_id"] == claim_id
        assert row["trace"]["action_recovery"]["through_checkpoint"] == str(
            second_input
        )
    for row in resolutions:
        context = _resolution_context(cast(str, row["text"]))
        assert set(context) == {
            "type",
            "action_id",
            "tool_name",
            "arguments",
            "status",
            "result",
        }
        assert context["type"] == "action_resolution_context_v1"
        assert context["tool_name"] == "gmail.create_draft"
        assert context["arguments"] == _gmail_arguments()
        assert context["status"] == "succeeded"
        assert context["result"] == {
            "type": "Success",
            "value": _gmail_success().model_dump(mode="json"),
        }
    await _mark_resolution_processed(engine, (first.id, second.id))


@postgres
async def test_reconciliation_only_recovery_never_enters_a_queued_write(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    queued_owner = await _owner(engine, created_at=NOW)
    executing_owner = await _owner(engine, created_at=NOW + timedelta(seconds=1))
    binding, plan = _gmail_plan()
    arguments = _gmail_arguments()
    queued = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=_contract(
            arguments,
            (queued_owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        ),
        origin_message_id=queued_owner,
    )
    executing = await _executing_gmail_action(
        store,
        binding,
        plan,
        (executing_owner,),
    )
    google = _GoogleReconciler(
        ReconciliationResult("succeeded", "synthetic exact match", _gmail_success())
    )
    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", google),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )

    assert await recovery.recover(allow_queued_execution=False) == 1
    assert await recovery.recover(allow_queued_execution=False) == 0
    untouched = await store.get(queued.id)
    resolved = await store.get(executing.id)
    assert untouched is not None
    assert untouched.status == "queued"
    assert untouched.attempts == 0
    assert untouched.result is None
    assert resolved is not None and resolved.status == "succeeded"
    assert google.calls == [executing.id]
    async with engine.connect() as connection:
        queued_processed, executing_processed = tuple(
            (
                await connection.execute(
                    select(message.c.processed_at)
                    .where(message.c.id.in_((queued_owner, executing_owner)))
                    .order_by(message.c.created_at, message.c.id)
                )
            ).scalars()
        )
        resolution_count = await connection.scalar(
            select(func.count(message.c.id)).where(
                message.c.source == "action",
                message.c.source_message_id == f"{executing.id}:succeeded",
            )
        )
    assert queued_processed is None
    assert executing_processed is not None
    assert resolution_count == 1

    await store.cancel_nonexecuting(
        action_id=queued.id,
        result={
            "type": "action_cancelled_v1",
            "reason_code": "synthetic_cleanup",
        },
    )
    await store.finish_recovered_origin(
        action_id=queued.id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic queued recovery cleanup.",
    )
    await _mark_resolution_processed(engine, (queued.id, executing.id))


@postgres
async def test_reconciliation_only_leaves_zero_attempt_evidence_executing(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    arguments = _gmail_arguments()
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=_contract(
            arguments,
            (owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        ),
        origin_message_id=owner,
    )
    await ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=4,
    ).dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    google = _GoogleReconciler(ReconciliationResult("uncertain", "unused"))
    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", google),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )

    assert await recovery.recover(allow_queued_execution=False) == 0
    dormant = await store.get(stored.id)
    assert dormant is not None
    assert dormant.status == "executing"
    assert dormant.attempts == 1
    assert dormant.recovered_external_attempts == 0
    assert google.calls == []

    await store.resolve_reconciliation(
        action_id=stored.id,
        status="failed",
        result={"type": "Failure", "error": {"type": "BudgetExceeded"}},
    )
    await store.finish_recovered_origin(
        action_id=stored.id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic zero-evidence recovery cleanup.",
    )
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_gmail_create_absence_is_terminal_uncertain_without_repeat(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    stored = await _executing_gmail_action(store, binding, plan, (owner,))
    google = _GoogleReconciler(ReconciliationResult("absent", "proved absent"))
    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", google),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )

    assert await recovery.recover(allow_queued_execution=False) == 1
    terminal = await store.get(stored.id)
    assert terminal is not None
    assert terminal.status == "uncertain"
    assert terminal.attempts == 1
    assert terminal.result is not None
    assert terminal.result["evidence_code"] == (
        "gmail-create-absence-is-not-repeat-safe"
    )
    assert google.calls == [stored.id]
    assert await recovery.recover(allow_queued_execution=False) == 0
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_gmail_update_proved_absence_permits_one_safe_repeat(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    provider = _SuccessfulUpdateProvider()
    catalog = ToolCatalog.compose((gmail_write_family(cast("Any", provider)),))
    tool_id = ToolId("gmail.update_draft")
    profile = CapabilityProfile(
        ProfileId("gmail_update_proved_absence"),
        (ToolGrant(tool_id, None),),
        RunLimits(1, 4, 524_288, 131_072, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    binding = catalog.binding(tool_id)
    replacement = GmailContent(
        to=(Mailbox(name=None, address="owner@example.invalid"),),
        cc=(),
        bcc=(),
        subject="Synthetic replacement",
        body_text="Synthetic replacement body",
        reply_to=None,
    )
    value = GmailUpdateDraftInput(
        draft_id="synthetic-draft",
        expected_content_digest="b" * 64,
        replacement=replacement,
    )
    arguments = value.model_dump(mode="json")
    stored = await store.insert_automatic(
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=_contract(
            arguments,
            (owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        ),
        origin_message_id=owner,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=4,
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    await store.stage_external_attempts(action_id=stored.id, actual_external_attempts=1)
    await store.stage_gmail_update_basis(
        action_id=stored.id,
        draft_id=value.draft_id,
        thread_id="synthetic-thread",
        jarvis_effect_id="a" * 64,
        old_content_digest=value.expected_content_digest,
    )
    google = _AbsentUpdateReconciler()

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", google),
            plan=plan,
            source_conversation_id="synthetic-recovery-channel",
        ).recover()
        == 1
    )

    terminal = await store.get(stored.id)
    assert terminal is not None
    assert terminal.status == "succeeded"
    assert terminal.attempts == 2
    assert google.calls == 1
    assert provider.effects == [stored.id]
    assert provider.budgets == [WriteAttemptBudget(1, 3)]
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_recovered_action_batch_rejects_divergent_same_claim_lineage(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    first_input = await _owner(engine, created_at=NOW)
    second_input = await _owner(engine, created_at=NOW + timedelta(seconds=1))
    binding, plan = _gmail_plan()
    claim_id = "synthetic-divergent-claim"
    first = await _executing_gmail_action(
        store,
        binding,
        plan,
        (first_input,),
        claim_id=claim_id,
        model_step_ordinal=1,
    )
    second = await _executing_gmail_action(
        store,
        binding,
        plan,
        (second_input,),
        claim_id=claim_id,
        model_step_ordinal=2,
    )
    for stored in (first, second):
        await store.resolve_reconciliation(
            action_id=stored.id,
            status="succeeded",
            result={
                "type": "Success",
                "value": _gmail_success().model_dump(mode="json"),
            },
        )

    with pytest.raises(ActionPersistenceDefect, match="incompatible input lineage"):
        await store.finish_recovered_origins(
            reports=((first.id, "Synthetic first."), (second.id, "Synthetic second.")),
            source_conversation_id="synthetic-recovery-channel",
        )
    async with engine.connect() as connection:
        processed = tuple(
            (
                await connection.execute(
                    select(message.c.processed_at).where(
                        message.c.id.in_((first_input, second_input))
                    )
                )
            ).scalars()
        )
        resolution_count = await connection.scalar(
            select(func.count(message.c.id)).where(
                message.c.source == "action",
                message.c.source_message_id.in_(
                    (f"{first.id}:succeeded", f"{second.id}:succeeded")
                ),
            )
        )
    assert processed == (None, None)
    assert resolution_count == 0
    cleanup_at = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(message.c.id.in_((first_input, second_input)))
            .values(processed_at=cleanup_at)
        )
        await connection.execute(
            insert(message),
            tuple(
                {
                    "id": uuid4(),
                    "role": "host",
                    "text": "Synthetic divergent-lineage cleanup.",
                    "source": "action",
                    "source_conversation_id": "synthetic-recovery-channel",
                    "source_message_id": f"{stored.id}:succeeded",
                    "created_at": cleanup_at,
                    "processed_at": cleanup_at,
                    "processing_attempts": 0,
                    "processing_parked_at": None,
                    "remembered_at": None,
                    "trace": {},
                }
                for stored in (first, second)
            ),
        )


@postgres
async def test_later_uncertain_to_success_transition_gets_its_own_resolution(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    stored = await _executing_gmail_action(store, binding, plan, (owner,))
    recovery = ActionRecovery(
        actions=store,
        google_write=cast(
            "Any",
            _GoogleReconciler(ReconciliationResult("uncertain", "ambiguous")),
        ),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )
    assert await recovery.recover() == 1
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="succeeded",
        result={
            "type": "Success",
            "value": _gmail_success().model_dump(mode="json"),
        },
    )

    assert await recovery.recover() == 1
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(message.c.source_message_id, message.c.text).where(
                    message.c.source == "action",
                    message.c.source_message_id.in_(
                        (f"{stored.id}:uncertain", f"{stored.id}:succeeded")
                    ),
                )
            )
        ).all()
    source_ids = {row.source_message_id for row in rows}
    succeeded_text = next(
        cast(str, row.text)
        for row in rows
        if row.source_message_id == f"{stored.id}:succeeded"
    )
    safe_succeeded = succeeded_text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)[0]
    assert (
        'Safe result: {"content_digest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
        in safe_succeeded
    )
    assert '"draft_id":"synthetic-draft"' in safe_succeeded
    assert '"message_id":"synthetic-message"' in safe_succeeded
    assert '"thread_id":"synthetic-thread"' in safe_succeeded
    assert source_ids == {f"{stored.id}:uncertain", f"{stored.id}:succeeded"}
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_uncertain_resolution_keeps_full_arguments_but_safe_fallback_is_bounded(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    private_marker = "SYNTHETIC-PRIVATE-BODY-"
    arguments = GmailCreateDraftInput(
        content=GmailContent(
            to=(Mailbox(name=None, address="owner@example.invalid"),),
            cc=(),
            bcc=(),
            subject="Synthetic maximum action resolution",
            body_text=private_marker + "x" * (100_000 - len(private_marker)),
            reply_to=None,
        )
    ).model_dump(mode="json")
    contract = _contract(
        arguments,
        (owner,),
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=owner,
    )
    await ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=4,
    ).dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    evidence = "u" * 256
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="uncertain",
        result={
            "type": "action_uncertainty_v1",
            "evidence_code": evidence,
            "recorded_at": NOW.isoformat(),
        },
    )
    recovery = ActionRecovery(
        actions=store,
        google_write=cast(
            "Any",
            _GoogleReconciler(ReconciliationResult("uncertain", "unused")),
        ),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )

    assert await recovery.recover() == 1
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{stored.id}:uncertain",
                    )
                )
            )
            .mappings()
            .one()
        )
    waking = await MessageStore(engine).message_by_id(cast(UUID, row["id"]))
    assert waking is not None
    full_text = cast(str, row["text"])
    safe_text = host_safe_text(waking)
    context = _resolution_context(full_text)
    assert private_marker in full_text
    assert private_marker not in safe_text
    assert f"Action ID: {stored.id}" in safe_text
    assert "Tool: gmail.create_draft" in safe_text
    assert "Status: uncertain" in safe_text
    assert evidence in safe_text
    assert 'Safe result: {"evidence_code":"' + evidence in safe_text
    assert "inspect the current provider state" in safe_text
    assert len(safe_text) <= 1_024
    assert len("Action update: " + safe_text) <= 2_000
    assert len(full_text.encode()) <= 262_144
    assert context["arguments"] == arguments
    assert context["status"] == "uncertain"
    assert context["result"] == {
        "type": "action_uncertainty_v1",
        "evidence_code": evidence,
        "recorded_at": NOW.isoformat(),
    }
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_failed_resolution_excludes_private_diagnostics_from_safe_result(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    stored = await _executing_gmail_action(store, binding, plan, (owner,))
    private_diagnostic = "SYNTHETIC-PRIVATE-DIAGNOSTIC"
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="failed",
        result={
            "type": "Failure",
            "error": {
                "type": "BudgetExceeded",
                "diagnostic": private_diagnostic,
            },
        },
    )

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", object()),
            plan=plan,
            source_conversation_id="synthetic-recovery-channel",
        ).recover()
        == 1
    )
    async with engine.connect() as connection:
        resolution_text = cast(
            str,
            await connection.scalar(
                select(message.c.text).where(
                    message.c.source == "action",
                    message.c.source_message_id == f"{stored.id}:failed",
                )
            ),
        )
    safe_text = resolution_text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)[0]
    context = _resolution_context(resolution_text)
    assert private_diagnostic not in safe_text
    assert private_diagnostic not in resolution_text
    assert context["arguments"] == stored.arguments
    assert context["status"] == "failed"
    assert context["result"] == {
        "type": "Failure",
        "error": {"type": "BudgetExceeded"},
    }
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_suspended_write_after_action_input_preserves_prior_visibility(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    messages = MessageStore(engine)
    conversation = f"synthetic-host-suspension-{uuid4()}"
    owner = await _owner(engine, source_conversation_id=conversation)
    prior_action_id = uuid4()
    prior_resolution_id = uuid4()
    private_marker = "SYNTHETIC-PRIVATE-PRIOR-ARGUMENT"
    prior_safe_text = (
        f"Action ID: {prior_action_id}\n"
        "Tool: gmail.create_draft\n"
        "Status: succeeded\n"
        "Evidence: Validated provider receipt."
    )
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=prior_resolution_id,
                role="host",
                text=(
                    prior_safe_text
                    + ACTION_MODEL_CONTEXT_SEPARATOR
                    + json.dumps({"body": private_marker})
                ),
                source="action",
                source_conversation_id=conversation,
                source_message_id=f"{prior_action_id}:succeeded",
                created_at=NOW + timedelta(seconds=1),
                processed_at=None,
                processing_attempts=0,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )
    binding, plan = _gmail_plan()
    checkpoint = PostgresInputCheckpoint(
        store=messages,
        thread_id=ThreadId(conversation),
        run_id=RunId(f"synthetic-host-suspension-{uuid4()}"),
        interactive_plan=plan,
        scheduled_wake_plan=plan,
        maximum_batch_size=10,
        maximum_attempts=3,
        turn_evidence=TurnEvidence(),
    )
    claimed = await checkpoint.claim(
        ThreadId(conversation),
        OwnerToken(f"synthetic-host-owner-{uuid4()}"),
    )
    assert isinstance(claimed, ClaimAcquired)
    input_ids = tuple(UUID(str(value.input_id)) for value in claimed.claim.inputs)
    assert input_ids == (owner, prior_resolution_id)
    arguments = _gmail_arguments()
    contract = _contract(
        arguments,
        input_ids,
        supporting_owner_ids=(owner,),
        claim_id=str(claimed.claim.claim_id),
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=owner,
    )
    await ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=4,
    ).dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="succeeded",
        result={
            "type": "Success",
            "value": _gmail_success().model_dump(mode="json"),
        },
    )
    await checkpoint.settle(
        claimed.claim,
        claimed.claim.through_checkpoint,
        SuspensionConclusion(HostRef(str(stored.id)), WaitingFor.system),
    )

    async with engine.connect() as connection:
        settled = (
            (
                await connection.execute(
                    select(message).where(message.c.id.in_(input_ids))
                )
            )
            .mappings()
            .all()
        )
        fallback = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.role == "assistant",
                        message.c.text == "Action update: " + prior_safe_text,
                    )
                )
            )
            .mappings()
            .one()
        )
    assert private_marker not in fallback["text"]
    assert all(
        row["trace"]["settlement"]["conclusion_kind"] == "suspension" for row in settled
    )
    assert all(row["trace"]["settlement"]["outcome"] == "system" for row in settled)
    assert all(
        row["trace"]["settlement"]["conclusion_message_id"] == str(fallback["id"])
        for row in settled
    )

    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", object()),
        plan=plan,
        source_conversation_id=conversation,
    )
    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    async with engine.connect() as connection:
        next_resolution = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{stored.id}:succeeded",
                    )
                )
            )
            .mappings()
            .one()
        )
        recovered_lineage = (
            (
                await connection.execute(
                    select(message).where(message.c.id.in_(input_ids))
                )
            )
            .mappings()
            .all()
        )
    assert next_resolution["processed_at"] is None
    assert all(
        row["trace"]["action_recovery"]["resolutions"]
        == [
            {
                "action_id": str(stored.id),
                "status": "succeeded",
                "resolution_message_id": str(next_resolution["id"]),
            }
        ]
        for row in recovered_lineage
    )
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_queued_gmail_recovery_does_not_repeat_after_absence(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    provider = _AlwaysAmbiguousProvider(store)
    catalog = ToolCatalog.compose((gmail_write_family(cast("Any", provider)),))
    tool_id = ToolId("gmail.create_draft")
    profile = CapabilityProfile(
        ProfileId("gmail_absence_is_uncertain"),
        (ToolGrant(tool_id, None),),
        RunLimits(1, 4, 524_288, 131_072, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    binding = catalog.binding(tool_id)
    owner = await _owner(engine)
    arguments = _gmail_arguments()
    stored = await store.insert_automatic(
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=_contract(
            arguments,
            (owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        ),
        origin_message_id=owner,
    )
    google = _SequenceGoogleReconciler(
        (ReconciliationResult("absent", "invalid Gmail absence"),)
    )

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", google),
            plan=plan,
            source_conversation_id="synthetic-recovery-channel",
        ).recover()
        == 1
    )

    terminal = await store.get(stored.id)
    assert terminal is not None
    assert terminal.status == "uncertain"
    assert terminal.attempts == 1
    assert provider.effects == [stored.id]
    assert provider.budgets == [WriteAttemptBudget(0, 4)]
    assert google.calls == [stored.id]
    assert not google.results
    assert terminal.result is not None
    assert terminal.result["type"] == "action_uncertainty_v1"
    assert terminal.result["evidence_code"] == (
        "gmail-create-absence-is-not-repeat-safe"
    )
    await _mark_resolution_processed(engine, (stored.id,))


@pytest.mark.parametrize(
    ("conclusion_kind", "outcome", "with_control"),
    (
        ("suspension", "system", False),
        ("stopped", "cancelled", False),
        ("stopped", "owner_stop", True),
    ),
)
@postgres
async def test_processed_stranded_action_outcome_gets_one_resolution(
    engine: AsyncEngine,
    conclusion_kind: str,
    outcome: str,
    with_control: bool,
) -> None:
    store = ActionStore(engine)
    messages = MessageStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    stored = await _executing_gmail_action(store, binding, plan, (owner,))
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="succeeded",
        result={
            "type": "Success",
            "value": _gmail_success().model_dump(mode="json"),
        },
    )
    consumed = (owner,)
    through = owner
    if with_control:
        control = await _owner(
            engine,
            created_at=NOW + timedelta(seconds=1),
            text="stop",
        )
        consumed = (owner, control)
        through = control
    settlement = SettlementTrace(
        run_id=f"synthetic-{conclusion_kind}-{outcome}",
        through_checkpoint=str(through),
        conclusion_kind=conclusion_kind,
        outcome=outcome,
    )
    conclusion_id = uuid4() if with_control else None
    await messages.settle(
        consumed_message_ids=consumed,
        source_conversation_id="synthetic-recovery-channel",
        trace=settlement,
        conclusion_text="Synthetic stopped conclusion." if with_control else None,
        conclusion_message_id=conclusion_id,
    )
    recovery = ActionRecovery(
        actions=store,
        google_write=cast(
            "Any",
            _GoogleReconciler(ReconciliationResult("uncertain", "unused")),
        ),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )

    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    async with engine.connect() as connection:
        resolution = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{stored.id}:succeeded",
                    )
                )
            )
            .mappings()
            .one()
        )
        owner_trace = cast(
            "dict[str, object]",
            await connection.scalar(
                select(message.c.trace).where(message.c.id == owner)
            ),
        )
    assert owner_trace["settlement"] == settlement.as_json(conclusion_id)
    recovery_trace = cast("dict[str, object]", owner_trace["action_recovery"])
    assert recovery_trace["resolutions"] == [
        {
            "action_id": str(stored.id),
            "status": "succeeded",
            "resolution_message_id": str(resolution["id"]),
        }
    ]
    await _mark_resolution_processed(engine, (stored.id,))


@pytest.mark.parametrize(
    ("conclusion_kind", "outcome", "conclusion_text"),
    (
        ("conversation", "answered", "Synthetic owner-visible result."),
        ("silent", "silent", None),
    ),
)
@postgres
async def test_completed_live_conversation_does_not_create_recovery_resolution(
    engine: AsyncEngine,
    conclusion_kind: str,
    outcome: str,
    conclusion_text: str | None,
) -> None:
    store = ActionStore(engine)
    messages = MessageStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    stored = await _executing_gmail_action(store, binding, plan, (owner,))
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="succeeded",
        result={
            "type": "Success",
            "value": _gmail_success().model_dump(mode="json"),
        },
    )
    conclusion_id = uuid4() if conclusion_text is not None else None
    await messages.settle(
        consumed_message_ids=(owner,),
        source_conversation_id="synthetic-recovery-channel",
        trace=SettlementTrace(
            run_id=f"synthetic-conversation-{outcome}",
            through_checkpoint=str(owner),
            conclusion_kind=conclusion_kind,
            outcome=outcome,
        ),
        conclusion_text=conclusion_text,
        conclusion_message_id=conclusion_id,
    )

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast(
                "Any",
                _GoogleReconciler(ReconciliationResult("uncertain", "unused")),
            ),
            plan=plan,
            source_conversation_id="synthetic-recovery-channel",
        ).recover()
        == 0
    )
    async with engine.connect() as connection:
        resolution_count = (
            await connection.execute(
                select(func.count())
                .select_from(message)
                .where(
                    message.c.source == "action",
                    message.c.source_message_id == f"{stored.id}:succeeded",
                )
            )
        ).scalar_one()
    assert resolution_count == 0


@postgres
async def test_unsupported_queued_action_is_cancelled_and_reported(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    _, plan = _gmail_plan()
    arguments = {"value": "unsupported persisted write"}
    stored = await store.insert_automatic(
        tool_name=ToolId("unsupported.write"),
        arguments=arguments,
        execution_contract=_contract(
            arguments,
            (owner,),
            plan_revision=plan.plan_revision,
        ),
        origin_message_id=owner,
    )

    recovered = await ActionRecovery(
        actions=store,
        google_write=cast(
            "Any",
            _GoogleReconciler(ReconciliationResult("uncertain", "unused")),
        ),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    ).recover()

    assert recovered == 1
    resolved = await store.get(stored.id)
    assert resolved is not None
    assert resolved.status == "cancelled"
    assert resolved.result == {
        "type": "action_cancelled_v1",
        "reason_code": "incompatible_execution_contract",
    }
    async with engine.connect() as connection:
        resolution = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{stored.id}:cancelled",
                    )
                )
            )
            .mappings()
            .one()
        )
    assert resolution["role"] == "host"
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_schedule_declared_failure_replays_from_terminal_action(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    family = schedule_family(store)
    binding = family.bindings[0]
    catalog = ToolCatalog.compose((family,))
    profile = CapabilityProfile(
        ProfileId("action_recovery_schedule_failure"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 5.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    execute_after = NOW - timedelta(minutes=1)
    arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": execute_after.isoformat(),
            "instruction": "Synthetic already-due reminder",
        }
    }
    contract = _contract(
        arguments,
        (owner,),
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=owner,
        execute_after=execute_after,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=2,
    )
    budgets = InMemoryBudgetState(RunLimits(1, 2, 16_384, 4_096, 1, 5.0))
    reservation = Reservation(
        calls=1,
        input_bytes=256,
        max_attempts=2,
        max_output_bytes=4_096,
    )
    assert await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=reservation,
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    failure = {
        "type": "Failure",
        "error": {"type": "ExecuteAfterNotFuture"},
    }
    await recorder.terminalize_and_settle(
        position=stored.position,
        budgets=budgets,
        result=failure,
        settlement=Settlement(
            actual_attempts=0,
            actual_output_bytes=len(canonical_json_bytes(failure)),
        ),
    )
    terminals = await store.unreported_terminal(
        source_conversation_id="synthetic-recovery-channel"
    )
    assert stored.id in {value.id for value in terminals}

    recovered = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=2,
    )
    replay = await recovered.occupy(
        position=stored.position,
        tool_id=binding.spec.id,
        tool_contract_revision=binding.spec.tool_contract_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
        input_digest=contract.input_digest,
        replay_policy=ReplayPolicy.ReDispatchable,
    )

    assert replay.terminal_result == failure
    await store.finish_recovered_origin(
        action_id=stored.id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic schedule request failed.",
    )
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_completed_schedule_creation_closes_owner_without_replaying_turn(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    family = schedule_family(store)
    binding = family.bindings[0]
    catalog = ToolCatalog.compose((family,))
    profile = CapabilityProfile(
        ProfileId("action_recovery_schedule_creation"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 5.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    due = datetime.now(UTC) + timedelta(minutes=5)
    arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": due.isoformat(),
            "instruction": "Synthetic recovered reminder",
        }
    }
    contract = _contract(
        arguments,
        (owner,),
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=owner,
        execute_after=due,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=2,
    )
    budgets = InMemoryBudgetState(RunLimits(1, 2, 16_384, 4_096, 1, 5.0))
    assert await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=Reservation(1, 256, 2, 4_096),
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    result = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "created",
                "action_id": str(stored.id),
                "execute_after": due.isoformat(),
                "arguments_digest": contract.input_digest,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        },
    }
    await recorder.terminalize_and_settle(
        position=stored.position,
        budgets=budgets,
        result=result,
        settlement=Settlement(0, len(canonical_json_bytes(result))),
    )
    recovery = ActionRecovery(
        actions=store,
        google_write=cast(
            "Any",
            _GoogleReconciler(ReconciliationResult("uncertain", "unused")),
        ),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
    )

    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    queued = await store.get(stored.id)
    assert queued is not None and queued.status == "queued"
    async with engine.connect() as connection:
        owner_row = (
            (await connection.execute(select(message).where(message.c.id == owner)))
            .mappings()
            .one()
        )
        resolutions = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{stored.id}:queued",
                    )
                )
            )
            .mappings()
            .all()
        )
    assert owner_row["processed_at"] is not None
    assert len(resolutions) == 1
    assert "Tool: schedule.wake" in resolutions[0]["text"]
    assert "Status: queued" in resolutions[0]["text"]
    safe_resolution = resolutions[0]["text"].partition(ACTION_MODEL_CONTEXT_SEPARATOR)[
        0
    ]
    assert 'Safe result: {"creation_receipt":{' in safe_resolution
    assert f'"action_id":"{stored.id}"' in safe_resolution
    assert f'"execute_after":"{due.isoformat()}"' in safe_resolution
    assert '"wake_outcome":null' in safe_resolution
    traced = owner_row["trace"]["action_recovery"]["resolutions"]
    assert [(item["action_id"], item["status"]) for item in traced] == [
        (str(stored.id), "queued")
    ]
    claimed = await store.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
        now=due,
    )
    assert claimed is not None
    assert claimed.message_inserted
    await store.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_cleanup",
            "recorded_at": (due + timedelta(seconds=1)).isoformat(),
        },
    )
    assert await recovery.recover() == 0
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(message.c.id == claimed.waking_message_id)
            .values(processed_at=due + timedelta(seconds=1))
        )
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_calendar_success_fallback_has_only_safe_snapshot_evidence(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    private_marker = "SYNTHETIC-PRIVATE-CALENDAR-PROSE"
    arguments: dict[str, object] = {
        "calendar_id": "owner@example.invalid",
        "event": {"description": private_marker},
    }
    contract = _contract(arguments, (owner,))
    stored = await store.insert_automatic(
        tool_name=ToolId("calendar.create_event"),
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=owner,
    )
    await ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=contract.implementation_revision,
        max_external_attempts=2,
    ).dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    result: dict[str, object] = {
        "type": "Success",
        "value": {
            "event": {
                "calendar_id": "owner@example.invalid",
                "event_id": "synthetic-event",
                "etag": '"synthetic-etag"',
                "status": "confirmed",
                "writable": {"description": private_marker},
                "organizer": {
                    "name": "Synthetic Private Organizer",
                    "address": "owner@example.invalid",
                },
                "updated_at": NOW.isoformat(),
            },
            "created_at": NOW.isoformat(),
        },
    }
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="succeeded",
        result=result,
    )
    binding, plan = _gmail_plan()
    del binding
    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", object()),
            plan=plan,
            source_conversation_id="synthetic-recovery-channel",
        ).recover()
        == 1
    )
    async with engine.connect() as connection:
        resolution_text = cast(
            str,
            await connection.scalar(
                select(message.c.text).where(
                    message.c.source == "action",
                    message.c.source_message_id == f"{stored.id}:succeeded",
                )
            ),
        )
    safe_text = resolution_text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)[0]
    assert '"calendar_id":"owner@example.invalid"' in safe_text
    assert '"event_id":"synthetic-event"' in safe_text
    assert '"etag":"\\"synthetic-etag\\""' in safe_text
    assert '"status":"confirmed"' in safe_text
    assert private_marker not in safe_text
    assert "Synthetic Private Organizer" not in safe_text
    context = _resolution_context(resolution_text)
    assert context["arguments"] == arguments
    assert context["result"] == result
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_cancelled_receipt_backed_schedule_is_not_reported_again(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    due = datetime.now(UTC) + timedelta(hours=1)
    arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": due.isoformat(),
            "instruction": "Synthetic cancelled reminder",
        }
    }
    contract = _contract(arguments, (owner,))
    identifier = uuid4()
    cancelled_at = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(action).values(
                id=identifier,
                tool_name="schedule.wake",
                arguments=arguments,
                execution_contract=contract.as_json(),
                status="cancelled",
                attempts=1,
                execute_after=due,
                origin_message_id=owner,
                approval_message_id=None,
                created_at=NOW,
                decided_at=cancelled_at,
                completed_at=cancelled_at,
                result={
                    "creation_receipt": {
                        "action_id": str(identifier),
                        "execute_after": due.isoformat(),
                        "arguments_digest": contract.input_digest,
                        "recorded_at": NOW.isoformat(),
                    },
                    "wake_outcome": {
                        "type": "cancelled",
                        "cancellation_action_id": str(uuid4()),
                        "recorded_at": cancelled_at.isoformat(),
                    },
                },
            )
        )

    terminals = await store.unreported_terminal(
        source_conversation_id="synthetic-recovery-channel"
    )
    assert identifier not in {value.id for value in terminals}


@postgres
async def test_recovered_schedule_cancel_reloads_timer_and_keeps_later_wake(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    family = schedule_family(store)
    binding = family.bindings[0]
    catalog = ToolCatalog.compose((family,))
    profile = CapabilityProfile(
        ProfileId(f"recovered_schedule_cancel_{uuid4()}"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 5.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    first_due = datetime.now(UTC) + timedelta(hours=1)
    later_due = first_due + timedelta(hours=1)
    target_ids: list[UUID] = []
    for due in (first_due, later_due):
        owner = await _owner(engine, processed_at=NOW)
        async with engine.begin() as connection:
            await connection.execute(
                update(message)
                .where(message.c.id == owner)
                .values(
                    trace={
                        "settlement": {
                            "run_id": f"synthetic-completed:{owner}",
                            "through_checkpoint": str(owner),
                            "conclusion_message_id": str(uuid4()),
                            "conclusion_kind": "conversation",
                            "outcome": "answered",
                        }
                    }
                )
            )
        identifier = uuid4()
        arguments: dict[str, object] = {
            "request": {
                "type": "create",
                "execute_after": due.isoformat(),
                "instruction": f"Synthetic reminder at {due.isoformat()}",
            }
        }
        contract = _contract(
            arguments,
            (owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        )
        await store.insert_automatic(
            action_id=identifier,
            tool_name=binding.spec.id,
            arguments=arguments,
            execution_contract=contract,
            origin_message_id=owner,
            execute_after=due,
        )
        async with engine.begin() as connection:
            await connection.execute(
                update(action)
                .where(action.c.id == identifier)
                .values(
                    status="queued",
                    attempts=1,
                    result={
                        "creation_receipt": {
                            "action_id": str(identifier),
                            "execute_after": due.isoformat(),
                            "arguments_digest": contract.input_digest,
                            "recorded_at": NOW.isoformat(),
                        },
                        "wake_outcome": None,
                    },
                )
            )
        target_ids.append(identifier)
    cancel_owner = await _owner(engine)
    cancel_arguments: dict[str, object] = {
        "request": {
            "type": "cancel",
            "target_action_id": str(target_ids[0]),
        }
    }
    cancellation = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=cancel_arguments,
        execution_contract=_contract(
            cancel_arguments,
            (cancel_owner,),
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
        ),
        origin_message_id=cancel_owner,
    )
    timer_reloads: list[None] = []
    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", object()),
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
        schedule_changed=lambda: timer_reloads.append(None),
    )

    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    first = await store.get(target_ids[0])
    later = await store.get(target_ids[1])
    resolved_cancel = await store.get(cancellation.id)
    assert first is not None and first.status == "cancelled"
    assert later is not None and later.status == "queued"
    assert resolved_cancel is not None and resolved_cancel.status == "succeeded"
    assert await store.next_due_at() == later_due
    assert timer_reloads == [None]
    async with engine.connect() as connection:
        cancellation_text = cast(
            str,
            await connection.scalar(
                select(message.c.text).where(
                    message.c.source == "action",
                    message.c.source_message_id == f"{cancellation.id}:succeeded",
                )
            ),
        )
    safe_cancellation = cancellation_text.partition(ACTION_MODEL_CONTEXT_SEPARATOR)[0]
    assert 'Safe result: {"receipt":{"recorded_at":' in safe_cancellation
    assert '"type":"cancelled"' in safe_cancellation
    assert f'"target_action_id":"{target_ids[0]}"' in safe_cancellation
    assert '"type":"schedule_operation"' in safe_cancellation
    claimed_later = await store.claim_due_schedule(
        action_id=target_ids[1],
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
        now=later_due,
    )
    assert claimed_later is not None
    await store.finish_schedule(
        action_id=target_ids[1],
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_cleanup",
            "recorded_at": (later_due + timedelta(seconds=1)).isoformat(),
        },
    )
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(message.c.id == claimed_later.waking_message_id)
            .values(processed_at=later_due + timedelta(seconds=1))
        )
    await _mark_resolution_processed(engine, (cancellation.id,))


@postgres
async def test_reconciliation_rejects_result_status_disagreement(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    binding, plan = _gmail_plan()
    stored = await _executing_gmail_action(store, binding, plan, (owner,))
    success = {
        "type": "Success",
        "value": _gmail_success().model_dump(mode="json"),
    }
    failure = {"type": "Failure", "error": {"type": "BudgetExceeded"}}

    with pytest.raises(ValueError, match="status disagrees"):
        await store.resolve_reconciliation(
            action_id=stored.id,
            status="failed",
            result=success,
        )
    with pytest.raises(ValueError, match="status disagrees"):
        await store.resolve_reconciliation(
            action_id=stored.id,
            status="succeeded",
            result=failure,
        )
    unchanged = await store.get(stored.id)
    assert unchanged is not None and unchanged.status == "executing"
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="failed",
        result=failure,
    )
    await store.finish_recovered_origin(
        action_id=stored.id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic congruence action failed.",
    )
    await _mark_resolution_processed(engine, (stored.id,))


@postgres
async def test_due_wake_preserves_owner_requested_timezone_offset_text(
    engine: AsyncEngine,
) -> None:
    store = ActionStore(engine)
    owner = await _owner(engine)
    family = schedule_family(store)
    binding = family.bindings[0]
    catalog = ToolCatalog.compose((family,))
    profile = CapabilityProfile(
        ProfileId("offset_schedule_claim"),
        (ToolGrant(binding.spec.id, None),),
        RunLimits(1, 2, 16_384, 4_096, 1, 5.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    requested = "2026-09-07T09:30:00-07:00"
    due = datetime.fromisoformat(requested)
    arguments: dict[str, object] = {
        "request": {
            "type": "create",
            "execute_after": requested,
            "instruction": "Synthetic offset reminder",
        }
    }
    contract = _contract(
        arguments,
        (owner,),
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
    )
    stored = await store.insert_automatic(
        tool_name=binding.spec.id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=owner,
        execute_after=due,
    )
    recorder = ActionPositionRecorder(
        store=store,
        action_id=stored.id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=2,
    )
    budgets = InMemoryBudgetState(RunLimits(1, 2, 16_384, 4_096, 1, 5.0))
    reservation = Reservation(1, 256, 2, 4_096)
    assert await recorder.reserve(
        position=stored.position,
        budgets=budgets,
        reservation=reservation,
    )
    await recorder.dispatch_started(
        position=stored.position,
        replay_policy=ReplayPolicy.ReDispatchable,
    )
    result = {
        "type": "Success",
        "value": {
            "receipt": {
                "type": "created",
                "action_id": str(stored.id),
                "execute_after": requested,
                "arguments_digest": contract.input_digest,
                "recorded_at": NOW.isoformat(),
            }
        },
    }
    await recorder.terminalize_and_settle(
        position=stored.position,
        budgets=budgets,
        result=result,
        settlement=Settlement(0, len(canonical_json_bytes(result))),
    )

    claim = await store.claim_due_schedule(
        action_id=stored.id,
        plan=plan,
        source_conversation_id="synthetic-recovery-channel",
        now=due,
    )
    assert claim is not None
    async with engine.connect() as connection:
        waking_text = (
            await connection.execute(
                select(message.c.text).where(message.c.id == claim.waking_message_id)
            )
        ).scalar_one()
    assert waking_text == (
        "Requested reminder at 2026-09-07T09:30:00-07:00: Synthetic offset reminder"
    )
    finished_at = due + timedelta(seconds=1)
    await store.finish_schedule(
        action_id=stored.id,
        wake_outcome={
            "type": "failed",
            "reason_code": "synthetic_cleanup",
            "recorded_at": finished_at.isoformat(),
        },
    )
    await store.finish_recovered_origin(
        action_id=stored.id,
        source_conversation_id="synthetic-recovery-channel",
        text="Synthetic offset reminder completed.",
    )
    async with engine.begin() as connection:
        await connection.execute(
            update(message)
            .where(message.c.id == claim.waking_message_id)
            .values(processed_at=finished_at)
        )
    await _mark_resolution_processed(engine, (stored.id,))

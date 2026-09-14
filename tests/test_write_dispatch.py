from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimAcquired,
    ClaimId,
    DispatchCompleted,
    DispatchLineage,
    DispatchSuspended,
    HostInput,
    InputId,
    OwnerToken,
    RunId,
    StructuredConclusion,
    ThreadId,
    WaitingFor,
)
from llm_tools import (
    CapabilityProfile,
    HostTable,
    ProfileId,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    RunLimits,
    ToolBinding,
    ToolCatalog,
    ToolGrant,
    ToolId,
    ToolPlan,
)
from llm_tools.testing import InMemoryBudgetState
from provider_fixture import decision_key, frozen_provider, model_journal
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine
from test_agent_control import INFO, REF, cli

from jarvis.actions import ActionStore
from jarvis.agent_control import AgentController
from jarvis.agent_tools import (
    AgentError,
    AgentKeysInput,
    AgentRefInput,
    AgentSendInput,
    AgentStartInput,
    agent_family,
)
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.db import action, create_engine, message
from jarvis.definitions import build_slice5_write_gate
from jarvis.messages import MessageStore
from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder
from jarvis.terminal import TurnEvidence
from jarvis.write_connectors import (
    CalendarCurrentSnapshot,
    ReconciliationResult,
    gmail_content_digest,
    gmail_effect_id,
)
from jarvis.write_dispatch import (
    ActionRecovery,
    WriteToolDispatcher,
    action_resolution_text,
)
from jarvis.write_gate import AutomaticWriteGate, WriteGateDecision
from jarvis.write_tools import (
    CalendarEventSnapshot,
    CalendarUpdateEventInput,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    GmailSendDraftInput,
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


class _Provider:
    def __init__(self, mode: Literal["success", "cancel"] = "success") -> None:
        self.mode = mode
        self.effects: list[UUID] = []

    async def gmail_create_draft(
        self,
        value: GmailCreateDraftInput,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        del value, attempts
        self.effects.append(effect_id)
        if self.mode == "cancel":
            raise asyncio.CancelledError
        return WriteResponse(
            GmailDraftSuccess(
                draft_id="synthetic-draft",
                message_id="synthetic-message",
                thread_id="synthetic-thread",
                jarvis_effect_id="a" * 64,
                content_digest="b" * 64,
                observed_at=NOW,
            ),
            1,
        )

    async def gmail_update_draft(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))

    async def gmail_send_draft(
        self,
        value: GmailSendDraftInput,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[object]:
        del value, attempts
        self.effects.append(effect_id)
        raise AssertionError("approval-required Gmail send executed directly")

    async def calendar_create_event(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))

    async def calendar_update_event(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))

    async def calendar_delete_event(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))


class _PreflightCrashUpdateProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.store: ActionStore | None = None
        self.budgets: list[WriteAttemptBudget] = []

    async def gmail_update_draft(
        self,
        value: object,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        assert isinstance(value, GmailUpdateDraftInput)
        self.effects.append(effect_id)
        self.budgets.append(attempts)
        assert self.store is not None
        await self.store.stage_external_attempts(
            action_id=effect_id,
            actual_external_attempts=attempts.recovered_attempts + 1,
        )
        if len(self.budgets) == 1:
            raise asyncio.CancelledError
        return WriteResponse(
            GmailDraftSuccess(
                draft_id=value.draft_id,
                message_id="synthetic-message",
                thread_id="synthetic-thread",
                jarvis_effect_id="a" * 64,
                content_digest=gmail_content_digest(value.replacement),
                observed_at=NOW,
            ),
            1,
        )


class _Checkpoint:
    def __init__(self, input_id: UUID, text: str = "Create the synthetic draft."):
        self.input = HostInput(
            InputId(str(input_id)),
            PromptSections(
                (
                    PromptSection(
                        PromptSectionKind("owner_input"),
                        (),
                        PromptText(text),
                    ),
                )
            ),
            NOW,
        )

    async def automatic_write_gate_inputs(
        self, lineage: DispatchLineage
    ) -> tuple[tuple[HostInput, ...], datetime]:
        assert lineage.input_ids == (self.input.input_id,)
        return (self.input,), NOW


class _Gate:
    def __init__(self, decision: Literal["allow", "deny"], owner_id: UUID) -> None:
        self.decision: Literal["allow", "deny"] = decision
        self.owner_id = owner_id
        self.calls = 0

    async def evaluate(self, *args: object, **kwargs: object) -> WriteGateDecision:
        del args, kwargs
        self.calls += 1
        return WriteGateDecision(
            self.decision,
            (self.owner_id,) if self.decision == "allow" else (),
            None,
            "completed",
            None,
        )


class _FailingGate:
    async def evaluate(self, *args: object, **kwargs: object) -> WriteGateDecision:
        del args, kwargs
        raise RuntimeError("synthetic gate failure")


class _CancelledGate:
    async def evaluate(self, *args: object, **kwargs: object) -> WriteGateDecision:
        del args, kwargs
        raise asyncio.CancelledError


class _CancellingAllowGate(_Gate):
    async def evaluate(self, *args: object, **kwargs: object) -> WriteGateDecision:
        cancellation = kwargs["cancellation"]
        assert isinstance(cancellation, CancellationToken)
        cancellation.cancel()
        return await super().evaluate(*args, **kwargs)


class _FailingCheckpoint:
    async def automatic_write_gate_inputs(
        self, lineage: DispatchLineage
    ) -> tuple[tuple[HostInput, ...], datetime]:
        del lineage
        raise RuntimeError("synthetic checkpoint failure")


class _ActionSpy:
    def __init__(self) -> None:
        self.inserts = 0
        self.creation_id = uuid4()

    async def insert_automatic(self, **kwargs: object) -> object:
        self.inserts += 1
        raise AssertionError(kwargs)

    async def insert_awaiting_approval(self, **kwargs: object) -> object:
        self.inserts += 1
        return kwargs

    async def gmail_draft_creation_action(self, **kwargs: object) -> UUID:
        del kwargs
        return self.creation_id


class _Google:
    def __init__(
        self, reconciliation: ReconciliationResult[GmailDraftSuccess] | None = None
    ) -> None:
        self.reconciliation = reconciliation
        self.reconciliations = 0

    async def reconcile_gmail_create(
        self, value: GmailCreateDraftInput, action_id: UUID
    ) -> ReconciliationResult[GmailDraftSuccess]:
        del value, action_id
        self.reconciliations += 1
        assert self.reconciliation is not None
        return self.reconciliation

    async def calendar_current_snapshot(self, *args: object) -> object:
        raise AssertionError(args)


class _CancellingCalendarGoogle(_Google):
    def __init__(
        self,
        cancellation: CancellationToken,
        snapshot: CalendarEventSnapshot,
    ) -> None:
        super().__init__()
        self._cancellation = cancellation
        self._snapshot = snapshot

    async def calendar_current_snapshot(self, *args: object) -> object:
        assert args == (self._snapshot.calendar_id, self._snapshot.event_id)
        self._cancellation.cancel()
        return CalendarCurrentSnapshot("found", self._snapshot, 1)


def _content() -> GmailContent:
    return GmailContent(
        to=(Mailbox(name=None, address="owner@example.invalid"),),
        cc=(),
        bcc=(),
        subject="Synthetic draft",
        body_text="Synthetic body",
        reply_to=None,
    )


def _calendar_snapshot() -> CalendarEventSnapshot:
    event = CalendarWritableEvent(
        summary="Synthetic event",
        description=None,
        location=None,
        start=TimedEventTime(date_time=NOW, time_zone="UTC"),
        end=TimedEventTime(date_time=NOW + timedelta(hours=1), time_zone="UTC"),
        recurrence=(),
        attendees=(),
        use_default_reminders=True,
        reminders=(),
    )
    return CalendarEventSnapshot(
        calendar_id="owner@example.invalid",
        event_id="synthetic-event",
        etag='"synthetic-etag"',
        status="confirmed",
        writable=event,
        organizer=Mailbox(name=None, address="owner@example.invalid"),
        updated_at=NOW,
    )


def _plan(
    provider: _Provider, tool_id: ToolId
) -> tuple[ToolBinding[Any, Any, Any], Any]:
    catalog = ToolCatalog.compose((gmail_write_family(cast("Any", provider)),))
    limits = RunLimits(1, 4, 524_288, 131_072, 1, 30.0)
    profile = CapabilityProfile(
        ProfileId(f"write_dispatch_{str(tool_id).replace('.', '_')}"),
        (ToolGrant(tool_id, None),),
        limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    return catalog.binding(tool_id), plan


def _calendar_plan(
    provider: _Provider, tool_id: ToolId
) -> tuple[ToolBinding[Any, Any, Any], Any]:
    catalog = ToolCatalog.compose((calendar_write_family(cast("Any", provider)),))
    limits = RunLimits(1, 2, 524_288, 131_072, 1, 30.0)
    profile = CapabilityProfile(
        ProfileId(f"write_dispatch_{str(tool_id).replace('.', '_')}"),
        (ToolGrant(tool_id, None),),
        limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    return catalog.binding(tool_id), plan


def _lineage(owner_id: UUID) -> DispatchLineage:
    return DispatchLineage(
        ClaimId(str(uuid4())),
        Checkpoint(str(owner_id)),
        (InputId(str(owner_id)),),
        1,
        definition_fingerprint="a" * 64,
        model_decision_id=decision_key(str(ClaimId(str(uuid4()))), 1),
    )


def _dispatcher(
    *,
    checkpoint: object,
    gate: object,
    actions: object,
    google: object,
    agents: object = None,
) -> WriteToolDispatcher:
    return WriteToolDispatcher(
        checkpoint=cast("Any", checkpoint),
        gate=cast("Any", gate),
        actions=cast("Any", actions),
        google_write=cast("Any", google),
        agents=cast("AgentController", agents),
        read=ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=()),
        owner_timezone="UTC",
        source_conversation_id="synthetic-channel",
        verified_owner_only_calendar_ids=("owner@example.invalid",),
        host_secrets=(),
    )


async def _dispatch(
    dispatcher: WriteToolDispatcher,
    binding: ToolBinding[Any, Any, Any],
    plan: Any,
    owner_id: UUID,
    value: object,
    *,
    lineage: DispatchLineage | None = None,
    cancellation: CancellationToken | None = None,
) -> object:
    return await dispatcher.dispatch(
        binding=binding,
        validated_input=value,
        plan=plan,
        budgets=InMemoryBudgetState(plan.profile.run_limits),
        cancellation=cancellation or CancellationToken(),
        lineage=lineage or _lineage(owner_id),
    )


async def test_gate_denial_and_failure_create_no_action_or_effect() -> None:
    owner_id = uuid4()
    provider = _Provider()
    binding, plan = _plan(provider, ToolId("gmail.create_draft"))
    checkpoint = _Checkpoint(owner_id)

    denied_actions = _ActionSpy()
    denied = await _dispatch(
        _dispatcher(
            checkpoint=checkpoint,
            gate=_Gate("deny", owner_id),
            actions=denied_actions,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailCreateDraftInput(content=_content()),
    )
    assert isinstance(denied, DispatchCompleted)
    assert denied.result == {"type": "Failure", "error": {"type": "ToolUnavailable"}}
    assert denied_actions.inserts == 0
    assert provider.effects == []

    failed_actions = _ActionSpy()
    failed = await _dispatch(
        _dispatcher(
            checkpoint=checkpoint,
            gate=_FailingGate(),
            actions=failed_actions,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailCreateDraftInput(content=_content()),
    )
    assert isinstance(failed, DispatchCompleted)
    assert failed.result == {"type": "Failure", "error": {"type": "ToolUnavailable"}}
    assert failed_actions.inserts == 0
    assert provider.effects == []

    checkpoint_failed_actions = _ActionSpy()
    checkpoint_failed = await _dispatch(
        _dispatcher(
            checkpoint=_FailingCheckpoint(),
            gate=_Gate("allow", owner_id),
            actions=checkpoint_failed_actions,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailCreateDraftInput(content=_content()),
    )
    assert isinstance(checkpoint_failed, DispatchCompleted)
    assert checkpoint_failed.result == {
        "type": "Failure",
        "error": {"type": "ToolUnavailable"},
    }
    assert checkpoint_failed_actions.inserts == 0
    assert provider.effects == []

    cancelled_actions = _ActionSpy()
    with pytest.raises(asyncio.CancelledError):
        await _dispatch(
            _dispatcher(
                checkpoint=checkpoint,
                gate=_CancelledGate(),
                actions=cancelled_actions,
                google=_Google(),
            ),
            binding,
            plan,
            owner_id,
            GmailCreateDraftInput(content=_content()),
        )
    assert cancelled_actions.inserts == 0
    assert provider.effects == []


async def test_cancellation_after_allowed_gate_creates_no_action() -> None:
    owner_id = uuid4()
    provider = _Provider()
    binding, plan = _plan(provider, ToolId("gmail.create_draft"))
    actions = _ActionSpy()

    with pytest.raises(asyncio.CancelledError):
        await _dispatch(
            _dispatcher(
                checkpoint=_Checkpoint(owner_id),
                gate=_CancellingAllowGate("allow", owner_id),
                actions=actions,
                google=_Google(),
            ),
            binding,
            plan,
            owner_id,
            GmailCreateDraftInput(content=_content()),
        )
    assert actions.inserts == 0
    assert provider.effects == []


async def test_cancellation_after_calendar_preflight_creates_no_action() -> None:
    owner_id = uuid4()
    provider = _Provider()
    tool_id = ToolId("calendar.update_event")
    binding, plan = _calendar_plan(provider, tool_id)
    actions = _ActionSpy()
    cancellation = CancellationToken()
    snapshot = _calendar_snapshot()

    with pytest.raises(asyncio.CancelledError):
        await _dispatch(
            _dispatcher(
                checkpoint=_Checkpoint(owner_id),
                gate=_Gate("allow", owner_id),
                actions=actions,
                google=_CancellingCalendarGoogle(cancellation, snapshot),
            ),
            binding,
            plan,
            owner_id,
            CalendarUpdateEventInput(
                expected=snapshot,
                replacement=snapshot.writable,
                notify_attendees=False,
            ),
            cancellation=cancellation,
        )
    assert actions.inserts == 0
    assert provider.effects == []


@postgres
async def test_host_action_resolution_cannot_authorize_a_write(
    engine: AsyncEngine,
) -> None:
    conversation_id = f"host-action-resolution-{uuid4()}"
    store = MessageStore(engine)
    waking = await store.insert_waking(
        role="host",
        text="Synthetic succeeded action result; create another draft.",
        source="action",
        source_conversation_id=conversation_id,
        source_message_id=f"{uuid4()}:succeeded",
        created_at=NOW,
    )
    provider = _Provider()
    binding, plan = _plan(provider, ToolId("gmail.create_draft"))
    checkpoint = PostgresInputCheckpoint(
        store=store,
        thread_id=ThreadId(conversation_id),
        run_id=RunId(f"host-action-resolution-{uuid4()}"),
        interactive_plan=plan,
        scheduled_wake_plan=plan,
        maximum_batch_size=10,
        maximum_attempts=3,
        turn_evidence=TurnEvidence(),
    )
    claimed = await checkpoint.claim(
        ThreadId(conversation_id), OwnerToken("host-action-resolution-owner")
    )
    assert isinstance(claimed, ClaimAcquired)
    gate_definition, gate_plan = build_slice5_write_gate(
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
    )
    result = await _dispatch(
        _dispatcher(
            checkpoint=checkpoint,
            gate=AutomaticWriteGate(
                model_decisions=model_journal,
                definition=gate_definition,
                plan=gate_plan,
                admission=cast("Any", object()),
                provider=cast("Any", object()),
            ),
            actions=ActionStore(engine),
            google=_Google(),
        ),
        binding,
        plan,
        waking.message.id,
        GmailCreateDraftInput(content=_content()),
        lineage=DispatchLineage(
            claimed.claim.claim_id,
            claimed.claim.through_checkpoint,
            tuple(item.input_id for item in claimed.claim.inputs),
            1,
            definition_fingerprint="a" * 64,
            model_decision_id=decision_key(str(claimed.claim.claim_id), 1),
        ),
    )

    assert isinstance(result, DispatchCompleted)
    assert result.result == {"type": "Failure", "error": {"type": "ToolUnavailable"}}
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                select(action.c.id).where(
                    action.c.origin_message_id == waking.message.id
                )
            )
            is None
        )
    assert provider.effects == []
    await checkpoint.settle(
        claimed.claim,
        claimed.claim.through_checkpoint,
        StructuredConclusion(
            {
                "response": {
                    "type": "answered",
                    "text": "Synthetic action result acknowledged.",
                }
            }
        ),
    )


async def test_approval_required_send_suspends_with_one_action_and_no_effect() -> None:
    owner_id = uuid4()
    provider = _Provider()
    binding, plan = _plan(provider, ToolId("gmail.send_draft"))
    actions = _ActionSpy()

    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner_id, "Send the synthetic draft."),
            gate=_Gate("allow", owner_id),
            actions=actions,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailSendDraftInput(
            draft_id="synthetic-draft",
            thread_id="synthetic-thread",
            jarvis_effect_id=gmail_effect_id(actions.creation_id),
            content=_content(),
        ),
    )

    assert isinstance(result, DispatchSuspended)
    assert result.waiting_for is WaitingFor.user
    assert actions.inserts == 1
    assert provider.effects == []


async def _origin(engine: AsyncEngine) -> UUID:
    owner_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=owner_id,
                role="owner",
                text="Create the synthetic draft.",
                source="discord",
                source_conversation_id="synthetic-channel",
                source_message_id=str(uuid4()),
                created_at=NOW,
                processed_at=None,
                processing_attempts=1,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )
    return owner_id


@postgres
async def test_automatic_write_creates_exactly_one_action_and_effect(
    engine: AsyncEngine,
) -> None:
    owner_id = await _origin(engine)
    provider = _Provider()
    binding, plan = _plan(provider, ToolId("gmail.create_draft"))
    store = ActionStore(engine)

    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner_id),
            gate=_Gate("allow", owner_id),
            actions=store,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailCreateDraftInput(content=_content()),
    )

    assert isinstance(result, DispatchCompleted)
    assert result.result["type"] == "Success"
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    select(action).where(action.c.origin_message_id == owner_id)
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["attempts"] == 1
    assert provider.effects == [rows[0]["id"]]


@postgres
async def test_interruption_after_action_creation_suspends_for_recovery(
    engine: AsyncEngine,
) -> None:
    owner_id = await _origin(engine)
    provider = _Provider("cancel")
    binding, plan = _plan(provider, ToolId("gmail.create_draft"))
    store = ActionStore(engine)

    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner_id),
            gate=_Gate("allow", owner_id),
            actions=store,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailCreateDraftInput(content=_content()),
    )

    assert isinstance(result, DispatchSuspended)
    assert result.waiting_for is WaitingFor.system
    stored = await store.get(UUID(str(result.host_ref)))
    assert stored is not None
    assert str(result.host_ref) == str(stored.id)
    assert stored.status == "executing"
    assert stored.attempts == 1
    assert provider.effects == [stored.id]
    await store.resolve_reconciliation(
        action_id=stored.id,
        status="failed",
        result={"type": "Failure", "error": {"type": "BudgetExceeded"}},
    )


@postgres
async def test_gmail_update_preflight_crash_is_safely_reentered_before_mutation(
    engine: AsyncEngine,
) -> None:
    owner_id = await _origin(engine)
    store = ActionStore(engine)
    provider = _PreflightCrashUpdateProvider()
    provider.store = store
    binding, plan = _plan(provider, ToolId("gmail.update_draft"))
    value = GmailUpdateDraftInput(
        draft_id="synthetic-draft",
        expected_content_digest="b" * 64,
        replacement=_content(),
    )

    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner_id, "Update the synthetic draft."),
            gate=_Gate("allow", owner_id),
            actions=store,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        value,
    )

    assert isinstance(result, DispatchSuspended)
    action_id = UUID(str(result.host_ref))
    interrupted = await store.get(action_id)
    assert interrupted is not None
    assert interrupted.status == "executing"
    assert interrupted.attempts == 1
    assert interrupted.recovered_external_attempts == 1
    assert interrupted.reconciliation_basis is None

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", _Google()),
            plan=plan,
            source_conversation_id="synthetic-channel",
        ).recover()
        >= 1
    )
    terminal = await store.get(action_id)
    assert terminal is not None
    assert terminal.status == "succeeded"
    assert terminal.attempts == 2
    assert provider.effects == [action_id, action_id]
    assert provider.budgets == [
        WriteAttemptBudget(0, 4),
        WriteAttemptBudget(1, 3),
    ]


async def _interrupted(
    engine: AsyncEngine,
) -> tuple[UUID, _Provider, ToolBinding[Any, Any, Any], Any, ActionStore]:
    owner_id = await _origin(engine)
    provider = _Provider("cancel")
    binding, plan = _plan(provider, ToolId("gmail.create_draft"))
    store = ActionStore(engine)
    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner_id),
            gate=_Gate("allow", owner_id),
            actions=store,
            google=_Google(),
        ),
        binding,
        plan,
        owner_id,
        GmailCreateDraftInput(content=_content()),
    )
    assert isinstance(result, DispatchSuspended)
    action_id = UUID(str(result.host_ref))
    await store.stage_external_attempts(action_id=action_id, actual_external_attempts=1)
    return action_id, provider, binding, plan, store


@postgres
async def test_startup_reconciliation_success_and_resolution_are_idempotent(
    engine: AsyncEngine,
) -> None:
    action_id, _, _, plan, store = await _interrupted(engine)
    success = GmailDraftSuccess(
        draft_id="synthetic-draft",
        message_id="synthetic-message",
        thread_id="synthetic-thread",
        jarvis_effect_id="a" * 64,
        content_digest="b" * 64,
        observed_at=NOW,
    )
    google = _Google(ReconciliationResult("succeeded", "exact", success))
    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", google),
        plan=plan,
        source_conversation_id="synthetic-channel",
    )

    assert await recovery.recover() == 1
    assert await recovery.recover() == 0
    stored = await store.get(action_id)
    assert stored is not None and stored.status == "succeeded"
    assert google.reconciliations == 1
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{action_id}:succeeded",
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1


@postgres
async def test_gmail_create_absence_and_uncertainty_never_repeat(
    engine: AsyncEngine,
) -> None:
    absent_id, absent_provider, _, absent_plan, absent_store = await _interrupted(
        engine
    )
    absent_provider.mode = "success"
    absent_google = _Google(ReconciliationResult("absent", "proved-absent"))
    await ActionRecovery(
        actions=absent_store,
        google_write=cast("Any", absent_google),
        plan=absent_plan,
        source_conversation_id="synthetic-channel",
    ).recover()
    absent = await absent_store.get(absent_id)
    assert absent is not None
    assert absent.status == "uncertain"
    assert absent.attempts == 1
    assert absent.result is not None
    assert absent.result["evidence_code"] == ("gmail-create-absence-is-not-repeat-safe")
    assert absent_provider.effects == [absent_id]

    (
        uncertain_id,
        uncertain_provider,
        _,
        uncertain_plan,
        uncertain_store,
    ) = await _interrupted(engine)
    uncertain_google = _Google(ReconciliationResult("uncertain", "ambiguous"))
    await ActionRecovery(
        actions=uncertain_store,
        google_write=cast("Any", uncertain_google),
        plan=uncertain_plan,
        source_conversation_id="synthetic-channel",
    ).recover()
    uncertain = await uncertain_store.get(uncertain_id)
    assert uncertain is not None
    assert uncertain.status == "uncertain"
    assert uncertain.attempts == 1
    assert uncertain_provider.effects == [uncertain_id]


@pytest.mark.parametrize("verb", ["start", "send", "keys", "interrupt", "stop", "kill"])
async def test_agent_denied_owner_write_never_reaches_action_or_cli(
    tmp_path: Path, verb: str
) -> None:
    owner = uuid4()
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"method": "terminal", "outcome": "written"}}
    )
    engine = create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
    try:
        actions = ActionStore(engine)
        controller = AgentController(
            executable=executable, client_config=config, actions=actions
        )
        catalog = ToolCatalog.compose((agent_family(controller),))
        tool = ToolId("agent." + verb)
        profile = CapabilityProfile(
            ProfileId("synthetic-denied"),
            (ToolGrant(tool, None),),
            RunLimits(1, 1, 65536, 65536, 1, 15.0),
        ).freeze(catalog)
        plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
        value = {
            "start": AgentStartInput(
                machine="devbox", profile="codex-work", cwd=str(tmp_path), name="worker"
            ),
            "send": AgentSendInput.model_validate({"ref": REF, "text": "Synthetic"}),
            "keys": AgentKeysInput.model_validate({"ref": REF, "keys": ["enter"]}),
            "interrupt": AgentRefInput.model_validate({"ref": REF}),
            "stop": AgentRefInput.model_validate({"ref": REF}),
            "kill": AgentRefInput.model_validate({"ref": REF}),
        }[verb]
        gate = _Gate("deny", owner)
        result = await _dispatch(
            _dispatcher(
                checkpoint=_Checkpoint(owner),
                gate=gate,
                actions=actions,
                google=_Google(),
                agents=controller,
            ),
            catalog.binding(tool),
            plan,
            owner,
            value,
        )
        assert isinstance(result, DispatchCompleted)
        assert result.result == {
            "type": "Failure",
            "error": {
                "type": "AgentFailure",
                "code": "policy_denied",
                "dispatch": "not_sent",
            },
        }
        assert gate.calls == 1
        assert not config.with_suffix(".receipt").exists()
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_stage", "exception_class"),
    [
        ("checkpoint", "write_check_unavailable", "checkpoint", "RuntimeError"),
        (
            "owner_projection",
            "write_check_unavailable",
            "owner_projection",
            "ValidationError",
        ),
        (
            "target_metadata",
            "write_check_unavailable",
            "target_metadata",
            "DeclaredToolFailure",
        ),
        ("descriptor", "write_check_unavailable", "descriptor", "ValueError"),
        ("gate", "write_check_unavailable", "gate", "RuntimeError"),
        ("completed", "policy_denied", "gate", None),
        ("no_owner_input", "policy_denied", "gate", None),
        ("provider_error", "write_check_unavailable", "gate", None),
        ("budget_exhausted", "write_check_unavailable", "gate", None),
        ("invalid_result", "write_check_unavailable", "gate", None),
        ("invalid_support", "write_check_unavailable", "gate", None),
        ("unexpected_outcome", "write_check_unavailable", "gate", None),
    ],
)
async def test_agent_keys_check_failures_are_distinct_and_content_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
    expected_code: str,
    expected_stage: str,
    exception_class: str | None,
) -> None:
    private = "SYNTHETIC-PRIVATE-WRITE-CHECK"
    owner = uuid4()
    actions = _ActionSpy()
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"method": "terminal", "outcome": "written"}}
    )
    if failure == "target_metadata":
        config.with_suffix(".info").write_text(
            json.dumps(
                {"ok": False, "error": {"code": "unavailable", "dispatch": "not_sent"}}
            )
        )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=cast(ActionStore, actions),
    )
    catalog = ToolCatalog.compose((agent_family(controller),))
    tool = ToolId("agent.keys")
    profile = CapabilityProfile(
        ProfileId("synthetic-write-check"),
        (ToolGrant(tool, None),),
        RunLimits(1, 1, 65536, 65536, 1, 15.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)

    class Checkpoint(_Checkpoint):
        async def automatic_write_gate_inputs(
            self, lineage: DispatchLineage
        ) -> tuple[tuple[HostInput, ...], datetime]:
            if failure == "checkpoint":
                raise RuntimeError(private)
            if failure == "no_owner_input":
                return (), NOW
            return await super().automatic_write_gate_inputs(lineage)

    class Gate(_Gate):
        async def evaluate(self, *args: object, **kwargs: object) -> WriteGateDecision:
            del kwargs
            self.calls += 1
            if failure == "gate":
                raise RuntimeError(private)
            if failure == "no_owner_input":
                assert args == ((),)
            return WriteGateDecision(
                "deny",
                (),
                None,
                private if failure == "unexpected_outcome" else failure,
                None,
            )

    if failure == "descriptor":

        def invalid_descriptor(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise ValueError(private)

        monkeypatch.setattr(
            "jarvis.write_dispatch.write_effect_descriptor", invalid_descriptor
        )

    gate = Gate("deny", owner)
    lineage = _lineage(owner)
    # The in-process Alembic fixture disables existing application loggers.
    monkeypatch.setattr(logging.getLogger("jarvis.write_dispatch"), "disabled", False)
    caplog.set_level(logging.INFO, logger="jarvis.write_dispatch")
    result = await _dispatch(
        _dispatcher(
            checkpoint=Checkpoint(
                owner, private * 100 if failure == "owner_projection" else private
            ),
            gate=gate,
            actions=actions,
            google=_Google(),
            agents=controller,
        ),
        catalog.binding(tool),
        plan,
        owner,
        AgentKeysInput.model_validate({"ref": REF, "keys": ["down", "enter"]}),
        lineage=lineage,
    )
    assert isinstance(result, DispatchCompleted)
    assert result.result == {
        "type": "Failure",
        "error": AgentError(code=expected_code, dispatch="not_sent").model_dump(
            mode="json"
        ),
    }
    assert actions.inserts == 0
    assert (
        (not config.with_suffix(".calls").exists())
        if failure in {"checkpoint", "owner_projection", "no_owner_input"}
        else config.with_suffix(".calls").read_text() == "info\n"
    )
    assert not config.with_suffix(".receipt").exists()
    assert gate.calls == (
        1 if expected_stage == "gate" and failure != "no_owner_input" else 0
    )
    records = [
        record for record in caplog.records if record.name == "jarvis.write_dispatch"
    ]
    assert len(records) == 1
    record = records[0]
    diagnostic = record.getMessage()
    assert f"stage={expected_stage}" in diagnostic
    assert "tool=agent.keys" in diagnostic
    assert f"decision={lineage.model_decision_id}" in diagnostic
    if exception_class is not None:
        assert f"exception={exception_class}" in diagnostic
    else:
        outcome = "unknown" if failure == "unexpected_outcome" else failure
        assert f"outcome={outcome}" in diagnostic
    assert private not in diagnostic
    assert str(owner) not in diagnostic
    assert record.exc_info is None
    assert record.stack_info is None


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("JARVIS_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL action boundary",
)
@pytest.mark.parametrize(
    ("verb", "outcome"),
    [
        ("stop", "lost"),
        ("stop", "partial"),
        ("stop", "closed"),
        ("kill", "lost"),
        ("kill", "closed"),
    ],
)
async def test_real_agent_dispatch_preserves_closure_evidence_without_replay(
    tmp_path: Path, verb: str, outcome: str
) -> None:
    response: dict[str, object] = (
        {"ok": False, "error": {"code": "unknown", "dispatch": "unknown"}}
        if outcome == "lost"
        else {
            "ok": True,
            "result": {
                "agent": "unconfirmed" if outcome == "partial" else "idle",
                "terminal": "closed",
            },
        }
    )
    if verb == "kill" and outcome == "closed":
        response = {"ok": True, "result": {"terminal": "closed"}}
    executable, config = cli(tmp_path, response)
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    owner = uuid4()
    channel = str(owner)
    messages = MessageStore(engine)
    await messages.insert_waking(
        role="owner",
        text="Stop the synthetic agent.",
        source="discord",
        source_conversation_id=channel,
        source_message_id=str(owner),
        created_at=datetime.now(UTC),
        message_id=owner,
    )
    try:
        actions = ActionStore(engine)
        controller = AgentController(
            executable=executable, client_config=config, actions=actions
        )
        catalog = ToolCatalog.compose((agent_family(controller),))
        tool = ToolId("agent." + verb)
        profile = CapabilityProfile(
            ProfileId("synthetic-stop"),
            (ToolGrant(tool, None),),
            RunLimits(1, 1, 65536, 65536, 1, 15.0),
        ).freeze(catalog)
        plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
        result = await _dispatch(
            _dispatcher(
                checkpoint=_Checkpoint(owner),
                gate=_Gate("allow", owner),
                actions=actions,
                google=_Google(),
                agents=controller,
            ),
            catalog.binding(tool),
            plan,
            owner,
            AgentRefInput.model_validate({"ref": REF}),
        )
        receipt = config.with_suffix(".receipt")
        first = receipt.stat().st_mtime_ns
        if outcome == "closed":
            assert isinstance(result, DispatchCompleted)
            assert result.result["type"] == "Success"
            async with engine.connect() as connection:
                identifier = await connection.scalar(
                    select(action.c.id).where(action.c.origin_message_id == owner)
                )
            assert identifier is not None
            completed = await actions.get(identifier)
            assert (
                completed is not None
                and completed.status == "succeeded"
                and completed.attempts == 1
            )
            assert '"terminal":"closed"' in action_resolution_text(completed)
            return
        assert isinstance(result, DispatchSuspended)
        stored = await actions.get(UUID(str(result.host_ref)))
        assert (
            stored is not None and stored.status == "uncertain" and stored.attempts == 1
        )
        assert stored.result is not None
        if outcome == "partial":
            control = cast(dict[str, object], stored.result["control"])
            observed = cast(dict[str, object], control["observed"])
            assert observed["terminal"] == "closed"
        recovery = ActionRecovery(
            actions=actions,
            google_write=cast(Any, _Google()),
            plan=plan,
            source_conversation_id=channel,
        )
        await recovery.recover(allow_queued_execution=False)
        await recovery.recover(allow_queued_execution=False)
        assert receipt.stat().st_mtime_ns == first
        consumed = await messages.message_by_id(owner)
        assert consumed is not None and consumed.processed_at is not None
    finally:
        await engine.dispose()


async def test_agent_metadata_grounds_name_and_keeps_original_ref(
    tmp_path: Path,
) -> None:
    owner = uuid4()
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"method": "terminal", "outcome": "written"}}
    )
    actions = _ActionSpy()
    controller = AgentController(
        executable=executable, client_config=config, actions=cast(ActionStore, actions)
    )
    info = {
        **INFO,
        "session": {
            **cast(dict[str, object], INFO["session"]),
            "ref": "refreshed-reference",
        },
    }
    config.with_suffix(".info").write_text(json.dumps({"ok": True, "result": info}))
    catalog = ToolCatalog.compose((agent_family(controller),))
    tool = ToolId("agent.stop")
    profile = CapabilityProfile(
        ProfileId("synthetic-grounding"),
        (ToolGrant(tool, None),),
        RunLimits(1, 1, 65536, 65536, 1, 15.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)

    class Gate(_Gate):
        async def evaluate(self, *args: object, **kwargs: object) -> WriteGateDecision:
            from jarvis.write_gate import WriteEffectDescriptor

            descriptor = kwargs["descriptor"]
            assert isinstance(descriptor, WriteEffectDescriptor)
            assert {(target.kind, target.value) for target in descriptor.targets} == {
                ("machine", "arch"),
                ("terminal_name", "reviewer"),
                ("terminal_id", REF),
            }
            return await super().evaluate(*args, **kwargs)

    gate = Gate("deny", owner)
    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner, "stop reviewer on arch"),
            gate=gate,
            actions=actions,
            google=_Google(),
            agents=controller,
        ),
        catalog.binding(tool),
        plan,
        owner,
        AgentRefInput(ref=REF),
    )
    assert isinstance(result, DispatchCompleted)
    assert result.result["error"]["code"] == "policy_denied"
    assert gate.calls == 1
    assert actions.inserts == 0
    assert config.with_suffix(".calls").read_text() == "info\n"
    assert not config.with_suffix(".receipt").exists()


async def test_metadata_refresh_never_changes_persisted_or_dispatched_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm_tools import ExecutionContext, ParsedJson, ToolExecutor, ToolResult

    owner = uuid4()
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"agent": "idle", "terminal": "closed"}}
    )
    config.with_suffix(".info").write_text(
        json.dumps(
            {
                "ok": True,
                "result": {
                    **INFO,
                    "session": {
                        **cast(dict[str, object], INFO["session"]),
                        "ref": "refreshed-reference",
                    },
                },
            }
        )
    )
    captured: list[object] = []

    class Actions(_ActionSpy):
        async def insert_automatic(self, **kwargs: object) -> object:
            self.inserts += 1
            captured.append(kwargs["arguments"])
            return None

    actions = Actions()
    controller = AgentController(
        executable=executable, client_config=config, actions=cast(ActionStore, actions)
    )
    catalog = ToolCatalog.compose((agent_family(controller),))
    tool = ToolId("agent.stop")
    profile = CapabilityProfile(
        ProfileId("synthetic-preserve-ref"),
        (ToolGrant(tool, None),),
        RunLimits(1, 1, 65536, 65536, 1, 15.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)

    async def execute(
        binding: object, raw: ParsedJson, context: ExecutionContext
    ) -> ToolResult:
        del binding
        assert raw.value == {"ref": REF}
        result = await controller.stop(AgentRefInput.model_validate(raw.value), context)
        return {"type": "Success", "value": result.value.model_dump(mode="json")}

    monkeypatch.setattr(ToolExecutor, "execute", execute)
    result = await _dispatch(
        _dispatcher(
            checkpoint=_Checkpoint(owner, "stop reviewer"),
            gate=_Gate("allow", owner),
            actions=actions,
            google=_Google(),
            agents=controller,
        ),
        catalog.binding(tool),
        plan,
        owner,
        AgentRefInput(ref=REF),
    )
    assert isinstance(result, DispatchCompleted) and result.result["type"] == "Success"
    assert captured == [{"ref": REF}]
    assert actions.inserts == 1
    assert config.with_suffix(".calls").read_text() == "info\nstop\n"
    receipt = json.loads(config.with_suffix(".receipt").read_text())
    assert receipt["argv"] == ["--config", str(config), "stop", "--json", "--ref", REF]

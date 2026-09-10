from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import discord
import httpx
import pytest
import pytest_asyncio
from llm_agent_kernel import CancellationToken
from llm_tools import (
    CapabilityProfile,
    EffectId,
    ExecutionContext,
    HostTable,
    ParsedJson,
    Principal,
    ProfileId,
    RecoveryRequired,
    ReplayPolicy,
    RunLimits,
    Scope,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolExecutor,
    ToolGrant,
    ToolId,
    ToolPlan,
    raw_input_digest,
)
from service_fixture import LocalGateway, service_settings
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
    StoredAction,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.approval import render_approval, render_inactive_approval
from jarvis.approval_runtime import (
    ApprovalActionHandler,
    ApprovalAwareDiscordDelivery,
    ApprovalRecoveryDisabler,
)
from jarvis.cli import run_service
from jarvis.db import create_engine, message
from jarvis.discord import (
    ApprovalComponentDecision,
    DeliveryFailed,
    DeliveryFailureKind,
    DeliverySucceeded,
    DiscordApprovalInteraction,
    approval_custom_id,
)
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.service import JarvisService, flush_pending_deliveries
from jarvis.state import PausedState
from jarvis.write_connectors import (
    ReconciliationResult,
    gmail_content_digest,
    gmail_effect_id,
)
from jarvis.write_dispatch import ActionRecovery, NoTelemetry
from jarvis.write_tools import (
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    GmailSendDraftInput,
    GmailSendDraftSuccess,
    Mailbox,
    WriteAttemptBudget,
    WriteResponse,
    gmail_write_family,
)

DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")
postgres = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="JARVIS_TEST_DATABASE_URL is not configured",
)
NOW = datetime(2026, 9, 7, 18, tzinfo=UTC)
SEND_ID = ToolId("gmail.send_draft")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if DATABASE_URL is None:
        pytest.skip("JARVIS_TEST_DATABASE_URL is not configured")
    value = create_engine(DATABASE_URL)
    yield value
    await value.dispose()


def _value(jarvis_effect_id: str = "a" * 64) -> GmailSendDraftInput:
    return GmailSendDraftInput(
        draft_id="synthetic-draft",
        thread_id="synthetic-thread",
        jarvis_effect_id=jarvis_effect_id,
        content=GmailContent(
            to=(Mailbox(name="Owner", address="owner@example.invalid"),),
            cc=(Mailbox(name=None, address="cc@example.invalid"),),
            bcc=(),
            subject="Synthetic approval runtime",
            body_text="Complete synthetic body.\nSecond line.",
            reply_to=None,
        ),
    )


class _Provider:
    def __init__(
        self,
        *,
        order: list[str] | None = None,
        mode: Literal["success", "recovery"] = "success",
    ) -> None:
        self.effects: list[UUID] = []
        self.creation_effects: list[UUID] = []
        self.expected: GmailSendDraftInput | None = None
        self.store: ActionStore | None = None
        self.entry_attempts: list[int] = []
        self.order = order
        self.mode = mode

    async def gmail_send_draft(
        self,
        value: GmailSendDraftInput,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[GmailSendDraftSuccess]:
        assert value == self.expected
        if self.store is not None:
            entered = await self.store.get(effect_id)
            assert entered is not None
            assert entered.status == "executing"
            self.entry_attempts.append(entered.attempts)
            expected_attempts = WriteAttemptBudget(
                entered.recovered_external_attempts,
                4 - entered.recovered_external_attempts,
            )
        else:
            expected_attempts = WriteAttemptBudget(0, 4)
        assert attempts == expected_attempts
        self.effects.append(effect_id)
        if self.order is not None:
            self.order.append("executor")
        if self.mode == "recovery":
            if self.store is not None:
                await self.store.stage_external_attempts(
                    action_id=effect_id,
                    actual_external_attempts=attempts.recovered_attempts + 1,
                )
            raise RecoveryRequired("synthetic accepted send needs reconciliation")
        return WriteResponse(
            GmailSendDraftSuccess(
                sent_message_id=f"sent-{effect_id}",
                thread_id=value.thread_id,
                jarvis_effect_id=value.jarvis_effect_id,
                content_digest="b" * 64,
                sent_at=NOW,
            ),
            1,
        )

    async def gmail_create_draft(
        self,
        value: GmailCreateDraftInput,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        assert attempts == WriteAttemptBudget(0, 4)
        self.creation_effects.append(effect_id)
        return WriteResponse(
            GmailDraftSuccess(
                draft_id="synthetic-draft",
                message_id="synthetic-created-message",
                thread_id="synthetic-thread",
                jarvis_effect_id=gmail_effect_id(effect_id),
                content_digest=gmail_content_digest(value.content),
                observed_at=NOW,
            ),
            1,
        )

    async def gmail_update_draft(self, *args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))


def _plan(
    provider: _Provider,
) -> tuple[ToolBinding[Any, Any, Any], Any]:
    catalog = ToolCatalog.compose((gmail_write_family(cast("Any", provider)),))
    limits = RunLimits(
        max_calls=2,
        max_external_attempts=8,
        max_input_bytes=524_288,
        max_output_bytes=131_072,
        max_in_flight=1,
        max_elapsed_seconds=30.0,
    )
    profile = CapabilityProfile(
        ProfileId(f"approval_runtime_{uuid4().hex}"),
        (
            ToolGrant(ToolId("gmail.create_draft"), None),
            ToolGrant(SEND_ID, None),
        ),
        limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    return catalog.binding(SEND_ID), plan


async def _origin(engine: AsyncEngine, conversation_id: str) -> UUID:
    identifier = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(message).values(
                id=identifier,
                role="owner",
                text="Send the exact synthetic draft.",
                source="discord",
                source_conversation_id=conversation_id,
                source_message_id=str(uuid4()),
                created_at=NOW,
                processed_at=None,
                processing_attempts=1,
                processing_parked_at=None,
                remembered_at=None,
                trace={},
            )
        )
    return identifier


def _contract(
    *,
    binding: ToolBinding[Any, Any, Any],
    plan: Any,
    arguments: Mapping[str, object],
    origin_id: UUID,
) -> ExecutionContract:
    return ExecutionContract(
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
        tool_effect=ToolEffect.Write,
        replay_policy=ReplayPolicy.ReDispatchable,
        input_digest=raw_input_digest(ParsedJson(dict(arguments))),
        max_attempts=ACTION_MAX_ATTEMPTS,
        claim_id=str(uuid4()),
        through_checkpoint=str(origin_id),
        model_step_ordinal=1,
        input_message_ids=(str(origin_id),),
        write_gate_supporting_owner_message_ids=(str(origin_id),),
    )


async def _insert_approval(
    engine: AsyncEngine,
    *,
    provider: _Provider,
    conversation_id: str,
    approval_text: str | None = None,
    mark_delivered: bool = True,
) -> tuple[ActionStore, Any, Any, Any, str]:
    binding, plan = _plan(provider)
    origin_id = await _origin(engine, conversation_id)
    store = ActionStore(engine)
    if provider.expected is None:
        creation_conversation_id = f"{conversation_id}-draft-creation"
        creation_origin_id = await _origin(engine, creation_conversation_id)
        creation_id = uuid4()
        value = _value(gmail_effect_id(creation_id))
        create_binding = plan.catalog_view.binding(ToolId("gmail.create_draft"))
        create_value = GmailCreateDraftInput(content=value.content)
        create_arguments = cast(
            "dict[str, object]", create_value.model_dump(mode="json")
        )
        await store.insert_automatic(
            tool_name=ToolId("gmail.create_draft"),
            arguments=create_arguments,
            execution_contract=_contract(
                binding=create_binding,
                plan=plan,
                arguments=create_arguments,
                origin_id=creation_origin_id,
            ),
            origin_message_id=creation_origin_id,
            action_id=creation_id,
            created_at=NOW,
        )
        create_recorder = ActionPositionRecorder(
            store=store,
            action_id=creation_id,
            implementation_revision=create_binding.implementation_revision,
            max_external_attempts=plan.grant(
                ToolId("gmail.create_draft")
            ).limits.max_attempts,
        )
        created = await ToolExecutor.execute(
            create_binding,
            ParsedJson(create_arguments),
            ExecutionContext(
                plan=plan,
                grant=plan.grant(ToolId("gmail.create_draft")),
                catalog_view=plan.catalog_view,
                position=create_recorder.position,
                recorder=create_recorder,
                effect_id=EffectId(str(creation_id)),
                budgets=ExactToolBudgetFactory().create(plan),
                principal=Principal("jarvis-owner"),
                scope=Scope("synthetic-automatic-write"),
                cancellation=CancellationToken(),
                telemetry=NoTelemetry(),
            ),
        )
        assert created["type"] == "Success"
        await store.finish_recovered_origin(
            action_id=creation_id,
            source_conversation_id=creation_conversation_id,
            text="Synthetic Gmail draft creation completed.",
            created_at=NOW,
        )
        provider.expected = value
    value = provider.expected
    assert value is not None
    arguments = cast("dict[str, object]", value.model_dump(mode="json"))
    action_id = uuid4()
    expected = render_approval(action_id, SEND_ID, value).content
    inserted = await store.insert_awaiting_approval(
        tool_name=SEND_ID,
        arguments=arguments,
        execution_contract=_contract(
            binding=binding,
            plan=plan,
            arguments=arguments,
            origin_id=origin_id,
        ),
        origin_message_id=origin_id,
        approval_text=approval_text or expected,
        source_conversation_id=conversation_id,
        action_id=action_id,
        created_at=NOW,
    )
    discord_message_id = str(int(action_id.hex[:12], 16))
    if mark_delivered:
        await MessageStore(engine).mark_delivered(
            message_id=inserted.message_id,
            source_message_id=discord_message_id,
        )
    return store, plan, inserted, value, discord_message_id


class _OrdinaryDelivery:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID | str, str]] = []

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliverySucceeded:
        self.calls.append((persisted_message_id, content))
        return DeliverySucceeded("ordinary-discord-message", 1)


class _ApprovalDelivery:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_approval_message(
        self, **kwargs: object
    ) -> DeliverySucceeded | DeliveryFailed:
        self.calls.append(dict(kwargs))
        return DeliverySucceeded("approval-discord-message", 1)


class _FailOnceApprovalDelivery(_ApprovalDelivery):
    async def create_approval_message(
        self, **kwargs: object
    ) -> DeliverySucceeded | DeliveryFailed:
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            return DeliveryFailed(
                DeliveryFailureKind.TRANSPORT,
                1,
                True,
                True,
            )
        return DeliverySucceeded("987654322", 1)


class _RecoveryGoogle:
    def __init__(
        self,
        result: ReconciliationResult[GmailSendDraftSuccess] | None = None,
        order: list[str] | None = None,
    ) -> None:
        self.result = result
        self.order = order
        self.send_reconciliations = 0

    async def reconcile_gmail_send(
        self, value: GmailSendDraftInput
    ) -> ReconciliationResult[GmailSendDraftSuccess]:
        assert value == _value(value.jarvis_effect_id)
        self.send_reconciliations += 1
        if self.order is not None:
            self.order.append("reconcile")
        assert self.result is not None
        return self.result


class _RecoveryDisabler:
    def __init__(
        self,
        store: ActionStore,
        order: list[str],
        *,
        expected_status: str = "executing",
    ) -> None:
        self.store = store
        self.order = order
        self.expected_status = expected_status
        self.actions: list[UUID] = []

    async def __call__(self, action: StoredAction) -> None:
        current = await self.store.get(action.id)
        assert current is not None
        assert current.status == self.expected_status
        assert current.attempts == 0
        self.actions.append(current.id)
        self.order.append("disable")


class _DisableDiscord:
    def __init__(self, result: DeliverySucceeded | DeliveryFailed) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def disable_approval_message(self, **kwargs: object) -> Any:
        self.calls.append(dict(kwargs))
        return self.result


class _Response:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.done = False

    def is_done(self) -> bool:
        return self.done

    async def edit_message(self, **kwargs: object) -> None:
        assert kwargs["suppress_embeds"] is True
        view = cast(discord.ui.View, kwargs["view"])
        assert len(view.children) == 2
        buttons = [
            cast(discord.ui.Button[Any], item)
            for item in view.children
            if isinstance(item, discord.ui.Button)
        ]
        assert len(buttons) == 2
        assert all(item.disabled for item in buttons)
        self.order.append("ack")
        self.done = True


class _InteractionEvent:
    def __init__(self, order: list[str]) -> None:
        self.response = _Response(order)


def _interaction(
    inserted: Any,
    discord_message_id: str,
    decision: ApprovalComponentDecision,
    *,
    action_id: UUID | None = None,
) -> DiscordApprovalInteraction:
    return DiscordApprovalInteraction(
        action_id=action_id or inserted.action.id,
        approval_message_id=inserted.message_id,
        decision=decision,
        discord_message_id=discord_message_id,
    )


async def _execute_preclaimed(
    store: ActionStore,
    plan: Any,
    action_id: UUID,
) -> None:
    stored = await store.get(action_id)
    assert stored is not None
    binding = plan.catalog_view.binding(stored.tool_name)
    grant = plan.grant(stored.tool_name)
    recorder = ActionPositionRecorder(
        store=store,
        action_id=action_id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=grant.limits.max_attempts,
        preclaimed_approval=True,
    )
    result = await ToolExecutor.execute(
        binding,
        ParsedJson(stored.arguments),
        ExecutionContext(
            plan=plan,
            grant=grant,
            catalog_view=plan.catalog_view,
            position=recorder.position,
            recorder=recorder,
            effect_id=EffectId(str(action_id)),
            budgets=ExactToolBudgetFactory().create(plan),
            principal=Principal("jarvis-owner"),
            scope=Scope("synthetic-approval-write"),
            cancellation=CancellationToken(),
            telemetry=NoTelemetry(),
        ),
    )
    assert result["type"] == "Success"


@postgres
async def test_delivery_routes_ordinary_and_rebuilds_approval_from_state(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    store, plan, inserted, value, _ = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=f"approval-delivery-{uuid4()}",
    )
    ordinary = _OrdinaryDelivery()
    discord_delivery = _ApprovalDelivery()
    delivery = ApprovalAwareDiscordDelivery(
        actions=store,
        plan=plan,
        discord=cast("Any", discord_delivery),
        ordinary=ordinary,
    )

    ordinary_result = await delivery.create_message(
        persisted_message_id="not-an-internal-uuid",
        content="Ordinary synthetic response.",
    )
    assert isinstance(ordinary_result, DeliverySucceeded)
    assert ordinary_result.discord_message_id == "ordinary-discord-message"
    assert ordinary.calls == [("not-an-internal-uuid", "Ordinary synthetic response.")]

    expected = render_approval(inserted.action.id, SEND_ID, value)
    approval_result = await delivery.create_message(
        persisted_message_id=inserted.message_id,
        content=expected.content,
    )
    assert isinstance(approval_result, DeliverySucceeded)
    assert approval_result.discord_message_id == "approval-discord-message"
    assert ordinary.calls == [("not-an-internal-uuid", "Ordinary synthetic response.")]
    assert discord_delivery.calls == [
        {
            "action_id": inserted.action.id,
            "approval_message_id": inserted.message_id,
            "content": expected.content,
            "attachment_name": expected.attachment.filename,
            "attachment_media_type": expected.attachment.media_type,
            "attachment_content": expected.attachment.content,
            "disabled": False,
        }
    ]


@postgres
async def test_delivery_rejects_durable_content_that_differs_from_host_rendering(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    store, plan, inserted, _, _ = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=f"approval-render-mismatch-{uuid4()}",
        approval_text="Synthetic model-authored substitute preview.",
    )
    discord_delivery = _ApprovalDelivery()
    delivery = ApprovalAwareDiscordDelivery(
        actions=store,
        plan=plan,
        discord=cast("Any", discord_delivery),
    )

    with pytest.raises(
        RuntimeError,
        match="durable approval message differs from host rendering",
    ):
        await delivery.create_message(
            persisted_message_id=inserted.message_id,
            content="Synthetic model-authored substitute preview.",
        )
    assert discord_delivery.calls == []


@postgres
async def test_approve_acknowledges_before_exact_action_execution_and_reports(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider(order=order)
    conversation_id = f"approval-execute-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )
    event = _InteractionEvent(order)

    claimed = await handler.claim_and_acknowledge(
        cast("Any", event),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None
    assert claimed.action.id == inserted.action.id
    assert order == ["ack"]
    assert provider.effects == []

    assert await handler.complete(claimed)
    assert order == ["ack", "executor"]
    assert provider.effects == [inserted.action.id]
    terminal = await store.get(inserted.action.id)
    assert terminal is not None
    assert terminal.status == "succeeded"
    assert terminal.attempts == 1
    async with engine.connect() as connection:
        reports = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id
                        == f"{inserted.action.id}:succeeded",
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(reports) == 1


@postgres
async def test_deny_acknowledges_reports_and_never_enters_executor(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider(order=order)
    conversation_id = f"approval-deny-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )

    claimed = await handler.claim_and_acknowledge(
        cast("Any", _InteractionEvent(order)),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.DENY,
        ),
    )
    assert claimed is not None
    assert order == ["ack"]
    assert await handler.complete(claimed)
    assert provider.effects == []
    denied = await store.get(inserted.action.id)
    assert denied is not None
    assert denied.status == "cancelled"
    assert denied.attempts == 0
    async with engine.connect() as connection:
        reports = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id
                        == f"{inserted.action.id}:cancelled",
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(reports) == 1
    assert "Status: cancelled" in reports[0]["text"]


@postgres
async def test_restart_after_denial_claim_disables_before_resolution_report(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider(order=order)
    conversation_id = f"approval-deny-restart-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    decision = await store.deny_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id=discord_message_id,
        source_conversation_id=conversation_id,
    )
    assert decision.applied
    disabler = _RecoveryDisabler(
        store,
        order,
        expected_status="cancelled",
    )

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", _RecoveryGoogle()),
            plan=plan,
            source_conversation_id=conversation_id,
            approval_disabler=disabler,
        ).recover()
        >= 1
    )

    assert order == ["disable"]
    assert disabler.actions == [inserted.action.id]
    assert provider.effects == []
    async with engine.connect() as connection:
        reports = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id
                        == f"{inserted.action.id}:cancelled",
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(reports) == 1


@postgres
async def test_duplicate_wrong_and_stale_interactions_have_no_effect(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-stale-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )

    wrong_event = _InteractionEvent([])
    assert (
        await handler.claim_and_acknowledge(
            cast("Any", wrong_event),
            _interaction(
                inserted,
                discord_message_id,
                ApprovalComponentDecision.APPROVE,
                action_id=uuid4(),
            ),
        )
        is None
    )
    stale_event = _InteractionEvent([])
    assert (
        await handler.claim_and_acknowledge(
            cast("Any", stale_event),
            _interaction(
                inserted,
                str(int(discord_message_id) + 1),
                ApprovalComponentDecision.APPROVE,
            ),
        )
        is None
    )
    assert not wrong_event.response.done
    assert not stale_event.response.done

    accepted_event = _InteractionEvent([])
    claimed = await handler.claim_and_acknowledge(
        cast("Any", accepted_event),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None
    assert await handler.complete(claimed)

    duplicate_event = _InteractionEvent([])
    assert (
        await handler.claim_and_acknowledge(
            cast("Any", duplicate_event),
            _interaction(
                inserted,
                discord_message_id,
                ApprovalComponentDecision.APPROVE,
            ),
        )
        is None
    )
    assert not duplicate_event.response.done
    assert provider.effects == [inserted.action.id]


@postgres
async def test_approved_recovery_required_stays_executing_without_report(
    engine: AsyncEngine,
) -> None:
    provider = _Provider(mode="recovery")
    conversation_id = f"approval-recovery-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )
    claimed = await handler.claim_and_acknowledge(
        cast("Any", _InteractionEvent([])),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None

    assert not await handler.complete(claimed)
    unresolved = await store.get(inserted.action.id)
    assert unresolved is not None
    assert unresolved.status == "executing"
    assert unresolved.attempts == 1
    assert provider.effects == [inserted.action.id]
    async with engine.connect() as connection:
        report = await connection.scalar(
            select(message.c.id).where(
                message.c.source == "action",
                message.c.source_message_id == f"{inserted.action.id}:executing",
            )
        )
    assert report is None
    await store.resolve_reconciliation(
        action_id=inserted.action.id,
        status="uncertain",
        result={
            "type": "action_uncertainty_v1",
            "evidence_code": "synthetic-recovery-required-cleanup",
            "recorded_at": NOW.isoformat(),
        },
    )


@postgres
async def test_cancelled_approved_completion_never_enters_executor(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-cancel-before-entry-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )
    claimed = await handler.claim_and_acknowledge(
        cast("Any", _InteractionEvent([])),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None
    cancellation = CancellationToken()
    cancellation.cancel()

    assert not await handler.complete(claimed, cancellation)

    unchanged = await store.get(inserted.action.id)
    assert unchanged is not None
    assert unchanged.status == "executing"
    assert unchanged.attempts == 0
    assert provider.effects == []
    await store.requeue_after_proved_absence(
        inserted.action.id,
        actual_external_attempts=0,
        max_external_attempts=plan.grant(SEND_ID).limits.max_attempts,
    )
    await store.cancel_nonexecuting(
        action_id=inserted.action.id,
        result={"type": "test_cleanup_v1", "reason_code": "synthetic-no-entry"},
    )


@postgres
async def test_two_identical_approved_actions_keep_distinct_effect_identities(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    actions: list[UUID] = []
    for suffix in ("one", "two"):
        conversation_id = f"approval-distinct-{suffix}-{uuid4()}"
        store, plan, inserted, _, discord_message_id = await _insert_approval(
            engine,
            provider=provider,
            conversation_id=conversation_id,
        )
        handler = ApprovalActionHandler(
            actions=store,
            plan=plan,
            source_conversation_id=conversation_id,
        )
        claimed = await handler.claim_and_acknowledge(
            cast("Any", _InteractionEvent([])),
            _interaction(
                inserted,
                discord_message_id,
                ApprovalComponentDecision.APPROVE,
            ),
        )
        assert claimed is not None
        assert await handler.complete(claimed)
        actions.append(inserted.action.id)

    assert actions[0] != actions[1]
    assert provider.effects == actions


@postgres
async def test_failed_approval_delivery_remains_pending_and_repairs_exactly(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-delivery-repair-{uuid4()}"
    store, plan, inserted, value, _ = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
        mark_delivered=False,
    )
    discord_delivery = _FailOnceApprovalDelivery()
    delivery = ApprovalAwareDiscordDelivery(
        actions=store,
        plan=plan,
        discord=cast("Any", discord_delivery),
    )
    messages = MessageStore(engine)

    failed = await flush_pending_deliveries(
        store=messages,
        delivery=delivery,
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert failed.selected == 1
    assert failed.delivered == 0
    assert failed.failure is not None
    assert (await store.get(inserted.action.id)).status == "awaiting_approval"  # type: ignore[union-attr]
    assert (
        await messages.pending_delivery(
            source_conversation_id=conversation_id,
            limit=10,
        )
    )[0].id == inserted.message_id

    repaired = await flush_pending_deliveries(
        store=messages,
        delivery=delivery,
        source_conversation_id=conversation_id,
        limit=10,
    )
    assert repaired.selected == 1
    assert repaired.delivered == 1
    assert repaired.failure is None
    assert len(discord_delivery.calls) == 2
    assert discord_delivery.calls[0] == discord_delivery.calls[1]
    expected = render_approval(inserted.action.id, SEND_ID, value)
    assert discord_delivery.calls[1]["action_id"] == inserted.action.id
    assert discord_delivery.calls[1]["content"] == expected.content
    assert discord_delivery.calls[1]["attachment_content"] == (
        expected.attachment.content
    )
    assert (
        await messages.pending_delivery(
            source_conversation_id=conversation_id,
            limit=10,
        )
        == ()
    )
    assert await store.approval_discord_message_id(inserted.action.id) == "987654322"


@postgres
async def test_restart_after_approval_claim_disables_before_first_executor_entry(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider(order=order)
    conversation_id = f"approval-pre-entry-restart-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    provider.store = store
    claimed = await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id=discord_message_id,
        source_conversation_id=conversation_id,
    )
    assert claimed.applied
    assert claimed.action.status == "executing"
    assert claimed.action.attempts == 0
    disabler = _RecoveryDisabler(store, order)

    recovered = await ActionRecovery(
        actions=store,
        google_write=cast("Any", _RecoveryGoogle()),
        plan=plan,
        source_conversation_id=conversation_id,
        approval_disabler=disabler,
    ).recover()

    assert recovered >= 1
    assert order == ["disable", "executor"]
    assert disabler.actions == [inserted.action.id]
    assert provider.effects == [inserted.action.id]
    assert provider.entry_attempts == [1]
    terminal = await store.get(inserted.action.id)
    assert terminal is not None
    assert terminal.status == "succeeded"
    assert terminal.attempts == 1


@postgres
async def test_paused_restart_disables_claimed_approval_without_executor_entry(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider(order=order)
    conversation_id = f"approval-paused-pre-entry-restart-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    decision = await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id=discord_message_id,
        source_conversation_id=conversation_id,
    )
    assert decision.applied
    disabler = _RecoveryDisabler(store, order)

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", _RecoveryGoogle()),
            plan=plan,
            source_conversation_id=conversation_id,
            approval_disabler=disabler,
        ).recover(allow_queued_execution=False)
        == 0
    )

    assert order == ["disable"]
    assert disabler.actions == [inserted.action.id]
    assert provider.effects == []
    unchanged = await store.get(inserted.action.id)
    assert unchanged is not None
    assert unchanged.status == "executing"
    assert unchanged.attempts == 0
    await store.requeue_after_proved_absence(
        inserted.action.id,
        actual_external_attempts=0,
        max_external_attempts=plan.grant(SEND_ID).limits.max_attempts,
    )
    await store.cancel_nonexecuting(
        action_id=inserted.action.id,
        result={"type": "test_cleanup_v1", "reason_code": "synthetic-no-entry"},
    )


@postgres
async def test_incompatible_delivered_approval_disables_before_cancellation(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider()
    conversation_id = f"approval-incompatible-delivered-{uuid4()}"
    store, _, inserted, _, _ = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    _, incompatible_plan = _plan(provider)
    disabler = _RecoveryDisabler(
        store,
        order,
        expected_status="awaiting_approval",
    )

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", _RecoveryGoogle()),
            plan=incompatible_plan,
            source_conversation_id=conversation_id,
            approval_disabler=disabler,
        ).recover()
        == 1
    )

    assert order == ["disable"]
    assert disabler.actions == [inserted.action.id]
    cancelled = await store.get(inserted.action.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.attempts == 0


@postgres
async def test_incompatible_undelivered_approval_cancels_and_delivers_inactive(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-incompatible-undelivered-{uuid4()}"
    store, _, inserted, _, _ = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
        mark_delivered=False,
    )
    _, incompatible_plan = _plan(provider)
    discord = _DisableDiscord(DeliverySucceeded("unused", 1))

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", _RecoveryGoogle()),
            plan=incompatible_plan,
            source_conversation_id=conversation_id,
            approval_disabler=ApprovalRecoveryDisabler(
                actions=store,
                discord=cast("Any", discord),
            ),
        ).recover()
        == 1
    )

    cancelled = await store.get(inserted.action.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.attempts == 0
    assert discord.calls == []
    approval_delivery = _ApprovalDelivery()
    delivery = ApprovalAwareDiscordDelivery(
        actions=store,
        plan=incompatible_plan,
        discord=cast("Any", approval_delivery),
    )
    pending = await MessageStore(engine).pending_delivery(
        source_conversation_id=conversation_id,
        limit=10,
    )
    approval_message = next(item for item in pending if item.id == inserted.message_id)
    result = await delivery.create_message(
        persisted_message_id=approval_message.id,
        content=approval_message.text,
    )

    assert isinstance(result, DeliverySucceeded)
    expected = render_inactive_approval(
        inserted.action.id,
        inserted.action.tool_name,
        inserted.action.arguments,
        approval_message.text,
    )
    assert approval_delivery.calls == [
        {
            "action_id": inserted.action.id,
            "approval_message_id": inserted.message_id,
            "content": approval_message.text,
            "attachment_name": expected.attachment.filename,
            "attachment_media_type": expected.attachment.media_type,
            "attachment_content": expected.attachment.content,
            "disabled": True,
        }
    ]


@postgres
async def test_recovery_disabler_uses_exact_durable_relation_and_fails_closed(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-recovery-disabler-{uuid4()}"
    store, _, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    claimed = await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id=discord_message_id,
        source_conversation_id=conversation_id,
    )
    assert claimed.applied
    succeeded = _DisableDiscord(DeliverySucceeded(discord_message_id, 1))
    await ApprovalRecoveryDisabler(
        actions=store,
        discord=cast("Any", succeeded),
    )(claimed.action)
    assert succeeded.calls == [
        {
            "action_id": inserted.action.id,
            "approval_message_id": inserted.message_id,
            "discord_message_id": discord_message_id,
        }
    ]

    failed = _DisableDiscord(
        DeliveryFailed(
            DeliveryFailureKind.TRANSPORT,
            attempts=3,
            retryable=True,
            ambiguous=True,
        )
    )
    with pytest.raises(
        RuntimeError,
        match="approval Discord components could not be disabled",
    ):
        await ApprovalRecoveryDisabler(
            actions=store,
            discord=cast("Any", failed),
        )(claimed.action)
    unchanged = await store.get(inserted.action.id)
    assert unchanged is not None
    assert unchanged.status == "executing"
    assert unchanged.attempts == 0
    assert provider.effects == []
    await store.requeue_after_proved_absence(
        inserted.action.id,
        actual_external_attempts=0,
        max_external_attempts=4,
    )
    await store.cancel_nonexecuting(
        action_id=inserted.action.id,
        result={"type": "test_cleanup_v1", "reason_code": "synthetic-no-entry"},
    )


@postgres
async def test_restart_before_entry_without_component_disabler_fails_closed(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-no-disabler-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id=discord_message_id,
        source_conversation_id=conversation_id,
    )

    with pytest.raises(
        RuntimeError,
        match="approved recovery requires a Discord component disabler",
    ):
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", _RecoveryGoogle()),
            plan=plan,
            source_conversation_id=conversation_id,
        ).recover()
    unchanged = await store.get(inserted.action.id)
    assert unchanged is not None
    assert unchanged.status == "executing"
    assert unchanged.attempts == 0
    assert provider.effects == []
    await store.requeue_after_proved_absence(
        inserted.action.id,
        actual_external_attempts=0,
        max_external_attempts=plan.grant(SEND_ID).limits.max_attempts,
    )
    await store.cancel_nonexecuting(
        action_id=inserted.action.id,
        result={
            "type": "test_cleanup_v1",
            "reason_code": "synthetic-no-entry",
        },
    )


@postgres
async def test_restart_after_executor_entry_reconciles_before_bounded_repeat(
    engine: AsyncEngine,
) -> None:
    order: list[str] = []
    provider = _Provider(order=order, mode="recovery")
    conversation_id = f"approval-post-entry-restart-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    provider.store = store
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )
    claimed = await handler.claim_and_acknowledge(
        cast("Any", _InteractionEvent(order)),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None
    assert not await handler.complete(claimed)
    interrupted = await store.get(inserted.action.id)
    assert interrupted is not None
    assert interrupted.status == "executing"
    assert interrupted.attempts == 1
    assert interrupted.recovered_external_attempts == 1

    provider.mode = "success"
    reconciliation = _RecoveryGoogle(
        ReconciliationResult("absent", "complete-thread-proved-absence"),
        order,
    )
    recovered = await ActionRecovery(
        actions=store,
        google_write=cast("Any", reconciliation),
        plan=plan,
        source_conversation_id=conversation_id,
    ).recover()

    assert recovered >= 1
    assert order == ["ack", "executor", "reconcile", "executor"]
    assert reconciliation.send_reconciliations == 1
    assert provider.effects == [inserted.action.id, inserted.action.id]
    assert provider.entry_attempts == [1, 2]
    terminal = await store.get(inserted.action.id)
    assert terminal is not None
    assert terminal.status == "succeeded"
    assert terminal.attempts == ACTION_MAX_ATTEMPTS


@postgres
async def test_startup_repairs_missing_terminal_resolution_once(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    conversation_id = f"approval-resolution-repair-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    provider.store = store
    decision = await store.claim_approval(
        action_id=inserted.action.id,
        approval_message_id=inserted.message_id,
        discord_message_id=discord_message_id,
        source_conversation_id=conversation_id,
    )
    assert decision.applied
    await _execute_preclaimed(store, plan, inserted.action.id)
    terminal = await store.get(inserted.action.id)
    assert terminal is not None
    assert terminal.status == "succeeded"
    async with engine.connect() as connection:
        before = await connection.scalar(
            select(message.c.id).where(
                message.c.source == "action",
                message.c.source_message_id == f"{inserted.action.id}:succeeded",
            )
        )
    assert before is None

    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", _RecoveryGoogle()),
        plan=plan,
        source_conversation_id=conversation_id,
    )
    assert await recovery.recover() >= 1
    assert await recovery.recover() == 0
    async with engine.connect() as connection:
        reports = (
            (
                await connection.execute(
                    select(message).where(
                        message.c.source == "action",
                        message.c.source_message_id
                        == f"{inserted.action.id}:succeeded",
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(reports) == 1
    assert "Status: succeeded" in reports[0]["text"]


@postgres
async def test_unresolved_approved_send_becomes_uncertain_without_repeat(
    engine: AsyncEngine,
) -> None:
    provider = _Provider(mode="recovery")
    conversation_id = f"approval-terminal-uncertain-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    provider.store = store
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )
    claimed = await handler.claim_and_acknowledge(
        cast("Any", _InteractionEvent([])),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None
    assert not await handler.complete(claimed)
    reconciliation = _RecoveryGoogle(
        ReconciliationResult("uncertain", "gmail-send-conflicting-exact-matches")
    )
    recovery = ActionRecovery(
        actions=store,
        google_write=cast("Any", reconciliation),
        plan=plan,
        source_conversation_id=conversation_id,
    )

    assert await recovery.recover() >= 1
    assert await recovery.recover() == 0
    terminal = await store.get(inserted.action.id)
    assert terminal is not None
    assert terminal.status == "uncertain"
    assert terminal.attempts == 1
    assert terminal.result is not None
    assert terminal.result["evidence_code"] == ("gmail-send-conflicting-exact-matches")
    assert provider.effects == [inserted.action.id]
    assert reconciliation.send_reconciliations == 1
    async with engine.connect() as connection:
        text = await connection.scalar(
            select(message.c.text).where(
                message.c.source == "action",
                message.c.source_message_id == f"{inserted.action.id}:uncertain",
            )
        )
    assert isinstance(text, str)
    assert "inspect the current provider state" in text


@postgres
async def test_approved_send_attempt_ceiling_fails_without_third_entry(
    engine: AsyncEngine,
) -> None:
    provider = _Provider(mode="recovery")
    conversation_id = f"approval-attempt-ceiling-{uuid4()}"
    store, plan, inserted, _, discord_message_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=conversation_id,
    )
    provider.store = store
    handler = ApprovalActionHandler(
        actions=store,
        plan=plan,
        source_conversation_id=conversation_id,
    )
    claimed = await handler.claim_and_acknowledge(
        cast("Any", _InteractionEvent([])),
        _interaction(
            inserted,
            discord_message_id,
            ApprovalComponentDecision.APPROVE,
        ),
    )
    assert claimed is not None
    assert not await handler.complete(claimed)
    reconciliation = _RecoveryGoogle(
        ReconciliationResult("absent", "complete-thread-proved-absence")
    )

    assert (
        await ActionRecovery(
            actions=store,
            google_write=cast("Any", reconciliation),
            plan=plan,
            source_conversation_id=conversation_id,
        ).recover()
        >= 1
    )
    terminal = await store.get(inserted.action.id)
    assert terminal is not None
    assert terminal.status == "failed"
    assert terminal.attempts == ACTION_MAX_ATTEMPTS
    assert terminal.result == {
        "type": "Failure",
        "error": {"type": "BudgetExceeded"},
    }
    assert provider.effects == [inserted.action.id, inserted.action.id]
    assert provider.entry_attempts == [1, 2]
    assert reconciliation.send_reconciliations == 2


@postgres
async def test_cross_action_approval_message_relation_cannot_claim_either_action(
    engine: AsyncEngine,
) -> None:
    provider = _Provider()
    first_conversation = f"approval-cross-one-{uuid4()}"
    second_conversation = f"approval-cross-two-{uuid4()}"
    first_store, first_plan, first, _, _ = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=first_conversation,
    )
    second_store, _, second, _, second_discord_id = await _insert_approval(
        engine,
        provider=provider,
        conversation_id=second_conversation,
    )
    handler = ApprovalActionHandler(
        actions=first_store,
        plan=first_plan,
        source_conversation_id=first_conversation,
    )
    event = _InteractionEvent([])

    assert (
        await handler.claim_and_acknowledge(
            cast("Any", event),
            DiscordApprovalInteraction(
                action_id=first.action.id,
                approval_message_id=second.message_id,
                decision=ApprovalComponentDecision.APPROVE,
                discord_message_id=second_discord_id,
            ),
        )
        is None
    )
    assert not event.response.done
    first_current = await first_store.get(first.action.id)
    second_current = await second_store.get(second.action.id)
    assert first_current is not None and first_current.status == "awaiting_approval"
    assert second_current is not None and second_current.status == "awaiting_approval"
    assert first_current.attempts == second_current.attempts == 0
    assert provider.effects == []


@postgres
async def test_shutdown_drains_approved_write_and_its_durable_result(
    tmp_path: Path,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    channel_id = int(uuid4().hex[:12], 16)
    settings = service_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "discord": settings.discord.model_copy(update={"channel_id": channel_id})
        }
    )
    ready: asyncio.Future[tuple[LocalGateway, UUID, asyncio.Task[None]]] = (
        asyncio.get_running_loop().create_future()
    )

    async def owned() -> None:
        async with httpx.AsyncClient() as http:

            class Provider(_Provider):
                async def gmail_send_draft(
                    self,
                    value: GmailSendDraftInput,
                    effect_id: UUID,
                    attempts: WriteAttemptBudget,
                ) -> WriteResponse[GmailSendDraftSuccess]:
                    entered.set()
                    await release.wait()
                    assert not http.is_closed
                    return await super().gmail_send_draft(value, effect_id, attempts)

            provider = Provider()
            async with deployment_ownership(engine) as database:
                store, plan, inserted, _, discord_id = await _insert_approval(
                    cast(Any, database),
                    provider=provider,
                    conversation_id=str(channel_id),
                )
                paused_path = tmp_path / "paused.json"
                PausedState.initialize(paused_path)
                service = JarvisService(
                    settings=settings,
                    store=MessageStore(database),
                    paused=PausedState(paused_path),
                    delivery=cast(Any, None),
                    runner=cast(Any, None),
                    approval_handler=ApprovalActionHandler(
                        actions=store, plan=plan, source_conversation_id=str(channel_id)
                    ),
                )
                gateway = LocalGateway(service, settings)
                event = cast(
                    discord.Interaction,
                    SimpleNamespace(
                        type=discord.InteractionType.component,
                        data={
                            "component_type": 2,
                            "custom_id": approval_custom_id(
                                inserted.action.id,
                                inserted.message_id,
                                ApprovalComponentDecision.APPROVE,
                            ),
                        },
                        user=SimpleNamespace(id=11, bot=False),
                        guild_id=22,
                        channel_id=channel_id,
                        message=SimpleNamespace(id=int(discord_id)),
                        response=_Response([]),
                    ),
                )
                callback = asyncio.create_task(gateway.on_interaction(event))
                ready.set_result((gateway, inserted.action.id, callback))
                await run_service(service, gateway, "synthetic", asyncio.Event())

    host = asyncio.create_task(owned())
    callback: asyncio.Task[None] | None = None
    try:
        gateway, action_id, callback = await asyncio.wait_for(ready, 2)
        await asyncio.wait_for(entered.wait(), 2)
        host.cancel()
        await asyncio.wait_for(gateway.stopped.wait(), 1)
        try:
            # The real effect is held until after checking its owners stay alive.
            done, _ = await asyncio.wait({host}, timeout=0.05)
            assert not done
            assert not gateway.closed.is_set()
        finally:
            release.set()
            await callback
            with pytest.raises(asyncio.CancelledError):
                await host
        terminal = await ActionStore(engine).get(action_id)
        assert terminal is not None and terminal.status == "succeeded"
        assert terminal.attempts == 1
        async with engine.connect() as connection:
            resolutions = (
                await connection.scalars(
                    select(message.c.id).where(
                        message.c.source == "action",
                        message.c.source_message_id == f"{action_id}:succeeded",
                    )
                )
            ).all()
        assert len(resolutions) == 1
        assert gateway.closed.is_set()
        async with deployment_ownership(engine):
            pass
    finally:
        release.set()
        if not host.done():
            host.cancel()
        await asyncio.gather(host, return_exceptions=True)
        if callback is not None:
            await asyncio.gather(callback, return_exceptions=True)
        await engine.dispose()

"""Approval delivery and execution over immutable durable actions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import discord
from llm_agent_kernel import CancellationToken
from llm_tools import (
    EffectId,
    ExecutionContext,
    FrozenToolPlan,
    ParsedJson,
    Principal,
    RecoveryRequired,
    Scope,
    ToolExecutor,
)

from jarvis.actions import (
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    StoredAction,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.approval import render_approval, render_inactive_approval
from jarvis.discord import (
    ApprovalComponentDecision,
    DeliveryFailed,
    DeliveryResult,
    DiscordApprovalInteraction,
    DiscordCreateMessageClient,
    acknowledge_and_disable_approval,
)
from jarvis.ownership import DeploymentOwnershipDefect
from jarvis.write_dispatch import (
    NoTelemetry,
    action_resolution_text,
    gmail_send_basis_is_current,
    require_current_action_binding,
)
from jarvis.write_tools import GmailSendDraftInput


class ApprovalAwareDiscordDelivery:
    """Rebuild approval components and the full preview from durable state."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        plan: FrozenToolPlan,
        discord: DiscordCreateMessageClient,
    ) -> None:
        self._actions = actions
        self._plan = plan
        self._discord = discord

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult:
        try:
            message_id = UUID(str(persisted_message_id))
        except ValueError:
            return await self._discord.create_message(
                persisted_message_id=persisted_message_id,
                content=content,
            )
        stored = await self._actions.get_by_approval_message(message_id)
        if stored is None:
            return await self._discord.create_message(
                persisted_message_id=persisted_message_id,
                content=content,
            )
        inactive = stored.status == "cancelled"
        if inactive:
            presentation = render_inactive_approval(
                stored.id,
                stored.tool_name,
                stored.arguments,
                content,
            )
        else:
            if stored.status != "awaiting_approval":
                raise RuntimeError("pending approval delivery is not awaiting approval")
            binding = require_current_action_binding(stored, self._plan)
            value = binding.spec.input_type.model_validate(stored.arguments).arguments
            if isinstance(value, GmailSendDraftInput) and not (
                await gmail_send_basis_is_current(self._actions, value)
            ):
                raise RuntimeError("Gmail send lost its immutable creation basis")
            presentation = render_approval(stored.id, stored.tool_name, value)
        if presentation.content != content:
            raise RuntimeError("durable approval message differs from host rendering")
        return await self._discord.create_approval_message(
            action_id=stored.id,
            approval_message_id=message_id,
            content=presentation.content,
            attachment_name=presentation.attachment.filename,
            attachment_media_type=presentation.attachment.media_type,
            attachment_content=presentation.attachment.content,
            disabled=inactive,
        )


class ApprovalRecoveryDisabler:
    """Restore an inactive approval view before recovery changes durable state."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        discord: DiscordCreateMessageClient,
    ) -> None:
        self._actions = actions
        self._discord = discord

    async def __call__(self, action: StoredAction) -> None:
        if action.approval_message_id is None:
            raise RuntimeError("approval action has no approval message")
        discord_message_id = await self._actions.approval_discord_message_id(action.id)
        result = await self._discord.disable_approval_message(
            action_id=action.id,
            approval_message_id=action.approval_message_id,
            discord_message_id=discord_message_id,
        )
        if isinstance(result, DeliveryFailed):
            raise RuntimeError("approval Discord components could not be disabled")


@dataclass(frozen=True, slots=True)
class ClaimedApproval:
    action: StoredAction
    decision: ApprovalComponentDecision


class ApprovalActionHandler:
    """Validate, claim, acknowledge, execute, and report one component click."""

    def __init__(
        self,
        *,
        actions: ActionStore,
        plan: FrozenToolPlan,
        source_conversation_id: str,
    ) -> None:
        self._actions = actions
        self._plan = plan
        self._source_conversation_id = source_conversation_id

    async def claim_and_acknowledge(
        self,
        event: discord.Interaction,
        interaction: DiscordApprovalInteraction,
    ) -> ClaimedApproval | None:
        """Claim exactly one valid decision, then disable both components."""

        try:
            stored = await self._actions.get_by_approval_message(
                interaction.approval_message_id
            )
            if stored is None or stored.id != interaction.action_id:
                return None
            binding = require_current_action_binding(stored, self._plan)
            value = binding.spec.input_type.model_validate(stored.arguments).arguments
            if isinstance(value, GmailSendDraftInput) and not (
                await gmail_send_basis_is_current(self._actions, value)
            ):
                return None
            render_approval(stored.id, stored.tool_name, value)
            if interaction.decision is ApprovalComponentDecision.APPROVE:
                decision = await self._actions.claim_approval(
                    action_id=interaction.action_id,
                    approval_message_id=interaction.approval_message_id,
                    discord_message_id=interaction.discord_message_id,
                    source_conversation_id=self._source_conversation_id,
                )
            else:
                decision = await self._actions.deny_approval(
                    action_id=interaction.action_id,
                    approval_message_id=interaction.approval_message_id,
                    discord_message_id=interaction.discord_message_id,
                    source_conversation_id=self._source_conversation_id,
                )
        except DeploymentOwnershipDefect:
            raise
        except (ActionPersistenceDefect, RuntimeError, ValueError):
            return None
        if not decision.applied:
            return None
        await acknowledge_and_disable_approval(event, interaction)
        return ClaimedApproval(decision.action, interaction.decision)

    async def complete(
        self,
        claimed: ClaimedApproval,
        cancellation: CancellationToken,
    ) -> bool:
        """Execute an approved action or report a denial after acknowledgement."""

        if claimed.decision is ApprovalComponentDecision.DENY:
            await self._report(claimed.action)
            return True
        if cancellation.cancelled:
            return False
        binding = require_current_action_binding(claimed.action, self._plan)
        value = binding.spec.input_type.model_validate(
            claimed.action.arguments
        ).arguments
        if isinstance(value, GmailSendDraftInput) and not (
            await gmail_send_basis_is_current(self._actions, value)
        ):
            raise RuntimeError("approved Gmail send lost its creation basis")
        grant = self._plan.grant(claimed.action.tool_name)
        recorder = ActionPositionRecorder(
            store=self._actions,
            action_id=claimed.action.id,
            implementation_revision=binding.implementation_revision,
            max_external_attempts=grant.limits.max_attempts,
            preclaimed_approval=True,
        )
        try:
            await ToolExecutor.execute(
                binding,
                ParsedJson(claimed.action.arguments),
                ExecutionContext(
                    plan=self._plan,
                    grant=grant,
                    catalog_view=self._plan.catalog_view,
                    position=recorder.position,
                    recorder=recorder,
                    effect_id=EffectId(str(claimed.action.id)),
                    budgets=ExactToolBudgetFactory().create(self._plan),
                    principal=Principal("jarvis-owner"),
                    scope=Scope("approval-write"),
                    cancellation=cancellation,
                    telemetry=NoTelemetry(),
                ),
            )
        except (RecoveryRequired, asyncio.CancelledError):
            return False
        current = await self._actions.get(claimed.action.id)
        if current is None:
            raise RuntimeError("approved action disappeared after execution")
        await self._report(current)
        return True

    async def _report(self, stored: StoredAction) -> None:
        if stored.status not in {"succeeded", "failed", "uncertain", "cancelled"}:
            return
        await self._actions.finish_recovered_origins(
            reports=((stored.id, action_resolution_text(stored)),),
            source_conversation_id=self._source_conversation_id,
        )


__all__ = [
    "ApprovalActionHandler",
    "ApprovalAwareDiscordDelivery",
    "ApprovalRecoveryDisabler",
    "ClaimedApproval",
]

#!/usr/bin/env python3
"""Run the sanitized live Slice 6 Approve/Deny qualification.

This destructive operator workflow sends two synthetic messages to the
authenticated Gmail account and creates, updates, then deletes one event on an
explicitly configured qualification calendar. Every send and every Calendar
mutation is decided by a real configured-owner click received through Discord
Gateway; this file contains no interaction simulation or approval bypass.

The qualified Gmail scopes cannot delete sent mail. After the send checks, Jarvis
posts one host-owned cleanup instruction. The owner must permanently delete the
two synthetic qualification threads in Gmail and empty Trash before the bounded
cleanup wait expires. The workflow verifies their disappearance with readonly
Gmail access, then removes every bot-authored Discord message. Draft and Calendar
cleanup uses its already-qualified narrow connector authority.

Required environment, in addition to normal Jarvis settings:

* ``JARVIS_APPROVALS_LIVE=1``
* ``JARVIS_APPROVALS_IRREVERSIBLE_ACK=send-real-owner-mail-and-mutate-calendar``
* ``JARVIS_APPROVALS_OWNER_SCOPE_ACK=recipient-and-calendar-are-owner-controlled``
* ``JARVIS_APPROVALS_MANUAL_GMAIL_CLEANUP=1``
* ``JARVIS_APPROVALS_RECIPIENT``: the authenticated Gmail profile address
* ``JARVIS_APPROVALS_CALENDAR_ID``: an owner-controlled calendar which is absent
  from ``JARVIS_VERIFIED_OWNER_ONLY_CALENDAR_IDS`` so approval is required

Optional bounded waits are ``JARVIS_APPROVALS_WAIT_SECONDS`` (60..900, default
300) and ``JARVIS_APPROVALS_CLEANUP_WAIT_SECONDS`` (60..1200, default 600).
Use a fresh migrated qualification database and private runtime directory.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from llm_agent_kernel import CancellationToken, require_host_plan
from llm_tools import (
    EffectId,
    ExecutionContext,
    InvocationPosition,
    ParsedJson,
    Principal,
    RecoveryRequired,
    Scope,
    ToolExecutor,
    ToolId,
    raw_input_digest,
)
from pydantic import BaseModel
from sqlalchemy import func, select

from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    ActionPersistenceDefect,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.approval import render_approval
from jarvis.approval_runtime import (
    ApprovalActionHandler,
    ApprovalAwareDiscordDelivery,
    ApprovalRecoveryDisabler,
)
from jarvis.connectors import GoogleTokenManager
from jarvis.db import action, create_engine, memory_log, memory_summary, message
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    EXPECTED_PACKAGE_VERSIONS,
    build_slice5_write_gate,
    build_slice6_definitions,
    verify_runtime_dependencies,
)
from jarvis.discord import (
    DISCORD_API_BASE_URL,
    ApprovalComponentDecision,
    DeliveryResult,
    DeliverySucceeded,
    DiscordApprovalInteraction,
    DiscordCreateMessageClient,
    DiscordGateway,
    DiscordOwnerMessage,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.read_tools import GMAIL_API_BASE_URL
from jarvis.service import flush_pending_deliveries
from jarvis.settings import Settings
from jarvis.write_composition import Slice6Composition, build_slice6_composition
from jarvis.write_connectors import (
    ReconciliationResult,
    calendar_event_id,
    gmail_effect_id,
)
from jarvis.write_dispatch import ActionRecovery, NoTelemetry
from jarvis.write_policy import classify_write
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarCreateEventSuccess,
    CalendarDeleteEventInput,
    CalendarDeleteEventSuccess,
    CalendarUpdateEventInput,
    CalendarUpdateEventSuccess,
    CalendarWritableEvent,
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    GmailSendDraftInput,
    GmailSendDraftSuccess,
    GmailUpdateDraftInput,
    Mailbox,
    TimedEventTime,
)

_LIVE_ENVIRONMENT = "JARVIS_APPROVALS_LIVE"
_IRREVERSIBLE_ACK = "send-real-owner-mail-and-mutate-calendar"
_OWNER_SCOPE_ACK = "recipient-and-calendar-are-owner-controlled"
_DECISIONS = (
    "gmail_normal_approve",
    "gmail_lost_response_approve",
    "gmail_mismatch_approve",
    "calendar_first_identical_deny",
    "calendar_second_identical_deny",
    "calendar_create_approve",
    "calendar_update_approve",
    "calendar_delete_approve",
)
_GMAIL_POLL_SECONDS = 2.0
_DISCORD_CLEANUP_MAX_ATTEMPTS = 3
_DISCORD_CLEANUP_MAX_MESSAGES = 100
_DISCORD_CLEANUP_MAX_RETRY_AFTER_SECONDS = 30.0
_DISCORD_CLEANUP_MAX_TOTAL_DELAY_SECONDS = 120.0
_DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS = 1.0


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, reason_code: str) -> None:
        super().__init__(stage)
        self.stage = stage
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class LiveArguments:
    recipient: str = field(repr=False)
    calendar_id: str = field(repr=False)
    approval_wait_seconds: float
    cleanup_wait_seconds: float


@dataclass(slots=True)
class Artifacts:
    gmail_draft_ids: set[str] = field(default_factory=lambda: set[str](), repr=False)
    gmail_sent_message_ids: set[str] = field(
        default_factory=lambda: set[str](), repr=False
    )
    gmail_sent_thread_ids: set[str] = field(
        default_factory=lambda: set[str](), repr=False
    )
    calendar_event_ids: set[str] = field(default_factory=lambda: set[str](), repr=False)
    discord_message_ids: set[str] = field(
        default_factory=lambda: set[str](), repr=False
    )


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    action_id: UUID
    decision: ApprovalComponentDecision
    completed_in_handler: bool
    error_code: str | None


@dataclass(slots=True)
class LostAcceptedSendTransport(httpx.AsyncBaseTransport):
    """Lose exactly one successful Gmail-send response after provider acceptance."""

    inner: httpx.AsyncBaseTransport
    armed: bool = False
    accepted_losses: int = 0
    send_requests: int = 0

    def arm(self) -> None:
        if self.armed:
            raise RuntimeError("lost-response transport is already armed")
        self.armed = True

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        is_send = (
            request.method == "POST"
            and request.url.path == "/gmail/v1/users/me/drafts/send"
        )
        if is_send:
            self.send_requests += 1
        response = await self.inner.handle_async_request(request)
        if not is_send or not self.armed or not 200 <= response.status_code < 300:
            return response
        self.armed = False
        self.accepted_losses += 1
        await response.aread()
        await response.aclose()
        raise httpx.ReadTimeout(
            "injected accepted Gmail send response loss",
            request=request,
        )

    async def aclose(self) -> None:
        await self.inner.aclose()


class _RecordingOrdinaryDelivery:
    def __init__(
        self,
        discord: DiscordCreateMessageClient,
        artifacts: Artifacts,
    ) -> None:
        self._discord = discord
        self._artifacts = artifacts

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult:
        result = await self._discord.create_message(
            persisted_message_id=persisted_message_id,
            content=content,
        )
        if isinstance(result, DeliverySucceeded):
            self._artifacts.discord_message_ids.add(result.discord_message_id)
        return result


class _RecordingApprovalDelivery:
    def __init__(
        self,
        discord: DiscordCreateMessageClient,
        artifacts: Artifacts,
    ) -> None:
        self._discord = discord
        self._artifacts = artifacts

    async def create_approval_message(
        self,
        *,
        action_id: UUID,
        approval_message_id: UUID,
        content: str,
        attachment_name: str,
        attachment_media_type: str,
        attachment_content: bytes,
        disabled: bool = False,
    ) -> DeliveryResult:
        result = await self._discord.create_approval_message(
            action_id=action_id,
            approval_message_id=approval_message_id,
            content=content,
            attachment_name=attachment_name,
            attachment_media_type=attachment_media_type,
            attachment_content=attachment_content,
            disabled=disabled,
        )
        if isinstance(result, DeliverySucceeded):
            self._artifacts.discord_message_ids.add(result.discord_message_id)
        return result


class LiveApprovalSession:
    """Route only real configured-owner Gateway components to production handling."""

    def __init__(
        self,
        *,
        settings: Settings,
        actions: ActionStore,
        messages: MessageStore,
        plan: Any,
        discord: DiscordCreateMessageClient,
        wait_seconds: float,
        artifacts: Artifacts,
    ) -> None:
        self._settings = settings
        self._actions = actions
        self._messages = messages
        self._handler = ApprovalActionHandler(
            actions=actions,
            plan=plan,
            source_conversation_id=str(settings.discord.channel_id),
        )
        self._delivery = ApprovalAwareDiscordDelivery(
            actions=actions,
            plan=plan,
            discord=cast(
                "DiscordCreateMessageClient",
                _RecordingApprovalDelivery(discord, artifacts),
            ),
            ordinary=_RecordingOrdinaryDelivery(discord, artifacts),
        )
        self._wait_seconds = wait_seconds
        self._artifacts = artifacts
        self._results: asyncio.Queue[ApprovalResult] = asyncio.Queue()

    async def owner_message(self, incoming: DiscordOwnerMessage) -> None:
        del incoming

    async def interaction(
        self,
        event: Any,
        interaction: DiscordApprovalInteraction,
    ) -> None:
        claimed = await self._handler.claim_and_acknowledge(event, interaction)
        if claimed is None:
            return
        try:
            completed = await self._handler.complete(claimed)
        except Exception:
            await self._results.put(
                ApprovalResult(
                    claimed.action.id,
                    claimed.decision,
                    False,
                    "execution_exception",
                )
            )
            return
        await self._results.put(
            ApprovalResult(
                claimed.action.id,
                claimed.decision,
                completed,
                None,
            )
        )

    async def deliver(self, action_id: UUID) -> None:
        stored = await self._actions.get(action_id)
        if stored is None or stored.approval_message_id is None:
            raise QualificationFailure("discord", "approval_relation_missing")
        result = await flush_pending_deliveries(
            store=self._messages,
            delivery=self._delivery,
            source_conversation_id=str(self._settings.discord.channel_id),
            limit=100,
        )
        if (
            result.selected < 1
            or result.delivered != result.selected
            or result.failure is not None
        ):
            raise QualificationFailure("discord", "approval_delivery_failed")
        try:
            discord_message_id = await self._actions.approval_discord_message_id(
                action_id
            )
        except ActionPersistenceDefect:
            raise QualificationFailure(
                "discord", "approval_delivery_relation_missing"
            ) from None
        self._artifacts.discord_message_ids.add(discord_message_id)

    async def flush(self) -> None:
        result = await flush_pending_deliveries(
            store=self._messages,
            delivery=self._delivery,
            source_conversation_id=str(self._settings.discord.channel_id),
            limit=100,
        )
        if result.delivered != result.selected or result.failure is not None:
            raise QualificationFailure("discord", "resolution_delivery_failed")

    async def wait(
        self,
        action_id: UUID,
        expected: ApprovalComponentDecision,
    ) -> ApprovalResult:
        while True:
            try:
                result = await asyncio.wait_for(
                    self._results.get(),
                    timeout=self._wait_seconds,
                )
            except TimeoutError:
                raise QualificationFailure(
                    "discord", "owner_decision_timeout"
                ) from None
            if result.action_id != action_id:
                continue
            if result.decision is not expected:
                raise QualificationFailure("discord", "unexpected_owner_decision")
            if result.error_code is not None:
                raise QualificationFailure("approval", result.error_code)
            return result


def _bounded_seconds(
    environment: Mapping[str, str],
    name: str,
    *,
    default: float,
    maximum: float,
) -> float:
    raw = environment.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a finite bounded number") from None
    if not 60.0 <= value <= maximum:
        raise ValueError(f"{name} must be between 60 and {maximum:g}")
    return value


def live_arguments(environment: Mapping[str, str]) -> LiveArguments:
    if environment.get(_LIVE_ENVIRONMENT) != "1":
        raise ValueError(f"live qualification requires {_LIVE_ENVIRONMENT}=1")
    if environment.get("JARVIS_APPROVALS_IRREVERSIBLE_ACK") != _IRREVERSIBLE_ACK:
        raise ValueError("live qualification irreversible acknowledgement is absent")
    if environment.get("JARVIS_APPROVALS_OWNER_SCOPE_ACK") != _OWNER_SCOPE_ACK:
        raise ValueError("live qualification owner-scope acknowledgement is absent")
    if environment.get("JARVIS_APPROVALS_MANUAL_GMAIL_CLEANUP") != "1":
        raise ValueError("manual Gmail cleanup acknowledgement is absent")
    private: dict[str, str] = {}
    for name in ("JARVIS_APPROVALS_RECIPIENT", "JARVIS_APPROVALS_CALENDAR_ID"):
        value = environment.get(name)
        if value is None or not value or value != value.strip():
            raise ValueError(f"{name} must be non-empty without edge whitespace")
        private[name] = value
    return LiveArguments(
        recipient=private["JARVIS_APPROVALS_RECIPIENT"],
        calendar_id=private["JARVIS_APPROVALS_CALENDAR_ID"],
        approval_wait_seconds=_bounded_seconds(
            environment,
            "JARVIS_APPROVALS_WAIT_SECONDS",
            default=300.0,
            maximum=900.0,
        ),
        cleanup_wait_seconds=_bounded_seconds(
            environment,
            "JARVIS_APPROVALS_CLEANUP_WAIT_SECONDS",
            default=600.0,
            maximum=1200.0,
        ),
    )


def _implementation() -> dict[str, str]:
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    return {
        "architecture": platform.machine().lower(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "os": platform.system().lower(),
    }


def assert_sanitized_output(
    result: dict[str, object], forbidden_values: tuple[str, ...]
) -> None:
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if any(value and value in encoded for value in forbidden_values):
        raise QualificationFailure("output", "private_value_exposed")


def validate_result_evidence(result: dict[str, object]) -> None:
    expected = {
        "actions",
        "approvals",
        "calendar",
        "cleanup",
        "dependencies",
        "gmail",
        "implementation",
        "status",
    }
    if set(result) != expected or result.get("status") != "passed":
        raise QualificationFailure("result", "evidence_shape_changed")
    approvals_value = result.get("approvals")
    actions_value = result.get("actions")
    gmail_value = result.get("gmail")
    calendar_value = result.get("calendar")
    cleanup_value = result.get("cleanup")
    approvals = (
        cast("dict[str, object]", approvals_value)
        if isinstance(approvals_value, dict)
        else None
    )
    actions = (
        cast("dict[str, object]", actions_value)
        if isinstance(actions_value, dict)
        else None
    )
    gmail = (
        cast("dict[str, object]", gmail_value)
        if isinstance(gmail_value, dict)
        else None
    )
    calendar = (
        cast("dict[str, object]", calendar_value)
        if isinstance(calendar_value, dict)
        else None
    )
    cleanup = (
        cast("dict[str, object]", cleanup_value)
        if isinstance(cleanup_value, dict)
        else None
    )
    if actions != {
        "identical_arguments_remained_distinct": True,
        "one_durable_effect_per_approval": True,
        "rows": 12,
    }:
        raise QualificationFailure("result", "action_evidence_incomplete")
    if approvals != {
        "approve": 6,
        "deny": 2,
        "real_owner_components": 8,
    }:
        raise QualificationFailure("result", "approval_evidence_incomplete")
    if gmail != {
        "accepted_send_lost_response_reconciled_once": True,
        "draft_mismatch_sent_nothing": True,
        "lost_response_exactly_one_recipient_copy": True,
        "normal_send_exactly_one_recipient_copy": True,
        "stable_creation_effect_header": True,
    }:
        raise QualificationFailure("result", "gmail_evidence_incomplete")
    if calendar != {
        "approved_unknown_calendar_create_update_delete": True,
        "denied_actions_had_no_effect": True,
        "exact_render_and_reconciliation": True,
    }:
        raise QualificationFailure("result", "calendar_evidence_incomplete")
    if cleanup != {
        "calendar": True,
        "discord": True,
        "gmail_drafts": True,
        "gmail_sent": True,
    }:
        raise QualificationFailure("result", "cleanup_evidence_incomplete")
    dependencies = result.get("dependencies")
    if dependencies != {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS}:
        raise QualificationFailure("result", "dependency_evidence_incomplete")
    implementation_value = result.get("implementation")
    if not isinstance(implementation_value, dict):
        raise QualificationFailure("result", "implementation_evidence_incomplete")
    implementation = cast("dict[str, object]", implementation_value)
    if set(implementation) != {
        "architecture",
        "lock_sha256",
        "main_definition_fingerprint",
        "main_plan_revision",
        "os",
        "session_compatibility_revision",
    } or any(
        not isinstance(value, str) or not value for value in implementation.values()
    ):
        raise QualificationFailure("result", "implementation_evidence_incomplete")


async def _require_empty_database(engine: Any) -> None:
    async with engine.connect() as connection:
        counts: list[int] = []
        for table in (message, memory_log, memory_summary, action):
            counts.append(
                cast(
                    int,
                    await connection.scalar(select(func.count()).select_from(table)),
                )
            )
    if counts != [0, 0, 0, 0]:
        raise ValueError("live approval qualification database must be empty")


async def _origin(messages: MessageStore, conversation_id: str, stage: str) -> UUID:
    inserted = await messages.insert_waking(
        role="owner",
        text=f"Explicitly run the synthetic Slice 6 {stage} qualification step.",
        source="qualification",
        source_conversation_id=conversation_id,
        source_message_id=str(uuid4()),
        created_at=datetime.now(UTC),
    )
    if not inserted.inserted:
        raise QualificationFailure(stage, "origin_not_inserted")
    return inserted.message.id


def _contract(
    *,
    binding: Any,
    plan: Any,
    arguments: dict[str, object],
    origin_id: UUID,
    stage: str,
) -> ExecutionContract:
    return ExecutionContract(
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
        tool_effect=binding.spec.effect,
        replay_policy=binding.replay_policy,
        input_digest=raw_input_digest(ParsedJson(arguments)),
        max_attempts=ACTION_MAX_ATTEMPTS,
        claim_id=f"slice6-live-{stage}-{uuid4()}",
        through_checkpoint=str(origin_id),
        model_step_ordinal=1,
        input_message_ids=(str(origin_id),),
        write_gate_supporting_owner_message_ids=(str(origin_id),),
    )


async def _execute_automatic(
    *,
    actions: ActionStore,
    messages: MessageStore,
    conversation_id: str,
    plan: Any,
    tool_id: ToolId,
    value: BaseModel,
    action_id: UUID,
    stage: str,
) -> dict[str, object]:
    binding = plan.catalog_view.binding(tool_id)
    grant = plan.grant(tool_id)
    arguments = cast("dict[str, object]", value.model_dump(mode="json"))
    origin_id = await _origin(messages, conversation_id, stage)
    contract = _contract(
        binding=binding,
        plan=plan,
        arguments=arguments,
        origin_id=origin_id,
        stage=stage,
    )
    await actions.insert_automatic(
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin_id,
        action_id=action_id,
    )
    recorder = ActionPositionRecorder(
        store=actions,
        action_id=action_id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=grant.limits.max_attempts,
    )
    try:
        result = await ToolExecutor.execute(
            binding,
            ParsedJson(arguments),
            ExecutionContext(
                plan=plan,
                grant=grant,
                catalog_view=plan.catalog_view,
                position=InvocationPosition(str(action_id)),
                recorder=recorder,
                effect_id=EffectId(str(action_id)),
                budgets=ExactToolBudgetFactory().create(plan),
                principal=Principal("jarvis-owner"),
                scope=Scope("slice6-live-qualification-automatic"),
                cancellation=CancellationToken(),
                telemetry=NoTelemetry(),
            ),
        )
    except RecoveryRequired:
        raise QualificationFailure(stage, "unexpected_recovery") from None
    stored = await actions.get(action_id)
    if (
        result.get("type") != "Success"
        or not isinstance(result.get("value"), dict)
        or stored is None
        or stored.status != "succeeded"
        or stored.attempts != 1
        or stored.result != result
    ):
        raise QualificationFailure(stage, "automatic_execution_failed")
    return cast("dict[str, object]", result["value"])


async def _persist_approval(
    *,
    actions: ActionStore,
    messages: MessageStore,
    conversation_id: str,
    plan: Any,
    tool_id: ToolId,
    value: BaseModel,
    stage: str,
) -> UUID:
    binding = plan.catalog_view.binding(tool_id)
    arguments = cast("dict[str, object]", value.model_dump(mode="json"))
    origin_id = await _origin(messages, conversation_id, stage)
    action_id = uuid4()
    presentation = render_approval(action_id, tool_id, value)
    inserted = await actions.insert_awaiting_approval(
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=_contract(
            binding=binding,
            plan=plan,
            arguments=arguments,
            origin_id=origin_id,
            stage=stage,
        ),
        origin_message_id=origin_id,
        approval_text=presentation.content,
        source_conversation_id=conversation_id,
        action_id=action_id,
    )
    if (
        inserted.action.id != action_id
        or inserted.action.status != "awaiting_approval"
        or inserted.action.approval_message_id != inserted.message_id
    ):
        raise QualificationFailure(stage, "approval_insert_failed")
    return action_id


def _gmail_content(recipient: str, marker: str) -> GmailContent:
    return GmailContent(
        to=(Mailbox(name=None, address=recipient),),
        cc=(),
        bcc=(),
        subject=f"Synthetic Jarvis Slice 6 {marker}",
        body_text=f"Synthetic owner-only Slice 6 qualification body: {marker}.",
        reply_to=None,
    )


async def _create_draft(
    *,
    actions: ActionStore,
    messages: MessageStore,
    conversation_id: str,
    plan: Any,
    recipient: str,
    marker: str,
    artifacts: Artifacts,
) -> tuple[GmailCreateDraftInput, GmailDraftSuccess, UUID]:
    value = GmailCreateDraftInput(content=_gmail_content(recipient, marker))
    action_id = uuid4()
    result = GmailDraftSuccess.model_validate(
        await _execute_automatic(
            actions=actions,
            messages=messages,
            conversation_id=conversation_id,
            plan=plan,
            tool_id=ToolId("gmail.create_draft"),
            value=value,
            action_id=action_id,
            stage=f"{marker}-draft-create",
        )
    )
    if result.jarvis_effect_id != gmail_effect_id(action_id):
        raise QualificationFailure(marker, "gmail_effect_identity_changed")
    artifacts.gmail_draft_ids.add(result.draft_id)
    return value, result, action_id


def _send_value(
    created: GmailDraftSuccess,
    content: GmailContent,
) -> GmailSendDraftInput:
    return GmailSendDraftInput(
        draft_id=created.draft_id,
        thread_id=created.thread_id,
        jarvis_effect_id=created.jarvis_effect_id,
        content=content,
    )


async def _require_terminal(
    actions: ActionStore,
    action_id: UUID,
    status: Literal["succeeded", "failed", "cancelled"],
) -> dict[str, object]:
    stored = await actions.get(action_id)
    if (
        stored is None
        or stored.status != status
        or stored.result is None
        or stored.attempts != (0 if status == "cancelled" else 1)
    ):
        raise QualificationFailure("action", "terminal_state_invalid")
    return stored.result


async def _google_json(
    client: httpx.AsyncClient,
    tokens: GoogleTokenManager,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
) -> tuple[int, dict[str, object] | None]:
    token, _ = await tokens.access_token()
    response = await client.request(
        method,
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
        timeout=httpx.Timeout(8.0, connect=3.0),
    )
    if response.status_code in {204, 404, 410}:
        return response.status_code, None
    if response.status_code != 200:
        raise QualificationFailure("google", "unexpected_provider_status")
    try:
        value = cast(object, response.json())
    except ValueError:
        raise QualificationFailure("google", "invalid_provider_response") from None
    if not isinstance(value, dict):
        raise QualificationFailure("google", "invalid_provider_response")
    return response.status_code, cast("dict[str, object]", value)


async def _verify_authenticated_recipient(
    client: httpx.AsyncClient,
    tokens: GoogleTokenManager,
    recipient: str,
) -> None:
    _, payload = await _google_json(
        client,
        tokens,
        "GET",
        f"{GMAIL_API_BASE_URL}/users/me/profile",
    )
    if payload is None or payload.get("emailAddress") != recipient:
        raise QualificationFailure("setup", "recipient_is_not_authenticated_owner")


async def _verify_one_recipient_copy(
    client: httpx.AsyncClient,
    tokens: GoogleTokenManager,
    result: GmailSendDraftSuccess,
) -> None:
    for _ in range(15):
        _, payload = await _google_json(
            client,
            tokens,
            "GET",
            f"{GMAIL_API_BASE_URL}/users/me/threads/{quote(result.thread_id, safe='')}",
            params={"format": "minimal"},
        )
        messages = None if payload is None else payload.get("messages")
        if isinstance(messages, list):
            inbox = 0
            sent = 0
            for raw_item in cast("list[object]", messages):
                if not isinstance(raw_item, dict):
                    continue
                item = cast("dict[str, object]", raw_item)
                raw_labels = item.get("labelIds")
                if not isinstance(raw_labels, list):
                    continue
                labels = cast("list[object]", raw_labels)
                inbox += int("INBOX" in labels)
                sent += int("SENT" in labels)
            if inbox == 1 and sent == 1:
                return
            if inbox > 1 or sent > 1:
                break
        await asyncio.sleep(_GMAIL_POLL_SECONDS)
    raise QualificationFailure("gmail", "recipient_copy_count_changed")


async def _delete_drafts(
    client: httpx.AsyncClient,
    tokens: GoogleTokenManager,
    artifacts: Artifacts,
) -> None:
    failures = 0
    for draft_id in sorted(artifacts.gmail_draft_ids):
        try:
            status, _ = await _google_json(
                client,
                tokens,
                "DELETE",
                f"{GMAIL_API_BASE_URL}/users/me/drafts/{quote(draft_id, safe='')}",
            )
        except (httpx.RequestError, QualificationFailure):
            failures += 1
        else:
            failures += int(status not in {204, 404, 410})
    if failures:
        raise QualificationFailure("cleanup", "gmail_draft_cleanup_failed")


async def _post_cleanup_instruction(
    discord: DiscordCreateMessageClient,
    artifacts: Artifacts,
) -> None:
    persisted = uuid4()
    result = await discord.create_message(
        persisted_message_id=persisted,
        content=(
            "Slice 6 qualification cleanup: permanently delete every synthetic "
            "Slice 6 qualification email thread from this owner Gmail account, "
            "including Trash. Jarvis is waiting to verify their disappearance."
        ),
    )
    if not isinstance(result, DeliverySucceeded):
        raise QualificationFailure("cleanup", "gmail_cleanup_instruction_failed")
    artifacts.discord_message_ids.add(result.discord_message_id)


async def _wait_for_sent_cleanup(
    client: httpx.AsyncClient,
    tokens: GoogleTokenManager,
    artifacts: Artifacts,
    wait_seconds: float,
) -> None:
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        remaining: set[str] = set()
        for message_id in sorted(artifacts.gmail_sent_message_ids):
            try:
                status, _ = await _google_json(
                    client,
                    tokens,
                    "GET",
                    f"{GMAIL_API_BASE_URL}/users/me/messages/"
                    f"{quote(message_id, safe='')}",
                    params={"format": "minimal"},
                )
            except (httpx.RequestError, QualificationFailure):
                remaining.add(message_id)
                continue
            if status not in {404, 410}:
                remaining.add(message_id)
        for thread_id in sorted(artifacts.gmail_sent_thread_ids):
            try:
                status, _ = await _google_json(
                    client,
                    tokens,
                    "GET",
                    f"{GMAIL_API_BASE_URL}/users/me/threads/"
                    f"{quote(thread_id, safe='')}",
                    params={"format": "minimal"},
                )
            except (httpx.RequestError, QualificationFailure):
                remaining.add(thread_id)
                continue
            if status not in {404, 410}:
                remaining.add(thread_id)
        if not remaining:
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise QualificationFailure("cleanup", "manual_gmail_cleanup_timeout")
        await asyncio.sleep(
            min(5.0, max(0.0, deadline - asyncio.get_running_loop().time()))
        )


async def _cleanup_discord(
    client: httpx.AsyncClient,
    settings: Settings,
    artifacts: Artifacts,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    if len(artifacts.discord_message_ids) > _DISCORD_CLEANUP_MAX_MESSAGES:
        raise QualificationFailure("cleanup", "discord_cleanup_target_bound_exceeded")
    failures = 0
    total_delay = 0.0
    headers = {"Authorization": "Bot " + settings.discord.bot_token.get_secret_value()}
    for message_id in sorted(artifacts.discord_message_ids):
        removed = False
        for attempt in range(1, _DISCORD_CLEANUP_MAX_ATTEMPTS + 1):
            response: httpx.Response | None = None
            try:
                response = await client.delete(
                    f"{DISCORD_API_BASE_URL}/channels/{settings.discord.channel_id}"
                    f"/messages/{message_id}",
                    headers=headers,
                    timeout=httpx.Timeout(8.0, connect=3.0),
                )
            except httpx.RequestError:
                delay = _DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS
            else:
                if response.status_code in {204, 404}:
                    removed = True
                    break
                if response.status_code == 429:
                    delay = _discord_cleanup_retry_after(response)
                    if delay is None:
                        break
                elif response.status_code in {408, 500, 502, 503, 504}:
                    delay = _DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS
                else:
                    break
            if attempt == _DISCORD_CLEANUP_MAX_ATTEMPTS:
                break
            if total_delay + delay > _DISCORD_CLEANUP_MAX_TOTAL_DELAY_SECONDS:
                break
            total_delay += delay
            await sleep(delay)
        failures += int(not removed)
    if failures:
        raise QualificationFailure("cleanup", "discord_cleanup_failed")


def _discord_cleanup_retry_after(response: httpx.Response) -> float | None:
    raw: object = response.headers.get("Retry-After")
    if raw is None:
        try:
            payload = cast(object, response.json())
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            raw = cast("dict[str, object]", payload).get("retry_after")
    if raw is None:
        return _DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS
    if isinstance(raw, bool) or not isinstance(raw, str | int | float):
        return _DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        return _DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS
    if not math.isfinite(delay) or delay < 0.0:
        return _DISCORD_CLEANUP_TRANSIENT_DELAY_SECONDS
    if delay > _DISCORD_CLEANUP_MAX_RETRY_AFTER_SECONDS:
        return None
    return delay


async def _collect_durable_artifacts(engine: Any, artifacts: Artifacts) -> None:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(
                    action.c.id,
                    action.c.tool_name,
                    action.c.arguments,
                    action.c.result,
                )
            )
        ).all()
    created_calendar_ids: set[str] = set()
    deleted_calendar_ids: set[str] = set()
    for action_id, tool_name, raw_arguments, raw_result in rows:
        if tool_name == "calendar.create_event" and isinstance(action_id, UUID):
            created_calendar_ids.add(calendar_event_id(action_id))
        if tool_name == "gmail.send_draft" and isinstance(raw_arguments, dict):
            thread_id = cast("dict[str, object]", raw_arguments).get("thread_id")
            if isinstance(thread_id, str):
                artifacts.gmail_sent_thread_ids.add(thread_id)
        if not isinstance(raw_result, dict):
            continue
        result = cast("dict[str, object]", raw_result)
        raw_value = result.get("value")
        if result.get("type") != "Success" or not isinstance(raw_value, dict):
            continue
        value = cast("dict[str, object]", raw_value)
        if tool_name in {"gmail.create_draft", "gmail.update_draft"}:
            draft_id = value.get("draft_id")
            if isinstance(draft_id, str):
                artifacts.gmail_draft_ids.add(draft_id)
        elif tool_name == "gmail.send_draft":
            message_id = value.get("sent_message_id")
            thread_id = value.get("thread_id")
            if isinstance(message_id, str):
                artifacts.gmail_sent_message_ids.add(message_id)
            if isinstance(thread_id, str):
                artifacts.gmail_sent_thread_ids.add(thread_id)
        elif tool_name == "calendar.delete_event" and isinstance(raw_arguments, dict):
            expected = cast("dict[str, object]", raw_arguments).get("expected")
            if isinstance(expected, dict):
                event_id = cast("dict[str, object]", expected).get("event_id")
                if isinstance(event_id, str):
                    deleted_calendar_ids.add(event_id)
    artifacts.calendar_event_ids.update(
        created_calendar_ids.difference(deleted_calendar_ids)
    )


async def _cleanup_calendar_with_approvals(
    *,
    actions: ActionStore,
    messages: MessageStore,
    composition: Slice6Composition,
    plan: Any,
    session: LiveApprovalSession,
    discord: DiscordCreateMessageClient,
    artifacts: Artifacts,
    calendar_id: str,
    conversation_id: str,
) -> None:
    failures = 0
    for event_id in sorted(artifacts.calendar_event_ids):
        try:
            observed = await composition.google_write.calendar_current_snapshot(
                calendar_id,
                event_id,
            )
            if observed.outcome == "not_found":
                artifacts.calendar_event_ids.discard(event_id)
                continue
            if observed.outcome != "found" or observed.value is None:
                raise QualificationFailure(
                    "cleanup", "calendar_cleanup_snapshot_unavailable"
                )
            value = CalendarDeleteEventInput(
                expected=observed.value,
                notify_attendees=False,
            )
            if (
                classify_write(
                    ToolId("calendar.delete_event"),
                    value,
                    verified_owner_only_calendar_ids=(),
                    live_calendar_event=observed.value,
                )
                != "approval_required"
            ):
                raise QualificationFailure(
                    "cleanup", "calendar_cleanup_approval_policy_changed"
                )
            cleanup_action = await _persist_approval(
                actions=actions,
                messages=messages,
                conversation_id=conversation_id,
                plan=plan,
                tool_id=ToolId("calendar.delete_event"),
                value=value,
                stage="calendar-owner-approved-cleanup",
            )
            await session.deliver(cleanup_action)
            click = await session.wait(
                cleanup_action,
                ApprovalComponentDecision.APPROVE,
            )
            if not click.completed_in_handler:
                await ActionRecovery(
                    actions=actions,
                    google_write=composition.google_write,
                    plan=plan,
                    source_conversation_id=conversation_id,
                    approval_disabler=ApprovalRecoveryDisabler(
                        actions=actions,
                        discord=discord,
                    ),
                ).recover(allow_queued_execution=False)
            await _require_terminal(actions, cleanup_action, "succeeded")
            if (
                await composition.google_write.reconcile_calendar_delete(value)
            ).outcome != "succeeded":
                raise QualificationFailure("cleanup", "calendar_cleanup_not_reconciled")
            artifacts.calendar_event_ids.discard(event_id)
        except Exception:
            failures += 1
    await session.flush()
    if failures:
        raise QualificationFailure("cleanup", "calendar_cleanup_failed")


async def _run(settings: Settings, arguments: LiveArguments) -> dict[str, object]:
    verify_runtime_dependencies()
    if settings.codex_model != "gpt-5.6-terra":
        raise QualificationFailure("setup", "unexpected_model_route")
    if arguments.calendar_id in settings.verified_owner_only_calendar_ids:
        raise QualificationFailure("setup", "calendar_does_not_require_approval")
    engine = create_engine(settings.database_url.get_secret_value())
    await _require_empty_database(engine)
    artifacts = Artifacts()
    result: dict[str, object] | None = None
    primary_error: BaseException | None = None
    composition: Slice6Composition | None = None
    actions: ActionStore | None = None
    messages: MessageStore | None = None
    session: LiveApprovalSession | None = None
    plan: Any | None = None
    gateway: DiscordGateway | None = None
    gateway_task: asyncio.Task[None] | None = None
    cleanup_google_complete = False
    cleanup_discord_complete = False
    manual_gmail_complete = False
    async with AsyncExitStack() as clients:
        oauth_http = await clients.enter_async_context(
            httpx.AsyncClient(trust_env=False, follow_redirects=False)
        )
        transport = LostAcceptedSendTransport(httpx.AsyncHTTPTransport())
        google_http = await clients.enter_async_context(
            httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            )
        )
        maps_http = await clients.enter_async_context(
            httpx.AsyncClient(trust_env=False, follow_redirects=False)
        )
        brave_http = await clients.enter_async_context(
            httpx.AsyncClient(trust_env=False, follow_redirects=False)
        )
        embedding_http = await clients.enter_async_context(
            httpx.AsyncClient(trust_env=False, follow_redirects=False)
        )
        discord_http = await clients.enter_async_context(
            httpx.AsyncClient(trust_env=False, follow_redirects=False)
        )
        tokens = GoogleTokenManager(
            state_path=settings.google_oauth_state_path,
            client=oauth_http,
            client_id=settings.google_oauth_client_id.get_secret_value(),
            client_secret=settings.google_oauth_client_secret.get_secret_value(),
            active_key_version=settings.connector_encryption_key_version,
            configured_keys=settings.connector_encryption_keys.get_secret_value(),
            single_secret=settings.connector_encryption_secret.get_secret_value(),
        )
        discord = DiscordCreateMessageClient(settings.discord, discord_http)
        try:
            async with deployment_ownership(engine):
                actions = ActionStore(engine)
                messages = MessageStore(engine)
                gate, _ = build_slice5_write_gate(
                    profile_key=settings.codex_profile_key,
                    model=settings.codex_model,
                )
                composition = build_slice6_composition(
                    settings=settings,
                    google_oauth_http=oauth_http,
                    google_api_http=google_http,
                    maps_http=maps_http,
                    brave_http=brave_http,
                    memory_repository=PostgresMemoryRepository(engine),
                    memory_embedder=OpenAIEmbedder(
                        settings.embedding_openai_api_key,
                        http_client=embedding_http,
                    ),
                    actions=actions,
                    automatic_write_gate_definition_fingerprint=gate.fingerprint,
                )
                definitions = build_slice6_definitions(
                    catalog=composition.catalog,
                    profile_key=settings.codex_profile_key,
                    model=settings.codex_model,
                    owner_timezone=settings.owner_timezone,
                )
                plan = definitions.plans["main"]
                require_host_plan(plan, definitions.main.maximum_profile)
                await _verify_authenticated_recipient(
                    google_http,
                    tokens,
                    arguments.recipient,
                )
                session = LiveApprovalSession(
                    settings=settings,
                    actions=actions,
                    messages=messages,
                    plan=plan,
                    discord=discord,
                    wait_seconds=arguments.approval_wait_seconds,
                    artifacts=artifacts,
                )
                ready = asyncio.Event()

                async def gateway_ready() -> None:
                    ready.set()

                gateway = DiscordGateway(
                    settings.discord,
                    session.owner_message,
                    ready_handler=gateway_ready,
                    approval_interaction_sink=session.interaction,
                )
                gateway_task = asyncio.create_task(
                    gateway.start(settings.discord.bot_token.get_secret_value()),
                    name="slice6-live-approval-gateway",
                )
                try:
                    await asyncio.wait_for(ready.wait(), timeout=60.0)
                except TimeoutError:
                    raise QualificationFailure(
                        "discord", "gateway_ready_timeout"
                    ) from None

                conversation_id = str(settings.discord.channel_id)
                normal_create, normal_draft, _ = await _create_draft(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    recipient=arguments.recipient,
                    marker="normal-send",
                    artifacts=artifacts,
                )
                normal_value = _send_value(normal_draft, normal_create.content)
                artifacts.gmail_sent_thread_ids.add(normal_value.thread_id)
                normal_action = await _persist_approval(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("gmail.send_draft"),
                    value=normal_value,
                    stage="gmail-normal-send",
                )
                await session.deliver(normal_action)
                normal_click = await session.wait(
                    normal_action,
                    ApprovalComponentDecision.APPROVE,
                )
                if not normal_click.completed_in_handler:
                    raise QualificationFailure("gmail", "normal_send_needs_recovery")
                normal_result = GmailSendDraftSuccess.model_validate(
                    cast(
                        "dict[str, object]",
                        (await _require_terminal(actions, normal_action, "succeeded"))[
                            "value"
                        ],
                    )
                )
                normal_reconciliation = (
                    await composition.google_write.reconcile_gmail_send(normal_value)
                )
                if normal_reconciliation.outcome != "succeeded":
                    raise QualificationFailure("gmail", "normal_send_not_reconciled")
                artifacts.gmail_sent_message_ids.add(normal_result.sent_message_id)
                artifacts.gmail_sent_thread_ids.add(normal_result.thread_id)
                await _verify_one_recipient_copy(google_http, tokens, normal_result)

                lost_create, lost_draft, _ = await _create_draft(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    recipient=arguments.recipient,
                    marker="lost-response-send",
                    artifacts=artifacts,
                )
                lost_value = _send_value(lost_draft, lost_create.content)
                artifacts.gmail_sent_thread_ids.add(lost_value.thread_id)
                lost_action = await _persist_approval(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("gmail.send_draft"),
                    value=lost_value,
                    stage="gmail-lost-response-send",
                )
                await session.deliver(lost_action)
                transport.arm()
                lost_click = await session.wait(
                    lost_action,
                    ApprovalComponentDecision.APPROVE,
                )
                if lost_click.completed_in_handler:
                    raise QualificationFailure("gmail", "lost_response_not_injected")
                await ActionRecovery(
                    actions=actions,
                    google_write=composition.google_write,
                    plan=plan,
                    source_conversation_id=conversation_id,
                    approval_disabler=ApprovalRecoveryDisabler(
                        actions=actions,
                        discord=discord,
                    ),
                ).recover()
                lost_result = GmailSendDraftSuccess.model_validate(
                    cast(
                        "dict[str, object]",
                        (await _require_terminal(actions, lost_action, "succeeded"))[
                            "value"
                        ],
                    )
                )
                artifacts.gmail_sent_message_ids.add(lost_result.sent_message_id)
                artifacts.gmail_sent_thread_ids.add(lost_result.thread_id)
                await _verify_one_recipient_copy(google_http, tokens, lost_result)
                if transport.accepted_losses != 1:
                    raise QualificationFailure("gmail", "lost_response_count_changed")

                mismatch_create, mismatch_draft, _ = await _create_draft(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    recipient=arguments.recipient,
                    marker="mismatch-send",
                    artifacts=artifacts,
                )
                mismatch_value = _send_value(
                    mismatch_draft,
                    mismatch_create.content,
                )
                artifacts.gmail_sent_thread_ids.add(mismatch_value.thread_id)
                mismatch_action = await _persist_approval(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("gmail.send_draft"),
                    value=mismatch_value,
                    stage="gmail-mismatch-send",
                )
                updated_content = mismatch_create.content.model_copy(
                    update={"body_text": "Synthetic changed-after-preview body."}
                )
                await _execute_automatic(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("gmail.update_draft"),
                    value=GmailUpdateDraftInput(
                        draft_id=mismatch_draft.draft_id,
                        expected_content_digest=mismatch_draft.content_digest,
                        replacement=updated_content,
                    ),
                    action_id=uuid4(),
                    stage="gmail-mismatch-update",
                )
                await session.deliver(mismatch_action)
                sends_before_mismatch = transport.send_requests
                mismatch_click = await session.wait(
                    mismatch_action,
                    ApprovalComponentDecision.APPROVE,
                )
                if not mismatch_click.completed_in_handler:
                    raise QualificationFailure("gmail", "mismatch_send_needs_recovery")
                mismatch_terminal = await _require_terminal(
                    actions,
                    mismatch_action,
                    "failed",
                )
                if (
                    cast("dict[str, object]", mismatch_terminal.get("error", {})).get(
                        "type"
                    )
                    != "DraftChanged"
                    or transport.send_requests != sends_before_mismatch
                ):
                    raise QualificationFailure("gmail", "mismatch_sent_external_effect")

                start = (datetime.now(UTC) + timedelta(days=7)).replace(microsecond=0)
                denied_calendar = CalendarCreateEventInput(
                    calendar_id=arguments.calendar_id,
                    event=CalendarWritableEvent(
                        summary="Synthetic Jarvis Slice 6 identical denied event",
                        description="Deny this qualification action.",
                        location=None,
                        start=TimedEventTime(date_time=start, time_zone="UTC"),
                        end=TimedEventTime(
                            date_time=start + timedelta(minutes=15),
                            time_zone="UTC",
                        ),
                        recurrence=(),
                        attendees=(),
                        use_default_reminders=True,
                        reminders=(),
                    ),
                    notify_attendees=False,
                )
                denied_ids: list[UUID] = []
                for ordinal in (1, 2):
                    denied = await _persist_approval(
                        actions=actions,
                        messages=messages,
                        conversation_id=conversation_id,
                        plan=plan,
                        tool_id=ToolId("calendar.create_event"),
                        value=denied_calendar,
                        stage=f"calendar-identical-deny-{ordinal}",
                    )
                    denied_ids.append(denied)
                    await session.deliver(denied)
                    click = await session.wait(
                        denied,
                        ApprovalComponentDecision.DENY,
                    )
                    if not click.completed_in_handler:
                        raise QualificationFailure("calendar", "deny_not_completed")
                    await _require_terminal(actions, denied, "cancelled")
                    absent = await composition.google_write.reconcile_calendar_create(
                        denied_calendar,
                        denied,
                    )
                    if absent.outcome != "absent":
                        raise QualificationFailure("calendar", "denied_effect_exists")
                if denied_ids[0] == denied_ids[1]:
                    raise QualificationFailure("action", "identical_actions_collapsed")

                approved_calendar = CalendarCreateEventInput(
                    calendar_id=arguments.calendar_id,
                    event=denied_calendar.event.model_copy(
                        update={
                            "summary": "Synthetic Jarvis Slice 6 approved event",
                            "start": TimedEventTime(
                                date_time=start + timedelta(hours=1),
                                time_zone="UTC",
                            ),
                            "end": TimedEventTime(
                                date_time=start + timedelta(hours=1, minutes=15),
                                time_zone="UTC",
                            ),
                        }
                    ),
                    notify_attendees=False,
                )
                if (
                    classify_write(
                        ToolId("calendar.create_event"),
                        approved_calendar,
                        verified_owner_only_calendar_ids=(
                            settings.verified_owner_only_calendar_ids
                        ),
                        live_calendar_event=None,
                    )
                    != "approval_required"
                ):
                    raise QualificationFailure("calendar", "approval_policy_changed")
                calendar_action = await _persist_approval(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("calendar.create_event"),
                    value=approved_calendar,
                    stage="calendar-approved-create",
                )
                artifacts.calendar_event_ids.add(calendar_event_id(calendar_action))
                await session.deliver(calendar_action)
                calendar_click = await session.wait(
                    calendar_action,
                    ApprovalComponentDecision.APPROVE,
                )
                if not calendar_click.completed_in_handler:
                    raise QualificationFailure("calendar", "approved_create_recovery")
                calendar_result = CalendarCreateEventSuccess.model_validate(
                    cast(
                        "dict[str, object]",
                        (
                            await _require_terminal(
                                actions, calendar_action, "succeeded"
                            )
                        )["value"],
                    )
                )
                if calendar_result.event.event_id != calendar_event_id(calendar_action):
                    raise QualificationFailure("calendar", "effect_identity_changed")
                reconciled_calendar: ReconciliationResult[
                    Any
                ] = await composition.google_write.reconcile_calendar_create(
                    approved_calendar,
                    calendar_action,
                )
                if reconciled_calendar.outcome != "succeeded":
                    raise QualificationFailure("calendar", "create_not_reconciled")

                calendar_update = CalendarUpdateEventInput(
                    expected=calendar_result.event,
                    replacement=calendar_result.event.writable.model_copy(
                        update={
                            "summary": (
                                "Synthetic Jarvis Slice 6 approved event updated"
                            ),
                            "description": "Approved exact shared-calendar update.",
                        }
                    ),
                    notify_attendees=False,
                )
                live_for_update = (
                    await composition.google_write.calendar_current_snapshot(
                        arguments.calendar_id,
                        calendar_result.event.event_id,
                    )
                )
                if (
                    live_for_update.outcome != "found"
                    or live_for_update.value != calendar_result.event
                    or classify_write(
                        ToolId("calendar.update_event"),
                        calendar_update,
                        verified_owner_only_calendar_ids=(
                            settings.verified_owner_only_calendar_ids
                        ),
                        live_calendar_event=live_for_update.value,
                    )
                    != "approval_required"
                ):
                    raise QualificationFailure(
                        "calendar", "update_approval_policy_changed"
                    )
                calendar_update_action = await _persist_approval(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("calendar.update_event"),
                    value=calendar_update,
                    stage="calendar-approved-update",
                )
                await session.deliver(calendar_update_action)
                calendar_update_click = await session.wait(
                    calendar_update_action,
                    ApprovalComponentDecision.APPROVE,
                )
                if not calendar_update_click.completed_in_handler:
                    raise QualificationFailure("calendar", "approved_update_recovery")
                calendar_update_result = CalendarUpdateEventSuccess.model_validate(
                    cast(
                        "dict[str, object]",
                        (
                            await _require_terminal(
                                actions, calendar_update_action, "succeeded"
                            )
                        )["value"],
                    )
                )
                if (
                    await composition.google_write.reconcile_calendar_update(
                        calendar_update
                    )
                ).outcome != "succeeded":
                    raise QualificationFailure("calendar", "update_not_reconciled")

                calendar_delete = CalendarDeleteEventInput(
                    expected=calendar_update_result.event,
                    notify_attendees=False,
                )
                live_for_delete = (
                    await composition.google_write.calendar_current_snapshot(
                        arguments.calendar_id,
                        calendar_update_result.event.event_id,
                    )
                )
                if (
                    live_for_delete.outcome != "found"
                    or live_for_delete.value != calendar_update_result.event
                    or classify_write(
                        ToolId("calendar.delete_event"),
                        calendar_delete,
                        verified_owner_only_calendar_ids=(
                            settings.verified_owner_only_calendar_ids
                        ),
                        live_calendar_event=live_for_delete.value,
                    )
                    != "approval_required"
                ):
                    raise QualificationFailure(
                        "calendar", "delete_approval_policy_changed"
                    )
                calendar_delete_action = await _persist_approval(
                    actions=actions,
                    messages=messages,
                    conversation_id=conversation_id,
                    plan=plan,
                    tool_id=ToolId("calendar.delete_event"),
                    value=calendar_delete,
                    stage="calendar-approved-delete",
                )
                await session.deliver(calendar_delete_action)
                calendar_delete_click = await session.wait(
                    calendar_delete_action,
                    ApprovalComponentDecision.APPROVE,
                )
                if not calendar_delete_click.completed_in_handler:
                    raise QualificationFailure("calendar", "approved_delete_recovery")
                CalendarDeleteEventSuccess.model_validate(
                    cast(
                        "dict[str, object]",
                        (
                            await _require_terminal(
                                actions, calendar_delete_action, "succeeded"
                            )
                        )["value"],
                    )
                )
                if (
                    await composition.google_write.reconcile_calendar_delete(
                        calendar_delete
                    )
                ).outcome != "succeeded":
                    raise QualificationFailure("calendar", "delete_not_reconciled")
                artifacts.calendar_event_ids.discard(calendar_result.event.event_id)

                await session.flush()
                if transport.send_requests != 2:
                    raise QualificationFailure("gmail", "send_request_count_changed")
                async with engine.connect() as connection:
                    action_rows = cast(
                        int,
                        await connection.scalar(
                            select(func.count()).select_from(action)
                        ),
                    )
                if action_rows != 12:
                    raise QualificationFailure("action", "action_count_changed")
                result = {
                    "actions": {
                        "identical_arguments_remained_distinct": True,
                        "one_durable_effect_per_approval": True,
                        "rows": action_rows,
                    },
                    "approvals": {
                        "approve": 6,
                        "deny": 2,
                        "real_owner_components": len(_DECISIONS),
                    },
                    "calendar": {
                        "approved_unknown_calendar_create_update_delete": True,
                        "denied_actions_had_no_effect": True,
                        "exact_render_and_reconciliation": True,
                    },
                    "cleanup": {
                        "calendar": False,
                        "discord": False,
                        "gmail_drafts": False,
                        "gmail_sent": False,
                    },
                    "dependencies": {
                        **EXPECTED_GIT_PINS,
                        **EXPECTED_PACKAGE_VERSIONS,
                    },
                    "gmail": {
                        "accepted_send_lost_response_reconciled_once": True,
                        "draft_mismatch_sent_nothing": True,
                        "lost_response_exactly_one_recipient_copy": True,
                        "normal_send_exactly_one_recipient_copy": True,
                        "stable_creation_effect_header": True,
                    },
                    "implementation": {
                        **_implementation(),
                        "main_definition_fingerprint": definitions.main.fingerprint,
                        "main_plan_revision": plan.plan_revision,
                        "session_compatibility_revision": (
                            definitions.main.session_compatibility_revision
                        ),
                    },
                    "status": "passed",
                }
        except BaseException as error:
            primary_error = error
        finally:
            cleanup_errors: list[BaseException] = []
            if (
                composition is not None
                and actions is not None
                and messages is not None
                and session is not None
                and plan is not None
            ):
                try:
                    async with deployment_ownership(engine):
                        await ActionRecovery(
                            actions=actions,
                            google_write=composition.google_write,
                            plan=plan,
                            source_conversation_id=str(settings.discord.channel_id),
                            approval_disabler=ApprovalRecoveryDisabler(
                                actions=actions,
                                discord=discord,
                            ),
                        ).recover(allow_queued_execution=False)
                        await session.flush()
                        await _collect_durable_artifacts(engine, artifacts)
                        await _cleanup_calendar_with_approvals(
                            actions=actions,
                            messages=messages,
                            composition=composition,
                            plan=plan,
                            session=session,
                            discord=discord,
                            artifacts=artifacts,
                            calendar_id=arguments.calendar_id,
                            conversation_id=str(settings.discord.channel_id),
                        )
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            else:
                try:
                    await _collect_durable_artifacts(engine, artifacts)
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            try:
                await _delete_drafts(
                    google_http,
                    tokens,
                    artifacts,
                )
                if artifacts.calendar_event_ids:
                    raise QualificationFailure(
                        "cleanup", "calendar_owner_approved_cleanup_incomplete"
                    )
                cleanup_google_complete = True
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
            if artifacts.gmail_sent_message_ids or artifacts.gmail_sent_thread_ids:
                try:
                    await _post_cleanup_instruction(discord, artifacts)
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
                try:
                    await _wait_for_sent_cleanup(
                        google_http,
                        tokens,
                        artifacts,
                        arguments.cleanup_wait_seconds,
                    )
                    manual_gmail_complete = True
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            else:
                manual_gmail_complete = True
            if gateway is not None:
                await gateway.close()
            if gateway_task is not None:
                await asyncio.gather(gateway_task, return_exceptions=True)
            try:
                await _cleanup_discord(discord_http, settings, artifacts)
                cleanup_discord_complete = True
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                primary_error = cleanup_errors[0]
    await engine.dispose()
    if primary_error is not None:
        if isinstance(primary_error, QualificationFailure):
            raise primary_error
        raise QualificationFailure("run", "unexpected_exception") from None
    if result is None:
        raise QualificationFailure("run", "result_missing")
    cleanup = cast("dict[str, object]", result["cleanup"])
    cleanup.update(
        {
            "calendar": cleanup_google_complete,
            "discord": cleanup_discord_complete,
            "gmail_drafts": cleanup_google_complete,
            "gmail_sent": manual_gmail_complete,
        }
    )
    validate_result_evidence(result)
    assert_sanitized_output(
        result,
        (
            *settings.host_secrets,
            arguments.recipient,
            arguments.calendar_id,
            *(str(value) for value in artifacts.gmail_draft_ids),
            *(str(value) for value in artifacts.gmail_sent_message_ids),
            *(str(value) for value in artifacts.gmail_sent_thread_ids),
            *(str(value) for value in artifacts.calendar_event_ids),
            *(str(value) for value in artifacts.discord_message_ids),
        ),
    )
    return result


def main() -> int:
    try:
        arguments = live_arguments(os.environ)
        result = asyncio.run(_run(Settings.from_env(), arguments))
    except QualificationFailure as error:
        result = {
            "failure": {
                "reason_code": error.reason_code,
                "stage": error.stage,
                "type": type(error).__name__,
            },
            "status": "failed",
        }
    except BaseException as error:
        result = {
            "failure": {
                "reason_code": "unexpected_exception",
                "stage": "setup",
                "type": type(error).__name__,
            },
            "status": "failed",
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

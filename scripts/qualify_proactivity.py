#!/usr/bin/env python3
"""Run sanitized live Slice 5 scheduled-wake and Discord qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import stat
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from llm_agent_kernel import (
    CancellationToken,
    ClaimAcquired,
    DispatchResult,
    OwnerToken,
    RunId,
    StructuredConclusion,
    ThreadCompleted,
    ThreadId,
    ToolDispatchLineage,
    require_host_plan,
)
from llm_tools import (
    BudgetState,
    EffectId,
    ExecutionContext,
    FrozenToolPlan,
    InvocationPosition,
    ParsedJson,
    Principal,
    ReplayPolicy,
    Scope,
    ToolBinding,
    ToolEffect,
    ToolExecutor,
    ToolId,
    ToolResult,
    raw_input_digest,
)
from sqlalchemy import func, select

from jarvis.actions import (
    ACTION_MAX_ATTEMPTS,
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
)
from jarvis.admission import (
    ExactToolBudgetFactory,
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
    slice5_admission_limits,
)
from jarvis.checkpoints import PostgresInputCheckpoint
from jarvis.codex_control import CodexController, CodexHostConfig
from jarvis.db import (
    action,
    create_engine,
    memory_log,
    memory_summary,
    message,
    model_decision,
    read_position,
)
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    QUALIFIED_CODEX_MODELS,
    SLICE2_READ_IDS,
    Slice6Definitions,
    build_slice5_write_gate,
    build_slice6_definitions,
    verify_runtime_dependencies,
)
from jarvis.discord import (
    DISCORD_API_BASE_URL,
    DeliveryResult,
    DeliverySucceeded,
    DiscordCreateMessageClient,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import (
    build_agent_runtime,
    build_kernel_runtime,
    resolve_provider_configuration,
)
from jarvis.memory import MemoryStore
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore, SettlementTrace
from jarvis.ownership import Database, deployment_ownership
from jarvis.proactivity import DueWakeSignal, ProcessLocalWakeTimer
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.schedule_tools import (
    ScheduleCancelRequest,
    ScheduleCreateRequest,
    ScheduleWakeInput,
)
from jarvis.service import (
    JarvisThreadRunner,
    RemembererWorker,
    flush_pending_deliveries,
)
from jarvis.settings import Settings
from jarvis.terminal import TurnEvidence
from jarvis.write_composition import build_slice6_composition
from jarvis.write_dispatch import WriteToolDispatcher
from jarvis.write_gate import AutomaticWriteGate

_LIVE_ENVIRONMENT = "JARVIS_PROACTIVITY_LIVE"
_MODEL_MARKER = "S5-PROACTIVE-MODEL"
_FALLBACK_MARKER = "S5-PROACTIVE-FALLBACK"


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, reason_code: str) -> None:
        super().__init__(stage)
        self.stage = stage
        self.reason_code = reason_code


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


@dataclass(slots=True)
class _RecordingDelivery:
    inner: DiscordCreateMessageClient
    delivered: dict[UUID, tuple[str, str]] = field(default_factory=lambda: {})

    async def create_message(
        self,
        *,
        persisted_message_id: UUID | str,
        content: str,
    ) -> DeliveryResult:
        result = await self.inner.create_message(
            persisted_message_id=persisted_message_id,
            content=content,
        )
        if isinstance(result, DeliverySucceeded):
            self.delivered[UUID(str(persisted_message_id))] = (
                result.discord_message_id,
                content,
            )
        return result


@dataclass(slots=True)
class _PlanRecordingDispatcher:
    delegate: WriteToolDispatcher
    scheduled_plan_revision: str
    tool_ids: list[str] = field(default_factory=lambda: [])

    async def dispatch(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: ToolDispatchLineage,
    ) -> DispatchResult:
        if plan.plan_revision != self.scheduled_plan_revision:
            raise QualificationFailure("proactive", "unexpected_dispatch_plan")
        if binding.spec.effect is not ToolEffect.Read:
            raise QualificationFailure("proactive", "non_read_dispatch")
        self.tool_ids.append(str(binding.spec.id))
        return await self.delegate.dispatch(
            binding=binding,
            validated_input=validated_input,
            plan=plan,
            budgets=budgets,
            cancellation=cancellation,
            lineage=lineage,
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
    encoded = json.dumps(result, separators=(",", ":"), sort_keys=True)
    if any(value and value in encoded for value in forbidden_values):
        raise QualificationFailure("output", "private_value_exposed")


def proactive_plan_evidence(definitions: Slice6Definitions) -> dict[str, object]:
    scheduled = definitions.plans["scheduled_wake"]
    if definitions.plans["proactive"] is not scheduled:
        raise QualificationFailure("plan", "proactive_alias_changed")
    require_host_plan(scheduled, definitions.main.maximum_profile)
    tool_ids = tuple(grant.id for grant in scheduled.profile.ordered_grants)
    if tool_ids != SLICE2_READ_IDS:
        raise QualificationFailure("plan", "proactive_tools_changed")
    if any(
        scheduled.catalog_view.binding(tool_id).spec.effect is not ToolEffect.Read
        for tool_id in tool_ids
    ):
        raise QualificationFailure("plan", "proactive_plan_not_read_only")
    if any(str(tool_id).startswith("memory.") for tool_id in tool_ids):
        raise QualificationFailure("plan", "proactive_plan_contains_recall")
    return {
        "plan_revision": scheduled.plan_revision,
        "profile_revision": scheduled.profile.profile_revision,
        "read_only": True,
        "recall_available": False,
        "tool_ids": tuple(map(str, tool_ids)),
    }


def validate_result_evidence(result: dict[str, object]) -> None:
    try:
        actions = cast("dict[str, object]", result["actions"])
        discord = cast("dict[str, object]", result["discord"])
        plan = cast("dict[str, object]", result["plan"])
        schedule = cast("dict[str, object]", result["schedule"])
        dispatches = cast("list[str]", result["tool_dispatches"])
    except (KeyError, TypeError) as error:
        raise QualificationFailure("evidence", "evidence_shape_invalid") from error
    required = (
        result.get("status") == "passed",
        actions.get("attempts") == 4,
        actions.get("cancel") == "passed",
        actions.get("creation_receipt_replay") == "passed",
        actions.get("distinct_effects") == 4,
        actions.get("rows") == 4,
        discord.get("delivered") == 3,
        discord.get("removed") == 3,
        discord.get("idempotent_resolution") is True,
        discord.get("visible_fallback") is True,
        discord.get("visible_model_completion") is True,
        plan.get("read_only") is True,
        plan.get("recall_available") is False,
        tuple(cast("tuple[str, ...]", plan.get("tool_ids")))
        == tuple(map(str, SLICE2_READ_IDS)),
        schedule.get("exact_due") is True,
        schedule.get("host_wake_count") == 2,
        schedule.get("idempotent_claim") is True,
        schedule.get("overdue_restart") is True,
        schedule.get("wake_outcomes") == 2,
        all(tool_id in tuple(map(str, SLICE2_READ_IDS)) for tool_id in dispatches),
    )
    if not all(required):
        raise QualificationFailure("evidence", "qualification_incomplete")


def _validate_settings(settings: Settings, host: CodexHostConfig) -> None:
    if settings.runtime_state_directory.exists():
        raise ValueError("qualification runtime directory must be unused")
    runtime_parent = settings.runtime_state_directory.parent
    if not runtime_parent.is_absolute() or not runtime_parent.is_dir():
        raise ValueError("runtime-state parent must be an existing absolute directory")
    if stat.S_IMODE(runtime_parent.stat().st_mode) & 0o077:
        raise ValueError("runtime-state parent must be private")
    cognition_parent = Path(host.cognition_cwd_parent)
    if (
        not cognition_parent.is_dir()
        or stat.S_IMODE(cognition_parent.stat().st_mode) != 0o2750
    ):
        raise ValueError("cognition cwd parent must be a mode-02750 directory")


async def _require_empty_database(engine: Database) -> None:
    async with engine.connect() as connection:
        counts: list[int] = []
        for table in (
            message,
            memory_log,
            memory_summary,
            action,
            model_decision,
            read_position,
        ):
            counts.append(
                cast(
                    int,
                    await connection.scalar(select(func.count()).select_from(table)),
                )
            )
    if any(counts):
        raise ValueError("qualification database must be empty")


async def _execute_schedule(
    *,
    actions: ActionStore,
    plan: FrozenToolPlan,
    origin_message_id: UUID,
    value: ScheduleWakeInput,
    action_id: UUID,
    created_at: datetime,
    claim_id: str,
    model_step_ordinal: int,
) -> ToolResult:
    tool_id = ToolId("schedule.wake")
    binding = plan.catalog_view.binding(tool_id)
    grant = plan.grant(tool_id)
    arguments = cast("dict[str, object]", value.model_dump(mode="json"))
    contract = ExecutionContract(
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
        tool_effect=ToolEffect.Write,
        replay_policy=ReplayPolicy.ReDispatchable,
        input_digest=raw_input_digest(ParsedJson(arguments)),
        max_attempts=ACTION_MAX_ATTEMPTS,
        claim_id=claim_id,
        through_checkpoint=str(origin_message_id),
        model_step_ordinal=model_step_ordinal,
        input_message_ids=(str(origin_message_id),),
        write_gate_supporting_owner_message_ids=(str(origin_message_id),),
    )
    execute_after = (
        value.request.execute_after
        if isinstance(value.request, ScheduleCreateRequest)
        else None
    )
    stored = await actions.insert_automatic(
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin_message_id,
        execute_after=execute_after,
        action_id=action_id,
        created_at=created_at,
    )
    recorder = ActionPositionRecorder(
        store=actions,
        action_id=action_id,
        implementation_revision=binding.implementation_revision,
        max_external_attempts=grant.limits.max_attempts,
    )
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
            scope=Scope("slice5-proactivity-qualification"),
            cancellation=CancellationToken(),
            telemetry=_NoTelemetry(),
        ),
    )
    if result.get("type") != "Success":
        raise QualificationFailure("schedule", "schedule_tool_failed")
    replayed = await actions.get(action_id)
    expected_attempts = 1 if stored.attempts == 0 else stored.attempts
    if replayed is None or replayed.attempts != expected_attempts:
        raise QualificationFailure("schedule", "action_attempt_count_invalid")
    return result


async def _fallback_next_host(
    *,
    messages: MessageStore,
    definitions: Slice6Definitions,
    conversation_id: str,
    expected_plan_revision: str,
) -> None:
    checkpoint = PostgresInputCheckpoint(
        store=messages,
        thread_id=ThreadId(conversation_id),
        run_id=RunId(str(uuid4())),
        interactive_plan=definitions.plans["main"],
        scheduled_wake_plan=definitions.plans["scheduled_wake"],
        maximum_batch_size=1,
        maximum_attempts=definitions.main.limits.max_no_progress_attempts,
        turn_evidence=TurnEvidence(),
    )
    claimed = await checkpoint.claim(
        ThreadId(conversation_id), OwnerToken("slice5-qualification-owner")
    )
    if not isinstance(claimed, ClaimAcquired):
        raise QualificationFailure("fallback", "host_input_not_claimed")
    if claimed.claim.plan.plan_revision != expected_plan_revision:
        raise QualificationFailure("fallback", "host_input_plan_changed")
    await checkpoint.settle(
        claimed.claim,
        claimed.claim.through_checkpoint,
        StructuredConclusion(
            {
                "response": {
                    "type": "silent",
                    "reason": "owner_needs_no_response",
                }
            }
        ),
    )


async def _deliver_and_verify(
    *,
    messages: MessageStore,
    delivery: _RecordingDelivery,
    client: httpx.AsyncClient,
    settings: Settings,
) -> int:
    conversation_id = str(settings.discord.channel_id)
    while True:
        flushed = await flush_pending_deliveries(
            store=messages,
            delivery=delivery,
            source_conversation_id=conversation_id,
            limit=settings.delivery_batch_size,
        )
        if flushed.failure is not None:
            replay = await flush_pending_deliveries(
                store=messages,
                delivery=delivery,
                source_conversation_id=conversation_id,
                limit=settings.delivery_batch_size,
            )
            if replay.failure is not None:
                raise QualificationFailure("discord", "delivery_failed")
        if flushed.selected < settings.delivery_batch_size:
            break
    headers = {"Authorization": "Bot " + settings.discord.bot_token.get_secret_value()}
    for discord_id, expected_text in delivery.delivered.values():
        response = await client.get(
            f"{DISCORD_API_BASE_URL}/channels/{settings.discord.channel_id}"
            f"/messages/{discord_id}",
            headers=headers,
            timeout=10.0,
        )
        if (
            response.status_code != 200
            or response.json().get("content") != expected_text
        ):
            raise QualificationFailure("discord", "visible_message_mismatch")
    return len(delivery.delivered)


async def _cleanup_discord(
    *,
    delivery: _RecordingDelivery,
    client: httpx.AsyncClient,
    settings: Settings,
) -> int:
    headers = {"Authorization": "Bot " + settings.discord.bot_token.get_secret_value()}
    removed = 0
    for discord_id, _ in delivery.delivered.values():
        try:
            response = await client.delete(
                f"{DISCORD_API_BASE_URL}/channels/{settings.discord.channel_id}"
                f"/messages/{discord_id}",
                headers=headers,
                timeout=10.0,
            )
        except BaseException:
            continue
        if response.status_code in {204, 404}:
            removed += 1
    if removed != len(delivery.delivered):
        raise QualificationFailure("cleanup", "discord_cleanup_incomplete")
    return removed


async def _run(settings: Settings) -> dict[str, object]:
    verify_runtime_dependencies()
    host = settings.codex_host_config
    _validate_settings(settings, host)
    settings.runtime_state_directory.mkdir(mode=0o700)
    admission_limits = slice5_admission_limits(settings.maximum_batch_size)
    RollingAdmissionPort.initialize(settings.admission_journal_path, admission_limits)
    raw_engine = create_engine(settings.database_url.get_secret_value())
    async with AsyncExitStack() as database_lifetime:
        database_lifetime.push_async_callback(raw_engine.dispose)
        engine = await database_lifetime.enter_async_context(
            deployment_ownership(raw_engine)
        )
        await _require_empty_database(engine)
        kernel_runtime = None
        delivery: _RecordingDelivery | None = None
        removed = 0
        primary_error: BaseException | None = None
        result: dict[str, object] | None = None
        async with AsyncExitStack() as clients:
            google_oauth_http = await clients.enter_async_context(
                httpx.AsyncClient(trust_env=False, follow_redirects=False)
            )
            google_api_http = await clients.enter_async_context(
                httpx.AsyncClient(trust_env=False, follow_redirects=False)
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
            try:
                actions = ActionStore(engine)
                agent_runtime = build_agent_runtime(
                    provider_state_root=settings.runtime_state_directory,
                    codex_endpoints=host.endpoints,
                )
                clients.push_async_callback(agent_runtime.close)
                messages = MessageStore(engine)
                memory = MemoryStore(engine)
                embedder = OpenAIEmbedder(
                    settings.embedding_openai_api_key,
                    http_client=embedding_http,
                )
                provider_configuration = await resolve_provider_configuration(
                    runtime=agent_runtime,
                    profile_key=settings.codex_profile_key,
                    model_key=settings.codex_model,
                )
                provisional_gate, _ = build_slice5_write_gate(
                    provider=provider_configuration,
                )
                composition = build_slice6_composition(
                    settings=settings,
                    google_oauth_http=google_oauth_http,
                    google_api_http=google_api_http,
                    maps_http=maps_http,
                    brave_http=brave_http,
                    memory_repository=PostgresMemoryRepository(engine),
                    memory_embedder=embedder,
                    actions=actions,
                    codex=CodexController(
                        control=agent_runtime.codex,
                        host=host,
                        actions=actions,
                    ),
                    automatic_write_gate_definition_fingerprint=(
                        provisional_gate.fingerprint
                    ),
                )
                definitions = build_slice6_definitions(
                    catalog=composition.catalog,
                    provider=provider_configuration,
                    owner_timezone=settings.owner_timezone,
                )
                plan_evidence = proactive_plan_evidence(definitions)
                main_plan = definitions.plans["main"]
                require_host_plan(main_plan, definitions.main.maximum_profile)
                now = datetime.now(UTC).replace(microsecond=0)
                conversation_id = str(settings.discord.channel_id)
                origin = await messages.insert_waking(
                    role="owner",
                    text="Synthetic Slice 5 scheduling qualification authority.",
                    source="qualification",
                    source_conversation_id=conversation_id,
                    source_message_id=str(uuid4()),
                    created_at=now,
                )
                await messages.settle(
                    consumed_message_ids=(origin.message.id,),
                    source_conversation_id=conversation_id,
                    trace=SettlementTrace(
                        run_id="slice5-proactivity-authority",
                        through_checkpoint=str(origin.message.id),
                        conclusion_kind="silent",
                        outcome="silent",
                    ),
                    conclusion_text=None,
                    settled_at=now,
                )

                cancel_target_id = uuid4()
                cancel_target_created_at = now + timedelta(seconds=1)
                cancel_target = ScheduleWakeInput(
                    request=ScheduleCreateRequest(
                        execute_after=now + timedelta(days=1),
                        instruction="Synthetic cancellation target.",
                    )
                )
                created_receipt = await _execute_schedule(
                    actions=actions,
                    plan=main_plan,
                    origin_message_id=origin.message.id,
                    value=cancel_target,
                    action_id=cancel_target_id,
                    created_at=cancel_target_created_at,
                    claim_id="slice5-qualification-cancel-create",
                    model_step_ordinal=1,
                )
                cancel_action_id = uuid4()
                await _execute_schedule(
                    actions=actions,
                    plan=main_plan,
                    origin_message_id=origin.message.id,
                    value=ScheduleWakeInput(
                        request=ScheduleCancelRequest(target_action_id=cancel_target_id)
                    ),
                    action_id=cancel_action_id,
                    created_at=now + timedelta(seconds=2),
                    claim_id="slice5-qualification-cancel",
                    model_step_ordinal=1,
                )
                replay = await _execute_schedule(
                    actions=actions,
                    plan=main_plan,
                    origin_message_id=origin.message.id,
                    value=cancel_target,
                    action_id=cancel_target_id,
                    created_at=cancel_target_created_at,
                    claim_id="slice5-qualification-cancel-create",
                    model_step_ordinal=1,
                )
                if replay != created_receipt:
                    raise QualificationFailure("schedule", "creation_replay_changed")
                resolution_text = (
                    f"Action {cancel_action_id} schedule.wake succeeded: "
                    "synthetic cancellation qualification."
                )
                first_resolution = await actions.insert_resolution_message(
                    action_id=cancel_action_id,
                    source_conversation_id=conversation_id,
                    text=resolution_text,
                    created_at=now + timedelta(seconds=3),
                )
                second_resolution = await actions.insert_resolution_message(
                    action_id=cancel_action_id,
                    source_conversation_id=conversation_id,
                    text=resolution_text,
                    created_at=now + timedelta(seconds=3),
                )
                if not first_resolution.inserted or second_resolution.inserted:
                    raise QualificationFailure("schedule", "resolution_not_idempotent")
                await _fallback_next_host(
                    messages=messages,
                    definitions=definitions,
                    conversation_id=conversation_id,
                    expected_plan_revision=main_plan.plan_revision,
                )

                exact_action_id = uuid4()
                exact_created_at = now + timedelta(seconds=4)
                exact_due = datetime.now(UTC).replace(microsecond=0) + timedelta(
                    minutes=5
                )
                await _execute_schedule(
                    actions=actions,
                    plan=main_plan,
                    origin_message_id=origin.message.id,
                    value=ScheduleWakeInput(
                        request=ScheduleCreateRequest(
                            execute_after=exact_due,
                            instruction=(
                                f"Say the exact synthetic-safe marker {_MODEL_MARKER}. "
                                "Do not use tools."
                            ),
                        )
                    ),
                    action_id=exact_action_id,
                    created_at=exact_created_at,
                    claim_id="slice5-qualification-exact-due",
                    model_step_ordinal=1,
                )
                current = exact_created_at
                exact_delays: list[float] = []
                exact_signals: list[DueWakeSignal] = []
                exact_cancellation = CancellationToken()

                async def exact_sleep(delay: float) -> None:
                    nonlocal current
                    exact_delays.append(delay)
                    current = exact_due

                def exact_signal(signal: DueWakeSignal) -> None:
                    exact_signals.append(signal)
                    exact_cancellation.cancel()

                await ProcessLocalWakeTimer(
                    store=actions,
                    on_due=exact_signal,
                    clock=lambda: current,
                    sleep=exact_sleep,
                ).run(exact_cancellation)
                if (
                    len(exact_delays) != 1
                    or exact_delays[0] != (exact_due - exact_created_at).total_seconds()
                    or exact_signals != [DueWakeSignal(exact_due, exact_due)]
                ):
                    raise QualificationFailure("schedule", "exact_due_timer_changed")
                first_claim = await actions.claim_due_schedule(
                    action_id=exact_action_id,
                    plan=definitions.plans["main"],
                    source_conversation_id=conversation_id,
                    now=exact_due,
                )
                second_claim = await actions.claim_due_schedule(
                    action_id=exact_action_id,
                    plan=definitions.plans["main"],
                    source_conversation_id=conversation_id,
                    now=exact_due,
                )
                if first_claim is None or second_claim is None:
                    raise QualificationFailure(
                        "schedule", "current_schedule_contract_rejected"
                    )
                if not first_claim.message_inserted or second_claim.message_inserted:
                    raise QualificationFailure("schedule", "wake_not_idempotent")

                admission = RootTrackingAdmissionPort(
                    RollingAdmissionPort(
                        settings.admission_journal_path, admission_limits
                    )
                )
                kernel_runtime = build_kernel_runtime(
                    runtime=agent_runtime,
                    shared_cwd_parent=Path(host.cognition_cwd_parent),
                    session_ref_path=settings.session_reference_path,
                    model=settings.codex_model,
                    kernel_limits=definitions.main.limits,
                )
                gate = AutomaticWriteGate(
                    model_decisions=lambda evidence: PostgresModelDecisionJournal(
                        engine, evidence=evidence
                    ),
                    definition=definitions.automatic_write_gate,
                    plan=definitions.plans["automatic_write_gate"],
                    admission=admission,
                    provider=kernel_runtime.provider,
                )
                rememberer = RemembererWorker(
                    model_decisions=lambda evidence: PostgresModelDecisionJournal(
                        engine, evidence=evidence
                    ),
                    definition=definitions.rememberer,
                    plan=definitions.plans["rememberer"],
                    admission=admission,
                    provider=kernel_runtime.provider,
                    dispatcher_factory=lambda: MemoryToolDispatcher(
                        recorder=PostgresReadRecorder(engine)
                    ),
                    memory=memory,
                    messages=messages,
                    embedder=embedder,
                    maximum_messages_per_group=settings.maximum_batch_size,
                )
                dispatchers: list[_PlanRecordingDispatcher] = []

                def dispatcher_factory(
                    checkpoint: PostgresInputCheckpoint,
                ) -> _PlanRecordingDispatcher:
                    delegate = WriteToolDispatcher(
                        checkpoint=checkpoint,
                        gate=gate,
                        actions=actions,
                        google_write=composition.google_write,
                        read=ReadToolDispatcher(
                            recorder=PostgresReadRecorder(engine),
                            host_secrets=settings.host_secrets,
                        ),
                        owner_timezone=settings.owner_timezone,
                        source_conversation_id=conversation_id,
                        verified_owner_only_calendar_ids=(
                            settings.verified_owner_only_calendar_ids
                        ),
                        host_secrets=settings.host_secrets,
                    )
                    recording = _PlanRecordingDispatcher(
                        delegate,
                        definitions.plans["scheduled_wake"].plan_revision,
                    )
                    dispatchers.append(recording)
                    return recording

                runner = JarvisThreadRunner(
                    model_decisions=lambda evidence: PostgresModelDecisionJournal(
                        engine, evidence=evidence
                    ),
                    settings=settings,
                    store=messages,
                    admission=admission,
                    kernel_runtime=kernel_runtime,
                    definitions=definitions,
                    history=PostgresCanonicalHistory(engine),
                    checkpoint_dispatcher_factory=dispatcher_factory,
                    memory=memory,
                    memory_dispatcher_factory=lambda: MemoryToolDispatcher(
                        recorder=PostgresReadRecorder(engine)
                    ),
                    rememberer=rememberer,
                )
                model_outcome = await runner.run(CancellationToken())
                if not isinstance(model_outcome, ThreadCompleted):
                    raise QualificationFailure("proactive", "model_run_not_completed")

                overdue_action_id = uuid4()
                overdue_due = datetime.now(UTC).replace(microsecond=0) + timedelta(
                    minutes=10
                )
                await _execute_schedule(
                    actions=actions,
                    plan=main_plan,
                    origin_message_id=origin.message.id,
                    value=ScheduleWakeInput(
                        request=ScheduleCreateRequest(
                            execute_after=overdue_due,
                            instruction=f"Synthetic {_FALLBACK_MARKER} reminder.",
                        )
                    ),
                    action_id=overdue_action_id,
                    created_at=now + timedelta(seconds=5),
                    claim_id="slice5-qualification-overdue",
                    model_step_ordinal=1,
                )
                overdue_cancellation = CancellationToken()
                overdue_signals: list[DueWakeSignal] = []

                def overdue_signal(signal: DueWakeSignal) -> None:
                    overdue_signals.append(signal)
                    overdue_cancellation.cancel()

                await ProcessLocalWakeTimer(
                    store=actions,
                    on_due=overdue_signal,
                    clock=lambda: overdue_due + timedelta(minutes=1),
                    sleep=lambda _delay: asyncio.sleep(0),
                ).run(overdue_cancellation)
                if len(overdue_signals) != 1 or not overdue_signals[0].overdue:
                    raise QualificationFailure("schedule", "overdue_restart_changed")
                overdue_claim = await actions.claim_due_schedule(
                    action_id=overdue_action_id,
                    plan=definitions.plans["main"],
                    source_conversation_id=conversation_id,
                    now=overdue_due + timedelta(minutes=1),
                )
                if overdue_claim is None:
                    raise QualificationFailure(
                        "schedule", "current_overdue_contract_rejected"
                    )
                if overdue_action_id in {
                    candidate.id for candidate in await actions.recovery_candidates()
                }:
                    raise QualificationFailure(
                        "schedule", "claimed_wake_entered_startup_recovery"
                    )
                await _fallback_next_host(
                    messages=messages,
                    definitions=definitions,
                    conversation_id=conversation_id,
                    expected_plan_revision=definitions.plans[
                        "scheduled_wake"
                    ].plan_revision,
                )

                action_ids = (
                    cancel_target_id,
                    cancel_action_id,
                    exact_action_id,
                    overdue_action_id,
                )
                async with engine.connect() as connection:
                    action_rows = (
                        (
                            await connection.execute(
                                select(action).where(action.c.id.in_(action_ids))
                            )
                        )
                        .mappings()
                        .all()
                    )
                    waking_rows = (
                        (
                            await connection.execute(
                                select(message).where(
                                    message.c.id.in_(
                                        (
                                            first_claim.waking_message_id,
                                            overdue_claim.waking_message_id,
                                            first_resolution.message_id,
                                        )
                                    )
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                    total_actions = cast(
                        int,
                        await connection.scalar(
                            select(func.count()).select_from(action)
                        ),
                    )
                if (
                    len(action_rows) != 4
                    or total_actions != 4
                    or sum(cast(int, row["attempts"]) for row in action_rows) != 4
                    or len(waking_rows) != 3
                ):
                    raise QualificationFailure("persistence", "duplicate_effect_or_row")
                waking_by_id = {row["id"]: row for row in waking_rows}
                exact_wake = waking_by_id[first_claim.waking_message_id]
                overdue_wake = waking_by_id[overdue_claim.waking_message_id]
                resolution_wake = waking_by_id[first_resolution.message_id]
                for row, expected_outcome in (
                    (exact_wake, "answered"),
                    (overdue_wake, "host_fallback"),
                    (resolution_wake, "host_fallback"),
                ):
                    trace = cast("dict[str, object]", row["trace"])
                    settlement = trace.get("settlement")
                    if row["processed_at"] is None or not isinstance(settlement, dict):
                        raise QualificationFailure(
                            "persistence", "visible_settlement_changed"
                        )
                    if (
                        cast("dict[str, object]", settlement).get("outcome")
                        != expected_outcome
                    ):
                        raise QualificationFailure(
                            "persistence", "visible_settlement_changed"
                        )
                if (
                    "recaller" in exact_wake["trace"]
                    or "recaller" in overdue_wake["trace"]
                ):
                    raise QualificationFailure("proactive", "recaller_invoked")
                exact_action = next(
                    row for row in action_rows if row["id"] == exact_action_id
                )
                overdue_action = next(
                    row for row in action_rows if row["id"] == overdue_action_id
                )
                if (
                    exact_action["status"] != "succeeded"
                    or overdue_action["status"] != "succeeded"
                    or exact_action["result"]["wake_outcome"]["type"] != "concluded"
                    or overdue_action["result"]["wake_outcome"]["type"] != "concluded"
                ):
                    raise QualificationFailure("schedule", "wake_outcome_changed")
                pending = await messages.pending_delivery(
                    source_conversation_id=conversation_id,
                    limit=10,
                )
                if len(pending) != 3:
                    raise QualificationFailure(
                        "discord", "visible_output_count_changed"
                    )
                model_messages = tuple(
                    value for value in pending if _MODEL_MARKER in value.text
                )
                fallback_messages = tuple(
                    value for value in pending if _FALLBACK_MARKER in value.text
                )
                if len(model_messages) != 1 or len(fallback_messages) != 1:
                    raise QualificationFailure("proactive", "visible_marker_missing")
                delivery = _RecordingDelivery(
                    DiscordCreateMessageClient(settings.discord, discord_http)
                )
                delivered = await _deliver_and_verify(
                    messages=messages,
                    delivery=delivery,
                    client=discord_http,
                    settings=settings,
                )
                result = {
                    "actions": {
                        "attempts": 4,
                        "cancel": "passed",
                        "creation_receipt_replay": "passed",
                        "distinct_effects": 4,
                        "rows": total_actions,
                    },
                    "dependencies": {
                        **EXPECTED_GIT_PINS,
                    },
                    "discord": {
                        "delivered": delivered,
                        "idempotent_resolution": True,
                        "visible_fallback": True,
                        "visible_model_completion": True,
                    },
                    "implementation": _implementation(),
                    "model": {
                        "definition_fingerprint": definitions.main.fingerprint,
                        "input_tokens": model_outcome.metrics.usage.input_tokens,
                        "output_tokens": model_outcome.metrics.usage.output_tokens,
                        "provider_turns": model_outcome.metrics.provider_turns,
                        "route": settings.codex_model,
                        "session_compatibility_revision": (
                            definitions.main.session_compatibility_revision
                        ),
                    },
                    "plan": plan_evidence,
                    "schedule": {
                        "exact_due": True,
                        "host_wake_count": 2,
                        "idempotent_claim": True,
                        "overdue_restart": True,
                        "wake_outcomes": 2,
                    },
                    "status": "passed",
                    "tool_dispatches": sorted(
                        tool_id
                        for dispatcher in dispatchers
                        for tool_id in dispatcher.tool_ids
                    ),
                }
            except BaseException as error:
                primary_error = error
            finally:
                if delivery is not None:
                    try:
                        removed = await _cleanup_discord(
                            delivery=delivery,
                            client=discord_http,
                            settings=settings,
                        )
                    except BaseException as cleanup_error:
                        if primary_error is None:
                            primary_error = cleanup_error
                if kernel_runtime is not None:
                    await kernel_runtime.close()
        if primary_error is not None:
            if isinstance(primary_error, QualificationFailure):
                raise primary_error
            raise QualificationFailure("run", "unexpected_exception") from primary_error
        if result is None:
            raise QualificationFailure("run", "result_missing")
        discord_evidence = cast("dict[str, object]", result["discord"])
        discord_evidence["removed"] = removed
        if removed != discord_evidence["delivered"]:
            raise QualificationFailure("cleanup", "discord_cleanup_incomplete")
        validate_result_evidence(result)
        assert_sanitized_output(
            result,
            (
                *settings.host_secrets,
                str(settings.runtime_state_directory),
                str(settings.google_oauth_state_path),
            ),
        )
        return result


def main() -> int:
    configured_route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    route = (
        configured_route
        if configured_route in QUALIFIED_CODEX_MODELS
        else "unconfigured"
    )
    try:
        if os.environ.get(_LIVE_ENVIRONMENT) != "1":
            raise ValueError(f"live qualification requires {_LIVE_ENVIRONMENT}=1")
        result = asyncio.run(_run(Settings.from_env()))
    except QualificationFailure as error:
        result = {
            "failure": {
                "reason_code": error.reason_code,
                "stage": error.stage,
                "type": type(error).__name__,
            },
            "route": route,
            "status": "failed",
        }
    except BaseException as error:
        result = {
            "failure": {
                "reason_code": "unexpected_exception",
                "stage": "setup",
                "type": type(error).__name__,
            },
            "route": route,
            "status": "failed",
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run sanitized live Slice 5 Gmail-draft and owner-calendar writes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from llm_agent_kernel import (
    CancellationToken,
    require_host_plan,
)
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
    ActionPositionRecorder,
    ActionStore,
    ExecutionContract,
)
from jarvis.admission import ExactToolBudgetFactory
from jarvis.agent_control import AgentController
from jarvis.connectors import GoogleTokenManager
from jarvis.db import action, create_engine
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    build_slice5_write_gate,
    build_slice6_definitions,
    verify_runtime_dependencies,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.kernel import build_agent_runtime, resolve_provider_configuration
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.read_tools import CALENDAR_API_BASE_URL, GMAIL_API_BASE_URL
from jarvis.settings import Settings
from jarvis.write_composition import Slice6Composition, build_slice6_composition
from jarvis.write_connectors import (
    GmailUpdateReconciliationBasis,
    ReconciliationResult,
    calendar_event_id,
    gmail_effect_id,
)
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
    GmailUpdateDraftInput,
    Mailbox,
    Reminder,
    TimedEventTime,
)

_OPERATIONS = (
    ToolId("gmail.create_draft"),
    ToolId("gmail.update_draft"),
    ToolId("calendar.create_event"),
    ToolId("calendar.update_event"),
    ToolId("calendar.delete_event"),
)


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(stage)
        self.stage = stage
        self.reason = reason


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


@dataclass(slots=True)
class _Artifacts:
    calendar_id: str = field(repr=False)
    gmail_create_action_id: UUID | None = field(default=None, repr=False)
    gmail_create_input: GmailCreateDraftInput | None = field(default=None, repr=False)
    gmail_draft_id: str | None = field(default=None, repr=False)
    calendar_event_id: str | None = field(default=None, repr=False)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty without edge whitespace")
    return value


def _implementation() -> dict[str, str]:
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    return {
        "architecture": platform.machine().lower(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "os": platform.system().lower(),
    }


async def _execute_write(
    *,
    actions: ActionStore,
    plan: Any,
    budgets: Any,
    origin_message_id: UUID,
    ordinal: int,
    tool_id: ToolId,
    value: BaseModel,
    action_id: UUID,
) -> dict[str, object]:
    binding = plan.catalog_view.binding(tool_id)
    grant = plan.grant(tool_id)
    arguments = cast("dict[str, object]", value.model_dump(mode="json"))
    contract = ExecutionContract(
        tool_contract_revision=binding.spec.tool_contract_revision,
        implementation_revision=binding.implementation_revision,
        policy_revision=binding.policy_revision,
        plan_revision=plan.plan_revision,
        tool_effect=binding.spec.effect,
        replay_policy=binding.replay_policy,
        input_digest=raw_input_digest(ParsedJson(arguments)),
        max_attempts=ACTION_MAX_ATTEMPTS,
        claim_id="slice5-live-write-qualification",
        through_checkpoint=str(origin_message_id),
        model_step_ordinal=ordinal,
        input_message_ids=(str(origin_message_id),),
        write_gate_supporting_owner_message_ids=(str(origin_message_id),),
    )
    stored = await actions.insert_automatic(
        tool_name=tool_id,
        arguments=arguments,
        execution_contract=contract,
        origin_message_id=origin_message_id,
        action_id=action_id,
    )
    if stored.id != action_id or stored.status != "queued":
        raise QualificationFailure(str(tool_id), "action_insert_invalid")
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
                budgets=budgets,
                principal=Principal("jarvis-owner"),
                scope=Scope("live-write-qualification"),
                cancellation=CancellationToken(),
                telemetry=_NoTelemetry(),
            ),
        )
    except RecoveryRequired:
        raise QualificationFailure(str(tool_id), "recovery_required") from None
    if result.get("type") != "Success" or not isinstance(result.get("value"), dict):
        error = result.get("error")
        error_type = (
            cast("dict[str, object]", error).get("type")
            if isinstance(error, dict)
            else None
        )
        raise QualificationFailure(
            str(tool_id),
            error_type if isinstance(error_type, str) else "invalid_result",
        )
    terminal = await actions.get(action_id)
    if (
        terminal is None
        or terminal.status != "succeeded"
        or terminal.attempts != 1
        or terminal.result != result
        or terminal.position != InvocationPosition(str(action_id))
    ):
        raise QualificationFailure(str(tool_id), "action_terminal_invalid")
    return cast("dict[str, object]", result["value"])


def _require_reconciled(
    stage: str,
    result: ReconciliationResult[Any],
) -> None:
    if result.outcome != "succeeded" or result.value is None:
        raise QualificationFailure(stage, f"reconciliation_{result.outcome}")


async def _cleanup_external_artifacts(
    *,
    client: httpx.AsyncClient,
    tokens: GoogleTokenManager,
    artifacts: _Artifacts,
) -> dict[str, bool]:
    cleaned = {
        "calendar": artifacts.calendar_event_id is None,
        "gmail": (
            artifacts.gmail_draft_id is None
            and artifacts.gmail_create_action_id is None
        ),
    }
    failures: list[str] = []
    targets = (
        (
            "gmail",
            None
            if artifacts.gmail_draft_id is None
            else (
                f"{GMAIL_API_BASE_URL}/users/me/drafts/"
                f"{quote(artifacts.gmail_draft_id, safe='')}",
                None,
            ),
        ),
        (
            "calendar",
            None
            if artifacts.calendar_event_id is None
            else (
                f"{CALENDAR_API_BASE_URL}/calendars/"
                f"{quote(artifacts.calendar_id, safe='')}/events/"
                f"{quote(artifacts.calendar_event_id, safe='')}",
                {"sendUpdates": "none"},
            ),
        ),
    )
    for name, target in targets:
        if target is None:
            continue
        url, params = target
        try:
            token, _ = await tokens.access_token()
            response = await client.delete(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=False,
                timeout=httpx.Timeout(8.0, connect=3.0),
            )
            if response.status_code not in {204, 404, 410}:
                failures.append(name)
            else:
                cleaned[name] = True
        except BaseException:
            failures.append(name)
    if failures:
        raise QualificationFailure("cleanup", "external_cleanup_failed")
    return cleaned


def assert_sanitized_output(
    result: dict[str, object], forbidden_values: tuple[str, ...]
) -> None:
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if any(value and value in encoded for value in forbidden_values):
        raise QualificationFailure("output", "private_value_exposed")


async def _run(settings: Settings, calendar_id: str) -> dict[str, object]:
    verify_runtime_dependencies()
    if calendar_id not in settings.verified_owner_only_calendar_ids:
        raise QualificationFailure("setup", "calendar_not_verified_owner_only")
    clients = tuple(
        httpx.AsyncClient(trust_env=False, follow_redirects=False) for _ in range(5)
    )
    raw_engine = create_engine(settings.database_url.get_secret_value())
    async with AsyncExitStack() as database_lifetime:
        database_lifetime.push_async_callback(raw_engine.dispose)
        engine = await database_lifetime.enter_async_context(
            deployment_ownership(raw_engine)
        )
        actions = ActionStore(engine)
        artifacts = _Artifacts(calendar_id=calendar_id)
        cleanup: dict[str, bool] | None = None
        primary_error: BaseException | None = None
        result: dict[str, object] | None = None
        composition: Slice6Composition | None = None
        host = settings.codex_host_config
        agent_runtime = build_agent_runtime(
            provider_state_root=settings.runtime_state_directory,
            codex_endpoints=host.endpoints,
        )
        database_lifetime.push_async_callback(agent_runtime.close)
        stage = "composition"
        try:
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
                google_oauth_http=clients[0],
                google_api_http=clients[1],
                maps_http=clients[2],
                brave_http=clients[3],
                memory_repository=PostgresMemoryRepository(engine),
                memory_embedder=OpenAIEmbedder(
                    settings.embedding_openai_api_key,
                    http_client=clients[4],
                ),
                actions=actions,
                agents=AgentController(
                    executable=settings.agent_cli_path,
                    client_config=settings.agent_client_config_path,
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
            plan = definitions.plans["main"]
            require_host_plan(plan, definitions.main.maximum_profile)
            budgets = ExactToolBudgetFactory().create(plan)
            action_ids = tuple(uuid4() for _ in _OPERATIONS)
            if len(set(action_ids)) != len(_OPERATIONS):
                raise QualificationFailure("setup", "action_identity_collision")
            messages = MessageStore(engine)
            origin = await messages.insert_waking(
                role="owner",
                text=(
                    "Run the explicitly authorized synthetic Slice 5 Gmail draft and "
                    "owner-only Calendar qualification, then remove all artifacts."
                ),
                source="qualification",
                source_conversation_id="slice5-live-writes",
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            async with engine.connect() as connection:
                actions_before = cast(
                    int,
                    await connection.scalar(select(func.count()).select_from(action)),
                )

            gmail_create = GmailCreateDraftInput(
                content=GmailContent(
                    to=(Mailbox(name=None, address="qualification@example.invalid"),),
                    cc=(),
                    bcc=(),
                    subject="Synthetic Jarvis Slice 5 qualification draft",
                    body_text="Synthetic unsent qualification content.",
                    reply_to=None,
                )
            )
            gmail_create_action = action_ids[0]
            artifacts.gmail_create_action_id = gmail_create_action
            artifacts.gmail_create_input = gmail_create
            stage = "gmail.create_draft"
            created_draft = GmailDraftSuccess.model_validate(
                await _execute_write(
                    actions=actions,
                    plan=plan,
                    budgets=budgets,
                    origin_message_id=origin.message.id,
                    ordinal=1,
                    tool_id=ToolId(stage),
                    value=gmail_create,
                    action_id=gmail_create_action,
                )
            )
            artifacts.gmail_draft_id = created_draft.draft_id
            if created_draft.jarvis_effect_id != gmail_effect_id(gmail_create_action):
                raise QualificationFailure(stage, "effect_identity_mismatch")
            gmail_create_reconciliation = (
                await composition.google_write.reconcile_gmail_create(
                    gmail_create, gmail_create_action
                )
            )
            if gmail_create_reconciliation.outcome == "absent":
                raise QualificationFailure(stage, "unsafe_absence_outcome")
            if (
                gmail_create_reconciliation.outcome == "succeeded"
                and gmail_create_reconciliation.value is not None
                and gmail_create_reconciliation.value.model_dump(
                    mode="json", exclude={"observed_at"}
                )
                != created_draft.model_dump(mode="json", exclude={"observed_at"})
            ):
                raise QualificationFailure(stage, "reconciliation_value_mismatch")
            if not gmail_create_reconciliation.evidence.startswith("gmail-create-"):
                raise QualificationFailure(stage, "reconciliation_evidence_invalid")
            create_row = await actions.get(gmail_create_action)
            if create_row is None or create_row.attempts != 1:
                raise QualificationFailure(stage, "reconciliation_repeated_create")

            gmail_update = GmailUpdateDraftInput(
                draft_id=created_draft.draft_id,
                expected_content_digest=created_draft.content_digest,
                replacement=GmailContent(
                    to=(Mailbox(name=None, address="qualification@example.invalid"),),
                    cc=(),
                    bcc=(),
                    subject="Synthetic Jarvis Slice 5 qualification draft updated",
                    body_text="Synthetic updated unsent qualification content.",
                    reply_to=None,
                ),
            )
            stage = "gmail.update_draft"
            updated_draft = GmailDraftSuccess.model_validate(
                await _execute_write(
                    actions=actions,
                    plan=plan,
                    budgets=budgets,
                    origin_message_id=origin.message.id,
                    ordinal=2,
                    tool_id=ToolId(stage),
                    value=gmail_update,
                    action_id=action_ids[1],
                )
            )
            gmail_reconciliation = (
                await composition.google_write.reconcile_gmail_update(
                    gmail_update,
                    GmailUpdateReconciliationBasis(
                        type="gmail_update_reconciliation_v1",
                        draft_id=created_draft.draft_id,
                        thread_id=created_draft.thread_id,
                        jarvis_effect_id=created_draft.jarvis_effect_id,
                        old_content_digest=created_draft.content_digest,
                    ),
                )
            )
            _require_reconciled(stage, gmail_reconciliation)
            if updated_draft.jarvis_effect_id != created_draft.jarvis_effect_id:
                raise QualificationFailure(stage, "effect_header_changed")

            start = (datetime.now(UTC) + timedelta(days=7)).replace(microsecond=0)
            calendar_create = CalendarCreateEventInput(
                calendar_id=calendar_id,
                event=CalendarWritableEvent(
                    summary="Synthetic Jarvis Slice 5 qualification event",
                    description="Synthetic qualification artifact; safe to delete.",
                    location=None,
                    start=TimedEventTime(date_time=start, time_zone="UTC"),
                    end=TimedEventTime(
                        date_time=start + timedelta(minutes=30), time_zone="UTC"
                    ),
                    recurrence=(),
                    attendees=(),
                    use_default_reminders=False,
                    reminders=(Reminder(method="popup", minutes=10),),
                ),
                notify_attendees=False,
            )
            if (
                classify_write(
                    ToolId("calendar.create_event"),
                    calendar_create,
                    verified_owner_only_calendar_ids=(calendar_id,),
                    live_calendar_event=None,
                )
                != "automatic"
            ):
                raise QualificationFailure("calendar.create_event", "not_automatic")
            calendar_create_action = action_ids[2]
            artifacts.calendar_event_id = calendar_event_id(calendar_create_action)
            stage = "calendar.create_event"
            created_event = CalendarCreateEventSuccess.model_validate(
                await _execute_write(
                    actions=actions,
                    plan=plan,
                    budgets=budgets,
                    origin_message_id=origin.message.id,
                    ordinal=3,
                    tool_id=ToolId(stage),
                    value=calendar_create,
                    action_id=calendar_create_action,
                )
            )
            if created_event.event.event_id != artifacts.calendar_event_id:
                raise QualificationFailure(stage, "effect_identity_mismatch")
            _require_reconciled(
                stage,
                await composition.google_write.reconcile_calendar_create(
                    calendar_create, calendar_create_action
                ),
            )

            calendar_update = CalendarUpdateEventInput(
                expected=created_event.event,
                replacement=created_event.event.writable.model_copy(
                    update={"summary": "Synthetic Jarvis Slice 5 event updated"}
                ),
                notify_attendees=False,
            )
            live_for_update = await composition.google_write.calendar_current_snapshot(
                calendar_id, created_event.event.event_id
            )
            if (
                live_for_update.outcome != "found"
                or live_for_update.value != created_event.event
                or classify_write(
                    ToolId("calendar.update_event"),
                    calendar_update,
                    verified_owner_only_calendar_ids=(calendar_id,),
                    live_calendar_event=live_for_update.value,
                )
                != "automatic"
            ):
                raise QualificationFailure(
                    "calendar.update_event", "authority_check_failed"
                )
            stage = "calendar.update_event"
            updated_event = CalendarUpdateEventSuccess.model_validate(
                await _execute_write(
                    actions=actions,
                    plan=plan,
                    budgets=budgets,
                    origin_message_id=origin.message.id,
                    ordinal=4,
                    tool_id=ToolId(stage),
                    value=calendar_update,
                    action_id=action_ids[3],
                )
            )
            _require_reconciled(
                stage,
                await composition.google_write.reconcile_calendar_update(
                    calendar_update
                ),
            )

            calendar_delete = CalendarDeleteEventInput(
                expected=updated_event.event,
                notify_attendees=False,
            )
            live_for_delete = await composition.google_write.calendar_current_snapshot(
                calendar_id, updated_event.event.event_id
            )
            if (
                live_for_delete.outcome != "found"
                or live_for_delete.value != updated_event.event
                or classify_write(
                    ToolId("calendar.delete_event"),
                    calendar_delete,
                    verified_owner_only_calendar_ids=(calendar_id,),
                    live_calendar_event=live_for_delete.value,
                )
                != "automatic"
            ):
                raise QualificationFailure(
                    "calendar.delete_event", "authority_check_failed"
                )
            stage = "calendar.delete_event"
            CalendarDeleteEventSuccess.model_validate(
                await _execute_write(
                    actions=actions,
                    plan=plan,
                    budgets=budgets,
                    origin_message_id=origin.message.id,
                    ordinal=5,
                    tool_id=ToolId(stage),
                    value=calendar_delete,
                    action_id=action_ids[4],
                )
            )
            _require_reconciled(
                stage,
                await composition.google_write.reconcile_calendar_delete(
                    calendar_delete
                ),
            )

            async with engine.connect() as connection:
                actions_after = cast(
                    int,
                    await connection.scalar(select(func.count()).select_from(action)),
                )
            if actions_after - actions_before != len(_OPERATIONS):
                raise QualificationFailure("ledger", "action_count_mismatch")
            result = {
                "implementation": {
                    **_implementation(),
                    "main_definition_fingerprint": definitions.main.fingerprint,
                    "main_plan_revision": plan.plan_revision,
                    "session_compatibility_revision": (
                        definitions.main.session_compatibility_revision
                    ),
                },
                "reconciliation": {
                    "calendar_create": True,
                    "calendar_delete": True,
                    "calendar_update": True,
                    "gmail_create": gmail_create_reconciliation.outcome,
                    "gmail_create_evidence": gmail_create_reconciliation.evidence,
                    "gmail_update": True,
                },
                "revisions": dict(EXPECTED_GIT_PINS),
                "status": "passed",
                "writes": {
                    "actions": len(_OPERATIONS),
                    "calendar_owner_only": True,
                    "effect_ids_sha256": hashlib.sha256(
                        json.dumps(
                            sorted(map(str, action_ids)), separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                    "gmail_sent": False,
                    "one_action_per_effect": True,
                    "operations": [str(value) for value in _OPERATIONS],
                },
            }
        except BaseException as exc:
            primary_error = exc
        finally:
            if (
                composition is not None
                and artifacts.gmail_draft_id is None
                and (
                    artifacts.gmail_create_input is not None
                    and artifacts.gmail_create_action_id is not None
                )
            ):
                try:
                    recovered = await composition.google_write.reconcile_gmail_create(
                        artifacts.gmail_create_input,
                        artifacts.gmail_create_action_id,
                    )
                    if recovered.outcome == "succeeded" and recovered.value is not None:
                        artifacts.gmail_draft_id = recovered.value.draft_id
                except BaseException:
                    pass
            try:
                cleanup_tokens = GoogleTokenManager(
                    state_path=settings.google_oauth_state_path,
                    client=clients[0],
                    client_id=settings.google_oauth_client_id.get_secret_value(),
                    client_secret=settings.google_oauth_client_secret.get_secret_value(),
                    active_key_version=settings.connector_encryption_key_version,
                    configured_keys=settings.connector_encryption_keys.get_secret_value(),
                    single_secret=settings.connector_encryption_secret.get_secret_value(),
                )
                cleanup = await _cleanup_external_artifacts(
                    client=clients[1], tokens=cleanup_tokens, artifacts=artifacts
                )
            except BaseException as exc:
                primary_error = exc
            for client in clients:
                await client.aclose()
        if cleanup != {"calendar": True, "gmail": True}:
            raise QualificationFailure("cleanup", "external_cleanup_incomplete")
        if primary_error is not None:
            if isinstance(primary_error, QualificationFailure):
                raise primary_error
            raise QualificationFailure(stage, "unexpected_exception") from None
        if result is None:
            raise QualificationFailure(stage, "missing_result")
        cast("dict[str, object]", result["writes"])["cleanup"] = cleanup
        assert_sanitized_output(
            result,
            (
                *settings.host_secrets,
                calendar_id,
                artifacts.gmail_draft_id or "",
                artifacts.calendar_event_id or "",
            ),
        )
        return result


def main() -> int:
    stage = "setup"
    try:
        if os.environ.get("JARVIS_LIVE_WRITES") != "1":
            raise ValueError("live writes require JARVIS_LIVE_WRITES=1")
        settings = Settings.from_env()
        calendar_id = _required("JARVIS_LIVE_WRITE_CALENDAR_ID")
        result = asyncio.run(_run(settings, calendar_id))
    except QualificationFailure as exc:
        result = {
            "failure": {"reason": exc.reason, "stage": exc.stage},
            "implementation": _implementation(),
            "revisions": EXPECTED_GIT_PINS,
            "status": "failed",
        }
    except BaseException as exc:
        result = {
            "failure": {"reason": type(exc).__name__, "stage": stage},
            "implementation": _implementation(),
            "revisions": EXPECTED_GIT_PINS,
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

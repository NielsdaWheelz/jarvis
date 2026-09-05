#!/usr/bin/env python3
"""Run one sanitized paid Discord-to-Codex-to-Discord qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import discord
import httpx
from llm_agent_kernel import (
    CancellationToken,
    DispatchResult,
    ThreadCompleted,
    ToolDispatchLineage,
)
from llm_tools import BudgetState, FrozenToolPlan, ToolBinding, WebReadInput
from sqlalchemy import RowMapping, func, select

from jarvis.admission import RollingAdmissionLimits, RollingAdmissionPort
from jarvis.db import action, create_engine, memory_log, memory_summary, message
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    EXPECTED_PACKAGE_VERSIONS,
    QUALIFIED_CODEX_MODELS,
    SLICE2_KERNEL_LIMITS,
    build_slice2_definitions,
    verify_runtime_dependencies,
)
from jarvis.discord import (
    DeliveryResult,
    DeliverySucceeded,
    DiscordCreateMessageClient,
    DiscordGateway,
    DiscordOwnerMessage,
)
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import build_kernel_runtime
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.read_composition import build_read_catalog
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_tools import (
    CalendarGetEventInput,
    GmailReadThreadInput,
    MapsDirectionsInput,
    MapsGetPlaceInput,
    PlaceLocation,
)
from jarvis.service import JarvisService, JarvisThreadRunner
from jarvis.settings import Settings
from jarvis.state import PausedState

_SUPPORTED_ROUTES = frozenset(QUALIFIED_CODEX_MODELS)
_MAX_CATCH_UP_PAGE = 100
_REQUIRED_COMPOUND_READS = frozenset(
    {
        "gmail.search",
        "gmail.read_thread",
        "calendar.list_events",
        "calendar.get_event",
        "maps.search_places",
        "maps.get_place",
        "maps.directions",
        "web.search",
        "web.read",
    }
)


class QualificationCheckFailed(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class QualificationFailure(RuntimeError):
    def __init__(
        self,
        stage: str,
        cause_type: str,
        reason_code: str,
        *,
        cleanup: QualificationFailure | None = None,
    ) -> None:
        super().__init__(stage)
        self.stage = stage
        self.cause_type = cause_type
        self.reason_code = reason_code
        self.cleanup = cleanup


def _failure(stage: str, exc: BaseException) -> QualificationFailure:
    reason_code = (
        exc.reason_code
        if isinstance(exc, QualificationCheckFailed)
        else "unexpected_exception"
    )
    return QualificationFailure(stage, type(exc).__name__, reason_code)


def _implementation() -> dict[str, str]:
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    return {
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "os": platform.system().lower(),
        "architecture": platform.machine().lower(),
    }


@dataclass(slots=True)
class _RecordingDelivery:
    inner: DiscordCreateMessageClient
    success: DeliverySucceeded | None = None

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
            self.success = result
        return result


class _RecordingDispatcher:
    def __init__(self, host_secrets: tuple[str, ...]) -> None:
        self.inner = ReadToolDispatcher(host_secrets=host_secrets)
        self.successful_tool_ids: list[str] = []
        self._gmail_thread_ids: set[str] = set()
        self._calendar_event_ids: set[tuple[str, str]] = set()
        self._maps_place_ids: set[str] = set()
        self._web_urls: set[str] = set()
        self.gmail_linked = False
        self.calendar_linked = False
        self.maps_directions_linked = False
        self.maps_get_linked = False
        self.web_linked = False

    def _record_success(
        self,
        *,
        tool_id: str,
        validated_input: object,
        value: dict[str, object],
    ) -> None:
        self.successful_tool_ids.append(tool_id)
        if tool_id == "gmail.search":
            self._gmail_thread_ids.update(
                cast(str, item["thread_id"])
                for item in cast("list[dict[str, object]]", value["threads"])
            )
        elif tool_id == "gmail.read_thread":
            self.gmail_linked = self.gmail_linked or (
                isinstance(validated_input, GmailReadThreadInput)
                and validated_input.thread_id in self._gmail_thread_ids
            )
        elif tool_id == "calendar.list_events":
            self._calendar_event_ids.update(
                (cast(str, item["calendar_id"]), cast(str, item["event_id"]))
                for item in cast("list[dict[str, object]]", value["events"])
            )
        elif tool_id == "calendar.get_event":
            self.calendar_linked = self.calendar_linked or (
                isinstance(validated_input, CalendarGetEventInput)
                and (validated_input.calendar_id, validated_input.event_id)
                in self._calendar_event_ids
            )
        elif tool_id == "maps.search_places":
            self._maps_place_ids.update(
                cast(str, item["place_id"])
                for item in cast("list[dict[str, object]]", value["places"])
            )
        elif tool_id == "maps.get_place":
            self.maps_get_linked = self.maps_get_linked or (
                isinstance(validated_input, MapsGetPlaceInput)
                and validated_input.place_id in self._maps_place_ids
            )
        elif tool_id == "maps.directions":
            self.maps_directions_linked = self.maps_directions_linked or (
                isinstance(validated_input, MapsDirectionsInput)
                and isinstance(validated_input.destination, PlaceLocation)
                and validated_input.destination.place_id in self._maps_place_ids
            )
        elif tool_id == "web.search":
            self._web_urls.update(
                cast(str, item["url"])
                for item in cast("list[dict[str, object]]", value["results"])
            )
        elif tool_id == "web.read":
            self.web_linked = self.web_linked or (
                isinstance(validated_input, WebReadInput)
                and validated_input.url in self._web_urls
            )

    def compound_linkage_complete(self) -> bool:
        return (
            self.gmail_linked
            and self.calendar_linked
            and self.maps_get_linked
            and self.maps_directions_linked
            and self.web_linked
        )

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
        result = await self.inner.dispatch(
            binding=binding,
            validated_input=validated_input,
            plan=plan,
            budgets=budgets,
            cancellation=cancellation,
            lineage=lineage,
        )
        if result.result.get("type") == "Success":
            tool_id = str(binding.spec.id)
            value = cast("dict[str, object]", result.result["value"])
            self._record_success(
                tool_id=tool_id,
                validated_input=validated_input,
                value=value,
            )
        return result


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty without edge whitespace")
    return value


def _validate_settings(settings: Settings) -> None:
    if settings.codex_model not in _SUPPORTED_ROUTES:
        raise ValueError("model must be a qualified local-account route")
    if settings.maximum_batch_size != 1 or settings.delivery_batch_size != 1:
        raise ValueError("live qualification batch and delivery limits must both be 1")
    if settings.discord.catch_up_limit > _MAX_CATCH_UP_PAGE:
        raise ValueError("live qualification catch-up limit must not exceed 100")
    for path, label in (
        (settings.codex_state_root, "Codex state root"),
        (settings.runtime_state_directory.parent, "runtime-state parent"),
    ):
        if not path.is_absolute() or not path.is_dir():
            raise ValueError(f"{label} must be an existing absolute directory")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError(f"{label} must be private")
    if settings.runtime_state_directory.exists():
        raise ValueError("runtime state must be an unused path")


async def _require_empty_database(settings: Settings) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with engine.connect() as connection:
            counts: list[int] = []
            for table in (message, memory_log, memory_summary, action):
                counts.append(
                    cast(
                        int,
                        await connection.scalar(
                            select(func.count()).select_from(table)
                        ),
                    )
                )
    finally:
        await engine.dispose()
    if counts != [0, 0, 0, 0]:
        raise ValueError("live qualification database must be empty")


def _owner_row(row: RowMapping | None) -> RowMapping:
    if row is None:
        raise QualificationCheckFailed("canonical_owner_missing")
    if (
        row.role != "owner"
        or row.source != "discord"
        or row.processed_at is None
        or not isinstance(row.trace.get("settlement"), dict)
    ):
        raise QualificationCheckFailed("canonical_owner_not_settled")
    return row


async def _visible_count(
    *,
    channel: discord.TextChannel,
    discord_message_id: str,
    content: str,
    bot_user_id: int,
) -> tuple[int, bool]:
    fetched = await channel.fetch_message(int(discord_message_id))
    owned = fetched.author.id == bot_user_id and fetched.content == content
    if not owned:
        raise QualificationCheckFailed("delivered_response_identity_mismatch")
    visible = 0
    async for candidate in channel.history(
        limit=50,
        around=discord.Object(id=int(discord_message_id)),
    ):
        if candidate.author.id == bot_user_id and candidate.content == content:
            visible += 1
    return visible, owned


async def _run(settings: Settings) -> dict[str, object]:
    expected_source_id = _required("JARVIS_LIVE_OWNER_MESSAGE_ID")
    expected_marker = _required("JARVIS_LIVE_EXPECTED_REPLY_MARKER")
    if (
        not expected_source_id.isascii()
        or not expected_source_id.isdecimal()
        or int(expected_source_id) <= 0
    ):
        raise ValueError("expected owner source ID must be a Discord snowflake")

    verify_runtime_dependencies()
    _validate_settings(settings)
    await _require_empty_database(settings)

    from jarvis.cli import initialize_state

    initialize_state(settings)
    engine = create_engine(settings.database_url.get_secret_value())
    kernel_runtime = build_kernel_runtime(
        provider_state_root=settings.codex_state_root,
        private_cwd_parent=settings.provider_cwd_parent,
        session_ref_path=settings.session_reference_path,
        model=settings.codex_model,
        kernel_limits=SLICE2_KERNEL_LIMITS,
    )
    google_oauth_http = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    google_api_http = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    maps_http = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    brave_http = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    catalog = build_read_catalog(
        settings=settings,
        google_oauth_http=google_oauth_http,
        google_api_http=google_api_http,
        maps_http=maps_http,
        brave_http=brave_http,
    )
    chosen: DiscordOwnerMessage | None = None
    non_control_candidates = 0
    catch_up_open = True
    failure: QualificationFailure | None = None
    cleanup_failure: QualificationFailure | None = None
    result: dict[str, object] | None = None

    async def capture(incoming: DiscordOwnerMessage) -> None:
        nonlocal chosen, non_control_candidates
        if not catch_up_open:
            raise RuntimeError("owner input arrived outside bounded catch-up")
        if incoming.control is None:
            chosen = incoming
            non_control_candidates += 1

    try:
        async with deployment_ownership(engine):
            admission_limits = RollingAdmissionLimits()
            admission = RollingAdmissionPort(
                settings.admission_journal_path,
                admission_limits,
            )
            definitions = build_slice2_definitions(
                catalog=catalog,
                profile_key=settings.codex_profile_key,
                model=settings.codex_model,
                owner_timezone=settings.owner_timezone,
            )
            store = MessageStore(engine)
            dispatchers: list[_RecordingDispatcher] = []

            def dispatcher_factory() -> _RecordingDispatcher:
                dispatcher = _RecordingDispatcher(settings.host_secrets)
                dispatchers.append(dispatcher)
                return dispatcher

            runner = JarvisThreadRunner(
                settings=settings,
                store=store,
                admission=admission,
                kernel_runtime=kernel_runtime,
                definitions=definitions,
                history=PostgresCanonicalHistory(engine),
                dispatcher_factory=dispatcher_factory,
            )
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
            ) as http_client:
                recording_delivery = _RecordingDelivery(
                    DiscordCreateMessageClient(settings.discord, http_client)
                )
                service = JarvisService(
                    settings=settings,
                    store=store,
                    paused=PausedState(settings.paused_state_path),
                    delivery=recording_delivery,
                    runner=runner,
                )
                gateway: DiscordGateway
                removed = False

                async def qualify() -> None:
                    nonlocal catch_up_open, cleanup_failure, failure, removed, result
                    delivered_id: str | None = None
                    response_text: str | None = None
                    channel: discord.TextChannel | None = None
                    stage = "catch_up"
                    try:
                        catch_up = await service.gateway_ready()
                        catch_up_open = False
                        selected = chosen
                        if selected is None:
                            raise QualificationCheckFailed("owner_input_missing")
                        if selected.source_message_id != expected_source_id:
                            raise QualificationCheckFailed("owner_input_id_mismatch")
                        if expected_marker.casefold() not in selected.text.casefold():
                            raise QualificationCheckFailed("owner_marker_missing")
                        stage = "processing"
                        await service.receive_owner_message(selected)
                        async with gateway.typing():
                            outcome = await runner.run(CancellationToken())
                        if not isinstance(outcome, ThreadCompleted):
                            raise QualificationCheckFailed("thread_not_completed")
                        admission_value: object = json.loads(
                            settings.admission_journal_path.read_text(encoding="utf-8")
                        )
                        if not isinstance(admission_value, dict):
                            raise QualificationCheckFailed(
                                "admission_journal_shape_invalid"
                            )
                        admission_document = cast("dict[str, object]", admission_value)
                        reservations_value = admission_document.get("reservations")
                        if not isinstance(reservations_value, list):
                            raise QualificationCheckFailed(
                                "admission_reservation_count_invalid"
                            )
                        reservations = cast("list[object]", reservations_value)
                        if len(reservations) != 1 or not isinstance(
                            reservations[0], dict
                        ):
                            raise QualificationCheckFailed(
                                "admission_reservation_count_invalid"
                            )
                        reservation = cast("dict[str, object]", reservations[0])
                        reserved = (
                            reservation.get("reserved_turns"),
                            reservation.get("reserved_input_tokens"),
                            reservation.get("reserved_output_tokens"),
                        )
                        actual = (
                            reservation.get("actual_turns"),
                            reservation.get("actual_input_tokens"),
                            reservation.get("actual_output_tokens"),
                        )
                        expected_reserved = (
                            SLICE2_KERNEL_LIMITS.max_provider_turns
                            + admission_limits.serial_child_turns,
                            SLICE2_KERNEL_LIMITS.max_provider_input_tokens
                            + admission_limits.root_input_token_overshoot
                            + admission_limits.serial_child_input_tokens,
                            SLICE2_KERNEL_LIMITS.max_provider_output_tokens
                            + admission_limits.root_output_token_overshoot
                            + admission_limits.serial_child_output_tokens,
                        )
                        if (
                            reservation.get("run_id") != str(outcome.metrics.run_id)
                            or reservation.get("state") != "settled"
                            or reservation.get("owns_live_slot") is not False
                            or reservation.get("children") != []
                            or reserved != expected_reserved
                            or any(type(value) is not int for value in actual)
                        ):
                            raise QualificationCheckFailed(
                                "admission_settlement_invalid"
                            )
                        usage_input = outcome.metrics.usage.input_tokens
                        usage_output = outcome.metrics.usage.output_tokens
                        if usage_input is None or usage_output is None:
                            raise QualificationCheckFailed(
                                "admission_usage_unavailable"
                            )
                        expected_actual = (
                            outcome.metrics.provider_turns,
                            usage_input,
                            usage_output,
                        )
                        if actual != expected_actual or any(
                            cast("int", actual[index]) > cast("int", reserved[index])
                            for index in range(3)
                        ):
                            raise QualificationCheckFailed("admission_usage_mismatch")
                        stage = "required_reads"
                        observed_tool_ids = frozenset(
                            tool_id
                            for dispatcher in dispatchers
                            for tool_id in dispatcher.successful_tool_ids
                        )
                        if not _REQUIRED_COMPOUND_READS <= observed_tool_ids:
                            raise QualificationCheckFailed("required_reads_missing")
                        stage = "linkage"
                        if not any(
                            dispatcher.compound_linkage_complete()
                            for dispatcher in dispatchers
                        ):
                            raise QualificationCheckFailed(
                                "search_read_linkage_missing"
                            )

                        stage = "persistence"
                        async with engine.connect() as connection:
                            owner = _owner_row(
                                (
                                    await connection.execute(
                                        select(message).where(
                                            message.c.source == "discord",
                                            message.c.source_message_id
                                            == selected.source_message_id,
                                        )
                                    )
                                )
                                .mappings()
                                .one_or_none()
                            )
                            action_count = cast(
                                int,
                                await connection.scalar(
                                    select(func.count()).select_from(action)
                                ),
                            )
                        if action_count != 0:
                            raise QualificationCheckFailed("action_row_created")
                        pending = await store.pending_delivery(
                            source_conversation_id=str(settings.discord.channel_id),
                            limit=2,
                        )
                        if len(pending) != 1:
                            raise QualificationCheckFailed(
                                "persisted_response_count_invalid"
                            )
                        assistant = pending[0]
                        response_text = assistant.text
                        if not response_text.strip() or len(response_text) > 2_000:
                            raise QualificationCheckFailed(
                                "persisted_response_text_invalid"
                            )
                        if expected_marker.casefold() not in response_text.casefold():
                            raise QualificationCheckFailed(
                                "persisted_response_marker_missing"
                            )
                        settlement = cast(dict[str, object], owner.trace["settlement"])
                        if settlement.get("conclusion_message_id") != str(assistant.id):
                            raise QualificationCheckFailed(
                                "settlement_response_mismatch"
                            )

                        stage = "delivery"
                        channel = await gateway.configured_channel()
                        if gateway.user is None:
                            raise QualificationCheckFailed(
                                "discord_bot_identity_missing"
                            )
                        bot_user_id = gateway.user.id
                        flushed = await service.flush_delivery()
                        if (
                            flushed.selected != 1
                            or flushed.delivered != 1
                            or flushed.failure is not None
                            or recording_delivery.success is None
                        ):
                            raise QualificationCheckFailed("response_delivery_failed")
                        delivered_id = recording_delivery.success.discord_message_id
                        async with engine.connect() as connection:
                            source_id = await connection.scalar(
                                select(message.c.source_message_id).where(
                                    message.c.id == assistant.id
                                )
                            )
                        if source_id != delivered_id or await store.pending_delivery(
                            source_conversation_id=str(settings.discord.channel_id),
                            limit=1,
                        ):
                            raise QualificationCheckFailed(
                                "delivery_watermark_not_durable"
                            )

                        stage = "visibility"
                        visible, bot_owned = await _visible_count(
                            channel=channel,
                            discord_message_id=delivered_id,
                            content=response_text,
                            bot_user_id=bot_user_id,
                        )
                        if not bot_owned or visible != 1:
                            raise QualificationCheckFailed(
                                "response_visibility_count_invalid"
                            )
                        result = {
                            "route": settings.codex_model,
                            "revisions": {
                                **EXPECTED_GIT_PINS,
                                **EXPECTED_PACKAGE_VERSIONS,
                            },
                            "implementation": {
                                **_implementation(),
                                "main_definition_fingerprint": (
                                    definitions.main.fingerprint
                                ),
                                "session_compatibility_revision": (
                                    definitions.main.session_compatibility_revision
                                ),
                                "reasoning_effort": "high",
                            },
                            "status": "passed",
                            "catch_up": {
                                "scanned": catch_up.scanned,
                                "accepted_owner_events": catch_up.accepted,
                                "non_control_candidates": non_control_candidates,
                                "persisted": 1,
                            },
                            "canonical": {
                                "owner_settled": True,
                                "settlement_trace_present": True,
                                "assistant_persisted_before_send": True,
                                "delivery_watermark_persisted": True,
                            },
                            "live": {
                                "automatic_read_tool_ids": sorted(observed_tool_ids),
                                "stable_id_linkage": {
                                    "calendar_list_to_get": True,
                                    "gmail_search_to_read": True,
                                    "maps_search_to_directions": True,
                                    "maps_search_to_get": True,
                                    "web_search_to_read": True,
                                },
                                "zero_actions": True,
                                "useful_reply": True,
                                "visible_count": visible,
                            },
                            "usage": {
                                "provider_turns": outcome.metrics.provider_turns,
                                "input_tokens": outcome.metrics.usage.input_tokens,
                                "output_tokens": outcome.metrics.usage.output_tokens,
                            },
                            "admission": {
                                "state": "settled",
                                "owns_live_slot": False,
                                "actual": {
                                    "turns": actual[0],
                                    "input_tokens": actual[1],
                                    "output_tokens": actual[2],
                                },
                                "reserved": {
                                    "turns": reserved[0],
                                    "input_tokens": reserved[1],
                                    "output_tokens": reserved[2],
                                },
                                "matches_run_usage": True,
                                "within_reservation": True,
                            },
                            "timing_ms": round(
                                outcome.metrics.duration_seconds * 1_000
                            ),
                            "expected_owner_id_enforced": True,
                            "expected_marker_enforced": True,
                        }
                    except BaseException as exc:
                        failure = _failure(stage, exc)
                    finally:
                        cleanup_id = delivered_id
                        if recording_delivery.success is not None:
                            cleanup_id = recording_delivery.success.discord_message_id
                        if channel is not None and cleanup_id is not None:
                            try:
                                await channel.get_partial_message(
                                    int(cleanup_id)
                                ).delete()
                                removed = True
                            except BaseException as exc:
                                cleanup_failure = QualificationFailure(
                                    "cleanup",
                                    type(exc).__name__,
                                    "response_delete_failed",
                                )
                        elif cleanup_id is not None:
                            cleanup_failure = QualificationFailure(
                                "cleanup",
                                "RuntimeError",
                                "cleanup_channel_unavailable",
                            )
                        try:
                            await gateway.close()
                        except BaseException as exc:
                            if cleanup_failure is None:
                                cleanup_failure = QualificationFailure(
                                    "cleanup",
                                    type(exc).__name__,
                                    "gateway_close_failed",
                                )

                gateway = DiscordGateway(
                    settings.discord,
                    capture,
                    ready_handler=qualify,
                )
                service.bind_gateway(gateway)
                gateway_failure: QualificationFailure | None = None
                try:
                    async with asyncio.timeout(600.0):
                        await gateway.start(
                            settings.discord.bot_token.get_secret_value()
                        )
                except BaseException as exc:
                    gateway_failure = QualificationFailure(
                        "processing", type(exc).__name__, "gateway_run_failed"
                    )
                finally:
                    try:
                        await gateway.close()
                    except BaseException as exc:
                        if cleanup_failure is None:
                            cleanup_failure = QualificationFailure(
                                "cleanup",
                                type(exc).__name__,
                                "gateway_close_failed",
                            )
                if failure is not None:
                    if cleanup_failure is not None:
                        raise QualificationFailure(
                            failure.stage,
                            failure.cause_type,
                            failure.reason_code,
                            cleanup=cleanup_failure,
                        ) from None
                    raise failure from None
                if cleanup_failure is not None:
                    raise cleanup_failure from None
                if gateway_failure is not None:
                    raise gateway_failure from None
                if gateway.event_failed:
                    raise QualificationFailure(
                        "processing", "RuntimeError", "gateway_event_failed"
                    )
                if result is None:
                    raise QualificationFailure(
                        "processing", "RuntimeError", "result_missing"
                    )
                if not removed:
                    raise QualificationFailure(
                        "cleanup", "RuntimeError", "response_not_removed"
                    )
                result["synthetic_response_removed"] = True
                return result
    finally:
        await google_oauth_http.aclose()
        await google_api_http.aclose()
        await maps_http.aclose()
        await brave_http.aclose()
        await kernel_runtime.close()
        await engine.dispose()


def main() -> int:
    route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    try:
        if os.environ.get("JARVIS_LIVE_E2E") != "1":
            raise ValueError("live qualification requires JARVIS_LIVE_E2E=1")
        settings = Settings.from_env()
        result = asyncio.run(_run(settings))
    except QualificationFailure as exc:
        failure_result: dict[str, object] = {
            "reason_code": exc.reason_code,
            "stage": exc.stage,
            "type": exc.cause_type,
        }
        if exc.cleanup is not None:
            failure_result["cleanup"] = {
                "reason_code": exc.cleanup.reason_code,
                "stage": exc.cleanup.stage,
                "type": exc.cleanup.cause_type,
            }
        result = {
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "implementation": _implementation(),
            "failure": failure_result,
            "status": "failed",
        }
    except BaseException as exc:
        result = {
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "implementation": _implementation(),
            "failure": {
                "reason_code": "unexpected_exception",
                "stage": "setup",
                "type": type(exc).__name__,
            },
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

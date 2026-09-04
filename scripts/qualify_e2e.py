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
from typing import cast
from uuid import UUID

import discord
import httpx
from llm_agent_kernel import CancellationToken, ThreadCompleted
from sqlalchemy import RowMapping, func, select

from jarvis.admission import RollingAdmissionLimits, RollingAdmissionPort
from jarvis.db import action, create_engine, memory_log, memory_summary, message
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    EXPECTED_PACKAGE_VERSIONS,
    build_slice1_definitions,
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
from jarvis.service import JarvisService, Slice1ThreadRunner
from jarvis.settings import Settings
from jarvis.state import PausedState

_SUPPORTED_ROUTES = frozenset({"gpt-5.6-terra", "gpt-5.4"})
_MAX_CATCH_UP_PAGE = 100


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


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty without edge whitespace")
    return value


def _validate_settings(settings: Settings) -> None:
    if settings.codex_model not in _SUPPORTED_ROUTES:
        raise ValueError("model must be one of the two qualified routes")
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
        raise RuntimeError("canonical owner row is missing")
    if (
        row.role != "owner"
        or row.source != "discord"
        or row.processed_at is None
        or not isinstance(row.trace.get("settlement"), dict)
    ):
        raise RuntimeError("canonical owner row was not durably settled")
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
        raise RuntimeError("delivered response identity did not match")
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
    )
    chosen: DiscordOwnerMessage | None = None
    non_control_candidates = 0
    catch_up_open = True
    failure: BaseException | None = None
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
            admission = RollingAdmissionPort(
                settings.admission_journal_path,
                RollingAdmissionLimits(),
            )
            definitions = build_slice1_definitions(
                profile_key=settings.codex_profile_key,
                model=settings.codex_model,
                owner_timezone=settings.owner_timezone,
            )
            store = MessageStore(engine)
            runner = Slice1ThreadRunner(
                settings=settings,
                store=store,
                admission=admission,
                kernel_runtime=kernel_runtime,
                definitions=definitions,
                history=PostgresCanonicalHistory(engine),
            )
            async with httpx.AsyncClient() as http_client:
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
                    nonlocal catch_up_open, failure, removed, result
                    delivered_id: str | None = None
                    response_text: str | None = None
                    channel: discord.TextChannel | None = None
                    try:
                        catch_up = await service.gateway_ready()
                        catch_up_open = False
                        selected = chosen
                        if selected is None:
                            raise RuntimeError(
                                "bounded catch-up found no non-control owner input"
                            )
                        if selected.source_message_id != expected_source_id:
                            raise RuntimeError("newest owner input was not expected")
                        if expected_marker.casefold() not in selected.text.casefold():
                            raise RuntimeError(
                                "newest owner input lacked expected marker"
                            )
                        await service.receive_owner_message(selected)
                        async with gateway.typing():
                            outcome = await runner.run(CancellationToken())
                        if not isinstance(outcome, ThreadCompleted):
                            raise RuntimeError("live Jarvis run did not complete")

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
                        pending = await store.pending_delivery(
                            source_conversation_id=str(settings.discord.channel_id),
                            limit=2,
                        )
                        if len(pending) != 1:
                            raise RuntimeError(
                                "run did not persist exactly one response"
                            )
                        assistant = pending[0]
                        response_text = assistant.text
                        if not response_text.strip() or len(response_text) > 2_000:
                            raise RuntimeError("persisted response was not useful text")
                        if expected_marker.casefold() not in response_text.casefold():
                            raise RuntimeError("response lacked expected marker")
                        settlement = cast(dict[str, object], owner.trace["settlement"])
                        if settlement.get("conclusion_message_id") != str(assistant.id):
                            raise RuntimeError(
                                "owner settlement did not name the response"
                            )

                        channel = await gateway.configured_channel()
                        if gateway.user is None:
                            raise RuntimeError("Discord bot identity is unavailable")
                        bot_user_id = gateway.user.id
                        flushed = await service.flush_delivery()
                        if (
                            flushed.selected != 1
                            or flushed.delivered != 1
                            or flushed.failure is not None
                            or recording_delivery.success is None
                        ):
                            raise RuntimeError("persisted response delivery failed")
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
                            raise RuntimeError("delivery watermark was not durable")

                        visible, bot_owned = await _visible_count(
                            channel=channel,
                            discord_message_id=delivered_id,
                            content=response_text,
                            bot_user_id=bot_user_id,
                        )
                        if not bot_owned or visible != 1:
                            raise RuntimeError(
                                "live response was not visible exactly once"
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
                                "useful_reply": True,
                                "visible_count": visible,
                            },
                            "usage": {
                                "provider_turns": outcome.metrics.provider_turns,
                                "input_tokens": outcome.metrics.usage.input_tokens,
                                "output_tokens": outcome.metrics.usage.output_tokens,
                            },
                            "timing_ms": round(
                                outcome.metrics.duration_seconds * 1_000
                            ),
                            "expected_owner_id_enforced": True,
                            "expected_marker_enforced": True,
                        }
                    except BaseException as exc:
                        failure = exc
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
                                failure = exc
                        await gateway.close()

                gateway = DiscordGateway(
                    settings.discord,
                    capture,
                    ready_handler=qualify,
                )
                service.bind_gateway(gateway)
                async with asyncio.timeout(600.0):
                    await gateway.start(settings.discord.bot_token.get_secret_value())
                if gateway.event_failed:
                    raise RuntimeError("Discord Gateway event failed")
                if failure is not None:
                    raise RuntimeError("live qualification failed") from failure
                if result is None or not removed:
                    raise RuntimeError("live qualification did not cleanly finish")
                result["synthetic_response_removed"] = True
                return result
    finally:
        await kernel_runtime.close()
        await engine.dispose()


def main() -> int:
    route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    try:
        if os.environ.get("JARVIS_LIVE_E2E") != "1":
            raise ValueError("live qualification requires JARVIS_LIVE_E2E=1")
        settings = Settings.from_env()
        result = asyncio.run(_run(settings))
    except BaseException:
        result = {
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "implementation": _implementation(),
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

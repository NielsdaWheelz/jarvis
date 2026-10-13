"""Minimal Jarvis service and operator entry points."""

from __future__ import annotations

import argparse
import asyncio
import grp
import json
import logging
import os
import stat
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from socket import socket
from uuid import UUID

import httpx
import uvicorn
from llm_agent_kernel import CancellationToken
from llm_tools import FrozenToolPlan
from provider_runtime.agent_runtime import AgentRuntime
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import MemoryError, MemoryStore
from universal_memory.policy import bounded_text
from universal_memory.schema import source_conversation

from jarvis.actions import ActionPersistenceDefect, ActionStore
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.approval import ApprovalRenderError, render_approval
from jarvis.approval_runtime import (
    ApprovalActionHandler,
    ApprovalAwareDiscordDelivery,
    ApprovalRecoveryDisabler,
)
from jarvis.codex_config import CodexHostConfig
from jarvis.config import ConfigurationError
from jarvis.db import create_engine, normalize_database_url
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.definitions import (
    RoleDefinitions,
    build_compactor,
    build_definitions,
    build_dreamer,
    build_write_gate,
)
from jarvis.discord import DiscordCreateMessageClient, DiscordGateway
from jarvis.embeddings import OpenAIEmbedder
from jarvis.kernel import (
    build_agent_runtime,
    build_kernel_runtime,
    resolve_provider_configuration,
)
from jarvis.memory_config import MEMORY_IDENTITIES, MemoryConfig
from jarvis.memory_http import create_memory_app
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import compose_memory_catalog
from jarvis.memory_workers import DreamerRunCompleted, DreamerWorker, MemoryWorker
from jarvis.messages import MessageStore
from jarvis.native_cutover import (
    cutover_native,
    require_native_data,
    require_native_files,
)
from jarvis.native_runtime import (
    NativeRunner,
    recover_native_products,
)
from jarvis.ownership import (
    Database,
    DeploymentAlreadyOwned,
    deployment_ownership,
)
from jarvis.proactivity import ProcessLocalWakeTimer
from jarvis.process_security import deny_same_identity_process_inspection
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.service import JarvisService
from jarvis.settings import Settings
from jarvis.state import PausedState
from jarvis.tool_composition import ToolComposition, build_tool_composition
from jarvis.tool_results import memory_result_size, memory_view_size
from jarvis.write_dispatch import (
    ActionRecovery,
    WriteToolDispatcher,
    gmail_send_basis_is_current,
    require_current_action_binding,
)
from jarvis.write_gate import AutomaticWriteGate
from jarvis.write_tools import GmailSendDraftInput

LOGGER = logging.getLogger(__name__)


class StartupDefect(RuntimeError):
    """The configured private runtime layout is unsafe or incomplete."""


class _MemoryHTTPServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        """The application Runner owns cooperative signal handling."""
        yield

    async def serve(self, sockets: list[socket] | None = None) -> None:
        try:
            await super().serve(sockets)
        except SystemExit as error:
            raise RuntimeError("memory endpoint could not start") from error


@asynccontextmanager
async def _memory_service(
    settings: Settings,
    config: MemoryConfig,
    database: Database,
    http: httpx.AsyncClient,
) -> AsyncIterator[MemoryService]:
    read_engine = create_engine(
        settings.database_url.get_secret_value(), memory_reads=True
    )
    try:
        yield MemoryService(
            library=MemoryStore(
                read_engine,
                result_size=memory_result_size,
                view_size=memory_view_size,
            ),
            database=database,
            embedder=OpenAIEmbedder(
                settings.embedding_openai_api_key, http_client=http
            ),
            admitted_lanes=config.admitted_lanes,
            nexus_admitted_owner=config.nexus_admitted_owner,
            guild_id=settings.discord.guild_id,
            channel_id=settings.discord.channel_id,
        )
    finally:
        await read_engine.dispose()


@dataclass(frozen=True, slots=True)
class _IsolatedMemoryRuntime:
    memory: MemoryService
    compactor: MemoryWorker
    dreamer: DreamerWorker


@asynccontextmanager
async def _isolated_memory_runtime(
    *,
    settings: Settings,
    config: MemoryConfig,
    host: CodexHostConfig,
    database: Database,
    owner: JarvisOwner,
) -> AsyncIterator[_IsolatedMemoryRuntime]:
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        async with _memory_service(settings, config, database, http) as memory:
            catalog = compose_memory_catalog(memory)
            runtime = build_agent_runtime(
                provider_state_root=settings.runtime_state_directory,
                codex_endpoints=host.endpoints,
            )
            kernel = None
            try:
                provider = await resolve_provider_configuration(
                    runtime=runtime,
                    profile_key=settings.codex_profile_key,
                    model_key=settings.codex_model,
                )
                compactor_definition, compactor_plan = build_compactor(
                    catalog=catalog,
                    provider=provider,
                    owner_timezone=settings.owner_timezone,
                )
                dreamer_definition, dreamer_plan = build_dreamer(
                    catalog=catalog,
                    provider=provider,
                    owner_timezone=settings.owner_timezone,
                )
                kernel = build_kernel_runtime(
                    runtime=runtime,
                    shared_cwd_parent=Path(host.cognition_cwd_parent),
                )
                compactor = MemoryWorker(
                    definition=compactor_definition,
                    plan=compactor_plan,
                    owner=owner,
                    provider=kernel.provider,
                    memory=memory,
                )
                yield _IsolatedMemoryRuntime(
                    memory,
                    compactor,
                    DreamerWorker(
                        definition=dreamer_definition,
                        plan=dreamer_plan,
                        owner=owner,
                        provider=kernel.provider,
                        memory=memory,
                        compactor=compactor,
                        owner_timezone=settings.owner_timezone,
                        nightly_time=settings.memory_nightly_time,
                    ),
                )
            finally:
                if kernel is None:
                    await runtime.close()
                else:
                    await kernel.close()


def _private_directory(path: Path, name: str) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise StartupDefect(f"{name} is unavailable") from exc
    if not path.is_dir() or mode & 0o077:
        raise StartupDefect(f"{name} must be a private directory")


def _shared_cognition_directory(path: Path, group: str) -> None:
    try:
        metadata = path.stat()
        group_id = grp.getgrnam(group).gr_gid
    except (KeyError, OSError) as exc:
        raise StartupDefect("cognition cwd parent is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o2750
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != group_id
    ):
        raise StartupDefect(
            "cognition cwd parent must be owned by Jarvis and the configured group "
            "with mode 02750"
        )


def _validate_runtime_layout(settings: Settings, host: CodexHostConfig) -> None:
    _private_directory(settings.runtime_state_directory, "runtime state directory")
    _shared_cognition_directory(Path(host.cognition_cwd_parent), host.client_group)


async def initialize_state(settings: Settings, host: CodexHostConfig) -> None:
    """Prepare private provider state and a canonical fresh deployment pause."""

    _shared_cognition_directory(Path(host.cognition_cwd_parent), host.client_group)
    directory = settings.runtime_state_directory
    if directory.exists():
        _private_directory(directory, "runtime state directory")
    else:
        try:
            directory.mkdir(mode=0o700)
        except OSError as exc:
            raise StartupDefect("runtime state directory could not be created") from exc
    require_native_files(directory)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            await require_native_data(
                database, conversation_id=str(settings.discord.channel_id)
            )
            await MessageStore(database).initialize_paused(
                str(settings.discord.channel_id)
            )
    finally:
        await engine.dispose()


async def recover_startup_actions(
    *,
    action_recovery: ActionRecovery,
    paused: PausedState,
    messages: MessageStore,
) -> int:
    inactive = await paused.is_paused() or await messages.circuit_is_open()
    return await action_recovery.recover(allow_queued_execution=not inactive)


async def run_service(
    service: JarvisService,
    gateway: DiscordGateway,
    token: str,
    shutdown: asyncio.Event,
    memory_http: uvicorn.Server,
) -> None:
    """Own the worker, Gateway and memory endpoint with their dependencies."""
    if shutdown.is_set():
        return
    worker = asyncio.create_task(service.run_worker(), name="jarvis-worker")

    async def run_gateway() -> None:
        await gateway.start(token)
        if gateway.event_failed:
            raise RuntimeError("Discord event processing failed")

    gateway_task = asyncio.create_task(run_gateway(), name="jarvis-discord-gateway")
    http_task = asyncio.create_task(memory_http.serve(), name="jarvis-memory-http")
    stopping = asyncio.create_task(shutdown.wait(), name="jarvis-shutdown-request")
    try:
        done, _ = await asyncio.wait(
            {worker, gateway_task, http_task, stopping},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
        if http_task in done and not shutdown.is_set():
            raise RuntimeError("memory endpoint stopped before application shutdown")
    finally:
        memory_http.should_exit = True
        gateway.stop_ingress()
        service.request_shutdown()
        stopping.cancel()  # This task only waits on an Event; it owns no I/O.
        await asyncio.gather(stopping, return_exceptions=True)
        results = await asyncio.gather(
            worker, gateway.drain_callbacks(), http_task, return_exceptions=True
        )
        try:
            await gateway.close()
        finally:
            await gateway_task
        for result in results:
            if isinstance(result, BaseException):
                raise result


async def _compose_main(
    *,
    settings: Settings,
    agent_runtime: AgentRuntime,
    actions: ActionStore,
    memory: MemoryService,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
) -> tuple[ToolComposition, RoleDefinitions, AgentController]:
    """Compose the release's tools and role plans from the live codex catalog."""

    provider_configuration = await resolve_provider_configuration(
        runtime=agent_runtime,
        profile_key=settings.codex_profile_key,
        model_key=settings.codex_model,
    )
    provisional_gate, _ = build_write_gate(
        provider=provider_configuration,
    )
    agents = AgentController(
        cli_path=settings.agent_cli_path,
        client_config_path=settings.agent_client_config_path,
        actions=actions,
        source_conversation_id=str(settings.discord.channel_id),
    )
    composition = build_tool_composition(
        settings=settings,
        google_oauth_http=google_oauth_http,
        google_api_http=google_api_http,
        maps_http=maps_http,
        brave_http=brave_http,
        memory=memory,
        actions=actions,
        agents=agents,
        automatic_write_gate_definition_fingerprint=provisional_gate.fingerprint,
    )
    definitions = build_definitions(
        catalog=composition.catalog,
        provider=provider_configuration,
        owner_timezone=settings.owner_timezone,
    )
    if definitions.automatic_write_gate.fingerprint != provisional_gate.fingerprint:
        raise StartupDefect("write-gate definition changed during composition")
    return composition, definitions, agents


async def serve(settings: Settings, host: CodexHostConfig) -> None:
    """Translate the Runner's first SIGINT into a cooperative stop request."""
    shutdown = asyncio.Event()
    running = asyncio.create_task(_serve(settings, host, shutdown), name="jarvis-owned")
    try:
        await asyncio.shield(running)
    except asyncio.CancelledError:
        shutdown.set()
        await running
        raise


async def _serve(
    settings: Settings, host: CodexHostConfig, shutdown: asyncio.Event
) -> None:
    """Own the deployment and run the one Discord channel service."""

    deny_same_identity_process_inspection()
    _validate_runtime_layout(settings, host)
    require_native_files(settings.runtime_state_directory)
    engine = create_engine(settings.database_url.get_secret_value())
    config = MemoryConfig.load(settings.memory_config_path)
    agent_runtime = None
    kernel_runtime = None
    try:
        async with deployment_ownership(
            engine, memory_admitted=config.jarvis_admitted
        ) as database:
            try:
                store = MessageStore(database)
                owner = JarvisOwner(database, str(settings.discord.channel_id))
                await require_native_data(database, conversation_id=owner.scope_id)
                await recover_native_products(owner)
                paused = PausedState(store, owner.scope_id)
                dispatch_lane = asyncio.Lock()
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
                    discord_http = await clients.enter_async_context(
                        httpx.AsyncClient(trust_env=False, follow_redirects=False)
                    )
                    embedding_http = await clients.enter_async_context(
                        httpx.AsyncClient(trust_env=False, follow_redirects=False)
                    )
                    memory = await clients.enter_async_context(
                        _memory_service(settings, config, database, embedding_http)
                    )
                    actions = ActionStore(database)
                    agent_runtime = build_agent_runtime(
                        provider_state_root=settings.runtime_state_directory,
                        codex_endpoints=host.endpoints,
                    )
                    composition, definitions, agents = await _compose_main(
                        settings=settings,
                        agent_runtime=agent_runtime,
                        actions=actions,
                        memory=memory,
                        google_oauth_http=google_oauth_http,
                        google_api_http=google_api_http,
                        maps_http=maps_http,
                        brave_http=brave_http,
                    )
                    kernel_runtime = build_kernel_runtime(
                        runtime=agent_runtime,
                        shared_cwd_parent=Path(host.cognition_cwd_parent),
                    )

                    gate = AutomaticWriteGate(
                        definition=definitions.automatic_write_gate,
                        plan=definitions.plans["automatic_write_gate"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        model_decisions=lambda: PostgresModelDecisionJournal(database),
                    )
                    compactor = MemoryWorker(
                        definition=definitions.compactor,
                        plan=definitions.plans["compactor"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        memory=memory,
                    )
                    dreamer = DreamerWorker(
                        definition=definitions.dreamer,
                        plan=definitions.plans["dreamer"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        memory=memory,
                        compactor=compactor,
                        owner_timezone=settings.owner_timezone,
                        nightly_time=settings.memory_nightly_time,
                    )
                    runner = NativeRunner(
                        settings=settings,
                        store=store,
                        owner=owner,
                        kernel_runtime=kernel_runtime,
                        definitions=definitions,
                        actions=actions,
                        dispatcher_factory=lambda checkpoint: (
                            WriteToolDispatcher(
                                checkpoint=checkpoint,
                                dispatch_lane=dispatch_lane,
                                gate=gate,
                                actions=actions,
                                google_write=composition.google_write,
                                agents=agents,
                                read=ReadToolDispatcher(
                                    host_secrets=settings.host_secrets,
                                    recorder=PostgresReadRecorder(database),
                                    memory=memory,
                                    cutoff=checkpoint.memory_cutoff,
                                ),
                                owner_timezone=settings.owner_timezone,
                                source_conversation_id=str(settings.discord.channel_id),
                                verified_owner_only_calendar_ids=(
                                    settings.verified_owner_only_calendar_ids
                                ),
                                host_secrets=settings.host_secrets,
                                schedule_changed=schedule_changed,
                            )
                        ),
                        memory=memory,
                        memory_worker=compactor,
                    )
                    discord_delivery = DiscordCreateMessageClient(
                        settings.discord, discord_http
                    )
                    delivery = ApprovalAwareDiscordDelivery(
                        actions=actions,
                        plan=definitions.plans["main"],
                        discord=discord_delivery,
                    )
                    wake_timer: ProcessLocalWakeTimer | None = None

                    def schedule_changed() -> None:
                        agents.notify_wait_changed()
                        if wake_timer is not None:
                            wake_timer.notify_changed()

                    action_recovery = ActionRecovery(
                        actions=actions,
                        google_write=composition.google_write,
                        plan=definitions.plans["main"],
                        source_conversation_id=str(settings.discord.channel_id),
                        schedule_changed=schedule_changed,
                        approval_disabler=ApprovalRecoveryDisabler(
                            actions=actions,
                            discord=discord_delivery,
                        ),
                    )
                    approval_handler = ApprovalActionHandler(
                        actions=actions,
                        plan=definitions.plans["main"],
                        source_conversation_id=str(settings.discord.channel_id),
                    )
                    approval_disabler = ApprovalRecoveryDisabler(
                        actions=actions,
                        discord=discord_delivery,
                    )

                    async def disable_stopped_approvals() -> None:
                        async with database.connect() as connection:
                            ids = tuple(
                                (
                                    await connection.execute(
                                        text(
                                            "select a.id from action a join message m "
                                            "on m.id = a.approval_message_id "
                                            "where a.status = 'cancelled' "
                                            "and a.result->>'reason_code' "
                                            "= 'owner_stopped' "
                                            "and m.source_conversation_id = :scope "
                                            "and m.source_message_id is not null"
                                        ),
                                        {"scope": owner.scope_id},
                                    )
                                ).scalars()
                            )
                        for identifier in ids:
                            stored = await actions.get(identifier)
                            assert stored is not None
                            await approval_disabler(stored)

                    service = JarvisService(
                        settings=settings,
                        store=store,
                        paused=paused,
                        delivery=delivery,
                        runner=runner,
                        background=compactor,
                        memory=memory,
                        dreamer=dreamer,
                        scheduled_wakes=actions,
                        action_plan=definitions.plans["main"],
                        action_recovery=action_recovery,
                        agent_waits=agents,
                        approval_handler=approval_handler,
                        dispatch_lane=dispatch_lane,
                        disable_stopped_approvals=disable_stopped_approvals,
                    )
                    wake_timer = ProcessLocalWakeTimer(
                        store=actions,
                        on_due=service.request_work,
                    )
                    service.bind_wake_timer(wake_timer)
                    if shutdown.is_set():
                        return
                    recovered_actions = await recover_startup_actions(
                        action_recovery=action_recovery,
                        paused=paused,
                        messages=store,
                    )
                    if recovered_actions:
                        LOGGER.warning(
                            "Recovered interrupted actions: count=%d",
                            recovered_actions,
                        )

                    async def ready() -> None:
                        result = await service.gateway_ready()
                        LOGGER.info(
                            "Discord catch-up completed: "
                            "scanned=%d accepted=%d bounded=%s",
                            result.scanned,
                            result.accepted,
                            result.reached_scan_limit,
                        )

                    gateway = DiscordGateway(
                        settings.discord,
                        service.receive_owner_message,
                        ready_handler=ready,
                        approval_interaction_sink=(
                            service.receive_approval_interaction
                        ),
                    )
                    service.bind_gateway(gateway)
                    await run_service(
                        service,
                        gateway,
                        settings.discord.bot_token.get_secret_value(),
                        shutdown,
                        _MemoryHTTPServer(
                            uvicorn.Config(
                                create_memory_app(memory, config),
                                host="127.0.0.1",
                                port=settings.memory_http_port,
                                lifespan="on",
                                access_log=False,
                                log_level="warning",
                            )
                        ),
                    )
            finally:
                if kernel_runtime is not None:
                    await kernel_runtime.close()
                elif agent_runtime is not None:
                    await agent_runtime.close()
    finally:
        await engine.dispose()


async def release_parked(settings: Settings, message_ids: tuple[UUID, ...]) -> None:
    """Clear only the named parked markers while holding deployment ownership."""

    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            await MessageStore(database).clear_parked(message_ids=message_ids)
    finally:
        await engine.dispose()


async def stopped_native_cutover(settings: Settings, host: CodexHostConfig) -> int:
    """Convert the stopped deployment before native activation."""
    _validate_runtime_layout(settings, host)
    config = MemoryConfig.load(settings.memory_config_path)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False
            ) as http:
                runtime = build_agent_runtime(
                    provider_state_root=settings.runtime_state_directory,
                    codex_endpoints=host.endpoints,
                )
                try:
                    async with _memory_service(
                        settings, config, database, http
                    ) as memory:
                        _, definitions, _ = await _compose_main(
                            settings=settings,
                            agent_runtime=runtime,
                            actions=ActionStore(database),
                            memory=memory,
                            google_oauth_http=http,
                            google_api_http=http,
                            maps_http=http,
                            brave_http=http,
                        )
                        return await cutover_native(
                            database,
                            directory=settings.runtime_state_directory,
                            conversation_id=str(settings.discord.channel_id),
                            plan=definitions.plans["main"],
                        )
                finally:
                    await runtime.close()
    finally:
        await engine.dispose()


async def _require_paused(database: Database, settings: Settings) -> None:
    require_native_files(settings.runtime_state_directory)
    scope = str(settings.discord.channel_id)
    await require_native_data(database, conversation_id=scope)
    if not await MessageStore(database).paused(scope):
        raise StartupDefect("activation requires a canonical deployment pause")


async def check_paused(settings: Settings) -> None:
    """Check stopped canonical pause without opening a provider or connector."""
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            await _require_paused(database, settings)
    finally:
        await engine.dispose()


async def check_activation(
    settings: Settings,
    host: CodexHostConfig,
) -> tuple[tuple[UUID, str, str, str], ...]:
    """Classify unfinished execution authority; read-only."""

    deny_same_identity_process_inspection()
    config = MemoryConfig.load(settings.memory_config_path)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with (
            deployment_ownership(engine) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            await _require_paused(database, settings)
            actions = ActionStore(database)
            agent_runtime = build_agent_runtime(
                provider_state_root=settings.runtime_state_directory,
                codex_endpoints=host.endpoints,
            )
            try:
                async with _memory_service(settings, config, database, http) as memory:
                    # No connector dispatches during the activation check.
                    _, definitions, _ = await _compose_main(
                        settings=settings,
                        agent_runtime=agent_runtime,
                        actions=actions,
                        memory=memory,
                        google_oauth_http=http,
                        google_api_http=http,
                        maps_http=http,
                        brave_http=http,
                    )
                    plan = definitions.plans["main"]
                    # End the locked read before loading any action.
                    async with database.connect() as connection:
                        unfinished = (
                            await connection.execute(
                                text(
                                    "select id, status, tool_name from action "
                                    "where status = any(:statuses) "
                                    "order by created_at, id"
                                ),
                                {
                                    "statuses": [
                                        "queued",
                                        "awaiting_approval",
                                        "executing",
                                        "uncertain",
                                    ]
                                },
                            )
                        ).all()
                    verdicts: list[tuple[UUID, str, str, str]] = []
                    for action_id, status, tool_name in unfinished:
                        verdict = (
                            "in_flight"
                            if status in {"executing", "uncertain"}
                            else await _pending_action_verdict(actions, plan, action_id)
                        )
                        verdicts.append((action_id, status, tool_name, verdict))
                    return tuple(verdicts)
            finally:
                await agent_runtime.close()
    finally:
        await engine.dispose()


async def _pending_action_verdict(
    actions: ActionStore,
    plan: FrozenToolPlan,
    action_id: UUID,
) -> str:
    """Apply startup recovery's revalidation to one queued or pending row."""

    try:
        stored = await actions.get(action_id)
    except ActionPersistenceDefect:
        return "incompatible does_not_load"
    if stored is None:
        raise ActionPersistenceDefect("unfinished action vanished under the lock")
    try:
        binding = require_current_action_binding(stored, plan)
    except RuntimeError:
        return "incompatible binding"
    value = binding.spec.input_type.model_validate(stored.arguments).arguments
    if stored.status == "awaiting_approval":
        try:
            render_approval(stored.id, stored.tool_name, value)
        except ApprovalRenderError:
            return "incompatible render"
    if isinstance(value, GmailSendDraftInput):
        try:
            current = await gmail_send_basis_is_current(actions, value)
        except ValueError:
            return "incompatible gmail_basis"
        if not current:
            return "incompatible gmail_basis"
    return "compatible"


async def dream_once(
    settings: Settings, host: CodexHostConfig
) -> DreamerRunCompleted | None:
    """One bounded stopped manual dream, without changing its nightly marker."""
    _validate_runtime_layout(settings, host)
    config = MemoryConfig.load(settings.memory_config_path)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(
            engine, memory_admitted=config.jarvis_admitted
        ) as database:
            async with _isolated_memory_runtime(
                settings=settings,
                config=config,
                host=host,
                database=database,
                owner=JarvisOwner(database, str(settings.discord.channel_id)),
            ) as runtime:
                return await runtime.dreamer.run_at(
                    as_of=datetime.now(UTC), cancellation=CancellationToken()
                )
    finally:
        await engine.dispose()


async def rebuild_memory(
    settings: Settings, host: CodexHostConfig, node: str | None = None
) -> None:
    """Refold admitted originals while stopped; preserve capture and dream progress."""
    _validate_runtime_layout(settings, host)
    config = MemoryConfig.load(settings.memory_config_path)
    start = count = None
    if node is not None:
        values = node.split("+")
        if len(values) != 2 or any(not value.isdecimal() for value in values):
            raise ValueError("node must be START+COUNT")
        start, count = map(int, values)
    memory_settings = settings
    if node is None:
        migration_url = os.environ.get("JARVIS_MIGRATION_DATABASE_URL")
        if not migration_url:
            raise ConfigurationError(
                "full rebuild requires the migration database role"
            )
        runtime_database = make_url(
            normalize_database_url(settings.database_url.get_secret_value())
        )
        migration_database = make_url(normalize_database_url(migration_url))
        if (
            runtime_database.host,
            runtime_database.port,
            runtime_database.database,
        ) != (
            migration_database.host,
            migration_database.port,
            migration_database.database,
        ):
            raise ConfigurationError("maintenance must use the configured database")
        memory_settings = settings.model_copy(
            update={"database_url": SecretStr(migration_url)}
        )
    engine = create_engine(memory_settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(
            engine, memory_admitted=config.jarvis_admitted
        ) as database:
            async with _isolated_memory_runtime(
                settings=memory_settings,
                config=config,
                host=host,
                database=database,
                owner=JarvisOwner(database, str(settings.discord.channel_id)),
            ) as runtime:
                async with database.begin() as connection:
                    await runtime.memory.library.rebuild(connection, start, count)
                cancellation = CancellationToken()
                await runtime.compactor.ensure_ready(
                    await runtime.memory.library.cutoff(), cancellation
                )
                if node is None:
                    while await runtime.memory.library.embedding_candidates(1):
                        if not await runtime.compactor.index_one(cancellation):
                            raise RuntimeError(
                                "memory rebuild embedding failed; "
                                "derived work remains pending"
                            )
    finally:
        await engine.dispose()


async def memory_status(settings: Settings) -> dict[str, object]:
    config = MemoryConfig.load(settings.memory_config_path)
    engine = create_engine(settings.database_url.get_secret_value(), memory_reads=True)
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
            memory = MemoryService(
                library=MemoryStore(
                    engine,
                    result_size=memory_result_size,
                    view_size=memory_view_size,
                ),
                database=engine,
                embedder=OpenAIEmbedder(
                    settings.embedding_openai_api_key, http_client=http
                ),
                admitted_lanes=config.admitted_lanes,
                nexus_admitted_owner=config.nexus_admitted_owner,
                guild_id=settings.discord.guild_id,
                channel_id=settings.discord.channel_id,
            )
            declared = {(lane.machine, lane.account): lane for lane in config.lanes}
            return {
                "memory": await memory.library.status(),
                "publication_backlog": len(await memory.pending_publication()),
                "declaration_sha256": config.declaration_sha256,
                "nexus_client": {
                    "declared": config.nexus_client is not None,
                    "admit": config.nexus_admitted_owner is not None,
                    "connect": config.nexus_client is not None
                    and config.nexus_client.connect,
                    "processors": list(config.processors.nexus_model_processors),
                },
                "lanes": [
                    {
                        "machine": machine,
                        "account": account,
                        "declared": (machine, account) in declared,
                        "admit": (machine, account) in config.admitted_lanes,
                        "connect": (machine, account) in declared
                        and declared[machine, account].connect,
                    }
                    for machine, account in sorted(MEMORY_IDENTITIES)
                ],
            }
    finally:
        await engine.dispose()


async def retry_memory(settings: Settings, conversation: str | None) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            library = MemoryStore(engine)
            async with database.begin() as connection:
                if conversation is None:
                    await library.retry_compression(connection)
                else:
                    try:
                        identifier = UUID(conversation)
                    except ValueError:
                        provider, separator, native_id = conversation.partition(":")
                        if not separator or provider not in {
                            "codex",
                            "claude",
                            "jarvis",
                        }:
                            raise MemoryError("invalid_input") from None
                        bounded_text(native_id, 256)
                        identities = (
                            (
                                await connection.execute(
                                    select(source_conversation.c.id)
                                    .where(
                                        source_conversation.c.provider == provider,
                                        source_conversation.c.native_id == native_id,
                                    )
                                    .limit(2)
                                )
                            )
                            .scalars()
                            .all()
                        )
                        if not identities:
                            raise MemoryError("not_found") from None
                        if len(identities) != 1:
                            raise MemoryError("ambiguous_source_use_uuid") from None
                        identifier = identities[0]
                    await library.retry_capture(connection, identifier)
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the Jarvis Discord service")
    commands.add_parser("initialize-state", help="initialize private host state")
    commands.add_parser("check-paused", help="check the stopped canonical pause")
    commands.add_parser(
        "check-activation",
        help="check unfinished actions against this release while stopped",
    )
    commands.add_parser(
        "cutover-native", help="convert stopped legacy state for native activation"
    )
    commands.add_parser("dream", help="run one isolated dream while stopped")
    rebuild = commands.add_parser(
        "rebuild-memory", help="refold derived memory while stopped"
    )
    rebuild.add_argument("--node", metavar="START+COUNT")
    memory = commands.add_parser("memory", help="inspect or repair shared memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_commands.add_parser(
        "status", help="inspect capture, publication and tree progress"
    )
    capture = memory_commands.add_parser(
        "retry-capture", help="retry a repaired source without moving its boundary"
    )
    capture.add_argument(
        "source", metavar="SOURCE", help="conversation uuid or provider:native_id"
    )
    memory_commands.add_parser(
        "retry-compression", help="retry a corrected parked compression"
    )
    release = commands.add_parser(
        "release-parked",
        help="release explicitly named parked input after operator correction",
    )
    release.add_argument("message_ids", metavar="MESSAGE_ID", type=UUID, nargs="+")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        host = settings.codex_host_config
        if arguments.command == "serve":
            asyncio.run(serve(settings, host))
        elif arguments.command == "initialize-state":
            asyncio.run(initialize_state(settings, host))
        elif arguments.command == "check-paused":
            asyncio.run(check_paused(settings))
            print("canonical deployment pause confirmed")
        elif arguments.command == "cutover-native":
            count = asyncio.run(stopped_native_cutover(settings, host))
            print(f"native cutover completed: converted_actions={count}")
        elif arguments.command == "check-activation":
            try:
                verdicts = asyncio.run(check_activation(settings, host))
            except DeploymentAlreadyOwned:
                print("another jarvis process owns the deployment")
                return 1
            for action_id, status, tool_name, verdict in verdicts:
                print(f"action {action_id} {status} {tool_name} {verdict}")
            compatible = sum(verdict == "compatible" for *_, verdict in verdicts)
            in_flight = sum(verdict == "in_flight" for *_, verdict in verdicts)
            incompatible = len(verdicts) - compatible - in_flight
            print(
                f"activation check: compatible={compatible} "
                f"incompatible={incompatible} in_flight={in_flight}"
            )
            if compatible != len(verdicts):
                return 1
        elif arguments.command == "dream":
            result = asyncio.run(dream_once(settings, host))
            if result is None:
                print("dream did not complete; admitted progress is preserved")
            else:
                print(
                    "dream completed: "
                    f"notes={len(result.created_note_ids)} "
                    f"seed={result.seed_start}+{result.seed_end - result.seed_start}"
                )
        elif arguments.command == "rebuild-memory":
            asyncio.run(rebuild_memory(settings, host, arguments.node))
            print("memory rebuild completed")
        elif arguments.command == "memory":
            if arguments.memory_command == "status":
                print(json.dumps(asyncio.run(memory_status(settings)), sort_keys=True))
            else:
                source = (
                    arguments.source
                    if arguments.memory_command == "retry-capture"
                    else None
                )
                asyncio.run(retry_memory(settings, source))
                print(
                    "memory retry armed; "
                    "original boundaries and completed progress preserved"
                )
        elif arguments.command == "release-parked":
            message_ids = tuple(arguments.message_ids)
            if len(set(message_ids)) != len(message_ids):
                raise StartupDefect("release IDs must be unique")
            asyncio.run(release_parked(settings, message_ids))
            print(f"Released {len(message_ids)} parked message(s).")
        else:  # pragma: no cover
            raise AssertionError("unknown command")
    except (
        ConfigurationError,
        RuntimeError,
        OSError,
        ValueError,
        SQLAlchemyError,
    ) as exc:
        if isinstance(exc, MemoryError):
            LOGGER.error("Jarvis command failed: code=%s", exc.code)
        else:
            LOGGER.error("Jarvis command failed: type=%s", type(exc).__name__)
        return 1
    except KeyboardInterrupt:
        LOGGER.info("Jarvis stopped by operator signal")
        return 130
    return 0


__all__ = [
    "StartupDefect",
    "check_activation",
    "check_paused",
    "dream_once",
    "initialize_state",
    "main",
    "rebuild_memory",
    "release_parked",
    "serve",
    "stopped_native_cutover",
]

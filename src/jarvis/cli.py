"""Minimal Jarvis service and operator entry points."""

from __future__ import annotations

import argparse
import asyncio
import grp
import json
import logging
import os
import socket
import stat
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

import httpx
import uvicorn
from llm_agent_kernel import CancellationToken, CodexProvider, ProviderConfiguration
from llm_tools import FrozenToolPlan
from provider_runtime.agent_runtime import (
    AgentRuntime,
    AgentRuntimeDefect,
    AgentRuntimeError,
)
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import MemoryError, MemoryStore
from universal_memory.policy import (
    ARCHIVE_GENERATION,
    EMBEDDING_BATCH_SIZE,
    bounded_text,
)
from universal_memory.schema import source_conversation

from jarvis.actions import ActionPersistenceDefect, ActionStore, archived_worker_action
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.codex_config import CodexHostConfig
from jarvis.config import ConfigurationError
from jarvis.connectors import GoogleReadConnector
from jarvis.db import (
    ASSISTANT_MEMORY_READS,
    action,
    create_engine,
    home_notice,
    normalize_database_url,
)
from jarvis.definitions import (
    RoleDefinitions,
    build_compactor,
    build_definitions,
    build_dreamer,
)
from jarvis.discord import DiscordCreateMessageClient
from jarvis.embeddings import EmbeddingFailure, OpenAIEmbedder
from jarvis.events import EventStore
from jarvis.home_http import create_home_app
from jarvis.home_pages import DEFAULT_EXPORT, NOTES_ROOT
from jarvis.kernel import (
    build_agent_runtime,
    build_kernel_runtime,
    main_provider_configuration,
    resolve_role_providers,
)
from jarvis.memory_config import MEMORY_IDENTITIES, MemoryConfig
from jarvis.memory_rpc import MemoryRPC
from jarvis.memory_server import serve_memory
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import compose_memory_catalog
from jarvis.memory_workers import DreamerRunCompleted, DreamerWorker, MemoryWorker
from jarvis.messages import MessageStore
from jarvis.native_cutover import (
    cutover_native,
    require_native_data,
    require_native_files,
)
from jarvis.native_diagnostics import log_native_failure
from jarvis.native_runtime import (
    NativeRunner,
    recover_native_products,
)
from jarvis.ownership import (
    DEPLOYMENT_LOCK_KEY,
    MEMORY_LOCK_KEY,
    Database,
    DeploymentAlreadyOwned,
    deployment_ownership,
    maintenance_ownership,
)
from jarvis.proactivity import WorkWakeTimer
from jarvis.process_security import deny_same_identity_process_inspection
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.service import JarvisService
from jarvis.settings import (
    CutoverSettings,
    DatabaseSettings,
    IsolatedRoleSettings,
    MemoryJobSettings,
    MemoryServerSettings,
    MemoryStatusSettings,
    NativeStateSettings,
    PausedSettings,
    Settings,
    embedding_key_from_env,
)
from jarvis.state import PausedState
from jarvis.tool_composition import (
    ToolComposition,
    build_attachment_store,
    build_tool_composition,
    google_tokens,
)
from jarvis.tool_results import memory_result_size, memory_view_size
from jarvis.work import WorkStore
from jarvis.write_dispatch import (
    ActionRecovery,
    WriteToolDispatcher,
    gmail_send_basis_is_current,
    require_current_action_binding,
)
from jarvis.write_tools import GmailSendDraftInput

LOGGER = logging.getLogger(__name__)
# initialize-state bootstraps only a fresh database stopped at this revision.
BOOTSTRAP_SCHEMA_REVISION = "0015"
HOME_SOCKET_GROUP = "jarvis-home"


class StartupDefect(RuntimeError):
    """The configured private runtime layout is unsafe or incomplete."""


class _MemoryWriter(Database, Protocol):
    async def check_available(self) -> bool: ...


@asynccontextmanager
async def _memory_service(
    settings: Settings | MemoryJobSettings,
    config: MemoryConfig,
    database: _MemoryWriter,
    *,
    offline_key: SecretStr | None = None,
) -> AsyncIterator[MemoryService]:
    reads = create_engine(
        settings.database_url.get_secret_value(), memory_reads=ASSISTANT_MEMORY_READS
    )
    try:
        transport = (
            httpx.AsyncHTTPTransport(uds=str(settings.memory_socket_path), retries=0)
            if offline_key is None
            else None
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://memory",
            trust_env=False,
            follow_redirects=False,
            # One provider embedding (45s) plus bounded read-pool work.
            timeout=60.0,
        ) as http:
            yield MemoryService(
                library=MemoryStore(
                    reads, result_size=memory_result_size, view_size=memory_view_size
                ),
                database=database,
                owner_available=database.check_available
                if offline_key is None
                else None,
                embedder=OpenAIEmbedder(offline_key, http_client=http)
                if offline_key is not None
                else None,
                remote=MemoryRPC(http) if offline_key is None else None,
                admitted_lanes=config.admitted_lanes,
                nexus_admitted_owner=config.nexus_admitted_owner,
                owner_scope=settings.owner_scope,
                owner_archive_key=settings.owner_archive_key,
            )
    finally:
        await reads.dispose()


@asynccontextmanager
async def _isolated_provider(
    settings: MemoryJobSettings,
    host: CodexHostConfig,
    role: Literal["compactor", "dreamer"],
) -> AsyncIterator[tuple[ProviderConfiguration, CodexProvider]]:
    runtime = build_agent_runtime(
        provider_state_root=settings.runtime_state_directory,
        codex_endpoints=host.endpoints,
    )
    kernel = None
    try:
        providers = await resolve_role_providers(
            runtime, settings.codex_profile_key, role
        )
        kernel = build_kernel_runtime(
            runtime=runtime, shared_cwd_parent=Path(host.cognition_cwd_parent)
        )
        yield providers[role], kernel.provider
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


def _attachment_cache_layout(
    settings: IsolatedRoleSettings | CutoverSettings, host: CodexHostConfig
) -> None:
    path = settings.attachment_cache_directory
    try:
        metadata = path.stat()
        group_id = grp.getgrnam(host.client_group).gr_gid
    except (KeyError, OSError) as exc:
        raise StartupDefect("attachment cache is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o750
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != group_id
        or path == Path("/")
        or path.is_relative_to(settings.runtime_state_directory)
        or settings.runtime_state_directory.is_relative_to(path)
        or path.is_relative_to(Path(host.notes_repository))
        or Path(host.notes_repository).is_relative_to(path)
    ):
        raise StartupDefect(
            "attachment cache must be app-owned mode 0750 in the native client group, "
            "separate from private state and the notes checkout"
        )


def _validate_runtime_layout(
    settings: IsolatedRoleSettings | CutoverSettings, host: CodexHostConfig
) -> None:
    _private_directory(settings.runtime_state_directory, "runtime state directory")
    _shared_cognition_directory(Path(host.cognition_cwd_parent), host.client_group)
    _attachment_cache_layout(settings, host)
    try:
        host.verify_notes_repository()
    except ValueError as exc:
        raise StartupDefect(str(exc)) from exc


async def initialize_state(
    settings: NativeStateSettings, host: CodexHostConfig
) -> None:
    """Pause a fresh 0015 database once; initialize_paused refuses any message."""

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
            # This bootstrap check replaces the runtime head check: the stopped
            # cut initializes at 0015, then migrates 0016 and 0017 under this pause.
            async with database.connect() as connection:
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            if revision != BOOTSTRAP_SCHEMA_REVISION:
                raise StartupDefect(
                    "initialize-state requires a fresh database at schema "
                    + BOOTSTRAP_SCHEMA_REVISION
                )
            await MessageStore(database).initialize_paused(settings.owner_scope)
    finally:
        await engine.dispose()


async def recover_startup_actions(
    *,
    action_recovery: ActionRecovery,
    paused: PausedState,
) -> int:
    inactive = await paused.is_paused()
    return await action_recovery.recover(allow_queued_execution=not inactive)


class _HomeListener(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        # The application owns signals; uvicorn would capture and re-raise them.
        yield


def _bind_home_socket(path: Path, group: str) -> socket.socket:
    """Listen on a 0660 socket whose group comes from systemd's setgid directory."""
    try:
        directory = path.parent.stat()
        group_id = grp.getgrnam(group).gr_gid
    except (KeyError, OSError) as exc:
        raise StartupDefect("home socket directory is unavailable") from exc
    if (
        not stat.S_ISDIR(directory.st_mode)
        or not directory.st_mode & stat.S_ISGID
        or directory.st_mode & 0o007
        or directory.st_gid != group_id
    ):
        raise StartupDefect(
            f"home socket directory must be setgid group {group} without world access"
        )
    # Deployment ownership excludes a live peer; a socket left by a crash is stale.
    if path.is_socket():
        path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(path))
    except BaseException:
        listener.close()
        raise
    try:
        os.chmod(path, 0o660)
        if path.stat().st_gid != group_id:
            raise StartupDefect(f"home socket must inherit group {group}")
        listener.listen()
    except BaseException:
        listener.close()
        path.unlink(missing_ok=True)
        raise
    return listener


async def run_service(
    service: JarvisService,
    app: Callable[..., Awaitable[None]],
    socket_path: Path,
    shutdown: asyncio.Event,
    *,
    group: str = HOME_SOCKET_GROUP,
) -> None:
    """Serve the home after startup; stop ingress before draining the worker."""
    if shutdown.is_set():
        return
    listener_socket = _bind_home_socket(socket_path, group)
    server = _HomeListener(
        uvicorn.Config(
            app,
            lifespan="off",
            ws="none",
            log_config=None,
            access_log=False,
            proxy_headers=False,
            server_header=False,
            timeout_graceful_shutdown=30,
        )
    )
    worker = asyncio.create_task(service.run_worker(), name="jarvis-worker")
    serving = asyncio.create_task(
        server.serve(sockets=[listener_socket]), name="jarvis-home"
    )
    stopping = asyncio.create_task(shutdown.wait(), name="jarvis-shutdown-request")
    try:
        done, _ = await asyncio.wait(
            {worker, serving, stopping}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            task.result()
        if not shutdown.is_set():
            raise RuntimeError("home listener or worker stopped before shutdown")
    finally:
        server.should_exit = True
        results = list(await asyncio.gather(serving, return_exceptions=True))
        service.request_shutdown()
        stopping.cancel()
        await asyncio.gather(stopping, return_exceptions=True)
        results.extend(await asyncio.gather(worker, return_exceptions=True))
        listener_socket.close()
        socket_path.unlink(missing_ok=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result


async def _compose_main(
    *,
    owner: JarvisOwner,
    settings: Settings,
    host: CodexHostConfig,
    agent_runtime: AgentRuntime,
    actions: ActionStore,
    work: WorkStore,
    events: EventStore,
    event_admitted: Callable[[], Awaitable[bool]],
    memory: MemoryService,
    google_oauth_http: httpx.AsyncClient,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
) -> tuple[ToolComposition, RoleDefinitions, AgentController]:
    """Compose the release's tools and role plans from the live codex catalog."""

    providers = await resolve_role_providers(
        agent_runtime, settings.codex_profile_key, "main", "compactor", "dreamer"
    )
    agents = AgentController(
        cli_path=settings.agent_cli_path,
        state_directory=settings.agent_state_directory,
        actions=actions,
        source_conversation_id=settings.owner_scope,
    )
    composition = build_tool_composition(
        owner=owner,
        settings=settings,
        google_oauth_http=google_oauth_http,
        google_api_http=google_api_http,
        maps_http=maps_http,
        brave_http=brave_http,
        memory=memory,
        actions=actions,
        agents=agents,
        work=work,
        events=events,
        event_admitted=event_admitted,
    )
    definitions = build_definitions(
        catalog=composition.catalog,
        main_provider=main_provider_configuration(
            providers["main"], notes_repository=host.notes_repository
        ),
        compactor_provider=providers["compactor"],
        dreamer_provider=providers["dreamer"],
        owner_timezone=settings.owner_timezone,
    )
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
    """Own the deployment, recover, then serve the private home."""

    if Path(host.notes_repository) != NOTES_ROOT:
        raise StartupDefect(f"the web home requires the notes checkout at {NOTES_ROOT}")
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
                owner = JarvisOwner(database, settings.owner_scope)
                await require_native_data(database, conversation_id=owner.scope_id)
                # A scope without canonical control would read as unpaused.
                if await store.current_control(owner.scope_id) is None:
                    raise StartupDefect("serve requires initialized canonical control")
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
                    memory = await clients.enter_async_context(
                        _memory_service(settings, config, database)
                    )
                    actions = ActionStore(database)
                    work = WorkStore(database, settings.owner_scope)
                    await work.recompute_calendar_wakes()
                    events = EventStore(database, settings.owner_scope)

                    async def event_admitted() -> bool:
                        return await service.events_admitted()

                    agent_runtime = build_agent_runtime(
                        provider_state_root=settings.runtime_state_directory,
                        codex_endpoints=host.endpoints,
                    )
                    composition, definitions, agents = await _compose_main(
                        owner=owner,
                        settings=settings,
                        host=host,
                        agent_runtime=agent_runtime,
                        actions=actions,
                        work=work,
                        events=events,
                        event_admitted=event_admitted,
                        memory=memory,
                        google_oauth_http=google_oauth_http,
                        google_api_http=google_api_http,
                        maps_http=maps_http,
                        brave_http=brave_http,
                    )
                    clients.push_async_callback(composition.google_read.aclose)
                    await composition.attachments.reset_cache()
                    kernel_runtime = build_kernel_runtime(
                        runtime=agent_runtime,
                        shared_cwd_parent=Path(host.cognition_cwd_parent),
                    )

                    compactor = MemoryWorker(
                        definitions=definitions.compactor,
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
                        dispatcher_factory=lambda checkpoint, journal: (
                            WriteToolDispatcher(
                                checkpoint=checkpoint,
                                dispatch_lane=dispatch_lane,
                                journal=journal,
                                actions=actions,
                                google_write=composition.google_write,
                                work=work,
                                events=events,
                                attachments=composition.attachments,
                                agents=agents,
                                read=ReadToolDispatcher(
                                    host_secrets=settings.host_secrets,
                                    recorder=PostgresReadRecorder(
                                        database,
                                        web_source_operation=(
                                            composition.web_source_operation
                                        ),
                                    ),
                                    memory=memory,
                                    cutoff=checkpoint.memory_cutoff,
                                ),
                                source_conversation_id=settings.owner_scope,
                                verified_owner_only_calendar_ids=(
                                    settings.verified_owner_only_calendar_ids
                                ),
                                host_secrets=settings.host_secrets,
                            )
                        ),
                        memory=memory,
                    )
                    delivery = DiscordCreateMessageClient(
                        settings.discord, discord_http
                    )
                    action_recovery = ActionRecovery(
                        actions=actions,
                        google_write=composition.google_write,
                        work=work,
                        events=events,
                        attachments=composition.attachments,
                        plan=definitions.plans["main"],
                        source_conversation_id=settings.owner_scope,
                        wait_changed=agents.notify_wait_changed,
                    )

                    work_timer = WorkWakeTimer(
                        work=work, paused=paused, on_event=lambda: runner.notify_work()
                    )
                    work.notify_changed = work_timer.notify_changed
                    service = JarvisService(
                        settings=settings,
                        database=database,
                        paused=paused,
                        delivery=delivery,
                        runner=runner,
                        background=compactor,
                        memory=memory,
                        dreamer=dreamer,
                        action_plan=definitions.plans["main"],
                        action_recovery=action_recovery,
                        agent_waits=agents,
                        dispatch_lane=dispatch_lane,
                        work_timer=work_timer,
                        event_poller=composition.event_poller,
                        attachments=composition.attachments,
                    )
                    events.publication_allowed = service.events_publication_allowed
                    events.notify_input = service.request_work
                    if shutdown.is_set():
                        return
                    recovered_actions = await recover_startup_actions(
                        action_recovery=action_recovery,
                        paused=paused,
                    )
                    if recovered_actions:
                        LOGGER.warning(
                            "Recovered interrupted actions: count=%d",
                            recovered_actions,
                        )

                    await service.startup()
                    if shutdown.is_set():
                        return
                    app = create_home_app(
                        database=database,
                        scope=settings.owner_scope,
                        owner_timezone=settings.owner_timezone,
                        work=work,
                        attachments=composition.attachments,
                        submit=service.submit,
                        spool=settings.runtime_state_directory / "uploads",
                        pages=DEFAULT_EXPORT,
                    )
                    await run_service(service, app, settings.home_socket_path, shutdown)
            finally:
                if kernel_runtime is not None:
                    await kernel_runtime.close()
                elif agent_runtime is not None:
                    await agent_runtime.close()
    finally:
        await engine.dispose()


async def reconcile_attachment(
    settings: Settings, attachment_id: UUID, *, after_manual_cleanup: bool
) -> dict[str, object]:
    """Observe a stopped original; manual cleanup never proves its old action."""
    _attachment_cache_layout(settings, settings.codex_host_config)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with (
            deployment_ownership(engine) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            store = build_attachment_store(
                settings=settings,
                database=database,
                google=GoogleReadConnector(
                    client=http, tokens=google_tokens(settings, http)
                ),
            )
            return await store.reconcile(
                attachment_id, after_manual_cleanup=after_manual_cleanup
            )
    finally:
        await engine.dispose()


async def release_parked(
    settings: DatabaseSettings, message_ids: tuple[UUID, ...]
) -> None:
    """Clear only the named parked markers while holding deployment ownership."""

    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            await MessageStore(database).clear_parked(message_ids=message_ids)
    finally:
        await engine.dispose()


async def stopped_native_cutover(
    settings: CutoverSettings, host: CodexHostConfig
) -> int:
    """Write the private stopped inventory without provider or connector work."""
    _validate_runtime_layout(settings, host)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            return await cutover_native(
                database,
                directory=settings.runtime_state_directory,
                conversation_id=settings.owner_scope,
            )
    finally:
        await engine.dispose()


async def _require_paused(database: Database, settings: PausedSettings) -> None:
    require_native_files(settings.runtime_state_directory)
    scope = settings.owner_scope
    await require_native_data(database, conversation_id=scope)
    if not await MessageStore(database).paused(scope):
        raise StartupDefect("activation requires a canonical deployment pause")


async def check_paused(settings: PausedSettings) -> None:
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
            async with database.connect() as connection:
                pending = await connection.scalar(
                    select(home_notice.c.id)
                    .where(
                        home_notice.c.discord_message_id.is_(None),
                        home_notice.c.kind != "reply",
                    )
                    .limit(1)
                )
                if pending is not None:
                    raise StartupDefect(
                        "predecessor must drain pending question and approval notices"
                    )
                old_approval = await connection.scalar(
                    select(action.c.id)
                    .join(home_notice, home_notice.c.action_id == action.c.id)
                    .where(
                        action.c.status == "awaiting_approval",
                        home_notice.c.kind == "approval",
                    )
                    .limit(1)
                )
            if old_approval is not None:
                raise StartupDefect("the predecessor must settle its open approvals")
            require_native_files(settings.runtime_state_directory)
            scope = settings.owner_scope
            await require_native_data(database, conversation_id=scope)
            if await MessageStore(database).current_control(scope) is None:
                raise StartupDefect("activation requires initialized canonical control")
            actions = ActionStore(database)
            agent_runtime = build_agent_runtime(
                provider_state_root=settings.runtime_state_directory,
                codex_endpoints=host.endpoints,
            )
            try:
                async with _memory_service(settings, config, database) as memory:

                    async def event_admitted() -> bool:
                        return False

                    # No connector dispatches during the activation check.
                    _, definitions, _ = await _compose_main(
                        owner=JarvisOwner(database, scope),
                        settings=settings,
                        host=host,
                        agent_runtime=agent_runtime,
                        actions=actions,
                        work=WorkStore(database, scope),
                        events=EventStore(database, scope),
                        event_admitted=event_admitted,
                        memory=memory,
                        google_oauth_http=http,
                        google_api_http=http,
                        maps_http=http,
                        brave_http=http,
                    )
                    plan = definitions.plans["main"]
                    return await _action_activation_verdicts(
                        actions,
                        plan,
                        source_conversation_id=scope,
                    )
            finally:
                await agent_runtime.close()
    finally:
        await engine.dispose()


async def _action_activation_verdicts(
    actions: ActionStore,
    plan: FrozenToolPlan,
    *,
    source_conversation_id: str,
) -> tuple[tuple[UUID, str, str, str], ...]:
    """assess stored execution authority without opening providers or connectors."""
    # End the locked read before loading any action.
    async with actions.engine.connect() as connection:
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
    retired_reports = await actions.unreported_terminal(
        source_conversation_id=source_conversation_id,
        limit=100,
        retired_only=True,
    )
    verdicts = [
        (
            item.id,
            item.status,
            str(item.tool_name),
            "incompatible retired_pending_events",
        )
        for item in retired_reports
    ]
    reported = {item.id for item in retired_reports}
    for action_id, status, tool_name in unfinished:
        if action_id in reported:
            continue
        if status == "uncertain":
            try:
                stored = await actions.get(action_id)
            except ActionPersistenceDefect:
                verdict = "incompatible does_not_load"
            else:
                if stored is not None and archived_worker_action(stored):
                    verdict = "compatible"
                else:
                    verdict = "in_flight"
        elif status == "executing":
            verdict = "in_flight"
        else:
            verdict = await _pending_action_verdict(actions, plan, action_id)
        verdicts.append((action_id, status, tool_name, verdict))
    return tuple(verdicts)


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
    if isinstance(value, GmailSendDraftInput):
        try:
            current = await gmail_send_basis_is_current(actions, value)
        except ValueError:
            return "incompatible gmail_basis"
        if not current:
            return "incompatible gmail_basis"
    return "compatible"


async def dream_once(
    settings: MemoryJobSettings, host: CodexHostConfig
) -> DreamerRunCompleted | None:
    """One bounded stopped manual dream, without changing its nightly marker."""
    _validate_runtime_layout(settings, host)
    config = MemoryConfig.load(settings.memory_config_path)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with (
            deployment_ownership(
                engine, memory_admitted=config.jarvis_admitted
            ) as database,
            _memory_service(settings, config, database) as memory,
            _isolated_provider(settings, host, "dreamer") as (provider, kernel),
        ):
            definition, plan = build_dreamer(
                catalog=compose_memory_catalog(memory),
                provider=provider,
                owner_timezone=settings.owner_timezone,
            )
            worker = DreamerWorker(
                definition=definition,
                plan=plan,
                owner=JarvisOwner(database, settings.owner_scope),
                provider=kernel,
                memory=memory,
                owner_timezone=settings.owner_timezone,
                nightly_time=settings.memory_nightly_time,
            )
            return await worker.run_at(
                as_of=datetime.now(UTC), cancellation=CancellationToken()
            )
    finally:
        await engine.dispose()


async def rebuild_memory(
    settings: MemoryJobSettings,
    host: CodexHostConfig,
    node: str | None = None,
    generation: int = 1,
) -> None:
    """Refold admitted originals while stopped; preserve capture and dream progress."""
    _validate_runtime_layout(settings, host)
    config = MemoryConfig.load(settings.memory_config_path)
    start = count = None
    if node is not None:
        if generation != ARCHIVE_GENERATION:
            raise ValueError(
                f"select a current node with --generation {ARCHIVE_GENERATION}"
            )
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
        async with (
            maintenance_ownership(
                engine, memory_admitted=config.jarvis_admitted
            ) as database,
            _memory_service(
                memory_settings,
                config,
                database,
                offline_key=embedding_key_from_env() if node is None else None,
            ) as memory,
            _isolated_provider(memory_settings, host, "compactor") as (
                provider,
                kernel,
            ),
        ):
            definitions, plan = build_compactor(
                catalog=compose_memory_catalog(memory),
                provider=provider,
                owner_timezone=settings.owner_timezone,
            )
            worker = MemoryWorker(
                definitions=definitions,
                plan=plan,
                owner=JarvisOwner(database, settings.owner_scope),
                provider=kernel,
                memory=memory,
            )
            async with database.begin() as connection:
                await memory.library.rebuild(
                    connection, start, count, generation=generation
                )
            await worker.ensure_ready(
                await memory.library.cutoff(), CancellationToken()
            )
            if node is None:
                while rows := await memory.library.embedding_candidates(
                    EMBEDDING_BATCH_SIZE
                ):
                    try:
                        await memory.index_batch(rows)
                    except EmbeddingFailure as error:
                        raise RuntimeError(
                            f"memory rebuild embedding failed ({error.reason}); "
                            "derived work remains pending"
                        ) from None
    finally:
        await engine.dispose()


async def memory_status(settings: MemoryStatusSettings) -> dict[str, object]:
    config = MemoryConfig.load(settings.memory_config_path)
    engine = create_engine(
        settings.database_url.get_secret_value(), memory_reads=ASSISTANT_MEMORY_READS
    )
    try:
        memory = MemoryService(
            library=MemoryStore(
                engine,
                result_size=memory_result_size,
                view_size=memory_view_size,
            ),
            database=engine,
            admitted_lanes=config.admitted_lanes,
            nexus_admitted_owner=config.nexus_admitted_owner,
            owner_scope=settings.owner_scope,
            owner_archive_key=settings.owner_archive_key,
        )
        declared = {(lane.machine, lane.account): lane for lane in config.lanes}
        registration = None
        if config.nexus_client is not None:
            async with engine.connect() as connection:
                state = await memory.library.nexus_capture_state(
                    connection, config.nexus_client.owner_user_id
                )
            if state.registration is not None:
                registration = state.registration.model_dump(mode="json")
        return {
            "memory": await memory.library.status(),
            "publication_backlog": len(await memory.pending_publication()),
            "declaration_sha256": config.declaration_sha256,
            "nexus_client": {
                "declared": config.nexus_client is not None,
                "admit": config.nexus_admitted_owner is not None,
                "connect": config.nexus_client is not None
                and config.nexus_client.connect,
                "capture": config.nexus_client is not None
                and config.nexus_client.capture,
                "registration": registration,
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


async def retry_memory(settings: DatabaseSettings, conversation: str | None) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        if conversation is None:
            async with (
                deployment_ownership(engine) as database,
                database.begin() as connection,
            ):
                await MemoryStore.retry_compression(connection)
            return
        try:
            selector = source_conversation.c.id == UUID(conversation)
        except ValueError:
            provider, separator, native_id = conversation.partition(":")
            if not separator or provider not in {"codex", "claude", "jarvis", "nexus"}:
                raise MemoryError("invalid_input") from None
            bounded_text(native_id, 256)
            selector = (source_conversation.c.provider == provider) & (
                source_conversation.c.native_id == native_id
            )
        query = (
            select(source_conversation.c.id, source_conversation.c.provider)
            .where(selector)
            .limit(2)
        )
        async with engine.connect() as connection:
            matches = (await connection.execute(query)).all()
        if not matches:
            raise MemoryError("not_found")
        if len(matches) > 1:
            raise MemoryError("ambiguous_source_use_uuid")
        identifier, provider = matches[0]
        key = DEPLOYMENT_LOCK_KEY if provider == "jarvis" else MEMORY_LOCK_KEY
        async with (
            deployment_ownership(engine, lock_key=key) as database,
            database.begin() as connection,
        ):
            expected_role = (
                "jarvis_runtime" if provider == "jarvis" else "jarvis_memory"
            )
            if await connection.scalar(text("SELECT current_user")) != expected_role:
                raise StartupDefect("capture retry requires the source writer role")
            if (await connection.execute(query)).all() != matches:
                raise MemoryError("source_conflict")
            await MemoryStore.retry_capture(connection, identifier)
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the Jarvis private home service")
    commands.add_parser("serve-memory", help="serve shared memory and capture")
    commands.add_parser("initialize-state", help="initialize private host state")
    commands.add_parser("check-paused", help="check the stopped canonical pause")
    commands.add_parser(
        "check-activation",
        help="check unfinished actions against this release while stopped",
    )
    commands.add_parser(
        "cutover-native",
        help="inventory stopped obligations before common-main cutover",
    )
    attachment = commands.add_parser(
        "attachment-reconcile", help="observe one stopped original and its cache"
    )
    attachment.add_argument("id", type=UUID)
    attachment.add_argument("--after-manual-cleanup", action="store_true")
    commands.add_parser("dream", help="run one isolated dream while stopped")
    rebuild = commands.add_parser(
        "rebuild-memory", help="refold derived memory while stopped"
    )
    rebuild.add_argument("--node", metavar="START+COUNT")
    rebuild.add_argument(
        "--generation",
        type=int,
        default=1,
        help="archive generation shown with the selected node",
    )
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "serve-memory":
            asyncio.run(
                serve_memory(MemoryServerSettings.from_env(), embedding_key_from_env())
            )
            return 0
        if arguments.command == "memory":
            if arguments.memory_command == "status":
                print(
                    json.dumps(
                        asyncio.run(memory_status(MemoryStatusSettings.from_env())),
                        sort_keys=True,
                    )
                )
            else:
                source = (
                    arguments.source
                    if arguments.memory_command == "retry-capture"
                    else None
                )
                asyncio.run(retry_memory(DatabaseSettings.from_env(), source))
                print(
                    "memory retry armed; "
                    "original boundaries and completed progress preserved"
                )
            return 0
        if arguments.command == "release-parked":
            message_ids = tuple(arguments.message_ids)
            if len(set(message_ids)) != len(message_ids):
                raise StartupDefect("release IDs must be unique")
            asyncio.run(release_parked(DatabaseSettings.from_env(), message_ids))
            print(f"Released {len(message_ids)} parked message(s).")
            return 0
        if arguments.command == "check-paused":
            asyncio.run(check_paused(PausedSettings.from_env()))
            print("canonical deployment pause confirmed")
            return 0
        if arguments.command == "initialize-state":
            initial = NativeStateSettings.from_env()
            asyncio.run(
                initialize_state(
                    initial, CodexHostConfig.load(initial.codex_host_config_path)
                )
            )
            return 0
        if arguments.command == "cutover-native":
            cutover = CutoverSettings.from_env()
            count = asyncio.run(
                stopped_native_cutover(
                    cutover, CodexHostConfig.load(cutover.codex_host_config_path)
                )
            )
            print(
                f"private cutover inventory retained: records={count}; "
                "activation unchanged"
            )
            return 0
        if arguments.command == "dream":
            job = MemoryJobSettings.from_env()
            result = asyncio.run(dream_once(job, job.codex_host_config))
            if result is None:
                print("dream did not complete; admitted progress is preserved")
            else:
                print(
                    "dream completed: "
                    f"notes={len(result.created_note_ids)} "
                    f"seed={result.seed_start}+{result.seed_end - result.seed_start}"
                )
            return 0
        if arguments.command == "rebuild-memory":
            job = MemoryJobSettings.from_env()
            asyncio.run(
                rebuild_memory(
                    job, job.codex_host_config, arguments.node, arguments.generation
                )
            )
            print("memory rebuild completed")
            return 0
        settings = Settings.from_env()
        if arguments.command == "serve":
            asyncio.run(serve(settings, settings.codex_host_config))
        elif arguments.command == "check-activation":
            try:
                verdicts = asyncio.run(
                    check_activation(
                        settings,
                        settings.codex_host_config,
                    )
                )
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
        elif arguments.command == "attachment-reconcile":
            result = asyncio.run(
                reconcile_attachment(
                    settings,
                    arguments.id,
                    after_manual_cleanup=arguments.after_manual_cleanup,
                )
            )
            print(json.dumps(result, sort_keys=True))
        else:  # pragma: no cover
            raise AssertionError("unknown command")
    except (AgentRuntimeError, AgentRuntimeDefect) as exc:
        log_native_failure(LOGGER, exc, attempt_id=None, boundary="command")
        return 1
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

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
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self, cast
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from llm_agent_kernel import CancellationToken, CodexProvider, ProviderConfiguration
from llm_tools import FrozenToolPlan
from provider_runtime.agent_runtime import (
    AgentRuntime,
    AgentRuntimeDefect,
    AgentRuntimeError,
)
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy import RowMapping, and_, or_, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import MemoryError, MemoryStore
from universal_memory.policy import (
    ARCHIVE_GENERATION,
    EMBEDDING_BATCH_SIZE,
    bounded_text,
)
from universal_memory.schema import source_conversation

from jarvis._atomic_json import read_private_json
from jarvis.actions import (
    ActionPersistenceDefect,
    ActionStore,
    StoredAction,
    archived_worker_action,
)
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.codex_config import NEON_CONTROL_SOCKET, CodexHostConfig
from jarvis.config import ConfigurationError
from jarvis.connectors import GoogleTokenManager
from jarvis.db import (
    ASSISTANT_MEMORY_READS,
    action,
    create_engine,
    home_notice,
    message,
    normalize_database_url,
)
from jarvis.definitions import (
    RoleDefinitions,
    build_compactor,
    build_definitions,
    build_dreamer,
)
from jarvis.embeddings import EmbeddingFailure, OpenAIEmbedder
from jarvis.events import EventStore
from jarvis.fcm import FcmSender
from jarvis.gmail_cut import (
    CUT_RECEIPT,
    historical_mail,
    verified_cut_ids,
)
from jarvis.home_http import create_home_app
from jarvis.home_notices import deliver_workspace_match
from jarvis.home_pages import DEFAULT_EXPORT, NOTES_ROOT
from jarvis.kernel import (
    RouteSelector,
    build_agent_runtime,
    build_kernel_runtime,
    main_provider_configuration,
    resolve_neon_provider,
    resolve_paid_provider,
    resolve_role_providers,
)
from jarvis.memory_config import MEMORY_IDENTITIES, MemoryConfig
from jarvis.memory_rpc import MemoryRPC
from jarvis.memory_server import serve_memory
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import compose_memory_catalog
from jarvis.memory_workers import DreamerRunCompleted, DreamerWorker, MemoryWorker
from jarvis.messages import MessageStore, ParkedInput
from jarvis.native_cutover import (
    MaintenanceWork,
    NativeActivationDefect,
    OwnerControl,
    cutover_native,
    maintenance_work,
    require_native_data,
    require_native_files,
)
from jarvis.native_diagnostics import log_native_failure
from jarvis.native_runtime import (
    NativeRunner,
    neon_paid_ready,
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
from jarvis.phone import PHONE_DIRECTORY, PhoneSlot
from jarvis.proactivity import WorkWakeTimer
from jarvis.process_security import deny_same_identity_process_inspection
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.recovery_catchup import (
    CatchupInventory,
    queue_catchup,
    resume_catchup_quota,
)
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
from jarvis.workspace_enrollment import enroll_workspace
from jarvis.workspace_host import WorkspaceHost, current_workspace_read
from jarvis.workspace_mcp import WorkspaceError
from jarvis.workspace_write_models import FrozenCompose
from jarvis.write_dispatch import (
    RECOVERABLE_ACTION_IDS,
    ActionRecovery,
    WriteToolDispatcher,
    require_current_action_binding,
)

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
) -> AsyncIterator[tuple[ProviderConfiguration, CodexProvider, RouteSelector]]:
    runtime = build_agent_runtime(
        provider_state_root=settings.runtime_state_directory,
        codex_endpoints={"personal": host.personal.socket},
    )
    kernel = None
    try:
        providers = await resolve_role_providers(runtime, host.personal.key, role)
        kernel = build_kernel_runtime(
            runtime=runtime, shared_cwd_parent=Path(host.cognition_cwd_parent)
        )
        yield providers[role], kernel.provider, RouteSelector(runtime, host)
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
    tokens: GoogleTokenManager,
    google_api_http: httpx.AsyncClient,
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    qualify_neon: bool = False,
) -> tuple[ToolComposition, RoleDefinitions, AgentController]:
    """Compose the release's tools and role plans from the live codex catalog."""

    providers = await resolve_role_providers(
        agent_runtime, host.personal.key, "main", "compactor", "dreamer"
    )
    if qualify_neon and host.google_neon.socket.is_socket():
        await resolve_neon_provider(agent_runtime)
    agents = AgentController(
        cli_path=settings.agent_cli_path,
        state_directory=settings.agent_state_directory,
        actions=actions,
        source_conversation_id=settings.owner_scope,
    )
    composition = build_tool_composition(
        owner=owner,
        settings=settings,
        tokens=tokens,
        workspace_access=current_workspace_read,
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
                    fcm_http = await clients.enter_async_context(
                        httpx.AsyncClient(trust_env=False, follow_redirects=False)
                    )
                    memory = await clients.enter_async_context(
                        _memory_service(settings, config, database)
                    )
                    tokens = google_tokens(settings, google_oauth_http)
                    workspace = WorkspaceHost(
                        owner,
                        owner_zone=ZoneInfo(settings.owner_timezone),
                        enrollment=tokens.enrollment,
                    )
                    await recover_native_products(
                        owner, workspace=workspace, settle_losses=False
                    )
                    actions = ActionStore(database)
                    work = WorkStore(
                        database,
                        settings.owner_scope,
                        owner_timezone=settings.owner_timezone,
                        workspace_grant_id=lambda: (
                            enrollment.grant_id
                            if (enrollment := tokens.enrollment())
                            else None
                        ),
                    )
                    await work.recompute_calendar_wakes()
                    events = EventStore(database, settings.owner_scope)

                    async def event_admitted() -> bool:
                        return await service.events_admitted()

                    agent_runtime = build_agent_runtime(
                        provider_state_root=settings.runtime_state_directory,
                        codex_endpoints=host.endpoints,
                        neon_origin=host.google_neon.adapter_origin,
                        antigravity_endpoint=host.agy_neon.socket,
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
                        tokens=tokens,
                        google_api_http=google_api_http,
                        maps_http=maps_http,
                        brave_http=brave_http,
                    )
                    clients.push_async_callback(composition.workspace_approvals.close)
                    _require_mail_cut(
                        await historical_mail(actions),
                        settings.runtime_state_directory / CUT_RECEIPT,
                    )
                    await composition.attachments.reset_cache()
                    await composition.mail_files.sweep(
                        await actions.active_mail_stages()
                    )
                    kernel_runtime = build_kernel_runtime(
                        runtime=agent_runtime,
                        shared_cwd_parent=Path(host.cognition_cwd_parent),
                    )
                    from provider_runtime.agent_runtime.neon_control import NeonControl

                    neon_control = NeonControl(NEON_CONTROL_SOCKET)

                    routes = RouteSelector(
                        agent_runtime,
                        host,
                        paid_ready=lambda: neon_paid_ready(owner, neon_control),
                        paid_provider=lambda route: resolve_paid_provider(
                            agent_runtime, route
                        ),
                    )

                    compactor = MemoryWorker(
                        definitions=definitions.compactor,
                        plan=definitions.plans["compactor"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        memory=memory,
                        routes=routes,
                    )
                    dreamer = DreamerWorker(
                        definition=definitions.dreamer,
                        plan=definitions.plans["dreamer"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        memory=memory,
                        routes=routes,
                        owner_timezone=settings.owner_timezone,
                        nightly_time=settings.memory_nightly_time,
                    )
                    delivery = FcmSender(fcm_http, settings.fcm_project)
                    phone = PhoneSlot(
                        PHONE_DIRECTORY / "slot.json",
                        lambda: service.request_delivery(),
                    )
                    action_recovery = ActionRecovery(
                        actions=actions,
                        work=work,
                        events=events,
                        attachments=composition.attachments,
                        mail_files=composition.mail_files,
                        plan=definitions.plans["main"],
                        source_conversation_id=settings.owner_scope,
                        delegation_changed=agents.delegations.notify_changed,
                    )

                    async def recover_original(
                        action_id: UUID, *, allow_queued_execution: bool
                    ) -> None:
                        async with dispatch_lane:
                            await action_recovery.recover_action(
                                action_id,
                                allow_queued_execution=allow_queued_execution,
                            )

                    runner = NativeRunner(
                        settings=settings,
                        store=store,
                        opening_reads=engine,
                        owner=owner,
                        kernel_runtime=kernel_runtime,
                        route_selector=routes,
                        recover_action=recover_original,
                        neon_control=neon_control,
                        definitions=definitions,
                        actions=actions,
                        dispatcher_factory=lambda checkpoint, journal: (
                            WriteToolDispatcher(
                                checkpoint=checkpoint,
                                dispatch_lane=dispatch_lane,
                                journal=journal,
                                actions=actions,
                                workspace_writes=composition.workspace_writes,
                                workspace_grant=tokens.enrollment,
                                work=work,
                                events=events,
                                attachments=composition.attachments,
                                mail_files=composition.mail_files,
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
                                    workspace=workspace,
                                ),
                                source_conversation_id=settings.owner_scope,
                                host_secrets=settings.host_secrets,
                            )
                        ),
                        memory=memory,
                        workspace=workspace,
                        notify_workspace_match=partial(
                            deliver_workspace_match, delivery, phone
                        ),
                    )
                    work_timer = WorkWakeTimer(
                        work=work, paused=paused, on_event=lambda: runner.notify_work()
                    )
                    work.notify_changed = work_timer.notify_changed
                    service = JarvisService(
                        settings=settings,
                        database=database,
                        workspace=workspace,
                        paused=paused,
                        delivery=delivery,
                        phone=phone,
                        runner=runner,
                        background=compactor,
                        memory=memory,
                        dreamer=dreamer,
                        action_plan=definitions.plans["main"],
                        action_recovery=action_recovery,
                        delegations=agents.delegations,
                        dispatch_lane=dispatch_lane,
                        work_timer=work_timer,
                        event_poller=composition.event_poller,
                        attachments=composition.attachments,
                    )
                    events.publication_allowed = service.events_publication_allowed
                    events.notify_input = service.request_work
                    if shutdown.is_set():
                        return
                    await actions.require_worker_cutover_drained()
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
                        phone=phone,
                        workspace_approvals=composition.workspace_approvals,
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
        async with deployment_ownership(engine) as database:
            store = build_attachment_store(
                settings=settings,
                database=database,
                google=None,
            )
            return await store.reconcile(
                attachment_id, after_manual_cleanup=after_manual_cleanup
            )
    finally:
        await engine.dispose()


async def workspace_operator(settings: Settings, arguments: argparse.Namespace) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with (
            deployment_ownership(engine) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            await require_native_data(database, conversation_id=settings.owner_scope)
            if arguments.command == "workspace-confirm-removed":
                await EventStore(database, settings.owner_scope).confirm_removed_ack(
                    arguments.account,
                    grant_id=arguments.grant_id,
                    label_id=arguments.label_id,
                    message_id=arguments.message,
                )
                print("recorded the verified absence of the named pending label.")
                return
            tokens = google_tokens(settings, http)
            if arguments.command == "workspace-enroll":
                enrollment = await enroll_workspace(
                    tokens,
                    arguments.client,
                    expected_email=arguments.email,
                    pending_label_id=arguments.label,
                    confirm=lambda text: input(f"{text}\ntype yes: ") == "yes",
                    show_url=print,
                )
                print(f"enrolled {enrollment.account} in {enrollment.project_id}.")
                return
            enrollment = tokens.enrollment()
            if enrollment is None:
                raise WorkspaceError("grant_unavailable")
            if arguments.command == "resume-recovery-quota-wait":
                inventory = CatchupInventory.model_validate_json(
                    arguments.inventory.read_bytes()
                )
                print(
                    await resume_catchup_quota(
                        database, settings.owner_scope, inventory, enrollment
                    )
                )
                return
            if arguments.command == "workspace-disconnect":
                await tokens.disconnect(enrollment.grant_id)
                print("workspace access disabled. revoke this app in google too.")
                return
            if arguments.command == "workspace-restore-gap":
                recorded = await EventStore(
                    database, settings.owner_scope
                ).record_restored_interval(
                    enrollment.account,
                    cut_at=arguments.cut,
                    restored_at=arguments.restored,
                )
                print(
                    "arrival gap recorded."
                    if recorded
                    else "arrival gap already recorded."
                )
                return
            if arguments.command == "workspace-enroll-arrivals":
                receipt = read_private_json(arguments.handoff)
                if (
                    receipt is None
                    or receipt.get("account") != enrollment.account
                    or receipt.get("grant_id") != str(enrollment.grant_id)
                    or receipt.get("label_id") != enrollment.pending_label_id
                    or enrollment.pending_label_id is None
                    or receipt.get("verified_handoff") is not True
                    or "expected_progress" not in receipt
                ):
                    raise ValueError("the receipt does not match this enrollment")
                prior = receipt["expected_progress"]
                if prior is not None and not isinstance(prior, dict):
                    raise ValueError("the inventoried cursor is invalid")
                await EventStore(database, settings.owner_scope).enroll(
                    enrollment.account,
                    enrollment.grant_id,
                    enrollment.pending_label_id,
                    expected_progress=cast(dict[str, object] | None, prior),
                )
                print("the event cursor now names the verified pending label.")
                return
            raise ValueError("unknown workspace maintenance command")
    finally:
        await engine.dispose()


def _require_mail_cut(history: Sequence[RowMapping], receipt: Path) -> frozenset[UUID]:
    cleared = verified_cut_ids(history, receipt)
    if cleared is None:
        raise StartupDefect(
            "historical Gmail sends require a complete stopped cut audit"
        )
    return cleared


async def list_parked(settings: PausedSettings) -> str:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        inputs = await MessageStore(engine).list_parked(settings.owner_scope)
    finally:
        await engine.dispose()

    if not inputs:
        return "no parked requests"

    groups: dict[tuple[datetime, UUID | None, UUID | None], list[ParkedInput]] = {}
    for item in inputs:
        # Uncorroborated and inspection-only rows stand alone.
        singleton = None if item.attempt_id and item.releasable else item.id
        groups.setdefault((item.parked_at, item.attempt_id, singleton), []).append(item)

    blocks: list[str] = []
    for (parked_at, attempt_id, _), members in groups.items():
        if attempt_id is not None:
            provenance = f"attempt {attempt_id}"
        elif (claim := members[0].claimed_attempt_id) is not None:
            provenance = f"claims attempt {claim} (unverified)"
        else:
            provenance = "attempt provenance unverified"
        lines = [f"{parked_at.isoformat()} · {provenance}"]
        for item in members:
            reason = (
                json.dumps(item.reason, ensure_ascii=False)
                if item.reason is not None
                else "reason unavailable"
            )
            lines.append(f"  {item.id} {item.role}/{item.source} · {reason}")
        if members[0].releasable:
            identifiers = " ".join(str(item.id) for item in members)
            lines.append(f"  jarvis release-parked {identifiers}")
        else:
            lines.append("  inspection only · release requires a live parked request")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


async def release_parked(
    settings: PausedSettings, message_ids: tuple[UUID, ...]
) -> None:
    """Clear only the named parked markers while holding deployment ownership."""

    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            await MessageStore(database).clear_parked(
                source_conversation_id=settings.owner_scope, message_ids=message_ids
            )
    finally:
        await engine.dispose()


async def queue_recovery_catchup(settings: PausedSettings, path: Path) -> UUID:
    inventory = CatchupInventory.model_validate_json(path.read_bytes())
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            return await queue_catchup(database, settings.owner_scope, inventory)
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


type AuthorityArea = Literal[
    "gmail",
    "calendar",
    "attachments",
    "worker",
    "events",
    "owner",
    "database",
    "native",
    "memory",
    "notice",
]
type AuthorityIdentity = Annotated[str, Field(min_length=1, max_length=1024)]


class MaintenanceAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    authority_changes: frozenset[AuthorityArea]
    source_scope: AuthorityIdentity | None = None
    gmail_source_account: AuthorityIdentity | None = None
    gmail_candidate_account: AuthorityIdentity | None = None

    @model_validator(mode="after")
    def require_paired_gmail_evidence(self) -> Self:
        if (self.gmail_source_account is None) != (
            self.gmail_candidate_account is None
        ):
            raise ValueError(
                "verify both gmail accounts or mark their authority unproved"
            )
        return self


@dataclass(frozen=True, slots=True)
class ActivationFinding:
    id: UUID | str | None
    status: str
    tool: str | None
    verdict: str
    detail: str
    source_start_safe: bool = False


@dataclass(frozen=True, slots=True)
class ActivationCheck:
    control: OwnerControl | None
    findings: tuple[ActivationFinding, ...]

    @property
    def passed(self) -> bool:
        return all(item.verdict == "compatible" for item in self.findings)

    def as_json(self) -> dict[str, object]:
        return asdict(self) | {"outcome": "compatible" if self.passed else "blocked"}


async def check_activation(
    settings: Settings,
    host: CodexHostConfig | None = None,
    *,
    authority: MaintenanceAuthority | None = None,
) -> ActivationCheck:
    """Classify unfinished execution authority without admitting any work."""

    deny_same_identity_process_inspection()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with (
            deployment_ownership(engine) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            scope = settings.owner_scope
            source_scope = (
                scope if authority is None else authority.source_scope or scope
            )
            work = await maintenance_work(database, scope=source_scope)
            findings = await _activation_prerequisites(
                database, settings, work, authority
            )
            if findings:
                return ActivationCheck(work.control, findings)
            actions = ActionStore(database)
            try:
                cleared_old_mail = _require_mail_cut(
                    await historical_mail(actions),
                    settings.runtime_state_directory / CUT_RECEIPT,
                )
            except StartupDefect as error:
                return ActivationCheck(
                    work.control,
                    (
                        ActivationFinding(
                            None,
                            "historical",
                            "gmail.send_draft",
                            "mail_audit_required",
                            str(error),
                        ),
                    ),
                )
            async with AsyncExitStack() as resources:
                try:
                    selected_host = (
                        host if host is not None else settings.codex_host_config
                    )
                    if authority is not None:
                        _validate_runtime_layout(settings, selected_host)
                    config = MemoryConfig.load(settings.memory_config_path)
                    agent_runtime = build_agent_runtime(
                        provider_state_root=settings.runtime_state_directory,
                        codex_endpoints=selected_host.endpoints,
                        neon_origin=selected_host.google_neon.adapter_origin,
                        antigravity_endpoint=selected_host.agy_neon.socket,
                    )
                    resources.push_async_callback(agent_runtime.close)
                    memory = await resources.enter_async_context(
                        _memory_service(settings, config, database)
                    )

                    async def event_admitted() -> bool:
                        return False

                    _, definitions, _ = await _compose_main(
                        owner=JarvisOwner(database, scope),
                        settings=settings,
                        host=selected_host,
                        agent_runtime=agent_runtime,
                        actions=actions,
                        work=WorkStore(database, scope),
                        events=EventStore(database, scope),
                        event_admitted=event_admitted,
                        memory=memory,
                        tokens=google_tokens(settings, http),
                        google_api_http=http,
                        maps_http=http,
                        brave_http=http,
                        qualify_neon=True,
                    )
                except (
                    AgentRuntimeError,
                    AgentRuntimeDefect,
                    ConfigurationError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ) as error:
                    if authority is None:
                        raise
                    detail = (
                        str(error)
                        if isinstance(error, StartupDefect)
                        else f"target runtime check failed ({type(error).__name__})"
                    )
                    safe = await _quiet_source_start(database, work, authority, scope)
                    return ActivationCheck(
                        work.control,
                        (
                            ActivationFinding(
                                None,
                                "target",
                                None,
                                "target_check",
                                detail,
                                safe,
                            ),
                        ),
                    )
                return ActivationCheck(
                    work.control,
                    await _action_activation_verdicts(
                        actions,
                        definitions.plans["main"],
                        source_conversation_id=source_scope,
                        cleared_old_mail=cleared_old_mail,
                        authority=authority,
                        work=work,
                    ),
                )
    finally:
        await engine.dispose()


async def _quiet_source_start(
    database: Database,
    work: MaintenanceWork,
    authority: MaintenanceAuthority,
    scope: str,
) -> bool:
    """A target-only failure can return to a source with no startup effect to enter."""
    if (
        work.control is None
        or (work.pending and work.control.kind != "pause")
        or work.unsettled
        or authority.source_scope not in (None, scope)
        or authority.authority_changes.intersection({"owner", "database"})
    ):
        return False
    async with database.connect() as connection:
        blocker = await connection.scalar(
            select(action.c.id)
            .join(message, message.c.id == action.c.origin_message_id)
            .where(
                or_(
                    action.c.status.in_(("queued", "executing", "uncertain")),
                    and_(
                        action.c.status == "awaiting_approval",
                        or_(
                            message.c.source_conversation_id != scope,
                            message.c.request_state.is_distinct_from("waiting"),
                            message.c.wait_reason.is_distinct_from("approval"),
                        ),
                    ),
                )
            )
            .limit(1)
        )
    return blocker is None


async def _activation_prerequisites(
    database: Database,
    settings: Settings,
    work: MaintenanceWork,
    authority: MaintenanceAuthority | None,
) -> tuple[ActivationFinding, ...]:
    if work.control is None or work.control.kind not in {"pause", "resume"}:
        return (
            ActivationFinding(
                work.control.id if work.control else None,
                "control",
                None,
                "uninitialized",
                "source canonical pause or resume is missing",
            ),
        )
    if authority is not None and authority.source_scope not in (
        None,
        settings.owner_scope,
    ):
        # Changing the active owner's scope requires its own admission contract.
        return (
            ActivationFinding(
                work.control.id,
                "control",
                None,
                "authority_changed",
                "selected owner scope differs from the staged owner scope",
            ),
        )
    try:
        require_native_files(settings.runtime_state_directory)
        await require_native_data(database, conversation_id=settings.owner_scope)
    except NativeActivationDefect as error:
        return (
            ActivationFinding(
                error.identifier,
                "native",
                None,
                "native_contract",
                str(error),
            ),
        )
    except RuntimeError as error:
        return (
            ActivationFinding(
                None,
                "native",
                None,
                "native_contract",
                str(error),
            ),
        )
    if authority is not None and authority.authority_changes.intersection(
        {"owner", "database", "native", "memory"}
    ):
        affected = work.resumable or work.unsettled
        if affected:
            return tuple(
                ActivationFinding(
                    identifier,
                    "request_or_attempt",
                    None,
                    "authority_changed",
                    "pending work belongs to the selected authority",
                )
                for identifier in affected
            )
    if authority is not None and "notice" in authority.authority_changes:
        async with database.connect() as connection:
            pending = await connection.scalar(
                select(home_notice.c.id)
                .where(home_notice.c.provider_id.is_(None))
                .order_by(home_notice.c.created_at, home_notice.c.id)
                .limit(1)
            )
        if pending is not None:
            return (
                ActivationFinding(
                    pending,
                    "pending_notice",
                    None,
                    "authority_changed",
                    "pending notice requires delivery under the original authority",
                ),
            )
    return ()


def _changed_action_authority(
    tool: str,
    stored: StoredAction,
    authority: MaintenanceAuthority | None,
) -> str | None:
    if authority is None:
        return None
    changed = authority.authority_changes
    namespace = tool.partition(".")[0]
    area = {"agent": "worker", "attachment": "attachments"}.get(namespace, namespace)
    if (
        namespace == "gmail"
        and "gmail" in changed
        and authority.gmail_candidate_account is None
    ):
        return "staged gmail subject or grants differ or are unverified"
    if namespace == "gmail":
        contract = stored.current_execution_contract.workspace
        account = contract.account if contract is not None else None
        candidate = authority.gmail_candidate_account
        source = authority.gmail_source_account
        if candidate is not None and (
            (account is not None and candidate != account)
            or (source is not None and candidate != source)
        ):
            return "stored mail authority differs from the staged gmail account"
        if (
            changed.intersection({"attachments", "native"})
            and contract is not None
            and isinstance(contract.effect, FrozenCompose)
            and contract.effect.files
        ):
            return "mail draft has files staged under the changed authority"
    if area in changed or changed.intersection({"owner", "database"}):
        return f"the staged {area} authority differs from the selected release"
    return None


async def _action_activation_verdicts(
    actions: ActionStore,
    plan: FrozenToolPlan,
    *,
    source_conversation_id: str,
    cleared_old_mail: frozenset[UUID] = frozenset(),
    authority: MaintenanceAuthority | None = None,
    work: MaintenanceWork | None = None,
) -> tuple[ActivationFinding, ...]:
    async with actions.engine.connect() as connection:
        unfinished = (
            await connection.execute(
                select(
                    action.c.id,
                    action.c.status,
                    action.c.tool_name,
                    message.c.source_conversation_id,
                    message.c.request_state,
                    message.c.wait_reason,
                )
                .join(message, message.c.id == action.c.origin_message_id)
                .where(
                    action.c.status.in_(
                        ("queued", "awaiting_approval", "executing", "uncertain")
                    )
                )
                .order_by(action.c.created_at, action.c.id)
            )
        ).all()
    retired = await actions.unreported_terminal(
        source_conversation_id=source_conversation_id,
        limit=100,
        retired_only=True,
    )
    verdicts = [
        ActivationFinding(
            item.id,
            item.status,
            str(item.tool_name),
            "retired_pending_events",
            "publish the original action outcome under the selected release",
        )
        for item in retired
    ]
    reported = {item.id for item in retired}
    source_paused = (
        work is not None and work.control is not None and work.control.kind == "pause"
    )
    quiet_approval_waits = (
        work is not None
        and not work.pending
        and not work.unsettled
        and not any(status in {"queued", "executing"} for _, status, *_ in unfinished)
    )
    for (
        identifier,
        status,
        tool,
        origin_scope,
        request_state,
        wait_reason,
    ) in unfinished:
        if identifier in reported:
            continue
        proof = False
        if origin_scope != source_conversation_id and status != "uncertain":
            verdict = "foreign_scope"
            detail = "executable action belongs to another owner scope"
        elif status == "uncertain" and identifier in cleared_old_mail:
            verdict = "compatible"
            detail = "terminal historical uncertainty retains its exact cut receipt"
        else:
            try:
                stored = await actions.get(identifier)
                if stored is None:
                    raise ActionPersistenceDefect("action is absent")
            except ActionPersistenceDefect:
                verdict = "does_not_load"
                detail = "stored action cannot be validated by this release"
            else:
                proof = status != "executing" and (
                    source_paused
                    or (
                        quiet_approval_waits
                        and status == "awaiting_approval"
                        and request_state == "waiting"
                        and wait_reason == "approval"
                    )
                )
                if status == "uncertain":
                    proof = False
                    if archived_worker_action(stored):
                        verdict = "compatible"
                        detail = "terminal historical uncertainty remains recorded"
                    else:
                        verdict = "uncertain"
                        detail = "outcome unknown; use the original reconciliation"
                else:
                    try:
                        require_current_action_binding(stored, plan)
                    except RuntimeError:
                        verdict = "binding"
                        detail = (
                            "stored action does not validate against the staged binding"
                        )
                    else:
                        changed = _changed_action_authority(tool, stored, authority)
                        if changed is not None:
                            verdict, detail = "authority_changed", changed
                        elif status == "executing":
                            if stored.tool_name in RECOVERABLE_ACTION_IDS:
                                verdict = "compatible"
                                detail = (
                                    "startup can reconcile the original executor entry"
                                )
                            else:
                                verdict = "in_flight"
                                detail = (
                                    "this release lacks the original recovery procedure"
                                )
                        else:
                            verdict = "compatible"
                            detail = (
                                "stored commitment can retain its original authority"
                            )
        verdicts.append(
            ActivationFinding(identifier, status, tool, verdict, detail, proof)
        )
    return tuple(verdicts)


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
            _isolated_provider(settings, host, "dreamer") as (
                provider,
                kernel,
                routes,
            ),
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
                routes=routes,
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
                routes,
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
                routes=routes,
            )
            async with database.begin() as connection:
                await memory.library.rebuild(
                    connection, start, count, generation=generation
                )
            cutoff = await memory.library.cutoff()
            try:
                await worker.ensure_ready(cutoff, CancellationToken())
            except MemoryError as error:
                if error.code != "compaction_blocked":
                    raise
                raise RuntimeError(
                    f"memory rebuild remains incomplete at cutoff {cutoff}"
                ) from None
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
    activation = commands.add_parser(
        "check-activation",
        help="check unfinished actions against this release while stopped",
    )
    activation.add_argument(
        "--maintenance",
        action="store_true",
        help="read authority changes and print a JSON verdict",
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
    enrollment = commands.add_parser(
        "workspace-enroll", help="enroll a workspace grant while stopped"
    )
    enrollment.add_argument("--client", required=True, type=Path)
    enrollment.add_argument("--email", required=True)
    enrollment.add_argument("--label")
    commands.add_parser(
        "workspace-disconnect",
        help="invalidate the local workspace grant while stopped",
    )
    restore_gap = commands.add_parser(
        "workspace-restore-gap", help="record the coverage gap from a verified restore"
    )
    restore_gap.add_argument("--cut", required=True, type=datetime.fromisoformat)
    restore_gap.add_argument("--restored", required=True, type=datetime.fromisoformat)
    arrival = commands.add_parser(
        "workspace-enroll-arrivals", help="bind a stopped verified arrival handoff"
    )
    arrival.add_argument("--handoff", required=True, type=Path)
    repair = commands.add_parser(
        "workspace-confirm-removed",
        help="confirm you verified removal of the pending label on a named message",
    )
    repair.add_argument("message")
    repair.add_argument("--account", required=True)
    repair.add_argument("--grant-id", required=True, type=UUID)
    repair.add_argument("--label-id", required=True)
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
    commands.add_parser("list-parked", help="inspect parked inputs and their commands")
    release = commands.add_parser(
        "release-parked",
        help="release explicitly named parked input after operator correction",
    )
    release.add_argument("message_ids", metavar="MESSAGE_ID", type=UUID, nargs="+")
    catchup = commands.add_parser(
        "queue-recovery-catchup",
        help="queue a reviewed read-only parked mail inventory",
    )
    catchup.add_argument("inventory", metavar="INVENTORY", type=Path)
    quota_wait = commands.add_parser(
        "resume-recovery-quota-wait",
        help="resume a reviewed held mail catch-up at its recorded quota deadline",
    )
    quota_wait.add_argument("inventory", metavar="INVENTORY", type=Path)
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
        if arguments.command == "list-parked":
            print(asyncio.run(list_parked(PausedSettings.from_env())))
            return 0
        if arguments.command == "queue-recovery-catchup":
            identifier = asyncio.run(
                queue_recovery_catchup(PausedSettings.from_env(), arguments.inventory)
            )
            print(identifier)
            return 0
        if arguments.command == "release-parked":
            message_ids = tuple(arguments.message_ids)
            if len(set(message_ids)) != len(message_ids):
                raise StartupDefect("release IDs must be unique")
            asyncio.run(release_parked(PausedSettings.from_env(), message_ids))
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
        elif arguments.command in {
            "resume-recovery-quota-wait",
            "workspace-enroll",
            "workspace-disconnect",
            "workspace-restore-gap",
            "workspace-enroll-arrivals",
            "workspace-confirm-removed",
        }:
            asyncio.run(workspace_operator(settings, arguments))
        elif arguments.command == "check-activation":
            authority = (
                MaintenanceAuthority.model_validate_json(sys.stdin.buffer.read(16_385))
                if arguments.maintenance
                else None
            )
            try:
                check = asyncio.run(check_activation(settings, authority=authority))
            except DeploymentAlreadyOwned:
                check = ActivationCheck(
                    None,
                    (
                        ActivationFinding(
                            None,
                            "deployment",
                            None,
                            "busy",
                            "another jarvis process owns the deployment",
                        ),
                    ),
                )
            if arguments.maintenance:
                print(json.dumps(check.as_json(), sort_keys=True, default=str))
            else:
                for item in check.findings:
                    print(
                        f"action {item.id} {item.status} {item.tool} "
                        f"{item.verdict}. {item.detail}"
                    )
                compatible = sum(
                    item.verdict == "compatible" for item in check.findings
                )
                in_flight = sum(item.verdict == "in_flight" for item in check.findings)
                incompatible = len(check.findings) - compatible - in_flight
                print(
                    f"activation check: compatible={compatible} "
                    f"incompatible={incompatible} in_flight={in_flight}"
                )
            return 0 if check.passed else 1
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
    except WorkspaceError as exc:
        LOGGER.error("workspace command failed: %s", exc.kind)
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
    "list_parked",
    "main",
    "rebuild_memory",
    "release_parked",
    "serve",
    "stopped_native_cutover",
]

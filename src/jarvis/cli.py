"""Minimal Jarvis service and operator entry points."""

from __future__ import annotations

import argparse
import asyncio
import grp
import logging
import os
import stat
from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from llm_agent_kernel import CancellationToken
from llm_tools import FrozenToolPlan
from provider_runtime.agent_runtime import AgentRuntime
from sqlalchemy import text

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
from jarvis.db import create_engine
from jarvis.decisions import ModelEvidence, PostgresModelDecisionJournal
from jarvis.definitions import (
    RoleDefinitions,
    build_definitions,
    build_dreamer,
    build_write_gate,
)
from jarvis.discord import DiscordCreateMessageClient, DiscordGateway
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
from jarvis.memory_tools import compose_memory_catalog
from jarvis.memory_workers import DreamerRunCompleted, DreamerWorker, RemembererWorker
from jarvis.messages import MessageStore
from jarvis.native_cutover import (
    cutover_native,
    require_native_data,
    require_native_files,
)
from jarvis.native_runtime import NativeRunner
from jarvis.ownership import (
    Database,
    DeploymentAlreadyOwned,
    deployment_ownership,
)
from jarvis.proactivity import ProcessLocalWakeTimer
from jarvis.process_security import deny_same_identity_process_inspection
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_positions import PostgresReadRecorder
from jarvis.rebuild import (
    DerivedMemoryCorpusRebuild,
    DreamMutationProgress,
    PostgresRebuildStore,
    rebuild_memory_corpus,
)
from jarvis.service import JarvisService
from jarvis.settings import Settings
from jarvis.state import PausedState
from jarvis.tool_composition import ToolComposition, build_tool_composition
from jarvis.write_dispatch import (
    ActionRecovery,
    WriteToolDispatcher,
    gmail_send_basis_is_current,
    require_current_action_binding,
)
from jarvis.write_gate import AutomaticWriteGate
from jarvis.write_tools import GmailSendDraftInput

LOGGER = logging.getLogger(__name__)

_MAXIMUM_REBUILD_MEMORY_ROWS = 10_000


class StartupDefect(RuntimeError):
    """The configured private runtime layout is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class _IsolatedMemoryRuntime:
    dreamer: DreamerWorker
    embedder: OpenAIEmbedder


@asynccontextmanager
async def _isolated_memory_runtime(
    *,
    settings: Settings,
    host: CodexHostConfig,
    engine: Database,
    owner: JarvisOwner,
) -> AsyncIterator[_IsolatedMemoryRuntime]:
    async with httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
    ) as http:
        memory = MemoryStore(engine)
        embedder = OpenAIEmbedder(
            settings.embedding_openai_api_key,
            http_client=http,
        )
        catalog = compose_memory_catalog(PostgresMemoryRepository(engine), embedder)
        agent_runtime = build_agent_runtime(
            provider_state_root=settings.runtime_state_directory,
            codex_endpoints=host.endpoints,
        )
        try:
            provider_configuration = await resolve_provider_configuration(
                runtime=agent_runtime,
                profile_key=settings.codex_profile_key,
                model_key=settings.codex_model,
            )
            definition, plan = build_dreamer(
                catalog=catalog,
                provider=provider_configuration,
                owner_timezone=settings.owner_timezone,
            )
            kernel = build_kernel_runtime(
                runtime=agent_runtime,
                shared_cwd_parent=Path(host.cognition_cwd_parent),
            )
        except BaseException:
            await agent_runtime.close()
            raise
        try:
            yield _IsolatedMemoryRuntime(
                dreamer=DreamerWorker(
                    definition=definition,
                    plan=plan,
                    owner=owner,
                    provider=kernel.provider,
                    model_decisions=lambda evidence: PostgresModelDecisionJournal(
                        engine, evidence=evidence
                    ),
                    dispatcher_factory=lambda: MemoryToolDispatcher(
                        PostgresReadRecorder(engine)
                    ),
                    memory=memory,
                ),
                embedder=embedder,
            )
        finally:
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


def initialize_state(settings: Settings, host: CodexHostConfig) -> None:
    """Create the private provider-state directory; host truth is in Postgres."""

    _shared_cognition_directory(Path(host.cognition_cwd_parent), host.client_group)
    directory = settings.runtime_state_directory
    if directory.exists():
        _private_directory(directory, "runtime state directory")
    else:
        try:
            directory.mkdir(mode=0o700)
        except OSError as exc:
            raise StartupDefect("runtime state directory could not be created") from exc


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
) -> None:
    """Own worker/Gateway lifetime inside the lifetime of their dependencies."""
    if shutdown.is_set():
        return
    worker = asyncio.create_task(service.run_worker(), name="jarvis-worker")

    async def run_gateway() -> None:
        await gateway.start(token)
        if gateway.event_failed:
            raise RuntimeError("Discord event processing failed")

    gateway_task = asyncio.create_task(run_gateway(), name="jarvis-discord-gateway")
    stopping = asyncio.create_task(shutdown.wait(), name="jarvis-shutdown-request")
    try:
        done, _ = await asyncio.wait(
            {worker, gateway_task, stopping}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            task.result()
    finally:
        gateway.stop_ingress()
        service.request_shutdown()
        stopping.cancel()  # This task only waits on an Event; it owns no I/O.
        await asyncio.gather(stopping, return_exceptions=True)
        results = await asyncio.gather(
            worker, gateway.drain_callbacks(), return_exceptions=True
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
    memory_repository: PostgresMemoryRepository,
    embedder: OpenAIEmbedder,
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
    )
    composition = build_tool_composition(
        settings=settings,
        google_oauth_http=google_oauth_http,
        google_api_http=google_api_http,
        maps_http=maps_http,
        brave_http=brave_http,
        memory_repository=memory_repository,
        memory_embedder=embedder,
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
    agent_runtime = None
    kernel_runtime = None
    try:
        async with deployment_ownership(engine) as database:
            try:
                store = MessageStore(database)
                owner = JarvisOwner(database, str(settings.discord.channel_id))
                await require_native_data(database, conversation_id=owner.scope_id)
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
                    memory = MemoryStore(database)
                    memory_repository = PostgresMemoryRepository(database)
                    actions = ActionStore(database)
                    agent_runtime = build_agent_runtime(
                        provider_state_root=settings.runtime_state_directory,
                        codex_endpoints=host.endpoints,
                    )
                    embedder = OpenAIEmbedder(
                        settings.embedding_openai_api_key,
                        http_client=embedding_http,
                    )
                    composition, definitions, agents = await _compose_main(
                        settings=settings,
                        agent_runtime=agent_runtime,
                        actions=actions,
                        memory_repository=memory_repository,
                        embedder=embedder,
                        google_oauth_http=google_oauth_http,
                        google_api_http=google_api_http,
                        maps_http=maps_http,
                        brave_http=brave_http,
                    )
                    kernel_runtime = build_kernel_runtime(
                        runtime=agent_runtime,
                        shared_cwd_parent=Path(host.cognition_cwd_parent),
                    )

                    def model_decisions(
                        evidence: ModelEvidence | None,
                    ) -> PostgresModelDecisionJournal:
                        return PostgresModelDecisionJournal(database, evidence=evidence)

                    def memory_dispatcher() -> MemoryToolDispatcher:
                        return MemoryToolDispatcher(PostgresReadRecorder(database))

                    history = PostgresCanonicalHistory(database)
                    gate = AutomaticWriteGate(
                        definition=definitions.automatic_write_gate,
                        plan=definitions.plans["automatic_write_gate"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        model_decisions=model_decisions,
                    )
                    rememberer = RemembererWorker(
                        definition=definitions.rememberer,
                        plan=definitions.plans["rememberer"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        model_decisions=model_decisions,
                        dispatcher_factory=memory_dispatcher,
                        memory=memory,
                        messages=store,
                        embedder=embedder,
                        maximum_messages_per_group=settings.maximum_batch_size,
                    )
                    dreamer = DreamerWorker(
                        definition=definitions.dreamer,
                        plan=definitions.plans["dreamer"],
                        owner=owner,
                        provider=kernel_runtime.provider,
                        model_decisions=model_decisions,
                        dispatcher_factory=memory_dispatcher,
                        memory=memory,
                    )
                    runner = NativeRunner(
                        settings=settings,
                        store=store,
                        owner=owner,
                        kernel_runtime=kernel_runtime,
                        model_decisions=model_decisions,
                        definitions=definitions,
                        history=history,
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
                                ),
                                owner_timezone=settings.owner_timezone,
                                source_conversation_id=str(settings.discord.channel_id),
                                verified_owner_only_calendar_ids=(
                                    settings.verified_owner_only_calendar_ids
                                ),
                                host_secrets=settings.host_secrets,
                                schedule_changed=lambda: (
                                    wake_timer.notify_changed()
                                    if wake_timer is not None
                                    else None
                                ),
                            )
                        ),
                        memory_repository=memory_repository,
                        memory_dispatcher_factory=memory_dispatcher,
                        rememberer=rememberer,
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
                    action_recovery = ActionRecovery(
                        actions=actions,
                        google_write=composition.google_write,
                        plan=definitions.plans["main"],
                        source_conversation_id=str(settings.discord.channel_id),
                        schedule_changed=lambda: (
                            wake_timer.notify_changed()
                            if wake_timer is not None
                            else None
                        ),
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
                        background=rememberer,
                        dreamer=dreamer,
                        scheduled_wakes=actions,
                        action_plan=definitions.plans["main"],
                        action_recovery=action_recovery,
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
                    _, definitions, _ = await _compose_main(
                        settings=settings,
                        agent_runtime=runtime,
                        actions=ActionStore(database),
                        memory_repository=PostgresMemoryRepository(database),
                        embedder=OpenAIEmbedder(
                            settings.embedding_openai_api_key, http_client=http
                        ),
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


async def check_activation(
    settings: Settings,
    host: CodexHostConfig,
) -> tuple[tuple[UUID, str, str, str], ...]:
    """Classify unfinished actions and undrained delivery; read-only."""

    deny_same_identity_process_inspection()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with (
            deployment_ownership(engine) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            actions = ActionStore(database)
            agent_runtime = build_agent_runtime(
                provider_state_root=settings.runtime_state_directory,
                codex_endpoints=host.endpoints,
            )
            try:
                # the unused http client fills every connector slot: nothing dispatches.
                _, definitions, _ = await _compose_main(
                    settings=settings,
                    agent_runtime=agent_runtime,
                    actions=actions,
                    memory_repository=PostgresMemoryRepository(database),
                    embedder=OpenAIEmbedder(
                        settings.embedding_openai_api_key, http_client=http
                    ),
                    google_oauth_http=http,
                    google_api_http=http,
                    maps_http=http,
                    brave_http=http,
                )
                plan = definitions.plans["main"]
                # raw text so an empty ledger passes whatever the target schema; the
                # lock connection is not reentrant, so this read ends before any load.
                async with database.connect() as connection:
                    unfinished = (
                        await connection.execute(
                            text(
                                "select id, status, tool_name from action "
                                "where status = any(:statuses) order by created_at, id"
                            ),
                            {"statuses": ["queued", "awaiting_approval", "executing"]},
                        )
                    ).all()
                # A catalog cut cannot strand an old resolution or its delivery.
                # Existing messages stay canonical; this check only reports IDs.
                unreported = await actions.unreported_terminal(
                    source_conversation_id=str(settings.discord.channel_id), limit=100
                )
                async with database.connect() as connection:
                    undrained = (
                        await connection.execute(
                            text(
                                "select id, role from message where "
                                "(role = 'assistant' and source_message_id is null) or "
                                "(source = 'action' and processed_at is null) "
                                "order by created_at, id"
                            )
                        )
                    ).all()
                verdicts: list[tuple[UUID, str, str, str]] = []
                for action_id, status, tool_name in unfinished:
                    verdict = (
                        "in_flight"
                        if status == "executing"
                        else await _pending_action_verdict(actions, plan, action_id)
                    )
                    verdicts.append((action_id, status, tool_name, verdict))
                verdicts.extend(
                    (
                        value.id,
                        value.status,
                        str(value.tool_name),
                        "undrained_resolution",
                    )
                    for value in unreported
                )
                verdicts.extend(
                    (identifier, role, "message", "undrained_delivery_or_resolution")
                    for identifier, role in undrained
                )
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
    settings: Settings,
    host: CodexHostConfig,
) -> DreamerRunCompleted | None:
    """Run one operator-requested dream while the service is stopped."""
    _validate_runtime_layout(settings, host)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            if await MemoryStore(database).raw_memory_count() == 0:
                return None
            async with _isolated_memory_runtime(
                settings=settings,
                host=host,
                engine=database,
                owner=JarvisOwner(database, "jarvis-memory"),
            ) as runtime:
                outcome = await runtime.dreamer.run_at(
                    as_of=datetime.now(UTC),
                    cancellation=CancellationToken(),
                )
            if not isinstance(outcome, DreamerRunCompleted):
                raise RuntimeError("manual dream did not complete")
            return outcome
    finally:
        await engine.dispose()


async def rebuild_memory(
    settings: Settings,
    host: CodexHostConfig,
) -> DerivedMemoryCorpusRebuild:
    """Rebuild the deployment's derived memory while the service is stopped."""
    _validate_runtime_layout(settings, host)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine) as database:
            async with _isolated_memory_runtime(
                settings=settings,
                host=host,
                engine=database,
                owner=JarvisOwner(database, "jarvis-memory"),
            ) as runtime:

                async def dream(as_of: datetime) -> DreamMutationProgress:
                    outcome = await runtime.dreamer.run_at(
                        as_of=as_of,
                        cancellation=CancellationToken(),
                    )
                    if not isinstance(outcome, DreamerRunCompleted):
                        raise RuntimeError("rebuild dreamer did not complete")
                    return DreamMutationProgress(
                        len(outcome.created_summary_ids),
                        len(outcome.removed_summary_ids),
                    )

                return await rebuild_memory_corpus(
                    store=PostgresRebuildStore(database),
                    embedder=runtime.embedder,
                    dream_once=dream,
                    maximum_memory_rows=_MAXIMUM_REBUILD_MEMORY_ROWS,
                    as_of=datetime.now(UTC),
                )
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the Jarvis Discord service")
    commands.add_parser("initialize-state", help="initialize private host state")
    commands.add_parser(
        "check-activation",
        help="check unfinished actions against this release while stopped",
    )
    commands.add_parser(
        "cutover-native", help="convert stopped legacy state for native activation"
    )
    commands.add_parser("dream", help="run one isolated dream while stopped")
    commands.add_parser(
        "rebuild-memory",
        help="rebuild all derived memory while stopped",
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
            initialize_state(settings, host)
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
                print("Dream skipped: no raw memory.")
            else:
                print(
                    "Dream completed: "
                    f"inserted={len(result.created_summary_ids)} "
                    f"removed={len(result.removed_summary_ids)}."
                )
        elif arguments.command == "rebuild-memory":
            result = asyncio.run(rebuild_memory(settings, host))
            print(
                "Memory rebuild completed: "
                f"raw={result.raw_memory_count} "
                f"summaries={result.summaries_after}."
            )
        elif arguments.command == "release-parked":
            message_ids = tuple(arguments.message_ids)
            if len(set(message_ids)) != len(message_ids):
                raise StartupDefect("release IDs must be unique")
            asyncio.run(release_parked(settings, message_ids))
            print(f"Released {len(message_ids)} parked message(s).")
        else:  # pragma: no cover
            raise AssertionError("unknown command")
    except (ConfigurationError, RuntimeError, OSError, ValueError) as exc:
        LOGGER.error("Jarvis command failed: type=%s", type(exc).__name__)
        return 1
    except KeyboardInterrupt:
        LOGGER.info("Jarvis stopped by operator signal")
        return 130
    return 0


__all__ = [
    "StartupDefect",
    "check_activation",
    "dream_once",
    "initialize_state",
    "main",
    "rebuild_memory",
    "release_parked",
    "serve",
    "stopped_native_cutover",
]

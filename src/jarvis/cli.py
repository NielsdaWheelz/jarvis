"""Minimal Jarvis service and operator entry points."""

from __future__ import annotations

import argparse
import asyncio
import logging
import stat
from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from llm_agent_kernel import (
    AdmissionGranted,
    AdmissionRequest,
    AdmissionToken,
    AdmissionUsage,
    CancellationToken,
    ProviderUsage,
    RunId,
    ThreadId,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis.actions import ActionStore
from jarvis.admission import (
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
    pre_all_calendar_slice6_admission_limits,
    slice5_admission_limits,
    slice6_admission_limits,
)
from jarvis.approval_runtime import (
    ApprovalActionHandler,
    ApprovalAwareDiscordDelivery,
    ApprovalRecoveryDisabler,
)
from jarvis.codex_control import CodexController, CodexHostConfig
from jarvis.config import ConfigurationError
from jarvis.db import create_engine
from jarvis.definitions import (
    Slice4Definitions,
    build_slice4_definitions,
    build_slice5_write_gate,
    build_slice6_definitions,
)
from jarvis.discord import DiscordCreateMessageClient, DiscordGateway
from jarvis.embeddings import OpenAIEmbedder
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import KernelRuntime, build_agent_runtime, build_kernel_runtime
from jarvis.memory import MemoryStore
from jarvis.memory_dispatch import MemoryToolDispatcher
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.proactivity import ProcessLocalWakeTimer
from jarvis.process_security import deny_same_identity_process_inspection
from jarvis.read_composition import build_slice3_catalog
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.rebuild import (
    DerivedMemoryCorpusRebuild,
    DreamMutationProgress,
    PostgresRebuildStore,
    corpus_rebuild_admission_limits,
    rebuild_memory_corpus,
)
from jarvis.service import (
    BackgroundDeferred,
    DreamerRunCompleted,
    DreamerWorker,
    JarvisService,
    JarvisThreadRunner,
    RemembererWorker,
)
from jarvis.settings import Settings
from jarvis.state import PausedState
from jarvis.write_composition import build_slice6_composition
from jarvis.write_dispatch import ActionRecovery, WriteToolDispatcher
from jarvis.write_gate import AutomaticWriteGate

LOGGER = logging.getLogger(__name__)

_MAXIMUM_REBUILD_MEMORY_ROWS = 10_000


class StartupDefect(RuntimeError):
    """The configured private runtime layout is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class _IsolatedMemoryRuntime:
    admission: RootTrackingAdmissionPort
    definitions: Slice4Definitions
    dreamer: DreamerWorker
    embedder: OpenAIEmbedder
    kernel: KernelRuntime
    memory: MemoryStore


@asynccontextmanager
async def _isolated_memory_runtime(
    *,
    settings: Settings,
    host: CodexHostConfig,
    engine: AsyncEngine,
    admission: RootTrackingAdmissionPort,
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
        catalog = build_slice3_catalog(
            settings=settings,
            google_oauth_http=http,
            google_api_http=http,
            maps_http=http,
            brave_http=http,
            memory_repository=PostgresMemoryRepository(engine),
            memory_embedder=embedder,
        )
        definitions = build_slice4_definitions(
            catalog=catalog,
            profile_key=settings.codex_profile_key,
            model=settings.codex_model,
            owner_timezone=settings.owner_timezone,
        )
        agent_runtime = build_agent_runtime(
            provider_state_root=settings.runtime_state_directory,
            codex_endpoints=host.endpoints,
        )
        try:
            kernel = build_kernel_runtime(
                runtime=agent_runtime,
                shared_cwd_parent=Path(host.cognition_cwd_parent),
                session_ref_path=settings.session_reference_path,
                model=settings.codex_model,
                kernel_limits=definitions.main.limits,
            )
        except BaseException:
            await agent_runtime.close()
            raise
        try:
            yield _IsolatedMemoryRuntime(
                admission=admission,
                definitions=definitions,
                dreamer=DreamerWorker(
                    definition=definitions.dreamer,
                    plan=definitions.plans["dreamer"],
                    admission=admission,
                    provider=kernel.provider,
                    dispatcher_factory=MemoryToolDispatcher,
                    memory=memory,
                ),
                embedder=embedder,
                kernel=kernel,
                memory=memory,
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


def _shared_cognition_directory(path: Path) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise StartupDefect("cognition cwd parent is unavailable") from exc
    if not path.is_dir() or mode != 0o2750:
        raise StartupDefect("cognition cwd parent must be a mode-02750 directory")


def _validate_runtime_layout(settings: Settings, host: CodexHostConfig) -> None:
    _private_directory(settings.runtime_state_directory, "runtime state directory")
    _shared_cognition_directory(Path(host.cognition_cwd_parent))


def initialize_state(settings: Settings, host: CodexHostConfig) -> None:
    """Create the private, content-free durable host state exactly once."""

    _shared_cognition_directory(Path(host.cognition_cwd_parent))
    directory = settings.runtime_state_directory
    if directory.exists():
        _private_directory(directory, "runtime state directory")
    else:
        try:
            directory.mkdir(mode=0o700)
        except OSError as exc:
            raise StartupDefect("runtime state directory could not be created") from exc
    if settings.paused_state_path.exists() or settings.admission_journal_path.exists():
        raise StartupDefect("private host state is already initialized")
    PausedState.initialize(settings.paused_state_path)
    RollingAdmissionPort.initialize(
        settings.admission_journal_path,
        slice6_admission_limits(settings.maximum_batch_size),
    )


async def recover_startup_actions(
    *,
    action_recovery: ActionRecovery,
    paused: PausedState,
    messages: MessageStore,
) -> int:
    inactive = await paused.is_paused() or await messages.circuit_is_open()
    return await action_recovery.recover(allow_queued_execution=not inactive)


async def serve(settings: Settings, host: CodexHostConfig) -> None:
    """Own the deployment and run the one Discord channel service."""

    deny_same_identity_process_inspection()
    _validate_runtime_layout(settings, host)
    engine = create_engine(settings.database_url.get_secret_value())
    agent_runtime = None
    kernel_runtime = None
    gateway = None
    service = None
    worker: asyncio.Task[None] | None = None
    gateway_task: asyncio.Task[None] | None = None
    try:
        async with deployment_ownership(engine):
            try:
                RollingAdmissionPort.migrate_limits(
                    settings.admission_journal_path,
                    previous=(
                        pre_all_calendar_slice6_admission_limits(
                            settings.maximum_batch_size
                        ),
                        slice5_admission_limits(settings.maximum_batch_size),
                    ),
                    current=slice6_admission_limits(settings.maximum_batch_size),
                )
                admission_store = RollingAdmissionPort(
                    settings.admission_journal_path,
                    slice6_admission_limits(settings.maximum_batch_size),
                )
                recovered = await admission_store.recover_orphans()
                if recovered:
                    LOGGER.warning(
                        "Recovered interrupted admission slots: count=%d",
                        len(recovered),
                    )
                paused = PausedState(settings.paused_state_path)
                await paused.is_paused()
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
                    memory = MemoryStore(engine)
                    actions = ActionStore(engine)
                    agent_runtime = build_agent_runtime(
                        provider_state_root=settings.runtime_state_directory,
                        codex_endpoints=host.endpoints,
                    )
                    embedder = OpenAIEmbedder(
                        settings.embedding_openai_api_key,
                        http_client=embedding_http,
                    )
                    provisional_gate, _ = build_slice5_write_gate(
                        profile_key=settings.codex_profile_key,
                        model=settings.codex_model,
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
                        profile_key=settings.codex_profile_key,
                        model=settings.codex_model,
                        owner_timezone=settings.owner_timezone,
                    )
                    if (
                        definitions.automatic_write_gate.fingerprint
                        != provisional_gate.fingerprint
                    ):
                        raise StartupDefect(
                            "write-gate definition changed during composition"
                        )
                    kernel_runtime = build_kernel_runtime(
                        runtime=agent_runtime,
                        shared_cwd_parent=Path(host.cognition_cwd_parent),
                        session_ref_path=settings.session_reference_path,
                        model=settings.codex_model,
                        kernel_limits=definitions.main.limits,
                    )
                    admission = RootTrackingAdmissionPort(admission_store)
                    store = MessageStore(engine)
                    history = PostgresCanonicalHistory(engine)
                    gate = AutomaticWriteGate(
                        definition=definitions.automatic_write_gate,
                        plan=definitions.plans["automatic_write_gate"],
                        admission=admission,
                        provider=kernel_runtime.provider,
                    )
                    rememberer = RemembererWorker(
                        definition=definitions.rememberer,
                        plan=definitions.plans["rememberer"],
                        admission=admission,
                        provider=kernel_runtime.provider,
                        dispatcher_factory=MemoryToolDispatcher,
                        memory=memory,
                        messages=store,
                        embedder=embedder,
                        maximum_messages_per_group=settings.maximum_batch_size,
                    )
                    dreamer = DreamerWorker(
                        definition=definitions.dreamer,
                        plan=definitions.plans["dreamer"],
                        admission=admission,
                        provider=kernel_runtime.provider,
                        dispatcher_factory=MemoryToolDispatcher,
                        memory=memory,
                    )
                    runner = JarvisThreadRunner(
                        settings=settings,
                        store=store,
                        admission=admission,
                        kernel_runtime=kernel_runtime,
                        definitions=definitions,
                        history=history,
                        checkpoint_dispatcher_factory=lambda checkpoint: (
                            WriteToolDispatcher(
                                checkpoint=checkpoint,
                                gate=gate,
                                actions=actions,
                                google_write=composition.google_write,
                                read=ReadToolDispatcher(
                                    host_secrets=settings.host_secrets
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
                        memory=memory,
                        memory_dispatcher_factory=MemoryToolDispatcher,
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
                    )
                    wake_timer = ProcessLocalWakeTimer(
                        store=actions,
                        on_due=lambda _: service.request_work(),
                    )
                    service.bind_wake_timer(wake_timer)
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
                    worker = asyncio.create_task(
                        service.run_worker(),
                        name="jarvis-worker",
                    )

                    async def run_gateway() -> None:
                        token = settings.discord.bot_token.get_secret_value()
                        await gateway.start(token)
                        if gateway.event_failed:
                            raise RuntimeError("Discord event processing failed")

                    gateway_task = asyncio.create_task(
                        run_gateway(),
                        name="jarvis-discord-gateway",
                    )
                    done, _ = await asyncio.wait(
                        {worker, gateway_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        task.result()
            finally:
                if service is not None:
                    service.request_shutdown()
                if gateway is not None and not gateway.is_closed():
                    await gateway.close()
                for task in (gateway_task, worker):
                    if task is not None and not task.done():
                        task.cancel()
                if gateway_task is not None or worker is not None:
                    await asyncio.gather(
                        *(task for task in (gateway_task, worker) if task is not None),
                        return_exceptions=True,
                    )
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
        async with deployment_ownership(engine):
            await MessageStore(engine).clear_parked(message_ids=message_ids)
    finally:
        await engine.dispose()


async def dream_once(
    settings: Settings,
    host: CodexHostConfig,
) -> DreamerRunCompleted | None:
    """Run one operator-requested dream while the service is stopped."""
    _validate_runtime_layout(settings, host)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        async with deployment_ownership(engine):
            if await MemoryStore(engine).raw_memory_count() == 0:
                return None
            limits = slice6_admission_limits(settings.maximum_batch_size)
            RollingAdmissionPort.migrate_limits(
                settings.admission_journal_path,
                previous=(
                    pre_all_calendar_slice6_admission_limits(
                        settings.maximum_batch_size
                    ),
                    slice5_admission_limits(settings.maximum_batch_size),
                ),
                current=limits,
            )
            admission_store = RollingAdmissionPort(
                settings.admission_journal_path,
                limits,
            )
            await admission_store.recover_orphans()
            admission = RootTrackingAdmissionPort(admission_store)
            async with _isolated_memory_runtime(
                settings=settings,
                host=host,
                engine=engine,
                admission=admission,
            ) as runtime:
                outcome = await runtime.dreamer.run_at(
                    as_of=datetime.now(UTC),
                    cancellation=CancellationToken(),
                )
            if isinstance(outcome, BackgroundDeferred):
                raise RuntimeError("manual dream is deferred by rolling admission")
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
    limits = corpus_rebuild_admission_limits()
    journal_path = settings.runtime_state_directory / "memory-rebuild-admission.json"
    engine = create_engine(settings.database_url.get_secret_value())
    root: AdmissionToken | None = None
    admission: RootTrackingAdmissionPort | None = None
    operation_failed = False
    try:
        async with deployment_ownership(engine):
            if not journal_path.exists():
                RollingAdmissionPort.initialize(journal_path, limits)
            admission_store = RollingAdmissionPort(journal_path, limits)
            recovered = await admission_store.recover_orphans()
            if recovered:
                LOGGER.warning(
                    "Recovered interrupted rebuild admission slots: count=%d",
                    len(recovered),
                )
            admission = RootTrackingAdmissionPort(admission_store)
            reserved = await admission.reserve(
                AdmissionRequest(
                    RunId(str(uuid4())),
                    ThreadId("jarvis-stopped-memory-rebuild"),
                    1,
                    1,
                    1,
                    1,
                )
            )
            if not isinstance(reserved, AdmissionGranted):
                raise RuntimeError("stopped rebuild admission is unavailable")
            root = reserved.token
            async with _isolated_memory_runtime(
                settings=settings,
                host=host,
                engine=engine,
                admission=admission,
            ) as runtime:

                async def dream(as_of: datetime) -> DreamMutationProgress:
                    assert root is not None
                    outcome = await runtime.dreamer.run_at(
                        as_of=as_of,
                        cancellation=CancellationToken(),
                        parent_admission=root,
                    )
                    if not isinstance(outcome, DreamerRunCompleted):
                        raise RuntimeError("rebuild dreamer did not complete")
                    return DreamMutationProgress(
                        len(outcome.created_summary_ids),
                        len(outcome.removed_summary_ids),
                    )

                result = await rebuild_memory_corpus(
                    store=PostgresRebuildStore(engine),
                    embedder=runtime.embedder,
                    dream_once=dream,
                    maximum_memory_rows=_MAXIMUM_REBUILD_MEMORY_ROWS,
                    as_of=datetime.now(UTC),
                )
        return result
    except BaseException:
        operation_failed = True
        raise
    finally:
        if root is not None and admission is not None:
            try:
                await admission.settle(
                    root,
                    AdmissionUsage(0, ProviderUsage(), 0.0),
                )
            except BaseException:
                if not operation_failed:
                    raise
                LOGGER.warning(
                    "Rebuild admission settlement also failed; recovery is required"
                )
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the Jarvis Discord service")
    commands.add_parser("initialize-state", help="initialize private host state")
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
    "dream_once",
    "initialize_state",
    "main",
    "rebuild_memory",
    "release_parked",
    "serve",
]

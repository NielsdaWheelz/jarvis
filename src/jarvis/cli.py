"""Minimal Jarvis service and operator entry points."""

from __future__ import annotations

import argparse
import asyncio
import logging
import stat
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import UUID

import httpx

from jarvis.admission import RollingAdmissionLimits, RollingAdmissionPort
from jarvis.config import ConfigurationError
from jarvis.db import create_engine
from jarvis.definitions import build_slice2_definitions
from jarvis.discord import DiscordCreateMessageClient, DiscordGateway
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import build_kernel_runtime
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.read_composition import build_read_catalog
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.service import JarvisService, JarvisThreadRunner
from jarvis.settings import Settings
from jarvis.state import PausedState

LOGGER = logging.getLogger(__name__)


class StartupDefect(RuntimeError):
    """The configured private runtime layout is unsafe or incomplete."""


def _private_directory(path: Path, name: str) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise StartupDefect(f"{name} is unavailable") from exc
    if not path.is_dir() or mode & 0o077:
        raise StartupDefect(f"{name} must be a private directory")


def _validate_runtime_layout(settings: Settings) -> None:
    _private_directory(settings.codex_state_root, "Codex state root")
    _private_directory(settings.runtime_state_directory, "runtime state directory")
    _private_directory(settings.provider_cwd_parent, "provider cwd parent")


def initialize_state(settings: Settings) -> None:
    """Create the private, content-free durable host state exactly once."""

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
    try:
        settings.provider_cwd_parent.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise StartupDefect("provider cwd parent could not be created") from exc
    _private_directory(settings.provider_cwd_parent, "provider cwd parent")
    PausedState.initialize(settings.paused_state_path)
    RollingAdmissionPort.initialize(
        settings.admission_journal_path,
        RollingAdmissionLimits(),
    )


async def serve(settings: Settings) -> None:
    """Own the deployment and run the one Discord channel service."""

    _validate_runtime_layout(settings)
    engine = create_engine(settings.database_url.get_secret_value())
    kernel_runtime = None
    gateway = None
    service = None
    worker: asyncio.Task[None] | None = None
    gateway_task: asyncio.Task[None] | None = None
    try:
        async with deployment_ownership(engine):
            try:
                admission = RollingAdmissionPort(
                    settings.admission_journal_path,
                    RollingAdmissionLimits(),
                )
                recovered = await admission.recover_orphans()
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
                    catalog = build_read_catalog(
                        settings=settings,
                        google_oauth_http=google_oauth_http,
                        google_api_http=google_api_http,
                        maps_http=maps_http,
                        brave_http=brave_http,
                    )
                    definitions = build_slice2_definitions(
                        catalog=catalog,
                        profile_key=settings.codex_profile_key,
                        model=settings.codex_model,
                        owner_timezone=settings.owner_timezone,
                    )
                    kernel_runtime = build_kernel_runtime(
                        provider_state_root=settings.codex_state_root,
                        private_cwd_parent=settings.provider_cwd_parent,
                        session_ref_path=settings.session_reference_path,
                        model=settings.codex_model,
                        kernel_limits=definitions.main.limits,
                    )
                    store = MessageStore(engine)
                    history = PostgresCanonicalHistory(engine)
                    runner = JarvisThreadRunner(
                        settings=settings,
                        store=store,
                        admission=admission,
                        kernel_runtime=kernel_runtime,
                        definitions=definitions,
                        history=history,
                        dispatcher_factory=lambda: ReadToolDispatcher(
                            host_secrets=settings.host_secrets
                        ),
                    )
                    delivery = DiscordCreateMessageClient(
                        settings.discord, discord_http
                    )
                    service = JarvisService(
                        settings=settings,
                        store=store,
                        paused=paused,
                        delivery=delivery,
                        runner=runner,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the Jarvis Discord service")
    commands.add_parser("initialize-state", help="initialize private host state")
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
        if arguments.command == "serve":
            asyncio.run(serve(settings))
        elif arguments.command == "initialize-state":
            initialize_state(settings)
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


__all__ = ["StartupDefect", "initialize_state", "main", "release_parked", "serve"]

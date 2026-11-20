"""Run the public archive and private embedding listeners under one writer lease."""

from __future__ import annotations

import asyncio
import os
import signal
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from socket import AF_UNIX, socket

import httpx
import uvicorn
from pydantic import SecretStr
from sqlalchemy import text
from universal_memory import MemoryStore

from jarvis.db import APPLICATION_SCHEMA_REVISION, SERVICE_MEMORY_READS, create_engine
from jarvis.embeddings import OpenAIEmbedder
from jarvis.memory_config import MemoryConfig
from jarvis.memory_http import create_memory_app
from jarvis.memory_rpc import create_internal_app
from jarvis.memory_service import MemoryService
from jarvis.ownership import MEMORY_LOCK_KEY, deployment_ownership
from jarvis.settings import MemoryServerSettings
from jarvis.tool_results import memory_result_size, memory_view_size


class _Server(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield  # Both listeners share the process shutdown signal.

    async def serve(self, sockets: list[socket] | None = None) -> None:
        try:
            await super().serve(sockets)
        except SystemExit as error:
            raise RuntimeError("memory endpoint could not start") from error


@contextmanager
def _private_listener(path: Path) -> Iterator[socket]:
    directory = path.parent.stat()
    if (
        not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != os.geteuid()
        or directory.st_mode & 0o027
    ):
        raise RuntimeError("memory socket requires a protected service-owned directory")
    # A killed predecessor may leave its socket behind. The memory key is held.
    if path.is_socket():
        path.unlink()
    with socket(AF_UNIX) as listener:
        listener.bind(str(path))
        if path.stat().st_gid != directory.st_gid:
            raise RuntimeError("memory socket must inherit the private client group")
        path.chmod(0o660)
        # The runtime directory is service-managed. Only unlink on acquisition:
        # a fenced predecessor exiting late must never unlink its successor.
        yield listener


async def serve_memory(settings: MemoryServerSettings, key: SecretStr) -> None:
    config = MemoryConfig.load(settings.memory_config_path)
    url = settings.database_url.get_secret_value()
    engine = create_engine(url)
    reads = create_engine(url, memory_reads=SERVICE_MEMORY_READS)
    try:
        async with (
            deployment_ownership(engine, lock_key=MEMORY_LOCK_KEY) as database,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as http,
        ):
            async with database.connect() as connection:
                revision, role = (
                    await connection.execute(
                        text("SELECT version_num, current_user FROM alembic_version")
                    )
                ).one()
                if role != "jarvis_memory":
                    raise RuntimeError(
                        "memory service requires the memory database role"
                    )
                if revision != APPLICATION_SCHEMA_REVISION:
                    raise RuntimeError("memory service requires the selected schema")
            memory = MemoryService(
                database=database,
                owner_available=database.check_available,
                library=MemoryStore(
                    reads, result_size=memory_result_size, view_size=memory_view_size
                ),
                embedder=OpenAIEmbedder(key, http_client=http),
                admitted_lanes=config.admitted_lanes,
                nexus_admitted_owner=config.nexus_admitted_owner,
            )
            public = _Server(
                uvicorn.Config(
                    create_memory_app(memory, config),
                    host="127.0.0.1",
                    port=settings.memory_http_port,
                    lifespan="on",
                    access_log=False,
                    log_level="warning",
                )
            )
            private = _Server(
                uvicorn.Config(
                    create_internal_app(memory),
                    lifespan="on",
                    access_log=False,
                    log_level="warning",
                )
            )
            with _private_listener(settings.memory_socket_path) as listener:
                shutdown = asyncio.Event()
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, shutdown.set)
                servers = (
                    asyncio.create_task(public.serve()),
                    asyncio.create_task(private.serve([listener])),
                )
                indexer = asyncio.create_task(memory.run_indexer(shutdown))
                loss = asyncio.create_task(database.wait_for_loss(shutdown))
                stopping = asyncio.create_task(shutdown.wait())
                try:
                    done, _ = await asyncio.wait(
                        (*servers, indexer, loss, stopping),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        task.result()
                    if not shutdown.is_set():
                        raise RuntimeError("memory service task stopped unexpectedly")
                finally:
                    if not shutdown.is_set():
                        # A dead owner cannot drain work. Cancel even stalled uploads.
                        public.config.timeout_graceful_shutdown = 0
                        private.config.timeout_graceful_shutdown = 0
                    public.should_exit = private.should_exit = True
                    shutdown.set()
                    stopping.cancel()
                    await asyncio.gather(
                        *servers, indexer, loss, stopping, return_exceptions=True
                    )
                    for sig in (signal.SIGTERM, signal.SIGINT):
                        loop.remove_signal_handler(sig)
    finally:
        await reads.dispose()
        await engine.dispose()

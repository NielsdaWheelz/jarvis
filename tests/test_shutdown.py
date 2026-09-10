from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from service_fixture import LocalGateway, host_config, service_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from jarvis import cli
from jarvis.cli import run_service
from jarvis.db import create_engine
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.service import JarvisService
from jarvis.state import PausedState

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("JARVIS_TEST_DATABASE_URL") is None,
        reason="JARVIS_TEST_DATABASE_URL is not configured",
    ),
]


async def _wait_for_query(engine: AsyncEngine, pid: int) -> None:
    async with asyncio.timeout(5):
        while True:
            async with engine.connect() as connection:
                blocked = await connection.scalar(
                    text(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity "
                        "WHERE pid = :pid"
                    ),
                    {"pid": pid},
                )
            if blocked:
                return
            await asyncio.sleep(0.01)


async def test_host_shutdown_finishes_inflight_owner_query_before_unlock(
    tmp_path: Path,
) -> None:
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    admin = create_engine(os.environ["JARVIS_TEST_MIGRATION_DATABASE_URL"])
    stopped = asyncio.Event()

    class Service(JarvisService):
        def request_shutdown(self) -> None:
            super().request_shutdown()
            stopped.set()

    try:
        async with deployment_ownership(engine) as database:
            async with database.connect() as owner:
                pid = await owner.scalar(text("SELECT pg_backend_pid()"))
            paused_path = tmp_path / "paused.json"
            PausedState.initialize(paused_path)
            paused = PausedState(paused_path)
            await paused.set_paused(True)
            service = Service(
                settings=service_settings(tmp_path),
                store=MessageStore(database),
                paused=paused,
                delivery=cast(Any, None),
                runner=cast(Any, None),
            )
            gateway = LocalGateway(service, service_settings(tmp_path))
            service.bind_gateway(gateway)
            async with admin.connect() as blocker:
                await blocker.execute(
                    text("LOCK TABLE message IN ACCESS EXCLUSIVE MODE")
                )
                service.request_work()
                host = asyncio.create_task(
                    run_service(service, gateway, "synthetic", asyncio.Event())
                )
                try:
                    await _wait_for_query(admin, pid)
                    host.cancel()  # Same cancellation as the Runner's first SIGINT.
                    await asyncio.wait_for(stopped.wait(), 1)
                    await asyncio.sleep(0.02)
                    assert not host.done(), "host abandoned an admitted database query"
                    assert not gateway.closed.is_set(), (
                        "dependencies closed before drain"
                    )
                finally:
                    await blocker.rollback()
                    with pytest.raises(asyncio.CancelledError):
                        await host
            assert not owner.invalidated
            assert gateway.closed.is_set()
        async with deployment_ownership(engine):
            pass  # A successor can acquire the released lock.
    finally:
        await admin.dispose()
        await engine.dispose()


@pytest.mark.parametrize("phase", ["startup", "worker"])
def test_real_sigint_exits_130_without_losing_database_ownership(
    tmp_path: Path, phase: str
) -> None:
    result = subprocess.run(
        [sys.executable, __file__, str(tmp_path), phase],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Jarvis stopped by operator signal" in result.stderr
    assert "DeploymentOwnershipDefect" not in result.stderr


async def _sigint_owned_fixture(
    tmp_path: Path, phase: str, shutdown: asyncio.Event
) -> None:
    """Real owner/store and host lifecycle; replace only live startup composition."""
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    admin = create_engine(os.environ["JARVIS_TEST_MIGRATION_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            async with database.connect() as owner:
                pid = await owner.scalar(text("SELECT pg_backend_pid()"))
            paused_path = tmp_path / "paused.json"
            PausedState.initialize(paused_path)
            paused = PausedState(paused_path)
            await paused.set_paused(True)
            store = MessageStore(database)
            service = JarvisService(
                settings=service_settings(tmp_path),
                store=store,
                paused=paused,
                delivery=cast(Any, None),
                runner=cast(Any, None),
            )
            gateway = LocalGateway(service, service_settings(tmp_path))
            async with admin.connect() as blocker:
                await blocker.execute(
                    text("LOCK TABLE message IN ACCESS EXCLUSIVE MODE")
                )

                async def interrupt() -> None:
                    await _wait_for_query(admin, pid)
                    signal.raise_signal(signal.SIGINT)  # This isolated child only.
                    await asyncio.wait_for(shutdown.wait(), 2)
                    if phase == "worker":
                        await asyncio.wait_for(gateway.stopped.wait(), 2)
                    await blocker.rollback()

                controller = asyncio.create_task(interrupt())
                try:
                    if phase == "startup":
                        await store.pending_delivery(
                            source_conversation_id="33", limit=1
                        )
                    else:
                        service.request_work()
                        await run_service(service, gateway, "synthetic", shutdown)
                finally:
                    await controller
                    await blocker.rollback()
                assert not owner.invalidated
        async with deployment_ownership(engine):
            pass
    finally:
        await admin.dispose()
        await engine.dispose()


if __name__ == "__main__":
    probe_path = Path(sys.argv[1])
    probe_phase = sys.argv[2]

    async def owned_fixture(
        settings: object, host: object, shutdown: asyncio.Event
    ) -> None:
        await _sigint_owned_fixture(probe_path, probe_phase, shutdown)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, "_serve", owned_fixture)
        patch.setattr(cli.Settings, "from_env", lambda: service_settings(probe_path))
        patch.setattr(
            cli.Settings,
            "codex_host_config",
            property(lambda _: host_config(probe_path)),
        )
        assert cli.main(("serve",)) == 130

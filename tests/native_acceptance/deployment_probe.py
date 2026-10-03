"""Actual PostgreSQL/local CLI and controlled SSH script surface; no deployment."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select

from jarvis import cli
from jarvis.db import create_engine, message
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership


async def main():
    with tempfile.TemporaryDirectory(prefix="jarvis-deploy-proof-") as temporary:
        directory = Path(temporary)
        peer = directory / "ssh"
        receipt = directory / "ssh.json"
        peer.write_text(
            "#!/usr/bin/env python3\n"
            "import json,os,sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['JARVIS_PROOF_SSH_RECEIPT']).write_text("
            "json.dumps({'arguments':sys.argv[1:],'body':sys.stdin.read()}))\n"
        )
        peer.chmod(0o700)
        environment = os.environ | {
            "PATH": str(directory) + os.pathsep + os.environ["PATH"],
            "JARVIS_DEPLOY_TARGET": "controlled-peer",
            "JARVIS_PROOF_SSH_RECEIPT": str(receipt),
        }
        captured = await asyncio.create_subprocess_exec(
            "bash", "deploy/activate-release", "a" * 40, env=environment
        )
        assert await captured.wait() == 0
        wire = json.loads(receipt.read_text())
        assert wire["arguments"][0] == "controlled-peer"
        body = wire["body"]
        assert "paused.json" not in body and "admission.json" not in body
        assert body.index("alembic") < body.index("cutover-native")
        assert body.index("cutover-native") < body.index("check-activation")
        assert body.index("check-activation") < body.index("systemctl enable --now")
        install_client = Path("deploy/install-agent-client").read_text()
        assert "paused.json" not in install_client and "check-paused" in install_client
        print(
            "canonical pause and migration/cutover/check/start SSH surface: "
            "GREEN (controlled peer)"
        )

        scope = str(9_000_000_000_000 + int(uuid4().hex[:9], 16))
        settings = SimpleNamespace(
            database_url=SecretStr(os.environ["JARVIS_PROOF_DATABASE_URL"]),
            runtime_state_directory=directory / "state",
            discord=SimpleNamespace(channel_id=int(scope)),
            codex_host_config=SimpleNamespace(
                cognition_cwd_parent=str(directory), client_group="controlled-peer"
            ),
        )
        engine = create_engine(settings.database_url.get_secret_value())
        try:

            async def control(text):
                async with deployment_ownership(engine) as database:
                    await MessageStore(database).insert_waking(
                        role="owner",
                        text=text,
                        source="proof",
                        source_conversation_id=scope,
                        source_message_id=str(uuid4()),
                        created_at=datetime.now(UTC),
                        control_kind=text,
                    )

            with (
                patch.object(cli.Settings, "from_env", return_value=settings),
                patch.object(cli, "_shared_cognition_directory"),
            ):
                assert await asyncio.to_thread(cli.main, ["initialize-state"]) == 0
                assert await asyncio.to_thread(cli.main, ["initialize-state"]) == 1
            async with deployment_ownership(engine) as database:
                assert await MessageStore(database).paused(scope)
                async with database.connect() as connection:
                    rows = (
                        await connection.execute(
                            select(message.c.role, message.c.control_kind).where(
                                message.c.source_conversation_id == scope
                            )
                        )
                    ).all()
                    assert rows == [("owner", "pause")]
            failure_scope = str(int(scope) + 1)
            failed_path = directory / "not-a-directory"
            failed_path.write_text("controlled filesystem failure")
            failed_settings = SimpleNamespace(
                **vars(settings)
                | {
                    "runtime_state_directory": failed_path,
                    "discord": SimpleNamespace(channel_id=int(failure_scope)),
                }
            )
            with (
                patch.object(cli.Settings, "from_env", return_value=failed_settings),
                patch.object(cli, "_shared_cognition_directory"),
            ):
                assert await asyncio.to_thread(cli.main, ["initialize-state"]) == 1
            owned_settings = SimpleNamespace(
                **vars(settings)
                | {
                    "runtime_state_directory": directory / "owned-state",
                    "discord": SimpleNamespace(channel_id=int(failure_scope)),
                }
            )
            async with deployment_ownership(engine) as database:
                with (
                    patch.object(cli.Settings, "from_env", return_value=owned_settings),
                    patch.object(cli, "_shared_cognition_directory"),
                ):
                    assert await asyncio.to_thread(cli.main, ["initialize-state"]) == 1
                async with database.connect() as connection:
                    assert (
                        await connection.scalar(
                            select(message.c.id).where(
                                message.c.source_conversation_id == failure_scope
                            )
                        )
                        is None
                    )
            assert settings.runtime_state_directory.stat().st_mode & 0o777 == 0o700
            with patch.object(cli.Settings, "from_env", return_value=settings):
                assert await asyncio.to_thread(cli.main, ["check-paused"]) == 0
            await control("resume")
            with (
                patch.object(cli.Settings, "from_env", return_value=settings),
                patch.object(cli, "_shared_cognition_directory"),
            ):
                assert await asyncio.to_thread(cli.main, ["initialize-state"]) == 1
            with patch.object(cli.Settings, "from_env", return_value=settings):
                assert await asyncio.to_thread(cli.main, ["check-paused"]) == 1

            async def no_model(*args, **kwargs):
                raise AssertionError(
                    "activation entered provider composition before pause gate"
                )

            with patch.object(cli, "_compose_main", no_model):
                try:
                    await cli.check_activation(settings, None)
                except cli.StartupDefect:
                    pass
                else:
                    raise AssertionError("activation accepted canonical resume")
            await control("pause")
            (settings.runtime_state_directory / "paused.json").write_text(
                '{"paused":true,"schema_version":"jarvis-paused.v1"}'
            )
            with patch.object(cli.Settings, "from_env", return_value=settings):
                assert await asyncio.to_thread(cli.main, ["check-paused"]) == 1
            print(
                "actual local CLI/PostgreSQL fresh pause, repeat/reset refusal "
                "and no-legacy gate: GREEN"
            )
        finally:
            await engine.dispose()


asyncio.run(main())

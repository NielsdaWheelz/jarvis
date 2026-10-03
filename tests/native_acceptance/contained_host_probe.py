"""Temporary real-socket proof of qualification before publication."""

from __future__ import annotations

import asyncio
import grp
import importlib.machinery
import importlib.util
import json
import os
import pwd
import stat
import tempfile
from pathlib import Path

from provider_runtime.agent_runtime import CODEX_CONTAINMENT_CATALOG_FILENAME
from websockets.asyncio.server import ServerConnection, unix_serve

from jarvis.codex_config import CodexHostConfig


async def probe(version: str, *, accepted: bool) -> None:
    loader = importlib.machinery.SourceFileLoader(
        "contained_host", str(Path(__file__).parents[2] / "deploy/codex-host")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    host = importlib.util.module_from_spec(spec)
    loader.exec_module(host)
    with tempfile.TemporaryDirectory(
        prefix="jarvis-contained-publish-", dir="/tmp"
    ) as directory:
        root = Path(directory)
        os.chown(root, -1, os.getegid())
        root.chmod(0o700)
        release = Path(__file__).parents[2].resolve()
        executable = str(release / ".venv/bin/python")
        evidence = {
            "type": "a(sasbttttuii)",
            "data": [
                [executable, [executable, str(release / "deploy/codex-host"), "start"]]
            ],
        }
        busctl = root / "busctl"
        busctl.write_text("#!/bin/sh\nprintf '%s\\n' '" + json.dumps(evidence) + "'\n")
        busctl.chmod(0o700)
        original_path = os.environ["PATH"]
        os.environ["PATH"] = str(root) + ":" + original_path
        try:
            host.verify_release()
            evidence["data"][0][0] = "/opt/jarvis/releases/other/.venv/bin/python"
            busctl.write_text(
                "#!/bin/sh\nprintf '%s\\n' '" + json.dumps(evidence) + "'\n"
            )
            try:
                host.verify_release()
            except RuntimeError:
                pass
            else:
                raise AssertionError("another host release was accepted")
        finally:
            os.environ["PATH"] = original_path
        physical = root / "native-proof.sock"
        alias = root / "app-server.sock"
        alias.symlink_to(physical)
        user = pwd.getpwuid(os.geteuid()).pw_name
        config = CodexHostConfig.model_validate(
            {
                "schema_version": 4,
                "development_user": user,
                "jarvis_user": user,
                "client_group": grp.getgrgid(os.getegid()).gr_name,
                "binary": "/usr/bin/true",
                "cognition_cwd_parent": str(root / "cwds"),
                "profiles": {
                    "personal": {
                        "account_home": str(root / "account"),
                        "endpoint": f"unix://{alias}",
                    }
                },
            }
        )

        async def peer(connection: ServerConnection) -> None:
            async for encoded in connection:
                request = json.loads(encoded)
                if "id" not in request:
                    continue
                if request["method"] == "initialize":
                    result = {"userAgent": f"codex/{version} native-proof"}
                else:
                    assert request["method"] == "config/read"
                    result = {
                        "config": {
                            "model_catalog_json": str(
                                root / CODEX_CONTAINMENT_CATALOG_FILENAME
                            )
                        },
                        "origins": {
                            "model_catalog_json": {"name": {"type": "sessionFlags"}}
                        },
                    }
                await connection.send(
                    json.dumps({"id": request["id"], "result": result})
                )

        async with unix_serve(peer, path=str(physical)):
            physical.chmod(0o600)
            try:
                await host.publish(config)
            except Exception:
                if accepted:
                    raise
            else:
                assert accepted, "unsupported native binary was exposed to the app"
            if accepted:
                assert os.readlink(alias) == physical.name
                assert stat.S_IMODE(root.stat().st_mode) == 0o710
                assert stat.S_IMODE(physical.stat().st_mode) == 0o660
                await host.verify(config)
                host.remove_alias(config)
                assert not alias.is_symlink() and physical.is_socket()
            else:
                assert os.readlink(alias) == str(physical)
                assert stat.S_IMODE(root.stat().st_mode) == 0o700
                assert stat.S_IMODE(physical.stat().st_mode) == 0o600


async def main() -> None:
    await probe("0.160.0", accepted=True)
    await probe("0.159.0", accepted=False)
    print("contained host controlled peer: qualified publication and refusal GREEN")


if __name__ == "__main__":
    asyncio.run(main())

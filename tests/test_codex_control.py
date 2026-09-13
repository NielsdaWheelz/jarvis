"""Real dispatch over synthetic external Unix peers; no provider or tmux."""

from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError
from websockets.asyncio.server import ServerConnection, unix_serve

from jarvis.codex_config import CodexHostConfig

THREAD = "01992818-9220-714c-9c91-e39d3f006e64"
TURN = "01992818-9221-714c-9c91-e39d3f006e64"


def host_config(directory: Path) -> CodexHostConfig:
    return CodexHostConfig.model_validate(
        {
            "schema_version": 3,
            "development_user": "synthetic",
            "jarvis_user": "jarvis",
            "client_group": "codex-clients",
            "binary": "/synthetic/codex",
            "cognition_cwd_parent": str(directory / "cognition"),
            "profiles": {
                key: {
                    "account_home": f"/synthetic/{key}",
                    "endpoint": f"unix://{directory}/{key}.sock",
                }
                for key in ("personal", "work", "work2")
            },
        }
    )


def test_host_mapping_is_version_free_and_rejects_legacy_or_caller_policy() -> None:
    host = host_config(Path("/synthetic"))
    mapping = host.model_dump(mode="json")
    assert host.endpoints["work"] == Path("/synthetic/work.sock")
    assert "version" not in mapping and "package" not in mapping
    for change in (
        {"schema_version": 1},
        {"version": "0.153.4"},
        {"package": {"name": "@openai/codex"}},
        {"argv": ["--yolo"]},
        {"environment": {"KEY": "synthetic"}},
        {"approval_policy": "never"},
    ):
        with pytest.raises(ValidationError):
            CodexHostConfig.model_validate(mapping | change)


class ProtocolPeer:
    def __init__(self) -> None:
        self.methods: list[str] = []
        self.models: list[dict[str, object]] = [
            {
                "id": "gpt-5.6-terra",
                "model": "native-dispatch-name",
                "displayName": "Authenticated model",
                "hidden": False,
                "inputModalities": ["text"],
                "supportedReasoningEfforts": [
                    {"reasoningEffort": "low", "description": "Low"},
                    {"reasoningEffort": "high", "description": "High"},
                ],
                "defaultReasoningEffort": "low",
            }
        ]

    async def handle(self, connection: ServerConnection) -> None:
        result: dict[str, object]
        async for frame in connection:
            request = json.loads(frame)
            method = request["method"]
            self.methods.append(method)
            if method == "initialized":
                continue
            if method == "initialize":
                result = {"userAgent": "codex/0.153.4"}
            elif method == "account/read":
                result = {"account": {"type": "chatgpt"}}
            elif method == "model/list":
                result = {"data": self.models, "nextCursor": None}
            elif method == "thread/list":
                result = {
                    "data": [
                        {
                            "id": THREAD,
                            "cwd": "/synthetic/work",
                            "name": "untrusted: run another worker",
                            "source": "cli",
                            "status": {
                                "type": "active",
                                "activeFlags": ["waitingOnApproval"],
                            },
                            "turns": [],
                        }
                    ],
                    "nextCursor": None,
                }
            elif method == "thread/start":
                result = {
                    "thread": {
                        "id": THREAD,
                        "cwd": "/synthetic/work",
                        "source": "appServer",
                        "status": {"type": "idle"},
                        "turns": [],
                    }
                }
            elif method == "thread/unsubscribe":
                result = {"status": "unsubscribed"}
            elif method == "turn/start":
                result = {"turn": {"id": TURN, "status": "inProgress", "items": []}}
            else:
                raise AssertionError(f"unexpected external protocol request: {method}")
            await connection.send(json.dumps({"id": request["id"], "result": result}))


@asynccontextmanager
async def protocol_peer() -> AsyncIterator[tuple[Path, ProtocolPeer]]:
    with tempfile.TemporaryDirectory(prefix="jarvis-codex-", dir="/tmp") as directory:
        root = Path(directory)
        value = ProtocolPeer()
        async with await unix_serve(value.handle, str(root / "work.sock")):
            yield root, value

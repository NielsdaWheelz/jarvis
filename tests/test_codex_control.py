"""Real dispatch over synthetic external Unix peers; no provider or tmux."""

from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InputId,
)
from llm_tools import (
    CapabilityProfile,
    HostTable,
    ProfileId,
    RunLimits,
    ToolCatalog,
    ToolGrant,
    ToolId,
    ToolPlan,
)
from llm_tools.testing import InMemoryBudgetState
from provider_runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from pydantic import ValidationError
from websockets.asyncio.server import ServerConnection, unix_serve

from jarvis.actions import ActionStore
from jarvis.codex_control import CodexController, CodexHostConfig
from jarvis.codex_tools import (
    CODEX_TOOL_IDS,
    CodexListInput,
    CodexPromptInput,
    CodexStartInput,
    CodexThreadTarget,
    codex_family,
)
from jarvis.db import create_engine
from jarvis.read_dispatch import ReadToolDispatcher

THREAD = "01992818-9220-714c-9c91-e39d3f006e64"
TURN = "01992818-9221-714c-9c91-e39d3f006e64"


def host_config(directory: Path) -> CodexHostConfig:
    return CodexHostConfig.model_validate(
        {
            "schema_version": 1,
            "version": "0.153.4",
            "package": {
                "name": "@openai/codex",
                "integrity": "sha512-" + "a" * 86 + "==",
                "shasum": "a" * 40,
            },
            "development_user": "synthetic",
            "jarvis_user": "jarvis",
            "client_group": "codex-clients",
            "binary": "/synthetic/codex",
            "tmux": "/synthetic/tmux",
            "cognition_cwd_parent": str(directory / "cognition"),
            "launcher_socket": str(directory / "helper.sock"),
            "profiles": {
                key: {
                    "account_home": f"/synthetic/{key}",
                    "endpoint": f"unix://{directory}/{key}.sock",
                    "work_roots": [str(directory)],
                }
                for key in ("personal", "work", "work2")
            },
        }
    )


class ProtocolPeer:
    def __init__(self) -> None:
        self.methods: list[str] = []

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


@pytest.fixture
async def peer() -> AsyncIterator[tuple[Path, ProtocolPeer]]:
    async with protocol_peer() as value:
        yield value


@pytest.mark.parametrize(
    "handle", ["last", "latest", "abc", THREAD.upper(), "12345678"]
)
def test_control_handles_reject_aliases_and_ambiguous_spelling(handle: str) -> None:
    with pytest.raises(ValidationError):
        CodexThreadTarget(profile="work", thread_handle=handle)


def test_control_input_is_closed_bounded_and_has_no_shell_or_model_options() -> None:
    valid = {
        "profile": "work",
        "cwd": "/synthetic/work",
        "name": "review",
        "prompt": "synthetic",
    }
    variants: tuple[dict[str, object], ...] = (
        {"env": {}},
        {"model": "other"},
        {"socket": "/tmp/other"},
        {"profile": "alias"},
        {"prompt": "界" * 11000},
        {"cwd": "/synthetic/../other"},
        {"name": "-option"},
    )
    for extra in variants:
        with pytest.raises(ValidationError):
            CodexStartInput.model_validate({**valid, **extra})
    with pytest.raises(ValidationError):
        CodexPromptInput.model_validate(
            {
                "thread": {"profile": "work", "thread_handle": THREAD},
                "input": {"type": "NewTurn", "text": "synthetic"},
            }
        )


def test_profile_mapping_change_invalidates_frozen_control_policy() -> None:
    from provider_runtime.agent_runtime.codex_control import CodexControl

    engine = create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
    control = CodexControl({}, lambda _: False)
    first = CodexController(
        control=control,
        host=host_config(Path("/synthetic/first")),
        actions=ActionStore(engine),
    )
    second = CodexController(
        control=control,
        host=host_config(Path("/synthetic/second")),
        actions=ActionStore(engine),
    )
    left = ToolCatalog.compose((codex_family(first),))
    right = ToolCatalog.compose((codex_family(second),))
    assert (
        left.binding(ToolId("codex.start")).policy_revision
        != right.binding(ToolId("codex.start")).policy_revision
    )


async def test_real_read_dispatch_exposes_native_inventory_without_creating_action(
    tmp_path: Path, peer: tuple[Path, ProtocolPeer]
) -> None:
    root, external = peer
    engine = create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
    try:
        async with AgentRuntime(
            AgentRuntimeConfig(
                state_root_base=tmp_path, codex_endpoints={"work": root / "work.sock"}
            )
        ) as runtime:
            controller = CodexController(
                control=runtime.codex,
                host=host_config(root),
                actions=ActionStore(engine),
            )
            catalog = ToolCatalog.compose((codex_family(controller),))
            assert tuple(catalog.tool_ids) == CODEX_TOOL_IDS
            profile = CapabilityProfile(
                ProfileId("synthetic-codex"),
                (ToolGrant(ToolId("codex.list"), None),),
                RunLimits(1, 1, 8192, 65536, 1, 30.0),
            ).freeze(catalog)
            plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
            dispatcher = ReadToolDispatcher(host_secrets=())
            result = await dispatcher.dispatch(
                binding=catalog.binding(ToolId("codex.list")),
                validated_input=CodexListInput(profile="work"),
                plan=plan,
                budgets=InMemoryBudgetState(profile.run_limits),
                cancellation=CancellationToken(),
                lineage=DispatchLineage(
                    ClaimId("synthetic-claim"),
                    Checkpoint("synthetic-checkpoint"),
                    (InputId("synthetic-input"),),
                    1,
                ),
            )
            assert result.result["type"] == "Success"
            assert THREAD in json.dumps(result.result)
            assert "waitingOnApproval" in json.dumps(result.result)
            assert dispatcher.recorder.terminal_count == 1
            assert external.methods.count("thread/list") == 1
            assert "thread/start" not in external.methods
    finally:
        await engine.dispose()

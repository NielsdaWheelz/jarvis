"""Qualification safety and real stored uncertainty; no provider or tmux."""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from uuid import uuid4

import pytest

QUALIFIER = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/qualify_codex_control.py")
)
SOCKET = "jarvis-codex-qualify-" + "a" * 32
NAME = "jarvis-qualify-" + "a" * 32 + "-personal"


def test_isolated_runner_refuses_default_or_reused_nonspecific_socket_names() -> None:
    for name in ("", "default", "production", "jarvis-codex-qualify", "../socket"):
        with pytest.raises(ValueError, match="isolated"):
            QUALIFIER["isolated_runner_source"](Path("/usr/bin/tmux"), name)


def test_opt_in_requires_all_three_boundaries_before_preparation_or_imports(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "provider_runtime", None)
    for args in (
        [],
        ["--allow-provider-calls"],
        ["--allow-provider-calls", "--allow-isolated-tmux-mutation"],
    ):
        assert QUALIFIER["main"](args) == 2
        assert json.loads(capsys.readouterr().out) == {
            "status": "NOT_RUN",
            "reason": "explicit_opt_in_required",
        }


def test_preparation_rejects_wrong_runner_or_non_disposable_database() -> None:
    tmux = Path("/usr/bin/tmux")
    runner = QUALIFIER["isolated_runner_source"](tmux, SOCKET)
    database = "postgresql+psycopg://user:synthetic@127.0.0.1/jarvis_codex_qualify_test"
    QUALIFIER["validate_preparation"](
        runner=runner,
        tmux=tmux,
        socket_name=SOCKET,
        launcher_socket=Path("/run") / SOCKET / "launcher.sock",
        database_url=database,
    )
    for changed_runner, changed_database in (
        (b'#!/bin/sh\nexec /usr/bin/tmux "$@"\n', database),
        (runner, database.replace("jarvis_codex_qualify_test", "jarvis")),
        (runner, database.replace("127.0.0.1", "production.invalid")),
    ):
        with pytest.raises(ValueError):
            QUALIFIER["validate_preparation"](
                runner=changed_runner,
                tmux=tmux,
                socket_name=SOCKET,
                launcher_socket=Path("/run") / SOCKET / "launcher.sock",
                database_url=changed_database,
            )
    with pytest.raises(ValueError, match="launcher socket"):
        QUALIFIER["validate_preparation"](
            runner=runner,
            tmux=tmux,
            socket_name=SOCKET,
            launcher_socket=Path("/run/codex-shared/launcher.sock"),
            database_url=database,
        )


def test_gateway_configuration_rejects_nonfixture_routes_and_bad_identity() -> None:
    valid = {
        "url": "http://127.0.0.1:17341",
        "machine_handle": "mh-" + "b" * 32,
        "bearer": "A" * 43,
    }
    QUALIFIER["Gateway"](json.dumps(valid).encode())
    for change in (
        {"url": "http://127.0.0.1:7341"},
        {"url": "https://production.invalid:17341"},
        {"url": "http://localhost:17341"},
        {"url": "http://127.0.0.1:17341/path"},
        {"url": "http://user@127.0.0.1:17341"},
        {"machine_handle": "default"},
        {"bearer": "not a bearer"},
        {"unexpected": True},
    ):
        with pytest.raises(ValueError):
            QUALIFIER["Gateway"](json.dumps(valid | change).encode())


async def test_invalid_terminal_identity_fails_before_external_execution() -> None:
    with pytest.raises(ValueError, match="exact test identity"):
        await QUALIFIER["observe_terminal"]("/absent", "last", NAME)


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("JARVIS_TEST_DATABASE_URL"),
    reason="requires the disposable PostgreSQL action boundary",
)
async def test_uncertain_write_projects_real_stored_evidence_without_reentry() -> None:
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
    from provider_runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
    from websockets.asyncio.server import ServerConnection, unix_serve

    from jarvis.actions import ActionStore
    from jarvis.admission import ExactToolBudgetFactory
    from jarvis.codex_control import CodexController, CodexHostConfig
    from jarvis.codex_tools import (
        CodexPromptInput,
        CodexSubmit,
        CodexThreadTarget,
        codex_family,
    )
    from jarvis.db import create_engine
    from jarvis.messages import MessageStore
    from jarvis.ownership import deployment_ownership

    submissions = 0

    async def native(connection: ServerConnection) -> None:
        nonlocal submissions
        async for frame in connection:
            request = json.loads(frame)
            method = request["method"]
            if method == "initialized":
                continue
            if method == "initialize":
                result = {"userAgent": "codex/0.153.4"}
            elif method == "account/read":
                result = {"account": {"type": "chatgpt"}}
            else:
                assert method == "turn/start"
                submissions += 1
                await connection.close()
                return
            await connection.send(json.dumps({"id": request["id"], "result": result}))

    origin = uuid4()
    channel = f"qualifier-uncertainty-{origin}"
    target = CodexThreadTarget(profile="work", thread_handle=str(uuid4()))
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    try:
        with tempfile.TemporaryDirectory(prefix="qualifier-", dir="/tmp") as temporary:
            root = Path(temporary)
            host = CodexHostConfig.model_validate(
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
                    "cognition_cwd_parent": str(root / "cognition"),
                    "launcher_socket": str(root / "unused-helper.sock"),
                    "profiles": {
                        profile: {
                            "account_home": f"/synthetic/{profile}",
                            "endpoint": f"unix://{root}/{profile}.sock",
                            "work_roots": [str(root)],
                        }
                        for profile in ("personal", "work", "work2")
                    },
                }
            )
            async with (
                await unix_serve(native, str(root / "work.sock")),
                deployment_ownership(engine) as database,
                AgentRuntime(
                    AgentRuntimeConfig(
                        state_root_base=root, codex_endpoints=host.endpoints
                    )
                ) as runtime,
            ):
                actions = ActionStore(database)
                controller = CodexController(
                    control=runtime.codex, host=host, actions=actions
                )
                catalog = ToolCatalog.compose((codex_family(controller),))
                profile = CapabilityProfile(
                    ProfileId("qualifier-proof"),
                    (ToolGrant(ToolId("codex.prompt"), None),),
                    RunLimits(2, 2, 1048576, 2097152, 1, 60.0),
                ).freeze(catalog)
                plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
                await MessageStore(database).insert_waking(
                    role="owner",
                    text="Synthetic worker request.",
                    source="discord",
                    source_conversation_id=channel,
                    source_message_id=str(origin),
                    created_at=datetime.now(UTC),
                    message_id=origin,
                )
                result = await QUALIFIER["_write"](
                    actions=actions,
                    plan=plan,
                    budgets=ExactToolBudgetFactory().create(plan),
                    origin=origin,
                    ordinal=1,
                    tool=ToolId("codex.prompt"),
                    value=CodexPromptInput(
                        thread=target, input=CodexSubmit(text="Synthetic.")
                    ),
                    expect_uncertain=True,
                )
                assert result == {
                    "type": "Unknown",
                    "stage": "submit",
                    "prefix": {"type": "thread", "thread": target.model_dump()},
                }
                (stored,) = await actions.unreported_terminal(
                    source_conversation_id=channel
                )
                assert stored.status == "uncertain" and stored.attempts == 1
                assert stored.result is not None
                assert stored.result["type"] == "codex_uncertainty_v1"
                assert submissions == 1
    finally:
        await engine.dispose()

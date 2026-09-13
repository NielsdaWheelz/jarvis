"""Hermetic checks at the installed CLI process boundary."""

import asyncio
import json
import os
from pathlib import Path
from typing import cast

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
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    HostTable,
    ProfileId,
    RunLimits,
    ToolCatalog,
    ToolGrant,
    ToolId,
    ToolPlan,
)
from llm_tools.testing import InMemoryBudgetState
from provider_fixture import decision_key

from jarvis.actions import ActionStore
from jarvis.agent_control import AgentController, AgentOutcomeUnknown
from jarvis.agent_tools import (
    AgentListInput,
    AgentReadInput,
    AgentSendInput,
    AgentTarget,
    agent_family,
)
from jarvis.db import create_engine
from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder

TARGET = dict(
    machine="devbox",
    tmuxId="$1",
    identityToken="fixture",
    paneId="%1",
    pid=42,
    startIdentity="start",
)


def cli(tmp_path: Path, response: dict[str, object]) -> tuple[Path, Path]:
    executable = tmp_path / "skid"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\nfrom pathlib import Path\n"
        "p=Path(sys.argv[2])\nrequest=json.load(sys.stdin)\n"
        "verb=sys.argv[-1]\n"
        "allowed={'list':{'machine'},'start':{'machine','profile','cwd','name'},"
        "'read':{'target','mode','maxBytes'},'send':{'target','text','mode'},"
        "'keys':{'target','keys'},'interrupt':{'target'},'stop':{'target'}}\n"
        "assert set(request) <= allowed[verb]\n"
        "assert all(value is not None for value in request.values())\n"
        "with p.with_suffix('.calls').open('a') as calls: calls.write('1\\n')\n"
        "p.with_suffix('.receipt').write_text("
        "json.dumps({'argv':sys.argv[1:],'input':request}))\n"
        "sys.stdout.write(p.read_text())\n"
        "sys.exit(0 if json.loads(p.read_text()).get('ok') is True else 1)\n"
    )
    executable.chmod(0o700)
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps(response))
    return executable, config


@pytest.mark.asyncio
async def test_real_process_preserves_target_and_multiline_text(tmp_path: Path) -> None:
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"method": "terminal", "outcome": "written"}}
    )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    result = await controller.send(
        AgentSendInput(
            target=AgentTarget.model_validate(TARGET), text="first\nsecond $(literal)"
        ),
        cast(ExecutionContext, None),
    )
    assert isinstance(result, HandlerSuccess)
    receipt = json.loads(config.with_suffix(".receipt").read_text())
    assert receipt == {
        "argv": ["--client-config", str(config), "agent", "send"],
        "input": {"target": TARGET, "mode": "auto", "text": "first\nsecond $(literal)"},
    }


@pytest.mark.asyncio
async def test_read_coverage_and_list_inventory(tmp_path: Path) -> None:
    value = {
        "text": "earlier than the viewport",
        "source": "native",
        "scope": "recent_messages",
        "truncated": True,
    }
    executable, config = cli(tmp_path, {"ok": True, "result": value})
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    result = await controller.read(
        AgentReadInput(target=AgentTarget.model_validate(TARGET)),
        cast(ExecutionContext, None),
    )
    assert isinstance(result, HandlerSuccess)
    assert result.value.model_dump() == value
    config.write_text(json.dumps({"ok": True, "result": {"peers": []}}))
    assert isinstance(
        await controller.list(AgentListInput(), cast(ExecutionContext, None)),
        HandlerSuccess,
    )


def test_catalog_is_exactly_common_seven_verbs(tmp_path: Path) -> None:
    executable, config = cli(tmp_path, {"ok": True, "result": {"peers": []}})
    family = agent_family(
        AgentController(
            executable=executable,
            client_config=config,
            actions=ActionStore(
                create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
            ),
        )
    )
    assert {binding.spec.id for binding in family.bindings} == {
        ToolId("agent." + verb)
        for verb in ("list", "read", "start", "send", "keys", "interrupt", "stop")
    }


@pytest.mark.asyncio
async def test_inventory_projects_complete_target_and_partial_peer_failure(
    tmp_path: Path,
) -> None:
    agent = {
        "provider": "Claude",
        "pid": 42,
        "paneId": "%1",
        "startIdentity": "start",
        "profile": "claude-work",
        "status": {"state": "blocked", "source": "terminal", "reason": "dialog"},
        "methods": {"read": "native", "send": "terminal", "interrupt": "terminal"},
    }
    inventory = {
        "observedAt": "2026-09-12T00:00:00Z",
        "profiles": [{"key": "claude-work", "label": "Work", "provider": "Claude"}],
        "sessions": [
            {
                "tmuxId": "$1",
                "tmuxName": "coordinator",
                "identityToken": "fixture",
                "cwd": "/synthetic",
                "agent": agent,
                "attachedClients": 2,
                "character": {"key": "inert"},
            }
        ],
    }
    executable, config = cli(
        tmp_path,
        {
            "ok": True,
            "result": {
                "peers": [
                    {
                        "label": "work",
                        "machine": "devbox",
                        "ok": True,
                        "result": inventory,
                    },
                    {
                        "label": "offline",
                        "machine": "offline-machine",
                        "ok": False,
                        "error": {"code": "unavailable", "dispatch": "not_sent"},
                    },
                ]
            },
        },
    )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    result = (
        await controller.list(AgentListInput(), cast(ExecutionContext, None))
    ).value
    target = result.peers[0].sessions[0].target
    assert target is not None and target.model_dump() == TARGET
    assert result.peers[0].sessions[0].provider == "Claude"
    assert (
        result.peers[1].error is not None
        and result.peers[1].error.code == "unavailable"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatch", ["not_sent", "unknown"])
async def test_cli_error_never_replays_mutation(tmp_path: Path, dispatch: str) -> None:
    executable, config = cli(
        tmp_path, {"ok": False, "error": {"code": "unavailable", "dispatch": dispatch}}
    )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    with pytest.raises(
        AgentOutcomeUnknown if dispatch == "unknown" else DeclaredToolFailure
    ):
        await controller.send(
            AgentSendInput.model_validate({"target": TARGET, "text": "synthetic"}),
            cast(ExecutionContext, None),
        )
    assert config.with_suffix(".calls").read_text() == "1\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", ['{"ok":true,"result":NaN}', '{"ok":true,"ok":false}', "x" * 65537]
)
async def test_malformed_or_oversized_reply_after_dispatch_is_unknown(
    tmp_path: Path, payload: str
) -> None:
    executable, config = cli(tmp_path, {})
    config.write_text(payload)
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    with pytest.raises(AgentOutcomeUnknown):
        await controller.send(
            AgentSendInput.model_validate({"target": TARGET, "text": "synthetic"}),
            cast(ExecutionContext, None),
        )
    assert config.with_suffix(".calls").read_text() == "1\n"


@pytest.mark.asyncio
async def test_cancellation_joins_only_its_cli_child(tmp_path: Path) -> None:
    executable, config = cli(tmp_path, {})
    executable.write_text(
        "#!/usr/bin/env python3\nimport os,sys,time\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).with_suffix('.pid').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    pending = asyncio.create_task(
        controller.list(AgentListInput(), cast(ExecutionContext, None))
    )
    async with asyncio.timeout(2):
        while not config.with_suffix(".pid").exists():  # noqa: ASYNC110 - process boundary
            await asyncio.sleep(0.01)
    pid = int(config.with_suffix(".pid").read_text())
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize(
    ("verb", "payload", "fields"),
    [
        ("list", {}, set[str]()),
        (
            "start",
            {"machine": "devbox", "profile": "codex-work", "cwd": "/synthetic"},
            {"machine", "profile", "cwd"},
        ),
        (
            "read",
            {"target": TARGET, "mode": "terminal"},
            {"target", "mode", "maxBytes"},
        ),
        ("send", {"target": TARGET, "text": "synthetic"}, {"target", "mode", "text"}),
        ("keys", {"target": TARGET, "keys": ["enter"]}, {"target", "keys"}),
        ("interrupt", {"target": TARGET}, {"target"}),
        ("stop", {"target": TARGET}, {"target"}),
    ],
)
async def test_each_tool_emits_cli_operation_specific_schema(
    tmp_path: Path, verb: str, payload: dict[str, object], fields: set[str]
) -> None:
    executable, config = cli(
        tmp_path,
        {"ok": False, "error": {"code": "machine_unknown", "dispatch": "not_sent"}},
    )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    binding = next(
        binding
        for binding in agent_family(controller).bindings
        if str(binding.spec.id) == "agent." + verb
    )
    value = binding.spec.input_type.model_validate(payload)
    with pytest.raises(DeclaredToolFailure):
        await getattr(controller, verb)(value, cast(ExecutionContext, None))
    emitted = json.loads(config.with_suffix(".receipt").read_text())["input"]
    assert set(emitted) == fields
    assert not any(value is None for value in emitted.values())
    if verb == "read":
        assert emitted["mode"] == "terminal"


async def test_fleet_read_uses_existing_recorder_without_action(tmp_path: Path) -> None:
    executable, config = cli(tmp_path, {"ok": True, "result": {"peers": []}})
    engine = create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
    try:
        catalog = ToolCatalog.compose(
            (
                agent_family(
                    AgentController(
                        executable=executable,
                        client_config=config,
                        actions=ActionStore(engine),
                    )
                ),
            )
        )
        profile = CapabilityProfile(
            ProfileId("synthetic-agent"),
            (ToolGrant(ToolId("agent.list"), None),),
            RunLimits(1, 1, 65536, 1048576, 1, 15.0),
        ).freeze(catalog)
        plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
        dispatcher = ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=())
        result = await dispatcher.dispatch(
            binding=catalog.binding(ToolId("agent.list")),
            validated_input=AgentListInput(),
            plan=plan,
            budgets=InMemoryBudgetState(profile.run_limits),
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("synthetic-claim"),
                Checkpoint("synthetic-checkpoint"),
                (InputId("synthetic-input"),),
                1,
                definition_fingerprint="a" * 64,
                model_decision_id=decision_key("synthetic-claim", 1),
            ),
        )
        assert result.result["type"] == "Success"
        assert dispatcher.recorder.terminal_count == 1
        assert config.with_suffix(".calls").read_text() == "1\n"
    finally:
        await engine.dispose()


async def test_list_accepts_more_than_control_limit_and_rejects_over_one_mib(
    tmp_path: Path,
) -> None:
    sessions = [
        {
            "tmuxId": "$" + str(index),
            "tmuxName": "synthetic-session-" + str(index),
            "identityToken": "fixture",
            "cwd": "/synthetic/cwd",
        }
        for index in range(700)
    ]
    inventory = {
        "observedAt": "2026-09-12T00:00:00Z",
        "profiles": [],
        "sessions": sessions,
    }
    response: dict[str, object] = {
        "ok": True,
        "result": {
            "peers": [
                {"label": "work", "machine": "devbox", "ok": True, "result": inventory}
            ]
        },
    }
    assert 65536 < len(json.dumps(response).encode()) < 1048576
    executable, config = cli(tmp_path, response)
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    result = await controller.list(AgentListInput(), cast(ExecutionContext, None))
    assert len(result.value.peers[0].sessions) == 700
    config.write_text("x" * 1048577)
    with pytest.raises(DeclaredToolFailure):
        await controller.list(AgentListInput(), cast(ExecutionContext, None))

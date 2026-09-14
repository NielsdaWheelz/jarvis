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
    AgentRefInput,
    AgentSendInput,
    AgentStartInput,
    agent_family,
)
from jarvis.db import create_engine
from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder

REF = "opaque-original-reference"
INFO = {
    "label": "arch",
    "machine": "host-fixture",
    "observedAt": "2026-09-13T00:00:00Z",
    "session": {
        "name": "reviewer",
        "ref": REF,
        "cwd": "/synthetic",
        "attachedClients": 0,
    },
}


def cli(tmp_path: Path, response: dict[str, object]) -> tuple[Path, Path]:
    executable = tmp_path / "skid"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\nfrom pathlib import Path\n"
        "assert sys.argv[1] == '--config' and sys.argv[4] == '--json'\n"
        "p=Path(sys.argv[2]); verb=sys.argv[3]; body=sys.stdin.buffer.read()\n"
        "with p.with_suffix('.calls').open('a') as calls: calls.write(verb+'\\n')\n"
        "receipt=p.with_suffix('.info-receipt' if verb=='info' else '.receipt')\n"
        "receipt.write_text(json.dumps({'argv':sys.argv[1:],'input':body.decode()}))\n"
        "source=p.with_suffix('.info') if verb=='info' else p\n"
        "output=source.read_text(); sys.stdout.write(output)\n"
        "v=json.loads(output); r=v.get('result',{})\n"
        "partial=r.get('partial',False) or r.get('outcome')=='unknown' or "
        "r.get('agent')=='unconfirmed' or r.get('terminal')=='unconfirmed'\n"
        "sys.exit(0 if v.get('ok') is True and not partial else 1)\n"
    )
    executable.chmod(0o700)
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps(response))
    config.with_suffix(".info").write_text(json.dumps({"ok": True, "result": INFO}))
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
        AgentSendInput(ref=REF, text="first\nsecond $(literal)"),
        cast(ExecutionContext, None),
    )
    assert isinstance(result, HandlerSuccess)
    receipt = json.loads(config.with_suffix(".receipt").read_text())
    assert receipt == {
        "argv": ["--config", str(config), "send", "--json", "--ref", REF, "--stdin"],
        "input": "first\nsecond $(literal)",
    }


@pytest.mark.asyncio
async def test_start_values_are_literal_arguments(tmp_path: Path) -> None:
    executable, config = cli(
        tmp_path,
        {"ok": False, "error": {"code": "invalid_name", "dispatch": "not_sent"}},
    )
    controller = AgentController(
        executable=executable,
        client_config=config,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    with pytest.raises(DeclaredToolFailure):
        await controller.start(
            AgentStartInput(
                name="reviewer", machine="--help", profile="--profile", cwd="--cwd"
            ),
            cast(ExecutionContext, None),
        )
    assert json.loads(config.with_suffix(".receipt").read_text()) == {
        "argv": [
            "--config",
            str(config),
            "start",
            "--json",
            "--machine",
            "--help",
            "--profile",
            "--profile",
            "--cwd",
            "--cwd",
            "--",
            "reviewer",
        ],
        "input": "",
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
        AgentReadInput(ref=REF),
        cast(ExecutionContext, None),
    )
    assert isinstance(result, HandlerSuccess)
    assert result.value.model_dump() == value
    config.write_text(
        json.dumps({"ok": True, "result": {"partial": False, "peers": []}})
    )
    assert isinstance(
        await controller.list(AgentListInput(), cast(ExecutionContext, None)),
        HandlerSuccess,
    )


def test_catalog_is_exactly_common_nine_verbs(tmp_path: Path) -> None:
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"partial": False, "peers": []}}
    )
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
        for verb in (
            "list",
            "info",
            "read",
            "start",
            "send",
            "keys",
            "interrupt",
            "stop",
            "kill",
        )
    }


@pytest.mark.asyncio
async def test_inventory_preserves_common_projection_and_partial_peer_failure(
    tmp_path: Path,
) -> None:
    value = {
        "partial": True,
        "peers": [
            {
                "label": "arch",
                "machine": "host-fixture",
                "ok": True,
                "observedAt": INFO["observedAt"],
                "profiles": [],
                "sessions": [INFO["session"]],
            },
            {
                "label": "offline",
                "machine": "offline-host",
                "ok": False,
                "error": {"code": "unavailable", "dispatch": "not_sent"},
            },
        ],
    }
    executable, config = cli(tmp_path, {"ok": True, "result": value})
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
    assert result.partial is True
    sessions = result.peers[0].sessions
    assert sessions is not None and sessions[0].ref == REF
    assert (
        result.peers[1].error is not None
        and result.peers[1].error.code == "unavailable"
    )
    metadata = (await controller.info(AgentRefInput(ref=REF))).value
    assert metadata.model_dump(exclude_none=True) == INFO


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
            AgentSendInput.model_validate({"ref": REF, "text": "synthetic"}),
            cast(ExecutionContext, None),
        )
    assert config.with_suffix(".calls").read_text() == "send\n"


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
            AgentSendInput.model_validate({"ref": REF, "text": "synthetic"}),
            cast(ExecutionContext, None),
        )
    assert config.with_suffix(".calls").read_text() == "send\n"


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
    ("verb", "payload", "arguments", "stdin"),
    [
        ("list", {}, [], ""),
        ("list", {"machine": "arch"}, ["--machine", "arch"], ""),
        (
            "start",
            {"machine": "arch", "profile": "work", "name": "worker"},
            ["--machine", "arch", "--profile", "work", "--cwd", "~", "--", "worker"],
            "",
        ),
        ("info", {"ref": REF}, ["--ref", REF], ""),
        (
            "read",
            {"ref": REF, "mode": "terminal"},
            ["--ref", REF, "--max-bytes", "16384", "--terminal"],
            "",
        ),
        (
            "send",
            {"ref": REF, "text": "first\nsecond\n"},
            ["--ref", REF, "--stdin"],
            "first\nsecond\n",
        ),
        (
            "keys",
            {"ref": REF, "keys": ["down", "enter"]},
            ["--ref", REF, "down", "enter"],
            "",
        ),
        ("interrupt", {"ref": REF}, ["--ref", REF], ""),
        ("stop", {"ref": REF}, ["--ref", REF], ""),
        ("kill", {"ref": REF}, ["--ref", REF], ""),
    ],
)
async def test_each_tool_uses_ordinary_cli_arguments(
    tmp_path: Path,
    verb: str,
    payload: dict[str, object],
    arguments: list[str],
    stdin: str,
) -> None:
    error: dict[str, object] = {
        "ok": False,
        "error": {"code": "machine_unknown", "dispatch": "not_sent"},
    }
    executable, config = cli(tmp_path, error)
    config.with_suffix(".info").write_text(json.dumps(error))
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
    receipt = json.loads(
        config.with_suffix(
            ".info-receipt" if verb == "info" else ".receipt"
        ).read_text()
    )
    assert receipt == {
        "argv": ["--config", str(config), verb, "--json", *arguments],
        "input": stdin,
    }


async def test_fleet_read_uses_existing_recorder_without_action(tmp_path: Path) -> None:
    executable, config = cli(
        tmp_path, {"ok": True, "result": {"partial": False, "peers": []}}
    )
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
        assert config.with_suffix(".calls").read_text() == "list\n"
    finally:
        await engine.dispose()


async def test_list_accepts_more_than_control_limit_and_rejects_over_one_mib(
    tmp_path: Path,
) -> None:
    sessions = [
        {
            "name": "synthetic-session-" + str(index),
            "ref": REF + str(index),
            "attachedClients": 0,
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
            "partial": False,
            "peers": [{"label": "work", "machine": "devbox", "ok": True, **inventory}],
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
    assert result.value.peers[0].sessions is not None
    assert len(result.value.peers[0].sessions) == 700
    config.write_text("x" * 1048577)
    with pytest.raises(DeclaredToolFailure):
        await controller.list(AgentListInput(), cast(ExecutionContext, None))

"""The fleet's ordinary CLI is also the model's control interface."""

import json
from pathlib import Path
from typing import cast

from llm_tools import ExecutionContext, ToolId

from jarvis.actions import ActionStore
from jarvis.agent_control import AgentController
from jarvis.agent_tools import agent_family
from jarvis.db import create_engine


async def test_named_tools_use_opaque_reference_and_literal_stdin(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "skid"
    receipt = tmp_path / "receipt"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\nfrom pathlib import Path\n"
        "assert sys.argv[1:] == ['--config', sys.argv[2], 'send', '--json', "
        "'--ref', 'opaque-reference', '--stdin']\n"
        "Path(sys.argv[2]).write_bytes(sys.stdin.buffer.read())\n"
        'print(\'{"ok":true,"result":{"method":"terminal","outcome":"written"}}\')\n'
    )
    executable.chmod(0o700)
    controller = AgentController(
        executable=executable,
        client_config=receipt,
        actions=ActionStore(
            create_engine("postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
        ),
    )
    bindings = {
        str(binding.spec.id): binding for binding in agent_family(controller).bindings
    }
    assert set(bindings) == {
        "agent." + verb
        for verb in (
            "list",
            "info",
            "start",
            "read",
            "send",
            "keys",
            "interrupt",
            "stop",
            "kill",
        )
    }
    binding = bindings[str(ToolId("agent.send"))]
    text = "first\nsecond $(literal)\n"
    result = await controller.send(
        binding.spec.input_type.model_validate(
            {"ref": "opaque-reference", "text": text}
        ),
        cast(ExecutionContext, None),
    )
    assert result.value.outcome == "written"
    assert receipt.read_bytes() == text.encode()


def test_old_start_receipt_remains_readable_after_cli_cut() -> None:
    from types import SimpleNamespace

    from jarvis.actions import StoredAction
    from jarvis.write_dispatch import action_resolution_text

    stored = cast(
        StoredAction,
        SimpleNamespace(
            id="synthetic-action",
            arguments={"name": "legacy-worker"},
            status="succeeded",
            tool_name=ToolId("agent.start"),
            result={
                "type": "Success",
                "value": {
                    "observedAt": "2026-09-12T00:00:00Z",
                    "session": {
                        "tmuxId": "$3",
                        "name": "legacy-worker",
                        "cwd": "/synthetic",
                    },
                },
            },
        ),
    )
    text = action_resolution_text(stored)
    safe = json.loads(text.split("Safe result: ", 1)[1].split("\n", 1)[0])
    assert safe == {
        "type": "agent_started",
        "name": "legacy-worker",
        "observedAt": "2026-09-12T00:00:00Z",
    }

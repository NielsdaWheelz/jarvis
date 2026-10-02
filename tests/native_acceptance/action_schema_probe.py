"""Temporary published/validated/executed ActionRequest integration proof."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from llm_tools import ToolCatalog

from jarvis.action_requests import bind_action_requests
from jarvis.agent_tools import agent_family


class Peer:
    cli_path = "/proof/skid"
    client_config_path = "/proof/config"

    async def start(self, value, context):
        assert value.machine == "macbook"
        assert not hasattr(value, "request_ref")
        return {"type": "started"}

    list = info = read = send = text = keys = stop = close = start


async def main():
    family = bind_action_requests(agent_family(Peer()))
    catalog = ToolCatalog.compose((family,))
    binding = catalog.binding("agent.start")
    fields = binding.spec.input_schema.semantic["properties"]
    assert set(fields) == {"request_ref", "existing_action_ref", "arguments"}
    assert set(binding.spec.input_schema.semantic["required"]) == set(fields)
    payload = {
        "request_ref": str(uuid4()),
        "existing_action_ref": None,
        "arguments": {
            "machine": "macbook",
            "profile": "personal",
            "name": "proof",
            "cwd": None,
        },
    }
    value = binding.spec.input_type.model_validate(payload)
    assert value.model_dump(mode="json") == payload
    await binding.execute.handler(value, None)
    read = catalog.binding("agent.info")
    assert "request_ref" not in read.spec.input_schema.semantic["properties"]
    print("published, validated and executed action wrapper: GREEN")


asyncio.run(main())

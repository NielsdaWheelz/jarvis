"""One bounded structured CLI process per fleet operation; never a second client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID

from llm_tools import DeclaredToolFailure, ExecutionContext, HandlerSuccess
from pydantic import BaseModel

from jarvis.agent_tools import (
    AgentActionEvidence,
    AgentError,
    AgentInterruptInput,
    AgentKeysInput,
    AgentListInput,
    AgentListResult,
    AgentReadInput,
    AgentReadResult,
    AgentSendInput,
    AgentStartInput,
    AgentStartResult,
    AgentStopInput,
    AgentStopResult,
    AgentWriteResult,
)

if TYPE_CHECKING:
    from jarvis.actions import ActionStore


class AgentOutcomeUnknown(RuntimeError):
    """The existing BilledOnce recorder must settle without replaying the CLI."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ValueError("non-finite JSON value")


def _session(raw: object, machine: str | None) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError("invalid session")
    raw = cast(dict[str, object], raw)
    result: dict[str, object] = {
        "tmuxId": raw["tmuxId"],
        "name": raw["tmuxName"],
        "cwd": raw.get("cwd"),
        "profile": raw.get("launchProfile"),
    }
    agent = raw.get("agent")
    if isinstance(agent, dict):
        agent = cast(dict[str, object], agent)
        result.update(
            provider=agent["provider"],
            profile=agent.get("profile"),
            status=agent["status"],
            methods=agent["methods"],
        )
        if machine is not None:
            result["target"] = {
                "machine": machine,
                "tmuxId": raw["tmuxId"],
                "identityToken": raw["identityToken"],
                "paneId": agent["paneId"],
                "pid": agent["pid"],
                "startIdentity": agent["startIdentity"],
            }
    return result


def _inventory(verb: str, value: object) -> object:
    # Project the CLI's validated inventory into the closed tool schema.
    if verb not in {"list", "start"}:
        return value
    if not isinstance(value, dict):
        raise ValueError("invalid inventory")
    value = cast(dict[str, object], value)
    if verb == "start":
        return {
            "observedAt": value["observedAt"],
            "session": _session(value["session"], None),
        }
    peers: list[dict[str, object]] = []
    for peer in cast(list[dict[str, object]], value["peers"]):
        row: dict[str, object] = {"label": peer["label"], "machine": peer["machine"]}
        if peer["ok"] is True:
            inventory = cast(dict[str, object], peer["result"])
            row.update(
                observedAt=inventory["observedAt"],
                profiles=inventory["profiles"],
                sessions=[
                    _session(session, cast(str, peer["machine"]))
                    for session in cast(list[object], inventory["sessions"])
                ],
            )
        else:
            row["error"] = peer["error"]
        peers.append(row)
    return {"peers": peers}


class AgentController:
    def __init__(
        self, *, executable: Path, client_config: Path, actions: ActionStore
    ) -> None:
        if not executable.is_absolute() or not client_config.is_absolute():
            raise ValueError("agent CLI and config paths must be absolute")
        self.executable = executable
        self.client_config = client_config
        self._actions = actions

    async def _run[T: BaseModel](
        self,
        verb: str,
        value: BaseModel,
        result_type: type[T],
        context: ExecutionContext,
    ) -> HandlerSuccess[T]:
        write = verb not in {"list", "read"}
        encoded = value.model_dump_json(exclude_none=True).encode("utf-8")
        if len(encoded) > 65536:
            raise DeclaredToolFailure(
                AgentError(code="input_limit", dispatch="not_sent"), actual_attempts=0
            )
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(15):
                process = await asyncio.create_subprocess_exec(
                    str(self.executable),
                    "--client-config",
                    str(self.client_config),
                    "agent",
                    verb,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(encoded)
                await process.stdin.drain()
                process.stdin.close()
                maximum = 1048576 if verb == "list" else 65536
                output = bytearray()
                while chunk := await process.stdout.read(
                    min(8192, maximum + 1 - len(output))
                ):
                    output.extend(chunk)
                    if len(output) > maximum:
                        raise ValueError("CLI output limit")
                returncode = await process.wait()
                envelope = json.loads(
                    output.decode("utf-8"),
                    object_pairs_hook=_object,
                    parse_constant=_constant,
                )
                if not isinstance(envelope, dict):
                    raise ValueError("invalid CLI envelope")
                envelope = cast(dict[str, object], envelope)
                if (
                    set(envelope) == {"ok", "error"}
                    and envelope["ok"] is False
                    and returncode == 1
                ):
                    error = AgentError.model_validate(envelope["error"])
                    if write and error.dispatch == "unknown":
                        raise AgentOutcomeUnknown(
                            "agent command outcome unconfirmed; do not repeat"
                        )
                    raise DeclaredToolFailure(error, actual_attempts=1)
                if (
                    set(envelope) != {"ok", "result"}
                    or envelope["ok"] is not True
                    or returncode != 0
                ):
                    raise ValueError("invalid CLI envelope")
                result = result_type.model_validate(
                    _inventory(verb, envelope["result"])
                )
                if (
                    isinstance(result, AgentWriteResult) and result.outcome == "unknown"
                ) or (
                    isinstance(result, AgentStopResult)
                    and (
                        result.agent == "unconfirmed"
                        or result.terminal == "unconfirmed"
                    )
                ):
                    if (
                        context.effect_id is None
                        or context.position != context.effect_id
                    ):
                        raise RuntimeError(
                            "agent Write requires its durable action position"
                        )
                    stage = asyncio.create_task(
                        self._actions.stage_agent_control(
                            action_id=UUID(str(context.effect_id)),
                            evidence=AgentActionEvidence(observed=result),
                        )
                    )
                    try:
                        await asyncio.shield(stage)
                    except asyncio.CancelledError:
                        await stage
                        raise
                    raise AgentOutcomeUnknown(
                        "agent command partially confirmed; do not repeat"
                    )
                return HandlerSuccess(result, actual_attempts=1)
        except (OSError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            if write and process is not None:
                raise AgentOutcomeUnknown(
                    "agent command reply unavailable; do not repeat"
                ) from exc
            raise DeclaredToolFailure(
                AgentError(code="unavailable", dispatch="not_sent"),
                actual_attempts=1 if process is not None else 0,
            ) from exc
        finally:
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    async with asyncio.timeout(0.5):
                        await process.wait()
                except TimeoutError:
                    process.kill()
                    await process.wait()

    async def list(
        self, value: AgentListInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentListResult]:
        return await self._run("list", value, AgentListResult, context)

    async def read(
        self, value: AgentReadInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentReadResult]:
        return await self._run("read", value, AgentReadResult, context)

    async def start(
        self, value: AgentStartInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStartResult]:
        return await self._run("start", value, AgentStartResult, context)

    async def send(
        self, value: AgentSendInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._run("send", value, AgentWriteResult, context)

    async def keys(
        self, value: AgentKeysInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._run("keys", value, AgentWriteResult, context)

    async def interrupt(
        self, value: AgentInterruptInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._run("interrupt", value, AgentWriteResult, context)

    async def stop(
        self, value: AgentStopInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStopResult]:
        return await self._run("stop", value, AgentStopResult, context)

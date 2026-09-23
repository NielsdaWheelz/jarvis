"""One bounded structured CLI process per fleet operation; never a second client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID

from llm_tools import (
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    canonical_json_bytes,
)
from pydantic import BaseModel

from jarvis.agent_tools import (
    AgentActionEvidence,
    AgentError,
    AgentInfoResult,
    AgentKeysInput,
    AgentKillResult,
    AgentListInput,
    AgentListResult,
    AgentReadInput,
    AgentReadResult,
    AgentRefInput,
    AgentSendInput,
    AgentStartInput,
    AgentStartResult,
    AgentStopResult,
    AgentWireError,
    AgentWriteResult,
    AgentWriteTarget,
    agent_error_type,
    agent_failure_partial,
    agent_failure_settles,
    agent_tool_limits,
    validate_agent_failure,
)

if TYPE_CHECKING:
    from jarvis.actions import ActionStore


class AgentOutcomeUnknown(RuntimeError):
    """The existing BilledOnce recorder must settle without replaying the CLI."""


class AgentTargetUnavailable(RuntimeError):
    """Preflight lookup could not prove exactly one original target."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ValueError("non-finite JSON value")


def _require_clean_strings(value: object) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if "\x00" in item:
                raise ValueError("NUL in CLI output")
            item.encode("utf-8")
        elif isinstance(item, dict):
            pending.extend(cast(dict[str, object], item).items())
        elif isinstance(item, list | tuple):
            pending.extend(cast(list[object], item))


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
        context: ExecutionContext | None,
    ) -> HandlerSuccess[T]:
        write = verb not in {"list", "info", "read"}
        argv = [
            str(self.executable),
            "--config",
            str(self.client_config),
            verb,
            "--json",
        ]
        stdin = b""
        if isinstance(value, AgentListInput):
            if value.machine is not None:
                argv.extend(("--machine", value.machine))
        elif isinstance(value, AgentStartInput):
            argv.extend(
                (
                    "--machine",
                    value.machine,
                    "--profile",
                    value.profile,
                    "--cwd",
                    value.cwd,
                    "--",
                    value.name,
                )
            )
        elif isinstance(value, AgentReadInput):
            argv.extend(
                (
                    "--ref",
                    value.ref,
                    "--coverage",
                    value.coverage,
                    "--max-bytes",
                    str(value.maxBytes),
                )
            )
        elif isinstance(value, AgentSendInput):
            argv.extend(("--ref", value.ref, "--stdin"))
            if value.mode == "terminal":
                argv.append("--terminal")
            stdin = value.text.encode("utf-8")
        elif isinstance(value, AgentKeysInput):
            argv.extend(("--ref", value.ref, *value.keys))
        elif isinstance(value, AgentRefInput):
            argv.extend(("--ref", value.ref))
        else:
            raise ValueError("unsupported agent input")
        limits = agent_tool_limits(verb)
        limit = limits.max_output_bytes
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(limits.deadline_seconds):
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(stdin)
                await process.stdin.drain()
                process.stdin.close()
                output = bytearray()
                while chunk := await process.stdout.read(limit + 2 - len(output)):
                    output.extend(chunk)
                    if len(output) > limit + 1:
                        raise ValueError("CLI output limit")
                returncode = await process.wait()
            document = bytes(output).removesuffix(b"\n")
            if len(document) == len(output) or document != document.strip():
                raise ValueError("CLI output is not one JSON line")
            envelope = json.loads(
                document.decode("utf-8"),
                object_pairs_hook=_object,
                parse_constant=_constant,
            )
            _require_clean_strings(envelope)
            if not isinstance(envelope, dict):
                raise ValueError("invalid CLI envelope")
            envelope = cast(dict[str, object], envelope)
            fields = set(envelope)
            target = fields & {"label", "machine"}
            if target not in (set(), {"label", "machine"}) or not all(
                isinstance(envelope[key], str) for key in target
            ):
                raise ValueError("invalid CLI envelope target")
            observed: T | AgentError
            if (
                fields - target in ({"ok", "error"}, {"ok", "error", "partial"})
                and envelope["ok"] is False
                and returncode in {1, 2}
            ):
                wire = AgentWireError.model_validate(envelope["error"])
                if returncode == 2 and (
                    fields != {"ok", "error"}
                    or (wire.code, wire.dispatch) != ("invalid_input", "not_sent")
                ):
                    raise ValueError("invalid CLI usage envelope")
                failure: dict[str, object] = {
                    "code": wire.code,
                    "message": wire.message,
                    "dispatch": wire.dispatch or "unknown",
                    "label": envelope.get("label"),
                    "machine": envelope.get("machine"),
                }
                if "partial" in envelope:
                    failure["partial"] = envelope["partial"]
                observed = validate_agent_failure(verb, failure)
            elif fields == {"ok", "result"} and envelope["ok"] is True:
                observed = result_type.model_validate(envelope["result"])
                if isinstance(observed, AgentWriteResult) and not observed.complete:
                    exits = {0, 1}
                elif isinstance(observed, AgentListResult) and observed.partial:
                    exits = {1}
                else:
                    exits = {0}
                if returncode not in exits:
                    raise ValueError("CLI exit status differs from its result")
                normalized = {
                    "type": "Success",
                    "value": observed.model_dump(mode="json"),
                }
                if len(canonical_json_bytes(normalized)) > limit:
                    raise ValueError("normalized result exceeds its declared limit")
            else:
                raise ValueError("invalid CLI envelope")
        except (OSError, TimeoutError, ValueError, TypeError, RecursionError) as exc:
            if process is None:
                raise DeclaredToolFailure(
                    agent_error_type(verb)(code="unavailable", dispatch="not_sent"),
                    actual_attempts=0,
                ) from exc
            if write:
                raise AgentOutcomeUnknown(
                    "agent command reply unavailable; do not repeat"
                ) from exc
            raise DeclaredToolFailure(
                agent_error_type(verb)(code="unavailable", dispatch="unknown"),
                actual_attempts=1,
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
        if isinstance(observed, AgentError):
            failed = not write or agent_failure_settles(observed)
            if failed and agent_failure_partial(observed) is None:
                raise DeclaredToolFailure(observed, actual_attempts=1)
        elif isinstance(observed, AgentWriteResult) and not observed.complete:
            failed = False
        else:
            return HandlerSuccess(observed, actual_attempts=1)
        if (
            context is None
            or context.effect_id is None
            or context.position != context.effect_id
        ):
            raise RuntimeError("agent Write requires its durable action position")
        stage = asyncio.create_task(
            self._actions.stage_agent_control(
                action_id=UUID(str(context.effect_id)),
                evidence=AgentActionEvidence(observed=observed),
            )
        )
        try:
            await asyncio.shield(stage)
        except asyncio.CancelledError:
            await stage
            raise
        if failed:
            raise DeclaredToolFailure(observed, actual_attempts=1)
        raise AgentOutcomeUnknown("agent command outcome unconfirmed; do not repeat")

    async def locate_agent(self, ref: str) -> AgentWriteTarget:
        try:
            inventory = (await self.list(AgentListInput())).value
        except DeclaredToolFailure as exc:
            raise AgentTargetUnavailable("fleet inventory unavailable") from exc
        matches = [
            (peer.label, terminal.name)
            for peer in inventory.peers
            for terminal in peer.terminals or ()
            if terminal.agent is not None and terminal.agent.ref == ref
        ]
        if len(matches) != 1:
            raise AgentTargetUnavailable(f"{len(matches)} current agents match the ref")
        label, name = matches[0]
        return AgentWriteTarget(label=label, name=name, ref=ref)

    async def locate_terminal(self, ref: str) -> AgentWriteTarget:
        try:
            observed = (await self.info(AgentRefInput(ref=ref))).value
        except DeclaredToolFailure as exc:
            raise AgentTargetUnavailable("terminal observation unavailable") from exc
        if observed.terminal.ref != ref:
            raise AgentTargetUnavailable("observed terminal differs from the ref")
        return AgentWriteTarget(
            label=observed.label, name=observed.terminal.name, ref=ref
        )

    async def list(
        self, value: AgentListInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentListResult]:
        return await self._run("list", value, AgentListResult, context)

    async def info(
        self, value: AgentRefInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentInfoResult]:
        return await self._run("info", value, AgentInfoResult, context)

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
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._run("interrupt", value, AgentWriteResult, context)

    async def stop(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStopResult]:
        return await self._run("stop", value, AgentStopResult, context)

    async def kill(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentKillResult]:
        return await self._run("kill", value, AgentKillResult, context)

"""The herdr codec: one allowlisted herdr command per ssh call to a host's gate."""

from __future__ import annotations

import asyncio
import base64
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from llm_tools import (
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    ToolId,
    canonical_json_bytes,
)
from pydantic import BaseModel, ConfigDict

from jarvis.agent_tools import (
    AGENT_CALL_SECONDS,
    AGENT_CONTROL_LIMIT_BYTES,
    AGENT_INVENTORY_LIMIT_BYTES,
    AGENT_PROFILES,
    AGENT_RAW_LIMIT_BYTES,
    AGENT_START_WAIT_MS,
    AgentActionEvidence,
    AgentCloseResult,
    AgentError,
    AgentInfoResult,
    AgentKeysInput,
    AgentListInput,
    AgentListResult,
    AgentMachine,
    AgentObservation,
    AgentReadInput,
    AgentReadResult,
    AgentRefInput,
    AgentSendInput,
    AgentStartFailure,
    AgentStartInput,
    AgentStartPartial,
    AgentStartResult,
    AgentStatus,
    AgentStopFailure,
    AgentStopPartial,
    AgentTerminal,
    AgentWriteResult,
    AgentWriteTarget,
)

if TYPE_CHECKING:
    from jarvis.actions import ActionStore

SSH = "/usr/bin/ssh"
# the gate's one content-free line when it refuses an argv before herdr runs.
GATE_REFUSAL = b"herdr-gate: command refused\n"
# sshd hands the command to the gate as SSH_ORIGINAL_COMMAND; stay far below
# linux's 128 KiB bound on one environment string.
_COMMAND_LIMIT_BYTES = 65_536
_ERROR_LIMIT_BYTES = 65_536


class AgentOutcomeUnknown(RuntimeError):
    """The existing BilledOnce recorder must settle without replaying the command."""


class AgentTargetUnavailable(RuntimeError):
    """Preflight could not prove the original target is current."""


class _ReplyLost(Exception):
    """The command may have run, but its reply is missing or unusable."""


class _Wire(BaseModel):
    """herdr's api envelope; unknown fields are ignored, as herdr's policy asks."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class _Pane(_Wire):
    pane_id: str
    terminal_id: str
    cwd: str | None = None
    foreground_cwd: str | None = None


class _Agent(_Wire):
    pane_id: str
    terminal_id: str
    name: str | None = None
    agent: str | None = None
    agent_status: AgentStatus
    interactive_ready: bool = False


class _Result(_Wire):
    type: str
    panes: tuple[_Pane, ...] | None = None
    agents: tuple[_Agent, ...] | None = None
    agent: _Agent | None = None
    root_pane: _Pane | None = None


class _Reply(_Wire):
    result: _Result


class _Refusal(_Wire):
    code: str
    message: str


class _ErrorReply(_Wire):
    error: _Refusal


class _TerminalRef(BaseModel):
    """One terminal lifetime: herdr never repeats a terminal_id, while a pane id
    changes when its pane moves and returns after a restart."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    machine: str
    terminal: str


class _AgentRef(_TerminalRef):
    name: str


def _encode(ref: _TerminalRef) -> str:
    return base64.urlsafe_b64encode(ref.model_dump_json().encode()).decode().rstrip("=")


def _observation(machine: str, agent: _Agent) -> AgentObservation:
    return AgentObservation(
        ref=None
        if agent.name is None
        else _encode(
            _AgentRef(machine=machine, terminal=agent.terminal_id, name=agent.name)
        ),
        name=agent.name,
        kind=agent.agent,
        status=agent.agent_status,
        ready=agent.interactive_ready,
    )


def _terminal(machine: str, pane: _Pane, agent: _Agent | None) -> AgentTerminal:
    return AgentTerminal(
        ref=_encode(_TerminalRef(machine=machine, terminal=pane.terminal_id)),
        pane=pane.pane_id,
        cwd=pane.foreground_cwd or pane.cwd,
        agent=None if agent is None else _observation(machine, agent),
    )


async def _read(stream: asyncio.StreamReader, limit: int) -> bytes:
    data = bytearray()
    while chunk := await stream.read(limit + 1 - len(data)):
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError("gate reply exceeds its limit")
    return bytes(data)


class AgentController:
    def __init__(
        self,
        *,
        ssh_config: Path,
        machines: Mapping[str, str],
        actions: ActionStore,
    ) -> None:
        if not ssh_config.is_absolute():
            raise ValueError("the herdr ssh config path must be absolute")
        self.ssh_config = ssh_config
        # label -> the owner's home on that host, as configured, never guessed
        self.machines = dict(machines)
        self._actions = actions

    async def _herdr(
        self, machine: str, argv: list[str], *, limit: int = AGENT_CONTROL_LIMIT_BYTES
    ) -> bytes | AgentError:
        """herdr's stdout, or a refusal: not_sent before herdr ran, else sent."""

        command = shlex.join(argv)
        if len(command.encode("utf-8")) > _COMMAND_LIMIT_BYTES:
            return AgentError(
                code="input_too_large", machine=machine, dispatch="not_sent"
            )
        try:
            process = await asyncio.create_subprocess_exec(
                SSH,
                "-F",
                str(self.ssh_config),
                machine,
                command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin"},
            )
        except OSError:
            return AgentError(code="unavailable", machine=machine, dispatch="not_sent")
        # `agent start` also spends herdr's own readiness wait inside the call.
        seconds = AGENT_CALL_SECONDS + (
            AGENT_START_WAIT_MS / 1000 if argv[:2] == ["agent", "start"] else 0
        )
        try:
            async with asyncio.timeout(seconds):
                assert process.stdout is not None and process.stderr is not None
                stdout = await _read(process.stdout, limit)
                stderr = await _read(process.stderr, _ERROR_LIMIT_BYTES)
                returncode = await process.wait()
        except (TimeoutError, ValueError) as exc:
            raise _ReplyLost from exc
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    async with asyncio.timeout(0.5):
                        await process.wait()
                except TimeoutError:
                    process.kill()
                    await process.wait()
        if returncode == 0:
            return stdout
        if returncode == 1 and stderr == GATE_REFUSAL:
            return AgentError(code="gate_refused", machine=machine, dispatch="not_sent")
        if returncode == 2:
            return AgentError(code="usage", machine=machine, dispatch="not_sent")
        if returncode != 1:
            raise _ReplyLost(f"gate exited {returncode}")
        try:
            refusal = _ErrorReply.model_validate_json(stderr).error
            return AgentError(
                code=refusal.code,
                message=refusal.message if len(refusal.message) <= 1024 else None,
                machine=machine,
                dispatch="sent",
            )
        except ValueError as exc:
            raise _ReplyLost from exc

    async def _call(
        self,
        machine: str,
        argv: list[str],
        kind: str,
        *,
        limit: int = AGENT_CONTROL_LIMIT_BYTES,
    ) -> _Result | AgentError:
        reply = await self._herdr(machine, argv, limit=limit)
        if isinstance(reply, AgentError):
            return reply
        try:
            result = _Reply.model_validate_json(reply).result
        except ValueError as exc:
            raise _ReplyLost from exc
        if result.type != kind:
            raise _ReplyLost(f"herdr answered {result.type}, not {kind}")
        return result

    async def _mutate(
        self,
        machine: str,
        argv: list[str],
        kind: str,
        context: ExecutionContext,
        known: AgentStartPartial | AgentStopPartial | None = None,
    ) -> _Result | AgentError:
        """Run one mutating command; a lost reply stages the known prefix, no repeat."""

        try:
            return await self._call(machine, argv, kind)
        except _ReplyLost as exc:
            if known is not None:
                await self._stage(context, known)
            raise AgentOutcomeUnknown(
                "agent command reply unavailable; do not repeat"
            ) from exc

    async def _stage(
        self, context: ExecutionContext, known: AgentStartPartial | AgentStopPartial
    ) -> None:
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("agent Write requires its durable action position")
        stage = asyncio.create_task(
            self._actions.stage_agent_control(
                action_id=UUID(str(context.effect_id)),
                evidence=AgentActionEvidence(observed=known),
            )
        )
        try:
            await asyncio.shield(stage)
        except asyncio.CancelledError:
            await stage
            raise

    def _ref[T: _TerminalRef](
        self, kind: type[T], ref: str, failure: type[AgentError] = AgentError
    ) -> T:
        try:
            decoded = kind.model_validate_json(
                base64.b64decode(ref + "=" * (-len(ref) % 4), b"-_", validate=True)
            )
            if decoded.machine not in self.machines:
                raise ValueError("ref names no configured machine")
        except ValueError as exc:
            raise DeclaredToolFailure(
                failure(code="invalid_reference", dispatch="not_sent"),
                actual_attempts=0,
            ) from exc
        return decoded

    async def _scan(self, machine: str) -> tuple[AgentTerminal, ...] | AgentError:
        """One machine's terminals: its panes joined with herdr's agents."""

        try:
            async with asyncio.timeout(AGENT_CALL_SECONDS):
                panes = await self._call(
                    machine,
                    ["pane", "list"],
                    "pane_list",
                    limit=AGENT_INVENTORY_LIMIT_BYTES,
                )
                if isinstance(panes, AgentError):
                    return panes
                agents = await self._call(
                    machine,
                    ["agent", "list"],
                    "agent_list",
                    limit=AGENT_INVENTORY_LIMIT_BYTES,
                )
                if isinstance(agents, AgentError):
                    return agents
            hosted = {
                (agent.pane_id, agent.terminal_id): agent
                for agent in agents.agents or ()
            }
            return tuple(
                _terminal(machine, pane, hosted.get((pane.pane_id, pane.terminal_id)))
                for pane in panes.panes or ()
            )
        except (_ReplyLost, TimeoutError, ValueError):
            return AgentError(code="unavailable", machine=machine, dispatch="unknown")

    async def _agent_now(self, ref: _AgentRef) -> _Agent | AgentError:
        """herdr's agent of that name, while it is still the referenced terminal."""

        try:
            observed = await self._call(
                ref.machine, ["agent", "get", ref.name], "agent_info"
            )
        except _ReplyLost:
            return AgentError(
                code="unavailable", machine=ref.machine, dispatch="not_sent"
            )
        if isinstance(observed, AgentError):
            return observed.model_copy(
                update={
                    "code": "stale_reference"
                    if observed.code == "agent_not_found"
                    else observed.code,
                    "dispatch": "not_sent",
                }
            )
        agent = observed.agent
        if agent is None or (agent.name, agent.terminal_id) != (ref.name, ref.terminal):
            return AgentError(
                code="stale_reference", machine=ref.machine, dispatch="not_sent"
            )
        return agent

    async def _terminal_now(self, ref: _TerminalRef) -> AgentTerminal | AgentError:
        """The ref's terminal wherever its pane is now, while that terminal lives."""

        scan = await self._scan(ref.machine)
        if isinstance(scan, AgentError):
            return scan
        wanted = _encode(_TerminalRef(machine=ref.machine, terminal=ref.terminal))
        for terminal in scan:
            if terminal.ref == wanted:
                return terminal
        return AgentError(
            code="stale_reference", machine=ref.machine, dispatch="not_sent"
        )

    async def locate(self, tool_id: ToolId, ref: str) -> AgentWriteTarget:
        """Prove an addressed write's original target before the gate sees it."""

        try:
            if tool_id != ToolId("agent.kill"):
                agent = self._ref(_AgentRef, ref)
                current = await self._agent_now(agent)
                if isinstance(current, AgentError):
                    raise AgentTargetUnavailable("agent ref is not current")
                return AgentWriteTarget(
                    machine=agent.machine, name=agent.name, pane=current.pane_id
                )
            decoded = self._ref(_TerminalRef, ref)
        except DeclaredToolFailure as exc:
            raise AgentTargetUnavailable("ref does not decode") from exc
        terminal = await self._terminal_now(decoded)
        if isinstance(terminal, AgentError):
            raise AgentTargetUnavailable("terminal ref is not current")
        return AgentWriteTarget(
            machine=decoded.machine,
            name=None if terminal.agent is None else terminal.agent.name,
            pane=terminal.pane,
        )

    async def list(
        self, value: AgentListInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentListResult]:
        if value.machine is not None and value.machine not in self.machines:
            raise DeclaredToolFailure(
                AgentError(
                    code="unknown_machine", machine=value.machine, dispatch="not_sent"
                ),
                actual_attempts=0,
            )
        labels = tuple(self.machines) if value.machine is None else (value.machine,)
        scans = await asyncio.gather(*(self._scan(label) for label in labels))
        machines = tuple(
            AgentMachine(machine=label, error=scan.code)
            if isinstance(scan, AgentError)
            else AgentMachine(machine=label, terminals=scan)
            for label, scan in zip(labels, scans, strict=True)
        )
        result = AgentListResult(
            partial=any(item.error is not None for item in machines),
            machines=machines,
        )
        normalized = {"type": "Success", "value": result.model_dump(mode="json")}
        if len(canonical_json_bytes(normalized)) > AGENT_INVENTORY_LIMIT_BYTES:
            raise DeclaredToolFailure(
                AgentError(code="output_limit", dispatch="unknown"),
                actual_attempts=1,
            )
        return HandlerSuccess(result, actual_attempts=1)

    async def info(
        self, value: AgentRefInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentInfoResult]:
        ref = self._ref(_TerminalRef, value.ref)
        terminal = await self._terminal_now(ref)
        if isinstance(terminal, AgentError):
            raise DeclaredToolFailure(terminal, actual_attempts=1)
        return HandlerSuccess(
            AgentInfoResult(machine=ref.machine, terminal=terminal), actual_attempts=1
        )

    async def read(
        self, value: AgentReadInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentReadResult]:
        ref = self._ref(_AgentRef, value.ref)
        current = await self._agent_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(current, actual_attempts=1)
        try:
            reply = await self._herdr(
                ref.machine,
                [
                    "agent",
                    "read",
                    ref.name,
                    "--source",
                    value.coverage,
                    "--lines",
                    str(value.lines),
                ],
            )
            if isinstance(reply, AgentError):
                raise DeclaredToolFailure(reply, actual_attempts=1)
            text = reply.decode("utf-8")
            if "\x00" in text:
                raise ValueError("NUL in terminal text")
        except (_ReplyLost, ValueError) as exc:
            raise DeclaredToolFailure(
                AgentError(code="unavailable", machine=ref.machine, dispatch="unknown"),
                actual_attempts=1,
            ) from exc
        truncated = len(reply) > AGENT_RAW_LIMIT_BYTES
        if truncated:
            tail = reply[-AGENT_RAW_LIMIT_BYTES:]
            start = 0
            while start < len(tail) and tail[start] & 0xC0 == 0x80:
                start += 1
            text = tail[start:].decode("utf-8")
        return HandlerSuccess(
            AgentReadResult(
                machine=ref.machine,
                text=text,
                coverage=value.coverage,
                truncated=truncated,
            ),
            actual_attempts=1,
        )

    async def start(
        self, value: AgentStartInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStartResult]:
        machine = value.machine
        home = self.machines.get(machine)
        if home is None:
            raise DeclaredToolFailure(
                AgentStartFailure(
                    code="unknown_machine", machine=machine, dispatch="not_sent"
                ),
                actual_attempts=0,
            )
        cwd = value.cwd or "~"
        cwd = home + cwd[1:] if cwd == "~" or cwd.startswith("~/") else cwd
        if not cwd.startswith("/"):
            raise DeclaredToolFailure(
                AgentStartFailure(
                    code="invalid_cwd", machine=machine, dispatch="not_sent"
                ),
                actual_attempts=0,
            )
        kind, variable, directory = AGENT_PROFILES[value.profile]
        try:
            taken = await self._call(
                machine, ["agent", "get", value.name], "agent_info"
            )
        except _ReplyLost as exc:
            raise DeclaredToolFailure(
                AgentStartFailure(
                    code="unavailable", machine=machine, dispatch="not_sent"
                ),
                actual_attempts=1,
            ) from exc
        if not isinstance(taken, AgentError) or taken.code != "agent_not_found":
            code = "name_taken" if not isinstance(taken, AgentError) else taken.code
            raise DeclaredToolFailure(
                AgentStartFailure(code=code, machine=machine, dispatch="not_sent"),
                actual_attempts=1,
            )
        created = await self._mutate(
            machine,
            [
                "workspace",
                "create",
                "--cwd",
                cwd,
                "--label",
                value.name,
                "--env",
                f"{variable}={home}/{directory}",
            ],
            "workspace_created",
            context,
        )
        if isinstance(created, AgentError):
            raise DeclaredToolFailure(
                AgentStartFailure.model_validate(created.model_dump()),
                actual_attempts=1,
            )
        if created.root_pane is None:
            raise AgentOutcomeUnknown("created workspace has no root pane")
        known = AgentStartPartial(created=_terminal(machine, created.root_pane, None))
        started = await self._mutate(
            machine,
            [
                "agent",
                "start",
                value.name,
                "--kind",
                kind,
                "--pane",
                created.root_pane.pane_id,
                "--timeout",
                str(AGENT_START_WAIT_MS),
            ],
            "agent_started",
            context,
            known,
        )
        if isinstance(started, AgentError):
            await self._stage(context, known)
            raise DeclaredToolFailure(
                AgentStartFailure(
                    **started.model_dump(exclude={"type", "dispatch"}),
                    dispatch="sent",
                    partial=known,
                ),
                actual_attempts=1,
            )
        if started.agent is None:
            await self._stage(context, known)
            raise AgentOutcomeUnknown("started agent is missing from herdr's reply")
        return HandlerSuccess(
            AgentStartResult(
                machine=machine,
                terminal=_terminal(machine, created.root_pane, started.agent),
            ),
            actual_attempts=1,
        )

    async def _deliver(
        self, value: str, argv: list[str], context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        """Check an agent ref, then write once to herdr's agent of that name."""

        ref = self._ref(_AgentRef, value)
        current = await self._agent_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(current, actual_attempts=1)
        kind = "agent_prompted" if argv[0] == "prompt" else "ok"
        written = await self._mutate(
            ref.machine, ["agent", argv[0], ref.name, *argv[1:]], kind, context
        )
        if isinstance(written, AgentError):
            raise DeclaredToolFailure(written, actual_attempts=1)
        return HandlerSuccess(
            AgentWriteResult(machine=ref.machine, outcome="written"),
            actual_attempts=1,
        )

    async def send(
        self, value: AgentSendInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._deliver(value.ref, ["prompt", value.text], context)

    async def keys(
        self, value: AgentKeysInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._deliver(value.ref, ["send-keys", *value.keys], context)

    async def interrupt(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._deliver(value.ref, ["send-keys", "ctrl+c"], context)

    async def stop(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCloseResult]:
        ref = self._ref(_AgentRef, value.ref, AgentStopFailure)
        current = await self._agent_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(
                AgentStopFailure.model_validate(current.model_dump()),
                actual_attempts=1,
            )
        interrupted = await self._mutate(
            ref.machine, ["agent", "send-keys", ref.name, "ctrl+c"], "ok", context
        )
        if isinstance(interrupted, AgentError):
            raise DeclaredToolFailure(
                AgentStopFailure.model_validate(interrupted.model_dump()),
                actual_attempts=1,
            )
        # the agent may have exited and dropped its name; find its terminal's pane.
        terminal = await self._terminal_now(ref)
        if isinstance(terminal, AgentError):
            raise await self._interrupted(context, terminal, "not_attempted")
        closed = await self._mutate(
            ref.machine,
            ["pane", "close", terminal.pane],
            "ok",
            context,
            AgentStopPartial(terminal="unconfirmed"),
        )
        if isinstance(closed, AgentError):
            raise await self._interrupted(context, closed, "refused")
        return HandlerSuccess(
            AgentCloseResult(machine=ref.machine, terminal="closed"),
            actual_attempts=1,
        )

    async def _interrupted(
        self,
        context: ExecutionContext,
        failure: AgentError,
        terminal: Literal["not_attempted", "refused"],
    ) -> DeclaredToolFailure:
        """A stop that sent its interrupt settles failed with that prefix staged."""

        known = AgentStopPartial(terminal=terminal)
        await self._stage(context, known)
        return DeclaredToolFailure(
            AgentStopFailure(
                **failure.model_dump(exclude={"type", "dispatch"}),
                dispatch="sent",
                partial=known,
            ),
            actual_attempts=1,
        )

    async def kill(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCloseResult]:
        ref = self._ref(_TerminalRef, value.ref)
        current = await self._terminal_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(
                current.model_copy(update={"dispatch": "not_sent"}), actual_attempts=1
            )
        closed = await self._mutate(
            ref.machine, ["pane", "close", current.pane], "ok", context
        )
        if isinstance(closed, AgentError):
            raise DeclaredToolFailure(closed, actual_attempts=1)
        return HandlerSuccess(
            AgentCloseResult(machine=ref.machine, terminal="closed"),
            actual_attempts=1,
        )

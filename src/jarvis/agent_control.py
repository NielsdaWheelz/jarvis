"""The herdr codec: one allowlisted herdr command per ssh call to a host's gate."""

from __future__ import annotations

import asyncio
import base64
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from llm_tools import (
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    ToolId,
    canonical_json_bytes,
)
from pydantic import BaseModel, ConfigDict, Field

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
    AgentName,
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
GATE_REFUSAL = b"herdr-gate: command refused"
# sshd hands the command to the gate as SSH_ORIGINAL_COMMAND; stay far below
# linux's 128 KiB bound on one environment string.
_COMMAND_LIMIT_BYTES = 65_536
_ERROR_LIMIT_BYTES = 65_536
# herdr 0.9.1 codes that refuse before anything is written, typed, created or
# closed: the cli's server and protocol checks (src/cli.rs), target resolution
# and readiness for prompt and send-keys and key validation
# (src/app/api/agents.rs), launch env validation (src/app/api/workspaces.rs),
# and pane close's lookup and confirmation (src/app/api/panes.rs). any other
# herdr error to a write counts as sent.
_REFUSED_BEFORE_EFFECT = frozenset(
    {
        "server_not_running",
        "protocol_mismatch",
        "agent_not_found",
        "agent_target_ambiguous",
        "agent_not_ready",
        "agent_blocked",
        "empty_agent_prompt",
        "invalid_key",
        "invalid_env",
        "pane_not_found",
        "confirmation_required",
    }
)

type _Id = Annotated[str, Field(min_length=1, max_length=128)]
type _Path = Annotated[str, Field(max_length=4096)]


class AgentOutcomeUnknown(RuntimeError):
    """The existing BilledOnce recorder must settle without replaying the command."""


class _ReplyLost(Exception):
    """The command may have run, but its reply is missing or unusable."""


class _Wire(BaseModel):
    """herdr's api envelope; unknown fields are ignored, as herdr's policy asks.
    the bounds are the tool results' own, so a reply that decodes projects."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class _Pane(_Wire):
    pane_id: _Id
    terminal_id: _Id
    cwd: _Path | None = None
    foreground_cwd: _Path | None = None


class _Agent(_Wire):
    pane_id: _Id
    terminal_id: _Id
    name: AgentName | None = None
    agent: Annotated[str, Field(min_length=1, max_length=64)] | None = None
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


def _terminal(machine: str, pane: _Pane, agent: _Agent | None) -> AgentTerminal:
    return AgentTerminal(
        ref=_encode(_TerminalRef(machine=machine, terminal=pane.terminal_id)),
        pane=pane.pane_id,
        cwd=pane.foreground_cwd or pane.cwd,
        agent=None
        if agent is None
        else AgentObservation(
            ref=None
            if agent.name is None
            else _encode(
                _AgentRef(machine=machine, terminal=agent.terminal_id, name=agent.name)
            ),
            name=agent.name,
            kind=agent.agent,
            status=agent.agent_status,
            ready=agent.interactive_ready,
        ),
    )


def _invalid_reference(failure: type[AgentError] = AgentError) -> DeclaredToolFailure:
    return DeclaredToolFailure(
        failure(code="invalid_reference", dispatch="not_sent"), actual_attempts=0
    )


def _stop_failure(
    failure: AgentError, terminal: Literal["not_attempted", "refused"]
) -> DeclaredToolFailure:
    return DeclaredToolFailure(
        AgentStopFailure(
            **failure.model_dump(exclude={"type", "dispatch"}),
            dispatch="sent",
            partial=AgentStopPartial(terminal=terminal),
        ),
        actual_attempts=1,
    )


async def _read(stream: asyncio.StreamReader, limit: int, tail: bool) -> bytes:
    """At most `limit` bytes: the whole stream, or with `tail` its rolling end."""

    data = bytearray()
    while chunk := await stream.read(65_536):
        data.extend(chunk)
        if len(data) > limit:
            if not tail:
                raise ValueError("gate reply exceeds its limit")
            del data[:-limit]
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
        self,
        machine: str,
        argv: list[str],
        *,
        limit: int = AGENT_CONTROL_LIMIT_BYTES,
        tail: bool = False,
    ) -> bytes | AgentError:
        """herdr's stdout, or its refusal: not_sent when nothing took effect."""

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
                stdout = await _read(process.stdout, limit, tail)
                stderr = await _read(process.stderr, _ERROR_LIMIT_BYTES, False)
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
        # the gate and herdr each end on one line; anything ssh said comes first.
        last = (stderr.splitlines() or [b""])[-1]
        if returncode == 1 and last == GATE_REFUSAL:
            return AgentError(code="gate_refused", machine=machine, dispatch="not_sent")
        if returncode == 2:
            return AgentError(code="usage", machine=machine, dispatch="not_sent")
        if returncode != 1:
            raise _ReplyLost(f"gate exited {returncode}")
        try:
            refusal = _ErrorReply.model_validate_json(last).error
        except ValueError as exc:
            raise _ReplyLost from exc
        return AgentError(
            code=refusal.code,
            message=refusal.message if len(refusal.message) <= 1024 else None,
            machine=machine,
            dispatch="not_sent" if refusal.code in _REFUSED_BEFORE_EFFECT else "sent",
        )

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
        self, machine: str, argv: list[str], kind: str
    ) -> _Result | AgentError:
        """Run one mutating command; a lost reply may have taken effect."""

        try:
            return await self._call(machine, argv, kind)
        except _ReplyLost as exc:
            raise AgentOutcomeUnknown(
                "agent command reply unavailable; do not repeat"
            ) from exc

    async def _stage(
        self, context: ExecutionContext, known: AgentStartPartial | AgentStopPartial
    ) -> None:
        """Record a partial effect when it happens, before anything can lose it."""

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

    def _ref[T: _TerminalRef](self, kind: type[T], value: str) -> T:
        """Decode a ref naming a configured machine; ValueError otherwise."""

        decoded = kind.model_validate_json(
            base64.b64decode(value + "=" * (-len(value) % 4), b"-_", validate=True)
        )
        # the label becomes an ssh argument: only configured hosts, never a new one.
        if decoded.machine not in self.machines:
            raise ValueError("ref names no configured machine")
        return decoded

    async def _scan(
        self, machine: str
    ) -> tuple[tuple[_Pane, _Agent | None], ...] | AgentError:
        """One machine's panes, each with herdr's agent in its terminal, if any."""

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
        except (_ReplyLost, TimeoutError):
            return AgentError(code="unavailable", machine=machine, dispatch="unknown")
        hosted = {agent.terminal_id: agent for agent in agents.agents or ()}
        return tuple((pane, hosted.get(pane.terminal_id)) for pane in panes.panes or ())

    async def _hosting(
        self, ref: _TerminalRef
    ) -> tuple[_Pane, _Agent | None] | AgentError:
        """The pane that holds the ref's terminal now, wherever it moved."""

        scan = await self._scan(ref.machine)
        if isinstance(scan, AgentError):
            return scan
        for pane, agent in scan:
            if pane.terminal_id == ref.terminal:
                return pane, agent
        return AgentError(
            code="stale_reference", machine=ref.machine, dispatch="not_sent"
        )

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

    async def locate(self, tool_id: ToolId, ref: str) -> AgentWriteTarget:
        """The gate's view of an addressed write's target; ValueError if unusable.

        an agent ref already names its machine and agent, and the executor
        re-checks it before writing; a terminal ref's hosted agent and pane are
        known only to herdr.
        """

        if tool_id != ToolId("agent.kill"):
            agent = self._ref(_AgentRef, ref)
            return AgentWriteTarget(machine=agent.machine, name=agent.name, pane=None)
        terminal = self._ref(_TerminalRef, ref)
        hosting = await self._hosting(terminal)
        if isinstance(hosting, AgentError):
            raise ValueError(f"terminal ref is not current: {hosting.code}")
        pane, hosted = hosting
        return AgentWriteTarget(
            machine=terminal.machine,
            name=None if hosted is None else hosted.name,
            pane=pane.pane_id,
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
            else AgentMachine(
                machine=label,
                terminals=tuple(_terminal(label, pane, agent) for pane, agent in scan),
            )
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
        try:
            ref = self._ref(_TerminalRef, value.ref)
        except ValueError as exc:
            raise _invalid_reference() from exc
        hosting = await self._hosting(ref)
        if isinstance(hosting, AgentError):
            raise DeclaredToolFailure(hosting, actual_attempts=1)
        return HandlerSuccess(
            AgentInfoResult(
                machine=ref.machine, terminal=_terminal(ref.machine, *hosting)
            ),
            actual_attempts=1,
        )

    async def read(
        self, value: AgentReadInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentReadResult]:
        try:
            ref = self._ref(_AgentRef, value.ref)
        except ValueError as exc:
            raise _invalid_reference() from exc
        current = await self._agent_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(current, actual_attempts=1)
        unavailable = AgentError(
            code="unavailable", machine=ref.machine, dispatch="unknown"
        )
        try:
            # one byte beyond the bound shows that herdr's text was cut.
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
                limit=AGENT_RAW_LIMIT_BYTES + 1,
                tail=True,
            )
        except _ReplyLost as exc:
            raise DeclaredToolFailure(unavailable, actual_attempts=1) from exc
        if isinstance(reply, AgentError):
            raise DeclaredToolFailure(reply, actual_attempts=1)
        text = reply[-AGENT_RAW_LIMIT_BYTES:].decode("utf-8", "ignore")
        if "\x00" in text:
            raise DeclaredToolFailure(unavailable, actual_attempts=1)
        return HandlerSuccess(
            AgentReadResult(
                machine=ref.machine,
                text=text,
                coverage=value.coverage,
                truncated=len(reply) > AGENT_RAW_LIMIT_BYTES,
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
        # the gate admits any pane id: jarvis starts agents only in panes it made.
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
        )
        if isinstance(created, AgentError):
            raise DeclaredToolFailure(
                AgentStartFailure.model_validate(created.model_dump()),
                actual_attempts=1,
            )
        pane = created.root_pane
        if pane is None:
            raise AgentOutcomeUnknown("created workspace has no root pane")
        known = AgentStartPartial(created=_terminal(machine, pane, None))
        await self._stage(context, known)
        started = await self._mutate(
            machine,
            [
                "agent",
                "start",
                value.name,
                "--kind",
                kind,
                "--pane",
                pane.pane_id,
                "--timeout",
                str(AGENT_START_WAIT_MS),
            ],
            "agent_started",
        )
        if isinstance(started, AgentError):
            failure = started
        elif started.agent is None:
            raise AgentOutcomeUnknown("herdr's start reply names no agent")
        elif (started.agent.name, started.agent.terminal_id) != (
            value.name,
            pane.terminal_id,
        ):
            failure = AgentError(
                code="start_mismatch", machine=machine, dispatch="sent"
            )
        else:
            return HandlerSuccess(
                AgentStartResult(
                    machine=machine, terminal=_terminal(machine, pane, started.agent)
                ),
                actual_attempts=1,
            )
        raise DeclaredToolFailure(
            AgentStartFailure(
                **failure.model_dump(exclude={"type", "dispatch"}),
                dispatch="sent",
                partial=known,
            ),
            actual_attempts=1,
        )

    async def _deliver(
        self,
        value: str,
        verb: str,
        args: list[str],
        reply: str,
        context: ExecutionContext,
    ) -> HandlerSuccess[AgentWriteResult]:
        """Check an agent ref, then write once to herdr's agent of that name."""

        try:
            ref = self._ref(_AgentRef, value)
        except ValueError as exc:
            raise _invalid_reference() from exc
        current = await self._agent_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(current, actual_attempts=1)
        written = await self._mutate(
            ref.machine, ["agent", verb, ref.name, *args], reply
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
        return await self._deliver(
            value.ref, "prompt", [value.text], "agent_prompted", context
        )

    async def keys(
        self, value: AgentKeysInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._deliver(value.ref, "send-keys", [*value.keys], "ok", context)

    async def interrupt(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._deliver(value.ref, "send-keys", ["ctrl+c"], "ok", context)

    async def stop(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCloseResult]:
        try:
            ref = self._ref(_AgentRef, value.ref)
        except ValueError as exc:
            raise _invalid_reference(AgentStopFailure) from exc
        current = await self._agent_now(ref)
        if isinstance(current, AgentError):
            raise DeclaredToolFailure(
                AgentStopFailure.model_validate(current.model_dump()),
                actual_attempts=1,
            )
        interrupted = await self._mutate(
            ref.machine, ["agent", "send-keys", ref.name, "ctrl+c"], "ok"
        )
        if isinstance(interrupted, AgentError):
            raise DeclaredToolFailure(
                AgentStopFailure.model_validate(interrupted.model_dump()),
                actual_attempts=1,
            )
        await self._stage(context, AgentStopPartial(terminal="unconfirmed"))
        # the agent may have exited and dropped its name; find its terminal's pane.
        hosting = await self._hosting(ref)
        if isinstance(hosting, AgentError):
            raise _stop_failure(hosting, "not_attempted")
        closed = await self._mutate(
            ref.machine, ["pane", "close", hosting[0].pane_id], "ok"
        )
        if isinstance(closed, AgentError):
            raise _stop_failure(closed, "refused")
        return HandlerSuccess(
            AgentCloseResult(machine=ref.machine, terminal="closed"),
            actual_attempts=1,
        )

    async def kill(
        self, value: AgentRefInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCloseResult]:
        try:
            ref = self._ref(_TerminalRef, value.ref)
        except ValueError as exc:
            raise _invalid_reference() from exc
        hosting = await self._hosting(ref)
        if isinstance(hosting, AgentError):
            raise DeclaredToolFailure(
                hosting.model_copy(update={"dispatch": "not_sent"}), actual_attempts=1
            )
        closed = await self._mutate(
            ref.machine, ["pane", "close", hosting[0].pane_id], "ok"
        )
        if isinstance(closed, AgentError):
            raise DeclaredToolFailure(closed, actual_attempts=1)
        return HandlerSuccess(
            AgentCloseResult(machine=ref.machine, terminal="closed"),
            actual_attempts=1,
        )

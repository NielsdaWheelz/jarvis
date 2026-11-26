"""Fixed skid subprocesses, private captured refs, and durable observation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast
from uuid import UUID

from llm_tools import (
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    ToolId,
)
from pydantic import BaseModel

from jarvis.agent_tools import (
    AGENT_CALL_SECONDS,
    AGENT_CONTROL_LIMIT_BYTES,
    AGENT_INVENTORY_LIMIT_BYTES,
    AgentActionEvidence,
    AgentCloseInput,
    AgentCloseReceipt,
    AgentCloseResult,
    AgentControlResult,
    AgentDelegateInput,
    AgentDelegateReceipt,
    AgentError,
    AgentInfoInput,
    AgentInfoResult,
    AgentKeysInput,
    AgentLabel,
    AgentListInput,
    AgentListResult,
    AgentMachineId,
    AgentPeerResult,
    AgentPlacement,
    AgentReadInput,
    AgentReadResult,
    AgentSendInput,
    AgentSessionResult,
    AgentStartInput,
    AgentStartResult,
    AgentStopInput,
    AgentTarget,
    AgentTargetInput,
    AgentWriteResult,
    AgentWriteTarget,
    ObservedSession,
    WireFailure,
    WireFleetStatus,
    WireInventory,
    WireReadResult,
    WireStartResult,
    WireTerminalClose,
)
from jarvis.delegation import Delegations

if TYPE_CHECKING:
    from jarvis.actions import ActionStore


class AgentOutcomeUnknown(RuntimeError):
    """An entered one-shot command has no replay-safe absence proof."""


def classify_agent_receipt(
    operation: str,
    value: AgentStartInput | AgentTargetInput,
    observed: WireFailure
    | WireStartResult
    | AgentWriteResult
    | AgentCloseReceipt
    | None,
    *,
    machine_id: AgentMachineId | None = None,
) -> AgentStartResult | AgentControlResult | AgentCloseResult | AgentError | None:
    """Project owned evidence; None is unresolved, invalid owned data is a defect."""
    if operation == "start":
        if not isinstance(value, AgentStartInput):
            raise ValueError("foreign launch input")
    elif operation in {"send", "text", "keys", "stop", "close"}:
        if not isinstance(value, AgentTargetInput) or (
            operation == "close" and not isinstance(value, AgentCloseInput)
        ):
            raise ValueError("foreign control input")
    else:
        raise ValueError("unknown receipt operation")
    if observed is None:
        return None
    if isinstance(observed, WireFailure):
        if observed.dispatch == "unknown":
            return None
        return AgentError(
            code=observed.code,
            dispatch="not_sent",
            target=None if isinstance(value, AgentStartInput) else value.target,
        )
    if isinstance(observed, WireStartResult):
        if operation != "start" or not isinstance(value, AgentStartInput):
            raise ValueError("foreign launch receipt")
        if observed.machine != machine_id:
            raise ValueError("launch receipt differs from captured machine")
        projected = AgentStartResult(
            machine=observed.label,
            target=None
            if observed.handle is None
            else AgentTarget(machine=observed.label, handle=observed.handle),
            captured=observed.target is not None,
            creation=observed.creation,
            failure=None if observed.failure is None else observed.failure.code,
        )
        if observed.creation == "unknown":
            return None
        if observed.creation != "created" or observed.failure is not None:
            return AgentError(
                code="launch_incomplete"
                if observed.failure is None
                else observed.failure.code,
                dispatch="sent" if observed.creation == "created" else "not_sent",
                launch=projected,
            )
        return projected
    if isinstance(observed, AgentCloseReceipt):
        if operation != "close" or not isinstance(value, AgentCloseInput):
            raise ValueError("foreign close receipt")
        if value.terminal_only and observed.interrupt != "not_sent":
            raise ValueError("terminal-only closure contains interruption")
        if observed.terminal == "unknown" or observed.interrupt == "unknown":
            return None
        closed = AgentCloseResult(target=value.target, **observed.model_dump())
        if observed.terminal != "closed" or (
            not value.terminal_only and observed.interrupt != "written"
        ):
            return AgentError(
                code="close_incomplete",
                dispatch="sent"
                if observed.interrupt == "written" or observed.terminal == "closed"
                else "not_sent",
                target=value.target,
                close=closed,
            )
        return closed
    if operation not in {"send", "text", "keys", "stop"} or not isinstance(
        value, AgentTargetInput
    ):
        raise ValueError("foreign write receipt")
    if observed.outcome == "unknown":
        return None
    return AgentControlResult(
        target=value.target, method=observed.method, outcome=observed.outcome
    )


async def _read(stream: asyncio.StreamReader, limit: int) -> bytes:
    data = bytearray()
    while chunk := await stream.read(65_536):
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError("skid output exceeds its limit")
    return bytes(data)


def _closed_json(raw: bytes) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for name, item in pairs:
            if name in value:
                raise ValueError("duplicate envelope field")
            value[name] = item
        return value

    def invalid_constant(value: str) -> object:
        raise ValueError("non-json constant")

    return json.loads(
        raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant
    )


def decode_agent_reply[T: BaseModel](raw: bytes, model: type[T]) -> T | WireFailure:
    decoded = _closed_json(raw)
    if not isinstance(decoded, dict):
        raise ValueError("invalid skid envelope")
    value = cast(dict[str, object], decoded)
    if type(value.get("ok")) is not bool:
        raise ValueError("invalid skid envelope")
    if value["ok"] and set(value) == {"ok", "result"}:
        return model.model_validate(value["result"])
    if not value["ok"] and set(value) == {"ok", "error"}:
        return WireFailure.model_validate(value["error"])
    raise ValueError("invalid skid envelope")


def _session(machine: AgentLabel, value: object) -> AgentSessionResult:
    from jarvis.agent_tools import AgentTerminal

    row = AgentTerminal.model_validate(value)
    return AgentSessionResult(
        target=AgentTarget(machine=machine, handle=row.terminalHandle),
        name=row.name,
        provider=None if row.agent is None else row.agent.provider,
        profile=None if row.agent is None else row.agent.profile,
        group=row.group,
        cwd=row.cwd,
        status=row.terminalStatus,
    )


def _output(target: AgentTarget, value: WireReadResult) -> AgentReadResult:
    return AgentReadResult(
        target=target,
        text=value.text,
        source=value.source,
        scope=value.scope,
        truncated=value.truncated,
    )


class AgentController:
    def __init__(
        self,
        *,
        cli_path: Path,
        state_directory: Path,
        actions: ActionStore,
        source_conversation_id: str,
    ) -> None:
        if not cli_path.is_absolute() or not state_directory.is_absolute():
            raise ValueError("agent CLI and installed state directory must be absolute")
        self.cli_path = cli_path
        self.state_directory = state_directory
        self._actions = actions
        self.source_conversation_id = source_conversation_id
        self.delegations = Delegations(self, actions, source_conversation_id)

    async def call[T: BaseModel](
        self,
        argv: list[str],
        model: type[T],
        *,
        text: str | None = None,
        write: bool = False,
        inventory: bool = False,
        deadline_seconds: float = AGENT_CALL_SECONDS,
    ) -> T | WireFailure:
        state = ["--config", str(self.state_directory)]
        fleet_status = argv == ["status"]
        arguments = [*argv, *state] if argv[0] in {"job", "status"} else [*state, *argv]
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.cli_path),
                *arguments,
                "--json",
                stdin=asyncio.subprocess.PIPE
                if text is not None
                else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin"},
            )
        except OSError:
            return WireFailure(code="unavailable", dispatch="not_sent")
        stdout_task: asyncio.Task[bytes] | None = None
        try:
            async with asyncio.timeout(deadline_seconds):
                assert process.stdout is not None
                stdout_task = asyncio.create_task(
                    _read(
                        process.stdout,
                        AGENT_INVENTORY_LIMIT_BYTES
                        if inventory
                        else AGENT_CONTROL_LIMIT_BYTES,
                    )
                )
                if text is not None:
                    assert process.stdin is not None
                    try:
                        process.stdin.write(text.encode("utf-8"))
                        await process.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        process.stdin.close()
                raw = await stdout_task
                if fleet_status:
                    if await process.wait() != 0:
                        return WireFailure(code="unavailable", dispatch="not_sent")
                    return model.model_validate(_closed_json(raw))
                return decode_agent_reply(raw, model)
        except (TimeoutError, ValueError, OSError) as exc:
            if write:
                raise AgentOutcomeUnknown(
                    "write outcome unknown; not replayed"
                ) from exc
            return WireFailure(code="unavailable", dispatch="not_sent")
        finally:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    async with asyncio.timeout(0.5):
                        await process.wait()
                except TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()
            if stdout_task is not None:
                if not stdout_task.done():
                    stdout_task.cancel()
                await asyncio.gather(stdout_task, return_exceptions=True)

    @staticmethod
    def _effect_id(context: ExecutionContext) -> UUID:
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("agent Write requires its durable action position")
        return UUID(str(context.effect_id))

    async def _stage(
        self,
        context: ExecutionContext,
        observed: WireFailure | WireStartResult | AgentWriteResult | AgentCloseReceipt,
    ) -> None:
        task = asyncio.create_task(
            self._actions.stage_agent_control(
                action_id=self._effect_id(context),
                evidence=AgentActionEvidence(observed=observed),
            )
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def locate(
        self, tool_id: ToolId, value: AgentTargetInput
    ) -> AgentWriteTarget:
        target = value.target
        observed = await self.call(
            ["info", target.handle, "--machine", target.machine], ObservedSession
        )
        if (
            isinstance(observed, WireFailure)
            or observed.label != target.machine
            or observed.session.terminalHandle != target.handle
        ):
            raise ValueError("terminal capture unavailable")
        return AgentWriteTarget(
            target=target,
            ref=observed.session.ref,
            name=observed.session.name,
            profile=None
            if observed.session.agent is None
            else observed.session.agent.profile,
        )

    async def resolve_machine(self, machine: AgentLabel) -> AgentPlacement | AgentError:
        roster = await self.call(["status"], WireFleetStatus, inventory=True)
        if isinstance(roster, WireFailure):
            return AgentError(code="roster_unavailable", dispatch="not_sent")
        try:
            matches = [
                placement
                for placement in roster.enrolled()
                if placement.machine == machine
            ]
        except ValueError:
            return AgentError(code="roster_unavailable", dispatch="not_sent")
        if len(matches) == 1:
            return matches[0]
        return AgentError(
            code="machine_ambiguous" if matches else "machine_unknown",
            dispatch="not_sent",
            machine=machine,
        )

    async def _target(
        self, value: AgentTargetInput, context: ExecutionContext
    ) -> AgentWriteTarget:
        stored = await self._actions.get(self._effect_id(context))
        if stored is None or stored.agent_target is None:
            raise RuntimeError("addressed action lacks captured target")
        captured = stored.agent_target
        if captured.target != value.target:
            raise RuntimeError("action substituted model target")
        return captured

    @staticmethod
    def _failure(
        value: WireFailure,
        *,
        target: AgentTarget | None = None,
    ) -> Never:
        raise DeclaredToolFailure(
            AgentError(code=value.code, dispatch=value.dispatch, target=target),
            actual_attempts=1,
        )

    async def _receipt(
        self,
        operation: str,
        value: AgentStartInput | AgentTargetInput,
        observed: WireFailure | WireStartResult | AgentWriteResult | AgentCloseReceipt,
        context: ExecutionContext,
        *,
        machine_id: AgentMachineId | None = None,
    ) -> AgentStartResult | AgentControlResult | AgentCloseResult:
        try:
            projected = classify_agent_receipt(
                operation, value, observed, machine_id=machine_id
            )
        except ValueError as exc:
            raise AgentOutcomeUnknown("invalid write receipt; not replayed") from exc
        await self._stage(context, observed)
        if projected is None:
            raise AgentOutcomeUnknown(
                "write outcome unknown; captured evidence retained"
            )
        if isinstance(projected, AgentError):
            raise DeclaredToolFailure(projected, actual_attempts=1)
        return projected

    async def list(
        self, value: AgentListInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentListResult]:
        argv = ["list"]
        if value.machine is not None:
            argv += ["--machine", value.machine]
        if value.group is not None:
            argv += ["--group", value.group]
        if value.unassigned:
            argv += ["--unassigned"]
        result = await self.call(argv, WireInventory, inventory=True)
        if isinstance(result, WireFailure):
            self._failure(result)
        peers = tuple(
            AgentPeerResult(
                machine=p.label,
                ok=p.ok,
                observedAt=p.observedAt,
                profiles=tuple(x.key for x in p.profiles or ()),
                sessions=tuple(_session(p.label, s) for s in p.sessions or ()),
                error=None if p.error is None else p.error.code,
            )
            for p in result.peers
        )
        return HandlerSuccess(
            AgentListResult(partial=result.partial, peers=peers), actual_attempts=1
        )

    async def info(
        self, value: AgentInfoInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentInfoResult]:
        target = value.target
        result = await self.call(
            ["info", target.handle, "--machine", target.machine], ObservedSession
        )
        if isinstance(result, WireFailure):
            self._failure(result, target=target)
        row = _session(result.label, result.session)
        if row.target != target:
            raise ValueError("inspection substituted target")
        projected = AgentInfoResult(target=target, terminal=row)
        return HandlerSuccess(projected, actual_attempts=1)

    async def read(
        self, value: AgentReadInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentReadResult]:
        target = value.target
        result = await self.call(
            [
                "read",
                target.handle,
                "--machine",
                target.machine,
                "--max-bytes",
                str(value.maxBytes),
            ],
            WireReadResult,
        )
        if isinstance(result, WireFailure):
            self._failure(result, target=target)
        return HandlerSuccess(_output(target, result), actual_attempts=1)

    async def start(
        self, value: AgentStartInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStartResult]:
        stored = await self._actions.get(self._effect_id(context))
        if stored is None or stored.agent_placement.machine != value.machine:
            raise RuntimeError("start lacks its captured machine")
        machine_id = stored.agent_placement.machine_id
        argv = [
            "start",
            *([] if value.name is None else [value.name]),
            "--machine-id",
            machine_id,
            "--profile",
            value.profile,
        ]
        for flag, item in (
            ("cwd", value.cwd),
            ("group", value.group),
            ("model", value.model),
            ("effort", value.effort),
        ):
            if item is not None:
                argv += ["--" + flag, item]
        result = await self.call(argv, WireStartResult, write=True)
        projected = await self._receipt(
            "start", value, result, context, machine_id=machine_id
        )
        assert isinstance(projected, AgentStartResult)
        return HandlerSuccess(projected, actual_attempts=1)

    async def _write(
        self,
        operation: str,
        value: AgentTargetInput,
        context: ExecutionContext,
        *,
        text: str | None = None,
        keys: tuple[str, ...] = (),
    ) -> HandlerSuccess[AgentControlResult]:
        captured = await self._target(value, context)
        argv = [operation, "--ref", captured.ref]
        if text is not None:
            argv += ["--stdin"]
        argv += list(keys)
        result = await self.call(argv, AgentWriteResult, text=text, write=True)
        projected = await self._receipt(operation, value, result, context)
        assert isinstance(projected, AgentControlResult)
        return HandlerSuccess(projected, actual_attempts=1)

    async def send(
        self, value: AgentSendInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentControlResult]:
        return await self._write("send", value, context, text=value.text)

    async def text(
        self, value: AgentSendInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentControlResult]:
        return await self._write("text", value, context, text=value.text)

    async def keys(
        self, value: AgentKeysInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentControlResult]:
        return await self._write("keys", value, context, keys=value.keys)

    async def stop(
        self, value: AgentStopInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentControlResult]:
        return await self._write("stop", value, context)

    async def close(
        self, value: AgentCloseInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCloseResult]:
        captured = await self._target(value, context)
        result = await self.call(
            [
                "close",
                "--ref",
                captured.ref,
                *(["--terminal-only"] if value.terminal_only else []),
            ],
            WireTerminalClose if value.terminal_only else AgentCloseReceipt,
            write=True,
        )
        receipt = (
            AgentCloseReceipt(interrupt="not_sent", terminal=result.terminal)
            if isinstance(result, WireTerminalClose)
            else result
        )
        projected = await self._receipt("close", value, receipt, context)
        assert isinstance(projected, AgentCloseResult)
        return HandlerSuccess(projected, actual_attempts=1)

    async def delegate(
        self, value: AgentDelegateInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentDelegateReceipt]:
        receipt = await self._actions.register_delegation(self._effect_id(context))
        return HandlerSuccess(receipt, actual_attempts=0)

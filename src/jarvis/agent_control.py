"""Fixed skid subprocesses, private captured refs, and durable observation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast
from uuid import UUID

from llm_agent_kernel import CancellationToken
from llm_tools import (
    DeclaredToolFailure,
    ExecutionContext,
    FrozenToolPlan,
    HandlerSuccess,
    ParsedJson,
    ToolId,
    raw_input_digest,
)
from pydantic import BaseModel

from jarvis.agent_tools import (
    AGENT_CALL_SECONDS,
    AGENT_CONTROL_LIMIT_BYTES,
    AGENT_INVENTORY_LIMIT_BYTES,
    AGENT_WAIT_CHUNK_SECONDS,
    AgentActionEvidence,
    AgentCancelWaitInput,
    AgentCancelWaitResult,
    AgentCloseInput,
    AgentCloseReceipt,
    AgentCloseResult,
    AgentControlResult,
    AgentError,
    AgentInfoInput,
    AgentInfoResult,
    AgentInspectResult,
    AgentKeysInput,
    AgentLabel,
    AgentListInput,
    AgentListResult,
    AgentPeerResult,
    AgentReadInput,
    AgentReadResult,
    AgentSendInput,
    AgentSendResult,
    AgentSessionResult,
    AgentStartInput,
    AgentStartResult,
    AgentStopInput,
    AgentTarget,
    AgentTargetInput,
    AgentWaitInput,
    AgentWaitOutcome,
    AgentWaitReceipt,
    AgentWriteResult,
    AgentWriteTarget,
    ObservedSession,
    WireFailure,
    WireInventory,
    WireReadResult,
    WireStartResult,
    WireTerminalClose,
    WireWaitResult,
)

if TYPE_CHECKING:
    from jarvis.actions import ActionStore, StoredAction


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
        if observed.label != value.machine or (observed.prompt == "not_requested") != (
            value.prompt is None
        ):
            raise ValueError("launch receipt differs from request")
        projected = AgentStartResult(
            machine=observed.label,
            target=None
            if observed.handle is None
            else AgentTarget(machine=observed.label, handle=observed.handle),
            captured=observed.target is not None,
            creation=observed.creation,
            prompt=observed.prompt,
            failure=None if observed.failure is None else observed.failure.code,
        )
        if observed.creation == "unknown" or observed.prompt == "unknown":
            return None
        if (
            observed.creation != "created"
            or observed.prompt == "not_sent"
            or observed.failure is not None
        ):
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
    if (observed.method == "native") != value.target.native or (
        observed.method == "native" and operation != "stop"
    ):
        raise ValueError("write receipt differs from target or operation")
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


def _session(machine: AgentLabel, value: object) -> AgentSessionResult:
    from jarvis.agent_tools import AgentTerminal

    row = AgentTerminal.model_validate(value)
    return AgentSessionResult(
        target=AgentTarget(machine=machine, handle=row.terminalHandle),
        conversation=None
        if row.conversationHandle is None
        else AgentTarget(machine=machine, handle=row.conversationHandle),
        name=row.name,
        provider=None if row.agent is None else row.agent.provider,
        profile=None if row.agent is None else row.agent.profile,
        group=row.group,
        cwd=row.cwd,
        status=row.terminalStatus,
    )


def _output(target: AgentTarget, value: WireReadResult) -> AgentReadResult:
    if (value.source == "native") != target.native:
        raise ValueError("read substituted target kind")
    return AgentReadResult(
        target=target,
        text=value.text,
        source=value.source,
        scope=value.scope,
        truncated=value.truncated,
        outputState=value.outputState,
        status=None if value.observation is None else value.observation.status,
    )


class AgentController:
    def __init__(
        self,
        *,
        cli_path: Path,
        client_config_path: Path,
        actions: ActionStore,
        source_conversation_id: str,
    ) -> None:
        if not cli_path.is_absolute() or not client_config_path.is_absolute():
            raise ValueError(
                "agent CLI and client configuration paths must be absolute"
            )
        self.cli_path = cli_path
        self.client_config_path = client_config_path
        self._actions = actions
        self.source_conversation_id = source_conversation_id
        self._wait_changed = asyncio.Event()

    async def _call[T: BaseModel](
        self,
        argv: list[str],
        model: type[T],
        *,
        text: str | None = None,
        write: bool = False,
        inventory: bool = False,
    ) -> T | WireFailure:
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.cli_path),
                "--config",
                str(self.client_config_path),
                *argv,
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
            async with asyncio.timeout(AGENT_CALL_SECONDS):
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
                decoded = _closed_json(await stdout_task)
                if not isinstance(decoded, dict):
                    raise ValueError("invalid skid envelope")
                value = cast(dict[str, object], decoded)
                if type(value.get("ok")) is not bool:
                    raise ValueError("invalid skid envelope")
                if value["ok"]:
                    if set(value) != {"ok", "result"}:
                        raise ValueError("invalid skid success envelope")
                    return model.model_validate(value["result"])
                if set(value) != {"ok", "error"}:
                    raise ValueError("invalid skid failure envelope")
                return WireFailure.model_validate(value["error"])
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
        if target.native:
            if str(tool_id) in {"agent.text", "agent.keys", "agent.close"}:
                raise ValueError("terminal operation requires t- handle")
            deadline = asyncio.get_running_loop().time() + AGENT_CALL_SECONDS
            observed = await self._call(
                ["inspect", target.handle, "--machine", target.machine],
                AgentInspectResult,
            )
            if (
                isinstance(observed, WireFailure)
                or not observed.inspection.ok
                or observed.label != target.machine
            ):
                raise ValueError("native capture unavailable")
            name = None
            try:
                async with asyncio.timeout_at(deadline):
                    inventory = await self._call(
                        ["list", "--machine", target.machine],
                        WireInventory,
                        inventory=True,
                    )
                if not isinstance(inventory, WireFailure):
                    matches = [
                        row
                        for peer in inventory.peers
                        if peer.ok
                        and peer.label == target.machine
                        and peer.machine == observed.machine
                        for row in peer.sessions or ()
                        if row.conversation == observed.target.conversation
                    ]
                    if len(matches) == 1:
                        name = matches[0].name
            except TimeoutError:
                # Optional display metadata cannot revoke the native capture.
                pass
            return AgentWriteTarget(
                target=target,
                ref=observed.target.ref,
                name=name,
                profile=observed.target.conversation.profileKey,
                conversation=observed.target.conversation,
                turn=observed.target.turn,
            )
        observed = await self._call(
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

    async def _target(
        self, value: AgentTargetInput, context: ExecutionContext
    ) -> AgentWriteTarget:
        stored = await self._actions.get(self._effect_id(context))
        if stored is None or stored.execution_contract.agent_target is None:
            raise RuntimeError("addressed action lacks captured target")
        captured = stored.execution_contract.agent_target
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
    ) -> AgentStartResult | AgentControlResult | AgentCloseResult:
        try:
            projected = classify_agent_receipt(operation, value, observed)
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
        result = await self._call(argv, WireInventory, inventory=True)
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
        if target.native:
            result = await self._call(
                ["inspect", target.handle, "--machine", target.machine],
                AgentInspectResult,
            )
            if isinstance(result, WireFailure):
                self._failure(result, target=target)
            if result.label != target.machine:
                raise ValueError("inspection substituted machine")
            current = result.inspection.result
            projected = AgentInfoResult(
                target=target,
                provider=result.target.conversation.provider,
                profile=result.target.conversation.profileKey,
                status=None if current is None else current.status,
                methods=None if current is None else current.methods,
                failure=None
                if result.inspection.error is None
                else result.inspection.error.code,
            )
        else:
            result = await self._call(
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
        result = await self._call(
            [
                "read",
                target.handle,
                "--machine",
                target.machine,
                "--max-bytes",
                str(value.maxBytes),
                *(["--history"] if value.source == "history" else []),
            ],
            WireReadResult,
        )
        if isinstance(result, WireFailure):
            self._failure(result, target=target)
        return HandlerSuccess(_output(target, result), actual_attempts=1)

    async def start(
        self, value: AgentStartInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStartResult]:
        argv = [
            "start",
            *([] if value.name is None else [value.name]),
            "--machine",
            value.machine,
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
        if value.prompt is not None:
            argv += ["--stdin"]
        result = await self._call(argv, WireStartResult, text=value.prompt, write=True)
        projected = await self._receipt("start", value, result, context)
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
        native = value.target.native
        if operation in {"text", "keys"} and native:
            raise DeclaredToolFailure(
                AgentError(
                    code="wrong_target_kind", dispatch="not_sent", target=value.target
                ),
                actual_attempts=0,
            )
        argv = [operation, "--ref", captured.ref]
        if text is not None:
            argv += ["--stdin"]
        if operation == "send" and native:
            argv += ["--input", "peer"]
        argv += list(keys)
        model = AgentSendResult if operation == "send" and native else AgentWriteResult
        result = await self._call(argv, model, text=text, write=True)
        if isinstance(result, AgentSendResult):
            projected = AgentControlResult(
                target=value.target, method=result.method, outcome=result.outcome
            )
        else:
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
        result = await self._call(
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

    async def wait(
        self, value: AgentWaitInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWaitReceipt]:
        await self._target(value, context)
        now = datetime.now(UTC)
        return HandlerSuccess(
            AgentWaitReceipt(
                action_id=self._effect_id(context),
                target=value.target,
                state=value.state,
                deadline=now + timedelta(seconds=value.timeout_seconds),
                recorded_at=now,
                arguments_digest=raw_input_digest(
                    ParsedJson(value.model_dump(mode="json"))
                ),
            ),
            actual_attempts=0,
        )

    async def cancel_wait(
        self, value: AgentCancelWaitInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCancelWaitResult]:
        target = await self._actions.get(value.action_id)
        if target is None or str(target.tool_name) != "agent.wait":
            raise DeclaredToolFailure(
                AgentError(code="wait_not_found", dispatch="not_sent"),
                actual_attempts=0,
            )
        cancelled = await self._actions.cancel_agent_wait(
            value.action_id,
            cancellation_action_id=self._effect_id(context),
            source_conversation_id=self.source_conversation_id,
        )
        return HandlerSuccess(
            AgentCancelWaitResult(
                action_id=value.action_id,
                outcome="cancelled" if cancelled else "already_settled",
            ),
            actual_attempts=0,
        )

    async def observe_wait(self, stored: StoredAction) -> AgentWaitOutcome | None:
        from jarvis.actions import agent_wait_state

        state = agent_wait_state(stored)
        request = AgentWaitInput.model_validate(stored.arguments)
        captured = stored.execution_contract.agent_target
        if captured is None:
            raise RuntimeError("wait lacks immutable target")
        now = datetime.now(UTC)
        remaining = (state.registration_receipt.deadline - now).total_seconds()
        if remaining <= 0:
            return AgentWaitOutcome(
                target=request.target, outcome="timeout", recorded_at=now
            )
        result = await self._call(
            [
                "wait",
                "--ref",
                captured.ref,
                "--state",
                request.state,
                "--timeout",
                f"{min(AGENT_WAIT_CHUNK_SECONDS, remaining):.6f}s",
            ],
            WireWaitResult,
        )
        if isinstance(result, WireFailure):
            return AgentWaitOutcome(
                target=request.target,
                outcome="unavailable",
                recorded_at=datetime.now(UTC),
                failure=result.code,
            )
        if result.target != captured.ref or (
            result.observation is not None
            and result.observation.binding.conversation != captured.conversation
        ):
            raise RuntimeError("wait substituted captured target")
        if (request.target.native and result.terminalStatus is not None) or (
            not request.target.native and result.observation is not None
        ):
            raise RuntimeError("wait substituted target kind")
        if (
            result.outcome == "timeout"
            and datetime.now(UTC) < state.registration_receipt.deadline
        ):
            return None
        output = None
        failure = None
        if result.outcome == "matched":
            read = await self._call(
                ["read", "--ref", captured.ref, "--max-bytes", str(request.maxBytes)],
                WireReadResult,
            )
            if isinstance(read, WireFailure):
                failure = read.code
            else:
                output = _output(request.target, read)
        return AgentWaitOutcome(
            target=request.target,
            outcome=result.outcome,
            recorded_at=datetime.now(UTC),
            status=None if result.observation is None else result.observation.status,
            terminalStatus=result.terminalStatus,
            output=output,
            failure=failure,
        )

    def notify_wait_changed(self) -> None:
        self._wait_changed.set()

    async def run_waits(
        self,
        cancellation: CancellationToken,
        *,
        paused: Callable[[], Awaitable[bool]],
        plan: FrozenToolPlan,
        on_event: Callable[[], None],
    ) -> None:
        from jarvis.write_dispatch import require_current_action_binding

        tasks: dict[UUID, tuple[asyncio.Task[None], CancellationToken]] = {}
        try:
            if await self._actions.publish_agent_wait_events(
                source_conversation_id=self.source_conversation_id
            ):
                on_event()
            while not cancellation.cancelled:
                self._wait_changed.clear()
                for action_id, (task, _) in tuple(tasks.items()):
                    if task.done():
                        task.result()
                        del tasks[action_id]
                inactive = await paused()
                active = () if inactive else await self._actions.active_agent_waits()
                selected = {value.id for value in active}
                for action_id, (_, token) in tasks.items():
                    if action_id not in selected:
                        token.cancel()
                for stored in active:
                    if stored.id not in tasks:
                        require_current_action_binding(stored, plan)
                        token = CancellationToken()
                        tasks[stored.id] = (
                            asyncio.create_task(
                                self._watch_wait(stored.id, token, on_event),
                                name=f"jarvis-agent-wait-{stored.id}",
                            ),
                            token,
                        )
                changed = asyncio.create_task(self._wait_changed.wait())
                stopped = asyncio.create_task(cancellation.wait())
                elapsed = asyncio.create_task(asyncio.sleep(5))
                try:
                    await asyncio.wait(
                        {changed, stopped, elapsed}, return_when=asyncio.FIRST_COMPLETED
                    )
                finally:
                    for task in (changed, stopped, elapsed):
                        task.cancel()
                    await asyncio.gather(
                        changed, stopped, elapsed, return_exceptions=True
                    )
        finally:
            for _, token in tasks.values():
                token.cancel()
            results = await asyncio.gather(
                *(task for task, _ in tasks.values()), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    async def _watch_wait(
        self,
        action_id: UUID,
        cancellation: CancellationToken,
        on_event: Callable[[], None],
    ) -> None:
        while not cancellation.cancelled:
            stored = await self._actions.get(action_id)
            if stored is None or stored.status != "queued":
                return
            observe = asyncio.create_task(self.observe_wait(stored))
            stopped = asyncio.create_task(cancellation.wait())
            try:
                done, _ = await asyncio.wait(
                    {observe, stopped}, return_when=asyncio.FIRST_COMPLETED
                )
                if stopped in done:
                    # Only read-only CLI processes, never database work.
                    observe.cancel()
                    await asyncio.gather(observe, return_exceptions=True)
                    return
                outcome = observe.result()
            finally:
                if not observe.done():
                    observe.cancel()
                    await asyncio.gather(observe, return_exceptions=True)
                stopped.cancel()
                await asyncio.gather(stopped, return_exceptions=True)
            if outcome is not None:
                if await self._actions.finish_agent_wait(
                    action_id,
                    outcome,
                    source_conversation_id=self.source_conversation_id,
                ):
                    on_event()
                return

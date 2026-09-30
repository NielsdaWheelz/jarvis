"""Fixed skid CLI calls; refs and gateway race validation remain skid-owned."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID

from llm_tools import DeclaredToolFailure, ExecutionContext, HandlerSuccess, ToolId
from pydantic import BaseModel

from jarvis.agent_tools import (
    AGENT_CALL_SECONDS,
    AGENT_CONTROL_LIMIT_BYTES,
    AGENT_INVENTORY_LIMIT_BYTES,
    AgentActionEvidence,
    AgentCloseInput,
    AgentCloseReceipt,
    AgentCloseResult,
    AgentError,
    AgentInfoInput,
    AgentInfoResult,
    AgentInspectResult,
    AgentKeysInput,
    AgentListInput,
    AgentListResult,
    AgentReadInput,
    AgentReadResult,
    AgentSendInput,
    AgentSendResult,
    AgentStartInput,
    AgentStartResult,
    AgentStopInput,
    AgentTerminalCloseResult,
    AgentWriteResult,
    AgentWriteTarget,
    WireFailure,
    validate_agent_success,
)

if TYPE_CHECKING:
    from jarvis.actions import ActionStore


class AgentOutcomeUnknown(RuntimeError):
    """An entered BilledOnce command has no replay-safe absence proof."""


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

    return json.loads(raw, object_pairs_hook=object_pairs)


class AgentController:
    def __init__(
        self, *, cli_path: Path, client_config_path: Path, actions: ActionStore
    ) -> None:
        if not cli_path.is_absolute() or not client_config_path.is_absolute():
            raise ValueError(
                "agent CLI and client configuration paths must be absolute"
            )
        self.cli_path = cli_path
        self.client_config_path = client_config_path
        self._actions = actions

    async def _call[T: BaseModel](
        self,
        argv: list[str],
        model: type[T],
        *,
        text: str | None = None,
        write: bool = False,
        inventory: bool = False,
    ) -> T | AgentError:
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
            return AgentError(code="unavailable", dispatch="not_sent")
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
                        # Early stdin closure does not erase an owned receipt.
                        pass
                    finally:
                        process.stdin.close()
                stdout = await stdout_task
                # A valid owned envelope outranks rc: partial and unconfirmed
                # results deliberately exit nonzero.
                decoded = _closed_json(stdout)
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
                failure = WireFailure.model_validate(value["error"])
                return AgentError(**failure.model_dump(exclude_none=True))
        except (TimeoutError, ValueError, OSError) as exc:
            if write:
                raise AgentOutcomeUnknown(
                    "write outcome unknown; not replayed"
                ) from exc
            return AgentError(code="unavailable", dispatch="not_sent")
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

    async def _stage(
        self,
        context: ExecutionContext,
        observed: AgentError | AgentWriteResult | AgentCloseReceipt,
    ) -> None:
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("agent Write requires its durable action position")
        task = asyncio.create_task(
            self._actions.stage_agent_control(
                action_id=UUID(str(context.effect_id)),
                evidence=AgentActionEvidence(observed=observed),
            )
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def locate(
        self,
        tool_id: ToolId,
        value: AgentSendInput | AgentKeysInput | AgentStopInput | AgentCloseInput,
    ) -> AgentWriteTarget:
        native = str(tool_id) == "agent.send" or (
            isinstance(value, AgentStopInput) and value.mode == "native"
        )
        compound = (
            isinstance(value, AgentCloseInput)
            and value.scope == "conversation_and_terminal"
        )
        captured = None
        if native or compound:
            captured = await self._call(
                ["inspect", "--ref", value.ref], AgentInspectResult
            )
            if isinstance(captured, AgentError):
                raise ValueError("captured conversation inspection unavailable")
            assert isinstance(captured, AgentInspectResult)
            if captured.target.ref != value.ref:
                raise ValueError("inspection substituted original reference")
            if native and not captured.inspection.ok:
                raise ValueError("native target inspection unavailable")
        # Optional matching-terminal identity grounds an owner request by name.
        # Missing or reassociated terminals cannot erase conversation authority.
        observed = await self._call(["info", "--ref", value.ref], AgentStartResult)
        terminal = None
        if isinstance(observed, AgentError):
            if not native:
                raise ValueError("exact terminal inspection unavailable")
        elif native:
            assert captured is not None
            runtime = observed.session.conversation
            if (
                runtime is not None
                and runtime.binding.conversation == captured.target.conversation
            ):
                terminal = observed
        else:
            terminal = observed
        if captured is not None:
            machine = captured.label
        else:
            assert terminal is not None
            machine = terminal.label
        return AgentWriteTarget(
            machine=machine,
            ref=value.ref,
            name=None if terminal is None else terminal.session.name,
            pane=None if terminal is None else terminal.session.activePaneId,
            conversation=None if captured is None else captured.target.conversation,
            turn=None if captured is None else captured.target.turn,
        )

    async def _execute[T: BaseModel](
        self,
        argv: list[str],
        model: type[T],
        *,
        context: ExecutionContext | None = None,
        text: str | None = None,
        inventory: bool = False,
        arguments: dict[str, object] | None = None,
    ) -> HandlerSuccess[T]:
        value = await self._call(
            argv, model, text=text, write=context is not None, inventory=inventory
        )
        if isinstance(value, AgentError):
            if context is not None and (
                value.dispatch == "unknown" or value.conversation is not None
            ):
                await self._stage(context, value)
                raise AgentOutcomeUnknown(
                    "write outcome unknown or partial; not replayed"
                )
            raise DeclaredToolFailure(value, actual_attempts=1)
        if context is not None:
            assert arguments is not None
            validate_agent_success(argv[0], arguments, value)
        if context is not None and (
            (isinstance(value, AgentWriteResult) and value.outcome == "unknown")
            or (
                isinstance(value, AgentCloseReceipt)
                and (value.terminal == "unconfirmed" or value.agent == "unconfirmed")
            )
        ):
            await self._stage(context, value)
            raise AgentOutcomeUnknown("write outcome unconfirmed; not replayed")
        return HandlerSuccess(value, actual_attempts=1)

    async def list(
        self, value: AgentListInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentListResult]:
        return await self._execute(
            ["list", *([] if value.machine is None else ["--machine", value.machine])],
            AgentListResult,
            inventory=True,
        )

    async def info(
        self, value: AgentInfoInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentInfoResult]:
        model = AgentStartResult if value.target == "terminal" else AgentInspectResult
        result = await self._execute(
            ["info" if value.target == "terminal" else "inspect", "--ref", value.ref],
            model,
        )
        return HandlerSuccess(
            AgentInfoResult(
                target=value.target,
                terminal=result.value
                if isinstance(result.value, AgentStartResult)
                else None,
                conversation=result.value
                if isinstance(result.value, AgentInspectResult)
                else None,
            ),
            actual_attempts=1,
        )

    async def read(
        self, value: AgentReadInput, context: ExecutionContext | None = None
    ) -> HandlerSuccess[AgentReadResult]:
        return await self._execute(
            [
                "read",
                "--ref",
                value.ref,
                "--max-bytes",
                str(value.maxBytes),
                *([] if value.source == "latest" else ["--" + value.source]),
            ],
            AgentReadResult,
        )

    async def start(
        self, value: AgentStartInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentStartResult]:
        return await self._execute(
            [
                "start",
                value.name,
                "--machine",
                value.machine,
                "--profile",
                value.profile,
                *([] if value.cwd is None else ["--cwd", value.cwd]),
            ],
            AgentStartResult,
            context=context,
            arguments=value.model_dump(mode="json"),
        )

    async def send(
        self, value: AgentSendInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentSendResult]:
        return await self._execute(
            ["send", "--ref", value.ref, "--input", "peer", "--stdin"],
            AgentSendResult,
            context=context,
            arguments=value.model_dump(mode="json"),
            text=value.text,
        )

    async def text(
        self, value: AgentSendInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._execute(
            ["text", "--ref", value.ref, "--stdin"],
            AgentWriteResult,
            context=context,
            arguments=value.model_dump(mode="json"),
            text=value.text,
        )

    async def keys(
        self, value: AgentKeysInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._execute(
            ["keys", "--ref", value.ref, *value.keys],
            AgentWriteResult,
            context=context,
            arguments=value.model_dump(mode="json"),
        )

    async def stop(
        self, value: AgentStopInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentWriteResult]:
        return await self._execute(
            [
                "stop",
                "--ref",
                value.ref,
                *(["--terminal"] if value.mode == "terminal" else []),
            ],
            AgentWriteResult,
            context=context,
            arguments=value.model_dump(mode="json"),
        )

    async def close(
        self, value: AgentCloseInput, context: ExecutionContext
    ) -> HandlerSuccess[AgentCloseReceipt]:
        # CLI shape differs by explicit scope; the tool receipt makes that sum closed.

        model = (
            AgentTerminalCloseResult
            if value.scope == "terminal_only"
            else AgentCloseResult
        )
        value_result = await self._call(
            [
                "close",
                "--ref",
                value.ref,
                *(["--terminal-only"] if value.scope == "terminal_only" else []),
            ],
            model,
            write=True,
        )
        if isinstance(value_result, AgentError):
            if value_result.dispatch == "unknown":
                await self._stage(context, value_result)
                raise AgentOutcomeUnknown("write outcome unknown; not replayed")
            raise DeclaredToolFailure(value_result, actual_attempts=1)
        receipt = AgentCloseReceipt.model_validate(
            value_result.model_dump(exclude_none=True)
        )
        validate_agent_success("close", value.model_dump(mode="json"), receipt)
        if receipt.terminal == "unconfirmed" or receipt.agent == "unconfirmed":
            await self._stage(context, receipt)
            raise AgentOutcomeUnknown(
                "terminal closure or conversation halt unconfirmed; not replayed"
            )
        return HandlerSuccess(receipt, actual_attempts=1)

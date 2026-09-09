"""Jarvis composition of native Codex controls and the host's closed launcher."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Never, cast
from uuid import UUID

from llm_tools import (
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    canonical_json_bytes,
)
from provider_runtime.agent_runtime import codex_control as native
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from jarvis.codex_tools import (
    CODEX_MAX_MESSAGE_BYTES,
    CodexAccepted,
    CodexActionEvidence,
    CodexBounded,
    CodexComplete,
    CodexFinished,
    CodexInterrupted,
    CodexInterruptInput,
    CodexInterruptResult,
    CodexListInput,
    CodexListResult,
    CodexNoPrefix,
    CodexPartial,
    CodexPrefix,
    CodexProfile,
    CodexPromptInput,
    CodexReadInput,
    CodexReadResult,
    CodexRejected,
    CodexStage,
    CodexStale,
    CodexStarted,
    CodexStartInput,
    CodexSteer,
    CodexTerminal,
    CodexTerminalPrefix,
    CodexThreadPrefix,
    CodexThreadSummary,
    CodexThreadTarget,
    CodexTurnPrefix,
    CodexTurnSnapshot,
    CodexTurnTarget,
)

if TYPE_CHECKING:
    from jarvis.actions import ActionStore


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class _Profile(_Closed):
    account_home: str
    endpoint: str
    work_roots: tuple[str, ...] = Field(min_length=1)


class _Package(_Closed):
    name: Literal["@openai/codex"]
    integrity: str = Field(pattern=r"^sha512-[A-Za-z0-9+/]{86}==$")
    shasum: str = Field(pattern=r"^[0-9a-f]{40}$")


class CodexHostConfig(_Closed):
    """Read-only non-secret host mapping; never credential or worker state."""

    schema_version: Literal[1]
    version: Literal["0.153.4"]
    package: _Package
    development_user: str
    jarvis_user: str
    client_group: str
    binary: str
    tmux: str
    cognition_cwd_parent: str
    launcher_socket: str
    profiles: dict[CodexProfile, _Profile]

    @property
    def endpoints(self) -> dict[str, Path]:
        return {key: Path(row.endpoint[7:]) for key, row in self.profiles.items()}

    @classmethod
    def load(cls, path: Path) -> CodexHostConfig:
        with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_mode & 0o022
            ):
                raise ValueError(
                    "Codex host mapping must be root-owned and not writable by clients"
                )
            encoded = source.read(CODEX_MAX_MESSAGE_BYTES + 1)
        if len(encoded) > CODEX_MAX_MESSAGE_BYTES:
            raise ValueError("Codex host mapping is oversized")
        result = cls.model_validate(_decode(encoded))
        if set(result.profiles) != {"personal", "work", "work2"}:
            raise ValueError("Codex host mapping must declare all three profiles")
        paths = [
            result.binary,
            result.tmux,
            result.cognition_cwd_parent,
            result.launcher_socket,
        ]
        for row in result.profiles.values():
            if not row.endpoint.startswith("unix:///"):
                raise ValueError("Codex host endpoint must be a Unix socket")
            paths.extend((row.account_home, row.endpoint[7:], *row.work_roots))
        if any(not _absolute(value) for value in paths):
            raise ValueError("Codex host mapping has a noncanonical path")
        if len(set(result.endpoints.values())) != 3:
            raise ValueError("Codex profiles must use distinct endpoints")
        return result


def _absolute(value: str) -> bool:
    return (
        value.startswith("/")
        and value != "/"
        and os.path.normpath(value) == value
        and not any(c in value for c in ("\x00", "\n"))
        and len(value.encode("utf-8")) <= 4096
    )


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    del value
    raise ValueError("non-JSON constant")


def _decode(encoded: bytes) -> object:
    return json.loads(
        encoded.decode("utf-8"),
        object_pairs_hook=_object,
        parse_constant=_invalid_constant,
    )


class _TerminalStarted(_Closed):
    kind: Literal["Started"]
    terminal: CodexTerminal


class _Resolved(_Closed):
    kind: Literal["Resolved"]
    cwd: str = Field(min_length=1, max_length=4096)


class _TerminalRejected(_Closed):
    kind: Literal["Rejected"]
    stage: Literal["validate"]
    reason: Literal["unauthorized", "invalid_request"]


class _TerminalUnknown(_Closed):
    kind: Literal["Unknown"]
    stage: Literal["create", "observe"]


type _TerminalResult = Annotated[
    _TerminalStarted | _TerminalRejected | _TerminalUnknown, Field(discriminator="kind")
]
_TERMINAL_RESULT: TypeAdapter[_TerminalResult] = TypeAdapter(_TerminalResult)
_RESOLVE_RESULT: TypeAdapter[_Resolved | _TerminalRejected] = TypeAdapter(
    _Resolved | _TerminalRejected
)


class _UnconfirmedControl(RuntimeError):
    """BilledOnce executor persists uncertainty; not a declared retryable error."""


class CodexController:
    def __init__(
        self,
        *,
        control: native.CodexControl,
        host: CodexHostConfig,
        actions: ActionStore,
    ) -> None:
        self._native = control
        self._host = host
        self._actions = actions

    @property
    def policy_fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(self._host.model_dump(mode="json"))
        ).hexdigest()

    async def _stage(
        self, context: ExecutionContext, stage: CodexStage, prefix: CodexPrefix
    ) -> None:
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("Codex Write requires its durable action position")
        write = asyncio.create_task(
            self._actions.stage_codex_control(
                action_id=UUID(str(context.effect_id)),
                evidence=CodexActionEvidence(stage=stage, prefix=prefix),
            )
        )
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            # Persist an already-observed prefix, then stop. No next native or
            # terminal operation is entered on this cancellation path.
            await write
            raise

    async def list(
        self, value: CodexListInput, context: ExecutionContext
    ) -> HandlerSuccess[CodexListResult]:
        del context
        try:
            result = await self._native.list(
                native.CodexListRequest(value.profile, value.cursor)
            )
        except native.CodexControlError as error:
            raise DeclaredToolFailure(_rejected(error), actual_attempts=1) from None
        return HandlerSuccess(
            CodexListResult(
                threads=tuple(_summary(row) for row in result.threads),
                next_cursor=result.next_cursor,
            ),
            actual_attempts=1,
        )

    async def read(
        self, value: CodexReadInput, context: ExecutionContext
    ) -> HandlerSuccess[CodexReadResult]:
        del context
        try:
            result = await self._native.read(_native_thread(value.thread))
        except native.CodexControlError as error:
            raise DeclaredToolFailure(_rejected(error), actual_attempts=1) from None
        coverage = (
            CodexComplete()
            if isinstance(result.coverage, native.CodexComplete)
            else CodexBounded(reason=result.coverage.reason)
        )
        turn = (
            None
            if result.turn is None
            else CodexTurnSnapshot(
                turn=_turn(result.turn.target), status=result.turn.status
            )
        )
        return HandlerSuccess(
            CodexReadResult(
                thread=_summary(result.thread),
                turn=turn,
                last_answer=result.last_answer,
                coverage=coverage,
            ),
            actual_attempts=1,
        )

    async def start(
        self, value: CodexStartInput, context: ExecutionContext
    ) -> HandlerSuccess[CodexStarted]:
        prefix: CodexPrefix = CodexNoPrefix()
        await self._stage(context, "resolve", prefix)
        try:
            resolved = _RESOLVE_RESULT.validate_python(
                await self._exchange(
                    {"kind": "ResolveCwd", "profile": value.profile, "cwd": value.cwd},
                    mutating=False,
                )
            )
        except ValueError:
            # Resolve is read-only; malformed resolution never reaches creation.
            raise DeclaredToolFailure(
                CodexRejected(reason="unavailable"), actual_attempts=1
            ) from None
        if isinstance(resolved, _TerminalRejected) or not _absolute(resolved.cwd):
            raise DeclaredToolFailure(
                CodexRejected(reason="invalid_input"), actual_attempts=1
            )
        value = value.model_copy(update={"cwd": resolved.cwd})
        await self._stage(context, "create", prefix)
        try:
            created = await self._native.create(
                native.CodexCreateRequest(value.profile, Path(value.cwd))
            )
        except native.CodexControlError as error:
            stage: CodexStage = "create"
            if error.known_thread is not None:
                prefix = CodexThreadPrefix(thread=_thread(error.known_thread))
                stage = "unsubscribe"
                await self._stage(context, stage, prefix)
            _write_error(error, stage, prefix, 2, partial_launch=True)
        thread = _thread(created)
        prefix = CodexThreadPrefix(thread=thread)
        await self._stage(context, "terminal", prefix)
        terminal = await self._launch(value, thread)
        if isinstance(terminal, _TerminalRejected):
            raise DeclaredToolFailure(
                CodexPartial(stage="terminal", prefix=prefix), actual_attempts=3
            )
        if isinstance(terminal, _TerminalUnknown):
            raise _UnconfirmedControl(
                "Codex terminal outcome unconfirmed; never repeat"
            )
        prefix = CodexTerminalPrefix(thread=thread, terminal=terminal.terminal)
        await self._stage(context, "submit", prefix)
        try:
            accepted = await self._native.prompt(
                native.CodexPromptRequest(created, native.CodexSubmit(value.prompt))
            )
        except native.CodexControlError as error:
            _write_error(error, "submit", prefix, 4, partial_launch=True)
        turn = _turn(accepted)
        await self._stage(
            context, "submit", CodexTurnPrefix(turn=turn, terminal=terminal.terminal)
        )
        return HandlerSuccess(
            CodexStarted(turn=turn, terminal=terminal.terminal), actual_attempts=4
        )

    async def _launch(
        self, value: CodexStartInput, thread: CodexThreadTarget
    ) -> _TerminalResult:
        try:
            result = _TERMINAL_RESULT.validate_python(
                await self._exchange(
                    {
                        "kind": "LaunchTerminal",
                        "profile": value.profile,
                        "thread_handle": thread.thread_handle,
                        "cwd": value.cwd,
                        "tmux_name": value.name,
                    },
                    mutating=True,
                )
            )
            if (
                isinstance(result, _TerminalStarted)
                and result.terminal.tmux_name != value.name
            ):
                raise ValueError("launcher returned a different terminal")
            return result
        except ValueError:
            raise _UnconfirmedControl(
                "Codex launcher response unconfirmed; never repeat"
            ) from None

    async def _exchange(self, fields: dict[str, str], *, mutating: bool) -> object:
        request = (
            json.dumps(
                fields,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if len(request) > CODEX_MAX_MESSAGE_BYTES:
            raise RuntimeError("validated Codex launcher request exceeds bound")
        writer: asyncio.StreamWriter | None = None
        sent = False
        try:
            async with asyncio.timeout(15):
                reader, writer = await asyncio.open_unix_connection(
                    self._host.launcher_socket, limit=CODEX_MAX_MESSAGE_BYTES
                )
                sent = True
                writer.write(request)
                await writer.drain()
                response = await reader.readuntil(b"\n")
                if len(response) > CODEX_MAX_MESSAGE_BYTES or await reader.read(1):
                    raise ValueError("launcher response framing invalid")
                return _decode(response)
        except (
            OSError,
            TimeoutError,
            ValueError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            if not sent or not mutating:
                return _TerminalRejected(
                    kind="Rejected", stage="validate", reason="invalid_request"
                ).model_dump(mode="json")
            raise _UnconfirmedControl(
                "Codex launcher response unconfirmed; never repeat"
            ) from None
        finally:
            if writer is not None:
                writer.close()
                # No additional drain or retry after the bounded exchange.

    async def prompt(
        self, value: CodexPromptInput, context: ExecutionContext
    ) -> HandlerSuccess[CodexAccepted]:
        stage: CodexStage = "steer" if isinstance(value.input, CodexSteer) else "submit"
        prefix: CodexPrefix = CodexThreadPrefix(thread=value.thread)
        if isinstance(value.input, CodexSteer):
            prefix = CodexTurnPrefix(
                turn=CodexTurnTarget(
                    thread=value.thread, turn_handle=value.input.turn_handle
                ),
                terminal=None,
            )
        await self._stage(context, stage, prefix)
        request = (
            native.CodexSteer(value.input.turn_handle, value.input.text)
            if isinstance(value.input, CodexSteer)
            else native.CodexSubmit(value.input.text)
        )
        try:
            accepted = await self._native.prompt(
                native.CodexPromptRequest(_native_thread(value.thread), request)
            )
        except native.CodexControlError as error:
            _write_error(error, stage, prefix, 1)
        turn = _turn(accepted)
        await self._stage(context, stage, CodexTurnPrefix(turn=turn, terminal=None))
        return HandlerSuccess(CodexAccepted(turn=turn), actual_attempts=1)

    async def interrupt(
        self, value: CodexInterruptInput, context: ExecutionContext
    ) -> HandlerSuccess[CodexInterruptResult]:
        prefix = CodexTurnPrefix(turn=value.turn, terminal=None)
        await self._stage(context, "interrupt", prefix)
        try:
            result = await self._native.interrupt(
                native.CodexTurnTarget(
                    _native_thread(value.turn.thread), value.turn.turn_handle
                )
            )
        except native.CodexControlError as error:
            _write_error(error, "interrupt", prefix, 1)
        if isinstance(result, native.CodexUnknown):
            raise _UnconfirmedControl("Codex interruption unconfirmed; never repeat")
        if isinstance(result, native.CodexInterrupted):
            outcome = CodexInterrupted(turn=value.turn)
        elif isinstance(result, native.CodexFinished):
            outcome = CodexFinished(turn=value.turn, native_status=result.native_status)
        else:
            outcome = CodexStale(turn=value.turn)
        return HandlerSuccess(CodexInterruptResult(outcome=outcome), actual_attempts=1)


def _native_thread(value: CodexThreadTarget) -> native.CodexThreadTarget:
    return native.CodexThreadTarget(value.profile, value.thread_handle)


def _thread(value: native.CodexThreadTarget) -> CodexThreadTarget:
    return CodexThreadTarget(
        profile=cast(CodexProfile, value.profile_key), thread_handle=value.thread_handle
    )


def _turn(value: native.CodexTurnTarget) -> CodexTurnTarget:
    return CodexTurnTarget(thread=_thread(value.thread), turn_handle=value.turn_handle)


def _summary(value: native.CodexThreadSummary) -> CodexThreadSummary:
    return CodexThreadSummary(
        thread=_thread(value.target),
        status=value.status,
        active_flags=value.active_flags,
        name=value.name,
        cwd=value.cwd,
        source=value.source,
    )


def _rejected(error: native.CodexControlError) -> CodexRejected:
    return CodexRejected.model_validate(
        {
            "reason": {
                "invalid": "invalid_input",
                "unauthorized": "unauthorized",
                "missing": "not_found",
                "busy": "busy",
                "stale": "stale",
                "unavailable": "unavailable",
                "auth": "authentication",
                "quota": "quota",
                "output_limit": "output_limit",
            }[error.code]
        }
    )


def _write_error(
    error: native.CodexControlError,
    stage: CodexStage,
    prefix: CodexPrefix,
    attempts: int,
    *,
    partial_launch: bool = False,
) -> Never:
    if error.dispatch == "Unknown":
        raise _UnconfirmedControl(
            "Codex native outcome unconfirmed; never repeat"
        ) from None
    if not partial_launch or isinstance(prefix, CodexNoPrefix):
        raise DeclaredToolFailure(_rejected(error), actual_attempts=attempts) from None
    raise DeclaredToolFailure(
        CodexPartial(stage=stage, prefix=prefix), actual_attempts=attempts
    ) from None

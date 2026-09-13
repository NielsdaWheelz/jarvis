"""Read-only decoding of historical worker action results; no executable tools."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from llm_tools import ToolId
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

HISTORICAL_CODEX_WRITE_IDS = tuple(
    ToolId("codex." + verb) for verb in ("start", "prompt", "interrupt")
)

type CodexProfile = Literal["personal", "work", "work2"]
type CodexStage = Literal[
    "dispatch",
    "resolve",
    "create",
    "unsubscribe",
    "terminal",
    "submit",
    "steer",
    "interrupt",
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _canonical_handle(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError("native handle must be a full canonical UUID") from exc
    if str(parsed) != value:
        raise ValueError("native handle must be a full canonical UUID")
    return value


class CodexThreadTarget(_Closed):
    profile: CodexProfile
    thread_handle: str = Field(min_length=1, max_length=256)

    _canonical_thread = field_validator("thread_handle")(_canonical_handle)


class CodexTurnTarget(_Closed):
    thread: CodexThreadTarget
    turn_handle: str = Field(min_length=1, max_length=256)

    _canonical_turn = field_validator("turn_handle")(_canonical_handle)


class CodexTerminal(_Closed):
    tmux_session_id: str = Field(pattern=r"^\$[0-9]+$", max_length=32)
    tmux_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class CodexNoPrefix(_Closed):
    type: Literal["none"] = "none"


class CodexThreadPrefix(_Closed):
    type: Literal["thread"] = "thread"
    thread: CodexThreadTarget


class CodexTerminalPrefix(_Closed):
    type: Literal["terminal"] = "terminal"
    thread: CodexThreadTarget
    terminal: CodexTerminal


class CodexTurnPrefix(_Closed):
    type: Literal["turn"] = "turn"
    turn: CodexTurnTarget
    terminal: CodexTerminal | None


type CodexPrefix = Annotated[
    CodexNoPrefix | CodexThreadPrefix | CodexTerminalPrefix | CodexTurnPrefix,
    Field(discriminator="type"),
]


class CodexActionEvidence(_Closed):
    type: Literal["codex_control_v1"] = "codex_control_v1"
    stage: CodexStage
    prefix: CodexPrefix


class CodexPartial(_Closed):
    type: Literal["Partial"] = "Partial"
    stage: CodexStage
    prefix: CodexPrefix


class CodexUnknown(_Closed):
    type: Literal["Unknown"] = "Unknown"
    stage: CodexStage
    prefix: CodexPrefix


class CodexRejected(_Closed):
    type: Literal["Rejected"] = "Rejected"
    reason: Literal[
        "invalid_input",
        "unauthorized",
        "not_found",
        "busy",
        "stale",
        "unavailable",
        "authentication",
        "quota",
        "output_limit",
    ]


type CodexControlError = CodexRejected | CodexPartial | CodexUnknown
CODEX_CONTROL_ERROR: TypeAdapter[CodexControlError] = TypeAdapter(CodexControlError)


class CodexStarted(_Closed):
    type: Literal["Started"] = "Started"
    turn: CodexTurnTarget
    terminal: CodexTerminal


class CodexAccepted(_Closed):
    turn: CodexTurnTarget


class CodexInterrupted(_Closed):
    type: Literal["Interrupted"] = "Interrupted"
    turn: CodexTurnTarget


class CodexFinished(_Closed):
    type: Literal["Finished"] = "Finished"
    turn: CodexTurnTarget
    native_status: Literal["completed", "failed"]


class CodexStale(_Closed):
    type: Literal["Stale"] = "Stale"
    turn: CodexTurnTarget


type CodexTurnOutcome = Annotated[
    CodexInterrupted | CodexFinished | CodexStale, Field(discriminator="type")
]


class CodexInterruptResult(_Closed):
    outcome: CodexTurnOutcome

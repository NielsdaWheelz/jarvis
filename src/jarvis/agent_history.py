"""Read-only decoding of receipts stored by earlier agent generations; no tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HISTORICAL_AGENT_IMPLEMENTATION_REVISIONS = (
    "jarvis-agent-control-v1",
    "jarvis-agent-control-v2",
    "jarvis-agent-control-v3",
    "jarvis-agent-control-v4",
)
_SKID_HERDR_REVISION = "jarvis-agent-control-v4"

type HistoricalAgentMethod = Literal["native", "terminal", "unavailable"]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class HistoricalAgentStatus(_Closed):
    state: Literal["working", "blocked", "idle", "done", "failed", "stopped", "unknown"]
    source: Literal["native", "terminal", "unavailable"]
    reason: (
        Literal["permission", "input", "dialog", "provider_unavailable", "unrecognized"]
        | None
    ) = None


class HistoricalAgentMethods(_Closed):
    read: HistoricalAgentMethod
    send: HistoricalAgentMethod
    interrupt: HistoricalAgentMethod


class HistoricalTmuxTarget(_Closed):
    machine: str = Field(min_length=1, max_length=256)
    tmuxId: str = Field(pattern=r"^\$[0-9]+$", max_length=32)
    identityToken: str = Field(min_length=1, max_length=256)
    paneId: str = Field(pattern=r"^%[0-9]+$", max_length=32)
    pid: int = Field(gt=0, strict=True)
    startIdentity: str = Field(min_length=1, max_length=256)


class HistoricalTmuxSession(_Closed):
    tmuxId: str
    name: str
    cwd: str | None = None
    profile: str | None = None
    provider: Literal["Codex", "Claude"] | None = None
    target: HistoricalTmuxTarget | None = None
    status: HistoricalAgentStatus | None = None
    methods: HistoricalAgentMethods | None = None


class HistoricalTmuxStartResult(_Closed):
    """agent.start receipt of jarvis-agent-control-v1 and -v2."""

    observedAt: str
    session: HistoricalTmuxSession


class HistoricalProviderSession(_Closed):
    id: str | None = None
    name: str | None = None


class HistoricalAgentObservation(_Closed):
    provider: Literal["Codex", "Claude"]
    profile: str | None = None
    providerSession: HistoricalProviderSession | None = None
    status: HistoricalAgentStatus
    methods: HistoricalAgentMethods


class HistoricalFleetSession(_Closed):
    name: str
    ref: str = Field(min_length=1, max_length=4096)
    cwd: str | None = None
    activeCommand: str | None = None
    launchProfile: str | None = None
    attachedClients: int = Field(ge=0, strict=True)
    agent: HistoricalAgentObservation | None = None


class HistoricalFleetStartResult(_Closed):
    """agent.start receipt of jarvis-agent-control-v3."""

    label: str
    machine: str
    observedAt: str
    session: HistoricalFleetSession


class HistoricalAgentWriteResult(_Closed):
    method: Literal["native", "terminal"]
    outcome: Literal["accepted", "written", "interrupted", "finished", "unknown"]
    turnId: str | None = None


class HistoricalAgentStopResult(_Closed):
    agent: Literal["stopped", "interrupted", "idle", "unconfirmed"]
    terminal: Literal["closed", "unconfirmed"]
    reason: Literal["stale", "unavailable"] | None = None


class HistoricalAgentKillResult(_Closed):
    terminal: Literal["closed"]


class HistoricalAgentError(_Closed):
    type: Literal["AgentFailure"] = "AgentFailure"
    code: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    dispatch: Literal["not_sent", "unknown"]


class HistoricalAgentActionEvidence(_Closed):
    type: Literal["agent_control_v1"] = "agent_control_v1"
    observed: HistoricalAgentStopResult | HistoricalAgentWriteResult | None = None


class HistoricalHerdrStartResult(_Closed):
    """agent.start receipt of jarvis-agent-control-v4, the skid herdr cli."""

    label: str
    machine: str
    observedAt: str
    terminal: dict[str, object]
    launch: Literal["submitted"]
    dispatch: Literal["sent"]


class HistoricalHerdrWriteResult(_Closed):
    label: str
    machine: str
    method: Literal["terminal"]
    outcome: Literal["written", "unknown"]
    dispatch: Literal["sent", "unknown"]


class HistoricalHerdrStopResult(_Closed):
    label: str
    machine: str
    agent: Literal["interrupt_sent", "exited"]
    terminal: Literal["closed"]
    dispatch: Literal["sent"]


class HistoricalHerdrKillResult(_Closed):
    label: str
    machine: str
    terminal: Literal["closed"]
    dispatch: Literal["sent"]


class HistoricalHerdrError(_Closed):
    type: Literal["AgentFailure"] = "AgentFailure"
    code: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    message: str | None = None
    label: str | None = None
    machine: str | None = None
    dispatch: Literal["not_sent", "sent", "unknown"]
    partial: dict[str, object] | None = None


class HistoricalHerdrActionEvidence(_Closed):
    type: Literal["agent_control_v2"] = "agent_control_v2"
    observed: HistoricalHerdrWriteResult | HistoricalHerdrError | None = None


def historical_agent_success_type(revision: str, tool: str) -> type[BaseModel]:
    """The success receipt model one historical generation stored for one tool."""

    if revision not in HISTORICAL_AGENT_IMPLEMENTATION_REVISIONS:
        raise ValueError("revision is not a historical agent generation")
    herdr = revision == _SKID_HERDR_REVISION
    match tool:
        case "agent.start" if herdr:
            return HistoricalHerdrStartResult
        case "agent.send" | "agent.keys" | "agent.interrupt" if herdr:
            return HistoricalHerdrWriteResult
        case "agent.stop" if herdr:
            return HistoricalHerdrStopResult
        case "agent.kill" if herdr:
            return HistoricalHerdrKillResult
        case "agent.start" if revision == "jarvis-agent-control-v3":
            return HistoricalFleetStartResult
        case "agent.start":
            return HistoricalTmuxStartResult
        case "agent.send" | "agent.keys" | "agent.interrupt":
            return HistoricalAgentWriteResult
        case "agent.stop":
            return HistoricalAgentStopResult
        case "agent.kill" if revision == "jarvis-agent-control-v3":
            return HistoricalAgentKillResult
        case _:
            raise ValueError("historical agent generation has no such receipt")


def historical_agent_error_type(revision: str) -> type[BaseModel]:
    """The AgentFailure model one historical generation stored."""

    return (
        HistoricalHerdrError
        if revision == _SKID_HERDR_REVISION
        else HistoricalAgentError
    )


def historical_agent_evidence_type(revision: str) -> type[BaseModel]:
    """The staged control evidence model; recovery wrapped codex rows as v1."""

    return (
        HistoricalHerdrActionEvidence
        if revision == _SKID_HERDR_REVISION
        else HistoricalAgentActionEvidence
    )


__all__ = [
    "HISTORICAL_AGENT_IMPLEMENTATION_REVISIONS",
    "historical_agent_error_type",
    "historical_agent_evidence_type",
    "historical_agent_success_type",
]

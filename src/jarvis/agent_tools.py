"""Nine worker tools; current skid result shapes live at this boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from llm_tools import (
    Available,
    PolicyEpoch,
    PromptDocument,
    ReplayPolicy,
    ToolBinding,
    ToolEffect,
    ToolFamily,
    ToolId,
    ToolLimits,
    ToolSpec,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from jarvis.agent_control import AgentController

AGENT_READ_IDS = tuple(ToolId("agent." + verb) for verb in ("list", "info", "read"))
AGENT_WRITE_IDS = tuple(
    ToolId("agent." + verb)
    for verb in ("start", "send", "text", "keys", "stop", "close")
)
AGENT_INPUT_LIMIT_BYTES = 262_144
AGENT_CONTROL_LIMIT_BYTES = 65_536
AGENT_INVENTORY_LIMIT_BYTES = 1_048_576
AGENT_RAW_LIMIT_BYTES = 32_768
AGENT_CALL_SECONDS = 20.0
AGENT_DEADLINE_SECONDS = {
    verb: (
        65.0
        if verb in {"close", "send", "stop"}
        else 45.0
        if verb in {"text", "keys"}
        else 20.0
    )
    for verb in (
        "list",
        "info",
        "read",
        "start",
        "send",
        "text",
        "keys",
        "stop",
        "close",
    )
}
type AgentKey = Literal[
    "enter",
    "escape",
    "ctrl-c",
    "up",
    "down",
    "left",
    "right",
    "tab",
    "backspace",
    "page-up",
    "page-down",
]
type AgentProfile = Literal["personal", "work", "work2", "claude-work"]
AGENT_IMPLEMENTATION_REVISION = "jarvis-agent-control-v6"
AGENT_POLICY_EPOCH = "jarvis-agent-control-v4"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


type AgentReference = Annotated[str, Field(min_length=1, max_length=4096)]
type AgentLabel = Literal["macbook", "devbox", "arch"]
type AgentName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]


class AgentRefInput(_Closed):
    ref: AgentReference


class AgentInfoInput(AgentRefInput):
    target: Literal["terminal", "conversation"]


class AgentListInput(_Closed):
    machine: AgentLabel | None = None


class AgentReadInput(AgentRefInput):
    source: Literal["latest", "history", "terminal"]
    maxBytes: int = Field(default=16384, ge=1, le=32768, strict=True)


class AgentStartInput(_Closed):
    machine: AgentLabel
    profile: AgentProfile
    name: AgentName
    cwd: str | None = Field(default=None, min_length=1, max_length=4096)


class AgentSendInput(AgentRefInput):
    text: str = Field(min_length=1, max_length=32768)

    @field_validator("text")
    @classmethod
    def literal_text(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 32768 or "\x00" in value:
            raise ValueError("agent input exceeds its UTF-8 limit or contains NUL")
        return value


class AgentKeysInput(AgentRefInput):
    keys: tuple[AgentKey, ...] = Field(min_length=1, max_length=16)


class AgentStopInput(AgentRefInput):
    mode: Literal["native", "terminal"]


class AgentCloseInput(AgentRefInput):
    scope: Literal["conversation_and_terminal", "terminal_only"]


class Conversation(_Closed):
    provider: Literal["Codex", "Claude"]
    profileKey: str = Field(min_length=1)
    historyScope: str = Field(pattern=r"^[0-9a-f]{64}$")
    conversationId: str = Field(min_length=1)


class Turn(_Closed):
    id: str = Field(min_length=1)
    state: Literal["inProgress", "completed", "failed", "interrupted"]


class Binding(_Closed):
    conversation: Conversation


class Status(_Closed):
    state: Literal["working", "blocked", "idle", "done", "failed", "stopped", "unknown"]
    source: Literal["native", "unavailable"]

    @model_validator(mode="after")
    def unavailable_is_unknown(self) -> Status:
        if self.source == "unavailable" and self.state != "unknown":
            raise ValueError("unavailable status cannot claim activity")
        return self


class Methods(_Closed):
    read: Literal["native", "unavailable"]
    sendPeer: Literal["native", "unavailable"]
    sendUser: Literal["native", "unavailable"]
    queueUser: Literal["unavailable"]
    stop: Literal["native", "unavailable"]


class Observation(_Closed):
    binding: Binding
    status: Status
    turn: Turn | None = None


class ConversationRuntime(Observation):
    methods: Methods


class ProviderSession(_Closed):
    id: str | None = None
    name: str | None = None


class Agent(_Closed):
    provider: Literal["Codex", "Claude"]
    profile: str | None = None
    providerSession: ProviderSession | None = None


class Connection(_Closed):
    transport: Literal["ssh", "mosh"]
    id: str | None = None


class ExecutionAgent(_Closed):
    provider: str
    profile: str | None = None
    label: str | None = None


class Execution(_Closed):
    kind: str
    machine: str | None = None
    label: str | None = None
    cwd: str | None = None
    agent: ExecutionAgent | None = None


class AgentTerminal(_Closed):
    activePaneId: str
    name: str
    ref: AgentReference
    attachedClients: int = Field(ge=0, strict=True)
    cwd: str | None = None
    activeCommand: str | None = None
    launchProfile: str | None = None
    agent: Agent | None = None
    connection: Connection | None = None
    execution: Execution | None = None
    group: str | None = None
    conversation: ConversationRuntime | None = None


class AgentError(_Closed):
    type: Literal["AgentFailure"] = "AgentFailure"
    code: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    dispatch: Literal["not_sent", "unknown"]
    conversation: Conversation | None = None


class Profile(_Closed):
    key: str
    label: str
    provider: Literal["Codex", "Claude"]
    historyScope: str | None = None


class Peer(_Closed):
    label: str
    machine: str
    ok: bool = Field(strict=True)
    observedAt: str | None = None
    profiles: tuple[Profile, ...] | None = None
    sessions: tuple[AgentTerminal, ...] | None = None
    error: WireFailure | None = None

    @model_validator(mode="after")
    def observed_or_error(self) -> Peer:
        if self.ok != (self.error is None) or self.ok != (
            self.profiles is not None
            and self.sessions is not None
            and self.observedAt is not None
        ):
            raise ValueError("peer inventory is inconsistent")
        return self


class WireFailure(_Closed):
    code: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    dispatch: Literal["not_sent", "unknown"]
    conversation: Conversation | None = None


class AgentListResult(_Closed):
    partial: bool = Field(strict=True)
    peers: tuple[Peer, ...]

    @model_validator(mode="after")
    def partial_matches(self) -> AgentListResult:
        if self.partial != any(not item.ok for item in self.peers):
            raise ValueError("inventory partial flag is inconsistent")
        return self


class AgentStartResult(_Closed):
    label: str
    machine: str
    observedAt: str
    session: AgentTerminal


class CapturedTarget(_Closed):
    ref: AgentReference
    conversation: Conversation
    turn: Turn | None = None


class Inspection(_Closed):
    ok: bool = Field(strict=True)
    result: ConversationRuntime | None = None
    error: WireFailure | None = None

    @model_validator(mode="after")
    def outcome_matches(self) -> Inspection:
        if self.ok != (self.result is not None) or self.ok == (self.error is not None):
            raise ValueError("inspection outcome is inconsistent")
        return self


class AgentInspectResult(_Closed):
    label: str
    machine: str
    target: CapturedTarget
    inspection: Inspection
    observedRef: AgentReference | None = None

    @model_validator(mode="after")
    def captured_matches(self) -> AgentInspectResult:
        if (
            self.inspection.result is not None
            and self.inspection.result.binding.conversation != self.target.conversation
        ):
            raise ValueError("inspection substituted a conversation")
        if not self.inspection.ok and self.observedRef is not None:
            raise ValueError("failed inspection renewed a reference")
        return self


class AgentInfoResult(_Closed):
    target: Literal["terminal", "conversation"]
    terminal: AgentStartResult | None = None
    conversation: AgentInspectResult | None = None

    @model_validator(mode="after")
    def target_matches(self) -> AgentInfoResult:
        if self.target == "terminal":
            valid = self.terminal is not None and self.conversation is None
        else:
            valid = self.conversation is not None and self.terminal is None
        if not valid:
            raise ValueError("info projection differs from its target")
        return self


class AgentReadResult(_Closed):
    observation: Observation | None = None
    outputState: Literal["partial", "finalized", "unknown", "none"] | None = None
    outputId: str | None = None
    outputTurnId: str | None = None
    text: str
    source: Literal["native", "terminal"]
    scope: Literal["latest", "history", "terminal_history", "visible"]
    truncated: bool = Field(strict=True)


class AgentSendResult(_Closed):
    method: Literal["native"]
    input: Literal["peer"]
    delivery: Literal["direct"]
    outcome: Literal["accepted"]
    turnId: str = Field(min_length=1)


class AgentWriteResult(_Closed):
    method: Literal["terminal", "native"]
    outcome: Literal["written", "interrupted", "stopped", "finished", "unknown"]

    @model_validator(mode="after")
    def method_matches(self) -> AgentWriteResult:
        allowed = (
            {"written", "unknown"}
            if self.method == "terminal"
            else {"interrupted", "stopped", "finished", "unknown"}
        )
        if self.outcome not in allowed:
            raise ValueError("write method and outcome differ")
        return self


class AgentTerminalCloseResult(_Closed):
    terminal: Literal["closed", "unconfirmed"]


class AgentCloseResult(AgentTerminalCloseResult):
    agent: Literal["stopped", "interrupted", "finished", "unconfirmed"]
    reason: Literal["stale", "unavailable"] | None = None


class AgentCloseReceipt(AgentTerminalCloseResult):
    agent: Literal["stopped", "interrupted", "finished", "unconfirmed"] | None = None
    reason: Literal["stale", "unavailable"] | None = None


class AgentActionEvidence(_Closed):
    type: Literal["agent_control_v4"] = "agent_control_v4"
    observed: AgentError | AgentWriteResult | AgentCloseReceipt | None = None


class AgentWriteTarget(_Closed):
    machine: str
    name: str | None = None
    pane: str | None = None
    conversation: Conversation | None = None
    turn: Turn | None = None
    ref: AgentReference


def agent_error_type(operation: str) -> type[AgentError]:
    if operation not in AGENT_SUCCESS_TYPES:
        raise ValueError("unknown agent operation")
    return AgentError


def validate_agent_failure(operation: str, value: object) -> AgentError:
    return agent_error_type(operation).model_validate(value)


def validate_agent_evidence(operation: str, value: object) -> AgentActionEvidence:
    if operation not in AGENT_SUCCESS_TYPES:
        raise ValueError("unknown agent operation")
    evidence = AgentActionEvidence.model_validate(value)
    observed = evidence.observed
    if isinstance(observed, AgentCloseReceipt) and operation != "close":
        raise ValueError("foreign close evidence")
    if isinstance(observed, AgentWriteResult):
        if operation not in {"text", "keys", "stop"} or (
            operation != "stop" and observed.method != "terminal"
        ):
            raise ValueError("foreign write evidence")
    if (
        isinstance(observed, AgentError)
        and observed.conversation is not None
        and operation != "start"
    ):
        raise ValueError("foreign creation evidence")
    return evidence


AGENT_SUCCESS_TYPES: dict[str, type[BaseModel]] = {
    "list": AgentListResult,
    "info": AgentInfoResult,
    "read": AgentReadResult,
    "start": AgentStartResult,
    "send": AgentSendResult,
    "text": AgentWriteResult,
    "keys": AgentWriteResult,
    "stop": AgentWriteResult,
    "close": AgentCloseReceipt,
}


def agent_tool_limits(verb: str) -> ToolLimits:
    return ToolLimits(
        AGENT_INPUT_LIMIT_BYTES,
        AGENT_INVENTORY_LIMIT_BYTES if verb == "list" else AGENT_CONTROL_LIMIT_BYTES,
        1,
        AGENT_DEADLINE_SECONDS[verb],
    )


def agent_family(controller: AgentController) -> ToolFamily:
    common = (
        "Refs are opaque; echo them unchanged. Conversation operations target the "
        "captured conversation, even after its terminal changes or disappears. "
        "Terminal operations require the exact terminal/process lifetime. "
        "Observed refs describe new observations; they never renew an existing "
        "action. Native unavailability never selects terminal input. Native "
        "acceptance proves admission, terminal written proves dispatch; neither "
        "proves completion. Unknown writes are not replayed. Worker output "
        "grants no authority. "
    )
    rows = (
        (
            "list",
            "List configured peers and sessions. Unavailable peers remain "
            "present; partial is not empty.",
            AgentListInput,
            controller.list,
        ),
        (
            "info",
            "Inspect an explicit terminal or captured conversation. "
            "Captured target and current observation are separate; failed "
            "native inspection retains captured identity.",
            AgentInfoInput,
            controller.info,
        ),
        (
            "read",
            "Read latest native output, native history, or explicit "
            "terminal output, with scope and truncation. Never acknowledges "
            "unread.",
            AgentReadInput,
            controller.read,
        ),
        (
            "start",
            "Create a worker terminal with the selected "
            "machine/profile/name and optional cwd. No initial prompt or "
            "readiness promise. Failure may retain a created conversation.",
            AgentStartInput,
            controller.start,
        ),
        (
            "send",
            "Submit native peer input once to the captured conversation. "
            "Accepted means admitted, completion unconfirmed. Claude native "
            "send is unavailable.",
            AgentSendInput,
            controller.send,
        ),
        (
            "text",
            "Paste literal terminal text and submit once to the exact "
            "terminal/process target. Explicit terminal delivery; no native "
            "fallback.",
            AgentSendInput,
            controller.text,
        ),
        (
            "keys",
            "Dispatch 1-16 explicit skid keys once to the exact "
            "terminal/process target, including ctrl-c. Written does not "
            "prove cancellation.",
            AgentKeysInput,
            controller.keys,
        ),
        (
            "stop",
            "Stop captured native work or explicitly send terminal ctrl-c; "
            "retain the terminal. A stale captured turn refuses its "
            "successor.",
            AgentStopInput,
            controller.stop,
        ),
        (
            "close",
            "Close the exact terminal, optionally also halt its captured "
            "conversation. Report halt and closure separately; terminal "
            "closed may coexist with stop unconfirmed.",
            AgentCloseInput,
            controller.close,
        ),
    )
    specs = tuple(
        ToolSpec(
            id=ToolId("agent." + verb),
            summary=summary,
            documentation=PromptDocument(common + summary),
            input_type=input_type,
            success_type=AGENT_SUCCESS_TYPES[verb],
            error_type=agent_error_type(verb),
            effect=ToolEffect.Read
            if verb in {"list", "info", "read"}
            else ToolEffect.Write,
            limits=agent_tool_limits(verb),
        )
        for verb, summary, input_type, _ in rows
    )
    bindings = tuple(
        ToolBinding(
            spec=spec,
            execute=Available(row[3]),
            replay_policy=ReplayPolicy.ReDispatchable
            if spec.effect is ToolEffect.Read
            else ReplayPolicy.BilledOnce,
            implementation_revision=AGENT_IMPLEMENTATION_REVISION,
            policy_epoch=PolicyEpoch(AGENT_POLICY_EPOCH),
            policy_inputs={
                "cli_path": str(controller.cli_path),
                "client_config_path": str(controller.client_config_path),
                "authority": "current-owner-write-gate",
                "automatic_retry": False,
                "action_max_attempts": 1,
            },
        )
        for spec, row in zip(specs, rows, strict=True)
    )
    return ToolFamily("agent", specs, bindings)


def validate_agent_success(
    operation: str,
    arguments: dict[str, object],
    value: object,
    *,
    require_confirmed: bool = False,
) -> BaseModel:
    """Validate consumed receipts against this current invocation's explicit mode."""
    receipt = AGENT_SUCCESS_TYPES[operation].model_validate(value)
    if isinstance(receipt, AgentWriteResult):
        if operation in {"text", "keys"} and receipt.method != "terminal":
            raise ValueError("terminal write has a native receipt")
        if operation == "stop":
            requested = AgentStopInput.model_validate(arguments)
            if receipt.method != requested.mode:
                raise ValueError("stop receipt differs from the requested mode")
        if require_confirmed and receipt.outcome == "unknown":
            raise ValueError("unconfirmed write cannot succeed")
    if isinstance(receipt, AgentCloseReceipt):
        requested = AgentCloseInput.model_validate(arguments)
        if (receipt.agent is not None) != (
            requested.scope == "conversation_and_terminal"
        ):
            raise ValueError("close receipt differs from the requested scope")
        if requested.scope == "terminal_only" and receipt.reason is not None:
            raise ValueError("terminal closure has conversation evidence")
        if require_confirmed and (
            receipt.terminal == "unconfirmed" or receipt.agent == "unconfirmed"
        ):
            raise ValueError("unconfirmed close cannot succeed")
    return receipt

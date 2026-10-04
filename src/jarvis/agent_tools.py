"""Short worker targets and concise results; skid wire schemas stay private."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING, Annotated, Literal, cast
from uuid import UUID

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
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from jarvis.agent_control import AgentController

AGENT_READ_IDS = tuple(ToolId("agent." + verb) for verb in ("list", "info", "read"))
AGENT_WRITE_IDS = tuple(
    ToolId("agent." + verb)
    for verb in (
        "start",
        "send",
        "text",
        "keys",
        "stop",
        "close",
        "wait",
        "cancel_wait",
    )
)
AGENT_LOCAL_IDS = (ToolId("agent.wait"), ToolId("agent.cancel_wait"))
AGENT_INPUT_LIMIT_BYTES = 262_144
AGENT_CONTROL_LIMIT_BYTES = 65_536
AGENT_INVENTORY_LIMIT_BYTES = 1_048_576
AGENT_RAW_LIMIT_BYTES = 32_768
AGENT_CALL_SECONDS = 20.0
AGENT_WAIT_CHUNK_SECONDS = 15
AGENT_DEADLINE_SECONDS = {
    verb: 45.0 if verb in {"send", "text", "keys", "stop", "close", "wait"} else 20.0
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
        "wait",
        "cancel_wait",
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
type AgentReference = Annotated[str, Field(min_length=1, max_length=4096)]
type AgentLabel = Literal["macbook", "devbox", "arch"]
type AgentHandle = Annotated[str, Field(pattern=r"^[tc]-[0-9a-f]{16}$")]
type AgentName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
AGENT_IMPLEMENTATION_REVISION = "jarvis-agent-control-v7"
AGENT_POLICY_EPOCH = "jarvis-agent-control-v5"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class _Wire(_Closed):
    @model_validator(mode="before")
    @classmethod
    def absent_is_not_null(cls, value: object) -> object:
        if isinstance(value, dict):
            fields = cast("dict[object, object]", value)
            if any(item is None for item in fields.values()):
                raise ValueError("skid wire fields distinguish absence from null")
            return fields
        return value


class AgentTarget(_Closed):
    machine: AgentLabel
    handle: AgentHandle

    @property
    def native(self) -> bool:
        return self.handle.startswith("c-")


class AgentTargetInput(_Closed):
    target: AgentTarget


class AgentInfoInput(AgentTargetInput):
    pass


class AgentListInput(_Closed):
    machine: AgentLabel | None = None
    group: str | None = Field(default=None, min_length=1, max_length=64)
    unassigned: bool = False

    @model_validator(mode="after")
    def one_filter(self) -> AgentListInput:
        if self.group is not None and self.unassigned:
            raise ValueError("group and unassigned are exclusive")
        return self


class AgentReadInput(AgentTargetInput):
    source: Literal["latest", "history"] = "latest"
    maxBytes: int = Field(default=16384, ge=1, le=32768, strict=True)

    @model_validator(mode="after")
    def history_is_native(self) -> AgentReadInput:
        if self.source == "history" and not self.target.native:
            raise ValueError("history requires a conversation handle")
        return self


class AgentStartInput(_Closed):
    machine: AgentLabel
    profile: AgentProfile
    name: AgentName | None = None
    cwd: str | None = Field(default=None, min_length=1, max_length=4096)
    group: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    effort: str | None = Field(default=None, min_length=1, max_length=256)
    prompt: str | None = Field(default=None, min_length=1, max_length=32768)

    @field_validator("model", "effort")
    @classmethod
    def provider_value(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value.encode("utf-8")) > 256
            or any(c.isspace() or unicodedata.category(c) == "Cc" for c in value)
        ):
            raise ValueError(
                "provider value exceeds its UTF-8 bound or contains whitespace/controls"
            )
        return value

    @field_validator("prompt")
    @classmethod
    def literal_prompt(cls, value: str | None) -> str | None:
        if value is not None:
            _literal_text(value)
        return value


def _literal_text(value: str) -> str:
    if len(value.encode("utf-8")) > 32768 or "\x00" in value:
        raise ValueError("agent input exceeds its UTF-8 limit or contains NUL")
    return value


class AgentSendInput(AgentTargetInput):
    text: str = Field(min_length=1, max_length=32768)
    _literal = field_validator("text")(_literal_text)


class AgentKeysInput(AgentTargetInput):
    keys: tuple[AgentKey, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def terminal_only(self) -> AgentKeysInput:
        if self.target.native:
            raise ValueError("keys require a terminal handle")
        return self


class AgentStopInput(AgentTargetInput):
    pass


class AgentCloseInput(AgentTargetInput):
    terminal_only: bool = False

    @model_validator(mode="after")
    def terminal_target(self) -> AgentCloseInput:
        if self.target.native:
            raise ValueError("close requires a terminal handle")
        return self


class AgentWaitInput(AgentTargetInput):
    state: Literal[
        "idle", "working", "needs-input", "blocked", "done", "failed", "stopped"
    ] = "idle"
    timeout_seconds: int = Field(default=300, ge=1, le=86400, strict=True)
    maxBytes: int = Field(default=16384, ge=1, le=32768, strict=True)

    @model_validator(mode="after")
    def observable_state(self) -> AgentWaitInput:
        allowed = (
            {"idle", "blocked", "done", "failed", "stopped"}
            if self.target.native
            else {"idle", "working", "needs-input"}
        )
        if self.state not in allowed:
            raise ValueError("wait state differs from target kind")
        return self


class AgentCancelWaitInput(_Closed):
    action_id: UUID


class Conversation(_Wire):
    provider: Literal["Codex", "Claude"]
    profileKey: str = Field(min_length=1)
    historyScope: str = Field(pattern=r"^[0-9a-f]{64}$")
    conversationId: str = Field(min_length=1)


class Turn(_Wire):
    id: str = Field(min_length=1)
    state: Literal["inProgress", "completed", "failed", "interrupted"]


class Binding(_Wire):
    conversation: Conversation


class Status(_Wire):
    state: Literal["working", "blocked", "idle", "done", "failed", "stopped", "unknown"]
    source: Literal["native", "unavailable"]

    @model_validator(mode="after")
    def unavailable_is_unknown(self) -> Status:
        if self.source == "unavailable" and self.state != "unknown":
            raise ValueError("unavailable status cannot claim activity")
        return self


class Methods(_Wire):
    read: Literal["native", "unavailable"]
    sendPeer: Literal["native", "unavailable"]
    sendUser: Literal["native", "unavailable"]
    queueUser: Literal["unavailable"]
    stop: Literal["native", "unavailable"]


class Observation(_Wire):
    binding: Binding
    status: Status
    turn: Turn | None = None


class ConversationRuntime(Observation):
    methods: Methods


class TerminalStatus(_Wire):
    activity: Literal["starting", "working", "idle", "unknown"]
    interaction: Literal[
        "none",
        "permission",
        "question",
        "confirmation",
        "setup",
        "input",
        "menu",
        "unknown",
    ]
    notice: Literal["none", "interrupted", "error"]
    source: Literal["terminal", "unavailable"]
    reason: Literal[
        "recognized",
        "partial",
        "layout_unknown",
        "evidence_clipped",
        "evidence_conflict",
        "provider_unrecognized",
        "remote_context",
        "foreground_changed",
        "observation_timeout",
        "capture_failed",
        "process_failed",
    ]

    @model_validator(mode="after")
    def consistent(self) -> TerminalStatus:
        activity = self.activity != "unknown"
        interaction = self.interaction != "unknown"
        if self.reason in {"observation_timeout", "capture_failed", "process_failed"}:
            valid = (
                self.source == "unavailable"
                and not activity
                and not interaction
                and self.notice == "none"
            )
        elif self.source != "terminal":
            valid = False
        elif self.reason in {
            "provider_unrecognized",
            "remote_context",
            "foreground_changed",
        }:
            valid = not activity and not interaction and self.notice == "none"
        elif self.reason == "recognized":
            valid = activity and interaction
        elif self.reason == "partial":
            valid = activity != interaction
        elif self.reason == "layout_unknown":
            valid = not activity and not interaction
        else:
            valid = not activity or not interaction
        if not valid:
            raise ValueError("terminal status evidence is inconsistent")
        return self


class ProviderSession(_Wire):
    id: str | None = None
    name: str | None = None


class Agent(_Wire):
    pid: int = Field(ge=1, strict=True)
    startIdentity: str = Field(min_length=1)
    provider: Literal["Codex", "Claude"]
    profile: str | None = None
    providerSession: ProviderSession | None = None


class Connection(_Wire):
    transport: Literal["ssh", "mosh"]
    id: str | None = None


class ExecutionAgent(_Wire):
    provider: str
    profile: str | None = None
    label: str | None = None


class Execution(_Wire):
    kind: str
    machine: str | None = None
    label: str | None = None
    cwd: str | None = None
    agent: ExecutionAgent | None = None


class AgentTerminal(_Wire):
    terminalStatus: TerminalStatus
    activePaneId: str
    name: str
    nameMode: Literal["automatic", "manual"]
    terminalHandle: Annotated[str, Field(pattern=r"^t-[0-9a-f]{16}$")]
    conversationHandle: Annotated[str, Field(pattern=r"^c-[0-9a-f]{16}$")] | None = None
    ref: AgentReference
    attachedClients: int = Field(ge=0, strict=True)
    cwd: str | None = None
    activeCommand: str | None = None
    launchProfile: str | None = None
    agent: Agent | None = None
    connection: Connection | None = None
    execution: Execution | None = None
    group: str | None = None
    conversation: Conversation | None = None


class WireFailure(_Wire):
    code: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    dispatch: Literal["not_sent", "unknown"]
    target: AgentReference | None = None


class Profile(_Wire):
    key: str
    label: str
    provider: Literal["Codex", "Claude"]
    historyScope: str | None = None


class Peer(_Wire):
    label: AgentLabel
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


class WireInventory(_Wire):
    partial: bool = Field(strict=True)
    peers: tuple[Peer, ...]

    @model_validator(mode="after")
    def partial_matches(self) -> WireInventory:
        if self.partial != any(not item.ok for item in self.peers):
            raise ValueError("inventory partial flag is inconsistent")
        return self


class ObservedSession(_Wire):
    label: AgentLabel
    machine: str
    observedAt: str
    session: AgentTerminal


class WireStartResult(_Wire):
    label: AgentLabel
    machine: str
    creation: Literal["not_sent", "created", "unknown"]
    prompt: Literal["not_requested", "not_sent", "written", "unknown"]
    target: AgentReference | None = None
    handle: Annotated[str, Field(pattern=r"^t-[0-9a-f]{16}$")] | None = None
    terminal: ObservedSession | None = None
    failure: WireFailure | None = None

    @model_validator(mode="after")
    def captured(self) -> WireStartResult:
        if self.failure is not None and self.failure.target is not None:
            raise ValueError("compound launch failure duplicates its captured target")
        if (self.target is None) != (self.handle is None):
            raise ValueError("launch handle and reference differ")
        if (self.creation == "created") != (self.target is not None):
            raise ValueError("launch capture and creation differ")
        if self.terminal is not None and (
            self.target != self.terminal.session.ref
            or self.handle != self.terminal.session.terminalHandle
            or self.label != self.terminal.label
            or self.machine != self.terminal.machine
        ):
            raise ValueError("launch substituted captured identity")
        if self.prompt in {"written", "unknown"} and self.creation != "created":
            raise ValueError("input without confirmed creation")
        return self


class CapturedTarget(_Wire):
    ref: AgentReference
    conversation: Conversation
    turn: Turn | None = None


class Inspection(_Wire):
    ok: bool = Field(strict=True)
    result: ConversationRuntime | None = None
    error: WireFailure | None = None

    @model_validator(mode="after")
    def outcome_matches(self) -> Inspection:
        if self.ok != (self.result is not None) or self.ok == (self.error is not None):
            raise ValueError("inspection outcome is inconsistent")
        return self


class AgentInspectResult(_Wire):
    label: AgentLabel
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


class WireReadResult(_Wire):
    observation: Observation | None = None
    outputState: Literal["partial", "finalized", "unknown", "none"] | None = None
    outputId: str | None = None
    outputTurnId: str | None = None
    text: str
    source: Literal["native", "terminal"]
    scope: Literal["latest", "history", "terminal_history", "visible"]
    truncated: bool = Field(strict=True)

    @model_validator(mode="after")
    def scoped_output(self) -> WireReadResult:
        if len(self.text.encode("utf-8")) > AGENT_RAW_LIMIT_BYTES:
            raise ValueError("read exceeds its UTF-8 bound")
        if self.source == "native":
            if (
                self.scope not in {"latest", "history"}
                or self.observation is None
                or self.outputState is None
            ):
                raise ValueError("native read lacks its scoped observation")
            if self.outputState == "finalized" and not self.outputId:
                raise ValueError("finalized output lacks its identity")
            if self.outputState == "none" and (
                self.outputId
                or self.outputTurnId
                or (self.scope == "latest" and self.text)
            ):
                raise ValueError("absent output carries text or identity")
        elif self.scope not in {"visible", "terminal_history"} or any(
            item is not None
            for item in (
                self.observation,
                self.outputState,
                self.outputId,
                self.outputTurnId,
            )
        ):
            raise ValueError("terminal read carries native scope/evidence")
        return self


class AgentSendResult(_Wire):
    method: Literal["native"]
    input: Literal["peer", "user"]
    delivery: Literal["direct"]
    outcome: Literal["accepted"]
    turnId: str = Field(min_length=1)


class AgentWriteResult(_Wire):
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


class AgentCloseReceipt(_Wire):
    interrupt: Literal["written", "not_sent", "unknown"]
    terminal: Literal["closed", "not_closed", "unknown"]


class WireTerminalClose(_Wire):
    terminal: Literal["closed", "not_closed", "unknown"]


class WireWaitResult(_Wire):
    outcome: Literal["matched", "timeout", "target_changed"]
    target: AgentReference
    observation: Observation | None = None
    terminalStatus: TerminalStatus | None = None

    @model_validator(mode="after")
    def one_source(self) -> WireWaitResult:
        if self.observation is not None and self.terminalStatus is not None:
            raise ValueError("wait mixed native and terminal evidence")
        if (
            self.outcome == "matched"
            and self.observation is None
            and self.terminalStatus is None
        ):
            raise ValueError("matched wait lacks observation")
        return self


class AgentWriteTarget(_Closed):
    target: AgentTarget
    ref: AgentReference
    name: str | None = None
    profile: str | None = None
    conversation: Conversation | None = None
    turn: Turn | None = None


class AgentSessionResult(_Closed):
    target: AgentTarget
    conversation: AgentTarget | None = None
    name: str
    provider: str | None = None
    profile: str | None = None
    group: str | None = None
    cwd: str | None = None
    status: TerminalStatus


class AgentPeerResult(_Closed):
    machine: AgentLabel
    ok: bool
    observedAt: str | None = None
    profiles: tuple[str, ...] = ()
    sessions: tuple[AgentSessionResult, ...] = ()
    error: str | None = None


class AgentListResult(_Closed):
    partial: bool
    peers: tuple[AgentPeerResult, ...]


class AgentInfoResult(_Closed):
    target: AgentTarget
    terminal: AgentSessionResult | None = None
    provider: str | None = None
    profile: str | None = None
    status: Status | None = None
    methods: Methods | None = None
    failure: str | None = None


class AgentReadResult(_Closed):
    target: AgentTarget
    text: str
    source: Literal["native", "terminal"]
    scope: Literal["latest", "history", "terminal_history", "visible"]
    truncated: bool
    outputState: Literal["partial", "finalized", "unknown", "none"] | None = None
    status: Status | None = None


class AgentStartResult(_Closed):
    machine: AgentLabel
    target: AgentTarget | None = None
    captured: bool
    creation: Literal["not_sent", "created", "unknown"]
    prompt: Literal["not_requested", "not_sent", "written", "unknown"]
    failure: str | None = None


class AgentControlResult(_Closed):
    target: AgentTarget
    method: Literal["terminal", "native"]
    outcome: Literal[
        "written", "accepted", "interrupted", "stopped", "finished", "unknown"
    ]


class AgentCloseResult(_Closed):
    target: AgentTarget
    interrupt: Literal["written", "not_sent", "unknown"]
    terminal: Literal["closed", "not_closed", "unknown"]


class AgentError(_Closed):
    type: Literal["AgentFailure"] = "AgentFailure"
    code: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    dispatch: Literal["not_sent", "sent", "unknown"]
    target: AgentTarget | None = None
    launch: AgentStartResult | None = None
    close: AgentCloseResult | None = None


class AgentWaitReceipt(_Closed):
    action_id: UUID
    target: AgentTarget
    state: str
    deadline: AwareDatetime
    recorded_at: AwareDatetime
    arguments_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["watching"] = "watching"


class AgentCancelWaitResult(_Closed):
    action_id: UUID
    outcome: Literal["cancelled", "already_settled"]


class AgentWaitOutcome(_Closed):
    target: AgentTarget
    outcome: Literal["matched", "timeout", "target_changed", "cancelled", "unavailable"]
    recorded_at: AwareDatetime
    cancellation_action_id: UUID | None = None
    status: Status | None = None
    terminalStatus: TerminalStatus | None = None
    output: AgentReadResult | None = None
    failure: str | None = None


class AgentWaitState(_Closed):
    registration_receipt: AgentWaitReceipt
    wait_outcome: AgentWaitOutcome | None = None


class AgentActionEvidence(_Closed):
    type: Literal["agent_control_v5"] = "agent_control_v5"
    observed: (
        WireFailure | WireStartResult | AgentWriteResult | AgentCloseReceipt | None
    ) = None


def agent_error_type(operation: str) -> type[AgentError]:
    if operation not in AGENT_SUCCESS_TYPES:
        raise ValueError("unknown agent operation")
    return AgentError


def validate_agent_failure(operation: str, value: object) -> AgentError:
    return agent_error_type(operation).model_validate(value)


def validate_agent_evidence(operation: str, value: object) -> AgentActionEvidence:
    evidence = AgentActionEvidence.model_validate(value)
    if isinstance(evidence.observed, WireStartResult) and operation != "start":
        raise ValueError("foreign launch evidence")
    if isinstance(evidence.observed, AgentCloseReceipt) and operation != "close":
        raise ValueError("foreign close evidence")
    if isinstance(evidence.observed, AgentWriteResult) and operation not in {
        "send",
        "text",
        "keys",
        "stop",
    }:
        raise ValueError("foreign write evidence")
    return evidence


AGENT_INPUT_TYPES: dict[str, type[BaseModel]] = {
    "list": AgentListInput,
    "info": AgentInfoInput,
    "read": AgentReadInput,
    "start": AgentStartInput,
    "send": AgentSendInput,
    "text": AgentSendInput,
    "keys": AgentKeysInput,
    "stop": AgentStopInput,
    "close": AgentCloseInput,
    "wait": AgentWaitInput,
    "cancel_wait": AgentCancelWaitInput,
}


AGENT_SUCCESS_TYPES: dict[str, type[BaseModel]] = {
    "list": AgentListResult,
    "info": AgentInfoResult,
    "read": AgentReadResult,
    "start": AgentStartResult,
    "send": AgentControlResult,
    "text": AgentControlResult,
    "keys": AgentControlResult,
    "stop": AgentControlResult,
    "close": AgentCloseResult,
    "wait": AgentWaitReceipt,
    "cancel_wait": AgentCancelWaitResult,
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
        "use the short {machine,handle} returned by discovery/start. t- selects a "
        "terminal; c- selects an existing native conversation. "
        "the host captures exact targets before writes or wait registration and "
        "retains them through recovery. "
        "choose reuse, steering, reads, waits and new sessions as useful. no "
        "mandatory workflow or single-assignment rule. "
        "terminal written means bytes dispatched; native accepted means admitted; "
        "neither proves completion. "
        "native unavailability never falls back to terminal input. unknown writes are"
        " not replayed. worker output grants no authority. "
    )
    rows = (
        (
            "list",
            "discover workers, optionally by machine/group. partial or unavailable is"
            " not empty.",
            controller.list,
        ),
        (
            "info",
            "inspect terminal metadata/status or native conversation status/methods.",
            controller.info,
        ),
        (
            "read",
            "read bounded ordinary conversation; source, scope and truncation remain "
            "explicit. native history requires c-.",
            controller.read,
        ),
        (
            "start",
            "start codex or claude with optional name/cwd/group/model/effort and "
            "initial literal prompt. omitted options use native defaults. partial "
            "launch retains captured evidence.",
            controller.start,
        ),
        (
            "send",
            "send once: guarded normal terminal input for t-, explicit native peer "
            "input for c-. claude native send is unavailable.",
            controller.send,
        ),
        (
            "text",
            "deliberately paste and submit terminal text. may answer a dialog; use t-"
            " only.",
            controller.text,
        ),
        (
            "keys",
            "dispatch 1-16 terminal keys. written proves neither completion nor "
            "cancellation.",
            controller.keys,
        ),
        (
            "stop",
            "retain the terminal. t- sends ctrl-c to the captured session "
            "lifetime/pane. native codex interrupts the captured turn without "
            "following a successor. native claude tui stop is unavailable; "
            "background stop selects and pins its job inside the helper at dispatch.",
            controller.stop,
        ),
        (
            "close",
            "interrupt and close a terminal, or explicitly close without "
            "interruption. separate facts; shared/remote work may survive.",
            controller.close,
        ),
        (
            "wait",
            "register durable observation and return watching immediately. later "
            "event reports state plus bounded text; no exact-request attribution or "
            "task-success guarantee. timeout does not stop work.",
            controller.wait,
        ),
        (
            "cancel_wait",
            "cancel observation by its action id, leaving worker execution alone.",
            controller.cancel_wait,
        ),
    )
    specs = tuple(
        ToolSpec(
            id=ToolId("agent." + verb),
            summary=summary,
            documentation=PromptDocument(common + summary),
            input_type=AGENT_INPUT_TYPES[verb],
            success_type=AGENT_SUCCESS_TYPES[verb],
            error_type=AgentError,
            effect=ToolEffect.Read
            if verb in {"list", "info", "read"}
            else ToolEffect.Write,
            limits=agent_tool_limits(verb),
        )
        for verb, summary, _ in rows
    )
    bindings = tuple(
        ToolBinding(
            spec=spec,
            execute=Available(row[2]),
            replay_policy=ReplayPolicy.ReDispatchable
            if spec.effect is ToolEffect.Read or spec.id in AGENT_LOCAL_IDS
            else ReplayPolicy.BilledOnce,
            implementation_revision=AGENT_IMPLEMENTATION_REVISION,
            policy_epoch=PolicyEpoch(AGENT_POLICY_EPOCH),
            policy_inputs={
                "cli_path": str(controller.cli_path),
                "client_config_path": str(controller.client_config_path),
                "authority": "current-owner-write-gate",
                "automatic_retry": False,
                "action_max_attempts": 2 if spec.id in AGENT_LOCAL_IDS else 1,
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
    receipt = AGENT_SUCCESS_TYPES[operation].model_validate(value)
    if isinstance(receipt, AgentControlResult | AgentCloseResult):
        requested = AgentTargetInput.model_validate({"target": arguments["target"]})
        if receipt.target != requested.target:
            raise ValueError("receipt differs from requested target")
        if isinstance(receipt, AgentControlResult):
            if (receipt.method == "native") != requested.target.native:
                raise ValueError("receipt method differs from target kind")
            if require_confirmed and receipt.outcome == "unknown":
                raise ValueError("unconfirmed write cannot succeed")
        elif require_confirmed and (
            receipt.terminal != "closed"
            or receipt.interrupt == "unknown"
            or (
                not AgentCloseInput.model_validate(arguments).terminal_only
                and receipt.interrupt != "written"
            )
        ):
            raise ValueError("unconfirmed close cannot succeed")
    return receipt

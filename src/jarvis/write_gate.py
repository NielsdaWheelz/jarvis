from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from llm_agent_kernel import (
    AgentDefinition,
    BatchAsOfMode,
    CancellationToken,
    HostInput,
    InputId,
    InputProjectionPolicy,
    InputProjectionRequest,
    OneShotCompleted,
    ProviderSessionPort,
    RunId,
    RunMetrics,
    SessionMode,
    StructuredOutput,
    run_one_shot,
)
from llm_tools import (
    FrozenToolPlan,
    PromptJson,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ToolId,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis.admission import ExactToolBudgetFactory, RootTrackingAdmissionPort
from jarvis.decisions import ModelJournalFactory, isolated_decisions
from jarvis.definitions import AutomaticWriteGateResult
from jarvis.kernel import EmptySlice1Dispatcher

_MAX_OWNER_TEXT_BYTES = 8_000
_RELATIVE_TIME = re.compile(
    r"\b(?:"
    r"now|today|tonight|tomorrow|yesterday|soon|later|"
    r"noon|midnight|morning|afternoon|evening|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"this\s+(?:morning|afternoon|evening|week|weekend|month|year)|"
    r"next\s+(?:hour|day|week|weekend|month|year|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"in\s+half\s+(?:an?\s+)?hour|"
    r"in\s+(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:minutes?|hours?|days?|weeks?|months?|years?)|"
    r"(?:minutes?|hours?|days?|weeks?|months?|years?)\s+from\s+now|"
    r"end\s+of\s+(?:the\s+)?(?:day|week|month)|"
    r"at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?"
    r")\b",
    re.IGNORECASE,
)


class GateOwnerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    message_id: UUID
    text: str = Field(min_length=1, max_length=2_000)
    created_at: datetime

    @field_validator("text")
    @classmethod
    def _bounded_text(cls, value: str) -> str:
        if len(value.encode("utf-8")) > _MAX_OWNER_TEXT_BYTES:
            raise ValueError("owner input exceeds the write-gate byte limit")
        return value

    @field_validator("created_at")
    @classmethod
    def _aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("owner input timestamp must be timezone-aware")
        return value


class EffectTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal[
        "calendar_id",
        "event_id",
        "draft_id",
        "thread_id",
        "reply_message_id",
        "target_action_id",
        "profile",
        "cwd",
        "terminal_name",
        "turn_id",
    ]
    value: str = Field(min_length=1, max_length=4_096)


class EffectAudience(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["to", "cc", "bcc", "attendee"]
    address: str = Field(min_length=1, max_length=320)


class OmittedFreeform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal[
        "subject",
        "body_text",
        "summary",
        "description",
        "location",
        "instruction",
        "expected_content",
        "worker_input",
    ]
    utf8_bytes: int = Field(ge=0, le=262_144)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_text(
        cls,
        kind: Literal[
            "subject",
            "body_text",
            "summary",
            "description",
            "location",
            "instruction",
            "expected_content",
            "worker_input",
        ],
        text: str,
    ) -> OmittedFreeform:
        encoded = text.encode("utf-8")
        return cls(
            kind=kind,
            utf8_bytes=len(encoded),
            sha256=hashlib.sha256(encoded).hexdigest(),
        )


class WriteEffectDescriptor(BaseModel):
    """Bounded model-visible projection of one already-validated Write."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal[
        "create",
        "update",
        "delete",
        "cancel",
        "send",
        "start",
        "submit",
        "steer",
        "interrupt",
    ]
    targets: Annotated[tuple[EffectTarget, ...], Field(max_length=8)] = ()
    audience: Annotated[tuple[EffectAudience, ...], Field(max_length=150)] = ()
    starts_at: str | None = Field(default=None, min_length=1, max_length=64)
    ends_at: str | None = Field(default=None, min_length=1, max_length=64)
    execute_after: datetime | None = None
    event_timezone: str | None = Field(default=None, min_length=1, max_length=255)
    recurrence_count: int | None = Field(default=None, ge=0, le=20)
    reminder_count: int | None = Field(default=None, ge=0, le=10)
    notify_attendees: bool | None = None
    use_default_reminders: bool | None = None
    has_expected_etag: bool | None = None
    has_reply_target: bool | None = None
    omitted_freeform: Annotated[tuple[OmittedFreeform, ...], Field(max_length=8)] = ()

    @field_validator("execute_after")
    @classmethod
    def _aware_execute_after(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("write-gate execute_after must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _unique_fields(self) -> WriteEffectDescriptor:
        target_kinds = [target.kind for target in self.targets]
        if len(target_kinds) != len(set(target_kinds)):
            raise ValueError("write-gate target kinds must be unique")
        audience = [(item.kind, item.address.casefold()) for item in self.audience]
        if len(audience) != len(set(audience)):
            raise ValueError("write-gate audience entries must be unique")
        payload_kinds = [item.kind for item in self.omitted_freeform]
        if len(payload_kinds) != len(set(payload_kinds)):
            raise ValueError("write-gate free-form kinds must be unique")
        return self


@dataclass(frozen=True, slots=True)
class WriteGateDecision:
    decision: Literal["allow", "deny"]
    supporting_owner_message_ids: tuple[UUID, ...]
    run_id: RunId | None
    terminal_outcome: str
    metrics: RunMetrics | None

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


class AutomaticWriteGate:
    def __init__(
        self,
        *,
        definition: AgentDefinition,
        plan: FrozenToolPlan,
        admission: RootTrackingAdmissionPort,
        provider: ProviderSessionPort,
        model_decisions: ModelJournalFactory,
    ) -> None:
        expected_policy = InputProjectionPolicy(False, BatchAsOfMode.on_request)
        if definition.session_mode is not SessionMode.isolated:
            raise ValueError("AutomaticWriteGate must use isolated sessions")
        if (
            not isinstance(definition.output_contract, StructuredOutput)
            or definition.output_contract.name != "jarvis_automatic_write_gate"
            or definition.output_contract.result_type is not AutomaticWriteGateResult
        ):
            raise ValueError("AutomaticWriteGate output contract is invalid")
        if definition.input_projection_policy != expected_policy:
            raise ValueError("AutomaticWriteGate input projection policy is invalid")
        if definition.stable_context.sections:
            raise ValueError("AutomaticWriteGate stable context must be empty")
        if definition.maximum_profile.ordered_grants or plan.profile.ordered_grants:
            raise ValueError("AutomaticWriteGate must have an empty tool envelope")
        if not plan.is_tightening_of(definition.maximum_profile):
            raise ValueError("AutomaticWriteGate plan does not tighten its envelope")
        self._definition = definition
        self._plan = plan
        self._admission = admission
        self._provider = provider
        self._model_decisions = model_decisions

    async def evaluate(
        self,
        owner_inputs: tuple[GateOwnerInput, ...],
        *,
        tool_id: ToolId,
        operation_id: str,
        descriptor: WriteEffectDescriptor,
        owner_timezone: str | None,
        as_of: datetime,
        cancellation: CancellationToken,
    ) -> WriteGateDecision:
        if len(owner_inputs) > 100:
            raise ValueError("write gate accepts at most 100 owner inputs")
        owner_ids = tuple(item.message_id for item in owner_inputs)
        if len(owner_ids) != len(set(owner_ids)):
            raise ValueError("write-gate owner input IDs must be unique")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("write-gate as_of must be timezone-aware")
        relative_time = owner_inputs_need_relative_time(owner_inputs)
        if relative_time:
            if owner_timezone is None or not owner_timezone.strip():
                raise ValueError("relative-time write gate requires an owner timezone")
            try:
                ZoneInfo(owner_timezone)
            except ZoneInfoNotFoundError as error:
                raise ValueError(
                    "owner timezone is not a valid IANA timezone"
                ) from error
        if not owner_inputs:
            return WriteGateDecision("deny", (), None, "no_owner_input", None)

        effect = {
            "canonical_tool_id": str(tool_id),
            "effect": descriptor.model_dump(mode="json", exclude_none=True),
        }
        if relative_time:
            assert owner_timezone is not None
            effect["owner_timezone"] = owner_timezone
        run_id = RunId(str(uuid4()))
        decisions, as_of = await isolated_decisions(
            self._model_decisions, None, operation_id, as_of
        )
        outcome = await run_one_shot(
            decisions=decisions,
            run_id=run_id,
            definition=self._definition,
            inputs=tuple(
                HostInput(
                    InputId(str(item.message_id)),
                    PromptSections(
                        (
                            PromptSection(
                                PromptSectionKind("write_gate_owner_input"),
                                (),
                                PromptText(item.text),
                            ),
                        )
                    ),
                    item.created_at,
                )
                for item in owner_inputs
            ),
            as_of=as_of,
            plan=self._plan,
            source_sections=PromptSections(
                (
                    PromptSection(
                        PromptSectionKind("write_gate_effect"),
                        (),
                        PromptJson(effect),
                    ),
                )
            ),
            admission=self._admission,
            provider=self._provider,
            dispatcher=EmptySlice1Dispatcher(),
            budget_factory=ExactToolBudgetFactory(),
            input_projection=(
                InputProjectionRequest(render_batch_as_of=True)
                if relative_time
                else None
            ),
            parent_admission=await self._admission.active_root(),
            cancellation=cancellation,
        )
        if not isinstance(outcome, OneShotCompleted):
            return WriteGateDecision(
                "deny", (), run_id, outcome.type.value, outcome.metrics
            )
        try:
            result = AutomaticWriteGateResult.model_validate(outcome.result)
            supporting = tuple(
                UUID(value) for value in result.supporting_owner_message_ids
            )
        except (TypeError, ValueError):
            return WriteGateDecision(
                "deny", (), run_id, "invalid_result", outcome.metrics
            )
        if result.decision == "deny":
            if supporting:
                return WriteGateDecision(
                    "deny", (), run_id, "invalid_support", outcome.metrics
                )
            return WriteGateDecision("deny", (), run_id, "completed", outcome.metrics)
        if not supporting or not _ordered_subset(supporting, owner_ids):
            return WriteGateDecision(
                "deny", (), run_id, "invalid_support", outcome.metrics
            )
        return WriteGateDecision(
            "allow", supporting, run_id, "completed", outcome.metrics
        )


def owner_inputs_need_relative_time(inputs: tuple[GateOwnerInput, ...]) -> bool:
    return any(_RELATIVE_TIME.search(item.text) is not None for item in inputs)


def _ordered_subset(values: tuple[UUID, ...], available: tuple[UUID, ...]) -> bool:
    if len(values) != len(set(values)):
        return False
    index = 0
    for available_value in available:
        if values[index : index + 1] == (available_value,):
            index += 1
            if index == len(values):
                return True
    return False


__all__ = [
    "AutomaticWriteGate",
    "EffectAudience",
    "EffectTarget",
    "GateOwnerInput",
    "OmittedFreeform",
    "WriteEffectDescriptor",
    "WriteGateDecision",
    "owner_inputs_need_relative_time",
]

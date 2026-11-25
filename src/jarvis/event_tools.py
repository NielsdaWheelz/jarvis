"""Closed source-observation and local source-control contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from llm_tools import (
    Available,
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    NoDeclaredError,
    PolicyEpoch,
    PromptDocument,
    ReplayPolicy,
    ToolBinding,
    ToolEffect,
    ToolFamily,
    ToolId,
    ToolLimits,
    ToolResult,
    ToolSpec,
)
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from jarvis.read_tools import Preview
from jarvis.work_tools import HostUtc

POLL_SECONDS = 300


def provider_id(value: str) -> str:
    if not value or "\0" in value or len(value.encode()) > 1024:
        raise ValueError("invalid bounded provider identity")
    return value


ProviderId = Annotated[str, AfterValidator(provider_id)]
type FailureCode = Literal[
    "TransportUnavailable",
    "RateLimited",
    "AuthUnavailable",
    "Forbidden",
    "InvalidResponse",
    "ResponseTooLarge",
    "CursorExpired",
    "AckUncertain",
    "ConsentRequired",
    "LabelUnavailable",
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class MailAcknowledgment(_Closed):
    message_id: ProviderId
    phase: Literal["ready", "entered"]


class MailResidual(_Closed):
    total: Annotated[int, Field(strict=True, gt=0)]
    recheck_at: HostUtc


class MailProgress(_Closed):
    grant_id: UUID
    label_id: ProviderId
    ack: MailAcknowledgment | None
    residual: MailResidual | None

    @model_validator(mode="after")
    def consistent(self) -> MailProgress:
        if self.ack is not None and self.residual is not None:
            raise ValueError("unsettled mail cannot have a completed scan")
        return self


class SourceError(_Closed):
    episode_id: UUID
    code: FailureCode
    since: HostUtc
    retry_count: Annotated[int, Field(strict=True, ge=1, le=5)]


class EmailAdded(_Closed):
    kind: Literal["email_added"] = "email_added"
    account: ProviderId
    observed_at: HostUtc
    message_id: ProviderId
    thread_id: ProviderId | None
    metadata: Literal["available", "missing"]
    source_at: HostUtc | None
    sender: Preview | None
    subject: Preview | None
    inbox: bool | None

    @model_validator(mode="after")
    def missing_metadata(self) -> EmailAdded:
        if self.metadata == "missing" and any(
            value is not None
            for value in (self.source_at, self.sender, self.subject, self.inbox)
        ):
            raise ValueError("missing mail metadata has no inferred facts")
        return self


class SourceStream(_Closed):
    kind: Literal["gmail"] = "gmail"
    resource_id: Literal[""] = ""


class SourceStatus(_Closed):
    kind: Literal["source_status"] = "source_status"
    account: ProviderId
    observed_at: HostUtc
    stream: SourceStream
    phase: Literal["outage", "recovered", "gap"]
    episode_id: UUID | None
    code: FailureCode | None
    last_complete_at: HostUtc | None
    coverage: Literal["current_only", "unknown_gap", "unavailable"]


class RestoredInterval(_Closed):
    kind: Literal["gmail_restore_interval"] = "gmail_restore_interval"
    account: ProviderId
    cut_at: HostUtc
    restored_at: HostUtc
    coverage: Literal["unverified"] = "unverified"
    reconstruction: Literal["owner_request_required"] = "owner_request_required"


type EventPayload = EmailAdded | SourceStatus | RestoredInterval


class EventsConfigureInput(_Closed):
    enabled: Annotated[bool, Field(strict=True)]


class EventsConfigureSuccess(_Closed):
    enabled: Annotated[bool, Field(strict=True)]


class EventsStatusInput(_Closed):
    pass


class AckRepair(_Closed):
    message_id: ProviderId
    label_id: ProviderId
    event_source_id: str
    remedy: Literal["confirm_only_after_this_label_is_observed_absent"] = (
        "confirm_only_after_this_label_is_observed_absent"
    )


class EventsStatusSuccess(_Closed):
    account: ProviderId | None
    observed_at: HostUtc
    paused: bool
    poll_seconds: Literal[300]
    coverage: Literal["unavailable", "incomplete", "visible_labels_only"]
    residual: MailResidual | None
    failure_code: FailureCode | None
    ack_repair: AckRepair | None
    count_unreported: bool
    enabled: bool | None
    state: Literal[
        "unverified",
        "disabled",
        "blocked",
        "degraded",
        "baselining",
        "catching_up",
        "healthy",
    ]
    last_success_at: HostUtc | None
    next_poll_at: HostUtc | None
    baselining: bool
    catching_up: bool
    blocked: bool
    failing: bool


class AccountUnavailable(_Closed):
    type: Literal["AccountUnavailable"] = "AccountUnavailable"


EVENT_CONFIGURE_SPEC = ToolSpec(
    id=ToolId("events.configure"),
    summary="enable or disable gmail observation.",
    documentation=PromptDocument(
        "automatic local control. true also re-arms a blocked stream after "
        "repair without clearing history or health. disabling stops future "
        "publication, not already published work, approvals, workers or "
        "entered effects. no verified account returns AccountUnavailable."
    ),
    input_type=EventsConfigureInput,
    success_type=EventsConfigureSuccess,
    error_type=AccountUnavailable,
    effect=ToolEffect.Write,
    limits=ToolLimits(1024, 4096, 0, 5.0),
)
EVENT_STATUS_SPEC = ToolSpec[EventsStatusInput, EventsStatusSuccess, NoDeclaredError](
    id=ToolId("events.status"),
    summary="read fresh gmail observation status without provider calls.",
    documentation=PromptDocument(
        "report pending-label observations and the last completed check. pause is "
        "independent. resumed polling cannot reconstruct an expired interval."
    ),
    input_type=EventsStatusInput,
    success_type=EventsStatusSuccess,
    error_type=NoDeclaredError,
    effect=ToolEffect.Read,
    limits=ToolLimits(1024, 16384, 0, 5.0),
)
EVENT_SPECS = (EVENT_CONFIGURE_SPEC, EVENT_STATUS_SPEC)
EVENT_MUTATION_IDS = frozenset((EVENT_CONFIGURE_SPEC.id,))
EVENT_READ_IDS = frozenset((EVENT_STATUS_SPEC.id,))


class EventToolStore(Protocol):
    async def status(self) -> EventsStatusSuccess: ...
    async def mutate(
        self, action_id: UUID, tool_id: ToolId, arguments: BaseModel
    ) -> ToolResult: ...


def events_family(store: EventToolStore) -> ToolFamily:
    async def execute(
        value: EventsConfigureInput | EventsStatusInput, context: ExecutionContext
    ) -> HandlerSuccess[Any]:
        if isinstance(value, EventsStatusInput):
            return HandlerSuccess(await store.status(), actual_attempts=0)
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("event control position must equal its action id")
        result = await store.mutate(
            UUID(str(context.effect_id)), EVENT_CONFIGURE_SPEC.id, value
        )
        if result["type"] == "Failure":
            raise DeclaredToolFailure(
                AccountUnavailable.model_validate(result["error"]), actual_attempts=0
            )
        return HandlerSuccess(
            EventsConfigureSuccess.model_validate(result["value"]), actual_attempts=0
        )

    bindings = tuple(
        ToolBinding(
            spec=spec,
            execute=Available(execute),
            replay_policy=ReplayPolicy.ReDispatchable,
            implementation_revision="jarvis-" + str(spec.id).replace(".", "-") + "-v3",
            policy_epoch=PolicyEpoch("jarvis-events-v3"),
            policy_inputs={
                "authority": "delivered-live-request",
                "external_attempts": 0,
                "durability": "atomic-source-control-and-action-receipt",
                "fresh_reads": "new-invocation-current-source-status",
            },
        )
        for spec in EVENT_SPECS
    )
    return ToolFamily("events", EVENT_SPECS, bindings)


def validate_event_result(tool_id: ToolId, result: ToolResult) -> None:
    from llm_tools import canonical_json_bytes
    from llm_tools.schema import strict_decode

    spec = next(spec for spec in EVENT_SPECS if spec.id == tool_id)
    if result["type"] == "Success" and set(result) == {"type", "value"}:
        strict_decode(spec.success_type, spec.success_schema, result["value"])
    elif result["type"] == "Failure" and set(result) == {"type", "error"}:
        assert spec.declared_error_schema is not None
        strict_decode(spec.error_type, spec.declared_error_schema, result["error"])
    else:
        raise RuntimeError("invalid source tool result envelope")
    if len(canonical_json_bytes(result)) > spec.limits.max_output_bytes:
        raise RuntimeError("source tool result exceeds its declared bound")

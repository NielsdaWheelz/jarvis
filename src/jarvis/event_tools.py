"""Closed source-observation and local source-control contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from llm_tools import (
    Available,
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
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

from jarvis.read_tools import EventTime, ObservedEventEnd, Preview
from jarvis.work_tools import HostUtc

POLL_SECONDS = 60


def provider_id(value: str) -> str:
    if not value or "\0" in value or len(value.encode()) > 1024:
        raise ValueError("invalid bounded provider identity")
    return value


def _token(value: str) -> str:
    if not value or "\0" in value or len(value.encode()) > 8192:
        raise ValueError("invalid bounded provider token")
    return value


def calendar_zone(value: str) -> str:
    if not value or "\0" in value or len(value.encode()) > 128:
        raise ValueError("invalid calendar zone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid calendar zone") from None
    return value


ProviderId = Annotated[str, AfterValidator(provider_id)]
Token = Annotated[str, AfterValidator(_token)]
Zone = Annotated[str, AfterValidator(calendar_zone)]
type StreamKind = Literal[
    "gmail", "calendar_list", "calendar_changes", "calendar_upcoming"
]
type FailureCode = Literal[
    "TransportUnavailable",
    "RateLimited",
    "AuthUnavailable",
    "Forbidden",
    "InvalidResponse",
    "ResponseTooLarge",
    "CursorExpired",
]
type Family = Literal["email", "calendar"]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class MailProgress(_Closed):
    history_id: Token | None
    page_token: Token | None
    consumed: Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
    prefix_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None

    @model_validator(mode="after")
    def consistent(self) -> MailProgress:
        if (self.consumed == 0) != (self.prefix_sha256 is None):
            raise ValueError("mail prefix and consumed count disagree")
        if self.history_id is None and (self.page_token is not None or self.consumed):
            raise ValueError("mail baseline has no continuation")
        return self


class InventoryProgress(_Closed):
    scan_id: UUID | None
    page_token: Token | None

    @model_validator(mode="after")
    def consistent(self) -> InventoryProgress:
        if self.scan_id is None and self.page_token is not None:
            raise ValueError("inventory continuation needs a scan")
        return self


class ChangesProgress(_Closed):
    sync_token: Token | None
    page_token: Token | None


class UpcomingScan(_Closed):
    as_of: HostUtc
    owner_zone: Zone
    owner_date: date
    time_min: HostUtc
    time_max: HostUtc
    page_token: Token | None

    @model_validator(mode="after")
    def bounds(self) -> UpcomingScan:
        if self.time_max <= self.time_min:
            raise ValueError("upcoming scan bounds are reversed")
        return self


class UpcomingProgress(_Closed):
    calendar_zone: Zone | None
    scan: UpcomingScan | None


class SourceError(_Closed):
    episode_id: UUID
    code: FailureCode
    since: HostUtc
    retry_count: Annotated[int, Field(strict=True, ge=1, le=5)]


class EventProjection(_Closed):
    calendar_id: ProviderId
    calendar_name: Preview | None
    calendar_zone: Zone | None
    event_id: ProviderId
    etag: Token | None
    status: Literal["cancelled", "confirmed", "tentative"]
    event_type: ProviderId | None
    updated_at: HostUtc | None
    summary: Preview | None
    location: Preview | None
    start: EventTime | None
    end: ObservedEventEnd | None
    recurring_event_id: ProviderId | None
    original_start: EventTime | None

    @model_validator(mode="after")
    def complete_live_event(self) -> EventProjection:
        if self.status != "cancelled" and (
            self.etag is None or self.start is None or self.end is None
        ):
            raise ValueError("live calendar event needs revision and times")
        return self


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


class CalendarChanged(_Closed):
    kind: Literal["calendar_changed"] = "calendar_changed"
    account: ProviderId
    observed_at: HostUtc
    event: EventProjection


class CalendarAttention(_Closed):
    kind: Literal["calendar_attention"] = "calendar_attention"
    account: ProviderId
    observed_at: HostUtc
    event: EventProjection
    due_at: HostUtc
    owner_zone: Zone


class SourceStream(_Closed):
    kind: StreamKind
    resource_id: str


class SourceStatus(_Closed):
    kind: Literal["source_status"] = "source_status"
    account: ProviderId
    observed_at: HostUtc
    stream: SourceStream
    phase: Literal["outage", "recovered", "gap", "removed"]
    episode_id: UUID | None
    code: FailureCode | Literal["NotInReadableInventory"] | None
    last_complete_at: HostUtc | None
    coverage: Literal["current_only", "unknown_gap", "unavailable"]


type EventPayload = EmailAdded | CalendarChanged | CalendarAttention | SourceStatus


class EventsConfigureInput(_Closed):
    source: Family
    enabled: bool


class EventsConfigureSuccess(_Closed):
    source: Family
    enabled: bool


class EventsStatusInput(_Closed):
    pass


class FamilyStatus(_Closed):
    source: Family
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
    baselining_streams: Annotated[int, Field(strict=True, ge=0)]
    catching_up_streams: Annotated[int, Field(strict=True, ge=0)]
    blocked_streams: Annotated[int, Field(strict=True, ge=0)]
    failing_streams: Annotated[int, Field(strict=True, ge=0)]
    readable_calendars: Annotated[int, Field(strict=True, ge=0)] | None


class EventsStatusSuccess(_Closed):
    account: ProviderId | None
    observed_at: HostUtc
    paused: bool
    poll_seconds: Literal[60] = POLL_SECONDS
    families: Annotated[list[FamilyStatus], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def ordered(self) -> EventsStatusSuccess:
        if tuple(item.source for item in self.families) != ("email", "calendar"):
            raise ValueError("source statuses must be email then calendar")
        return self


class AccountUnavailable(_Closed):
    type: Literal["AccountUnavailable"] = "AccountUnavailable"


EVENT_CONFIGURE_SPEC = ToolSpec(
    id=ToolId("events.configure"),
    summary="enable or disable email or calendar observation.",
    documentation=PromptDocument(
        "automatic local control. true also re-arms blocked streams after "
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
EVENT_STATUS_SPEC = ToolSpec(
    id=ToolId("events.status"),
    summary="read fresh source coverage and health without provider calls.",
    documentation=PromptDocument(
        "enabled is not readiness. counts cover known streams, not "
        "complete inventory during a scan; last success is the oldest "
        "complete check and null if any is incomplete. pause is "
        "independent. resumed polling never reconstructs an expired "
        "interval."
    ),
    input_type=EventsStatusInput,
    success_type=EventsStatusSuccess,
    error_type=AccountUnavailable,
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
            implementation_revision="jarvis-" + str(spec.id).replace(".", "-") + "-v1",
            policy_epoch=PolicyEpoch("jarvis-events-v1"),
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


def attention_due(
    event: EventProjection, now: datetime, owner_zone: str
) -> datetime | None:
    from datetime import timedelta

    from jarvis.read_tools import AllDayEventTime, TimedEventTime
    from jarvis.work_schedule import DailyRule, resolve_occurrence

    if event.status == "cancelled":
        return None
    if isinstance(event.start, TimedEventTime):
        due = event.start.date_time - timedelta(minutes=15)
        if due > now:
            return None
        if now <= event.start.date_time or (
            isinstance(event.end, TimedEventTime) and now < event.end.date_time
        ):
            return due
    elif isinstance(event.start, AllDayEventTime):
        if event.start.date != now.astimezone(ZoneInfo(owner_zone)).date():
            return None
        due = resolve_occurrence(
            DailyRule(type="daily", at="09:00", zone=owner_zone), event.start.date
        )
        if due <= now:
            return due
    return None

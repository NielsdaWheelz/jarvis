"""Closed Slice 5 Gmail draft and Calendar write contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, Protocol, cast
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
    ToolSpec,
    Unavailable,
    canonical_json_bytes,
)
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from jarvis.read_tools import (
    CALENDAR_API_BASE_URL,
    GoogleReadProvider,
)
from jarvis.read_tools import (
    calendar_family as calendar_read_family,
)
from jarvis.read_tools import (
    gmail_family as gmail_read_family,
)

WRITE_ACTION_MAX_ATTEMPTS = 2


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _bounded_utf8(value: str, maximum: int, name: str) -> str:
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} exceeds its UTF-8 byte bound")
    return value


def _utc(value: datetime) -> datetime:
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC offset")
    return value


def _timezone(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("time zone must be a non-empty IANA name")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("time zone must be an installed IANA name") from exc
    return _bounded_utf8(value, 255, "time zone")


class Mailbox(_StrictModel):
    name: Annotated[str | None, Field(max_length=320)]
    address: Annotated[str, Field(min_length=3, max_length=320)]

    @field_validator("name")
    @classmethod
    def bounded_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\r" in value or "\n" in value:
            raise ValueError("mailbox name contains a line break")
        return _bounded_utf8(value, 320, "mailbox name")

    @field_validator("address")
    @classmethod
    def normalized_address(cls, value: str) -> str:
        if value != value.strip() or "\r" in value or "\n" in value:
            raise ValueError("mailbox address is not normalized")
        local, separator, domain = value.rpartition("@")
        if (
            not separator
            or not local
            or not domain
            or any(character.isspace() for character in value)
        ):
            raise ValueError("mailbox address is invalid")
        try:
            normalized_domain = domain.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("mailbox domain is invalid") from exc
        return _bounded_utf8(f"{local}@{normalized_domain}", 320, "mailbox address")


class GmailReplyTo(_StrictModel):
    thread_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    parent_message_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    parent_rfc822_message_id: Annotated[str, Field(min_length=1, max_length=998)]

    @field_validator("thread_id", "parent_message_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Gmail ID")

    @field_validator("parent_rfc822_message_id")
    @classmethod
    def bounded_header(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("RFC 822 message ID contains a line break")
        return _bounded_utf8(value, 998, "RFC 822 message ID")


class GmailContent(_StrictModel):
    to: Annotated[tuple[Mailbox, ...], Field(min_length=1, max_length=50)]
    cc: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    bcc: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    subject: Annotated[str, Field(max_length=998)]
    body_text: Annotated[str, Field(max_length=100_000)]
    reply_to: GmailReplyTo | None

    @field_validator("subject")
    @classmethod
    def bounded_subject(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("Gmail subject contains a line break")
        return _bounded_utf8(value, 998, "Gmail subject")

    @field_validator("body_text")
    @classmethod
    def bounded_body(cls, value: str) -> str:
        return _bounded_utf8(value, 100_000, "Gmail body")


class GmailCreateDraftInput(_StrictModel):
    content: GmailContent


class GmailUpdateDraftInput(_StrictModel):
    draft_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    expected_content_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    replacement: GmailContent

    @field_validator("draft_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Gmail draft ID")


class GmailSendDraftInput(_StrictModel):
    draft_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    thread_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    jarvis_effect_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    content: GmailContent

    @field_validator("draft_id", "thread_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Gmail ID")


class GmailDraftSuccess(_StrictModel):
    draft_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    message_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    thread_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    jarvis_effect_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    content_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    observed_at: AwareDatetime

    @field_validator("draft_id", "message_id", "thread_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Gmail ID")

    _utc_observed_at = field_validator("observed_at")(_utc)


class GmailSendDraftSuccess(_StrictModel):
    sent_message_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    thread_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    jarvis_effect_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    content_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    sent_at: AwareDatetime

    @field_validator("sent_message_id", "thread_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Gmail ID")

    _utc_sent_at = field_validator("sent_at")(_utc)


class TimedEventTime(_StrictModel):
    type: Literal["timed"] = "timed"
    date_time: AwareDatetime
    time_zone: Annotated[str, Field(min_length=1, max_length=255)]

    _valid_timezone = field_validator("time_zone")(_timezone)


class AllDayEventTime(_StrictModel):
    type: Literal["all_day"] = "all_day"
    date: date


type EventTime = Annotated[
    TimedEventTime | AllDayEventTime,
    Field(discriminator="type"),
]


class Reminder(_StrictModel):
    method: Literal["email", "popup"]
    minutes: Annotated[int, Field(ge=0, le=40_320)]


class CalendarWritableEvent(_StrictModel):
    summary: Annotated[str, Field(max_length=1_024)]
    description: Annotated[str | None, Field(max_length=16_384)]
    location: Annotated[str | None, Field(max_length=4_096)]
    start: EventTime
    end: EventTime
    recurrence: Annotated[
        tuple[Annotated[str, Field(max_length=1_024)], ...],
        Field(max_length=20),
    ]
    attendees: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    use_default_reminders: bool
    reminders: Annotated[tuple[Reminder, ...], Field(max_length=10)]

    @field_validator("summary")
    @classmethod
    def bounded_summary(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "event summary")

    @field_validator("description")
    @classmethod
    def bounded_description(cls, value: str | None) -> str | None:
        return None if value is None else _bounded_utf8(value, 16_384, "description")

    @field_validator("location")
    @classmethod
    def bounded_location(cls, value: str | None) -> str | None:
        return None if value is None else _bounded_utf8(value, 4_096, "location")

    @field_validator("recurrence")
    @classmethod
    def bounded_recurrence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_bounded_utf8(item, 1_024, "recurrence") for item in value)


class CalendarEventSnapshot(_StrictModel):
    calendar_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    event_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    etag: Annotated[str, Field(min_length=1, max_length=1_024)]
    status: Literal["confirmed", "tentative"]
    writable: CalendarWritableEvent
    organizer: Mailbox | None
    updated_at: AwareDatetime

    @field_validator("calendar_id", "event_id", "etag")
    @classmethod
    def bounded_identity(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Calendar identity")


class CalendarCreateEventInput(_StrictModel):
    calendar_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    event: CalendarWritableEvent
    notify_attendees: bool

    @field_validator("calendar_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "calendar ID")


class CalendarUpdateEventInput(_StrictModel):
    expected: CalendarEventSnapshot
    replacement: CalendarWritableEvent
    notify_attendees: bool


class CalendarDeleteEventInput(_StrictModel):
    expected: CalendarEventSnapshot
    notify_attendees: bool


class CalendarCreateEventSuccess(_StrictModel):
    event: CalendarEventSnapshot
    created_at: AwareDatetime

    _utc_created_at = field_validator("created_at")(_utc)


class CalendarUpdateEventSuccess(_StrictModel):
    event: CalendarEventSnapshot
    updated_at: AwareDatetime

    _utc_updated_at = field_validator("updated_at")(_utc)


class CalendarDeleteEventSuccess(_StrictModel):
    calendar_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    event_id: Annotated[str, Field(min_length=1, max_length=1_024)]
    prior_etag: Annotated[str, Field(min_length=1, max_length=1_024)]
    deleted_at: AwareDatetime

    @field_validator("calendar_id", "event_id", "prior_etag")
    @classmethod
    def bounded_identity(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Calendar identity")

    _utc_deleted_at = field_validator("deleted_at")(_utc)


class InvalidRecipient(_StrictModel):
    type: Literal["InvalidRecipient"] = "InvalidRecipient"


class ThreadNotFound(_StrictModel):
    type: Literal["ThreadNotFound"] = "ThreadNotFound"


class ThreadMismatch(_StrictModel):
    type: Literal["ThreadMismatch"] = "ThreadMismatch"


class Conflict(_StrictModel):
    type: Literal["Conflict"] = "Conflict"


class DraftNotFound(_StrictModel):
    type: Literal["DraftNotFound"] = "DraftNotFound"


class DraftChanged(_StrictModel):
    type: Literal["DraftChanged"] = "DraftChanged"


class InvalidEvent(_StrictModel):
    type: Literal["InvalidEvent"] = "InvalidEvent"


class CalendarNotFound(_StrictModel):
    type: Literal["CalendarNotFound"] = "CalendarNotFound"


class EventIdConflict(_StrictModel):
    type: Literal["EventIdConflict"] = "EventIdConflict"


class UnsupportedEventType(_StrictModel):
    type: Literal["UnsupportedEventType"] = "UnsupportedEventType"


class EventNotFound(_StrictModel):
    type: Literal["EventNotFound"] = "EventNotFound"


class EventChanged(_StrictModel):
    type: Literal["EventChanged"] = "EventChanged"


class RateLimited(_StrictModel):
    type: Literal["RateLimited"] = "RateLimited"


class ProviderUnavailable(_StrictModel):
    type: Literal["ProviderUnavailable"] = "ProviderUnavailable"


type GmailCreateDraftError = (
    InvalidRecipient
    | ThreadNotFound
    | ThreadMismatch
    | Conflict
    | RateLimited
    | ProviderUnavailable
)
type GmailUpdateDraftError = (
    DraftNotFound | DraftChanged | ThreadMismatch | RateLimited | ProviderUnavailable
)
type GmailSendDraftError = (
    DraftNotFound | DraftChanged | InvalidRecipient | RateLimited | ProviderUnavailable
)
type CalendarCreateEventError = (
    InvalidEvent
    | CalendarNotFound
    | EventIdConflict
    | UnsupportedEventType
    | RateLimited
    | ProviderUnavailable
)
type CalendarUpdateEventError = (
    EventNotFound
    | EventChanged
    | InvalidEvent
    | UnsupportedEventType
    | RateLimited
    | ProviderUnavailable
)
type CalendarDeleteEventError = (
    EventNotFound
    | EventChanged
    | UnsupportedEventType
    | RateLimited
    | ProviderUnavailable
)


@dataclass(frozen=True, slots=True)
class WriteResponse[ValueT]:
    value: ValueT
    attempts: int

    def __post_init__(self) -> None:
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("write attempt count must be a non-negative integer")


class WriteConnectorFailure(RuntimeError):
    def __init__(self, code: str, *, attempts: int) -> None:
        if not code or type(attempts) is not int or attempts < 0:
            raise ValueError("write connector failure evidence is invalid")
        self.code = code
        self.attempts = attempts
        super().__init__("write connector failed")


@dataclass(frozen=True, slots=True)
class WriteAttemptBudget:
    recovered_attempts: int
    max_attempts: int

    def __post_init__(self) -> None:
        if (
            type(self.recovered_attempts) is not int
            or self.recovered_attempts < 0
            or type(self.max_attempts) is not int
            or self.max_attempts <= 0
        ):
            raise ValueError("write attempt budget is invalid")


class GoogleWriteProvider(Protocol):
    async def gmail_create_draft(
        self,
        value: GmailCreateDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]: ...

    async def gmail_update_draft(
        self,
        value: GmailUpdateDraftInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]: ...

    async def calendar_create_event(
        self,
        value: CalendarCreateEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarCreateEventSuccess]: ...

    async def calendar_update_event(
        self,
        value: CalendarUpdateEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarUpdateEventSuccess]: ...

    async def calendar_delete_event(
        self,
        value: CalendarDeleteEventInput,
        effect_id: UUID,
        attempt_budget: WriteAttemptBudget,
    ) -> WriteResponse[CalendarDeleteEventSuccess]: ...


GMAIL_CREATE_DRAFT_SPEC = ToolSpec[
    GmailCreateDraftInput, GmailDraftSuccess, GmailCreateDraftError
](
    id=ToolId("gmail.create_draft"),
    summary="Create an unsent Gmail draft.",
    documentation=PromptDocument(
        "Create an unsent draft only. This never sends mail. Use reply_to only from "
        "live Gmail evidence and preserve every intended recipient and body detail."
    ),
    input_type=GmailCreateDraftInput,
    success_type=GmailDraftSuccess,
    error_type=cast(type[GmailCreateDraftError], GmailCreateDraftError),
    effect=ToolEffect.Write,
    limits=ToolLimits(262_144, 65_536, 4, 20.0),
)
GMAIL_UPDATE_DRAFT_SPEC = ToolSpec[
    GmailUpdateDraftInput, GmailDraftSuccess, GmailUpdateDraftError
](
    id=ToolId("gmail.update_draft"),
    summary="Replace one unchanged unsent Gmail draft.",
    documentation=PromptDocument(
        "Replace an unsent draft only after its exact content digest still matches. "
        "This never sends mail and never overwrites a concurrently changed draft."
    ),
    input_type=GmailUpdateDraftInput,
    success_type=GmailDraftSuccess,
    error_type=cast(type[GmailUpdateDraftError], GmailUpdateDraftError),
    effect=ToolEffect.Write,
    limits=ToolLimits(262_144, 65_536, 4, 20.0),
)
GMAIL_SEND_DRAFT_SPEC = ToolSpec[
    GmailSendDraftInput, GmailSendDraftSuccess, GmailSendDraftError
](
    id=ToolId("gmail.send_draft"),
    summary="Send one exact unchanged Gmail draft after owner approval.",
    documentation=PromptDocument(
        "This consequential communication always requires the host-owned Approve or "
        "Deny flow. Slice 5 declares the exact contract but cannot execute it."
    ),
    input_type=GmailSendDraftInput,
    success_type=GmailSendDraftSuccess,
    error_type=cast(type[GmailSendDraftError], GmailSendDraftError),
    effect=ToolEffect.Write,
    limits=ToolLimits(262_144, 65_536, 4, 20.0),
)
CALENDAR_CREATE_EVENT_SPEC = ToolSpec[
    CalendarCreateEventInput, CalendarCreateEventSuccess, CalendarCreateEventError
](
    id=ToolId("calendar.create_event"),
    summary="Create one Google Calendar event.",
    documentation=PromptDocument(
        "Create exactly one event. Automatic execution is restricted by host policy "
        "to verified owner-only calendars and events with no attendees."
    ),
    input_type=CalendarCreateEventInput,
    success_type=CalendarCreateEventSuccess,
    error_type=cast(type[CalendarCreateEventError], CalendarCreateEventError),
    effect=ToolEffect.Write,
    limits=ToolLimits(262_144, 131_072, 2, 20.0),
)
CALENDAR_UPDATE_EVENT_SPEC = ToolSpec[
    CalendarUpdateEventInput, CalendarUpdateEventSuccess, CalendarUpdateEventError
](
    id=ToolId("calendar.update_event"),
    summary="Conditionally replace one Google Calendar event.",
    documentation=PromptDocument(
        "Replace the writable projection only when the live event still has the "
        "complete expected snapshot and etag."
    ),
    input_type=CalendarUpdateEventInput,
    success_type=CalendarUpdateEventSuccess,
    error_type=cast(type[CalendarUpdateEventError], CalendarUpdateEventError),
    effect=ToolEffect.Write,
    limits=ToolLimits(524_288, 131_072, 2, 20.0),
)
CALENDAR_DELETE_EVENT_SPEC = ToolSpec[
    CalendarDeleteEventInput, CalendarDeleteEventSuccess, CalendarDeleteEventError
](
    id=ToolId("calendar.delete_event"),
    summary="Conditionally delete one Google Calendar event.",
    documentation=PromptDocument(
        "Delete only when the live event still has the complete expected snapshot "
        "and etag. Host policy controls whether execution is automatic."
    ),
    input_type=CalendarDeleteEventInput,
    success_type=CalendarDeleteEventSuccess,
    error_type=cast(type[CalendarDeleteEventError], CalendarDeleteEventError),
    effect=ToolEffect.Write,
    limits=ToolLimits(262_144, 65_536, 2, 20.0),
)

AUTOMATIC_WRITE_TOOL_IDS = frozenset(
    (
        GMAIL_CREATE_DRAFT_SPEC.id,
        GMAIL_UPDATE_DRAFT_SPEC.id,
        CALENDAR_CREATE_EVENT_SPEC.id,
        CALENDAR_UPDATE_EVENT_SPEC.id,
        CALENDAR_DELETE_EVENT_SPEC.id,
    )
)
WRITE_TOOL_IDS = AUTOMATIC_WRITE_TOOL_IDS | {GMAIL_SEND_DRAFT_SPEC.id}


def _declared_error(code: str) -> _StrictModel:
    errors: dict[str, type[_StrictModel]] = {
        "calendar_not_found": CalendarNotFound,
        "conflict": Conflict,
        "draft_changed": DraftChanged,
        "draft_not_found": DraftNotFound,
        "event_changed": EventChanged,
        "event_id_conflict": EventIdConflict,
        "event_not_found": EventNotFound,
        "invalid_event": InvalidEvent,
        "invalid_recipient": InvalidRecipient,
        "provider_unavailable": ProviderUnavailable,
        "rate_limited": RateLimited,
        "thread_mismatch": ThreadMismatch,
        "thread_not_found": ThreadNotFound,
        "unsupported_event_type": UnsupportedEventType,
    }
    error_type = errors.get(code)
    if error_type is None:
        raise RuntimeError("connector returned an undeclared failure code")
    return error_type()


async def _run[InputT, SuccessT](
    operation: Callable[
        [InputT, UUID, WriteAttemptBudget], Awaitable[WriteResponse[SuccessT]]
    ],
    value: InputT,
    context: ExecutionContext,
) -> HandlerSuccess[SuccessT]:
    if context.effect_id is None or context.position != context.effect_id:
        raise RuntimeError("write position and effect identity must be the action ID")
    try:
        effect_id = UUID(str(context.effect_id))
    except ValueError as exc:
        raise RuntimeError("write effect identity must be a canonical UUID") from exc
    if str(effect_id) != str(context.effect_id):
        raise RuntimeError("write effect identity must be a canonical UUID")
    try:
        declared_attempts = context.plan.grant(context.grant.id).limits.max_attempts
        remaining_attempts = context.grant.limits.max_attempts
        recovered_attempts = declared_attempts - remaining_attempts
        response = await operation(
            value,
            effect_id,
            WriteAttemptBudget(recovered_attempts, remaining_attempts),
        )
    except WriteConnectorFailure as exc:
        raise DeclaredToolFailure(
            _declared_error(exc.code), actual_attempts=exc.attempts
        ) from exc
    envelope = {
        "type": "Success",
        "value": cast("Any", response.value).model_dump(mode="json"),
    }
    if len(canonical_json_bytes(envelope)) > context.grant.limits.max_output_bytes:
        raise RuntimeError("write provider result exceeds the granted output bound")
    return HandlerSuccess(response.value, actual_attempts=response.attempts)


def _binding[InputT, SuccessT, ErrorT](
    spec: ToolSpec[InputT, SuccessT, ErrorT],
    operation: Callable[
        [InputT, UUID, WriteAttemptBudget], Awaitable[WriteResponse[SuccessT]]
    ],
    policy_inputs: dict[str, object],
    *,
    implementation_revision: str | None = None,
) -> ToolBinding[InputT, SuccessT, ErrorT]:
    async def execute(
        value: InputT, context: ExecutionContext
    ) -> HandlerSuccess[SuccessT]:
        return await _run(operation, value, context)

    return ToolBinding(
        spec=spec,
        execute=Available(execute),
        replay_policy=ReplayPolicy.ReDispatchable,
        implementation_revision=(
            implementation_revision or f"jarvis-{str(spec.id).replace('.', '-')}-v1"
        ),
        policy_epoch=PolicyEpoch("jarvis-write-v1"),
        policy_inputs={
            "action_max_attempts": WRITE_ACTION_MAX_ATTEMPTS,
            "authority": "automatic-write-gated",
            **policy_inputs,
        },
    )


def gmail_write_family(provider: GoogleWriteProvider) -> ToolFamily:
    return ToolFamily(
        namespace="gmail",
        declarations=(
            GMAIL_CREATE_DRAFT_SPEC,
            GMAIL_UPDATE_DRAFT_SPEC,
            GMAIL_SEND_DRAFT_SPEC,
        ),
        bindings=(
            _binding(
                GMAIL_CREATE_DRAFT_SPEC,
                provider.gmail_create_draft,
                {
                    "effect_header": "X-Jarvis-Effect-ID",
                    "effect_identity": "sha256(jarvis-gmail-v1:action-id)",
                    "send": False,
                },
                implementation_revision="jarvis-gmail-create_draft-v1",
            ),
            _binding(
                GMAIL_UPDATE_DRAFT_SPEC,
                provider.gmail_update_draft,
                {
                    "conflict_check": "exact-normalized-content-digest",
                    "effect_header": "preserve-X-Jarvis-Effect-ID",
                    "send": False,
                },
            ),
            ToolBinding(
                spec=GMAIL_SEND_DRAFT_SPEC,
                execute=Unavailable("Slice 6 approval execution is not implemented"),
                replay_policy=ReplayPolicy.ReDispatchable,
                implementation_revision="jarvis-gmail-send_draft-v1",
                policy_epoch=PolicyEpoch("jarvis-write-v1"),
                policy_inputs={
                    "action_max_attempts": WRITE_ACTION_MAX_ATTEMPTS,
                    "authority": "approval-required-unavailable-slice-5",
                    "effect_header": "preserve-X-Jarvis-Effect-ID",
                },
            ),
        ),
    )


def calendar_write_family(provider: GoogleWriteProvider) -> ToolFamily:
    return ToolFamily(
        namespace="calendar",
        declarations=(
            CALENDAR_CREATE_EVENT_SPEC,
            CALENDAR_UPDATE_EVENT_SPEC,
            CALENDAR_DELETE_EVENT_SPEC,
        ),
        bindings=(
            _binding(
                CALENDAR_CREATE_EVENT_SPEC,
                provider.calendar_create_event,
                {
                    "create_id": "first-32-hex-sha256(jarvis-calendar-v1:action-id)",
                    "endpoint": (
                        f"{CALENDAR_API_BASE_URL}/calendars/{{calendar_id}}/events"
                    ),
                },
                implementation_revision="jarvis-calendar-create_event-v1",
            ),
            _binding(
                CALENDAR_UPDATE_EVENT_SPEC,
                provider.calendar_update_event,
                {"conditional": "If-Match expected.etag", "http_method": "PATCH"},
            ),
            _binding(
                CALENDAR_DELETE_EVENT_SPEC,
                provider.calendar_delete_event,
                {"conditional": "If-Match expected.etag", "http_method": "DELETE"},
            ),
        ),
    )


def gmail_main_family(
    read_provider: GoogleReadProvider, write_provider: GoogleWriteProvider
) -> ToolFamily:
    reads = gmail_read_family(read_provider)
    writes = gmail_write_family(write_provider)
    return ToolFamily(
        namespace="gmail",
        declarations=reads.declarations + writes.declarations,
        bindings=reads.bindings + writes.bindings,
    )


def calendar_main_family(
    read_provider: GoogleReadProvider, write_provider: GoogleWriteProvider
) -> ToolFamily:
    reads = calendar_read_family(read_provider)
    writes = calendar_write_family(write_provider)
    return ToolFamily(
        namespace="calendar",
        declarations=reads.declarations + writes.declarations,
        bindings=reads.bindings + writes.bindings,
    )


__all__ = [
    "AUTOMATIC_WRITE_TOOL_IDS",
    "CALENDAR_CREATE_EVENT_SPEC",
    "CALENDAR_DELETE_EVENT_SPEC",
    "CALENDAR_UPDATE_EVENT_SPEC",
    "GMAIL_CREATE_DRAFT_SPEC",
    "GMAIL_SEND_DRAFT_SPEC",
    "GMAIL_UPDATE_DRAFT_SPEC",
    "WRITE_ACTION_MAX_ATTEMPTS",
    "WRITE_TOOL_IDS",
    "AllDayEventTime",
    "CalendarCreateEventInput",
    "CalendarCreateEventSuccess",
    "CalendarDeleteEventInput",
    "CalendarDeleteEventSuccess",
    "CalendarEventSnapshot",
    "CalendarUpdateEventInput",
    "CalendarUpdateEventSuccess",
    "CalendarWritableEvent",
    "EventTime",
    "GmailContent",
    "GmailCreateDraftInput",
    "GmailDraftSuccess",
    "GmailReplyTo",
    "GmailSendDraftInput",
    "GmailSendDraftSuccess",
    "GmailUpdateDraftInput",
    "GoogleWriteProvider",
    "Mailbox",
    "Reminder",
    "TimedEventTime",
    "WriteAttemptBudget",
    "WriteConnectorFailure",
    "WriteResponse",
    "calendar_main_family",
    "calendar_write_family",
    "gmail_main_family",
    "gmail_write_family",
]

"""Closed Google Workspace write contracts and tool bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from llm_tools import (
    Available,
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
)
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from jarvis.mail_files import (
    MAIL_MAX_FILES,
    FileUnavailable,
    MailFile,
    MailLimit,
    Sha256,
)
from jarvis.read_tools import ATTACHMENT_OPERATION_SECONDS
from jarvis.workspace_mcp import HUMAN_WAIT_SECONDS
from jarvis.workspace_write_models import (
    CalendarWriteReceipt,
    CreateDraft,
    CreateEvent,
    DeleteEvent,
    DocsUpdate,
    DraftWriteReceipt,
    DriveCopy,
    DriveCreate,
    DriveRevise,
    DriveWriteReceipt,
    UpdateEvent,
)
from jarvis.write_connectors import WorkspaceWriteFailure, execute_workspace_write

if TYPE_CHECKING:
    from jarvis.workspace_writes import WorkspaceWrites


# Original types and declarations used by the historical draft and proposal views.
@dataclass(frozen=True, slots=True)
class GmailWritePolicy:
    max_attempts: int = 12
    operation_seconds: float = 180.0
    mime_bytes: int = 36_700_160
    raw_bytes: int = 48 * 1024 * 1024
    metadata_bytes: int = 2 * 1024 * 1024


GMAIL_WRITE_POLICY = GmailWritePolicy()


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


class _GmailEnvelope(_StrictModel):
    to: Annotated[tuple[Mailbox, ...], Field(min_length=1, max_length=50)]
    cc: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    bcc: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    subject: Annotated[str, Field(max_length=998)]
    body_text: Annotated[str, Field(max_length=100_000)]

    @field_validator("subject")
    @classmethod
    def bounded_subject(cls, value: str) -> str:
        if any(
            character in value for character in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"
        ):
            raise ValueError("Gmail subject contains a line break")
        return _bounded_utf8(value, 998, "Gmail subject")

    @field_validator("body_text")
    @classmethod
    def bounded_body(cls, value: str) -> str:
        return _bounded_utf8(value, 100_000, "Gmail body")


class GmailContent(_GmailEnvelope):
    reply_to: GmailReplyTo | None


type GmailId = Annotated[str, Field(min_length=1, max_length=1_024)]
type MailPartNumber = Annotated[int, Field(strict=True, ge=1)]
type RfcMessageId = Annotated[str, Field(min_length=3, max_length=998)]


class GmailDraftIdentity(_StrictModel):
    draft_id: GmailId
    thread_id: GmailId
    message_id: GmailId

    @field_validator("draft_id", "thread_id", "message_id")
    @classmethod
    def bounded_id(cls, value: str) -> str:
        return _bounded_utf8(value, 1_024, "Gmail ID")


class GmailRevision(GmailDraftIdentity):
    account: GmailId
    jarvis_effect_id: Sha256
    content_digest: Sha256


class GmailSnapshot(_GmailEnvelope):
    model_config = ConfigDict(
        validate_by_name=True,
        serialize_by_alias=True,
    )

    sender: Annotated[str, Field(alias="from", min_length=3, max_length=320)]
    in_reply_to: RfcMessageId | None
    references: tuple[RfcMessageId, ...]
    files: Annotated[tuple[MailFile, ...], Field(max_length=MAIL_MAX_FILES)]


class GmailStagedPart(_StrictModel):
    slot: MailPartNumber
    file: MailFile


class GmailRetainedPart(_StrictModel):
    existing_part: MailPartNumber
    file: MailFile


class GmailComposeContract(_StrictModel):
    kind: Literal["compose"] = "compose"
    creation_id: UUID
    base_revision: GmailRevision | None
    parts: Annotated[
        tuple[GmailStagedPart | GmailRetainedPart, ...],
        Field(max_length=MAIL_MAX_FILES),
    ]


class GmailCurrentDraft(_StrictModel):
    state: Literal["draft"] = "draft"
    draft_ref: UUID
    revision: GmailRevision
    in_reply_to: RfcMessageId | None
    references: tuple[RfcMessageId, ...]
    files: Annotated[tuple[MailFile, ...], Field(max_length=MAIL_MAX_FILES)]
    observed_at: AwareDatetime

    _utc_observed_at = field_validator("observed_at")(_utc)


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


class CalendarCreateEventSuccess(_StrictModel):
    account: Annotated[str | None, Field(min_length=1, max_length=1_024)]
    event: CalendarEventSnapshot
    created_at: AwareDatetime

    _utc_created_at = field_validator("created_at")(_utc)


class CalendarUpdateEventSuccess(_StrictModel):
    account: Annotated[str | None, Field(min_length=1, max_length=1_024)]
    event: CalendarEventSnapshot
    updated_at: AwareDatetime

    _utc_updated_at = field_validator("updated_at")(_utc)


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
_GMAIL_FILE_GUIDANCE = (
    "For a Drive item, pass its subject and id. Native Docs need an explicit export. "
    "For a machine file, use a worker and scp into a 0700 request "
    "directory under /var/lib/jarvis-notes/.git/jarvis-mail/incoming on dev-server. "
    "Verify source and copy size and SHA-256, then publish the copy with the "
    "selected release's deploy/jarvis-mail-file prepare PATH. Use its returned "
    "native ref. If the source is unavailable, give the machine, file and one "
    "recovery. Never substitute a link for a requested attachment."
)


HISTORICAL_CALENDAR_CREATE_EVENT_SPEC = ToolSpec[
    CalendarCreateEventInput, CalendarCreateEventSuccess, CalendarCreateEventError
](
    id=ToolId("calendar.create_event"),
    summary="Create one Google Calendar event.",
    documentation=PromptDocument(
        "Create exactly one event. Automatic execution is restricted by host policy "
        "to verified owner-only calendars and events with no attendees. Timed start "
        "and end discard fractional seconds; the resulting interval must be positive."
    ),
    input_type=CalendarCreateEventInput,
    success_type=CalendarCreateEventSuccess,
    error_type=cast(type[CalendarCreateEventError], CalendarCreateEventError),
    effect=ToolEffect.Write,
    limits=ToolLimits(262_144, 131_072, 3, 20.0),
)
HISTORICAL_CALENDAR_UPDATE_EVENT_SPEC = ToolSpec[
    CalendarUpdateEventInput, CalendarUpdateEventSuccess, CalendarUpdateEventError
](
    id=ToolId("calendar.update_event"),
    summary="Conditionally replace one Google Calendar event.",
    documentation=PromptDocument(
        "Replace the writable projection only when the live event still has the "
        "complete expected snapshot and etag. Replacement timed start and end "
        "discard fractional seconds; the resulting interval must be positive. "
        "The expected snapshot stays exact."
    ),
    input_type=CalendarUpdateEventInput,
    success_type=CalendarUpdateEventSuccess,
    error_type=cast(type[CalendarUpdateEventError], CalendarUpdateEventError),
    effect=ToolEffect.Write,
    limits=ToolLimits(524_288, 131_072, 3, 20.0),
)
type WorkspaceFailure = WorkspaceWriteFailure | FileUnavailable | MailLimit


def _workspace_spec(
    name: str,
    summary: str,
    documentation: str,
    input_type: type[BaseModel],
    success_type: type[BaseModel],
    limits: ToolLimits,
) -> ToolSpec[Any, Any, Any]:
    return ToolSpec(
        id=ToolId(name),
        summary=summary,
        documentation=PromptDocument(documentation),
        input_type=input_type,
        success_type=success_type,
        error_type=cast(type[WorkspaceFailure], WorkspaceFailure),
        effect=ToolEffect.Write,
        limits=limits,
    )


# One executor entry includes the separately bounded provider exchanges and consent.
_GMAIL_LIMITS = ToolLimits(262_144, 65_536, 1, 180.0 + HUMAN_WAIT_SECONDS)
_CALENDAR_LIMITS = ToolLimits(262_144, 65_536, 1, 20.0 + HUMAN_WAIT_SECONDS)

GMAIL_CREATE_DRAFT_SPEC = _workspace_spec(
    "gmail.create_draft",
    "Save one unsent Gmail draft.",
    "Use the intended recipients, reply parent and ordered files. "
    "Report Gmail's acknowledged draft id and its separate verification. "
    + _GMAIL_FILE_GUIDANCE,
    CreateDraft,
    DraftWriteReceipt,
    _GMAIL_LIMITS,
)
CALENDAR_CREATE_EVENT_SPEC = _workspace_spec(
    "calendar.create_event",
    "Create one Calendar event for the enrolled owner alone.",
    "Supply the calendar and the event fields. The connector verifies the effective "
    "organizer and suppresses guest notifications.",
    CreateEvent,
    CalendarWriteReceipt,
    _CALENDAR_LIMITS,
)
CALENDAR_UPDATE_EVENT_SPEC = _workspace_spec(
    "calendar.update_event",
    "Change one verified solo Calendar event.",
    "Name the event and scope and give the changed fields. The connector verifies "
    "participation immediately before sending. Clearing the summary, description "
    "or location and converting all-day events to timed events are unavailable.",
    UpdateEvent,
    CalendarWriteReceipt,
    _CALENDAR_LIMITS,
)
CALENDAR_DELETE_EVENT_SPEC = _workspace_spec(
    "calendar.delete_event",
    "Delete one verified solo Calendar event.",
    "Name the calendar, event and scope. A lost acknowledgement is uncertain.",
    DeleteEvent,
    CalendarWriteReceipt,
    _CALENDAR_LIMITS,
)
_DRIVE_LIMITS = ToolLimits(
    32_768, 65_536, 1, ATTACHMENT_OPERATION_SECONDS + HUMAN_WAIT_SECONDS
)
_DOCS_LIMITS = ToolLimits(32_768, 65_536, 1, 20.0 + HUMAN_WAIT_SECONDS)
DRIVE_CREATE_SPEC = _workspace_spec(
    "drive.create",
    "Create one Drive item at its intended destination.",
    "Give the destination folder, title and one exact source. Authored prose can "
    "use a Google Doc. Owner uploads, selected Gmail parts and native publications "
    "keep their bytes. Report the Drive id and verification separately.",
    DriveCreate,
    DriveWriteReceipt,
    _DRIVE_LIMITS,
)
DRIVE_COPY_SPEC = _workspace_spec(
    "drive.copy",
    "Copy one existing Drive item under a new id.",
    "Give the source id, destination folder and new title. Copying leaves the "
    "source in place. If Google may have created the copy, report the uncertainty.",
    DriveCopy,
    DriveWriteReceipt,
    _DRIVE_LIMITS,
)
DRIVE_REVISE_SPEC = _workspace_spec(
    "drive.revise",
    "Replace the bytes of one Drive file under its current id.",
    "Use the exact fresh etag returned by Drive metadata and a verified source. "
    "A conflict requires a fresh observation and the owner's intended edit.",
    DriveRevise,
    DriveWriteReceipt,
    _DRIVE_LIMITS,
)
DOCS_UPDATE_SPEC = _workspace_spec(
    "docs.update",
    "Apply one ordered edit or suggestion to an existing Google Doc.",
    "Use the observed Docs revision and the actual tab, segment and UTF-16 "
    "positions from Docs. Stop on revision conflict. Report provider warnings and "
    "the observed verification.",
    DocsUpdate,
    DriveWriteReceipt,
    _DOCS_LIMITS,
)
_CALENDAR_SPECS = (
    CALENDAR_CREATE_EVENT_SPEC,
    CALENDAR_UPDATE_EVENT_SPEC,
    CALENDAR_DELETE_EVENT_SPEC,
)
_DRIVE_SPECS = (DRIVE_CREATE_SPEC, DRIVE_COPY_SPEC, DRIVE_REVISE_SPEC)
_DOCS_SPECS = (DOCS_UPDATE_SPEC,)
DRIVE_WRITE_IDS = frozenset(spec.id for spec in _DRIVE_SPECS)
DOCS_WRITE_IDS = frozenset(spec.id for spec in _DOCS_SPECS)
WRITE_TOOL_IDS = frozenset(
    spec.id
    for spec in (GMAIL_CREATE_DRAFT_SPEC, *_CALENDAR_SPECS, *_DRIVE_SPECS, *_DOCS_SPECS)
)
RETIRED_DRAFT_WRITE_IDS = ("gmail.prepare_replacement", "gmail.discard_draft")
WORKSPACE_IMPLEMENTATION = "jarvis-workspace-write-v1"
WORKSPACE_WRITE_IMPLEMENTATION = "jarvis-workspace-write-v2"
WORKSPACE_MAIL_SNAPSHOT_IMPLEMENTATION = "jarvis-workspace-mail-preview-v2"
WORKSPACE_MAIL_IMPLEMENTATION = "jarvis-workspace-mail-owner-v3"
WORKSPACE_MAIL_SNAPSHOT_REVISIONS = frozenset(
    (WORKSPACE_MAIL_SNAPSHOT_IMPLEMENTATION, WORKSPACE_MAIL_IMPLEMENTATION)
)


def workspace_implementation(tool: ToolId) -> str:
    if tool == GMAIL_CREATE_DRAFT_SPEC.id:
        return WORKSPACE_MAIL_IMPLEMENTATION
    return WORKSPACE_WRITE_IMPLEMENTATION


def _workspace_binding(
    spec: ToolSpec[Any, Any, Any],
    writes: WorkspaceWrites,
) -> ToolBinding[Any, Any, Any]:
    async def execute(
        value: BaseModel, context: ExecutionContext
    ) -> HandlerSuccess[Any]:
        return await execute_workspace_write(writes, context)

    return ToolBinding(
        spec=spec,
        execute=Available(execute),
        replay_policy=ReplayPolicy.BilledOnce,
        implementation_revision=workspace_implementation(spec.id),
        policy_epoch=PolicyEpoch("jarvis-workspace-main-v2"),
        policy_inputs={"action_max_attempts": 1},
    )


def gmail_write_family(writes: WorkspaceWrites) -> ToolFamily:
    return ToolFamily(
        "gmail",
        (GMAIL_CREATE_DRAFT_SPEC,),
        (_workspace_binding(GMAIL_CREATE_DRAFT_SPEC, writes),),
    )


def calendar_write_family(writes: WorkspaceWrites) -> ToolFamily:
    return ToolFamily(
        "calendar",
        _CALENDAR_SPECS,
        tuple(_workspace_binding(s, writes) for s in _CALENDAR_SPECS),
    )


def drive_write_family(writes: WorkspaceWrites) -> ToolFamily:
    return ToolFamily(
        "drive",
        _DRIVE_SPECS,
        tuple(_workspace_binding(s, writes) for s in _DRIVE_SPECS),
    )


def docs_write_family(writes: WorkspaceWrites) -> ToolFamily:
    return ToolFamily(
        "docs",
        _DOCS_SPECS,
        tuple(_workspace_binding(s, writes) for s in _DOCS_SPECS),
    )

"""Workspace write inputs, frozen effects and receipts."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

from jarvis.mail_files import (
    MAIL_MAX_FILES,
    MailFile,
    NativeFileRef,
    NewMailFile,
    OriginalFileRef,
    Sha256,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _bounded_utf8(value: str, maximum: int, name: str) -> str:
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} exceeds its UTF-8 byte bound")
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


type ResourceId = Annotated[
    str, Field(min_length=1, max_length=1024, pattern=r"^[^\s\x00-\x1f\x7f]+$")
]
type Scope = Literal["single", "occurrence", "series"]
type Recipients = Annotated[tuple[Mailbox, ...], Field(max_length=50)]
type FileList = Annotated[tuple[NewMailFile, ...], Field(max_length=MAIL_MAX_FILES)]


class _Changes(_StrictModel):
    # Missing fields are semantically absent across both action persistence and replay.
    @model_serializer(mode="wrap")
    def _supplied(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result = handler(self)
        return {key: result[key] for key in self.model_fields_set}


class DraftChanges(_Changes):
    to: Recipients | None = None
    cc: Recipients | None = None
    bcc: Recipients | None = None
    subject: str | None = None
    body_text: str | None = None


class DraftRef(_StrictModel):
    draft_id: ResourceId
    message_id: ResourceId


class ExistingMailPart(_StrictModel):
    kind: Literal["existing"]
    existing_part: Annotated[int, Field(strict=True, ge=1, le=MAIL_MAX_FILES)]


type ReplacementFile = Annotated[
    OriginalFileRef | NativeFileRef | ExistingMailPart, Field(discriminator="kind")
]


class CreateDraft(_StrictModel):
    content: GmailContent
    files: FileList


class DraftEdits(_StrictModel):
    draft_ref: DraftRef
    changes: DraftChanges
    files: (
        Annotated[tuple[ReplacementFile, ...], Field(max_length=MAIL_MAX_FILES)] | None
    ) = None


class DiscardTarget(_Changes):
    standalone_draft_ref: DraftRef | None = None
    verified_replacement_action_id: UUID | None = None

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if len(self.model_fields_set) != 1 or (
            self.standalone_draft_ref is None
            and self.verified_replacement_action_id is None
        ):
            raise ValueError("specify exactly one discard target")
        return self


class DiscardSelection(_StrictModel):
    target: DiscardTarget


class EventRef(_StrictModel):
    calendar_id: ResourceId
    event_id: ResourceId
    scope: Scope


class CalendarChanges(_Changes):
    summary: Annotated[str, Field(max_length=1024)] | None = None
    description: Annotated[str, Field(max_length=16384)] | None = None
    location: Annotated[str, Field(max_length=4096)] | None = None
    start: EventTime | None = None
    end: EventTime | None = None
    recurrence: (
        Annotated[
            tuple[Annotated[str, Field(max_length=1024)], ...], Field(max_length=20)
        ]
        | None
    ) = None
    attendees: Recipients | None = None
    use_default_reminders: StrictBool | None = None
    reminders: Annotated[tuple[Reminder, ...], Field(max_length=10)] | None = None

    @field_validator("summary", "description", "location")
    @classmethod
    def bounded_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        bounds = {"summary": 1024, "description": 16384, "location": 4096}
        name = str(info.field_name)
        return None if value is None else _bounded_utf8(value, bounds[name], name)


type RemovedAttendees = Annotated[
    tuple[Annotated[str, Field(min_length=3, max_length=320)], ...],
    Field(min_length=1, max_length=50),
]


class CalendarEdits(CalendarChanges):
    remove_attendees: RemovedAttendees | None = None


class CreateEvent(_StrictModel):
    calendar: ResourceId
    fields: CalendarWritableEvent
    notify: StrictBool


class EventEdits(_StrictModel):
    event_ref: EventRef
    changes: CalendarEdits
    notify: StrictBool


class DeleteEvent(_StrictModel):
    event_ref: EventRef
    notify: StrictBool


class _Change[Tag: str, Value](_StrictModel):
    field: Tag
    value: Value


type DraftFieldChange = Annotated[
    _Change[
        Literal["to"],
        Annotated[tuple[Mailbox, ...], Field(min_length=1, max_length=50)],
    ]
    | _Change[Literal["cc"], Recipients]
    | _Change[Literal["bcc"], Recipients]
    | _Change[Literal["subject"], Annotated[str, Field(max_length=998)]]
    | _Change[Literal["body_text"], Annotated[str, Field(max_length=100_000)]],
    Field(discriminator="field"),
]
type CalendarFieldChange = Annotated[
    _Change[Literal["summary"], Annotated[str, Field(max_length=1024)]]
    | _Change[Literal["description"], Annotated[str, Field(max_length=16_384)] | None]
    | _Change[Literal["location"], Annotated[str, Field(max_length=4096)] | None]
    | _Change[Literal["start"], EventTime]
    | _Change[Literal["end"], EventTime]
    | _Change[
        Literal["recurrence"],
        Annotated[
            tuple[Annotated[str, Field(max_length=1024)], ...], Field(max_length=20)
        ],
    ]
    | _Change[Literal["attendees"], Recipients]
    | _Change[Literal["remove_attendees"], RemovedAttendees]
    | _Change[Literal["use_default_reminders"], StrictBool]
    | _Change[
        Literal["reminders"], Annotated[tuple[Reminder, ...], Field(max_length=10)]
    ],
    Field(discriminator="field"),
]


class PrepareReplacement(_StrictModel):
    draft_ref: DraftRef
    changes: Annotated[tuple[DraftFieldChange, ...], Field(max_length=5)]
    files: (
        Annotated[tuple[ReplacementFile, ...], Field(max_length=MAIL_MAX_FILES)] | None
    )

    @model_validator(mode="after")
    def exact_edits(self) -> Self:
        if len({change.field for change in self.changes}) != len(self.changes):
            raise ValueError("duplicate draft change")
        if not self.changes and self.files is None:
            raise ValueError("specify a draft change or final files")
        return self


class StandaloneDiscard(_StrictModel):
    kind: Literal["standalone"]
    standalone_draft_ref: DraftRef

    @property
    def verified_replacement_action_id(self) -> None:
        return None


class LinkedDiscard(_StrictModel):
    kind: Literal["replacement"]
    verified_replacement_action_id: UUID


class DiscardDraft(_StrictModel):
    target: Annotated[StandaloneDiscard | LinkedDiscard, Field(discriminator="kind")]


class UpdateEvent(_StrictModel):
    event_ref: EventRef
    changes: Annotated[
        tuple[CalendarFieldChange, ...], Field(min_length=1, max_length=10)
    ]
    notify: StrictBool

    @model_validator(mode="after")
    def unique_changes(self) -> Self:
        if len({change.field for change in self.changes}) != len(self.changes):
            raise ValueError("duplicate event change")
        return self


def workspace_write_arguments(payload: BaseModel) -> dict[str, object]:
    """Project a validated native request into semantic effect arguments."""
    args = payload.model_dump(mode="json")
    if isinstance(payload, PrepareReplacement | UpdateEvent):
        args["changes"] = {
            change["field"]: change["value"] for change in args["changes"]
        }
    elif isinstance(payload, DiscardDraft):
        args["target"] = payload.target.model_dump(mode="json", exclude={"kind"})
    return args


class DraftObservation(DraftRef):
    thread_id: ResourceId
    digest: Sha256
    subject: Annotated[str | None, Field(max_length=998)]
    link: str | None
    observed_at: AwareDatetime


class FrozenCompose(_StrictModel):
    tool: Literal["gmail.create_draft", "gmail.prepare_replacement"]
    old: DraftObservation | None
    content: GmailContent
    files: Annotated[tuple[MailFile, ...], Field(max_length=MAIL_MAX_FILES)]
    references: tuple[str, ...]
    # Only the digest of the verified parent's quoted text is needed for readback.
    quote_digest: Sha256 | None
    expected_body_digest: Sha256 | None


class FrozenDiscard(_StrictModel):
    tool: Literal["gmail.discard_draft"] = "gmail.discard_draft"
    old: DraftObservation
    replacement: DraftObservation | None
    verified_replacement_action_id: UUID | None


class EventObservation(_StrictModel):
    digest: Sha256
    fields: CalendarChanges
    observed_at: AwareDatetime


class EventAttendee(_StrictModel):
    email: str
    displayName: str | None = None


class CalendarMutation(_StrictModel):
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    allDay: StrictBool | None = None
    timeZone: str | None = None
    recurrenceData: tuple[str, ...] | None = None
    attendees: tuple[EventAttendee, ...] | None = None
    addedAttendees: tuple[EventAttendee, ...] | None = None
    removedAttendeeEmails: tuple[str, ...] | None = None
    overrideReminders: tuple[Reminder, ...] | None = None
    useDefaultReminders: StrictBool | None = None


class FrozenCalendar(_StrictModel):
    tool: Literal[
        "calendar.create_event", "calendar.update_event", "calendar.delete_event"
    ]
    calendar_id: ResourceId
    event_id: ResourceId | None
    scope: Scope
    notify: StrictBool
    prior: EventObservation | None
    wire: CalendarMutation
    expected: CalendarChanges
    preserved_digest: Sha256 | None


class FrozenWorkspaceWrite(_StrictModel):
    action_id: UUID
    grant_id: UUID
    account: str
    effect: Annotated[
        FrozenCompose | FrozenDiscard | FrozenCalendar, Field(discriminator="tool")
    ]

    @property
    def tool(self) -> str:
        return self.effect.tool


class _Receipt(_StrictModel):
    action_id: UUID
    grant_id: UUID
    account: str
    acknowledged_at: AwareDatetime
    observed_at: AwareDatetime
    verification: Literal["verified", "unverified"]
    reason: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")] | None

    @model_validator(mode="after")
    def verified_or_reason(self) -> Self:
        if (self.verification == "verified") != (self.reason is None):
            raise ValueError("unverified outcome needs a reason")
        return self


class DraftWriteReceipt(_Receipt):
    outcome: Literal["created"] = "created"
    old_draft_id: ResourceId | None
    old_message_id: ResourceId | None
    old_digest: Sha256 | None
    old_thread_id: ResourceId | None
    old_link: str | None
    old_observed_at: AwareDatetime | None
    new_draft_id: ResourceId
    new_message_id: ResourceId | None
    new_digest: Sha256 | None
    new_thread_id: ResourceId | None
    new_link: str | None
    files: tuple[MailFile, ...]
    generated_quote: bool | None

    @model_validator(mode="after")
    def evidence(self) -> Self:
        if self.verification == "verified" and (
            self.new_message_id is None
            or self.new_digest is None
            or self.new_thread_id is None
            or self.generated_quote is None
        ):
            raise ValueError("verified draft needs its exact revision")
        return self


class DiscardReceipt(_Receipt):
    outcome: Literal["trashed"] = "trashed"
    old_draft_id: ResourceId
    old_message_id: ResourceId
    old_link: str | None
    new_draft_id: ResourceId | None
    new_message_id: ResourceId | None
    new_link: str | None
    verified_replacement_action_id: UUID | None


class CalendarWriteReceipt(_Receipt):
    outcome: Literal["created", "updated", "deleted"]
    calendar_id: ResourceId
    event_id: ResourceId
    scope: Scope
    notify: StrictBool
    link: str | None

"""Workspace write inputs, frozen effects and receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    StrictInt,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

from jarvis.home_refs import DRIVE_MIME_PATTERN
from jarvis.home_refs import DriveId as DriveId
from jarvis.mail_files import (
    MAIL_MAX_FILES,
    DriveMailFileRef,
    MailFile,
    NativeFileRef,
    NewMailFile,
    Sha256,
)
from jarvis.read_tools import GoogleId


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
    DriveMailFileRef | NativeFileRef | ExistingMailPart, Field(discriminator="kind")
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
    use_default_reminders: StrictBool | None = None
    reminders: Annotated[tuple[Reminder, ...], Field(max_length=10)] | None = None

    @field_validator("summary", "description", "location")
    @classmethod
    def bounded_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        bounds = {"summary": 1024, "description": 16384, "location": 4096}
        name = str(info.field_name)
        return None if value is None else _bounded_utf8(value, bounds[name], name)


class CreateEvent(_StrictModel):
    calendar: ResourceId
    fields: CalendarWritableEvent


class EventEdits(_StrictModel):
    event_ref: EventRef
    changes: CalendarChanges


class DeleteEvent(_StrictModel):
    event_ref: EventRef


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


class DraftSnapshot(_GmailEnvelope):
    sender: Mailbox
    files: Annotated[tuple[MailFile, ...], Field(max_length=MAIL_MAX_FILES)]


class DraftEditorStamp(_StrictModel):
    epoch: UUID
    google_sub: Annotated[str, Field(min_length=1, max_length=255)]


class FrozenCompose(_StrictModel):
    tool: Literal["gmail.create_draft", "gmail.prepare_replacement"]
    old: DraftObservation | None
    content: GmailContent
    files: Annotated[tuple[MailFile, ...], Field(max_length=MAIL_MAX_FILES)]
    references: tuple[str, ...]
    # Only the digest of the verified parent's quoted text is needed for readback.
    quote_digest: Sha256 | None
    expected_body_digest: Sha256 | None
    expected_sender_name: Annotated[str, Field(max_length=320)] | None = None
    editor: DraftEditorStamp | None = None

    def matches_observed_body(self, body: str) -> bool:
        if (
            self.expected_body_digest is not None
            and sha256(body.encode()).hexdigest() != self.expected_body_digest
        ):
            return False
        authored = self.content.body_text
        return body == authored or (
            body.startswith(authored)
            and sha256(body[len(authored) :].encode()).hexdigest() == self.quote_digest
        )

    def matches_snapshot(
        self, snapshot: DraftSnapshot, receipt: DraftWriteReceipt
    ) -> bool:
        envelope = {"to", "cc", "bcc", "subject"}
        return (
            snapshot.sender.address == receipt.account
            and (self.old is None or snapshot.sender.name == self.expected_sender_name)
            and snapshot.model_dump(include=envelope)
            == self.content.model_dump(include=envelope)
            and snapshot.files == self.files
            and receipt.generated_quote
            == (snapshot.body_text != self.content.body_text)
            and self.matches_observed_body(snapshot.body_text)
        )


class FrozenDiscard(_StrictModel):
    tool: Literal["gmail.discard_draft"] = "gmail.discard_draft"
    old: DraftObservation
    replacement: DraftObservation | None
    verified_replacement_action_id: UUID | None


class EventObservation(_StrictModel):
    digest: Sha256
    fields: CalendarChanges
    observed_at: AwareDatetime


class CalendarMutation(_StrictModel):
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    allDay: StrictBool | None = None
    timeZone: str | None = None
    recurrenceData: tuple[str, ...] | None = None
    overrideReminders: tuple[Reminder, ...] | None = None
    useDefaultReminders: StrictBool | None = None


class FrozenCalendar(_StrictModel):
    tool: Literal[
        "calendar.create_event", "calendar.update_event", "calendar.delete_event"
    ]
    calendar_id: ResourceId
    event_id: ResourceId | None
    scope: Scope
    prior: EventObservation | None
    inherited_digest: Sha256 | None = None
    wire: CalendarMutation
    expected: CalendarChanges
    preserved_digest: Sha256 | None


type DriveToken = Annotated[str, Field(min_length=1, max_length=1024)]


def _drive_name(value: str) -> str:
    if not value.isprintable() or value.strip() != value:
        raise ValueError("drive title must be printable")
    return _bounded_utf8(value, 255, "drive title")


type DriveName = Annotated[
    str, Field(min_length=1, max_length=255), AfterValidator(_drive_name)
]
type DriveMime = Annotated[str, Field(pattern=DRIVE_MIME_PATTERN)]


class MailObservation(_StrictModel):
    model_config = ConfigDict(strict=True)
    account: str
    message_id: GoogleId
    draft_id: GoogleId | None
    file_selectors: list[str]


@dataclass(frozen=True, slots=True)
class DriveSourceFile:
    path: Path
    name: str
    media_type: str
    size: int
    sha256: str


class SubmissionSource(_StrictModel):
    submission_id: UUID


class GmailPartSource(_StrictModel):
    gmail_observation: MailObservation
    part_selector: GoogleId

    @model_validator(mode="after")
    def observed(self) -> Self:
        if self.part_selector not in self.gmail_observation.file_selectors:
            raise ValueError("gmail part needs its observed selector")
        return self


class NativePublicationSource(_StrictModel):
    native_file_id: UUID
    manifest_sha256: Sha256


class DriveTextSource(_StrictModel):
    text: str
    format: Literal["doc", "markdown", "plain"] = "doc"


class DriveNewSource(_StrictModel):
    new_type: Literal["folder", "doc", "sheet", "slides"]


type DriveBinarySource = SubmissionSource | GmailPartSource | NativePublicationSource


class DriveCreateSource(_StrictModel):
    """Closed source objects are portable through the tool-schema compiler."""

    submission_id: UUID | None = None
    gmail_observation: MailObservation | None = None
    part_selector: GoogleId | None = None
    native_file_id: UUID | None = None
    manifest_sha256: Sha256 | None = None
    text: str | None = None
    format: Literal["doc", "markdown", "plain"] | None = None
    new_type: Literal["folder", "doc", "sheet", "slides"] | None = None

    @property
    def value(self) -> DriveBinarySource | DriveTextSource | DriveNewSource:
        fields = {
            name for name in type(self).model_fields if getattr(self, name) is not None
        }
        if fields == {"submission_id"} and self.submission_id is not None:
            return SubmissionSource(submission_id=self.submission_id)
        if fields == {"gmail_observation", "part_selector"} and (
            self.gmail_observation is not None and self.part_selector is not None
        ):
            return GmailPartSource(
                gmail_observation=self.gmail_observation,
                part_selector=self.part_selector,
            )
        if fields == {"native_file_id", "manifest_sha256"} and (
            self.native_file_id is not None and self.manifest_sha256 is not None
        ):
            return NativePublicationSource(
                native_file_id=self.native_file_id,
                manifest_sha256=self.manifest_sha256,
            )
        if self.text is not None and (
            fields == {"text"}
            or (fields == {"text", "format"} and self.format is not None)
        ):
            return DriveTextSource(text=self.text, format=self.format or "doc")
        if fields == {"new_type"} and self.new_type is not None:
            return DriveNewSource(new_type=self.new_type)
        raise ValueError("exactly one drive source is required")

    @model_validator(mode="after")
    def selected(self) -> Self:
        _ = self.value
        return self


class DriveCreate(_StrictModel):
    parent: DriveId
    name: DriveName
    source: DriveCreateSource


class DriveCopy(_StrictModel):
    id: DriveId
    parent: DriveId
    name: DriveName


class DriveRevise(_StrictModel):
    id: DriveId
    etag: DriveToken
    source: DriveCreateSource

    @model_validator(mode="after")
    def blob_source(self) -> Self:
        selected = self.source.value
        if isinstance(selected, DriveNewSource) or (
            isinstance(selected, DriveTextSource) and selected.format == "doc"
        ):
            raise ValueError(
                "provide a file or plain/markdown source for a blob revision"
            )
        return self


type DocsPosition = Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]
type DocsText = Annotated[str, Field(max_length=32_768)]


class DocsLocation(_StrictModel):
    index: DocsPosition
    segmentId: str | None = None
    tabId: DriveToken | None = None


class DocsEndLocation(_StrictModel):
    segmentId: str | None = None
    tabId: DriveToken | None = None


class DocsRange(_StrictModel):
    startIndex: DocsPosition
    endIndex: DocsPosition
    segmentId: str | None = None
    tabId: DriveToken | None = None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.endIndex <= self.startIndex:
            raise ValueError("docs range must have a positive length")
        return self


class DocsInsert(_StrictModel):
    location: DocsLocation | None = None
    endOfSegmentLocation: DocsEndLocation | None = None

    @model_validator(mode="after")
    def destination(self) -> Self:
        if (self.location is None) == (self.endOfSegmentLocation is None):
            raise ValueError("provide one document insertion location")
        return self


class DocsInsertText(DocsInsert):
    text: DocsText


class DocsDelete(_StrictModel):
    range: DocsRange


class DocsContains(_StrictModel):
    text: Annotated[str, Field(min_length=1, max_length=8192)]
    matchCase: StrictBool | None = None
    searchByRegex: StrictBool | None = None


class DocsTabs(_StrictModel):
    tabIds: Annotated[tuple[DriveToken, ...], Field(min_length=1, max_length=64)]


class DocsReplaceAll(_StrictModel):
    replaceText: DocsText
    containsText: DocsContains
    tabsCriteria: DocsTabs | None = None


class DocsTextStyle(_StrictModel):
    bold: StrictBool | None = None
    italic: StrictBool | None = None
    underline: StrictBool | None = None
    strikethrough: StrictBool | None = None
    smallCaps: StrictBool | None = None
    baselineOffset: Literal["NONE", "SUPERSCRIPT", "SUBSCRIPT"] | None = None


class DocsUpdateTextStyle(_StrictModel):
    range: DocsRange
    textStyle: DocsTextStyle
    fields: Annotated[str, Field(pattern=r"^[A-Za-z]+(,[A-Za-z]+)*$")]

    @field_validator("fields")
    @classmethod
    def mask(cls, value: str) -> str:
        if not set(value.split(",")) <= DocsTextStyle.model_fields.keys():
            raise ValueError("unsupported style field")
        return value


class DocsParagraphStyle(_StrictModel):
    namedStyleType: (
        Literal[
            "NORMAL_TEXT",
            "TITLE",
            "SUBTITLE",
            "HEADING_1",
            "HEADING_2",
            "HEADING_3",
            "HEADING_4",
            "HEADING_5",
            "HEADING_6",
        ]
        | None
    ) = None
    alignment: Literal["START", "CENTER", "END", "JUSTIFIED"] | None = None
    keepWithNext: StrictBool | None = None
    keepLinesTogether: StrictBool | None = None


class DocsUpdateParagraphStyle(_StrictModel):
    range: DocsRange
    paragraphStyle: DocsParagraphStyle
    fields: Annotated[str, Field(pattern=r"^[A-Za-z]+(,[A-Za-z]+)*$")]

    @field_validator("fields")
    @classmethod
    def mask(cls, value: str) -> str:
        if not set(value.split(",")) <= DocsParagraphStyle.model_fields.keys():
            raise ValueError("unsupported style field")
        return value


class DocsBullets(_StrictModel):
    range: DocsRange
    bulletPreset: Literal[
        "BULLET_DISC_CIRCLE_SQUARE",
        "BULLET_DIAMONDX_ARROW3D_SQUARE",
        "BULLET_CHECKBOX",
        "NUMBERED_DIGIT_ALPHA_ROMAN",
    ]


class DocsInsertTable(DocsInsert):
    rows: Annotated[StrictInt, Field(ge=1, le=50)]
    columns: Annotated[StrictInt, Field(ge=1, le=50)]


class DocsRequest(_StrictModel):
    """One non-notifying, documented Google Docs operation."""

    replaceAllText: DocsReplaceAll | None = None
    insertText: DocsInsertText | None = None
    deleteContentRange: DocsDelete | None = None
    updateTextStyle: DocsUpdateTextStyle | None = None
    updateParagraphStyle: DocsUpdateParagraphStyle | None = None
    createParagraphBullets: DocsBullets | None = None
    deleteParagraphBullets: DocsDelete | None = None
    insertPageBreak: DocsInsert | None = None
    insertTable: DocsInsertTable | None = None

    @model_validator(mode="after")
    def operation(self) -> Self:
        if (
            sum(getattr(self, name) is not None for name in type(self).model_fields)
            != 1
        ):
            raise ValueError("each docs request needs one supported operation")
        return self


class DocsUpdate(_StrictModel):
    id: DriveId
    revision: DriveToken
    mode: Literal["edit", "suggest"]
    requests: Annotated[tuple[DocsRequest, ...], Field(min_length=1, max_length=50)]


class DrivePermission(_StrictModel):
    source: DriveId
    id: DriveToken | None
    role: DriveToken | None
    type: DriveToken | None
    address: DriveToken | None
    domain: DriveToken | None
    view: DriveToken | None
    space: DriveToken | None
    expires_at: str | None
    pending_owner: bool | None


class DriveExpected(_StrictModel):
    name: DriveName
    parent: DriveId | None
    media_type: DriveMime
    size: Annotated[int, Field(strict=True, ge=0)] | None
    sha256: Sha256 | None


class FrozenDriveCreate(DriveCreate):
    tool: Literal["drive.create"] = "drive.create"
    subject: DriveId
    expected: DriveExpected


class FrozenDriveCopy(DriveCopy):
    tool: Literal["drive.copy"] = "drive.copy"
    subject: DriveId
    expected: DriveExpected
    source_etag: DriveToken


class FrozenDriveRevise(DriveRevise):
    tool: Literal["drive.revise"] = "drive.revise"
    subject: DriveId
    expected: DriveExpected


class FrozenDocsUpdate(DocsUpdate):
    tool: Literal["docs.update"] = "docs.update"
    subject: DriveId


type FrozenDriveEffect = (
    FrozenDriveCreate | FrozenDriveCopy | FrozenDriveRevise | FrozenDocsUpdate
)


class FrozenWorkspaceWrite(_StrictModel):
    action_id: UUID
    grant_id: UUID
    account: str
    effect: Annotated[
        FrozenCompose | FrozenDiscard | FrozenCalendar | FrozenDriveEffect,
        Field(discriminator="tool"),
    ]

    @property
    def tool(self) -> str:
        return self.effect.tool


type UncertainVerification = Literal[
    "target_observed", "target_differs", "verification_unavailable"
]


def can_observe_workspace_target(frozen: FrozenWorkspaceWrite) -> bool:
    effect = frozen.effect
    return (
        isinstance(effect, FrozenDiscard)
        or (isinstance(effect, FrozenCalendar) and effect.event_id is not None)
        or (
            isinstance(effect, FrozenDriveRevise) and effect.expected.sha256 is not None
        )
    )


class _Receipt(_StrictModel):
    action_id: UUID
    grant_id: UUID
    account: str
    acknowledged_at: AwareDatetime
    observed_at: AwareDatetime
    verification: Literal["verified", "unverified"]
    reason: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")] | None

    def with_readback(self, reason: str | None, **evidence: object) -> Self:
        return type(self).model_validate(
            {
                **self.model_dump(),
                **evidence,
                "verification": "verified" if reason is None else "unverified",
                "reason": reason,
                "observed_at": datetime.now(UTC),
            }
        )

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


class DriveWriteReceipt(_Receipt):
    kind: Literal["drive_file"] = "drive_file"
    outcome: Literal["created", "copied", "revised", "updated"]
    subject: DriveId
    file_id: DriveId
    title: str | None = None
    link: str | None = None
    revision: DriveToken | None = None
    etag: DriveToken | None = None
    warnings: tuple[str, ...] = ()
    mode: Literal["edit", "suggest"] | None = None
    suggestion_ids: tuple[DriveToken, ...] = ()

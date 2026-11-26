"""Freeze owner-scoped Workspace effects, enter one write and verify its receipt."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.errors import HeaderParseError
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from jarvis._thread_io import finish_entered
from jarvis.drive_connector import (
    FOLDER,
    NATIVE_MIME,
    audience,
    document,
    document_revision,
    fetch_binary,
    file_href,
    metadata,
)
from jarvis.gmail_drafts import (
    WorkspaceReplyParent,
    provider_id,
    provider_labels,
    reply_subject_matches,
    workspace_draft_content,
    workspace_draft_snapshot,
    workspace_raw,
    workspace_reply_parent,
)
from jarvis.mail_files import MailFileFailure, MailFiles, NewMailFile, ObservedMailPart
from jarvis.read_tools import ATTACHMENT_MAX_BYTES
from jarvis.workspace_links import workspace_link
from jarvis.workspace_mcp import (
    Fence,
    Product,
    WorkspaceError,
    WorkspaceMcpClient,
    screen_workspace_content,
    workspace_attempts,
)
from jarvis.workspace_write_models import (
    AllDayEventTime,
    CalendarChanges,
    CalendarEdits,
    CalendarMutation,
    CalendarWriteReceipt,
    CreateDraft,
    CreateEvent,
    DeleteEvent,
    DiscardReceipt,
    DiscardSelection,
    DiscardTarget,
    DocsUpdate,
    DraftEditorStamp,
    DraftEdits,
    DraftObservation,
    DraftRef,
    DraftSnapshot,
    DraftWriteReceipt,
    DriveBinarySource,
    DriveCopy,
    DriveCreate,
    DriveExpected,
    DriveNewSource,
    DriveRevise,
    DriveSourceFile,
    DriveTextSource,
    DriveWriteReceipt,
    EventEdits,
    EventObservation,
    EventTime,
    ExistingMailPart,
    FrozenCalendar,
    FrozenCompose,
    FrozenDiscard,
    FrozenDocsUpdate,
    FrozenDriveCopy,
    FrozenDriveCreate,
    FrozenDriveEffect,
    FrozenDriveRevise,
    FrozenWorkspaceWrite,
    GmailContent,
    GmailReplyTo,
    Mailbox,
    Scope,
    TimedEventTime,
)
from jarvis.write_tools import GMAIL_WRITE_POLICY

type Obj = dict[str, object]
type Receipt = (
    DraftWriteReceipt | DiscardReceipt | CalendarWriteReceipt | DriveWriteReceipt
)
type AckRecorder = Callable[[Receipt], Awaitable[None]]
type EventRequest = CreateEvent | EventEdits | DeleteEvent

_PARSE_ERRORS = (ValueError, LookupError, HeaderParseError, RecursionError)
_DRIVE_WRITE_ATTEMPTS = 96
_DRIVE_WRITE_SECONDS = 300.0
_DOC = NATIVE_MIME + "document"
_NEW_DRIVE_TYPES = {
    "folder": FOLDER,
    "doc": _DOC,
    "sheet": NATIVE_MIME + "spreadsheet",
    "slides": NATIVE_MIME + "presentation",
}


class DriveSources(Protocol):
    def open(
        self, source: DriveBinarySource, *, invocation_id: str, before_send: Fence
    ) -> AbstractAsyncContextManager[DriveSourceFile]: ...


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_digest(value: object) -> str:
    return _digest(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    )


def _obj(value: object) -> Obj:
    if not isinstance(value, dict):
        raise ValueError("invalid resource")
    return cast(Obj, value)


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("invalid collection")
    return cast(list[object], value)


class WorkspaceWriteConflict(WorkspaceError):
    """Only the bounded host-observed differences are safe to surface in chat."""

    def __init__(self, kind: str, differences: Obj):
        super().__init__(kind)
        self.differences: Obj = {}
        for key, value in differences.items():
            try:
                screen_workspace_content(value)
                self.differences[key] = value
            except WorkspaceError:
                self.differences[key] = {"changed": True}


@dataclass(slots=True)
class _Exchange:
    client: WorkspaceMcpClient
    grant: UUID
    account: str
    invocation: str
    fence: Fence
    read_resumptions: int = 0
    background: bool = False

    async def call(
        self,
        product: Product,
        tool: str,
        args: Obj,
        *,
        raw: bool = False,
        preflight: Fence | None = None,
        write: bool = False,
        upload: tuple[Path, int] | None = None,
        download: tuple[BinaryIO, int] | None = None,
    ) -> Obj:
        transmissions = 0
        possible_effect = False

        async def before_send() -> None:
            nonlocal transmissions, possible_effect
            # A repeated entry here follows a proved pre-effect provider response.
            possible_effect = False
            try:
                await self.fence()
                if preflight is not None:
                    await preflight()
                    await self.fence()
            except WorkspaceError:
                raise
            except (Exception, asyncio.CancelledError):
                raise WorkspaceError("preflight_unavailable") from None
            if transmissions and not write:
                self.read_resumptions += 1
            transmissions += 1
            possible_effect = write

        try:
            result = await self.client.call(
                product,
                tool,
                args,
                grant_id=self.grant,
                invocation_id=self.invocation,
                background=self.background,
                before_send=before_send,
                max_response_bytes=GMAIL_WRITE_POLICY.raw_bytes
                if raw
                else GMAIL_WRITE_POLICY.metadata_bytes,
                upload=upload,
                download=download,
            )
        except WorkspaceError as exc:
            if not write and exc.kind == "uncertain":
                raise WorkspaceError("read_unavailable") from None
            if write and product in {"drive", "docs"}:
                if not possible_effect:
                    exc.known_no_effect = True
                if not exc.known_no_effect and exc.kind != "uncertain":
                    raise WorkspaceError("uncertain") from None
            if write and not possible_effect and exc.kind == "uncertain":
                raise WorkspaceError(
                    "preflight_unavailable", known_no_effect=True
                ) from None
            raise
        except (asyncio.CancelledError, TimeoutError, OSError):
            if possible_effect:
                raise WorkspaceError("uncertain") from None
            raise
        if not write:
            await self.fence()
        return result


@dataclass(frozen=True, slots=True)
class _Draft:
    observation: DraftObservation
    message: EmailMessage


async def _draft(io: _Exchange, draft_id: str) -> _Draft:
    payload = await io.call(
        "gmail", "get_draft", {"draftId": draft_id, "messageFormat": "RAW"}, raw=True
    )

    def decode() -> _Draft:
        labels = provider_labels(payload)
        if provider_id(payload, "id") != draft_id:
            raise WorkspaceError("draft_identity_differs")
        if "DRAFT" not in labels or labels.intersection({"SENT", "TRASH"}):
            raise WorkspaceWriteConflict(
                "draft_not_active",
                {
                    "draft_id": draft_id,
                    "observed_message_id": provider_id(payload, "messageId"),
                    "observed_state_labels": sorted(
                        labels & {"DRAFT", "SENT", "TRASH"}
                    ),
                },
            )
        raw = workspace_raw(payload.get("raw"))
        message = BytesParser(policy=policy.default).parsebytes(raw)
        if not raw or message.defects or not message.keys():
            raise ValueError("invalid draft")
        subjects = message.get_all("Subject", [])
        if len(subjects) > 1 or (subjects and subjects[0].defects):
            raise ValueError("ambiguous draft subject")
        subject = str(subjects[0]) if subjects else None
        try:
            screen_workspace_content(subject)
        except WorkspaceError:
            subject = None
        message_id = provider_id(payload, "messageId")
        return _Draft(
            DraftObservation(
                draft_id=draft_id,
                message_id=message_id,
                thread_id=provider_id(payload, "threadId"),
                digest=_digest(raw),
                subject=subject,
                link=workspace_link(
                    payload.get("viewUrl"), "gmail", message_id, account=io.account
                ),
                observed_at=datetime.now(UTC),
            ),
            message,
        )

    try:
        result = await asyncio.to_thread(decode)
    except _PARSE_ERRORS:
        raise WorkspaceError("draft_unreadable") from None
    await io.fence()
    return result


async def _verify_trash(io: _Exchange, old: DraftObservation) -> None:
    try:
        observed = await io.call(
            "gmail",
            "get_draft",
            {"draftId": old.draft_id, "messageFormat": "METADATA_ONLY"},
        )
    except WorkspaceError as exc:
        if exc.kind != "not_found":
            raise
        # A trashed former draft may now be readable only as a message.
        observed = await io.call(
            "gmail",
            "get_message",
            {"messageId": old.message_id, "messageFormat": "METADATA_ONLY"},
        )
        matches = provider_id(observed, "id") == old.message_id
    else:
        matches = (
            provider_id(observed, "id") == old.draft_id
            and provider_id(observed, "messageId") == old.message_id
        )
    labels = provider_labels(observed)
    if (
        not matches
        or observed.get("threadId", old.thread_id) != old.thread_id
        or "TRASH" not in labels
        or "SENT" in labels
    ):
        raise WorkspaceError("trash_unverified")


def _same_draft(
    expected: DraftRef, current: DraftObservation, *, digest: str | None = None
) -> None:
    if (
        expected.draft_id != current.draft_id
        or expected.message_id != current.message_id
        or (digest is not None and current.digest != digest)
        or (
            isinstance(expected, DraftObservation)
            and expected.thread_id != current.thread_id
        )
    ):
        raise WorkspaceWriteConflict(
            "draft_changed",
            {
                "draft_id": expected.draft_id,
                "expected_message_id": expected.message_id,
                "observed_message_id": current.message_id,
                "content_changed": digest is not None and current.digest != digest,
            },
        )


async def _parent(io: _Exchange, thread: str, message_id: str) -> WorkspaceReplyParent:
    raw = await io.call(
        "gmail",
        "get_message",
        {"messageId": message_id, "messageFormat": "RAW"},
        raw=True,
    )
    if provider_id(raw, "id") != message_id or provider_id(raw, "threadId") != thread:
        raise WorkspaceError("reply_parent_changed")
    return await asyncio.to_thread(
        workspace_reply_parent, workspace_raw(raw.get("raw"))
    )


async def _find_parent(
    io: _Exchange, thread: str, rfc_id: str
) -> tuple[GmailReplyTo, WorkspaceReplyParent]:
    # The draft MIME contains an RFC id. Only a same-thread message with the
    # exact header establishes the provider id required by replyToMessageId.
    page = await io.call(
        "gmail", "get_thread", {"threadId": thread, "messageFormat": "METADATA_ONLY"}
    )
    members = _array(page.get("messages"))
    count = page.get("messageCount", len(members))
    if (
        provider_id(page, "id") != thread
        or type(count) is not int
        or count != len(members)
        or not members
        or len(members) > GMAIL_WRITE_POLICY.max_attempts
    ):
        raise WorkspaceError("reply_parent_unverified")
    found = None
    for member in members:
        message_id = provider_id(_obj(member), "id")
        parent = await _parent(io, thread, message_id)
        if parent.rfc_id == rfc_id:
            if found is not None:
                raise WorkspaceError("reply_parent_ambiguous")
            found = (
                GmailReplyTo(
                    thread_id=thread,
                    parent_message_id=message_id,
                    parent_rfc822_message_id=rfc_id,
                ),
                parent,
            )
    if found is None:
        raise WorkspaceError("reply_parent_unverified")
    return found


def _plain_addresses(content: GmailContent) -> None:
    for mailbox in (*content.to, *content.cc, *content.bcc):
        # The public wire takes plain addr-spec strings and has no display-name field.
        try:
            address = Address(addr_spec=mailbox.address)
        except (ValueError, HeaderParseError):
            raise WorkspaceError("unrepresentable_recipient") from None
        if mailbox.name or not address.domain or address.addr_spec != mailbox.address:
            raise WorkspaceError("unrepresentable_recipient")


async def _compose(
    io: _Exchange,
    files: MailFiles,
    action_id: UUID,
    account: str,
    request: CreateDraft | DraftEdits,
) -> FrozenCompose:
    parent = None
    old = None
    expected_body = None
    sources: tuple[NewMailFile | ObservedMailPart, ...]
    if isinstance(request, CreateDraft):
        tool = "gmail.create_draft"
        content = request.content
        sources = request.files
        if (reply := content.reply_to) is not None:
            parent = await _parent(io, reply.thread_id, reply.parent_message_id)
            if parent.rfc_id != reply.parent_rfc822_message_id:
                raise WorkspaceError("reply_parent_changed")
    else:
        tool = "gmail.prepare_replacement"
        original = await _draft(io, request.draft_ref.draft_id)
        old = original.observation
        _same_draft(request.draft_ref, old)
        try:
            snapshot, parts = await asyncio.to_thread(
                workspace_draft_content, original.message, account, replacing=True
            )
        except _PARSE_ERRORS:
            raise WorkspaceError("unrepresentable_draft_mime") from None
        body = snapshot.body_text
        reply = None
        quote = ""
        if snapshot.in_reply_to is not None:
            reply, parent = await _find_parent(io, old.thread_id, snapshot.in_reply_to)
            if (
                parent.references != snapshot.references
                or parent.quote is None
                or not body.endswith(parent.quote)
            ):
                raise WorkspaceError("unrepresentable_reply")
            quote = parent.quote
            body = body[: -len(quote)]
        if not request.changes.model_fields_set and request.files is None:
            raise WorkspaceError("no_changes")
        envelope = snapshot.model_dump(
            include={"to", "cc", "bcc", "subject"}, mode="json"
        )
        edits = request.changes.model_dump(mode="json")
        screen_workspace_content(edits)
        content = GmailContent.model_validate(
            {
                **envelope,
                "body_text": body,
                "reply_to": reply,
                **edits,
            }
        )
        expected_body = _digest((_lf(content.body_text) + quote).encode())
        retained = tuple(
            ObservedMailPart(file, data)
            for file, data in zip(snapshot.files, parts, strict=True)
        )
        if request.files is None:
            sources = retained
        else:
            selected: list[NewMailFile | ObservedMailPart] = []
            positions: set[int] = set()
            for item in request.files:
                if isinstance(item, ExistingMailPart):
                    if item.existing_part in positions or item.existing_part > len(
                        retained
                    ):
                        raise WorkspaceError("invalid_existing_part")
                    positions.add(item.existing_part)
                    selected.append(retained[item.existing_part - 1])
                else:
                    selected.append(item)
            sources = tuple(selected)
    if parent is not None and not reply_subject_matches(
        content.subject, parent.subject
    ):
        raise WorkspaceError("reply_subject_changed")
    _plain_addresses(content)
    content = content.model_copy(update={"body_text": _lf(content.body_text)})
    staged = await files.stage(
        action_id, sources, invocation_id=io.invocation, before_send=io.fence
    )
    return FrozenCompose(
        tool=tool,
        old=old,
        content=content,
        files=staged,
        references=parent.references if parent else (),
        quote_digest=_digest(parent.quote.encode())
        if parent and parent.quote is not None
        else None,
        expected_body_digest=expected_body,
    )


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


async def _discard(
    io: _Exchange,
    target: DiscardTarget,
    receipt: DraftWriteReceipt | None,
    account: str,
) -> FrozenDiscard:
    if target.standalone_draft_ref is not None:
        if receipt is not None:
            raise WorkspaceError("invalid_discard_authority")
        old = (await _draft(io, target.standalone_draft_ref.draft_id)).observation
        _same_draft(target.standalone_draft_ref, old)
        return FrozenDiscard(
            old=old, replacement=None, verified_replacement_action_id=None
        )
    if (
        receipt is None
        or receipt.action_id != target.verified_replacement_action_id
        or (receipt.account, receipt.grant_id) != (account, io.grant)
        or receipt.verification != "verified"
        or not receipt.old_draft_id
        or not receipt.old_message_id
        or not receipt.new_message_id
        or not receipt.old_thread_id
        or not receipt.new_thread_id
        or not receipt.new_digest
        or not receipt.old_digest
        or receipt.old_draft_id == receipt.new_draft_id
        or receipt.old_message_id == receipt.new_message_id
    ):
        raise WorkspaceError("invalid_discard_authority")
    new = (await _draft(io, receipt.new_draft_id)).observation
    if new.thread_id != receipt.new_thread_id:
        raise WorkspaceError("replacement_thread_changed")
    _same_draft(
        DraftRef(draft_id=receipt.new_draft_id, message_id=receipt.new_message_id),
        new,
        digest=receipt.new_digest,
    )
    old = (await _draft(io, receipt.old_draft_id)).observation
    if old.thread_id != receipt.old_thread_id:
        raise WorkspaceError("draft_thread_changed")
    _same_draft(
        DraftRef(draft_id=receipt.old_draft_id, message_id=receipt.old_message_id),
        old,
        digest=receipt.old_digest,
    )
    return FrozenDiscard(
        old=old, replacement=new, verified_replacement_action_id=receipt.action_id
    )


async def _fresh_drafts(io: _Exchange, targets: tuple[DraftObservation, ...]) -> None:
    while True:
        resumed = io.read_resumptions
        for expected in targets:
            current = (await _draft(io, expected.draft_id)).observation
            _same_draft(expected, current, digest=expected.digest)
        if len(targets) < 2 or resumed == io.read_resumptions:
            return


def _verify_content(
    expected: FrozenCompose, draft: _Draft, account: str
) -> tuple[bool, DraftSnapshot]:
    snapshot, _ = workspace_draft_content(draft.message, account)
    content = expected.content
    if (
        snapshot.model_dump(mode="json", include={"to", "cc", "bcc", "subject"})
        != content.model_dump(mode="json", include={"to", "cc", "bcc", "subject"})
        or snapshot.files != expected.files
        or snapshot.references != expected.references
        or snapshot.in_reply_to
        != (content.reply_to.parent_rfc822_message_id if content.reply_to else None)
        or (
            content.reply_to is not None
            and draft.observation.thread_id != content.reply_to.thread_id
        )
    ):
        raise WorkspaceError("draft_content_differs")
    if not expected.matches_observed_body(snapshot.body_text):
        raise WorkspaceError("draft_body_differs")
    return snapshot.body_text != content.body_text, workspace_draft_snapshot(
        draft.message, snapshot
    )


def _event_scope(raw: Obj) -> Scope:
    recurring_id = raw.get("recurringEventId")
    instance = raw.get("originalStartTime")
    rules = _array(raw.get("recurrence", []))
    if recurring_id is not None or instance is not None:
        provider_id(raw, "recurringEventId")
        _event_time(instance)
        if rules:
            raise WorkspaceError("ambiguous_event_scope")
        return "occurrence"
    return "series" if rules else "single"


def _event_time(value: object) -> EventTime:
    time = _obj(value)
    if "date" in time and "dateTime" not in time:
        return AllDayEventTime.model_validate({"type": "all_day", "date": time["date"]})
    stamp = time.get("dateTime")
    if not isinstance(stamp, str) or "date" in time:
        raise ValueError("invalid event time")
    parsed = datetime.fromisoformat(stamp)
    if parsed.utcoffset() is None:
        raise ValueError("event time lacks offset")
    zone = time.get("timeZone")
    # UTC is an exact rendering of an instant whose original IANA zone was omitted.
    if zone is None:
        parsed, zone = parsed.astimezone(UTC), "UTC"
    return TimedEventTime.model_validate(
        {"type": "timed", "date_time": parsed, "time_zone": zone}
    )


def _event_fields(raw: Obj) -> CalendarChanges:
    if raw.get("attendeesOmitted", False) is not False:
        raise WorkspaceError("attendees_incomplete")
    attendees = [
        Mailbox.model_validate(
            {"address": _obj(a).get("email"), "name": _obj(a).get("displayName")}
        )
        for a in _array(raw.get("attendees", []))
    ]
    if len({a.address.casefold() for a in attendees}) != len(attendees):
        raise ValueError("ambiguous attendees")
    return CalendarChanges.model_validate(
        {
            **{k: raw[k] for k in ("summary", "description", "location") if k in raw},
            "start": _event_time(raw["start"]),
            "end": _event_time(raw["end"]),
            "attendees": attendees,
            "recurrence": raw.get("recurrence", []),
            "reminders": raw.get("overrideReminders", []),
            **(
                {"use_default_reminders": raw["useDefaultReminders"]}
                if "useDefaultReminders" in raw
                else {}
            ),
        }
    )


async def _event(io: _Exchange, calendar: str, event_id: str) -> Obj:
    raw = await io.call(
        "calendar", "get_event", {"calendarId": calendar, "eventId": event_id}
    )
    if provider_id(raw, "id") != event_id:
        raise WorkspaceError("event_identity_differs")
    return raw


def _observed_event(raw: Obj, scope: Scope) -> EventObservation:
    if raw.get("status", "confirmed") not in {"confirmed", "tentative"}:
        raise WorkspaceError("event_not_active")
    if raw.get("eventType", "DEFAULT") not in {
        "DEFAULT",
        "default",
        "EVENT_TYPE_UNSPECIFIED",
    }:
        raise WorkspaceError("unsupported_event_type")
    observed_scope = _event_scope(raw)
    if observed_scope != scope:
        raise WorkspaceWriteConflict(
            "event_scope_changed", {"expected": scope, "observed": observed_scope}
        )
    return EventObservation(
        digest=_json_digest(raw),
        fields=_event_fields(raw),
        observed_at=datetime.now(UTC),
    )


def _time_args(
    changes: CalendarChanges, old: CalendarChanges | None, wire: Obj, expected: Obj
) -> None:
    if not {"start", "end"}.intersection(changes.model_fields_set):
        return
    start = changes.start or (old.start if old else None)
    end = changes.end or (old.end if old else None)
    if start is None or end is None:
        raise WorkspaceError("invalid_event_interval")
    if changes.start and changes.end is None and old:
        if (
            isinstance(start, AllDayEventTime)
            and isinstance(old.start, AllDayEventTime)
            and isinstance(old.end, AllDayEventTime)
        ):
            end = AllDayEventTime(
                type="all_day", date=start.date + (old.end.date - old.start.date)
            )
        elif (
            isinstance(start, TimedEventTime)
            and isinstance(old.start, TimedEventTime)
            and isinstance(old.end, TimedEventTime)
        ):
            duration = old.end.date_time.astimezone(
                UTC
            ) - old.start.date_time.astimezone(UTC)
            end = TimedEventTime(
                type="timed",
                date_time=(start.date_time.astimezone(UTC) + duration).astimezone(
                    ZoneInfo(start.time_zone)
                ),
                time_zone=start.time_zone,
            )
        else:
            raise WorkspaceError("invalid_event_interval")
        expected["end"] = end
    if isinstance(start, AllDayEventTime) and isinstance(end, AllDayEventTime):
        if end.date <= start.date:
            raise WorkspaceError("invalid_event_interval")
        wire.update(
            allDay=True,
            startTime=start.date.isoformat() + "T00:00:00",
            endTime=end.date.isoformat() + "T00:00:00",
        )
        return
    elif isinstance(start, TimedEventTime) and isinstance(end, TimedEventTime):
        if (
            start.date_time.astimezone(UTC) >= end.date_time.astimezone(UTC)
            or start.time_zone != end.time_zone
        ):
            raise WorkspaceError("unrepresentable_event_interval")
        wire["timeZone"] = start.time_zone
        if old is not None and not isinstance(old.start, TimedEventTime):
            wire["allDay"] = False
    else:
        raise WorkspaceError("invalid_event_interval")
    for key, stamp in (("startTime", changes.start), ("endTime", changes.end)):
        if isinstance(stamp, TimedEventTime):
            local = stamp.date_time.astimezone(ZoneInfo(stamp.time_zone))
            # Use the named zone. Only the repeated hour also needs an offset.
            if local.replace(fold=0).utcoffset() == local.replace(fold=1).utcoffset():
                local = local.replace(tzinfo=None)
            wire[key] = local.isoformat()


def _guest_args(
    changes: CalendarChanges,
    old: CalendarChanges | None,
    raw: Obj | None,
    account: str,
    wire: Obj,
    expected: Obj,
) -> None:
    removals = changes.remove_attendees if isinstance(changes, CalendarEdits) else None
    expected.pop("remove_attendees", None)
    if changes.attendees is None and removals is None:
        return
    requested = changes.attendees or ()
    new = {person.address.casefold(): person for person in requested}
    previous = {p.address.casefold(): p for p in (old.attendees or ())} if old else {}
    if len(new) != len(requested):
        raise WorkspaceError("ambiguous_attendees")
    retained = previous.copy()
    additions: list[Obj] = []
    for key, person in new.items():
        if key not in previous:
            additions.append(
                {
                    "email": person.address,
                    **({"displayName": person.name} if person.name else {}),
                }
            )
            retained[key] = person
        elif person.name is not None and person.name != previous[key].name:
            raise WorkspaceError("unrepresentable_attendee_change")
    if additions:
        wire["attendees" if old is None else "addedAttendees"] = additions
    if removals and raw is not None:
        organizer = _obj(raw.get("organizer", {})).get("email")
        protected = {account.casefold()}
        if isinstance(organizer, str):
            protected.add(organizer.casefold())
        organizer_known = isinstance(organizer, str) and bool(organizer)
        for entry in _array(raw.get("attendees", [])):
            member = _obj(entry)
            if member.get("organizer") is True:
                organizer_known = True
            if member.get("self") is True or member.get("organizer") is True:
                protected.add(provider_id(member, "email").casefold())
        removed = [Mailbox(name=None, address=r).address.casefold() for r in removals]
        if (
            not organizer_known
            or len(set(removed)) != len(removed)
            or any(r not in previous or r in protected or r in new for r in removed)
        ):
            raise WorkspaceError("unrepresentable_attendee_removal")
        wire["removedAttendeeEmails"] = [retained.pop(r).address for r in removed]
    expected["attendees"] = tuple(retained.values())


def _preserved(raw: Obj, changes: CalendarChanges, wire: CalendarMutation) -> str:
    # update_event is a patch. Verify untouched provider-only fields as well as
    # the rich per-guest state of every retained attendee.
    remaining = dict(raw)
    for key in ("updated", "etag", "sequence", "htmlLink"):
        remaining.pop(key, None)
    for key in changes.model_fields_set - {"attendees"}:
        remaining.pop(
            {
                "use_default_reminders": "useDefaultReminders",
                "reminders": "overrideReminders",
            }.get(key, key),
            None,
        )
    if "attendees" in changes.model_fields_set:
        affected = {a.email for a in wire.addedAttendees or ()} | set(
            wire.removedAttendeeEmails or ()
        )
        kept = [
            _obj(item)
            for item in _array(remaining.get("attendees", []))
            if _obj(item).get("email") not in affected
        ]
        remaining["attendees"] = sorted(kept, key=lambda x: str(x["email"]))
    return _json_digest(remaining)


def _require_supported_patch(wire: CalendarMutation) -> None:
    # Explicit empty strings and allDay=false need provider presence proof.
    if wire.allDay is False or "" in (wire.summary, wire.description, wire.location):
        raise WorkspaceError("unrepresentable_event_change")


async def _freeze_event(
    io: _Exchange, request: EventRequest, account: str
) -> FrozenCalendar:
    raw = None
    prior = None
    event_id = None
    if isinstance(request, CreateEvent):
        tool = "calendar.create_event"
        calendar = request.calendar
        scope: Scope = "series" if request.fields.recurrence else "single"
        changes = CalendarChanges.model_validate(request.fields.model_dump(mode="json"))
    else:
        ref = request.event_ref
        calendar, event_id, scope = ref.calendar_id, ref.event_id, ref.scope
        raw = await _event(io, calendar, event_id)
        prior = _observed_event(raw, scope)
        if isinstance(request, DeleteEvent):
            return FrozenCalendar(
                tool="calendar.delete_event",
                calendar_id=calendar,
                event_id=event_id,
                scope=scope,
                notify=request.notify,
                prior=prior,
                wire=CalendarMutation(),
                expected=CalendarChanges(),
                preserved_digest=None,
            )
        tool = "calendar.update_event"
        changes = request.changes
        if not changes.model_fields_set:
            raise WorkspaceError("no_changes")
        if "recurrence" in changes.model_fields_set:
            raise WorkspaceError("unrepresentable_recurrence_change")

    expected = changes.model_dump(mode="json")
    if any(
        val is None
        for key, val in expected.items()
        if key not in {"description", "location"}
    ):
        raise WorkspaceError("invalid_event_change")
    wire: Obj = {}
    for key in ("summary", "description", "location"):
        if key in expected and (expected[key] is not None or prior is not None):
            wire[key] = expected[key] or ""
    if changes.recurrence:
        if any(
            not item.startswith(("RRULE:", "RDATE:", "EXDATE:"))
            for item in changes.recurrence
        ):
            raise WorkspaceError("unrepresentable_recurrence")
        wire["recurrenceData"] = list(changes.recurrence)
    _time_args(changes, prior.fields if prior else None, wire, expected)
    _guest_args(changes, prior.fields if prior else None, raw, account, wire, expected)
    if changes.use_default_reminders is not None or changes.reminders is not None:
        reminders = changes.reminders or ()
        defaults = changes.use_default_reminders
        if defaults is None:
            defaults = False
        if defaults and reminders:
            raise WorkspaceError("invalid_reminders")
        if (
            defaults is False
            and changes.reminders is None
            and prior
            and prior.fields.reminders
        ):
            raise WorkspaceError("reminder_change_requires_overrides")
        wire["useDefaultReminders"] = defaults
        if reminders:
            wire["overrideReminders"] = [r.model_dump(mode="json") for r in reminders]
        expected.update(use_default_reminders=defaults, reminders=reminders)
    if prior and not wire:
        raise WorkspaceError("no_changes")
    mutation = CalendarMutation.model_validate(wire)
    if prior is not None:
        _require_supported_patch(mutation)
    wanted = CalendarChanges.model_validate(expected)
    return FrozenCalendar(
        tool=tool,
        calendar_id=calendar,
        event_id=event_id,
        scope=scope,
        notify=request.notify,
        prior=prior,
        wire=mutation,
        expected=wanted,
        preserved_digest=_preserved(raw, wanted, mutation) if raw is not None else None,
    )


async def _fresh_event(io: _Exchange, frozen: FrozenCalendar) -> None:
    if frozen.event_id is None or frozen.prior is None:
        return
    raw = await _event(io, frozen.calendar_id, frozen.event_id)
    current = _observed_event(raw, frozen.scope)
    if current.digest != frozen.prior.digest:
        previous = frozen.prior.fields.model_dump(mode="json")
        latest = current.fields.model_dump(mode="json")
        differences: Obj = {
            k: {"expected": previous.get(k), "observed": latest.get(k)}
            for k in sorted(previous.keys() | latest.keys())
            if previous.get(k) != latest.get(k)
        }
        raise WorkspaceWriteConflict(
            "event_changed", differences or {"other_provider_fields_changed": True}
        )


def _verify_event(raw: Obj, frozen: FrozenCalendar) -> None:
    if frozen.tool == "calendar.delete_event":
        if raw.get("status") != "cancelled":
            raise WorkspaceError("deletion_unverified")
        return
    observed = _observed_event(raw, frozen.scope).fields
    for field in frozen.expected.model_fields_set:
        actual = getattr(observed, field)
        desired = getattr(frozen.expected, field)
        if field in {"description", "location"}:
            if (actual or "") == (desired or ""):
                continue
        elif field == "attendees" and actual is not None and desired is not None:
            if {v.address: v.name for v in actual} == {
                v.address: v.name for v in desired
            }:
                continue
        elif isinstance(actual, TimedEventTime) and isinstance(desired, TimedEventTime):
            if actual.time_zone == desired.time_zone and actual.date_time.astimezone(
                UTC
            ) == desired.date_time.astimezone(UTC):
                continue
        elif actual == desired:
            continue
        raise WorkspaceError("event_fields_differ")
    if (
        frozen.preserved_digest is not None
        and _preserved(raw, frozen.expected, frozen.wire) != frozen.preserved_digest
    ):
        raise WorkspaceError("untouched_event_fields_differ")


def _document_text(doc: Obj) -> str:
    # Traverse structural elements in their document order. Exclude editor metadata.
    def content(item: object) -> str:
        if isinstance(item, list):
            return "".join(content(element) for element in cast(list[object], item))
        if not isinstance(item, dict):
            return ""
        row = cast(Obj, item)
        if "textRun" in row:
            return str(_obj(row["textRun"])["content"])
        return "".join(
            content(row[key])
            for key in (
                "documentTab",
                "body",
                "content",
                "paragraph",
                "elements",
                "table",
                "tableRows",
                "tableCells",
                "childTabs",
                "tableOfContents",
            )
            if key in row
        )

    if "tabs" in doc:
        return content(doc["tabs"])
    if "body" in doc:
        return content(doc["body"])
    raise WorkspaceError("document_structure_unavailable")


def _document_locations(doc: Obj, update: DocsUpdate) -> None:
    tabs: dict[str | None, set[str]] = {}

    def load(item: Obj, tab: str | None) -> None:
        if "body" not in item:
            raise WorkspaceError("document_structure_unavailable")
        names: set[str] = set()
        for key in ("headers", "footers", "footnotes"):
            names.update(_obj(item.get(key, {})))
        tabs[tab] = names

    def walk(items: object) -> None:
        for item in _array(items):
            row = _obj(item)
            tab = _obj(row["tabProperties"])["tabId"]
            if not isinstance(tab, str) or not tab or tab in tabs:
                raise WorkspaceError("document_structure_unavailable")
            load(_obj(row["documentTab"]), tab)
            walk(row.get("childTabs", []))

    if "tabs" in doc:
        walk(doc["tabs"])
        if not tabs:
            raise WorkspaceError("document_structure_unavailable")
    else:
        load(doc, None)
    first = next(iter(tabs))

    def check(value: object) -> None:
        if isinstance(value, list):
            for item in cast(list[object], value):
                check(item)
        elif isinstance(value, dict):
            row = cast(Obj, value)
            if "tabIds" in row and not all(
                isinstance(tab, str) and tab in tabs for tab in _array(row["tabIds"])
            ):
                raise WorkspaceError("document_location_unavailable")
            if any(
                key in row
                for key in ("tabId", "segmentId", "index", "startIndex", "endIndex")
            ):
                tab = row.get("tabId") or first
                segment = row.get("segmentId") or ""
                indices = [
                    row[key]
                    for key in ("index", "startIndex", "endIndex")
                    if key in row
                ]
                if (
                    (tab is not None and not isinstance(tab, str))
                    or tab not in tabs
                    or not isinstance(segment, str)
                    or (segment and segment not in tabs[tab])
                    or any(
                        type(i) is not int or not 0 <= i <= 2**31 - 1 for i in indices
                    )
                ):
                    raise WorkspaceError("document_location_unavailable")
            for child in row.values():
                check(child)

    for request in update.requests:
        check(request.model_dump(mode="json", exclude_none=True))


async def _drive_bytes(io: _Exchange, id: str) -> tuple[int, str]:
    async def transfer(args: Obj, output: BinaryIO, maximum: int) -> Obj:
        return await io.call(
            "drive", "download_file_content", args, download=(output, maximum)
        )

    with tempfile.TemporaryFile() as output:
        _, size, digest = await fetch_binary(
            io.call, transfer, id, None, output, ATTACHMENT_MAX_BYTES
        )
        return size, digest


async def _drive_readback(
    io: _Exchange, effect: FrozenDriveEffect, receipt: DriveWriteReceipt
) -> Obj:
    if isinstance(effect, FrozenDocsUpdate):
        current = await document(io.call, effect.id)
        if document_revision(current, effect.id) != receipt.revision:
            raise WorkspaceError("document_changed")
        if receipt.warnings:
            raise WorkspaceError("document_update_warned")
        return {}
    current = await metadata(io.call, receipt.file_id)
    expected = effect.expected
    if (
        current.name != expected.name
        or current.parent != expected.parent
        or current.mime != expected.media_type
        or (
            isinstance(effect, FrozenDriveRevise)
            and (receipt.etag is None or current.etag != receipt.etag)
        )
    ):
        raise WorkspaceError("file_changed")
    if expected.sha256 is not None:
        if current.mime == _DOC:
            text = _document_text(await document(io.call, receipt.file_id))
            if _digest(text.removesuffix("\n").encode()) != expected.sha256:
                raise WorkspaceError("document_content_differs")
        elif await _drive_bytes(io, receipt.file_id) != (
            expected.size,
            expected.sha256,
        ):
            raise WorkspaceError("file_bytes_differ")
    return {"title": current.name, "etag": current.etag}


class WorkspaceWrites:
    def __init__(
        self,
        client: WorkspaceMcpClient,
        mail_files: MailFiles,
        *,
        discard_qualified: bool = False,
        drive_sources: DriveSources | None = None,
        drive_download_qualified: bool = False,
        drive_revise_qualified: bool = False,
        docs_update_qualified: bool = False,
        editor_stamp: Callable[[UUID], DraftEditorStamp | None] | None = None,
    ):
        self._client = client
        self._files = mail_files
        self._discard_qualified = discard_qualified
        self._drive_sources = drive_sources
        self._drive_download_qualified = drive_download_qualified
        self._drive_revise_qualified = drive_revise_qualified
        self._docs_update_qualified = docs_update_qualified
        self._editor_stamp = editor_stamp

    async def prepare(
        self,
        tool: str,
        arguments: Mapping[str, object],
        *,
        action_id: UUID,
        grant_id: UUID,
        account: str,
        invocation_id: str,
        before_send: Fence,
        replacement: DraftWriteReceipt | None = None,
        subject: str | None = None,
    ) -> FrozenWorkspaceWrite:
        if tool.startswith(("drive.", "docs.")):
            if subject is None or replacement is not None:
                raise WorkspaceError("grant_unavailable")
            with workspace_attempts(
                _DRIVE_WRITE_ATTEMPTS, seconds=_DRIVE_WRITE_SECONDS
            ):
                io = _Exchange(
                    self._client, grant_id, account, invocation_id, before_send
                )
                try:
                    await io.fence()
                    drive = await self._prepare_drive(io, tool, arguments, subject)
                    await io.fence()
                    return FrozenWorkspaceWrite(
                        action_id=action_id,
                        grant_id=grant_id,
                        account=account,
                        effect=drive,
                    )
                except (TypeError, *_PARSE_ERRORS):
                    raise WorkspaceError("unrepresentable") from None
        with workspace_attempts(
            GMAIL_WRITE_POLICY.max_attempts,
            seconds=GMAIL_WRITE_POLICY.operation_seconds
            if tool.startswith("gmail.")
            else 20.0,
        ):
            await before_send()
            try:
                account = Mailbox(name=None, address=account).address
                io = _Exchange(
                    self._client, grant_id, account, invocation_id, before_send
                )
                if (
                    tool in {"gmail.prepare_replacement", "gmail.discard_draft"}
                    and not self._discard_qualified
                ):
                    raise WorkspaceError("discard_unqualified")
                if tool != "gmail.discard_draft" and replacement is not None:
                    raise WorkspaceError("invalid_discard_authority")
                effect: FrozenCompose | FrozenDiscard | FrozenCalendar
                if tool == "gmail.create_draft":
                    effect = await _compose(
                        io,
                        self._files,
                        action_id,
                        account,
                        CreateDraft.model_validate(arguments),
                    )
                    if self._editor_stamp is not None:
                        effect = effect.model_copy(
                            update={"editor": self._editor_stamp(grant_id)}
                        )
                elif tool == "gmail.prepare_replacement":
                    effect = await _compose(
                        io,
                        self._files,
                        action_id,
                        account,
                        DraftEdits.model_validate(arguments),
                    )
                elif tool == "gmail.discard_draft":
                    effect = await _discard(
                        io,
                        DiscardSelection.model_validate(arguments).target,
                        replacement,
                        account,
                    )
                elif tool == "calendar.create_event":
                    effect = await _freeze_event(
                        io, CreateEvent.model_validate(arguments), account
                    )
                elif tool == "calendar.update_event":
                    effect = await _freeze_event(
                        io, EventEdits.model_validate(arguments), account
                    )
                elif tool == "calendar.delete_event":
                    effect = await _freeze_event(
                        io, DeleteEvent.model_validate(arguments), account
                    )
                else:
                    raise WorkspaceError("unsupported")
            except MailFileFailure:
                raise
            except (TypeError, *_PARSE_ERRORS):
                raise WorkspaceError("unrepresentable") from None
            try:
                await io.fence()
                return FrozenWorkspaceWrite(
                    action_id=action_id,
                    grant_id=grant_id,
                    account=account,
                    effect=effect,
                )
            except BaseException:
                if isinstance(effect, FrozenCompose) and effect.files:
                    await self._files.discard(action_id)
                raise

    async def execute(
        self,
        frozen: FrozenWorkspaceWrite,
        *,
        invocation_id: str,
        before_send: Fence,
        record_ack: AckRecorder | None = None,
        capture_draft: Callable[[DraftSnapshot], None] | None = None,
    ) -> Receipt:
        drive = frozen.tool.startswith(("drive.", "docs."))
        with workspace_attempts(
            _DRIVE_WRITE_ATTEMPTS if drive else GMAIL_WRITE_POLICY.max_attempts,
            seconds=_DRIVE_WRITE_SECONDS
            if drive
            else GMAIL_WRITE_POLICY.operation_seconds
            if frozen.tool.startswith("gmail.")
            else 20.0,
        ):
            io = _Exchange(
                self._client,
                frozen.grant_id,
                frozen.account,
                invocation_id,
                before_send,
            )
            try:
                await io.fence()
            except WorkspaceError as e:
                e.known_no_effect = True
                raise
            effect = frozen.effect
            if (
                effect.tool in {"gmail.prepare_replacement", "gmail.discard_draft"}
                and not self._discard_qualified
            ):
                raise WorkspaceError("discard_unqualified")
            if isinstance(effect, FrozenCompose):
                receipt: Receipt = await self._create(io, frozen, effect)
            elif isinstance(effect, FrozenDiscard):
                receipt = await self._trash(io, frozen, effect)
            elif isinstance(effect, FrozenCalendar):
                receipt = await self._calendar(io, frozen, effect)
            else:
                receipt = await self._write_drive(io, frozen, effect)
            # No admission fence between a validated acknowledgement and local custody.
            if record_ack is not None:
                # Once Google acknowledges the effect, local cancellation must
                # join the entered receipt transaction before the executor exits.
                async def persist() -> None:
                    await record_ack(receipt)

                commit = asyncio.create_task(persist())
                try:
                    try:
                        await asyncio.shield(commit)
                    except asyncio.CancelledError:
                        await finish_entered(commit)
                        return receipt.with_readback("readback_unavailable")
                except (Exception, asyncio.CancelledError):
                    # Final local settlement can still take custody of this ack.
                    return receipt.with_readback("ack_recording_failed")
            verified_fields: Obj = {}
            snapshot = None
            try:
                await io.fence()
                if isinstance(effect, FrozenCompose) and isinstance(
                    receipt, DraftWriteReceipt
                ):
                    live = await _draft(io, receipt.new_draft_id)
                    rev = live.observation
                    if (
                        (
                            receipt.new_message_id is not None
                            and receipt.new_message_id != rev.message_id
                        )
                        or (effect.old and effect.old.message_id == rev.message_id)
                        or (
                            receipt.new_thread_id is not None
                            and receipt.new_thread_id != rev.thread_id
                        )
                    ):
                        raise WorkspaceError("draft_changed")
                    generated_quote, snapshot = await asyncio.to_thread(
                        _verify_content, effect, live, frozen.account
                    )
                    await io.fence()
                    verified_fields = {
                        "new_message_id": rev.message_id,
                        "new_thread_id": rev.thread_id,
                        "new_digest": rev.digest,
                        "new_link": rev.link or receipt.new_link,
                        "generated_quote": generated_quote,
                    }
                elif isinstance(effect, FrozenDiscard) and isinstance(
                    receipt, DiscardReceipt
                ):
                    await _verify_trash(io, effect.old)
                elif isinstance(effect, FrozenCalendar) and isinstance(
                    receipt, CalendarWriteReceipt
                ):
                    raw = await _event(io, effect.calendar_id, receipt.event_id)
                    _verify_event(raw, effect)
                    verified_fields["link"] = (
                        workspace_link(
                            raw.get("htmlLink"),
                            "calendar",
                            receipt.event_id,
                            effect.calendar_id,
                            account=io.account,
                        )
                        or receipt.link
                    )
                elif isinstance(receipt, DriveWriteReceipt) and isinstance(
                    effect,
                    FrozenDriveCreate
                    | FrozenDriveCopy
                    | FrozenDriveRevise
                    | FrozenDocsUpdate,
                ):
                    verified_fields = await _drive_readback(io, effect, receipt)
                await io.fence()
                verified = receipt.with_readback(None, **verified_fields)
                if snapshot is not None and capture_draft is not None:
                    capture_draft(snapshot)
                return verified
            except (Exception, asyncio.CancelledError) as exc:
                # No readback or later ownership failure can revoke the provider's ack.
                reason = (
                    exc.kind
                    if isinstance(exc, WorkspaceError)
                    and re.fullmatch(r"[a-z][a-z0-9_]{0,95}", exc.kind)
                    else "readback_unavailable"
                )
                return receipt.with_readback(reason)

    async def _prepare_drive(
        self,
        io: _Exchange,
        tool: str,
        arguments: Mapping[str, object],
        subject: str,
    ) -> FrozenDriveEffect:
        if tool == "docs.update":
            if not self._docs_update_qualified:
                raise WorkspaceError("docs_update_unqualified")
            update = DocsUpdate.model_validate(arguments)
            observed = await document(io.call, update.id)
            if document_revision(observed, update.id) != update.revision:
                raise WorkspaceError("document_changed")
            _document_locations(observed, update)
            shared = await audience(io.call, update.id, io.account)
            return FrozenDocsUpdate(
                **update.model_dump(), subject=subject, audience=shared
            )
        if tool == "drive.copy":
            copy = DriveCopy.model_validate(arguments)
            original = await metadata(io.call, copy.id)
            if original.etag is None or original.mime == FOLDER:
                raise WorkspaceError("copy_source_unavailable")
            size, digest = None, None
            if original.mime == _DOC:
                text = _document_text(await document(io.call, copy.id))
                digest = _digest(text.removesuffix("\n").encode())
            elif not original.native:
                if not self._drive_download_qualified:
                    raise WorkspaceError("drive_download_unqualified")
                size, digest = await _drive_bytes(io, copy.id)
            if (await metadata(io.call, copy.id)).etag != original.etag:
                raise WorkspaceError("source_changed")
            shared = await audience(io.call, copy.parent, io.account)
            return FrozenDriveCopy(
                **copy.model_dump(),
                subject=subject,
                audience=shared,
                source_etag=original.etag,
                expected=DriveExpected(
                    name=copy.name,
                    parent=copy.parent,
                    media_type=original.mime,
                    size=size,
                    sha256=digest,
                ),
            )
        if tool == "drive.create":
            request = DriveCreate.model_validate(arguments)
            name, parent = request.name, request.parent
            target = parent
        elif tool == "drive.revise":
            if not self._drive_revise_qualified:
                raise WorkspaceError("drive_revise_unqualified")
            request = DriveRevise.model_validate(arguments)
            current = await metadata(io.call, request.id)
            if current.etag != request.etag or current.native:
                raise WorkspaceError("file_revision_changed")
            name, parent = current.name, current.parent
            target = request.id
        else:
            raise WorkspaceError("unsupported")

        source = request.source.value
        size, digest = None, None
        if isinstance(source, DriveNewSource):
            mime = _NEW_DRIVE_TYPES[source.new_type]
            if mime == _DOC:
                digest = _digest(b"")
        elif isinstance(source, DriveTextSource):
            mime = {"doc": _DOC, "plain": "text/plain", "markdown": "text/markdown"}[
                source.format
            ]
            data = source.text.encode()
            if mime == _DOC:
                digest = _digest(_lf(source.text).encode())
            else:
                size, digest = len(data), _digest(data)
        else:
            if self._drive_sources is None:
                raise WorkspaceError("source_unavailable")
            async with self._drive_sources.open(
                source,
                invocation_id=io.invocation,
                before_send=io.fence,
            ) as file:
                mime, size, digest = file.media_type, file.size, file.sha256
        if mime.startswith(NATIVE_MIME) and isinstance(request, DriveRevise):
            raise WorkspaceError("native_edit_requires_docs")
        if not mime.startswith(NATIVE_MIME) and not self._drive_download_qualified:
            raise WorkspaceError("drive_download_unqualified")
        expected = DriveExpected(
            name=name, parent=parent, media_type=mime, size=size, sha256=digest
        )
        shared = await audience(io.call, target, io.account)
        if isinstance(request, DriveCreate):
            return FrozenDriveCreate(
                **request.model_dump(),
                subject=subject,
                audience=shared,
                expected=expected,
            )
        return FrozenDriveRevise(
            **request.model_dump(),
            subject=subject,
            audience=shared,
            expected=expected,
        )

    async def _write_drive(
        self,
        io: _Exchange,
        frozen: FrozenWorkspaceWrite,
        effect: FrozenDriveEffect,
    ) -> DriveWriteReceipt:
        async def fresh() -> None:
            while True:
                rounds = io.read_resumptions
                observed = await audience(io.call, effect.audience.target, io.account)
                if observed.fingerprint != effect.audience.fingerprint or (
                    observed.state != effect.audience.state
                ):
                    raise WorkspaceWriteConflict(
                        "drive_audience_changed",
                        {"audience": observed.model_dump(mode="json")},
                    )
                if isinstance(effect, FrozenDocsUpdate):
                    doc = await document(io.call, effect.id)
                    if document_revision(doc, effect.id) != effect.revision:
                        raise WorkspaceError("document_changed")
                elif isinstance(effect, FrozenDriveRevise):
                    if (await metadata(io.call, effect.id)).etag != effect.etag:
                        raise WorkspaceError("file_revision_changed")
                elif isinstance(effect, FrozenDriveCopy):
                    if (await metadata(io.call, effect.id)).etag != effect.source_etag:
                        raise WorkspaceError("source_changed")
                if rounds == io.read_resumptions:
                    return

        upload: AbstractAsyncContextManager[DriveSourceFile | None] = nullcontext()
        product: Product = "drive"
        outcome: Literal["created", "copied", "revised", "updated"]
        if isinstance(effect, FrozenDocsUpdate):
            if not self._docs_update_qualified:
                raise WorkspaceError("docs_update_unqualified", known_no_effect=True)
            product, operation, outcome = "docs", "update_doc", "updated"
            args: Obj = {
                "documentId": effect.id,
                "requests": [
                    r.model_dump(mode="json", exclude_none=True)
                    for r in effect.requests
                ],
                "writeControl": {
                    "requiredRevisionId": effect.revision,
                    "writeMode": effect.mode.upper(),
                },
            }
        elif isinstance(effect, FrozenDriveCopy):
            operation, outcome = "copy_file", "copied"
            args = {
                "fileId": effect.id,
                "parentId": effect.parent,
                "title": effect.name,
            }
        else:
            if isinstance(effect, FrozenDriveCreate):
                operation, outcome = "create_file", "created"
                args = {"parentId": effect.parent, "title": effect.name}
            else:
                if not self._drive_revise_qualified:
                    raise WorkspaceError(
                        "drive_revise_unqualified", known_no_effect=True
                    )
                operation, outcome = "upload_file_revision", "revised"
                args = {"fileId": effect.id, "etag": effect.etag}
            source = effect.source.value
            if isinstance(source, DriveNewSource):
                args["mimeType"] = effect.expected.media_type
            else:
                mime = effect.expected.media_type
                if isinstance(source, DriveTextSource):
                    args["textContent"] = source.text
                    if mime == _DOC:
                        mime = "text/plain"
                else:
                    if self._drive_sources is None:
                        raise WorkspaceError("source_unavailable", known_no_effect=True)
                    upload = self._drive_sources.open(
                        source,
                        invocation_id=io.invocation,
                        before_send=io.fence,
                    )
                args["contentMimeType"] = mime
                if mime != "text/plain" or effect.expected.media_type != _DOC:
                    if isinstance(effect, FrozenDriveCreate):
                        args["disableConversionToGoogleType"] = True
        dispatch_started = False
        try:
            async with upload as file:
                if (
                    file is not None
                    and isinstance(effect, FrozenDriveCreate | FrozenDriveRevise)
                    and (file.sha256, file.size, file.media_type)
                    != (
                        effect.expected.sha256,
                        effect.expected.size,
                        effect.expected.media_type,
                    )
                ):
                    raise WorkspaceError("source_changed")
                dispatch_started = True
                result = await io.call(
                    product,
                    operation,
                    args,
                    preflight=fresh,
                    write=True,
                    upload=(file.path, file.size) if file is not None else None,
                )
        except WorkspaceError as e:
            if not dispatch_started:
                e.known_no_effect = True
            raise
        except (OSError, asyncio.CancelledError):
            raise WorkspaceError(
                "uncertain" if dispatch_started else "source_unavailable",
                known_no_effect=not dispatch_started,
            ) from None
        try:
            warnings: tuple[str, ...] = ()
            revision, etag = None, None
            if isinstance(effect, FrozenDocsUpdate):
                control = _obj(result["writeControl"])
                revision = provider_id(control, "requiredRevisionId")
                replies = _array(result.get("replies", []))
                warnings = tuple(
                    item
                    for reply in replies
                    for item in (_obj(reply).get("warning"), _obj(reply).get("error"))
                    if isinstance(item, str) and len(item.encode()) <= 512
                )[:20]
                id, title = effect.id, None
            elif isinstance(effect, FrozenDriveRevise):
                id, title = effect.id, effect.expected.name
                revision = provider_id(result, "id")
                if "fileEtag" in result:
                    etag = provider_id(result, "fileEtag")
            else:
                id, title = provider_id(result, "id"), effect.name
                if isinstance(effect, FrozenDriveCopy) and id == effect.id:
                    raise ValueError("copy identity is not new")
            now = datetime.now(UTC)
            return DriveWriteReceipt(
                action_id=frozen.action_id,
                grant_id=frozen.grant_id,
                account=frozen.account,
                acknowledged_at=now,
                observed_at=now,
                verification="unverified",
                reason="readback_pending",
                outcome=outcome,
                subject=effect.subject,
                file_id=id,
                title=title,
                link=file_href(effect.subject, id),
                revision=revision,
                etag=etag,
                warnings=warnings,
            )
        except (TypeError, *_PARSE_ERRORS):
            raise WorkspaceError("uncertain") from None

    async def recover_drive(
        self,
        frozen: FrozenWorkspaceWrite,
        receipt: DriveWriteReceipt,
        *,
        invocation_id: str,
        before_send: Fence,
    ) -> DriveWriteReceipt:
        effect = frozen.effect
        if (
            not isinstance(
                effect,
                FrozenDriveCreate
                | FrozenDriveCopy
                | FrozenDriveRevise
                | FrozenDocsUpdate,
            )
            or (receipt.action_id, receipt.grant_id, receipt.account, receipt.subject)
            != (frozen.action_id, frozen.grant_id, frozen.account, effect.subject)
            or (
                isinstance(effect, FrozenDriveRevise | FrozenDocsUpdate)
                and receipt.file_id != effect.id
            )
        ):
            raise WorkspaceError("invalid_receipt")
        with workspace_attempts(_DRIVE_WRITE_ATTEMPTS, seconds=_DRIVE_WRITE_SECONDS):
            io = _Exchange(
                self._client,
                frozen.grant_id,
                frozen.account,
                invocation_id,
                before_send,
                background=True,
            )
            try:
                await io.fence()
                evidence = await _drive_readback(io, effect, receipt)
                await io.fence()
                return receipt.with_readback(None, **evidence)
            except WorkspaceError as e:
                return receipt.with_readback(e.kind)
            except (TypeError, *_PARSE_ERRORS):
                return receipt.with_readback("invalid_response")

    async def _create(
        self, io: _Exchange, frozen: FrozenWorkspaceWrite, effect: FrozenCompose
    ) -> DraftWriteReceipt:
        content = effect.content
        attachments: list[Obj] = []
        for slot, file in enumerate(effect.files, 1):
            data = await self._files.read(frozen.action_id, slot, file)
            attachments.append(
                {
                    "filename": file.filename,
                    "mimeType": file.media_type,
                    "content": base64.b64encode(data).decode("ascii"),
                }
            )
        args: Obj = {
            "to": [m.address for m in content.to],
            "cc": [m.address for m in content.cc],
            "bcc": [m.address for m in content.bcc],
            "subject": content.subject,
            "body": content.body_text,
            "includeSignature": False,
            "attachments": attachments,
        }
        reply = content.reply_to
        if reply:
            args["replyToMessageId"] = reply.parent_message_id
        old = effect.old

        async def fresh() -> None:
            nonlocal old
            while True:
                resumed = io.read_resumptions
                if reply:
                    parent = await _parent(io, reply.thread_id, reply.parent_message_id)
                    if (
                        parent.rfc_id != reply.parent_rfc822_message_id
                        or parent.references != effect.references
                        or not reply_subject_matches(content.subject, parent.subject)
                        or (
                            _digest(parent.quote.encode())
                            if parent.quote is not None
                            else None
                        )
                        != effect.quote_digest
                    ):
                        raise WorkspaceError("reply_parent_changed")
                if old:
                    current = (await _draft(io, old.draft_id)).observation
                    _same_draft(old, current, digest=old.digest)
                    old = current
                if not reply or old is None or resumed == io.read_resumptions:
                    return

        result = await io.call(
            "gmail", "create_draft", args, preflight=fresh, write=True
        )
        try:
            did = provider_id(result, "id")
            mid = provider_id(result, "messageId") if "messageId" in result else None
            thread = provider_id(result, "threadId") if "threadId" in result else None
            if old and (old.draft_id == did or old.message_id == mid):
                raise ValueError("replacement identity is not new")
        except _PARSE_ERRORS:
            raise WorkspaceError("uncertain") from None
        now = datetime.now(UTC)
        return DraftWriteReceipt(
            action_id=frozen.action_id,
            grant_id=frozen.grant_id,
            account=frozen.account,
            acknowledged_at=now,
            observed_at=now,
            verification="unverified",
            reason="readback_pending",
            old_draft_id=old.draft_id if old else None,
            old_message_id=old.message_id if old else None,
            old_digest=old.digest if old else None,
            old_thread_id=old.thread_id if old else None,
            old_link=old.link if old else None,
            old_observed_at=old.observed_at if old else None,
            new_draft_id=did,
            new_message_id=mid,
            new_digest=None,
            new_thread_id=thread,
            new_link=workspace_link(
                result.get("viewUrl"), "gmail", mid, account=io.account
            )
            if mid
            else None,
            files=effect.files,
            generated_quote=None,
        )

    async def _trash(
        self, io: _Exchange, frozen: FrozenWorkspaceWrite, effect: FrozenDiscard
    ) -> DiscardReceipt:
        old, new = effect.old, effect.replacement
        targets = (new, old) if new is not None else (old,)
        result = await io.call(
            "gmail",
            "trash_message",
            {"messageId": old.message_id},
            preflight=lambda: _fresh_drafts(io, targets),
            write=True,
        )
        # Google's TrashMessageResponse is an empty object in a completed tool result.
        if result != {}:
            raise WorkspaceError("uncertain")
        now = datetime.now(UTC)
        return DiscardReceipt(
            action_id=frozen.action_id,
            grant_id=frozen.grant_id,
            account=frozen.account,
            acknowledged_at=now,
            observed_at=now,
            verification="unverified",
            reason="readback_pending",
            old_draft_id=old.draft_id,
            old_message_id=old.message_id,
            old_link=old.link,
            new_draft_id=new.draft_id if new else None,
            new_message_id=new.message_id if new else None,
            new_link=new.link if new else None,
            verified_replacement_action_id=effect.verified_replacement_action_id,
        )

    async def _calendar(
        self, io: _Exchange, frozen: FrozenWorkspaceWrite, effect: FrozenCalendar
    ) -> CalendarWriteReceipt:
        if effect.tool == "calendar.update_event":
            _require_supported_patch(effect.wire)
        args = effect.wire.model_dump(mode="json", exclude_none=True)
        args.update(
            calendarId=effect.calendar_id,
            notificationLevel="ALL" if effect.notify else "NONE",
        )
        if effect.event_id is not None:
            args["eventId"] = effect.event_id
        operation = effect.tool.removeprefix("calendar.")
        result = await io.call(
            "calendar",
            operation,
            args,
            preflight=lambda: _fresh_event(io, effect),
            write=True,
        )
        try:
            if (
                operation == "delete_event"
                and "id" not in result
                and effect.event_id is not None
            ):
                event_id = effect.event_id
            else:
                event_id = provider_id(result, "id")
            if effect.event_id is not None and effect.event_id != event_id:
                raise ValueError("different event")
            status = result.get("status")
            if (
                operation != "delete_event"
                and status is not None
                and status not in {"confirmed", "tentative"}
            ):
                raise ValueError("conflicting acknowledgement")
        except (TypeError, *_PARSE_ERRORS):
            raise WorkspaceError("uncertain") from None
        now = datetime.now(UTC)
        outcome: Literal["created", "updated", "deleted"] = (
            "created"
            if operation == "create_event"
            else "updated"
            if operation == "update_event"
            else "deleted"
        )
        return CalendarWriteReceipt(
            action_id=frozen.action_id,
            grant_id=frozen.grant_id,
            account=frozen.account,
            acknowledged_at=now,
            observed_at=now,
            verification="unverified",
            reason="readback_pending",
            outcome=outcome,
            calendar_id=effect.calendar_id,
            event_id=event_id,
            scope=effect.scope,
            notify=effect.notify,
            link=workspace_link(
                result.get("htmlLink"),
                "calendar",
                event_id,
                effect.calendar_id,
                account=io.account,
            ),
        )

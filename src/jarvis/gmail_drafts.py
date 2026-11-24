"""Verified Gmail draft revisions and their RFC 822 representation."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.errors import HeaderParseError, NonASCIILocalPartDefect
from email.header import Header, decode_header, make_header
from email.headerregistry import Address, AddressHeader, BaseHeader
from email.message import EmailMessage, MIMEPart
from email.parser import BytesParser
from email.utils import getaddresses
from typing import Protocol, cast
from urllib.parse import quote
from uuid import UUID

from llm_tools import canonical_json_bytes

from jarvis.connectors import provider_string
from jarvis.mail_files import (
    MAIL_MAX_BYTES,
    MAIL_MAX_FILES,
    MailFile,
    MailFileFailure,
    MailLimit,
    canonical_media_type,
)
from jarvis.write_tools import (
    GMAIL_WRITE_POLICY,
    GmailAlreadySent,
    GmailComposeBasis,
    GmailComposeContract,
    GmailContent,
    GmailCurrentDraft,
    GmailDraftIdentity,
    GmailDraftSuccess,
    GmailRevision,
    GmailSendDraftSuccess,
    GmailSnapshot,
    GmailStagedPart,
    Mailbox,
    ReconciliationResult,
    WriteConnectorFailure,
    WriteResponse,
)

EFFECT_HEADER = "X-Jarvis-Effect-ID"
MAX_DRAFT_PAGES = 5
DRAFT_PAGE_SIZE = 8
_RAW_DRAFT_FIELDS = "id,message(id,threadId,labelIds,raw)"
_METADATA_MESSAGE_FIELDS = "id,threadId,labelIds,payload(headers)"
_ACK_DRAFT_FIELDS = "id,message(id,threadId)"
_RFC_ID = re.compile(r"<[^<>\s\x00-\x1f\x7f]+>")
_EFFECT_ID = re.compile(r"[0-9a-f]{64}")
_REPLY_PREFIX = re.compile(r"^(?:re:[ \t]*)+", re.IGNORECASE)
_ROUTING_HEADERS = {
    "reply-to",
    "x-envelope-from",
    "x-envelope-to",
    "x-original-to",
    "errors-to",
}


class GmailOperation(Protocol):
    @property
    def attempts(self) -> int: ...

    def now(self) -> datetime: ...

    async def sleep(self, delay: float) -> None: ...

    async def account(self) -> str: ...

    async def request(
        self,
        method: str,
        route: str,
        *,
        account: str = "me",
        params: Mapping[str, str | int | tuple[str, ...]] | None = None,
        metadata: dict[str, object] | None = None,
        mime: bytes | None = None,
        raw: bool = False,
        errors: Mapping[int, str | None] | None = None,
    ) -> dict[str, object] | None: ...


@dataclass(frozen=True, slots=True)
class DecodedMail:
    snapshot: GmailSnapshot
    effect_id: str
    parts: tuple[bytes, ...]


def gmail_effect_id(creation_id: UUID) -> str:
    return hashlib.sha256(f"jarvis-gmail-v1:{creation_id}".encode()).hexdigest()


def content_digest(snapshot: GmailSnapshot) -> str:
    return hashlib.sha256(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    ).hexdigest()


def _body(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _address(mailbox: Mailbox) -> Address:
    local, _, domain = mailbox.address.rpartition("@")
    return Address(display_name=mailbox.name or "", username=local, domain=domain)


def _canonical_recipient(mailbox: Mailbox) -> Mailbox:
    return Mailbox(name=mailbox.name or None, address=mailbox.address)


def _set_recipients(
    message: EmailMessage, name: str, recipients: tuple[Mailbox, ...]
) -> None:
    if not recipients:
        return
    values: list[str] = []
    for recipient in recipients:
        address = _address(recipient)
        display_name = address.display_name
        if display_name:
            label = Header(display_name, charset="utf-8", header_name=name).encode(
                linesep="\r\n"
            )
            values.append(f"{label} <{address.addr_spec}>")
        else:
            values.append(address.addr_spec)
    message.set_raw(name, ",\r\n ".join(values))


def compose_snapshot(
    content: GmailContent,
    account: str,
    files: tuple[MailFile, ...],
    in_reply_to: str | None,
    references: tuple[str, ...],
) -> GmailSnapshot:
    return GmailSnapshot(
        sender=Mailbox(name=None, address=account).address,
        to=tuple(_canonical_recipient(item) for item in content.to),
        cc=tuple(_canonical_recipient(item) for item in content.cc),
        bcc=tuple(_canonical_recipient(item) for item in content.bcc),
        subject=content.subject,
        body_text=_body(content.body_text),
        in_reply_to=in_reply_to,
        references=references,
        files=files,
    )


def _limit(measure: str, actual: int, maximum: int) -> None:
    if actual > maximum:
        raise MailFileFailure(
            MailLimit.model_validate(
                {"measure": measure, "actual": actual, "maximum": maximum}
            )
        )


def _describe_part(filename: str, media_type: str, data: bytes) -> MailFile:
    return MailFile(
        filename=filename,
        media_type=canonical_media_type(media_type),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def encode_mime(
    snapshot: GmailSnapshot, effect_id: str, parts: tuple[bytes, ...]
) -> bytes:
    if not _EFFECT_ID.fullmatch(effect_id) or len(parts) != len(snapshot.files):
        raise ValueError("invalid Gmail encode input")
    _limit("decoded_bytes", sum(map(len, parts)), MAIL_MAX_BYTES)
    message = EmailMessage(policy=policy.SMTP.clone(refold_source="none"))
    message["From"] = _address(Mailbox(name=None, address=snapshot.sender))
    recipients = (("To", snapshot.to), ("Cc", snapshot.cc), ("Bcc", snapshot.bcc))
    for name, mailboxes in recipients:
        _set_recipients(message, name, mailboxes)
    parsed = BytesParser(policy=policy.default).parsebytes(
        message.as_bytes(), headersonly=True
    )
    if any(_mailboxes(parsed, name) != mailboxes for name, mailboxes in recipients):
        raise ValueError("invalid Gmail recipient representation")
    message.set_raw(
        "Subject",
        Header(snapshot.subject, charset="utf-8", header_name="Subject").encode(
            linesep="\r\n"
        ),
    )
    message[EFFECT_HEADER] = effect_id
    if snapshot.in_reply_to is not None:
        message["In-Reply-To"] = snapshot.in_reply_to
    if snapshot.references:
        message["References"] = " ".join(snapshot.references)
    # The bytes content handler preserves the presence or absence of a final LF.
    message.set_content(
        snapshot.body_text.encode(),
        maintype="text",
        subtype="plain",
        cte="base64",
        params={"charset": "utf-8"},
    )
    for descriptor, data in zip(snapshot.files, parts, strict=True):
        if (
            _describe_part(descriptor.filename, descriptor.media_type, data)
            != descriptor
        ):
            raise ValueError("Gmail part does not match its frozen descriptor")
        maintype, _, subtype = descriptor.media_type.partition("/")
        message.add_attachment(
            data, maintype=maintype, subtype=subtype, filename=descriptor.filename
        )
    mime = message.as_bytes()
    _limit("mime_bytes", len(mime), GMAIL_WRITE_POLICY.mime_bytes)
    return mime


async def encode_for_write(
    mail: GmailOperation,
    snapshot: GmailSnapshot,
    effect_id: str,
    parts: tuple[bytes, ...],
) -> bytes:
    try:
        return await asyncio.to_thread(encode_mime, snapshot, effect_id, parts)
    except MailFileFailure as exc:
        raise WriteConnectorFailure(
            "mail_limit", attempts=mail.attempts, details=exc.error
        ) from None
    except (ValueError, TypeError):
        raise WriteConnectorFailure("invalid_mail", attempts=mail.attempts) from None


def decode_raw(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > GMAIL_WRITE_POLICY.raw_bytes:
        raise ValueError("raw Gmail message is malformed or oversized")
    try:
        decoded = base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error):
        raise ValueError("raw Gmail message is malformed") from None
    if len(decoded) > GMAIL_WRITE_POLICY.mime_bytes:
        raise ValueError("raw Gmail MIME is oversized")
    return decoded


def _header(message: MIMEPart, name: str) -> str | None:
    values = message.get_all(name, [])
    if not values:
        return None
    if len(values) != 1 or values[0].defects:
        raise ValueError("ambiguous Gmail header")
    value = str(values[0])
    if len(value.encode()) > 16_384:
        raise ValueError("oversized Gmail header")
    return value


def _mailboxes(message: MIMEPart, name: str) -> tuple[Mailbox, ...]:
    values = message.get_all(name, [])
    if not values:
        return ()
    header = values[0]
    if (
        len(values) != 1
        or not isinstance(header, AddressHeader)
        or any(
            not isinstance(defect, NonASCIILocalPartDefect)
            for defect in cast(BaseHeader, header).defects
        )
        or any(group.display_name is not None for group in header.groups)
        or len(str(header).encode()) > 16_384
    ):
        raise ValueError("ambiguous Gmail routing")
    # Decode the raw phrases after the structured check. RFC 2047 discards
    # whitespace between adjacent encoded words, including across folds.
    raw = [
        value for field, value in message.raw_items() if field.lower() == name.lower()
    ]
    phrases = getaddresses(raw, strict=True)
    if len(phrases) != len(header.addresses):
        raise ValueError("ambiguous Gmail routing")
    try:
        return tuple(
            Mailbox(
                name=str(make_header(decode_header(phrase))) or None,
                address=f"{address.username}@{address.domain}",
            )
            for (phrase, _), address in zip(phrases, header.addresses, strict=True)
        )
    except (HeaderParseError, LookupError):
        raise ValueError("invalid Gmail display phrase") from None


def _message_ids(value: str) -> tuple[str, ...]:
    ids = tuple(value.split())
    if len(value.encode()) > 16_384 or not all(
        _RFC_ID.fullmatch(item) and len(item.encode()) <= 998 for item in ids
    ):
        raise ValueError("invalid RFC message ids")
    return ids


def _leaf_payload(message: MIMEPart, *, attachment: bool) -> bytes:
    for name in (
        "MIME-Version",
        "Content-Type",
        "Content-Disposition",
        "Content-Transfer-Encoding",
        "Content-ID",
        "Content-Location",
    ):
        value = _header(message, name)
        if name in {"Content-ID", "Content-Location"} and value is not None:
            raise ValueError("inline Gmail part")
    transfer = message.get("Content-Transfer-Encoding", "").lower()
    if (
        message.is_multipart()
        or message.get_content_disposition() != ("attachment" if attachment else None)
        or transfer not in {"", "7bit", "8bit", "binary", "base64", "quoted-printable"}
    ):
        raise ValueError("unsupported Gmail part")
    data = message.get_payload(decode=True)
    if not isinstance(data, bytes) or message.defects:
        raise ValueError("malformed Gmail part")
    return data


def decode_mime(raw: bytes, account: str) -> DecodedMail:
    if len(raw) > GMAIL_WRITE_POLICY.mime_bytes:
        raise ValueError("raw Gmail MIME is oversized")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if message.defects or any(
        header.lower() in _ROUTING_HEADERS or header.lower().startswith("resent-")
        for header in message.keys()
    ):
        raise ValueError("unsupported Gmail routing")
    sender = Mailbox(name=None, address=account).address
    from_ = _mailboxes(message, "From")
    sent_by = _mailboxes(message, "Sender")
    if (
        len(from_) != 1
        or from_[0].address != sender
        or (sent_by and (len(sent_by) != 1 or sent_by[0].address != sender))
        or ("Sender" in message and not sent_by)
    ):
        raise ValueError("Gmail sender is not the configured account")
    effect = _header(message, EFFECT_HEADER)
    if effect is None or not _EFFECT_ID.fullmatch(effect):
        raise ValueError("invalid Gmail effect header")
    subject = _header(message, "Subject")
    in_reply_to = _message_ids(_header(message, "In-Reply-To") or "")
    references = _message_ids(_header(message, "References") or "")
    if (
        subject is None
        or ("In-Reply-To" in message and len(in_reply_to) != 1)
        or ("References" in message and not references)
        or bool(in_reply_to) != bool(references)
    ):
        raise ValueError("invalid Gmail subject or reply headers")

    leaves = tuple(message.iter_parts())
    if leaves:
        for name in (
            "MIME-Version",
            "Content-Type",
            "Content-Disposition",
            "Content-Transfer-Encoding",
            "Content-ID",
            "Content-Location",
        ):
            value = _header(message, name)
            if name not in {"MIME-Version", "Content-Type"} and value is not None:
                raise ValueError("unsupported Gmail MIME container")
        if (
            message.get_content_type() != "multipart/mixed"
            or len(leaves) < 2
            or len(leaves) - 1 > MAIL_MAX_FILES
            or (message.preamble or "").strip()
            or (message.epilogue or "").strip()
        ):
            raise ValueError("unsupported Gmail MIME shape")
        body, *attachments = leaves
    else:
        body, attachments = message, []
    if body.get_content_type() != "text/plain" or body.get_filename() is not None:
        raise ValueError("unsupported Gmail body")
    body_data = _leaf_payload(body, attachment=False)
    charset = body.get_content_charset() or "ascii"
    if charset not in {"utf-8", "utf8", "us-ascii", "ascii"}:
        raise ValueError("unsupported Gmail body charset")
    body_text = _body(body_data.decode(charset))
    files: list[MailFile] = []
    parts: list[bytes] = []
    total = 0
    for part in attachments:
        data = _leaf_payload(part, attachment=True)
        filename = part.get_param("filename", header="Content-Disposition")
        if not isinstance(filename, str) or not filename:
            raise ValueError("missing Gmail attachment filename")
        total += len(data)
        if total > MAIL_MAX_BYTES:
            raise ValueError("Gmail attachment total exceeds bound")
        files.append(_describe_part(filename, part.get_content_type(), data))
        parts.append(data)
    snapshot = GmailSnapshot(
        sender=sender,
        to=_mailboxes(message, "To"),
        cc=_mailboxes(message, "Cc"),
        bcc=_mailboxes(message, "Bcc"),
        subject=subject,
        body_text=body_text,
        in_reply_to=in_reply_to[0] if in_reply_to else None,
        references=references,
        files=tuple(files),
    )
    return DecodedMail(snapshot, effect, tuple(parts))


def provider_id(payload: dict[str, object], key: str) -> str:
    value = provider_string(payload, key)
    if len(value.encode()) > 1_024 or any(
        character.isspace() or ord(character) < 32 for character in value
    ):
        raise ValueError("malformed Gmail identifier")
    return value


def provider_labels(payload: dict[str, object]) -> frozenset[str]:
    values = payload.get("labelIds")
    if not isinstance(values, list):
        raise ValueError("malformed Gmail labels")
    labels = frozenset(
        provider_id({"label": value}, "label") for value in cast(list[object], values)
    )
    if len(labels) != len(cast(list[object], values)):
        raise ValueError("duplicate Gmail labels")
    return labels


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("malformed Gmail object")
    return cast(dict[str, object], value)


def _metadata_headers(message: dict[str, object]) -> dict[str, str]:
    # A selected Gmail projection can omit an empty payload or headers array.
    payload = _mapping(message.get("payload", {}))
    headers = payload.get("headers", [])
    if not isinstance(headers, list):
        raise ValueError("malformed Gmail header projection")
    result: dict[str, str] = {}
    for item in cast(list[object], headers):
        header = _mapping(item)
        key = provider_id(header, "name").lower()
        value = header.get("value")
        if not isinstance(value, str) or len(value.encode()) > 16_384 or key in result:
            raise ValueError("malformed Gmail header projection")
        result[key] = value
    return result


def metadata_marker(message: dict[str, object]) -> str | None:
    marker = _metadata_headers(message).get(EFFECT_HEADER.lower())
    if marker is not None and not _EFFECT_ID.fullmatch(marker):
        raise ValueError("malformed Gmail effect marker")
    return marker


def _draft_identity(payload: dict[str, object]) -> GmailDraftIdentity:
    message = _mapping(payload.get("message"))
    return GmailDraftIdentity(
        draft_id=provider_id(payload, "id"),
        thread_id=provider_id(message, "threadId"),
        message_id=provider_id(message, "id"),
    )


def _decode_draft(
    payload: dict[str, object], account: str
) -> tuple[GmailRevision, DecodedMail]:
    identity = _draft_identity(payload)
    message = _mapping(payload.get("message"))
    labels = provider_labels(message)
    if "DRAFT" not in labels or "SENT" in labels:
        raise ValueError("invalid draft labels")
    decoded = decode_mime(decode_raw(message.get("raw")), account)
    revision = GmailRevision(
        draft_id=identity.draft_id,
        thread_id=identity.thread_id,
        message_id=identity.message_id,
        account=account,
        jarvis_effect_id=decoded.effect_id,
        content_digest=content_digest(decoded.snapshot),
    )
    return revision, decoded


async def _read_draft(
    mail: GmailOperation, account: str, draft_id: str
) -> tuple[GmailRevision, DecodedMail] | None:
    payload = await mail.request(
        "GET",
        f"drafts/{quote(draft_id, safe='')}",
        account=account,
        params={"format": "raw", "fields": _RAW_DRAFT_FIELDS},
        errors={404: None},
        raw=True,
    )
    if payload is None:
        return None
    observed = await asyncio.to_thread(_decode_draft, payload, account)
    if observed[0].draft_id != draft_id:
        raise ValueError("draft id changed")
    return observed


async def read_revision(mail: GmailOperation, revision: GmailRevision) -> DecodedMail:
    try:
        observed = await _read_draft(mail, revision.account, revision.draft_id)
    except ValueError:
        raise WriteConnectorFailure("draft_changed", attempts=mail.attempts) from None
    if observed is None:
        raise WriteConnectorFailure("draft_not_found", attempts=mail.attempts)
    live_revision, decoded = observed
    if live_revision != revision:
        raise WriteConnectorFailure("draft_changed", attempts=mail.attempts)
    return decoded


async def _reply_headers(
    mail: GmailOperation, account: str, content: GmailContent
) -> tuple[str | None, tuple[str, ...]]:
    reply = content.reply_to
    if reply is None:
        return None, ()
    parent = await mail.request(
        "GET",
        f"messages/{quote(reply.parent_message_id, safe='')}",
        account=account,
        params={
            "format": "metadata",
            "metadataHeaders": ("Message-ID", "References", "Subject"),
            "fields": _METADATA_MESSAGE_FIELDS,
        },
        errors={404: None},
    )
    if parent is None:
        raise WriteConnectorFailure("thread_not_found", attempts=mail.attempts)
    try:
        headers = _metadata_headers(parent)
        ids = _message_ids(headers["message-id"])
        references = _message_ids(headers.get("references", ""))
        subject = str(make_header(decode_header(headers["subject"])))
        if (
            provider_id(parent, "id") != reply.parent_message_id
            or provider_id(parent, "threadId") != reply.thread_id
            or ids != (reply.parent_rfc822_message_id,)
            or _REPLY_PREFIX.sub("", subject) != _REPLY_PREFIX.sub("", content.subject)
        ):
            raise ValueError("reply parent differs")
        parent_id = ids[0]
        chain = (*tuple(item for item in references if item != parent_id), parent_id)
        _message_ids(" ".join(chain))
    except (KeyError, ValueError, LookupError):
        raise WriteConnectorFailure("thread_mismatch", attempts=mail.attempts) from None
    return parent_id, chain


def _receipt(
    action_id: UUID, revision: GmailRevision, desired: GmailSnapshot, now: datetime
) -> GmailCurrentDraft:
    return GmailCurrentDraft(
        draft_ref=action_id,
        revision=revision,
        in_reply_to=desired.in_reply_to,
        references=desired.references,
        files=desired.files,
        observed_at=now,
    )


async def compose_draft(
    mail: GmailOperation,
    content: GmailContent,
    contract: GmailComposeContract,
    action_id: UUID,
    *,
    read_part: Callable[[int, MailFile], Awaitable[bytes]],
    stage_basis: Callable[[GmailComposeBasis], Awaitable[object]],
    stage_ack: Callable[[GmailDraftIdentity], Awaitable[object]],
) -> WriteResponse[GmailDraftSuccess]:
    account = await mail.account()
    old = contract.base_revision
    current: DecodedMail | None = None
    if old is not None:
        if (
            account != old.account
            or gmail_effect_id(contract.creation_id) != old.jarvis_effect_id
        ):
            raise WriteConnectorFailure("draft_changed", attempts=mail.attempts)
        current = await read_revision(mail, old)
    reply_id, references = await _reply_headers(mail, account, content)
    thread_id = content.reply_to.thread_id if content.reply_to is not None else None
    if old is not None and current is not None:
        if current.snapshot.in_reply_to != reply_id or thread_id not in (
            None,
            old.thread_id,
        ):
            raise WriteConnectorFailure("thread_mismatch", attempts=mail.attempts)
        thread_id = old.thread_id

    parts: list[bytes] = []
    for source in contract.parts:
        if isinstance(source, GmailStagedPart):
            parts.append(await read_part(source.slot, source.file))
        else:
            if (
                current is None
                or source.existing_part > len(current.parts)
                or current.snapshot.files[source.existing_part - 1] != source.file
            ):
                raise WriteConnectorFailure("draft_changed", attempts=mail.attempts)
            parts.append(current.parts[source.existing_part - 1])
    effect = gmail_effect_id(contract.creation_id)
    try:
        desired = compose_snapshot(
            content,
            account,
            tuple(source.file for source in contract.parts),
            reply_id,
            references,
        )
    except ValueError:
        raise WriteConnectorFailure("invalid_mail", attempts=mail.attempts) from None
    if old is not None and current is not None and desired == current.snapshot:
        return WriteResponse(
            _receipt(action_id, old, desired, mail.now()), mail.attempts
        )
    mime = await encode_for_write(mail, desired, effect, tuple(parts))
    del parts, current
    await stage_basis(
        GmailComposeBasis(
            account=account, old_revision=old, desired=desired, thread_id=thread_id
        )
    )

    message: dict[str, object] = {}
    if thread_id is not None:
        message["threadId"] = thread_id
    metadata: dict[str, object] = {"message": message}
    method, route = "POST", "drafts"
    errors: dict[int, str | None] = {
        400: "invalid_recipient",
        404: "thread_not_found",
        409: "conflict",
    }
    if old is not None:
        method, route = "PUT", f"drafts/{quote(old.draft_id, safe='')}"
        metadata["id"] = old.draft_id
        errors = {
            400: "thread_mismatch",
            404: "draft_not_found",
            409: "draft_changed",
            412: "draft_changed",
        }
    response = await mail.request(
        method,
        route,
        account=account,
        params={"fields": _ACK_DRAFT_FIELDS},
        metadata=metadata,
        mime=mime,
        errors=errors,
    )
    del mime
    try:
        ack = _draft_identity(_mapping(response))
        await stage_ack(ack)
        if (thread_id is not None and ack.thread_id != thread_id) or (
            old is not None
            and (ack.draft_id != old.draft_id or ack.message_id == old.message_id)
        ):
            raise ValueError("unexpected draft acknowledgement")
        observed = await _read_draft(mail, account, ack.draft_id)
        if observed is None:
            raise ValueError("created draft missing")
        revision, decoded = observed
        if (
            revision.message_id != ack.message_id
            or revision.thread_id != ack.thread_id
            or revision.jarvis_effect_id != effect
            or decoded.snapshot != desired
        ):
            raise ValueError("created draft does not match")
    except (ValueError, WriteConnectorFailure) as exc:
        raise TimeoutError("Gmail draft write needs reconciliation") from exc
    return WriteResponse(
        _receipt(action_id, revision, desired, mail.now()), mail.attempts
    )


class _ConflictingDraftEvidence(ValueError):
    pass


async def _create_scan(
    mail: GmailOperation,
    basis: GmailComposeBasis,
    effect: str,
    acknowledgement: GmailDraftIdentity | None,
) -> GmailRevision | None:
    matched: GmailRevision | None = None
    seen: set[str] = set()
    token: str | None = None
    tokens: set[str] = set()
    for _ in range(MAX_DRAFT_PAGES):
        params: dict[str, str | int] = {
            "fields": "drafts(id,message(id,threadId)),nextPageToken",
            "maxResults": DRAFT_PAGE_SIZE,
        }
        if token is not None:
            params["pageToken"] = token
        page = _mapping(
            await mail.request("GET", "drafts", account=basis.account, params=params)
        )
        drafts = page.get("drafts", [])
        if (
            not isinstance(drafts, list)
            or len(cast(list[object], drafts)) > DRAFT_PAGE_SIZE
        ):
            raise WriteConnectorFailure("provider_unavailable", attempts=mail.attempts)
        for item in cast(list[object], drafts):
            identity = _draft_identity(_mapping(item))
            if identity.draft_id in seen:
                raise WriteConnectorFailure(
                    "provider_unavailable", attempts=mail.attempts
                )
            seen.add(identity.draft_id)
            metadata = _mapping(
                await mail.request(
                    "GET",
                    f"messages/{quote(identity.message_id, safe='')}",
                    account=basis.account,
                    params={
                        "format": "metadata",
                        "metadataHeaders": EFFECT_HEADER,
                        "fields": _METADATA_MESSAGE_FIELDS,
                    },
                )
            )
            if (
                provider_id(metadata, "id") != identity.message_id
                or provider_id(metadata, "threadId") != identity.thread_id
            ):
                raise WriteConnectorFailure(
                    "provider_unavailable", attempts=mail.attempts
                )
            if metadata_marker(metadata) != effect:
                continue
            if matched is not None:
                raise _ConflictingDraftEvidence("duplicate Gmail create marker")
            try:
                observed = await _read_draft(mail, basis.account, identity.draft_id)
                draft_labels = provider_labels(metadata)
            except ValueError:
                raise _ConflictingDraftEvidence("invalid marked Gmail draft") from None
            if (
                observed is None
                or "DRAFT" not in draft_labels
                or "SENT" in draft_labels
            ):
                raise _ConflictingDraftEvidence(
                    "missing or conflicting marked Gmail draft"
                )
            revision, decoded = observed
            if (
                revision.message_id != identity.message_id
                or revision.thread_id != identity.thread_id
                or revision.jarvis_effect_id != effect
                or decoded.snapshot != basis.desired
                or (
                    basis.thread_id is not None
                    and revision.thread_id != basis.thread_id
                )
                or (acknowledgement is not None and acknowledgement != identity)
            ):
                raise _ConflictingDraftEvidence("conflicting Gmail create matches")
            matched = revision
        if "nextPageToken" not in page:
            break
        token = provider_id(page, "nextPageToken")
        if token in tokens:
            raise WriteConnectorFailure("provider_unavailable", attempts=mail.attempts)
        tokens.add(token)
    return matched


async def reconcile_draft(
    mail: GmailOperation,
    action_id: UUID,
    contract: GmailComposeContract,
    basis: GmailComposeBasis,
    *,
    acknowledged: bool,
    acknowledgement: GmailDraftIdentity | None,
    observe_sent: Callable[
        [GmailRevision, GmailSnapshot],
        Awaitable[ReconciliationResult[GmailSendDraftSuccess]],
    ],
) -> ReconciliationResult[GmailDraftSuccess]:
    effect = gmail_effect_id(contract.creation_id)
    old = contract.base_revision
    if (
        basis.old_revision != old
        or basis.account != basis.desired.sender
        or (
            old is not None
            and (old.account != basis.account or effect != old.jarvis_effect_id)
        )
        or (acknowledgement is not None and not acknowledged)
    ):
        raise ValueError("stored Gmail draft recovery basis conflicts with the action")
    try:
        if await mail.account() != basis.account:
            return ReconciliationResult("uncertain", "gmail-account-changed")
    except WriteConnectorFailure:
        return ReconciliationResult("uncertain", "gmail-account-unavailable")

    intact = 0
    for delay in GMAIL_WRITE_POLICY.recovery_delays:
        if delay:
            await mail.sleep(delay)
        if old is None:
            try:
                revision = await _create_scan(mail, basis, effect, acknowledgement)
            except _ConflictingDraftEvidence:
                return ReconciliationResult(
                    "uncertain", "conflicting-gmail-draft-evidence"
                )
            except (WriteConnectorFailure, ValueError):
                continue
            if revision is not None:
                return ReconciliationResult(
                    "succeeded",
                    "verified-created-draft",
                    _receipt(action_id, revision, basis.desired, mail.now()),
                )
            continue
        try:
            observed = await _read_draft(mail, basis.account, old.draft_id)
        except WriteConnectorFailure:
            continue
        except ValueError:
            return ReconciliationResult("uncertain", "conflicting-gmail-draft-evidence")

        if observed is None:
            sent = await observe_sent(old, basis.desired)
            if sent.value is not None:
                receipt = GmailAlreadySent(
                    draft_ref=None,
                    sent=sent.value,
                    files=basis.desired.files,
                    observed_at=mail.now(),
                )
                return ReconciliationResult("succeeded", sent.evidence, receipt)
            return ReconciliationResult("uncertain", sent.evidence)
        revision, decoded = observed
        if revision == old:
            intact += 1
            continue
        if (
            revision.message_id != old.message_id
            and revision.thread_id == old.thread_id
            and revision.jarvis_effect_id == effect
            and decoded.snapshot == basis.desired
            and (
                acknowledgement is None
                or (
                    acknowledgement.message_id,
                    acknowledgement.thread_id,
                    acknowledgement.draft_id,
                )
                == (revision.message_id, revision.thread_id, revision.draft_id)
            )
        ):
            return ReconciliationResult(
                "succeeded",
                "verified-replaced-draft",
                _receipt(action_id, revision, basis.desired, mail.now()),
            )
        return ReconciliationResult("uncertain", "conflicting-gmail-draft-evidence")
    if intact == len(GMAIL_WRITE_POLICY.recovery_delays) and not acknowledged:
        return ReconciliationResult("absent", "intact-unsent-base-revision")
    return ReconciliationResult("uncertain", "incomplete-gmail-draft-evidence")

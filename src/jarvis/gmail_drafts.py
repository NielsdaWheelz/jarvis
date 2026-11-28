"""Historical draft receipt rendering and strict Workspace MIME evidence."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from email import policy
from email.errors import HeaderParseError, NonASCIILocalPartDefect
from email.header import decode_header, make_header
from email.headerregistry import AddressHeader, BaseHeader
from email.message import MIMEPart
from email.parser import BytesParser
from email.utils import getaddresses
from typing import Annotated, cast
from uuid import UUID

from llm_tools import canonical_json_bytes
from llm_tools.content import html_visible_text
from pydantic import Field

from jarvis.actions import (
    ActionPersistenceDefect,
    StoredAction,
)
from jarvis.connectors import provider_string
from jarvis.mail_files import (
    MAIL_MAX_BYTES,
    MAIL_MAX_FILES,
    MailFile,
    canonical_media_type,
)
from jarvis.workspace_write_models import DraftSnapshot
from jarvis.write_tools import (
    GMAIL_WRITE_POLICY,
    GmailComposeContract,
    GmailContent,
    GmailCurrentDraft,
    GmailReplyTo,
    GmailSnapshot,
    Mailbox,
)

_RFC_ID = re.compile(r"<[^<>\s\x00-\x1f\x7f]+>")
_REPLY_PREFIX = re.compile(r"^(?:re:[ \t]*)+", re.IGNORECASE)
_PLAIN_ALTERNATIVE_MARKUP = re.compile(
    r"(?i)(?:[ \t\r\n]*<!doctype[ \t]+html[ \t]*>)?"
    r"(?:[^<>]++|</(?:html|body|div|span|p)[ \t\r\n]*>"
    r"|<(?:html|body|div|span|p)"
    r"""(?:[ \t\r\n]+dir=(?:"(?:ltr|rtl|auto)"|'(?:ltr|rtl|auto)'|ltr|rtl|auto))?"""
    r"[ \t\r\n]*>|<br[ \t\r\n]*/?>)*"
)
_ROUTING_HEADERS = {
    "reply-to",
    "x-envelope-from",
    "x-envelope-to",
    "x-original-to",
    "errors-to",
}


def gmail_effect_id(creation_id: UUID) -> str:
    return hashlib.sha256(f"jarvis-gmail-v1:{creation_id}".encode()).hexdigest()


def content_digest(snapshot: GmailSnapshot) -> str:
    return hashlib.sha256(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class VerifiedDraft:
    receipt: GmailCurrentDraft
    snapshot: GmailSnapshot
    reply_to: GmailReplyTo | None
    creation_id: UUID


def verified_draft(stored: StoredAction) -> VerifiedDraft | None:
    """Render an outgoing-files binding's original, immutable revision."""
    if stored.status != "succeeded" or stored.tool_name not in {
        "gmail.create_draft",
        "gmail.update_draft",
    }:
        return None
    contract = stored.execution_contract.as_json()
    if (
        contract.get("implementation_revision")
        != f"jarvis-{stored.tool_name.replace('.', '-')}-v2"
    ):
        return None
    try:
        authority = GmailComposeContract.model_validate(contract.get("mail"))
    except ValueError as exc:
        raise ActionPersistenceDefect(
            "compose receipt lacks its frozen contract"
        ) from exc
    receipt = stored.result
    if (
        receipt is None
        or set(receipt) != {"type", "value"}
        or receipt["type"] != "Success"
    ):
        raise ActionPersistenceDefect("successful compose lacks its receipt")
    value = receipt["value"]
    if (
        isinstance(value, dict)
        and cast(dict[str, object], value).get("state") == "already_sent"
    ):
        return None
    try:
        draft = GmailCurrentDraft.model_validate(value)
        content = GmailContent.model_validate(
            stored.payload.get(
                "content" if stored.tool_name == "gmail.create_draft" else "replacement"
            )
        )
        snapshot = compose_snapshot(
            content,
            draft.revision.account,
            draft.files,
            draft.in_reply_to,
            draft.references,
        )
    except ValueError as exc:
        raise ActionPersistenceDefect("verified draft receipt is invalid") from exc
    if (
        draft.draft_ref != stored.id
        or gmail_effect_id(authority.creation_id) != draft.revision.jarvis_effect_id
    ):
        raise ActionPersistenceDefect("draft receipt has a different creation identity")
    if content_digest(snapshot) != draft.revision.content_digest:
        raise ActionPersistenceDefect("verified draft content changed in the ledger")
    return VerifiedDraft(draft, snapshot, content.reply_to, authority.creation_id)


def _body(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_recipient(mailbox: Mailbox) -> Mailbox:
    return Mailbox(name=mailbox.name or None, address=mailbox.address)


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


def _describe_part(filename: str, media_type: str, data: bytes) -> MailFile:
    return MailFile(
        filename=filename,
        media_type=canonical_media_type(media_type),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


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


def _attachment_filename(message: MIMEPart) -> str:
    _header(message, "Content-Disposition")
    filename = message.get_param("filename", header="Content-Disposition")
    if not isinstance(filename, str) or not filename:
        raise ValueError("missing Gmail attachment filename")
    return filename


class EditorSnapshot(GmailSnapshot):
    """A human draft may have no primary recipient and retains its sender name."""

    to: Annotated[tuple[Mailbox, ...], Field(max_length=50)]
    sender_name: str | None


def _envelope_snapshot(
    message: MIMEPart,
    account: str,
    body_text: str,
    files: tuple[MailFile, ...],
    editor: bool,
) -> GmailSnapshot:
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
    subject = _header(message, "Subject")
    if editor and subject is None:
        subject = ""
    in_reply_to = _message_ids(_header(message, "In-Reply-To") or "")
    references = _message_ids(_header(message, "References") or "")
    if (
        subject is None
        or ("In-Reply-To" in message and len(in_reply_to) != 1)
        or ("References" in message and not references)
        or bool(in_reply_to) != bool(references)
    ):
        raise ValueError("invalid Gmail subject or reply headers")

    fields = {
        "from": sender,
        "to": _mailboxes(message, "To"),
        "cc": _mailboxes(message, "Cc"),
        "bcc": _mailboxes(message, "Bcc"),
        "subject": subject,
        "body_text": body_text,
        "in_reply_to": in_reply_to[0] if in_reply_to else None,
        "references": references,
        "files": files,
    }
    if editor:
        return EditorSnapshot.model_validate({**fields, "sender_name": from_[0].name})
    return GmailSnapshot.model_validate(fields)


def _draft_container(message: MIMEPart) -> None:
    for name in ("MIME-Version", "Content-Type"):
        _header(message, name)
    if (
        message.defects
        or any(
            name in message
            for name in (
                "Content-Disposition",
                "Content-Transfer-Encoding",
                "Content-ID",
                "Content-Location",
            )
        )
        or (message.preamble or "").strip()
        or (message.epilogue or "").strip()
    ):
        raise ValueError("unsupported Gmail MIME container")


def _plain_parts(
    message: MIMEPart,
) -> tuple[str, tuple[MailFile, ...], tuple[bytes, ...]]:
    body = message
    attachments: list[MIMEPart] = []
    if message.get_content_type() == "multipart/mixed":
        _draft_container(message)
        leaves = list(message.iter_parts())
        if not 2 <= len(leaves) <= MAIL_MAX_FILES + 1:
            raise ValueError("unsupported Gmail MIME shape")
        body, *attachments = leaves
    html = None
    if body.get_content_type() == "multipart/alternative":
        _draft_container(body)
        choices = tuple(body.iter_parts())
        if len(choices) != 2 or choices[1].get_content_type() != "text/html":
            raise ValueError("unsupported Gmail body alternative")
        body, html = choices
    if body.get_content_type() != "text/plain" or body.get_filename() is not None:
        raise ValueError("unsupported Gmail body")
    body_data = _leaf_payload(body, attachment=False)
    charset = body.get_content_charset() or "ascii"
    if charset not in {"utf-8", "utf8", "us-ascii", "ascii"}:
        raise ValueError("unsupported Gmail body charset")
    body_text = _body(body_data.decode(charset))
    if body.get_param("format") == "flowed" and any(
        line.startswith(" ") or (line.endswith(" ") and line != "-- ")
        for line in body_text.splitlines()
    ):
        raise ValueError("unsupported flowed Gmail draft body")
    if html is not None:
        data = _leaf_payload(html, attachment=False)
        charset = html.get_content_charset() or "ascii"
        if (
            html.get_filename() is not None
            or charset not in {"utf-8", "utf8", "us-ascii", "ascii"}
            or len(data) > 1024 * 1024
        ):
            raise ValueError("unsupported Gmail body alternative")
        markup = data.decode(charset)
        if _PLAIN_ALTERNATIVE_MARKUP.fullmatch(markup) is None or html_visible_text(
            markup
        )[0] != " ".join(body_text.split()):
            raise ValueError("Gmail HTML alternative changes the draft")
    files: list[MailFile] = []
    parts: list[bytes] = []
    total = 0
    for part in attachments:
        data = _leaf_payload(part, attachment=True)
        filename = _attachment_filename(part)
        total += len(data)
        if total > MAIL_MAX_BYTES:
            raise ValueError("Gmail attachment total exceeds bound")
        files.append(_describe_part(filename, part.get_content_type(), data))
        parts.append(data)
    return body_text, tuple(files), tuple(parts)


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


def workspace_raw(value: object) -> bytes:
    """Accept bounded RFC 822 text or Gmail's base64url representation of it."""
    if not isinstance(value, str) or len(value) > GMAIL_WRITE_POLICY.raw_bytes:
        raise ValueError("invalid raw mail")
    if "\n" in value:
        if len(value) > GMAIL_WRITE_POLICY.mime_bytes:
            raise ValueError("oversized raw mail")
        raw = value.encode()
        if len(raw) > GMAIL_WRITE_POLICY.mime_bytes:
            raise ValueError("oversized raw mail")
        return raw
    if len(value) > 4 * ((GMAIL_WRITE_POLICY.mime_bytes + 2) // 3):
        raise ValueError("oversized raw mail")
    return decode_raw(value)


def workspace_draft_content(
    message: MIMEPart,
    account: str,
    *,
    editor: bool = False,
) -> tuple[GmailSnapshot, tuple[bytes, ...]]:
    """Return only a plain envelope that the public create_draft can reproduce."""
    normal_headers = {
        "from",
        "to",
        "cc",
        "bcc",
        "subject",
        "in-reply-to",
        "references",
        "message-id",
        "date",
        "received",
        "mime-version",
        "content-type",
        "content-transfer-encoding",
    }
    if any(name.lower() not in normal_headers for name in message):
        raise ValueError("draft has headers outside the composition schema")
    for part in message.walk():
        if part is not message and any(
            name.lower()
            not in {
                "content-type",
                "mime-version",
                "content-transfer-encoding",
                "content-disposition",
            }
            for name in part
        ):
            raise ValueError("unsupported draft part headers")
        attachment = part.get_content_disposition() == "attachment"
        if attachment:
            if canonical_media_type(part.get_content_type()) != part.get_content_type():
                raise ValueError("unsupported attachment media type")
            name_parameter = part.get_param("name")
            if name_parameter is not None and name_parameter != _attachment_filename(
                part
            ):
                raise ValueError("attachment filenames conflict")
        content_params = {"name"} if attachment else {"charset", "boundary"}
        if part.get_content_type() == "text/plain" and part.get_param("format") in {
            "fixed",
            "flowed",
        }:
            content_params.add("format")
        for name, allowed in (
            ("content-type", content_params),
            ("content-disposition", {"filename"}),
        ):
            parameters = part.get_params(header=name) or []
            if any(key.lower() not in allowed for key, _ in parameters[1:]):
                raise ValueError("unsupported draft mime parameter")
    body, files, parts = _plain_parts(message)
    return _envelope_snapshot(message, account, body, files, editor), parts


def workspace_draft_snapshot(
    message: MIMEPart, snapshot: GmailSnapshot
) -> DraftSnapshot:
    (sender,) = _mailboxes(message, "From")
    return DraftSnapshot.model_validate(
        {
            **snapshot.model_dump(
                include={"subject", "to", "cc", "bcc", "body_text", "files"}
            ),
            "sender": sender.model_dump(),
        }
    )


@dataclass(frozen=True, slots=True)
class WorkspaceReplyParent:
    rfc_id: str
    subject: str
    references: tuple[str, ...]
    quote: str | None


def workspace_reply_parent(raw: bytes) -> WorkspaceReplyParent:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    ids = _message_ids(_header(message, "Message-ID") or "")
    subject = _header(message, "Subject")
    if message.defects or len(ids) != 1 or subject is None:
        raise ValueError("invalid reply parent")
    chain = _message_ids(_header(message, "References") or "")
    references = (*tuple(item for item in chain if item != ids[0]), ids[0])
    _message_ids(" ".join(references))
    quote_text = None
    body = message.get_body(preferencelist=("plain",))
    if body is not None and body.get_content_type() == "text/plain":
        try:
            data = _leaf_payload(body, attachment=False)
            if len(data) <= 100_000:
                plain = _body(data.decode(body.get_content_charset() or "ascii"))
                if plain:
                    quote_text = "\n\n" + "\n".join(
                        "> " + line for line in plain.split("\n")
                    )
        except (ValueError, LookupError):
            pass
    return WorkspaceReplyParent(ids[0], subject, references, quote_text)


def reply_subject_matches(subject: str, parent: str) -> bool:
    return _REPLY_PREFIX.sub("", subject) == _REPLY_PREFIX.sub("", parent)

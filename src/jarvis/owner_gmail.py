"""The human client's fixed, same-draft Gmail REST operations and MIME codec."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from email import policy
from email.errors import MessageError
from email.header import Header
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Literal, cast
from urllib.parse import quote
from uuid import UUID

import httpx
from llm_tools import canonical_json_bytes

from jarvis.connectors import (
    GoogleCredentialDefect,
    GoogleTokenManager,
    provider_array,
    provider_json_body,
    provider_object,
    provider_string,
)
from jarvis.gmail_drafts import (
    EditorSnapshot,
    decode_raw,
    provider_id,
    provider_labels,
    workspace_draft_content,
)
from jarvis.mail_files import MAIL_MAX_BYTES, MAIL_MAX_FILES, MailFile
from jarvis.read_tools import ConnectorFailure
from jarvis.workspace_enrollment import OWNER_DRAFT_SCOPES, WorkspaceEnrollment
from jarvis.workspace_mcp import WorkspaceError
from jarvis.write_tools import GMAIL_WRITE_POLICY, Mailbox

_API = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
_UPLOAD = "https://gmail.googleapis.com/upload/gmail/v1/users/me/drafts"
_MIME_ERRORS = (ValueError, TypeError, UnicodeError, MessageError, LookupError)


class MailError(Exception):
    """Only classified, content-free facts cross the home API boundary."""

    def __init__(
        self,
        reason: str,
        *,
        uncertain: bool = False,
        acknowledged_id: str | None = None,
        retry_after: str | None = None,
    ):
        super().__init__(reason)
        self.reason = reason
        self.uncertain = uncertain
        self.acknowledged_id = acknowledged_id
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class OwnerDraft:
    account: str
    draft_id: str
    thread_id: str | None
    quote: str | None = None


@dataclass(frozen=True, slots=True)
class LiveDraft:
    target: OwnerDraft
    workspace_grant: UUID
    account: str
    message_id: str
    raw_digest: str
    thread_id: str
    sender: Mailbox
    to: tuple[Mailbox, ...]
    cc: tuple[Mailbox, ...]
    bcc: tuple[Mailbox, ...]
    subject: str
    body: str = field(repr=False)
    quote: str | None = field(repr=False)
    in_reply_to: str | None
    references: tuple[str, ...]
    files: tuple[MailFile, ...]
    parts: tuple[bytes, ...] = field(repr=False)
    semantic_digest: str

    @property
    def threaded(self) -> bool:
        return self.in_reply_to is not None


@dataclass(frozen=True, slots=True)
class PreparedMail:
    target: OwnerDraft
    workspace_grant: UUID
    thread_id: str
    base_message_id: str
    send: bool
    mime: bytes = field(repr=False)
    semantic_digest: str


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _semantic(snapshot: EditorSnapshot, thread_id: str) -> str:
    return _digest(
        canonical_json_bytes(
            ["owner-mail-v1", thread_id, snapshot.model_dump(mode="json")]
        )
    )


def _decode(
    target: OwnerDraft, workspace_grant: UUID, payload: dict[str, object]
) -> LiveDraft:
    nested = payload.get("message")
    if not isinstance(nested, dict) or payload.get("id") != target.draft_id:
        raise MailError("provider_error")
    nested = cast(dict[str, object], nested)
    message_id = provider_id(nested, "id")
    thread_id = provider_id(nested, "threadId")
    if target.thread_id is not None and thread_id != target.thread_id:
        raise MailError("draft_changed")
    labels = provider_labels(nested)
    if "DRAFT" not in labels or labels.intersection({"SENT", "TRASH"}):
        raise MailError("draft_changed")
    try:
        raw = decode_raw(nested.get("raw"))
        message = BytesParser(policy=policy.default).parsebytes(raw)
        snapshot, parts = workspace_draft_content(message, target.account, editor=True)
        if not isinstance(snapshot, EditorSnapshot):
            raise ValueError("invalid owner draft representation")
        if any(
            len(message.get_all(header, [])) > 1 for header in ("Date", "Message-ID")
        ):
            raise ValueError("ambiguous draft header")
    except _MIME_ERRORS:
        raise MailError("unrepresentable_draft_mime") from None
    body = snapshot.body_text
    suffix = target.quote if target.quote and body.endswith(target.quote) else None
    return LiveDraft(
        target=target,
        workspace_grant=workspace_grant,
        account=snapshot.sender,
        message_id=message_id,
        raw_digest=_digest(raw),
        thread_id=thread_id,
        sender=Mailbox(name=snapshot.sender_name, address=snapshot.sender),
        to=snapshot.to,
        cc=snapshot.cc,
        bcc=snapshot.bcc,
        subject=snapshot.subject,
        body=body.removesuffix(suffix) if suffix else body,
        quote=suffix,
        in_reply_to=snapshot.in_reply_to,
        references=snapshot.references,
        files=snapshot.files,
        parts=parts,
        semantic_digest=_semantic(snapshot, thread_id),
    )


def prepare(
    live: LiveDraft,
    *,
    to: tuple[Mailbox, ...],
    cc: tuple[Mailbox, ...],
    bcc: tuple[Mailbox, ...],
    subject: str,
    body: str,
    files: tuple[tuple[MailFile, bytes], ...],
    send: bool,
) -> PreparedMail:
    if live.threaded and subject != live.subject:
        raise MailError("invalid_reply_subject")
    if send and not (to or cc or bcc):
        raise MailError("invalid_envelope")
    if (
        len(files) > MAIL_MAX_FILES
        or sum(len(data) for _, data in files) > MAIL_MAX_BYTES
    ):
        raise MailError("too_large")
    try:
        desired = EditorSnapshot(
            sender=live.sender.address,
            sender_name=live.sender.name,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body.replace("\r\n", "\n").replace("\r", "\n")
            + (live.quote or ""),
            in_reply_to=live.in_reply_to,
            references=live.references,
            files=tuple(file for file, _ in files),
        )
        message = EmailMessage(policy=policy.SMTP.clone(refold_source="none"))
        for key, recipients in (
            ("From", (live.sender,)),
            ("To", to),
            ("Cc", cc),
            ("Bcc", bcc),
        ):
            if not recipients:
                continue
            values: list[str] = []
            for mailbox in recipients:
                local, _, domain = mailbox.address.rpartition("@")
                addr = Address(username=local, domain=domain)
                if mailbox.name:
                    name = Header(
                        mailbox.name, charset="utf-8", header_name=key
                    ).encode(linesep="\r\n")
                    values.append(f"{name} <{addr.addr_spec}>")
                else:
                    values.append(addr.addr_spec)
            message.set_raw(key, ",\r\n ".join(values))
        message.set_raw(
            "Subject",
            Header(subject, charset="utf-8", header_name="Subject").encode(
                linesep="\r\n"
            ),
        )
        if live.in_reply_to is not None:
            message["In-Reply-To"] = live.in_reply_to
        if live.references:
            message["References"] = " ".join(live.references)
        message.set_content(
            desired.body_text.encode(),
            maintype="text",
            subtype="plain",
            cte="base64",
            params={"charset": "utf-8"},
        )
        for file, data in files:
            if file.size_bytes != len(data) or file.sha256 != _digest(data):
                raise MailError("invalid_file")
            maintype, subtype = file.media_type.split("/", 1)
            message.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=file.filename
            )
        mime = message.as_bytes()
        if len(mime) > GMAIL_WRITE_POLICY.mime_bytes:
            raise MailError("too_large")
        # The email encoder can refold headers, filenames and display names.
        # Refuse any loss before sending, including in unmodified retained parts.
        observed, _ = workspace_draft_content(
            BytesParser(policy=policy.default).parsebytes(mime),
            live.account,
            editor=True,
        )
        if observed != desired:
            raise MailError("invalid_envelope")
    except _MIME_ERRORS:
        raise MailError("invalid_envelope") from None
    return PreparedMail(
        live.target,
        live.workspace_grant,
        live.thread_id,
        live.message_id,
        send,
        mime,
        _semantic(desired, live.thread_id),
    )


class OwnerGmail:
    def __init__(
        self,
        http: httpx.AsyncClient,
        human: GoogleTokenManager,
        workspace_identity: Callable[[], WorkspaceEnrollment | None],
    ):
        if human.human_product != "gmail":
            raise ValueError("owner draft adapter requires a standard mail client")
        self._http = http
        self._human = human
        self._workspace = workspace_identity

    def _identity(self, target: OwnerDraft) -> tuple[WorkspaceEnrollment, UUID]:
        try:
            human = self._human.enrollment()
            workspace = self._workspace()
        except (GoogleCredentialDefect, WorkspaceError, OSError, ValueError):
            raise MailError("reconnect_required") from None
        if (
            human is None
            or workspace is None
            or human.scopes != OWNER_DRAFT_SCOPES
            or human.subject != workspace.subject
            or human.account.casefold() != workspace.account.casefold()
            or human.account.casefold() != target.account.casefold()
        ):
            raise MailError("reconnect_required")
        return human, workspace.grant_id

    def identity(self, target: OwnerDraft) -> WorkspaceEnrollment:
        return self._identity(target)[0]

    def require_current(
        self, target: OwnerDraft, grant_id: UUID, workspace_grant: UUID
    ) -> None:
        human, workspace = self._identity(target)
        if human.grant_id != grant_id or workspace != workspace_grant:
            raise MailError("reconnect_required")

    async def _token(self, grant_id: UUID, rejected: str | None = None) -> str:
        try:
            return (await self._human.credential(grant_id, rejected)).access_token
        except (GoogleCredentialDefect, OSError, ValueError):
            raise MailError("reconnect_required") from None
        except WorkspaceError as exc:
            reason = {"rate_limited": "rate_limited", "temporary": "temporary"}.get(
                exc.kind, "reconnect_required"
            )
            raise MailError(reason) from None

    async def _request(
        self,
        method: Literal["GET", "PUT", "POST"],
        url: str,
        token: str,
        *,
        params: dict[str, str],
        content_type: str | None = None,
        content: bytes | None = None,
    ) -> dict[str, object]:
        writing = method != "GET"
        limit = (
            GMAIL_WRITE_POLICY.metadata_bytes
            if writing
            else GMAIL_WRITE_POLICY.raw_bytes
        )
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            async with (
                asyncio.timeout(60),
                self._http.stream(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    content=content,
                    follow_redirects=False,
                    timeout=httpx.Timeout(60, connect=5),
                ) as response,
            ):
                status = response.status_code
                if status == 401:
                    raise MailError("reconnect_required")
                if status == 429:
                    raise MailError(
                        "rate_limited", retry_after=response.headers.get("Retry-After")
                    )
                if status == 404:
                    raise MailError("draft_missing")
                if status in {400, 413, 422}:
                    raise MailError(
                        "too_large" if status == 413 else "invalid_envelope"
                    )
                if status not in {200, 403}:
                    raise MailError("temporary", uncertain=writing)
                try:
                    result = await provider_json_body(
                        response,
                        attempts=1,
                        maximum=limit
                        if status == 200
                        else GMAIL_WRITE_POLICY.metadata_bytes,
                    )
                except ConnectorFailure as exc:
                    if status == 403:
                        raise MailError("permission_denied") from None
                    reason = (
                        "too_large"
                        if exc.code == "provider_response_too_large"
                        else "provider_error"
                    )
                    raise MailError(reason, uncertain=writing) from None
                if status == 403:
                    # Gmail also returns some quota rejections as 403.
                    try:
                        error = provider_object(result.get("error"), "error")
                        details = provider_array(error.get("errors"), "errors")
                        reasons: set[str] = {
                            provider_string(provider_object(item, "detail"), "reason")
                            for item in details
                        }
                    except ValueError:
                        reasons = set()
                    if reasons.intersection(
                        {
                            "rateLimitExceeded",
                            "userRateLimitExceeded",
                            "dailyLimitExceeded",
                        }
                    ):
                        raise MailError(
                            "rate_limited",
                            retry_after=response.headers.get("Retry-After"),
                        )
                    raise MailError("permission_denied")
                return result
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise MailError("temporary") from None
        except (httpx.HTTPError, TimeoutError, OSError):
            raise MailError("temporary", uncertain=writing) from None
        except (UnicodeError, ValueError, RecursionError):
            raise MailError("provider_error", uncertain=writing) from None

    async def read(self, target: OwnerDraft, grant_id: UUID) -> LiveDraft:
        human, workspace = self._identity(target)
        if human.grant_id != grant_id:
            raise MailError("reconnect_required")
        path = _draft_path(target)
        rejected = None
        while True:
            token = await self._token(grant_id, rejected)
            self.require_current(target, grant_id, workspace)
            try:
                result = await self._request(
                    "GET",
                    f"{_API}/{path}",
                    token,
                    params={
                        "format": "raw",
                        "fields": "id,message(id,threadId,labelIds,raw)",
                    },
                )
                break
            except MailError as exc:
                self.require_current(target, grant_id, workspace)
                if exc.reason != "reconnect_required" or rejected is not None:
                    raise
                rejected = token
        try:
            live = await asyncio.to_thread(_decode, target, workspace, result)
        except (ValueError, TypeError):
            raise MailError("provider_error") from None
        self.require_current(target, grant_id, workspace)
        return live

    async def write(
        self, target: OwnerDraft, grant_id: UUID, prepared: PreparedMail, *, send: bool
    ) -> str:
        if target != prepared.target or send != prepared.send:
            raise MailError("draft_changed")
        path = _draft_path(target)
        metadata = canonical_json_bytes(
            {"id": target.draft_id, "message": {"threadId": prepared.thread_id}}
        )
        boundary = "jarvis-" + secrets.token_hex(16)
        payload = (
            f"--{boundary}\r\n".encode()
            + b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: message/rfc822\r\n\r\n".encode()
            + prepared.mime
            + f"\r\n--{boundary}--\r\n".encode()
        )
        if len(payload) > 36 * 1024 * 1024:
            raise MailError("too_large")
        token = await self._token(grant_id)
        self.require_current(target, grant_id, prepared.workspace_grant)
        result = await self._request(
            "POST" if send else "PUT",
            f"{_UPLOAD}/send" if send else f"{_UPLOAD}/{path}",
            token,
            params={
                "uploadType": "multipart",
                "fields": "id,threadId,labelIds"
                if send
                else "id,message(id,threadId,labelIds)",
            },
            content_type=f"multipart/related; boundary={boundary}",
            content=payload,
        )
        msg = result if send else result.get("message")
        if not isinstance(msg, dict):
            raise MailError("provider_error", uncertain=True)
        msg = cast(dict[str, object], msg)
        try:
            accepted = provider_id(msg, "id")
        except ValueError:
            raise MailError("provider_error", uncertain=True) from None
        try:
            labels: frozenset[str] = provider_labels(msg)
        except ValueError:
            labels = frozenset()
        if (
            (send and accepted == prepared.base_message_id)
            or msg.get("threadId") != prepared.thread_id
            or ("SENT" if send else "DRAFT") not in labels
            or ("DRAFT" if send else "SENT") in labels
            or "TRASH" in labels
            or (not send and result.get("id") != target.draft_id)
        ):
            raise MailError("provider_error", uncertain=True, acknowledged_id=accepted)
        return accepted


def _draft_path(target: OwnerDraft) -> str:
    if (
        not target.draft_id
        or target.draft_id in {".", ".."}
        or len(target.draft_id.encode()) > 1024
    ):
        raise MailError("draft_changed")
    return quote(target.draft_id, safe="")

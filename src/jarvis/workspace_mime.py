"""Project bounded Workspace RAW results into headers, MIME parts and originals."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from email import policy
from email.message import MIMEPart
from email.parser import BytesParser

from llm_tools import canonical_json_bytes
from llm_tools.content import html_visible_text

from jarvis.connectors import OriginalTooLarge, decode_gmail_body
from jarvis.read_tools import ATTACHMENT_MAX_BYTES, display_descriptor


@dataclass(frozen=True)
class MailPart:
    selector: str
    filename: str | None
    media_type: str
    charset: str | None
    content: bytes | None = field(repr=False)
    is_file: bool
    issue: str | None

    def describe(self) -> dict[str, object]:
        desc = display_descriptor(
            self.filename,
            self.media_type,
            None if self.content is None else len(self.content),
        )
        return {
            "part_id": self.selector,
            "filename": desc["name"],
            "filename_truncated": desc["name_truncated"],
            "media_type": self.media_type,
            "size": desc["advertised_size"],
            "is_file": self.is_file,
            "issue": self.issue,
        }

    def text(self, readable: bool) -> str:
        if self.content is None or not self.media_type.startswith("text/"):
            raise ValueError("selected part has no supported text")
        value = self.content.decode(self.charset or "us-ascii", errors="strict")
        if readable and self.media_type == "text/html":
            value, _ = html_visible_text(value)
        return value


@dataclass(frozen=True)
class Mail:
    headers: list[dict[str, str]]
    parts: tuple[MailPart, ...]
    partial: bool


def parse_mail(
    raw: object, identity: tuple[str, ...], draft_id: str | None = None
) -> Mail:
    if not isinstance(raw, str) or not raw:
        raise ValueError("raw message missing")
    if "\n" in raw and ":" in raw.partition("\n")[0]:
        # Some servers return the RFC message itself. Preserve its line endings.
        if (
            len(raw) > ATTACHMENT_MAX_BYTES
            or sum(
                len(raw[i : i + 65536].encode("utf-8"))
                for i in range(0, len(raw), 65536)
            )
            > ATTACHMENT_MAX_BYTES
        ):
            raise OriginalTooLarge
        content = raw.encode("utf-8")
    else:
        content = decode_gmail_body(raw)
    parsed = BytesParser(policy=policy.default).parsebytes(content)
    if not tuple(parsed.keys()):
        raise ValueError("invalid raw message")
    headers = [{"name": k, "value": str(v)} for k, v in parsed.items()]
    prefix = "mime1."
    if draft_id is not None:
        encoded = base64.urlsafe_b64encode(draft_id.encode()).decode().rstrip("=")
        prefix += f"d{encoded}."
    parts: list[MailPart] = []
    partial = False
    stack: list[tuple[str, MIMEPart]] = [("0", parsed)]
    while stack:
        path, part = stack.pop()
        if len(path) > 256 or len(parts) + len(stack) > 8192:
            raise ValueError("mime structure exceeds supported bounds")
        kind = part.get_content_type()
        if part.is_multipart() and kind.startswith("multipart/"):
            partial |= bool(part.defects)
            children = list(part.iter_parts())
            stack.extend(
                (f"{path}.{i}", child)
                for i, child in reversed(list(enumerate(children)))
            )
            continue
        filename = part.get_filename()
        is_file = (
            bool(filename)
            or part.get_content_disposition() == "attachment"
            or not kind.startswith("text/")
        )
        transfer = str(part.get("Content-Transfer-Encoding", "7bit")).strip().lower()
        data = part.get_payload(decode=True)
        usable = (
            isinstance(data, bytes)
            and not part.defects
            and transfer
            in {
                "base64",
                "quoted-printable",
                "7bit",
                "8bit",
                "binary",
            }
        )
        issue = None if usable else "unsupported_or_malformed_part"
        data = data if isinstance(data, bytes) and usable else None
        partial |= issue is not None
        digest = hashlib.sha256(
            canonical_json_bytes(
                [
                    *identity,
                    path,
                    kind,
                    filename,
                    hashlib.sha256(data).hexdigest() if data is not None else None,
                ]
            )
        ).hexdigest()
        selector = f"{prefix}{path}.{digest}"
        if len(selector) > 1024:
            raise ValueError("MIME selector exceeds source reference bound")
        parts.append(
            MailPart(
                selector,
                filename,
                kind,
                part.get_content_charset(),
                data,
                is_file,
                issue,
            )
        )
    return Mail(headers, tuple(parts), partial)

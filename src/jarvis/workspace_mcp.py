"""Host-owned Google Workspace transport and transient owner challenges."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mmap
import re
import tempfile
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterator,
    Mapping,
)
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
    contextmanager,
    nullcontext,
)
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import BinaryIO, Literal, cast
from uuid import UUID, uuid4

import httpx

from jarvis._secrets import contains_secret
from jarvis._thread_io import joined_thread
from jarvis.home_refs import (
    DRIVE_ID_PATTERN,
    DRIVE_MIME_PATTERN,
    DRIVE_STRONG_ETAG_PATTERN,
)
from jarvis.read_tools import ATTACHMENT_MAX_BYTES

Product = Literal["gmail", "calendar", "drive", "docs"]
Obj = dict[str, object]
Audit = Callable[[Obj], Awaitable[None]]
Fence = Callable[[], Awaitable[None]]
DriveScratch = Callable[[int], AbstractAsyncContextManager[Path]]
PROTOCOL_VERSION = "2026-07-28"
HUMAN_WAIT_SECONDS = 120
MAX_CONSENT_ROUNDS = 3
WORKSPACE_DRIVE_RPC_LIMIT = 96
_ORIGINS: dict[Product, str] = {
    "gmail": "https://gmailmcp.googleapis.com/mcp/v1",
    "calendar": "https://calendarmcp.googleapis.com/mcp/v1",
    "drive": "https://drivemcp.googleapis.com/mcp/v1",
}
_SCOPE_PREFIX = "https://www.googleapis.com/auth/"
_GMAIL = {
    "get_message": "gmail.messages.readonly",
    "get_thread": "gmail.messages.readonly",
    "search_threads": "gmail.messages.readonly",
    "create_draft": "gmail.drafts.create",
    "list_drafts": "gmail.drafts.readonly",
    "get_draft": "gmail.drafts.readonly",
    "list_labels": "gmail.labels.readonly",
    "unlabel_message": "gmail.messages.modify",
}
_CALENDAR = {
    "list_calendars": "calendar.calendarlist.readonly",
    "list_events": "calendar.events",
    "get_event": "calendar.events",
    "create_event": "calendar.events",
    "update_event": "calendar.events",
    "delete_event": "calendar.events",
}
_TOOL_SCOPES: dict[Product, dict[str, str]] = {
    "gmail": _GMAIL,
    "calendar": _CALENDAR,
    "drive": dict.fromkeys(
        (
            "search_files",
            "list_recent_files",
            "get_file_metadata",
            "get_file_permissions",
            "get_file_revision",
            "read_file_content",
            "download_file_content",
            "create_file",
            "copy_file",
            "upload_file_revision",
        ),
        "drive",
    ),
    "docs": dict.fromkeys(("get_document", "batch_update_document"), "drive"),
}
DRIVE_SCOPE = _SCOPE_PREFIX + "drive"
GMAIL_SCOPES = frozenset(_SCOPE_PREFIX + scope for scope in _GMAIL.values())
ARRIVAL_SCOPES = frozenset(
    _SCOPE_PREFIX + _GMAIL[k] for k in ("get_message", "list_labels", "unlabel_message")
)
CALENDAR_SCOPES = frozenset(_SCOPE_PREFIX + scope for scope in _CALENDAR.values())
SCOPES = GMAIL_SCOPES | CALENDAR_SCOPES
GMAIL_TOOL_WEIGHTS = {
    tool: 10 if tool in {"search_threads", "list_drafts"} else 1 for tool in _GMAIL
}
_WRITES = frozenset(
    {
        "unlabel_message",
        "create_draft",
        "create_event",
        "update_event",
        "delete_event",
        "create_file",
        "copy_file",
        "upload_file_revision",
        "batch_update_document",
    }
)
# November 24 public discovery. Pin wire structure and effect annotations,
# excluding descriptive prose. Schema changes disable only the affected tool.
_SCHEMA_PINS = {
    # November 26 public Drive discovery.
    "copy_file": "U49wDUMGv6ZikBRF1J3lJbSJZYyFCS5VybFdFYrw25E=",
    "create_file": "YGTrKZmNfnD9l1qOX+84GThM2AXjzuLhSBx8eNBexpU=",
    "download_file_content": "2P0v0m+mloEnDjI4XR5zZv5KP7o2dVnZrnxxkFoo3Fc=",
    "get_file_metadata": "W/JNKvlOxU+huD//7/WmoDaIrpNrtIeEOiCUCWhXJhY=",
    "get_file_permissions": "etjuVzNJT1suq34+Co4sDZ2iuYzNvjzsdHYswdGEYUI=",
    "list_recent_files": "E9KCT3tzqBz0l+cnhfLvfC/HQv1VZD3QNpImPJYSmt4=",
    "read_file_content": "2pkL+TJV5TmTAvFS17eYXqdYtpiQS22pvwa7A4h4vug=",
    "search_files": "7xfRKME8rSGEBzZXUYzVEzDBXLa9Fiyvl/UZaXzJ6io=",
    "create_draft": "qi/0Oj43f0JOEDc5erwM//wekiIomOwlET+h+H7JMNY=",
    "create_event": "YREPOYlfk8StMYhNPHI38xDz1DXt6SJR9WhgeP8Ee84=",
    "delete_event": "xJgwRu9dI5nVBWBy6fXnwMoJT8Gtlb0JstM6tdkFh40=",
    "get_draft": "xGO6XZNSdQcVNFsW74UN1HaRSSeow/up13IvxxAZ8mo=",
    "get_event": "zSt6VKWUi0ZP6m7t6Z4nM2yRjXiy+8hOO+DPxjZGNLA=",
    "get_message": "eEst/PhiHk+hbk8+nw0GUOroNs/B8fB/Uelruq1l1tM=",
    "get_thread": "oMs5CUYaM8sp+Huv7ncoDR4rnyjMH0llBQKxaTLKp20=",
    "list_calendars": "3CA90TJr/OPqaWr91HoASV8MImtI7siyjAhyydj+PTo=",
    "list_drafts": "N0yi0XiVbcwsByjlbIgWennSAvIj7qV7n0pv9vhqGmI=",
    "list_events": "AZBu7A2TSHMtP4rQxRKkjUymTZCvGzK2rjN6wcSXMsY=",
    "list_labels": "bJ4hYifIl2LTcGqy2g8q4ELjOZQJujwaN4Zf1tRur2o=",
    "search_threads": "t6TBynZXZ+XurmG66FYJKkRidu/MivFpEzYilcyIct4=",
    "unlabel_message": "Xv/XkaDptumHcsBY5R9TzvAfcv/79h2YgpsxWrNuecg=",
    "update_event": "zZWd9BmIzEbngYpa9JgIIcXd+mpaVKfgIULX0to5P5I=",
}
_CHOICES = frozenset(
    {
        "ALLOW_ONCE",
        "DENY_ONCE",
        "ALLOW_AUDIENCE_ALWAYS",
        "ALLOW_RESOURCE_ALWAYS",
        "ALLOW_OWNER_ALWAYS",
        "ALLOW_TOOL_ALWAYS",
    }
)
_METADATA_BYTES = 2 * 1024 * 1024
_MAX_REQUEST_BYTES = 36 * 1024 * 1024
_BINARY_CHUNK_BYTES = 3 * 65_536
_DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
_DRIVE_UPLOAD_PATH = "/upload/drive/v3/files"
_DRIVE_UPLOAD = f"https://www.googleapis.com{_DRIVE_UPLOAD_PATH}"
_DRIVE_REVISION_FIELDS = {
    "fields": "id,etag,headRevisionId",
    "supportsAllDrives": "true",
}


@dataclass(frozen=True, slots=True)
class WorkspaceRequest:
    product: Product
    operation: str
    grant_id: UUID
    target_key: str
    arrival_episode: UUID | None


def workspace_target_key(grant_id: UUID, arguments: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            (str(grant_id), dict(arguments)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


class WorkspaceError(Exception):
    """A classified observation with no provider prose, credentials or body."""

    def __init__(
        self,
        kind: str,
        *,
        retry_at: datetime | None = None,
        known_no_effect: bool = False,
    ):
        super().__init__(kind)
        self.kind = kind
        self.retry_at = retry_at
        self.known_no_effect = known_no_effect
        self.request: WorkspaceRequest | None = None


@dataclass(slots=True)
class WorkspaceAttempts:
    maximum: int | None
    seconds: float | None
    attempts: int = 0
    elapsed: float = 0.0
    reserved: int = 0
    human_elapsed: float = 0.0
    consent_rounds: int = 0


_attempt_limits: ContextVar[tuple[WorkspaceAttempts, ...]] = ContextVar(
    "workspace_attempt_limits", default=()
)


@contextmanager
def workspace_attempts(
    maximum: int | None,
    *,
    seconds: float | None = None,
    human_elapsed: float = 0.0,
    consent_rounds: int = 0,
) -> Iterator[WorkspaceAttempts]:
    """Bound provider exchanges and cumulative Google consent for one invocation."""
    if (
        (maximum is not None and maximum < 0)
        or (seconds is not None and seconds <= 0)
        or not 0 <= human_elapsed <= HUMAN_WAIT_SECONDS
        or type(consent_rounds) is not int
        or not 0 <= consent_rounds <= MAX_CONSENT_ROUNDS
    ):
        raise ValueError("invalid workspace request budget")
    meter = WorkspaceAttempts(
        maximum, seconds, human_elapsed=human_elapsed, consent_rounds=consent_rounds
    )
    reset = _attempt_limits.set((*_attempt_limits.get(), meter))
    try:
        yield meter
    finally:
        _attempt_limits.reset(reset)


@contextmanager
def _before_submission() -> Iterator[None]:
    """Failures here are known to precede the next Google tools/call."""
    try:
        yield
    except WorkspaceError:
        raise
    except asyncio.CancelledError:
        raise WorkspaceError("cancelled") from None
    except Exception:
        raise WorkspaceError("preflight_unavailable") from None


@asynccontextmanager
async def workspace_http_attempt(
    io_seconds: float,
    before_send: Fence | None = None,
    *,
    on_transmission: Callable[[], None] | None = None,
) -> AsyncIterator[None]:
    limits = _attempt_limits.get()
    if any(
        m.maximum is not None and m.attempts + m.reserved >= m.maximum for m in limits
    ):
        raise WorkspaceError("budget_exceeded")

    def remaining_io() -> float:
        remaining = min(
            (m.seconds - m.elapsed for m in limits if m.seconds is not None),
            default=io_seconds,
        )
        if remaining <= 0:
            raise WorkspaceError("budget_exceeded")
        return min(remaining, io_seconds)

    remaining = remaining_io()
    for meter in limits:
        meter.reserved += 1
    try:
        if before_send is not None:
            # A committed quota debit survives a later local refusal.
            with _before_submission():
                await before_send()
            # A fresh guard read can consume time within this same invocation.
            remaining = remaining_io()
    finally:
        for meter in limits:
            meter.reserved -= 1
    for meter in limits:
        meter.attempts += 1
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        async with asyncio.timeout(remaining):
            if on_transmission is not None:
                on_transmission()
            yield
    finally:
        elapsed = loop.time() - started
        for meter in limits:
            meter.elapsed += elapsed


@dataclass(frozen=True, slots=True)
class WorkspaceCredential:
    access_token: str = field(repr=False)
    scopes: frozenset[str]
    pending_label_id: str | None = None


def _obj(value: object) -> Obj:
    if not isinstance(value, dict):
        raise ValueError("expected object")
    return cast(Obj, value)


def _schema_shape(value: object) -> object:
    if isinstance(value, list):
        return [_schema_shape(item) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    return {
        key: (
            {name: _schema_shape(child) for name, child in _obj(item).items()}
            if key in {"properties", "$defs"}
            else _schema_shape(item)
        )
        for key, item in cast(Obj, value).items()
        if key not in {"description", "title", "x-google-enum-descriptions"}
    }


def _schema_pin(tool: Obj) -> str:
    shapes = [
        _schema_shape(tool.get(key, {}))
        for key in ("inputSchema", "outputSchema", "annotations")
    ]
    wire = json.dumps(shapes, sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(hashlib.sha256(wire).digest()).decode()


def _items(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return cast(list[object], value)


def _strings(value: object) -> list[str]:
    items = _items(value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError("expected strings")
    return cast(list[str], items)


# Content is displayed as inert evidence. Screen the visible prompt and
# decoded text separately from opaque transport bytes (MIME and attachments).
_INJECTION = re.compile(
    r"(?i)\b(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system|developer)"
    r"\s+(?:instructions?|prompts?)\b|\b(?:reveal|exfiltrate)\s+(?:the\s+)?"
    r"(?:system prompt|refresh token|access token|api key)\b"
)


def screen_workspace_content(value: object, secrets: tuple[str, ...] = ()) -> None:
    if isinstance(value, str):
        if contains_secret(value, secrets) or _INJECTION.search(value):
            raise WorkspaceError("screened")
    elif isinstance(value, dict):
        for key, item in cast(Obj, value).items():
            # The workflow verifies and screens decoded MIME at its point of use.
            if key not in {"raw", "content"} or not isinstance(item, str):
                screen_workspace_content(item, secrets)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            screen_workspace_content(item, secrets)


def _safe_prompt(value: object, *, limit: int) -> str:
    if not isinstance(value, str) or not 0 < len(value.encode()) <= limit:
        raise ValueError("invalid prompt")
    if any(
        (ord(c) < 32 and c not in "\n\t")
        or 127 <= ord(c) <= 159
        or 0x202A <= ord(c) <= 0x202E
        or 0x2066 <= ord(c) <= 0x2069
        for c in value
    ):
        raise ValueError("invalid prompt characters")
    return value


@dataclass(frozen=True, slots=True)
class _Form:
    prompt: str
    choices: tuple[tuple[str, str], ...]
    state: str = field(repr=False)

    @classmethod
    def parse(cls, result: Obj, token: str) -> _Form:
        requests = _obj(result["inputRequests"])
        if requests.keys() != {"approval_choice"}:
            raise ValueError("unsupported requests")
        request = _obj(requests["approval_choice"])
        params = _obj(request["params"])
        if (
            request.get("method") != "elicitation/create"
            or params.get("mode") != "form"
        ):
            raise ValueError("unsupported form")
        schema = _obj(params["requestedSchema"])
        properties = _obj(schema["properties"])
        if (
            schema.get("type") != "object"
            or schema.get("required") != ["approval_choice"]
            or properties.keys() != {"approval_choice"}
        ):
            raise ValueError("unsupported fields")
        field = _obj(properties["approval_choice"])
        values = _strings(field["enum"])
        labels = _strings(field["enumNames"])
        if (
            field.get("type") != "string"
            or len(values) != len(labels)
            or len(set(values)) != len(values)
            or not set(values) <= _CHOICES
            or not {"ALLOW_ONCE", "DENY_ONCE"} <= set(values)
        ):
            raise ValueError("unsupported choices")
        prompt = _safe_prompt(params["message"], limit=8192)
        question = _safe_prompt(field["title"], limit=1024)
        choices = tuple(
            (value, _safe_prompt(label, limit=256))
            for value, label in zip(values, labels, strict=True)
        )
        state = result.get("requestState")
        if not isinstance(state, str) or not 0 < len(state.encode()) <= 32768:
            raise ValueError("invalid request state")
        prompt = f"{prompt}\n\n{question}"
        screen_workspace_content([prompt, *labels], (token, state))
        return cls(prompt, choices, state)


@dataclass(slots=True)
class _Round:
    id: UUID
    grant_id: UUID
    invocation: str
    product: Product
    tool: str
    number: int
    form: _Form
    expires_at: datetime
    deadline: float
    answer: asyncio.Future[str | None]
    request: WorkspaceRequest | None
    visible: bool = False
    claimed: bool = False
    invalid: bool = False

    def display(self) -> Obj:
        return {
            "id": str(self.id),
            "product": self.product,
            "operation": self.tool,
            "prompt": self.form.prompt,
            "choices": [
                {"value": value, "label": label} for value, label in self.form.choices
            ],
            "expires_at": self.expires_at.isoformat(),
        }

    def fact(self, stage: str) -> Obj:
        return {
            "source": "workspace_consent",
            "stage": stage,
            "stage_key": f"workspace_consent:{self.id}:{stage}",
            "invocation_id": self.invocation,
            "round": self.number,
            "grant_id": str(self.grant_id),
            "product": self.product,
            "operation": self.tool,
            "approval_id": str(self.id),
            "observed_at": datetime.now(UTC).isoformat(),
            "target_key": None if self.request is None else self.request.target_key,
            "arrival_episode": None
            if self.request is None or self.request.arrival_episode is None
            else str(self.request.arrival_episode),
        }


class WorkspaceApprovals:
    """One visible challenge. Only the authenticated host invokes respond."""

    def __init__(self, *, audit: Audit):
        self._audit = audit
        self._round: _Round | None = None
        self._expired: UUID | None = None
        self._closed = False
        self.notify_released: Callable[[], None] = lambda: None
        self.provider_success: (
            Callable[[WorkspaceRequest, str], Awaitable[None]] | None
        ) = None

    def busy(self) -> bool:
        return self._round is not None

    def owns(self, round_id: str) -> bool:
        return self._round is not None and str(self._round.id) == round_id

    def pending(self) -> list[Obj]:
        current = self._round
        if (
            current is None
            or not current.visible
            or current.claimed
            or current.invalid
            or asyncio.get_running_loop().time() >= current.deadline
        ):
            return []
        return [current.display()]

    async def respond(self, id: UUID, choice: str | None, actor: str) -> int:
        current = self._round
        if current is None or current.id != id:
            return 410 if id == self._expired else 409
        if asyncio.get_running_loop().time() >= current.deadline:
            return 410
        if (
            not actor
            or not current.visible
            or current.claimed
            or current.invalid
            or (choice is not None and choice not in dict(current.form.choices))
        ):
            return 409
        current.claimed = True  # no await between checking and taking the round
        fact = current.fact("cancelled" if choice is None else "choice")
        fact.update(actor=actor, choice=choice)
        try:
            await self._audit(fact)
        except BaseException:
            self.invalidate(current.grant_id)
            raise
        if asyncio.get_running_loop().time() >= current.deadline:
            return 410
        if current.invalid or current.answer.done() or self._round is not current:
            return 409
        current.answer.set_result(choice)
        return 204

    def invalidate(
        self, grant_id: UUID, products: frozenset[Product] | None = None
    ) -> None:
        current = self._round
        if (
            current is not None
            and current.grant_id == grant_id
            and (products is None or current.product in products)
        ):
            current.invalid = True
            if not current.answer.done():
                current.answer.cancel()

    def interrupt(self) -> None:
        if self._round is not None:
            self.invalidate(self._round.grant_id)

    async def close(self) -> None:
        self._closed = True
        self.interrupt()

    async def ask(
        self,
        form: _Form,
        product: Product,
        tool: str,
        grant_id: UUID,
        invocation: str,
        request: WorkspaceRequest | None = None,
    ) -> str | None:
        if self._closed:
            raise WorkspaceError("cancelled")
        if self._round is not None:
            raise WorkspaceError("approval_busy")
        limits = _attempt_limits.get()
        number = 1 + max(m.consent_rounds for m in limits)
        remaining = HUMAN_WAIT_SECONDS - max(m.human_elapsed for m in limits)
        if number > MAX_CONSENT_ROUNDS or remaining <= 0:
            raise WorkspaceError("consent_expired")
        for meter in limits:
            meter.consent_rounds += 1
        loop = asyncio.get_running_loop()
        started = loop.time()
        current = _Round(
            uuid4(),
            grant_id,
            invocation,
            product,
            tool,
            number,
            form,
            datetime.now(UTC) + timedelta(seconds=remaining),
            started + remaining,
            loop.create_future(),
            request,
        )
        self._round = current
        try:
            async with asyncio.timeout_at(current.deadline):
                await self._audit(current.fact("presented") | current.display())
                if current.invalid:
                    raise WorkspaceError("cancelled")
                current.visible = True
                return await current.answer
        except TimeoutError:
            self._expired = current.id
            await self._audit(current.fact("expired"))
            raise WorkspaceError("consent_expired") from None
        except asyncio.CancelledError:
            await self._audit(current.fact("interrupted"))
            if current.invalid:
                raise WorkspaceError("cancelled") from None
            raise
        finally:
            elapsed = loop.time() - started
            for meter in limits:
                meter.human_elapsed = min(
                    HUMAN_WAIT_SECONDS, meter.human_elapsed + elapsed
                )
            self._round = None
            self.notify_released()


def _decode(data: bytes | bytearray | str) -> Obj:
    def distinct(pairs: list[tuple[str, object]]) -> Obj:
        result: Obj = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate json key")
            result[key] = value
        return result

    return _obj(json.loads(data, object_pairs_hook=distinct))


def _wire_result(body: bytearray, mime: str, id: str) -> Obj:
    if mime == "application/json":
        response = _decode(body)
    elif mime == "text/event-stream":
        response = None
        for event in re.split(r"\n\n+", body.decode("utf-8").replace("\r\n", "\n")):
            lines = [
                line[5:].removeprefix(" ")
                for line in event.split("\n")
                if line.startswith("data:")
            ]
            if lines:
                packet = _decode("\n".join(lines))
                if "method" in packet:
                    if packet.get("jsonrpc") != "2.0" or "id" in packet:
                        raise ValueError("invalid stream notification")
                    continue
                if response is not None:
                    raise ValueError("multiple responses")
                response = packet
        if response is None:
            raise ValueError("missing stream response")
    else:
        raise ValueError("unexpected MIME type")
    if (
        response.get("jsonrpc") != "2.0"
        or response.get("id") != id
        or ("error" in response) == ("result" in response)
    ):
        raise ValueError("mismatched response")
    return response


# A large JSON string is an owned wire span until the parsed MCP envelope binds it
# to FileContent.content or its one JSON text presentation. Quotes inside strings
# are never structural. Everything outside the spans uses the ordinary MCP parser.
_STRING_BOUNDARY = re.compile(rb'["\\]')
_LITERAL_BYTES = 65_536
type _Span = tuple[int, int]


def _bounded_envelope(mapped: mmap.mmap) -> tuple[bytearray, dict[str, _Span]]:
    metadata = bytearray()
    spans: dict[str, _Span] = {}
    offset = cursor = 0
    while (opened := mapped.find(b'"', cursor)) != -1:
        start = cursor = opened + 1
        while True:
            boundary = _STRING_BOUNDARY.search(mapped, cursor)
            if boundary is None:
                raise ValueError("unterminated json string")
            if boundary[0] == b'"':
                end = boundary.start()
                cursor = end + 1
                break
            cursor = boundary.end() + 1
        if end - start <= _LITERAL_BYTES:
            continue
        if len(spans) == 2 or len(metadata) + start - offset > _METADATA_BYTES:
            raise ValueError("oversize drive download envelope")
        marker = f"!drive-binary-{uuid4()}!"
        spans[marker] = (start, end)
        metadata.extend(mapped[offset:start])
        metadata.extend(marker.encode("ascii"))
        offset = end
    if len(metadata) + len(mapped) - offset > _METADATA_BYTES:
        raise ValueError("oversize drive download envelope")
    metadata.extend(mapped[offset:])
    return metadata, spans


def _literal_bytes(mapped: mmap.mmap, span: _Span) -> Iterator[bytes]:
    offset, end = span
    while offset < end:
        limit = min(end, offset + _BINARY_CHUNK_BYTES)
        slash = mapped.find(b"\\", offset, limit)
        if slash < 0:
            yield mapped[offset:limit]
            offset = limit
            continue
        if slash > offset:
            yield mapped[offset:slash]
        finish = slash + (6 if mapped[slash + 1 : slash + 2] == b"u" else 2)
        if finish > end:
            raise ValueError("truncated json escape")
        escape = mapped[slash:finish]
        if len(escape) == 6 and 0xD800 <= int(escape[2:], 16) <= 0xDBFF:
            if mapped[finish : finish + 2] != b"\\u" or finish + 6 > end:
                raise ValueError("unpaired json surrogate")
            finish += 6
            escape = mapped[slash:finish]
        value = cast(str, json.loads(b'"' + escape + b'"'))
        yield value.encode("utf-8")
        offset = finish


def _decode_drive_content(
    payload: Obj,
    mapped: mmap.mmap,
    spans: dict[str, _Span],
    maximum: int,
    destination: BinaryIO | None,
) -> Obj:
    file = {key: payload[key] for key in ("id", "title", "mimeType")}
    if not all(isinstance(value, str) for value in file.values()):
        raise ValueError("invalid drive download metadata")
    content = payload["content"]
    if not isinstance(content, str):
        raise ValueError("invalid drive binary content")
    span = spans.pop(content, None)
    pieces = (
        _literal_bytes(mapped, span)
        if span is not None
        else iter((content.encode("ascii"),))
    )
    if destination is not None:
        destination.seek(0)
        destination.truncate()
    digest = hashlib.sha256()
    size = 0
    carry = b""
    padded = False
    for piece in pieces:
        if padded and piece:
            raise ValueError("premature base64 padding")
        word = carry + piece
        end = len(word) - len(word) % 4
        carry = word[end:]
        if not end:
            continue
        encoded = word if end == len(word) else word[:end]
        padded = b"=" in encoded
        if padded and carry:
            raise ValueError("premature base64 padding")
        data = base64.b64decode(encoded, validate=True)
        size += len(data)
        if size > maximum:
            raise WorkspaceError("too_large")
        digest.update(data)
        if destination is not None:
            destination.write(data)
    if carry:
        raise ValueError("incomplete base64 quartet")
    if destination is not None:
        destination.flush()
        destination.seek(0)
    return file | {"size": size, "sha256": digest.hexdigest()}


def _download_envelope(
    wire: BinaryIO,
    mime: str,
    id: str,
    destination: BinaryIO,
    maximum: int,
    directory: Path | None = None,
) -> Obj:
    with mmap.mmap(wire.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        metadata, spans = _bounded_envelope(mapped)
        packet = _wire_result(metadata, mime, id)
        result = _obj(packet.get("result", {}))
        if (
            result.get("resultType") != "complete"
            or result.get("isError", False) is not False
            or result.get("truncated", False) is not False
            or result.get("isTruncated", False) is not False
        ):
            if spans:
                raise ValueError("oversize drive error or challenge")
            return packet
        normalized = None
        if "structuredContent" in result:
            normalized = _decode_drive_content(
                _obj(result["structuredContent"]),
                mapped,
                spans,
                maximum,
                destination,
            )
        parts = _items(result.get("content", []))
        if parts:
            if len(parts) != 1:
                raise ValueError("drive download needs one binary content block")
            block = _obj(parts[0])
            text = block.get("text")
            if block.get("type") != "text" or not isinstance(text, str):
                raise ValueError("drive download needs JSON text")
            target = destination if normalized is None else None
            outer = spans.pop(text, None)
            if outer is None:
                observed = _decode_drive_content(
                    _decode(text), mapped, {}, maximum, target
                )
            else:
                with tempfile.TemporaryFile(dir=directory) as inner:
                    length = 0
                    cap = _METADATA_BYTES + 4 * ((maximum + 2) // 3)
                    for piece in _literal_bytes(mapped, outer):
                        length += len(piece)
                        if length > cap:
                            raise WorkspaceError("too_large")
                        inner.write(piece)
                    inner.flush()
                    with mmap.mmap(inner.fileno(), 0, access=mmap.ACCESS_READ) as local:
                        inner_metadata, inner_spans = _bounded_envelope(local)
                        observed = _decode_drive_content(
                            _decode(inner_metadata),
                            local,
                            inner_spans,
                            maximum,
                            target,
                        )
                        if inner_spans:
                            raise ValueError(
                                "unexpected large string in drive file metadata"
                            )
            if normalized is not None and observed != normalized:
                raise ValueError("drive download representations disagree")
            normalized = observed
        if normalized is None or spans:
            raise ValueError("invalid drive download envelope")
        packet["result"] = {"resultType": "complete", "structuredContent": normalized}
        return packet


def workspace_retry_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.isdecimal():
            return datetime.now(UTC) + timedelta(seconds=int(value))
        when = parsedate_to_datetime(value)
        return when.astimezone(UTC) if when.tzinfo else None
    except (OverflowError, ValueError, TypeError):
        return None


class _Unauthorized(Exception):
    pass


async def _upload_chunks(path: Path, size: int) -> AsyncIterator[bytes]:
    with path.open("rb") as data:
        remaining = size
        while remaining:
            requested = min(remaining, _BINARY_CHUNK_BYTES)
            piece = await joined_thread(data.read, requested)
            if len(piece) != requested:
                raise OSError("drive upload source changed")
            remaining -= len(piece)
            yield piece
        if await joined_thread(data.read, 1):
            raise OSError("drive upload source changed")


def _identity_length(response: httpx.Response) -> int | None:
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise ValueError("unsupported response encoding")
    length = response.headers.get("Content-Length")
    if length is None:
        return None
    if not length.isdecimal():
        raise ValueError("invalid content length")
    return int(length)


def _response_mime(response: httpx.Response) -> str:
    return response.headers.get("Content-Type", "").partition(";")[0].strip().lower()


async def _bounded_body(
    chunks: AsyncIterable[bytes], limit: int, length: int | None, oversize: Exception
) -> bytearray:
    if length is not None and length > limit:
        raise oversize
    body = bytearray()
    async for chunk in chunks:
        if len(body) + len(chunk) > limit:
            raise oversize
        body.extend(chunk)
    if length is not None and len(body) != length:
        raise ValueError("truncated reply")
    return body


async def _drive_rest_json(response: httpx.Response) -> Obj:
    if _response_mime(response) != "application/json" or not isinstance(
        response.stream, httpx.AsyncByteStream
    ):
        raise ValueError("invalid Drive JSON response")
    # Read the identity stream to EOF. The surrounding response context owns
    # close, so a complete acknowledgement can be validated before teardown.
    return _decode(
        await _bounded_body(
            response.stream,
            _METADATA_BYTES,
            _identity_length(response),
            ValueError("oversize Drive JSON response"),
        )
    )


def _drive_rest_status(
    response: httpx.Response, *success: int, finalizing: bool = False
) -> None:
    status = response.status_code
    if status in success:
        return
    retry = workspace_retry_at(response.headers.get("Retry-After"))
    if finalizing:
        raise WorkspaceError("uncertain", retry_at=retry)
    if status == 401:
        raise _Unauthorized
    if status == 429:
        raise WorkspaceError("rate_limited", retry_at=retry)
    if status == 403:
        raise WorkspaceError("denied")
    if status == 404:
        raise WorkspaceError("not_found")
    raise WorkspaceError("temporary" if status >= 500 else "invalid_response")


def _file_etag(value: object) -> str | None:
    if (
        isinstance(value, str)
        and len(value) <= 1024
        and re.fullmatch(DRIVE_STRONG_ETAG_PATTERN, value)
    ):
        return value
    return None


def _file_revision(result: Obj, file_id: str) -> tuple[str | None, str | None]:
    if result.get("id") != file_id:
        raise ValueError("mismatched Drive file identity")
    head = result.get("headRevisionId")
    if (
        not isinstance(head, str)
        or not 0 < len(head.encode()) <= 1024
        or any(character.isspace() or ord(character) < 32 for character in head)
    ):
        head = None
    return _file_etag(result.get("etag")), head


def _provider_error(
    error: Obj, product: Product, write: bool, retry: datetime | None
) -> WorkspaceError:
    reasons: set[str] = set()
    for detail in _items(error.get("details", [])):
        reason = _obj(detail).get("reason")
        if isinstance(reason, str):
            reasons.add(reason)
    if "UserDeniedAction" in reasons:
        return WorkspaceError("denied", known_no_effect=True)
    if "AdminPolicyBlock" in reasons:
        return WorkspaceError("policy_block", known_no_effect=True)
    if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons:
        return WorkspaceError("scope_missing", known_no_effect=True)
    if not write and error.get("status") == "NOT_FOUND" and error.get("code") == 404:
        return WorkspaceError("not_found")
    if product == "drive" and error.get("status") == "FAILED_PRECONDITION":
        return WorkspaceError("precondition_failed", known_no_effect=True)
    if (
        write
        and product == "docs"
        and error.get("status") == "INVALID_ARGUMENT"
        and error.get("code") == 400
    ):
        return WorkspaceError("document_write_rejected", known_no_effect=True)
    if (
        (not write or product in {"drive", "docs"})
        and error.get("status") == "RESOURCE_EXHAUSTED"
        and error.get("code") == 429
    ):
        return WorkspaceError("rate_limited", retry_at=retry, known_no_effect=True)
    if (
        not write
        and error.get("status") == "PERMISSION_DENIED"
        and error.get("code") == 403
    ):
        return WorkspaceError("denied", known_no_effect=True)
    if error.get("code") in (-32601, -32602, -32020, -32021, -32022):
        return WorkspaceError("unsupported", known_no_effect=True)
    if error.get("status") in {"UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"}:
        return WorkspaceError("uncertain" if write else "temporary", retry_at=retry)
    return WorkspaceError("uncertain" if write else "invalid_response")


class WorkspaceMcpClient:
    """Only typed host dispatchers may call Workspace MCP and REST."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        credential: Callable[[UUID, str | None], Awaitable[WorkspaceCredential]],
        debit: Callable[[UUID, str], Awaitable[None]],
        approvals: WorkspaceApprovals,
        transfer_scratch: DriveScratch | None = None,
    ):
        self._http = http
        self._credential = credential
        self._debit = debit
        self.approvals = approvals
        self._transfer_scratch = transfer_scratch
        self._invalid: set[UUID] = set()
        self._drive_generation: dict[UUID, int] = {}
        self._reading: dict[tuple[Product, UUID], set[asyncio.Task[Obj]]] = {}
        self._catalog: dict[tuple[Product, UUID], dict[str, Obj]] = {}
        self._discovery_locks = {product: asyncio.Lock() for product in _ORIGINS}

    def invalidate(self, grant_id: UUID) -> None:
        self._invalid.add(grant_id)
        self.approvals.invalidate(grant_id)
        self._invalidate_products(grant_id, frozenset(_TOOL_SCOPES))

    def invalidate_drive(self, grant_id: UUID) -> None:
        self._drive_generation[grant_id] = self._drive_generation.get(grant_id, 0) + 1
        products: frozenset[Product] = frozenset({"drive", "docs"})
        self.approvals.invalidate(grant_id, products)
        self._invalidate_products(grant_id, products)

    def _invalidate_products(
        self, grant_id: UUID, products: frozenset[Product]
    ) -> None:
        for product in products:
            key = (product, grant_id)
            self._catalog.pop(key, None)
            for task in self._reading.get(key, ()):
                task.cancel()

    def _generation(self, grant_id: UUID, product: Product) -> int | None:
        return (
            self._drive_generation.get(grant_id, 0)
            if product in {"drive", "docs"}
            else None
        )

    def _check(self, grant_id: UUID, generation: int | None = None) -> None:
        if grant_id in self._invalid:
            raise WorkspaceError("grant_unavailable")
        if generation is not None and generation != self._drive_generation.get(
            grant_id, 0
        ):
            raise WorkspaceError("scope_missing")

    def drive_scratch(self, reserved: int) -> AbstractAsyncContextManager[Path]:
        if self._transfer_scratch is None:
            raise WorkspaceError("drive_scratch_unavailable")
        return self._transfer_scratch(reserved)

    @asynccontextmanager
    async def drive_temporary(self, maximum: int) -> AsyncIterator[BinaryIO]:
        async with self.drive_scratch(maximum) as directory:
            with tempfile.TemporaryFile(dir=directory) as output:
                yield output

    @asynccontextmanager
    async def _stream(
        self,
        verb: str,
        url: str | httpx.URL,
        headers: dict[str, str] | httpx.Headers,
        *,
        params: dict[str, str] | None = None,
        request: Obj | None = None,
        content: bytes | AsyncIterator[bytes] | None = None,
        transfer_bytes: int = 0,
        before_send: Fence | None = None,
        on_transmission: Callable[[], None] | None = None,
    ) -> AsyncIterator[httpx.Response]:
        # Allow 30 seconds of provider work plus one second per wire MiB.
        seconds = max(60.0, 30.0 + transfer_bytes / (1024 * 1024))
        async with (
            workspace_http_attempt(
                seconds, before_send, on_transmission=on_transmission
            ),
            self._http.stream(
                verb,
                url,
                params=params,
                headers=headers,
                json=request,
                content=content,
                follow_redirects=False,
                timeout=60,
            ) as response,
        ):
            yield response

    async def _create_blob(
        self,
        args: Obj,
        headers: dict[str, str],
        upload: tuple[Path, int],
        before_send: Fence | None,
    ) -> Obj:
        _, size = upload
        parent = args["parentId"]
        mime = cast(str, args["contentMimeType"])
        try:
            async with self._stream(
                "GET",
                _DRIVE_FILES + "/generateIds",
                headers,
                params={"count": "1", "space": "drive"},
            ) as response:
                _drive_rest_status(response, 200)
                ids = _items((await _drive_rest_json(response)).get("ids"))
                if (
                    len(ids) != 1
                    or not isinstance(file_id := ids[0], str)
                    or re.fullmatch(DRIVE_ID_PATTERN, file_id) is None
                    or file_id in (parent, "root", "appDataFolder")
                ):
                    raise ValueError("invalid generated Drive id")
            async with self._stream(
                "POST",
                _DRIVE_UPLOAD,
                headers
                | {"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)},
                params={
                    "uploadType": "resumable",
                    "fields": "id",
                    "supportsAllDrives": "true",
                },
                request={
                    "id": file_id,
                    "name": args["title"],
                    "parents": [parent],
                    "mimeType": mime,
                },
                before_send=before_send,
            ) as response:
                _drive_rest_status(response, 200)
                # Google owns the session URI and its query parameters.
                session = httpx.URL(response.headers.get("Location", ""))
                upload_ids = session.params.get_list("upload_id")
                if (
                    session.scheme != "https"
                    or session.host != "www.googleapis.com"
                    or session.port is not None
                    or session.userinfo
                    or session.fragment
                    or session.raw_path.split(b"?", 1)[0] != _DRIVE_UPLOAD_PATH.encode()
                    or len(upload_ids) != 1
                    or not upload_ids[0]
                ):
                    raise ValueError("invalid Drive upload session")

        except WorkspaceError as error:
            error.known_no_effect = True
            raise
        except asyncio.CancelledError:
            raise WorkspaceError("cancelled", known_no_effect=True) from None
        except (httpx.RequestError, OSError, TimeoutError):
            raise WorkspaceError("temporary", known_no_effect=True) from None
        except (httpx.InvalidURL, KeyError, ValueError, RecursionError, TypeError):
            raise WorkspaceError("invalid_response", known_no_effect=True) from None

        # Opening a resumable session does not create a file. The byte PUT
        # needs its own fresh authority and audience check.
        return await self._put_blob(
            session, headers, file_id, mime, upload, before_send
        )

    async def _read_blob_revision(
        self, file_id: str, headers: dict[str, str], before_send: Fence | None
    ) -> Obj:
        try:
            async with self._stream(
                "GET",
                f"https://www.googleapis.com/drive/v2/files/{file_id}",
                headers,
                params=_DRIVE_REVISION_FIELDS | {"updateViewedDate": "false"},
                before_send=before_send,
            ) as response:
                _drive_rest_status(response, 200)
                etag, head = _file_revision(await _drive_rest_json(response), file_id)
                return {"id": file_id, "etag": etag, "headRevisionId": head}
        except (httpx.RequestError, OSError, TimeoutError):
            raise WorkspaceError("temporary") from None
        except (ValueError, RecursionError, TypeError):
            raise WorkspaceError("invalid_response") from None

    async def _put_blob(
        self,
        url: str | httpx.URL,
        headers: dict[str, str],
        file_id: str,
        mime: str,
        source: bytes | tuple[Path, int],
        before_send: Fence | None,
        *,
        etag: str | None = None,
    ) -> Obj:
        if isinstance(source, bytes):
            content: bytes | AsyncIterator[bytes] = source
            size = len(source)
        else:
            path, size = source
            content = _upload_chunks(path, size)
        headers = headers | {"Content-Type": mime, "Content-Length": str(size)}
        request_headers = httpx.Headers(headers)
        query = None
        if etag is not None:
            request_headers.update([(b"If-Match", etag.encode("latin-1"))])
            query = _DRIVE_REVISION_FIELDS | {"uploadType": "media"}
        transmitted = False

        def transmitting() -> None:
            nonlocal transmitted
            transmitted = True

        outcome: Obj | WorkspaceError | None = None
        try:
            try:
                async with self._stream(
                    "PUT",
                    url,
                    request_headers,
                    params=query,
                    content=content,
                    transfer_bytes=size,
                    before_send=before_send,
                    on_transmission=transmitting,
                ) as response:
                    if etag is not None and response.status_code == 412:
                        outcome = WorkspaceError(
                            "precondition_failed", known_no_effect=True
                        )
                    else:
                        success = (200, 201) if etag is None else (200,)
                        _drive_rest_status(response, *success, finalizing=True)
                        result = await _drive_rest_json(response)
                        if etag is None:
                            if result.get("id") != file_id:
                                raise ValueError("mismatched Drive creation id")
                            outcome = {"id": file_id}
                        else:
                            changed, head = _file_revision(result, file_id)
                            if changed is None or changed == etag or head is None:
                                raise ValueError(
                                    "invalid Drive revision acknowledgement"
                                )
                            outcome = {"id": head, "fileEtag": changed}
            except (Exception, asyncio.CancelledError):
                if outcome is None:
                    raise
                # Teardown cannot invalidate an acknowledgement or refusal.
        except WorkspaceError as error:
            if not transmitted:
                error.known_no_effect = True
            raise
        except asyncio.CancelledError:
            raise WorkspaceError(
                "uncertain" if transmitted else "cancelled",
                known_no_effect=not transmitted,
            ) from None
        except (httpx.RequestError, OSError, TimeoutError):
            raise WorkspaceError(
                "uncertain" if transmitted else "temporary",
                known_no_effect=not transmitted,
            ) from None
        except (httpx.InvalidURL, KeyError, ValueError, RecursionError, TypeError):
            raise WorkspaceError(
                "uncertain" if transmitted else "invalid_response",
                known_no_effect=not transmitted,
            ) from None
        if isinstance(outcome, WorkspaceError):
            raise outcome
        assert outcome is not None
        return outcome

    async def _download_blob(
        self,
        file_id: str,
        headers: dict[str, str],
        download: tuple[BinaryIO, int],
        before_send: Fence | None,
    ) -> Obj:
        output, maximum = download
        try:
            async with self._stream(
                "GET",
                f"{_DRIVE_FILES}/{file_id}",
                headers,
                params={"alt": "media", "supportsAllDrives": "true"},
                transfer_bytes=maximum,
                before_send=before_send,
            ) as response:
                _drive_rest_status(response, 200)
                length = _identity_length(response)
                if length is not None and length > maximum:
                    raise WorkspaceError("too_large")
                mime = _response_mime(response)
                if (
                    re.fullmatch(DRIVE_MIME_PATTERN, mime) is None
                    or "Content-Range" in response.headers
                ):
                    raise ValueError("invalid Drive media response")
                await joined_thread(output.seek, 0)
                await joined_thread(output.truncate)
                size = 0
                digest = hashlib.sha256()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    size += len(chunk)
                    if size > maximum:
                        raise WorkspaceError("too_large")
                    digest.update(chunk)
                    await joined_thread(output.write, chunk)
                if length is not None and size != length:
                    raise ValueError("truncated Drive media response")
                await joined_thread(output.flush)
                await joined_thread(output.seek, 0)
                return {
                    "id": file_id,
                    "mimeType": mime,
                    "size": size,
                    "sha256": digest.hexdigest(),
                }
        except (httpx.RequestError, OSError, TimeoutError):
            raise WorkspaceError("temporary") from None
        except (ValueError, TypeError):
            raise WorkspaceError("invalid_response") from None

    async def _rpc(
        self,
        product: Product,
        method: str,
        params: Obj,
        token: str,
        write: bool,
        cap: int,
        before_send: Fence | None = None,
        upload: tuple[Path, int] | None = None,
        download: tuple[BinaryIO, int] | None = None,
    ) -> Obj:
        name = params.get("name")
        id = str(uuid4())
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
        }
        if product == "drive" and name == "create_file" and upload is not None:
            return await self._create_blob(
                _obj(params["arguments"]), headers, upload, before_send
            )
        if product == "drive" and name == "get_file_revision":
            return await self._read_blob_revision(
                cast(str, _obj(params["arguments"])["fileId"]), headers, before_send
            )
        if product == "drive" and name == "upload_file_revision":
            args = _obj(params["arguments"])
            file_id = cast(str, args["fileId"])
            return await self._put_blob(
                f"https://www.googleapis.com/upload/drive/v2/files/{file_id}",
                headers,
                file_id,
                cast(str, args["contentMimeType"]),
                upload
                if upload is not None
                else cast(str, args["textContent"]).encode(),
                before_send,
                etag=cast(str, args["etag"]),
            )
        if product == "drive" and download is not None:
            args = _obj(params["arguments"])
            if "exportMimeType" not in args:
                return await self._download_blob(
                    cast(str, args["fileId"]), headers, download, before_send
                )
        verb = "POST"
        query: dict[str, str] | None = None
        request: Obj | None
        if product == "docs":
            args = dict(_obj(params["arguments"]))
            document_id = args.pop("documentId")
            url = f"https://docs.googleapis.com/v1/documents/{document_id}"
            headers["Accept"] = "application/json"
            if write:
                url += ":batchUpdate"
                request = args
            else:
                verb = "GET"
                query = {
                    "includeTabsContent": "true",
                    "suggestionsViewMode": "SUGGESTIONS_INLINE",
                }
                request = None
        else:
            url = _ORIGINS[product]
            headers.update(
                {
                    "Accept": "application/json, text/event-stream",
                    "Mcp-Protocol-Version": PROTOCOL_VERSION,
                    "Mcp-Method": method,
                }
            )
            if isinstance(name, str):
                headers["Mcp-Name"] = name
            capabilities: Obj = {"elicitation": {"form": {}}}
            params = params | {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "jarvis",
                        "version": "1",
                    },
                    "io.modelcontextprotocol/clientCapabilities": capabilities,
                }
            }
            request = {"jsonrpc": "2.0", "id": id, "method": method, "params": params}
        transfer_bytes = cap if download is not None else 0
        transmitted = False

        def transmitting() -> None:
            nonlocal transmitted
            transmitted = True

        try:
            async with self._stream(
                verb,
                url,
                headers,
                params=query,
                request=request,
                transfer_bytes=transfer_bytes,
                before_send=before_send,
                on_transmission=transmitting,
            ) as response:
                status = response.status_code
                retry = workspace_retry_at(response.headers.get("Retry-After"))
                if status == 401:
                    raise _Unauthorized
                if product == "docs" and status >= 500:
                    raise WorkspaceError("uncertain" if write else "temporary")
                if not 200 <= status < 300 and (
                    _response_mime(response) != "application/json"
                ):
                    if status == 429 and not write:
                        raise WorkspaceError("rate_limited", retry_at=retry)
                    if status == 403 and not write:
                        raise WorkspaceError("denied")
                    raise WorkspaceError("uncertain" if write else "temporary")
                successful_download = download is not None and 200 <= status < 300
                if download is not None and not successful_download:
                    cap = _METADATA_BYTES
                advertised = _identity_length(response)
                mime = _response_mime(response)
                if download is not None and successful_download:
                    if advertised is not None and advertised > cap:
                        raise WorkspaceError("too_large")
                    # Both raw carriers may exist. At most one text presentation
                    # needs unescaping into a second encoded spool.
                    inner_cap = _METADATA_BYTES + 4 * ((download[1] + 2) // 3)
                    async with self.drive_scratch(cap + inner_cap) as directory:
                        with tempfile.TemporaryFile(dir=directory) as spool:
                            seen = 0
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                seen += len(chunk)
                                if seen > cap:
                                    raise WorkspaceError("too_large")
                                await joined_thread(spool.write, chunk)
                            if not seen or (
                                advertised is not None and seen != advertised
                            ):
                                raise ValueError("truncated reply")
                            await joined_thread(spool.flush)
                            packet = await joined_thread(
                                _download_envelope,
                                spool,
                                mime,
                                id,
                                *download,
                                directory,
                            )
                else:
                    body = await _bounded_body(
                        response.aiter_bytes(chunk_size=65536),
                        cap,
                        advertised,
                        WorkspaceError("uncertain" if write else "partial"),
                    )
                    if not 200 <= status < 300:
                        error_envelope = _decode(body)
                        if product != "docs" and "jsonrpc" in error_envelope:
                            error_envelope = _wire_result(body, mime, id)
                        detail = _obj(error_envelope.get("error", {}))
                        if product == "docs" and detail.get("code") != status:
                            raise WorkspaceError("uncertain" if write else "temporary")
                        if status == 429 and not write:
                            raise WorkspaceError("rate_limited", retry_at=retry)
                        raise _provider_error(detail, product, write, retry)
                    if product == "docs":
                        if mime != "application/json":
                            raise ValueError("expected a Docs JSON response")
                        return _decode(body)
                    packet = _wire_result(body, mime, id)
                if "error" in packet:
                    raise _provider_error(_obj(packet["error"]), product, write, retry)
                result = _obj(packet["result"])
                if result.get("isError") is True:
                    metadata = _obj(result.get("_meta", {}))
                    if "google.com/error" in metadata:
                        raise _provider_error(
                            _obj(metadata["google.com/error"]), product, write, retry
                        )
                    # Text-only tool errors have no stable machine proof of a write's
                    # effect. A refused read gives no evidence about item existence.
                    raise WorkspaceError("uncertain" if write else "withheld")
                if (
                    result.get("truncated", False) is not False
                    or result.get("isTruncated", False) is not False
                ):
                    raise WorkspaceError("uncertain" if write else "partial")
                if result.get("isError", False) is not False:
                    raise ValueError("invalid error flag")
                return result
        except WorkspaceError as e:
            if write and not transmitted:
                e.known_no_effect = True
            raise
        except (httpx.RequestError, TimeoutError, OSError):
            raise WorkspaceError(
                "uncertain" if write and transmitted else "temporary",
                known_no_effect=not transmitted,
            ) from None
        except (KeyError, ValueError, RecursionError, TypeError):
            raise WorkspaceError("uncertain" if write else "invalid_response") from None

    async def _read_rpc(
        self,
        grant: UUID,
        product: Product,
        method: str,
        params: Obj,
        token: str,
        cap: int,
        before_send: Fence | None = None,
        download: tuple[BinaryIO, int] | None = None,
    ) -> Obj:
        generation = self._generation(grant, product)
        self._check(grant, generation)
        task = asyncio.create_task(
            self._rpc(
                product,
                method,
                params,
                token,
                False,
                cap,
                before_send,
                download=download,
            )
        )
        key = (product, grant)
        active = self._reading.setdefault(key, set())
        active.add(task)
        try:
            result = await task
        except asyncio.CancelledError:
            caller = asyncio.current_task()
            if caller is not None and not caller.cancelling():
                self._check(grant, generation)
            raise
        finally:
            active.discard(task)
            if not active:
                self._reading.pop(key, None)
        self._check(grant, generation)
        return result

    async def discover(self, product: Product, *, grant_id: UUID) -> None:
        if product not in _ORIGINS:
            raise WorkspaceError("unsupported")
        generation = self._generation(grant_id, product)
        async with self._discovery_locks[product]:
            self._check(grant_id, generation)
            if (product, grant_id) in self._catalog:
                return
            names = _TOOL_SCOPES[product]
            catalog: dict[str, Obj] = {}
            try:
                rejected = None
                for retry in (False, True):
                    credential = await self._credential(grant_id, rejected)
                    try:
                        discovery = await self._read_rpc(
                            grant_id,
                            product,
                            "server/discover",
                            {},
                            credential.access_token,
                            _METADATA_BYTES,
                        )
                        if (
                            discovery.get("resultType") != "complete"
                            or PROTOCOL_VERSION
                            not in _strings(discovery.get("supportedVersions"))
                            or "tools" not in _obj(discovery.get("capabilities"))
                        ):
                            raise WorkspaceError("unsupported")
                        page = await self._read_rpc(
                            grant_id,
                            product,
                            "tools/list",
                            {},
                            credential.access_token,
                            _METADATA_BYTES,
                        )
                        break
                    except _Unauthorized:
                        if retry:
                            raise WorkspaceError("grant_unavailable") from None
                        rejected = credential.access_token
                else:
                    raise WorkspaceError("grant_unavailable")
                if page.get("resultType") != "complete" or page.get("nextCursor"):
                    raise WorkspaceError("unsupported")
                for entry in _items(page.get("tools")):
                    tool = _obj(entry)
                    name = tool.get("name")
                    if (
                        not isinstance(name, str)
                        or name not in names
                        or name not in _SCHEMA_PINS
                    ):
                        continue
                    if name in catalog:
                        raise ValueError("duplicate tool")
                    if _schema_pin(tool) == _SCHEMA_PINS[name]:
                        catalog[name] = _obj(tool["inputSchema"])
            except (KeyError, TypeError, ValueError):
                raise WorkspaceError("invalid_response") from None
            self._check(grant_id, generation)
            self._catalog[(product, grant_id)] = catalog

    async def call(
        self,
        product: Product,
        tool: str,
        arguments: Mapping[str, object],
        *,
        grant_id: UUID,
        invocation_id: str,
        arrival_episode: UUID | None = None,
        consent_allowed: bool = True,
        before_send: Fence | None = None,
        max_response_bytes: int = _METADATA_BYTES,
        upload: tuple[Path, int] | None = None,
        download: tuple[BinaryIO, int] | None = None,
    ) -> Obj:
        request = WorkspaceRequest(
            product,
            tool,
            grant_id,
            workspace_target_key(grant_id, arguments),
            arrival_episode,
        )
        try:
            result = await self._call(
                request,
                arguments,
                invocation_id=invocation_id,
                consent_allowed=consent_allowed,
                before_send=before_send,
                max_response_bytes=max_response_bytes,
                upload=upload,
                download=download,
            )
            if (
                tool not in _WRITES
                and request.arrival_episode is None
                and self.approvals.provider_success is not None
            ):
                await self.approvals.provider_success(request, invocation_id)
            return result
        except WorkspaceError as error:
            if error.request is None:
                error.request = request
            raise

    async def _call(
        self,
        request: WorkspaceRequest,
        arguments: Mapping[str, object],
        *,
        invocation_id: str,
        consent_allowed: bool,
        before_send: Fence | None,
        max_response_bytes: int,
        upload: tuple[Path, int] | None,
        download: tuple[BinaryIO, int] | None,
    ) -> Obj:
        product, tool, grant_id = request.product, request.operation, request.grant_id
        is_arrival = request.arrival_episode is not None
        scopes = _TOOL_SCOPES.get(product, {})
        if tool not in scopes or not invocation_id:
            raise WorkspaceError("unsupported")
        if tool == "unlabel_message" and (
            not is_arrival
            or before_send is None
            or not isinstance(arguments.get("labelIds"), list)
            or len(_items(arguments["labelIds"])) != 1
        ):
            raise WorkspaceError("denied")
        write = tool in _WRITES
        create_blob = (
            product == "drive" and tool == "create_file" and upload is not None
        )
        revise_blob = product == "drive" and tool == "upload_file_revision"
        read_revision = product == "drive" and tool == "get_file_revision"
        download_blob = (
            product == "drive"
            and tool == "download_file_content"
            and "exportMimeType" not in arguments
        )
        if is_arrival and (product != "gmail" or (write and tool != "unlabel_message")):
            raise WorkspaceError("denied")
        generation = self._generation(grant_id, product)
        if generation is not None:
            credential = await self._credential(grant_id, None)
            if DRIVE_SCOPE not in credential.scopes:
                raise WorkspaceError("scope_missing")
            self._check(grant_id, generation)
        if product == "docs":
            keys = (
                {"documentId", "requests", "writeControl"} if write else {"documentId"}
            )
            document_id = arguments.get("documentId")
            if (
                set(arguments) != keys
                or not isinstance(document_id, str)
                or re.fullmatch(DRIVE_ID_PATTERN, document_id) is None
            ):
                raise WorkspaceError("unsupported")
        elif create_blob:
            title = arguments.get("title")
            parent = arguments.get("parentId")
            mime = arguments.get("contentMimeType")
            if (
                set(arguments)
                != {
                    "title",
                    "parentId",
                    "contentMimeType",
                    "disableConversionToGoogleType",
                }
                or before_send is None
                or not isinstance(title, str)
                or not title
                or not isinstance(parent, str)
                or re.fullmatch(DRIVE_ID_PATTERN, parent) is None
                or not isinstance(mime, str)
                or re.fullmatch(DRIVE_MIME_PATTERN, mime) is None
                or mime.startswith("application/vnd.google-apps.")
                or arguments["disableConversionToGoogleType"] is not True
            ):
                raise WorkspaceError("unsupported")
        elif revise_blob:
            file_id = arguments.get("fileId")
            mime = arguments.get("contentMimeType")
            keys = {"fileId", "etag", "contentMimeType"}
            if upload is None:
                keys.add("textContent")
            if (
                set(arguments) != keys
                or before_send is None
                or not isinstance(file_id, str)
                or re.fullmatch(DRIVE_ID_PATTERN, file_id) is None
                or _file_etag(arguments.get("etag")) is None
                or not isinstance(mime, str)
                or re.fullmatch(DRIVE_MIME_PATTERN, mime) is None
                or mime.startswith("application/vnd.google-apps.")
                or (
                    upload is None and not isinstance(arguments.get("textContent"), str)
                )
            ):
                raise WorkspaceError("unsupported")
        elif download_blob or read_revision:
            file_id = arguments.get("fileId")
            if (
                set(arguments) != {"fileId"}
                or not isinstance(file_id, str)
                or re.fullmatch(DRIVE_ID_PATTERN, file_id) is None
            ):
                raise WorkspaceError("unsupported")
        else:
            await self.discover(product, grant_id=grant_id)
            self._check(grant_id, generation)
            spec = self._catalog[(product, grant_id)].get(tool)
            if spec is None or (
                not arguments.keys() <= _obj(spec.get("properties", {})).keys()
                or not set(_strings(spec.get("required", []))) <= arguments.keys()
            ):
                raise WorkspaceError("unsupported")
        if upload is not None and (
            not (create_blob or revise_blob)
            or not 0 <= upload[1] <= ATTACHMENT_MAX_BYTES
        ):
            raise WorkspaceError("unsupported")
        if download is not None and (
            product != "drive"
            or tool != "download_file_content"
            or not 0 <= download[1] <= ATTACHMENT_MAX_BYTES
        ):
            raise WorkspaceError("unsupported")
        if (tool == "download_file_content") != (download is not None):
            raise WorkspaceError("unsupported")
        # Freeze caller-owned arguments before the first provider submission.
        encoded = json.dumps(
            dict(arguments), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        if len(encoded) > _MAX_REQUEST_BYTES or max_response_bytes <= 0:
            raise WorkspaceError("unsupported")
        if download is not None and not download_blob:
            max_response_bytes = _METADATA_BYTES + 2 * 4 * ((download[1] + 2) // 3)
        params: Obj = {"name": tool, "arguments": _decode(encoded)}
        rejected = None
        refreshed = False
        after_form = False
        # A raw call also owns a budget shared with its nested guard reads.
        with nullcontext() if _attempt_limits.get() else workspace_attempts(None):
            while True:
                try:
                    self._check(grant_id, generation)
                    credential = await self._credential(grant_id, rejected)
                    if _SCOPE_PREFIX + scopes[tool] not in credential.scopes:
                        raise WorkspaceError("scope_missing")
                    self._check(grant_id, generation)
                except WorkspaceError as e:
                    if after_form:
                        e.known_no_effect = True
                    raise
                if tool == "unlabel_message" and (
                    not credential.pending_label_id
                    or _obj(params["arguments"]).get("labelIds")
                    != [credential.pending_label_id]
                ):
                    raise WorkspaceError("denied")

                async def enter() -> None:
                    if product == "gmail":
                        await self._debit(grant_id, tool)
                    self._check(grant_id, generation)
                    if before_send is not None:
                        await before_send()
                    self._check(grant_id, generation)

                try:
                    if write:
                        result = await self._rpc(
                            product,
                            "tools/call",
                            params,
                            credential.access_token,
                            True,
                            max_response_bytes,
                            enter,
                            upload,
                        )
                    else:
                        result = await self._read_rpc(
                            grant_id,
                            product,
                            "tools/call",
                            params,
                            credential.access_token,
                            max_response_bytes,
                            enter,
                            download,
                        )
                except _Unauthorized:
                    if refreshed or write:
                        raise WorkspaceError(
                            "grant_unavailable", known_no_effect=True
                        ) from None
                    refreshed = True
                    rejected = credential.access_token
                    continue
                rejected = None
                if write and (product == "docs" or create_blob or revise_blob):
                    # Acknowledgements go straight to custody. Readback is fenced.
                    return result
                if product in {"drive", "docs"}:
                    try:
                        current = await self._credential(grant_id, None)
                        if DRIVE_SCOPE not in current.scopes:
                            raise WorkspaceError("scope_missing")
                        self._check(grant_id, generation)
                    except WorkspaceError as e:
                        if write:
                            if result.get("resultType") == "input_required":
                                e.known_no_effect = True
                            else:
                                raise WorkspaceError("uncertain") from None
                        raise
                if product == "docs" or download_blob or read_revision:
                    return result
                if result.get("resultType") == "complete":
                    try:
                        return _obj(result["structuredContent"])
                    except (ValueError, KeyError):
                        raise WorkspaceError(
                            "uncertain" if write else "invalid_response"
                        ) from None
                if result.get("resultType") != "input_required":
                    raise WorkspaceError("uncertain" if write else "invalid_response")
                try:
                    form = _Form.parse(result, credential.access_token)
                except (ValueError, KeyError):
                    raise WorkspaceError("unsupported", known_no_effect=True) from None
                if not consent_allowed:
                    raise WorkspaceError("consent_required", known_no_effect=True)
                # input_required proves the earlier submission has had no effect.
                try:
                    self._check(grant_id, generation)
                    with _before_submission():
                        choice = await self.approvals.ask(
                            form, product, tool, grant_id, invocation_id, request
                        )
                except WorkspaceError as e:
                    e.known_no_effect = True
                    raise
                if choice is None or choice == "DENY_ONCE":
                    raise WorkspaceError("denied", known_no_effect=True)
                answer: Obj = {
                    "action": "accept",
                    "content": {"approval_choice": choice},
                }
                after_form = True
                params["requestState"] = form.state
                params["inputResponses"] = {"approval_choice": answer}

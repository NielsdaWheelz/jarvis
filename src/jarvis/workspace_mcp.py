"""Host-owned Google Workspace MCP transport and transient owner challenges."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal, cast
from uuid import UUID, uuid4

import httpx

from jarvis._secrets import contains_secret

Product = Literal["gmail", "calendar"]
Obj = dict[str, object]
Audit = Callable[[Obj], Awaitable[None]]
Fence = Callable[[], Awaitable[None]]
PROTOCOL_VERSION = "2026-07-28"
HUMAN_WAIT_SECONDS = 120
MAX_CONSENT_ROUNDS = 3
_ORIGINS = {
    "gmail": "https://gmailmcp.googleapis.com/mcp/v1",
    "calendar": "https://calendarmcp.googleapis.com/mcp/v1",
}
_SCOPE_PREFIX = "https://www.googleapis.com/auth/"
_GMAIL = {
    "get_message": "gmail.messages.readonly",
    "get_thread": "gmail.messages.readonly",
    "search_threads": "gmail.messages.readonly",
    "create_draft": "gmail.drafts.create",
    "list_drafts": "gmail.drafts.readonly",
    "get_draft": "gmail.drafts.readonly",
    "trash_message": "gmail.messages.delete",
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
        "trash_message",
        "unlabel_message",
        "create_draft",
        "create_event",
        "update_event",
        "delete_event",
    }
)
# November 24 public discovery. Pin wire structure and effect annotations,
# excluding descriptive prose. Schema changes disable only the affected tool.
_SCHEMA_PINS = {
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
    "trash_message": "uXR40vFo5a8EHRcXDFqIaxkyZGgxZV+RGRL0siPPGDI=",
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


class WorkspaceError(Exception):
    """A classified observation with no provider prose, credentials or body."""

    def __init__(self, kind: str, *, retry_at: datetime | None = None):
        super().__init__(kind)
        self.kind = kind
        self.retry_at = retry_at


@dataclass(slots=True)
class WorkspaceAttempts:
    maximum: int
    seconds: float | None
    attempts: int = 0
    elapsed: float = 0.0
    reserved: int = 0


_attempt_limits: ContextVar[tuple[WorkspaceAttempts, ...]] = ContextVar(
    "workspace_attempt_limits", default=()
)


@contextmanager
def workspace_attempts(
    maximum: int, *, seconds: float | None = None
) -> Iterator[WorkspaceAttempts]:
    """Bound and report this invocation's provider HTTP exchanges, including refresh."""
    if maximum < 0 or (seconds is not None and seconds <= 0):
        raise ValueError("invalid workspace request budget")
    meter = WorkspaceAttempts(maximum, seconds)
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
    io_seconds: float, before_send: Fence | None = None
) -> AsyncIterator[None]:
    limits = _attempt_limits.get()
    if any(m.attempts + m.reserved >= m.maximum for m in limits):
        raise WorkspaceError("budget_exceeded")
    remaining = min(
        (m.seconds - m.elapsed for m in limits if m.seconds is not None),
        default=io_seconds,
    )
    if remaining <= 0:
        raise WorkspaceError("budget_exceeded")
    for meter in limits:
        meter.reserved += 1
    try:
        if before_send is not None:
            # A committed quota debit survives a later local refusal.
            with _before_submission():
                await before_send()
    finally:
        for meter in limits:
            meter.reserved -= 1
    for meter in limits:
        meter.attempts += 1
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        async with asyncio.timeout(min(remaining, io_seconds)):
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
        }


class WorkspaceApprovals:
    """One visible challenge. Only the authenticated host invokes respond."""

    def __init__(self, *, audit: Audit):
        self._audit = audit
        self._round: _Round | None = None
        self._expired: UUID | None = None
        self._closed = False

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

    def invalidate(self, grant_id: UUID) -> None:
        current = self._round
        if current is not None and current.grant_id == grant_id:
            current.invalid = True
            if not current.answer.done():
                current.answer.cancel()

    async def close(self) -> None:
        self._closed = True
        if self._round is not None:
            self.invalidate(self._round.grant_id)

    async def ask(
        self,
        form: _Form,
        product: Product,
        tool: str,
        grant_id: UUID,
        invocation: str,
        number: int,
        remaining: float,
    ) -> str | None:
        if self._closed:
            raise WorkspaceError("cancelled")
        if self._round is not None:
            raise WorkspaceError("temporary")
        loop = asyncio.get_running_loop()
        current = _Round(
            uuid4(),
            grant_id,
            invocation,
            product,
            tool,
            number,
            form,
            datetime.now(UTC) + timedelta(seconds=remaining),
            loop.time() + remaining,
            loop.create_future(),
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
            self._round = None


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


def _provider_error(error: Obj, write: bool, retry: datetime | None) -> WorkspaceError:
    reasons: set[str] = set()
    for detail in _items(error.get("details", [])):
        reason = _obj(detail).get("reason")
        if isinstance(reason, str):
            reasons.add(reason)
    if "UserDeniedAction" in reasons:
        return WorkspaceError("denied")
    if "AdminPolicyBlock" in reasons:
        return WorkspaceError("policy_block")
    if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons:
        return WorkspaceError("scope_missing")
    if not write and error.get("status") == "NOT_FOUND" and error.get("code") == 404:
        return WorkspaceError("not_found")
    if (
        not write
        and error.get("status") == "RESOURCE_EXHAUSTED"
        and error.get("code") == 429
    ):
        return WorkspaceError("rate_limited", retry_at=retry)
    if (
        not write
        and error.get("status") == "PERMISSION_DENIED"
        and error.get("code") == 403
    ):
        return WorkspaceError("denied")
    if error.get("code") in (-32601, -32602, -32020, -32021, -32022):
        return WorkspaceError("unsupported")
    return WorkspaceError("uncertain" if write else "temporary")


class WorkspaceMcpClient:
    """Only the typed host dispatchers may call this allowlisted transport."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        credential: Callable[[UUID, str | None], Awaitable[WorkspaceCredential]],
        debit: Callable[[UUID, str, bool], Awaitable[None]],
        approvals: WorkspaceApprovals,
    ):
        self._http = http
        self._credential = credential
        self._debit = debit
        self.approvals = approvals
        self._invalid: set[UUID] = set()
        self._reading: dict[UUID, set[asyncio.Task[Obj]]] = {}
        self._catalog: dict[tuple[Product, UUID], dict[str, Obj]] = {}
        self._discovery_locks = {"gmail": asyncio.Lock(), "calendar": asyncio.Lock()}

    def invalidate(self, grant_id: UUID) -> None:
        self._invalid.add(grant_id)
        self.approvals.invalidate(grant_id)
        for product in _ORIGINS:
            self._catalog.pop((cast(Product, product), grant_id), None)
        for task in self._reading.get(grant_id, ()):
            task.cancel()

    def _check(self, grant_id: UUID) -> None:
        if grant_id in self._invalid:
            raise WorkspaceError("grant_unavailable")

    async def _rpc(
        self,
        product: Product,
        method: str,
        params: Obj,
        token: str,
        write: bool,
        cap: int,
        before_send: Fence | None = None,
    ) -> Obj:
        name = params.get("name")
        id = str(uuid4())
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Accept-Encoding": "identity",
            "Mcp-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": method,
        }
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
        try:
            async with (
                workspace_http_attempt(60, before_send),
                self._http.stream(
                    "POST",
                    _ORIGINS[product],
                    headers=headers,
                    json=request,
                    follow_redirects=False,
                    timeout=60,
                ) as response,
            ):
                status = response.status_code
                retry = workspace_retry_at(response.headers.get("Retry-After"))
                if status == 401:
                    raise _Unauthorized
                if not 200 <= status < 300 and (
                    response.headers.get("content-type", "").partition(";")[0].lower()
                    != "application/json"
                ):
                    if status == 429 and not write:
                        raise WorkspaceError("rate_limited", retry_at=retry)
                    if status == 403 and not write:
                        raise WorkspaceError("denied")
                    raise WorkspaceError("uncertain" if write else "temporary")
                if (
                    response.headers.get("Content-Encoding", "identity").lower()
                    != "identity"
                ):
                    raise ValueError("unsupported response encoding")
                advertised = response.headers.get("content-length")
                if advertised is not None and (
                    not advertised.isdecimal() or int(advertised) > cap
                ):
                    raise WorkspaceError("uncertain" if write else "partial")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > cap:
                        raise WorkspaceError("uncertain" if write else "partial")
                    body.extend(chunk)
                if advertised is not None and len(body) != int(advertised):
                    raise ValueError("truncated reply")
                mime = (
                    response.headers.get("content-type", "")
                    .partition(";")[0]
                    .strip()
                    .lower()
                )
                if not 200 <= status < 300:
                    error_envelope = _decode(body)
                    if "jsonrpc" in error_envelope:
                        error_envelope = _wire_result(body, mime, id)
                    detail = _obj(error_envelope.get("error", {}))
                    if status == 429 and not write:
                        raise WorkspaceError("rate_limited", retry_at=retry)
                    raise _provider_error(detail, write, retry)
                packet = _wire_result(body, mime, id)
                if "error" in packet:
                    raise _provider_error(_obj(packet["error"]), write, retry)
                result = _obj(packet["result"])
                if result.get("isError") is True:
                    metadata = _obj(result.get("_meta", {}))
                    if "google.com/error" in metadata:
                        raise _provider_error(
                            _obj(metadata["google.com/error"]), write, retry
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
        except (httpx.RequestError, TimeoutError):
            raise WorkspaceError("uncertain" if write else "temporary") from None
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
    ) -> Obj:
        self._check(grant)
        task = asyncio.create_task(
            self._rpc(product, method, params, token, False, cap, before_send)
        )
        active = self._reading.setdefault(grant, set())
        active.add(task)
        try:
            result = await task
        except asyncio.CancelledError:
            self._check(grant)
            raise
        finally:
            active.discard(task)
            if not active:
                self._reading.pop(grant, None)
        self._check(grant)
        return result

    async def discover(self, product: Product, *, grant_id: UUID) -> None:
        if product not in _ORIGINS:
            raise WorkspaceError("unsupported")
        async with self._discovery_locks[product]:
            self._check(grant_id)
            if (product, grant_id) in self._catalog:
                return
            names = _GMAIL if product == "gmail" else _CALENDAR
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
                    if not isinstance(name, str) or name not in names:
                        continue
                    if name in catalog:
                        raise ValueError("duplicate tool")
                    if _schema_pin(tool) == _SCHEMA_PINS[name]:
                        catalog[name] = _obj(tool["inputSchema"])
            except (KeyError, TypeError, ValueError):
                raise WorkspaceError("invalid_response") from None
            self._check(grant_id)
            self._catalog[(product, grant_id)] = catalog

    async def call(
        self,
        product: Product,
        tool: str,
        arguments: Mapping[str, object],
        *,
        grant_id: UUID,
        invocation_id: str,
        background: bool,
        before_send: Fence | None = None,
        max_response_bytes: int = _METADATA_BYTES,
    ) -> Obj:
        scopes = _GMAIL if product == "gmail" else _CALENDAR
        if product not in _ORIGINS or tool not in scopes or not invocation_id:
            raise WorkspaceError("unsupported")
        if tool == "unlabel_message" and (
            not background
            or before_send is None
            or not isinstance(arguments.get("labelIds"), list)
            or len(_items(arguments["labelIds"])) != 1
        ):
            raise WorkspaceError("denied")
        write = tool in _WRITES
        if background and write and tool != "unlabel_message":
            raise WorkspaceError("denied")
        await self.discover(product, grant_id=grant_id)
        self._check(grant_id)
        spec = self._catalog[(product, grant_id)].get(tool)
        if spec is None:
            raise WorkspaceError("unsupported")
        if (
            not arguments.keys() <= _obj(spec.get("properties", {})).keys()
            or not set(_strings(spec.get("required", []))) <= arguments.keys()
        ):
            raise WorkspaceError("unsupported")
        # Freeze caller-owned arguments before the first provider submission.
        encoded = json.dumps(
            dict(arguments), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        if len(encoded) > _MAX_REQUEST_BYTES or max_response_bytes <= 0:
            raise WorkspaceError("unsupported")
        params: Obj = {"name": tool, "arguments": _decode(encoded)}
        rejected = None
        refreshed = False
        wait_left = float(HUMAN_WAIT_SECONDS)
        rounds = 0
        while True:
            self._check(grant_id)
            credential = await self._credential(grant_id, rejected)
            if _SCOPE_PREFIX + scopes[tool] not in credential.scopes:
                raise WorkspaceError("scope_missing")
            self._check(grant_id)
            if tool == "unlabel_message" and (
                not credential.pending_label_id
                or _obj(params["arguments"]).get("labelIds")
                != [credential.pending_label_id]
            ):
                raise WorkspaceError("denied")

            async def enter() -> None:
                if product == "gmail":
                    await self._debit(grant_id, tool, background)
                self._check(grant_id)
                if before_send is not None:
                    await before_send()
                self._check(grant_id)

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
                    )
            except _Unauthorized:
                if refreshed or write:
                    raise WorkspaceError("grant_unavailable") from None
                refreshed = True
                rejected = credential.access_token
                continue
            rejected = None
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
                raise WorkspaceError("unsupported") from None
            if background:
                raise WorkspaceError("consent_required")
            self._check(grant_id)
            rounds += 1
            if rounds > MAX_CONSENT_ROUNDS or wait_left <= 0:
                raise WorkspaceError("consent_expired")
            started = asyncio.get_running_loop().time()
            # input_required proves the earlier submission has had no effect.
            with _before_submission():
                choice = await self.approvals.ask(
                    form, product, tool, grant_id, invocation_id, rounds, wait_left
                )
            wait_left -= asyncio.get_running_loop().time() - started
            answer: Obj = (
                {"action": "cancel"}
                if choice is None
                else {"action": "accept", "content": {"approval_choice": choice}}
            )
            params["requestState"] = form.state
            params["inputResponses"] = {"approval_choice": answer}

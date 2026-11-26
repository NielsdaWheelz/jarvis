"""Bounded inspection of the original observations belonging to a delivered request."""

from __future__ import annotations

import hashlib
import json
from functools import partial
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from llm_tools import (
    Available,
    BoundaryFailure,
    DeclaredToolFailure,
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
    canonical_json_bytes,
)
from llm_tools.content import fit_text_chunk, projection_digest, utf8_slice
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, String, func, select, tuple_
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.engine import Row, RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.action_requests import CanonicalUuid
from jarvis.actions import (
    archived_worker_action,
    delegation_state,
    recorded_action,
    recorded_action_result,
)
from jarvis.admission import JarvisOwner
from jarvis.agent_tools import AGENT_DELEGATE_ID, AGENT_IMPLEMENTATION_REVISION
from jarvis.connectors import gmail_headers
from jarvis.db import native_attempt, native_invocation, read_position
from jarvis.delegation import delegation_evidence
from jarvis.messages import causal_component_ids
from jarvis.ownership import lock_conversation
from jarvis.read_tools import (
    GOOGLE_MESSAGE_PROJECTION,
    InvalidCursor,
    Preview,
    SourceChanged,
    text_preview,
)
from jarvis.work_tools import NotFound

RECEIPT_READ_ID = ToolId("receipt.read")
RESULT_BYTES = 65_536
type Offset = Annotated[int, Field(ge=0, le=2**53 - 1)]
type Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type Part = Literal["arguments", "result", "reply"]
type Cursor = Annotated[str, Field(min_length=1, max_length=100)]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListSelection(Closed):
    kind: Literal["list"]
    tool_id: str | None
    after: Cursor | None
    limit: Annotated[int, Field(ge=1, le=50)]


class OpenSelection(Closed):
    kind: Literal["open"]
    invocation_id: CanonicalUuid
    part: Part
    offset: Offset
    max_bytes: Annotated[int, Field(ge=1, le=32768)]
    expected_digest: Digest | None


class WorkerAnswerSelection(Closed):
    kind: Literal["worker_answer"]
    job_id: CanonicalUuid
    offset: Offset
    max_bytes: Annotated[int, Field(ge=1, le=32768)]
    expected_digest: Digest | None


class ReceiptInput(Closed):
    request_ref: CanonicalUuid
    selection: Annotated[
        ListSelection | OpenSelection | WorkerAnswerSelection,
        Field(discriminator="kind"),
    ]


class Entry(Closed):
    invocation_id: CanonicalUuid
    tool_id: str
    attempt_seq: Annotated[int, Field(gt=0)]
    ordinal: Annotated[int, Field(gt=0)]
    validation: Literal["accepted", "rejected"]
    read_state: Literal["prepared", "dispatched", "uncertain", "completed"] | None
    action_id: CanonicalUuid | None
    has_result: bool
    has_reply: bool
    arguments_preview: Preview
    result_preview: Preview | None


class ListResult(Closed):
    kind: Literal["list"]
    entries: list[Entry]
    next_cursor: Cursor | None


class TextPage(Closed):
    digest: Digest
    total_bytes: Offset
    offset: Offset
    end: Offset
    next_offset: Offset | None
    text: str


class OpenResult(TextPage):
    kind: Literal["open"]
    invocation_id: CanonicalUuid
    part: Part


class WorkerAnswerResult(TextPage):
    kind: Literal["worker_answer"]
    job_id: CanonicalUuid


class PartUnavailable(Closed):
    type: Literal["PartUnavailable"] = "PartUnavailable"


type Failure = InvalidCursor | SourceChanged | PartUnavailable | NotFound


type ReceiptResult = ListResult | OpenResult | WorkerAnswerResult

SPEC = ToolSpec[ReceiptInput, ReceiptResult, Failure](
    id=RECEIPT_READ_ID,
    summary="page or open original tool observations for a delivered request.",
    documentation=PromptDocument(
        "list up to 50 at a time. previews locate originals. open arguments, result "
        "or reply by byte range, or select worker_answer by the exact job id. "
        "use the digest on continuation. counts alone "
        "establish no coverage."
    ),
    input_type=ReceiptInput,
    success_type=cast(type[ReceiptResult], ReceiptResult),
    error_type=cast(type[Failure], Failure),
    effect=ToolEffect.Read,
    limits=ToolLimits(4096, RESULT_BYTES, 0, 5.0),
)


def receipt_scope(scope: str, component: tuple[UUID, ...]):
    """Membership uses only facts fixed at invocation creation."""
    return (
        native_attempt.c.conversation_id == scope,
        native_invocation.c.proposal["input_ids"].op("?|")(
            array(tuple(map(str, component)))
        ),
        native_invocation.c.tool_id != RECEIPT_READ_ID,
    )


def original_read_position():
    return read_position.c.position == func.coalesce(
        native_invocation.c.read_position,
        "native-invocation:" + sql_cast(native_invocation.c.id, String),
    )


async def _result(
    connection: AsyncConnection, row: RowMapping
) -> dict[str, Any] | None:
    reply: dict[str, Any] = row["reply"] or {}
    if row["action_id"] is not None and row["tool_id"].startswith(("agent.", "codex.")):
        stored = await recorded_action(connection, row["action_id"])
        if (
            stored is not None
            and stored.tool_name == AGENT_DELEGATE_ID
            and stored.execution_contract.implementation_revision
            in ("jarvis-agent-control-v12", AGENT_IMPLEMENTATION_REVISION)
            and stored.result is not None
            and "registration_receipt" in stored.result
        ):
            return {
                "type": "Success",
                "value": delegation_evidence(delegation_state(stored)),
            }
        if stored is not None and archived_worker_action(stored):
            return stored.result
    if reply.get("type") == "local_result":
        return reply["result"]
    if reply.get("kind") == "host":
        return reply["rejection"]
    if row["action_id"] is not None:
        return await recorded_action_result(connection, row["action_id"])
    return row["result"]


def _entry(row: RowMapping, result: dict[str, Any] | None) -> Entry:
    arguments = row["arguments"]
    summary: str | None = None
    value: Any = None if result is None else result.get("value", result.get("error"))
    if result is not None:
        content = (
            cast(dict[str, Any], value).get("text") if isinstance(value, dict) else None
        )
        summary = (
            content
            if isinstance(content, str)
            else canonical_json_bytes(value).decode()
        )
    if (
        row["tool_id"] == "gmail.read_message"
        and row["implementation_revision"] == "jarvis-gmail-read_message-v1"
        and isinstance(arguments, dict)
    ):
        args = cast(dict[str, Any], arguments)
        locator = ", ".join(
            str(args.get(k)) for k in ("message_id", "section", "offset")
        )
        if isinstance(value, dict):
            chunk = cast(dict[str, Any], value)
            if (
                args.get("section") == "message"
                and chunk.get("projection") == GOOGLE_MESSAGE_PROJECTION
            ):
                if chunk["offset"] == 0 and chunk["next_offset"] is None:
                    headers = gmail_headers(json.loads(chunk["text"]))
                    labels: list[str] = []
                    for field in ("subject", "from", "date"):
                        matches = [
                            h["value"] for h in headers if h["name"].lower() == field
                        ]
                        if len(matches) == 1 and matches[0]:
                            labels.append(f"{field}: {matches[0]}")
                    summary = ", ".join(labels)
                else:
                    summary = "metadata fragment: " + locator
    else:
        locator = canonical_json_bytes(arguments).decode()
        if (
            isinstance(value, dict)
            and row["implementation_revision"]
            == ("jarvis-" + str(row["tool_id"]).replace(".", "-") + "-workspace-v1")
            and row["tool_id"]
            in {
                "gmail.search",
                "gmail.read_thread",
                "gmail.get_message",
                "gmail.list_drafts",
                "gmail.get_draft",
                "calendar.list_calendars",
                "calendar.list_events",
                "calendar.get_event",
            }
            and "coverage" in value
        ):
            page = cast(dict[str, Any], value)
            state = page.get("coverage", {}).get("state", "partial")
            items = page.get("items")
            chunk = page.get("chunk")
            if isinstance(items, list):
                summary = f"{len(cast(list[Any], items))} visible items, {state}"
            elif isinstance(chunk, dict):
                detail = cast(dict[str, Any], chunk)
                summary = (
                    f"bytes {detail.get('offset')} to {detail.get('end_offset')}, "
                    f"{state}"
                )
    return Entry(
        invocation_id=str(row["id"]),
        tool_id=row["tool_id"],
        attempt_seq=row["attempt_seq"],
        ordinal=row["ordinal"],
        validation=row["validation"],
        read_state=row["state"],
        action_id=None if row["action_id"] is None else str(row["action_id"]),
        has_result=result is not None,
        has_reply=row["reply"] is not None,
        arguments_preview=text_preview(locator, 160),
        result_preview=None if summary is None else text_preview(summary, 160),
    )


_order = (native_attempt.c.attempt_seq, native_invocation.c.ordinal)
_key = tuple_(*_order)
_joined = native_invocation.join(native_attempt)
_keys = select(native_invocation.c.id, *_order).select_from(_joined)
_originals = select(
    native_invocation.c.id,
    *_order,
    native_invocation.c.tool_id,
    native_invocation.c.validation,
    native_invocation.c.frozen_contract["implementation_revision"]
    .as_string()
    .label("implementation_revision"),
    native_invocation.c.action_id,
    native_invocation.c.proposal["arguments"].label("arguments"),
    native_invocation.c.reply_receipt.label("reply"),
    read_position.c.state,
    read_position.c.result,
).select_from(_joined.outerjoin(read_position, original_read_position()))


async def _list(
    connection: AsyncConnection,
    scope: str,
    request_ref: str,
    target: ListSelection,
    current: Row[Any],
    scoped: Select[Any],
) -> HandlerSuccess[ListResult]:
    first = current
    if target.tool_id is not None:
        scoped = scoped.where(native_invocation.c.tool_id == target.tool_id)
    if target.after is not None:
        try:
            revision, first_text, last_text = target.after.split(".")
            first_id, last_id = UUID(first_text), UUID(last_text)
            if revision != "v1":
                raise ValueError
        except ValueError:
            raise DeclaredToolFailure(InvalidCursor(), actual_attempts=0) from None
        first = (
            await connection.execute(
                _keys.where(
                    native_invocation.c.id == first_id,
                    native_invocation.c.tool_id == RECEIPT_READ_ID,
                    native_invocation.c.validation == "accepted",
                    native_attempt.c.conversation_id == scope,
                    native_invocation.c.proposal["input_ids"].op("?")(request_ref),
                    native_invocation.c.proposal["arguments"]["request_ref"].as_string()
                    == request_ref,
                    _key < (current.attempt_seq, current.ordinal),
                ).add_columns(
                    native_invocation.c.proposal["arguments"]["selection"].label(
                        "selection"
                    )
                )
            )
        ).one_or_none()
        last = (
            await connection.execute(scoped.where(native_invocation.c.id == last_id))
        ).one_or_none()
        if (
            first is None
            or first.selection["kind"] != "list"
            or first.selection["after"] is not None
            or first.selection["tool_id"] != target.tool_id
            or last is None
            or (last.attempt_seq, last.ordinal) >= (first.attempt_seq, first.ordinal)
        ):
            raise DeclaredToolFailure(InvalidCursor(), actual_attempts=0)
        scoped = scoped.where(_key > (last.attempt_seq, last.ordinal))
    ids = list(
        (
            await connection.execute(
                scoped.where(
                    _key < (first.attempt_seq, first.ordinal),
                )
                .order_by(*_order)
                .limit(target.limit + 1)
            )
        ).scalars()
    )

    rows = (
        await connection.execute(
            _originals.where(native_invocation.c.id.in_(ids[: target.limit])).order_by(
                *_order
            )
        )
    ).mappings()
    entries: list[Entry] = []
    # Reserve the full continuation envelope before adding complete entries.
    empty = ListResult(kind="list", entries=[], next_cursor=f"v1.{first.id}.{first.id}")
    size = len(canonical_json_bytes({"type": "Success", "value": empty.model_dump()}))
    for row in rows:
        entry = _entry(row, await _result(connection, row))
        size += len(canonical_json_bytes(entry.model_dump())) + bool(entries)
        if size > RESULT_BYTES:
            break
        entries.append(entry)
    after = (
        f"v1.{first.id}.{entries[-1].invocation_id}"
        if len(entries) < len(ids)
        else None
    )
    return HandlerSuccess(
        ListResult(kind="list", entries=entries, next_cursor=after),
        actual_attempts=0,
    )


def _chunk(
    content: bytes | None, target: OpenSelection | WorkerAnswerSelection
) -> HandlerSuccess[OpenResult | WorkerAnswerResult]:
    if content is None:
        raise DeclaredToolFailure(PartUnavailable(), actual_attempts=0)
    if isinstance(target, WorkerAnswerSelection):
        source = {"job_id": target.job_id}
        part = target.kind
        identity = {"kind": target.kind, **source}
    else:
        source = {"invocation_id": target.invocation_id}
        part = target.part
        identity = {"kind": target.kind, "part": part, **source}
    digest = projection_digest(source, part, hashlib.sha256(content).hexdigest())
    if target.expected_digest is None and target.offset:
        raise BoundaryFailure("InvalidInput", actual_attempts=0)
    if target.expected_digest is not None and target.expected_digest != digest:
        raise DeclaredToolFailure(SourceChanged(), actual_attempts=0)
    try:
        chunk = fit_text_chunk(
            utf8_slice(content, target.offset, target.max_bytes),
            offset=target.offset,
            total_bytes=len(content),
            max_bytes=target.max_bytes,
            build=lambda text, end, nxt: {
                **identity,
                "digest": digest,
                "total_bytes": len(content),
                "offset": target.offset,
                "end": end,
                "next_offset": nxt,
                "text": text,
            },
            max_output_bytes=RESULT_BYTES,
        )
    except ValueError:
        raise BoundaryFailure("InvalidInput", actual_attempts=0) from None
    return HandlerSuccess(
        WorkerAnswerResult.model_validate(chunk)
        if isinstance(target, WorkerAnswerSelection)
        else OpenResult.model_validate(chunk),
        actual_attempts=0,
    )


async def _read(
    owner: JarvisOwner, value: ReceiptInput, context: ExecutionContext
) -> HandlerSuccess[ReceiptResult]:
    prefix = "native-invocation:"
    if not context.position.startswith(prefix):
        raise ValueError("receipt read requires a native invocation position")
    invocation, attempt = native_invocation.c, native_attempt.c
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        current = (
            await connection.execute(
                _keys.where(
                    invocation.id == UUID(context.position.removeprefix(prefix)),
                    invocation.tool_id == RECEIPT_READ_ID,
                    invocation.validation == "accepted",
                    invocation.proposal["input_ids"].op("?")(value.request_ref),
                    attempt.conversation_id == owner.scope_id,
                    attempt.owner_epoch == str(owner.token),
                    attempt.fenced_at.is_(None),
                    attempt.terminal_at.is_(None),
                    attempt.product_outcome.is_(None),
                )
            )
        ).one_or_none()
        if current is None:
            raise DeclaredToolFailure(NotFound(), actual_attempts=0)
        component = await causal_component_ids(connection, (UUID(value.request_ref),))
        scope = receipt_scope(owner.scope_id, component)
        target = value.selection
        if isinstance(target, ListSelection):
            return await _list(
                connection,
                owner.scope_id,
                value.request_ref,
                target,
                current,
                _keys.where(*scope),
            )
        if isinstance(target, WorkerAnswerSelection):
            stored = await recorded_action(
                connection, UUID(target.job_id), source_conversation_id=owner.scope_id
            )
            if (
                stored is None
                or stored.tool_name != AGENT_DELEGATE_ID
                or stored.origin_message_id not in component
            ):
                raise DeclaredToolFailure(NotFound(), actual_attempts=0)
            outcome = (
                delegation_state(stored).outcome
                if stored.result is not None and "registration_receipt" in stored.result
                else None
            )
            return _chunk(
                None
                if outcome is None or outcome.answer is None
                else outcome.answer.encode(),
                target,
            )
        row = (
            (
                await connection.execute(
                    _originals.where(
                        *scope,
                        invocation.id == UUID(target.invocation_id),
                        _key < (current.attempt_seq, current.ordinal),
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DeclaredToolFailure(NotFound(), actual_attempts=0)
        if target.part == "reply":
            text = None if row["reply"] is None else row["reply"]["wire_text"]
            content = None if text is None else text.encode()
        elif target.part == "result":
            result = await _result(connection, row)
            content = None if result is None else canonical_json_bytes(result)
        else:
            content = canonical_json_bytes(row["arguments"])

    return _chunk(content, target)


def receipt_family(owner: JarvisOwner) -> ToolFamily:
    binding = ToolBinding(
        spec=SPEC,
        execute=Available(partial(_read, owner)),
        replay_policy=ReplayPolicy.ReDispatchable,
        implementation_revision="jarvis-receipt-read-v2",
        policy_epoch=PolicyEpoch("jarvis-receipt-v1"),
        policy_inputs={
            "scope": "live-delivered-causal-component",
            "upstream_attempts": 0,
        },
    )
    return ToolFamily("receipt", (SPEC,), (binding,))

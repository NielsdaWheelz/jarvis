"""The bounded archive writer for one native main attempt."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from provider_runtime.agent_runtime import AgentToolUse, thaw_json_value
from pydantic import JsonValue, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import MemoryError
from universal_memory.policy import (
    BATCH_EVENTS,
    BODY_BYTES,
    bounded_text,
    canonical_json,
    clip_tool_text,
    encoded_size,
    redact_secrets,
)
from universal_memory.types import Event, normalize_event

from jarvis.memory_service import MemoryService

LOGGER = logging.getLogger(__name__)


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _redact_payload(value: JsonValue) -> tuple[JsonValue, int]:
    if isinstance(value, str):
        if "\x00" in value:
            raise MemoryError("unsupported")
        return redact_secrets(value)
    if isinstance(value, list):
        children = [_redact_payload(child) for child in value]
        return [child for child, _ in children], sum(count for _, count in children)
    if isinstance(value, dict):
        fields = {key: _redact_payload(child) for key, child in value.items()}
        return (
            {key: child for key, (child, _) in fields.items()},
            sum(count for _, count in fields.values()),
        )
    return value, 0


def stock_observation_events(attempt: UUID, event: AgentToolUse) -> tuple[Event, ...]:
    stock = event.stock
    if stock is None:
        raise ValueError("expected a typed stock observation")

    phase = "call" if event.phase == "started" else "result"
    carrier = "stock:" + _sha256([str(attempt), event.tool_call_id, phase])
    timestamp = stock.occurred_at_ms
    occurred_at = (
        datetime.fromtimestamp(timestamp / 1000, UTC)
        if timestamp is not None and 0 <= timestamp < 253402300799999
        else None
    )
    records: list[Event] = []
    if stock.delivery_id is None:
        try:
            if stock.unsupported:
                raise MemoryError("unsupported")
            bounded_text(event.tool_call_id, 256)
            bounded_text(event.name, 256)
            payload = cast(JsonValue, thaw_json_value(event.payload))
            retained, omissions = _redact_payload(payload)
            attributes: dict[str, object] = {
                "native_call_id": event.tool_call_id,
                "secret_omissions": omissions,
            }
            source_out = None
            if phase == "call":
                attributes["tool_name"] = event.name
            else:
                attributes["outcome"] = "ok" if event.succeeded else "error"
                attributes["omitted_characters"] = 0
                if stock.shell_output is not None:
                    source_out = {
                        "state": stock.shell_output,
                        "omitted_characters": stock.upstream_omitted_characters,
                    }
                    attributes["source_output"] = source_out
                    attributes["exit_code"] = stock.exit_code
            text = (
                retained or ""
                if stock.shell_output is not None and isinstance(retained, str | None)
                else canonical_json(retained)
            )
            text, attributes["omitted_characters"] = clip_tool_text(
                text, arguments=phase == "call"
            )
            records.append(
                normalize_event(
                    {
                        "native_event_id": carrier,
                        "native_digest": _sha256(
                            [
                                carrier,
                                event.name,
                                payload,
                                event.succeeded,
                                source_out,
                                stock.exit_code,
                            ]
                        ),
                        "turn_id": str(attempt),
                        "occurred_at": occurred_at,
                        "role": "assistant" if phase == "call" else "tool",
                        "kind": "tool_" + phase,
                        "text": text,
                        "attributes": attributes,
                    },
                    stock_call=phase == "call",
                )
            )
        except (ValidationError, ValueError, UnicodeError):
            records.append(_unsupported(attempt, carrier))

    for ordinal, (sender, text) in enumerate(stock.reports):
        address = [stock.delivery_id or carrier, "peer", sender, ordinal]
        identifier = "utterance:" + _sha256(address)
        try:
            delivery: dict[str, object] = {
                "kind": "report",
                "carrier_event_id": stock.delivery_id or carrier,
                "sender_id": sender,
                "ordinal": ordinal,
            }
            if stock.delivery_id is None:
                delivery["call_id"] = event.tool_call_id
            else:
                delivery["delivery_id"] = stock.delivery_id
            records.append(
                normalize_event(
                    {
                        "native_event_id": identifier,
                        "native_digest": _sha256([address, text]),
                        "turn_id": str(attempt),
                        "occurred_at": occurred_at,
                        "role": "peer",
                        "kind": "text",
                        "text": text,
                        "attributes": {"delivery": delivery, "secret_omissions": 0},
                    }
                )
            )
        except (ValidationError, ValueError, UnicodeError):
            records.append(_unsupported(attempt, identifier))
    return tuple(records)


def _unsupported(attempt: UUID, identifier: str) -> Event:
    return normalize_event(
        {
            "native_event_id": identifier,
            "native_digest": _sha256([identifier, "unsupported"]),
            "turn_id": str(attempt),
            "role": "host",
            "kind": "gap",
            "text": "",
            "attributes": {"reason": "unsupported"},
        }
    )


class StockObservationWriter:
    def __init__(self, memory: MemoryService, owner_epoch: str, attempt: UUID) -> None:
        self._memory, self._owner_epoch, self._attempt = memory, owner_epoch, attempt
        self._queue: deque[tuple[Event, int]] = deque()
        self._bytes = 2
        self._wake = asyncio.Event()
        self._finished = False
        self._lost = False
        self._task = asyncio.create_task(self._drain())

    def offer(self, event: AgentToolUse) -> None:
        if self._finished or self._lost:
            return
        records = stock_observation_events(self._attempt, event)
        entries = [
            (record, encoded_size(record.model_dump(mode="json")) + 1)
            for record in records
        ]
        size = sum(length for _, length in entries)
        if (
            len(self._queue) + len(entries) > BATCH_EVENTS
            or self._bytes + size > BODY_BYTES
        ):
            self._lost = True
            LOGGER.warning(
                "stock observation suffix omitted: attempt=%s reason=overflow",
                self._attempt,
            )
            return
        self._queue.extend(entries)
        self._bytes += size
        self._wake.set()

    async def close(self, deadline: float, *, incomplete: bool) -> None:
        self._lost |= incomplete
        self._finished = True
        self._wake.set()
        try:
            async with asyncio.timeout_at(deadline):
                await self._task
        except TimeoutError:
            LOGGER.warning(
                "stock observation suffix omitted: attempt=%s reason=timeout",
                self._attempt,
            )

    async def _drain(self) -> None:
        try:
            while self._queue or not self._finished:
                if not self._queue:
                    self._wake.clear()
                    await self._wake.wait()
                    continue
                events = tuple(event for event, _ in self._queue)
                await self._memory.append_stock_observations(
                    self._owner_epoch, self._attempt, events
                )
                for _ in events:
                    _, size = self._queue.popleft()
                    self._bytes -= size
        except (MemoryError, SQLAlchemyError, TimeoutError) as error:
            self._lost = True
            self._queue.clear()
            LOGGER.warning(
                "stock observation suffix omitted: attempt=%s reason=%s",
                self._attempt,
                type(error).__name__,
            )
        try:
            await self._memory.finish_stock_observations(
                self._owner_epoch, self._attempt, incomplete=self._lost
            )
        except (MemoryError, SQLAlchemyError, TimeoutError) as error:
            LOGGER.warning(
                "stock observation recovery pending: attempt=%s error=%s",
                self._attempt,
                type(error).__name__,
            )

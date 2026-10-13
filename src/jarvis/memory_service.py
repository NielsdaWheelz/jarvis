"""Host admission, canonical publication and the one shared embedding boundary."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from llm_tools import canonical_json_bytes
from pydantic import ValidationError
from sqlalchemy import exists, literal, select
from sqlalchemy.exc import SQLAlchemyError
from universal_memory import (
    MemoryError,
    MemoryStore,
    NexusSubmission,
    NoteProducer,
    Submission,
    memory_reference_attributes,
)
from universal_memory.policy import (
    BATCH_EVENTS,
    BODY_BYTES,
    SEARCH_STARTS,
    SEARCH_WINDOW_SECONDS,
    encoded_size,
)
from universal_memory.schema import source_conversation, source_record
from universal_memory.types import (
    Conversation,
    Event,
    Lane,
    NoteReceipt,
    SearchInput,
    SearchResult,
    normalize_event,
)

from jarvis.db import message, native_attempt, native_invocation
from jarvis.embeddings import EmbeddingBusy, EmbeddingFailure, MemoryEmbedder
from jarvis.ownership import Database, DeploymentOwnershipDefect

LOGGER = logging.getLogger(__name__)


class MemoryServiceError(MemoryError):
    def __init__(self, code: str, *, actual_attempts: int = 0) -> None:
        super().__init__(code)
        self.actual_attempts = actual_attempts


@dataclass(frozen=True, slots=True)
class Publication:
    kind: Literal["message", "call", "reply"]
    id: UUID


class MemoryService:
    def __init__(
        self,
        *,
        library: MemoryStore,
        database: Database,
        embedder: MemoryEmbedder,
        admitted_lanes: frozenset[tuple[str, str]],
        guild_id: int,
        channel_id: int,
        nexus_admitted_owner: UUID | None = None,
    ) -> None:
        self.library, self.database, self.embedder = library, database, embedder
        self.admitted_lanes = admitted_lanes
        self.jarvis_admitted = ("devbox", "jarvis") in admitted_lanes
        self.native_id = f"discord:{guild_id}:{channel_id}"
        self.channel_id = str(channel_id)
        self.nexus_admitted_owner = nexus_admitted_owner
        self._search_starts: deque[float] = deque()

    async def search(
        self, value: SearchInput, *, cutoff: int | None = None
    ) -> SearchResult:
        # Validation and the caller's grant precede this service boundary.
        if cutoff is not None:
            try:
                admitted = await self.library.cutoff()
            except MemoryError:
                raise MemoryServiceError("unavailable") from None
            if type(cutoff) is not int or not 0 <= cutoff <= admitted:
                raise MemoryServiceError("invalid_input")
        try:
            async with self.database.connect() as connection:
                await connection.execute(select(literal(1)))
        except (DeploymentOwnershipDefect, SQLAlchemyError):
            raise MemoryServiceError("unavailable") from None
        now = time.monotonic()
        while (
            self._search_starts
            and now - self._search_starts[0] >= SEARCH_WINDOW_SECONDS
        ):
            self._search_starts.popleft()
        if len(self._search_starts) >= SEARCH_STARTS:
            raise MemoryServiceError("rate_limited")
        self._search_starts.append(now)
        try:
            vectors = await self.embedder.embed((value.query,))
        except EmbeddingBusy:
            raise MemoryServiceError("rate_limited") from None
        except EmbeddingFailure:
            raise MemoryServiceError("unavailable", actual_attempts=1) from None
        if len(vectors) != 1:
            raise MemoryServiceError("unavailable", actual_attempts=1)
        try:
            return await self.library.search(value, vectors[0], cutoff=cutoff)
        except (MemoryError, SQLAlchemyError):
            raise MemoryServiceError("unavailable", actual_attempts=1) from None

    async def save_note(self, text: str, submission: NoteProducer) -> NoteReceipt:
        admitted = (
            submission.owner_user_id == self.nexus_admitted_owner
            if isinstance(submission, NexusSubmission)
            else (submission.machine, submission.account) in self.admitted_lanes
        )
        if not admitted:
            raise MemoryServiceError("forbidden")
        async with self.database.begin() as connection:
            return await self.library.append_note(connection, text, submission)

    @staticmethod
    def main_submission(position: str) -> Submission:
        return Submission(
            kind="native",
            machine="devbox",
            account="jarvis",
            provider="jarvis",
            submission_id=uuid5(
                NAMESPACE_URL, "urn:jarvis:main-memory-save-note:" + position
            ),
            native_conversation_id=None,
        )

    async def save_main_note(self, text: str, position: str) -> NoteReceipt:
        return await self.save_note(text, self.main_submission(position))

    async def recover_main_note(self, text: str, position: str) -> NoteReceipt | None:
        # Ownership serializes with any earlier append transaction. This records
        # an existing fact even after revocation; it never authorizes an append.
        async with self.database.begin() as connection:
            return await self.library.recover_note(
                connection, text, self.main_submission(position)
            )

    async def pending_publication(self) -> tuple[Publication, ...]:
        """Freeze eligible canonical identities, including late callback replies."""
        async with self.database.connect() as connection:
            conversation_id = await connection.scalar(
                select(source_conversation.c.id).where(
                    source_conversation.c.provider == "jarvis",
                    source_conversation.c.native_id == self.native_id,
                )
            )
            rows = (
                (
                    await connection.execute(
                        select(message.c.id)
                        .where(
                            message.c.memory_admitted,
                            message.c.source_conversation_id == self.channel_id,
                            ~exists().where(
                                source_record.c.conversation_id == conversation_id,
                                source_record.c.native_event_id
                                == literal("message:")
                                + message.c.id.cast(message.c.text.type),
                            ),
                        )
                        .order_by(message.c.created_at, message.c.id)
                    )
                )
                .scalars()
                .all()
            )
            pending = [Publication("message", identifier) for identifier in rows]
            for kind in ("call", "reply"):
                conditions = [
                    native_attempt.c.memory_admitted,
                    native_attempt.c.conversation_id == self.channel_id,
                    ~exists().where(
                        source_record.c.conversation_id == conversation_id,
                        source_record.c.native_event_id
                        == literal("invocation:")
                        + native_invocation.c.id.cast(message.c.text.type)
                        + literal(":" + kind),
                    ),
                ]
                if kind == "reply":
                    conditions.append(native_invocation.c.reply_receipt.is_not(None))
                ids = (
                    (
                        await connection.execute(
                            select(native_invocation.c.id)
                            .join(native_attempt)
                            .where(*conditions)
                            .order_by(
                                native_attempt.c.attempt_seq,
                                native_invocation.c.ordinal,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                pending.extend(Publication(kind, i) for i in ids)
        return tuple(pending)

    async def publish(self) -> None:
        """Projection follows canonical commit; its failure cannot replace a receipt."""
        try:
            await self.project_pending()
        except (MemoryError, SQLAlchemyError, ValidationError) as error:
            LOGGER.warning("memory publication pending: error=%s", type(error).__name__)

    async def project_pending(
        self, pending: tuple[Publication, ...] | None = None
    ) -> int:
        if not self.jarvis_admitted:
            return 0
        if pending is None:
            pending = await self.pending_publication()
        if not pending:
            return 0
        lane = Lane(machine="devbox", account="jarvis", provider="jarvis")
        start = 0
        while start < len(pending):
            async with self.database.begin() as connection:
                now = datetime.now(UTC)
                await self.library.activate_lane(connection, lane, (), now)
                receipts = await self.library.sync_conversations(
                    connection,
                    lane,
                    (Conversation(native_id=self.native_id),),
                    now,
                    False,
                )
                receipt = receipts[0]
                batch = pending[start : start + BATCH_EVENTS]
                event_ids = tuple(
                    f"message:{original.id}"
                    if original.kind == "message"
                    else f"invocation:{original.id}:{original.kind}"
                    for original in batch
                )
                archived = set(
                    (
                        await connection.execute(
                            select(source_record.c.native_event_id).where(
                                source_record.c.conversation_id == receipt.id,
                                source_record.c.native_event_id.in_(event_ids),
                            )
                        )
                    ).scalars()
                )
                events: list[Event] = []
                consumed = 0
                for original, event_id in zip(batch, event_ids, strict=True):
                    if event_id in archived:
                        consumed += 1
                        continue
                    if original.kind == "message":
                        row = (
                            (
                                await connection.execute(
                                    select(message).where(message.c.id == original.id)
                                )
                            )
                            .mappings()
                            .one()
                        )
                        data = {
                            "id": event_id,
                            "role": row["role"],
                            "text": row["text"],
                            "source": row["source"],
                            "conversation": row["source_conversation_id"],
                            "created_at": row["created_at"].isoformat(),
                        }
                        event = normalize_event(
                            {
                                "native_event_id": data["id"],
                                "native_digest": hashlib.sha256(
                                    canonical_json_bytes(data)
                                ).hexdigest(),
                                "role": row["role"],
                                "kind": "text",
                                "text": row["text"],
                                "attributes": {"secret_omissions": 0},
                                "occurred_at": row["created_at"],
                            }
                        )
                    else:
                        row = (
                            (
                                await connection.execute(
                                    select(native_invocation).where(
                                        native_invocation.c.id == original.id
                                    )
                                )
                            )
                            .mappings()
                            .one()
                        )
                        call = original.kind == "call"
                        payload = (
                            {
                                "arguments": row["proposal"]["arguments"],
                                "validation": row["validation"],
                            }
                            if call
                            else row["reply_receipt"]["wire_text"]
                        )
                        data = {
                            "id": event_id,
                            "tool": row["tool_id"],
                            "payload": payload,
                            "native_call_id": row["native_call_id"],
                        }
                        kind = "tool_call" if call else "tool_result"
                        attributes: dict[str, object] = {
                            "native_call_id": row["native_call_id"],
                            "secret_omissions": 0,
                        }
                        if call:
                            attributes["tool_name"] = row["tool_id"]
                        else:
                            attributes.update(outcome="unknown", omitted_characters=0)
                        text = (
                            canonical_json_bytes(payload).decode()
                            if call
                            else cast(str, payload)
                        )
                        if str(row["tool_id"]).startswith("memory."):
                            kind = "memory_reference"
                            references = payload
                            if not call:
                                try:
                                    references = json.loads(cast(str, payload))
                                except ValueError:
                                    references = None
                            attributes = cast(
                                dict[str, object],
                                memory_reference_attributes(row["tool_id"], references),
                            )
                            if row["tool_id"] == "memory.save_note":
                                attributes["submission_id"] = str(
                                    self.main_submission(
                                        "native-invocation:" + str(original.id)
                                    ).submission_id
                                )
                            text = ""
                        event = normalize_event(
                            {
                                "native_event_id": data["id"],
                                "native_digest": hashlib.sha256(
                                    canonical_json_bytes(data)
                                ).hexdigest(),
                                "turn_id": str(row["attempt_id"]),
                                "role": "assistant" if call else "tool",
                                "kind": kind,
                                "text": text,
                                "attributes": attributes,
                                "occurred_at": row["reply_recorded_at"]
                                if not call
                                else None,
                            }
                        )
                    if (
                        encoded_size(
                            [e.model_dump(mode="json") for e in (*events, event)]
                        )
                        > BODY_BYTES
                    ):
                        if not events:
                            raise MemoryError("event_too_large")
                        break
                    events.append(event)
                    consumed += 1
                if events:
                    await self.library.append_events(
                        connection,
                        receipt.id,
                        receipt.checkpoint_event_id,
                        receipt.checkpoint_native_digest,
                        tuple(events),
                        True,
                        datetime.now(UTC),
                    )
                start += consumed
        return len(pending)

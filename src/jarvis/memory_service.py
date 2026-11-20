"""Host admission, canonical publication and the one shared embedding boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
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
    EMBEDDING_BATCH_SIZE,
    READ_STATEMENT_SECONDS,
    SEARCH_STARTS,
    SEARCH_WINDOW_SECONDS,
    encoded_size,
)
from universal_memory.schema import source_conversation, source_record
from universal_memory.store import EmbeddingCandidate, EmbeddingKey
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
from jarvis.embeddings import (
    EmbeddingBusy,
    EmbeddingFailure,
    MemoryEmbedder,
)
from jarvis.input_framing import archive_message_text
from jarvis.memory_rpc import (
    MemoryRequestStopped,
    MemoryRPC,
    MemoryServiceError,
)
from jarvis.ownership import Database, DeploymentOwnershipDefect

LOGGER = logging.getLogger(__name__)
INDEX_INTERVAL_SECONDS = 60


async def _until_stopped[T](
    operation: Coroutine[Any, Any, T], stop: Callable[[], Awaitable[object]] | None
) -> T:
    if stop is None:
        return await operation
    stopped = asyncio.ensure_future(stop())
    work = asyncio.create_task(operation)
    try:
        await asyncio.wait((stopped, work), return_when=asyncio.FIRST_COMPLETED)
        if stopped.done():
            stopped.result()
            raise MemoryRequestStopped
        return work.result()
    finally:
        work.cancel()
        stopped.cancel()
        await asyncio.gather(work, stopped, return_exceptions=True)


@dataclass(frozen=True, slots=True)
class Publication:
    kind: Literal["message", "call", "reply"]
    id: UUID


class ArchiveIdentityDefect(RuntimeError):
    """The configured archive key differs from the stored canonical archive."""


class MemoryService:
    def __init__(
        self,
        *,
        library: MemoryStore,
        database: Database,
        embedder: MemoryEmbedder | None = None,
        remote: MemoryRPC | None = None,
        owner_available: Callable[[], Awaitable[bool]] | None = None,
        admitted_lanes: frozenset[tuple[str, str]],
        owner_scope: str | None = None,
        owner_archive_key: str | None = None,
        nexus_admitted_owner: UUID | None = None,
    ) -> None:
        if embedder is not None and remote is not None:
            raise ValueError("memory inference must have one owner")
        if (owner_scope is None) != (owner_archive_key is None):
            raise ValueError("canonical projection requires both owner identities")
        self.library, self.database = library, database
        self._embedder, self._remote = embedder, remote
        self._owner_available = owner_available
        self.admitted_lanes = admitted_lanes
        self.jarvis_admitted = ("devbox", "jarvis") in admitted_lanes
        # The archive key stays the historical Discord identity so canonical
        # memory is never republished under a new conversation.
        self.native_id = owner_archive_key
        self.owner_scope = owner_scope
        self.nexus_admitted_owner = nexus_admitted_owner
        self._search_starts: deque[float] = deque()

    async def _require_owner(self) -> None:
        try:
            if self._owner_available is not None:
                if not await self._owner_available():
                    raise MemoryServiceError("rate_limited")
                return
            async with self.database.connect() as connection:
                await connection.execute(select(literal(1)))
        except (DeploymentOwnershipDefect, SQLAlchemyError):
            raise MemoryServiceError("unavailable") from None

    async def search(
        self,
        value: SearchInput,
        *,
        cutoff: int | None = None,
        stop: Callable[[], Awaitable[object]] | None = None,
    ) -> SearchResult:
        try:
            if self._embedder is not None:
                self._embedder.require_idle()
            await self._require_owner()
            if self._remote is not None:
                if cutoff is None:
                    raise MemoryServiceError("invalid_input")
                return await self._remote.search(value, cutoff=cutoff)
            return await _until_stopped(self._local_search(value, cutoff), stop)
        except EmbeddingBusy as error:
            LOGGER.info("memory search refused: reason=%s_slot", error.owner)
            raise MemoryServiceError("rate_limited") from None

    async def _local_search(
        self, value: SearchInput, cutoff: int | None
    ) -> SearchResult:
        if self._embedder is None:
            raise MemoryServiceError("unavailable")
        if cutoff is not None:
            try:
                async with asyncio.timeout(READ_STATEMENT_SECONDS):
                    admitted = await self.library.cutoff()
            except (MemoryError, TimeoutError):
                raise MemoryServiceError("unavailable") from None
            if type(cutoff) is not int or not 0 <= cutoff <= admitted:
                raise MemoryServiceError("invalid_input")
        now = time.monotonic()
        while (
            self._search_starts
            and now - self._search_starts[0] >= SEARCH_WINDOW_SECONDS
        ):
            self._search_starts.popleft()
        if len(self._search_starts) >= SEARCH_STARTS:
            LOGGER.info("memory search refused: reason=search_rate_limit")
            raise MemoryServiceError("rate_limited")
        # Charge an entered search even if its requester disconnects. Slot
        # contention returns synchronously before the provider attempt.
        self._search_starts.append(now)
        try:
            vectors = await self._embedder.embed((value.query,), use="search")
        except EmbeddingBusy:
            self._search_starts.pop()
            raise
        except EmbeddingFailure as error:
            if not error.actual_attempts:
                self._search_starts.pop()
            LOGGER.info(
                "memory search embedding failed: reason=%s attempts=%d",
                error.reason,
                error.actual_attempts,
            )
            raise MemoryServiceError(
                "unavailable", actual_attempts=error.actual_attempts
            ) from None
        if len(vectors) != 1:
            raise MemoryServiceError("unavailable", actual_attempts=1)
        try:
            return await self.library.search(value, vectors[0], cutoff=cutoff)
        except (MemoryError, SQLAlchemyError):
            raise MemoryServiceError("unavailable", actual_attempts=1) from None

    async def index_batch(
        self,
        rows: Sequence[EmbeddingCandidate],
        *,
        stop: asyncio.Event | None = None,
    ) -> int:
        """Commit one eligible batch through the current fenced writer."""
        if not rows:
            return 0
        references = tuple(row.reference for row in rows)
        if len({(ref.store, ref.id) for ref in references}) != len(references):
            raise EmbeddingFailure("invalid_input", actual_attempts=0)
        if self._embedder is None:
            raise EmbeddingFailure("invalid_input", actual_attempts=0)
        if stop is not None and stop.is_set():
            raise MemoryRequestStopped
        try:
            await self._require_owner()
        except MemoryServiceError:
            raise EmbeddingFailure("database_unavailable", actual_attempts=0) from None

        embedder = self._embedder

        async def infer() -> tuple[tuple[float, ...], ...]:
            if stop is not None and stop.is_set():
                raise MemoryRequestStopped
            return await embedder.embed(tuple(row.text for row in rows), use="index")

        vectors = await _until_stopped(infer(), None if stop is None else stop.wait)
        if len(vectors) != len(references):
            raise EmbeddingFailure("invalid_vector_reply", actual_attempts=1)
        try:
            # Wait for the existing writer lock without cancelling its connection.
            # Work that has entered this transaction settles before shutdown.
            async with self.database.begin() as connection:
                if stop is not None and stop.is_set():
                    raise MemoryRequestStopped
                return await self.library.write_embeddings(
                    connection, tuple(zip(references, vectors, strict=True))
                )
        except MemoryError as error:
            raise EmbeddingFailure(
                "invalid_vector_reply"
                if error.code == "invalid_input"
                else "database_unavailable",
                actual_attempts=1,
            ) from None
        except (DeploymentOwnershipDefect, SQLAlchemyError):
            raise EmbeddingFailure("database_unavailable", actual_attempts=1) from None

    async def run_indexer(self, stop: asyncio.Event) -> None:
        """Run one provider dispatch per sweep, including while Jarvis is stopped."""
        after: EmbeddingKey | None = None
        through: EmbeddingKey | None = None
        isolated: set[EmbeddingKey] = set()
        width = EMBEDDING_BATCH_SIZE
        while not stop.is_set():
            try:
                rows = await self.library.embedding_candidates(
                    width, after=after, through=through
                )
                if not rows and after is not None:
                    after = through = None
                    rows = await self.library.embedding_candidates(width)
                for index, row in enumerate(rows):
                    if row.key in isolated:
                        # Finish the healthy prefix first. Revisit this row alone.
                        rows = rows[:index] if index else rows[:1]
                        break
                try:
                    written = await self.index_batch(rows, stop=stop)
                except EmbeddingBusy as error:
                    LOGGER.info("memory index refused: reason=%s_slot", error.owner)
                except EmbeddingFailure as error:
                    LOGGER.warning(
                        "memory index failed: reason=%s attempts=%d refs=%s",
                        error.reason,
                        error.actual_attempts,
                        [(row.key[1], str(row.key[2])) for row in rows],
                    )
                    if error.reason in (
                        "context_overflow",
                        "unclassified_provider_error",
                        "invalid_vector_reply",
                    ):
                        if len(rows) > 1:
                            width = len(rows) // 2
                        elif rows:
                            if through is None:
                                through = await self.library.last_pending_embedding()
                            after = rows[0].key
                            isolated.add(after)
                            width = EMBEDDING_BATCH_SIZE
                else:
                    if written:
                        LOGGER.info("memory index committed: records=%d", written)
                        if after is not None:
                            after = rows[-1].key
                        for row in rows:
                            if row.key in isolated:
                                LOGGER.info(
                                    "memory index recovered: ref=%s/%s",
                                    row.key[1],
                                    row.key[2],
                                )
                                isolated.remove(row.key)
                        width = EMBEDDING_BATCH_SIZE
            except MemoryRequestStopped:
                return
            except MemoryError:
                LOGGER.warning(
                    "memory index failed: reason=database_unavailable attempts=0"
                )
            try:
                await asyncio.wait_for(stop.wait(), INDEX_INTERVAL_SECONDS)
            except TimeoutError:
                pass

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
                            message.c.source_conversation_id == self.owner_scope,
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
                    native_attempt.c.conversation_id == self.owner_scope,
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
        if not self.jarvis_admitted or self.native_id is None:
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
                # One owner has one canonical archive. A different stored key means
                # a mistyped setting; registering it would republish the corpus.
                if await connection.scalar(
                    select(literal(1))
                    .where(
                        source_conversation.c.provider == "jarvis",
                        source_conversation.c.native_id != self.native_id,
                    )
                    .limit(1)
                ):
                    raise ArchiveIdentityDefect(
                        "configured owner archive key differs from the stored archive"
                    )
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
                        text = archive_message_text(
                            row["text"], row["trace"], row["id"], row["home"]
                        )
                        data = {
                            "id": event_id,
                            "role": row["role"],
                            "text": text,
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
                                "text": text,
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
                        if row["tool_id"] == "receipt.read":
                            kind, text = "memory_reference", ""
                            attributes = cast(
                                dict[str, object],
                                memory_reference_attributes("receipt.read", None),
                            )
                        elif str(row["tool_id"]).startswith("memory."):
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

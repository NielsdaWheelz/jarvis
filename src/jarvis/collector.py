"""Stateless host-native collection; central receipts alone determine eligibility."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

import httpx
from llm_tools import canonical_json_bytes
from provider_runtime.agent_runtime import CodexUnixEndpoint
from provider_runtime.agent_runtime.archive import (
    ARCHIVE_CONTRACT_REVISION,
    ArchiveError,
    ArchiveHome,
    ArchiveMissing,
    archive_capabilities,
    archive_capture,
    archive_head,
    archive_list,
)
from pydantic import Field, ValidationError, field_validator, model_validator
from universal_memory import MemoryError, normalize_event
from universal_memory.policy import BATCH_EVENTS, BODY_BYTES
from universal_memory.tools import MemoryToolFailure
from universal_memory.types import (
    Closed,
    Conversation,
    ConversationReceipt,
    Lane,
    Occurrence,
)

from jarvis.config import ConfigurationError
from jarvis.memory_capture import (
    Activate,
    Baseline,
    CaptureError,
    CaptureLanes,
    Events,
    Sync,
    SyncResult,
)
from jarvis.memory_config import Machine, memory_origin

SWEEP_SECONDS = 30
REVISIT_SECONDS = 3600
_LOG = logging.getLogger(__name__)


class _Home(Closed):
    provider: Literal["codex", "claude"]
    state_root: Path
    codex_endpoint: Path | None = None

    @model_validator(mode="after")
    def native_paths(self) -> Self:
        if (
            not self.state_root.is_absolute()
            or (
                self.codex_endpoint is not None
                and not self.codex_endpoint.is_absolute()
            )
            or (self.provider == "codex") != (self.codex_endpoint is not None)
        ):
            raise ValueError("invalid native home mapping")
        return self


class CollectorConfig(Closed):
    machine: Machine
    service_url: str
    bearer_env: str = Field(
        default="JARVIS_MEMORY_CAPTURE_BEARER", pattern=r"^[A-Z][A-Z0-9_]{0,127}$"
    )
    homes: dict[str, _Home]

    _valid_service = field_validator("service_url")(memory_origin)

    @model_validator(mode="after")
    def declared_homes(self) -> Self:
        for account, home in self.homes.items():
            Lane.model_validate(
                {"machine": self.machine, "account": account, "provider": home.provider}
            )
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_bytes())
        except (OSError, ValueError):
            raise ConfigurationError("invalid native collector mapping") from None


@dataclass(frozen=True, slots=True)
class _Candidate:
    lane: Lane
    home: ArchiveHome
    receipt: ConversationReceipt
    hint: datetime | None
    changed: bool
    age: float


class Collector:
    def __init__(self, config: CollectorConfig, client: httpx.AsyncClient) -> None:
        self.config, self.client = config, client
        # Metadata hint, first-seen/last-attempt scheduling age, proved caught-up.
        self._hints: dict[tuple[str, str], tuple[datetime | None, float, bool]] = {}
        self._prefer_recent = True
        self._activation_index = 0

    async def _request(self, path: str, value: Closed | None = None) -> bytes:
        body = (
            b""
            if value is None
            else canonical_json_bytes(value.model_dump(mode="json"))
        )
        if len(body) > BODY_BYTES:
            raise MemoryError("event_too_large")
        try:
            async with self.client.stream(
                "GET" if value is None else "POST", path, content=body
            ) as response:
                received = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(received) + len(chunk) > BODY_BYTES:
                        raise MemoryError("unavailable")
                    received.extend(chunk)
                if response.status_code != 200:
                    try:
                        failure = MemoryToolFailure.model_validate(
                            json.loads(received)["error"]
                        )
                    except (ValueError, KeyError, TypeError):
                        raise MemoryError("unavailable") from None
                    raise MemoryError(failure.code)
                return bytes(received)
        except httpx.HTTPError:
            raise MemoryError("unavailable") from None

    async def _read(
        self, lane: Lane, home: ArchiveHome, receipt: ConversationReceipt
    ) -> bool:
        checkpoint = receipt.checkpoint_event_id
        reason: str | None = None
        try:
            batch = await archive_capture(
                home,
                receipt.native_id,
                after=receipt.capture_after_event_id,
                from_event_id=checkpoint,
                resume_selected=(lane.machine, lane.account)
                == ("macbook", "codex-work"),
            )
            pending = batch.occurrences
            if checkpoint is not None and not batch.replayed_from_cut:
                if not pending or pending[0].native_event_id != checkpoint:
                    raise ArchiveError("history_changed")
                first, pending = pending[0], pending[1:]
                if first.native_digest != receipt.checkpoint_native_digest or (
                    receipt.checkpoint_capture_digest is not None
                    and first.capture_digest != receipt.checkpoint_capture_digest
                ):
                    raise ArchiveError("source_conflict")
            request = Events(
                lane=lane,
                contract_revision=ARCHIVE_CONTRACT_REVISION,
                conversation_id=receipt.id,
                expected_checkpoint=checkpoint,
                expected_capture_generation=receipt.capture_generation,
                checkpoint_native_digest=receipt.checkpoint_native_digest,
                checkpoint_capture_digest=receipt.checkpoint_capture_digest,
                occurrences=(),
                caught_up=False,
                observed_at=batch.observed_at,
            )
            accepted: list[Occurrence] = []
            count = 0
            # The canonical encoding of the empty occurrence array already accounts
            # for its brackets. Using false reserves one extra byte for caught_up.
            bytes_used = len(canonical_json_bytes(request.model_dump(mode="json")))
            for native in pending[:BATCH_EVENTS]:
                try:
                    if len(native.records) > BATCH_EVENTS:
                        raise MemoryError("event_too_large")
                    occurrence = Occurrence(
                        native_event_id=native.native_event_id,
                        native_digest=native.native_digest,
                        capture_digest=native.capture_digest,
                        records=tuple(
                            normalize_event(asdict(record)) for record in native.records
                        ),
                    )
                    encoded = len(
                        canonical_json_bytes(occurrence.model_dump(mode="json"))
                    )
                except MemoryError as error:
                    reason = (
                        "event_too_large"
                        if error.code == "event_too_large"
                        else "unsupported"
                    )
                    break
                except ValidationError:
                    reason = "unsupported"
                    break
                bytes_used += encoded + bool(accepted)
                count += len(occurrence.records)
                if bytes_used > BODY_BYTES or count > BATCH_EVENTS:
                    if not accepted:
                        reason = "event_too_large"
                    break
                accepted.append(occurrence)
            caught_up = (
                batch.caught_up and len(accepted) == len(pending) and reason is None
            )
            if accepted or caught_up:
                try:
                    receipt = ConversationReceipt.model_validate_json(
                        await self._request(
                            "/v1/memory/ingest",
                            request.model_copy(
                                update={
                                    "occurrences": tuple(accepted),
                                    "caught_up": caught_up,
                                }
                            ),
                        )
                    )
                except MemoryError as error:
                    if error.code != "event_too_large" or len(accepted) < 2:
                        raise
                    # The receiver checks final read rendering, including host-specific
                    # wrappers. The rejected transaction made no progress.
                    for index, occurrence in enumerate(accepted):
                        checkpoint = receipt.checkpoint_event_id
                        generation = receipt.capture_generation
                        native_digest = receipt.checkpoint_native_digest
                        capture_digest = receipt.checkpoint_capture_digest
                        receipt = ConversationReceipt.model_validate_json(
                            await self._request(
                                "/v1/memory/ingest",
                                request.model_copy(
                                    update={
                                        "expected_checkpoint": checkpoint,
                                        "expected_capture_generation": generation,
                                        "checkpoint_native_digest": native_digest,
                                        "checkpoint_capture_digest": capture_digest,
                                        "occurrences": (occurrence,),
                                        "caught_up": caught_up
                                        and index == len(accepted) - 1,
                                    }
                                ),
                            )
                        )
            if reason is None:
                return caught_up
        except ArchiveMissing:
            reason = "native_missing"
        except ArchiveError as error:
            if error.code == "unavailable":
                return False
            reason = error.code
        except MemoryError as error:
            if error.code not in {
                "source_conflict",
                "event_too_large",
                "unsupported",
                "native_missing",
                "history_changed",
                "activation_boundary_lost",
            }:
                return False
            reason = error.code
        report = CaptureError.model_validate(
            {
                "lane": lane,
                "contract_revision": ARCHIVE_CONTRACT_REVISION,
                "conversation_id": receipt.id,
                "expected_checkpoint": receipt.checkpoint_event_id,
                "expected_capture_generation": receipt.capture_generation,
                "error": reason,
            }
        )
        await self._request("/v1/memory/ingest", report)
        _LOG.warning(
            "memory capture parked %s %s %s", lane.machine, lane.account, reason
        )
        return False

    async def _discover(
        self, lane: Lane, home: ArchiveHome
    ) -> tuple[dict[UUID, ConversationReceipt], dict[str, datetime]]:
        inventory = await archive_list(home, capture=True)
        hints = {
            item.native_id: item.updated_at
            for item in inventory.conversations
            if not item.internal
        }
        conversations = tuple(
            Conversation(
                native_id=item.native_id,
                relation=item.relation,
                parent_native_id=item.parent_native_id,
                working_directory=None if item.worker else item.working_directory,
                worker_excluded=item.worker,
            )
            for item in inventory.conversations
            if not item.internal
        )
        receipts: dict[UUID, ConversationReceipt] = {}
        offset = 0
        page: UUID | None = None
        while True:
            next_conversations = conversations[offset : offset + BATCH_EVENTS]
            offset += len(next_conversations)
            sync = Sync(
                lane=lane,
                contract_revision=ARCHIVE_CONTRACT_REVISION,
                conversations=next_conversations,
                observed_at=inventory.observed_at,
                complete=inventory.complete and offset == len(conversations),
                page=page,
            )
            result = SyncResult.model_validate_json(
                await self._request("/v1/memory/sync", sync)
            )
            receipts.update((receipt.id, receipt) for receipt in result.conversations)
            page = result.next_page
            if page is None and offset == len(conversations):
                return receipts, hints

    async def _activate(self, lane: Lane, home: ArchiveHome) -> None:
        started = datetime.now(UTC)
        capability = await archive_capabilities(home)
        inventory = await archive_list(home, with_heads=True, capture=True)
        if not inventory.complete:
            _LOG.info("memory activation pending %s %s", lane.machine, lane.account)
            return
        activation = Activate(
            lane=lane,
            contract_revision=ARCHIVE_CONTRACT_REVISION,
            conversations=tuple(
                Conversation(
                    native_id=item.native_id,
                    head_event_id=item.head_event_id,
                    baseline_error=item.head_error,
                    relation=item.relation,
                    parent_native_id=item.parent_native_id,
                    working_directory=None if item.worker else item.working_directory,
                    worker_excluded=item.worker,
                )
                for item in inventory.conversations
                if not item.internal
            ),
            sample_started_at=started,
            observed_at=inventory.observed_at,
            provider_version=capability.provider_version,
            complete=True,
        )
        await self._request("/v1/memory/sync", activation)

    async def sweep(self) -> None:
        remote = CaptureLanes.model_validate_json(
            await self._request("/v1/memory/lanes")
        )
        if remote.contract_revision != ARCHIVE_CONTRACT_REVISION:
            raise MemoryError("unsupported")
        candidates: list[_Candidate] = []
        activations: list[tuple[Lane, ArchiveHome]] = []
        first_seen = time.monotonic()
        for declared in remote.lanes:
            lane = declared.lane
            if lane.machine != self.config.machine:
                raise MemoryError("forbidden")
            native_home = self.config.homes.get(lane.account)
            if native_home is None or native_home.provider != lane.provider:
                _LOG.warning("memory home undeclared %s %s", lane.machine, lane.account)
                continue
            home = ArchiveHome(
                native_home.provider,
                native_home.state_root,
                CodexUnixEndpoint(native_home.codex_endpoint)
                if native_home.codex_endpoint is not None
                else None,
            )
            if declared.status == "pending":
                activations.append((lane, home))
                continue
            try:
                receipts, hints = await self._discover(lane, home)
            except (ArchiveError, MemoryError, ValidationError) as error:
                code = (
                    error.code
                    if isinstance(error, ArchiveError | MemoryError)
                    else "unsupported"
                )
                _LOG.warning(
                    "memory inventory blocked %s %s %s",
                    lane.machine,
                    lane.account,
                    code,
                )
                continue
            for receipt in receipts.values():
                key = (lane.account, receipt.native_id)
                if (
                    receipt.foreign
                    or receipt.worker_excluded
                    or receipt.capture_error is not None
                ):
                    self._hints.pop(key, None)
                    continue
                hint = hints.get(receipt.native_id)
                previous = self._hints.get(key)
                changed = previous is None or previous[0] != hint
                if previous is None:
                    previous = (hint, first_seen, False)
                    self._hints[key] = previous
                if (
                    receipt.baseline_error is None
                    and not changed
                    and previous[2]
                    and time.monotonic() - previous[1] < REVISIT_SECONDS
                ):
                    continue
                candidates.append(
                    _Candidate(lane, home, receipt, hint, changed, previous[1])
                )

        # Discovery is never trapped behind old history. Each serial operation
        # finishes before yielding; its central receipt remains the only cursor.
        deadline = time.monotonic() + SWEEP_SECONDS
        recent = iter(
            sorted(
                (item for item in candidates if item.receipt.baseline_error is None),
                key=lambda item: (
                    not item.changed,
                    -item.hint.timestamp() if item.hint is not None else float("inf"),
                    item.receipt.id,
                ),
            )
        )
        waiting = iter(sorted(candidates, key=lambda item: (item.age, item.receipt.id)))
        handled: set[UUID] = set()
        while True:
            preferred, other = (
                (recent, waiting) if self._prefer_recent else (waiting, recent)
            )
            candidate = next(
                (item for item in preferred if item.receipt.id not in handled), None
            )
            if candidate is None:
                candidate = next(
                    (item for item in other if item.receipt.id not in handled), None
                )
            if candidate is None:
                break
            handled.add(candidate.receipt.id)
            self._prefer_recent = not self._prefer_recent
            lane, home, receipt = candidate.lane, candidate.home, candidate.receipt
            caught_up = False
            try:
                if receipt.baseline_error is not None:
                    try:
                        head = await archive_head(home, receipt.native_id, capture=True)
                        head_id, baseline_error, observed_at = (
                            head.head_event_id,
                            None,
                            head.observed_at,
                        )
                    except ArchiveError as failure:
                        head_id, baseline_error, observed_at = (
                            None,
                            failure.code,
                            datetime.now(UTC),
                        )
                    baseline = Baseline.model_validate(
                        {
                            "lane": lane,
                            "contract_revision": ARCHIVE_CONTRACT_REVISION,
                            "conversation_id": receipt.id,
                            "head_event_id": head_id,
                            "baseline_error": baseline_error,
                            "observed_at": observed_at,
                        }
                    )
                    ConversationReceipt.model_validate_json(
                        await self._request("/v1/memory/sync", baseline)
                    )
                else:
                    caught_up = await self._read(lane, home, receipt)
            except (MemoryError, ValidationError):
                pass
            finally:
                self._hints[(lane.account, receipt.native_id)] = (
                    candidate.hint,
                    time.monotonic(),
                    caught_up,
                )
            if time.monotonic() >= deadline:
                break

        # A fresh lane still requires an indivisible complete head inventory.
        # Give active capture a slice between attempts, including failed ones.
        if activations:
            lane, home = activations[self._activation_index % len(activations)]
            self._activation_index += 1
            try:
                await self._activate(lane, home)
            except (ArchiveError, MemoryError, ValidationError) as error:
                code = (
                    error.code
                    if isinstance(error, ArchiveError | MemoryError)
                    else "unsupported"
                )
                _LOG.warning(
                    "memory activation blocked %s %s %s",
                    lane.machine,
                    lane.account,
                    code,
                )

    async def run(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.sweep()
            except (MemoryError, ValidationError) as error:
                code = error.code if isinstance(error, MemoryError) else "unsupported"
                _LOG.warning("memory collector blocked %s", code)
            await asyncio.sleep(max(0, SWEEP_SECONDS - (time.monotonic() - started)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="collect admitted native archive lanes"
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = CollectorConfig.load(args.config)
        bearer = os.environ.get(config.bearer_env)
        if bearer is None:
            raise ConfigurationError("capture bearer environment variable is missing")

        async def run() -> None:
            async with httpx.AsyncClient(
                base_url=config.service_url,
                headers={
                    "authorization": "Bearer " + bearer,
                    "content-type": "application/json",
                },
                timeout=30.0,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                await Collector(config, client).run()

        asyncio.run(run())
    except (ConfigurationError, KeyboardInterrupt):
        return 1
    return 0

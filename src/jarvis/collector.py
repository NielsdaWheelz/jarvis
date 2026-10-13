"""Stateless host-native collection; central receipts alone determine eligibility."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

import httpx
from llm_tools import canonical_json_bytes
from provider_runtime.agent_runtime.archive import (
    ARCHIVE_CONTRACT_REVISION,
    ArchiveError,
    ArchiveHome,
    ArchiveMissing,
    archive_capabilities,
    archive_list,
    archive_read,
)
from pydantic import Field, ValidationError, field_validator, model_validator
from universal_memory import MemoryError, normalize_event
from universal_memory.policy import BATCH_EVENTS, BODY_BYTES
from universal_memory.tools import MemoryToolFailure
from universal_memory.types import (
    Closed,
    Conversation,
    ConversationReceipt,
    Event,
    Lane,
)

from jarvis.config import ConfigurationError
from jarvis.memory_capture import (
    Activate,
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


class Collector:
    def __init__(self, config: CollectorConfig, client: httpx.AsyncClient) -> None:
        self.config, self.client = config, client
        self._hints: dict[tuple[str, str], tuple[datetime | None, float, bool]] = {}

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
            batch = await archive_read(
                home,
                receipt.native_id,
                after=receipt.capture_after_event_id,
                from_event_id=checkpoint,
            )
            pending = list(batch.events)
            digest = None
            if checkpoint is not None:
                if not pending or pending[0].native_event_id != checkpoint:
                    raise ArchiveError("history_changed")
                digest = pending.pop(0).native_digest
                if digest != receipt.checkpoint_native_digest:
                    raise ArchiveError("source_conflict")
            accepted: list[Event] = []
            for native in pending[:BATCH_EVENTS]:
                try:
                    candidate = normalize_event(asdict(native))
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
                trial = Events(
                    lane=lane,
                    contract_revision=ARCHIVE_CONTRACT_REVISION,
                    conversation_id=receipt.id,
                    expected_checkpoint=checkpoint,
                    checkpoint_native_digest=digest,
                    events=tuple([*accepted, candidate]),
                    caught_up=False,
                    observed_at=batch.observed_at,
                )
                if (
                    len(canonical_json_bytes(trial.model_dump(mode="json")))
                    > BODY_BYTES
                ):
                    if not accepted:
                        reason = "event_too_large"
                    break
                accepted.append(candidate)
            caught_up = (
                batch.caught_up and len(accepted) == len(pending) and reason is None
            )
            if accepted or caught_up:
                request = Events(
                    lane=lane,
                    contract_revision=ARCHIVE_CONTRACT_REVISION,
                    conversation_id=receipt.id,
                    expected_checkpoint=checkpoint,
                    checkpoint_native_digest=digest,
                    events=tuple(accepted),
                    caught_up=caught_up,
                    observed_at=batch.observed_at,
                )
                try:
                    receipt = ConversationReceipt.model_validate_json(
                        await self._request("/v1/memory/ingest", request)
                    )
                    checkpoint = receipt.checkpoint_event_id
                except MemoryError as error:
                    if error.code != "event_too_large" or len(accepted) < 2:
                        raise
                    # A permanent central rejection rolled back the whole batch.
                    # Replay its frozen events until the first unretainable one.
                    for index, event in enumerate(accepted):
                        individual = Events(
                            lane=lane,
                            contract_revision=ARCHIVE_CONTRACT_REVISION,
                            conversation_id=receipt.id,
                            expected_checkpoint=checkpoint,
                            checkpoint_native_digest=receipt.checkpoint_native_digest,
                            events=(event,),
                            caught_up=caught_up and index == len(accepted) - 1,
                            observed_at=batch.observed_at,
                        )
                        receipt = ConversationReceipt.model_validate_json(
                            await self._request("/v1/memory/ingest", individual)
                        )
                        checkpoint = receipt.checkpoint_event_id
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
                "expected_checkpoint": checkpoint,
                "error": reason,
            }
        )
        await self._request("/v1/memory/ingest", report)
        _LOG.warning(
            "memory capture parked %s %s %s", lane.machine, lane.account, reason
        )
        return True

    async def sweep(self) -> None:
        remote = CaptureLanes.model_validate_json(
            await self._request("/v1/memory/lanes")
        )
        if remote.contract_revision != ARCHIVE_CONTRACT_REVISION:
            raise MemoryError("unsupported")
        for declared in remote.lanes:
            lane = declared.lane
            if lane.machine != self.config.machine:
                raise MemoryError("forbidden")
            native_home = self.config.homes.get(lane.account)
            if native_home is None or native_home.provider != lane.provider:
                _LOG.warning("memory home undeclared %s %s", lane.machine, lane.account)
                continue
            home = ArchiveHome(
                native_home.provider, native_home.state_root, native_home.codex_endpoint
            )
            try:
                if declared.status == "pending":
                    started = datetime.now(UTC)
                    capability = await archive_capabilities(home)
                    inventory = await archive_list(home, with_heads=True)
                    if not inventory.complete:
                        _LOG.info(
                            "memory activation pending %s %s",
                            lane.machine,
                            lane.account,
                        )
                        continue
                    conversations = tuple(
                        Conversation(
                            native_id=item.native_id,
                            head_event_id=item.head_event_id,
                            relation=item.relation,
                            parent_native_id=item.parent_native_id,
                            working_directory=item.working_directory,
                        )
                        for item in inventory.conversations
                        if not item.internal
                    )
                    activation = Activate(
                        lane=lane,
                        contract_revision=ARCHIVE_CONTRACT_REVISION,
                        conversations=conversations,
                        sample_started_at=started,
                        observed_at=inventory.observed_at,
                        provider_version=capability.provider_version,
                        complete=True,
                    )
                    await self._request("/v1/memory/sync", activation)
                inventory = await archive_list(home)
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
                    working_directory=item.working_directory,
                )
                for item in inventory.conversations
                if not item.internal
            )
            handled: set[UUID] = set()
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
                try:
                    result = SyncResult.model_validate_json(
                        await self._request("/v1/memory/sync", sync)
                    )
                except (MemoryError, ValidationError):
                    break
                for receipt in result.conversations:
                    if (
                        receipt.id in handled
                        or receipt.foreign
                        or receipt.capture_error is not None
                    ):
                        continue
                    handled.add(receipt.id)
                    key = (lane.account, receipt.native_id)
                    hint = hints.get(receipt.native_id)
                    previous = self._hints.get(key)
                    if (
                        previous is not None
                        and previous[0] == hint
                        and previous[2]
                        and time.monotonic() - previous[1] < REVISIT_SECONDS
                    ):
                        continue
                    try:
                        caught_up = await self._read(lane, home, receipt)
                    except (MemoryError, ValidationError):
                        continue
                    self._hints[key] = hint, time.monotonic(), caught_up
                page = result.next_page
                if page is None and offset == len(conversations):
                    break

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

"""Closed native capture requests using provider identities and library events."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from provider_runtime.agent_runtime.archive import ARCHIVE_CONTRACT_REVISION
from pydantic import Field, TypeAdapter, model_validator
from universal_memory.policy import BATCH_EVENTS
from universal_memory.types import (
    Closed,
    Conversation,
    ConversationReceipt,
    Event,
    Lane,
    LaneReceipt,
)


class CaptureRequest(Closed):
    lane: Lane
    contract_revision: str

    @model_validator(mode="after")
    def supported(self) -> Self:
        if self.contract_revision != ARCHIVE_CONTRACT_REVISION:
            raise ValueError("unsupported archive contract revision")
        if self.lane.provider == "jarvis":
            raise ValueError("native capture cannot publish canonical Jarvis records")
        return self


class Activate(CaptureRequest):
    type: Literal["activate"] = "activate"
    conversations: tuple[Conversation, ...]
    sample_started_at: datetime
    observed_at: datetime
    provider_version: str = Field(min_length=1, max_length=4096)
    complete: Literal[True]

    @model_validator(mode="after")
    def complete_interval(self) -> Self:
        if (
            self.sample_started_at.utcoffset() is None
            or self.observed_at.utcoffset() is None
            or self.sample_started_at > self.observed_at
        ):
            raise ValueError("invalid native inventory interval")
        return self


class Sync(CaptureRequest):
    type: Literal["sync"] = "sync"
    conversations: tuple[Conversation, ...] = Field(max_length=BATCH_EVENTS)
    observed_at: datetime
    complete: bool
    page: UUID | None = None


class Events(CaptureRequest):
    type: Literal["events"] = "events"
    conversation_id: UUID
    expected_checkpoint: str | None
    checkpoint_native_digest: str | None
    events: tuple[Event, ...] = Field(max_length=BATCH_EVENTS)
    caught_up: bool
    observed_at: datetime


class CaptureError(CaptureRequest):
    type: Literal["error"] = "error"
    conversation_id: UUID
    expected_checkpoint: str | None
    error: Literal[
        "native_missing",
        "unsupported",
        "event_too_large",
        "history_changed",
        "activation_boundary_lost",
        "source_conflict",
    ]


class CaptureLane(Closed):
    lane: Lane
    status: Literal["pending", "active"]
    receipt: LaneReceipt | None


class CaptureLanes(Closed):
    contract_revision: str = ARCHIVE_CONTRACT_REVISION
    lanes: tuple[CaptureLane, ...]


class SyncResult(Closed):
    lane_receipt: LaneReceipt
    conversations: tuple[ConversationReceipt, ...]
    next_page: UUID | None = None


SYNC_REQUEST: TypeAdapter[Annotated[Activate | Sync, Field(discriminator="type")]] = (
    TypeAdapter(Annotated[Activate | Sync, Field(discriminator="type")])
)
INGEST_REQUEST: TypeAdapter[
    Annotated[Events | CaptureError, Field(discriminator="type")]
] = TypeAdapter(Annotated[Events | CaptureError, Field(discriminator="type")])

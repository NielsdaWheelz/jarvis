"""Private handoff bound to one stopped shared-memory snapshot."""

from collections.abc import Hashable
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from universal_memory.types import Event, Occurrence

type Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type NativeID = Annotated[str, Field(min_length=1, max_length=256)]
type GapReason = Literal[
    "source_unavailable", "source_unsupported", "source_conflict", "delivery_unproven"
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HistoricalCarrier(_Closed):
    conversation_id: UUID
    native_event_id: NativeID
    native_digest: Digest
    part_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]

    @property
    def key(self) -> tuple[UUID, str, str]:
        return self.conversation_id, self.native_event_id, self.native_digest


class _Replacement(_Closed):
    conversation_id: UUID
    carrier_native_event_id: NativeID
    carrier_native_digest: Digest
    event: Event

    @property
    def carrier_key(self) -> tuple[UUID, str, str]:
        return (
            self.conversation_id,
            self.carrier_native_event_id,
            self.carrier_native_digest,
        )


class HistoricalSpeech(_Replacement):
    @model_validator(mode="after")
    def validate_speech(self) -> Self:
        if self.event.kind != "text" or not self.event.attributes.get("delivery"):
            raise ValueError("recovery needs typed source delivery")
        Occurrence(
            native_event_id=self.carrier_native_event_id,
            native_digest=self.carrier_native_digest,
            capture_digest="0" * 64,
            records=(self.event,),
        )
        return self


class HistoricalGap(_Replacement):
    reason: GapReason

    @model_validator(mode="after")
    def validate_gap(self) -> Self:
        reason = (
            "unsupported"
            if self.reason in ("source_unsupported", "delivery_unproven")
            else "unreadable"
        )
        if (
            self.event.kind != "gap"
            or self.event.role != "unknown"
            or self.event.text
            or self.event.attributes != {"reason": reason}
            or self.event.native_event_id == self.carrier_native_event_id
        ):
            raise ValueError("unresolved carrier needs a content-free gap")
        return self


class HistoricalHold(_Closed):
    carrier: HistoricalCarrier
    reason: GapReason


class HistoricalCaptureManifest(_Closed):
    format: Literal["historical-capture.v1"] = "historical-capture.v1"
    snapshot_sha256: Digest
    source_schema: Literal["0020"]
    leaf_count: Annotated[int, Field(ge=0)]
    retire: tuple[HistoricalCarrier, ...]
    recovered: tuple[HistoricalSpeech, ...]
    gaps: tuple[HistoricalGap, ...]
    hold: tuple[HistoricalHold, ...]
    counts: dict[str, Annotated[int, Field(ge=0)]]

    @model_validator(mode="after")
    def validate_membership(self) -> Self:
        carriers = (*self.retire, *(item.carrier for item in self.hold))
        original_ids: set[Hashable] = set()
        part_ids: set[UUID] = set()
        for carrier in carriers:
            address = carrier.conversation_id, carrier.native_event_id
            if address in original_ids:
                raise ValueError("duplicate original event in manifest")
            original_ids.add(address)
            for part_id in carrier.part_ids:
                if part_id in part_ids:
                    raise ValueError("duplicate original part in manifest")
                part_ids.add(part_id)

        retired = {carrier.key for carrier in self.retire}
        replacement_ids: set[tuple[UUID, str]] = set()
        for replacement in (*self.recovered, *self.gaps):
            address = replacement.conversation_id, replacement.event.native_event_id
            if replacement.carrier_key not in retired:
                raise ValueError("replacement needs an exact retired carrier")
            if address in replacement_ids or address in original_ids:
                raise ValueError("duplicate or occupied replacement address")
            replacement_ids.add(address)
        return self

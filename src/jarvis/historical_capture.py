"""Classify a stopped archive and recover typed native speech without publishing it."""

import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from hashlib import sha256
from itertools import groupby
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from provider_runtime.agent_runtime import _claude_archive, _codex_archive
from provider_runtime.agent_runtime.archive import (
    ARCHIVE_CONTRACT_REVISION,
    ArchiveError,
    ArchiveHome,
    ArchiveOccurrence,
)
from provider_runtime.agent_runtime.codex_endpoint import CodexUnixEndpoint
from pydantic import AwareDatetime, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from universal_memory.policy import canonical_json
from universal_memory.types import Closed, normalize_event

from jarvis.collector import CollectorConfig
from jarvis.historical_capture_manifest import (
    Digest,
    GapReason,
    HistoricalCaptureManifest,
    HistoricalCarrier,
    HistoricalGap,
    HistoricalSpeech,
)

_ROUTINE_TOOLS = {
    "codex": frozenset({"shell", "apply_patch", "web.search"}),
    "claude": frozenset(
        {
            "Bash",
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Glob",
            "Grep",
            "WebFetch",
            "WebSearch",
            "NotebookEdit",
            "TodoWrite",
            "Skill",
            "ToolSearch",
        }
    ),
}
_CLAUDE_TRANSCRIPT_BYTES = 256 * 1024**2


class HistoricalEvent(HistoricalCarrier):
    provider: Literal["codex", "claude", "nexus"]
    machine: str | None
    account: str | None
    native_conversation_id: str
    kind: Literal["tool_call", "tool_result", "memory_reference", "text"]
    call_id: str | None = None
    tool_name: str | None = None
    child_link: bool = False
    worker_excluded: bool = False
    first_position: Annotated[int, Field(ge=0)]
    occurred_at: AwareDatetime | None = None


class HistoricalCohort(Closed):
    snapshot_sha256: Digest
    source_schema: Literal["0020"]
    leaf_count: Annotated[int, Field(ge=0)]
    events: tuple[HistoricalEvent, ...]

    @property
    def fingerprint(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()


class SourceObservation(Closed):
    carrier: HistoricalCarrier
    status: Literal["matched", "worker_excluded"] | GapReason
    speech: tuple[HistoricalSpeech, ...] = ()


class HistoricalEvidence(Closed):
    cohort_sha256: Digest
    machine: str
    observations: tuple[SourceObservation, ...]


_COHORT_SQL = text("""
    SELECT c.id AS conversation_id, c.provider, c.machine, c.account,
        c.native_id AS native_conversation_id, c.worker_excluded,
        r.id AS part_id, r.native_event_id, r.native_digest, r.kind,
        r.part, r.part_count,
        r.occurred_at, r.attributes->>'native_call_id' AS call_id,
        r.attributes->>'tool_name' AS tool_name,
        (r.attributes->>'child_native_id') IS NOT NULL AS child_link, l.position
    FROM public.source_record r
    JOIN public.source_conversation c ON c.id = r.conversation_id
    LEFT JOIN public.memory_leaf l ON l.source_record_id = r.id
    WHERE c.provider IN ('codex', 'claude', 'nexus') AND (
        r.kind IN ('tool_call', 'tool_result', 'memory_reference') OR
        (c.provider = 'claude' AND r.kind = 'text' AND r.role = 'owner'
         AND r.attributes #>> '{delivery,kind}' IS NULL)
    )
    ORDER BY r.conversation_id, r.native_event_id, r.part
""")


def _whole_events(
    rows: Iterable[Mapping[str, Any]], leaf_count: int
) -> tuple[HistoricalEvent, ...]:
    events: list[HistoricalEvent] = []
    for _, group in groupby(
        rows, key=lambda row: (row["conversation_id"], row["native_event_id"])
    ):
        parts = list(group)
        first = parts[0]
        cuts = tuple(part["position"] for part in parts)
        ignored = {"part", "part_id", "position"}
        identity = {key: value for key, value in first.items() if key not in ignored}
        if (
            len(parts) != first["part_count"]
            or any(
                position is None or not 0 <= position < leaf_count for position in cuts
            )
            or cuts != tuple(range(cuts[0], cuts[0] + len(parts)))
            or any(
                part["part"] != index
                or any(part[key] != value for key, value in identity.items())
                for index, part in enumerate(parts)
            )
        ):
            raise ValueError(
                "historical classification needs whole parts in the stopped cut"
            )
        identity.pop("part_count")
        events.append(
            HistoricalEvent.model_validate(
                identity
                | {
                    "first_position": cuts[0],
                    "part_ids": tuple(part["part_id"] for part in parts),
                }
            )
        )
    return tuple(sorted(events, key=lambda event: event.first_position))


async def enumerate_cut(
    connection: AsyncConnection, snapshot_sha256: str, leaf_count: int
) -> HistoricalCohort:
    await connection.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    )
    await connection.execute(text("SET LOCAL statement_timeout = '60s'"))
    if (
        await connection.scalar(text("SELECT version_num FROM public.alembic_version"))
        != "0020"
        or await connection.scalar(
            text("SELECT leaf_count FROM public.memory_state WHERE id=1")
        )
        != leaf_count
    ):
        raise ValueError("archive does not match the stopped cut")
    rows = (await connection.execute(_COHORT_SQL)).mappings()
    return HistoricalCohort(
        snapshot_sha256=snapshot_sha256,
        source_schema="0020",
        leaf_count=leaf_count,
        events=_whole_events(cast(Iterable[Mapping[str, Any]], rows), leaf_count),
    )


def _carrier(event: HistoricalEvent) -> HistoricalCarrier:
    return HistoricalCarrier(
        conversation_id=event.conversation_id,
        native_event_id=event.native_event_id,
        native_digest=event.native_digest,
        part_ids=event.part_ids,
    )


def _invocations(
    events: Sequence[HistoricalEvent],
) -> dict[tuple[UUID, str], list[HistoricalEvent]]:
    groups: dict[tuple[UUID, str], list[HistoricalEvent]] = defaultdict(list)
    for event in events:
        if event.call_id is not None and event.kind in ("tool_call", "tool_result"):
            groups[event.conversation_id, event.call_id].append(event)
    return groups


def _routine(event: HistoricalEvent, related: Sequence[HistoricalEvent]) -> bool:
    if (
        event.kind == "memory_reference"
        or event.provider == "nexus"
        or event.worker_excluded
    ):
        return True
    calls = [item for item in related if item.kind == "tool_call"]
    return (
        len(calls) == 1
        and calls[0].tool_name in _ROUTINE_TOOLS[event.provider]
        and not any(item.child_link for item in related)
    )


def _delivered(
    event: HistoricalEvent, native: ArchiveOccurrence
) -> tuple[HistoricalSpeech, ...]:
    deliveries: list[HistoricalSpeech] = []
    for record in native.records:
        delivery = record.attributes.get("delivery")
        if not isinstance(delivery, dict):
            continue
        delivery = cast(dict[str, object], delivery)
        if event.kind == "text":
            if delivery.get("kind") != "report" or record.role != "peer":
                continue
        elif not event.call_id or delivery.get("call_id") != event.call_id:
            raise ValueError(
                "typed utterance has a conflicting historical call identity"
            )
        deliveries.append(
            HistoricalSpeech(
                conversation_id=event.conversation_id,
                carrier_native_event_id=event.native_event_id,
                carrier_native_digest=event.native_digest,
                event=normalize_event(asdict(record)),
            )
        )
    return tuple(deliveries)


def _probe_claude(
    home: ArchiveHome, native_id: str, transcript: _claude_archive.Transcript | None
) -> tuple[str, Sequence[ArchiveOccurrence]]:
    if transcript is None or _claude_archive.marked(home, native_id, transcript):
        return "source_unavailable", ()
    if _claude_archive.worker(transcript):
        return "worker_excluded", ()
    version = _claude_archive.file_version(transcript.path)
    if version[0] > _CLAUDE_TRANSCRIPT_BYTES:
        return "source_unavailable", ()
    events, complete, _, _ = _claude_archive.history(
        home, native_id, transcript, capture=True
    )
    if _claude_archive.file_version(transcript.path) != version:
        return "source_conflict", ()
    return ("source_conflict" if complete else "source_unavailable"), cast(
        Sequence[ArchiveOccurrence], events
    )


async def _probe_codex(
    home: ArchiveHome, native_id: str
) -> tuple[str, Sequence[ArchiveOccurrence]]:
    async with asyncio.timeout(60):
        async with _codex_archive.client(home) as connection:
            thread = await _codex_archive.read_thread(connection, native_id)
            info, _ = _codex_archive.conversation(thread, archived=False)
            if info.native_id != native_id or info.internal:
                return "source_conflict", ()
            if info.worker:
                return "worker_excluded", ()
            events, complete = await _codex_archive.history(
                connection, home, native_id, thread, capture=True
            )
    return ("source_conflict" if complete else "source_unavailable"), cast(
        Sequence[ArchiveOccurrence], events
    )


async def observe_native(
    cohort: HistoricalCohort, config: CollectorConfig
) -> HistoricalEvidence:
    if ARCHIVE_CONTRACT_REVISION != "native-archive.v5":
        raise ValueError("historical recovery requires the selected native adapter")
    calls = _invocations(cohort.events)
    candidates: dict[UUID, list[HistoricalEvent]] = defaultdict(list)
    for event in cohort.events:
        if event.machine != config.machine or event.worker_excluded:
            continue
        related = calls.get((event.conversation_id, event.call_id or ""), ())
        if (event.kind == "text" and event.provider == "claude") or (
            event.kind in ("tool_call", "tool_result") and not _routine(event, related)
        ):
            candidates[event.conversation_id].append(event)
    observations: list[SourceObservation] = []
    inventories: dict[Path, dict[str, _claude_archive.Transcript] | ArchiveError] = {}
    for members in candidates.values():
        first = members[0]
        home = config.homes.get(first.account or "")
        if home is None or home.provider != first.provider:
            continue
        try:
            source = ArchiveHome(
                home.provider,
                home.state_root,
                CodexUnixEndpoint(home.codex_endpoint) if home.codex_endpoint else None,
            )
            if source.provider == "claude":
                if source.state_root not in inventories:
                    try:
                        inventories[source.state_root] = await asyncio.to_thread(
                            _claude_archive.files, source
                        )
                    except ArchiveError as error:
                        inventories[source.state_root] = error
                inventory = inventories[source.state_root]
                if isinstance(inventory, ArchiveError):
                    raise inventory.with_traceback(None)
                state, native = await asyncio.to_thread(
                    _probe_claude,
                    source,
                    first.native_conversation_id,
                    inventory.get(first.native_conversation_id),
                )
            else:
                state, native = await _probe_codex(source, first.native_conversation_id)
        except TimeoutError:
            state, native = "source_unavailable", ()
        except ArchiveError as error:
            state = {
                "unsupported": "source_unsupported",
                "event_too_large": "source_unsupported",
                "source_conflict": "source_conflict",
                "history_changed": "source_conflict",
            }.get(error.code, "source_unavailable")
            native = ()
        by_id = {item.native_event_id: item for item in native}
        for member in members:
            occurrence = by_id.get(member.native_event_id)
            status = state
            speech = ()
            if occurrence is not None:
                status = "source_conflict"
                if occurrence.native_digest == member.native_digest:
                    try:
                        speech = _delivered(member, occurrence)
                        status = "matched"
                        if not speech and member.kind in ("tool_call", "tool_result"):
                            if any(
                                record.kind == "gap" for record in occurrence.records
                            ):
                                status = "source_unsupported"
                            elif any(
                                record.kind == "text" for record in occurrence.records
                            ):
                                status = "delivery_unproven"
                    except (ValueError, ValidationError):
                        status = "source_conflict"
            if member.kind != "text" or speech:
                observations.append(
                    SourceObservation.model_validate(
                        {
                            "carrier": _carrier(member),
                            "status": status,
                            "speech": speech,
                        }
                    )
                )
    return HistoricalEvidence(
        cohort_sha256=cohort.fingerprint,
        machine=config.machine,
        observations=tuple(observations),
    )


def _gap(event: HistoricalEvent, reason: GapReason) -> HistoricalGap:
    digest = sha256(
        canonical_json(
            [str(event.conversation_id), event.native_event_id, event.native_digest]
        ).encode()
    ).hexdigest()
    return HistoricalGap(
        conversation_id=event.conversation_id,
        carrier_native_event_id=event.native_event_id,
        carrier_native_digest=event.native_digest,
        reason=reason,
        event=normalize_event(
            {
                "native_event_id": f"historical-gap:{digest}",
                "native_digest": digest,
                "role": "unknown",
                "kind": "gap",
                "text": "",
                "occurred_at": event.occurred_at,
                "attributes": {
                    "reason": "unsupported"
                    if reason in ("source_unsupported", "delivery_unproven")
                    else "unreadable"
                },
            }
        ),
    )


def build_manifest(
    cohort: HistoricalCohort, evidence: Sequence[HistoricalEvidence]
) -> HistoricalCaptureManifest:
    all_events = {event.key: event for event in cohort.events}
    observed: dict[tuple[UUID, str, str], SourceObservation] = {}
    for report in evidence:
        if report.cohort_sha256 != cohort.fingerprint:
            raise ValueError("native evidence refers to a different stopped cohort")
        for record in report.observations:
            event = all_events.get(record.carrier.key)
            if (
                event is None
                or event.machine != report.machine
                or _carrier(event) != record.carrier
                or record.carrier.key in observed
                or (record.speech and record.status != "matched")
            ):
                raise ValueError(
                    "native evidence does not target a unique whole carrier in its lane"
                )
            for speech in record.speech:
                delivery = cast(dict[str, object], speech.event.attributes["delivery"])
                if (
                    speech.carrier_key != event.key
                    or (
                        event.kind == "text"
                        and (
                            delivery["kind"] != "report" or speech.event.role != "peer"
                        )
                    )
                    or (
                        event.kind != "text"
                        and (
                            not event.call_id
                            or delivery.get("call_id") != event.call_id
                        )
                    )
                ):
                    raise ValueError(
                        "native speech contradicts its receiving historical carrier"
                    )
            observed[event.key] = record

    calls = _invocations(cohort.events)
    counts = Counter[str]()
    retire: list[HistoricalCarrier] = []
    recovered: dict[tuple[UUID, str], HistoricalSpeech] = {}
    gaps: list[HistoricalGap] = []
    for event in cohort.events:
        observation = observed.get(event.key)
        speech = observation.speech if observation else ()
        if event.kind == "text" and not speech:
            continue
        retire.append(_carrier(event))
        counts[f"retired_{event.kind}_parts"] += len(event.part_ids)
        related = calls.get((event.conversation_id, event.call_id or ""), ())
        for item in speech:
            address = item.conversation_id, item.event.native_event_id
            previous = recovered.get(address)
            if previous:
                if (
                    previous.event.native_digest != item.event.native_digest
                    or previous.event.text != item.event.text
                    or previous.event.role != item.event.role
                    or (
                        event.kind == "text"
                        and previous.carrier_key != item.carrier_key
                    )
                ):
                    raise ValueError("conflicting shared delivery identity")
            else:
                recovered[address] = item
                delivery = cast(dict[str, object], item.event.attributes["delivery"])
                counts[f"recovered_{delivery['kind']}"] += 1
        if (
            speech
            or _routine(event, related)
            or (observation and observation.status in ("matched", "worker_excluded"))
        ):
            continue
        if event.kind == "tool_call" and any(
            item.kind == "tool_result" for item in related
        ):
            continue
        status = observation.status if observation else "source_unavailable"
        reason = cast(GapReason, status)
        gaps.append(_gap(event, reason))
        counts[f"gaps_{reason}"] += 1
    return HistoricalCaptureManifest(
        snapshot_sha256=cohort.snapshot_sha256,
        source_schema=cohort.source_schema,
        leaf_count=cohort.leaf_count,
        retire=tuple(retire),
        recovered=tuple(recovered.values()),
        gaps=tuple(gaps),
        hold=(),
        counts=dict(counts),
    )

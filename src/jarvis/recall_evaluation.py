"""Frozen recall-case validation and compact selection/open scoring."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecallFixture(_StrictModel):
    id: UUID
    table_kind: Literal["memory_log", "memory_summary"]
    text: str = Field(min_length=1, max_length=8_000)
    source_memory_ids: tuple[UUID, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def valid_lineage(self) -> RecallFixture:
        if self.table_kind == "memory_log" and self.source_memory_ids:
            raise ValueError("raw recall fixtures cannot carry summary lineage")
        if self.table_kind == "memory_summary" and not self.source_memory_ids:
            raise ValueError("summary recall fixtures require raw lineage")
        if len(set(self.source_memory_ids)) != len(self.source_memory_ids):
            raise ValueError("summary recall fixture lineage must be unique")
        return self


class RecallCase(_StrictModel):
    id: str = Field(pattern=r"^R[0-9]{2}$")
    provenance: Literal["owner-approved"]
    lane: Literal[
        "lexical",
        "semantic",
        "empty",
        "contradiction",
        "semantic-lineage",
        "summary-raw",
        "references",
        "multi-search-open",
        "identity-dedup",
    ]
    query: str = Field(min_length=1, max_length=512)
    must_select_ids: tuple[UUID, ...] = Field(max_length=20)
    must_open_ids: tuple[UUID, ...] = Field(max_length=20)
    max_selected: int = Field(ge=0, le=20)
    max_opened: int = Field(ge=0, le=20)
    min_search_calls: int = Field(ge=1, le=6)

    @model_validator(mode="after")
    def compact_bounds_cover_requirements(self) -> RecallCase:
        if len(set(self.must_select_ids)) != len(self.must_select_ids):
            raise ValueError("required selected memory IDs must be unique")
        if len(set(self.must_open_ids)) != len(self.must_open_ids):
            raise ValueError("required opened memory IDs must be unique")
        if len(self.must_select_ids) > self.max_selected:
            raise ValueError("selected-memory bound cannot exclude a requirement")
        if len(self.must_open_ids) > self.max_opened:
            raise ValueError("opened-memory bound cannot exclude a requirement")
        if self.lane == "empty" and (
            self.must_select_ids
            or self.must_open_ids
            or self.max_selected != 0
            or self.max_opened != 0
        ):
            raise ValueError("empty cases must require exactly zero memory")
        return self


class RecallObservation(_StrictModel):
    id: str = Field(pattern=r"^R[0-9]{2}$")
    selected_ids: tuple[UUID, ...] = Field(max_length=20)
    opened_ids: tuple[UUID, ...] = Field(max_length=20)
    search_calls: int = Field(ge=0, le=8)


class CaseScore(_StrictModel):
    id: str
    selected_pass: bool
    opened_pass: bool
    search_pass: bool
    duplicate_selected_ids: bool
    duplicate_opened_ids: bool
    passed: bool


class RecallScore(_StrictModel):
    cases: tuple[CaseScore, ...]
    selected_passed: int
    opened_passed: int
    search_passed: int
    passed: int
    total: int


def load_recall_set(
    memories_path: Path,
    cases_path: Path,
) -> tuple[tuple[RecallFixture, ...], tuple[RecallCase, ...]]:
    memories = tuple(
        RecallFixture.model_validate(value) for value in _json_lines(memories_path)
    )
    cases = tuple(RecallCase.model_validate(value) for value in _json_lines(cases_path))
    _validate_recall_set(memories, cases)
    return memories, cases


def load_observations(path: Path) -> tuple[RecallObservation, ...]:
    observations = tuple(
        RecallObservation.model_validate(value) for value in _json_lines(path)
    )
    if len({item.id for item in observations}) != len(observations):
        raise ValueError("recall observations contain duplicate case IDs")
    return observations


def score_recall(
    cases: tuple[RecallCase, ...],
    observations: tuple[RecallObservation, ...],
) -> RecallScore:
    by_id = {item.id: item for item in observations}
    if set(by_id) != {item.id for item in cases}:
        raise ValueError("recall observations do not match the frozen case IDs")
    scores: list[CaseScore] = []
    for case in cases:
        observation = by_id[case.id]
        duplicate_selected = len(set(observation.selected_ids)) != len(
            observation.selected_ids
        )
        duplicate_opened = len(set(observation.opened_ids)) != len(
            observation.opened_ids
        )
        selected_pass = (
            not duplicate_selected
            and set(case.must_select_ids).issubset(observation.selected_ids)
            and len(observation.selected_ids) <= case.max_selected
        )
        opened_pass = (
            not duplicate_opened
            and set(case.must_open_ids).issubset(observation.opened_ids)
            and len(observation.opened_ids) <= case.max_opened
        )
        search_pass = observation.search_calls >= case.min_search_calls
        scores.append(
            CaseScore(
                id=case.id,
                selected_pass=selected_pass,
                opened_pass=opened_pass,
                search_pass=search_pass,
                duplicate_selected_ids=duplicate_selected,
                duplicate_opened_ids=duplicate_opened,
                passed=selected_pass and opened_pass and search_pass,
            )
        )
    values = tuple(scores)
    return RecallScore(
        cases=values,
        selected_passed=sum(item.selected_pass for item in values),
        opened_passed=sum(item.opened_pass for item in values),
        search_passed=sum(item.search_pass for item in values),
        passed=sum(item.passed for item in values),
        total=len(values),
    )


def _json_lines(path: Path) -> Iterable[object]:
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                value: object = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path.name}:{line_number} is not valid JSON"
                ) from exc
            yield value


def _validate_recall_set(
    memories: tuple[RecallFixture, ...],
    cases: tuple[RecallCase, ...],
) -> None:
    if len(memories) != len({item.id for item in memories}):
        raise ValueError("recall fixtures contain duplicate memory IDs")
    if len(cases) != len({item.id for item in cases}):
        raise ValueError("recall cases contain duplicate case IDs")
    if len(cases) < 15:
        raise ValueError("recall evaluation requires at least fifteen cases")
    lane_counts = Counter(item.lane for item in cases)
    if lane_counts["semantic"] < 5:
        raise ValueError("recall evaluation requires five semantic cases")
    if lane_counts["lexical"] < 3:
        raise ValueError("recall evaluation requires three lexical cases")
    if lane_counts["empty"] < 3:
        raise ValueError("recall evaluation requires three empty cases")
    if lane_counts["contradiction"] < 1:
        raise ValueError("recall evaluation requires a contradiction case")
    if lane_counts["semantic-lineage"] < 1:
        raise ValueError("recall evaluation requires a summary-lineage case")
    by_id = {item.id: item for item in memories}
    referenced = {
        identity
        for case in cases
        for identity in (*case.must_select_ids, *case.must_open_ids)
    }
    if not referenced.issubset(by_id):
        raise ValueError("recall case references an unknown fixture memory")
    raw_ids = {item.id for item in memories if item.table_kind == "memory_log"}
    for fixture in memories:
        if not set(fixture.source_memory_ids).issubset(raw_ids):
            raise ValueError("summary fixture lineage must resolve directly to raw IDs")
    for case_id in ("R13", "R14"):
        case = next((item for item in cases if item.id == case_id), None)
        required = {
            UUID("00000000-0000-4000-8000-000000000011"),
            UUID("00000000-0000-4000-8000-000000000012"),
        }
        if case is None or set(case.must_open_ids) != required:
            raise ValueError(f"{case_id} must open both seeded raw summary sources")


__all__ = [
    "CaseScore",
    "RecallCase",
    "RecallFixture",
    "RecallObservation",
    "RecallScore",
    "load_observations",
    "load_recall_set",
    "score_recall",
]

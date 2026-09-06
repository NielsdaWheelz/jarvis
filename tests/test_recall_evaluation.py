from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from jarvis.recall_evaluation import (
    SEEDED_S01_ID,
    PostRebuildSummary,
    RecallObservation,
    bind_post_rebuild_s01,
    load_recall_set,
    score_recall,
)

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "eval" / "recall-memories.jsonl"
CASES = ROOT / "eval" / "recall.jsonl"


def _perfect_observations() -> tuple[RecallObservation, ...]:
    _, cases = load_recall_set(MEMORIES, CASES)
    return tuple(
        RecallObservation(
            id=case.id,
            selected_ids=case.must_select_ids,
            opened_ids=case.must_open_ids,
            search_calls=case.min_search_calls,
        )
        for case in cases
    )


def test_owner_approved_recall_set_is_frozen_and_has_required_coverage() -> None:
    memories, cases = load_recall_set(MEMORIES, CASES)

    assert len(memories) == 13
    assert len(cases) == 17
    assert {case.provenance for case in cases} == {"owner-approved"}
    assert next(case for case in cases if case.id == "R06").query == (
        "What units make kitchen instructions easiest for me to follow?"
    )
    assert next(case for case in cases if case.id == "R17").max_selected == 1


def test_explicit_ember_raw_and_summary_fixtures_are_byte_exact() -> None:
    memories, _ = load_recall_set(MEMORIES, CASES)
    by_id = {str(item.id): item for item in memories}

    assert by_id["00000000-0000-4000-8000-000000000011"].text == (
        "The synthetic Ember procurement matter is linked to a supplier email and "
        "review meeting. Current status must be checked in the live records before "
        "answering.\n\n"
        "<refs>\n"
        '  <ref uri="gmail://synthetic/message/ember-procurement-001">Supplier '
        "email</ref>\n"
        '  <ref uri="gcal://synthetic/event/ember-review-001">Review meeting</ref>\n'
        "</refs>"
    )
    assert by_id["10000000-0000-4000-8000-000000000001"].text == (
        "The synthetic Ember procurement review has an unresolved warranty "
        "comparison. Its supporting raw memories link an email and meeting that must "
        "be checked for current state."
    )


def test_perfect_compact_observations_score_every_lane_separately() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)

    score = score_recall(cases, _perfect_observations())

    assert score.total == 17
    assert score.selected_passed == score.total
    assert score.opened_passed == score.total
    assert score.search_passed == score.total
    assert score.passed == score.total


def test_return_everything_fails_compact_selection_and_empty_cases() -> None:
    memories, cases = load_recall_set(MEMORIES, CASES)
    all_ids = tuple(item.id for item in memories)
    observations = tuple(
        RecallObservation(
            id=case.id,
            selected_ids=all_ids,
            opened_ids=case.must_open_ids,
            search_calls=max(1, case.min_search_calls),
        )
        for case in cases
    )

    score = score_recall(cases, observations)

    assert score.selected_passed == 0
    assert score.passed == 0


def test_duplicate_selected_identity_fails_r17() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    observations = list(_perfect_observations())
    index = next(index for index, item in enumerate(observations) if item.id == "R17")
    identity = observations[index].selected_ids[0]
    observations[index] = observations[index].model_copy(
        update={"selected_ids": (identity, identity)}
    )

    score = score_recall(cases, tuple(observations))
    r17 = next(item for item in score.cases if item.id == "R17")

    assert r17.duplicate_selected_ids
    assert not r17.selected_pass
    assert not r17.passed


@pytest.mark.parametrize("case_id", ["R13", "R14"])
def test_lineage_cases_fail_without_both_opened_raw_sources(case_id: str) -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    observations = list(_perfect_observations())
    index = next(index for index, item in enumerate(observations) if item.id == case_id)
    observations[index] = observations[index].model_copy(
        update={"opened_ids": observations[index].opened_ids[:1]}
    )

    score = score_recall(cases, tuple(observations))
    result = next(item for item in score.cases if item.id == case_id)

    assert result.selected_pass
    assert not result.opened_pass
    assert not result.passed


def test_multi_search_case_requires_two_search_calls() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    observations = list(_perfect_observations())
    index = next(index for index, item in enumerate(observations) if item.id == "R16")
    observations[index] = observations[index].model_copy(update={"search_calls": 1})

    score = score_recall(cases, tuple(observations))
    r16 = next(item for item in score.cases if item.id == "R16")

    assert not r16.search_pass
    assert not r16.passed


def test_observation_accepts_the_exact_eight_call_recaller_plan_bound() -> None:
    observation = RecallObservation(
        id="R01",
        selected_ids=(),
        opened_ids=(),
        search_calls=8,
    )

    assert observation.search_calls == 8
    with pytest.raises(ValueError):
        RecallObservation(
            id="R01",
            selected_ids=(),
            opened_ids=(),
            search_calls=9,
        )


def test_post_rebuild_binds_s01_by_exact_flattened_raw_lineage() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    regenerated_id = UUID("20000000-0000-4000-8000-000000000001")

    bound = bind_post_rebuild_s01(
        cases,
        (
            PostRebuildSummary(
                id=regenerated_id,
                source_memory_ids=(
                    UUID("00000000-0000-4000-8000-000000000012"),
                    UUID("00000000-0000-4000-8000-000000000011"),
                ),
            ),
            PostRebuildSummary(
                id=UUID("20000000-0000-4000-8000-000000000002"),
                source_memory_ids=(UUID("00000000-0000-4000-8000-000000000001"),),
            ),
        ),
    )

    changed = {
        case.id for original, case in zip(cases, bound, strict=True) if original != case
    }
    assert changed == {"R13", "R14", "R16"}
    for case_id in changed:
        case = next(item for item in bound if item.id == case_id)
        assert regenerated_id in case.must_select_ids
        assert SEEDED_S01_ID not in case.must_select_ids
        assert set(case.must_open_ids) == {
            UUID("00000000-0000-4000-8000-000000000011"),
            UUID("00000000-0000-4000-8000-000000000012"),
        }
    assert cases == load_recall_set(MEMORIES, CASES)[1]


@pytest.mark.parametrize("count", [0, 2])
def test_post_rebuild_requires_exactly_one_s01_lineage_summary(count: int) -> None:
    _, cases = load_recall_set(MEMORIES, CASES)
    summaries = tuple(
        PostRebuildSummary(
            id=UUID(f"20000000-0000-4000-8000-{index:012d}"),
            source_memory_ids=(
                UUID("00000000-0000-4000-8000-000000000011"),
                UUID("00000000-0000-4000-8000-000000000012"),
            ),
        )
        for index in range(1, count + 1)
    )

    with pytest.raises(ValueError, match="exactly one summary"):
        bind_post_rebuild_s01(cases, summaries)


def test_post_rebuild_rejects_summary_identity_conflicting_with_raw_fixture() -> None:
    _, cases = load_recall_set(MEMORIES, CASES)

    with pytest.raises(ValueError, match="conflicts with a frozen raw identity"):
        bind_post_rebuild_s01(
            cases,
            (
                PostRebuildSummary(
                    id=UUID("00000000-0000-4000-8000-000000000011"),
                    source_memory_ids=(
                        UUID("00000000-0000-4000-8000-000000000011"),
                        UUID("00000000-0000-4000-8000-000000000012"),
                    ),
                ),
            ),
        )


def test_post_rebuild_summary_lineage_must_be_unique() -> None:
    identity = UUID("00000000-0000-4000-8000-000000000011")

    with pytest.raises(ValueError, match="lineage must be unique"):
        PostRebuildSummary(
            id=UUID("20000000-0000-4000-8000-000000000001"),
            source_memory_ids=(identity, identity),
        )

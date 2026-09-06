from __future__ import annotations

import json
import stat
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import pytest

from jarvis.rebuild import rebuild_derived_memory
from jarvis.recall_evaluation import (
    RecallObservation,
    load_recall_set,
    score_recall,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_dreaming.py"))
embedding_credential_absent = cast(
    "Callable[[Mapping[str, str], str], bool]",
    _QUALIFIER["embedding_credential_absent"],
)
PHASE_EVIDENCE_FILENAME = cast(str, _QUALIFIER["PHASE_EVIDENCE_FILENAME"])
record_phase_evidence = _QUALIFIER["record_phase_evidence"]


def test_live_spawn_observation_rejects_embedding_credential_name_or_value() -> None:
    assert embedding_credential_absent(
        {"HOME": "/synthetic/private"}, "synthetic-embedding-key"
    )
    assert not embedding_credential_absent(
        {"JARVIS_EMBEDDING_OPENAI_API_KEY": "unrelated"},
        "synthetic-embedding-key",
    )
    assert not embedding_credential_absent(
        {"SYNTHETIC_UNRELATED": "synthetic-embedding-key"},
        "synthetic-embedding-key",
    )


async def test_pre_score_artifact_survives_an_injected_later_rebuild_failure(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "private-runtime"
    runtime.mkdir(mode=0o700)
    evidence_path = runtime / PHASE_EVIDENCE_FILENAME
    _, cases = load_recall_set(
        ROOT / "eval" / "recall-memories.jsonl",
        ROOT / "eval" / "recall.jsonl",
    )
    score = score_recall(
        cases,
        tuple(
            RecallObservation(
                id=case.id,
                selected_ids=case.must_select_ids,
                opened_ids=case.must_open_ids,
                search_calls=case.min_search_calls,
            )
            for case in cases
        ),
    )
    records: list[dict[str, object]] = []

    class FailingStore:
        async def raw_snapshot(self, maximum_rows: int) -> object:
            del maximum_rows
            raise RuntimeError("injected failure after pre score")

    async def evaluate(selected: object) -> object:
        assert selected == cases
        return score

    async def dream(as_of: object) -> object:
        del as_of
        raise AssertionError("failure must occur before dreaming")

    with pytest.raises(RuntimeError, match="injected failure after pre score"):
        await rebuild_derived_memory(
            store=cast(Any, FailingStore()),
            embedder=cast(Any, object()),
            cases=cases,
            evaluate=cast(Any, evaluate),
            dream_once=cast(Any, dream),
            record_score=lambda phase, value: record_phase_evidence(
                evidence_path,
                records,
                phase,
                value,
            ),
            maximum_memory_rows=100,
        )

    assert stat.S_IMODE(evidence_path.stat().st_mode) == 0o600
    value = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert value == {
        "phases": [
            {
                "aggregate": {
                    "opened_passed": 17,
                    "passed": 17,
                    "search_passed": 17,
                    "selected_passed": 17,
                    "total": 17,
                },
                "cases": [
                    {
                        "id": f"R{index:02d}",
                        "opened_pass": True,
                        "passed": True,
                        "search_pass": True,
                        "selected_pass": True,
                    }
                    for index in range(1, 18)
                ],
                "phase": "pre_rebuild",
            }
        ],
        "schema_version": "jarvis-slice-4-recall-phase-evidence.v1",
    }
    assert "usage" not in evidence_path.read_text(encoding="utf-8")

"""Validate and score the frozen owner-approved Slice 3 recall set."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from jarvis.recall_evaluation import (
    bind_post_rebuild_s01,
    load_observations,
    load_post_rebuild_summaries,
    load_recall_set,
    score_recall,
)

ROOT = Path(__file__).resolve().parents[1]
MEMORIES = ROOT / "eval" / "recall-memories.jsonl"
CASES = ROOT / "eval" / "recall.jsonl"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--post-rebuild-summaries", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    memories, cases = load_recall_set(MEMORIES, CASES)
    if arguments.post_rebuild_summaries is not None:
        if arguments.observations is None:
            parser.error("--post-rebuild-summaries requires --observations")
        cases = bind_post_rebuild_s01(
            cases,
            load_post_rebuild_summaries(arguments.post_rebuild_summaries),
        )
    if arguments.observations is None:
        print(
            json.dumps(
                {
                    "cases": len(cases),
                    "fixtures": len(memories),
                    "provenance": "owner-approved",
                    "status": "valid",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    result = score_recall(cases, load_observations(arguments.observations))
    print(
        json.dumps(
            result.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if result.passed == result.total else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Slice 3 recall evaluation

The 17 redacted, synthetic-safe cases in `recall.jsonl` and the 13 rows in
`recall-memories.jsonl` were explicitly approved by the owner on 4 September
2026 before retrieval or prompt tuning. They are owner-approved, not
owner-authored.

The `memory_summary` row conventionally called S01 is a seeded evaluation
fixture. Slice 3 does not grant summary-writing authority; summary creation and
rebuild remain Slice 4 work.

Validate the frozen corpus, or score a bounded observation file, with:

```sh
uv run python scripts/evaluate_recall.py
uv run python scripts/evaluate_recall.py --observations /path/to/observations.jsonl
```

Selection and opened-source identities are scored separately. Empty cases
require no selected memory, duplicate identities fail, and every positive case
has a compact maximum. R13 and R14 require both raw sources behind S01; R16
requires multiple searches plus source opening; R17 requires one exact selected
identity despite lexical/vector overlap.

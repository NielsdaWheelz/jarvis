# ADR 0002: Preserve raw memory; rebuild every interpretation

- Status: Accepted
- Date: 2026-09-01

## Context

An earlier design proposed distinct evidence, episode, claim, procedure,
projection, entity, provenance, temporal-validity, and confidence layers. Those
concepts can matter in large knowledge systems, but implementing and enforcing
them would add substantial infrastructure and could constrain rather than improve
agent reasoning.

[Victor Taelin's OptMem](https://github.com/VictorTaelin/OptMem) demonstrates a
smaller principle: preserve a canonical append-only log and treat model-generated
summaries as disposable, progressively retrievable views.

What is adopted from it is exactly that principle and nothing else. Its
positional summary tree, its coverage relationship between the log and the tree,
and its retrieval mechanics are **not** adopted; Jarvis uses a flat summary table
with flattened raw lineage, and the recaller searches raw rows directly. The
citation explains where the idea came from. It is not a specification by
reference, and nothing in OptMem is binding here.

## Decision

Use two logical tables for the memory subsystem:

```text
memory_log(id, text, created_at, embedding)
memory_summary(id, text, source_memory_ids, created_at, embedding)
```

`memory_log` is permanent and append-only during normal operation.
`memory_summary`, embeddings, and search indexes are rebuildable.

Rememberer appends raw natural-language memories. Recaller runs before every
human input and combines full-text and semantic search. Dreamer constructs and
maintains summaries without mutating raw memory.

Every summary resolves directly to the raw memory IDs that support it. External
Gmail, Calendar, Maps, Discord, Nexus, and Skidbladnir targets live as stable
references in natural-language memory text rather than domain tables.

## Consequences

Positive:

- Consolidation cannot destroy the raw substrate.
- Summary and embedding models can improve without data migration semantics.
- Recall remains useful if the dreamer or summary table is lost.
- Memory behavior is primarily improved through prompts, models, retrieval, and
  evaluation rather than schema work.

Accepted costs:

- Raw memory grows indefinitely under normal operation.
- Model-made memories may contain mistakes or contradictions.
- Retrieval and summarization must cope with repetition.
- Current external truth still requires live tools.
- V1 has no erasure mechanism. Designing one safely requires accounting for
  messages, actions, backups, provider state, Discord, and external systems, not
  just punching an exception through the raw-memory invariant.

## Rejected alternatives

- Destructive consolidation: memory quality would depend irreversibly on dreamer
  output.
- Vector-only memory: exact names and rare terms need lexical search.
- A temporal fact database: too much representational machinery for v1.
- One mutable summary document: poor lineage and too much overwrite risk.
- Raw transcript as the only memory: too verbose and insufficiently selective.

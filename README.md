# Jarvis

Jarvis is a personal, persistent AI assistant for one user. It lives primarily
in its own Discord server, uses the user's existing Gmail, Google Calendar,
Google Maps, and Discord integrations, and develops durable memory through a
simple remember/retrieve/dream loop.

This repository is intentionally specification-first. No implementation is
present yet.

## V1 in one paragraph

Jarvis converses naturally in Discord, recalls relevant memories before every
human turn, uses connected tools, acts automatically for reads and ordinary
reversible work, asks for a simple Approve or Deny decision before consequential
communication to another person, and appends useful memories after interactions.
Conversation history is centralized independently of Discord. Raw memories are
permanent. Summaries, embeddings, and indexes are rebuildable.

Jarvis owns exactly four application tables:

```text
message
memory_log
memory_summary
action
```

## Authoritative documents

1. [V1 specification](SPEC.md) — normative product and engineering contract.
2. [Architecture](docs/architecture.md) — runtime, component, data, and tool
   boundaries.
3. [Memory](docs/memory.md) — exact rememberer, recaller, and dreamer behavior,
   plus the physical schema and the recall evaluation set.
4. [Acceptance](docs/acceptance.md) — the definition of done, and the single
   completion predicate for v1.
5. [Implementation plan](docs/implementation-plan.md) — ordered, independently
   acceptable slices.
6. [Decision records](docs/decisions/) — why the current design exists.

When documents disagree, `SPEC.md` wins. Changing a frozen decision requires an
ADR that also updates every affected normative document in the same change.

## Status

- Baseline date: 2026-09-01
- Status: v1 specification frozen; implementation not started
- Intended deployment: personal, single-user, always-on Linux service
- Primary client: dedicated private Discord server
- Model provider: subscription-backed Codex through `provider-runtime`

## Explicit non-goals

- A general multi-user assistant platform
- A visible society of named agents
- A project-management database or personal knowledge graph
- A workflow-engine deployment
- A mobile application in v1
- Web search or browsing in v1
- Rebuilding integrations that already work
- Broad speculative integration work

## Stated trade-offs

These are accepted knowingly, not overlooked.

- Discord is a third-party processor for every conversation, every quoted
  memory, every summarized email, and every approval preview.
- The complete raw memory corpus is disclosed to the embedding processor; see
  [ADR 0008](docs/decisions/0008-embedding-source.md).
- One subscription pool is a single point of total conversational outage, with
  no fallback by design.
- Every foreground turn needs recall plus the main-agent call, while remembering
  follows asynchronously. This is slower and more expensive than a stateless
  chat response.
- Raw memory grows without bound and model-made memories can be wrong.
  Correction is by append; v1 deliberately has no erasure mechanism.
- Conversational Discord delivery is at least once, so a crash at the delivery
  boundary can repeat a response. Effectful actions remain independently
  idempotent.
- A one-user system has no second reviewer. The owner is simultaneously the
  builder, the auditor, and the beneficiary, which instrumentation mitigates and
  nothing removes.

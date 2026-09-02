# Jarvis

Jarvis is a personal, persistent AI assistant for one user. It lives in one
configured private Discord channel, uses the user's existing Gmail, Google
Calendar, Google Maps, and Discord integrations plus bounded public-Web tools,
and develops durable memory through a simple remember/retrieve/dream loop.

This repository is intentionally specification-first. No implementation is
present yet.

## V1 in one paragraph

Jarvis converses naturally in Discord, recalls relevant memories before every
human turn, uses connected tools, acts automatically for reads and ordinary
reversible work, asks for a simple Approve or Deny decision before consequential
communication to another person, and appends useful memories after interactions.
Conversation history is centralized independently of Discord. Raw memories are
permanent. Summaries, embeddings, and indexes are rebuildable. One main Codex
session normally continues across turns and restarts, while a provider-neutral
kernel reconstruction path can restore it from canonical messages and recalled
memory.
Jarvis is the first consumer of the independent `llm-agent-kernel` library:
Jarvis chooses product context and policy, while the library supplies the
bounded whole-step/drain machinery around `provider-runtime` and `llm-tools`.

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
- Primary client: one configured channel in a dedicated private Discord server
- Agent runtime: pinned `llm-agent-kernel`, using subscription-backed Codex
  through `provider-runtime` and host tools through `llm-tools`

## Explicit non-goals

- A general multi-user assistant platform
- A visible society of named agents
- General subagent delegation or a model-generated program runtime in v1
- A project-management database or personal knowledge graph
- A workflow-engine deployment
- A mobile application in v1
- Authenticated browsing, browser automation, or unrestricted Web access
- Rebuilding integrations that already work
- Broad speculative integration work
- Multiple Discord channels, threads, direct messages, or server organization in
  v1

## Stated trade-offs

These are accepted knowingly, not overlooked.

- Discord is a third-party processor for every conversation, every quoted
  memory, every summarized email, and every approval preview.
- The complete raw memory corpus is disclosed to the embedding processor; see
  [ADR 0008](docs/decisions/0008-embedding-source.md).
- One subscription pool is a single point of total conversational outage, with
  no fallback by design.
- Every owner-authored foreground turn needs recall plus the main-agent call,
  while remembering follows asynchronously. This is slower and more expensive
  than a stateless chat response.
- Conversation, approvals, and proactive notices interleave in one Discord
  channel. Multiple channels are deferred until that produces a measured
  problem.
- Public search queries are disclosed to Brave, and public page reads disclose
  the requested URL and host IP to the destination. The tools send no connector
  credentials or cookies and do not provide authenticated or JavaScript browsing.
- Codex session history, compaction, and cache behavior are non-canonical
  optimizations. A changed session-scoped contract or lost session takes a cold
  context bootstrap, and no cost saving is guaranteed.
- Extracting the generic run loop adds a third pinned local-library boundary.
  In return, crash/race semantics, strict protocol handling, and provider-neutral
  reconstruction have one reusable conformance contract instead of becoming
  Jarvis-specific orchestration.
- Raw memory grows without bound and model-made memories can be wrong.
  Correction is by append; v1 deliberately has no erasure mechanism.
- Discord deduplicates a stable per-message nonce only within a recent window.
  Jarvis reconciles delayed retries through channel history; if that check is
  unavailable, delivery waits rather than risking a duplicate. A Discord service
  defect or inconsistent history remains outside Jarvis's guarantee.
- Discord transport uses `discord.py` for Gateway/interactions and one direct
  REST create binding because the qualified client does not expose enforced
  nonces; this small split remains until its public API can replace the binding.
- Some providers cannot prove whether every timed-out external effect committed.
  Jarvis exhausts provider-specific automatic reconciliation first, then records
  terminal `uncertain` and asks the owner to inspect rather than retrying blindly.
- A one-user system has no second reviewer. The owner is simultaneously the
  builder, the auditor, and the beneficiary, which instrumentation mitigates and
  nothing removes.

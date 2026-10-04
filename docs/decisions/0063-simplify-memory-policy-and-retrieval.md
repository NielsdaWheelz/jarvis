# adr 0063: simplify memory policy and retrieval

- status: accepted implementation target, 2026-10-01; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved six further simplifications, agent discretion
  instead of mandatory steps, and global policy/resource ownership with reuse.
- supersedes affected activation, native parsing, ranking, dreamer procedure,
  status-tool and per-client limits in adrs 0051/0054/0058/0059/0060/0062.
  main's durable effect/read recovery and host authority remain binding.
- current implementer contract: [universal memory](../universal-memory.md).

## evidence

the existing repository already retrieves lexical/vector candidates and deduplicates
identities. learned ranking was an unselected second model dependency without
measured benefit here. pending-note dreaming supplies evidence before a tool call,
yet the old worker rejects completion without a search. manual activation requires
an inventory transfer and stopped service despite a transaction already owning its
receipt and baselines. strict parsing of unused native metadata causes avoidable
breakage. profile-specific quotas protect one user's shared resources.

## decision

1. use equal-weight reciprocal-rank fusion of the global top 50 candidates in
   each mode: sum `1 / (60 + one_based_rank)`, absent mode contributing zero;
   ties use `(store, id)`. keep the existing per-mode order and identity union.
   no learned reranker, second processor, dormant path or fallback. main search
   needs at most one external attempt; dreamer retains eight, not sixteen.
2. activate admitted native lanes automatically online. collectors submit a
   complete content-free head inventory through an activation variant of sync,
   within the common body bound. atomically store receipt and all baselines;
   retries of active lanes return the original receipt. no inventory file,
   manual activation command, stopped jarvis or staging table. incomplete or
   oversized inventories leave the lane pending; never lazily baseline threads.
3. strictly validate consumed native semantics, while ignoring unrelated additive
   diagnostic/transport fields. both derived event identity and `native_digest`
   exclude ignored metadata; the digest binds the capture-relevant projection
   before secret redaction. normalized wire schemas and model/tool inputs remain
   closed. unknown kinds stay explicit gaps; ambiguous required fields fail.
4. give agents context, available tools, goals and quality constraints; let them
   choose their method. remove mandatory-first-tool, search-count and scripted
   research/delegation requirements. the dreamer may produce seed-only synthesis
   or empty success without tools. permissions, evidence/lineage checks, protocol,
   current-owner grounding, approval and atomic commits remain host preconditions.
5. keep content-free operational status in the operator cli. remove `memory_status`
   from mcp and its model-facing report schema. retain useful diagnostics.
6. use one global search limit: 30 accepted service executions per rolling minute
   across main, dreamer and mcp. authorization/input/grants precede counting;
   accepted failures count, rate rejection performs no provider call, stored
   receipt replay consumes no new allowance. no per-client quota or durable
   short-window rate ledger.

## global ownership and reuse

define policy once as checked-in globals at its owner. reuse existing settings,
validators, serializers, SQL transactions, clocks and bounded execution primitives;
centralize shared memory constants/types in a small dependency-free module.
construct shared clients, repositories, pools and services once at the existing
composition root. all callers use those same instances and policy; no profile
variants or forwarding frameworks. one embedding inference semaphore covers
queries, indexing and rebuild, with no additional search-only semaphore. busy
returns a typed zero-attempt result immediately; no queue that can expire into
false paid-call uncertainty.

keep the existing global cognitive admission, deployment lock and serial dispatch.
resource limits with different units keep their existing owners; a search is not
a new root cognitive turn. each invocation gets fresh budget/transaction state
from the shared policy. provenance, lane authorization, conversation progress and
receipts describe distinct subjects and must not be collapsed into shared mutable
turn state. this is centralized ownership, not arbitrary import-time singletons.

use one embedding client/runtime with explicit one-attempt public retry policy;
ordinary later indexing sweeps supply retry. the
[existing retry-accounting discrepancy](../issues/embedding-retry-accounting.md)
is recorded separately; disabling sdk retries alone would not repair it.

## accepted costs

- deterministic fusion may order nuanced evidence worse than learned ranking.
  benchmark observed misses before adding another model; no quality parity claim.
- activation occurs at the first successful baseline. a pre-commit failure may
  move the eventual cut later, excluding that earlier history. a busy native lane
  may need a quiet period; an inventory exceeding the bound needs an explicit
  bound revision. jarvis itself need not stop.
- unmapped added metadata is not archived. native identity, attribution, text,
  reasoning exclusions and memory-tool suppression must still be understood.
- discretionary search can miss older connections or yield redundant summaries.
  lineage and output quality remain required; prescribed steps do not establish
  either.
- agents lose fleet self-diagnosis through a memory tool; the operator retains it.
- all callers compete for shared search/embedding resources. one busy caller can
  consume the search allowance; indexing may make a query return busy. restart resets the
  process-local minute counter. durable cognition accounting remains unchanged.

## cutover and acceptance

no runtime change in this doc update. update the shared binding revision and
plans, remove unimplemented reranker/status/manual-activation paths from the
handoff, and drain incompatible old cognition under the existing stopped cutover.
no compatibility branch or restored test framework.

focused checks cover exact fusion/ties, shared limits across callers, replay
without new charges, one actual embedding attempt, zero-search dream completion,
activation before/after-commit failures and late turns, additive metadata stability,
and failure on malformed consumed fields. preserve idempotent saves, main effect
recovery, scoped provenance and atomic progress.

# ADR 0040: Shared kernel with durable inference and Read positions

- Status: **Accepted**
- Date: **2026-09-09**
- Owner approval: approved the complete shared-kernel cutover and strict fixes for
  issues encountered in its implementation.
- Amends: the four-table limit, provider selection, recoverable inference, and
  deployment ownership transaction boundary.

## Decision

Use llm-agent-kernel `35f42b91bc214f556c1b5b6a36d9629ed00e574d`, provider-runtime
`8fde23ac56571a63c65cfcff55c73a0976f83eb4`, and llm-tools
`9e6d155f3b64f03495911435b7cae8b8d131f9a2`. Resolve an authenticated exact Codex
catalog row and reasoning choice at startup. Freeze all four catalog facts in
ProviderConfiguration; no raw model alias or inferred catalog metadata remains.

Add `model_decision` for the shared kernel's original request/terminal contract.
Its stable scope and ordinal determine decision identity; its request fingerprint
binds original ordered inputs, checkpoint, clock, definition/plan, counters, and
canonical/submitted context. Commit uncertainty before entering the provider.
Commit the exact normalized terminal and bounded Jarvis host evidence together
before dependent work. Never retry unknown inference automatically. Reopen
completed decisions without another provider call; current contract mismatch
blocks new dependent work. Restore claim lineage before retry/poison decisions.

Preserve Main Calendar incompleteness/material observations and isolated memory
candidate/opened/search evidence in the same terminal transaction. Restore these
app-owned validation facts before applying the existing strict result validators.
The kernel does not acquire a generic application-evidence schema.

Add `read_position` implementing the existing llm-tools PositionRecorder contract.
Stable model decision positions and stable isolated initial-read positions survive
restarts. Reservations, dispatch uncertainty, exact terminal results, and settlement
are durable. Completed results replay; unknown Reads stop. This closes the paid
Maps, Brave, and memory-embedding repetition gap without weakening Write actions.
Restore accepted Read reservations and settlements in initial-read/model ordinal
order into the existing BudgetState before further tools. Rejected reservations
remain uncharged. Calls, attempts, and bytes retain the logical scope's frozen cap;
elapsed time retains the existing active-invocation monotonic contract. Process
downtime does not consume a new durable wall deadline. No second budget ledger
or timeout wrapper is introduced. Original action recovery closes accepted Write
input scopes before model replay, including the approval suspension commit gap.

Main claim scope uses its thread and first original input. Recall uses its original
owner UUID; rememberer its ordered settled-owner group; write gate the original
Main decision ID. Dreamer admits work from one canonical raw/summary identity
snapshot. It retains the original deterministic job identity and clock on replay.
An unchanged snapshot cannot cause another paid maintenance decision; a changed
snapshot admits distinct work. Unresolved action recovery remains prior authority.

Run all consequential store transactions on the existing dedicated connection that
holds deployment ownership. Serialize short transactions with one asyncio lock;
no external call holds a transaction. The lock is session-scoped across commits.
Closed, invalidated, and released owners cannot reconnect, including during cleanup.
No lease table, distributed scheduler, or workflow framework is introduced.

## Historical fidelity and trade-offs

Keep the existing immutable action ExecutionContract unchanged. Its original tool,
arguments, plan/binding revisions, authority, and stable effect identity remain the
only action recovery authority. A definition fingerprint cannot honestly be
backfilled into historical actions; the new model journal already owns that fact.
New definition mismatches block model replay, while original authorized action
reconciliation remains governed by the existing action contract.

The application now has six tables. Private storage grows with bounded original
model context, results, and validation evidence. Serial database transactions
reduce potential throughput; the one-owner prototype does not need concurrent
writers. Refusing unknown paid work trades availability for truthful billing and
effect semantics. Dreaming once per immutable snapshot avoids redundant payment
and repeated no-change maintenance. These records are durable application truth,
not a promise that provider inference or arbitrary external effects are exactly
once. The provider may have completed work whose response never arrived.

## Cutover and verification

Migration 0004 adds the two stores without altering historical action contracts.
New session compatibility and exact dependency pins cold-boot old native sessions.
There is no legacy kernel/provider fallback. Use normal stopped-owner migration,
then the exact frozen release gates before activation.

Behavioral tests cover journal reopen, original claim restoration before poison,
immutable completion, forbidden unknown redispatch, original Read replay, owner
loss blocking model/read/action/publication, and service restart after accepted
terminal but before publication. Diagnostic probes explicitly disclaim recovery.
Docker Desktop VM failures interrupted local PostgreSQL qualification; final Linux
CI evidence is required and is not replaced by these local unit tests. Paid/live
provider probes and deployment remain separate, explicitly unrun gates.

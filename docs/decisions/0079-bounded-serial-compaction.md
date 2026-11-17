# adr 0079: bounded serial compaction

status: accepted, 2026-11-16, by explicit owner decision during installed f2
qualification. supersedes the single-source inference and 512-byte free-copy
policy in the memory contract, and adr 0078's decision against a throughput
change. adr 0078's two resets and all remaining f2 acceptance stay binding.

## evidence

the preliminary reset removed the old central corpus and established fresh
native cuts. comparison of all 1,885 subsequently captured native parts against
the old 39,825 parts found no repeated source identity. much of this genuine new
work arrived while canonical cognition was paused. this is evidence of backfill
cost, not demonstrated steady-state throughput failure.

the stopped fresh corpus has 1,888 leaves and coverage through 31. exact complete
source measurement of the 1,857 missing leaves finds 716 at most 512 bytes, 809
between 513 and 2,048, and 332 above 2,048. the current free-copy rule therefore
requires 1,141 leaf inferences before parent/retry work. the new rule removes 809
of those required leaf inferences; it does not establish an elapsed-time estimate.

## decision

copy a complete source verbatim when it fits the existing 2,048-byte hard node
bound. retain the 512-byte target for inferred summaries and the existing view
allocation. preserve all admitted originals, fixed personal-subscription models,
full-history main preparation, source cuts and existing atomic progress.

one serial compactor may infer up to eight independent ready nodes in one
isolated call. free copies do not consume those eight slots. initial and retry
calls pack whole entries under the unchanged 262,144-byte prepared-request
ceiling, retaining complete sources and feedback. one caller-side measurement
counts actual framing and escaping through the existing kernel preparation
primitive. an additional proposed 64,000-byte source cap was discarded: it would
duplicate that authority without satisfying another requirement. token,
candidate, retry and isolated-role ceilings remain binding. a smaller call,
including one node, uses the same contract; the whole selected batch commits
atomically after all its calls succeed.

the memory library owns readiness, complete immutable task sources, shared frozen
context and atomic completion validation. deterministic copies can share the
batch and wait for its completion. commit them before selecting newly enabled
parents. the ready cache learns only committed nodes. inferred tasks in a batch
depend only on already committed children.
validate the exact complete set of addressed results and their source identities
before inserting any node; advance persisted frontiers in the same transaction.
hard-cut the old single-task producer interface. add no table, daemon, parallel
worker, durable job/retry ledger or orchestration framework.

use one bounded earlier context prefix for the batch. separately supply every
task's complete own source. summaries may resolve references from that prefix;
they must not import facts from another task's source. later sibling sources are
visible within the batch: this explicitly supersedes physical isolation from
later material for these inference calls. retries include only unfinished size
candidates, with their original sources and existing per-node limits. malformed
or incomplete addressed output never partially commits a batch.

## consequences

larger exact free nodes can consume the fixed view budget sooner and coarsen
older detail earlier. batching exposes later sibling material to earlier output;
own-source attribution needs meaningful content proof. interruption may repeat
up to eight uncommitted summaries. none of these changes removes an original or
allows a stale main view. the owner explicitly accepted these trade-offs.

f2 owns temporary integration/live red/green/refactor proof, independent review,
new source/pin qualification and installed acceptance. remove its new probes
after proof; adapt the retained regression groups to the replacement interface.
report actual costs and limits without claiming unmeasured speedup or broad
memory usefulness. the [memory contract](../universal-memory.md#views-and-compactor-execution)
owns the interface and policy; the [roadmap](../implementation-plan.md#v2-finishing-prs)
remains the sole delivery sequence.

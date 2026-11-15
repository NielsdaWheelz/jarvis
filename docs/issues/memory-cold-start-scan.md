# memory collector cold-start latency

status: owner requested investigation and completion on 2026-11-15; repair in progress.

problem: a restarted stateless collector revisits eligible conversations in each
configured home before reaching later homes. native reads can traverse long
prefixes to verify event identity and the stored boundary/checkpoint. initial
activation of a later lane waits behind those reads.

impact: capture and new-lane activation can lag by hours on the owner's
existing corpus. successful reads continue; this is separate from missing native
files or an invalid capture boundary. activity before a new lane's actual cut is
still excluded under the future-only contract.

evidence: after the qualified 0fc3d64 restart, macbook had 2,183 claude-work
conversations, then further claude/codex homes ahead of codex-work2. at 18:11 utc,
1,095 claude-work conversations had been revisited; at 18:21 utc the collector
had reached 217 of 317 codex-personal conversations, with 1,203 codex-work still
ahead. dev-server likewise traversed earlier homes before its work2 inventory.
central commits continued and established codex lanes had no parked captures.
independent provider review found the history/pagination implementation unchanged
from adf1b71 to 70178ec. each successful baseline reads the history twice;
paginated native history uses roughly one rpc per item per pass, serially.
repeated cursors fail and each rpc has a timeout, but the whole inventory has no
elapsed deadline. unreadable entries previously aborted before later histories;
retaining them as pending now exposes the full cost of the remaining reads.
the initial head inventory publishes no per-head progress before its atomic
activation receipt. process activity and absence of retry logs therefore cannot
establish its current cursor or a reliable completion estimate.
at 19:55 utc, dev-server work2's first inventory had run for approximately 97
minutes without a receipt. the same collector process remained alive and a
separate metadata-only endpoint request succeeded; neither proves scan progress.
installed dev-server work2 capture acceptance remains open.

investigation: the first inventory committed at 21:59:08 utc, about 3 hours
41 minutes after it began: 190 established boundaries, all modern native ids,
and 21 unavailable baselines. there were no legacy heads in that group. the
normal synthetic turn finished at 21:59:32; at 23:01 it was still undiscovered.
the collector was still in its first sweep, rereading excluded prefixes to prove
empty tails. discovery sync pages are interleaved with content reads, homes are
serial, and a sweep exceeding one hour expires earlier hints before the next pass.

for this modern format, each one-item rpc resolves native rollout lineage before
reading indexed items. the provider repeats that cost across the entire old
prefix even when its exact boundary is already established. upstream codex
defines completed native items as immutable; only legacy identities require a
prefix hash chain. adversarial review nevertheless rejected reverse traversal:
a later oversized native item could prevent reaching an earlier unfinished
barrier and prematurely park its otherwise-readable prefix.

the scoped repair batches forward native item pages under the unchanged bounds.
an oversized multi-item response retries the same cursor with a smaller page;
only a single-item overflow keeps the existing refusal. this preserves full
prefix validation and forward unfinished-item semantics. it reduces round trips
and repeated native lineage resolution; it does not eliminate prefix decoding
or promise fast fresh-baseline proof. the
[active plan](../implementation-plan.md#native-capture-read-repair) owns delivery.

reproduce with an ordinary collector restart and content-free lane/read progress
observations. no broad load experiment was run. record native terminal→discovery
and discovery→archive/open separately. preserve complete identity coverage,
native event/digest verification, immutable cuts and exactly-once ingestion.
do not skip histories, weaken provenance or add a second collector to hide delay.

resolved when: the repaired normal journey and cold restart demonstrate useful
discovery/capture latency with the capture invariants intact. report remaining
fresh-baseline and large-new-backlog costs separately; one passing small turn
does not resolve those broader limits.

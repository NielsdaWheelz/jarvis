# memory collector cold-start latency

status: observed during the 2026-11-15 rollout; follow-up after functional delivery.

problem: a restarted stateless collector revisits eligible conversations in each
configured home before reaching later homes. native reads can traverse long
prefixes to verify event identity and the stored boundary/checkpoint. initial
activation of a later lane waits behind those reads.

impact: capture and new-lane activation can lag by tens of minutes on the owner's
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

reproduce with an ordinary collector restart and content-free lane/read progress
observations. no broad load experiment was run. investigate native checkpoint
navigation and home scheduling in the deferred performance/usefulness pass;
first define the acceptable capture delay. preserve complete identity coverage,
native event/digest verification, immutable cuts and exactly-once ingestion.
do not skip histories, weaken provenance or add a second collector to hide delay.

resolved when: the agreed cold-start bound is demonstrated across the configured
homes, including a newly admitted later lane, with the capture invariants intact.

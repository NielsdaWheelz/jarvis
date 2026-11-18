# adr 0078: fresh-corpus-first acceptance

status: accepted, 2026-11-16, by explicit owner decision during installed f2
qualification. supersedes adr 0077's acceptance-before-reset ordering and its
pre-migration full-artifact retention through acceptance; all other requirements
remain binding.

## evidence

the genuine owner fixture reached canonical history, but main waited for its
complete admitted-memory view before native dispatch. stopped metadata contains
39,873 leaves with `view_through=2238`; at least 15,257 missing leaves require
serial model compression, plus parent and retry work. the
[original operational analysis](https://github.com/NielsdaWheelz/jarvis/blob/5fa9897af4e28c3cf2ab91b133c79e5d2bd737cc/docs/issues/memory-preparation-backlog.md)
records the source proof. this is a material preparation backlog, not a demonstrated deadlock, and
provides no completion-time estimate. the original ordering made that historical
backfill a prerequisite for a journey intended to precede clearing the same data.

## decision

after qualified source integration and the stopped `0013` cutover, perform a
preliminary fresh reset, run the real production journey on that fresh corpus,
then perform the final fresh reset after acceptance. the owner approved this
order instead of the historical backfill or a new throughput change.

both resets use [f2's existing finite procedure](../runtime-reliability-and-integration.md#e-fresh-history-resets),
not a new runtime capability. before the first wipe, use existing canonical
controls to stop/disposition the pending fixture and cancel unentered work;
stopped does not mean completed. finish/reconcile entered work, drain the outbox,
quiesce writers and retain the private stopped `0013` inventory/recovery snapshot.
the three separately reviewed finalized retired `agent.stop` uncertainties retain
their exact original private evidence and unknown-effect status; they never
become known or replayable. current or unreviewed unknown effects remain blockers.

retain one verified current recovery artifact. temporarily move the old `0008a`
artifact outside the snapshot helper's parent, create the stopped `0013` dump and
private-state/configuration copies, then run the unchanged helper's verification
and dump listing before disposing of the superseded full artifact. f2 states the
verification's exact limits. retain original manifests,
hashes, retarget receipts and the exact historical uncertainty rows/receipts
outside the replaced full artifacts. before the final wipe, replace the first `0013`
artifact with the then-current stopped `0013` state the same way. never overwrite
or delete the predecessor before its successor verifies. this is bounded recovery
replacement, not indefinite backup retention or a new snapshot framework.

retain actual journey outcomes and recovery evidence before the final wipe.
both resets clear the configured discord/jarvis/all central shared history and
commitments, preserve schema/grants/guards, initialize fresh paused control and
establish current source cuts before new writers resume. preserve private repos,
credentials, real google data and original native/nexus chats. all other adr 0077
requirements, isolated fault proof and installed journey acceptance remain binding.
this authorized two bounded administrative operations. [adr 0085](0085-preserve-google-cursors-during-correction.md)
subsequently authorizes one further stopped correction retaining verified google cursors.

## consequences

the first reset intentionally precedes installed journey acceptance; retain
preliminary observations without representing them as a passed journey. the final
reset removes its fixture history after concise acceptance evidence is retained.
new owner ingress, complete fresh-corpus preparation, actual memory-role completion,
effects and restart recovery still require real proof. this sequence does not
qualify warm-up latency or throughput for the discarded 39,873-leaf corpus.
no stale view, parallel compactor, skipped admitted history or model substitution
is adopted. the [roadmap](../implementation-plan.md#v2-finishing-prs) remains the
sole delivery sequence; f2 owns both operations and their file/resource disposition.

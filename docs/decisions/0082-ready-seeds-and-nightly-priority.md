# adr 0082: ready seeds and nightly priority

status: accepted, 2026-11-17, by explicit owner choice: "adopt ready seeds and
due-nightly priority". supersedes dreamer's full-preparation requirement retained
by adr 0081 and the affected portions of the consolidated memory contract.
maintenance preparation, full-tree construction, retention and both resets stay.
source implementation and controlled qualification pass at memory `87a202c`;
installed qualification remains pending in f2.

## evidence and decision

the stopped repair run builds the formerly missing `4040+8` node and advances
coverage from 4,106 to 4,127 of 21,234 admitted leaves. the original failure cause
remains unknown. before this change, full-prefix preparation blocked dreaming.
the prior background loop ran compactor/indexer before checking a due dream,
so a healthy backlog could indefinitely postpone the nightly attempt.

inside the library's existing dream-input transaction, retain the frozen full
admitted cutoff for archive reads and valid references. read committed ready
coverage and consumed progress together. select seeds only through the lesser
of admitted cutoff and committed ready coverage, using existing eligible-node
selection and bounded fitting. this is construction coverage, not the fitting
main view's potentially smaller endpoint. no available new interval means no
inference or consumed progress: return the unchanged empty interval even if
stopped rebuilding leaves ready coverage below consumed progress. a synthesis-only
interval keeps its existing bookkeeping completion. never skip unbuilt or
unselected seeds.

retain the 64,000-byte seed bound, older sampling, synthesis exclusion and atomic
note/reference/leaf/consumed-cursor completion. the consumed cursor advances only
through the actual selected interval. admitted originals retain existing read
scope and availability semantics; do not narrow the cutoff or fabricate
readiness. remove dreamer's required
compactor dependency. strict maintenance preparation remains unchanged.

after main reports no work, check the existing due-nightly attempt before the
next compactor/indexer batch. reuse existing due state, atomic nightly claim,
background runner, cancellation and owner controls. an absent/already-claimed
attempt or zero-progress run falls through to compression. after actual dream
progress, return through foreground admission. add no task, timer, queue, mode,
schema, replay journal or generalized scheduling mechanism. models and grants
stay fixed; rotate only affected owning revisions and dependency pins.

## trade-offs and qualification

seeds can lag admitted history, including corrections. one bounded nightly dream
can delay the next compression/index batch. material becoming ready after that
night's attempt may wait until the next night or a manual run. no freshness,
throughput or usefulness guarantee follows. empty, failed and preempted nightly
attempts retain the existing once-nightly semantics; later seeds remain pending.

use f2's temporary actual-postgres and worker/service red/green/refactor proof
with independent review. prove distinct admitted/read and ready/seed bounds,
successive progress without skipped seeds, no-ready behavior, synthesis exclusion,
atomic completion, nightly priority/fallthrough and foreground cancellation.
retain required composition/regression checks and actual fixed-model quiet
completion, then delete only new probes. installed journey and final reset remain
separate obligations.

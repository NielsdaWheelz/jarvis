# adr 0061: simplify memory recovery and capture

[adr 0062](0062-simplify-memory-policy-and-retrieval.md) supersedes activation, additive native metadata, agent procedure and global resource policy.
see the [current contract](../universal-memory.md) for implementation.

- status: accepted implementation target, 2026-10-01; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved the simplicity audit and requested doc changes.
- amends adrs 0040/0051/0053–0060 only for background memory computation, capture
  transport/repair, configuration representation and delivery ceremony. main's
  durable decisions, paid-read policy, note-save identity, external effects and
  shared admission remain binding.
- current implementer contract: [universal memory](../universal-memory.md).

## evidence

the target treated durable storage and avoiding repeated paid computation as
one requirement. source bookmarks and pending flags already establish whether
memory work committed. the pinned kernel exposes `TransientModelDecisions` for
disposable isolated inference; llm-tools permits nondurable read recorders.
main additionally anchors external effects and note identities, so its journal
cannot be removed by the same argument.

partial-event transfer required a part checkpoint, normalization digest and
recovery rules before this prototype had measured need for oversized transport.
automatic historical rereads tried to repair unusual native mutations. neither
is necessary to capture ordinary complete events reliably. repeated amendment
notices and per-feature review choreography obscured the operative contract.

## decision

1. rememberer and dreamer use transient kernel inference. dreamer uses a small
   production llm-tools run-local read recorder (`durable=False` fixed), promoted
   from its helper and released/pinned, through the existing executor; no durable
   background scopes, frozen-request recovery, uncertain-call parking or journal
   retirement. input and clock stay fixed within a live run. after interruption,
   pending work may be selected afresh and computed again.
2. preserve transactional completion: notes plus the expected source bookmark;
   summaries plus exact pending seed flags. empty success completes work. discard
   stale/abandoned results. retain one serial worker and normal admission; unknown
   old usage keeps its charge. three unsuccessful extraction starts park that
   conversation, using the existing counter, not a new job table. clean returned
   foreground preemption refunds that local start without editing admission.
   ordinary clean-exit settlement and orphan-charge rules remain. dreamer failure
   ends the sweep until a later daily opportunity.
3. upload complete events; the service chunks text for storage and commits all
   parts with the event checkpoint. remove `checkpoint_part`,
   `normalized_digest` and extraction's scope-salt `extraction_attempts`.
   initial bounds: 8 mib canonical encoded event, 64 whole events/16 mib actual
   encoded request. oversized events park capture without truncation or skipping.
4. park/report unexpected rewrites, identity conflicts and missing native history.
   never reset checkpoints or reread historical prefixes automatically. repair
   uses existing stopped maintenance and preserves activation. status replaces
   per-absence interval bookkeeping; codec-detected gaps remain archive evidence.
5. declare shared recipients/processors once, with per-lane controller, sharing
   authorization and independent admission/connection. generate repeated profile
   configuration and credentials; ordinary convergence does not rotate bearers.
6. keep one local pre-migration snapshot and existing stopped rollback limits.
   add no backup/restore platform. use one current implementation contract, an
   operations runbook and historical adrs for rationale. use focused boundary
   review and small capture/retry and memory-completion checks; no repeated
   designer/reviewer ceremony for every feature.

## accepted costs and limits

- interrupted background inference/search can be charged twice and produce
  different uncommitted wording. commit boundaries prevent duplicate completion,
  not repeated computation. main's paid-read barriers remain unchanged.
- a crash between reserving a local extraction start and dispatch consumes that
  start conservatively; three such starts can require operator retry. admission
  denial consumes none. existing global limits still bound paid work.
- oversized events and unrecoverable native rewrites can block a conversation
  until manual repair; no automatic skip, resampling or unlimited transfer.
  the size bounds are provisional constants to measure, not universal capacity.
- no durable per-model-call history for new background runs. diagnose with
  content-free failures/counters, stored evidence and committed outputs.
- native storage remains the outage recovery source; pre-capture deletion can
  lose evidence. one local cutover dump does not protect against host loss.
- fewer mandatory review stages trade process coverage for focused verification
  and human comprehension. the retained regression groups remain required once
  implemented; the wider testing redesign remains open.

## cutover and acceptance

these capture/schema changes precede implementation, so no compatibility path
is needed. drain existing durable memory work before changing its contract;
transient inference is not permission to discard unresolved legacy work. retain
old main/effect recovery and expired-charge requirements during recaller removal.
no runtime or private data changes in this documentation update.

prove complete-event atomicity, lost-receipt retries, oversized/rewrite parking,
notes/bookmark and summaries/flags crash boundaries, bounded fresh retries,
stale-result rejection, and unchanged main effects/direct saves. do not require
identical regenerated answers or a background inference replay journal.

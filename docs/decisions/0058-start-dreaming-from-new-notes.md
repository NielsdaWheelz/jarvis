# adr 0058: start dreaming from new notes

[adr 0063](0063-simplify-memory-policy-and-retrieval.md) supersedes the mandatory first search and procedural completion rules.
see the [current contract](../universal-memory.md) for implementation.

[adr 0062](0062-simplify-memory-recovery-and-capture.md) supersedes this record's
frozen background scopes, failure retirement and rebuild journals. the
[current contract](../universal-memory.md) consolidates the implementation target.

[adr 0060](0060-replace-recaller-with-reranked-search.md) replaces the first-search
1/1 arguments with `limit=2` and shared bounded reranked results. pending-note
selection and atomic completion below remain unchanged.
[adr 0061](0061-remove-memory-forgetting.md) removes the erasure-specific rules
and checks below; failure retirement and derived rebuild remain.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved daily new-note batches, followed by memory
  search, and a later read-only snapshot of v2 active work.
- amends SPEC 6.5/9 and the universal-memory target's dreamer input, completion
  and mutable-field rules. the nine-table target and summary lineage stay intact.

## decision

retain the existing approximate 24-hour timer and foreground precedence. start
each bounded dreamer invocation with complete new notes, then search older notes
and summaries using the supplied material. remove the generic-topic first-search
instruction and reduce the first search from 10/10 to 1/1 lexical/semantic results
so its observation fits alongside the seeds in the existing context budget.
"today's notes" means notes awaiting a completed batch, including
backlog after downtime; it is not a calendar-date filter.

add one operational `memory_log.dream_pending` boolean. existing notes start
false at cutover; every new extracted or directly submitted note starts true.
freeze at most 100 complete pending notes within 64 kib per invocation, using
the existing kernel inputs and decision journal. the existing summary transaction
also clears exactly that batch's flags, including a valid empty result. no
separate progress table, cursor file or durable daily-sweep ledger is added.
the [implementation contract](../universal-memory.md#daily-dreaming) owns replay,
known-failure retirement, erasure and stopped-rebuild behavior.

v2 later supplies a compact host-rendered snapshot of doing now, blocked and next
up work. it guides relevance and suggestions; it supplies no authority or source
lineage for memory summaries. main owns work changes and acts on suggestions
through v2's existing planned event path. this integration cannot block shipping
note batching and does not add work tools to the dreamer.

## evidence and costs

the current worker starts with a generic maintenance instruction and no notes;
the prompt requires a broad topical search. this offers no coverage of newly
arrived notes and can revisit familiar results. the existing decision journal
already freezes inputs, and the summary writer already owns atomic mutations.

the cost is one mutable operational flag and narrow batch discovery/retirement
logic. daily seeds bias attention toward recent material; historical searches
help, but do not guarantee whole-corpus coverage. smaller seed batches and the
first search leave room for escaped results and follow-up reads, at the cost of
potentially more batches and fewer initial candidates.
active work must not crowd out personal, scientific or creative material.
summaries need not be produced for every seed. pre-cutover notes remain searchable
without an automatic historical
sweep. large backlogs use multiple admitted calls and can wait behind foreground
work; timer drift remains accepted. known failed scopes can be discarded once
all outcomes are known, retaining charges rather than a permanent failure history.

## implementation and acceptance

extend the pending universal-memory migration and existing packages. change the
dreamer prompt/compatibility revision, worker, summary transaction and rebuild
path; retain the memory search/open grants and paid-call uncertainty barriers.
remove snapshot-wide dream selection and the no-seed maintenance prompt.

retain batch completion/replay checks in the existing memory regression groups:
mixed note origins, bounded complete seeds, downtime, same-timestamp arrivals,
empty success, failure/preemption, crash around commit, erasure and rebuild.
the later work integration proves read-only context, truthful snapshot omissions,
note-grounded summaries and main-owned suggestions. this decision changes docs only.

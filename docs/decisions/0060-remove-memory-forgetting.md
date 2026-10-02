# adr 0060: remove memory forgetting from the prototype

[adr 0061](0061-simplify-memory-recovery-and-capture.md) supersedes this record's
background paid-call recovery (append-only storage remains). the
[current contract](../universal-memory.md) consolidates the implementation target.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner requested that forgetting be removed from the one-user
  prototype, including conversation exclusion and erasure.
- supersedes the exclusion/erasure requirements in adrs 0051/0053/0055/0056/0057
  and their affected schema, maintenance and verification rules. retained checks
  now cover capture and memory processing/replay only.

## decision

remove the exclude/include/erase commands, conversation `policy` column,
tombstones, erasure trigger bypass, association-based save restrictions,
erasure-specific session/journal purges and the dedicated erasure regression
group. these paths are unimplemented; no runtime data migration or deletion is
needed to remove them from the target. do not move them into a v2 commitment.

archive records and notes remain append-only. corrections append new evidence;
summaries, embeddings and indexes remain derived and rebuildable. optional
conversation attribution and direct source lineage still explain provenance.

retain lane admission/connection, activation boundaries, secret omission before
ingestion, content-free memory references, capture/extraction repair, paid-call
recovery and stopped derived rebuild. those serve ingestion, evidence and replay
correctness independently of forgetting. revoking admission stops new capture
and direct note saves from that lane; already admitted material remains stored,
searchable and eligible for memory processing.

## cost and acceptance

the product has no supported selective forgetting or conversation-level capture
opt-out. unwanted captured material stays in the corpus. this is an accepted
scope reduction, not an unfinished privacy mechanism.

remove all active implementation and acceptance obligations for these paths;
retain historical adr text with explicit supersession notices. preserve the
existing capture and memory-processing/replay regression groups, including
shared retrieval and derived rebuild checks. no new group or harness replaces
erasure. no code or runtime state changes are made in this documentation update.

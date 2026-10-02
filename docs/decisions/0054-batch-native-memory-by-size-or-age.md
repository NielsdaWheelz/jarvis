# adr 0054: batch native memory by size or age

[adr 0061](0061-simplify-memory-recovery-and-capture.md) supersedes this record's
durable extraction replay (size/age batching remains). the
[current contract](../universal-memory.md) consolidates the implementation target.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved conversation-specific size/age batching,
  independent episodes without overlap, continuous capture and an atomic
  per-conversation extraction bookmark, then requested the documentation update.
- amends adr 0053's decision 4 and SPEC's universal-memory extension. all other
  0051/0053 decisions, serial cognition, authority and verification scope remain.

## reason

a fixed sweep can dispatch ten words or a large backlog. the owner challenged
the fixed overhead of tiny invocations and rejected context overlap. unrelated
conversations were already separate; grouping them by clock window would lose
that boundary. native sessions may resume indefinitely, so waiting for their
completion is not a reliable capture or extraction rule.

## decision

the [implementation contract](../universal-memory.md#5-extraction) owns details:

1. keep continuous incremental capture and the startup/20-minute extraction check.
   never hold capture for a conversation to finish or a batch to become eligible.
2. for native conversations, dispatch the next bounded episode when the remaining
   complete pending prefix's rendered condensed input reaches 16 kib or its oldest
   pending central `received_at` reaches two hours. test before the 128 kib episode
   cut; keeping event boundaries can yield smaller episodes. these are provisional checked-in
   defaults; tune from measured traffic, not an adaptive scheduler.
3. freeze check time and complete source prefixes per sweep. reevaluate size/age
   after every successful episode; small fresh tails may wait. exclude incomplete
   events. resume frozen decisions before selecting new work. no new timers,
   columns, jobs, per-conversation workers or configuration surface.
4. use one conversation per fresh isolated invocation, the same central prompt,
   nonoverlapping source ranges, and no carried summary or session. long-lived
   conversations keep their archive identity across independent episodes.
5. preserve jarvis's settled-group eligibility each sweep and existing material
   cap; those complete groups cannot accumulate together, so waiting buys no
   batching. retain the existing atomic notes/bookmark transaction, including
   successful extraction that produces no notes.

the bookmark denotes the prefix requiring no further extraction. ineligible
jarvis groups keep their existing host-only completion at publication.

## costs and acceptance

- quiet native conversations normally reach eligibility after two hours to two
  hours twenty minutes, plus any foreground/admission delay before execution.
  raw archive search does not wait. a short message may be important; age prevents
  size-based indefinite deferral but is not a completion deadline.
- no overlap or carried context means references to earlier episodes may be
  unclear. extraction must not invent their missing antecedents.
- context isolation and bounded input take precedence over processing an entire
  long-lived conversation in one model call. no claim of measured savings yet.
- extraction batching does not bound stored archive volume. full captured tool
  payloads and indefinite retention remain; reducing them needs a separate decision.

record the size/age, isolation, completion and replay observations in the existing
feature acceptance and retain its small extraction regression group. no new
verification framework or migration is needed for this unimplemented target.
this change is documentation only; behavioral verification is not run.

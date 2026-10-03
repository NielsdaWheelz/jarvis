# adr 0054: simplify universal memory before implementation

[adr 0063](0063-simplify-memory-policy-and-retrieval.md) supersedes manual activation and related capture-policy rules.
see the [current contract](../universal-memory.md) for implementation.

[adr 0062](0062-simplify-memory-recovery-and-capture.md) supersedes this record's
background inference recovery and delivery ceremony. the
[current contract](../universal-memory.md) consolidates the implementation target.

[adr 0061](0061-remove-memory-forgetting.md) removes forgetting and its dedicated
regression group. retain only capture and memory-processing replay checks.

decision 4 is amended by [adr 0055](0055-batch-native-memory-by-size-or-age.md):
the periodic sweep tests native per-conversation size/age eligibility; independent
episodes have no overlap. other decisions apply except where subsequently amended.

[adr 0056](0056-save-agent-notes-over-mcp.md) adds direct agent note submission
with optional conversation attribution; source-only background extraction remains.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner accepted the final simplicity review and requested these
  documentation changes before implementation.
- supersedes the affected choices in [adr 0051](0051-universal-memory.md): eight
  tables and filesystem activation inventory; memory-reading extraction and its
  dependency graph; historical jarvis archive/provenance migration; extraction
  triggers; fleet completeness timestamps; source-specific retrieval tuning;
  deletion of all feature checks after acceptance.
- amends SPEC 6.4/7.1/7.3 (rememberer has no tools, including its maximum
  envelope), 9 (three added tables and direct source lineage), the universal-memory
  extension and the scoped adr 0046 testing
  exception. action authority, serial cognition, native containment and adr 0052's
  skid control remain unchanged. this does not activate any runtime change.

## evidence and decision

review of the unimplemented contract found that its eight-table limit forced
activation across filesystem manifests, configuration digests and database rows.
memory reads during extraction introduced a second provenance graph and deletion
closure. neither mechanism is essential to a shared corpus. historical jarvis
reconstruction also expanded a slice whose historical import was otherwise
deferred. the existing retrieval already supplies keyword and exact vector search.

adopt the revised [contract](../universal-memory.md):

1. add `memory_lane` beside `source_conversation` and `source_record`: three new
   tables, nine against v1. one transaction stores activation and every baseline,
   including empty lanes. an input inventory may be transient; postgres is the
   sole durable authority. table count is a description, not a competing goal.
2. give the rememberer only its frozen source episode and an empty tool plan.
   notes link directly to source ranges; summaries retain existing flattened raw
   lineage. remove consulted-memory ids, novelty search and transitive raw-note
   erasure. recall and dreaming retain cross-conversation synthesis.
3. defer historical jarvis archiving and provenance reconstruction to v2. drain
   old eligible rememberer work before cutover; preserve messages, notes and
   summaries, then publish only new groups through the new path.
4. use one 20-minute extraction sweep plus bounded episodes. drain fairly within
   existing foreground precedence and admission; no per-turn, idle or six-hour
   trigger. jarvis groups retain their existing material bound but use the same
   periodic schedule.
5. report checkpoints, successful inventory/read observations, backlog and known
   gaps. fast-poll detected changes; periodically revisit everything else. remove
   lane/fleet coverage-through timestamps and their proof protocol.
6. extend existing full-text, vector and ranking primitives. defer reduced
   precision, approximate indexes and a new fusion algorithm until measurement
   justifies them.
7. retain small capture, extraction-replay and erasure regression groups after
   red/green/refactor. remove exploratory/live helpers; restore no old suite,
   broad framework or recurring fleet qualification gate. the general testing
   redesign remains open.

## costs and limits

- one additional table removes a second durable activation store; no capture
  semantics are lost.
- independent extraction may repeat notes and miss connections during formation.
  direct lineage covers supplied source evidence, not semantic ancestry of
  independently restated content.
- old canonical messages remain outside archive search. existing notes and
  summaries remain searchable, but their unknown source lineage prevents targeted
  source erasure of those legacy derivations.
- notes wait for a sweep and available capacity. periodic boundaries can reduce
  coherence or increase the number of calls; measure rather than assume savings.
- missed native change hints can delay capture until the initially hourly revisit.
  successful scans do not imply complete history; outage recovery still depends
  on native retention.
- exact vector scans and full-precision vectors cost more time/storage as the
  corpus grows. optimize when the captured corpus demonstrates the need.
- retained checks require modest maintenance; they preserve repeatable evidence
  for the failure boundaries most costly to reconstruct manually.

## migration and acceptance

the universal-memory target has not shipped, so revise its planned migration
directly; add no compatibility path for the earlier proposal. keep the stopped
snapshot, old-work drain, multipart capture, echo suppression, unknown-call
barriers, source tombstones and pre-purge main-reference invalidation. the target
contract owns schemas, work boundaries and acceptance observations. this change
adds documentation only; behavioral verification remains not run.

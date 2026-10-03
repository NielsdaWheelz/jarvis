# adr 0051: one universal memory corpus

[adr 0063](0063-simplify-memory-policy-and-retrieval.md) supersedes manual activation, native-field strictness, status-tool and client-quota rules.
see the [current contract](../universal-memory.md) for implementation.

[adr 0062](0062-simplify-memory-recovery-and-capture.md) supersedes this record's
capture transport/repair and background inference recovery. the
[current contract](../universal-memory.md) consolidates the implementation target.

[adr 0061](0061-remove-memory-forgetting.md) removes the conversation exclusion,
erasure and tombstone requirements below; archive/notes remain append-only.

amended before implementation by [adr 0054](0054-simplify-universal-memory.md)
on 2026-09-30. its simpler activation, extraction, migration, retrieval and
verification decisions supersede the affected choices recorded below; the linked
implementation contract is current.

[adr 0056](0056-save-agent-notes-over-mcp.md) additionally permits direct external
note submission with optional conversation attribution; retrieval stays pull-only.

- status: accepted implementation target, 2026-09-28; implementation and live
  acceptance `NOT_RUN`. numbered 0051 because the reverted jarvis commit `bada736`
  and skid's `herdr-mobile-separation.md` already use "adr 0050" for a withdrawn
  home change.
- authority: the owner approved one corpus and the central
  archive/extraction/retrieval architecture, then, during the 2026-09-28
  adversarial review, decided: pull-only retrieval with no corpus-derived
  injection; independent default-deny `admit` and `connect` lane switches;
  capture from activation, with historical and legacy-home import deferred to v2;
  claude retention raised through dev-server as a separate prerequisite; no local
  spool and no provider hooks; no external `memory.recall`; temporary
  feature-specific checks deleted after recorded acceptance. off-machine backup
  and disabling native automatic memory remain deferred to v2. jarvis baseline
  `e6a6d20`.
- review corrections, owner-authorized 2026-09-29: native activation positions,
  inclusive checkpoint rereads, complete-role replay, flattened memory lineage
  and crash-safe erasure ordering; no implementation in this documentation change.
- supersedes or amends, for this slice: SPEC 6.1 (schema; no forgetting), 6.2 and
  9.1 (`remembered_at`), 6.3 (recall stores), 6.4 (rememberer trigger and sweep),
  7.2 (embedding disclosure), 7.3 (memory tool results), 8 (listener, host
  collectors), 9 (eight tables; `source_conversation` is a conversation table;
  a read pool outside the owner connection; rememberer decision scope), 11
  (listener) and 13 (six tables; no v1 redaction); adr 0002 (stopped erasure);
  adr 0008 (disclosure scope); adr 0031 (no jarvis listener; one host); adr 0040
  (six tables; all store work on the owner connection; rememberer scope); adr
  0046 (the scoped verification exception below); AGENTS.md's six-table,
  `remembered_at`, per-row fallback and permanent-memory invariants.
- affected acceptance: A1.4 (eight tables), A5.4 (three stores), A5.6–A5.8
  (episode extraction and source completion replace `remembered_at`) and A7.1
  (eight tables; the cutover snapshot is a transient operator artifact deleted
  after acceptance, not a backup or restore command).
- preserves: action authority and main's catalog, serial cognition and its
  foreground precedence, codex containment (SPEC 7.5), durable decisions and read
  positions for jarvis's own runs, adr 0033's backup deferral, and adr 0041/0044's
  exclusion of worker-control transcripts. the archive is memory evidence, not
  worker-control state.

## evidence

observed on 2026-09-28, macbook metadata and structure only, plus sibling
repositories at their current revisions:

- memory is a model-made recollection, not original evidence. the rememberer's
  completion depends on jarvis's settled message groups (`memory.py`
  `select_pending_rememberer_groups`); skid's result reader is terminal-bound and
  text-free. neither is an archive.
- native history lives only in provider homes: about 8.1 gb across the configured
  homes, about 775k 8,000-byte parts, with tool calls and results 85–90% of visible
  text; a further 34.9 gb sits in the legacy `~/.codex-personal` outside every
  configured home.
- claude code deletes transcripts after `cleanupPeriodDays`, which defaults to 30
  and is unset in both claude homes. `~/.claude-work/projects` dates from
  2026-05-14; its oldest surviving transcript is from 2026-08-28.
- claude's jsonl transcript is its only history surface, and anthropic documents
  its format as internal and version-dependent. codex exposes read-only
  thread and item reads, but legacy-mode threads carry replay-derived ids.
- codex hook context is added as developer context, and the agents launched on
  these hosts run shell commands without approval prompts. automatic injection
  of corpus text would give archived tool, web and email text developer authority
  in those agents. summarizing it first does not make it trusted.
- per-turn extraction windows of 24 parts / 32 kib cost 10–16 serial rememberer
  runs per sampled coding turn. that exceeds the serial role's capacity for one
  busy lane.
- skid's `historyScope` hashes a home's real path, so keying the archive on it
  would duplicate the corpus after a home move and let erased conversations
  return; jarvis `bada736` already attempted such a move.
- `memory_log`'s guard trigger rejects every delete; all owned-store transactions
  share one lock-guarded connection (`ownership.py`); exact vector scans and
  per-row lexical ranking over millions of rows cannot serve interactive reads on
  that connection.

## decision

adopt the [universal memory contract](../universal-memory.md). native capture
from admitted lanes by stateless per-host collectors through provider-runtime's
schema-strict archive codecs, preserving adr 0042's native installation policy;
immutable per-conversation activation boundaries in a content-free central lane
inventory; one central source archive with checkpoints
committed beside the data; per-episode extraction by the existing rememberer over
a condensed view; retrieval by explicit mcp search and open, with the authority
notice owned by the server; stopped exclusion and logical erasure with
tombstones.

two source tables and memory lineage columns extend adr 0040's six tables to
eight. source completion replaces `message.remembered_at`. hard cut means one
current implementation with no compatibility path, preceded by an on-host
database snapshot for rollback before first start; it never means discarding
existing data.

for this feature only, the owner requires temporary end-to-end, integration and
live red-green-refactor checks, then their deletion after recorded green and
refactor evidence. this is an exception to AGENTS.md's reset rule against adding
a replacement harness and to adr 0046's suspended gates, scoped to this feature;
it restores no retired suite and does not close the testing redesign.

## accepted costs

- no guaranteed recall in external clients; the model may miss a useful search.
  retrieved text still reaches shell-capable agents as tool results.
- one corpus is bounded by its most restricted reader. connecting an
  employer-administered client discloses admitted personal content to that
  provider; admitted work content is processed by jarvis's personal embedding
  project and codex account.
- native capture starts at per-conversation activation boundaries, not one
  simultaneous wall-clock cut. the small central inventory is required recovery
  metadata; losing it stops that lane. native writers may need a one-time pause
  for complete enumeration. earlier native history waits for v2; later turns in
  older conversations lack earlier context. existing canonical jarvis history is
  migrated at cutover as an explicit exception.
- preservation is bounded by native retention. native deletion, corruption or
  rewrite before capture loses evidence; no local copy guards against deletion
  during an outage. losing both the current checkpoint and original activation
  boundary parks that conversation. changing normalization mid-event likewise
  requires repair; capture never silently combines partial layouts.
- extraction is eventual, its limits provisional, child sessions unextracted
  except through their parents' results, and tool output clipped in its input. it
  consumes the extraction account's usage. interruption that leaves an armed
  model request or uncertain read needs operator retry; a known-undispatched
  cancellation does not.
- conservative lineage erases derived memories in full; erasure is logical and
  scoped to the archive and its derivations. invalidating the saved main session
  before purge makes crashes safe but can cost a cold start even if purge aborts.
- a devbox outage stops capture and reads; possible total loss without
  off-machine backup.
- `connect` binds honest clients only: every profile runs as the owner's unix
  user, so a same-user process can read another profile's bearer.
- native automatic memories independently influence replies.
- secret matching is pattern-based; a miss is centralized and remedied by
  rotating the secret, not by erasure.
- repair is forward after first start, and no regression suite remains after
  acceptance.

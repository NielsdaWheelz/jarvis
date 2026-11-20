# adr 0089. native capture repair

design accepted 2026-11-19. reader implementation is source-qualified.
both online collectors are installed. original recovery and remaining gaps
are recorded below.
one macbook conversation had a recoverable post-cut prefix. of the 22
other conversations originally awaiting first baselines, 21 still lack source. this amends the
[native capture contract](../universal-memory.md#3-native-capture) and retains
[adr 0073](0073-per-conversation-memory-baselines.md).

## capability and ownership

the collector calls `archive_head(home, native_id)` for a pending baseline.
its first stable head, including a proved empty head, establishes an exclusive
cut once. earlier activity stays excluded. `archive_read(home, native_id,
after=cut, from_event_id=checkpoint)` rereads the checkpoint inclusively when
present. jarvis checks its native digest. `POST /v1/memory/sync` records the
baseline. `POST /v1/memory/ingest` accepts pages or a closed error.
universal-memory commits complete retained parts, leaves and checkpoint together.
retries use the central receipt.

keep `native-archive.v3` and the existing `source_conversation` schema.
`baseline_error` identifies a pending cut. `capture_error` parks an established
conversation. `checkpoint_event_id` and `checkpoint_native_digest` advance
together. `last_read_at` dates an acknowledged caught-up read. timestamps and
file sizes alone never establish coverage.

## a. boundary evidence and macbook repair

reader modules live in `llm-calling/src/provider_runtime/agent_runtime/`.
`_archive_codec.select` owns the missing-marker decision.
`_codex_archive.read/history` and `_claude_archive.read/history` own native
observations. decide on the traversed history **before** slicing a 100-event
public page. a full page may have more completed events behind it.

| observation at the effective marker | result |
| --- | --- |
| marker unnecessary or found in the completed prefix | ordinary ordered page, including before an unfinished suffix. a checkpoint digest mismatch remains `source_conflict` |
| marker absent from an unfinished prefix | `unavailable`. ordinary sweep retries from the same position |
| first exhausted traversal lacks marker | confirm once on the same native source. require two exhausted traversals with identical ordered native id/digest pairs, both missing the marker, under the stability guards below |
| stability guard fails on a miss, or confirmation differs, stops early or finds the marker | `unavailable`. independently proved native errors retain their codes, including a missing conversation |
| confirmed absent | `activation_boundary_lost` before the first checkpoint, otherwise `history_changed`. park this conversation |

reuse the head guards. codex must be non-active with equal native conversation
metadata spanning both scans. claude requires the same eligible transcript,
stable size and nanosecond mtime, and a complete final line. retain the first
scan's comparison pairs and release its payloads before confirmation. ordinary
reads need one traversal. log an inconclusive missing-marker observation in the
existing private collector log with opaque identity and reason. a changing
history can retry indefinitely. a rewrite that removes the marker can genuinely
park. neither establishes the historical cause of the macbook incident.

**boundary designer.** fixtures distinguish unfinished from exhausted, active
from quiescent, cut from checkpoint, and a missing conversation from a missing
event. exercise the public reader, collector, http and postgres. prove one
capture after reappearance, normal progress before an unfinished suffix,
identical and differing exhausted misses, and changed checkpoint content.

**installed repair.** privately freeze the ordered ids/digests from the
original cut through the recorded terminal event (digest under installed evidence).
use the incident list if retained. otherwise date the new enumeration and
compare its count, page overlaps and end digest with the record. resolve a
discrepancy before clearing the park. this repair can precede the release.
under the [stopped memory-service procedure](../operations.md#memory-operations), recheck
the row, original cut, null checkpoint and exact parked reason while the writer
is stopped. clear only that diagnostic via `jarvis memory retry-capture
SOURCE_CONVERSATION_UUID` as the memory-service identity. restore the unit on
every exit. if state differs or the row parks again, preserve its diagnostic
for investigation. external clients briefly lose the memory endpoint.

match all 458 observed ids/digests across three turns against
`source_record.native_digest`, with unique complete parts and one leaf per
part. prove the checkpoint reaches the terminal pair or a verified later pair
in native order. reopen the terminal original through installed `memory_open`
for retained content. preserve 42 `subAgentActivity` and nine `sleep` gap markers.
record counts, reason and verified end digest without private ids or chat bodies.
the total historical loss remains unknown.

## b. claude archive capacity

`_claude_archive.record` owns a **16 mib** physical jsonl line limit, including
newline, across claude homes, transcript layouts and bookkeeping. apply the
same ceiling to the existing decoded-record walk. keep depth 32 and 100,000
items. an unterminated line within budget remains incomplete. reject an
oversized line before parsing with `event_too_large`.

`_claude_archive.row_events` selects **8 mib** for the full native identity
projection of an ordinary `tool_result`. pass it to `_archive_codec.event`'s
existing structural walk. its default stays 4 mib for other events, including
memory-tool references and user image/document blocks. preserve canonical
hashing before suppression. reuse `universal_memory.types.normalize_event`
for redaction, the 30,000-character tool-text cap and 8 mib normalized limit.

**tool-result designer.** reproduce the observed duplicated document and short
visible text. changing the projected document changes its digest. changing
only its ignored companion preserves it. use separate exact-fit and one-over
fixtures for physical bytes and `bounded_payload_size` walk units. include a
4 mib control and old-input digest parity. red on the stock reader, then on
the projection with only raw capacity raised. green through head/read, fresh
baseline, later append, inclusive retry, single commit and successful reopen.
the [measured case](../issues/native-archive-record-bound.md) was 15,957,980
physical bytes, 7,978,982 canonical projection bytes and 574 normalized bytes.
the isolated head peaked at 181 mib rss. measure the candidate. its 368
pre-baseline events stay excluded.

## c. devbox native lineage

the native account owner owns restoration. the [lineage designer's record](../issues/devbox-work2-native-source.md)
groups the 21 pending threads by missing original, 14 and seven. record exact
native identity privately, places checked, date, native error, baseline and
later capture separately. no retained copy is known. keep the lookup open for
an owner-designated source. audit dev-server's `lib/ai-tools.sh` and
`lib/memory.sh` for cleanup reaching referenced native history. repair only a
demonstrated destructive path. the cause remains unknown.

if a copy appears, verify provenance, expected segment identity and transferred
bytes. first exercise the candidate in an isolated native home with its lineage
metadata. withhold and restore it, leaving child timestamps untouched. the
native reader must resolve each dependent claimed as recovered. place only the
verified original in a vacant advertised native path. investigate conflicts
without overwriting. track each thread and group independently. until then,
retain the observed failing reads and qualify independent new chats. fair
baseline retries already exist.
recurring native backups, fabrication and historical backfill are out of scope.

## integration and acceptance

1. each feature designer above supplies expected content before implementation.
   write temporary end-to-end/live probes, record red and its cause, implement,
   record green, refactor and rerun. use an independent opus review per feature
   and on the integrated result. delete new probes and disposable fixtures after
   final green. retain the exact revisions, red cause and final observations in
   the linked issues until resolved. existing checks remain in jarvis
   `tests/capture_retry.py` and universal-memory `tests/test_capture.py` and
   `tests/test_completion.py`. recreating the temporary cases costs another
   qualification run. a missing real original stays open even when the release passes.
2. land a and b by the named functions. one integrator owns pins, locks and
   provider `docs/native-archive.md`. build the collector from its installed
   jarvis `b6cf4b3`, provider `6582551` plus these reader changes, and kernel
   `42e7ecd` with the matching provider pin. retain its other dependencies.
   keep the shipped commits reachable via immutable release tags. integrate
   the repair upstream on the current endpoint type. align kernel and jarvis
   `pyproject.toml` and `uv.lock`, jarvis
   `src/jarvis/definitions.py` and `src/jarvis/session-compatibility.json`.
   retire the unconditional park and superseded size rule. no runtime switch,
   fallback, migration or standing maintenance branch.
3. qualify against the installed codex endpoint mapping and claude homes.
   change dev-server's `assets/memory/release-pin.json`. replace only the
   collectors with scoped `memory_install`, one online host at a time. a failed
   host stops the rollout for forward repair. verify loaded pins and authenticated
   lanes. prove post-cut capture/reopen on disposable macbook/claude-work2 and
   devbox/codex-work2 chats under existing authorizations. report preserved
   cuts, last acknowledged reads and receipts for affected originals. verify
   real baselines read-only. per-thread post-cut proof waits for natural activity.
   central services and assistant releases have separate deployment ownership.
   if fleet discovery delays the two original macbook repairs, a bounded pass
   may temporarily own that host's stopped collector. it reuses the installed
   stable head and ordinary authenticated baseline and ingest operations on the
   exact incident identities. restore the same collector on exit and verify
   both original receipts read-only. this shortens recovery at the cost of one
   additional macbook collector pause and discovery restart.

independent design review, 2026-11-19. claude opus 5.5 found the initial park
test too weak. the revised design passed its second review. immutable release
tags address its remaining artifact-fetch concern.

## implementation evidence

the stock reader went red through collector, http and postgres 16 by parking
an unfinished codex prefix and refusing the oversized claude record. with only
the raw limit raised, the claude projection still failed at 4 mib. the candidate
retried incomplete and differing observations, committed after reappearance
before an unfinished suffix, parked a corroborated miss, and fenced a changed
checkpoint digest. the large claude record established one exclusive cut. a
later event committed once, retried inclusively and reopened through authenticated
streamable-http `memory_open`.

native reader probes covered codex paginated and legacy histories, active and
changing metadata, missing conversations, ordered comparison and release of
first-scan payloads. claude probes covered transcript stability, exact physical
and structural limits, one-over rejection, the unchanged 4 mib cases and
digest parity. the actual claude read returned 368 distinct pre-cut events, with
matching overlaps and terminal head. candidate peak rss was 187.92 mib, up from
116.06 mib for the stock process that refused the record.

release `8c82c5fa406a1e0f7b6b21c151a2b1b8fe14bf7c` is a direct descendant of
`b6cf4b3`. its frozen lock changes only provider `f72155db` and kernel
`c8ed5901`. all three repos publish the exact objects under
`jarvis-native-capture-adr0089`. active tag rules prohibit updates and
deletion of that exact ref, with no bypass actors. the explicit-endpoint port uses provider
`477f7141` and kernel `0df607e` through their dedicated integration branches.
a future jarvis release adopting the current provider still needs the existing
[explicit endpoint consumer cut](https://github.com/NielsdaWheelz/llm-calling/blob/477f714106247dfd4ca51becc4448f971c41b21b/docs/issues/jarvis-codex-endpoint-cutover.md).
the fleet's selected collector stays on the qualified stock socket line until
that consumer cut.
the tagged provider and the port passed 983 and 1,000 existing tests
respectively. each kernel passed 176. the existing jarvis capture/retry and
universal-memory capture/completion regressions passed against disposable
postgres 16. broad provider generation stays separately scoped.

independent opus reviewed the source and refactor, the installed retry procedure,
and the managed fleet cleanup audit. it required ownership of the release lock,
verification of the exact running and restored release, and comparison of the
stopped post-retry row and persisted native evidence.

### installed evidence

on 2026-11-20 utc, macbook sealed collector `8c82c5f` at 02:13:44
and devbox sealed it at 02:22:11. each loaded the exact four locked dependency
revisions, authenticated all six original lanes, and preserved their activation
times and native profile mappings. the mac staging runner initially failed
before stopping the service under system bash 3.2. retry through the installed
workstation bash passed. the memory-service repair used the then-selected
`9b96667d` under its deployment lock and memory-writer role, restored the unit
and its private socket, and changed only the original conversation's
`activation_boundary_lost` diagnostic. no assistant or central release was
installed by this delivery.

the stopped-state retry preserved the macbook codex cut and null checkpoint.
the installed native read reproduced the incident range at 02:01 utc with four
matching overlaps. the scheduled collector acknowledged the first 64 events.
slow full-home inventories delayed the remainder, so a bounded single-collector
pass used the installed read and authenticated ingest path to finish the two
macbook repairs. the first stop check raced launchd unloading and exited before
capture. the retry used the fleet's bounded stop helper. the macbook launch
agent resumed the same exact pinned release and all six lanes reauthenticated.

at 02:24:33.574247 utc postgres acknowledged the original codex cut through the
frozen terminal digest
`873091e8a576b06af106bbd5d01dfc3dfbae58033ba40496ed45a2238818c2db`.
the independent comparison matched all 458 ordered native id/digest pairs
across three turns, complete unique parts and one leaf per part. it preserved
42 `subAgentActivity` and nine `sleep` gap markers. the installed
`memory_open` returned the exact terminal text. historical loss and the
original trigger remain unknown.

the macbook claude baseline settled at 02:23:58.953615 utc. the installed read
matched all 368 pre-cut native pairs and the final head. read-only central
verification found zero admitted pre-cut parts, no checkpoint, and no later
acknowledged read. qualification of the real conversation after its cut awaits
natural activity. [affected conversation record](../issues/native-archive-record-bound.md)

the ordinary macbook `claude-work2` canary acknowledged final capture at
02:20:39.900 utc. all 11 ordered native events matched central storage and the
terminal checkpoint. the installed tool reopened the exact assistant original
at 02:20:52.385 utc.

the ordinary devbox `codex-work2` canary acknowledged final capture at
02:24:50.410669 utc and reopened at 02:25:14.738029 utc. the exact two ordered
text events matched their central digests and checkpoint. across both canaries,
13 complete native events produced 13 unique parts and 13 leaves. the fixtures
made no tool calls. original native chats retain their own histories.

21 devbox baselines remain `unavailable` across the two missing native segment
groups, 14 and seven. the installed reader could see one newest-first page
per thread, with a continuation cursor. each oldest-first request reported its
missing rollout, and every full head read remained unavailable. the fleet
cleanup audit found no path to repair. an exact owner-designated source is
required before the conditional restoration drill or original-lineage
acceptance can run.
[remaining source issue](../issues/devbox-work2-native-source.md)

the temporary integration and live probes, disposable postgres, canary working
directories and both private installer stages were removed after qualification.
the normal retained canary histories and existing regression groups remain.

the fleet pin landed in [dev-server 227](https://github.com/NielsdaWheelz/dev-server/pull/227).
the current endpoint ports are [provider 60](https://github.com/NielsdaWheelz/llm-calling/pull/60)
and [kernel 33](https://github.com/NielsdaWheelz/llm-agent-kernel/pull/33).

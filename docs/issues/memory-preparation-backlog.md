# main blocked by admitted-memory preparation backlog

status: open operational blocker, 2026-11-16. the preliminary reset under
[adr 0078](../decisions/0078-fresh-corpus-first-acceptance.md) is complete.
the owner subsequently approved
[adr 0079's free-copy and serial-batch amendment](../decisions/0079-bounded-serial-compaction.md)
after genuine new capture exposed substantial preparation work. source and a
real-model candidate are qualified; the repair is installed as `0b33fc4`.
complete production preparation and the real journey remain pending. large-corpus
throughput and latency remain unqualified.
the owner additionally approved [first valid hard-fitting summaries](../decisions/0080-first-valid-compaction.md)
after the real 516→504-byte soft-target retry demonstrated an extra post-valid
call. that stopping amendment is under source/candidate qualification; it does
not change the fixed models or accepted coverage/reset scope.

problem: main waits for the complete admitted-history view before opening a native
turn. the existing archive has a large uncompressed tail. the genuine production
fixture request entered canonical history at 22:55:02 utc and remained pending
without a main native attempt, action or email. the application stopped cleanly at
22:58:14 utc to inspect required work before continuing paid preparation. gmail
and calendar baselines had completed quietly, with no event facts or errors.

impact: the installed combined journey awaits fresh-corpus preparation. successful source ci
`43974508049` at installed `b3615292b0628322be00dba8855d03f65904fec5` does not
qualify this backlog's operational cost. broader
[memory usefulness/load evaluation](memory-usefulness-evaluation.md) remains separate.

evidence: stopped metadata reports 39,873 admitted leaves, `view_through=2238`,
2,238 built level-zero nodes, both shrink flags false and no compaction error.
37,635 leaves remain unbuilt: 37,629 source leaves and six notes. raw text alone
exceeds 512 utf-8 bytes for 15,251 of those source leaves and all six notes.

pinned `universal-memory` `b616ee924454f40305c49d3b73e81694819ba1e4` advances views
only across consecutive built leaves. `tree.Ready.next` supplies the entire source
plus provenance and grants `free_text` only at 512 bytes or less. therefore at least
15,257 additional leaf jobs require model inference through main's serial
`MemoryWorker.ensure_ready` path. parent compression and retries add work. the
`missing_nodes` status metric counts all potential tree nodes, including free
construction; it is not a model-call estimate. parent scheduling favors older
subtrees. the observed two-leaf progress is insufficient for an eta or throughput
claim. this evidence proves a material backlog, not a deadlock or algorithm defect.
independent adversarial source/metadata review confirms the lower bound.

the preliminary reset cleared eighteen tables and the configured channel;
all twelve online native lanes activated with fresh readable-head cuts and
explicit pending baselines for unreadable heads. all 1,885 subsequently
captured native parts have zero source-identity overlap with the old 39,825 parts.
much of this new work accumulated while canonical cognition was paused. stopped
fresh metadata has 1,888 leaves and coverage through 31. complete-source
measurement of the 1,857 missing leaves finds 716 at most 512 bytes, 809 between
513 and 2,048 bytes, and 332 above 2,048 bytes. the approved free-copy rule removes
809 of the current 1,141 required leaf inferences, before parent/retry work.
ordinary web/file/shell tools account for the inspected tool traffic; no memory-tool
feedback explanation was demonstrated. the installed old/new provider archive
codecs are byte-identical at their respective pins.

all 44 fresh google cursors completed with zero poll errors. a real
calendar-attention fact remains pending. jarvis stopped cleanly at
`2026-11-17T00:41:57Z`, preserving genuine owner `resume` sequence 9, with zero
actions or todos. there is no elapsed-time or steady-state capacity claim.
the latest read-only observation also retains 23 unreadable pending baselines
and one separate `macbook/claude-work` capture rejection, `event_too_large`.
[the latter](native-archive-record-bound.md) reproduces the provider's existing
8-mib physical transcript-record refusal before any central request. no new
implementation defect is established. neither state was cleared or treated as a cut.

after actual candidate content/route proof and routine host/application
replacement, genuine `resume` sequence 9 remains current and catch-up completes.
production coverage advances from 31 through 122 with no compaction error.
thirteen newly built level-zero nodes have raw source above 2,048 bytes, proving
actual inference rather than free copying under the new policy; raw source reaches
8,000 bytes and those stored nodes are at most 514 bytes. the main native attempt
has not yet opened at this observation. this is progress, not a latency or
steady-state capacity qualification.

owner disposition: implement exact free copies through 2,048 bytes and bounded
serial batches, qualify the real journey, then perform the final reset. before
either wipe, disposition pending work through existing controls, satisfy every
stopped-reset obligation and retain verified current private `0013` recovery and
original uncertainty evidence. replace an older full recovery artifact only after
its successor verifies; retain concise original receipts. both resets establish
fresh source cuts and preserve original native/nexus chats and private data. no
stale view, parallel compactor or skipped admitted history is adopted.

resolved when: the amended library/caller contract passes meaningful source/live
proof and the actual main turn reaches native dispatch with the required complete
fresh view, followed by the remaining real
journey and reset evidence. fresh-corpus success would not qualify latency for
this 39,873-leaf backlog; retain that limitation explicitly.

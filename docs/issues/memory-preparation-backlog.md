# main blocked by admitted-memory preparation backlog

status: open operational blocker, 2026-11-16. the owner approved
[adr 0078's preliminary reset → real journey → final reset](../decisions/0078-fresh-corpus-first-acceptance.md);
execution remains pending. large-corpus throughput and latency remain unqualified.

problem: main waits for the complete admitted-history view before opening a native
turn. the existing archive has a large uncompressed tail. the genuine production
fixture request entered canonical history at 22:55:02 utc and remained pending
without a main native attempt, action or email. the application stopped cleanly at
22:58:14 utc to inspect required work before continuing paid preparation. gmail
and calendar baselines had completed quietly, with no event facts or errors.

impact: the installed combined journey awaits the approved preliminary reset and
fresh-corpus preparation. successful source ci
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

owner disposition: perform the preliminary fresh reset, the real journey and
its final reset instead of this historical backfill or a throughput change. before
either wipe, disposition pending work through existing controls, satisfy every
stopped-reset obligation and retain verified current private `0013` recovery and
original uncertainty evidence. replace an older full recovery artifact only after
its successor verifies; retain concise original receipts. both resets establish
fresh source cuts and preserve original native/nexus chats and private data. no
stale view, parallel compactor or skipped admitted history is adopted.

resolved when: the approved preliminary reset runs and the actual main turn reaches
native dispatch with the required complete fresh view, followed by the remaining real
journey and reset evidence. fresh-corpus success would not qualify latency for
this 39,873-leaf backlog; retain that limitation explicitly.

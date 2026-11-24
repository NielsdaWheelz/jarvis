# claude data-flow records stop chat capture

the [reader and recovery plan](../claude-data-flow-capture.md) specifies the v3 repair before workers freeze under v4.

on november 23, 34 `macbook/claude-work` conversations were parked with
`capture_error=unsupported`. all 34 native files were present. replaying the
installed reader offline stopped 33 at a `data-flow-records` row and one at
a `data-flow-incomplete` row. each lacked a uuid. the provider rejects an
unrecognized row without a usable identity before it can return the later
conversation. [installed reader](https://github.com/NielsdaWheelz/llm-calling/blob/f72155db78a16acf58a7ac396f84def9c887cb07/src/provider_runtime/agent_runtime/_claude_archive.py#L341)

four are top-level chats. three `jarvis-0095` transcripts contain november
23 activity and have zero central records. the fourth has 332 central parts
ending november 21 and a later local reply at 17:47 utc on november 23.
the other 30 are child or workflow sessions. other chats in the same profile
continued to enter memory. central backups cover the admitted portions only.

resolve when the provider handles both row types according to their native
meaning and the installed collector recovers the affected post-cut events
from their existing positions. compare native and central identities and
reopen the later replies. [capture contract](../decisions/0089-native-capture-repair.md)

## november 23 preflight

the 19:38 utc production census still showed all 34 parks. all 34 have an
established cut from the beginning. 33 have zero central parts and a null
checkpoint. the remaining top-level chat retains its checkpoint and 332 parts.
the macbook and devbox collector processes both ran jarvis
`8c82c5fa406a1e0f7b6b21c151a2b1b8fe14bf7c` with installed provider
`f72155db78a16acf58a7ac396f84def9c887cb07`.

on the mac, public `archive_read` against each original cut and checkpoint
reproduced all 34 errors. claude code writes `data-flow-records` as updates
or snapshots of its data provenance, including request and tool-use
references. `data-flow-incomplete` records loss codes for that tracking.
the native reader restores these into data-flow state separately from
messages. the installed provider reaches its required-uuid check on these
rows and returns `unsupported`.

the 332-part chat also has a later uuid-less `derived-from` row. its only
source is the same session via `compact`. handling just the first two row
types would leave this chat parked. qualify this observed compaction record
separately and preserve native evidence for other lineage relationships.

an unaffected chat in the same profile matched all 100 eligible native
id/digest pairs in order, its terminal checkpoint, and 111 complete unique
parts with one leaf each. installed `memory_open` returned the full terminal
reply with the same utf-8 hash. the collector acknowledged this chat at
19:23 utc. affected-conversation recovery and post-installation proof remain
open.

at 20:38 utc all 34 were still parked, plus a fifth top-level chat. this
new conversation had its first message at 19:51 utc and a reply at 20:05
utc on claude code `2.1.330`. it had zero central parts. public
`archive_read` reproduced `unsupported` on a uuid-less `data-flow-records`
row before a later assistant reply. the earlier 332-part chat also had
a new local reply at 19:55 utc. all five top-level chats had november 23
replies. by last user or assistant text in the other 30 sessions, 22 were
active november 22 and eight november 21.

all 24 workflow and six direct-child transcripts have an on-record
sidechain message with matching agent and parent-session ids. at the
prospective adr 0098 cut, confirmed workers freeze at their existing
positions. a report delivered into an admitted parent remains eligible
there. report worker exclusion separately from full v3 recovery. the five
known top-level conversations still need the reader repair under either
contract.

the 20:55:58 utc november 23 mac census found 39 parked conversations, five
top-level and 34 child/workflow. in a disposable process using the installed
reader, classifying both data-flow rows as bookkeeping left exactly one
failure, at the self-compaction row. after checking its full provenance
shape in that file, the public reader exhausted all 39 transcripts in
61 pages. all five stored checkpoint pairs and 22 page overlaps matched.
all 34 children had matching on-record worker evidence. the v3 normalizer accepted
all 1,372 remaining top-level events and 2,825 remaining child/workflow
events. every top-level suffix contained a later assistant utterance.
the private mac receipt `~/.local/state/jarvis/evidence/native-capture-20261123/replay-205558z.json`
was reopened and hashed, sha256
`7b3835f3a189f04bb36c7f30c09ebfc15df0df8df1f466025bf82ea45030973d`.
it freezes the ordered native pairs and terminal reply hashes for comparison.
installed recovery still requires a qualified release, individual retry
receipts and central readback.

## november 24 design evidence

at 00:59 utc, both online collectors still ran `8c82c5f` and postgres
reported `0018`. the five root and 34 child parks remained. the owner chose
to recover all eligible v3 chats before the adr 0098 worker freeze.

on macbook, the installed public reader reproduced `unsupported` separately
for a provenance update, snapshot, loss marker and self-compaction. the
unmodified four-message control matched the designer’s five-event oracle,
including its real branch. the disposable home was removed. a read-only
census at 01:07 utc found 1,114 update/snapshot rows, three loss markers
and one self-compaction across the 39 original files. all 1,118 matched
the specified field, session and agent rules. eight were full snapshots.
the largest matching line was 96,367 bytes including its newline. one root
and four children had saved checkpoints and 332 and 662 prior parts,
respectively. the other four roots and 30 children had neither.

the 01:16 utc cross-account census found zero pending claude baselines. it
also found one separate top-level `macbook/claude-work2` park. its public
reader returned 22 later events after a matching checkpoint pair. two tool
results contained nul and the installed v3 normalizer rejected them. keep
this case with [0098 installed capture](adr0098-installed-capture.md) and
outside the 39 metadata retries. the private `work2-discovery.json` and
`work2-normalization.json` receipts retain the case identity and digest proof.

the native writer also emits foreign or mixed `derived-from` on branch,
import or some resumed histories. these shapes can park a new fork or a
previously recovered root. none occurred in the frozen cohort. qualify their
ancestry and event identity separately before widening this classifier.

private receipts under `~/.local/state/jarvis/qualification/claude-data-flow-design-20261124/`
were reopened and hashed. `reader-preflight.json` has sha256
`b78aae04906296952d3993f2619153ddd0826174e9e78695a0138a1f2a168f59`.
`shape-inventory.json` has sha256
`e4a9acc68d35a4e6a58f469d92dedfd2320b0ec888310fb46a300b1961e2486f`.

on november 24 an independent claude opus 5.5 review passed design sha256
`b9a303d15a1a8799097c20821bc5b4a64999c6826a4f6672d3f9ad65814e42f6`
after correction of fleet asset selection, workflow header scope, exact key
handling and the v4 worker-freeze gate. the reopened private `opus-final.md`
receipt has sha256
`1194e922b89da529a216d95281f120749d5603f8c13390fa712c1d5c6008630a`.
implementation, candidate qualification and installed recovery were still
open at the design review.

## november 24 implementation and mac qualification

the reader now consumes the three exact diagnostic envelopes after record
validation and before event or lineage state changes. v4 uses the same rule
before looking for a direct child's native proof. workflow discovery's first
record still establishes its parent. the [separate header issue](claude-workflow-leading-metadata.md)
tracks its inventory impact.

| candidate | jarvis | provider | kernel | fleet |
| --- | --- | --- | --- | --- |
| v3 recovery | `74b616a` | `3dc3fb7` | `32ca343` | `e093061` |
| v4 worker-freeze successor | `403b1f7` | `36c5b34` | `8f10cdf` | `8aee9cf` |

at 01:38 utc central was `43ed919` / `0019`. canonical resume `32`
arrived at 01:38:26.821165 utc. macbook and devbox still ran `8c82c5f`.
the v3 collector and exact central passed a detached postgres 16 rehearsal.
the old reader reparked the root and metadata-only worker. after separate
stopped retries, the new reader recovered 132 events after the root checkpoint,
retained 187 unique parts and leaves across all 133 post-cut events, and
reopened a 55-part reply through eight authenticated `memory_open` pages.
lost acknowledgement and a failure during leaf insertion preserved atomicity.
the worker acknowledged catch-up with the same verified pair and zero new
parts or leaves. the unaffected reply reopened.

v4 passed its separate authenticated collector and postgres 16 proof at
`0020`, preserving both digests and excluding a child with proven lineage
after leading tracking metadata. raw reads still exposed the child. the
existing jarvis regression now injects its failure at `append_main_events`,
the current canonical projection call. both candidates passed the retained
capture and memory checks for their own schemas. fleet rendering matched
managed config, instruction and unit bytes on both hosts. the v3 launcher
changes its collector release path.

the 01:43–01:44 utc packaged v3 replay matched the original cuts, all five
checkpoint pairs, the 994 retained parts and all 27 reply hashes. it found
4,197 new events and 4,641 new parts across 35 chats, with zero events beyond
the frozen manifest. the projection retains gaps, branch events and context
references. ordinary tool-output clipping accounts for 198,028 characters.
four workers had only a metadata suffix. retry those individually to
acknowledge their unchanged terminal pairs. the proposed
39-case uuid list and comparison receipts are private. the candidate replay
sha256 is `58443d3d1deb53e4d3b31a9c05043b27b7836b4c11d29bee418106b6100c60ca`.

independent claude opus 5.5 review passed both exact candidates at 01:59 utc.
the review receipt sha256 is
`7006f923a5501e5741481a503a65e7eeb4ccd6bf2b0088f24ba6b783ee5715ee`.
the owner authorized the v3 tags, macbook recovery and then the devbox
collector update on november 24 from 02:30 to 04:00 utc. the historical owner
confirmed no overlap. the recovery set contains only the 39 manifest uuids,
on central `43ed919` / `0019`, with a memory-service stop budget of five
minutes. the pre-cut status was zero recovered, 39 metadata parks, a separate
nul park and 21 missing-source devbox baselines. `0020` stays gated on v3
closure receipts or named owner exceptions.

at 02:30 utc the four v3 tags were published and fetched at their exact
commits. at 02:31:30 utc macbook ran `74b616a` with the reviewed provider
reader hash and six authenticated lanes. an ordinary `claude-work` control
reply reached central and was acknowledged at 02:40:01 utc. installed
`memory_open` returned the matching normalized text hash.

the stopped-retry guard found canonical web pause `33`, committed at
02:24:11.972737 utc after historical clearance. it exited before any stop
or retry. the pause belongs to the separate `0020` and nexus cut. its
operator acknowledged the recovery dependency and held the schema cut
and worker freeze. at 02:42 utc both central writers were active on
`43ed919` / `0019` under pause `33`. all 39 recovery cases still require
retry and readback. devbox remains on `8c82c5f`. recovery awaits explicit
operator handoff. ordinary control traffic preceded the capacity window.

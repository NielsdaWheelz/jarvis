# macbook codex-work capture

### three changed histories

the original rollouts contain complete assistant items at all three
checkpoints. applying the installed provider's projection to each original
item, including turn id, phase and native start time, reproduced its stored
checkpoint digest. the same calculation matched the live terminal digest
for each selected history.

the three selected continuation files began between 01:47:57 and 01:48:16
utc on november 20. all three contained later replies that day. the
20:38 utc census on november 23 still counted three changed histories in
this profile. the evidence establishes one cluster.

each selected continuation's native `history_base` chain cuts the original
before its saved checkpoint. the columns give byte positions in that
original. central part counts distinguish the cases without publishing chat
identifiers.

| central parts | local segments | original prefix ends | checkpoint item starts |
| ---: | ---: | ---: | ---: |
| 396 | 3 | 3,389,993 | 3,415,897 |
| 522 | 2 | 4,490,538 | 4,643,163 |
| 636 | 3 | 4,219,015 | 4,253,280 |

through the installed app-server, ordinary `archive_read` returned
`history_changed` for all three after its two stable, exhausted traversals.
the continuations expose later replies. the saved event is absent from
each selected history. who or what selected the earlier boundaries remains
unknown. recovery requires native continuity through the saved checkpoint or
a separately accepted contract for divergent histories.
[checkpoint contract](../universal-memory.md#provider-contract)

#### what the mac can prove, november 24 utc

there are five divergent edges across eight local segments. the 396- and
636-part chats each have an intermediate version with a completed user message
and a final assistant reply beyond the point inherited by the selected version.
each of the five cuts lands on a complete line. its byte offset and logical
ordinal agree. on either side, the first subsequent completed user items have
different ids. all three saved checkpoints are the final assistant items in
their original files. the installed projection reproduced all three saved hashes.
the admission receipts have an established, exclusive cut from the beginning.

| stored parts | inherited end in original / checkpoint item (ordinals) | inherited end in middle (ordinal / local bytes) | selected suffix occurrences | v4 records |
| ---: | ---: | ---: | ---: | ---: |
| 396 | 990 / 998 | 993 / 32,619 | 1,151 | 112 |
| 522 | 1,144 / 1,156 | none | 735 | 34 |
| 636 | 1,116 / 1,126 | 1,119 / 32,623 | 761 | 30 |

native rollout ordinals are zero-based and inherited ends are exclusive.
both middle-file prefixes contain a header and two settings records. the
selected suffix counts start after the shared assistant item. the first
selected user item and terminal assistant item match local evidence in each case.

the macbook work endpoint first reported codex 0.171.0 and later 0.172.0.
the 0.172.0 experimental schema offers thread-, turn- and item-based reads.
the scoped thread listing returned one selected path per chat. the common
thread id read the selected history. an exact turn/item lookup returned zero
items for each original checkpoint and one for each selected terminal reply.
all five non-root segment ids resolved metadata for their own paths, bearing
the same logical thread id. version-addressed turn and item paging returned
`-32601`. the timeline also lacked the original checkpoints. neither the
returned metadata nor the read schema supplies a version-bound parent edge.
the files locate the physical splits. the installed api cannot freeze, page
and compare every side in capture order. the initiator remains unknown.

#### original all-version proposal

the original proposal required a codex-native version read or official
export, explicit operator admission and verified live continuity or a seal. the selected
view can verify a shared checkpoint on either tail. it cannot detect that
later split by checking the checkpoint alone. the proposed roster check
covers this profile.

the private design review is `codex-history-design-opus-20261124T014511Z.json`
in the evidence directory below. its reopened sha-256 is
`4a6d9c399670a87d9cc2fea218f70af745b4f120beade736e66a05bd47b1c41a`.
the reviewed all-version draft had sha-256
`42dde3ad2c7f1371e442b9a4900c0a6cd140f33ac60f9bfe437843412e64322a`.

#### mac test and outstanding proof

the read-only test ran through the installed collector. in each selected
history the test used its penultimate final reply as a control checkpoint.
it verified the inclusive native id and digest and reached the independently
projected final reply once, after 113, 53 and 23 further native events in
table order. the 396-part control crossed a page. using each real saved
checkpoint instead returned `history_changed`. the separate v4 read also
returned that park for all three. from the diagnostic shared markers it
matched all page overlaps and froze the ordered selected occurrences,
expected records, part counts and retained text hashes. these 176 selected
records belong to the three selected tails. the two intermediate replies
have private forensic witnesses and still require native version reads.

installed `memory_open` reopened the three original checkpoint replies at
their existing event selectors. each had one complete part and matched the
independent retained-text sha-256. under those same central conversation
uuids, all five later terminal reply ids returned `not_found`.

the test and three reopened private receipts are in
`~/.local/state/jarvis/evidence/native-capture-20261123/`. run
`history-branches-mac.py` with the installed collector's python and `-B`.
the diagnostic receipt is `history-branches-20261124T005831Z.json`, sha-256
`94fe1d71abd42c406ef3cf628d08eaf963ad5e3ea958722774aab31ad1438322`.
the v4 expectation is `selected-v4-branches-20261124T010100Z.json`, sha-256
`a7b42e6ef3a4f8aec05eab57670768dee9ecaec2e45b27b3274ab9ef65f739a7`.
the installed open results are `history-branches-open-20261124T010636Z.json`,
sha-256 `7433f5b3f284da73f6d4bba82507e9157fe93ffaba05ad7dea9897e6347c27b6`.

version-aware collector-to-postgres capture and installed reopen of the five
later terminal replies remain pending. production repair needs separate
authorization.

#### all-version capability test

the live capability probe matched the socket owner before and after reading
and generated the experimental schema from that exact codex 0.172.0 binary.
it listed one logical history in each case, against the frozen 3/2/3 roster
expectation. inline, turn, timeline, item-page and direct item reads returned
`-32601` for all five non-root aliases. the three selected-history controls
verified their terminal digests and the three original saved-boundary reads
returned `history_changed`.

the temporary all-version probe exited 1 for
this capability red. the private receipt `codex-history-native-red-20261124T015304Z.json`
has reopened sha-256
`fa4818fb64683575e788785028608529db326fc7ce7c49ffad383433af495eac`.
native green, archive integration and installed repair remain pending.

the current native release has one selected pointer per logical thread. its
revert code persists and closes a replacement rollout before switching that
pointer. interruption between those steps can leave a well-formed file that
was never selected. `history_base` proves the inherited cut of a file.
the filesystem alone cannot certify an exhaustive roster of committed
versions or finality. tagged 0.172.0 and 0.174.0-alpha.1 page the selected
lineage. the official transcript export renders one thread to markdown.
[codex selection](https://github.com/openai/codex/blob/rust-v0.172.0/codex-rs/thread-store/src/local/revert_thread.rs#L124-L151)
· [prerelease history reader](https://github.com/openai/codex/blob/rust-v0.174.0-alpha.1/codex-rs/thread-store/src/local/thread_history/read.rs#L102-L225)
· [export](https://github.com/openai/codex/blob/rust-v0.172.0/codex-rs/tui/src/app/transcript_export.rs#L82-L135)

qualify a native frozen roster and stable per-version reads before starting
storage work. the reader or official export must distinguish committed
versions from tentative replacements, include each exclusive inherited
boundary, and prove live continuity or native finality for every version.
a native feature that starts tracking future replacements would still need
an authoritative historical witness for these three cases. maintaining a
codex build would add a distribution and upgrade obligation. a supported
source capability avoids that obligation.

independent claude opus 5.5 reviewed the gate and confirmed this blocker.
its private receipt `codex-history-capability-opus-20261124T015234Z.json`
has reopened sha-256
`bd140657b61dbcc008271ef62c4f03f5092577c7ac23f3626713c8720c62bd50`.

#### selected-history repair

the owner accepted capture of the currently selected codex history. preserve
the original uuid, cut and saved parts. after confirming a missing checkpoint,
resume from the same admission cut and retain unseen selected replies once.
the two inaccessible intermediate tails remain an explicit coverage gap.
[recovery spec](../codex-history-recovery.md)

candidate `76c20e7a68cf72c69ab2838a58b91b1ec6638ef0` passed on mac with
exact pinned dependencies. the read-only replay matched 2,647 frozen
occurrences, 176 eligible records and three terminal digests. disposable codex
and postgres preserved old parts and reopened old and new replies, including
equal text with distinct ids. the rehearsal checked restart after lost
acknowledgement, stale event and error fencing, active histories, missing cuts,
changed checkpoints and a later append. schema `0020→0021` preserved the stopped
table inventories. an isolated restore reopened a multipart original and note.
opus reviewed the exact tested candidate. the detached worktree and temporary
probes were removed.

private reopened receipts under the same evidence directory:

| proof | file | sha-256 |
| --- | --- | --- |
| live red | `codex-selected-history-red-20261124T021406Z.json` | `7d9b49703db032dd20b3987960d3fad59e923d015ca1e0cf137d930cfb926ad9` |
| three read-only selected histories | `codex-selected-history-native-green-20261124T021831Z.json` | `c64d7e977825cf12a644d7fd00529af81198fdca427698832626421dee287218` |
| exact candidate and cleanup | `selected-76c20e7/receipt.json` | `53482fdd8d7db4130f8d0496fb9b798d6208d320b7e07013f2957671efc7cbb1` |
| end-to-end assertions | `selected-76c20e7/integration.json` | `7045dc7fda64afac149f998c3e72c09dc9b839875e1d8d2152b9e4ea77372451` |
| migration and isolated restore | `codex-selected-0021-restore-20261124T022353Z.json` | `77dec6441e1b7b105f8c3a9548fc8bd31b4727f80892bc7848f07265ab005590` |
| independent opus review | `selected-76c20e7/opus.json` | `f5007b8cb78fbcf2bcde24868d6c6fbcfe9c9c5b5b6a3af717ad48725821d797` |

the retained capture/retry regression passed under `jarvis_runtime` after
updating two mocks to the canonical append api. its reopened receipt
`codex-selected-capture-retry-20261124T023145Z.json` has sha-256
`278ee15f99ebd0940d8058d5a110cb866a2c8ae8a7918c06159c6fc5d63ea35d`.

the initial mac candidate was qualified before the historical archive cut
claimed schema `0021`. the integrated rewind repair now follows that cut
at `0022` and requires independent proof on the new release.
[historical cut](../decisions/0102-historical-capture-cleanup.md)

read-only comparison against the actual stopped historical retirement cohort
found zero overlaps with records emitted by these three selected histories.
the original terminal ids are outside the retirement cohort. the historical
cut owns its deliberate removals and sequence changes. freeze surviving
records, retired links and new leaf positions after that cut before retry.

# adr 0098. conversation capture

owner decisions, november 23, 2026. prospective design against jarvis `43ed919`. implementation, installation and [historical cleanup](0102-historical-capture-cleanup.md) are separate. this supersedes [0066’s full worker histories](0066-optchat-memory-adoption.md#d07a-retain-available-worker-histories-and-reports) and amends [native capture](0089-native-capture-repair.md), [memory delivery](../memory-delivery.md) and the [live observation boundary](../private-notes-and-rolodex.md).

## product contract

remember the conversation, what jarvis observed and what workers delivered. external tool-call/result records occupied 81% of the first 77,150 production memory positions and 94% of retained body bytes. november 23 measurement, memory note `6df7a803-8fe5-5f3d-8a20-a5ade8f39799`. admission cost and model spend are measured separately.

| source | enters shared memory after the cut |
| --- | --- |
| the one jarvis main chat | owner conversation, host facts, callback proposals/results, observed stock calls/results and delivered reports. mail and timer turns of that main qualify. memory and receipt inspections keep content-free references. |
| other top-level codex or claude chat, including owner forks | ordinary speech, source-proven human answers and reports delivered into the chat. preserve non-tool attachments, reference-only context, revisions and real source gaps. omit ordinary calls/results, including memory-tool wrappers. |
| provider-proven worker | only its report as delivered into an admitted parent. private speech and tools stay in existing provider logs. log deletion can lose them. jarvis’s ephemeral children can leave only the report. an unmarked skid terminal contributes top-level prose. a fork, title or directory alone cannot establish worker identity. |
| nexus owner chat | question, answer, attachments, citations and settlement provenance. tools stay local. |

“tools off” governs capture. agents retain execution capabilities. explicit note writes have separate admission and receipts. archived speech grants no authority. no historical import, new trace recorder, retrieval redesign or compactor repair in this cut.

## a. native conversation evidence

**provider-runtime** owns `agent_runtime/{archive,_archive_codec,_codex_archive,_claude_archive}.py`. preserve the legacy codex id chain, original native digests, stable prefix and source read ceilings. mark workers from on-record child/launch evidence, including claude sidechain/agent markers and codex spawns that also have fork lineage. a missing file with only a directory-derived relationship stays an ordinary park. inventory such sessions by identity and marker only. skip their heads and content.

classify an occurrence from itself and earlier source only. inclusive rereads must produce identical output while the owner is still answering.

- a question call alone is a skip. a matched typed delivery supplies question wording under the asker, then each selected or free-form answer and human annotation under the respondent. use source order and native question id or stable field key. skip tool previews, defaults, cancellations, bare acknowledgements and older tool results lacking answer evidence. a codex async question published as assistant speech and its ordinary user reply each enter once with their native attribution.
- decode codex collaboration states per child and claude agent/task completions or confirmed deliveries per sender. a queue enqueue/remove is bookkeeping. only the delivered conversation record can carry its report. require a delivered message and source-proven sender/recipient. distinguish failure with a report from idle status. a launch, `SendMessage` argument or child id alone proves no report.
- for claude user records inspect `origin.kind`, `promptSource` and `turnOrigin` before assigning a speaker. any stated non-human origin kind, system prompt source or task-notification turn origin precludes owner attribution, even when the other fields are absent. absent fields confer no human provenance. admit its delivered worker report only with a matching earlier worker launch and delivery identity. skip background shell notifications. ordinary human or unmarked user messages, including pasted markup, retain their existing terminal user-role attribution. missing proof can cost a real report. undecodable required identity follows the typed source-error path.

emit one `text` event per utterance. body = literal speaker text after redaction. only speech can carry closed `delivery{kind,carrier_event_id,call_id?,delivery_id?,question_id?,sender_id?,ordinal}`. kinds are `question|answer|answer_note|report`, ids use the existing 256-byte bound and ordinals start at zero. use roles `assistant|owner|peer` as evidenced. an owner excerpt must never attribute the question to the respondent. a genuine report follows the conversation event limit even when its tool carrier is clipped.

ordinary records retain their addresses and native digests. for derived speech, scope ids to the source conversation. use a reserved id prefix plus sha-256 of the canonical tuple (proven delivery id, otherwise carrier id, speaker, field, source key/ordinal). its record digest binds that tuple, source speaker and literal pre-redaction payload. a repeated proven delivery and identical record digest keeps the first carrier, including within one batch. a changed payload at that address conflicts. distinct deliveries of identical words survive.

## b. native transport and storage

**universal-memory and jarvis collector** own selection, admission and continuity. hard-cut the existing activation, sync and ingest routes to `native-archive.v4`. a supplies source evidence. the shared policy selects records before transmission. the receiver checks the authenticated lane, conversation and allowed record kinds. only jarvis’s internal publisher can select main.

```text
events request = lane, conversation, expected checkpoint and both expected digests,
                 observed_at, caught_up, ordered occurrences
occurrence = {native_event_id, native_digest, capture_digest, records: [Event, ...]}
capture_digest = sha256(canonical_json_bytes(["capture.v4", native_digest, evidence]))
```

`evidence` binds consumed origin/launch/delivery discriminants and the ordered selected ids, roles, kinds, provenance and literal content before redaction. ignored diagnostics do not participate. a skip sends only occurrence id, the two hashes and empty records. the old claude digest omits answer companions. add nullable sha-256 `source_conversation.checkpoint_capture_digest` for native lanes. pre-cut checkpoints carry null. compare every available proof on inclusive reread. store both on each new advance. this checks the revisited boundary, without scanning for historical edits.

add `source_conversation.worker_excluded` (boolean, default false, one-way for native lanes). sync conveys proven worker markers. freeze pre-existing worker rows, including any park or pending baseline, at their last cut. mark only existing worker lineage with retained native proof, including when the file has gone. refuse ingest/head/baseline work for excluded ids and show them separately from lag. new workers need only marker rows. retain ordinary chat parks for their existing repair. identity coverage still gates activation.

in `src/jarvis/{collector,memory_capture,memory_http}.py` and `universal_memory/{types,archive,store,schema}.py`, fit whole occurrences and their fanout to `BATCH_EVENTS`, `EVENT_BYTES` and the encoded `BODY_BYTES`. preserve the valid prefix before an unfit occurrence. keep source identity/parse limits, including claude’s 16 mib physical and 8 mib tool projection limits. a skippable body containing nul never enters event normalization. under existing state→conversation locks, compare both expected proofs, verify duplicate complete originals, insert records/parts/leaves and advance to the last accounted occurrence atomically. all-skipped pages advance with zero leaves. empty pages cannot advance. lost ack resumes from the central receipt. stale races cannot rewind. reuse direct-origin proof for ordinary forks. retain derived speech fork-locally, accepting occasional copies without claiming old raw tools prove new speech.

## c. jarvis main observations

**provider-runtime, kernel and jarvis main** own the live path. in `codex_sdk.py` take typed stock item start/result fields before diagnostic clipping. for shell retain command, cwd, delivered output and exit/status. distinguish empty, absent, upstream-truncated and missing completion. ignore raw echoes, deltas, aggregate diffs and permission telemetry. reuse a’s extraction for collaborative deliveries. kernel `native.py` offers validated root-thread `AgentToolUse` after containment through a non-awaiting main-only hook. declared callbacks keep their single existing publication path.

in `native_runtime.py` and `memory_service.py` use the owner archive key, attempt admission, live grant and fenced writer. identity = (attempt id, native call id, phase). persist in observation order in transactions independent of canonical publication. link a delivered peer report to its carrier even when main also kept the tool result. redact the complete provider-admitted text and retained nested fields before clipping. apply retention before fifo admission and count clipped records. cutting raw text first could split a secret. extend the one shared matcher in `policy.py` to recognize jwt-shaped tokens and google access/refresh tokens (`ya29.`, `1//0`), with synthetic positive and near-miss cases. a harmless lookalike can be redacted from capture or rejected by an explicit note write.

use `clip_tool_text` for every archived result. its head, omission marker and tail total at most 30,000 unicode code points after redaction. keep the archive omission count separately. stock shell results add closed attributes `source_output{state,omitted_characters}` and nullable `exit_code`. state is `reported|absent|truncated`. the upstream count is nonnegative when known, null otherwise. a missing result has no result phase. canonical execution and paid-read receipts keep exact recovery via `receipt.read`. the same bound applies to newly archived stock call arguments. share the clipping function, give calls an argument-specific omission marker and `omitted_characters`, and retain tool name and call id. the middle may be unrecoverable. deterministic normalization failures publish a content-free per-phase `gap/unsupported` and the drain continues.

one bounded per-attempt fifo/writer uses `BATCH_EVENTS`, `BODY_BYTES` and the existing shutdown deadline. on overflow, write loss or timeout stop accepting that attempt’s suffix and log the reason without content. set `native_attempt.stock_observations_pending` (boolean, default false) when creating an observation-eligible attempt. clear it after clean drain or atomically with one deterministic attempt-level `gap/unreadable`. restart uses existing fenced/settled attempt recovery to close leftovers under valid admission. crash after the last append can conservatively report incomplete coverage. main can settle during a stall. no tool replay, new journal or effect authority.

## d. nexus export

**nexus and the library’s nexus codec** own `nexus/services/memory_capture.py` and `universal_memory/nexus.py`. publish `nexus-turn-capture-v2`. remove the tools field, receipt query and projection loop. the librarian exposes no human-answer or worker-report tool. preserve real message text, attachments, citations and retry linkage. derive ids, count (two plus attachments and published citations), digest and duplicate proof from the same immutable envelope. local receipts/undo and explicit saves retain their paths. jarvis `memory_nexus.py` admits the matching revision and owner only.

## proof and cutover

on november 24 the owner waived the installed before/after traffic windows
and authorized proceeding directly. retain the frozen matched replay and
the installed sender, receiver, restore and conversation checks.

freeze interfaces first. a owns archive adapters and shared extraction. b owns the native wire, storage, global retention policy and the single `0020` migration, including c’s attempt column, guards and grants. c owns live sdk/kernel/main. d owns the nexus wire and producer. one integrator owns pins, locks, `dev-server/assets/memory/release-pin.json`, docs and release. the six public memory tool names, selectors and grants persist. update the closed `open`/leaf `zoom` schemas and typed readers for the optional delivery and stock call/result fields. rotate affected `memory_tools.py` and `session-compatibility.json` bindings. reopen both historical originals and new 8,000-byte parts.

| feature designer | good content and required counterexamples |
| --- | --- |
| a · conversation | real codex/claude answers and multi-worker reports have the right words, speaker and receiving chat. try a pending question, old unstructured answer, forged quote, shell/worker notices with identical markup, origin alone or turn origin alone, enqueue/remove versus confirmed delivery, nested child and ordinary fork. |
| b · continuity | real collector→http→postgres. cross a legacy codex tool checkpoint, an all-skipped page containing nul, stale/lost ack, restart and a later correction. reopen it once. exercise changed companion, conflicting repeated delivery, excluded parked worker, oversized occurrence and cut-spanning fork. inspect wire and database for forbidden bytes. |
| c · main | contained stock shell, file, callback and child. test 29,999/30,000/30,001 unicode characters, empty/absent, upstream omission, synthetic secret, nul and >8 mib patch. a 7 mib patch yields bounded call text with an exact omission count. a long result followed by ten commands must fit after clipping. stall storage during a burst and restart. main settles, later canonical messages publish, gaps reopen, original callback recovers with zero redispatch. |
| d · nexus | actual outbox→receiver. a question, attachment, answer and citation yield four originals. one tool-only decoy stays local. an explicit note reopens once. cover cancellation, retry, lost ack, deletion before publish and pending v1 export. |

per feature on macbook, the designer freezes examples and blind answers. write temporary end-to-end/live tests, demonstrate red on the predecessor, pass green, simplify and rerun. use a fresh reader/model for attributed recall. independent opus reviews design, failures and final diff/evidence. run existing checks. reopen and hash named evidence outside scratch, then delete only new probes/fixtures. record cleanup separately. [testing scope](0046-reset-testing.md)

predeclare a matched tool-heavy replay and equal busy/quiet windows before and after installation. compare positions and retained bytes per lane, kind and day, with main observations separate. the replay must shrink both totals and preserve every expected utterance. record model usage only where attributable. a parked compactor or historic backlog can absorb the gain. [capacity evidence](../issues/memory-usefulness-evaluation.md)

the recorded installed baseline is `e7f5916`/`0018`. qualify source on `0019`. install `0019→0020` as its own cut after its selected predecessor’s gates, including [0096 google verification](0096-calendar-on-demand.md#live-google-calendar). 0098 does not bundle 0095–0097 activations. recheck installed release and both collector pins. quiesce new nexus sends/retries while its old publisher/receiver finish admitted runs and acknowledge all v1 exports. a park holds this cut. if inactive, verify registration, admissions and outbox without activating. use the existing owner pause, stopped writers/locks, verified backup and isolated restore. preserve cuts and historical refs. hard-reject old producers. deferred lanes resume at their last committed boundary, irrespective of source date. prove an installed root, delivered report, skipped span, fresh recall and main observation separately.

## installed cut, november 24, 2026

the matched macbook replay fed the same tool-heavy conversation through both
collectors, the authenticated receiver and postgres. its four utterances kept
their wording, speakers and order. capture went from 199 to four positions
and from 108,155 to 119 retained body bytes. the replay made zero model calls.
the owner waived live before/after traffic windows.

before the worker freeze, the v3 recovery on `74b616a` accounted for all 39
named macbook conversations. 35 supplied 4,197 events and 4,641 new parts.
four acknowledged their existing checkpoints. all 994 earlier parts matched,
and 27 recovered replies and one unaffected follow-up reopened. the v3 operator
handed web pause 33 back to the release operator. both hosts then had `74b616a`.
the v4 candidate `403b1f7` includes the same reader repair. the private receipt
`claude-data-flow-implementation-20261124/closure-receipts.json` has sha256
`186f0a94ad1d1069bc67b26e494a745653425ddc31d719d9c912d3b4d3d87f41`.

nexus selected `e3d8352` at schema `0347`, client wire 25. its three capture
declarations stayed disabled, with zero registrations, exports or parks.
the installed native model, structured oracle, and metered openai and anthropic
requests completed. the gemini carbon request exhausted the interactive
worker’s memory. neon and hydrogen generation remain unverified. the owner’s
previous model selection was restored.

jarvis selected `403b1f7` at `0020` under the same owner pause. all six
authenticated lanes on each host used v4. the installed service rejected
native v3 and the nexus v1 envelope. a previously saved result at position
904 reopened with its exact id, digest and body. both the remote and held
copies of backup `20261124T035511711726Z-4726c5ef21114553ba4dd409e26da895`
restored on macbook and reopened an original and a note. an ordinary macbook
root acknowledged its checkpoint with 16 parts before the historical cut.

after the cut its 16 parts and both saved source digests matched. the installed
collector advanced across an omitted bash result. the later assistant text
and the delivered worker report each appeared once, with the original text
hash, sender and receiving conversation. a later poll acknowledged the same
checkpoint with all 37 parts intact. the observed interval also contained
ordinary speech and context. a whole tool-only batch committing zero rows
was exercised in the matched source checks. the live sample did not isolate
such a batch. installed native receipt sha256
`f72b37162f79a6cededd75c5eda5c2eb2bec8badd4b5c846bd269611c9ee6ee8`.

under owner resume 34, jarvis's own contained shell call and result appeared
once, with exit status zero and 33 bytes matching the independent output
hash. receipt sha256 `960d0bf0efa3e42835929e5d0e19b4e99afbbbd655ce5c7a407571bd6eafe2d2`.
the [historical cleanup](0102-historical-capture-cleanup.md) records the
result-reader correction found during this turn.

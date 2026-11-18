# adr 0086. bounded native recovery and independent shared memory

accepted 2026-11-18. the first release implements a–c at schema `0015`.
this release implements d at `0016`. production acceptance is pending.
the deployed base is jarvis `05d1c33`, provider-runtime `0ebc1cb`, kernel `3afc584`,
llm-tools `b25bd5f`, universal-memory `13ac202`, stock codex `0.160.0`, database migration
`0013`.

## outcome and scope

an unfinished request can address its eligible original observations through a bounded opening.
a refused or ambiguous native call has a finite disposition. recovery reads only actionable
attempts. external memory clients can initialize, read, save and capture while jarvis and its
native host are stopped.

of the first opening’s 2,326,106 characters, 2,249,631 came from receipts for 302 gmail message
reads and 37 searches. recovery fetched 394 mb for 108 inert attempts on the serialized owner
connection. the same event loop served the station-enclosure save.
[incident record](../issues/native-recovery-memory-outage.md)

amends adrs 0065, 0066, 0071 and 0081. retain original evidence, effect and paid-read barriers,
grants, frozen orientation, model pins and public protocols. add one main tool, one unit, two
private calls and the schema below. broader search, summarization, quotas, schedulers,
replication and corpus resets stay outside scope.

## a. recover outstanding work

at startup or between turns, hold deployment ownership and take the conversation lock. fence
only an abandoned row in scope with `fenced_at IS NULL AND product_outcome IS NULL`. the
existing unique index admits at most one. select the oldest sealed id with
`terminal_at IS NOT NULL AND product_outcome IS NULL`, ordered by `attempt_seq LIMIT 1`.
migration `0014` adds a partial index on `(conversation_id, attempt_seq) INCLUDE (id)` with that
predicate. restart the query after each settlement to find late seals on older rows.

project that id’s original provider identity, output schema, input ids, control sequence and
seal. reuse locked delivery/authority checks, original-schema decoding, stale disposition and
atomic outbox. a fence ends dispatch authority. entered effects and evidence survive. narrow
routine poll, permit, outcome and settlement queries to their used columns. apply the same
active predicate to `MessageStore._apply_control`. lock conversation → target messages →
current attempt → its invocations. the conversation lock still serializes late seals, replies
and action links on fenced attempts.

**content and proof.** count committed fences, settlements and stale dispositions. zero-work
sweeps stay quiet. an unexpected settlement/storage error identifies the attempt and stops the
drain for repair. compare a deployment-sized candidate with 108 inert incident-sized rows
against the same candidate with zero. include one valid and one superseded seal in both. separately race pause against a late seal and a fenced invocation’s reply. trace
sql projections, received bytes and cold peak rss. require zero inert request bytes, under 1 mib
additional database traffic, under 64 mib additional peak rss and an authenticated memory read
within 5s during recovery. crash and deliver a late older seal. verify one publication, correct
stale settlement and intact receipts.

## b. native admission, rejection and one fresh retry

**provider-runtime** owns fit on the lowered opening or steer during planning and immediately
before wire entry. stock sums unicode scalars across text items in `input`. start may instead
carry `toolOutput` with empty input and counts its text items. instructions, schema, nontext
items and json escapes add zero scalars. limit 1,048,576 inclusive. independently measure the
complete encoded rpc envelope with the existing serializer and legal id bound, limit 4 mib
inclusive. return measured size and violated limit. the kernel exposes the provider fit result.
jarvis owns batch selection.
[stock start](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/request_processors/turn_processor.rs#L551)
·
[stock steer](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/request_processors/turn_processor.rs#L1048)

add
`AgentSubmissionRejected(attempt, code=input_too_large, rpc_code=-32602, actual_chars, max_chars)`
to the public submission union, journal codec and all kernel consumers. require the matching rpc
id/method, structured stock error and integer `actual_chars > max_chars > 0`. record only these
fields. keep never-written, definite refusal, accepted and unknown distinct. contradictory
positive evidence fences authority and quarantines the protocol fault while retaining any seal.
a definitively rejected steer records its existing control receipt and defers those ids to the
next opening. log a post-fit size mismatch with both measurements. keep the active turn running.
an ambiguous steer fences the old turn.

**jarvis** removes optional waiting context and tries smaller batches in stable priority order.
a singleton that still exceeds the limit parks only that waking input. before arm, lock and
recheck the live row, park it and insert its notice atomically without creating an attempt.
continue independent work. a fitted opening refused by stock is a contract defect. park its
still-live waking inputs together and report both measurements.

on an ambiguous submission, fence and reconcile receipts. only committed owner stop/pause
suppresses a covered loss. a process exit, including systemd shutdown, is a loss if submission
was possible. drain planned maintenance first where feasible. a definite `AgentNotSubmitted`
keeps the existing failure/park disposition. a crash after arm and before initial preparation
returns the unsubmitted inputs to ordinary admission. neither charges an ambiguous loss. allow
one fresh opening after 30s for late evidence. the existing idle wake gives 30–90s on a healthy
idle host. due retries must open a turn. a second loss before this input’s own disposition parks
it. return `progressed` on the failure path only after a durable transition excludes the same
selection. otherwise yield `blocked`.

an accepted opening delivers its initial inputs. a steer joins the turn’s delivered
inputs only when the provider records it. queued or uncertain steers can incur a
loss without authorizing a disposition, callback origin or notification acknowledgment.

migration `0015` adds three fields.

| field | transition |
| --- | --- |
| `message.native_retry_after timestamptz null` | null = unused. first loss sets database time + 30s. a due nonnull value remains spent. clear on its own committed `continue`, `waiting`, `complete`, `stop` or named operator release. omission leaves it spent. enforce at selection and under the admission lock. |
| `native_input_delivery.was_waking boolean not null` | freeze at preparation for each initial/steered id under the existing lock. charge still-live waking inputs of the failed opening and recorded or ambiguously sent waking steers. exclude contextual waiters, definitively unsent/rejected steers and later arrivals. |
| `native_attempt.recovery_pending boolean not null` | set on new arm. index `(conversation_id,attempt_seq) WHERE recovery_pending AND fenced_at IS NOT NULL`. under the conversation lock settle any seal first, then consume the flag once atomically with retry/park and its notice. recheck delivery, newer authority, controls and quarantine. clear on consumed loss, settled product, definitive failure or covered owner control. |

migration defaults give existing messages a null deadline and old deliveries/attempts false
flags. grant the runtime column updates for the deadline and pending flag. `was_waking` is
insert-only. the 108 incur zero retroactive charges. leave `processing_attempts` retired. reuse
park fields, outbox and stopped `jarvis release-parked MESSAGE_ID...`. release resets only
named live inputs. a late seal can settle during delay under original authority. superseded or
parked inputs stay fenced from stale output. keep the seal and stale disposition.

**content and proof.** only a transition into quarantine inserts a canonical notice, in the same
transaction. “i lost contact with the model twice on request {id}. its actions and reads are
recorded. to resume, stop jarvis, run `jarvis release-parked {id}`, then start jarvis.”
substitute the specific size, unit and limit for a size failure. exercise equal/+1, multibyte
and multi-item counts, independent wire overflow, genuine/contradictory refusal, lost
start/steer, shutdown versus a covered owner control at catch-up, omission, late seal, unrelated work and release.
crash on both sides of charging. require no early reopening, one notice per parking transition
and intact effect barriers.

## c. make recorded observations addressable

fresh openings carry exact selected requests, current control, approvals, commitments,
stop/uncertainty facts and the frozen ready view. include counts by eligible tool id and one
instruction for finding originals. commitments carry action/request refs, verb, operative terms,
status and entry/uncertainty. remove inline historical bodies, last-100 fill, per-row prompt
reads and the steer receipt-version map. live callbacks retain their original reply. steer with
new inputs and current operative facts. admission rechecks existing causal barriers. unit b
parks an irreducible oversized input.

publish `receipt.read` only in main’s plan and local read dispatcher. zero upstream attempts,
redispatchable. replay the same callback exactly. add `receipt.read` to
`read_positions.FRESH_READ_IDS` so a deliberate new lookup sees fresh availability. input is
`{request_ref:uuid, selection}`. `selection.kind` discriminates the two closed schemas. all
fields are required, `?` means nullable.

| selection | response |
| --- | --- |
| `list {tool_id: string?, after: cursor?, limit: 1..50}` | `{kind:list, entries, next_cursor?}`. entry fields are `invocation_id,tool_id,attempt_seq,ordinal,validation,read_state?,action_id?,has_result,has_reply,arguments_preview,result_preview?`. each preview has `text,truncated`. |
| `open {invocation_id: uuid, part: arguments\|result\|reply, offset: uint, max_bytes: 1..32768, expected_digest: sha256?}` | `{kind:open, invocation_id, part, digest, total_bytes, offset, end, next_offset?, text}`. digest and offsets identify one complete byte projection. an exact end returns an empty final chunk. |

request, invocation and action refs are uuids. tool ids are strings. sequence and ordinal are
positive integers. validation is `accepted` or `rejected`. read state uses the existing journal
enum. availability flags are booleans.
resolve the executing invocation from its trusted position. require a current permit and
`request_ref` in its delivered lineage. limit both operations to the same conversation and
causal component. out-of-scope and missing ids return the same `NotFound`. keyset page
ascending `(attempt_seq,ordinal)`. bind the cursor to revision, request, tool filter, first
list invocation and last key. rederive its exclusive upper bound and validate scope on every
page, including after restart. eligibility uses recorded invocation lineage at creation.
when a callback records two delivered requests, either can address its receipt. this includes
a waiting request delivered as context. the inventory describes those recorded associations.
later results may become available. filter before limit.

fetch previews only for the selected page. cap each at 160 utf-8 bytes in the stated field
order, flag clipping. for `gmail.read_message` lead with message id, section and offset. use
actual subject, from and date in a complete recorded metadata projection. reuse header and
preview primitives. mark fragments with source id and offset. omit unavailable or ambiguous
headers. other previews show the start of the original text field or structured value/error. fit
complete entries to the 64 kib encoded envelope, always advancing by the last returned key.
exclude inspection calls and opaque retired contracts. archive inspections as content-free
references. unrelated follow-ups use the existing shared view, search and open, subject to
archive caps and any search cost.

arguments and completed typed results use canonical json bytes. reply means the original
recorded model wire text. resolve the recorded read position (including deterministic
`native-invocation:<uuid>` before link), existing model-safe `recorded_action_result`, or
recorded local result. preserve absence. if the result committed before reply recording, expose
the result and return `PartUnavailable` for the reply. preserve json nul and utf-8. reuse
`projection_digest` and `fit_text_chunk` with a 64 kib result envelope. require the digest after
offset zero. distinguish `InvalidInput`, `InvalidCursor`, `SourceChanged` and
`PartUnavailable`. a deliberate new gmail call remains a fresh observation. byte offsets must
start on a scalar boundary and make progress before end.

**content and proof.** “339 associated calls, including 302 message reads” describes inventory.
claim coverage only for inspected material. use 339 receipts, repeated ids and
`connectors._gmail_metadata` with long delivered-to, received and dkim headers before the
subject. give fresh main neither id. it must locate the subject, open a fact midway through the
matching multibyte body, survive another interruption and answer with zero gmail calls. check
metadata fragments, missing continuation, result-before-reply, sibling unknown effect, foreign
id, concurrent append and recursive inspection. an unrelated follow-up uses shared memory and
acknowledges omissions.

## d. serve shared memory independently

`jarvis-memory.service` runs `jarvis serve-memory` from the same selected release. it owns an os
identity, cgroup, memory-only database role, archive writer and bounded read pool. keep the
tailnet proxy on 8443, loopback listener on 8768, six mcp tools, native/nexus capture routes and
lane grants. no dependency on discord, stock codex or the assistant's deployment lock.
generalize `deployment_ownership` with a stable distinct key. keep its dedicated serialized
`_OwnedDatabase` connection for the writer’s lifetime. fence and exit on ownership loss.
load settings per command. only the memory service and exclusive offline rebuild load the
embedding credential. enforce the existing
append/leaf/checkpoint transactions, submission identity and append-only privileges. jarvis
retains canonical projection, internal note recovery and permit-fenced compaction, dreaming and
vector commits. both writers use the library's existing transactional memory-state allocation.

one online memory process owns the embedding credential, existing 30 search starts per rolling
minute and one concurrent embedding call. private http uses `/run/jarvis-memory/internal.sock`
(0660, protected directory). group membership authorizes jarvis and memory service identities
only. jobs run under the matching identity. mount neither private route on the public listener.

- `POST /search {input:SearchInput, cutoff:uint}` returns the closed union `{ok:true,value:SearchResult,actual_attempts:1}` or `{ok:false,error:MemoryToolFailure,actual_attempts:0|1}`. honor the caller’s frozen cutoff.
- `POST /index_batch {}` returns `{rows:[{ref:RecordReference,vector:number[1536]}]}` for up to 32 existing candidates, or the existing typed busy/unavailable failure. validate shape, finite values and unique refs. jarvis rechecks its permit and cancellation before database commit.

the caller authorizes and reserves paid main reads before sending. map a missing socket, refused
connection or proved pre-dispatch busy reply to the existing declared failure with zero
attempts. after possible transmission, propagate transport loss to llm-tools’ billed-once
exception path so it records uncertainty. no automatic rpc retry. dreaming retains run-local
accounting. indexing stays assistant-scheduled so owner input can preempt it. local ready views
and exact opens retain their existing read semantics.

split the existing four read connections 3/1 service/assistant, zero overflow, existing 5s
statement limit. grant schema usage and select on `alembic_version` and the eight memory tables.
insert only on `memory_lane,source_conversation,source_record,memory_log,memory_leaf`. update
only `memory_lane.last_inventory_at`, `memory_state.leaf_count` and the following
`source_conversation` columns — `checkpoint_event_id`, `checkpoint_native_digest`,
`last_read_at`, `capture_error`, `baseline_error`, `capture_after_event_id`, `captured_from`.
reuse existing column grants and triggers. the service cannot write
vectors, nodes or canonical assistant rows. keep model, discord and google credentials outside
the memory unit. bound assistant memory/swap separately and verify postgres headroom under the
actual host budget.

with jarvis stopped, new originals open immediately. keyword ranking can find them before
indexing if query embedding succeeds. `view` reports its ready prefix and admitted bound.
derived work waits for jarvis. memory restart invalidates disposable cursors. while memory is
down, assistant local opens use postgres and private search fails explicitly. migration `0016`
grants the new role. both units run one selected release.

| command / operation | exclusive owner |
| --- | --- |
| `memory status` | read-only, neither key |
| `release-parked`, `dream`, `memory retry-compression`, `initialize-state`, `check-paused`, `cutover-native`, `check-activation`, `attachment-reconcile` | assistant stopped, jarvis key. manual dream uses the online private search interface |
| `memory retry-capture` | for externally captured sources, memory key with service stopped. for jarvis canonical projection, jarvis key with assistant stopped. resolve an unambiguous source and revalidate under its owning key |
| schema, grants, declarations, corpus reset, `rebuild-memory [--node …]` | both stopped, acquire jarvis then memory. exclusive offline rebuild uses the existing protected credential source and embedding implementation locally |

**content and proof.** a successful save returns its existing `NoteReceipt.id`. a view with
`through=120, admitted_through=126` covers [0,120) even if all six newer leaves open. stalled
capture beyond 126 remains unknown. suspend the assistant under candidate memory pressure, then
stop it and the native host. exercise all six tools and both capture protocols. require a save
within 10s during one maximal ingest, exact reopen, truthful lag and deduplication after lost
save/ingest acknowledgements. show one combined search limit/embedding slot, denied grants,
preserved paid uncertainty, both-lock maintenance exclusion and subsequent catch-up without
duplicates. postgres and host loss remain common failure modes.

## delivery, ownership and cost

| unit | sole edit responsibility |
| --- | --- |
| a | jarvis `native_runtime.recover_native_products`, narrow journal/permit/poll projections, `messages._apply_control` fencing, `db.py` index and migration 0014 |
| b | provider-runtime `agent_runtime/{codex_sdk,codex_app_server,turn,terminal_codec,__init__}`, kernel `native{,_contract}` and shared submission consumers, jarvis `messages/native_journal/native_runtime/service` retry transitions, `pyproject.toml`, lockfile and compatibility pins, schema 0015 |
| c | jarvis `native_runtime` context assembly, new `receipt_tools.py`, `read_dispatch/read_positions/tool_composition/definitions`, archive projection and `session-compatibility.json`. check the full compiled main instructions against the existing 16,384-byte ceiling |
| d | jarvis `memory_http`, `memory_service`, `memory_workers`, `memory_tools`, `embeddings`, cli composition, database grants, deployment units/installer/activation, operations, shared memory settings, `ownership.py`, `db.py` pool composition and schema 0016. reuse universal-memory transactions |

each unit has a content designer for its examples and acceptance criteria and an independent
opus reviewer for contract, faults and final diff. write temporary end-to-end tests and witness
red on the predecessor. implement, witness green, refactor and rerun through the same entry
points. use isolated postgres, synthetic incident-sized data, real pinned stock, a disposable
live model for retrieval and controlled loss for ambiguity. retain artifact ids, results and
cleanup evidence, then delete only the new tests. [roadmap](../implementation-plan.md)

**installed cuts.** the a–c integrator owns `deploy/prepare-cutover` and `activate-release`
for `0013→0015`. d later owns `0015→0016`, `provision-database`, release installation,
unit files and service-specific credentials. validate exact source, target and stopped snapshot
at each cut. exercise the actual entry points on a candidate. one selected release serves.
retain originals, cuts, cursors, actions, unknowns and note keys.

the owner approved one verified stopped repair for `0013→0015` if the wedged release cannot
record a discord pause. retain the last actual pause/resume. synthesizing a pause would stop
pending requests and cancel unentered actions. the ordinary recorded-pause procedure governs
the later memory-service cut.

1. bind the operation to installed source `05d1c33b5dc31db96f9aef6318591ded786c3c4f`,
   schema `0013` and the qualified target’s externally selected release receipt. install a
   root-owned hold file and persistent drop-in under `/etc/systemd/system/jarvis.service.d/`
   with `ConditionPathExists=!<absolute hold file>`. reload systemd, verify the loaded condition,
   stop the old unit and verify inactive or failed state, no pending unit job, zero main/control
   pids, empty cgroup and exclusive deployment lock. accept a historical timeout/signal only
   with those proofs. record its actual systemd result.
2. extend the existing stopped snapshot and verifier for this exact transition. bind the source
   and target release receipts, last canonical control, pending mail lineage, outstanding
   actions, paid-read barriers, outbox, native high-water and capture checkpoints. use ordered
   ids and digests of original values. recheck under the lock before migration. a mismatch,
   running writer, or bad recovery copy leaves the hold in place.
3. run the qualified migrations, then stopped `check-activation` at `0015`. compare preserved
   facts, the 108 uncharged attempts and initial retry fields. fit the live mail opening
   without wire entry if it is still pending. list already-authorized queued effects that
   startup recovery can execute before discord catch-up. only then remove the drop-in and hold
   file, reload systemd and start the selected release. qualify an interrupted snapshot, a reboot during the hold, changed
   barriers and a denied early start on the candidate. retire this one-time path at d’s cut.
4. normal discord catch-up gates main admission. a retained pause needs the owner’s ordinary
   resume. settled work stays settled. verify the pending mail request from original receipts.
   verify the note from macbook codex-work2 using its original id, exact text and omitted
   conversation id. require one original receipt and one leaf. d’s separate `0015→0016`
   procedure requires the ordinary recorded pause and both writers stopped. keep fault
   injection in the candidate.

old evidence costs local calls and sometimes a separate shared-memory search. one additional
paid reasoning attempt is possible. an omitted request can carry its spent retry indefinitely.
operator release requires stopping jarvis. storage adds two narrow indexes and three fields.
independent availability costs one unit, database role, private socket and coordinated
maintenance. overnight readiness can lag indefinitely. postgres and the host bound availability.

**design review, 2026-11-18.** four feature designers reviewed the deployed source.
independent `claude-opus-5-5` at high effort challenged the contracts in session
`c94455f3-30a2-4e77-8b6d-bc9123a7d72a`. revisions covered crash/retry accounting, actual
gmail header order, paid-search uncertainty, control races and the pre-start hold. opus found
no remaining implementation blocker. the owner separately approved the exact stopped repair.
the acceptance figures above are implementation targets.

## implementation evidence

**a · recovery.** on the predecessor, one inert incident-sized request transferred
7,325,471 bytes. the isolated correction `c0df456` used a linux service cgroup
with the deployment's 2 gib high and 3 gib max. with zero versus 108 inert
requests, recovery traffic was 17,534 versus 17,554 bytes. peak rss was
231,376 versus 230,984 kib. the authenticated reads finished inside recovery
in 16.28 and 15.05 ms. sql traces identified both actionable seals and zero
inert request bytes. these are client traffic and process rss measurements.

restarts before and after publication each ended with one conclusion. a newer
delivery superseded the older product. five control/seal/reply orderings
preserved original evidence. invalid model content parks its inputs, including
a completion hiding an open action or decoded nul in response text. a failed
storage transaction preserves the seal and identifies the attempt for repair.
independent opus approved the correction after its final live and crash runs.

**0015 candidate.** linux installed `34879a3c4fb70581ea4e3b60da44b510205c16a0`
from `05d1c33` with provider `f42d6cf`, kernel `eae7b86` and stock
`0.160.0`. the frozen lock sha256 was
`c5982434ce8932825969ee47122b7b7fa4d25f243d2e8fe362a72ce7489e449e`.
under a 2 gib high / 3 gib max cgroup, zero versus 108 inert rows produced
16,991 versus 17,007 received recovery bytes. cold peak rss was 232,304
versus 232,168 kib. queries fetched zero inert request bytes. authenticated
reads finished during recovery in 19.4 and 20.6 ms.

the candidate retained the prior stop result across reboot. killing snapshot
creation left an unpublished partial copy and schema 0013. preparing again
succeeded. corrupting a recovery file or changing a paid barrier blocked the
cut. the verified stopped candidate preserved its resume, 108 inert attempts,
339 original gmail calls, unknown paid read and outbox. its pending opening
fit at 2,017 scalars and 6,294 wire bytes. the activated service returned a
receipt and exact reopen in 21 ms. the candidate used synthetic mail and
discord state. an outstanding action from an incompatible old plan blocks
activation. check the real action inventory and opening on a private restored
copy of the stopped database before migrating it.

**b · admission.** stock accepted 1,048,576 unicode scalars spread over two
items and returned its structured refusal at one more. separate wire tests
exercised equality and overflow at 4 mib. the pinned provider passed 996
tests, the kernel 188. the postgres/kernel journey covered crashes before and
after loss accounting, late seals, refusal, pause, omitted requests, one
notice per park and release of a named request. a release records the current
attempt sequence on that request to fence late originals.

review withdrew `d029f47` after an unrecorded steer completed in a real
terminal transaction. on the successor, an accepted opening and a recorded
steer confer authority. possible transmission still counts toward retry.
nine additional kernel/postgres cases passed. a queued steer named by a write
callback produced zero actions. opus independently reran the original and
successor probes under the pinned packages.

**c · receipt access.** on the frozen 0015 release, real stock ran three fresh
`gpt-6-astra`/max sessions with all 48 main tools. compiled instructions were
16,147 of 16,384 bytes. openings used 3,514, 3,530 and 1,520 bytes. the first
model found the hidden subject among 339 calls before interruption. the
journal charged one loss, waited 30 seconds and admitted the request again.
the second model rediscovered the subject, opened the original and committed
the exact answer to the canonical outbox. the third answered an unrelated
question by opening its shared-memory original and identified 746 omitted
characters. all three made zero gmail calls. search embeddings and mail
records were synthetic. the gmail tripwire stood outside the published plan.

the real admission test keeps the earlier uncertain draft and its handled
notification. a separate trial with a pending draft-reconciliation task also
requested a gmail read. the trace retained its tool name alone, so its purpose
is unknown. pending/waiting sibling admission and settlement passed separately.
the postgres checks exercised result-before-reply, scoped cursors across
restart, multibyte chunks, stored json nul, opaque retired receipts and
content-free capture. `connectors.gmail_headers` supplies the existing header
parser to receipt previews.

**d · service.** application `656e3874109167962277b3b46e1b80fc3e100507`
has the qualified 0015 code as its parent. opus checked the clean checkout.
on isolated postgres 16, 19 clients exercised all six tools (114 calls) and
both capture protocols redelivered without duplicate originals. saving during
a 64-event, 16 mib ingest took 2.317 s. with the assistant stopped, a ready
view covered [0,120) while 126 leaves were admitted. all six newer originals
were immediately addressable. resuming the assistant caught up derived work.

both private routes released their checked-out read connections on disconnect.
assistant writer contention returned zero attempts in 5.169 s without socket
entry. a lost paid-search acknowledgment after transmission remained uncertain
on replay and made zero additional calls. migrations verified both writer
locks, the recorded pause and least-privilege grants. a separate stock session
opened an unseen witness. embedding http and compaction output were controlled
in this proof. postgres and the host remain shared failure domains.

**0016 candidate.** an isolated linux host installed
`c81324fdc9719d3d9fd2d6aea5447bedc8271377` over the qualified 0015 release.
the actual handler recorded its pause. the competing memory lock blocked the
cut. provisioning preserved the 0015 credentials, and both services started
from the same 0016 receipt. pressure crossed the assistant's 2 gib threshold
six times with zero oom kills. postgres answered while the assistant was
frozen. the memory unit returned the same note in 125 ms under pressure,
15 ms with the assistant and stock stopped, and 14 ms after its own restart.

a separate 16,777,216-byte ingest took 1.603 s on the installed unit. the save
completed in 78 ms during that ingest, with one note leaf. replay preserved
the checkpoint. reopening a middle event recovered all 33 parts. the unit
peaked at 420,560,896 bytes on this corpus, with zero high/max/oom events.
opus approved the installed candidate and its two-key maintenance and
credential boundaries. actual host pressure, archive size and embedding
latency can differ. the frozen wheel, static typing and retained capture and
completion regressions passed.

## production cutover evidence

**0013→0015.** on 2026-11-18 the wedged production unit reached its six-minute
stop timeout. the persistent condition remained loaded. systemd reported zero
main/control pids, an empty cgroup and no pending job. the stopped snapshot
preserved resume 14, the pending owner mail request, its 302 message reads and
37 searches, and inert attempts 19–126. the stopped source listed zero unfinished
actions. the initial note had no committed original in this stopped snapshot.

the host had postgres clients 16 and 18. debian's wrapper chose 18 for the tcp
dump from server 16. the stream check passed, but an actual 16 restore rejected
the archive format. restoring directly with 18 rejected its `transaction_timeout`
setting on server 16. the live schema was still 0013. the original snapshot,
target receipt and deployment hold remained intact. a second export using
`/usr/lib/postgresql/16/bin` took a repeatable-read snapshot under the same
deployment lock and matched the original inventory. its receipt binds the
original manifest, archive, stop receipt and both releases.

the private pg16 dump sha256 is
`c3d44099f9523b5beb59772cc7ede273f7744623ba631d4cf90d36b8e8813e34`.
a strict single-transaction restore matched all 18 tables, the 108 attempts,
grants, extensions and sequence values/call states. postgres flattened nested
`and` expressions in three check constraints on restore. an independent
schema-only restore from the stopped source matched the recovered schema and
grants byte-for-byte. the scratch database migrated to 0015. all seven pending
inputs fit together at cutoff 3,218, with 77,955 unicode scalars and 85,796
wire bytes. the scratch databases were removed. the root-owned supplemental
archive, binding receipt and rehearsal log remain beside the original recovery
directory under `/var/lib/jarvis-cutover/adr0086`.

the same live verification and migrations passed. `34879a3` started with
resume 14 preserved. the first fresh attempt was 127. hashes of the original
339 gmail receipts matched their pre-cut values. the subsequent d release
`d49b3799adc2eceea41ec5006c5a4374591dbcb7` pins both snapshot commands to
the deployed postgres major. an independent mixed-client restore matched all
18 tables on postgres 16. opus approved that deployment-only change.

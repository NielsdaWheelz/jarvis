# universal memory: completion and nexus capture

status: owner-approved target, 2026-11-14; documentation only.
[adr 0070](decisions/0070-nexus-capture-and-memory-delivery.md) adopts the scope.
[SPEC.md](../SPEC.md) is authoritative; [universal memory](universal-memory.md)
owns unchanged storage, compression, search, note and dream contracts. this file
owns the completion delta and bounded cross-repository handoffs. the
[implementation plan](implementation-plan.md#memory-delivery) owns sequencing.

## outcome and scope

one admitted corpus serves jarvis, configured native clients and the configured
nexus owner. finish the existing memory source and prove its actual api/mcp/model
composition. add automatic future-only capture of nexus's durable librarian
conversation. capture and optional authored-note saves remain different operations.

accepted choices:

- keep postgres, the standalone library, chronological tree/views, hybrid search,
  exact opening, fresh jarvis turns and quiet first-delivery dreaming;
- nexus captures new runs admitted after activation, including new retries of old
  failed/cancelled turns; no old-run scan or historical import;
- capture once; retain captured evidence after nexus deletes its turn. corrections
  and retries are new conversation, not archive updates or semantic deduplication;
- retain durable question/answer text, saved attachment/citation excerpts and
  available persisted tool receipts. exclude prompts, hidden reasoning, streaming
  deltas, pruned uncited excerpts and otherwise-transient tool bodies;
- a pending source export survives deletion and outages until central
  acknowledgement. no transaction spans the two databases or a network call;
- complete functional integration/live proof now. broader usefulness, realistic
  load, algorithm comparisons and memory-policy experiments belong to a later pr;
- historical native/nexus/browser import, backup/restore, browser-chat capture,
  dashboard, new search algorithms, uncapped-search delivery, native context
  replacement, graph database and unrelated product slices remain outside scope.

## current source and responsibility

the october memory core/repair source exists; recorded proof applies to its exact
artifacts. it does not qualify current nexus or establish installed activation.
current nexus is one account-owned transcript: send, cancel, failed/cancelled
retry and terminal deletion. no successful-answer regeneration or message editing
exists. optional notes use current `Call.id` and `Call.principal`; preserve those
identities through the existing executor. current nexus builds fetch public
dependencies; do not restore removed private-dependency key plumbing.

| owner | responsibility |
| --- | --- |
| provider-runtime | native codex/claude archive codecs and internal-session marking; no nexus database knowledge |
| nexus | source admission, canonical terminal snapshot, pending export, publication retry and acknowledgement cleanup |
| memory library | normalized public source types, archive/leaf/progress transactions, summaries, views, search and navigation |
| jarvis | authenticated capture/mcp adapters, sharing/admission, inference, scheduling, main publication and operational status |
| dev-server | common private declaration, credentials/routes, collector/client installation and exact qualified artifact pins |
| kernel / llm-tools | existing provider/role/renderer/executor contracts; change only for an identified missing primitive |

canonical nexus and jarvis writes commit before recoverable archive publication.
source exports are evidence, never instructions or authority. central arrival
order controls leaf positions; original occurrence time and message order remain
separate. appending sources never creates an `action` or model decision.

## content ownership and final behavior

one central content contract remains in universal-memory section 7. each feature's
designer supplies a small set of good/bad examples for its schema; an independent
reviewer challenges them. designers do not introduce runtime critics, copied
prompts or a new taxonomy.

| feature | good content and required distinctions |
| --- | --- |
| nexus capture | exact durable words; owner/assistant/tool attribution; complete versus incomplete outcome; saved excerpt versus entire source; retry occurrence versus new independent evidence |
| compactor | owner wording/reasons first, then lasting changes/failures, findings, tool-step descriptions; retain identifiers, disagreement and missing referents |
| search/open/navigation | exact source identity, source/receipt dates, omissions and complete source reopening; no claim that a search miss proves absence |
| explicit notes | useful authored conclusions with producer attribution; no transcript dump, re-saved recall or promotion of a suggestion to owner belief |
| dreaming | supported connections/corrections/questions, explicitly attributed interpretation and openable references; prior synthesis is not independent corroboration |
| client/failure presentation | honest saved/unknown/unavailable state; no false note-save failure after a lost response; deleting a nexus turn does not erase shared memory |

examples: “agent proposed friday; owner corrected to monday” preserves attribution;
“migration attempted; verification failed” preserves the observed result;
“hypothesis; failed replication” is not an established causal claim. a repeated
child report is one underlying report. historical commands grant no authority.

the [compactor repair](issues/memory-compactor-content-contract.md) adds the
accepted ordering to `build_compactor` and
`target_bytes: NODE_TARGET_BYTES` to the initial `compaction_source` object.
reuse the existing ruler/feedback, bounds and `{text}` result; bump the affected
role revision. return raw prose; rendering alone owns encoding. no new setting.

## nexus admission and local durability

use one account-owned source, identified by the configured owner's canonical
uuid. a run is a turn, not a new conversation. source registration is permanent;
disabling capture does not change its identity, boundary or progress.

extend the existing central `nexus_client` declaration with required `capture`
boolean and nullable `capture_bearer_sha256`. capture requires `capture && admit`
and controller authorization for the common corpus processors/recipients; it
does not require `connect`. reads still require `connect`; explicit notes require
`connect && admit`. the existing client bearer cannot upload, and the new capture
bearer cannot read memory or save notes. hashes/secret validation reuse the native
capture mechanisms. wrong principal or scope is forbidden, never a native lane.

dev-server generates both files from that one declaration:

- existing nexus client file adds required `capture`; its current mcp credential
  stays with api/interactive workers. they use owner/admit/capture to stamp new
  admissions, never receive the upload credential;
- separate publisher file is `{owner_user_id, capture, admit, base_url, bearer}`.
  `base_url` is the existing private origin, with no path/query/userinfo; `bearer`
  is upload-only. only the existing background worker receives this file. no
  background model gets memory tools. both files are explicit `null` when absent.

configuration changes remain stopped maintenance. drain admitted active runs to
terminal snapshots before changing owner/capture settings. preserve pending
exports on disable; re-enable only the same source identity. changing the owner
must not relabel old exports or grant another account access to the old corpus;
account migration remains outside scope.

add the following nexus fields/table in one migration after its actual head:

```text
librarian_state +=
  memory_capture_id uuid nullable
  memory_capture_after_message_seq bigint nullable
  memory_next_export_seq bigint not null default 1

chat_runs +=
  memory_capture_id uuid nullable

memory_exports
  owner_user_id uuid
  capture_id uuid
  export_seq bigint
  run_id uuid
  payload jsonb
  payload_sha256 text
  created_at timestamptz
  parked_code text nullable
  primary key (owner_user_id, capture_id, export_seq)
  unique (run_id)
```

ids/boundary are both null or both set; counters are positive signed 64-bit
integers. the pending payload, identity and digest are immutable; only the
content-free parked code changes. this table has NO cascading relationship to
chat runs, messages, retrievals or tools. existing account/generation locks and
job claims provide concurrency; add no leases or per-export job rows.

activation is two recoverable commits, not a distributed transaction:

1. the publisher, with capture admitted, locks the existing account state. if
   unset, create `memory_capture_id` and copy `next_seq` into the boundary. commit
   once. this is the inclusive first eligible question sequence; no old rows are
   scanned. new runs may now queue exports even while the central service is down.
2. register those exact values centrally through `activate` below. retry the
   existing local values after failure; never choose a later boundary. any
   disagreement with an existing registration is an operator repair error.

new run admission, under the same account mutex, copies the capture id only when
the owner matches, the current client declaration admits capture, activation is
set and the question sequence is at/after the boundary. existing runs remain null.
new retries independently acquire eligibility and retain `retry_of_run_id`; the
duplicated question is an actual new request. no inherited-copy omission applies.

the sole `chat/events.py:finalize` folds complete/error/cancelled answers, including
queued cancellation and dead-generation recovery. AFTER canonical text,
citation publication/pruning and tool-status settlement, it freezes the export
and increments `memory_next_export_seq` under the account mutex, in the SAME
transaction as terminal publication. flush, then read canonical rows through
fresh SQL or explicit refresh/populate_existing in that transaction; raw SQL
updates do not refresh cached ORM messages. the existing terminal no-op prevents
duplicate exports. rollback commits neither.
do not reconstruct an answer from an uncommitted provider result or ledger seal.

export sequence follows terminal commit order: a later queued cancellation can
settle before an earlier running turn. retain question/answer sequence and source
times separately. deleting a terminal pair leaves its pending export intact.
questions wait for terminal settlement; this delivery promises no partial-turn
streaming archive. later undo or source deletion never rewrites the snapshot.

## nexus wire and central archive

the library exports closed transport values in `nexus.py`; it imports no nexus
application types. nexus's adapter alone understands its saved-reference/tool
schemas. use canonical json/digest helpers already owned by the library. all keys
are required, absence is null, uuids canonical, timestamps aware utc, and sequence
values positive decimal strings without leading zeros (boundary may be zero).

```text
NexusTurnExport
  contract_revision = "nexus-turn-capture-v1"
  capture_id, owner_user_id, run_id: uuid
  export_seq: decimal string
  retry_of_run_id: uuid | null
  question, answer: {message_id: uuid, message_seq: decimal string,
                     created_at: timestamp, text: string}
  settlement: {status: "complete" | "error" | "cancelled",
               completed_at: timestamp, error_code: string | null,
               publication_warning_code: string | null}
  attachments: [{ordinal: positive integer, snapshot_json: string}]
  citations: [{ordinal: positive integer, snapshot_json: string}]
  tools: [{id: uuid, generation_seq: decimal string, position: positive integer,
           tool_name: string, status: "complete" | "error" | "cancelled",
           created_at: timestamp, reverted_at: timestamp | null,
           arguments_json: string, result_json: string, created_refs_json: string}]
```

`snapshot_json` is the canonical serialization of the existing stored
`SavedReference` for an attachment, or published saved target for a citation.
it is original evidence text, not a second resource schema or model input object.
the three tool json strings serialize exactly the stored columns, including json
`null`; no transient executor input/output or resource rehydration. snapshot
serializers use their owning source schemas; the library treats these strings as
opaque evidence, validates canonical json syntax, and never grants source access.
attachments retain original order; citations sort by their unique published
ordinal; tools sort by `(generation_seq, position, id)`. duplicate ids/ordinals or
tool `(generation_seq, position)` pairs,
invalid times or inconsistent owner/message/terminal identity reject. require
`question.message_seq >= registered boundary`, answer sequence exactly question
sequence + 1, distinct message ids and the source's exact run/owner associations.
retain already-present `reverted_at`; later undo never changes this snapshot. error
codes use existing source codes; no exception text or invented completion.

freeze this envelope and sha256 of its canonical bytes before delivery. source
serialization imposes no new bound that could refuse a valid canonical terminal:
the immutable outbox can hold a larger envelope for repair. the publisher checks
the entire encoded request against existing `BODY_BYTES` (16 mib), before I/O.
no multipart transport or event-count quota is added. oversized envelopes stay
parked, never cropped. projected events still satisfy shared `EVENT_BYTES`,
part/open/zoom admission and tool-result retention rules. all retained source
parts must be reopenable before any central row is committed.

jarvis mounts three private source routes beside the existing native capture api:

| route | closed request / successful response |
| --- | --- |
| `GET /v1/memory/nexus/state` | no body → `{contract_revision, registration: null | {capture_id, owner_user_id, capture_after_message_seq, activated_at, through_export_seq, through_export_sha256}}`; initial through is `"0"` and digest null |
| `POST /v1/memory/nexus/activate` | `{contract_revision, capture_id, owner_user_id, capture_after_message_seq}` → registration above; exact retry returns original registration, with current progress |
| `POST /v1/memory/nexus/ingest` | `{contract_revision, expected_through_export_seq, payload: NexusTurnExport, payload_sha256}` → `{capture_id, export_seq, run_id, payload_sha256}` only after commit |

all routes require the upload bearer and current capture admission, and bind body
owner identity to the configured owner. envelope and outer revisions must match.
reuse current origin/body/request-id/error handling; no public listener, model
tool or new HTTP retrieval protocol. normal errors use existing `MemoryError`
codes: invalid input/revision, unauthorized/forbidden, unavailable, too large,
stale checkpoint or source conflict. authentication precedes parsing; no private
body/exception text enters ordinary logs.

central schema changes are limited to `source_conversation`:

- add provider `nexus`, nullable native `machine/account`, and nullable
  `capture_id uuid`; keep the existing native/jarvis lane foreign key;
- enforce disjoint shapes: nexus has capture id, owner uuid as `native_id`, null
  machine/account/relation/parent/cwd; native/jarvis has non-null matching lane and
  null capture id. existing rows are unchanged. add no jarvis table;
- store the immutable boundary as `capture_after_event_id="message-seq:<n>"`,
  source registration time as `captured_from`, and checkpoint as
  `checkpoint_event_id="export:<n>"` plus original envelope digest. before export
  1 both checkpoint fields are null. the sixteen native/jarvis lanes keep their
  current meaning; a nexus source is not a fabricated native lane;
- extend public provenance/provider filters and null-aware source rendering,
  search/open/zoom/date and repair to this explicit source variant. native client
  lane schemas still exclude nexus. no host name is inferred for nexus.

project events in fixed order: question, attachments, ordered tool calls/results,
answer, published citations. ids are `run:<uuid>:question`, `:answer`,
`:attachment:<ordinal>`, `:citation:<ordinal>` and
`run:<uuid>:tool:<call-uuid>:call|result`; turn id is the run uuid. question/answer
are separate owner/assistant `text` events. attachment/citation snapshots use
`attachment`, source reference `nexus:<owner-uuid>:<event-id>`, media type
`application/json`, and exact snapshot json as text; availability means complete
retention of the SAVED SNAPSHOT, never of its underlying document. tool-call text
is exact `arguments_json`; result text is canonical json
`{result: <parsed result_json>, created_refs: <parsed created_refs_json>}`. label
these as stored receipts; apply the existing tool-result head/tail cap with
explicit omissions. never replace the original effect receipt with current truth.

add a closed optional `nexus` attribute to these kinds, including
`memory_reference`, permitted only for nexus:

```text
{capture_id, export_seq, run_id, retry_of_run_id,
 message_id, message_seq, message_created_at,
 turn_status, completed_at, error_code, publication_warning_code,
 envelope_sha256, event_count,
 tool: null | {generation_seq, position, status, created_at, reverted_at}}
```

all keys are required. message fields name the owning question for attachments,
answer for citations, and are null for tools; `tool` is null except on tool
events/references. settlement fields describe the turn at snapshot time, never
an inferred success from prose. retain every source error/warning and tool
status/position/time above even when body suppression applies. ordinary tool
outcome maps complete→ok, error→error, cancelled→unknown; retained status makes
the distinction explicit. values derive solely from the frozen envelope.

`occurred_at` is question creation time for the question, terminal completion
time for the published answer and tool creation time for a call. results and
attachment/citation snapshots have no independent persisted occurrence time and
use null; do not fabricate one. message creation times remain explicit metadata,
including the answer placeholder's original creation time.

every projected event's digest binds its original input before suppression; the
envelope digest is separate. `event_count` counts complete logical events before
source-part splitting. metadata is evidence and is included in result-fit checks.

recognize memory tools from their canonical bound names before ordinary tool
projection. replace BOTH call/result bodies, including failed/malformed saves,
with existing `memory_reference` events. retain call uuid as save submission id;
a valid successful save receipt's stored `id` maps explicitly to
`{store:"memory_log", id}` even though nexus's persisted result omits `store`.
do not rely on a recursive reference extractor to infer it. preserve valid bounded
references from other memory results through the shared extractor. no query/save/retrieved prose enters
those events. ordinary assistant words remain captured conversation, not new
independent corroboration. use existing `archive_internal=True` when nexus opens
native generation sessions, BEFORE submission, to prevent the native collectors
from also capturing nexus's assembled context and duplicate answers.

the library supplies `register_nexus_source`, `nexus_capture_state` and
`append_nexus_export` on `MemoryStore`; writes accept the caller's transaction.
factor ordinary record/part/leaf insertion and complete-source validation from
`archive.append_events` into one shared implementation. native's 64-event upload
bound and inclusive reread wrapper remain native-only; a nexus turn is one
16-mib-bounded request and transaction, internally batched using existing helpers.
no copied SQL, separate receipt table or library dependency on jarvis/nexus.
reuse the existing secret suppression, content-free reference projection, source
part splitting and complete-fit validation; retain original digests before these
admitted transformations. ordinary logs never include an envelope or private body.

under the existing central writer/state/conversation lock order:

1. validate source/activation, closed envelope, original canonical digest and
   immutable identities;
2. check the original question event's retained `nexus` attributes BEFORE new-event
   normalization or current rendering/fit checks. matching
   capture/sequence/run/envelope digest AND complete recorded event/part coverage
   return the original deterministic receipt, even if central progress is later;
   conflicting reuse of a run, sequence or digest fails;
3. for a new export, require supplied expected checkpoint equals current progress,
   and `export_seq = through + 1`. validate normalized events and complete-fit
   bounds, then append every event/part/leaf and advance both
   checkpoint fields in ONE transaction. no partial turn, gaps or duplicate dream
   seeds. no inference runs in that transaction;
4. acknowledge only the committed identity. the permanent source attributes prove
   old duplicate receipts after the sender deletes its acknowledged payload.

nexus does not perform the native protocol's inclusive checkpoint reread. its
pending lowest sequence plus central registration and permanent duplicate proof
replace that requirement. a stale checkpoint causes a state read, never a reset,
skip, rebaseline or reconstruction from current mutable chat state.

## publisher, failure and operational contract

register one `JobDefinition` in nexus's existing `jobs/registry.py`, with
`periodic_seconds=60`; `jobs/worker.py` already schedules it. reuse job
claims/recovery; each invocation drains the configured
owner's lowest pending export first, sequentially. periodic claims deduplicate
one utc slot, not all source work: overlapping invocations must converge through
central exact duplicate receipts and conditional local deletion. add no new
source lock. reuse the memory client's HTTP timeout settings (20 seconds,
10 seconds for connect), defined once for both adapters, and
the 16-mib request bound. publish at most 64 envelopes per invocation, then let
the existing scheduler continue. no per-turn jobs, extra daemon, polling loop in
main, durable replay scope or general connector registry.

verify all four receipt fields before deleting the exact pending row. cancellation,
timeout, invalid response or lost acknowledgement leaves it intact. retry the same
frozen payload/digest at a later ordinary job invocation; only the expected
checkpoint may change after a state read. never repeat generation or
an external effect. current admission is checked before each request. an already
received exact receipt permits cleanup of that existing export only.

401/403 end the invocation without immediate retry; later scheduled work may
recheck repaired configuration. 429/temporary transport
or service failure leaves pending work for a later job. payload/digest/size/source
conflict parks the head with a content-free code and stops that source prefix.
operator retry clears only the diagnostic after fixing its cause; it cannot
rewrite the frozen payload, skip the row, reset the boundary or discard evidence.
forward repair may change a rejected contract only through an explicit amendment.

extend nexus's existing maintenance-role cli with `nexus memory-capture-status`
and `nexus memory-capture-retry <capture_id> <export_seq>`. status reads its local
registration/boundary, pending count/oldest time and head parked code; optional
central state uses the publisher credential. unknown remote progress is unknown,
not zero. retry locks the configured owner's exact row and clears only its
diagnostic; ordinary scheduling delivers it. jarvis's cli reports central source
progress only, never pretends to know the remote pending count. no private text,
status mcp tool, cross-database query or new dashboard.
the ordinary nexus delete confirmation says: “deleting this turn does not remove
copies already captured or queued for shared memory.” do not add a per-turn
capture badge or block deletion on remote I/O.

costs: one additional nexus table plus small existing-row fields; duplicate local
storage until acknowledgement; terminal-settlement latency; prefix blocking for
an irreducible bad export; extra central storage/compression. temporary exports
are delivery durability, not backup. current all-history view may still wait for
compression; changing that availability policy is outside this delivery.

## non-overlapping implementation boundaries

| writer / feature designer | exclusive production boundary and files |
| --- | --- |
| a: library | `universal-memory/src/universal_memory/{nexus,types,schema,archive,store,retrieval,tree,tools,policy}.py`; closed source values, provenance, atomic append/duplicate proof and shared insertion refactor |
| b: jarvis capture | `src/jarvis/{memory_capture,memory_config,memory_http,memory_service}.py`, new `memory_nexus.py`, one migration after current head; private source transport/admission, adapters and composed schema grants |
| c: jarvis cognition | `src/jarvis/{definitions,memory_workers,native_runtime}.py`; compactor content fix and current model/main/dream qualification; preserve canonical receipts and active-loop behavior |
| d: nexus | `python/nexus/db/models.py`, migration after actual head, `services/chat/{admit,events,timeline}.py`, new `services/memory_capture.py`, `jobs/registry.py` and `cli.py`, `services/tools/memory.py`, generation provider configuration, current delete confirmation and owning module docs |
| e: fleet | dev-server `scripts/memory-config.py`, `lib/memory.sh`, memory profile/collector assets, routing and release pin; separate upload secret and current source/client installation |
| f: integration lead | consumer pyprojects/locks, jarvis compatibility manifest/cli composition, deployment examples, governing docs and final artifact selection; sole writer of shared pins/composition |
| independent reviewers | temporary probes/content examples and review findings only; no competing production edits |

nexus owns canonical snapshot formation. library owns source-neutral representation
and append. jarvis owns transport authentication. do not move resource parsing into
the library or duplicate native codecs in nexus/jarvis. content designers a–e
apply the shared content contract to their own feature; f integrates instruction
and revision changes once. reviewers must be independent of the reviewed writer.

dependency order: settle shared source values → library and nexus/jarvis adapters
against that contract → publish exact library pin → compose current consumers →
qualify → refactor/requalify affected behavior → remove temporary probes → prepare
fleet handoff. cognition content repair can proceed independently; shared files
are integrated by their named owner. source handoff precedes external repo edits.

publish one compatible memory contract/pin for both consumers. do not downgrade
current nexus to october's provider/kernel/tools stack or claim their old equal-pin
table proves current compatibility. preserve supported consumer compositions;
any required upstream upgrade gets its own exact compatibility/live proof.

## acceptance and proof

all rows below are required functional proof, not the deferred usefulness/load
study. use a small synthetic corpus with the content examples above. model tool
choice stays discretionary in production; direct protocol checks cover every
operation, while a few actual model journeys prove composed use.

| journey | required evidence |
| --- | --- |
| native capture | real lane inventory/activation/sync/ingest/error routes; post-boundary capture; duplicate/lost-response/checkpoint retry; incomplete native tail; changed history; fork-original coverage; collector/server restart; current codex and claude persisted artifacts; no internal cognition capture |
| shared mcp | actual initialize/list/call; `memory_view`, `memory_zoom`, `memory_date`, `memory_search`, `memory_open`, `memory_save_note`; exact source/note/synthesis attribution; lexical+real embedding search; complete paged opening; frozen/stale views; auth/admit/connect denial and exact save replay/conflict |
| jarvis main | canonical input→projection→ready view→fresh native turn; all five reads; save in full plan only; scheduled read-only grants; original invocation save recovery without gate/action; failed projection recovery; current-owner loss/cancel/restart preserves canonical receipts and rejects late authority |
| compactor/dreamer | actual rendered first compactor request contains priority and numeric target; reversible controls/unicode; stable prefix before volatile task/clock; observed cache usage or explicit unavailable telemetry, no hit threshold; ready/park/restart; dream seeds/sample/cutoff/quiet completion; transactional notes/leaves/cursor; empty success and no self-seeding; one actual synthesis content case, not merely an empty live run |
| nexus tools | authenticated current librarian send and failed/cancelled retry through actual canonical tool rows; every memory operation; applicable provider-function and native-callback routes; owner/processor/read-only denials; typed outage with continued chat; committed save/lost acknowledgement/outer deadline; exact original receipt replay |
| nexus capture | successful/error/partial/queued-cancelled terminal snapshots; retry lineage; pre-cut run excluded despite later completion; activation retry preserves cut; out-of-admission-order settlement; local rollback; outage→delete→delivery; central commit→lost ack→replay; ack→local cleanup crash; changed payload/run/sequence conflict; durable excerpts without refetch; receipt-only tools and echo suppression; oversize parks without losing terminal; native double-capture exclusion |
| current artifacts/clients | frozen static/build gates; anonymous clean current image targets; no memory secrets in artifacts/logs; actual loaded native mcp config per selected home; post-boundary capture per admitted home, read per connected client, save per admitted/connected client and denial otherwise; actual nexus backend upload/read credentials and grants; exact release identities |

exercise initialization and tool-call failures at their owning boundary once:
401, 403, 429, 5xx/disconnect/timeout, malformed reply and a genuine unexpected
defect. expected outages settle typed tool failures; cancellation and defects keep
their existing semantics. do not multiply these cases across every tool/provider.
real embedding/inference/native persistence and authenticated current routes cannot
be replaced by direct-library mocks. live unavailable routes remain unqualified
unless the owner explicitly accepts a named exception; never silently omit them.

use task-owned credentials/configuration and synthetic conversations. actual loaded
fleet smoke checks follow separately authorized installation; isolated proof can
finish source qualification first. no personal-history admission or production
resumption is implied by a successful live test. document both completion levels.

## delivery discipline

for each feature: designer's examples and contract → independent adversarial
design review → temporary end-to-end/live red case for the missing guarantee and
independent review of that failure → owning implementation → green evidence and
review → refactor, affected checks and independent review of the refactor
→ independent cleanup review → delete the new temporary probes/fixtures/helpers.
already-working baseline cases remain passes; do not manufacture red failures.
record exact commits, locks, commands, observed routes/results and exceptions in
the existing integration evidence/pr. do not create another evidence archive.

use actual application composition and disposable synthetic state. mocks cover
specific faults, not live-provider or installed-client acceptance. retain existing
authorized regression groups and checks; only newly added delivery probes are
temporary. no benchmark framework, provider×tool×failure cartesian suite or
broader usefulness/load evaluator ships here.

run `scripts/verify` in jarvis/library and each consumer's required static/build
command after changes. report any pre-existing failure honestly; do not upgrade
unrelated dependencies, suppress an audit or claim behavior from static checks.

## implementation and activation boundary

this documentation task changes no code, schema, configuration, credential,
installed service or personal-history admission. subsequent source work first
adopts the bounded handoffs in the owning repositories. qualifying the selected
source artifacts precedes private installation and separately authorized
production activation. preserve original data/checkpoints and entered-effect
recovery; hard-cut only replaced code/configuration paths, never canonical history.

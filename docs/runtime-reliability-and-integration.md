# reliability repairs and final integrated acceptance

status: integrated source and isolated fault proof qualified. the preliminary
production reset is complete. the installed journey has verified fixture arrival,
pdf artifacts, a private note, a threaded draft, a private calendar update,
and actual todo, calendar and installed-worker outcomes. the first run missed
the restart window and did not independently verify native-child completion.

installed `650eb7c` completed the quiet dream. on `844fe16` main reopened
the original attachment and integrated an independently observed native child.
the next calendar update failed before action creation. on `34d1620` the
owner supplied a fresh timing instruction and the update succeeded with all
120 delivered inputs. restart catch-up admitted the owner's downtime approval.
the original send executed once and the verified self-reply was in the same
thread. the todo wake and worker wait settled. after initially missing the
fixture's completed calendar notice, main reopened its archived original,
delivered the corrected outcome, completed the three remaining owner requests
and closed the same todo. compaction and a quiet dream completed on the selected
graph. the owner then paused the application. the disposition checks passed
under pause 10. the final recovery snapshot verified. the fixture storage,
calendar, mail and channel cleanup completed. the final database reset committed,
and production started under fresh pause 11 after the empty-corpus proof.
all twelve online native lanes completed their fresh inventories under pause
11. the owner resumed through discord and the new owner message entered
the fresh archive. final acceptance remains open because [old calendar
revisions were republished](issues/calendar-revision-republication.md). under
genuine pause 13 the retained cursor returned 80 previously published revisions.
the operator preserved the corpus and recovery snapshot. the [authorized
correction](decisions/0085-preserve-google-cursors-during-correction.md) remains unexecuted.

[adr 0075](decisions/0075-v2-completion-and-subscription-model.md) and
[adr 0077](decisions/0077-production-acceptance-and-fresh-reset.md) govern f2.
the amendments below govern reset order, compaction, ready orientation and dream
limits. the implementation evidence records each observation on its actual graph.
the [roadmap](implementation-plan.md#v2-finishing-prs) owns sequence.

## goal, scope and decisions

recover from transient discord startup outages without crash loops; stop cleanly
during login/retry; retain enough safe native-failure evidence to repair the
responsible layer. perform the preliminary fresh reset, prove the assembled
product through a useful real production journey, then perform the final reset.

original audit base: jarvis `80af4e4`, landed slices 1–6 and f1, before f3's
implementation. the integrated source now consumes qualified f3 `001cc8d`
(runtime `1fed26c`), with unchanged cognition pins, main astra/max, memory sol/xhigh
and deliberate native-child/per-session skid choices. f2's measured dreamer
capacity amendment is recorded below. installed acceptance still requires the
exact selected artifact/configuration/host pair and genuine owner ingress.

- use production exclusively for final live acceptance after isolated fault proof
  and stopped cutover. no concurrent gateway with its token or autonomous actor
  on its mailbox/calendars. no destructive fault injection into production.
- use one authorized synthetic self-email with a test pdf; actual owner messages
  exercise ordinary approval and catch-up. no owner impersonation or third-party
  recipient. tests must inspect outcomes, not merely accept model claims.
- an irreproducible historical native incident may remain OPEN after diagnostics
  and representative reproduction pass. new demonstrated defects must be fixed.
- reset discord/jarvis/central shared history and all work/waits before the real
  journey and again after acceptance. preserve private repos, credentials, real
  google data and original native/nexus chats. the owner selected this order after
  the [historical preparation backlog](#historical-preparation-limit) blocked
  main; fresh-corpus proof does not qualify that backlog's latency.
- adr 0079 changes free-copy and serial-batch policy after fresh capture exposed
  substantial new preparation work. originals, source cuts, fixed models and
  full-tree construction stay binding. its exact contract and trade-offs live
  in the memory contract; source and actual installed proof remain separate.
- adr 0081 removes foreground full-preparation waiting. use the same fitting
  ready prefix as native clients, with explicit coverage/admitted backlog and
  unchanged canonical inputs, receipt context, effect barriers and admitted
  archive-read scope. indefinite stale or empty historical orientation is an
  accepted trade-off. retain idle full compression and strict maintenance
  preparation; no new task, timer, fairness mechanism or fallback.
- adr 0082 bounds dream seeds by committed ready coverage while preserving full
  admitted reads and unbuilt seeds. after main reports no work, the existing
  due-nightly attempt precedes compression/indexing; an absent or zero-progress
  attempt falls through. one bounded dream can delay those batches and later
  ready seeds may wait until the next night/manual run. no new scheduling task,
  mode, schema or grant; fixed roles and atomic completion remain.

non-goals: new features, orchestration/notification systems, standing benchmark or
test harness, general retry framework, native protocol relaxation, automatic
unpark, legacy execution paths, model fallback, new credential/budget/browser
products or runtime history-deletion tools. ordinary approvals stay conversation.

## a. discord startup and stop

the current `run_service` calls `gateway.start` once and later awaits it during
shutdown without interrupting login. pinned `discord.py 2.7.1` replaces its HTTP
session on each login; retrying that same client leaks sessions. `close` + `clear`
retains a closed connector in that version. use its public lifecycle, not private
field repair.

the current transitive aiohttp DNS resolver uses executor-backed `getaddrinfo`;
cancelling login cannot stop that thread and Python's runner can wait minutes
for executor shutdown. create each gateway with public `aiohttp.AsyncResolver`
and `TCPConnector`, passed through public `discord.Client(connector=...)`.
declare exact compatible aiohttp/aiodns dependencies; retain the already selected
aiohttp version unless a demonstrated issue requires change. own and close the
explicit resolver after its client/connector; the connector does not own an
externally supplied resolver. no resolver-thread killing, private client fields
or executor-shutdown bypass. qualify actual process exit under non-answering DNS.
explicitly close the owned connector even if stop precedes HTTP-session creation;
`Client.close()` alone then has no session to close. resolver closure follows.

target internal composition: `run_service(service, gateway_factory, token,
shutdown, memory_http)`. the factory creates the existing `DiscordGateway` with
the same owner sink/ready handler. worker, deployment ownership and memory HTTP
start once. login attempts do not rebuild the service or repeat action recovery.
capture the latest canonical owner source id before this process opens gateway
ingress; retain that fixed cut for every readiness catch-up in the process.
reading the watermark in `on_ready` is too late: a live message can advance it
past downtime messages. reconnects may rescan one bounded newest history page;
the existing sink deduplication prevents duplicate canonical persistence. add no
separate cursor store or mutable coverage tracker.

1. create an unbound gateway and call public `login(token)`.
2. on a classified transient failure, fully close that client, wait interruptibly
   and create a fresh client. after success, recheck shutdown and bind that one
   client through existing `service.bind_gateway` exactly once.
3. run public `connect(reconnect=True)`. discord.py owns websocket connection and
   established-session resume/backoff. do not duplicate that implementation.
4. `on_ready` serializes readiness with one local lock. validate the configured
   guild/channel/permissions, then perform bounded canonical catch-up. only
   successful catch-up opens the existing startup-ready latch; recheck service
   shutdown after sinks finish. do not reset that latch on every later disconnect.

jarvis-owned login/readiness retry policy: `1, 2, 4, 8, 16, 30` seconds, then 30;
no retry-count exhaustion for a transient outage. honor a valid longer server
rate-limit wait. retain the library's rate-limit/request handling; no outer login
timeout that cuts short `Retry-After`. no new environment setting or systemd
restart-policy change.

| retry | fail explicitly |
| --- | --- |
| transport timeout, DNS/network interruption, disconnected/truncated response, HTTP 408/429/5xx | invalid token, forbidden/missing configured resources, other 4xx, certificate/trust failure, invalid configuration, local permission/resource errors, unexpected exceptions |

use exact public exception/status/errno classification, shared by login and
readiness; no blanket `OSError`, `ClientError`, `Exception` or `AttributeError`
retry. SDK-handled rate limits need no second retry counter.
keep the shared classifier, backoff and interruptible-network helper in
`src/jarvis/discord.py`; `cli.py` owns composition, not duplicate retry policy.

readiness retries only the network regions: configuration/channel lookup and
collection of one bounded history page. extract `_collect_history` from
`bounded_catch_up`, keeping its captured `after_source_message_id` and limit fixed
across retries. persist accepted owner messages afterward through the original
sink/dedup path, OUTSIDE retry and cancellation helpers. database/sink failures,
`on_message` failures and arbitrary event-handler errors remain fatal.

replace `on_error`'s immediate client close with synchronous failure marking,
`stop_ingress()` and content-free logging. the lifecycle owner observes that
stopping event directly, independently of connect completion. recheck
`event_failed` after draining admitted callbacks so an error racing owner stop
remains nonzero. no new failure bus/future or early HTTP close.

use one small interruptible-I/O helper for public login/readiness reads
and retry waits. it races an owned transport/timer child against the stop event,
cancels and joins only that child, and rethrows real completed failures. replace
the gateway's stopping bool with a stopping event as needed. never pass a ready
handler, database sink, entered write, `connect()` or client `close()` to this
helper. connect itself can await close; cancelling it can poison shared cleanup.

stop order: close ingress admission; request cooperative service stop; interrupt
network/retry children; let their owners finish cleanup; drain admitted callbacks
and service work; close clients, then join connect without cancelling it. do not cancel the gateway
owner while it awaits `Client.close()`: the library's shared closing task can
otherwise remain cancelled. preserve simultaneous permanent/unexpected failures;
only intentional cancellation/stopped transient retries become a normal stop.
with no entered work, a stop during blocked login/backoff must finish within five
seconds; entered work retains the existing drain/360-second service policy.

startup still permits existing authorized action recovery/bookkeeping before
catch-up. new main reasoning/background memory/event publication retain their
existing startup gates. no broader offline-mode policy is introduced.

upstream concern: pinned `connect(reconnect=True)` appears to dereference `self.ws`
after initial websocket creation fails while it is still `None`. source inspection
also found this in upstream master; neither proves a runtime reproduction. add
one controlled initial-connect probe. if confirmed, repair discord.py's owning
branch and adopt an exact qualified fix/release, preferring an official fix when
available. no monkeypatch, `AttributeError` catch or copied reconnect loop. update
dependency/pin/runbook claims together; retaining 2.7.1 is conditional on proof.
also qualify public close during websocket backoff: stock sleeps can outlast the
service stop deadline. the same bounded upstream lifecycle handoff must make close
wake that wait and finish connect without masking its original fatal exception.
close-then-join alone is insufficient unless this public behavior is proved.
disable raw SDK exception logging through public logger configuration; retain
controlled host outage/recovery/failure facts, not library response bodies/traces.

## b. native diagnostics and repair

the [native issue](issues/native-protocol-diagnostics.md) retains three failed
attempts across slices 3–4; only the second slice-4 failure was narrowed to progress
validation. do not infer one cause. current progress validation chains
`ValidationError` into `NativeDefect`, then logs only its class. two root validators
emit indistinguishable `value_error` codes. terminal validation also discards its
reason. kernel propagation/fencing already preserves original exceptions/evidence;
no upstream diagnostic redesign is currently justified.

add one private jarvis projection, reused before existing run parking, terminal
failure handling and command failure propagation. emit into existing logs, not
new database fields, native receipts or a telemetry service:

```text
event: "native_failure"
attempt_id: host attempt uuid | null
boundary: "run" | "terminal" | "command"
exceptions: [{kind, frames: [{module, function, line}],
              validation: [{code, location}], validation_total}]
truncated: boolean
```

closed projection: at most four causes, four innermost owned frames each, eight
validation entries total, eight location segments and 8 kib valid json. follow
explicit cause, otherwise unsuppressed context; bound cycles. `kind` is a known
exception class or fixed `other`. frames contain only installed owned-code
module/function/line coordinates; never absolute paths or source lines. source
pins in evidence give those coordinates meaning. drop excess entries with
`truncated=true`, never crop serialized json.

validation codes come from public `pydantic_core.ErrorType` plus the static codes
below; unknown codes become `unknown_validation`. schema locations admit declared
fields/fixed union labels and list indexes;
replace unknown strings with `?`. even input-free pydantic errors can expose an
unknown private property name through `loc`. never emit messages, `str`/`repr`,
arguments, context, inputs, notes, locals, private ids/payloads or payload digests.

replace these existing ordinary validator errors with `PydanticCustomError(code,
existing_constant_message)`, without context. preserve conditions, order and
byte-identical `model_json_schema()`; this changes diagnostics, not valid behavior:

| current check | code |
| --- | --- |
| invalid utf-8 | `jarvis_text_utf8_invalid` |
| progress byte bound | `jarvis_progress_bytes_exceeded` |
| duplicate action refs | `jarvis_action_refs_duplicate` |
| blocker on nonwaiting disposition | `jarvis_nonwaiting_has_blocker` |
| waiting without blocker | `jarvis_waiting_missing_blocker` |
| blocker/action-ref mismatch | `jarvis_blocker_action_refs_mismatch` |
| duplicate input dispositions | `jarvis_input_dispositions_duplicate` |
| progress with dispositions | `jarvis_progress_has_dispositions` |

provider public `AgentRuntimeError`/`AgentRuntimeDefect` roots currently escape
the cli's type-only handler and can produce raw tracebacks containing provider
strings. catch them at that existing nonzero-exit boundary; apply the same safe
projection and retain fail-stop behavior. do not convert provider defects into
recoverable `NativeDefect`. log before parking/propagation so a later persistence
failure cannot erase the initiating cause.

reproduce the two candidate progress violations and malformed terminal output with
synthetic faults to prove distinguishability and unchanged recovery. then exercise
the representative actual scheduled-worker and native-workspace/progress paths on
the final stack. synthetic faults prove diagnostics, not historical causation.
repair any reproduced current defect at its responsible prompt/schema, jarvis,
kernel or provider boundary; change no protocol merely on suspicion. when no
current cause is reproduced, retain the issue and state that precise residual risk.
no endless model tournament or repeated live runs after meaningful proof passes.

## c. final composition and content

inspect actual composed definitions/native-session material, not just prompt
strings: goals/personality, owner timezone, source framing, clock, memory view,
complete published schemas/grants, callback/native authority, exact f3 selections
and effective child/worker choices. preserve three distinct role contracts.

f1 measured 16,372/16,384 bytes at its largest tested system prompt. consolidate
repeated evidence/authority/silence/replay guidance before increasing any bound;
retain distinct exceptions, personality/goals and explicit progress rules. do not
hide overflow in another instruction channel. measure final system/developer/output
schema sizes with actual and longest supported representative timezone. any needed
bound amendment must name the measured requirement and owning contract.

the measured dreamer composition requires 292,817 initial context bytes for its
complete host table, the existing full 64,000-byte seed and 8,000-byte older sample,
and actual role/time/identity framing. the owning
[memory contract](universal-memory.md#daily-dreaming) therefore raises
only the dreamer's cumulative host context cap from 262,144 to 327,680 bytes
(320 kib), originally with dreamer role revision v4. adr 0082 advances the role
to v5 without changing these bounds. shared allocation and the other finite
token, turn, tool and elapsed bounds retain their values. this permits 65,536 more
rendered context bytes; existing post-read overflow behavior still applies.

adr 0083 subsequently raises only dreamer's cumulative reported-input ceiling
from 160,000 to 1,000,000 after the actual composed role reaches 241,692 in three
turns. owning revision becomes v6; output, context, turn, time and tool bounds
stay fixed. the owner accepts a 6.25x resource threshold, including cached input,
and existing post-generation overshoot. it is not a monetary bill or a guarantee
that every ten-turn path or weekly account availability will fit.

adr 0084 subsequently raises only cumulative host context to 1,048,576 bytes
and advances dreamer to v7 after the real v6 run reaches the context guard.
valid maximal seed/sample plus eight bounded read frames size this amendment;
all other bounds and behavior stay fixed. the 3.2x threshold and possible earlier
exhaustion of unchanged input/time/native limits are accepted, without a
maximal-path or useful-completion guarantee.

the content designer reviews each feature:

- outage logs state fixed phase/reason, attempt and next delay; one recovery fact
  is enough. no raw response, token, URL or repeated discord outage announcements.
- native failure notices use existing failed-response behavior: work stopped,
  existing effects/evidence remain for inspection. diagnostics stay operator-side;
  malformed output never becomes a successful-looking answer or auto-retry.
- useful results lead with findings, correct attachment page/section references,
  source links, reply routing and local times. distinguish draft/created/scheduled/
  sent/completed; report material limits without routine narration or dashboards.
- briefs carry task, needed context, constraints and expected result. integrate
  child/worker findings; launch/input/idle alone proves no useful completion.
  unrelated events may settle silently. tests can request both delegation paths;
  the permanent prompt must not require a scripted procedure.

## d. cutover and one live journey

one integration owner reconciles f1/f2/f3 source, pins and schemas. source migration
head is currently `0013`; inspect the installed head before selecting migrations. restore
`deploy/activate-release` from the qualified primitive's responsibilities in
`50611a3`, not by copying its obsolete branches. use current release helpers,
`dev-server-deploy` and `sudo -n`; retain the shared deploy lock, clean-stopped
checks, exact host/application pair, current activation checks and canonical
control. remove the intermediate unconditional refusal only after source readiness.
no fallback SSH target, automatic authority resume, old scheduler or retained
legacy migration/execution branch.

before production starts: original-release disposition of incompatible actions/
waits and reminder accounting; existing stopped database/runtime snapshot;
selected migrations; actual private-notes origin/bootstrap and schema-5 host
mapping; private r2 access; discovered canonical calendar ids with complete
owner-only ACLs. use the existing operations procedures, not another installer.
the owner's fresh-start decision permits cancelling old commitments instead of
recreating them. never discard entered/unknown work to bypass activation checks.
qualify activation script refusals and successful selection using controlled
system/command boundaries before its actual production use. code rollback is not
database rollback; failed cutover leaves the service stopped for explicit repair.

after the preliminary reset and fresh source cuts in section e, the installed
journey uses harmless synthetic content and bounded real work:

1. verify the installed artifacts, sole gateway/actor, canonical control and quiet
   google baselines. the owner posts a real task in the configured channel:
   review the incoming fixture, research its claim, draft a reply, make a private
   preparation block, delegate independent checks and schedule follow-through;
   explicitly ask before sending. no fabricated owner message or approval.
2. an operator helper delivers the authorized self-email outside jarvis's action
   store. independently verify the recipient is the owner. use a unique subject,
   harmless two-page pdf and one material correction on page two; retain exact
   fixture ids. no blind resend after ambiguous delivery, extra recipients or
   private material. mail arrival must wake main through the real source adapter.
3. main reads full relevant message/attachment content, retains the original in
   private r2, reads a useful real web source and writes a concise workspace note.
   integrate one native child's result and launch/register a wait for an installed
   codex worker's meaningful independent check. use f3's actual model-choice
   capabilities; retain the
   owner-deferred `claude-work` live NOT_RUN boundary.
4. inspect a real unsent threaded draft and an owner-only calendar block with no
   attendees; verify the corrected conclusion, routing and source citations.
   the calendar's approaching-event fact exercises real ingress; its own mutation
   echo may correctly be suppressed. observe the actual event fact, not a mock.
5. retain a pending send proposal, scheduled todo and registered worker wait;
   cleanly restart the application. the owner's ordinary approval during downtime
   must arrive through real catch-up. independently verify the self-addressed
   plain-text reply. reopen the original attachment and consume the actual timer/
   worker outcomes using the same references, with no relaunch or duplicate write.
   arrange the fixture timing so the wait is still registered at the restart;
   record evidence instead of inferring this from a quick successful run.
6. deliver a useful, grounded result through the real discord outbox; verify
   original receipts and terminal dispositions. inspect workspace/git after
   interruption; native commands retain their own recovery domain. confirm
   actual memory roles/quiet completion on the final f3 composition. use existing
   stopped `jarvis dream` when needed for bounded installed proof: under adr 0082
   it consumes committed ready seeds with the full admitted read/reference cutoff
   and leaves the nightly marker unchanged. no overnight wait/new hook.

reuse existing depth/format proofs where unchanged; no full connector/media/fleet
matrix or competitor-parity claim. fault injection remains isolated. ordinary
installed-worker capture policy is unchanged, so synthetic worker histories can
enter shared memory before the later reset. record reality, not a claim of total
candidate isolation. close relevant installed-cutover issues only on real evidence.

## e. fresh history resets

adr 0078 authorizes this finite administrative procedure twice: before the real
journey, then after acceptance. neither reset is a product capability. before the
first, retain the preliminary observations and stopped `0013` inventory/recovery;
before the second, retain actual journey outcomes and current recovery evidence.
use canonical pause to stop pending requests and cancel unentered work, without
claiming completion. finish/reconcile entered effects and task-owned work and drain
the outbox before either wipe. never erase a failed proof or nonterminal recovery
obligation. preserve unrelated running native terminals.

retain one verified current recovery artifact through each wipe. replace the old
`0008a` cutover artifact with a stopped `0013` snapshot through the unchanged
snapshot helper before the first reset; similarly replace that artifact with the
current stopped `0013` state before the final reset. temporarily retain the
predecessor privately outside the helper's snapshot parent, create the new dump
and private-state/configuration copies, run helper verification, then dispose of the
superseded full artifact. retain concise original manifests, hashes and retarget
receipts, plus exact historical uncertainty rows/receipts outside replaced full
artifacts. never overwrite or delete the predecessor before its successor verifies.
this narrowly supersedes pre-migration-artifact retention through acceptance; it
adds no backup framework or indefinite snapshot retention.

helper verification checks the manifest and selected release receipt, presence of
the private-state/declaration copy directories and `pg_restore --list` readability.
it does not qualify a restore or hash every copied private file; record any
separate operator hashes with the private evidence, without implying helper proof.

the three separately reviewed finalized retired `agent.stop` uncertainties keep
their exact original private receipts and unknown-effect status. only the reviewed
finite ids may pass the stopped reset gate; changed/current or unreviewed unknown
effects remain blockers. retaining an uncertainty never makes its effect known
or replayable.

quiesce jarvis, memory HTTP writers and native collectors. remove history only
from the configured discord channel using operator authority; verify permission
and complete enumeration first. do not recreate the channel or broaden bot tools.
delete exact fixture draft/calendar/file resources and the recorded incoming/
self-reply Gmail message ids after independently recording their outcomes; a sent
draft id may already be absent. preserve nonfixture thread messages and real
google data. use owner-side cleanup when existing scopes cannot delete sent mail;
do not add inbox-housekeeping tools or broaden OAuth grants. if deletion is interrupted, keep the
service stopped and resume the exact inventory, not a broader selection.

clear these 18 application tables together through the stopped administrative
boundary; preserving canonical admitted history would otherwise republish it:

```text
message, action, model_decision, read_position, native_attempt,
native_invocation, native_input_delivery, memory_log, memory_summary,
memory_lane, source_conversation, source_record, memory_leaf, memory_node,
memory_state, work, attachment, event_cursor
```

preserve schema/alembic head, roles/grants, append-only guards and private config.
use an explicit finite table allowlist, not an indiscriminate database drop or
permanent privilege relaxation. restore all guards in the same controlled reset;
reseed `memory_state(id=1)` with empty defaults. existing `initialize-state` creates
the sole fresh, non-memory-admitted paused control row. work/waits remain empty;
no automatic daily-review recreation.

inventory attachment rows and actual object keys before removing metadata. delete
proved fixture keys/cache only. any nonfixture original must retain its bytes and
an exact private key/hash/source manifest outside live memory and notes git, unless
its deletion is separately selected. do not leave undiscoverable orphan blobs or
silently delete a retained contract/pdf. private notes/source repos stay intact.

restart stateless native collectors through existing complete-inventory/current-
head activation; old cuts are replaced only for these two authorized resets. unavailable
conversations retain normal pending-baseline behavior, with no old-prefix import.
nexus is recorded disabled: verify it and leave it disabled. if it is actually
active, quiesce its captured runs/publisher and coordinate its source-owned
`memory_exports`/capture registration before clearing central proof. dispose of
old pending exports and establish a current boundary; do not let them replay or
rotate capture identity under a live old run. preserve source nexus chats.

verify empty central history, no old work/waits and no old fixture retrieval before
new writers resume. start paused, validate discord catch-up and fresh memory cuts,
then obtain ordinary owner resumption. source controls use their existing enabled
defaults and quiet current google baselines; current calendar attention remains
eligible. verify genuine new owner activity/new capture without planting more
test history. old facts can still be quoted in future source conversations; this
is a reset of the corpus, not permanent erasure of preserved source files.

### one stopped correction with established google cursors

[adr 0085](decisions/0085-preserve-google-cursors-during-correction.md) authorizes
one correction after isolated proof. apply the controls above, including genuine
owner pause, disposition of entered work and verified full current private recovery.
keep the complete verified `event_cursor` rows in place across the atomic clear
of the other 17 tables. clear the configured discord channel. genuine intervening
central history and its derivatives fall within this correction. retain private
evidence for both discarded corpora. establish fresh native cuts and verify
the empty history and unchanged cursor inventory under the existing initializer
pause. after ordinary owner resumption, verify new capture, subsequent successful
google polls and absence of the old provider revision identities. current
attention remains eligible. recurrence requires a new disposition.

## implementation ownership and acceptance

| boundary | owner/files |
| --- | --- |
| discord lifecycle | `cli.py:run_service`, `discord.py:DiscordGateway/bounded_catch_up`, shutdown guard in `service.py:gateway_ready`, exact aiohttp/aiodns dependencies; fresh-client login, owned asynchronous DNS, network-only retry/stop, bounded catch-up |
| websocket lifecycle | discord.py upstream `Client.connect/close`: initial failure and close-during-backoff proof/repair; exact qualified dependency adoption in `pyproject.toml`/`uv.lock`; no jarvis monkeypatch |
| native diagnostics | one private `src/jarvis/native_diagnostics.py`, `native_runtime.py`, `terminal.py`, existing cli failure catch; no action/journal schema change |
| composition/content | `definitions.py`, compatibility manifest and relevant tool guidance only for demonstrated omissions; one integration owner coordinates f3 overlaps |
| installed cutover/reset | `deploy/activate-release`, existing deploy helpers/checks and `docs/operations.md`; temporary operator reset procedure, source-owned capture handoffs, no runtime deletion api |
| evidence/issues | this contract and existing linked issue records; remove resolved issues, retain the explicit historical unknown if applicable |

parallelize discord and diagnostics work; their cli edits own different functions.
integration follows both and qualified f3. the designer owns wording/rubric;
an independent adversary reviews contract, implementation and final evidence for
each boundary. no new standing review machinery.

temporary red → green → refactor → delete proof:

- real integration/process tests with controlled network faults: repeated login
  failure then success in one process; failed-client closure; stop during login,
  retry wait and readiness fetch; initial websocket failure and close during
  websocket backoff; fatal authentication/
  configuration/sink errors; concurrent failure during stop. prove readiness gates,
  fixed catch-up watermark, no duplicate persistence, drain-before-close and no
  leaked tasks/clients/resolvers or raw SDK payload logging. measure subprocess exit under non-answering DNS,
  not only coroutine return.
- synthetic native faults after an accepted callback, malformed terminal and a
  provider failure containing private markers in its message/cause; include a
  marker in an extra JSON property name. assert distinct bounded diagnostics and
  no markers in logs/stdout/stderr/notices, unchanged schemas, fencing/parking and
  original evidence. reject stale callbacks; no replay of effects/paid reads.
- representative actual native reproduction and the installed journey above.
  record either reproduced-and-repaired or historical-cause-unknown explicitly.
- real-postgres reset rehearsal plus controlled discord/capture boundaries prove
  the finite wipe, required singleton/control initialization, guards and fresh
  capture without old-history republication before production cleanup.

after useful proof passes, refactor duplicated paths and remove superseded code.
run affected upstream checks, approved memory regressions and `scripts/verify`;
repeat only a changed boundary or unresolved concern. then delete only this work's
temporary probes/resources. retain exact source/pins/host/model identities, live
versus controlled scope, useful outcomes, fault/recovery evidence, downtime,
reset inventory disposition and unrun/unknown boundaries here. history deletion
must not remove the concise evidence required to assess acceptance.

trade-offs: transient outages wait indefinitely with bounded backoff; bad config
still needs repair. safe diagnostics deliberately omit payloads. an unreproduced
historical defect can recur. production testing incurs downtime and genuine
subscription/provider usage. the reset deliberately discards useful history and
commitments too; private recovery material remains outside the live corpus.

## implementation evidence

reliability source: `84f4179f1178e5755ed93170da4244483491326d`, based on
`80af4e4`. independent adversarial review covered the contract, owning-layer
repairs, temporary probes and their actual outcomes. this is isolated proof;
it is not installed acceptance or a diagnosed historical native cause.

| boundary | qualified scope |
| --- | --- |
| discord dependency | exact public fork `4c137a2de1c8aa36ac1df19f654afb99856824f2`, based on official 2.7.1; no official equivalent was available in the audited upstream. all three initial no-session resume paths, handshake ownership, close/backoff and simultaneous fatal-error races are repaired in the dependency. eight controlled fault probes and 282 existing upstream tests pass; affected typing and formatting pass. |
| jarvis lifecycle | thirteen controlled service/gateway checks cover fresh-client retry, one worker/bind, stop during login/retry/readiness, callback drain, fixed page bounds, fatal sinks and concurrent event failure. actual SDK HTTP login received two controlled 408 responses, then succeeded with three distinct, closed sessions. actual local websocket 503 recovery reached HELLO/IDENTIFY; close joined a 30-second backoff promptly. these used local transport peers, not Discord production. |
| catch-up cut | an additional controlled actual gateway/service scheduling probe reproduced live id 13 advancing canonical id 10 and skipping downtime ids 11/12. the repaired pre-ingress cut remains 10 through truncated-page retry and another readiness callback; each accepted input persists once. no new cursor store or protocol fallback. |
| linux process stop | fresh frozen CPython 3.12.13 on Linux 6.8/x86-64/glibc 2.39, aiohttp 3.14.4, aiodns 4.0.4, pycares 5.2.1 and the exact installed fork. after two unanswered UDP DNS queries, parent SIGINT to whole-process exit took 1.123 seconds; service cleanup took 1.62 ms. exit 0, no bindings, one worker, no pending tasks, closed client/connector and empty stderr. an earlier five-second total-startup probe expired during 8.74-second cold imports; that setup failure is retained separately from the stop measurement. |
| safe fatal exits | actual command subprocesses with private markers in Discord/aiohttp/provider failures and causes reproduce the old raw traceback leak and now exit 1 without markers or traceback. SDK child logging is contained through public logging configuration. |
| native diagnostics | thirteen schema/validator/privacy checks and eleven bounds checks pass. both exact schema byte snapshots remain unchanged. actual kernel, controlled public app-server socket and real postgres prove three faults after an accepted billed-once read: distinct progress violations and a malformed sealed terminal. each fences/parks, rejects stale callbacks and preserves original read/reply bytes across recovery with one executor entry; the terminal retains its original seal. this proves a read callback boundary, not a write fault or historical causation. |
| composed roles | clean committed `9184f074be5d9046688cdf66ff97c65dfd6b47ec` captures actual kernel session and prepared-turn material through a nonexecuting provider port. main's SDK-joined system is 16,315 bytes for `America/Los_Angeles`, 16,328 for the longest installed IANA name; compactor/dreamer system material is 848 bytes each. developer material is empty; output schemas are 3,802/808/1,623 bytes. all 47 main callback schemas and isolated HostTable schemas match their grants structurally. fixed-cwd comparison against `45d1135` preserves main/compactor fingerprints and every role's prepared model/policy/instruction/schema material; only the amended dreamer's fingerprint/revision changes. this is source composition, not a fresh entitlement or effective-runtime observation. |
| dreamer context amendment | real migration `0013`, runtime-role PostgreSQL and public library compaction produce 32 stored nodes bounded at 2,048 bytes, an exact 64,000-byte seed and 8,000-byte older sample. the original 262,144-byte cap stops the actual worker/kernel before any provider session opens. the 327,680-byte/v4 repair prepares exactly 292,817 bytes and completes one controlled inference turn. an independent observer sees the old 36 notes/leaves and cursor 4 until commit, then 37 notes/leaves and cursor 36 together; canonical messages remain the sole paused control. model/policy, other budgets and shared allocation stay fixed. a preliminary typed-only 7.8k-node witness did not satisfy the stored-node bound and was superseded by this public-API proof. actual installed sol/xhigh completion remains part of the production journey. |
| private workspace origin | the specified private `NielsdaWheelz/jarvis-notes` origin now has an empty main branch at `fdcf2c60d176b94d4b266b104cdcba032ab83de8`. authenticated metadata reports private; anonymous API returns 404; the existing server account reads that exact branch through its existing SSH authentication. production bootstrap remains pending. |
| stopped administration | twenty exercised command-boundary activation cases plus three usage refusals pass. ten real `0008a` preflights reject operative old obligations before migration while preserving finalized retired uncertainty and stopped/completed native read barriers byte-exact. nine real dump/copy/mode/refusal checks prove snapshot preparation and verification, not restore qualification. two installer checks prove explicit canonical-calendar configuration replaces the hardcoded alias. |
| reset rehearsal | six real postgres/initializer/collector boundaries prove the finite eighteen-table atomic wipe, interrupted-wipe rollback, unchanged schema/grants/guards, empty singleton defaults and the sole non-memory-admitted paused control. controlled native-source collection proves a fresh cut, quiet old prefix, genuine later capture, retry idempotence and pending baselines. five additional controlled channel/actual catch-up/postgres checks prove finite deletion inventory and fresh channel input. these do not prove Discord operator permission, production deletion or production collector reset. |
| required checks | final runtime `9184f074` passes `scripts/verify`: frozen lock, formatting/lint, zero typing errors, 140 documentation files, sdist/wheel build and fresh wheel install, runtime dependency/CLI checks and dependency audit. the audit reports no known vulnerabilities for auditable packages; the three owned kernel/tools/provider Git packages are outside PyPI audit coverage. all three retained library regressions from exact `b616ee9` pass with zero skips; Jarvis capture/retry passes against a fresh actual `0013` database. the subsequent host allowance change is covered by the actual worker proof above. |
| journey preparation | eight controlled transport checks and independent review qualify the disposable operator helper, two-page PDF/correction and actual-owner task/worker briefs. the helper crosschecks Gmail/OpenID identity, follows complete calendar/ACL pages, retains an exclusive send-entry marker and never resends an ambiguous invocation. no authenticated audit, mail send, fixture arrival, genuine owner message or cleanup is inferred from these checks. |

the exact dependency fork adds a maintenance obligation until an official
equivalent is qualified. asynchronous DNS adds the explicit aiodns/pycares
dependency instead of abandoning Python runner cleanup. reconnect catch-up may
rescan one bounded page; canonical deduplication remains unchanged.

independent review accepts final source `9184f074`, its original tool-session
check receipts and scoped source-probe cleanup. the first capture migration
omitted its required explicit memory declaration; the corrected fixture uses the
checked-in deny-all declaration. composition setup likewise corrected invalid
synthetic encryption material. neither setup correction changed product behavior.

accepted source probes, copied test/source trees, isolated Linux runtime and
source-only databases are removed after review. 87 compact result files and
exact cleanup inventories remain private; checked-in regressions are preserved.
live journey/reset helpers and the active reset rehearsal fixtures remain for
their actual use. the retained rehearsal is explicitly fixture-only, not a
production wipe command; the real finite operation needs the stopped inventory
and disposition of the three historical retired-worker uncertainties.
production
journey and fresh reset are not yet claimed. the historical native issue remains
OPEN. at that recorded source-qualification boundary, production selected
`b6cf4b32d32f2b01291d47291a206d4fc744fce4`, schema `0008a`; production
service/configuration/history changes had not yet occurred.

### bootstrap metadata permission repair

installed source `9632d8c55acd87fa98c8f458ca107e40e6dca5ca` cloned the private
notes origin, then failed setting its new `.git` directory to `02750` with
`PermissionError: EPERM`. the checkout root was `niels:codex-clients:02750`;
`.git` inherited `02700` under the unit's `0077` umask. the unit's existing
`RestrictSUIDSGID=true` rejects explicit SGID chmod even for directories, as
[systemd documents](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html#RestrictSUIDSGID=).

one source line changes the new metadata-directory mode to `0750`: application
preflight needs group read/traversal, not SGID or group write. native commands
already run with the client group. host restrictions and existing-checkout
permissions remain unchanged; retrying an existing checkout never repairs modes.
the existing checkout is checked separately; any selected operator correction
must name the exact directory. no automatic existing-state repair is added.

a root-executed restricted transient systemd unit reproduced the actual boundary
with the host uid/client gid, `NoNewPrivileges`, empty capabilities,
`RestrictSUIDSGID=true` and umask `0077`. actual `bootstrap_notes` and real local
git clone reached `EPERM` with the original source and inherited `.git` mode
`02700`; the repaired source completed a fresh clone at `0750`. a dirty existing
checkout then retained every file byte and mode on retry. actual application uid
read/traversal passed and metadata-directory write was denied. origin/privacy
reads were controlled locally; this is not a fresh production bootstrap receipt.
old/new source sha256 values are
`ef439fb3acdca2215097681fac36957ba5987ce9e36b9ce32de0e189a514efb7` and
`70b4003e3f1ea3a8a98fdbe0e8c07f0fd0ba611ab9ca098a78b90bab7227901c`.
independent adversarial review covers the one-line fix and these exact outcomes;
private receipts remain under `source-evidence/bootstrap-mode`. only this
boundary changes; schemas, roles, pins and the host unit are unchanged.

### installer service-group permission checks

installed `7eaf262c4e57790532d333032bdeac0bae82f838` completed notes bootstrap,
then stopped at the installer's bare `sudo -u jarvis` read check. the application
account has primary group `jarvis` without global `codex-clients` membership;
`jarvis.service` supplies that client group through `SupplementaryGroups`.
the directory permissions were correct for the service identity. the installer
was checking a different group set.

four installer notes/metadata read/traversal checks now explicitly select
`codex-clients`. the two matching containment no-write checks use the same group,
so group-write access cannot produce a false pass. for these filesystem checks,
selecting the client group as primary tests the same access grant as the service's
supplementary group. no account membership, runtime identity, unit restriction or
checkout permission changes.

the operator's read-only check reproduced the bare-user refusal and passed all
four read/traversal checks plus both no-write checks with the explicit group.
a retained, owned fixture's metadata directory was temporarily changed from
`0750` to `0770`: the bare-user no-write check falsely passed, while the explicit
group check correctly refused. the fixture returned to `0750`; production
permissions were untouched by this proof. independent adversarial review and
private receipts under `source-evidence/installer-service-group` qualify this
boundary. this is not a completed installation or production acceptance claim.

### historical preparation limit

before the preliminary reset, the owner request reached canonical history and
waited for full memory preparation. 2,238 of 39,873 leaves were ready. the
then-installed 512-byte free-copy rule required inference for at least 15,257
remaining leaves before accounting for parents or retries. adr 0078 records
the resulting change to reset order. adr 0081 later removed complete preparation
from foreground dispatch. the installed journey verified dispatch with a backlog.
large-corpus throughput, warm-up time and memory usefulness remain unmeasured.

### bounded serial compaction amendment

[adr 0079](decisions/0079-bounded-serial-compaction.md) adopts the owner-approved
repair after genuine post-reset capture exposed substantial preparation work.
the standalone library is `6506ae0813edb207caf5234034acc30b7ff5fca1`, based on
qualified `b616ee9`. its immutable batch carries up to eight independent inferred
tasks and 128 exact free copies. the caller uses the existing kernel preparation
primitive to pack complete initial/retry entries under the unchanged 262,144-byte
request ceiling. completion validates the exact whole result before any insertion,
then commits nodes and persisted frontiers atomically. compactor revision is
`jarvis-memory-compactor-v4`; fixed models, kernel/provider/tools pins, main/dreamer
instructions and schemas, database schema and authority stay unchanged. manifest-derived fingerprints
include the new shared library pin as designed.

| proof | qualified boundary |
| --- | --- |
| library red/green | an actual 1,248-byte complete source requires inference under the old rule and becomes an exact free copy. seven real-postgres cases cover batch independence, source identity, committed-only readiness, rollback and observer-visible atomic frontiers. additional checks cover 128-copy selection, fitting-view refusal, exact 2,048/2,049-byte boundary, a bad second result with zero partial insertion, and public admission of near-limit metadata. |
| caller red/green | the old caller commits one of three leaves; the new caller completes two paid nodes and an exact copy through one actual isolated-kernel call. fourteen controlled-provider/real-runtime-role-postgres cases cover addressed output, per-node retries/shortest accepted candidate, initial/full-feedback escaping and repacking, free-only progress, source conflict, cancellation, canonical control change and owner loss. malformed later subsets commit neither earlier candidates nor copies. these use no paid inference or production data. |
| required checks | the library's three retained regressions pass on real postgres with zero skips, and its static/build verification passes. jarvis passes full frozen static/types/docs/build, fresh wheel installation, runtime provenance/cli checks and the existing audit scope; capture/retry exits 0 against a fresh actual `0013` database with the runtime role. the first static pass found missing explicit task annotations; the corrected pass has zero typing errors. |
| actual model content | exact inactive jarvis `0b33fc40075a601dd0dc4e6140b43c9115e68611` and memory `6506ae0`, with the unchanged qualified stock endpoint. one real personal-subscription `gpt-6.1-sol/xhigh` batch summarizes three synthetic historical sources. independent review verifies each correction, reason, identifier, clock time, uncertainty and peer-versus-owner attribution. a later sibling's attempted cross-import remains quoted and rejected. only the 516-byte third candidate is retried, becoming 504 bytes; the first two nodes remain unchanged. two actual one-shot/prepared turns, unchanged originals and zero-until-commit then three-node/frontier visibility. this qualifies the example, not general semantic fidelity or performance. |
| actual isolated authority | a separate metadata-only public-client observation matches the first prepared thread exactly: one configured/reported inherited mcp server, disabled, zero tools/errors. the retry thread is not independently mcp-observed. both actual turn-start records retain `xhigh` and approval `never`; exact model/auth/policy checks remain mandatory in the pinned live provider. raw policy settings are not independently observed. no gateway, google, embedding or production-database call occurs in this fixture. |
| disposition | independent review approves exact source, real content/route and candidate. new library/caller probes are deleted after hash receipts; live-probe cleanup retains concise content/route evidence. all four isolated databases, their owned container/anonymous volume and tunnel are removed after zero active clients. the real journey and final reset remain pending. |

the preliminary reset's complete native identity comparison finds zero overlap
between 1,885 newly captured parts and 39,825 old parts. all 44 fresh google cursors
completed with zero poll errors. one real calendar-attention request awaits memory
preparation; no action or todo exists at the recorded stopped boundary. 23 pending
unreadable baselines and a separate [native physical-record bound](issues/native-archive-record-bound.md)
remain explicit. this proves neither steady-state capacity nor broader memory
usefulness. the [later installed ready-view proof](#ready-view-activation-and-incomplete-real-journey-2026-11-17)
records foreground dispatch despite the remaining backlog.

the stopped routine replacement selects that same runtime
`0b33fc40075a601dd0dc4e6140b43c9115e68611`, tree
`90f87126700bdafcccfda957f2b4ba9969b203e6`, lock sha256
`021c330d51e24faf78dd1d934782a9b82ed758cce2721cc7138f199ba65e2f85`.
host and application use the same artifact, schema remains `0013`, the current
non-secret host mapping is byte-identical, and genuine `resume` sequence 9 is
preserved. application startup is `2026-11-17T02:33:53Z`, with zero restarts;
validated discord catch-up scans one existing input and accepts zero. the previous
installed release is pruned. hosted source ci `44001754315` succeeds.
the existing installed containment verifier passes for the new pair, including
process/secret isolation and actual worker gateway reads on dev-server/macbook;
arch remains explicitly deferred.
an initial scp timeout occurred before installation: the incomplete staging
archive's hash differed, its exact file was removed, and the ordinary retry
installed the same artifact. no migration or activation ran on that failed upload.
production coverage advances from 31 to 122 with no compaction error while genuine
capture continues. thirteen new level-zero nodes with raw source above 2,048 bytes
prove actual installed compactor inference under the new free-copy rule; raw
source reaches 8,000 bytes and these stored nodes are at most 514 bytes.
main dispatch and the complete real journey are still pending;
there is no latency or capacity conclusion from that progress.

### first valid summary amendment

[adr 0080](decisions/0080-first-valid-compaction.md) follows the owner's explicit
decision after the 516→504-byte real-model retry. the caller accepts a first valid
candidate within the existing 2,048-byte hard bound while still prompting for
512. it removes shortest-candidate tracking and soft-target retries; only hard
oversize or transient failure retries. capture/library/model/schema/authority
contracts stay fixed; compactor compatibility becomes
`jarvis-memory-compactor-v5`. larger inferred nodes may coarsen older detail
earlier; net parent cost and general quality remain unmeasured.

the genuine red uses the actual kernel and a runtime-role `0013` database: the
old caller stores the already-valid 516-byte candidate only after five
appearances, failing the one-call requirement. seven focused green cases verify
first 516 and exact 2,048-byte acceptance, exclusion of a completed peer while an
oversized 2,050-byte candidate becomes 1,500, exhausted five hard oversizes,
malformed addressing, cancellation and three transient failures. the latter
boundaries commit neither inferred nodes nor accompanying copies. setup-only
model-constant/XML parsing and interpreter-selection errors remain separate from
that behavior red. full frozen static/types/docs/build, fresh install/provenance
and audit checks pass. unchanged library regressions and the prior fourteen
caller cases are not repeated without a new concern.

exact candidate `8bc3c155c617761d26acf82c0fa662c4f135c098` then completes one real
personal-subscription sol/xhigh inference with one prepared turn. its first
1,041-byte summary preserves the complete 695-byte synthetic opaque evidence
locator, thursday-not-wednesday correction, accreditation-report reason,
unconfirmed attendee count, background fact and synthetic attribution. independent
review verifies source grounding and that the first returned candidate equals
committed text byte-for-byte. originals remain unchanged and the observer sees zero uncommitted nodes/coverage,
then one node/coverage after commit. no new mcp/raw-policy observation is claimed;
unchanged authority qualification and mandatory pinned runtime validation retain
their stated scope. this is one meaningful boundary case, not a general quality
or speed claim.

the routine stopped replacement installs matching host/application artifacts at
that exact commit, tree `855897e8b9f7f33779c4f9011e2d5ccb19b8a689`, with unchanged
lock sha256 `021c330d51e24faf78dd1d934782a9b82ed758cce2721cc7138f199ba65e2f85`.
schema stays `0013`, host mapping stays byte-identical, genuine `resume` sequence 9
and coverage through 190 survive, and the application starts at
`2026-11-17T03:24:28Z` with zero restarts. the prior installed release is pruned;
hosted ci `44008432190` and the installed containment/client verifier pass. new
controlled/live probes, duplicate padded/raw model captures, both fixture
databases, owned container/anonymous volume and tunnel are removed after reviewed
hash receipts and zero active clients. concise source/content/route/atomicity
witnesses remain private.

production coverage subsequently reaches 353 with no compaction error. main has
not opened its native attempt at this observation. the verified ordinary owner
task can queue while the fixed preparation cutoff is completed: ordinary ingress
does not cancel that preparation or move its cutoff. late steering is journaled
normally; same-turn delivery is not guaranteed. self-email still waits for the
actual canonical waiting-for-fixture disposition. the real journey and final
fresh reset remain pending.

### compaction rejection diagnostic and observed recovery

at `2026-11-17T09:11:49Z`, production parks `2112+64` as
`invalid_completion`, with coverage 2,233 of 3,039 leaves and zero main native
attempts. the original reply is unavailable through the pinned public ephemeral
contract; the selected first address does not identify the offending result.
this record retains that unknown cause and the genuine owner request.

the worker now logs only host run/requested-address coordinates and a closed
kernel stop enum, caller result-schema rejection, duplicate-address rejection or
address-set mismatch. no transcript, payload or exception prose is retained.
the durable park, models, limits, retries and atomic completion stay unchanged.
the actual postgres/kernel red parks correctly but lacks the diagnostic. seven
focused controlled green checks pass independent review: six actual-kernel paths
cover protocol/quota stops, duplicate/missing/wrong addresses and valid completion;
one explicitly controlled post-kernel result corruption covers defensive caller
validation. every rejection preserves originals and commits zero inferred/free
nodes or frontier progress. full `scripts/verify`, fresh-wheel/types/docs/audit
checks and hosted ci `44057103705` pass. the new probe and owned fixture
database/container/anonymous volume/tunnel are removed; concise proof remains.

routine replacement installs matching host/application
`c544f68c37628cece24ee9811a980853ee3897b7`, tree
`b5a1f8a808a534e3f6c0eeb95eef11520ab9f32f`, with unchanged lock sha256
`021c330d51e24faf78dd1d934782a9b82ed758cce2721cc7138f199ba65e2f85`.
initial health at `2026-11-17T09:47:37Z` reports host/application pids
2,807,962/2,818,932, successful results and zero restarts; host configuration is
byte-identical and the prior `8bc3c15` installation is pruned.

before application activation, one supported stopped `memory retry-compression`
clears only the park. fingerprints of 3,039 source records, 4,444 nodes and 3,039
leaves, coverage 2,233, genuine `resume` sequence 9 and the pending owner request
remain unchanged; the command makes no model call. the previously missing
level-6/index-33 node (`2112+64`) is absent at 09:47:54 and present at 09:49:15,
with coverage 2,241 and no compaction error. this proves genuine parent recovery,
not the original failure's cause. main native attempts are zero at that observation.
any newly reproduced rejection requires diagnosis and responsible repair before
another explicit retry.

production subsequently reaches complete coverage of the then-current 3,039
leaves with no compaction error. native main attempt
`96e13f2b-6c6b-4c89-a422-7df0a632a278` starts at
`2026-11-17T12:34:16Z`, with genuine owner request
`2487c506-4aef-4f2e-9018-554ada7377d0` recorded as initial input. its terminal is
retained at `12:38:36Z`. this satisfies the diagnostic issue's qualified execution
past blocked preparation; that resolved issue is removed. the original rejected
reply remains unrecoverable and its cause unknown. the private main/delivery and
recovery receipts remain; no historical causation or large-corpus latency claim
follows. later capture can extend the corpus beyond that completed prefix.

### first main dispatch and stopped write failures

at this first main turn, the fixture email has not yet been sent. the turn enters
calendar action `5b577ec6-cfbf-4bcc-b89a-3058400d812e`, which is subsequently recorded
uncertain, and encounters `BudgetExceeded` before the proposed todo or a later
web search enters execution. the system-suspension reply incorrectly states that
the entered action has not executed. required memory preparation succeeded;
these are separate write/recovery defects, not evidence of a continued compaction
block. the application stops cleanly at `2026-11-17T12:40:54Z`, retaining genuine
`resume` sequence 9. no hidden reschedule, repeated effect or fabricated owner
input has been used.

an exact-id read-only calendar observation at `12:47:37Z` finds the event at its
deterministic id. only start/end fractional seconds differ, each by -954,234
microseconds; owner, time zones and all other writable fields match. the
[stopped positive recovery](#stopped-positive-recovery-of-the-entered-calendar-effect) records that
source repair and actual same-effect recovery. the
[executor-capacity repair](#qualified-write-and-pending-result-repairs) addresses the
shared in-flight slot left occupied after recovery handoff; a 2,767-byte todo
request was below its 65,792-byte wrapped input limit. original arguments,
uncertain receipts and failed results remain unchanged. private receipts retain the first main
turn, write failure and independent event observation. the real combined journey
and final reset remain unqualified.

### qualified write and pending-result repairs

the source repair graph selects kernel
`9fd491a2aca24022bf1fbbf8a41c4668d55ba758`, tools
`b25bd5f08bc82eb47eb4384139cfb2623ad12a68` and memory
`f77a4c7a5f85b897fbea08066b9dd5b890c2e6d7`. memory changes only its tools pin and
lock; all twelve runtime files remain byte-identical to `6506ae08`, and its three
retained real-postgres regressions pass without skips. provider `ea9f820`, stock
0.160.0 and the main/memory model and effort selections stay unchanged.

eleven controlled actual-connector cases qualify whole-second desired calendar
encoding and strict positive comparison, including pre-io refusal of collapsed
intervals and preservation of exact observed snapshots. ten executor cases and
seven actual jarvis/postgres checks qualify independent work/read progress on the
same serial budget after recovery handoff, preserving unresolved cost, original
effect rows and nonreplayability. kernel v5's pending-result wording reports an
unresolved outcome without asserting nonexecution; supervisor/public-client Unix
peer checks preserve action references, waiting actors and byte-exact recorded
replies. these checks use controlled transports, not new production effects or
model calls. application session revision v2 captures common recorder admission;
calendar create/update bindings separately advance to v4 for precision behavior.

one full `scripts/verify` passes on the resolved graph: frozen lock, formatting,
lint, zero typing errors, documentation links, source/wheel build, fresh-wheel
installation/cli/dependency verification and audit. runtime source hashes remain
unchanged through that check; three owned Git packages remain outside the index
audit's coverage. the lock sha256 is
`b112b3f5119392c536929ff6d069462b206a36f26cb01f4715329caad068eba7`.
the unchanged retained jarvis capture/retry group passes on a fresh actual `0013`
runtime-role database with no skips. its two injected publication `MemoryError`
warnings are expected; the owned fixture is removed after zero-client and
independent container/volume/tunnel/listener absence checks.

final nonexecuting composition passes for the configured and longest supported
representative time zones across all three roles. main's joined system text is
16,322/16,335 bytes, developer text is empty and its output schema is 3,802 bytes;
all 47 captured callback input schemas match the declarations and grants.
compactor/dreamer system text stays 848 bytes, with output schemas of 1,083/1,623
bytes and unchanged grants/containment. goals, personality and role builders are
byte-identical apart from exact dependency pins; only native base wording grows
seven bytes and the two calendar guides change. callback schema/contract revisions
stay unchanged while the calendar implementation/policy precision change remains
explicit. these local request captures stop before any real session or turn;
they prove no fresh account entitlement, effective live settings or installed
consumer behavior. concise qualification and cleanup receipts remain private.

### stopped positive recovery of the entered calendar effect

candidate `0c3edfc5bd102ae6db5e8f9768dc2ff0b6309530`, tree
`1664a794983e8b44832eabcef00ae1c10791b001`, was installed inactive with the qualified
lock above. its exact hosted push verification, run `44096443485`, passes. the
matching contained host was installed; at this recovery boundary the application
remained stopped with `c544f68` selected and genuine `resume` sequence 9 unchanged.

the qualified stopped operator uses fresh verified account identity and strict
read-only reconciliation of the original deterministic event. at
`2026-11-17T13:52:56Z`, the later positive evidence resolves the original action to
typed `Success`, retaining its null account qualification. its v3 execution
contract, fractional arguments, executor-entry count of one, both original callback
rows and the old resolution fact's immutable evidence remain unchanged. the normal
atomic resolution adds exactly one admitted success fact,
`f16a39b2-00bf-567d-9b0b-458627ecb5fc`; the old fact plus this new fact total two.
no calendar mutation or action reexecution occurs; ordinary oauth token refresh
is separate from that statement. the independent database reread at `13:54:29Z`
confirms the same success, v3 contract, entry count and two facts, with one native
attempt, two action rows and no work rows. the candidate's stopped preflight passes
with zero compatible, incompatible or in-flight unfinished actions; it makes
no cognition call. concise before/observed/after, independent reread and unit
receipts remain private.

at this stopped recovery boundary, the application had not continued through the
repaired action. at
`2026-11-17T13:17:41Z`, the original event had ended and no fixture
calendar-attention fact existed, so that timing window was missed. the fixture
email had not yet been sent. production activation and genuine owner timing
steering were still separate; positive recovery alone does not complete installed
acceptance or the final reset.

### production activation and single fixture arrival

the same `0c3edfc5bd102ae6db5e8f9768dc2ff0b6309530` application starts at
`2026-11-17T15:39:48Z`, pid `3452494`, with zero restarts, the unchanged contained
host and genuine `resume` sequence 9. real discord catch-up scans one message and
accepts zero new inputs.

the one authorized self-email fixture is acknowledged at gmail message/thread
`1a1ea0e17a9c6aa3`. original send receipt sha256
`efc1fc19cc8e27583b2f3c7db83801c9c32b6f2ef679b4af7a332c5dc5f51352`,
submitted mime and fixture identity remain unchanged. independent inspection
(raw mime sha256 `f845d14159bf52d9f912150cdf509039013e47bcb78f6f4ddb9bc914093fc46f`)
finds one valid delivered rfc message-id differing from the submitted id; the
verified self account, exact acknowledged message/thread, subject, self-routing,
absent cc/bcc/effect header and single original pdf all match. pdf sha256 remains
`1241524cdb3c1a0f14a5512bfbafb1a647f2cff184cc1ef5539a5b411269a992`.
no resend occurs and no product connector defect is established.

the disposable inspector's preserved-rfc assumption is repaired in base helper
`acaf482c0f241929cbc64346472dc861bdbfaf392ad3f369099ba6a4c3741ae9`
and future updated-event helper
`8341a097849eb70a3d08a2825420949f55e7967ee01a0a244473b39c668549b1`.
inspection now requires the exact acknowledged message/thread and one valid
actual message-id, retaining the submitted id separately. reply and cleanup
ancestry use only the observed actual id. original `19bb` fails on the actual raw
message; intermediate `6502` also reproduces acceptance of a duplicate recipient
header. the final repair requires exact single, defect-free subject and
self-routing headers. 23 base controlled cases plus five shared rfc flows through
the future helper pass and are independently rerun; the new probe and its
compiled file are deleted. all
other helper functions, including the respective calendar branches, remain
byte-identical. private `operator-rfc-repair-receipt.json`, sha256
`44db59c2fb8b2bd72b134473e447ac880cdef1a3cbf979effbe72d0a55d78605`,
binds source, retained baseline, red/green, review and disposition evidence. only
the base helper is staged; the future helper remains conditional on a real
same-event update.

fresh live inspection succeeds, retaining `observed.json` sha256
`170f28501b161567da3ee6009f9976c76018a48702151e8ef683efb5e5b0a019`.
the real adapter publishes exact canonical mail fact
`e0ab7889-d8fc-4105-9e88-b7306f008c48`, pending and unparked, with payload
`observed_at=2026-11-17T15:40:08.603735Z`. its canonical
`created_at=2026-11-17T15:09:14Z` is the message's source time, not application
admission time. these observations prove arrival and the original pdf bytes;
native pdf processing, the combined journey and final reset remain pending.

### coordinated native instruction publication

two owner-authorized stopped maintenance windows publish native memory startup
instructions from dev-server prs 222 and 223; the final source merge is
`d3b5c7a792008ddadb733d50aa106cfc0cbfa7c0`. the final six instruction files have
sha256 `8590c23d7d2c3cd2359bd4184d7c57e3ed63a5a0ef586e803d5d88280a205bae`
and mode `0600`; their managed source asset has sha256
`fabc89711bdd4f7f312fbf5207bb2ef46696a91860bc21155a559c187f352e15`
and mode `0644`. the publishing peer reports all eighteen protected configuration,
authentication and collector files unchanged. f2 independently verifies the seven
published files, selected release and host mapping; it does not repeat that
eighteen-file audit.

each window cleanly stops the application and passive observer with no entered
obligations, preserves canonical `resume` sequence 9 and the pending fixture,
and restarts the same selected `0c3edfc5bd102ae6db5e8f9768dc2ff0b6309530`
release after the contained host's service-identity verification. that verification
submits no model turn. the final fresh passive observer initializes at
`2026-11-17T18:19:19.138092Z`, before application start at `18:19:29Z`, pid
`3735981`. contained pid is `3731846`; observer pid is `3735581`. independent
health checks report all three running, success, and zero application restarts.
real discord catch-up scans one message and accepts zero new inputs. there is no
canonical control write, migration, release change or source-cut reset.

the peer's final devbox codex and claude probes each complete a frozen ready
snapshot before task reads, covering `[0,3693)` with admitted bound 7118.
codex abandons its first snapshot, then fully completes a second without observed
splicing. the corresponding macbook probes cover `[0,3664)` with admitted bound
6556. this is bounded startup-order evidence, not complete capture or general
usefulness qualification.
the claude probe rereads an oversized saved memory-view result. two verified
native saved-file reads reintroduced summary prose as ordinary tool output at
tree positions 5,528–5,531 and 5,980–5,983. private
`saved-memory-view-tree-membership.json` has sha256
`4b113a40191c68cf0353d8e297aab854b35aff5a7f21f5dbfece9a15a56e9f93`.
the [bounded page repair](#bounded-view-page-repair-and-actual-consumer) covers
this specific feedback path.

### bounded view-page repair and actual consumer

memory `ab8db62c203128b2012577a8183f752567794503` changes only the existing
view-page packing comparison and its one global limit. jarvis records that limit
in the view binding's revisioned policy inputs. public schemas, 64-kib hard
result/admission limits, other binding policies, frozen coverage and the complete
128,000-byte automatic main view remain unchanged.

real-postgres/public-mcp red observes a 64,936-byte first page for a controlled
89,477-byte complete view. green packs that view into seven whole-node pages,
with a maximum framed page of 16,146 bytes. append, cutoff, stale-cursor and
complete frozen coverage checks pass. an actual reachable 2,048-byte control
node fits; an 8,000-byte original remains byte-exact through open and leaf zoom,
whose framed results are 57,289 and 57,287 bytes. independent reruns pass.

one actual claude `2.1.326` cli session makes eight memory-view calls and reads all
103 controlled nodes inline, ending its exact cursor chain at null with the
expected node digest. the maximum framed result is 16,146 bytes and no spill
occurs. the session exits zero after 26 seconds. private
`view-pages-consumer-live.json`, sha256
`0d9a31dce5cbcec60bbc93f4a8dabe0640cdbaacf5bba1b072b7e402fd58234d`,
retains public metadata, hashes and counts, excluding reasoning and assistant
prose. this uses strict fixture-only mcp, only `memory_view`, disabled builtins
and requested nonpersistence; native capture absence is not independently checked.
it qualifies that representative restricted client, not a default-client causal
comparison, numeric spill threshold or all memory-derived generic reads. more
cursor reads remain the trade-off. installed activation is pending.

### stopped compactor configuration failure

at `2026-11-17T19:32:57.291815Z`, memory parks `4040+8` with
`invalid_completion`. the installed safe log identifies run
`da07ca83-482e-4b5c-af34-1e6933e75478`, `reason=kernel_stopped` and
`stop_kind=configuration_error`. that kernel stop covers several configuration,
provider, protocol and invariant failures; it does not establish malformed model
output, exhausted quota or an instruction-file cause. the original isolated
exception and terminal are not retained.

the application and passive observer stop cleanly at `19:34:14Z`. canonical
`resume` sequence 9, the pending unparked fixture, all 13,224 admitted leaves,
coverage 4,106 and original nodes/frontiers are retained for the retry comparison.
active main
attempts, unfinished actions, unresolved reads, todos and undelivered replies are
all zero. observer capture 3 ends with operator stop and zero selected roots;
there is no post-email native-work proof to infer. the contained host remains
running on the same selected release. the diagnostic gap is under repair at
this boundary; no retry or cause attribution is claimed here. the later stopped
recovery below retains the original failure separately.

one reviewed service-identity observation at `19:56:14Z` uses only public account,
default rate-limit and visible-model reads under a hard 60-second process bound;
it submits no model turn. subscription authentication is present, and the catalog
offers `gpt-6.1-sol` with `xhigh` and the expected dispatch identity. default
seven-day usage is 99%, resetting at `2026-11-19T04:20:27Z`; no five-hour field is
returned. private `cognition-health-live.json`, sha256
`981b7977d80b3e00fb3ad187f5427387abdbb0fc5e925bd8718cc07e7515351f`,
retains only approved booleans, counts and numeric usage. current account/catalog
health neither identifies the lost failure nor proves inference will succeed;
default usage does not establish every model-specific limit.

### isolated diagnostics and ready-view source qualification

kernel `36f9c6b8e4674916d185eb14e522e77d21c3f86f` retains fixed failure metadata
on the existing outcome event at three exception boundaries, before accounting
or cleanup can replace it. the caught type/code remain distinct from at most two
verified owned source coordinates selected through a bounded explicit cause
chain. the host's narrow logger excludes all other fields. public-client
validator faults, wrapped causes, bootstrap failure and secondary cleanup failure
pass independent privacy/reason-distinction checks. actual runtime-role postgres
proof retains one filtered log, unchanged originals and the original atomic park,
with zero nodes, actions or native attempts. the new probe is deleted after
hash receipts. the lost production cause remains unknown; installed retry and
progress through `4040+8` were pending at this source-qualification boundary.
the later stopped recovery below records their separate completion.

memory `e52a48dc48376f73ae94601d080110c3a26dcfa3` factors one immutable
`ReadyView` and one measured renderer from the existing external-view assembly.
main consumes that value directly; its compactor dependency is removed. main's
owning revision is v2 and only the affected `memory.view` implementation becomes
v4; other role/binding schemas, limits, authority and models remain unchanged.
the new coverage/backlog framing stays inside the existing historical budget:
an actual boundary measures 127,999 bytes before metadata, 128,035 unadjusted,
and 126,274 after shared fitting.

the first of two actual native-runner/kernel turns through a controlled public
unix socket completes with ready coverage 122 and admitted bound 130 despite a
construction park. exact operative inputs and original local `memory.open`
receipt bytes survive; the second turn checks receipt continuity in its fresh
context. unprepared admitted originals open, later originals remain fenced, and
input polling after construction progress preserves the frozen historical value.
this is local-read proof,
not a new billed external-read claim. official mcp traversal returns six complete
pages matching the direct ready value, maximum 16,263 framed bytes. strict actual
dreamer preparation still blocks as required. library static/package checks and
all three retained postgres regressions pass without skips; independent review
approves the exact source and proof. all new source probes and their matching
compiled files are deleted after hash receipts. the exact combined graph uses
kernel `36f9c6b`, memory `e52a48d`, tools `b25bd5f` and provider `ea9f820`, with
lock sha256 `05fed3cfb5694318413dda82b041942ad592ada4cc6021d24f1acfee3bfcbaba`.
full static/types/docs/build/fresh-wheel/cli/audit checks pass, as does the retained
runtime-role capture/retry group on pristine `0013`; only its two expected
injected publication warnings appear. public-registry audit coverage still
excludes the three owned kernel/tools/provider git packages. private combined verify/capture receipts
have sha256 `ff7c98bbf831586590e2a4cf5017a0df6e3bc7fcd543b7b3cdd91151d6951c2c`
and `5618e6f514f3a70fcd257e7b7c2fa34eaae1616a054d36aa00ff63b20fa1f13d`.
the owned synthetic mcp fixture and rootless postgres resources are removed after
zero-client checks; original journey inputs, operational helpers and bounded
proof receipts remain. installed journey, compactor recovery, quiet production
roles and final reset remain separate obligations. strict production dreaming
still requires its full frozen prefix; adr 0081 does not waive that cost or proof.

### ready-view activation and incomplete real journey, 2026-11-17

release `ca101b5a242dfa65aab9f95314bc2d630a01d983`, tree
`3e915890f43c3b432e6290c643bdfbd83f4bdf2b`, passes hosted
[verification](https://github.com/NielsdaWheelz/jarvis/actions/runs/44181059738).
same-release contained-host qualification and normal activation pass without
changing schema `0013` or canonical resume sequence 9. the application starts
at `21:43:34Z`; actual astra/max main starts at `21:43:47Z` with ready coverage
4,106, admitted bound 13,224 and the original `4040+8` compaction park intact.
this proves foreground availability under that park, not memory catch-up.

the actual fixture original is retained and opened. both pdf-page renders and
extracted text exist at `21:47:18Z`; the useful private note exists at `21:51:58Z`.
original action receipts prove one unsent draft, its unentered send proposal,
an update of the same private calendar event, one todo, and one installed
sol/high worker with a registered 600-second idle observation. its matched
outcome at `22:03:47Z` retains a visible report of useful independent checks
followed by a foreground delay measured at 480.006382231 seconds. a later main
integrates the actual calendar attention, todo wake and worker report without
relaunching the worker. independent stopped Google inspections positively match
the exact draft MIME and updated owner-only event; they do not qualify timing.

at `21:56:55Z` terminal `8cf5836e-5500-40ca-bdb0-b5baa3c80b4f` incorrectly
attached the send proposal to two distinct parentless owners. only
`19c6030b-fc0a-4c06-a7d1-8257498d6be1` owned that proposal. the host rejected
the whole disposition and preserved the seal, roots and original effects.
private `main-8cf-failure-fixture-state.json` has sha256
`a950162994fcea03d6078f068d0bae409d3a25600452a67d7cf54093307eeb31`.
the [later approval](#restart-catch-up-and-original-send) and
[completed roots](#recovered-final-and-reset-disposition) verify the genuine
continuation. the separate
[observer gap](#installed-native-child-and-action-lineage-failure) leaves native-child
completion without sufficient independent evidence. the exact root command
transcript is unavailable; actual file artifacts and git state remain inspectable.
the one-time wake is 574.597771 seconds after committed creation; event start
is 1,185.783290 seconds after the update receipt, with exact 20-minute duration.
no tolerance or hidden rescheduling makes those exact requested offsets pass.

the application stops cleanly at `22:08:26Z`, after a zero-active-attempt,
zero-unsettled-read, zero-entered-action and zero-outbound-watermark observation.
contained host and observer remain active; canonical resume is unchanged. no
restart occurred while both the original timer and worker wait were pending:
the combined restart criterion is **MISS**. the draft is still unapproved and
unsent. at this stop, genuine continuation, sufficient native proof, quiet
production roles, compactor recovery and final reset remained outstanding.

the source clarification defines approval-reference authority through the
input's recorded `parent_request_id` root. main revision v3 changes no guard,
schema, tool grant, model or isolated-role fingerprint. actual joined instructions
shrink six bytes to 16,316 configured and 16,329 for the longest supported zone.
the controlled construction proof and independent content review pass; it does
not guarantee future model compliance. its new probe and matching compiled-file
inventory are removed after the private receipt, sha256
`c44e4e520c2ce13a929bd1e60ffd086a58fbcdd94b87640b624156e97318db3d`.

the child-only observer repair discovers unknown typed thread identifiers through
one public metadata read per bounded candidate, then verifies actual parent
lineage before retaining later events. an unverified triggering completion is
discarded, not buffered. four controlled unix-websocket cases cover absent child
announcements, missing ancestors, unrelated-root privacy and early-completion
loss; independent rerun passes. its exact new probe is deleted after review.
root item subscription is unchanged. actual workspace/PDF artifacts and git state
own file-behavior verification; no exact root command transcript is claimed.
capture 4 stops explicitly with five roots, zero selected native frames and
seven unverified frames; acceptance remains false. the repaired helper is staged
with sha256 `43ac01aa14dfd02762dde0aed8c83bea90c63fffa310907f99db23992366fe5f`;
a new live child capture is still required.

one explicit stopped `memory retry-compression` succeeds on the installed
diagnostic stack. the existing stopped `jarvis dream` then commits the formerly
missing `4040+8` node: 507 bytes, sha256
`3a3c2bdd75db693f2e493e50752bd99a56bb40dd910809589b242693f1bd489b`.
coverage advances beyond 4,106 with no construction error. this resolves the
diagnostic/retry gap and proves recovery progress, while the lost original cause
remains unknown. at that recovery observation, the manual run was still
preparing its frozen prefix; no dreamer
completion, whole-prefix readiness or latency qualification follows.

### ready-seed dreaming source qualification, 2026-11-17

the owner explicitly adopts adr 0082 after the bounded stopped repair run ends
with coverage 4,127 of 21,234 admitted leaves and no dream completion. library
`87a202cd124de9d09a50b2548b1938f403c8e1b8` changes existing seed selection and
its public readme only: committed ready coverage bounds seeds; the full admitted
cutoff still governs reads/references. no api, type or schema changes. actual
postgres red/green covers eight cases, including unbuilt admitted-original reads,
future fencing, successive progress without skipped seeds, synthesis exclusion,
no-ready/rebuild coverage below consumed progress, and atomic completion/rollback.
the exact independent rerun passes. static/build checks and all three retained
library regressions pass without skips; the new probe and matching compiled-file
inventory are removed after hash receipts.

jarvis removes dreamer's compactor dependency and gives the existing due-nightly
attempt priority after main reports no work. absent, already-claimed and
zero-progress attempts fall through to compression; nonempty synthesis-only
bookkeeping counts as progress. four actual service-drain cases and their
independent rerun verify priority, fallthrough and foreground interruption.
dreamer's owning revision becomes v5; main stays v3. models, policies, grants,
context ceilings and the other dependency pins remain unchanged.

the actual worker/kernel/tool-executor proof uses runtime-role postgres `0013`
and a controlled public provider port, not a real sdk/socket/model. the original
worker with the new library held fixed rejects on its actual persisted park.
the new worker opens an admitted original beyond ready coverage and commits one
note/reference/leaf with consumed progress 0→1 while preserving the park. an
independent snapshot before the provider terminal sees the old notes/cursor;
the library proof separately owns uncommitted-transaction visibility and rollback.
actual no-ready and repeated-nightly calls enter no provider work or seed progress.
a synthesis-only call advances 2→3 without inference or another note.

independent source/proof review approves the exact graph; private review receipt
has sha256 `ef9ec5929a81599321c9ab9bb3eade3eb417dba5d1e8d2b512fd9c3c4f489853`.
combined frozen static/types/docs/build/fresh-wheel/cli/audit checks pass, as does
the retained capture/retry group on separate pristine `0013` under the runtime
role, with only its two expected injected publication warnings. owned git
kernel/tools/provider packages remain outside public-registry audit coverage.
combined verify/capture receipts have sha256
`28ae96729ca8d6a5b4ef5e82e1f3c5516d03c3a306ba0b0c3ca9235d5c68d4a2`
and `4d9be3a7d9b494adc2318de5801a1c8bbfb56ef06e230ec2d222c7277ee4b103`.
new caller/service probes, the copied baseline and its owned compiled file are
deleted after independent review; final caller receipt has sha256
`fa1c97682753d50dfec666b5d6b737653e288e69875f201e99b150feaa335f76`.
the one rootless postgres container, its exact anonymous volume and ssh tunnel
are removed after zero sessions in all three assigned databases; both listeners
are absent. original operational helpers, journey inputs and private receipts stay.
actual fixed-model quiet completion, the real restart journey and final reset
remain separate outstanding obligations.

### first ready-seed installed dream remains incomplete

candidate `40325aa212877fa93f405192105e4d0216e5b291`, tree
`7cf2ae67713e6096b76fbd6d3260de4614d71ad6`, passes hosted
[verification](https://github.com/NielsdaWheelz/jarvis/actions/runs/44194510237).
its same-release contained host qualifies without a model turn; application and
observer remain stopped, canonical resume 9 and the unentered proposal preserved.
the actual stopped dream returns no completion after 61.269 seconds. consumed
progress, notes, canonical work, read positions and the nightly marker stay
unchanged. the command's zero exit is not accepted as successful completion.
the dreamer diagnostic and budget follow-through requires bounded repairs and
qualified retries below; the original cause is unknown. later
[quiet completion](#installed-quiet-completion-and-native-startup-failure)
does not identify this earlier failure.
a finite REST-only read verifies the revised journey as genuine owner message
`1572385672046575698` in the configured channel, with 1,547 characters and body
sha256 `69c51f3dcba15413cf802b2aca5a315d2a0645c17b7064cbd2b37029aaf5dba1`.
only the file's final newline is absent. no Gateway connects or canonical input
is inserted; normal startup catch-up must still admit and verify that message.

the minimal source diagnostic repair shares compactor's existing closed kernel
failure projection with dreamer and logs the actual stopped enum/run identity
before returning. no role, pin, model, retry, return or cli-semantic change.
actual worker/kernel controlled-port configuration and provider faults reproduce
the missing logs and then produce distinct safe diagnostics; independent rerun
passes without private sentinels/causes or a completion call. no postgres, model
or socket probe is needed for this logging path. the exact new probe is deleted
after review; private final receipt has sha256
`6eedc294ad14f4244a106dfd13e070f7348adc9f3810f1a2c35dead17176ac1e`.
format/lint, zero typing errors and all 153 documentation files pass. the real
retry still owns cause identification and installed quiet qualification.

the same-release `ff440f4` host qualification passes. its actual stopped retry
retains `budget_exhausted` after 53.746 seconds, run
`afcccfe0-74a9-4170-bd70-e66760f4128c`; no seed progress or notes commit.
that enum covers several exact kernel decisions, including a native turn timeout.
it does not establish account quota, elapsed-time exhaustion or a specific token
ceiling. a bounded diagnostic refinement adds the exact decision tag to the
existing kernel outcome event and fixed public numeric metrics at the host;
limits, roles and model policy remain unchanged while the cause is measured.

kernel `42e1ff252a3232b14721f7068d86812c1c3a7e08` adds five closed budget tags
at the original decision sites. it preserves cooperative-time `>=`, token `>`,
turn/repair counting, native-timeout precedence and quota classification. the
host forwards only a known tag or its original safe failure projection and logs
fixed returned metrics; unknown token counts remain null. `native_turn_timeout`
names the runtime's timeout classification, not a proved remote-server origin.

twenty controlled actual-kernel cases compare original outcome enums, returned
metrics, clock-read counts and semantic event kind/attributes after excluding
only the added tag events. event timestamps/run ids are outside that comparison;
no complete event-byte identity is claimed. applicable isolated/decision/event
conformance, static/types and standard isolated package build pass. independent
producer rerun passes, as do two actual worker/provider-port/kernel→host cases
and four mixed/unknown metadata privacy groups. producer/host probes, copied
baseline and owned compiled files are deleted after hash receipts. private
producer/host receipts have sha256
`5cd5f2eda87195ded398375a37143be951ee795505a236e14ad432d4c7893542`
and `a6830484e8206c8ce10c706d58c870b6f792b31ca8bae0a2ed0f0d82ebf8316f`.
kernel hosted [ci](https://github.com/NielsdaWheelz/llm-agent-kernel/actions/runs/44200305924)
passes. all four consumer pins match; frozen installed kernel bytes match the
reviewed source, and combined static/types/docs/build/fresh-wheel/cli/audit checks
pass. unchanged stateful capture/library evidence remains scoped to its original
graph; new budget-branch proof covers this diagnostic delta. all limits stay
fixed, and the qualified actual retry still owns live diagnosis/completion.

### measured dreamer input ceiling and owner amendment

actual `0ec6f73` run `7b3a3c61-a319-4a3b-914e-cea2852da226` reports the exact
`provider_input_tokens` guard: 241,692 input tokens, 1,094 output tokens, three
provider turns and 40.581 kernel seconds. no notes or consumed progress commit;
canonical work and the nightly marker remain unchanged. this establishes that
run's input limit, not the exact causes of earlier uninstrumented attempts.

pinned-source accounting and continuation audits find no duplicate counting,
cache re-addition or accidental bootstrap resend. complete portable tool schemas
produce a 218,636-byte host table and 220,802-byte empty-seed bootstrap. reducing
that publication contract is separate work. the owner explicitly approves adr
0083's single input ceiling of 1,000,000; dreamer becomes v6. all other caps,
models, instructions, policies, grants, schemas and dependency pins stay fixed.
the owner accepts the 6.25x reported-input threshold and existing post-generation
overshoot; ten maximal turns and weekly availability remain unguaranteed.

the product diff is exactly those two literals. actual compiled-role/kernel
controlled-port red/green admits the measured aggregate 241,692 across three
scripted read/read/finish turns, accepts exactly one million, rejects one million
plus one at the original input guard, and preserves unknown usage as null. these
scripted steps reproduce aggregate resource use, not the unseen original live
steps. other composition compares exact. independent rerun passes, and the new
probe/matching compiled-file inventory is removed after hash receipts. private
final receipt has sha256
`97d03b01872891c812f7e759f2556efd5c1f220ae077ec3c0dc2f51470c05701`.
frozen static/types/docs/build/fresh-wheel/cli/audit checks pass; unchanged
stateful evidence remains scoped to its original graph. actual installed quiet
completion, the genuine restart journey and final reset remain pending.

### installed context failure and owner context amendment

the stopped real fixed-model dream on
`d34d30c223cae8e8cb22750ca1dd965bdb852543`, run
`734fb92c-70a8-498b-9e21-bf34e71e58ca`, passes the former input threshold:
421,532 input tokens, 1,063 output tokens and five provider turns. it then stops
at the separate 327,680-byte context guard with `ContextLimitExceeded`, reported
as `kernel_configuration` at `continuation_context:184` / `_project:242`.
kernel duration is 42.025 seconds and cli wall time 53.882 seconds. the zero exit
is not completion. private `d34d30c-stopped-dream-live.json` has sha256
`4d04463a070906b2cd9449a392548a57bc4f1793023620a947e064934cbc9fc1`.
this establishes the current context failure; it preserves the earlier measured
input diagnosis and the unknown causes of earlier uninstrumented attempts.

an independent stopped read-only snapshot retains 21,234 leaves, ready coverage
4,127, dream cursor 0, synthesis notes 0, 177 messages, 12 actions, 37 read
positions, seven native attempts, canonical `resume` sequence 9 and nightly
marker `2026-11-17T21:56:55.974535Z`. private
`d34d30c-post-dream-quiet-state.json` has sha256
`4772dc0e72e3f084f4940cca8b3041eb4b47a3f196039570ea4da6066d1bc1d0`.
no seed progress or synthesis commits; canonical work remains unchanged.

source continuation/rendering audits find no duplicate bootstrap or read frame.
actual compiled-role/kernel controlled-port sizing uses an exact 64,000-byte
seed, 8,000-byte sample and nodes bounded at 2,048 bytes. the bootstrap measures
292,790 bytes; the prior actual-postgresql proof's different identity/framing
measured 292,817. valid ordinary and escaping-heavy memory pages pass the actual
archive-admission and shared framed-result checks. one supported near-limit
ordinary read adds 65,533 bytes and reproduces the installed failure site under
the unchanged ceiling. a test-only copied 1 mib ceiling completes one and eight
reads for both payloads. eight ordinary reads consume 817,054 visible bytes and
825,582 canonical bytes before the final provider turn; including the final
terminal gives 825,809. canonical size follows actual submitted inputs plus the
public recorded-model-context projection. these repeated controlled pages size
the existing envelope; they are not actual storage reads or the original live
sequence. no database, socket, account, model or production call occurs in this
source proof. independent rerun of all six cases passes.

the owner explicitly approves [adr 0084](decisions/0084-dreamer-continuation-context.md)'s 1 mib ceiling,
leaving 222,767 bytes after that conservative canonical total. 512 kib fits only
three maximal read frames. only the context literal and dreamer's owning revision
v6→v7 change. the 3.2x host threshold retains all other caps, fixed models,
instructions, grants, ready/full-read scope and atomic completion; it promises
neither maximal-path fit nor useful completion. the installed quiet proof below
subsequently resolves this measured context blocker.
private measurement and independent receipts have sha256
`349cc4f6c79a77bf3c43ccf0b225e54c0374e44f94d0efd0cd868dfc06634aa5`
and `b7ff9b6b1d84ead495af8547272ac88473f0ac760d8087f99ac706aa2dd58895`.

the final actual compiled v6 role reproduces the one-read failure before the
product edit. actual compiled v7 then completes eight valid ordinary and
escaping-heavy reads through the real kernel and controlled public ports.
normalizing only the context cap and owning revision gives exact prior
composition, including provider policy, instructions, output/HostTable schemas,
other limits, dependency pins, other role revisions and compactor fingerprint.
independent final rerun passes; no invalid oversized storage fixture or generic
kernel boundary matrix is added. private final green and independent receipts
have sha256
`f57f3e10d728eefdd901c9e4c46aed67a33b4f18c4de8f30d90fe42c12b4d03e`
and `02f86ace55d347086a04e0d5c51e19049bc15885bacd232536ead8d39f991a36`.
the new probe and any owned compiled file are deleted after hash inventory;
original red/green, sizing and review receipts remain. source qualification alone
does not establish the installed quiet proof below, the genuine journey or final
reset.

### installed quiet completion and native startup failure

actual installed `650eb7cb5db3604358906771dff472003232bfa0` completes the stopped
fixed personal-subscription sol/xhigh dream with no wrapper. the real cli reports
success; an independent stopped repeatable-read observation verifies three
committed synthesis notes, their references and tree positions 21,234–21,236,
and consumed seed progress `[0,4127)`. leaf count becomes 21,237 while ready
coverage stays 4,127. all eleven canonical table fingerprints and the nightly
marker remain unchanged. private `650eb7c-quiet-completion.json` has sha256
`39890b4acca342cc4c56c747eec917fd329ecc227920fedc2ac9fa40a25cc006`.
independent adversarial review accepts this installed quiet-role evidence;
source postgres proof separately owns transactional isolation/rollback.
the resolved context issue is removed. all five earlier failed attempts retain
their original receipts, diagnoses and explicit unknown causes; later completion
does not make them successful. this qualifies the stated quiet run, not every
maximal path, nightly workload, useful synthesis or the combined journey/reset.

the following application startup catches up six channel messages and accepts
the genuine owner continuation `36f388f2-be2a-4f3c-8d17-f4264d1122c5`, with body
sha256 `69c51f3dcba15413cf802b2aca5a315d2a0645c17b7064cbd2b37029aaf5dba1`.
actual main attempt `5f10be1d-781f-475b-8704-655ca148cd79`, native thread
`01a1ec22-55a0-7761-894d-4ec900658613`, then fails with `source_protocol`.
the closed command diagnostic retains provider `ProtocolDefect` through
`_token_usage` / `_decode_token_usage` / `_usage_member:1881`. this is a new
[native usage protocol issue](#native-usage-accounting-repair), separate
from historical unknown native incidents and the resolved dreamer capacities.
private `650eb7c-startup-protocol-fence-journal.log` has sha256
`4e20e0af214e702e1f2dc6f19d8f3b6497289196d9c9c0542447127bcbf7fffe`.

the original attempt remains fenced and unsealed. one automatic restart creates
`cb1cb8c6-910b-45b7-b6aa-8c7c8887f602`, cancelled/stale at the clean service
stop. no new action is created; the old work stays blocked and journey clocks
have not started. all 97 previously released messages remain pending and
unparked; canonical `resume` sequence 9 is preserved. existing fresh-start
recovery fences unsettled callback owners, settles only sealed terminals and
uses canonical unfinished requests/original receipts for fresh reasoning.
no new lifecycle or recovery machinery follows. installed main continuation,
the combined journey and final reset remain outstanding.

the stopped inventory was independently reread on resumption. schema `0013`,
owner resume sequence 9, 12 actions, 37 read positions, an empty outbox and
the original pending send with zero executor entries were observed. the genuine
continuation remained pending and unparked. the selected notes checkout retained
the exact private origin and bootstrap head `fdcf2c6`. the stopped configuration
had adopted the canonical calendar id after inspection of 21 calendars and one
complete owner-only acl. the actual same-event update and subsequent attention
observation qualify the installed calendar read/write path. the original reminder
inventory and disposition are recorded in [operations](operations.md#supervised-todo-setup).

### native usage accounting repair

on the installed provider, the failing line rejects a reported cumulative total
different from input plus output. stock `0.160.0` source at `a956835d` reports
the three counters independently. on context exhaustion it also replaces the
counters with a full-window estimate. either contract can violate the old
equality assumption. the failed frame was never retained.

six public unix-websocket cases reproduced the exception at the installed
source coordinate. provider `0ebc1cb07f6320afb4af6e30f3661c36b76a2529`
preserves each reported counter. the exact synthetic full-window shape
establishes a fresh counter baseline. paid usage already observed in the
invocation survives it, and subsequent reported increments count once. unknown
optional counts stay unknown for the affected invocation. resume/start ordering
was significant: independent review found two replay races after initial green.
the final proof covers replay before resume returns, before preparation, and
during turn start, including stale and missing turn identities. uncertainty
about an unobserved interval can undercount consumption.

all 30 focused cases passed the independent rerun. the provider suite passed
983 cases with one skip and 40 live cases deselected. formatting, lint, types,
wheel and sdist checks passed. the private `usage-provider-qualified.json`
receipt (sha256 `7a7820ed87071a98577a118bd518a1b963a64b1dfeddbf67c08e4dea64f729af`)
records the probe and deletion inventory. this controlled transport proof
does not identify which shape reached the production decoder.

### installed accounting and context exhaustion

jarvis `c5392bec900fcbdff478e2735e0ac33bd300a96c`, tree
`d512d981e46cd8760bb8e51f1100ed2e80dc08b4`, pins kernel `3afc584`
and provider `0ebc1cb`. the frozen build, fresh wheel, cli, dependency
identity, types, docs, registry audit and actual postgres capture/retry passed.
the selected release passed [hosted verification](https://github.com/NielsdaWheelz/jarvis/actions/runs/44217004070).
same-release host replacement, observer initialization, activation and discord
catch-up succeeded. the pending proposal remained compatible.

fresh attempt `a98fc5b5-044b-4e42-a3f7-30a7358249b3` sealed an actual failed
native terminal at `2026-11-18T01:38:29Z` with 217,616 input and 608 output
tokens. the retained diagnostic and stock log both identify context exhaustion.
the terminal passed the repaired accounting path. a retrospective exact-thread
log match also found the underlying context exhaustion on `5f10be1d`; its
original usage frame remains unavailable. no new callback or action occurred.
jarvis parked all 103 inputs and delivered the failure notice. the operator
stopped the application cleanly with zero restarts. the original 12 action
snapshots, work row, 37 read positions and resume 9 were preserved. capture 6
ended with one root and zero descendants.

the [steering reconstruction](#steering-receipt-publication) quantifies the
duplication. reducing unrelated recent history alone still republishes
824,360 rendered bytes of already supplied required evidence in this run.

### steering receipt publication

main v4 publishes optional recent observations in a fresh opening. a steering
batch still selects its complete causal evidence. the host identifies each
operative invocation by id and the sha256 of its canonical projection. when the
same native turn already received that version, the new batch names the earlier
invocation. new or changed projections travel in full. request, action and stop
records remain explicit. the host retains 32 digest bytes per distinct delivered
invocation plus its id and map overhead for the active attempt.

the supervisor sends each steer only after accepting the opening. subsequent
offers wait for the previous batch's recorded or rejected outcome. a queued
or rejected control earns no receipt credit. this can delay further steering
while the acknowledgment is outstanding. pause, stop and fencing remain
observable. fresh reasoning rebuilds the opening without reusing any version
map. no action, tool binding, paid-read policy or isolated role changed.

the isolated postgres proof reproduced repetition before the repair. the
repaired runner selected a compact reference for the unchanged causal body,
the complete new and changed bodies, and the full opening on a fresh attempt.
independent cases covered an optional candidate that failed the fit check,
a projection changing and returning to its original value, and prepared,
queued, rejected, missing and recorded delivery. the controlled provider port
did not exercise the installed model. the retained capture/retry regression
passed against a separate clean schema `0013`.

the stopped read-only candidate reconstruction matched all 63 opening records
and reduced the seven appended receipt frames from 2,156,133 to 9,899 bytes
(four at 2,432, three at 57). the prior frames are reconstructed because the
journal records delivered steering ids and evidence, not each wire body.
private `c5392be-steering-projection-candidate.json` has sha256
`4045e514f297d081a1d8c3fc231b913bd289d79ed878cc6aca7f3dd6b2d0a93a`.
the two fresh postgres fixtures and temporary probes were removed after review.

### installed native child and action lineage failure

jarvis `844fe165892ac4d70f1c8f4d399ade7d29b1c0b6` passed local verification
and [hosted ci](https://github.com/NielsdaWheelz/jarvis/actions/runs/44220142312).
the first hosted audit timed out reading pypi. retrying the unchanged source
passed. the existing stopped operator command released the 103 exact inputs.
their ids, bodies, parentage, original delivery evidence and terminal hashes
matched the stopped inventory. same-release host, observer and application
activation preserved schema `0013`, resume 9 and the original pending send.

fresh main `0070f823-1255-4b4f-89c9-fb604f42301d` reopened the same original
(1,572 bytes, sha256 `1241524cdb3c1a0f14a5512bfbafb1a647f2cff184cc1ef5539a5b411269a992`).
capture 7 independently recorded the sol/high child
`01a1ec68-d080-7fc0-90ad-95fa107dc48a`, its parent and its successful final
turn at `02:08:17Z`. the child checked all eight years and the gregorian rule,
and identified which pdf details it received from its parent. the parent's
private note retained its first 2,170 bytes and appended the child's findings
before the new clock. discord delivered the matching progress message at
`02:10:55Z`. the parent reported rechecking both pages. workspace artifacts
and content corroborate that account; the exact root command stream remains
unavailable. the remaining restart/approval criterion is distinct from this
installed proof of useful native-child integration.

a subsequent calendar callback carried 124 delivered input ids. the application
accepted the invocation, then failed constructing the immutable execution
contract at its obsolete 100-id limit. no action, executor entry or external
effect resulted. systemd restarted once. the following attempt was cancelled
at the clean stop. the stop retained twelve actions, 41 read positions, one
blocked todo with no new wake and the original unentered send. neither timer
nor worker wait was armed and the inferred 02:20:58Z wake time passed. the
[installed lineage proof](#installed-lineage-and-stopped-restart-window)
records the subsequent repair.

action lineage repair `f8f7fc6` removes the single-batch maximum from the
persisted execution envelope. the run keeps its complete ordered inputs. long
active turns can therefore produce larger local action records. per-batch and
transport limits, nonempty canonical ids, uniqueness, checkpoint and admission
checks retain their existing meanings. no migration or model/tool change.

the original typed calendar proposal passed. reconstructing its execution
envelope failed only on lineage length, at 101 and 124. independent isolated
postgres dispatch on the repaired source preserved all 124 ids and the exact
checkpoint, recorded one action and entered the controlled calendar effect once.
a missing origin delivery and a fenced owner each produced zero actions and
effects. new probes, container and volume were removed. private
`lineage-dispatch-qualified.json` has sha256
`a5f692913a0b62adaae658615d2f5ec2471705adedc5cc56635c5b9cbd246505`.

runtime source `34d162048175da1ca3da7f685042da4013047189`, tree
`016e0d1276ca2647eaa7aef72e3ef2b8168ca0e4`, passed local
`scripts/verify` and [hosted verification](https://github.com/NielsdaWheelz/jarvis/actions/runs/44224432011).
the local first pass and first two hosted passes timed out reading pypi. the
unchanged source passed on retry. the release and its same-release contained
host installed and verified before activation.

### installed lineage and stopped restart window

on november 18 the owner's ordinary discord post `1572445427326910505`
supplied fresh timing authority. main on selected `34d1620` reported a clock
anchor of `03:01:52Z`, corroborated by contemporaneous host input timestamps.
the exact native shell output was unavailable. its accepted calendar invocation
`8953f32c-ffba-49e7-8ff5-4a5a6ad1443b` and succeeded action
`6bf4221b-a6fb-4cfb-b836-b2ad85de9cac` contained the same 120 ordered,
distinct canonical ids. all matched the recorded delivery at their ordinal,
20 opening and 100 steered. the checkpoint on both records matched their
last input, `45207690-6394-4c10-a582-9aea4ca9b5ad`. origin, attempt and
step matched. this attempt issued one calendar update with one executor
entry. the earlier 124-input callback retained its original unentered status.
private `34d1620-installed-action-lineage.json` has sha256
`07bcf7944ea5a74813522bafc5fbc5b6f1a3ea5fbaae5a91f5188b0e996c2930`.

the same todo was due at `03:11:52Z`. the same private calendar event was
scheduled from `03:21:52Z` to `03:41:52Z`, with no attendees. main sent work to the
original worker and registered wait `4ba31552-af4c-460e-8c0c-58d603e58092`
at `03:02:54Z` with deadline `03:12:54Z`. discord delivered the ordinary
approval question as `1572447925911556217`. at `03:07:02Z` the original
draft and send proposal, new timer and registered wait coexisted. skid showed
the exact original worker target working at `03:07:40Z`. this attempt made
one worker send and one wait registration and started no worker.

the application stopped cleanly at `03:09:51Z`. the `03:10:46Z` stopped
snapshot matched the eight selected live action identities, arguments and
receipts. the original send still had zero executor entries and the todo wake
and worker deadline were both ahead. private `34d1620-live-stopped-conjunction.json`
has sha256 `543f879003d799f736e68225a7a4727882fc0b1801948c9db800967f9e957cef`.
the worker checked 12,400 cases and found 97 leap years. its terminal recorded
a deliberate 480.005909560-second foreground delay and exit zero. skid observed
the worker idle during downtime. private `34d1620-worker-final.txt` has sha256
`4bf6d965b8b14047b4ba3fad1ab2879abc4651665cffb488bb7585301a5d5407`.

positive google reads during downtime verified the same event on its owner-only
calendar at `03:13:29Z` and the original threaded draft at `03:13:34Z`.
private `34d1620-timed-event-positive.json` and `34d1620-timed-draft-positive.json`
have sha256 `fb79861d26109491334f029d3450c26736bc5db29d5e02b3481bd27cc617ace1`
and `83cc9b99dae66ec29d578674ef4207b5ad4fec19797a80bb35d3fcf6ca200fa7`,
respectively.

all three retained synthesis notes came from `650eb7c`. the stopped
`34d1620` snapshot had ready coverage and `dream_through` both at 4,127.
post-journey compaction and a quiet dream still need observation on this graph.
private `34d1620-stopped-memory-roles.json` has sha256
`d456569bfa7a05d4fc9c9618881f436ad987b759178e6970eb99ce30b801f5e0`.

### restart catch-up and original send

the owner approved the existing draft in ordinary discord message
`1572453887498264599` at `03:30:21.560Z` during downtime. systemd started
only the application at `03:36:52Z`. the gateway scanned four messages,
accepted one and completed catch-up below its scan limit at `03:37:04Z`.
canonical owner input `45efcc25-4674-45ce-a9d8-e18bcf8ee755` matched the
observed post. fresh native attempt `fbdbc40a-0362-454c-af18-fe5481ffeee6`
recorded that input, the original timer wake and the worker wait outcome in
its opening. the canonical control remained resume 9.

the timer's one-time occurrence retained its original todo, wake id and
scheduled time of `03:11:52Z`. startup settled the registered wait at
`03:37:01Z` as a timeout after its deadline. its original registration and
full worker target matched. the native progress report distinguished the
wait timeout from the successful independent worker result.

the accepted `approval.respond` invocation `1c92b5b5-d6c2-49b9-b8c4-401e0ab38196`
bound that exact owner input to original send `8bc53688-c507-467b-9945-b6b359d7996e`
at `03:37:22Z`. the original send succeeded at `03:37:23Z` with one executor
entry. its arguments and input digest matched the stopped proposal. the draft
and send receipts matched on content digest, thread and original effect marker.
there was one draft creation, one send proposal and one worker launch.
private `34d1620-original-send-confirmed.json` has sha256
`af34efc84805932f44d857b707b218409c8fe2e0f60d3d4539062a97e77cbce8`.

the restart attempt committed its partial final at `03:44:13Z` and delivered
discord message `1572457378773864509`. the fresh timing instruction, approval,
todo wake, wait resolution and send resolution were completed. the three
earlier owner requests were waiting for owner input, the existing todo was
blocked and the outbox was empty. the final correctly distinguished the timed-out
wait from the worker's completed report. it left the renewed event's attention
unverified and asked whether to run another window.

the canonical source had already observed that exact event at `03:07:20.538512Z`,
due `03:06:52Z` for the `03:21:52Z` start. both provider ids and the start
matched the renewed event. pre-stop attempt 14 recorded the fact
`b1ab8435-2c1a-4cef-87f8-1e7321a61327` as its fifth input and completed it
at `03:09:42Z`. its delivered conclusion mentioned the scheduled block. the
restart attempt received a different calendar notice. its final missed the
retained fixture fact. private `34d1620-fixture-attention-occurrences.json`
has sha256 `b8c90e8c85c346346b5263f8ef2c38f378446e8204bc086de5ea242d11e4192e`.
private `34d1620-approval-restart-terminal-16.json` has sha256
`c2970e588ba5e32099472e235c350473ce1ffff1dccf1af6a5af8278ddd45f65`.

the retained notice occupied leaf 22,192 within the restart attempt's admitted
cutoff of 22,199. that attempt searched for the event, etag and a timestamp
without the utc suffix. postgres full-text search required the token `52`.
the archived timestamp ended in `52z` and the actual query returned zero.
on the same original, the event id with either the etag or the event kind
matched. the source record remained directly openable. private
`34d1620-attention-search-miss.json` has sha256
`3b33adfdb6e3c5ab74ac57b471a7ec8c5885dce2f5834e8134b7c6e641e7d3b7`.

the resumed main reopened the same retained original at `03:39:44Z` and read
the checker's complete report at `03:39:48Z`. after the run, the private
checkout remained at `fdcf2c6`. its untracked 3,812-byte note included the
page-two correction, primary source, 12,400 cases and measured delay. both
original page renders and the extracted text were still present. these
observations establish the file contents and git state at inspection. private
`34d1620-reopened-original-and-reports.json` and `34d1620-postrestart-workspace.json`
have sha256 `266a5702c74b59ef611b2abcc3b42df5020405c930717881e20cffff4d11e5c8`
and `152a01969d63b7faf3a32be9b8b8ad850f0c47142495b195cfbdba687228ea0a`,
respectively.

an independent gmail read at `03:56:39Z` verified the sent plain-text reply,
its sole owner recipient, original thread, reply headers and corrected body.
the private receipt retains the original and sent message ids for exact cleanup.
private `34d1620-final-sent-positive.json` has sha256
`d0ab5ced67f4b5d49a5c5a0e7fb752d195e69644c7f5e5effa00f479b337dcdb`.

by `03:50:28Z` the post-journey compactor had committed ready coverage
through 4,131. two 8,000-byte inputs at positions 4,129 and 4,130 produced
528- and 516-byte nodes, respectively. the dream cursor remained at 4,127.
private `34d1620-selected-compactor.json` has sha256
`faf62ce966b6f81725536d71ce95597404ee828d0e7de8d33245f7621396fdca`.

the application stopped cleanly at `03:55:42Z` for the independent mail
read and the stopped `jarvis dream`. by this stop the compactor had prepared
through 4,150. the selected release's fixed sol/xhigh dream consumed the
23 ready seeds in `[4127,4150)` and exited successfully after 169.8 seconds.
an independent postgres read found four committed synthesis notes at positions
25,396–25,399 with 3, 2, 2 and 4 references. the nightly marker and the hashes
of all eleven canonical tables matched across the run. private
`34d1620-independent-postdream.json` has sha256
`bb334b5b2555e146dcd4e8a7ac888edf378217b5c2f903c411b613784f7eb7f2`.
the same application restarted at `04:13:17Z` under existing resume 9.

### recovered final and reset disposition

at `04:13:31Z` native attempt `7cc8d8e1-551d-4c04-b624-2e537cc225d8`
opened with a new email host fact and the three waiting owner requests.
a separate calendar notice arrived as a steer. the latest owner input at
admission was still the original downtime approval. main searched again and
opened the exact archived fixture notice through invocation
`633600e4-d1b6-4f13-9783-9203ef972db7`. it marked the existing todo done
with its wake cleared. the single self-send, worker launch and event schedule
were preserved.

the terminal committed at `04:19:01Z`. all five recorded inputs completed
with canonical conclusion `d70bb3ee-45cb-54e3-b1af-c712d9824dc3`, delivered
as discord message `1572466137206099979`. it reported the recovered fixture
notice, the approved send, the eight corrected cases, the worker's successful
report, its timed-out wait and the todo wake 25 minutes 9 seconds late.
the delivered result retained a partial qualifier because main lacked a reply
receipt for historical callback `07cc4e46-ca39-44d4-810e-1ca4295e6dd2`.
the earlier failure occurred before action insertion. its original callback
still has neither a linked action nor a recorded reply. the later successful
calendar change has its own independently verified receipt. private
`34d1620-17-final.json` has sha256
`3d12f21f9fe5be65e67db1572932593180eacd12377666e6885a8236f3170429`.

the owner's discord message `1572466562030510122` established canonical
pause 10 at `04:20:43Z`. the `04:20:58Z` disposition check found zero
unfinished requests or todos, undelivered replies, parked messages, pending
or uncertain actions, unresolved reads or inference, and unsettled native
products. the original send retained its single executor entry. private
`34d1620-postfinal-reset-disposition-gate.json` has sha256
`53a729ee68b8225ff86f9a24ab47316e391b04f5f874c180b80b664d80ffc6a2`.

### final recovery snapshot and exact fixture cleanup

both native collectors stopped before the application exited cleanly at
`04:21:37Z`. nexus capture was disabled on both sides, with zero source
exports, registered boundaries or stamped runs. the selected release's
stopped `0013` snapshot passed the existing helper's creation and verification
checks. its 22,631,392-byte dump has sha256
`d018e6245ebe483d983f2a6b6d5ea54170b103be0df5fded354ba790d57d043e`.
the extracted identity inventory matched the live stopped counts, including
25,653 native parts across 5,428 native conversations. the predecessor full
snapshot was removed after verification. both manifests and the separate
original historical uncertainty receipts were retained. dump listing and
identity extraction do not qualify a restore.

the complete bucket inventory contained one object, the exact 1,572-byte
fixture pdf. the storage service acknowledged its deletion with 204 and a
fresh exact-key read returned 404. the fixture cache was absent. private
`34d1620-final-attachment-cleanup.json` has sha256
`656c20c22d4de324a275e0753cbb62a02bbe86b7e2b9c57141a752264877fab2`.
the sent draft was already absent on two reads. the exact synthetic calendar
event was deleted once and a fresh read found its matching cancelled
tombstone. the idle fixture checker had zero attached clients and its original
full reference before its terminal-only close. the eight observer captures
were retained and verified before removal of the remote probe copies.
the private notes checkout and original native chats were preserved.

the complete configured channel inventory contained 18 bot messages and
seven owner messages. discord acknowledged deletion of all 18 bot messages.
a second exhaustive read found only the seven owner messages. after owner
cleanup the complete channel scan at `04:39:33Z` returned zero. at the first
gmail check both fixture messages still existed. an exact label read found both
in trash. after permanent deletion, two independent, exact-id reads against
the original account returned 404 at `05:42:52Z`, one for the original and
one for its reply. the application and collectors remained stopped. private
`34d1620-final-discord-empty.json` and `final-reset-google-mail-absence-02.json`
have sha256 `2b62079b0f1841045758f1d96aa698247e51b49114b322b5a178648e3b21aff9`
and `95bd33092d0df93a041994b48b6d9253f888f66519745ead6ddf3cd0aba197b7`.

the final staging cleanup matched and removed eleven temporary operator
helpers and two compiled cache files. all 68 retained private files matched
their prior hashes. private `34d1620-final-staging-disposition.json` has
sha256 `d8b15172493f394bbdb579a44b13acf7ea1f863e946d788e9d67f7e9a7372635`.

### final database reset and fresh capture

under the deployment lock the stopped reset cleared all 18 application tables
in one transaction and reseeded the empty memory singleton. immediately before
the wipe there were 232 canonical messages, 19 actions, one todo, 26,066
archived source parts and 44 event cursors. afterwards all tables were empty
apart from `memory_state(id=1)`. the original historical uncertainty receipts
remain in private recovery evidence. private `final-reset-database-result.json`
has sha256 `638c604e55a808117e0f7a28d1cebce7da37547fe17a828f0144c34dcf680d4c`.

the existing initializer created the sole nonadmitted canonical pause, sequence
11. an independent read confirmed schema `0013`, unchanged table and column
grants and all 19 original guards enabled with matching definitions. the
archive, work, actions and waits were empty. the normal memory search for
the old fixture returned zero lexical or semantic candidates and wrote no
history. these checks preceded all fresh writers. the selected application
started under pause 11 at `05:46:56Z`. private
`34d1620-independent-reset-structure-after.json` and
`34d1620-final-empty-memory-search.json` have sha256
`566e338911da317ef6d0e9944c570fd23bcb77c54d285d1fc2fe0bc886ea8930`
and `2b1f3117d02059c7fc0970d5303bef1816d0e52fde88464a63b9e70639e9f206`.

at `06:26:34Z` eleven of the twelve online native lanes had activated and
completed inventory. they held 3,183 conversation rows. all 3,182 identities
shared with the stopped inventory had new row ids. 24 unreadable conversations
had explicit pending baselines, zero captured parts and no checkpoint. the
remaining `macbook/claude-work` account had 2,246 conversations before the wipe
and failed discovery before establishing its lane. the two `observations.jsonl`
test fixtures under a scratch directory fell outside the supported archive
layouts. metadata-only listing, listing with heads and activation all returned
`unsupported` at the same file before making any http request. private
`final-reset-mac-claude-inventory-red.json` has sha256
`8d3077c2d2fe841a062f4ff792684ac02123df2bae5c18f7ec9fb90b0fd8cf73`.
at this checkpoint no old native, jarvis or nexus event parts had reappeared. private
`final-reset-paused-eleven-cuts-comparison.json` has sha256
`e0934be5836397445e2f562eaf9726c1ff606c6a670528c80d27801eb30ac7c0`.

with owner authorization the scratch directory moved intact from the claude
archive into the ordinary workspace. its directory identity, three checkout
heads and statuses, untracked-file digest and both JSONL fixture digests
matched immediately before and after the move. ten path substitutions in nine
current files resolved to existing targets. the historical recovery copies and
git states were preserved. private `34d1620-scratch-live-paths.json` has
sha256 `eac2750e63d8c7fdcf98f895805bd2850f5cb4252487435efad511a64f6135cf`.
the same installed provider listed 2,269 conversation ids through its
metadata-only interface. ordinary
collector activation established the `macbook/claude-work` cut at `06:47:46Z`.

the `06:48:46Z` paused inventory covered all twelve online native lanes and
5,452 conversations. all 5,428 previously known identities had fresh row ids,
and 24 were newly discovered. 25 heads remained explicitly pending with no
parts or checkpoint: 21 unavailable on devbox codex-work2, three unavailable
on macbook codex-work2 and one oversized record on macbook claude-work.
comparison with all 25,653 stopped native parts found zero overlap. at this
point no new native part had entered the archive. private
`final-reset-browser-scratch-move.json` and
`final-reset-paused-twelve-comparison.json` have sha256
`b8ac9610ae1f25d0e6de4141f425c1d05ad4682549842d6705a5add80a9f338c`
and `cf8e045a9a97b0a89dd7c0bb499f25c5f0d34b77b59a764861286ac81fcb31b5`.

the owner posted `resume` in the configured discord channel at
`07:00:05.084Z`. discord message `1572506666623172710` created canonical
owner control `82235226-8d8c-4ea7-82cb-110319b7d41b`, sequence 12. its
admitted original entered the jarvis archive at position zero. the fresh
initializer's pause stayed outside memory. no test input was planted.

at `07:10:29Z` all 44 google cursors had completed baselining. both source
families were enabled, with no errors, blocked streams or open page continuations.
at `07:12:27Z` the fresh archive contained 145 jarvis parts and zero native parts.
comparison with 413 old jarvis parts and 25,653 old native parts found no
matching source part ids. the twelve native lanes and jarvis lane were active.
the six arch lanes and nexus remained disabled. private
`final-reset-cuts-comparison.json` has sha256
`d9f45116759b403cbfcd4874e0e1eb76d3365546b1b25def7788ac4578baa278`.
ordinary macbook claude-work activity then produced 50 native parts. none
matched any of the 25,653 stopped native part identities. private
`final-reset-positive-native-native-overlap.json` has sha256
`7e8738f40b78d9a5b356f7707f458718b0c53df66209447d20e57805b5d8b0fb`.

a current calendar-attention fact was eligible and completed. separately,
one public virtual calendar returned 71 confirmed and 71 cancelled all-day
revisions during tokened sync after its initial baseline. at `07:13:20Z` all
142 provider identities and facts matched earlier ones in the stopped dump,
apart from their observation times. the fresh canonical messages had new ids.
the poller admitted incremental rows under the existing source contract.
google’s internal reason for returning them is unknown. the
[calendar issue](issues/calendar-revision-republication.md) records the
scope of the owner's subsequent adr 0085 decision and the installed
observation that prevented the correction.

### stopped google cursor correction

the isolated rehearsal used real postgres 16 at schema `0013` and the
selected event poller and connector against controlled provider responses.
the original reset discarded all 44 cursors. initial sync discarded its rows,
then the next incremental poll published a previously admitted revision.
the correction preserved all 44 rows in place while clearing the other 17
tables. the normal initializer created the sole nonadmitted pause. the poller
used the preserved token and admitted a new etag for the same event. when
the provider deliberately returned the old etag on that same warm token,
the poller published it. retaining a token alone cannot suppress that response.

twelve refusal and rollback checks preserved the prior corpus, including a
forced failure after truncation. the helper also refused reuse of the reviewed
owner pause after fresh initialization. the private helper
`reset-database-warm.py` has sha256
`d272ffec6e45631a2e52835d55f360f34a10ecdf75b143134f9bdcd714bae13a`.
private `adr0085-correction-qualification.json` records the test receipts
and removal of the temporary test and database. its sha256 is
`ebdc96e68ba46f42752ffb96dc2d64269dfd83f19bcdd7c1eae18b3537e6a372`.

normal polling later completed several quiet rounds. during one later transition
between two observed token digests the source identity index recorded 142
individual hits in four seconds. the index serves other requests too, and its
counters do not identify individual revisions. one quiet response from a
warm token therefore cannot settle this incident.

a finite read-only observer follows the affected calendar from its stopped
cursor through the ordinary connector and poller. it compares offers with the
142 prior provider identities before canonical deduplication. isolated proof
covered a quiet round followed by all 142 old identities over eight pages,
a changed etag, token expiry and the reverse transition. an incomplete window
cannot establish the suspect transition. private
`warm-calendar-window-qualification.json` records the exact observer and
proof cleanup, sha256
`b7beb01d5364daf7d8af9e06e857e5bfd381e963e31f677744a45339c8708edd`.

the final observer also retains exact matches from each completely decoded
page if a later page fails. that proves a reoffer without attributing a terminal
token or direction to an incomplete delta. six controlled cases qualified this
revision. private `warm-calendar-partial-qualification.json` has sha256
`3b364c36a381becad624d5d946e35cd74a678b9f1aa78bc889a6946d831bf32b`.

on 2026-11-18 the owner's discord pause became canonical control 13 at
`08:02:18Z`. after the service stopped, the read-only observer held deployment
ownership and used the stored cursor from its successful `08:02:04Z` poll.
at `08:04:45Z` the first incremental round completed five pages. all 80 offered
revisions were distinct, and all 80 matched the 142 previously published keys.
the final sync token matched the starting token. the observer exited 3 on
that evidence. private `correction-pause13-warm-preflight.json` has sha256
`d3fe860fe57eb79fa84067649fb9291ed9add5799e8891f85757a6c5e78236ff`.

the observer committed no facts or cursor progress. clearing the canonical
publication keys would remove the existing protection against these offers.
the operator left the channel, central corpus, source cuts and recovery
snapshot in place and performed no external cleanup. the same release restarted
at `08:07:43Z` under pause 13. discord catch-up scanned one message and accepted
zero. both collectors resumed. at `08:10:05Z` the database still held all 149
canonical messages and all 44 google cursors. no google stream had advanced
after the pause. the retained dump still matched its original sha256. f2
remains open pending owner disposition of calendar revision replay.

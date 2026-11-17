# reliability repairs and final integrated acceptance

status: f2 implementation contract, 2026-11-16, under
[adr 0075](decisions/0075-v2-completion-and-subscription-model.md) and the owner's
[adr 0077 refinement](decisions/0077-production-acceptance-and-fresh-reset.md),
with [adr 0078's reset order](decisions/0078-fresh-corpus-first-acceptance.md),
[adr 0079's bounded serial compaction](decisions/0079-bounded-serial-compaction.md)
and [adr 0080's first valid stopping rule](decisions/0080-first-valid-compaction.md).
source implementation, integrated composition and isolated fault proof qualified.
the preliminary production reset is complete. the free-copy/batch and first-valid
repairs have source and real-model candidate qualification and are installed.
complete production preparation, the real journey and final fresh reset remain pending.
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
  the [historical preparation backlog](issues/memory-preparation-backlog.md) blocked
  main; fresh-corpus proof does not qualify that backlog's latency.
- adr 0079 changes free-copy and serial-batch policy after fresh capture exposed
  substantial new preparation work. originals, source cuts, fixed models and
  full-history preparation stay binding. its exact contract and trade-offs live
  in the memory contract; source and actual installed proof remain separate.

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
(320 kib), with dreamer role revision v4. shared allocation and the other finite
token, turn, tool and elapsed bounds retain their values. this permits 65,536 more
rendered context bytes; existing post-read overflow behavior still applies.

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
   stopped `jarvis dream` when needed for bounded installed proof: it prepares
   compaction and leaves the nightly marker unchanged. no overnight wait/new hook.

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
usefulness. the [backlog issue](issues/memory-preparation-backlog.md) owns the
remaining preparation blocker; both owner-approved resets retain their original
scope.

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
the [diagnostic issue](issues/compaction-invalid-completion.md) retains that
unknown cause and the still-pending genuine owner request.

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
not the original failure's cause. main native attempts remain zero; preparation,
the real journey and final reset are still pending. any newly reproduced rejection
requires diagnosis and responsible repair before another explicit retry.

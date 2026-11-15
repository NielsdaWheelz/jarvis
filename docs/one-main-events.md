# one main for every event — slice 1 / o6

status: accepted v2 implementation contract under [adr 0071](decisions/0071-simple-event-driven-v2.md),
2026-11-14; source implemented and isolated-qualified, installed activation pending.
source audit: `8c0bf36`; [implementation evidence](#implementation-evidence) below. the
[roadmap](implementation-plan.md) owns sequencing. this includes o9's source
changes; installed skid qualification remains slice 3.

## goal and scope

every admitted event starts or steers the same main with the same normal tools.
main decides whether to inspect, act, delegate, ask, report or remain silent.
progress, blockers, consent and results are ordinary conversation.

slice 1 delivers common ingress/lifecycle, full event authority, conversational
consent, scoped conversational stop and their recovery. current producers are
owner input, action outcomes and asynchronous worker observations. remove the
old scheduler now; slice 2 supplies scheduled todos. intermediate slices need
not form a usable product. preserve outstanding commitments for final cutover.

non-goals: todos/recurrence, email/calendar producers, installed skid repair,
notes/native file access, attachments, memory changes, browser control, credential
products, interactive deliverables/television, new ui or general orchestration.
future producers reuse the append contract; this slice does not implement them.
shared memory and quiet dreaming retain their separate delivery.

```text
source transaction -> canonical message -> common native input path
  -> one main / one full plan -> existing tools and original receipts
  -> explicit request dispositions + optional prose -> existing outbox
```

| responsibility | owner / change |
| --- | --- |
| input, deduplication, request state, outbox | `MessageStore`; one transaction-level append |
| delivery, invocation, original reply, terminal seal | `PostgresNativeJournal`; preserve durability boundaries |
| selection, context, steering, fresh reasoning | `NativeInputs` / `NativeRunner`; one full main plan |
| intent, consent meaning, priorities, notice/silence | main; no second classifier or output critic |
| effect entry/recovery and worker observation | existing `ActionStore`, `ActionPositionRecorder`, dispatch/watchers |
| execution and transport | llm-tools, kernel and provider-runtime through current public interfaces |

no new table, event bus, queue framework, role, worker controller or dependency
upgrade. keep one deployment lock, one native main and the serial dispatch lock.
ingress, input steering and outbox remain responsive during tool/model waits.
isolated memory roles keep their own envelopes.

## capability contract

- every origin gets the same frozen main plan. remove `AutomaticWriteGate`, its
  supporting-owner fields and the read-only wake plan. retain normal validation,
  `classify_write`, secret rejection and finite operation/transport bounds.
- application writes name a delivered live owner OR host request. current
  deployment ownership and an unfenced, unpaused invocation govern NEW admission.
  an owner permit proves runtime ownership, not fresh human consent.
  new executor entry for committed queued work needs current ownership, unpaused
  live origin and stored consent/recovery proof, not a still-live original attempt.
  entered effects retain their separate reconciliation rules during pause/stop.
- source/tool/memory text is evidence. it cannot become owner speech. only a
  canonical owner message supplies the consent reference; main interprets it.
- reads, drafts, private calendar work and existing trusted worker control remain
  automatic. consequential connector communication, spending, secret exposure
  and irreversible destruction require consent where supported; no new tools
  are implied. web search/read remain available whenever useful.
- retain immutable effect arguments, provider preconditions, original receipts,
  finite executor-entry ceilings and reconciliation. entered effects settle after
  their originating turn ends. no outer write timeout or blind replay.
- main still uses the contained endpoint; native notes/tools arrive in slice 4.
  workers already have independent authority. connector consent is not a
  transitive sandbox for either.

## schemas and internal api

keep existing tables and closed schemas except these explicit deltas:

| record | target |
| --- | --- |
| `message` | nullable immutable `parent_request_id uuid references message(id)`; parent must already exist, be waking and in the same conversation. independent inputs have null parent; action/worker outcomes use the action's origin. insert-only parentage prevents cycles. |
| waking request | owner and host both use `pending / waiting / completed / stopped`; unfinished rows have null `processed_at`. retain wait reason and operator `processing_parked_at`. |
| bounded `message.trace` | host-owned `observed_at` records first admission time; action outcomes also carry immutable `action_id`. store current `waiting_action_ids` from input outcomes; clear on leaving the wait. retain settlement/seal references. no notice policy. |
| `ExecutionContract` | add required `schema_version = "jarvis.action.v2"`; remove `write_gate_supporting_owner_message_ids`. retain attempt/callback identity, ordered input ids, tool/policy/plan revisions, digest, target and entry ceiling. |
| native reply journal | one narrow `local_result` variant for `approval.respond`, below; no decision ledger. |
| `InputOutcome.disposition` | `complete / continue / waiting / stop`; `stop` has null wait reason and empty action refs. other validation stays. |
| silence / progress | `Silent.reason = no_owner_notice_needed`; progress is at most 2,000 utf-8 bytes with no input outcomes. assembled final discord content retains its 2,000-character bound. |

factor this from `MessageStore.insert_waking`; retain that method as its ordinary
transaction-owning wrapper, not a second insertion implementation:

```python
append_waking_input(connection, *, role, text, source, source_conversation_id,
                    source_message_id, created_at, parent_request_id=None,
                    action_id=None, message_id=None) -> InboundInsert
```

run under the existing conversation lock. require nonempty source identity, aware
source time and validated parent/action linkage. retain the unique
`(source, source_message_id)` key. duplicate identity returns the original row
only when role, text, conversation, source time, parent and action agree;
mismatch fails without overwriting evidence. retain the first observed time on
retry. preserve memory admission through its existing hook. source progress and
publication share the transaction; signal native input after commit. a missed
signal is recoverable from pending rows. no model event-publishing api.

both action-result publishers use this function. `source_message_id` remains a
key such as `<action uuid>:<status>`; never parse it as an action uuid. read the
receipt through `trace.action_id`. parentage is attribution/recovery scope, not
permission, a todo relation or a worker graph.
both publishers derive text and source time from the same durable outcome:
terminal action completion time or the stored worker-observation time. never use
retry time; repeated publication must reconstruct the same fact.
report eligibility is absence of that canonical outcome identity, never whether
the originating request is finished. only a newly inserted fact counts as recovery
progress; an already reported worker wait must not spin recovery ahead of main.

`ActionRequest` stays `{request_ref, existing_action_ref, arguments}`. null means
new invocation; do not infer replay from equal tool/payload. an explicit action
reference must identify a compatible original in the request's causal component
and returns its original result/pending state. duplicate native callback ids
already replay through the journal. rotate wrapper/policy/session revisions;
retain one current executable decoder.

## selection, continuation and recovery

1. share one selector between initial submission and midturn polling. pending
   unparked input starts work, owner first then host, each in source-time/id order.
   remaining batch capacity includes unparked waiting owner/host requests as
   explicit context; waiters alone never start a turn. expose omitted waiting
   context. journal delivered ids; only delivered live ids may be dispositioned.
2. frame id, honest role/source, source time, observed time, parent, state and
   blocker. one host `as_of` per selected/appended batch. preserve original dates.
   compatible input steers main; incompatible/bounded-out input queues durably.
   progress and omitted dispositions leave work unfinished.
3. select required receipts for initial AND appended inputs. derive the causal
   root through immutable parents, then its descendants: ancestors alone miss
   siblings. reuse message/action/native queries, not a stored root or graph
   service. retain operative receipts, pending decisions, stopped-parent state
   and the canonical inputs/settlement establishing a stop. never trim a required
   recovery fact; leave input pending and surface the context limit.
4. replace blanket recovered-request write denial with concrete barriers. an
   entered action without its original effect receipt, or terminal `uncertain`,
   blocks new effect-bearing action admission in its causal component. local
   approval/note writes, stop bookkeeping and reconciliation remain available.
   queued/unentered work and pending
   approval are known commitments; existing recovery owns their execution.
   `agent.wait` registration is known while observation remains pending. retain
   matching billed-once tool/typed-input read barriers across the component;
   unrelated reads needed for reconciliation remain usable. known outcomes allow
   new work. independent roots have no semantic deduplication guarantee; changing
   to a sibling request cannot erase a barrier.
5. only explicit `complete` or `stop` sets processed time, including host rows.
   `continue` leaves pending; `waiting` records the actual reason/action refs.
   `complete` cannot hide that request's OWN unresolved actions; it may finish
   handling an uncertain-result observation while its parent remains blocked.
   waiting refs may name original actions anywhere in the same causal component.
   an established observation registration alone is not an unknown effect.
   silence follows identical rules.
6. atomically publish a newly resolved action fact and rearm only requests whose
   current `waiting_action_ids` contain it: set pending, clear wait reason/refs.
   other actions/receipts remain unchanged; main may install a fresh wait. duplicates,
   owner-input waits and configuration waits do not rearm. if a blocker resolves
   before final commit, validate its original identity and keep the request
   pending for integration instead of installing a stale wait or rejecting the
   seal. do not invent success from this race.
7. malformed output preserves the seal and parks ALL affected live waking
   requests as waiting/configuration, null processed time and stamped
   `processing_parked_at`. atomically enqueue one deterministic truthful batch
   failure notice. do not fulfill reminders or consume facts. stopped or
   superseded/control-invalidated requests remain untouched. cold-recovery fencing
   alone does not prevent the current owner settling/parking an original seal.
   named repair changes configuration waits to pending, clears park/wait fields
   and signals input; merely clearing the park timestamp would strand them.
   no automatic malformed-output retry loop.

replace owner-only checks together in input dispatch, `record_invocation`, action
insertion, executor entry and recovery. validate before target lookup/provider io
and again at existing transaction boundaries. retain conversation → request →
attempt → invocation → action lock order. associate paid reads through original
invocation input ids, never prose. preserve main's existing operation bounds.

## conversational approvals

main asks an ordinary question when needed. clear earlier consent suffices.
no repeated question, buttons, payload recital, argument attachment or semantic
matcher. a consent-needed proposal stores only `awaiting_approval` and returns
its existing suspended-action reference; main supplies normal prose.

add one main-only declared local-bookkeeping `Write` with strict closed types:

```text
approval.respond({action_id: uuid, decision: "approve" | "deny",
                  owner_message_id: uuid})
success.value = {action_id, decision, owner_message_id, decided_at}
```

use canonical uuids and host utc decision time; `ReplayPolicy.ReDispatchable`,
zero external attempts, 512-byte input and 1,024-byte result limits defined once
on the binding. no `ActionRequest` wrapper or new action. handle it explicitly
beside the local note exception in journaling/dispatch; validated native
bookkeeping commits directly in its journal transaction, without another recorder
or generic executor framework. it is neither a read nor recursive approval.
validate its binding/plan and serialize through the existing dispatch lane.

the transaction checks the current permit/live invocation, a delivered live
input, matching conversation and a real owner message. consent need not be
new/recent. host validates identity; main owns meaning. lock the action and
look up any successful decision BEFORE checking mutable target eligibility:

- first decision requires a live origin and `awaiting_approval` target.
  approve: `awaiting_approval -> queued`, set `decided_at`; no executor entry.
- first deny: `awaiting_approval -> cancelled`, set `decided_at/completed_at` and
  retain the ordinary denial result for outcome publication.
- in the SAME transaction, link the native invocation to the target action and
  store `{type: local_result, wire_text, success, result}` in its reply receipt.
  `result` is the bounded ordinary `ToolResult`; canonical rendering, no `host_ref`
  (which currently means an effect/read result). this link records a decision
  about the original action, not another action admission.
- same callback replays that receipt. a new callback with the same decision copies
  the first successful decision result. an opposing decision returns the existing
  host-rejection envelope with reason `approval_conflict`, without mutation.
  replay never requeues an action, including after completion/cancellation/pause;
  ordinary stale-session fencing still applies. missing/foreign targets and first
  decisions on ineligible origins/actions reject. do not derive the first
  decision from mutable action status or `decided_at`.

journal `_reply` reconstructs `DispatchCompleted(result, wire_text, host_ref=None)`
from that local receipt; `record_reply` verifies an already committed reply matches,
not recodes it as invalid arguments. after commit, schedule a
tracked effect task that acquires the shared dispatch lock after the callback
releases it and uses the common recorded-action execution helper. ALWAYS publish
its eventual outcome: the callback returned a decision, not the effect result.
startup scans queued work after a lost notification. merely setting service work
would wait behind main; no second executor or wait for its final response.
pre-commit crash changes nothing; an accepted local invocation without its atomic
receipt proves no decision. fence it on restart; fresh main may issue a new
admitted callback using retained owner evidence. post-commit crash replays the
decision and recovers execution without interpreting consent again. a decision's
`local_result` never suppresses publication as an external `tool_result_ref` would.

stored arguments remain immutable. an undecided proposal can be denied and
replaced; main judges whether earlier consent covers the replacement. approved
or automatic queued work is already committed: there is no individual action-edit
or revoke tool. scoped stop cancels ALL unentered work of its named request;
observe cancellation before replacement from another live request (for example,
stop the original and continue the owner's editing request into the next turn).
entered/uncertain effects cannot be replaced by pretending they were cancelled.
first consent decisions are immutable; ordinary stop may arrive after entry.

## stop and administrative control

ordinary `stop`, including scoped prose, reaches main unchanged. main may emit
`InputOutcome.stop` for named delivered requests. terminal settlement reuses only
the transaction-level cancellation of proven unentered actions, marks those
requests stopped, clears waits and preserves entered effects. do not reuse global
`_apply_control`: no control sequence, global fence, automatic resume, worker or
descendant cancellation. missing context is not proof unseen work stopped.
latest owner intent/stopped-parent state accompanies later factual events; those
events have normal capabilities but cannot revive their parent request.

administrative pause/resume remains. pause fences ALL waking origins and cancels
unentered actions/approvals; entered effects reconcile. resume releases only its
own stopped targets and never resurrects cancelled actions, old approval decisions
or conversationally stopped requests. repeated pause during the same paused
period retains prior targets and adds newly paused requests; a completed resume
ends that accumulation. reuse existing control targets, not another control ledger.
deployment shutdown remains host-owned.
no todo eligibility or new revocation mechanism.

## content designer's contract

a designer owns framing, main instructions and public rendering for each feature.
examples illustrate quality, not mandatory templates.

| schema / surface | good content |
| --- | --- |
| event framing | honest source, age, cause and fact; no invented owner speech or public leakage of internal context |
| `progress.text` | useful finding, changed direction or blocker; no periodic filler or unrecorded later-work promise |
| `waiting.text` | actual blocker or ordinary consent question: `send the lease questions to maya?` |
| `needs_input.context/question` | one material missing decision; tools supply discoverable facts |
| `partial.text/limitation/question` | useful result, relevant limit, at most one needed question |
| `answered.text` | supported outcome/evidence; attribute worker reports and material verification limits; dispatched bytes, idle and approval recorded are not effect success |
| `failed.explanation` | observed failure and useful next step; no promised safe retry of uncertain effects |
| `silent.reason` | `no_owner_notice_needed`; normal settlement, no public text |
| stop / failure notice | `i sent an interruption; i cannot yet confirm it stopped.` / `i couldn't finish processing these requests. they remain unfinished and need repair.` |

lowercase authored prose/host labels; preserve source casing. bound assembled
finals including labels; reject oversize, never crop. remove origin-required
notices and unconditional calendar/fleet incompleteness rewrites of answered or
silent output; retain typed coverage receipts and truthful-answer instructions.
main judges relevance. remove stale `c-` worker guidance: current skid is
terminal-only v9. small deliverables here are prose; repo files/access arrive in
later slices. no cards, notification subsystem or runtime content critic.

## non-overlapping implementation boundaries

production units follow this order; interfaces above are the handoffs. unit 5
runs THROUGHOUT: each feature's red proof precedes its implementation. one writer
per file, including shared files changed for another unit. no parallel work order.

| unit | exclusive files / responsibility |
| --- | --- |
| 1. durable facts | `db.py`, next migration, `messages.py`, `actions.py`, `native_journal.py`: append, causal/request state, decision receipts, settlement and scoped cancellation |
| 2. protocol/content | `terminal.py`, `action_requests.py`, new small `approval_tools.py`, `definitions.py`, `session-compatibility.json`: schemas, one prompt/plan, binding declarations and designer content |
| 3. runtime composition | `native_runtime.py`, `write_dispatch.py`, `read_dispatch.py`, `read_positions.py`, `admission.py`, `write_policy.py`, `tool_composition.py`, `service.py`, `cli.py`: admission, receipts, serial dispatch/recovery and wiring; delete `write_gate.py`, `schedule_tools.py`, `proactivity.py` |
| 4. discord/cutover | `discord.py`, `native_cutover.py`, operational docs: plain ingress/outbox and stopped inventory; delete `approval.py`/`approval_runtime.py`; shared-file edits go to their owners |
| 5. qualification | disposable probes and concise evidence here; designer and independent adversary review each feature/stage |

paths are under `src/jarvis/` except migrations/docs. preserve memory's changes and
approved checks. no upstream change is identified; report an actually missing
public primitive rather than inventing a bridge. consolidate existing helpers;
do not add a generic approval framework or separate state machine.

## hard cutover and deletion

use the actual migration predecessor, including concurrent memory work. with the
service stopped: snapshot privately; inventory pending effects/approvals,
reminders, waits, parks and undelivered results; reconcile entered effects and
settle original seals. explicitly drain/cancel incompatible unentered actions;
disable old components before replacing handlers. unfinished old executable
contracts block admission. never rewrite receipts or renew old approvals.
historical terminal contracts/columns stay opaque where deletion would erase
history; no executable old codec.

backfill retained waking state/parents only from canonical action/invocation
facts. ambiguous settlement is named repair work, not inferred completion.
ambiguous historical host settlement is parked for named repair.
preserve reminder purpose/time/source references as private cutover data; slice 2
converts retained obligations to todos. no temporary reminder table/future schema.
no unattended activation until selected slices and commitments are accounted for.

delete gate definitions/fingerprints/descriptors, owner-only write checks,
source-specific main routes, payload-equality replay, component renderers/
interactions/recovery predicates, schedule tools/timers/finalization/fallbacks,
chat-stop interception, mandatory-notice parsing and obsolete output critics.
drop `approval_message_required`; new actions do not write component/successor
fields. remove unreachable imports/helpers/configuration and old cutover rewriting.
retain nonce-backed outbox, connector reconciliation and asynchronous worker wait.
rotate affected tool/policy/plan/session revisions. repair forward after new
admission; no restoration over new canonical effects.

## acceptance and red/green/refactor

for EACH feature: designer defines good content above; adversary reviews design
and proposed red cases; implementation proves green; designer/adversary inspect
actual outputs and crash boundaries; refactor duplicated logic, re-run affected
and final journeys, record evidence, then delete only these temporary probes.
no permanent harness or restoration of the retired suite.

| feature | minimum temporary proof |
| --- | --- |
| common events | real postgres/store/journal/runner for owner, action and worker inputs; event arrives midturn; same plan admits an automatic write; honest provenance, duplicate/mismatched identities and optional silence |
| consent | ordinary question → owner yes/no; earlier consent on an event; quoted external yes cannot supply owner identity; decision-commit/reply crash, same/conflicting callbacks after completion/pause, repeated pause/resume retains correct targets, effect once and outcome publication while main remains active |
| continuation | result races waiting commit; duplicates/unrelated waits; reported worker wait does not spin recovery; sibling unknown-effect/matching-paid-read barriers; known result permits genuinely new same-arguments work |
| scoped stop | exact chat `stop` reaches main unchanged; two requests, stop one waiting request, cancel only unentered work, other remains live; entered effect settles once; late event/restart preserves stop without reviving its parent |
| product/recovery | malformed mixed owner/host batch parks all with one notice; named repair, sealed-result recovery, context-bound exclusion and multibyte progress boundaries; irrelevant incomplete calendar/fleet evidence does not force prose, while material coverage limits stay explicit |
| cutover | predecessor migration, unfinished old execution blocks admission, history/outbox retained, retired paths absent, reminder obligations held for slice 2 |

inject failures around real transactions/dispatch; do not replace the durable
implementation under test. deterministic provider/connector ports prove
integration, not live behavior. separately exercise actual contained provider and
discord: owner plus host event, conversational consent to an actual connector
effect using synthetic content on an owner-controlled test resource, useful
result/silence and restart after canonical commit
before delivery. use private synthetic content/existing authorized resources,
no unrelated recipients or private fixtures. installed worker proof stays slice 3;
actual todo timing/busy-main publication stays slice 2. fabricated time input
proves only generic framing, never a scheduler.

record source/dependency revisions, red failure, final green, content/adversarial
review and probe deletion here. run `scripts/verify`; report the existing
[dependency audit](issues/dependency-audit.md) separately if still failing. remove
resolved issue records only after proof. the original documentation adoption
performed no code, behavioral/live test, deployment or service resumption; the
subsequent owner-authorized implementation is recorded below.

specification review: architecture, content design and independent adversarial
passes completed against the stated source. material findings are incorporated;
no unresolved product choice remains. this is design review, not runtime proof.

## implementation evidence

qualified source: `b8299b4`, on `feature/one-main-events`, following the source
audit at `8c0bf36` and memory delivery
`d66e84057cb2468f23aacf3f359dac49453e0a3a`. the branch was rebased memory-first
while preserving newer main changes. migration `0008` follows memory's unchanged
`0007`; fresh `0001`→`0008` and populated `0007`→`0008` upgrades pass. the stopped
deployment lock rejects a concurrent migration atomically. historical text,
dates, effect contracts and receipts survive; ambiguous host history is parked.

frozen dependencies:

| dependency | revision |
| --- | --- |
| llm-agent-kernel | `8524c8c737bbe56a0993da1421084d0122d08f49` |
| provider-runtime | `7a2493e5f4da34f6d9a32e2504d8fc6333482385` |
| llm-tools | `8989f3afdcc640f775bd0cc9e7a0b4c246f10e57` |
| universal-memory | `27d6f1b4e2ddcbc2aa831eb6066f384fccb552ad` |

temporary verification used real postgres 16/pgvector, actual stores, journal,
runner, dispatch lane and tool executor. deterministic external ports supplied
failure timing; they are integration evidence, not claims of live provider work.
nine independent adversarial journeys and the durable/protocol/cutover probes
pass on the final schema. the retained memory capture/retry regression passes
unchanged on its own disposable database.

| feature | observed red and final proof |
| --- | --- |
| common events | baseline owner priority and host settlement failed; final shared selection, honest framing, strict duplicate identity, full host write authority, appended input and optional silence pass |
| consent | baseline had no local decision binding/receipt; final atomic decision/receipt rollback and postcommit reply recovery pass, including earlier owner evidence, forged owner rejection, same/conflicting decisions, pause and completed targets |
| effect recovery | review exposed approved ambiguity waiting behind main and a pause-after-entry recovery spin; final existing one-action reconciliation publishes while main remains active, never repeats without proof, and leaves denied queued entry safely pending |
| continuation | baseline host paid-read and midturn receipt probes failed; final sibling barriers, unrelated work, new equal-arguments writes, stable appended batches, required-context exclusion, waiting races and nonspinning reported worker waits pass |
| stop and pause | exact chat stop reaches main; two-request scoped settlement cancels only proven unentered work, entered effects settle once, late events retain stopped-parent facts, repeated pause/resume keeps its own targets |
| product and content | baseline malformed mixed input consumed host facts and progress admitted excessive utf-8 bytes; final parking/one notice/named repair/cold-seal recovery and exact byte boundaries pass; incomplete irrelevant coverage no longer forces a rewrite |
| cutover | opaque retired terminal history publishes metadata once without execution; old unfinished contracts block admission; private inventory preserves obligations, history and outbox; retired gate/components/scheduler paths are absent |

the actual contained stock `0.160.0` endpoint passed public containment
qualification before model discovery under the final provider pin. live runs used
`gpt-5.6-terra`, reasoning `high`, a separate auth-only task home, runtime state,
private cognition directories and disposable database/ownership lock. no installed
service or native fleet history was used.

live owner arithmetic plus an independent host fact produced a useful mixed
answer and explicit completion. midturn delivery retained unfinished owner work;
an early silent/empty result exposed an instruction gap, repaired by specifying
that appended batches add to unfinished requests. unrelated partial fleet
evidence yielded `42`; material calendar denial yielded an explicit partial
answer without claiming overall availability. routine host handling could be
silent. content review judged relevance and evidence, not exact wording.

live connector consent used synthetic mail addressed only to the authenticated
owner's own account. the first actual run created one draft, then supplied an
invalid action reference while asking permission. the original seal was retained,
the request parked, and nothing sent. clearer wait-state instructions and named
repair reused that original draft. ordinary owner `yes` then committed one local
decision, one send with one executor entry, and a separate outcome event. gmail
raw readback matched the stored recipient, subject and body exactly. all requests
and the outcome completed. ordinary owner `no` separately cancelled a pending
proposal with zero executor entries and zero connector operations.

actual discord received the canonical question, truthful repair notice and result.
a separate lost-watermark/restart trial returned the same discord id for the
same persisted nonce, with one visible message and an empty outbox. no real
gateway session or production database was started. installed skid remains slice 3;
real todo timing remains slice 2. this source refuses unattended activation until
the selected slices and retained commitments are accounted for.

content design and independent adversarial review covered every feature and the
final source; all concrete source findings are closed. temporary probes were
deleted after final acceptance; the existing memory regression remains. static,
types, all 121 documentation checks, build and fresh installation passed.
`scripts/verify` failed only at its final dependency audit: six pre-existing findings in
three registry packages. dependency repair is coordinated with memory rollout.

## explicit costs

- consent, relevance, completeness and silence depend on main's judgment; no host
  proof that prose conveyed every argument or useful notice.
- component-wide uncertainty delays some safe new writes; independent requests
  have no semantic duplicate detector.
- conversational stop waits for main and affects only named, proven unentered
  work; no effect reversal or guaranteed descendant interruption. replacing
  committed unentered work cancels its request's other unentered actions too;
  surgical editing/revocation is outside this slice.
- intermediate slices may lack scheduling and remain unreleased. historical
  evidence remains while old executable paths are removed.
- temporary-probe deletion reduces retained regression coverage; preserve the
  qualification record and separately approved memory checks.

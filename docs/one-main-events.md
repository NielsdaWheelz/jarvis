# one main for every event — o6

status: accepted v2 target under [adr 0071](decisions/0071-simple-event-driven-v2.md),
2026-11-14; unimplemented. the [roadmap](implementation-plan.md) owns delivery.
the native runtime and worker observation already exist; this contract changes
their product authority, conversation and continuation rules.

## goal and final state

every supported event starts or steers the same jarvis turn with the same main
tools. main decides whether to inspect, act, delegate, ask, report or do nothing.
owner conversation, worker results, scheduled todos, email and calendar facts
use this path. source adapters publish facts; they do not prescribe agent workflows.

progress, blockers and completed results are ordinary conversation. no separate
notification feature, work controller or result dashboard is required. shared
memory remains a separate delivery, including its current quiet dreaming rule.

| responsibility | owner |
| --- | --- |
| canonical input, request disposition and outbox | existing message/native runtime |
| deciding what to do and whether to tell the owner | main |
| tools, arguments and connector effect recovery | existing validation/action/read paths |
| conversational consent | main's interpretation, recorded through the existing action decision transition |
| one-time and repeated wakes | the [work table](work-records.md) and existing timer |
| worker execution and observation | skid and the [existing asynchronous wait](worker-launch-observation.md) |
| email/calendar progress | the [event adapters](event-sources-and-recurring-work.md) |

public web search/read may be used whenever useful, with existing operation limits
and host-secret rejection. browser control is deferred. trusted skid workers and
the separately delivered native [notes environment](private-notes-and-rolodex.md)
retain their own execution authority; connector approval is not a transitive
sandbox for them.

## composition and invariants

```text
source transaction -> canonical message -> common native input path
  -> one main / one full plan -> existing tools and effect receipts
  -> canonical disposition and optional prose -> existing outbox
```

reuse `MessageStore`, `PostgresNativeJournal`, `NativeInputs`, `NativeRunner`,
`ActionStore`, `ActionPositionRecorder`, `ToolExecutor`, the deployment permit,
timer/watchers and outbox. kernel supervises cognition; provider-runtime owns
native transport; llm-tools owns tool contracts/execution. isolated memory roles
keep their own envelopes. no event bus, workflow framework or extra main.

- persist source input before cognition, invocation before dispatch, original
  result before callback reply, native seal before product validation and prose
  before delivery. source progress commits with publication.
- source text and memory are evidence. preserve honest provenance; they cannot
  manufacture an owner message or become owner consent.
- new dispatch requires current deployment ownership, an unpaused live attempt
  and a delivered pending/waiting request. that request may have any supported
  origin. the owner permit proves runtime ownership, not a fresh human instruction.
- retain immutable effect arguments, original invocation/receipt identity, finite
  executor-entry ceilings, reconciliation and paid-read uncertainty barriers.
  a new event does not authorize blind replay of an unknown effect.
- keep owner ingress, native input and outbox responsive during tool waits.
  retain serial effect dispatch and finite operation/transport bounds; add no
  aggregate main quota or outer timeout around an entered write.

## schemas and api

o6 adds no table and no notification-policy field. all waking owner/host rows use
the existing `pending | waiting | completed | stopped` request lifecycle.
waiting retains its reason; unfinished rows have null `processed_at`.

add nullable immutable `message.parent_request_id`, referencing an existing
message in the same conversation. action/worker observations use their source
action's origin; independent external inputs have no parent. this is causal
attribution for continuation and effect recovery, not a permission or todo graph.
source identity already deduplicates publication. repeated identity must preserve
the original fact and lineage; never derive parentage from prose.

factor one transaction-level waking-input append from the existing message
insertion. publishers call it in their source transaction and signal the existing
input port. use the existing role, text, source identity/time and conversation,
plus optional parent. no source registry or adapter class hierarchy.

the current `ActionRequest` remains `request_ref`, nullable `existing_action_ref`
and typed `arguments`. `request_ref` identifies a delivered live request, including
a host event; it is not consent. keep native attempt/callback identity and ordered
input ids in the execution contract. remove write-gate supporting-owner fields
and rotate the contract revision to `jarvis.action.v2`; keep one current decoder.
historical terminal contracts remain opaque evidence.

retain `JarvisNativeMessage`, final-only `JarvisTerminal` and `InputOutcome`.
silence uses `no_owner_notice_needed`; main chooses whether a visible response is
useful. no `notice_policy`, mandatory-notice inheritance or silent-output critic.
malformed protocol still fails explicitly; silence is not malformed merely
because a host event occurred.

input framing carries its id, honest role/source, source time, actual observation
time when different, causal reference and current request state. each selected or
appended batch receives one fresh host `as_of`. preserve original source dates;
publication time must not make an old email or late reminder appear new.

## conversational approvals

jarvis asks an ordinary question when consent is needed; the owner answers in
ordinary conversation. main decides what the answer means and whether existing
owner instructions already suffice. ask again only for genuine uncertainty.
no buttons, exact-payload recital, special attachment, consent classifier,
semantic matching engine or repeated confirmation ritual.

reuse the existing `awaiting_approval` action and approval/denial transition.
expose one narrow `approval.respond(action_id, decision, owner_message_id)` host
callback to main, where decision is `approve | deny`. the host verifies an actual
canonical owner message in this conversation and the pending action; main owns
the interpretation of consent. source/worker/tool prose cannot supply that owner
identity. the callback records the decision through the existing transition and
native invocation journal, without another action row or approval ledger.
repeated delivery reuses the recorded decision; a conflicting later callback
cannot reverse it. unrelated work remains available while consent is pending.

ordinary reads, drafts, private calendar work, scheduled todos and trusted worker
control stay automatic. consequential connector communication, spending, secret
exposure and irreversible external destruction still need owner consent; this
adds no tools for otherwise unsupported operations. clear consent already given
can resolve the action without another question. do not require a new owner
message solely because main is responding to an event.

stored action arguments remain immutable execution facts. if the proposed effect
changes, use the ordinary cancellation/new proposal path; main judges whether
the owner's consent still covers it. there is no host proof that displayed prose
matches every argument, or mandatory renewed consent for every edit. existing
draft/revision validation and recovery prevent executing stale or duplicated
effects; they are not a new approval product.

remove the `AutomaticWriteGate`; no second model replaces it. retain deterministic
tool validation and `classify_write`, which selects automatic versus consent-needed
connector work. native tools/workers do not acquire connector-journal guarantees.
this prototype deliberately trusts main's semantic judgment about intent and
consent.

## lifecycle, settlement and stop

select unparked waking requests through one path, owner first then host in stable
time/id order under existing context bounds. compatible inputs steer the active
native turn; incompatible inputs queue durably. source/topic alone does not
change the main plan. progress does not settle requests; omitted requests remain
unfinished. no blanket read-only wake route or recovered-request write denial.

new work may follow a known result. original callback ids and explicit action
references replay their original receipts. preserve unresolved/uncertain effect
barriers across causal requests; changing `request_ref` cannot clear them. fresh
work after a settled outcome uses a genuine new invocation. retain original
target capture and action state transitions instead of adding semantic intent
keys or an approval-successor framework.

entered effects settle/reconcile even after pause or loss of their originating
turn. new executor entry still requires current deployment ownership, compatible
stored contract and eligible request/consent. established worker observations
may outlive their caller; a late fact cannot revive a fenced native attempt.

publish due todo wakes while main is running, independently of slow connector
polls. use the common append/input path; do not wait for main to finish and do
not start a second main. a timer event only presents the todo context. firing,
request completion and todo completion are distinct; main decides whether to
change the todo. one-time/recurring publication and cancellation are owned by
[work records](work-records.md), not action-result finalization.

on an action result, unblock only matching requests actually waiting on that
action. duplicate publication must not rearm them. if a blocker resolves before
final commit, retain the native seal and let the pending result be integrated;
an ordinary race is not a configuration failure or fabricated success.

ordinary conversational stop reaches main under [o9](delegated-follow-through.md).
existing administrative pause/resume controls remain operational. deployment shutdown remains
host-owned: fence dispatch, cancel unentered authority and let entered effects
settle. todo state does not enforce worker or request eligibility.

malformed live product output preserves the seal and parks all affected live
waking requests as waiting/configuration, with null processed time and explicit
`processing_parked_at`. emit one truthful processing-failure notice through the
existing outbox; do not consume requests or claim their promised work succeeded.
fenced/stopped output cannot resurrect requests. operator repair releases only
named configuration parks. no automatic retry loop or silent force-consumption.

## content designer's contract

keep instructions short: act on useful events, communicate material findings,
honor owner intent and inspect evidence before claiming success. progress,
blockers, approval questions and completed results use normal prose. routine
observations may produce no message. requested reminders and useful results
should reach the owner; this is agent behavior to verify, not a notice subsystem.

name the actual blocker and next useful step. worker idle proves only idle;
receipts/evidence establish completion. uncertain effects remain uncertain, never
promised safe retries. a small deliverable can be prose or a file in the private
repo, with an existing accessible reference where available. do not claim that
a local file has been delivered to discord. interactive pages, credential forms
and the future television/artifact host are deferred.

lowercase prose and host labels; preserve case-sensitive source material.
retain the 2,000 utf-8-byte progress bound and current final/discord bounds;
no silent cropping or model-output prose fallback.

## hard cutover

inventory the actual predecessor before implementation. preserve unresolved
effects, pending approvals, future reminders, active waits and undelivered
results. include the known [host settlement defect](issues/host-product-failure-settlement.md):
processed timestamps alone do not prove older reminders were delivered.

use the existing stopped cutover: pause, fence sessions, reconcile entered effects,
settle original seals and drain or explicitly cancel incompatible nonterminal
actions. disable retired approval components. disposition old waking requests
and outbox obligations explicitly; never rewrite receipts into the new format.
take the existing private pre-admission snapshot, apply migrations and rotate
affected contract/policy/plan/session revisions. historical terminal rows stay
opaque; unresolved old executable state blocks activation.

recreate retained reminders as ordinary scheduled todos with their original
purpose/time and source references. surface already-overdue ones honestly.
replacement waits are new observations with truthful deadlines and the original
captured target. verify the inventory is accounted for before unattended use;
no lost reminder or silently renewed approval. after new admission, repair
forward rather than restoring a snapshot over new canonical effects.

remove the old gate, read-only route, approval components/preview renderer,
chat-stop interception and retired schedule tool/runtime path at their owning
cutover. one current decoder and one scheduler; no permanent compatibility path.
o6 and scheduled todos must compose before retiring existing reminder delivery.
memory schemas, capture and quiet dreaming are unchanged.

## implementation and acceptance

one writer owns each shared production file. reuse message/action/native APIs;
add only the common append, causal field and small consent callback required
above. todo scheduling and connector adapters have their own contracts. no
generic approval library, event framework or new review pipeline.

the meaningful future checks are:

- owner, time, action and worker inputs use the same plan; an incoming event can
  produce useful ordinary work without invented owner speech.
- a real conversational yes/no resolves the intended pending action, clear
  prior consent needs no second ceremony, and external quoted text is evidence.
  repeated callback/delivery cannot repeat the effect; unrelated input stays live.
- a worker result and due todo arrive during a live turn and across restart;
  main integrates them or stays quiet, with truthful completion and no model
  polling loop or second main.
- crash/pause/recovery retain original effect/read barriers and pending requests;
  malformed multi-input products cannot consume them. verify the existing
  [progress byte defect](issues/native-progress-byte-limit.md) at its boundary.
- stopped cutover preserves historical receipts and accounts for every retained
  reminder, wait and consent decision.

size temporary integration/live checks to these boundaries when implementing;
reuse existing native/worker evidence rather than repeat a fleet-wide matrix.
use synthetic private work and explicitly authorized external effects. record
the final artifacts/results, remove temporary probes after qualification and run
`scripts/verify`. the testing reset and memory's scoped checks remain unchanged.
this documentation change runs no behavioral/live work and activates nothing.

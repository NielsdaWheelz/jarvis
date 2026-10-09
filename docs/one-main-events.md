# one main for every event — o6

status: proposed implementation contract; no runtime change. updated 2026-10-06.
the owner has settled the product choices below. source audit: jarvis `f3b4dc3`.
this document owns o6; the [roadmap](implementation-plan.md) owns sequencing.
accept an authority adr and adopt this target in [spec](../SPEC.md) before coding.

## goal and final state

one native main handles every supported waking input with one frozen tool plan,
one request lifecycle and the same effect/approval rules. honest provenance and
notification obligations differ; capability does not depend on origin.

main may inspect, prepare ordinary work, delegate, schedule a finite follow-up,
propose an exact consequential effect, or do nothing. no invented owner message,
new standing permission conversation or separate background agent is required.

| decision | target |
| --- | --- |
| worker authority | trusted skid workers retain their own authority settings; jarvis approval governs its direct connector effects, not transitive worker effects |
| public web | bounded search/read whenever useful; retain operation limits and host-secret rejection |
| visibility | ambient routine success may be silent; requested results/reminders, approvals, unresolved blockers and failed/uncertain effects need notice |
| scheduling | finite one-shot follow-ups; no recurrence/polling feature or indefinite timer rearming |
| quiet wakes | explicit immutable `notice = required | optional`; requested reminders use `required`, internal follow-ups may use `optional` |
| conversational stop | [o9](delegated-follow-through.md) replaces chat-stop interception/per-work fencing with main's interpretation and ordinary actions; existing deployment pause/resume remain operational |

## scope and non-goals

support existing owner discord inputs, ordinary action resolutions, worker-wait
observations (`source = action`) and due wakes (`source = schedule_wake`). provide
one append contract for later trusted source adapters; implement none here.

no work table/o7 bookkeeping, delegation content/o9, email ingress,
connector polling, recurring scheduler, memory overhaul, new integrations, ui,
workflow engine, worker graph, semantic intent registry, privacy classifier,
notification ledger or replacement model gate. current recall/remembering still
apply to owner rows only. no kernel/provider/tools/skid api change is required.

## composition and invariants

```text
existing source transaction
  -> canonical message + source fact (atomic)
  -> common pending-input selector / native input port
  -> one run_native main + one full frozen plan
  -> read recorder OR deterministic write policy + action/approval
  -> original native seal
  -> validated dispositions + canonical outbox + due-wake settlement (atomic)
  -> existing discord delivery
```

reuse `MessageStore`, `PostgresNativeJournal`, `NativeInputs`, `NativeRunner`,
`ActionStore`, `ActionPositionRecorder`, `ToolExecutor`, `classify_write`, native
owner permits, scheduler/watchers and outbox. jarvis owns product authority;
kernel supervises the native turn; provider-runtime owns transport; llm-tools
owns frozen contracts and execution. isolated memory roles keep their envelopes.

- source text, tool results and memory are evidence. none can create an owner
  control, grant, approval, parent relation or notice policy.
- persist input before provider use, invocation before dispatch, result before
  callback reply, native seal before product validation, output before delivery.
- preserve original identities, payloads, receipts, finite executor ceilings,
  reconciliation, paid-read barriers, containment and one serial dispatch lane.
- native reader, owner ingress, consent and outbox remain responsive. no new
  main elapsed/cumulative quota or timeout around an entered write.
- new dispatch requires current deployment ownership and live canonical requests;
  the owner permit is runtime ownership, not proof of a fresh human instruction.

## schemas and api

no new table. extend the current nine-table predecessor with one migration:

| item | exact contract |
| --- | --- |
| `message.parent_request_id` | nullable `UUID` fk to `message.id`, delete restricted; immutable after insert/backfill |
| parent rules | owner inputs have null parent; current host publishers set it from the source action's `origin_message_id`; parent already exists in the same conversation; no self-link |
| `message.notice_policy` | immutable `required | optional | null`; null for assistant/control rows; ordinary owner rows optional, preserving courtesy silence; host policy below |
| `message.request_state` | existing `pending | waiting | completed | stopped` applies to every waking owner/host row |
| `wait_reason`, `processed_at` | waiting alone has a wait reason; pending/waiting have null processed time; completion/stop commit their timestamp with the disposition/control |
| `ExecutionContract.contract_revision` | required literal `jarvis.action.v2`; one current closed decoder |
| execution contract | remove `write_gate_supporting_owner_message_ids`; retain existing tool/implementation/policy/plan revisions, effect/replay/input digest, attempt ceiling, `claim_id`, `through_checkpoint`, `model_step_ordinal`, ordered `input_message_ids` and immutable `agent_target` |
| native meanings | `claim_id` names the original native attempt; `model_step_ordinal` is its callback ordinal; that pair already identifies the invocation |
| `ActionRequest` | unchanged keys: canonical `UUID` `request_ref`, nullable `existing_action_ref`, exact typed `arguments`; ref names a delivered live owner OR host request, not human consent |
| schedule create | existing `type`, aware `execute_after`, bounded `instruction`, plus required `notice: required | optional`; no default/old shape |
| schedule cancel | unchanged; cancellation targets a queued original only |
| `result.wake_outcome` | existing closed `concluded` object: `type`, `conclusion_message_id: UUID string | null`, `recorded_at`; null only for an optional wake completed by a silent final |
| native output | retain `JarvisNativeMessage`, final-only `JarvisTerminal`, `InputOutcome`; replace `Silent.reason` with literal `no_owner_notice_needed` |

backfill host state from processed status ONLY after the failed-product inventory
below resolves false consumption; parent from canonical source/action identity;
notice conservatively as required. never parse prose or old execution contracts
to invent lineage. unresolved identity/notice evidence blocks activation. parent
insertion followed by immutable links establishes acyclicity; timestamps do not.
runtime updates never change parent/notice/source identity.

factor one plain transaction-level waking-input insertion function in
`messages.py`; `MessageStore.insert_waking` and all three host publishers call it.
accept the existing role/text/source/conversation/source-id/time fields plus
parent and notice. it uses the caller's source transaction and existing lock
order. repeated identity must match all immutable values; otherwise fail closed.
do not create a source registry or adapter class hierarchy.

new source times are immutable: discord's original timestamp; wake `execute_after`;
action `completed_at`; wait outcome `recorded_at`. separately published creation/
registration facts use their immutable receipt time. missing time is a defect,
not permission to use publication time. preserve historical message timestamps;
never relabel them during backfill. each selected/appended batch separately
receives one fresh host utc `as_of`; render it once. initial request freezes it;
cold reasoning gets a fresh clock; sealed-terminal recovery never rerenders.

host input framing reuses `HostInput`/`PromptSections`: input id, honest role/
source, source timestamp, parent, request state/blocker
and notice policy. separate instructions from evidence. no model-authored
capability/approval/notice override.

## authority and effect recovery

delete `AutomaticWriteGate`; no second model replaces it. use one global
host-owned write-policy revision in binding policy inputs. retain strict pure
validation, exact frozen plan proof, host-secret checks, immutable target capture,
live draft/etag checks and deterministic `classify_write`.

ordinary reads, drafts, verified owner-only/no-attendee calendar work, one-shot
schedules and trusted worker control remain automatic from every event. gmail
send and shared/unknown/attendee-bearing calendar changes retain exact-action
approval. unsupported consequential operations remain unavailable. free-form
text never approves. only declared host callbacks are available; undeclared
built-ins/mcp/network and permission escalation remain disabled.

new native tool dispatch requires current deployment ownership, an unpaused live
attempt and at least one delivered pending/waiting request in the same
conversation. writes and their target capture bind that request through
`request_ref`. parent links supply attribution/effect recovery, not a work
eligibility gate. a fresh admitted event gets the full main plan regardless of
historical conversational stop. known rejection uses existing typed host
rejection, never a configuration park.

stored-action approval/executor entry requires current deployment ownership,
unpaused pending/waiting origin, compatible exact frozen
stored contract and stored automatic policy or valid exact approval as classified.
the ORIGINAL native turn need not remain live: durable actions outlive it.
original invocation remains immutable
acceptance evidence, including approval successors. entered-effect reconciliation
requires current deployment ownership and original stored contract/evidence;
it remains available while paused/stopped. any evidence-proven safe repeat is
NEW executor entry and requires eligible origin/authority above. established
schedule/wait observation, publication, settlement and receipt replay are host
lifecycle work; they may outlive caller completion. late in-flight facts may
commit after operational fencing; facts do not revive the fenced attempt.
fresh events use normal main authority. repeat sensitive checks
under existing conversation/input/native/action locks.

remove the blanket `accepted_actions.recovered` / `recovery_requires_action_reference`
denial. recovered requests may perform genuinely new work, subject to these rules:

apply in this order:

1. original callback identity replays its original reply/action. explicit refs
   recover exact self/ancestor actions, retaining their original stored envelope.
2. enforce current proposal/stored-action authority above. matching denial and
   queued/approval/executing/uncertain ancestor effects retain their barrier/result;
   changing `request_ref` cannot launder them. `Deny` survives resume for that
   exact canonical tool/inner payload throughout the lineage, leaving unrelated
   work available; a fresh genuine owner root may propose a fresh exact approval.
3. same request + exact tool/inner payload reuses its accepted successor-chain
   TIP, following `supersedes_action_id`, never wall-clock order. sole automatic
   replacement exception: NEW proposal, null existing ref, zero original attempts,
   no original approval, exact `action_cancelled_v1` / `owner_stopped` result,
   eligible live origin and a genuine resume targeting that origin satisfying
   `old_attempt.control_sequence < resume.sequence <= current_attempt.control_sequence`.
   no existing successor; use the existing unique `supersedes_action_id`. worker
   replacement must freshly capture the SAME original ref/stop mode/closure scope;
   reassociated handles are rejected. genuinely different proposals use normal
   admission. original callback replay still returns the original.
4. only remaining KNOWN settled ancestor outcomes permit a new event's fresh
   effect, including renewed observation after timeout. denied, unknown and
   owner-stopped cancellation are not this exception. do not deduplicate all
   settled ancestor payloads forever.

approval successors retain original immutable proposal/contract and link their
cancelled original; fresh exact approval supplies authority. do not invent a new
native invocation or relink its original action. automatic replacements have a
new genuine invocation/current contract. original cancelled actions never execute.

## lifecycle, settlement and stop

- select only unparked pending waking requests, owner first then host in stable
  time/id order, with current batch/context bounds. delete scheduled route/plan
  filters. source/topic alone never forces an incompatible provider session.
- publish due wakes while main runs: reuse `claim_next_due_schedule` from common
  selection/native polling, then the same atomic publisher and append path.
  recheck deployment ownership/pause/park under the existing claim locks. the
  timer's work flag alone is insufficient; do not wait for main to finish or
  start a second main. source work defers while paused/parked as today.
- compatible input steers; incompatible input queues through existing native
  ports. explicit dispositions apply equally to owner/host rows; omitted inputs
  remain unfinished. progress changes no disposition.
- own unresolved effects prevent completion. registered schedule/wait receipts
  are the existing exception: their later lifecycle may outlive the caller.
  ancestor effects may justify waiting refs without preventing an independent
  host notification's completion. preserve exact blocker validation.
- only NEW action-event insertion can unblock a waiter. inspect latest committed
  `native_attempt.product_outcome` that actually dispositions that input; match
  current wait reason, exact action ref and self/ancestor ownership. unblock only
  approval/reconciliation waits. inspect all real waiters; never blindly reset
  owner-input/configuration waits or rearm on duplicate publication/settlement.
- if a formerly valid action blocker resolves before final commit, preserve the
  native seal, mark the product stale and leave inputs eligible to integrate the
  pending result. fabricated refs are defects; an ordinary status race is not a
  configuration failure or synthetic success.
- a due wake finishes only when its waking request completes. commit its outcome
  with dispositions/outbox; waiting for approval does not finish it. optional
  silent completion has null conclusion-message id; preserve creation receipt.
  `finish_schedule_conclusion`, `_wake_outcome`, `_schedule_result` and the safe
  result projection accept that exact nullable case; pass the actual final id
  from `commit_product`. do not weaken other atom/uuid validation or alter the
  creation/cancel callback receipt codec.
- existing deployment `pause` includes unfinished host requests; fence callbacks
  and cancel unentered authority. entered effects settle/reconcile. administrative
  resume retains current exact-action recovery rules. ordinary chat stop reaches
  main under o9; no per-work eligibility or stopped-ancestry gate.
- malformed live product output or required-notice silence preserves the seal,
  parks all affected live waking rows atomically: waiting/configuration,
  `processed_at = null`, `processing_parked_at = failure timestamp`; emit ONE
  deterministic batch-processing-failure notice through the existing outbox.
  report source counts/recorded action failures and uncertainty; imply neither
  external-effect absence nor success.
  original reminder/result notices stay pending; no wake is marked fulfilled.
  stale/fenced/stopped output cannot park or resurrect requests.
- existing operator release clears only named park stamps under conversation/input
  locks; only waiting/configuration becomes pending. stopped/completed/other wait
  states remain unchanged. resume/old results never clear parks; no automatic
  retry loop. remember only completed owner rows, as today.

## content designer's contract

the content designer supplies prompt sections and examples to the single
definition-file owner; no separate critic or content pipeline is introduced.

| output | good content |
| --- | --- |
| progress | one new useful finding, changed direction or blocker; no ceremonial status, unproved success or promised uncommitted work |
| answered | direct answer/receipt-backed outcome with recognizable target and result |
| partial | useful result, explicit material omission, at most one question |
| needs_input | one necessary choice and enough context to decide |
| waiting | actual blocker/next step, exact canonical action refs, no success claim |
| failed | known failure; uncertain effect is not proved absence |
| silent | no useful notice required; durable disposition still commits |

lowercase prose/host labels; preserve case-sensitive source material. hide protocol
bookkeeping unless needed for inspection. exact approval attachment remains whole.
progress is at most 2,000 utf-8 BYTES; final rendering keeps the existing discord
character bound and variant field bounds. no silent cropping, phrase matcher,
terminal-envelope extraction or model-output fallback.

snapshot host notice at event insertion:

- due wake: immutable schedule `notice`.
- ordinary action failure/uncertainty or unresolved intervention: required.
- asynchronous requested result: required when its direct parent is owner input
  or has required notice; routine success from optional host work: optional.
- worker wait `unavailable`/`target_changed` or non-null `failure`: required,
  including a matched observation whose subsequent read failed. matched/timeout/
  cancelled with no failure: optional; main may still report a useful result or
  blocker. idle alone proves no task success; action status alone cannot classify
  the observation.
- main chooses visible content for requested answers/results: a prompt/live
  acceptance obligation. owner courtesy silence remains possible; the host does
  not infer natural-language intent.

approval ui always displays. a final waiting-for-owner/configuration/blocker
disposition needs visible explanation. mandatory notices cannot settle silently;
commentary never discharges a final-notice obligation. combined final prose must
cover every required event it completes. typed incomplete reads remain visibly
partial. autonomous wakes are called scheduled wakes, never fabricated requests.

requested reminder: `reminder: submit the abstract by 5 pm.` quiet follow-up may
complete silently after routine work. an uncertain send reports uncertainty and
inspection, never a retry promise. batch-processing error names counts/known
uncertainty and retained requests; it is not delivery of their promised results.

## hard cutover

1. inspect actual predecessor and private inventory of future wakes/active waits.
   include host rows/wake outcomes consumed by prior failed native products:
   `processed_at` alone cannot prove fulfillment after the known failure defect.
   retain original evidence; record explicit disposition of missing notices.
   unresolved provenance/notice evidence blocks activation, not silent backfill.
   finish previous native conversion under its qualified release if still needed.
2. pause/stop; reconcile entered effects and unknown paid reads, settle original
   sealed native products, fence sessions and stop source workers cleanly. original
   release drains or explicitly cancels every old nonterminal action/registration.
   publish all owed terminal resolutions; drain or explicitly disposition outbound
   notices/approval components before retiring their decoder. inventory closure
   must prove these outcomes were reported or deliberately disposed, not skipped.
   close EVERY old waking owner/host request as completed/stopped; no old due-wake
   input reaches the new settlement decoder. missing reminders get compensating
   notices/recorded owner disposition, never rewritten old receipts. use genuine
   deployment `pause`, close the inventory above, then pause again; verify latest
   pause has EMPTY `control_targets`
   before snapshot. new resume must not rearm old action-bearing requests after
   their dedup evidence becomes opaque history.
3. take one private stopped pre-admission database/runtime snapshot. apply the
   migration; verify states/parent/notice backfill and source identities.
   rotate affected contract/implementation/policy/plan/session revisions; remove
   the gate role. unchanged isolated memory roles retain their contracts.
4. startup admits ONLY current tagged contracts. old terminal rows remain opaque
   audit bytes, filtered before current decoding. unresolved old active state
   refuses startup. a fenced unsealed interrupted attempt is history, not an
   unresolved product; its entered action/read obligations still need resolution.
   never rewrite receipts or copy them onto fresh actions.
5. explicitly resume the new release for supervised inventory restoration through
   genuine owner controls/normal inputs; never fabricate invocations or bypass
   admission. retained commitments use fresh owner roots. at ACTUAL recreation
   time, still-future reminders get normal new
   actions/receipts at the original instant; overdue reminders get explicit overdue
   notices, not invalid past-due creates. old waits drain/cancel; replacements are
   NEW observations with truthful new deadlines and proven original targets.
   no silent retargeting, lost commitment or reset passed off as continuation.
6. operator records receipts and closes EVERY inventory item before unattended
   cutover is complete. before the FIRST o6 admission, snapshot rollback is
   possible; afterwards repair forward preserving evidence, even without a new
   external effect. remove temporary conversion/proof code after completion.

delete owner-gate code/projections/fingerprint/role/manifest entry, scheduled-only
route/plan, text-parsed wait-notice exception, blanket recovered-write denial,
host force-consumption/blind requeue, historical executable action decoder
branches and prior `native-cutover` runtime command. keep canonical historical
data. no old executor, codec alias, dual policy or feature-flag fallback.

## non-overlapping implementation ownership

agree these contracts before parallel work. one writer per production file;
design/review specialists send changes to that writer.

| unit | files owned | delivered boundary |
| --- | --- | --- |
| a: persistence/publishers/cutover | `db.py`, new migration, `messages.py`, `actions.py`, removal of `native_cutover.py` | canonical append, parent/notice, generic states, v2 contract/receipt selection, safe unblock and cutover preflight |
| b: native execution/settlement | `native_runtime.py`, `native_journal.py`, necessary `context.py`/`service.py`/`proactivity.py` adaptations | one route, live publication/framing/clock, all-source dispositions, stale/failure/stop semantics |
| c: authority/catalogue/composition | `action_requests.py`, `write_dispatch.py`, `write_policy.py`, `write_tools.py`, `agent_tools.py`, `tool_composition.py`, `definitions.py`, `cli.py`, `session-compatibility.json`; delete `write_gate.py` | gate removal, shared policy, one main plan, recovery/approval wiring; applies designer's prompt |
| d: schemas/content rendering | `terminal.py`, `schedule_tools.py`, necessary `approval.py` label edits | closed notice/silence schema, byte limits, honest bounded labels and rendering |
| e: temporary proofs | new scoped proof files only | end-to-end database/native/tool/service tests and live qualification; no production edits |

a supplies append/lineage/action APIs; d supplies schemas; b/c consume them. b/c
coordinate the existing dispatch interface; c supplies the shared policy change
to d's schedule binding. remove obsolete gate labels from read/write metadata.
e can write
red proofs from the frozen contract. serialize shared-file integration/cutover;
never add compatibility to accommodate arbitrary merge order.

## acceptance and red/green/refactor plan

write a small temporary end-to-end group, not a new framework. controlled faults
use real postgresql, actual jarvis service/native/kernel/llm-tools composition and
existing ports; controlled provider/connectors make crash races deterministic.
live qualification separately uses real contained codex, google, discord and
installed skid. controlled evidence never claims live external acceptance.

| proof | green criterion |
| --- | --- |
| equal origins | actual contained-codex artifacts for EACH owner/wake/action/worker origin show the same grants and automatic draft/private-calendar/worker work without fabricated owner input |
| consequential work | background send/shared-calendar effect waits for exact approval; unrelated owner input remains serviceable; `Deny`/forged prose/wrong components never execute |
| notices/schedules | required reminder/result visible; optional follow-up silent; failed/uncertain/blocking outcome visible; one-shot receipt/due event deduplicates across restart |
| mixed inputs | required wake becomes due during a held native turn and publishes/steers before it ends, with no second main; honest sources/clocks/dispositions; omissions remain pending; no completion over unresolved own actions |
| deployment control races | real pause versus approval/executor interleavings; delayed callbacks/results retain facts without reviving fenced attempts; administrative resume preserves fresh approval/replacement rules |
| recovery | crash after acceptance/entry/result/before reply: original effect/reply once; new distinct follow-through allowed; unknown read/effect still blocked |
| effect laundering | changed request ref cannot duplicate unresolved ancestor payload; denial stays denied; settled observation permits fresh renewal; automatic replacement needs real resume |
| settlement race | resolved blocker before waiting commit yields stale product plus pending result, not a park, forged success or lost request |
| content/schema faults | non-ascii progress respects bytes; final stays bounded; malformed/mandatory-silent batch stamps parks on ALL affected requests, one honest error notice, zero fulfilled wakes; repair releases configuration waits only |
| cutover | unfinished old state refuses activation; false old failure fulfillment inventoried; opaque old bytes/times unchanged; every retained reminder/watch has truthful disposition/new receipt; no legacy decoder path |

record red evidence against the unchanged predecessor. implement by the ownership
map, review each boundary adversarially, then run green proofs. refactor duplicate
append/authority/settlement logic; rerun changed concerns and final integrated
journeys. designer reviews recorded live content against the rubric, including
hostile quoted evidence, courtesy silence and requests for indefinite recurrence.

one authorized live journey: optional scheduled preparation/worker observation
leads to an automatic draft/private-calendar change, a required reminder and a
consequential proposal; owner verifies unrelated conversation and exact approval,
then administrative pause/restart/resume. use synthetic private payloads, harmless worker tasks
and one owner-approved test send; credentials never enter fixtures/logs. actual
installed fleet/endpoint availability is a dependency, not a fallback opportunity.

retain concise artifact identities/results in acceptance; delete temporary tests,
fixtures and qualification scripts only after final-tree integration/live review
passes. run `scripts/verify` after deletion. failure/NOT_RUN is not acceptance;
the standing testing redesign and memory's two regression groups are unchanged.

## explicit trade-offs and follow-ups

- removing owner entailment permits useful autonomous private work and removes
  an independent intent check. main's semantic judgment is trusted; deterministic
  approval/containment/recovery are not a proof against all unwanted private work.
- workers are trusted execution domains, not transitive jarvis approval enforcement.
- public queries disclose text. keep host-secret rejection and a prompt rule
  against private source prose/credentials; no claim of general privacy detection.
- one-shot receipts are host-enforced; finite useful follow-up/no indefinite
  rearming is a model/acceptance rule, not a host proof of termination.
- explicit parent/notice facts add two columns and checks, absorbing provenance/visibility
  complexity without another event or notification subsystem.
- fresh events may legitimately repeat settled effects; semantic duplicates with
  altered arguments remain a model-quality risk, not a new intent-key framework.
- hard cutover closes old waking requests; retained commitments need fresh owner
  roots/inventory re-registration. it forecloses post-admission snapshot rollback.
  temporary-test deletion leaves less regression coverage by the owner's choice.

when m4 ships, its search/open/save attach to this ONE full main plan for every
origin, superseding scheduled save restrictions. preserve canonical save's
special local receipt/atomic append exception; never wrap it in `ActionRequest`.
no memory implementation is authorized by this clause.

existing content defects belong to units b/d:
[progress byte enforcement](issues/native-progress-byte-limit.md) and
[host product-failure settlement](issues/host-product-failure-settlement.md).

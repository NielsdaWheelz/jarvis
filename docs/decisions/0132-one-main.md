# adr 0132. one main for every wake

**owner-selected design, november 27, 2026.** this is the target and implementation contract.
production still uses the previous contracts. the observed baseline is source
`5be8429`, installed `6e6c8a4`, postgres schema `0028`. verify the actual
predecessor before implementation and cutover.

[adr 0133](0133-viewer-approved-send.md) amends the mail rule with an
exact owner approval in the viewer. it defers agent draft deletion and
replacement to a separate release. the model has no executable send path.

## product contract

one owner-facing assistant runs one main turn. a message, new mail, a scheduled
todo, worker result, action result, catch-up or retry changes its input. all
have the same definition, instructions, effective tool catalog, provider
permissions, working directory, network, native children, worker abilities and
terminal contract on a given route. batches and mid-turn arrivals follow the
ordinary input rules. provenance, dates, receipts and the owner's actual
instructions remain distinguishable. a wake does not oblige jarvis to speak.

the owner delegates all **already-supported agent operations**, including
editing a shared document and creating a draft, without another jarvis
approval. the agent connectors have two product bans:

1. jarvis cannot send mail. only the separate authenticated human editor may
   send through its deliberate send action.
2. jarvis may read meetings with anyone. it cannot create, change or delete an
   event involving another person. both the existing and proposed event count.

google may require its own choice or deny a call. enrollment, account identity,
stop, provider scopes, input validity, revision checks, quota and receipts are
execution facts. an explicit instruction such as “draft only” still binds.
this is connector enforcement. independent worker machines and browser logins
are outside that technical guarantee. a prohibition also applies to what main
asks a worker to do. zero new worker containment or credential brokerage.

**why.** thirty-four mail arrivals completed in one native attempt with zero
body reads. main had a message reference but an arrival alone could not use
the gmail reader. a rate limit then consent within one outage produced only
the original status notice. an owner-present thread read and re-arm restored
reception. the count of nine residual labels established neither identities
nor nine missed emails. [turn evidence](../issues/arrival-body-review.md) ·
[outage and recovery](../issues/gmail-mcp-arrivals.md)

## a. one turn, ordinary scheduled work

**unit owner.** cognition and work. change `native_protocol`,
`definitions`, `kernel`, `native_runtime`, `native_journal`, `messages`,
`work`, `work_tools`, `recovery_catchup` and `workspace_host` in
`src/jarvis`. retire the special profiles, profile selection, reduced tool
sets, singleton admission and restricted terminals for named checks and
foreground recovery. replace native request v8/output v5 with v9/v6.
the ordinary typed terminal, per-input dispositions, steering, progress,
silence and source-backed replies apply everywhere. provider mechanics may
differ. every serving route must deliver the same main capabilities. a route
that cannot demonstrate parity cannot qualify this cut. retain the existing
account selection and effect settlement rules.

admit workspace reads under the live main invocation and current enrollment.
delete the latest-owner, selector and occurrence tests as authority gates.
an event can search another thread and consult the calendar. keep the exact
invocation, current grant and account checks at entry and on returned data.
retain causal action and read receipts, grant-bound cursors and original
source references. extract the queries still used by `citation_sources` and
`attachments` before retiring `workspace_checks`. keep quiet memory roles
and delegated workers as their existing components.

the timer continues to emit `work_wake`. a scheduled instruction carries its
condition, cadence, scope in ordinary language and end date. use the normal
reply or silence. drop the special `workspace_result`, refresh input, match
push and work tool selector field. preserve a real final local date for
bounded recurring work at the timer. a late wake after expiry cannot revive
it. move inclusive `until` to an optional date on an ordinary recurring wake,
stored as `work.wake_until date null` and evaluated in the configured owner
timezone. preserve the scheduled instant, rule, wake id, local cursor and
exact legacy selectors in the ordinary todo. expired schedules clear their
wake atomically. ordinary catch-up supplies original inputs, outstanding
questions and receipts to main. before a new opening, settle a usable original seal.
an unknown earlier effect stays attached to its original action: reconcile
that effect or report uncertainty. independent work can proceed. a new call
id, new turn or different model is no evidence that the old call failed.

**designer's specimens.** wake on “same quote as last time. can you do
thursday?” let main find the prior quote, read the calendar and update an
ordinary todo. contrast an ignorable mailing, a scheduled “only tell me if”
with no match, and an interrupted edit with an unrelated owed answer. good
content gives the owner the concrete decision and source when useful, honors
the condition, and distinguishes verified effects from uncertain ones.

## b. connector effects

**unit owner.** connectors. own `write_policy`, `write_dispatch`,
`actions`, `action_requests`, `write_tools`, `workspace_write_models`,
`workspace_writes`, `drive_connector` and the exposed action catalog. remove
the local approval decision tool from the live catalog, automatic-versus-
approval classification for supported operations, owner-origin prerequisite,
and drive audience/ancestor walks used solely for approval. remove special
check/recovery write rejection. audit attachment filing, work, worker and
draft call sites for the same wake-dependent restriction. retain fresh target,
draft identity, exact revision, byte custody, provider conflict and uncertain
effect checks. keep explicit permission inspection when the task asks for it.
the owner accepts collaborator-visible writes without a second confirmation.

keep send-capable scopes (including compose) off the agent grant and sending absent from its
catalog and executor. verify enrolled scope names without logging tokens. no agent tool,
worker adapter or blocker-resume endpoint dispatches through the human editor.
draft creation uses the existing binding. leave draft replacement and disposal
off the agent's tool surface until the [provider proof](../issues/gmail-agent-draft-discard.md)
passes. do not add a send tool, general trash, sharing editor or new calendar verb.

use one calendar participation predicate in the connector. for create, verify
the chosen calendar's effective organizer and proposed participants. for
update/delete, fetch the addressed original, verify scope/identity, construct
the effective after-state for update and check both. count google's recorded
organizer and participants, including optional/declined guests. no inference
from title, calendar visibility, display name or the authenticated viewer's
edit access. prove self by verified enrolled identity. incomplete lists,
unresolved identities, groups with unknown membership and additional unnamed
guests cannot establish a solo event. mere readers of a shared calendar do
not count. a verified non-person resource by itself is not another person.
on a secondary calendar, establish that a calendar-address organizer belongs
to the owner from verified provider data. a calendar-relative self flag or
manager role alone is insufficient. qualify what the enrolled mcp response
actually proves. an unknown secondary organizer yields an unavailable write.
interpret omitted wire fields only under qualified provider semantics. a
full addressed `get_event` on the enrolled owner's primary calendar may omit
an empty attendee array when its verified organizer is also the copy marked
self. the live synthetic primary event exhibited this shape. explicit
withholding or an incomplete response blocks the write.
retire guest editing from the model's write schemas and executor. default
new events to no invitees. preserve verified existing non-person resources.
return a typed rejection with no provider mutation if prohibited or
unverifiable. no override button. solo writes suppress guest notifications.

a verified owner-only recurring event can be created. a single occurrence uses
the effective instance and inherited guests. for a series-wide edit/delete, prove coverage of
its affected exceptions as well as the master. if the provider cannot enumerate
them reliably (including unbounded series), explain that the series change is
unavailable and permit a separately verified solo occurrence. the current mcp
catalog offers no complete exception enumeration for an existing series.
a guest on one exception matters even with a solo master. qualify the representation on the
real connector before enabling the relevant scope. the mcp calendar list has no
documented ownership field equivalent to rest’s `dataOwner`.
[calendar list contract](https://developers.google.com/workspace/calendar/api/v3/reference/mcp/tools_list/list_calendars)

use the installed workspace transport. reread immediately before sending and
again after any consent wait. bind the full decision evidence to the frozen
action. on mismatch return a conflict before the write. changed arguments
need a new action. the owner accepts that a concurrent guest
addition after the last read can beat an unconditional write. no atomic
google guarantee is claimed. treat ambiguous entered mutations through their
original receipts. [calendar update](https://developers.google.com/workspace/calendar/api/v3/reference/mcp/tools_list/update_event) ·
[event fields](https://developers.google.com/workspace/calendar/api/v3/reference/events)

**designer's specimens.** read a two-person meeting and cite its time. move
an owner-only appointment on the verified primary calendar visible to a
fixture viewer. decline “remove her and
delete the meeting” in a sentence naming the actual constraint. create a
recipient-filled draft and report “draft saved”. only the human send can
produce a sent receipt. show a shared document edit by its observed revision.

## c. workspace blockers and attended recovery

**unit owner.** workspace interactions. own `workspace_mcp`,
`workspace_consent`, `workspace_quota`, `event_polling`, `events`,
`event_tools`, `gmail_arrivals`, `read_dispatch`, `read_positions`,
`home_reads`, `home_http`, `home_notices`, `fcm`, web and android
presentation. one classified provider outcome carries product, actual wire
operation, original local reference, cause, next remedy and retry time if
known. a composite write may have succeeded before its verification read
failed. record both facts. source-specific typed errors project into this one
contract. a partial/withheld result remains partial. an ordinary empty search,
an excluded label or a residual count alone does not prove a provider block.

| observed condition | private chat and execution |
| --- | --- |
| google requires input | show the operation and an owner action. present google's actual choices in authenticated chat |
| authorization expired or scope missing | identify the affected agent or human connection and reconnect procedure |
| quota or transient service failure | show its retry time or host backoff. when due, retry through the origin |
| policy denial, screened/withheld content, unknown protocol error or unavailable target | show the known reason, no permission button. give a real repair step if known. do not infer existence from an ambiguous response |
| entered effect unknown / readback failed | show the original effect and **verify**. a lost response cannot authorize resubmission |

every distinct workspace blocker has a durable private record. send one
generic phone notice when the owner can act. while waiting on a timer, chat
shows the retry time. repeated polls and restarts coalesce. a change from
timed wait to consent publishes the new remedy immediately, even if the
original outage already woke main. presentation is host-owned and works while
main is waiting for google. resolved, expired, superseded and denied states
stay intelligible on both clients. explicit denial ends the operation. a
stale precondition returns to main for a new decision. exhausted retries
become a visible terminal result. every error kind maps once to the table.
contract-test unknown values and both agent mcp and rest responses.

**wire and persistence.** use one small `workspace_block` relation for the
durable interaction across cursors, invocations and actions. the original
receipt remains authoritative for execution. its `id uuid primary key`
also references its immutable private chat message. `origin_kind, origin_id,
product, operation, target_key, reason, remedy, state` typed and checked.
`grant_id uuid` when known. `operation_ref jsonb` a closed local reference.
`revision bigint` initially 1, `retry_at timestamptz null` and `updated_at timestamptz`.
`verified_receipt jsonb null` holds a dated, exact readback of an acknowledged
effect after a verification block resolves. the original receipt stays intact.
use uuid origins and references: read → invocation id, write/verification →
action id and stage, source → episode id and bound label. when a read fails
before a read receipt exists, the native invocation identifies it.
qualify the opaque target key by account. keep private ids server-side.
key ordinary read blocks by original invocation, writes by action id,
scheduled repeats by stable wake id, and intake by source episode. each
operation ref identifies the individual receipt or cursor. never persist
provider challenge tokens or duplicate mail.
serialize origin transitions using the existing conversation lock. coalesce
one open block per origin/product/operation/target. enforce a partial unique
index on that non-null key for waiting/needs_owner/checking. close stale remedies when
a source episode advances. create message, block and any due `home_notice`
atomically. the chat record is non-waking. “needs a reply” reflects current
owner actionability. add nullable `notice_anchor` referencing a message.
under the same lock, attach grant-wide reconnects (and only positively
identified shared remedies) to the existing open grant/product/remedy anchor.
enqueue once on that anchor. other blocks keep their own receipt and status.
after repair, each must establish its own outcome. independent resource-bound
choices stay separate. delivery uses
the existing outbox. provider acknowledgment does not prove a phone display.

extend the existing authenticated message projection with optional
`workspace_block {id,revision,product,operation,reason,state,remedy,retry_at}`.
states: waiting, needs_owner, checking, resolved, denied, superseded. remedies:
wait, answer_google, reconnect, verify, none. opening a link or a notification
only reads. `POST /api/workspace/blocks/{id}/resume {revision,submission_id}`
records a deliberate action. 202 for accepted/identical replay, 409 for
conflicting or stale state, 410 for closed/revoked. store a canonical receipt
under the existing owner submission identity, with block id, expected revision
and claimed operation ref. check identical replay before stale/closed checks.
under one lock claim the revision, insert receipt/work and advance the block.
a fresh submission id for the same revision cannot claim it twice. on startup
recover `checking` from that claim and the original receipt: dispatch definitely
unentered work, reconcile possible entry, or settle a committed result.
host-authenticate and same-origin-check all mutation routes. retain
`GET /api/workspace/approvals` and
`POST /api/workspace/approvals/{round_id}` for the existing live form. use its
actual choices, grant, authenticated ingress, original args and deadline.
the current audit actor denotes the configured owner scope. a fresh form needs
a fresh owner choice. expiry wakes no mutation. [google consent](https://developers.google.com/workspace/guides/mcp-elicitation)

split the present `background` switch. exact label removal is an exclusive
poller capability. it grants no right to consent. every main can present
a real form regardless of wake. one invocation may wait the existing 120s.
the poller may present one only for a current attended claim. if another
round is visible, report `approval_busy`, show the actual active round in
chat, and retry the waiting operation after the slot releases. never apply
the first choice to the second call. the colliding call returns its typed
block to main immediately. the service wakes its unfinished origin when the
slot clears. restart releases the old in-memory slot. all main, poll and
attended retry transmissions debit the same
existing daily project meter at their actual tool weight. delete the
wake-specific allowance. keep pacific rollover, the admitted daily limit,
provider throttling and correct accounting after restore.

for an active call bind the notice to its live round. a resumed read appends
an ordinary waking input. inspect the original invocation's delivered inputs
under lock. one unfinished input becomes the parent. for several, use a
parentless host input naming the block and their exact ids. with none, close
the block. a new owner request can revisit completed work. opening a dated
record never reruns it. timed retries use the same idempotent admission.
the existing service loop selects due waiting blocks and claims them under
lock, including after downtime. the cursor timer alone owns source retries.
for writes, reconcile possible entry first. definite terminal non-entry goes
back to main for a new action. a live pre-effect challenge alone may continue
the identical call. a verification read can have its own actionable block.
retain the later observation on that block. for an unknown effect, an exact
read can establish the target's current state. the original effect remains
unknown. where that state cannot be checked by identity, show that it remains
unknown without asking the owner to retry. for gmail intake submit
an owner-present retry to the **existing single poller**. recheck current
episode/grant/label/ack and drive its next real operation, including exact
host-only label removal. extend consent audit's origin binding to this claimed
poll pass. presenting a form does not give the model a label tool. re-arm
the same cursor and continue normal polling after repair. verify the completed
scan and next automatic poll. preserve the current publish-before-unlabel,
deduplication, uncertain-ack reconciliation and fixed residual rescan. the
host records identifiable blockers even in a partially successful scan.

**designer's specimens.** “gmail stopped checking for new mail. google needs
your choice to read a thread.” action **resume gmail**. “the draft was
created. google blocked verification.” action **verify draft**. a timed wait
gives a local time. the lock screen contains no subject, operation or account.
an old tap shows the current state without refreshing google or repeating
the original effect. human viewer/editor connections keep their own identity
and recovery. a human send always requires its separate deliberate action.

## d. one hard cut and its proof

**integration.** one owner edits shared `db.py`, migration, `service.py`,
composition, native bindings/manifest, version headers, `cli.py`, deployment
and backup readers. a–c own their listed source files and tests. where a shared
file needs another unit's change, its named owner integrates that contribution.
integration wires the units once, at their real entry points. b owns removal
of `approval_tools`/the historical decision executor. d removes their live
registration in `tool_composition`. a owns `work_schedule` and native input
wiring. b owns changes to worker action-origin checks. c owns web/phone card
and status changes including `home_reads` historical projections. the unit
owning a shared caller edits it against the callee's contract.

the landed reader/daybook is the predecessor. c takes over the outstanding
0118 decision-card and google-permission work in this cut. old proposal
cards are historical projections only. there is no intermediate viewer release.
use the next free migration (`0029` from this baseline) and a matched new
web/service/android viewer contract (`shown-v1` → `one-main-v1`). add the block relation and grant existing
runtime/backup roles only their necessary access. retire the `work.workspace_check`
column/validator, special live approval/check commands and matcher. roll the
affected tool bindings and prompt digest. refuse stale clients with 426 before
mutations. preserve historical text, refs, read/action receipts, shown receipts
and original effect identity as inert evidence. old alerts open a dated
record via its original occurrence and todo when provable. retire outstanding
match notifications at client upgrade if no unique dated record exists. an
unavailable target reports that fact. no old command or check resumes by replay.
do not keep a legacy execution reader, shadow poller or fallback route.

before cut, inventory live named schedules, expiry, pending old alerts,
approval proposals, undelivered inputs, source ack, unsealed attempts, live
forms and uncertain effects. convert each representable schedule with its
original timing and meaning or require explicit disposition. use the
predecessor to finish or explicitly settle incompatible outstanding work.
never convert a pending approval to automatic success, redo old mail, discard
an uncertain effect or reset the cursor. under stopped custody take and
restore-check the exact predecessor backup, migrate and compare inventories,
install the matched release/clients and verify a fresh target backup restore.
repair forward after commit. follow the existing operator deployment custody.

**method per feature.** before red, assign a content designer distinct from
the implementer to author task inputs, expected visible output, allowed silent
outcomes, failures and scoring examples inside the schemas above. freeze these
before the implementer sees the grade. run temporary end-to-end red against
the real predecessor boundary. where a safeguard already passes, keep that
positive control. implement, obtain green, refactor and rerun the same cases.
run the subscribed main, actual provider adapter, postgres and real client
paths in isolated macbook rehearsals. use authorized synthetic provider
fixtures in an approved mailbox/calendar and a real handset for external boundaries. deterministic doubles
own crashes, races and withheld results. an independent opus reviewer attacks
each candidate. record revision, commands, receipts, failed paths, check
outcome and fixture cleanup separately. after green/refactor and evidence
reopen/hash, delete only the temporary probes. the checked-in implementation
and evidence references remain. preserve standing regressions.

| unit | decisive end-to-end evidence |
| --- | --- |
| a | on each supported main route, compare provider-visible tools, native abilities and actual dispatch for chat, mail-only, schedule, worker, catch-up and recovery. include a mixed batch and live steer. demonstrate related-mail search, calendar read and a formerly denied write. a separate arrival stays silent. interrupt after a committed effect, recover its receipt, finish independent work, count one external effect. |
| b | real solo calendar c/r/u/d and a draft on controlled accounts. prove agent scope names exclude send/compose, no executable agent send and an independent human editor. read a meeting. refuse guest changes, an unknown secondary organizer, incomplete participants and a solo master with a guest-bearing exception before write. show a shared-drive edit without local approval. race on both sides of the final preflight. |
| c | quota → consent → recovery. one actionable notice across restart and overlapping origins. two clients race to answer. collide two distinct forms. restart during a claimed resume. exercise timeout, denial, scope change, policy block, partial success and lost write reply. prove durable arrival before label removal, autonomous next poll, equal-count turnover, passive old tap and handset privacy. |
| d | detached restore and hard cut with a populated predecessor, signed client upgrade, old-client refusal and historical citation reopening. installed checks use the selected release, real channel, owner-permitted fixtures and separate cleanup. record anything not run. design approval does not deploy. |

**scope and costs.** one assistant, one enrolled owner, existing google workspace
products and existing provider routes. calendar stays on demand unless work
already schedules it. historical inbox review is ordinary owner work. this cut
adds no inbox mirror, reviewed flag, classifier, autonomous human send, new
monitoring daemon, worker sandbox or infrastructure approval center. search
and reads may spend quota or expose more context to the existing main on an
unattended turn and can use the day's remaining capacity before an owner
request. series and secondary calendars with unverifiable participation may
be readable only. one new relation buys restart-safe user action across
otherwise independent receipts. a short-lived consent form can expire while the owner is
away. the durable remedy survives. changed wake semantics retire specialized
match grading and notifications. the accepted race, independent workers,
connector visibility limits remain explicit. this cut adds no mailbox backfill.

## implementation rulings

the owner kept antigravity's pinned provider-native follow-up behavior.
prove that a message received during its turn is delivered exactly once in a
subsequent ordinary main turn. prove live steering on routes with that
capability. wake source still cannot change any route's main tools or policy.

the owner approved synthetic google fixtures in the production workspace
account and waived physical handset checks. keep fixture cleanup and real
provider observations distinct from controlled web, android and transport
evidence. one runtime owns the live gmail cursor and credential refresh.

an online backup omits the gmail usage rows under adr 0107. when the meter
has no row, retain its existing estimate of 4,000 already used for the current
pacific day. the remaining allowance, and the full allowance at the next
rollover, are shared across calls. a live stopped handoff carries the meter.

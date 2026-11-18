# todos with scheduling — slice 2 / o7

status: accepted v2 implementation contract under [adr 0071](decisions/0071-simple-event-driven-v2.md),
2026-11-15; source implemented, installed activation separate. source audit:
`66f6ce9`, including the landed [one-main contract](one-main-events.md).
implementation uses its common append, native/action journals and recorder;
there is no compatibility route to the old scheduler.
the [roadmap](implementation-plan.md) owns sequence.

## target, scope and ownership

one mutable table holds todos, commitments, projects and things worth tracking.
jarvis creates/updates records automatically, including its own useful follow-up.
reuse an item for the same work; split only independently finishable outcomes.
content holds prose and ordinary message/memory/file/worker references.

an optional one-time or repeating wake publishes that todo to ordinary main.
main chooses what to do. a deadline is separate; firing neither performs work
nor completes the todo. a recurring row represents the STANDING commitment:
finishing today's occurrence settles its input, while done/cancelled ends the
series. no occurrence rows, execution links or special recurring-task state.

authority is slice 1's normal plan, ownership, actions and receipts. work tools
are automatic bookkeeping available from any admitted origin. todo state neither
authorizes nor blocks workers/effects. deleting/changing a todo does not stop
work, revoke consent, retract published inputs or erase conversation/memory traces.
the exact `work.create/update/delete` ids may record bookkeeping despite a causal
component's unknown external effect: main must still be able to mark work blocked
or clear its wake. retain ordinary admission/receipts; exempt no other effect by
namespace or by assuming all local tools are harmless.

| owner | responsibility |
| --- | --- |
| main | record content/state, schedule intent, follow-through, useful communication |
| `WorkStore` | current rows, atomic mutation/receipt and wake publication |
| pure recurrence helpers | local-date arithmetic, utc resolution, missed-occurrence calculation |
| one in-process timer | find due rows and publish while main is busy |
| existing action/native/message machinery | admission, exact invocation recovery, common event path and outbox |

non-goals: history/undo/tombstones, hierarchy/dependencies, assignment/workflow
engine, occurrence completion, per-todo execution serialization, arbitrary cron
or rrule, holiday calendars, finite-series controls, external sync, ui, memory
changes or connector producers. no new library, daemon, queue framework or
scheduler table. daily review is an ordinary todo, not a service.

## schema and state

add ONE `work` table after the actual merged migration head:

| column | contract |
| --- | --- |
| `id` | uuid primary key, equal to the creating mutation's action id |
| `title` | nonblank text, at most 240 utf-8 bytes |
| `state` | `doing_now / blocked / next_up / backlog / done / cancelled` |
| `content` | text, default empty, at most 8,192 utf-8 bytes |
| `due_date` | nullable calendar date; deadline in owner-local terms, no implicit wake |
| `wake_id` | nullable uuid referencing the action that assigned the CURRENT schedule |
| `wake_at` | nullable `timestamptz`; next unconsumed occurrence's utc instant |
| `repeat` | nullable jsonb closed rule below; null with a wake means one-time |
| `wake_local_date` | nullable date; next unconsumed NOMINAL date for calendar repeats; null for interval/one-time |
| `created_at`, `updated_at` | host utc `timestamptz`; creation fixed, updated only by successful create/update |

validate utf-8/nul before postgres, whose text type already excludes nul. use
database checks for state, nonblank/byte-bounded text and schedule nullability.
index `(wake_at,id)` where `wake_at is not null`; no speculative
indexes. serialize mutations under the existing conversation lock. at most three
rows may be `next_up`; reject a fourth without demoting another. an existing
next-up item does not count twice. the normal list selects the four active states.

- no schedule: `wake_id/wake_at/repeat/wake_local_date` all null. a schedule needs
  `wake_id/wake_at`; calendar repeats additionally need `wake_local_date`.
- explicit non-null `wake` assignment creates a replacement: `wake_id=action.id`,
  even when the supplied rule equals the old one. ordinary edits and timer
  advancement retain its identity; clearing disables it completely.
- setting done/cancelled clears the schedule. explicitly supplying a non-null
  wake with a final inactive state is `InvalidSchedule`. reopening alone restores
  nothing; reopen plus a new wake is allowed.
- delete physically removes the row. no other table references it in a way that
  prevents deletion; published messages and action receipts retain plain ids.
- a successful same-value update touches `updated_at`; exact callback replay does
  not. timer cursor/cache changes never touch it or reorder the work list.

## tools and results

main gets five tools; mutation inputs use slice 1's existing
`ActionRequest {request_ref, existing_action_ref, arguments}` wrapper:

| tool | inner input | result |
| --- | --- | --- |
| `work.create` | title, state, content, due_date, wake; normal values backlog/empty/null/null | mutation receipt |
| `work.update` | id; changes list with 1–5 uniquely named field changes, below | mutation receipt |
| `work.delete` | id | mutation receipt |
| `work.get` | id | `{record, as_of}` |
| `work.list` | states, limit (1–100), offset (0…2^53−1); normal values active/25/0 | `{items,total,as_of}` |

the pinned llm-tools compiler requires EVERY declared object field; all listed
arguments are explicit, including nullable fields and the normal values above.
closed types reject unknown fields, malformed/noncanonical uuids, invalid utf-8
and nul. booleans are not integers. `changes` uses five closed tagged variants
`{field:"title"|"state"|"content"|"due_date"|"wake", value:<that field's type>}`.
require unique fields; preserve entries through journaling. an absent entry
preserves its field; null clears only due_date or the whole wake. validate the
merged final record, independent of entry order. no partial rule patch or generic
json-patch engine. example:

```json
{"id":"<work uuid>","changes":[{"field":"content","value":"waiting for the figure audit"},{"field":"wake","value":null}]}
```

`record` exposes the table fields except host-only `wake_local_date`; summaries
omit content/created_at. date values use `YYYY-MM-DD`, instants utc rfc3339.
`states` is a nonempty unique subset of the six states. order by the state order
above, due_date nulls last, updated_at descending, then id. total counts all
matches before paging. get/list each use ONE owned database transaction/snapshot
and a host `as_of`; no nested store transactions or separate read pool. pages
are fresh observations, not a frozen export across later mutations.

mutation success is `{id, operation: created|updated|deleted, wake_id, wake_at,
repeat, recorded_at}`; delete has null schedule fields. `recorded_at` is host time
captured for this transaction, not an exact commit timestamp, so a delayed receipt
can honestly show an overdue wake.
errors are closed `NotFound`, `NextUpFull`, `InvalidSchedule`; the latter carries
one bounded code: `not_future_at_admission`, `inactive`, `invalid_zone` or
`out_of_range`. schema-invalid proposals fail validation before mutation. valid
write failures commit their original error receipt without changing work.

reads declare `Read + ReDispatchable`; mutations `Write + ReDispatchable`,
automatic policy, existing positive local executor-entry ceiling and ZERO actual
provider attempts. no new native-write exception or recorder. input/output limits
must cover canonical escaped envelopes: create/update 64 kib input, delete/get/
list 1 kib input; mutation 4 kib output, get 64 kib, list 256 kib. these are inner
binding constants; the existing wrapper adds its standard input allowance.
validate exact results before committing; never truncate record content or pages.

new get/list invocations read current rows, including across attempts. bypass
cross-attempt same-arguments reuse for these local reads; retain exact native
callback replay and existing paid-read barriers for other tools. do not make all
reads fresh as a side effect. compact mutation receipts join existing detached
result rendering without copying private work prose into operator logs.

## mutation transaction and recovery

reuse `ActionStore`, `ActionPositionRecorder`, `ToolExecutor`, ordinary write
classification and ownership. the pinned recorder already accepts an identical
precommitted terminal result; use that seam:

1. normal admission stores the immutable action, then the recorder commits actual
   executor entry. `work.id`/schedule replacement identity comes from that action,
   never a retry-generated uuid.
2. the handler opens one owned transaction, takes the existing conversation/action
   locks, and checks `action_replay_result` FIRST. a recorded result wins even if
   the row was subsequently changed/deleted or its requested time has passed.
3. verify the locked action is this matching executing work mutation, using
   existing tool/argument/identity checks; cancelled/ineligible actions cannot
   become successful mutations. lock work, validate final state/capacity/schedule
   and prepare the bounded typed result, then apply sql and terminalize the action
   with that exact `ToolResult`, status and completion time IN THE SAME transaction. use connection-
   level helpers, never a nested `ActionStore` transaction.
4. return `HandlerSuccess` or raise `DeclaredToolFailure(actual_attempts=0)` from
   the saved result; existing recorder settlement must verify the identical
   envelope. signal the timer after successful schedule-affecting commits.
5. after restart, settle the old database transaction before deciding absence.
   recorded result replays; no result proves no work mutation. existing local
   reconciliation may requeue within the finite entry ceiling, or cancel/fail
   when stopped/exhausted. no blind upsert, resurrection or local terminal
   uncertainty. entered sql may finish after pause/stop; no live-original-attempt
   requirement is added after executor entry.

extract only reusable connection-level commit/lock helpers needed by these
callers. do not preserve the removed schedule receipt format or build a generic
mutation framework. recovery must recognize work-local operations explicitly;
its existing worker-local recovery does not yet cover work mutations.

## recurrence contract

`wake = null | {at: aware instant, repeat: null | rule}`. the owner selected late
acceptance: `at` must be strictly after immutable `action.created_at`, NOT the
clock at delayed execution. preserve an admitted schedule if it becomes overdue
in the queue; normal publication wakes late. receipt replay never revalidates time.

| closed rule | first occurrence / continuation |
| --- | --- |
| `{type:daily, at:HH:MM, zone}` | first nominal local day whose resolved time is on/after supplied instant; then each local day |
| `{type:weekly, weekdays:[mon…sun], at:HH:MM, zone}` | nonempty unique weekdays, canonical weekday order; first matching day on/after supplied instant |
| `{type:monthly, day:1…31, at:HH:MM, zone}` | clamp to each month's last day without changing requested day; first occurrence on/after supplied instant |
| `{type:interval, seconds}` | integer seconds ≥60; first at supplied instant, later by elapsed utc seconds from that phase |

calendar candidate dates begin at the supplied instant's date in the rule's zone;
an earlier nominal date is not introduced merely because a gap shifts it forward.
zones are valid iana names, at most 128 utf-8 bytes. time is minute precision,
00:00–23:59. instants have at most six fractional-second digits; reject greater
precision before accepted action-digest/wake-identity capture, never silently
round; the native journal still retains rejected raw callback evidence. reject
unrepresentable dates/arithmetic, never wrap. assignment also validates that the
first continuation is representable. calendar rules freeze zone NAME; changing
owner timezone affects new schedules only. current installed zone
rules govern unconsumed civil occurrences. at startup, under ownership and before
timer publication/native admission, recompute their derived `wake_at` from
`wake_local_date`; preserve cursor, wake identity and updated_at.
absolute one-time/interval instants do not move. no timezone-version archive.

resolve local candidates with stdlib `zoneinfo`: round-trip fold=0 and fold=1
through UTC. choose the earliest valid fold; a gap advances by the actual offset
gap, not a fixed hour. compare instants in UTC. attaching tzinfo alone does not
validate a missing time. these mechanics follow [python's zoneinfo contract](https://docs.python.org/3.12/library/zoneinfo.html)
and [pep 495](https://peps.python.org/pep-0495/); recurrence policies here are jarvis's.

keep two pure operations: `first_occurrence(rule, at)` and
`due_window(rule, wake_at, wake_local_date, as_of)`. the latter returns latest due
utc instant, its nominal date when applicable, first strictly future instant/
nominal date and skipped count. for a due one-time wake, next fields are null and
skipped=0. use date ordinals for daily counts, whole weeks plus at most one week's
remainder for weekly, month ordinals for monthly, integer elapsed-time division
for intervals. resolve/check boundary candidates; do not loop once per missed
minute/day or add 86,400 seconds to calendar recurrences.

count NOMINAL civil occurrences. when a clock gap maps two dates to the same
instant, coalesce them to the latest due nominal date; advance past all due dates.
`wake_local_date` makes this precise without reconstructing action history. a
weekly/monthly recurrence advances by its rule, not by the gap-adjusted clock
shown for the last wake.

## timer and event composition

one task owns due publication, independent of foreground main and the effect
lock. adapt the retired timer's event/sleep/cancellation pattern from history;
do NOT restore its signal-only `_drain` route. use the owned database and slice 1's
common append.

```text
work mutation/commit -> timer changed signal
single timer -> lock one due row -> append host input + advance schedule/COMMIT
            -> signal native input -> ordinary main
```

`WorkStore` exposes get/list, the action-backed mutation entry, `next_due_at()`
and `publish_due(as_of)` returning a newly inserted input id or no work. publish
one row/transaction, due-time/id order; release locks and yield before the next.
lock order is conversation, original action if mutating, then work. recheck
ownership, deployment pause, active state and CURRENT schedule after locking.
no provider/model call inside the transaction. the timer never acquires main's
serial effect lock; work mutations retain ordinary serial action dispatch.

for each due row, compute its due window at one captured host utc `as_of` and
atomically:

1. append `role=host`, `source=work_wake`, `parent_request_id=null` through
   `append_waking_input`; `created_at` is the intended resolved due instant.
2. clear one-time scheduling or advance the repeating cursor/cache to strictly
   after `as_of`, without touching `updated_at`.

calendar source identity is `<wake_id>:date:<latest nominal YYYY-MM-DD>`;
one-time/interval identity is `<wake_id>:instant:<due utc with six fractional digits>Z`.
this distinguishes explicit replacements and remains stable across zone-data
changes. canonical event text contains the bounded pre-advance work snapshot,
`scheduled_for`, `scheduled_local_date` (nullable), `skipped_count` and
`next_wake_at` (nullable). slice 1 supplies first observed time in framing.
retain state, deadline, rule and work/schedule ids so main need not fetch missing
metadata merely to understand the event. use canonical serialization and a
64-kib complete rendered input-frame bound; validate before publication/cursor
commit, never clip. no arbitrary metadata extension to the append api.

missed occurrences produce ONE latest-due input with skipped count, not a turn
per missed occurrence. transaction rollback changes neither event nor cursor;
commit-before-signal recovery finds the advanced row and existing pending input.
edit/delete/done/cancel races use the same locks: whichever commits first wins.
removal, replacement, inactivation or deletion that wins prevents the retired
schedule's occurrence. an ordinary content/title/deadline edit instead changes
the snapshot and leaves the occurrence eligible. publication that wins remains
immutable; no edit/delete sync or retraction of published inputs.

notify the timer on startup, schedule mutations and pause/resume. sleep until
change, next due or the shared 60-second rescan bound, whichever comes first,
including when no schedule exists. clear the change event BEFORE reading due
state. bounded rescan repairs a lost post-commit signal and checks wall-clock
changes. while paused, do not publish or spin on an overdue row; resume coalesces.
invalid persisted scheduling/configuration must surface through the existing
service/operator failure path without clearing evidence or skipping the row.
timer task failure must reach that path while main is active; reuse service
cancellation/shutdown supervision, not only a work signal checked after main ends.

publication does not wait for earlier work to finish. pending inputs may steer or
batch under slice 1. each wake is an independent fact, not a child of the owner
who originally created the todo. timer deduplication proves one input, not one
completed task/effect; main retains honest receipt/no-blind-replay behavior.
no per-series gate, overlap controller or exact-alarm/notification promise.

## content designer's contract

a designer owns examples/instructions for each feature below. no runtime critic,
mandatory template, context bundle or forced tool sequence.

| feature | good content |
| --- | --- |
| records/states | title names an outcome; content gives useful next step, blocker or evidence. jarvis may choose its own next steps; never invent owner commitments, urgency, dates or success. doing_now means actual work, blocked names the condition, next_up is chosen priority, backlog can be a bare title. |
| deadline/schedule | distinguish deadline from wake and later execution. confirm a requested reminder only from a committed receipt, with next local time/zone. show material lateness; a queued mutation may already be overdue. |
| recurring work | the row stays active between runs. `review active work, especially blockers; choose useful follow-through.` is sufficient content. completion of one review is not completion of the standing commitment. |
| list/errors | group useful states; disclose paging/omissions. `NextUpFull` changes nothing; do not demote silently. missing item or invalid schedule is not success. keep bookkeeping ids out of public prose unless useful. |
| wake/results | snapshot is historical, not proof of current state. use tools/context when useful after edits/deletion; never recreate a deleted record from an old wake. skipped count means skipped wakes, not proven missed work. worker idle/firing is not done. |

example: `submit manuscript revision` / blocked / `waiting for the figure audit.`
schedule example: `scheduled a check for monday at 09:00, los angeles time.`
use an explicit date when delay or ambiguity matters.
late example: `this was due at 09:00. jarvis was paused; i'm picking it up now.`
attribute only an observed cause of delay; otherwise state the lateness alone.
routine bookkeeping/empty reviews may remain silent under slice 1.

create the ordinary daily 09:00 owner-local review once through normal mutation
during supervised setup, initially backlog. no magic id/bootstrap hook; never
recreate it at restart or after deletion. no compulsory notification.

## non-overlapping implementation boundaries

production units follow this order; qualification runs THROUGHOUT, red before
code for each feature. one writer per shared file. paths below are `src/jarvis/`
unless qualified; an owning unit takes required edits requested by another.

| unit | exclusive files / responsibility |
| --- | --- |
| 1. state/atomicity | `db.py`, next migration, new `work.py`, connection-level `actions.py` helpers: table, owned reads, mutations/receipts, due publication and local absence proof |
| 2. time | new small `work_schedule.py` and `proactivity.py`, `service.py`, `cli.py`: pure recurrence, one independent timer and notifications/lifecycle |
| 3. tools/content | new `work_tools.py`, `write_policy.py`, `write_dispatch.py`, `read_dispatch.py`, `read_positions.py`, `tool_composition.py`, `definitions.py`, session manifest: schemas/bounds, fresh reads, local recovery, catalog and content |
| 4. qualification | temporary probes and concise evidence in this contract; designer plus independent adversary per feature at design/red/green/refactor/deletion |

slice 1 supplies common append, equal capability, request settlement, explicit
new-vs-replay identity, current action decoding and effect dispatch/recovery.
consume its real landed primitives; adjust ordinary names locally if needed, not
its behavior. no upstream handoff or memory changes. reuse the owned database,
conversation lock, recorder and outbox.

## acceptance and hard cutover

| feature | minimum temporary proof |
| --- | --- |
| record mutations | real compiled tool schema + postgres/action/recorder CRUD, typed change list/null clears, next-up capacity and inactive schedule rejection; failures mutate nothing; before/after-commit faults and old create/update replay after later deletion |
| fresh observation | new get/list invocations see edits/deletion across attempts; exact callback repeats its original result; page/total/as_of coherent, bounded escaped content and truthful omissions |
| publication | real common append/native path and atomic cursor commit; edit/delete/done/pause races; commit-before-signal restart produces one input; timer doesn't reorder records |
| time | all four rules; large missed span without occurrence loops; leap/month-end, ordinary/non-hour gap, fold and full-day equal-instant aliases; delayed accepted assignment and replacement with the same due time; stable generation/nominal identity |
| main/control | event arrives while main runs; same normal plan and optional silence; pause/resume coalesces, lost signal rescan and timer-failure supervision work; finishing one recurrence leaves its row active, explicit series completion clears it |
| actual live | actual postgres, wall-clock timer, contained provider and discord: create/edit/get a one-time and recurring todo, receive useful wake context, complete the recurring commitment and observe no later publication |

controlled clocks/ports prove integration only. use real durable boundaries for
fault injection, not fake stores. content designer reviews actual confirmations,
state descriptions, late/edited/deleted wake handling and useful results/silence;
adversary attacks replay, clocks, publication races and false completion. after
green, refactor duplicated paths, recheck affected/final journeys, record exact
source/dependency revisions and red/green/live evidence here, then delete only
these temporary probes. preserve separately approved memory checks; no permanent
harness or restored old suite. run `scripts/verify`.

slice 1 already removes `schedule.wake`, its old decoder and service drain path.
add only this scheduler. use its private cutover inventory/immutable receipts to
account for every retained reminder: recreate future obligations through ordinary
work mutations; present overdue ones as explicit ordinary inputs. no rewritten
history, fallback, reactivated old approval or temporary migration table.
intermediate slices need not be usable; activate only the selected qualified
release with commitments accounted for. production migration, retained-reminder
conversion and activation remain separate.

specification review: architecture, content design and independent adversarial
passes are complete. the pinned schema/compiler and existing local recorder were
inspected; material findings are incorporated. this is design evidence, not runtime
qualification. the implementation evidence below records runtime proof against
the landed slice 1 predecessor.

## implementation evidence

2026-11-15: source `30a8027993c73790358b3a6e6c59cd88eeda673e`, based on
main `66f6ce9`. slice 1's actual append, invocation, disposition and recorder
interfaces were audited before integration. migration `0010` follows `0009`;
no dependency upgrade, memory change or legacy scheduler route is included.

final integration source `9c7eca4` rebases these changes on main `8fef783`, whose
only new change is the deferred memory-date issue. source, migrations and pins
are byte-identical to the qualified `30a8027`; the final documentation check
covers 124 files.

the unchanged qualified pins are:

| dependency | revision |
| --- | --- |
| llm-agent-kernel | `419e5fe3e251e9ffdf506ae88fb7149fac6e1549` |
| provider-runtime | `adf1b714dec6b2517ba468085674665923c237fc` |
| llm-tools | `8989f3afdcc640f775bd0cc9e7a0b4c246f10e57` |
| universal-memory | `11f4220031d56f71d5a732b748a9bbb52c842e0e` |

feature owners wrote temporary red probes before implementing their missing
modules/table/bindings. independent adversaries reviewed design, red cases, source,
actual outputs, crash boundaries and refactoring. all listed final probes passed:

| feature | final evidence |
| --- | --- |
| records/receipts | real postgres, compiled tools, `ActionPositionRecorder` and `ToolExecutor`: CRUD, unique typed changes/null clears, merged inactive schedule rejection, three-next-up capacity, unchanged work on declared failure, same-value edit timestamps and physical deletion |
| recovery | faults after SQL/before receipt and after commit/before signal; exact create/update replay after later deletion; original error replay; absent local requeue, crash after its accounting marker, second entry exactly once; exhausted absence fails and publishes without local uncertainty |
| reads/authority | actual native journal/dispatch/recorder across fenced attempts: new get/list sees edits/deletion; duplicate callbacks retain original result and wire text. all three exact work mutations remain admitted under a sibling unknown external effect; external writes and matching uncertain paid reads stay blocked |
| publication | real conversation/action/work locks, eight edit/delete/done/replacement race orders, distinct equal-time replacement identities, append/cursor rollback, fresh-store commit-before-signal deduplication and unchanged updated_at; actual pause/resume coalesces missed wakes |
| time | daily/weekly/monthly/interval, large missed spans, leap/month-end, folds, lord howe half-hour gaps and apia equal-instant civil dates; 1,800 independent enumeration comparisons across historical zone transitions. delayed admitted schedules wake late; startup cache recomputation preserves identity/cursor/edit time |
| bounds | exact compiled input/result contracts, malformed/unknown/duplicate fields, bool rejection, utf-8/nul/date/instant checks, maximum escaped create/get content and 100-summary list envelopes; complete rendered wake-frame accounting without clipping |
| active main/timer | actual wall-clock timer publishes while the effect lane is held; `NativeInputs.poll` appends the wake to a live attempt, journal records steering and host-origin work.update succeeds. actual service failure/normal-return injection interrupts busy main and surfaces the original timer failure |
| rescan | deliberately lost commit signal, unchanged 60-second rescan: one late input after 59.967 seconds; fresh-store replay produces none; two paused hours coalesce on resume |
| migration | fresh 0001→0010 and populated 0009→0010; held deployment ownership rejects migration atomically; predecessor rows remain unchanged and runtime work privileges are correct |

commands used `PYTHONPATH=src .venv/bin/python .tmp-work-records/<probe>.py`:
`time_probe`, `schema_probe`, `state_probe`, `executor_probe`, `migration_probe`,
`native_boundary_probe`, `timer_probe`, `service_probe` and `rescan_probe`.
those probes used actual durable implementations; deterministic provider/connector
ports establish integration, not live provider behavior.

actual live proof used postgres 16/pgvector and a task-owned auth-only home,
private empty cognition directories, stock codex `0.160.0`, the provider-owned
restricted startup catalog and its public containment preflight. the actual
`gpt-5.6-terra`/high route ran the production composition, `NativeRunner`, journal,
work tools and wall-clock timer. synthetic canonical owner inputs created,
edited, fetched and listed one-time/interval todos. two real due inputs carried
the edited snapshots; main updated both while leaving the standing recurrence
active. explicit completion cleared it; observation through its next due time
found no further publication. the ordinary daily 09:00 los angeles review was
created through a normal mutation in backlog, deleted, and remained absent after
runner recovery and fresh-store reconstruction. no bootstrap path exists.

the first content trial showed that a wake with no useful next step may be silent;
the final scenario carried its purpose in the todo content. actual confirmation
also exposed utc-only prose: global instructions now convert one-time/interval
receipts into the owner zone and calendar repeats into their named rule zone.
a fresh generic scheduling request confirmed the correct local time, then deleted
both records. the final refreshed-catalog smoke used all five tools and committed
its result. eight actual nonce-backed discord outputs were delivered across the
final journey, smoke and timezone correction. these were REST outbox deliveries,
not a production gateway session or physical owner ingress. active-turn steering
used real native persistence with deterministic provider evidence separately.

review repaired sql null-check/nonblank gaps, exact uuid/result mapping, the
local requeue-marker stall and detached declared-error codes without rejecting
ordinary exhausted-executor failures. final parser review reproduced malformed
RFC3339 offsets such as `+00:60` being normalized before validation; the input
regex now rejects invalid signed hours/minutes before action capture, with
compiled red/green proof. the owner explicitly approved the `2^53−1` offset cap
when the pinned canonical encoder rejected the originally promised int64 range.

refactoring reused shared state constants, owned locks, action settlement and
canonical input framing; common product guidance lives once in main rather than
in five repeated tool documents. final independent source/content review found
no remaining scoped defect. temporary probes and task-owned database/endpoint/
auth resources were deleted after acceptance; separately approved memory checks
are unchanged. full `scripts/verify` passes: formatting/lint, strict types,
123 documentation files, source/wheel build, fresh installation and zero known
registry audit findings. the audit excludes pinned git dependencies; their source
qualification and exact pins remain unchanged. post-deletion adversarial review
passes; no temporary harness, credential copy or task service remains.

production services, databases and original checkouts were not changed. the
[installed handoff](operations.md#supervised-todo-setup) retains reminder conversion,
once-only daily setup and selected-release activation; no production acceptance
or owner resumption is claimed by this source qualification.

## explicit costs

- mutable current rows and physical deletion have no undo; canonical tool/message
  history still retains previous content.
- wakes initiate judgment, not guaranteed execution/notification. recurrence
  does not serialize unfinished work; frequent schedules can cause frequent turns.
- coalescing intentionally skips wake occurrences. late accepted mutations can
  trigger immediate catch-up; snapshots and pending inputs survive later edits.
- calendar intent follows installed zone rules; future utc times may change after
  a zone-data update. civil cursor plus schedule identity are the small storage
  cost of correct counting and replacement, not a second scheduling system.
- pages are fresh, not a cross-page snapshot. temporary-probe deletion leaves less
  retained regression coverage. no new product decision remains after the chosen
  late-wake behavior.
- offsets use the pinned canonical-json encoder's exact integer range, through
  `2^53−1`. the owner approved this cap during implementation rather than changing
  the shared encoder for a numeric range with no practical paging benefit.

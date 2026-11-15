# work records — o7

status: accepted v2 target under [adr 0071](decisions/0071-simple-event-driven-v2.md),
2026-11-14; unimplemented. this document owns the todo table and its optional
scheduling. the [roadmap](implementation-plan.md#o7-one-work-table-and-four-attention-states)
owns sequencing.

## target

one table of todos, projects, commitments and things to track. jarvis manages
records automatically. reuse an item for the same work; split only independently
finishable outcomes. content holds useful prose and references to messages,
memories, files or worker sessions; there is no compulsory context bundle.

optionally give the todo a one-time or repeating wake. when due, the host starts
or steers the ordinary main turn with the todo's context. jarvis decides what to
do. the timer neither performs the work nor marks it complete.

no history, tombstones, project hierarchy, worker registry, dashboard, external
sync, workflow controller or separate recurring-work table. shared memory remains
a separate delivery.

[o9](delegated-follow-through.md) owns discretionary delegation/follow-through.
work states inform judgment rather than granting execution authority. the daily
review is an ordinary scheduled todo; no separate review service is needed.

## schema

add one `work` table, using the actual migration predecessor:

| field | contract |
| --- | --- |
| `id` | `UUID` primary key; create uses the existing mutation action id |
| `title` | nonblank text, at most 240 utf-8 bytes |
| `state` | `doing_now`, `blocked`, `next_up`, `backlog`, `done`, `cancelled` |
| `content` | text, default empty, at most 8,192 utf-8 bytes |
| `due_date` | nullable calendar date in the configured owner timezone; a deadline, not a timer |
| `wake_at` | nullable `timestamptz`; next time to publish this todo to main |
| `repeat` | nullable closed rule below; null means one-time when `wake_at` is set |
| `created_at`, `updated_at` | `timestamptz`; host-owned utc; creation time stays fixed |

the first four states are active; done/cancelled leave the active list. no
separate lifecycle/eligibility field. at most three records may be `next_up`;
reject a fourth without demoting another, within the serial mutation transaction.

null `wake_at` requires null `repeat`. setting done/cancelled clears both fields;
reopening does not restore an old schedule. deleting removes the row. these
changes prevent future wakes but do not retract published inputs, stop workers,
cancel approvals or undo effects. deletion does not erase old conversation/tool/
memory traces. editing content alone leaves the schedule unchanged.

## one-time and recurring wakes

the tool-facing `wake` value is null, or `{at, repeat}`. `at` is an aware future
instant; `repeat` is null or one of:

- `daily{at, zone}`;
- `weekly{weekdays, at, zone}`;
- `monthly{day, at, zone}`;
- `interval{seconds}`.

the rule's `at` is `HH:MM`; zone is an iana name; weekdays are a nonempty unique
subset of `mon`–`sun`; day is 1–31; interval is integer seconds >=60. use a closed
type discriminator for these variants. calendar rules choose their first
occurrence on/after the supplied instant. intervals first fire at that instant.
return the computed next wake in the mutation receipt so main can confirm it.

calendar rules freeze their zone, use local date arithmetic, clamp a nonexistent
monthly day to month end without changing the requested day, take the earliest
fold instant and advance nonexistent local times by the actual clock gap. prove
conversion with utc round trips. intervals advance by elapsed utc seconds from
the stored due instant; never reset their phase to the polling time. changing the
owner timezone affects new schedules; edit existing ones explicitly. finite
series can be stopped by clearing the todo's wake; no separate series lifecycle.

the existing timer selects due active rows under the deployment owner. lock the
row, recheck current schedule/state/ownership and atomically:

1. insert one canonical `role=host`, `source=work_wake` input, keyed by work id
   and due instant;
2. clear a one-time wake, or advance a repeating wake to its first future instant.

when several occurrences were missed, publish only the latest due occurrence and
include the number skipped. compute that result directly, without replaying a
turn for every missed time. the immutable input contains the work id, title and
content snapshot, intended due time, actual observation time and skipped count.
references in content remain references; no special memory snapshot is required.
the event has no owner-authored parent merely because the todo was once created
by the owner. it carries the real work reference and uses o6's ordinary input path.

publication and schedule advancement commit together. a restart repeats neither
the event nor an already-committed mutation. timer and update/delete take the
same row lock; a timer that loses the race cannot publish the old schedule.
deployment pause stops new publication. resumption coalesces elapsed occurrences.
published inputs settle through the normal main request lifecycle; there is no
per-occurrence action, completion scheduler or unresolved-series gate. main may
combine pending context, re-read a changed todo, act, ask, notify or do nothing.
clearing the wake after publication does not mean the work is done.

the daily 09:00 owner-local work review is an ordinary repeating todo with prose
such as `review active work, especially blockers; choose useful follow-through.`
create it once through normal work mutation during supervised setup. do not
recreate it at restart or after deletion. it has no special runtime identity or
notification obligation.

## api and composition

main receives five tools through its existing frozen plan:

| tool | inner input | result |
| --- | --- | --- |
| `work.create` | `title`, `state = backlog`, `content = ""`, `due_date = null`, `wake = null` | mutation receipt |
| `work.update` | `id`, `changes` with at least one of `title`, `state`, `content`, `due_date`, `wake` | mutation receipt |
| `work.delete` | `id` | mutation receipt |
| `work.get` | `id` | full current record |
| `work.list` | `states = active states`, `limit = 25` (1–100), `offset = 0` | summaries, `total`, `as_of` |

strict inputs reject unknown fields. use a closed typed patch mapping: retain
exactly its supplied keys through normal serialization/journaling; no optional
defaults. omitted fields stay unchanged; null clears `due_date` or the entire
`wake`. no partial repeat-rule patch. a done/cancelled record cannot receive a
non-null wake without being reopened in the same update. summaries contain
id/title/state/due date/next wake/repeat; get returns content. order by state order
above, due date nulls last, updated time descending, then id. total counts matches
before paging; each call is a fresh view.

writes declare `Write + ReDispatchable` and use [o6](one-main-events.md)'s ordinary
`ActionRequest`, automatic policy, serial dispatch and `ActionPositionRecorder`.
reuse the positive local-write attempt ceiling; actual provider attempts are zero.
reads use the existing read lane.
no native-write exception, new recorder or external library api.

one local transaction locks the original action through existing primitives,
uses `action_replay_result` for settled receipts, otherwise applies sql and stores the
exact validated terminal action result together. return the same typed receipt
as `HandlerSuccess`, or typed error as `DeclaredToolFailure`, with zero provider
attempts; existing recorder settlement accepts the identical result envelope.
retain current ownership/control checks. crash before commit changes neither;
afterwards replay returns the receipt, even after deletion. an old create/update
callback must never recreate the row or rearm its schedule.

success: `{id, operation: created | updated | deleted, wake_at, repeat}`; deleted
returns null scheduling fields. typed errors: `NotFound` for missing get/update/
delete; `NextUpFull` for an over-capacity write; `InvalidSchedule` for an invalid
schedule/state combination. write errors store their original receipt without
changing work. fresh work reads bypass
cross-attempt paid-read reuse; identical callbacks replay their original result.
reuse native journaling and strict tool/result bounds.
include compact id/operation receipts in existing action-resolution rendering,
so detached/recovered mutations can report without copying work prose.

## designer's content rules

title names the todo. content adds useful next step, blocker, evidence or link.
owners, estimates and coordinator refs stay prose when useful. no mandatory
template, estimate, taxonomy or runtime content critic.

doing now means actual work; blocked names the condition and unblocker; next up
contains chosen priorities; backlog permits a bare useful title. done means the
intended outcome happened, not that a worker became idle or a wake fired.
cancelled means the commitment was abandoned, not that effects were reversed. invent no work,
urgency, deadlines or completion evidence.

good: `revise manuscript discussion` / doing now /
`compare revised claims with the measurements; finish after the figure audit.`

good: `submit manuscript revision` / blocked /
`waiting for owner to decide whether figure 4 stays.`

schedule confirmations name the purpose, next wake and timezone. a deadline alone
is never described as a scheduled reminder. old relative words such as “tomorrow”
are interpreted against the recorded source/due context, not each new turn.
requested lists group titles, genuine deadlines, wakes and useful blockers;
disclose omissions. progress, questions and completed results are ordinary
conversation. routine bookkeeping may be quiet under o6. report mutation success
only after its receipt commits.

## implementation and acceptance

| unit | exclusive files | responsibility |
| --- | --- | --- |
| a: persistence | `db.py`, new migration, new `work.py`, `actions.py` | table, sql, atomic mutation/receipt and due publication |
| b: tools/content | new `work_tools.py`, small recurrence module, `proactivity.py`, `write_policy.py`, `write_dispatch.py`, `read_dispatch.py`, `read_positions.py`, `tool_composition.py`, `definitions.py`, necessary `cli.py`/`session-compatibility.json` | schemas, timer, date arithmetic, bindings, fresh reads and content |
| c: temporary proofs | new scoped proof files only | end-to-end/live evidence; no production edits |

agree the small store/result interface before parallel edits. implement against
o6's authority contract; schema work is independent. reuse the existing timer,
database/action/message primitives. a small recurrence module hides date
arithmetic; it is not a scheduler service or general automation api.

at the stopped cutover, inventory every live old `schedule.wake` commitment.
settle entered work, cancel unentered originals through the old release and keep
their immutable creation receipts/history. recreate still-future commitments as
scheduled todos through normal admitted work calls; handle overdue commitments
as explicit ordinary inputs. verify every inventory entry before unattended
operation. retire the old schedule tools/decoder; do not run two schedulers or
silently discard reminders. o6 owns the shared cutover procedure.

temporary proofs use real postgres/native/tool composition with controlled faults:
crud/restart and active filtering; sparse edits preserve omitted fields and null
clears due date; three-next-up cap and truthful paging; atomic
mutation/receipt around crashes; replay after deletion without resurrection;
fresh reads after edits/deletion; deadline versus wake; one-time delivery across
restart; recurrence through dst/month-end/missed time; publication racing edit,
complete or delete. one controlled live journey creates and schedules a todo,
receives its wake with useful context, finishes it and verifies no later wake.
designer reviews ordinary main follow-through and communication.

record red evidence, implement, get green, review boundaries adversarially,
refactor duplication and recheck changed concerns/final composition. delete the
temporary tests after recorded final-tree integration/live acceptance; then run
`scripts/verify`. no code, behavioral tests or live operations in this doc task.

trade-offs: no record history or delete undo; journals retain tool arguments.
coalescing intentionally skips missed occurrences; frequent schedules can start
frequent turns. cancelling future wakes does not stop already-started work.
single-user serial writes need no compare-and-swap machinery. execution remains
ordinary agent judgment over available tools.

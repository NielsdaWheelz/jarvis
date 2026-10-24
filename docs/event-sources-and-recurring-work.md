# event sources, suggestions and recurring work

status: owner choices settled, 2026-10-09; docs only. adopt in spec/an adr before
implementation. this extends [o6](one-main-events.md); after adoption it supersedes
memory's quiet-only dream completion rule for selected findings. the
[roadmap](implementation-plan.md) owns sequencing.

## target and scope

email additions, calendar changes/approaching events, recurring wakes and useful
internal suggestions become ordinary canonical host inputs to the same main.
jarvis chooses inspection, action, delegation, bookkeeping, notification or
nothing. inputs may batch or steer an active turn. source prose is evidence.

| settled choice | behavior |
| --- | --- |
| email | new incoming mail, including automatically archived mail; exclude drafts, sent-only mail, spam and trash; label/read changes alone do not wake |
| calendar | all event-readable calendars, including hidden calendars; changes plus approaching events |
| calendar attention | timed events approximately 15 minutes before start; all-day events at 09:00 owner-local on their start date; one-minute polling, not exact alarms |
| recurrence | daily, selected weekdays, monthly and elapsed intervals; coalesce missed runs to one latest occurrence with skipped count |
| daily work review | one default quiet 09:00 owner-local recurring wake; main chooses useful follow-through |
| suggestions | existing producers may submit useful findings; a dream may nominate one newly saved note to wake main |
| activation/gaps | baseline quietly; report expired-cursor coverage gaps and rebaseline; no historical reconstruction |

reuse the current process, deployment lock, google client/auth, timer, o6 waking
append, native input port, action/read journals and outbox. add two small tables.
no event bus, workflow controller, mailbox/calendar mirror, push infrastructure,
new agent, future calendar-timer cache or per-todo automation.

one-shot reminders and worker waits keep their owning contracts. work due dates
stay bookkeeping. attachments, historical imports, dreamer work context and
budget integration remain separate. complete-search APIs supply reopenable mail/
calendar references; dreaming requires the accepted memory core. other sources
can ship before memory; the default review requires o7.

## source progress and publication

one new poll task signals the existing input path while main runs. the existing
timer publishes due wakes independently of slow connector reads and signals due
polls. rotate due sources after one page; no overlapping scan of the same source.
one shared 60-second poll default. owner ingress, consent and delivery stay live.
due selection excludes disabled/blocked streams and unresolved series; settlement
or enable/cancel signals timer change. a publisher losing to cancellation is a no-op.

add `event_cursor`:

| field | meaning |
| --- | --- |
| `kind`, `account_id`, `resource_id` | composite primary key; one row per polled stream: `gmail`, `calendar_list`, `calendar_changes`, `calendar_upcoming`; root resource empty, child resource exact calendar id; account is verified `getProfile.emailAddress`, never generic `me` |
| `enabled` | boolean on family roots only; null on calendar children; initialized true once, never reset at restart |
| `progress` | closed per-kind json below; cursors only, no bodies or source corpus |
| `page_size` | persisted provider page count; initially 20, reduced on page-bound failures before restarting the scan |
| `next_poll_at`, `last_success_at` | utc timestamp; last success nullable |
| `error` | null or `{episode_id, code, since}`; uuid, bounded host code, utc time; no private prose |
| `seen_inventory_scan` | nullable uuid on calendar children; supports complete inventory reconciliation |

gmail progress is `{history_id, page_token}`; calendar-list is `{scan_id,
page_token}`; changes are `{sync_token, page_token, baselining}`; upcoming is
`{calendar_zone, scan}`, with scan null or `{as_of, owner_zone, calendar_zone,
page_token}`. tokens are nullable opaque strings. freeze base token/selectors
throughout pagination. baseline starts with null sync token; inventory id and
upcoming clock/zones persist before the first page. continuation is due immediately;
completed polls schedule the next check 60 seconds later. timestamps are
`timestamptz`; json times use aware utc values. account changes create a new scope
and baseline; poll/admit only the current verified account, leaving old scopes
inactive. never transfer an old account's cursor. freeze page size with selectors;
reducing it restarts that scan from its committed base, preserving identity dedup.

fetch one complete bounded provider page and any required metadata outside the
database transaction. then atomically insert its canonical inputs and advance
its continuation. install a new history/sync checkpoint only after the final
page. interruption or partial failure retries the original page; google reads may
repeat. keep only the current page in memory. bound the assembled page, including
metadata/notices, by the existing 2 mib provider-buffer constant and each whole
page attempt to 30 seconds; reduce page size rather than clipping a tail. an
irreducible page failure is explicit unavailability. no cumulative traversal cap.

every provider entry and publication requires current deployment ownership and
an enabled, unpaused source. publication rechecks the family root under existing
locks; provider results losing that race cannot publish or advance progress.
lookup canonical identities before rebuilding a previously published fact:
duplicate polling preserves the original text/times, rather than reinserting
fresh metadata under an old id. hash canonical identity tuples for bounded source
ids; never identify events by prose equality. all inputs route to the configured
conversation through o6's transaction-level append. put source facts/references
in canonical host text, not mutable trace. email/calendar/suggestions have null
parent and optional notice; recurring inputs copy parent/notice from their series.
status/gap/unavailable facts require notice; recovery is optional. `created_at`
uses known provider source time, first observation if absent, or intended due time
for wakes/attention; retain actual observation separately. duplicates freeze both.

transport/rate failures retain progress and back off from 60 seconds to 15
minutes. one required `event_status` input per outage episode identifies source,
known gap/error and recovery needed; recovery may be optional. invalid auth or
schema blocks that source until repaired. healthy calendars continue. success,
restart and resume never clear a parked main input.

## email and calendar adapters

gmail starts from `users.getProfile.historyId`. poll `history.list` for
`messageAdded`; process `messagesAdded`, not the duplicate general message list.
fetch candidate metadata and apply the settled label exclusions; sent-only means
`SENT` without `INBOX`. identity is account + message id, including different
messages with identical text. imported old mail is a newly observed addition,
not proof of a recent sending date. definitive missing metadata produces an
explicit unavailable fact; transient failure does not advance the page.
expired history returns 404: persist the gap notice and a fresh baseline together.
ordinary downtime catches up only while history remains available.
[gmail history](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list)
and [profile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile)
define this protocol.

calendar inventory traverses all pages, stamping children with one scan id. delete
missing child cursors only after the whole inventory succeeds; canonical history
remains. publication rechecks the child's existence. new calendars baseline
quietly. the family switch governs all calendar reads/publication; revoked access
is explicit.

changes use `events.list(singleEvents=false, showDeleted=true,
showHiddenInvitations=true)` without time bounds, and one sync token per calendar.
discard initial baseline events; change capture begins when its final sync token
commits. incremental results are latest-state observations, not a mutation audit.
identity is account/calendar/event/etag; sparse cancellations without a revision
also bind the fixed starting sync token. preserve missing source times/fields;
never invent an etag or fetch a deleted event as a prerequisite. 410 produces an
explicit gap and a fresh baseline. sync tokens cannot use the upcoming time
filters. [calendar sync](https://developers.google.com/workspace/calendar/api/guides/sync)
and [event list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
own the provider constraints.

upcoming uses `singleEvents=true, showDeleted=false, showHiddenInvitations=true`.
freeze owner date/zone and each calendar's zone. query the union window of ongoing/
next-15-minute timed events and that owner date interpreted in the calendar zone:
`timeMin=min(as_of, calendar-midnight(date))`,
`timeMax=max(as_of+15m, calendar-midnight(date+1))`. round bounds outward to seconds,
then filter exactly: timed attention is start minus 15m, due now, with known real
end still future at admission; all-day attention is 09:00 owner-local on actual start
date, still that date at admission in the frozen owner zone. skip cancelled items.
this includes foreign-zone all-day
events; multi-day ones do not repeat daily. preserve unknown real ends.

attention identity is logical occurrence + actual start: one-off event id, or
recurring parent/original start, plus current start instant/date. moves can produce
a new approaching input; title/attendee edits alone cannot. include frozen owner
zone for all-day identity; returning to an already-noticed start stays deduplicated.
edits/cancellations after publication remain new change facts; old inputs stay fixed.
[event semantics](https://developers.google.com/workspace/calendar/api/v3/reference/events)
define recurring identity and sparse cancellations. no local google recurrence
expander or replay of already-ended appointments.

suppress only proven self-echoes: an exact committed gmail sent-message id, or a
calendar change matching the exact resulting revision in a successful connector
receipt. do not suppress later edits or upcoming attention for that event.
calendar deletes lack an after-revision; retain ambiguous tombstones. native
commands and uncertain effects have no such proof. no text/author heuristic.

## recurring wakes and tools

keep action-backed one-shot `schedule.wake` and its immutable creation receipt.
add `recurring_wake`:

| field | contract |
| --- | --- |
| `id`, `creation_action_id`, `parent_request_id` | uuid primary key; agent-created id equals its action id; nullable action/parent only for the named host default |
| `title`, `instruction`, `notice`, `rule`, `start_at`, `until` | immutable; title <=240 utf-8 bytes; reuse one-shot instruction/notice bounds; aware start, nullable exclusive end |
| `next_due_at`, `current_message_id` | nullable utc due time and canonical occurrence reference |
| `cancelled_at`, `created_at` | nullable cancellation time; immutable creation time |

closed rules: `daily{at, zone}`, `weekly{weekdays, at, zone}`,
`monthly{day, at, zone}`, `interval{seconds}`. `at` is `HH:MM`; zone is an iana
name; weekdays are a nonempty unique subset of `mon`–`sun`; day is 1–31; interval
is integer seconds >=60. start must be future at creation; interval's first due
is start, calendar rules choose their first occurrence on/after it. end must
follow start and admit an occurrence. null end permits indefinite recurrence.

calendar rules freeze their zone, use local date arithmetic, clamp nonexistent
monthly days to month end without changing the requested day, take the earliest
fold instant and advance nonexistent local times by the actual clock gap. prove
conversion with utc round trips. intervals use elapsed utc seconds from the
original anchor. compute latest due/count/next directly, not by replaying missed
turns. changing owner timezone affects new schedules; edit existing ones explicitly.

| tool | input / result |
| --- | --- |
| `schedule.recurring` | `type=create`: title/instruction/notice/rule/start_at/until; `type=cancel`: id; result created(id,next_due_at) or cancelled(id,current_message_id) |
| `schedule.list` | kind both/one_shot/recurring, status active/all, page_size 1–100 (default20), cursor; summaries + next_cursor/as_of |
| `schedule.get` | kind/id; complete current schedule, including original instruction and latest occurrence reference |
| `events.configure` | source email/calendar, enabled; result source/enabled |
| `events.status` | no arguments; both families' enable state, baseline/healthy/degraded/blocked status, last success, cadence/scope and readable-calendar count |

strict schemas reject unknown fields. summaries are kind/id/title/notice/status/
next due/instruction preview; get opens full content. list uses live keyset order next due nulls
last, kind, id; disclose its current-contract scope. historical retired actions
remain opaque. get/list are fresh reads; edits use cancel+create. local writes are
automatic `Write + ReDispatchable`, with the existing action id, serial dispatch,
positive local attempt ceiling and zero external attempts. store mutation and
original success/typed error receipt in one transaction; callback replay cannot
recreate a cancelled series. use `NotFound`, `InvalidSchedule`, `NoOccurrence`
and existing one-shot errors; cancellation of an already cancelled series succeeds.

due publication atomically inserts `source=recurring_wake`, identity series + due
instant, original instruction/notice, actual observation time and skipped count,
then advances next due and sets the current message reference. at most one
unresolved occurrence per series; waiting/parked input retains its place. choose
latest eligible due before `until`, even after series expiry; skipped count is
eligible instants since persisted next due minus one. advance to first future
eligible time or null. active means not cancelled and (next due exists or latest
input remains unresolved). retain latest reference for get. after closure, coalesce
elapsed occurrences.
recurring inputs settle through o6; never call one-shot action finalization or
fabricate an action/native invocation for each occurrence.

install the quiet 09:00 review once with a stable deployment/purpose id and honest
host origin. instruction: review active work, especially blockers; choose useful
follow-through. cancellation survives restart; no reseeding or per-record timer.

cancel disables future publication, even while a published occurrence remains
unfinished. disable retains source cursors; re-enable catches up or reports a gap.
neither changes existing inputs, approvals, workers or entered effects. ordinary
stop reaches main under o9; deployment pause prevents new polling/publication/
cognition, while existing recovery/delivery remain. cancellation and publication
race under the same target lock. move one-shot cancel's separate precheck/receipt
decision into that transaction: a lost race returns `TargetNotQueued`, not a
successful receipt or configuration defect.

## useful internal suggestions

extend dream completion to `{notes:[{text,references}], wake_note_index:int|null}`.
null is ordinary success; otherwise require an index into this run's newly saved
notes. retain existing note/evidence/budget bounds.

in the same caller transaction, `complete_dream` appends notes/leaves/progress;
jarvis inserts one optional `internal_suggestion` host input keyed by the selected
note id. commit all or none. library code stays product-independent. canonical
input is the immutable note reference; ordinary main context renders its saved
text, attribution and references, without a mandatory memory.open call. existing
progress handles lost commit receipts; do not rerun to reconstruct a missing wake.

archive that input as `synthesis_reference`, empty text and closed `{note_id}`
attributes and null embedding. render its reference/attribution in the shared tree; exclude it, like
synthesis notes, from new dream seeds and automatic random sampling, including
mixed nodes. bind canonical identity/digest before suppression. no second prose
copy or new eligibility flag. ordinary main outcomes remain historical material.

other existing trusted producers use the same transaction-level append with a
stable producer/result identity, concise suggestion and actual supporting refs;
ordinary invocation results may carry the finding directly. no model-callable
suggestion tool. saved notes, assistant
outputs and unchanged polls do not automatically become suggestions.

## designer's contract

the content designer supplies source framing, instructions and examples to the
one definition-file owner. agents choose procedure.

- source inputs: identity, source/observation times, actual facts, marked previews
  and exact reopenable references. email includes sender/subject previews and
  message/thread ids; calendar includes status, actual start/end/all-day/zone and
  event/instance ids. missing data and clipping are explicit. never fabricate
  owner speech, consent, earlier values or message-body inspection.
- recurring instructions: recognizable target and useful purpose; retain original
  due anchor so old “tomorrow” does not drift. creation confirms rule/zone/next due;
  cancellation states the receipt-backed scope. overdue output identifies lateness.
- nominated dreams: a connection, correction, question or next step worth main's
  attention now, including scientific/creative/personal findings. supported
  premises, uncertainty and why it matters; null beats narrating dreaming or
  repeating an unchanged finding. main restatement is evidence it was considered,
  not independent corroboration of the hypothesis.
- main output follows o6: routine ambient success may be quiet; requested results/
  reminders, approvals, blockers and failed/uncertain effects stay visible. daily
  review may produce nothing; don't manufacture todos, urgency or completion.

good: `late reminder: submit the abstract; this was due yesterday at 5 pm.`
good: `the pilot results disagree. comparing their task wording may explain why.`
good: `figure 4 is still waiting on your decision: keep it or cut it?`
claims require observed evidence and committed receipts, not exact wording.

## implementation, cutover and acceptance

| unit | exclusive ownership |
| --- | --- |
| persistence/local tools | `db.py`, one migration, new `events.py`/`recurrence.py`, `schedule_tools.py`, `actions.py`: cursor/series stores, atomic receipts/publication and cancel race |
| google adapters | `connectors.py`, small new `event_polling.py`: history, inventory, sync/upcoming queries, identities and exact echo proof; existing auth/http only |
| runtime composition | `service.py`, `proactivity.py`, `messages.py`, `settings.py`, `cli.py`, dispatch/composition/policy files: live source task, ownership, controls, fresh reads; one writer per shared file |
| memory/content | `memory_workers.py`, `definitions.py`, session compatibility plus library archive/seed schemas: nomination, shared-transaction completion and reference-only capture; designer supplies content |
| temporary proof | scoped new checks only; end-to-end/live evidence and adversarial content review |

adopt the two tables/tools, all-source ingress and selected-dream amendment
together with their owning spec/adr changes; core sources need no kernel/provider/
skid API upgrade. existing worker waits remain o8. reuse shared serializers,
google pagination, note validation, append and local-write receipt primitives;
remove replaced serial-only source publication and contradictory quiet-only
dream/output rules. preserve original receipts and accepted memory progress.
use stopped cutover/revision rotation; no dual decoder or fallback path.

temporary red/green/refactor/live journeys:

1. real postgres/native composition: baseline, unchanged polls, multipage restart,
   identical/distinct mail, archived arrivals, missing metadata, sparse calendar
   cancellations, expired cursors and exact self-echo versus later edits.
2. synthetic controlled calendar: timed/all-day/recurring/moved/ended events,
   approximate attention, complete paging, partial calendar availability; ordinary
   owner input remains responsive while sources steer main.
3. recurring create/inspect/cancel/restart: dst fold/gap, month31, interval anchor,
   coalescing, unresolved approval/park, cancel/publication race and cancelled
   default review; original receipts replay without resurrection.
4. memory composition: zero/one nominated note, invalid index, rollback/lost commit,
   synthesis-reference seed/sample exclusion; a real main integrates or ignores
   a useful finding, and consequential connector output still needs exact approval.

use synthetic/private controlled content. record red, get green, adversarially
review, refactor actual duplication, verify the final journeys, then delete the
temporary tests and run `scripts/verify`. no code, behavioral/live execution,
provider account access or deployment in this documentation task.

costs: polling consumes provider reads and discovers short/last-minute events
late; it is not lossless or an alarm sla. first calendar baseline may absorb
intervening changes. simple rules omit compound calendars; month-end clamping
differs from skipping missing dates. coalescing deliberately skips occurrences;
source toggles/cancellation do not stop already published work. one-minute minimum
is an explicit recurrence rule. suggestions and daily review can incur autonomous
cognition; bounded nomination/identity prevent immediate replay, not guaranteed
semantic novelty. temporary test deletion reduces retained regression coverage.

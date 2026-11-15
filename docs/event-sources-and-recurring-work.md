# event sources, suggestions and recurring work

status: accepted v2 target under [adr 0071](decisions/0071-simple-event-driven-v2.md),
2026-11-14; unimplemented. this extends [o6](one-main-events.md). the
[roadmap](implementation-plan.md) owns sequencing. shared memory's separate
delivery and quiet dreaming remain unchanged.

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
| daily work review | an ordinary scheduled todo at 09:00 owner-local; main chooses useful follow-through |
| suggestions | existing trusted producers may submit useful findings through the same input path; selected dream wakes are deferred |
| activation/gaps | baseline quietly; report expired-cursor coverage gaps and rebaseline; no historical reconstruction |

reuse the current process, deployment lock, google client/auth, timer, o6 waking
append, native input port, action/read journals and outbox. this feature adds one
`event_cursor` table. [work records](work-records.md) owns both one-time and
repeating wakes in its existing todo table; there is no `recurring_wake` table.
no event bus, workflow controller, mailbox/calendar mirror, push infrastructure,
new agent or calendar-timer cache.

work deadlines remain bookkeeping, separate from optional wake times. worker
waits retain their [existing observation path](worker-launch-observation.md).
attachments, historical imports, dreamer work context and budget integration
remain separate. source adapters carry reopenable mail/calendar references;
they need no memory amendment or new skid push api.

## source progress and publication

one new poll task signals the existing input path while main runs. the existing
timer publishes due wakes independently of slow connector reads and signals due
polls. rotate due sources after one page; no overlapping scan of the same source.
one shared 60-second poll default. owner ingress, consent and delivery stay live.
due selection excludes disabled/blocked streams. source enable/disable and work
schedule mutations signal timer change. a publisher losing to disable is a no-op.
scheduled todos use work's own atomic publication, independently of connector reads.

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
in canonical host text, not mutable trace. independent email/calendar/suggestion
events have null parent; an actual causal request may be referenced when known.
do not invent owner speech or consent. `created_at` uses known provider source
time, first observation if absent, or intended due time for wakes/attention;
retain actual observation separately. duplicates freeze both. main chooses
whether a source fact needs communication; there is no notice-policy field.

transport/rate failures retain progress and back off from 60 seconds to 15
minutes. one `event_status` input per outage episode identifies source,
known gap/error and recovery needed; a recovery event reports restored coverage.
main can explain a material interruption in ordinary conversation. invalid auth or
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

[work records](work-records.md#recurrence-contract) owns one-time and
repeating scheduling, date rules, coalescing and atomic due publication. use
`work.create`, `work.update`, `work.get` and `work.list`. clearing a todo's wake
stops future publication; done/cancelled/delete also removes its schedule.
previously published inputs remain ordinary main work. there is no additional
schedule table, schedule inspection api or recurring-work controller.

this source feature adds only:

| tool | input / result |
| --- | --- |
| `events.configure` | source email/calendar, enabled; result source/enabled |
| `events.status` | no arguments; both families' enable state, baseline/healthy/degraded/blocked status, last success, cadence/scope and readable-calendar count |

configuration is an automatic local `Write + ReDispatchable` using the existing
action id, serial dispatch, local attempt ceiling and zero external attempts.
store mutation and original receipt in one transaction; replay returns that
receipt rather than applying an old toggle again. status is a fresh read. no
new consent flow or credential handling is introduced.

disable retains cursors. re-enable catches up or reports a gap. neither changes
existing inputs, approvals, workers or entered effects. ordinary stop reaches
main under [o9](delegated-follow-through.md); deployment pause prevents new
polling/publication/cognition while existing recovery/delivery remain.

## useful internal suggestions

an existing trusted producer can use o6's transaction-level append with a stable
producer/result identity, concise finding and supporting references. when its
result already returns to a live invocation, use that existing result path.
no event bus, model-callable suggestion tool or special notification agent.

shared memory is ongoing separately. this delivery does not change dream output,
completion transactions, archive schemas or seed rules. dreams continue to save
quietly; main can read their notes during ordinary turns. automatic nomination of
dream findings as waking events is deferred. saving a note or assistant output
does not itself create a new input.

## designer's contract

the content designer supplies source framing, instructions and examples to the
one definition-file owner. agents choose procedure.

- source inputs: identity, source/observation times, actual facts, marked previews
  and exact reopenable references. email includes sender/subject previews and
  message/thread ids; calendar includes status, actual start/end/all-day/zone and
  event/instance ids. missing data and clipping are explicit. never fabricate
  owner speech, consent, earlier values or message-body inspection.
- scheduled todo context follows the [work contract](work-records.md): recognizable
  purpose, useful references, intended due time and an honest current snapshot.
  ordinary requests can set or clear a wake; no scheduling command syntax.
- internal suggestions name the finding, supporting references and uncertainty.
  main's restatement is consideration, not independent corroboration.
- main chooses progress, blocker and result communication through ordinary
  conversation. a useful reminder should arrive; routine ambient success and a
  daily review may need no reply. don't manufacture urgency or completion.
  consequential actions use o6's conversational consent, with no special ui.

good: `late reminder: submit the abstract; this was due yesterday at 5 pm.`
good: `the pilot results disagree. comparing their task wording may explain why.`
good: `figure 4 is still waiting on your decision: keep it or cut it?`
claims require observed evidence and committed receipts, not exact wording.

## implementation, cutover and acceptance

| unit | exclusive ownership |
| --- | --- |
| persistence/local tools | `db.py`, one migration, small `events.py`, existing action/local-write primitives: cursor store, atomic source progress/publication and enable/disable |
| google adapters | `connectors.py`, small new `event_polling.py`: history, inventory, sync/upcoming queries, identities and exact echo proof; existing auth/http only |
| runtime composition | `service.py`, `proactivity.py`, `messages.py`, `settings.py`, `cli.py`, dispatch/composition/policy files: live source task, ownership, controls, fresh reads; one writer per shared file |
| content | `definitions.py` and session compatibility: honest source framing and ordinary main follow-through; shared memory code is untouched |
| temporary proof | scoped new checks only; end-to-end/live evidence and adversarial content review |

adr 0071 adopts the single cursor table/tools and all-source ingress. core sources
need no kernel/provider/skid api upgrade. existing worker waits remain o8. reuse
shared serializers, google pagination, waking append and local-write receipt
primitives. work owns recurrence and migration of old reminders. remove replaced
serial-only publication; preserve original receipts and memory's separate
contract. use stopped cutover/revision rotation; no dual decoder or fallback path.

temporary red/green/refactor/live journeys:

1. real postgres/native composition: baseline, unchanged polls, multipage restart,
   identical/distinct mail, archived arrivals, missing metadata, sparse calendar
   cancellations, expired cursors and exact self-echo versus later edits.
2. synthetic controlled calendar: timed/all-day/recurring/moved/ended events,
   approximate attention, complete paging, partial calendar availability; ordinary
   owner input remains responsive while sources steer main.
3. source enable/disable/restart preserves progress and races safely with publication;
   a trusted suggestion starts the same main and can be integrated or ignored.
4. scheduled todo journeys belong to work's acceptance; prove one combined
   owner/mail/work/worker-result journey through main without a second agent,
   notification controller or model polling loop.

use synthetic/private controlled content. record red, get green, adversarially
review, refactor actual duplication, verify the final journeys, then delete the
temporary tests and run `scripts/verify`. no code, behavioral/live execution,
provider account access or deployment in this documentation task.

costs: polling consumes provider reads and discovers short/last-minute events
late; it is not lossless or an alarm sla. first calendar baseline may absorb
intervening changes. source toggles do not stop already published work. events
can incur autonomous cognition; source identity prevents duplicate publication,
not repeated semantic ideas. scheduled-todo costs belong to work's contract.
temporary test deletion reduces retained regression coverage.

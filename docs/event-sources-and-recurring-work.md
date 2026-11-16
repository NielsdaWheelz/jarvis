# email/calendar events

status: slice 6 implementation contract under [adr 0071](decisions/0071-simple-event-driven-v2.md),
source-audited against main `d93b84d`, 2026-11-15; implementation and qualification
in progress on `feature/event-sources`. the
[roadmap](implementation-plan.md) owns sequence. attachment implementation is
concurrent; audit its actual merge before integrating shared files. no production
activation, provider-account operations or behavioral proof in this doc task.

## target and settled scope

email additions and calendar changes/approaching events become ordinary canonical
host inputs to [one main](one-main-events.md), including while main is busy.
main chooses inspection, action, delegation, bookkeeping, notification or silence.
external prose is evidence, never owner speech or consent.

| choice | behavior |
| --- | --- |
| email | incoming additions, including automatically archived mail; exclude drafts, spam, trash and sent-only mail (`SENT` without `INBOX`); label/read changes alone do not wake |
| calendars | every event-readable calendar in the account's calendar list, including hidden calendars; readable does not mean owned or attended |
| attention | timed events about 15 minutes before start; all-day events at 09:00 owner-local on their start date; 60-second polling, no exact-alarm promise |
| activation | quiet initial mail/change baselines; currently due attention remains eligible; expired cursors produce an explicit gap and a fresh baseline |
| controls | independent email/calendar family switches; disabling preserves progress and already published work; re-enable catches up while provider history survives |
| daily review/recurrence | already owned by [work](work-records.md); ordinary scheduled todos, no new recurrence feature |

one new cursor table, one poll task, two model tools. reuse the process, deployment
lock, google authorization/client, canonical append, native admission, local action
receipts and outbox. no event bus, push/webhooks, mailbox/calendar mirror, local
recurrence expander, notification controller or additional agent.

attachments remain [slice 5](attachments-and-durable-originals.md): event inputs
carry exact mail references; main chooses file discovery/retention. do not fetch
mail bodies or attachment bytes during polling. shared memory projects ordinary
host-message metadata through its existing path; no capture-engine/schema change,
mailbox archive, dream wake, search overhaul or budget work.

## source audit and parallel handoff

| boundary | implement here |
| --- | --- |
| common append and native steering already exist | source adapters and atomic cursor/publication; no second main loop |
| `WorkWakeTimer` is db-only | leave it unchanged; new poll task owns its own due wait using the same notify/wait pattern |
| owned database serializes one connection | all provider io outside db transactions, `_active_lock` and `_dispatch_lane` |
| existing model-facing calendar reads clip/drop required metadata | share scalar parsers/transport; add one narrow event projection, not another full connector or search rewrite |
| shared token manager has concurrent-refresh/stale-invalidation risk | serialize refresh only; invalidate only the rejected token; source finding repaired and qualified below |
| old success receipts lack account-qualified echo evidence | add verified `account` to new send/create/update successes; never infer it for old receipts |

slice 5's in-flight source has `0011_attachments`, `gmail_account` and
`FRESH_READ_IDS`; these are unqualified until its merge. consume the landed
versions. factor one shared profile read/parse returning `{account, history_id}`
from the same response, preserving attachment callers' account view. one token
manager/client composition serves foreground tools, attachments and polling.
expected event migration is `0012_event_sources` after landed `0011`; no parallel
migration head. specification/source work can proceed now; integrated proof
must use the actual combined tree. production cutover stays a separate final step.

## cursor schema and ownership

`event_cursor` contains progress only. times are `timestamptz`; json timestamps
are aware utc; opaque tokens are nullable bounded strings, never logged.

| column | contract |
| --- | --- |
| `kind`, `account_id`, `resource_id` | composite primary key; kinds `gmail`, `calendar_list`, `calendar_changes`, `calendar_upcoming`; verified profile email; root resource empty, child resource exact calendar id |
| `enabled` | non-null boolean on family roots (`gmail`, `calendar_list`), null on children; initialize true only for a new account/root |
| `progress` | closed per-kind json below; no bodies, event cache or exclusion ledger |
| `next_poll_at` | nullable; null means blocked pending repair/re-arm, never an invisible busy-loop deadline |
| `last_success_at` | nullable; time of last COMPLETE baseline/scan/checkpoint, not a successful intermediate page |
| `error` | null or `{episode_id, code, since, retry_count}`; uuid, closed safe code, utc timestamp, saturated count 1..5 |
| `seen_inventory_scan` | nullable uuid, set only on calendar children; complete-inventory membership proof |

closed progress shapes:

```text
gmail: {history_id, page_token, consumed, prefix_sha256}
calendar_list: {scan_id, page_token}
calendar_changes: {sync_token, page_token}
calendar_upcoming: {calendar_zone, scan}
scan: null | {as_of, owner_zone, owner_date, time_min, time_max, page_token}
```

null history means mail baseline pending, with no page token/consumed prefix.
consumed is a strict integer 0..2^53−1, digest null exactly when consumed=0.
null inventory scan id requires null page token; start a new uuid before its first
page. null calendar sync token means baselining; its page token may still continue
that baseline, without a redundant boolean. upcoming zone is an iana
name, or null only while that resource is unavailable; scan bounds/selectors are
frozen before the first page, including actual utc query bounds.

use existing exact provider-id bounds (1024 utf-8 bytes), calendar/work zone
validation and canonical json hashing; tokens have an 8192-byte bound. enforce
root/child shape, closed progress and nonnegative count constraints. no generic
workflow/version registry. account is fixed after verification for one running
composition; stopped private-account replacement follows existing authority/drain
rules. a different verified account creates a fresh scope; old rows remain inactive.

before profile verification there is no honest account-scoped cursor. report
`account=null/unverified`, return `AccountUnavailable` for configuration and use
safe operator diagnostics; never invent a `me` account or fabricate a source event.
retry transient verification failures with the same bounded backoff; unusable
credentials require repair/restart. existing operational pause remains available.

## polling and atomic publication

one `EventPoller.run` task starts provider work only after validated discord
catch-up (`service._startup_ready`), with current deployment ownership and an
unpaused, enabled family. child eligibility requires both root.enabled and a
non-null root.next_poll_at, plus its own non-null due deadline. a blocked inventory
root blocks that family; one blocked child leaves peers eligible.
select due streams in `(next_poll_at, kind, resource_id)`
order; fetch one page or bounded gmail prefix, commit, yield, rotate. continuations
become due now; completed scans become due 60 seconds later. idle waits use the
existing change-event pattern with a 60-second rescan ceiling. ingress/control,
configuration and readiness changes wake it. work timers, worker waits and
outbound delivery remain independent of slow provider reads.
recheck admission before EVERY provider request, including metadata/refresh calls:
an entered read may settle after pause/disable, but no subsequent request starts.
surface unexpected poll-task exit through existing service supervision.

provider requests retain existing 8-second transport bounds and 2-mib decoded
response limit; a poll quantum has a 30-second elapsed bound. use fixed 20-item
provider pages and at most 20 gmail candidates per quantum. do not retain a page
across processes or hold a transaction during a fetch. no traversal-length cap.
calendar sync query parameters, including page size, remain fixed for a token's
lifetime; do not shrink a page beneath an existing token. an irreducible response
is explicit blocked unavailability, not a clipped page or silently advanced cursor.

publication takes the existing conversation lock, then family/root/child rows in
stable order. recheck ownership, pause, enable state, child existence and expected
progress before committing observations and progress together. a stale/disabled
result commits neither. an off/on cycle may resume still-valid old progress; no
new generation counter is required. shutdown cancels uncommitted reads; committed
facts/progress survive. no new publication after ownership loss.

lookup canonical identities before re-fetching/re-rendering already published
facts. duplicates preserve original text/source/observation times. canonical
source ids are sha-256 of the tuples below using the existing serializer; their
namespace is the `message.source`. use `append_waking_input` with `role=host`,
configured conversation and null parent. known causal suggestions may use an
eligible ordinary request parent; controls cannot be parents.

| source | identity tuple |
| --- | --- |
| `email_event` | account, message id |
| `calendar_event` | account, calendar id, event id, tagged `{kind:etag,value}`; sparse cancellation without etag uses `{kind:sync_base,value}` from the fixed starting sync token |
| `calendar_attention` | account, calendar id, logical occurrence, actual start; include owner zone for all-day attention |
| `event_status` | stream identity + tagged phase; outage/recovered use episode id, removed uses completed scan id + calendar id, gap uses expired base-token digest |

no text-equality or semantic deduplication. no revision on a sparse cancellation
means no promise of deduplication across different sync bases. independent facts
may batch/steer main; they do not require a response. publication signals ordinary
main work and the existing memory projector. source inputs never clear parked
requests or settle unrelated work.

## provider contracts

### gmail

initial profile `historyId` becomes a quiet baseline. `history.list` uses
`historyTypes=messageAdded`, no label filter, fixed base `startHistoryId` and page
token. read `messagesAdded`, not the duplicate generic `messages` field. request
only history ids, added message ids/thread ids and continuation/high-water fields.
[gmail history](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list).

`maxResults` counts history RECORDS, not messages. flatten each page into ordered
`(history_id, message_id)` candidates: numeric history order, lexical message order
within each record, duplicate pairs collapsed. validate the stored consumed prefix
against its sha-256 before resuming. mismatch resets only this page's prefix;
retain the committed base cursor and source deduplication, never skip guessed
positions. digest the identity prefix, not response high-water or page-token bytes.

for each new candidate fetch metadata only: id, thread id, label ids, internal date
and From/Subject headers. apply current label exclusions; raw sender/subject are
bounded previews, not strict address-parser admission gates. a definitive 404
produces an unavailable-addition fact, without claiming it was eligible incoming
mail. failure/timeout leaves that unfinished candidate unconsumed. commit any
earlier completed prefix and the failure/backoff together in an owned transaction;
do not let an outer timeout discard useful prefix progress.

atomically publish-or-exclude a completed candidate prefix and update consumed/
digest, including excluded candidates. commit completed progress before rotating;
an interrupted unfinished candidate repeats its read. only after the entire page
is classified advance its page token and clear prefix state. only the final page
installs returned historyId. this prevents a long excluded prefix from starving
valid mail without adding an inbox mirror or per-message read ledger.

imported old mail is a newly observed addition, not evidence of recent sending.
label changes after observation do not rewrite it. expired history (404 on the
history endpoint) atomically publishes a gap and resets baseline progress; obtain
a fresh profile next. lost historical additions are not reconstructed.

### calendar inventory and changes

inventory fully pages `calendarList.list(showHidden=true, showDeleted=false,
minAccessRole=reader)`; do not filter selected/primary calendars. request exact id,
access role and timezone with `fields=nextPageToken,items(id,accessRole,timeZone)`.
use the provider's read-access selector; do not reject a returned read-capable role
merely because an older model-facing enum omitted it.
full scans are intentional: incremental list sync can
omit property/access changes. stamp/create both child streams per valid calendar.
only a completed inventory may remove unseen children, atomically with a truthful
`no longer in readable inventory` fact; do not assert specifically revoked access.
partial/failed scans remove nothing. unknown resource-local zone/schema problems
block the affected child; malformed inventory identity blocks that inventory page.
[calendar inventory](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list).

changes use `events.list(singleEvents=false, showDeleted=true,
showHiddenInvitations=true)` without time filters/orderBy, with fixed selectors
through baseline and incremental sync. baseline validates the response envelope
and tokens, then discards rows WITHOUT normal event/time projection; irrelevant
historical data must not block future-only activation. install nextSyncToken only
on the last page. incremental results are latest snapshots, not every
intermediate mutation. preserve cancelled records with missing fields; never fetch
a deleted event as a prerequisite. expired sync (410) atomically publishes a gap,
clears only that stream's token/page and starts a quiet baseline; canonical facts
stay immutable. [calendar synchronization](https://developers.google.com/workspace/calendar/api/guides/sync).

share one narrow projection for changes/attention: id, etag, status, updated,
summary/location previews, start, real end, recurrence parent/original start and
event type; calendar id/name/zone establish provenance. list response `summary`
provides the calendar name without storing a calendar mirror. reuse scalar/time
parsers, not full write snapshots or clipped model list results. omit attendee
inventories; calendar `self` is not proof of owner attendance. sparse cancellations
can contain id alone; noncancelled malformed identity/time fails that child.
[event semantics](https://developers.google.com/workspace/calendar/api/v3/reference/events).

both event list calls request only
`fields=summary,timeZone,nextPageToken,nextSyncToken,items(id,etag,status,updated,summary,location,start,end,endTimeUnspecified,recurringEventId,originalStartTime,eventType)`.
the mask stays fixed through sync baselines/incremental pages. projecting only
after fetching full events would still transfer descriptions and attendee lists.

### approaching events

use `singleEvents=true, showDeleted=false, showHiddenInvitations=true`. freeze
scan clock, owner date/zone, calendar zone and exact query bounds. the candidate
window is the union of ongoing/next-15-minute timed events and the owner date
interpreted in the calendar zone:

```text
lower = min(as_of, calendar_midnight(owner_date))
upper = max(as_of + 15m, calendar_midnight(owner_date + 1))
timeMin = floor lower to whole seconds - 1 second
timeMax = floor upper to whole seconds + 1 second
```

query bounds strictly enclose the window: both provider bounds are exclusive and
ignore milliseconds. the extra lower second also admits an unspecified-end event
exactly at start; final filters reject ended events. filter at PUBLICATION time,
not the frozen scan time:

- timed: `start−15m <= now`; admit before/at start, or later only when a known real
  end is still future. `endTimeUnspecified`'s compatibility end is not a real end.
- all-day: actual start date equals today's date in the frozen owner zone and
  resolved 09:00 <= now. multi-day events do not repeat daily. reuse work's fold/
  gap resolver through one shared helper; no second civil-time algorithm.
- skip cancellations/ended events. timezone configuration/inventory changes discard
  an unfinished upcoming scan; preserve already published facts. a scan crossing
  owner midnight cannot publish yesterday's all-day attention.

logical occurrence is one-off event id, or recurrence parent plus original start.
use tagged all-day dates or utc instants, never iCalUID alone. include actual start
in identity: a move may produce new attention; title edits cannot; returning to
an already noticed start stays deduplicated. later cancellation/change is another
fact, never a rewrite of old attention. [query boundaries](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).

### proven self-echoes

suppress only a committed successful connector receipt matching verified account
and exact sent message id, or account/calendar/event/resulting etag. add `account`
to NEW `GmailSendDraftSuccess`, `CalendarCreateEventSuccess` and
`CalendarUpdateEventSuccess`, using shared verified identity before effect entry.
owner amendment, 2026-11-16: a recovered success whose effect is proved may use
`account=null` when account qualification is unavailable. this is still success;
missing echo qualification never makes a proved effect uncertain. direct
successes still require verification before effect entry. null-account receipts
cannot suppress echoes. retain existing bounded effect reconciliation; do not
repeat an effect, infer account or add durable recovery state for this qualifier.
model arguments/consent/action schema stay unchanged; rotate affected bindings.
old unqualified receipts remain historical evidence and cannot suppress; no
backfill, compatibility decoder or echo ledger. deletes lack an after-revision;
native commands, unknown outcomes and racing uncommitted receipts provide no
proof. preserve those facts and all approaching attention; do not wait for a
pending action merely to suppress its possible echo.

## failures, controls and capability contract

safe source failure codes: `TransportUnavailable`, `RateLimited`, `AuthUnavailable`,
`Forbidden`, `InvalidResponse`, `ResponseTooLarge`, `CursorExpired`.
transient failures retain progress and back off 60, 120, 240, 480, then 900 seconds;
honor a later valid provider retry deadline. one outage fact opens an episode;
repeat failures update its code/count without repeated outage messages. only a
complete scan/baseline clears it and publishes recovery. recovery means current
polling resumed; previously announced gaps remain unreconstructed.

auth/grant failure blocks the affected family root (shared unusable credentials
block both); forbidden/malformed child data blocks that stream, leaving healthy
calendars eligible. do not collapse cursor expiry into generic provider failure.
reuse narrow http/status/credential helpers without changing unrelated tool error
contracts. a first 401 invalidates only its rejected token, obtains the current/
refreshed token and makes ONE explicitly counted same-request retry within the
quantum; persistent 401 blocks. this stage is request-local, not inferred from
episode retry_count. no hidden transport retry.

fix shared token concurrency at `GoogleTokenManager`: one async refresh lock,
recheck cached state inside it, atomically persist any rotated refresh token,
and `invalidate_access_token(rejected_token)` only if it is still current. update
existing read/write callers together. count refresh attempts at the actual caller
that entered refresh. provider reads remain concurrent; no global io lock or new
credential storage/configuration.

closed model contracts, normal envelopes:

| tool | input → result / behavior |
| --- | --- |
| `events.configure` | `{source: email\|calendar, enabled: boolean}` → `{source, enabled}`; automatic local write; fresh true also re-arms blocked family streams after repair, preserving cursors and error episode |
| `events.status` | `{}` → `{account, observed_at, paused, poll_seconds:60, families:[email,calendar]}`; fresh read, no provider io |

families contains exactly two family-status objects, email then calendar.
family status is `{source, enabled, state, last_success_at, next_poll_at,
baselining_streams, catching_up_streams, blocked_streams, failing_streams,
readable_calendars}`. counts are nonnegative integers; unavailable account yields
enabled=null/state=unverified, null times/readable count and zero known streams;
zero here does not assert verified empty coverage. otherwise
state is `unverified|disabled|blocked|degraded|baselining|catching_up|healthy`;
precedence is disabled, blocked (root deadline null), degraded (any error/blocked child),
baselining, catching_up (unfinished scan), healthy. `paused` is independent.
counts describe known inventory; an unfinished inventory is catching-up/baselining,
not a complete count claim. last success is the oldest completed check among its
current streams, null if one has never completed; not a global coverage watermark.
next poll is the earliest eligible deadline; readable count is null for email.
baseline counts derive from null gmail/change base tokens or never-completed
inventory/upcoming scans. nonbaseline page/prefix/scan continuation counts as
catching up; failure/block counts are independent and may overlap those counts.

configure uses existing `ActionRequest`, `ReDispatchable`, local lifetime ceiling
2, zero external attempts and atomic mutation/original receipt. exact callback
replay cannot reapply an old switch or re-arm again. add this named mutation to
work's local receipt/recovery and uncertainty-bypass paths in BOTH dispatch and
action admission; disabling sources must remain possible during another uncertain
effect. preserve all other effect barriers. status joins landed `FRESH_READ_IDS`;
exact original callbacks still replay their original receipt. both tools belong
to main's full event plan, not isolated memory roles. `AccountUnavailable` is the
only new configuration failure beyond existing validation/local failures.

re-arm sets blocked deadlines due now, not fresh history or cleared health.
disable retains progress; re-enable catches up or reports expiry. neither stops
already published inputs, approvals, workers or entered effects. ordinary stop is
main's scoped request disposition; administrative pause fences new polls and
publication. no source-specific approval ui or semantic consent system.

## designer's content contract

host input is bounded deterministic structured text with kind, exact references,
source time (nullable), observation time and source facts. `created_at` uses
known provider time, first observation if absent, or intended attention time;
deduplication freezes those values. previews are `{text, truncated}` with 240-byte
utf-8-safe display text. escape external prose inside host framing; never truncate
ids. fit the existing canonical/native input bounds before publication.

use four closed payload variants below; shared field names refer to one typed
definition, not an extensible event envelope. `account` and `observed_at` occur
in each. previews are nullable only when absent/unavailable. no opaque provider
cursor, body, attachment bytes or invented before-state enters these payloads.

| `message.source` / payload kind | additional fields |
| --- | --- |
| `email_event` / `email_added` | `message_id`, nullable `thread_id`, `metadata: available\|missing`, nullable `source_at`, `sender`, `subject`, `inbox`; missing metadata leaves these facts null, except any actually known thread id |
| `calendar_event` / `calendar_changed` | `event` projection below |
| `calendar_attention` / `calendar_attention` | `event`, `due_at`, `owner_zone` |
| `event_status` / `source_status` | `stream:{kind,resource_id}`, `phase:outage\|recovered\|gap\|removed`, nullable `episode_id`, `code`, `last_complete_at`; `coverage:current_only\|unknown_gap\|unavailable` |

event projection is `{calendar_id, calendar_name, calendar_zone, event_id, etag,
status, event_type, updated_at, summary, location, start, end, recurring_event_id,
original_start}`. reuse current tagged `EventTime`/`ObservedEventEnd`; normalize
timed instants to utc while retaining zone. dates remain dates. sparse cancellations
require calendar/event ids and status; other fields may be null. normal events
require etag/start and a real or explicitly unspecified end. no attendance claim.

outage uses its episode, failure code and unavailable coverage; recovered uses
the same episode, null code and current_only. gap uses CursorExpired/unknown_gap;
removed uses the notice-only `NotInReadableInventory` code and unavailable,
with episode optional. notice codes do not extend persisted failure codes.
gap never claims an exact lost-message count
or reconstructed interval. canonical source identity still follows the table above;
it needs neither token disclosure nor another ledger.

| feature | good content |
| --- | --- |
| mail | sender/subject previews, message/thread ids, current eligibility or explicit metadata unavailability; no claim that body/attachments were examined |
| changed calendar | calendar provenance, actual observed status/start/end/zone and event/occurrence ids; previous values require actual earlier evidence |
| attention | actual start/end and intended due time; use current host clock to distinguish upcoming/in-progress/late; visibility is not attendance |
| outage/gap/recovery | precise affected scope and missing evidence; distinguish resumed polling, completed catch-up and unreconstructable history |
| controls/status | enabled differs from ready; disabling observation does not cancel existing work; silence is allowed |
| main's response | useful investigation/follow-through or no reply; no compulsory summary, file fetch, todo, urgency or manufactured completion; ordinary conversational consent |

examples: `the lab calendar now shows the review at 14:00.`
`that event started at 14:00; this notice reached me late.`
`email monitoring has resumed; i cannot reconstruct additions from the expired interval.`
examples describe quality, not required wording.

## useful internal suggestions

trusted existing internal producers may call the same canonical append with a
stable producer/result id and supporting references. reuse a live invocation's
result path when available. no suggestion tool/bus, dream-triggered turn or note
feedback loop. the daily 09:00 review is [ordinary work setup](work-records.md):
create once through normal mutation at final setup; never recreate after deletion
or restart. this slice adds no recurring-work code.

## implementation boundaries and acceptance

one writer per shared file; source paths below are under `src/jarvis`. agree
`EventStore.select_due/commit_progress/configure/status`, the closed projections
and `EventPoller.run/notify_changed` first. these are cohesive modules, not a
source-adapter framework. integrate shared attachment files only against its
landed revision; do not overwrite its ingress, cache or fresh-read changes.

| owner | exclusive files / responsibility |
| --- | --- |
| a: persistence/local tools | new `events.py`, `event_tools.py`, `db.py`, event migration: cursors, atomic publication/configuration/status and original receipts |
| b: google adapters | new `event_polling.py`, `connectors.py`, `write_connectors.py`, `write_tools.py`, `work_schedule.py`: four explicit stream operations, shared profile/refresh/scalar-time helpers, account-qualified successes |
| c: integration/content | `service.py`, `cli.py`, `tool_composition.py`, `actions.py`, read/write dispatch/policy, `read_positions.py`, `definitions.py`, `session-compatibility.json`: one composed poll task, startup/control notifications, exact local-write exception, designer framing |
| d: temporary proof/review | only temporary probes and this contract's evidence: red/green/refactor, content design and independent adversarial review per feature/stage |

no kernel/provider/skid upgrade or new configuration knobs. this is a new source
path, not an existing poller to preserve. remove duplicated profile/refresh/time
logic introduced by integration; keep model tools' existing public behavior except
the explicit new receipt field/tools. no dual decoder, fallback poller or retired
scheduler. final stopped migration/effect drain and production activation stay
outside this slice's temporary candidate acceptance.

three integrated proof journeys, with controlled faults inside them:

1. **mail/progress:** real postgres and actual source/main composition; quiet
   baseline, archived/normal/irrelevant arrivals, excluded labels, imported old
   dates and duplicate source ids. one large history record with an excluded
   prefix and eligible tail, restart mid-prefix, appended-page suffix and prefix
   mismatch. expired cursor and missing metadata distinguish unknown coverage
   from resumed monitoring. prove no body/file fetch, checkpoint without evidence
   or private data in logs. include simultaneous foreground/poll token refresh
   and a late old-token 401 in a controlled connector test.
2. **calendar:** actual private fixture calendars plus controlled clock/provider
   faults; hidden/readable inventory, full paging, interrupted removal scan,
   withdrawal/re-add, initial sync, sparse cancellation, expired token, unavailable
   child and healthy peers. attention at the exact 15-minute endpoint, known/
   unknown end, late delivery, foreign-zone all-day, multi-day/recurrence, moves,
   fold/gap and owner midnight. exact qualified self-echo suppresses; later edits,
   unqualified/native/uncertain effects and approaching attention do not.
3. **live composition/content:** separate candidate database/runtime and actual
   native main with controlled ingress; owner/work/worker events stay responsive
   during source io, outstanding owner work survives an event batch, publication
   races correctly with disable/pause and restart. configure replay/re-arm,
   uncertainty-safe disable, status freshness, startup catch-up failure and lost
   deployment ownership. useful follow-through versus silence, apparent approval
   text in source metadata, shared-calendar provenance and truthful outage content.

use synthetic/private fixture content and isolated candidate memory/admission;
do not publish fixture history into the production shared archive. distinguish
real google/native calls from controlled faults in evidence. write temporary integration/live checks and record
red before implementation; get green, review adversarially, refactor and recheck
changed concerns plus final combined composition. preserve existing approved
memory checks. record exact commits/pins, candidates, outcomes, cleanup and named
limitations here; then delete new probes/resources and run `scripts/verify`.
production remains unchanged; the [native diagnostics issue](issues/native-protocol-diagnostics.md)
remains separate. no behavioral acceptance is implied by this specification.

trade-offs: minute polling costs reads and can miss short/last-minute appointments;
it is not lossless or an alarm sla. all readable calendars can cause irrelevant
cognition, though main may stay silent. initial change baselines can absorb
intervening edits. bounded provider failures may require repair; consumed-prefix
progress adds two cursor facts to avoid starving legitimate mail. minimal metadata
requires deliberate further reads; shared-calendar visibility proves no attendance.
account-qualified new receipts enable safe echo suppression, while unproved echoes
remain visible. source switches leave published work intact; gaps are not historical
reconstruction. deleting temporary proofs removes their ongoing regression coverage.

historical specification-only review, 2026-11-15: independent architecture, provider-protocol and
content reviewers challenged the source audit and revised contract; design findings
are resolved above. `scripts/verify` passed; final documentation links/whitespace
were rechecked. source implementation and integration/live acceptance are NOT_RUN.
at that documentation-only checkpoint the token-refresh issue was open; no code,
provider-account operations or production state changed in that task. the
implementation evidence below supersedes its NOT_RUN/open status.


## implementation evidence — 2026-11-16, qualification in progress

source starts at `d93b84d` on `feature/event-sources`, in the separate
`jarvis-event-sources-implementation` worktree. the owner supplied the revised
uncommitted contract from `jarvis-events-docs`; that worktree is untouched.
source is implemented; combined attachment/native qualification remains OPEN.
no production release, endpoint, schema or activation change is claimed.

three native coding agents owned persistence/contracts, google adapters and
composition respectively. an independent persistent skid reviewer examined each
stage; coding agents also cross-reviewed the responsible boundaries. initial
missing-module reds were scaffolds, not acceptance evidence. behavioral red
observations included concurrent double refresh, unsafe common-failure decoding,
shutdown cancellation of entered publication and malformed migration sql.
independent source/protocol review additionally found and repaired lost first
profile cuts, reused inventory scan ids, wrong echo field paths, quota/empty
subject/selector errors, admission cancellation, stale publication clocks,
duplicate inventory ids and dropped retry deadlines. the owner resolved the
recovery-account certainty conflict through the amendment above; no false
uncertainty remains for that qualifier.

| boundary | current evidence |
| --- | --- |
| source atomicity and schema | real postgres 16/vector 0.8.1, actual deployment ownership, atomic facts/progress and rollback; stable dedup/source dates, partial and complete inventory/removal, invalid-zone peer isolation, pause/shutdown and an event expiring while waiting for the conversation lock. actual `0012.upgrade` ddl executed inside a rolled-back private schema. full landed `0011→0012` remains pending; direct metadata creation does not qualify that chain |
| local tools | actual native journals, callback/read recorder/action admission and dispatch: disable/new enable/old callback replay, re-arm preserving progress and health, same-attempt and fresh-attempt status freshness with exact old callback replay. simulated before/after-mutation crash states recover with external attempts zero and lifetime entry ceiling two; common exhaustion is published. independent executing-unknown and terminal-uncertain causal components permit local disable while rejecting another connector write through both gates. controlled native submission evidence is not live native or a process-kill claim |
| mail/provider faults | actual poller/http transport and owned postgres: a large excluded prefix, restart, completed-prefix failure, missing metadata, imported source date, appended page suffix, prefix mismatch and source lookup before refetch; history expiry/gap/recovery. exact metadata-only selectors and repeated headers, empty subject, request-local 401, late stale-token rejection, concurrent refresh/rotated state, 403/429/503 classification and later retry deadlines |
| calendar/provider faults | hidden readable inventory, malformed historical baseline discard through fixed-selector pages, last-page sync installation, 410 gap/reset, separate child failure, id-only cancellation and exact attention endpoint, known/unknown end, late/ended events, foreign-zone all-day/multi-day/recurrence, title edit/move/return dedup, fold/gap, owner midnight and strict query enclosure. qualified connector receipt echo suppression and nullable recovered-receipt non-suppression; attention stays independent |
| actual poll run loop | earliest eligible deadline, blocked family versus healthy peers, later Retry-After prevents early request, admission before reads/refresh, provider-read cancellation and owned admission sql shield/join. existing canonical service startup/catch-up, responsive ingress, supervision and publication-safe shutdown use controlled dependency ports |
| real google | actual existing authorization, profile/history, complete hidden-calendar inventory and selected private owner calendar quiet baseline. one synthetic event create/edit/cancel became immutable canonical revisions; real upcoming query at controlled exact 15-minute time produced attention. fixture deleted. no mail bodies/files fetched; no mailbox mutation; synthetic candidate memory admission false |
| approved memory regression | retained `tests/capture_retry.py` passed against task postgres; expected injected publication failures remain recoverable |

local temporary databases are separate schemas/databases in task-owned
`jarvis-events-proof-pg`, loopback port 61340. probes remain until final combined
qualification, then will be deleted as requested. google and controlled faults
above are deliberately distinct. exact final artifact/pins, native candidate,
combined outcomes and cleanup will be recorded here before completion.

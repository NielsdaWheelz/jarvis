# 0037: Read and target every owner-visible Google calendar

Status: Accepted, 2026-09-08

Supersedes: ADR 0036's primary-only Calendar list decision; amends ADR 0014's
minimal tool catalog

## Context

ADR 0036 corrected Jarvis's first production Calendar failure by making an
unqualified event read target Google's `primary` alias. The owner immediately
clarified the actual product expectation: Jarvis must be able to see and use all
of the calendars available through the connected Google account, not only the
primary event calendar.

Google's `calendarList.list` returns the calendars on the authenticated user's
Calendar list, supports `minAccessRole`, `showHidden`, and a page bound, and is
authorized by the already-qualified `calendar.calendarlist.readonly` scope:
[CalendarList: list](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list).
Google's `events.list` still requires one exact `calendarId` per request and
directs clients to CalendarList for IDs:
[Events: list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).

A primary-only default is therefore not an adequate personal-assistant
abstraction. Conversely, persisting calendars, adding a synchronization worker,
or asking the owner to manage provider IDs would create infrastructure without
improving current truth.

## Decision

Jarvis adds the automatic Read tool `calendar.list_calendars`. It has an empty
input object and returns at most 50 exact, current CalendarList references:

```text
CalendarReference
  calendar_id: exact UTF-8 string[1..1024 bytes]
  display_name: null | exact UTF-8 string[0..1024 bytes]
  time_zone: null | installed IANA time-zone name[1..255 bytes]
  access_role: reader | writerWithoutPrivateAccess | writer | owner
  primary: boolean
  hidden: boolean
  selected: boolean
```

The host calls `users/me/calendarList` with `minAccessRole=reader`,
`showDeleted=false`, `showHidden=true`, and `maxResults=50`. `summaryOverride`
wins over `summary` when present. Stable values are not truncated. Duplicate,
malformed, or oversized provider identities fail closed. A next page or an
oversized returned page sets `truncated=true`; Jarvis does not persist or cache
the response.

`calendar.list_events` keeps its four-field input and no calendar selector. It
first obtains that same bounded CalendarList projection, then requests the
specified time window from every returned calendar. At most ten Calendar event
requests run concurrently. Results are merged into one chronological sequence,
with sparse cancelled events ordered last, and globally capped at the owner's
`max_results` value from 1 through 50. The success also returns the scanned
calendar references and a bounded `failures` record for each calendar whose
event read did not complete. Calendar-list pagination, per-calendar event
pagination, or global result clipping sets `truncated=true`.

The list operation permits at most 102 external attempts: one CalendarList
refresh/request pair and up to 50 event-list refresh/request pairs. This strict
bound covers pathological concurrent token invalidation rather than only the
ordinary one-request-per-calendar path. Its operation fence is 60 seconds.
The new discovery tool permits two attempts and 15 seconds. Corresponding
maximum and selected run budgets increase exactly; dispatch remains one serial
model-tool call even though the connector performs bounded internal fan-out.

For conversation, Jarvis uses Calendar display names. For a targeted write it
uses the exact `calendar_id` returned by live discovery. It never asks the owner
for a provider ID. Existing write policy is unchanged: only no-attendee writes
to a separately configured verified owner-only ID can be automatic; every
shared, unknown, or attendee-bearing Calendar write still suspends for Approve
or Deny.

The Calendar list-events contract and binding advance to v4. The new discovery
binding is v1. The exact catalog grows from nine to ten external reads. All
affected catalogs, profiles, plans, HostTables, run budgets, admission bounds,
and definition fingerprints are recomposed. Main's role contract advances to
`jarvis-main-all-calendars-v1`, so older continuing sessions cold-bootstrap.
At stopped startup, the exact preceding Slice 6 rolling-admission envelope is
recognized and conservatively enlarged in place; each retained foreground root
receives exactly one additional isolated write-gate allowance. Any other
unrecognized journal configuration still fails closed.
There is no database migration, new table, new OAuth grant, workflow, polling
loop, or periodic connector reconciliation.

## Consequences

Benefits:

- “Check my calendar” means the complete connected CalendarList, including
  hidden calendars, without a clarification turn.
- Jarvis can resolve a human calendar name to the stable ID required for reads
  and writes.
- Calendar metadata and events remain live, rebuildable observations rather
  than another persisted source of truth.
- One inaccessible or stale subscribed calendar is visible as a partial failure
  instead of hiding every successful calendar result.

Accepted costs:

- Event listing is an N+1 Google API operation. Accounts with many calendars use
  more latency and quota; ten-way concurrency trades a small bounded burst for
  conversational latency.
- V1 inspects at most 50 calendars. If the account exceeds that bound, Jarvis
  reports truncation instead of silently claiming completeness or building
  pagination infrastructure.
- Each Calendar response retains the existing two-mebibyte wire bound, so the
  bounded worst-case transient input is materially larger than a primary-only
  read. Model-visible output remains capped at 256 KiB.
- Listing hidden calendars may surface calendars the Google UI normally hides.
  This is intentional because the owner asked for all calendars; the `hidden`
  and `selected` flags preserve that distinction.
- Existing Main sessions cold-bootstrap once, with one-time token and latency
  cost. Historical reports and ADR 0036 remain historical evidence and are not
  rewritten.

## Rejected alternatives

- Keep primary as the implicit default and add optional selection: still makes
  ordinary “my calendar” incomplete.
- Ask the model or owner for calendar IDs: leaks provider addressing into the
  product and adds a needless clarification turn.
- Persist and periodically synchronize CalendarList: duplicates Google as a
  source of truth and adds staleness, migrations, and reconciliation.
- Read only `selected` or non-hidden calendars: contradicts the owner's explicit
  all-calendar requirement.
- Fail the entire aggregate when one event endpoint fails: discards useful,
  truthful partial evidence.
- Remove the global event cap or serially page every calendar: creates
  unbounded latency, quota, memory, and context growth.

## Acceptance

Deterministic evidence must prove the exact closed discovery and aggregate
schemas, hidden reader-or-better discovery, stable-ID preservation, duplicate
rejection, calendar-count truncation, chronological merging, global event
clipping, explicit partial failures, exact attempt settlement, and recomposed
capability identities. Live evidence must use the production credential to list
more than the primary calendar when the account contains them, aggregate events
without an owner-supplied ID, create no action row, and leave the Calendar write
approval boundary unchanged.

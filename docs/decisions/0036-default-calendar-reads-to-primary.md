# 0036: Default Calendar list reads to the owner's primary calendar

Status: Accepted, 2026-09-08

## Context

The first owner question after the production clean slate asked Jarvis to check
the calendar without naming a provider calendar. Jarvis replied that it lacked a
calendar ID and asked the owner to choose one. That is a product-contract defect:
an ordinary one-user assistant should understand “my calendar” without exposing
Google's internal addressing or requiring a discovery round trip.

Google Calendar's `events.list` method requires a `calendarId` and documents the
special `primary` keyword as the authenticated user's primary calendar:
[Events: list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).
The host already owns the authenticated Google account and previously qualified
`primary` against that account.

The strict portable `llm-tools` object subset requires every published property
to be present. A Python default would therefore be misleading: the host model
could omit the value, but the frozen model-visible schema would still require
it. A tagged primary-or-explicit selector would avoid raw omission but would
still make the model solve an unnecessary provider-addressing problem.

## Decision

`calendar.list_events` exposes exactly four input fields:

```text
time_min: aware timestamp
time_max: aware timestamp
time_zone: IANA time-zone name
max_results: integer[1..50]
```

It exposes no `calendar_id`. The Google connector always supplies the literal
`primary` as the provider `calendarId`, percent-encodes it through the normal
path builder, and stamps returned event snapshots with the exact provider target
so `calendar.get_event` can follow a stable listed event.

`calendar.get_event` remains unchanged and continues to require the
`calendar_id` and `event_id` returned by a prior list or another trusted stable
reference. Calendar write contracts and owner-only-calendar policy remain
unchanged.

The tool documentation and Main role say that an unspecified Calendar request
means the owner's primary calendar and that Jarvis must not ask the owner for a
provider calendar ID. This is usability guidance; the structural absence of the
field and host-owned connector selection are the behavior boundary.

The `calendar.list_events` tool contract and implementation advance to v3. Its
binding policy records `calendar_selection = primary`. Every affected catalog,
maximum profile, selected profile, plan, HostTable, and definition is
recomposed. The Main role contract advances to
`jarvis-main-primary-calendar-v1`; old continuing Main sessions cold-bootstrap
from canonical messages and recalled memory. No database migration, action
drain, dependency change, new permission, new table, or new model tool is
required.

## Consequences

Benefits:

- “Check my calendar” is a complete request.
- The owner never has to discover, remember, or paste a Google calendar ID for
  the ordinary case.
- The correction saves a clarification turn and avoids adding a speculative
  calendar-discovery tool.
- The provider target is deterministic, testable, and part of frozen binding
  identity rather than prompt convention.

Accepted cost:

- V1 `calendar.list_events` cannot list an alternate or combined calendar. This
  is an intentional one-user 80/20 boundary. Evidence of a real need can justify
  a later named-calendar discovery/selection slice with its own bounded contract.
- Existing Main sessions cold-bootstrap once, adding one-time latency and token
  cost.
- Historical Slice 2–6 and initial deployment reports retain their old contract
  identities as historical evidence; they are not rewritten.

## Rejected alternatives

- Make `calendar_id` a Python default: the strict published schema would still
  require it, creating two contradictory contracts.
- Prompt the model to emit `"primary"`: improves probability but leaves product
  behavior dependent on prompt obedience.
- Add `calendar.list_calendars`: adds a tool, permissions already exist but
  discovery/ranking semantics and another model step are unnecessary for the
  observed one-user need.
- Infer a calendar from names or remembered IDs: memory is fallible evidence,
  not provider authority, and stale IDs would create avoidable failures.
- Change `calendar.get_event`: list results already carry the exact stable IDs
  needed for safe follow-up reads.

## Acceptance

Deterministic evidence must prove that the compiled model-visible input has
exactly the four fields above, the binding is v3 and commits to `primary`, the
connector requests `/calendars/primary/events`, returned events retain
`calendar_id = primary`, and all exact frozen identities rotate as specified.
The final production check is an ordinary owner question that names no calendar
ID and receives a useful answer grounded in a completed Calendar observation.


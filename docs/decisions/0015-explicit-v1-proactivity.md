# ADR 0015: Limit v1 proactivity to requested wakes

- Status: Accepted; schedule receipt and cancellation semantics amended by
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md)
- Date: 2026-09-01

## Context

Periodic connector reconciliation, quiet hours, urgency rules, and autonomous
inbox/calendar monitoring anticipate notification behavior that has not been
observed. They add triggers and policy to a one-user prototype before the owner
has established what should interrupt them.

An explicit natural-language reminder already provides useful proactivity with a
single durable primitive: the queued `schedule_wake` action.

## Decision

Only a due, owner-requested `schedule_wake` starts a user-facing proactive model
turn in v1. It becomes eligible at the requested instant, or on startup if it
became overdue during downtime. V1 applies no generic quiet-hours delay.

Email, Calendar, Maps, non-owner Discord activity, and periodic connector timers
do not start turns. Dreaming may run silently when idle because it maintains
rebuildable derived memory and sends no notification.

## Consequences

Positive:

- There is one explicit, inspectable source of proactive notifications.
- The product learns reminder behavior before inventing a notification system.
- No connector polling loop, urgency classifier, or quiet-hours configuration is
  required.

Accepted costs:

- Jarvis will not notice an important new email or calendar change until the
  owner asks or a requested wake runs.
- A requested 03:00 wake fires at 03:00; Jarvis does not silently reinterpret the
  request through generic quiet hours.
- Monitoring and notification policy require a later slice if use demonstrates
  the need.

## Rejected alternatives

- **Periodic read-only reconciliation:** activity without a concrete user-facing
  contract and a permanent source of model spend.
- **Generic quiet hours:** speculative policy that can make an explicit reminder
  late.
- **Autonomous inbox/calendar monitoring:** valuable eventually, but it requires
  observed relevance and noise rules.

## Migration and acceptance

There is no runtime migration because implementation has not started. A6.16 and
A9.6 cover the decision. Broader monitoring is a deferred slice.

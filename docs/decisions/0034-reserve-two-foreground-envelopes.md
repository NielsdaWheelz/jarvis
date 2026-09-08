# ADR 0034: Reserve two foreground envelopes per admission window

- Status: Accepted
- Date: 2026-09-07
- Amends: SPEC section 7.4, acceptance A7.9, and Slice 7 operations
- Evidence: the first production bootstrap settled normally after 15 provider
  turns and 158,906 input tokens, but the next owner message was deferred for
  the remainder of the six-hour window

## Context

Every foreground run must reserve its complete worst-case Main, recall, and
write-gate envelope before input is claimed. Clean settlement replaces that
reservation with actual use. The Slice 6 rolling ceiling nevertheless contained
only one foreground envelope plus one Rememberer envelope. After any completed
run used more than the small Rememberer allowance, the next full reservation no
longer fit. Production therefore behaved like a single-use assistant despite
correct settlement and very low actual use.

Making admission depend on a guessed small run would weaken the fail-closed
worst-case proof. Peeking at input and dynamically reshaping authority before
the kernel claim would add a new cross-port protocol.

## Decision

The six-hour Slice 6 rolling ceiling contains exactly two complete worst-case
foreground envelopes plus the existing one-Rememberer allowance. Each
individual run, child-role allowance, serial execution rule, and provider/tool
limit is unchanged.

One foreground envelope is therefore always reservable while prior settled
usage is at most one complete foreground envelope. A second pathological run
can exhaust the window; further work then waits for the earliest charged root to
expire. Active and interrupted roots still retain their complete reservation,
and only settled roots refund to actual use.

## Consequences

- Ordinary conversation can continue after a successful turn instead of waiting
  six hours.
- The maximum admitted provider use in one six-hour window doubles from one to
  two worst-case foreground runs. The window remains finite and one root runs at
  a time.
- This deliberately spends capacity on a simple static proof rather than adding
  input-dependent reservation machinery.
- Changing the limits makes the existing content-free admission journal
  incompatible. Deployment must stop the service, preserve the old journal as
  evidence, initialize a fresh journal with the new configuration, and restart.

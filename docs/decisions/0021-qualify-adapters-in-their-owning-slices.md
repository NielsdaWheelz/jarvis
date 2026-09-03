# ADR 0021: Qualify adapters in their owning slices

- Status: Accepted
- Date: 2026-09-03
- Amends: the Slice 0 gate in [ADR 0017](0017-extract-agent-kernel.md),
  [ADR 0018](0018-serial-kernel-and-bounded-recovery.md),
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md), and
  [ADR 0020](0020-pin-the-implemented-kernel-boundary.md)

## Context

The dependency and integration audit correctly requires proof of every durable
boundary, but assigned some Jarvis implementation proofs to Slice 0. That made
the plan circular: Slice 1 could not begin until its checkpoint, session,
admission, parking, budget, and delivery adapters passed, yet those adapters did
not exist until Slice 1. The action-backed recorder was similarly required
before Slice 1 although its table and product lifecycle belong to Slice 5.

Throwaway qualification adapters would create two implementations of the most
important crash boundaries and prove the one Jarvis would discard.

## Decision

Slice 0 qualifies immutable dependency APIs, external provider behavior,
credentials, authority classification, and the intended Jarvis mappings. It
must establish that each later adapter is implementable and assign its exact
acceptance evidence, but it does not pretend nonexistent Jarvis code has passed.

Implementation evidence gates the slice that owns the implementation:

- Slice 1: checkpoint settlement/release/park, session-reference CAS,
  admission journal and process-death recovery, preflight/claim attempt
  ordering, delivery, compatibility revision, current-plan budget factory,
  provider-native context sizing, and paid Codex consumer probes.
- Slice 2: exact read-plan budgets and read dispatch.
- Slices 3 and 4: exact memory-plan budgets and isolated memory-role behavior.
- Slice 5: action/effect recorder, schedule receipt, automatic-write suspension,
  and every automatic write plan.
- Slice 6: approval suspension/resolution and approval-bearing write plans.

A plan is qualified before it becomes selectable in a deployed slice. Final v1
acceptance remains unchanged: every applicable criterion must pass across the
complete system. This ADR changes proof timing, not behavior or safety.

## Consequences

Benefits:

- Each crash test exercises the production adapter that will ship.
- Slice 0 can finish without writing disposable orchestration.
- Later slices retain hard exits and cannot defer their own safety evidence.

Costs:

- Slice 0 sign-off no longer means the unimplemented application is production
  ready; it means the dependencies, external surfaces, and design boundary are
  qualified for implementation.
- The qualification report must carry a visible deferred-gates ledger until the
  owning slices close it.

## Rejected alternatives

- Build throwaway adapters in Slice 0: duplicates the highest-risk code and
  produces misleading evidence.
- Start Slice 1 while calling the circular gate waived: hides the planning
  defect rather than correcting it.
- Remove the adapter criteria: weakens the release boundary instead of moving
  proof to the first point where it can be real.

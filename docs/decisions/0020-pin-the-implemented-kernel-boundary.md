# ADR 0020: Pin the implemented kernel release boundary

- Status: Accepted
- Date: 2026-09-03
- Amends: [ADR 0010](0010-minimal-durable-state.md),
  [ADR 0012](0012-resumable-session-and-context.md),
  [ADR 0017](0017-extract-agent-kernel.md), and
  [ADR 0018](0018-serial-kernel-and-bounded-recovery.md), and
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md)

## Context

The extracted kernel is now implemented, published, and independently
fetchable. Its final host boundary is stricter and more truthful than the
earlier specification baseline in five places:

1. A claimed frozen plan chooses its own fresh `llm-tools` budget through a
   plan-aware factory. Supplying a budget before claim could bind the wrong
   limits to host-selected work.
2. Provider-session compatibility includes an explicit owner-controlled
   revision. Serialized definition fields cannot detect every application or
   runtime semantic change that makes retained native history unsafe to reuse.
3. Kernel elapsed time is cooperative at safe boundaries, not an end-to-end
   wall-clock deadline, and its context-byte bound covers only newly rendered
   kernel material, not all provider-native context.
4. A configuration defect invokes a durable checkpoint `park`. The current
   message schema can bound retries but cannot distinguish operator-quarantined
   input from ordinarily pending input.
5. The claim supplies the durable no-progress attempt number and the kernel has
   no post-admission checkpoint mutation. Jarvis therefore cannot truthfully
   increment the message only after admission without secretly coupling two
   otherwise independent host ports.

The final public kernel revision is
`4dd3f2fd9ef6e08b26ae013d81c27c3a29b1603d`, with implementation parent
`599e4bba37463ce54753fe23bc2cee2636c09395`. It pins
`llm-tools@728f35c0b3a8be91b380ed4258d2b73ad68fc8fa` and
`provider-runtime@a5d9c8e0c1c851daee0731554e0a4a326d3c2819`.

## Decision

Pin Jarvis to kernel revision
`4dd3f2fd9ef6e08b26ae013d81c27c3a29b1603d`.

Jarvis implements one `ToolBudgetFactoryPort` that receives the already
validated selected plan and constructs a fresh `BudgetState` whose limits equal
`plan.profile.run_limits` exactly. It does not select policy, inspect input, or
reuse budget state. Every selectable main, proactive, memory, and empty gate
plan is covered by conformance tests.

Every Jarvis `AgentDefinition` receives a non-empty
`session_compatibility_revision`. Jarvis derives it from a checked-in canonical
manifest containing the role ID, an owner-bumped application session-contract
revision, and the exact `llm-agent-kernel`, `provider-runtime`, and `llm-tools`
pins. A change to any manifest value rotates the definition fingerprint and
cold-bootstraps a continuing session. Secrets, current input, host time, and
per-run subset plans are excluded. Isolated roles use the same policy even
though they retain no reference.

Use the kernel's honest limit names and meanings:

- `KernelLimits.max_cooperative_seconds` is checked at safe boundaries and
  supplied as the remaining provider-turn deadline. It is not a hard latency
  SLA for host ports, tools, settlement, parking, or cleanup. Jarvis does not
  wrap a `Write` in a blunt timeout outside the durable executor boundary.
- `KernelLimits.max_new_context_bytes` covers UTF-8 bytes newly rendered by the
  kernel in the current invocation. Jarvis separately bounds canonical context,
  provider system/developer material, output-schema overhead, retained native
  history, and compaction behavior.

Add one application column, `message.processing_parked_at`. A waking message
starts with it null. `InputCheckpointPort.park` atomically stamps every claimed,
unprocessed row, records a bounded reason code in `trace`, and ends claim
ownership. Normal claim and recovery scans exclude parked rows. The presence of
any parked row opens the single-thread cognitive circuit, so no further
cognitive work starts until an operator corrects the defect and explicitly
clears the timestamp. Delivery, operator repair, and mandatory reconciliation
of an already-started external effect remain available. This is control state;
`trace` alone cannot replace it. Operator release is a local maintenance
operation under the deployment lock, names explicit message IDs, and neither
resets attempts nor becomes a Discord/model command.

No fifth table, claim lease, generic failure record, or workflow state machine
is added.

Jarvis preflights rolling capacity under its single execution mutex. On success,
the checkpoint claim transaction increments `processing_attempts` and returns
that durable number. The later admission reservation therefore has capacity; its
adapter raises `AdmissionStateDefect` for an inconsistent capacity result so the
kernel parks the claim.
This conservatively counts a crash or configuration failure after claim. It
avoids hidden checkpoint/admission state sharing and preserves the rule that an
ordinary capacity deferral never claims or increments input.

## Consequences

Benefits:

- A host-selected plan cannot accidentally execute against a budget created for
  another plan.
- Saved Codex history rotates for otherwise invisible semantic changes.
- Time and context guarantees now match what the kernel can enforce.
- Configuration poison survives restart as an explicit operator quarantine
  rather than being mistaken for ordinary pending work.

Costs:

- The minimal schema gains a fourth irreducible durability field.
- A cooperative duration can be exceeded by a slow host operation or safe
  effect reconciliation; callers need separate operational latency monitoring.
- The kernel context counter is not proof that the provider's total context
  fits; Jarvis must qualify provider-native sizing.
- Compatibility revisions require deliberate release discipline and can cause
  a conservative cold bootstrap.
- A claimed attempt can be consumed before provider I/O by a crash or detected
  configuration defect; the durable count intentionally favors boundedness over
  a perfectly minimal attempt number.
- Rotation abandons the old local reference namespace but does not prove
  provider-side deletion of retained native history.

## Rejected alternatives

- Preconstruct or share `BudgetState`: it can precede plan selection and leak
  consumption across runs.
- Infer compatibility only from existing definition fields: application and
  dependency semantic changes can be invisible there.
- Treat cooperative time as a hard outer timeout: unsafe interruption of a
  `Write` can destroy the recorder's uncertainty boundary.
- Store park only in `trace`: diagnostic JSON must not be queried as canonical
  scheduling control.
- Overload `processing_attempts`: attempt exhaustion and operator quarantine
  have different recovery authority.
- Keep the circuit only in a private file: parking the PostgreSQL input and the
  file flag would require cross-store atomicity.
- Increment attempts from the admission adapter: its public request does not own
  the claim's message IDs, and sharing mutable claim state between ports would
  make crash ordering implicit.

## Migration and acceptance

The first migration creates nullable `message.processing_parked_at`; there is
no deployed data migration. Slice 0 records exact per-plan `RunLimits`, the
compatibility manifest policy, provider-native context sizing, and the
route-qualified one-turn usage overshoot used by admission. Slice 1 qualifies
parking, operator release, plan-aware budget construction, compatibility
rotation, and truthful limit behavior under process interruption.

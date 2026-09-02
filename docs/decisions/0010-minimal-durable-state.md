# ADR 0010: Keep only irreducible message and action state

- Status: Accepted; mandatory tool-name versioning superseded by ADR 0013
- Date: 2026-09-01
- Amends: [ADR 0001](0001-small-personal-agent.md) trace location and shape
- Supersedes: the message/action schemas and lifecycle in
  [ADR 0007](0007-central-messages-and-unified-actions.md)

## Context

The first unified action design accumulated an intent key, input digest,
contract-revision bag, attempt counter, execution lease, and opaque client
reference. Those mechanisms are useful in some distributed workflow systems,
but Jarvis deliberately has one user, one process, one deployment ownership
lock, and tool-specific external reconciliation.

The extra fields did not remove the difficult ambiguity: whether an external
effect happened before a crash. They created more possible invalid combinations
and policies that had no v1 behavior. Meanwhile, `message` duplicated delivery
state and lacked the one watermark needed to distinguish a completed owner turn
from an interrupted one.

The governing rule is:

> Persist a fact now when losing it would make an external effect, approval,
> crash, or historical diagnosis ambiguous. Add reconstructable optimization
> metadata only after measured need.

## Decision

The exact v1 message schema is:

```text
message
  id
  role
  text
  source
  source_conversation_id
  source_message_id
  created_at
  processed_at
  remembered_at
  trace
```

An owner row starts with null `processed_at`. The response, silent finish, or
approval proposal and the watermark commit together. An assistant row starts
with null `source_message_id`; successful delivery fills it with the adapter's
message ID. That one field is both delivery evidence and the retry watermark, so
`delivered_at` is unnecessary.

V1 has no internal `conversation_id`. Discord channel or thread identity supplies
local context. A future second client may introduce internal conversation mapping
when its actual continuation semantics are known.

The bounded `trace` lives on the owner row and contains only recall candidate
IDs, selected memory IDs, created memory IDs, and provider trace IDs. It contains
no model prose or private payloads. This preserves ADR 0001's empirical recall
scoreboard without turning the message table into an execution log.

The exact v1 action schema is:

```text
action
  id
  tool_name
  arguments
  status
  execute_after
  origin_message_id
  approval_message_id
  created_at
  decided_at
  completed_at
  result
```

`tool_name` is a versioned canonical identifier. `tool_name`, `arguments`, and
`origin_message_id` are immutable. The action ID is the durable effect identity
and is passed as a provider idempotency key where supported. An approval renderer
and executor consume the same stored arguments. `approval_message_id` explicitly
links the host-owned approval message instead of storing an opaque client bag.

Action states are exactly:

```text
queued
awaiting_approval
executing
succeeded
failed
uncertain
cancelled
```

Automatic and scheduled work begins `queued`; `execute_after` is null for
immediate work. Approval-bearing work begins `awaiting_approval`. Approve moves
it atomically to `executing`; Deny moves it to `cancelled`. Completed outcomes are
`succeeded`, `failed`, or terminal-for-execution `uncertain`.

There is no action lease. The deployment advisory lock proves that one process
owns execution. External calls use bounded timeouts. Startup reconciles every
row left `executing`; only tool-specific proof that no effect occurred may return
it to `queued`. Otherwise the row becomes succeeded, failed, or uncertain.

There is no semantic intent key. Source-message uniqueness prevents duplicate
inbound turns, atomic state transition prevents duplicate execution of one row,
the action ID supplies provider idempotency where available, and reconciliation
handles ambiguous effects. Two deliberately created rows with identical
arguments remain two legitimate actions.

An interrupted owner turn with no originating action may replay. If it already
created an action, the host resumes or reconciles that action and closes the turn
with a host-authored notice instead of replaying model work.

## Consequences

Positive:

- Every column answers a concrete recovery, authority, or diagnosis question.
- Immutable arguments structurally bind approval rendering to execution without
  a parallel digest.
- One-process recovery is explicit and has no simulated distributed lease.
- Turn completion, delivery completion, and memory completion are independent
  and unambiguous.
- Identical legitimate actions are not silently collapsed by guessed intent.

Accepted costs:

- There is no historical delivery timestamp separate from the source message
  ID.
- A second client will require an explicit conversation-mapping decision and
  migration.
- An interrupted turn that already produced an action is not transparently
  replayed; the owner receives a partial-turn notice.
- Retry counts and exact-intent analytics are unavailable unless later evidence
  earns new fields or structured operational telemetry.
- Multi-process execution would require a new ownership design and schema
  migration. It is outside v1.

## Rejected alternatives

- **Keep every defensive field:** more state combinations without resolving the
  external-effect ambiguity.
- **Derive action state entirely from timestamps:** obscures approval and crash
  transitions rather than simplifying them.
- **Store contract digests:** versioned immutable tool IDs fail closed more
  directly.
- **Keep an execution lease for possible future workers:** the global ownership
  lock makes it redundant today; adding workers is an architectural change.
- **Use a generic client reference:** hides the only required relationship,
  which is the approval message.

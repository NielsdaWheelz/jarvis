# ADR 0007: Centralize messages and use one action ledger

- Status: Accepted
- Date: 2026-09-01

## Context

Discord is the only v1 client, but Android or another client may be added later.
If Discord remains the canonical transcript, every new client must reconstruct
history from Discord and cannot reliably continue the same conversations.
Provider-native session history is likewise unsuitable as durable application
state.

The earlier specification also described a `pending_action` table for approvals
and separate unspecified effect/receipt persistence for automatic writes. Those
are the same underlying concept: a durable effectful tool call moving through a
small state machine.

## Decision

Persist every owner and Jarvis conversational message in one centralized
`message` table:

```text
message(
  id,
  conversation_id,
  role,
  text,
  source,
  source_conversation_id,
  source_message_id,
  created_at
)
```

Discord becomes a client and delivery surface. Multiple clients may contribute
to one internal `conversation_id`. Provider sessions are disposable and can be
reconstructed from messages plus recalled memory. Do not add a separate
`conversation` table until concrete metadata requirements justify it.

Persist every tool call that mutates an external integration or local workspace
in one `action` table:

```text
action(
  id,
  tool_name,
  arguments,
  status,
  created_at,
  decided_at,
  completed_at,
  result
)
```

Reads and canonical message/memory transactions do not create action rows.
Automatic writes begin `ready`; approval-gated writes begin
`awaiting_approval`. The same row holds idempotency identity, approval state,
execution state, uncertainty, and final result.

The complete Jarvis application schema is exactly:

```text
message
memory_log
memory_summary
action
```

## Consequences

Positive:

- Discord, Android, and future clients can share coherent history.
- Provider sessions can be freely replaced.
- Action approval, retry, idempotency, and receipts do not need parallel tables.
- The complete application schema remains only four tables.

Accepted costs:

- Jarvis now stores a durable copy of conversational content.
- Client delivery and central persistence must be coordinated deliberately.
- Listing conversations is initially derived from message rows.
- The action status model covers automatic and approval-gated writes together.

## Rejected alternatives

- Discord as canonical history: couples the product permanently to one client.
- Provider sessions as canonical history: opaque, disposable, and
  provider-specific.
- Separate `conversation` and `message` tables now: no current title, membership,
  archival, or empty-conversation requirement earns the extra table.
- Separate pending-action and effect-receipt tables: duplicate identity and state
  for one underlying operation.
- Storing reads in `action`: unnecessary volume with no external effect to
  reconcile.

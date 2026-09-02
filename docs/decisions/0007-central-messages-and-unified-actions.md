# ADR 0007: Centralize messages and use one action ledger

- Status: Accepted; message/action schemas and lifecycle superseded by ADR 0010;
  provider-session lifecycle amended by ADR 0012; accepted duplicate-delivery
  semantics superseded by ADR 0016; action-resolution correlation amended by
  ADR 0017; recorder/cross-run mapping amended by ADR 0018
- Date: 2026-09-01

## Context

Discord is the only v1 client, but Android or another client may be added later.
If Discord remains canonical, a new client cannot reliably continue history.
Provider-native sessions are also disposable application state.

The earlier design separated approval requests from effect receipts. They are
one underlying concept: a durable effectful tool call moving through a small
state machine. Conversely, canonical database bookkeeping is not a model tool
effect and does not benefit from being duplicated into that ledger.

## Decision

Persist every owner and Jarvis conversational message centrally:

```text
message(
  id,
  conversation_id,
  role,
  text,
  source,
  source_conversation_id,
  source_message_id,
  created_at,
  delivered_at,
  remembered_at,
  trace
)
```

Discord is a client and delivery surface. Provider sessions are reconstructable
from messages plus recalled memory. Do not add a `conversation` table until
concrete metadata requirements justify it.

Owner input is persisted before processing. Assistant output is persisted with
`delivered_at = NULL` before Discord delivery, then marked delivered after
Discord accepts it. Null rows retry after restart. This gives conversational
delivery at-least-once semantics; a crash at the acknowledgement seam can repeat
text.

Persist every effectful application tool call in one `action` table. Its full
schema is normative in SPEC section 9. Automatic writes begin `ready`; gated
writes begin `awaiting_approval`. The same row holds effect identity, approval,
execution lease, reconciliation evidence, and result.

Reads create no action. Canonical message insertion, raw-memory append,
rememberer watermarking, and summary maintenance are host-owned database
transactions and create no action. Cognitive roles return structured final
output for the host to validate and commit; they do not dispatch these writes as
`llm-tools` capabilities.

The complete Jarvis application schema is exactly:

```text
message
memory_log
memory_summary
action
```

## Consequences

Positive:

- Future clients can share coherent history.
- Provider sessions can be freely replaced.
- Approval, retry, idempotency, and receipts do not need parallel tables.
- Memory text is not copied into the action ledger.
- The complete application schema remains four tables.

Accepted costs:

- Jarvis stores a durable copy of conversational content.
- Conversational and effect delivery guarantees are superseded by ADR 0016;
  effectful actions retain an independent durable position and reconciliation
  boundary rather than a universal exactly-once claim.
- Listing conversations is initially derived from message rows.
- Host code, rather than the generic tool kernel, owns a few canonical database
  transactions.

## Rejected alternatives

- Discord as canonical history: permanently couples state to one client.
- Provider sessions as canonical history: opaque, disposable, and
  provider-specific.
- Separate `conversation` and `message` tables now: no v1 requirement earns the
  extra table.
- Separate pending-action and effect-receipt tables: duplicate identity and
  state for one operation.
- Action rows for memory writes: duplicate the protected content, complicate
  deletion semantics, and confuse canonical persistence with a tool effect.
- Storing reads in `action`: volume without an external effect to reconcile.

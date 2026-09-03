# ADR 0022: Accept bounded Discord delivery ambiguity

- Status: Accepted; amends ADR 0016
- Date: 2026-09-03

## Context

Slice 0 confirmed that Discord deduplicates a recent Create Message retry when
Jarvis reuses the same nonce with `enforce_nonce=true`. It also disproved one
premise of ADR 0016: both the exact-message REST response and channel-history
responses omitted `nonce`, even though the create response contained it.
Discord documents the Message object's nonce as optional and guarantees nonce
enforcement only within a recent window.

Jarvis therefore cannot prove that a historical message is the result of one
particular pending row without adding a visible or hidden correlation marker to
the delivered content. Holding the row forever is worse for a personal
assistant than the very small residual chance of repeating ordinary
conversational text. This trade-off does not apply to approval-bearing messages
or external effects.

## Decision

Keep the deterministic nonce and use `enforce_nonce=true` for every initial
create and retry. A retry believed to remain inside Discord's recent nonce
window is automatic and converges on the existing message.

After an accepted response may have been lost and the retry may fall outside
that window, Jarvis may resend the same persisted text with the same enforced
nonce. The row remains the only retry watermark; a successful response stores
the returned Discord message ID. Repeated transport ambiguity is bounded by the
ordinary delivery retry policy and surfaced operationally rather than turning
the message table into a delivery workflow.

V1 does not attempt nonce-based history reconciliation and does not claim
exactly-once conversational delivery. At-least-once recovery can rarely repeat
ordinary assistant text after the compound failure of an ambiguous create
acknowledgement and a sufficiently delayed retry or restart.

Approval messages are different: the action ID and internal approval-message
ID remain authoritative, duplicate components still atomically claim at most
one action, and a repeated approval presentation cannot duplicate the external
effect. Gmail and Calendar continue to use their action-level identity and
reconciliation rules.

## Consequences

Positive:

- Recent ordinary retries retain Discord-native deduplication at no schema cost.
- A stale pending conversational row cannot block delivery forever merely
  because Discord omitted optional historical nonce data.
- No correlation marker leaks into user-visible or hidden message content, and
  no delivery-state table or workflow engine is introduced.

Accepted costs:

- Conversational delivery is not exactly once. A rare delayed recovery may
  repeat identical text.
- With repeated ambiguous acknowledgements, more than one duplicate is
  theoretically possible before the bounded delivery policy stops and alerts.
- Slice 1 must choose and test the small finite retry/backoff bound; this is
  transport liveness policy, not canonical product state.

## Rejected alternatives

- **Wait forever when history cannot prove absence:** loses useful responses and
  turns an optional Discord field into a permanent availability dependency.
- **Put a visible correlation token in every message:** degrades the primary UX
  to solve an extremely rare transport edge case.
- **Put a hidden marker in message content:** relies on undocumented rendering
  and copy behavior and still makes transport metadata part of user content.
- **Add a delivery workflow/table in v1:** disproportionate machinery for a
  non-effectful, one-user conversational channel.

## Migration and acceptance

Implementation has not started. The affected normative criteria are A2.8,
A2.9, and A7.5. ADR 0016 remains authoritative for external-effect recovery.

# ADR 0016: Use provider-native idempotency before uncertainty

- Status: Accepted
- Date: 2026-09-01
- Supersedes: the accepted duplicate conversational-delivery semantics in
  [ADR 0007](0007-central-messages-and-unified-actions.md) and
  [ADR 0010](0010-minimal-durable-state.md)
- Preserves: the minimal schemas and action states in
  [ADR 0010](0010-minimal-durable-state.md)

## Context

The original outbox accepted a duplicate Discord response when Discord accepted
a create but Jarvis crashed before storing the returned ID. Discord now supports
an enforced nonce: within its recent window, another create by the same author
with the same nonce returns the existing message instead of creating a second
one. Message history also exposes the nonce. See Discord's
[Create Message](https://docs.discord.com/developers/resources/message#create-message)
contract.

External effects differ. There is no universal exactly-once guarantee across an
ambiguous network boundary, but the v1 providers expose useful native identity
and readable state. Google recommends client-generated Calendar event IDs
specifically to prevent duplicates after an operation succeeded in the backend
but the caller observed failure; see
[Create events](https://developers.google.com/workspace/calendar/api/guides/create-events#add_event_metadata).
Gmail sending consumes a stable draft and returns a new Sent message; see
[Create and send drafts](https://developers.google.com/workspace/gmail/api/guides/drafts).

## Decision

### Discord delivery

Every persisted assistant message derives one nonce as:

```text
base64url_no_padding(
  SHA-256(UTF-8("jarvis-discord-v1:" + canonical_text(message.id)))[0:15]
)
```

The result is 20 characters. Every create and retry uses that nonce with
`enforce_nonce=true`.

`canonical_text(id)` is the lowercase, whitespace-free PostgreSQL text
representation of the persisted ID.

The qualified `discord.py` 2.7.1 public send method exposes `nonce` but not
`enforce_nonce`. Outbound Create Message therefore uses a narrow host-owned
Discord REST v10 binding over `httpx`; Gateway and interactions remain on
`discord.py`. Private client-library internals are not an interface.

Before a delayed retry that may be outside Discord's recent deduplication window,
the adapter boundedly reads history after the nearest known preceding Discord
message. If its own message with that nonce exists, it adopts the provider ID.
If the history check cannot complete, delivery remains pending. A nonce is
derived state; no column is added.

### Effectful tools

The action ID is the durable provider effect identity wherever the provider
offers an idempotency or client-identity surface. For Calendar create, the
provider event ID is:

```text
SHA-256(UTF-8("jarvis-calendar-v1:" + canonical_text(action.id)))
  as lowercase hex, first 32 characters
```

This is a 128-bit identifier in Google's permitted event-ID alphabet. A timeout
or duplicate response is reconciled by getting that exact event and comparing a
normalized writable-field projection with the immutable action arguments.
Calendar update/delete reconcile through their known event ID. Gmail send keeps
the stored-draft and Sent-mail procedure.

Every binding owns a bounded reconciliation procedure. A timeout alone
authorizes neither retry nor `uncertain`. The action returns to `queued` only
when evidence proves the effect did not occur and a repeat is safe. It becomes
terminal `uncertain` only after automatic reconciliation is exhausted and the
remaining evidence genuinely cannot decide. Jarvis then presents that evidence
and asks the owner to inspect provider state. No uncertain action re-executes.

## Consequences

Positive:

- Jarvis has no designed duplicate Discord-delivery path.
- Calendar create retries converge on one provider resource.
- Gmail and Calendar ambiguity normally resolves without owner involvement.
- The honest `uncertain` escape hatch remains for failures no protocol can prove.
- No table, column, action state, lease, attempt counter, or workflow system is
  added.

Accepted costs:

- Discord's enforced nonce is time-bounded, so delayed retries require a history
  read and wait when history is unavailable.
- A provider defect or inconsistent Discord history can still violate the
  delivery guarantee.
- The 128-bit Calendar identifier has a negligible but non-zero collision risk;
  Google also notes that its distributed backend cannot guarantee collision
  detection at creation time.
- Provider-specific reconciliation code and failure fixtures are required.
- Discord transport uses two deliberate surfaces: `discord.py` for Gateway and
  interactions, plus direct REST for message creation.
- Some external outcomes can remain genuinely unknowable and need owner
  inspection; v1 refuses to hide that with a blind retry.

## Rejected alternatives

- **Continue accepting Discord duplicates:** unnecessary now that the provider
  exposes a cheap deduplication primitive.
- **Add a nonce column:** duplicates deterministic state and creates a migration
  without improving recovery.
- **Use server-generated Calendar IDs:** reintroduces duplicate-create ambiguity.
- **Treat every timeout as uncertain:** gives up before using provider evidence.
- **Retry every timeout:** can duplicate socially consequential effects.
- **Build a generic exactly-once workflow engine:** cannot manufacture a provider
  guarantee and adds infrastructure the v1 does not need.

## Migration and acceptance

There is no database migration because implementation has not started and every
new identity derives from existing IDs. The affected criteria are A2.8, A2.9,
A3.4, A6.11, A6.12, A6.13, and A7.5.

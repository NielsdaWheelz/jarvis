# ADR 0016: Use provider-native idempotency before uncertainty

- Status: Accepted; schema-cost statement amended by ADR 0018; lifetime attempt
  ceiling amended by ADR 0019; Discord history claim and delivery guarantee
  amended by ADR 0022; Gmail identity amended by ADR 0023
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
one. Slice 0 later established that message history and exact-message reads may
omit the nonce; the corrected bounded-delivery contract is in
[ADR 0022](0022-accept-bounded-discord-delivery-ambiguity.md). See Discord's
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

For delayed retries outside Discord's recent deduplication window, follow ADR
0022: nonce-based history reconciliation is not a v1 guarantee, and a bounded
retry may rarely repeat ordinary conversational text. A nonce is derived state;
no column is added.

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

- Recent Discord retries converge through the provider's enforced nonce.
- Calendar create retries converge on one provider resource.
- Gmail and Calendar ambiguity normally resolves without owner involvement.
- The honest `uncertain` escape hatch remains for failures no protocol can prove.
- No new table, action state, lease, or workflow system is added. ADR 0018 later
  added `action.attempts` as audit evidence for actual executor entries; it does
  not authorize retry. ADR 0019 bounds those entries for the action's lifetime.

Accepted costs:

- Discord's enforced nonce is time-bounded and historical responses may omit it,
  so delayed conversational recovery carries the rare duplicate cost accepted
  in ADR 0022.
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

- **Accept every Discord duplicate without using nonce enforcement:** rejected;
  the provider's recent-window primitive cheaply removes the common case.
- **Add a nonce column:** duplicates deterministic state and creates a migration
  without improving recovery.
- **Use server-generated Calendar IDs:** reintroduces duplicate-create ambiguity.
- **Treat every timeout as uncertain:** gives up before using provider evidence.
- **Retry every timeout:** can duplicate socially consequential effects.
- **Build a generic exactly-once workflow engine:** cannot manufacture a provider
  guarantee and adds infrastructure the v1 does not need.

## Migration and acceptance

Implementation had not started when this ADR was accepted; every provider
identity still derives from existing IDs. ADR 0018's later schema migration is
independent of that identity derivation. The affected criteria are A2.8, A2.9,
A3.4, A6.11, A6.12, A6.13, and A7.5.

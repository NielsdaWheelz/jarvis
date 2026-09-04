# ADR 0024: Use a stable Gmail effect header

- Status: Accepted; supersedes ADR 0023 and amends ADR 0016
- Date: 2026-09-03

## Context

ADR 0023 proposed a caller-generated RFC `Message-ID` as the durable identity
linking a Gmail draft to its Sent replacement. Live Slice 0 qualification
disproved that design: Gmail replaced the supplied value during draft creation
with its own `@mail.gmail.com` identity. The stored draft was otherwise exact,
but searching for the caller-generated identity found nothing.

A follow-up live probe established the smaller working primitive. Gmail
preserved one `X-Jarvis-Effect-ID` MIME header exactly in an unsent draft. Full
new-thread and reply-thread canaries then preserved it through draft creation
and send, retained the known thread ID, found exactly one matching raw message
in that thread on the first read, and returned 404 when asked to send the
consumed draft again.

## Decision

During `gmail.create_draft`, compute `effect_id` as the full lowercase
hexadecimal encoding of:

```text
SHA-256(
  UTF-8("jarvis-gmail-v1:" + canonical_text(create_action.id))
)
```

Set the MIME header `X-Jarvis-Effect-ID: {effect_id}`. Let Gmail own the RFC
`Message-ID`; use that provider-generated value only for normal reply threading.
Draft updates preserve the Jarvis header. A later `gmail.send_draft` action
copies the Jarvis effect ID into its immutable arguments and verifies the live
draft before approval execution.

Reconciliation is provider-specific and bounded:

- After ambiguous create, list a bounded recent Draft set and fetch raw
  candidates. Exactly one matching Jarvis header plus exact normalized content
  proves success. An incomplete scan or multiple/conflicting candidates is not
  absence.
- After ambiguous update, fetch the known draft and compare its Jarvis header
  and normalized content. If it disappeared, inspect the known thread.
- After ambiguous send, first inspect the known draft ID, then fetch the known
  thread and inspect raw messages for the exact Jarvis header. One exact content
  match proves success. Multiple/conflicting matches are `uncertain`.

No Gmail search-index result is required for effect reconciliation. A transient
absence at any one read never proves non-delivery. A repeat is possible only
when the complete bounded procedure proves the effect absent and repetition
safe.

## Consequences

Positive:

- Identity survives Gmail's draft-message replacement and Sent-message
  creation behavior verified in both thread shapes.
- Two intentionally identical emails from separate actions remain
  distinguishable.
- Reconciliation uses the already-known draft/thread locality rather than a
  mailbox-wide subject/recipient heuristic or eventually indexed search.
- No table column or new provider scope is needed.

Accepted costs:

- The opaque Jarvis header is visible to a recipient who inspects raw message
  source. It contains only a one-way digest of an internal random identifier.
- Ambiguous draft creation may require a bounded scan of recent drafts; if that
  scan is incomplete, Jarvis fails uncertain rather than claiming absence.
- Every matching candidate must be fetched and content-compared; header equality
  alone is insufficient.

## Rejected alternatives

- **Caller-generated RFC `Message-ID`:** live Gmail draft creation rewrites it.
- **Gmail thread ID alone:** identifies a conversation, not one effect.
- **Subject/recipient/time matching:** cannot distinguish legitimate identical
  sends.
- **Mailbox search for a custom header:** Gmail exposes no documented arbitrary-
  header search primitive, and reconciliation does not need one.
- **A new identity column:** duplicates deterministic/action-argument state.

## Migration and acceptance

Implementation has not started. Replace the ADR 0023 RFC-identity fields in all
contracts and fixtures with `jarvis_effect_id`. The affected criteria remain
A1.9, A6.11–A6.13, and A6.17.

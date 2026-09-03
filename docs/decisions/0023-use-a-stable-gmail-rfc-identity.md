# ADR 0023: Use a stable Gmail RFC identity

- Status: Accepted; amends ADR 0016
- Date: 2026-09-03

## Context

Gmail replaces the message resource inside a draft when the draft is updated,
and sending deletes the draft and creates a new Sent message with a new provider
message ID. A provider `threadId` is useful but is not a unique effect identity:
one thread can contain multiple similar messages, and new-thread behavior still
needed live verification.

Gmail accepts an RFC-formatted MIME message in the draft's `raw` field and its
documented search syntax can find a message by its RFC `Message-ID`. See Google's
[draft guide](https://developers.google.com/workspace/gmail/api/guides/drafts)
and
[search-operator reference](https://support.google.com/mail/answer/7190).

## Decision

The `gmail.create_draft` action owns a deterministic RFC identity. Let `digest`
be the full lowercase hexadecimal encoding of:

```text
SHA-256(
  UTF-8("jarvis-gmail-v1:" + canonical_text(create_action.id))
)
```

The MIME `Message-ID` is `<{digest}@jarvis.invalid>`. The `.invalid` namespace
cannot resolve. Draft updates preserve this header. A later `gmail.send_draft`
action copies the identity into its immutable arguments; it does not derive a
new identity from the send action ID.

After ambiguous create, update, or send outcomes, the binding searches the
relevant Draft/Sent state by the exact RFC identity and fetches candidate raw
messages. One exact normalized match is evidence; multiple or conflicting
matches are not collapsed into success. Thread, draft, provider response, and
bounded temporal evidence remain useful corroboration, but subject and
recipients alone are never effect identity.

## Consequences

Positive:

- Draft-message replacement and Sent-message creation preserve one
  action-derived reconciliation identity.
- Two deliberately identical emails from two actions remain distinguishable.
- No table column is added; the identity is derived during create and already
  belongs in the immutable send arguments shown for approval.

Accepted costs:

- Reconciliation depends on Gmail preserving and indexing a caller-supplied RFC
  `Message-ID`; Slice 0 must verify new-thread and reply-thread behavior live.
- Gmail search can lag, so absence at one observation never proves non-delivery.
- The live draft fetch and normalized MIME comparison are still required; an
  RFC identity match alone does not prove content equality.

## Rejected alternatives

- **Use Gmail message ID:** it changes across draft replacement and send.
- **Use thread ID:** it identifies a conversation, not one send effect.
- **Search only subject and recipients:** two legitimate actions can be
  identical and close in time.
- **Add a Gmail-identity column:** duplicates deterministic/action-argument
  state without improving recovery.

## Migration and acceptance

Implementation has not started. The affected criteria are A1.9, A6.13, A6.17,
and the Gmail portions of A6.11 and A6.12.

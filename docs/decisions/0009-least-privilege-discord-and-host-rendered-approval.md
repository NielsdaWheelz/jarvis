# ADR 0009: Least-privilege Discord and a host-rendered approval preview

- Status: Accepted
- Date: 2026-09-01
- Supersedes: the Administrator trade-off in
  [ADR 0003](0003-natural-discord-and-autonomy.md)

## Context

[ADR 0003](0003-natural-discord-and-autonomy.md) accepted Discord Administrator
for the bot and recorded the cost as "literal Discord Administrator access can
destroy or reorganize the dedicated server if the bot misbehaves." Adversarial
review found that framing incomplete on both sides.

On the cost side, `ADMINISTRATOR` subsumes `CREATE_INSTANT_INVITE`,
`MANAGE_GUILD`, `MANAGE_ROLES`, and `MANAGE_WEBHOOKS`. A prompt-injected bot
holding it can add a member, which directly violates the membership invariant
SPEC section 4.1 states two sentences after granting it, and can mint a webhook
URL, which is an unauthenticated egress endpoint. Egress matters unusually much
in this system: the Codex session has no network, and every other outward channel
crosses the approval boundary, so a webhook would be the one unmetered way out.

On the benefit side, nothing in SPEC section 4.1 requires it. The trade-off as
recorded weighed a real cost against no benefit.

Review found a second defect on the same seam. The approval preview — the text
the owner reads before authorizing an irreversible outward action — was a field
the model emitted in the same object as the arguments, with nothing binding the
two. An injected email could produce a truthful-looking preview over an
exfiltrating payload, and every other control in the system would hold perfectly
while the owner clicked Approve. Related: SPEC section 4.1 granted the model
automatic authority to edit and delete its own messages, which includes the
message carrying those buttons.

## Decision

**Least-privilege Discord.** The bot MUST NOT hold `ADMINISTRATOR`,
`MANAGE_GUILD`, `MANAGE_ROLES`, `MANAGE_WEBHOOKS`, `CREATE_INSTANT_INVITE`,
`KICK_MEMBERS`, `BAN_MEMBERS`, `MENTION_EVERYONE`, `MANAGE_GUILD_EXPRESSIONS`, or
`MODERATE_MEMBERS`. Its role grants exactly the eleven permissions enumerated
in SPEC section 4.1. Server membership, invites, roles, and webhooks are
owner-only operations. Channel deletion leaves the automatic set entirely:
Jarvis archives instead, because a channel can hold owner messages, the approval
record, and the targets of `discord://` references stored in memory.

**Host-rendered approval preview.** The preview is rendered deterministically by
host code from the stored arguments, by a renderer owned by the application, one
per approval-bearing tool. The step protocol carries no preview field, and there
is no preview column on the `action` row — the preview is derived at display
time, so a model-authored preview is structurally impossible rather than
forbidden by policy. A model-supplied rationale may appear in a subordinate
labelled block and may not substitute for the rendered action. An
approval-bearing tool with no host renderer fails closed.

**Host-owned approval messages.** Messages carrying Approve or Deny components
are excluded from the automatic message-management capability. Jarvis cannot edit
or delete a message referenced by an `action` row. After atomically claiming or
denying an interaction, the host immediately acknowledges it and disables its
components before any slow external work.

**Host-owned rich rendering.** Normal model-authored output is text. Host code
does not translate model-supplied rich-content objects into embeds, attachments,
or components. The approval renderer may generate a plain-text payload attachment
and Approve or Deny components from the validated stored action. `EMBED_LINKS` is
withheld, so ordinary model-authored links remain clickable but Discord does not
automatically fetch them to build previews.

## Consequences

Positive:

- The membership invariant becomes enforceable rather than aspirational.
- The one human checkpoint in the system now shows what will actually execute.
  Every other approval control — closed schemas, server-side arguments, the
  atomic claim, owner-ID binding, the free-form-text prohibition — previously
  terminated at a sentence of prose the model wrote about itself.
- The approval boundary for communication outside Jarvis's private server
  remains structural.
- Cost is roughly one function per implemented approval-bearing tool.

Accepted costs:

- Rendering is per-tool work, and a new approval-bearing capability cannot ship
  without its renderer.
- A long email body must be rendered whole. Host code may split it across
  host-owned messages or generate an attachment, with the final message carrying
  Approve and Deny and identifying the complete payload.
- The owner must configure a permission integer rather than clicking
  Administrator once.
- Jarvis can no longer delete a channel it created, so the server accumulates
  archived channels.

## Rejected alternatives

- **Keep Administrator and rely on the model behaving.** The system's entire
  containment posture is structural rather than behavioral; this would have been
  the one place it was not.
- **A cryptographic action-hash protocol binding preview to arguments.** ADR 0003
  and SPEC section 5.3 correctly judge this unnecessary for one owner with one
  identity and server-side arguments. Host rendering solves the same problem with
  no protocol.
- **Sanitizing model-authored previews.** Sanitizing prose cannot establish that
  the prose describes the arguments. Deriving the prose from the arguments can.
- **Granting `EMBED_LINKS`:** server-side link fetching creates unnecessary
  zero-click egress. Clickable text links preserve the useful part without it.

# ADR 0025: Accept existing Discord role authority

- Status: Accepted; amends ADRs 0009 and 0011
- Date: 2026-09-03

## Context

The reused bot has the four permissions Jarvis needs, but inherits 25 additional
permissions from the server's `@everyone` role. It has no Administrator,
guild/channel/message/thread/role/webhook management, moderation, kick, or ban
authority. The managed bot role cannot remove inherited grants, and the owner
does not want Discord permission maintenance to gate this one-user prototype.

This is dormant authority rather than a model capability: v1 exposes no
model-callable Discord tool, and the host adapter implements only configured-
channel ingress, ordinary/approval delivery, typing, and editing its own
approval message. Nevertheless, a compromised host process or bot token could
exercise inherited invite, mention, thread, reaction, application, event, poll,
media, or voice permissions. `EMBED_LINKS` also permits Discord-side handling of
model-written links.

## Decision

Reuse the current role configuration in v1. The deployment must contain the four
operational permissions—View Channel, Send Messages, Attach Files, and Read
Message History—but exact Discord-level least privilege is not a Slice 0 gate.
Startup still rejects Administrator and guild/channel/message/thread/role/
webhook management, moderation, kick, or ban authority.

Constrain the application surface instead:

- Keep Discord absent from every model tool catalog.
- Keep ingress restricted to the configured owner, guild, and channel.
- Every Create Message and content-bearing edit sets
  `allowed_mentions = {"parse": []}`.
- Every Create Message sets the `SUPPRESS_EMBEDS` message flag and supplies no
  model-authored embed object. Content-bearing edits retain that flag.
- Do not implement invite, reaction, thread, poll, event, voice, application,
  membership, or server-organization operations.

The live direct-REST probe confirmed that a message containing literal
`@everyone` plus a public URL returned `mention_everyone = false`, zero embeds,
and the suppress-embeds flag, then was deleted successfully.

## Consequences

Positive:

- No server-role reconfiguration or ongoing permission drift maintenance blocks
  v1.
- The application remains much narrower than the bot's dormant Discord role.
- Ordinary model output cannot intentionally ping users or request a rich embed
  through the implemented Create Message path.

Accepted costs:

- Compromise of the bot token or host process has more Discord authority than
  Jarvis needs.
- `SUPPRESS_EMBEDS` is a message rendering control, not proof that Discord never
  performs any server-side URL handling. A model-generated link can therefore
  still create third-party request risk while `EMBED_LINKS` remains granted.
- The owner is consciously accepting role-level overbreadth for a one-user
  prototype; revisit before adding Discord tools, more users, or broader server
  routing.

## Rejected alternatives

- **Block Slice 0 on an exact four-permission override:** the owner explicitly
  rejected that operational burden for v1.
- **Grant Administrator:** materially expands compromise impact and remains
  prohibited.
- **Trust broad permissions without host restrictions:** unnecessarily exposes
  mentions and displayed link embeds through the one operation Jarvis does use.
- **Add Discord tools because authority already exists:** confuses provider role
  authority with intentionally exposed application capability.

## Migration and acceptance

Implementation has not started. A2.2 now tests the accepted authority ceiling
and host request controls instead of exact four-permission equality. The
production adapter proof belongs to Slice 1.

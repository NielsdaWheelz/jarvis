# ADR 0011: Use one Discord channel as a transport

- Status: Accepted
- Date: 2026-09-01
- Supersedes: the server-organization decisions in
  [ADR 0003](0003-natural-discord-and-autonomy.md), the Discord tool-surface
  decision in [ADR 0005](0005-reuse-integrations.md), and the Discord permission
  and channel-archival portions of
  [ADR 0009](0009-least-privilege-discord-and-host-rendered-approval.md)

## Context

Natural Discord conversation is sufficient to test whether Jarvis produces
useful cognitive offloading. Channel and thread creation, organization,
archival, reactions, and broad message management add permissions, model tools,
routing state, and failure cases before any observed need for topic separation.

Discord is already a delivery surface rather than canonical history. The
`message` table can recover conversation context, so Jarvis does not need to
read or reorganize the whole server to preserve continuity.

## Decision

V1 uses one configured private Discord text channel, conventionally
`#general`, in one configured guild. The deployment also configures one owner
Discord user ID. Jarvis accepts owner messages and approval interactions only in
that channel. It ignores direct messages, Discord threads, other channels, and
all other users.

Discord is a transport adapter, not a model-callable application tool family.
The adapter may receive and catch up owner messages, show typing state, deliver
ordinary `say` output, deliver host-rendered approval messages and attachments,
and edit its own approval message to disable components. Those operations are
host-owned conversation delivery and create no `action` rows.

The bot role grants exactly:

- `VIEW_CHANNEL`
- `SEND_MESSAGES`
- `ATTACH_FILES`
- `READ_MESSAGE_HISTORY`

The integration enables exactly the `GUILDS`, `GUILD_MESSAGES`, and
`MESSAGE_CONTENT` Gateway intents. It does not request direct-message, member,
presence, or reaction intents; host filtering rejects thread events.

`ADMINISTRATOR`, `MANAGE_CHANNELS`, `MANAGE_THREADS`, `MANAGE_MESSAGES`, thread
creation and send permissions, reactions, invites, roles, webhooks, moderation,
and `EMBED_LINKS` remain absent. A bot may edit its own messages without
`MANAGE_MESSAGES`; it cannot edit messages authored by anyone else.

Expanding Discord into a workspace is a later product slice, not dormant v1
authority.

## Consequences

Positive:

- Discord integration becomes ingress, egress, and Approve/Deny only.
- The model receives no Discord administration tools.
- Prompt injection cannot reorganize the server or manipulate other messages.
- One channel maps directly to one continuing main-agent session.
- `READ_MESSAGE_HISTORY` permits bounded catch-up after downtime while
  PostgreSQL remains canonical.

Accepted costs:

- Conversation, approvals, and proactive notices interleave in one channel.
- V1 has no topic-specific notification routing or channel organization.
- The owner must create or select the channel and organize the server manually.
- Links do not unfurl and long approvals may use plain-text attachments.

## Rejected alternatives

- **One Discord thread:** thread archival, permissions, routing, and lifecycle
  add machinery while providing no benefit over one private channel.
- **Keep broad permissions but expose no tools:** dormant authority is still
  authority and can be reached through implementation defects.
- **Remove `READ_MESSAGE_HISTORY`:** a bot that loses its Gateway resume window
  could miss owner input sent during downtime.
- **Multiple channels from launch:** no observed routing or separation need
  justifies the capability surface.

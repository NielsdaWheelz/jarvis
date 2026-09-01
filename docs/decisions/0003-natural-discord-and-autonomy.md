# ADR 0003: Natural Discord interaction and a narrow approval boundary

- Status: Accepted; action storage amended by ADR 0007
- Date: 2026-09-01

## Context

Jarvis should remove work rather than turn the user into its supervisor. Command
taxonomies, pervasive confirmations, dashboards, and many action buttons would
make the assistant another system to operate.

Discord already supplies conversation, Markdown, files, channels, threads,
notifications, and interaction components. A dedicated server can become
Jarvis's evolving workspace without building a separate client.

## Decision

Jarvis receives a dedicated private Discord server and may administer and
organize it. Interaction is natural conversation. V1 has no slash commands.

Approve and Deny are the only custom action components.

Reads, memory work, local writes, personal no-attendee calendar changes, email
drafts, and Jarvis-server administration are automatic.

Approval is required only when an action communicates consequentially to another
person, spends money, exposes a secret, or irreversibly destroys meaningful
external data.

Approval references one stored row in the unified `action` ledger. It executes
that exact action at most once. Free-form conversation is not approval.

## Consequences

Positive:

- Jarvis behaves like an assistant rather than a copilot awaiting constant input.
- The natural interface can evolve through use.
- Discord provides a capable v1 client at almost no product-development cost.
- The approval rule can be understood without a permission matrix.

Accepted costs:

- Literal Discord Administrator access can destroy or reorganize the dedicated
  server if the bot misbehaves.
- Natural language can be less discoverable than commands for repeated exact
  operations.
- Discord is not an ideal long-term surface for secrets or biometric approval.
- Some external writes require judgment about whether they communicate or are
  irreversible.

## Rejected alternatives

- Android first: delays learning the actual interaction model.
- Slash commands from launch: speculative and constraining.
- A large risk-tier framework: more supervision and product surface than v1
  requires.
- Approval for every write: defeats personal-assistant autonomy.
- No approval at all: sending communications or spending money exercises the
  user's social or financial authority.

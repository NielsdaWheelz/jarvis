# ADR 0003: Natural Discord interaction and a narrow approval boundary

- Status: Accepted; action storage amended by ADR 0007; Administrator and
  approval-preview decisions superseded by ADR 0009; server organization
  superseded by ADR 0011; generic local-write scope superseded by ADR 0014
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

- Natural language can be less discoverable than commands for repeated exact
  operations.
- **Discord is a third-party processor for the entire product.** Every
  conversation, every memory Jarvis quotes back, every email it summarizes, and
  every approval preview passes through and is retained by Discord — including
  content Jarvis later deletes, which leaves the client and not the platform.
  This is the single largest privacy fact about the design, and it is accepted
  knowingly. Discord is also not an appropriate surface for secrets or biometric
  approval.
- Some external writes require judgment about whether they communicate or are
  irreversible.
- The Administrator grant originally accepted here has been withdrawn; see
  [ADR 0009](0009-least-privilege-discord-and-host-rendered-approval.md).

## Rejected alternatives

- Android first: delays learning the actual interaction model.
- Slash commands from launch: speculative and constraining.
- A large risk-tier framework: more supervision and product surface than v1
  requires.
- Approval for every write: defeats personal-assistant autonomy.
- No approval at all: sending communications or spending money exercises the
  user's social or financial authority.

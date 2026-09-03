# ADR 0012: Reuse one main Codex session over provider-neutral context

- Status: Accepted; implementation ownership, polling, admission, and isolated
  write-gate role amended by ADRs 0017–0019; explicit compatibility revision
  amended by [ADR 0020](0020-pin-the-implemented-kernel-boundary.md)
- Date: 2026-09-01
- Amends: [ADR 0004](0004-python-codex-and-tool-kernel.md) and the provider-session
  lifecycle in [ADR 0007](0007-central-messages-and-unified-actions.md)

## Context

The [official Codex SDK documentation](https://developers.openai.com/codex/sdk/)
and `provider-runtime` support continuing and resuming native sessions.
Rebuilding and resending a complete transcript on every owner message would
discard that capability, duplicate history management, and may reduce provider
cache reuse.

Native session history and compaction are nevertheless provider-owned and
opaque. They cannot replace canonical messages or durable memory: a local state
directory can be lost, a session can fail to resume, and a future API-backed
model may be stateless or use a different continuation mechanism.

Time context had also been specified too broadly. Repeating a changing clock in
every model context is unnecessary and makes stable prompt prefixes shorter.
Relative owner time still needs an authoritative host value and IANA timezone.

## Decision

The configured Discord channel normally maps to one continuing main Codex
session. Ordinary process restarts and compatible deployments resume its
persisted `AgentSessionRef`. A changed session-scoped configuration starts a
fresh main session rather than carrying old prompts, model configuration,
containment, or capability assumptions across a deployment.

V1 uses the stateful `provider_runtime.agent_runtime.AgentRuntime`
open/stream/close surface, not root stateless generation. The adapter consumes
`stream_turn` so every native authority event remains observable; it does not
use the terminal-only `run_turn` projection. The live session is a resource
owned by the adapter; the serialized ref is only its disposable continuation
handle.

The reference and a fingerprint of complete session-scoped configuration live
in atomically replaced private runtime state outside PostgreSQL. The fingerprint
covers stable instructions, model/reasoning/output contract,
credential-profile identity, SDK/runtime revisions, cwd/directories/MCP
configuration, `PermissionPolicy`, native options, and the session capability
envelope. It also covers the required `session_compatibility_revision`, derived
from a checked-in role/application session-contract revision and the exact
kernel, provider-runtime, and llm-tools pins. This owner-controlled value rotates
when a semantic compatibility change is not otherwise serialized in the
definition. Secret bytes, current input, time, and per-run subset plans are
excluded. This runtime state is non-canonical, contains no conversation bodies
or credentials, and need not be backed up. A fingerprint mismatch or resume
failure discards the reference and starts a new session.

Recaller, rememberer, dreamer, and AutomaticWriteGate invocations use fresh
isolated sessions. They do not share the main session or one another's history.
Their narrower prompts and capabilities must not accumulate in Jarvis's visible
conversation. ADR 0019 restricts the gate to its own owner-input/effect
projection rather than this general context package.

Jarvis retains a provider-neutral context builder. Its application-owned output
contains plain structured sections, not Codex SDK message types:

```text
stable instructions
bounded completed message history
current event and its source timestamp
recalled memories with IDs and timestamps
granted capability descriptions
owner IANA timezone
one host-generated as_of instant
```

The builder supports two projections:

- **Continuation:** for a healthy main session, send only the new event, fresh
  recall, current capabilities, and one `as_of` value. Stable session context,
  including the owner timezone, and native history carry prior turns.
- **Bootstrap/stateless:** for a new or lost session, include stable instructions
  and bounded canonical history before the same current-turn material. A future
  API-backed provider may consume this projection without changing application
  context selection.

Each admitted owner input appears exactly once. Completed history excludes every
current claimed row. Compatible input may be appended mid-loop and receives a
new continuation delta. In-progress read observations remain turn-local and may
be performed again under the existing recovery rules.

The owner timezone is stable deployment configuration. It is included once when
a main or isolated cognitive session opens. Each newly admitted input batch or
background job receives one authoritative `as_of` value. Source messages retain
their own `created_at`; tool-only continuations and embedding calls do not
receive a repeated clock. Stable instructions precede dynamic time when a
provider projection is rendered.

Session reuse is an optimization and continuity feature, not a correctness,
durability, or promised-cost property. Canonical messages plus recall must always
be sufficient to start again.

## Consequences

Positive:

- Ordinary conversation benefits from native continuation and compaction.
- Jarvis does not reconstruct its entire recent transcript on every healthy
  turn.
- Losing all provider session state causes a cold start, not amnesia.
- Context selection remains usable by a future stateless or API-backed provider.
- Internal roles retain clean capability and prompt boundaries.

Accepted costs:

- Main-session compaction is opaque and may retain stale prior observations.
  Fresh recalled context is authoritative for the current turn.
- A changed session-scoped configuration takes a cold-start context bootstrap.
- Runtime state contains one additional rebuildable file.
- Cache improvement is measured rather than guaranteed; no acceptance criterion
  depends on a particular cache hit rate or billing behavior.
- A bootstrap reconstructs useful semantic context, not byte-identical native
  reasoning history.

## Rejected alternatives

- **Provider session as canonical history:** opaque state cannot satisfy restore,
  migration, or future-provider requirements.
- **Fresh main session for every message:** throws away useful native continuity
  and repeats prompt packing without a correctness benefit.
- **One session for every cognitive role:** cross-contaminates instructions,
  memory work, capabilities, and conversational history.
- **Codex-specific context assembly:** makes lost-session recovery and a future
  API provider separate orchestration implementations.
- **A live clock in every prompt section:** unnecessary dynamic prefix churn and
  multiple competing notions of "now."

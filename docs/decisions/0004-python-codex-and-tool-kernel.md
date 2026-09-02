# ADR 0004: Python, Codex, `provider-runtime`, and `llm-tools`

- Status: Accepted; amended by ADR 0008 on embedding, ADR 0012 on session and
  context lifecycle, ADR 0014 on portable Web tool ownership, and ADR 0017 on
  reusable agent-loop ownership
- Date: 2026-09-01

## Context

The user requires subscription-backed Codex and owns two relevant local Python
libraries. `provider-runtime` supplies authenticated, isolated Codex session
lifecycle. `llm-tools` supplies closed tool contracts, capability exposure,
validation, budgets, effect identity, and replay semantics.

The current Codex SDK lane does not provide a host callback that turns native
tool invocation into Jarvis-owned execution and user approval. Its built-in tool
surface also cannot currently be reduced to a proven application-tools-only
kernel.

## Decision

Use Python 3.12.

Use `provider-runtime` for all subscription-backed Codex cognitive roles. Use
`llm-tools` as the host-owned application tool kernel. `llm-tools` supplies the
kernel and four portable tools; every Jarvis capability declaration and binding
is new work in the Jarvis repository, not an adaptation of something the library
already ships.

Confine the Codex session with the native option that disables its built-in
feature set, a read-only empty working directory, disabled network, deny-mode
approvals, and the `("*",)` allowed-tools sentinel that is the only spelling the
route accepts. The sandbox and approval mode, not a tool filter, are what confine
a Codex session.

Use a multi-turn structured-step protocol between Codex and the host instead of
giving Codex connector credentials or direct write-authority MCP tools. Confine
the Codex worker to an empty read-only environment and fail on unexpected native
tool activity.

Pin and qualify the exact Codex SDK/runtime pair. Do not automatically upgrade
it or silently fall back to a different provider.

## Consequences

Positive:

- Existing high-quality personal libraries remain authoritative.
- Connector credentials and action authority stay outside model execution.
- Tool requests are inspectable and testable before execution.
- Python avoids a language boundary through the core agent loop.

Accepted costs:

- A foreground response needs recall and main-agent turns; host-mediated tools
  may add more. Remembering follows asynchronously. Jarvis will still be slower
  than stateless chat for simple questions.
- Codex runtime containment depends partly on the deployment boundary.
- The Codex worker, if run as the Jarvis service uid, can read the owner's entire
  home directory under `read_only`. There is no network egress under the mandated
  policy, so this is a confidentiality-in-context cost rather than an
  exfiltration path, and running a second unprivileged uid removes it.
- The current library qualification target is Linux, not macOS.
- **A single subscription pool is a single point of total conversational
  outage.** The lane blocks and stops on quota exhaustion by design and never
  overflows onto API credentials. There is no fallback, deliberately.
- Embedding cannot run on this lane at all; see
  [ADR 0008](0008-embedding-source.md).

## Rejected alternatives

- TypeScript server: would wrap or replace the required Python libraries.
- Direct remote MCP in v1: unnecessary network and execution surface.
- An API-key provider fallback: violates the personal Codex requirement and
  creates divergent behavior.
- A general agent framework: duplicates state, tool, and orchestration concepts
  already owned by the application and local libraries.

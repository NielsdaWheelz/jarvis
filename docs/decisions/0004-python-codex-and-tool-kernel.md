# ADR 0004: Python, Codex, `provider-runtime`, and `llm-tools`

- Status: Accepted
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
`llm-tools` as the host-owned application tool kernel.

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

- Host-mediated tools may require additional Codex turns.
- Codex runtime containment depends partly on the deployment boundary.
- The current library qualification target is Linux, not macOS.
- Subscription quotas and model availability are operational constraints.

## Rejected alternatives

- TypeScript server: would wrap or replace the required Python libraries.
- Direct remote MCP in v1: unnecessary network and execution surface.
- An API-key provider fallback: violates the personal Codex requirement and
  creates divergent behavior.
- A general agent framework: duplicates state, tool, and orchestration concepts
  already owned by the application and local libraries.

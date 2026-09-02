# ADR 0005: Reuse working integrations and defer new ones

- Status: Accepted; Discord tool-surface decision superseded by ADR 0011;
  public-Web scope amended by ADR 0014
- Date: 2026-09-01

## Context

Discord, Gmail, Google Calendar, and Google Maps are already integrated and
authorized in the user's current environment. Recreating their provider setup,
OAuth grants, credential handling, and tested behavior would produce risk and
work without new user value.

OnePassword, Nexus, Skidbladnir, and Android are desirable but are not necessary
to prove the core memory-and-assistance loop.

## Decision

Audit and reuse the existing working Discord and Google integrations. Adapt the
smallest stable callable surface to `llm-tools`. Preserve existing credentials
and registrations when safe and possible.

Do not copy or reuse unrelated Ariel agent, memory, orchestration, prompt, or
product-domain code.

Defer OnePassword, Nexus, Skidbladnir, and Android to separately reviewable
post-v1 slices recorded in the implementation plan.

## Consequences

Positive:

- V1 starts with live useful capabilities.
- The user avoids needless provider reauthorization.
- The first work targets Jarvis behavior and memory.
- Deferred integrations can respond to actual usage.

Accepted costs:

- V1 may temporarily depend on integration boundaries shaped by Ariel.
- **Ariel is a running deployment on the same host, not a library.** Reusing its
  authorizations without deciding ownership would leave two gateway clients on
  one Discord bot token and two agents acting autonomously on one mailbox. The
  audit MUST assign exactly one owning process to each credential; see
  [SPEC.md section 10](../../SPEC.md#10-existing-integrations).
- Some adapters may later deserve extraction into independent packages.
- The new repository is not initially a completely self-contained deployment.

## Rejected alternatives

- Reimplement every provider integration: expensive and risky duplication.
- Import Ariel wholesale: contaminates the clean-slate architecture.
- Add all desired integrations in v1: delays the core learning loop.
- Direct database access to Nexus or generic terminal access through Skidbladnir:
  bypasses their intended interfaces and creates needless coupling.

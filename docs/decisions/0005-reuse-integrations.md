# ADR 0005: Reuse working integrations and defer new ones

- Status: Accepted; Discord tool-surface decision superseded by ADR 0011;
  public-Web scope amended by ADR 0014; Google grant amended below
- Date: 2026-09-01
- Amended: 2026-09-02

## Context

Discord, Gmail, Google Calendar, and Google Maps are already integrated and
authorized in the user's current environment. Recreating their provider setup,
OAuth grants, credential handling, and tested behavior would produce risk and
work without new user value. Slice 0 later established that both the canonical
and backup Google refresh tokens are revoked (`invalid_grant`), so preserving
that particular grant is impossible even though the registration and other
credentials remain reusable.

OnePassword, Nexus, Skidbladnir, and Android are desirable but are not necessary
to prove the core memory-and-assistance loop.

## Decision

Audit and reuse the existing working Discord and Google integrations. Adapt the
smallest stable callable surface to `llm-tools`. Preserve existing credentials
and registrations when safe and possible.

Reuse the Google OAuth registration but perform one unavoidable replacement
offline consent using exactly the minimal seven-scope set in SPEC section 8.
Do not carry forward the legacy Drive scopes or redundant Gmail/Calendar
authority. Import encrypted token state once under the legacy associated-data
namespace, then immediately re-encrypt it under a Jarvis-owned namespace.

Do not copy or reuse unrelated Ariel agent, memory, orchestration, prompt, or
product-domain code.

Defer OnePassword, Nexus, Skidbladnir, and Android to separately reviewable
post-v1 slices recorded in the implementation plan.

## Consequences

Positive:

- V1 starts with live useful capabilities.
- The user avoids needless provider registration and authorization; one Google
  re-consent remains necessary because every reusable refresh token is revoked.
- The first work targets Jarvis behavior and memory.
- Deferred integrations can respond to actual usage.

Accepted costs:

- V1 may temporarily depend on integration boundaries shaped by Ariel.
- **Ariel is a deployment on the same host, not a library.** Slice 0 found all
  four Ariel services inactive and disabled. They MUST remain disabled when
  Jarvis assumes sole Gateway and autonomous connector ownership; see
  [SPEC.md section 10](../../SPEC.md#10-existing-integrations).
- Some adapters may later deserve extraction into independent packages.
- The new repository is not initially a completely self-contained deployment.

## Rejected alternatives

- Reimplement every provider integration: expensive and risky duplication.
- Import Ariel wholesale: contaminates the clean-slate architecture.
- Add all desired integrations in v1: delays the core learning loop.
- Direct database access to Nexus or generic terminal access through Skidbladnir:
  bypasses their intended interfaces and creates needless coupling.

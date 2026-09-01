# V1 implementation plan

This plan consists of small vertical slices. Each slice should leave the
repository understandable and demonstrably closer to the acceptance contract.
It is not a schedule and does not authorize deferred features.

## Slice 0: integration and runtime audit

Deliverables:

- Delegated summaries of the existing Discord, Gmail, Calendar, and Maps
  integration surfaces without importing unrelated Ariel design.
- Exact reuse plan for their credentials and authorizations.
- A clean dependency strategy for `provider-runtime` and `llm-tools` that does
  not touch the user's staged-deletion `llm-tools` checkout.
- Linux qualification tests for the pinned Codex SDK/runtime combination.
- Initial threat and private-data fixture inventory.

Exit condition: every external dependency needed for the first conversation has
a known callable surface and ownership boundary.

## Slice 1: conversational skeleton

Deliverables:

- Python project and locked environment.
- PostgreSQL connection and migrations.
- Reused Discord ingress/egress.
- Owner identity and dedicated-server configuration.
- Subscription-backed `provider-runtime` main-agent session.
- Strict `answer` and `finish_silent` model outputs.
- Natural text conversations without commands.

Exit condition: the owner can have a useful natural Discord conversation through
a fresh and a resumed Jarvis process.

## Slice 2: read tools

Deliverables:

- `llm-tools` catalog and host executor.
- Strict `read` model step.
- Reused Gmail read/search operations.
- Reused Calendar read operations.
- Reused Maps lookup operations.
- Typed observations and bounded multi-turn tool loop.

Exit condition: Jarvis can answer a compound natural question using all three
live Google services without exposing credentials to the model.

## Slice 3: raw memory and recall

Deliverables:

- `memory_log` schema, append path, embeddings, and full-text search.
- Memory search and open primitives.
- Recaller invoked before every owner input.
- Rememberer invoked after completed interactions.
- Stable reference convention and link resolver for existing services.
- Fixed personal/redacted recall evaluation set.

Exit condition: a remembered preference and linked external matter are recalled
in a fresh provider session without user repetition.

## Slice 4: dreaming and summaries

Deliverables:

- `memory_summary` schema with raw lineage.
- Dreamer capability profile.
- Simple systemd or process timer.
- Summary generation, replacement, and deletion.
- Complete summary/embedding rebuild command.
- Contradiction and flattened-lineage tests.

Exit condition: wiping derived memory and rebuilding it from the raw log restores
passing recall evaluations.

## Slice 5: automatic writes

Deliverables:

- Reused Gmail draft operation.
- Reused personal Calendar write operations.
- Discord channel/server organization tools.
- Automatic action classification for these capabilities.
- Write effect IDs and recovery tests where required.

Exit condition: Jarvis performs a natural request involving a draft, personal
calendar change, and Discord organization without unnecessary approval.

## Slice 6: Approve and Deny

Deliverables:

- `pending_action` schema.
- `propose_action` model step.
- Discord preview with Approve and Deny.
- Owner-only atomic claim and execution.
- Reused Gmail send binding.
- Duplicate-click, restart, provider-timeout, and uncertainty tests.

Exit condition: an approved email sends exactly once and a denied email never
sends.

## Slice 7: production acceptance

Deliverables:

- Linux deployment definition.
- Secret/configuration procedure.
- PostgreSQL backup and tested restore.
- Redacted operational inspection.
- Complete automated acceptance run.
- Seven-day personal acceptance period.
- Dated acceptance report.

Exit condition: every non-waived mandatory criterion in `docs/acceptance.md`
passes and the owner signs off.

## Deferred slices

These are deliberately unordered until v1 usage supplies evidence.

### OnePassword

- Integrate selected vault/item retrieval using the user's existing preferred
  OnePassword mechanism.
- Do not bulk-copy secrets into memory.
- Add narrowly defined write or fill behavior only after real use.

### Nexus

- Search and open Nexus resources through a stable authenticated interface.
- Preserve Nexus resource URIs in raw memories.
- Consider additive notes/highlights only after read behavior is useful.

### Skidbladnir

- Read machine and session state first.
- Preserve exact session identity in memory references.
- Do not expose generic terminal or SSH authority to Jarvis.

### Android

- Build only when Discord usage demonstrates a need for biometrics, widgets,
  quick capture, share targets, device-local context, or a richer private UI.
- Prefer native Kotlin and Jetpack Compose.

### Additional autonomy

- Add approval-bearing operations one at a time.
- Reduce approval only when repeated accepted actions establish a clear rule.
- Do not introduce a general permission framework preemptively.

## Features that require a new ADR

- A workflow engine.
- An explicit personal-domain object model.
- A graph database or separate vector/search service.
- Slash commands or a general Discord control surface.
- A provider other than Codex.
- Direct model access to connector credentials or execution authority.
- Destructive consolidation of raw memory.
- Autonomous code, prompt, permission, or deployment modification.

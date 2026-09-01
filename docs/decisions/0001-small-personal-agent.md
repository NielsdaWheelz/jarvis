# ADR 0001: Build one small personal agent system

- Status: Accepted
- Date: 2026-09-01

## Context

Jarvis is a personal-only assistant. Its desired value comes from access to the
user's context, useful memory, capable reasoning, and willingness to perform
tedious work. A service mesh, agent organization, project ontology, and broad
control plane would increase implementation surface before demonstrating value.

Rich Sutton's bitter lesson is about AI *methods* — general learning and search
beating hand-encoded human knowledge — and applying it directly to database
schema design would be borrowing authority the essay does not lend. The narrower
and sufficient argument stands on its own: we do not yet know which structure
this user's life actually needs, capable models over natural language and tools
may not need any, and an ontology written before that is known constrains the
system to a guess. Give the model the chance first.

## Decision

Build one visible Jarvis as a Python modular monolith with internal recaller,
rememberer, dreamer, and main-agent roles.

Use PostgreSQL as the only new state service. Do not add explicit tables for
people, projects, commitments, tasks, decisions, episodes, claims, or their
relationships.

Add structure only after a repeated measured failure shows that model reasoning
over memories and live tools is insufficient.

A bet with no scoreboard is a belief. The instrument that makes this falsifiable
is the per-turn trace on the response `message` row — candidate memory IDs,
selected memory IDs, and the IDs the main agent reports using — recorded from
Slice 1, plus the recall evaluation set frozen at Slice 3. Every escape hatch in
this specification releases on "measured failure"; these are what measure it.

## Consequences

Positive:

- The whole system remains understandable.
- Models retain freedom to discover useful abstractions.
- Early development targets user value rather than schema completeness.
- Removing or changing cognitive behavior is inexpensive.

Accepted costs:

- Some relationships will be inferred repeatedly.
- Natural-language memory will be less convenient for deterministic reporting.
- A successful future feature may justify migration into structured state.
- Model quality matters more than it would with a rigid domain model.

## Rejected alternatives

- A visible multi-agent organization: more interaction and debugging complexity
  without a user benefit.
- A personal knowledge graph: premature entity resolution and ontology work.
- A project-management data model: imposes current assumptions before Jarvis has
  demonstrated what it actually needs.
- A collection of microservices: inappropriate for one user and one host.

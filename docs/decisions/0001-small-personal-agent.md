# ADR 0001: Build one small personal agent system

- Status: Accepted
- Date: 2026-09-01

## Context

Jarvis is a personal-only assistant. Its desired value comes from access to the
user's context, useful memory, capable reasoning, and willingness to perform
tedious work. A service mesh, agent organization, project ontology, and broad
control plane would increase implementation surface before demonstrating value.

The bitter lesson favors general learning and computation over large collections
of hand-authored domain machinery. For v1, capable models operating over natural
language and tools should be given the opportunity to solve the problem before
we encode an ontology of the user's life.

## Decision

Build one visible Jarvis as a Python modular monolith with internal recaller,
rememberer, dreamer, and main-agent roles.

Use PostgreSQL as the only new state service. Do not add explicit tables for
people, projects, commitments, tasks, decisions, episodes, claims, or their
relationships.

Add structure only after a repeated measured failure shows that model reasoning
over memories and live tools is insufficient.

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

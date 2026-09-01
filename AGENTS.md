# Repository instructions

These instructions govern all work in this repository.

## Source of truth

- Read `SPEC.md` before proposing or making implementation changes.
- Read the relevant supporting document before changing that subsystem.
- Treat accepted ADRs as binding until superseded by a new ADR.
- If code and specification disagree, stop and surface the discrepancy. Do not
  silently reinterpret the specification.

## V1 constraints

- Keep the system small. Do not add infrastructure for hypothetical scale.
- Use Python 3.12 for server-side application code.
- Use subscription-backed Codex through the local `provider-runtime` library.
- Use the local `llm-tools` library for tool declarations, capability exposure,
  validation, budgets, and execution semantics.
- Do not add DBOS, Temporal, Restate, Celery, or another workflow framework.
- Do not add LangChain, LlamaIndex, CrewAI, AutoGen, or another agent framework.
- Do not add Redis, Kafka, Kubernetes, Elasticsearch, Neo4j, or a dedicated
  vector database without a new accepted ADR supported by measured need.
- Do not add people, projects, commitments, episodes, claims, procedures, or
  other personal-domain tables in v1.
- Do not add memory categories, confidence fields, salience scores, temporal
  validity models, or source-authority taxonomies.
- Do not add slash commands or speculative Discord components. Natural
  conversation plus Approve and Deny is the v1 interface.
- Do not add Android code in v1.
- Do not copy agent, orchestration, or memory implementation from Ariel.
- Reuse the working Gmail, Calendar, Maps, and Discord integrations and their
  existing authorizations. Audit and adapt their public surfaces; do not force
  new provider setup merely to make the architecture cleaner.
- Jarvis owns exactly four application tables: `message`, `memory_log`,
  `memory_summary`, and `action`. Adding another requires an accepted ADR.

## Conversation invariants

- `message` is the centralized conversation record across every client.
- Store every inbound owner message before processing it.
- Store every Jarvis response centrally.
- Enforce source-message uniqueness so adapter retries cannot duplicate history.
- Discord is a client and delivery surface, not canonical conversation storage.
- Provider sessions are disposable and reconstructable from `message` plus
  recalled memory.
- Tool execution belongs in `action`; learned context belongs in memory.

## Memory invariants

- `memory_log` is the canonical, append-only memory substrate.
- The rememberer may only append to `memory_log`.
- Normal consolidation must never edit or delete `memory_log` rows.
- `memory_summary`, embeddings, and search indexes are derived and rebuildable.
- Every summary must resolve directly to raw `memory_log` IDs.
- A summary built from other summaries must flatten its lineage to raw IDs.
- The recaller runs before every human input reaches the main agent.
- External resource references live inside natural-language memory text.

## Authority invariants

- The model never owns connector credentials.
- Host code executes tools through `llm-tools`.
- Reads, memory changes, local writes, personal calendar management, and Jarvis
  Discord-server management are automatic.
- Consequential communication to another person, spending money, exposing a
  secret, or irreversible destructive action requires Approve or Deny.
- Every tool call that mutates an external integration or local workspace is
  recorded once in `action`; reads and canonical message/memory transactions are
  not.
- Approval executes the exact stored `action` once. Do not interpret a free-form
  conversational reply as approval.

## Engineering rules

- Prefer plain functions, explicit data flow, and database transactions.
- Derived state must be safely rebuildable.
- Preserve user-owned changes in every repository.
- Never place credentials, OAuth tokens, email bodies, or private memory text in
  ordinary logs or fixtures.
- Every behavioral change needs tests against the acceptance criteria.
- Every dependency and model upgrade must be explicit and replay-tested.
- Avoid abstractions with only one caller unless they enforce a stated boundary.

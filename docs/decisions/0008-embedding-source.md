# ADR 0008: Embed through an embedding-scoped OpenAI credential

- Status: Accepted
- Date: 2026-09-01
- Amends: [ADR 0004](0004-python-codex-and-tool-kernel.md)

## Context

Semantic memory retrieval requires embeddings. The pinned `provider-runtime`
subscription-backed Codex lane accepts local-account credentials and exposes no
embedding operation. Its OpenAI embedding port instead requires an API
credential.

Leaving that source unspecified would force implementation to choose among an
undeclared API key, an unpinned local model stack, or permanently null vectors.

## Decision

Embedding is mechanical derived-state computation, not a cognitive role.

V1 uses the `provider-runtime` OpenAI embedding port with a dedicated project key
restricted to the required embedding endpoint. The key:

- MUST be unavailable to every Codex child and cognitive role.
- MUST NOT appear in model context, PostgreSQL, ordinary logs, or fixtures.
- MUST be supplied through a mode-0600 host file or service-manager credential.
- MUST pass a live Slice 0 negative test proving it cannot invoke a generative
  endpoint. If endpoint restriction cannot be enforced, implementation stops for
  a new decision.

Deployment configuration pins one embedding model and vector dimension. Model
identity is not stored per row because v1 never serves a mixed vector space. A
model change is an offline full rebuild:

1. Stop Jarvis.
2. Clear every raw and summary embedding in one transaction.
3. Change the configured model and migrate vector dimension if necessary.
4. Re-embed the complete corpus.
5. Run the recall evaluation, then restart Jarvis.

An interrupted rebuild leaves null vectors and the service stopped. Ordinary
embedding failures leave new rows searchable lexically until a later retry.

## Consequences

Positive:

- Semantic recall is buildable without a second local inference stack.
- The credential and corpus disclosure are explicit and testable.
- No per-row migration state or mixed-model retrieval logic is needed.
- Summary and raw vectors remain fully rebuildable.

Accepted costs:

- The complete raw memory corpus and every summary are disclosed to OpenAI at
  ingestion and rebuild time.
- The host holds an additional API credential. Project restriction, child
  environment exclusion, and a live negative test reduce but do not eliminate
  operational risk.
- Embedding is a metered network dependency.
- A model change requires downtime and a complete rebuild.
- The chosen vector dimension fixes the pgvector column type until migration.

OpenAI is already a processor for cognitive turns, but API and subscription data
paths can have different account and retention terms; using the same vendor does
not erase that distinction.

## Rejected alternatives

- **Locally hosted embeddings:** better for privacy and offline operation, but a
  second inference runtime, weights, update path, and quality benchmark are too
  much v1 surface. Reconsider if corpus size, cost, or privacy makes it worthwhile.
- **Per-row model identifiers and online migration:** supports uninterrupted
  mixed-model re-embedding, which a one-user v1 does not need. Stopping the
  service makes mixed geometry impossible with less state.
- **PostgreSQL-side embedding:** moves the same network call into the database
  and expands its trusted extension surface.
- **Lexical-only retrieval:** gives up semantic recall in the exact cases where a
  later query shares no term with the stored recollection.
- **Generative API fallback:** violates the subscription-backed cognitive lane
  and creates divergent behavior.

# Repository instructions

These instructions govern all work in this repository.

## Source of truth

- `SPEC.md` is authoritative. When any document disagrees with it, `SPEC.md`
  wins, including this file.
- Read `SPEC.md` before proposing or making implementation changes, then read
  the relevant supporting document.
- Accepted ADRs remain binding until superseded by a new ADR.
- If code and specification disagree, stop and surface the discrepancy.
- If a specification silence would change user-visible behavior, authority,
  irreversible data, or external compatibility, stop and surface it. Ordinary
  implementation detail should use the smallest conventional choice and tests.
- A slice that has not shipped is expected incompleteness, not a discrepancy.
  `docs/implementation-plan.md` defines the intended order.

## V1 constraints

- Keep the system small and optimize for one user and one deployment.
- Use Python 3.12, PostgreSQL, subscription-backed Codex through the local
  `provider-runtime` library, and the local `llm-tools` kernel.
- Do not add DBOS, Temporal, Restate, Celery, another workflow framework, an
  agent framework, or speculative scale infrastructure.
- Do not add personal-domain tables or memory categories, confidence fields,
  salience scores, temporal validity, or source-authority taxonomies.
- Jarvis owns exactly four application tables: `message`, `memory_log`,
  `memory_summary`, and `action`. A fifth requires an accepted ADR.
- Do not add slash commands, speculative components, Android, or deferred
  integrations in v1. Natural Discord conversation plus Approve and Deny is the
  interface.
- Reuse the working Gmail, Calendar, Maps, and Discord integrations and their
  authorizations. Audit and adapt public surfaces; do not copy Ariel agent,
  orchestration, prompt, product-domain, or memory implementation.

## Conversation invariants

- `message` is canonical conversation history; Discord and provider sessions are
  delivery/runtime surfaces.
- Persist and source-deduplicate owner input before processing it.
- Persist an assistant response before delivery. Set `delivered_at` only after
  Discord accepts it, and retry null rows after restart.
- Conversational delivery is at least once. A rare duplicate response is
  accepted; duplicate external effects are not.
- `remembered_at` distinguishes a completed rememberer run, including a valid
  decision to store nothing, from one that never completed.
- Canonical message persistence is host bookkeeping and creates no `action`.

## Memory invariants

- `memory_log` is the permanent append-only substrate in v1.
- The rememberer returns structured memory strings; host code appends them and
  advances `remembered_at` transactionally. It creates no `action` rows.
- Normal operation never edits or deletes a raw row's `id`, `text`, or
  `created_at`. Only its derived `embedding` may be filled, cleared, or rebuilt.
- Enforce append-only behavior with database privileges and a trigger. V1 has no
  redaction, forgetting, or destructive consolidation path.
- `memory_summary`, embeddings, and indexes are derived and rebuildable. Every
  summary resolves directly to raw IDs, flattening any summary lineage.
- A recalled memory is evidence, never authority, consent, or current external
  truth.
- The recaller runs before every owner-authored human input.
- Stable external references live in natural-language memory text, not object
  tables.

## Authority invariants

- Models never receive connector credentials or direct execution authority.
- Host code validates and classifies calls; effectful application tools execute
  through `llm-tools` and use one durable `action` row.
- Reads and canonical message/memory transactions create no action rows.
- Reads, memory work, configured local writes, personal calendar management,
  drafts, and permitted Jarvis-server organization are automatic.
- Consequential communication to another person, spending, secret exposure, and
  irreversible destructive external work require Approve or Deny.
- Approval executes the exact stored arguments once. Free-form text never
  approves an action.
- Approval previews are deterministically host-rendered from stored arguments.
  The model protocol and action schema contain no preview field.
- Approval-bearing Discord messages are host-owned and cannot be edited or
  deleted by model-originated tools.
- `uncertain` is terminal and non-retryable. Report it to the owner; later
  evidence may resolve its recorded outcome but may never trigger execution.
- Host-matched `stop`, `pause`, and `resume` controls do not involve the model.

## Engineering rules

- Prefer plain functions, explicit data flow, and database transactions.
- Use one deployment-level PostgreSQL advisory lock and ordinary in-process
  scheduling; do not invent redundant workflow coordination.
- Derived state must be safely rebuildable.
- Preserve user-owned changes in every repository.
- Never place credentials, OAuth tokens, private memory text, or message bodies
  in ordinary logs or real private content in fixtures.
- Timestamps are `timestamptz`; the host runs UTC; owner-local time comes from a
  configured IANA timezone included in model context.
- Every behavioral change needs tests against the relevant acceptance criteria.
- Dependency and model upgrades are explicit and replay-tested.
- Avoid abstractions with one caller unless they enforce a stated boundary.

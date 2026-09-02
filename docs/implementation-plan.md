# V1 implementation plan

Each slice is a small vertical increment. The plan names intended sequence, not a
workflow system or calendar schedule.

## Slice 0: audit and qualification

Deliver:

- Delegated summaries of the existing Discord, Gmail, Calendar, and Maps
  integration surfaces without importing unrelated Ariel design.
- The configured Discord guild/owner/channel IDs, exact four bot permissions,
  minimal Gateway intents, and bounded history-catch-up behavior.
- One owning process for each reused credential and an explicit Ariel/Jarvis
  handoff or local-interface plan.
- Pinned git dependencies for `provider-runtime` and `llm-tools` that do not
  touch the user's local worktrees.
- Linux qualification of the pinned Codex SDK/runtime containment policy plus
  start, continue, and resume behavior.
- A restricted embedding API key plus a live negative generative-call test.
- Live Gmail checks for draft-send and reconciliation behavior on new and reply
  threads.
- The verified owner-only Calendar ID set.

Exit: every required external surface and credential has a known owner,
interface, and test strategy.

## Slice 1: conversation skeleton

Deliver:

- Python project, lockfile, PostgreSQL, and migrations.
- `message` table and owner/source identity.
- Existing Discord ingress/egress restricted to one configured channel, with no
  model-callable Discord tools.
- Inbound deduplication.
- Bounded owner-message catch-up after downtime.
- Persist-before-send assistant messages using null `source_message_id` as the
  delivery watermark.
- `processed_at` turn completion and interrupted-turn recovery.
- Prompt typing state, stop/pause/resume, and no streaming.
- Provider-neutral context package with continuation and bootstrap projections.
- Subscription-backed main Codex session with `say` and `finish`, one atomically
  persisted session reference and configuration digest, compatible resume, and
  cold bootstrap after a digest change or session loss.
- A fake stateless adapter test proving bootstrap context contains no Codex SDK
  types and carries the current owner message exactly once.
- Deployment ownership lock and in-process provider mutex.

Exit: natural conversation in one channel survives compatible session resume
and deliberate session loss, a simulated outbound-delivery failure is retried,
and an interrupted effect-free turn is safely replayed.

## Slice 2: read tools

Deliver:

- Jarvis-owned `llm-tools` catalog, profiles, bounds, and executor.
- No Discord declarations in the model tool catalog; conversation delivery stays
  in the adapter.
- Strict `call_tool | say | finish` schema.
- Existing Gmail read/search bindings.
- Existing Calendar read bindings.
- Existing Maps lookup bindings.
- Typed observations and bounded tool loops.
- Confined Codex drift tests.

Exit: Jarvis answers a natural compound question using all live read services
without exposing credentials to Codex.

## Slice 3: raw memory and recall

Deliver:

- Exact `memory_log` schema and append-only database enforcement.
- Host-owned rememberer commit with `remembered_at` in the same transaction.
- Full-text search and nullable OpenAI embeddings.
- Memory search/open tools for the recaller only.
- Fresh isolated recaller before every owner input and fresh isolated rememberer
  after every eligible completed turn.
- Stable external-reference convention.
- Fifteen-case owner-authored redacted recall evaluation set.
- Bounded retry sweep for completed unremembered turns.

Exit: a durable preference and linked external matter are recalled in a fresh
provider session, and memory persistence creates no action row or duplicate text.

## Slice 4: dreaming and summaries

Deliver:

- Exact `memory_summary` schema with raw lineage.
- Fresh isolated dreamer search/open profile.
- Structured final summary-mutation batch and host-owned transaction.
- Simple idle/system timer with one dreamer at a time.
- Full derived-memory rebuild command.
- Contradiction, unsupported-summary, lineage, and pre/post rebuild tests.

Exit: wiping every summary and embedding and rebuilding from raw memory preserves
or improves the recall evaluation result.

## Slice 5: automatic writes and proactivity

Deliver:

- Exact minimal `action` schema, unversioned immutable calls, seven statuses, and
  terminal-for-execution `uncertain` semantics.
- Existing Gmail draft binding.
- Existing owner-only Calendar writes.
- Automatic/approval classification owned by host code.
- `schedule_wake`, quiet-hour delay, and periodic read-only connector reconcile.
- Bounded external timeouts and startup reconciliation of `executing` actions,
  without leases, attempt counters, or blind retry.
- Interrupted turns that already created an action close without model replay.

Exit: Jarvis performs a draft, personal calendar change, and scheduled proactive
message in the configured channel without unnecessary approval or workflow
framework.

## Slice 6: Approve and Deny

Deliver:

- Gmail send as draft-send by stored `draftId`.
- Host preview renderers for Gmail send and non-owner-only calendar writes, with
  no model preview field or action preview column.
- Long-action rendering through host-owned split messages or attachment.
- Host-owned Approve/Deny message and immediate interaction acknowledgement.
- Owner/guild/channel/approval-message validation.
- `approval_message_id`, atomic claim, duplicate-click protection, and
  Gmail-specific reconciliation.
- Free-form approval rejection and terminal uncertainty reporting.

Exit: Deny sends nothing; Approve sends the exact rendered email once; a shared
calendar change is also rendered exactly; an ambiguous result is reconciled or
reported without blind retry.

## Slice 7: production acceptance

Deliver:

- Always-on Linux deployment.
- Secret and configuration procedure.
- Daily encrypted backup and off-host copy.
- Clean-host restore test.
- Configuration-compatible Codex session resume plus recovery after deleting
  every provider session reference.
- Complete acceptance run.
- Seven-day owner acceptance period.
- Dated acceptance report.

Exit: every non-waived mandatory criterion in `docs/acceptance.md` passes and the
owner signs off.

## Deferred slices

### Discord workspace expansion

- Add a second channel or thread only after single-channel use demonstrates a
  concrete routing or noise problem.
- Design channel/session mapping from observed continuation semantics.
- Grant and expose only the additional Discord operations the chosen behavior
  requires.

### API-backed cognitive provider

- Reuse the provider-neutral bootstrap context package and canonical message
  store.
- Add a provider adapter rather than a second context-selection path.
- Decide credentials, continuation, compaction, cost, and fallback policy in a
  dedicated ADR before implementation.

### OnePassword

- Retrieve selected items using the owner's preferred OnePassword interface.
- Never copy vault contents into memory in bulk.
- Add writes only after read behavior proves useful.

### Nexus

- Search and open resources through a stable authenticated interface.
- Preserve Nexus resource URIs in raw memory.
- Consider additive notes/highlights after read use is proven.

### Skidbladnir

- Read machine and exact session state first.
- Preserve session identity in memory references.
- Never substitute generic terminal or SSH authority for an adapter.

### Android

- Build only when Discord usage demonstrates a need for biometrics, widgets,
  capture, share targets, device context, or a more private interface.
- Prefer native Kotlin and Jetpack Compose.

### Administrative memory erasure

- Design only if requested.
- Cover messages, raw memory, summaries, action payloads, traces, provider state,
  backups, Discord, and live source systems.
- Do not promise erasure by tombstoning only one table.

## Changes requiring an ADR

- A fifth application table.
- A semantic memory field or explicit personal-domain model.
- A workflow or agent framework.
- A graph or separate vector/search service.
- Slash commands or a general control surface.
- More than one Jarvis Discord channel, Discord threads or direct messages, or
  model-callable Discord management.
- A cognitive provider other than subscription-backed Codex.
- Direct model credentials, MCP execution authority, or generic shell access.
- Destructive raw-memory consolidation or administrative erasure.
- Android or a new external service in v1.

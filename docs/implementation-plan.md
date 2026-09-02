# V1 implementation plan

Each slice is a small vertical increment. The plan names intended sequence, not a
workflow system or calendar schedule.

## Slice 0: audit and qualification

Status: owner-authorized on 2026-09-01; qualification findings not yet produced
or accepted.

Deliver:

- Delegated summaries of the existing Discord, Gmail, Calendar, and Maps
  integration surfaces without importing unrelated Ariel design.
- The exact canonical tool manifest, schemas, typed observations, and live
  automatic/approval classification from SPEC section 7.3.
- The configured Discord guild/owner/channel IDs, exact four bot permissions,
  minimal Gateway intents, and bounded history-catch-up behavior.
- Live Discord confirmation that `enforce_nonce` returns the existing message
  for the same recent bot nonce and that history exposes that nonce.
- Qualification of `discord.py` 2.7.1 for Gateway/interactions and direct
  `httpx` Discord REST v10 Create Message for enforced nonces, with no private
  client-library API.
- One owning process for each reused credential and an explicit Ariel/Jarvis
  handoff or local-interface plan.
- Credential discovery from Ariel's local operator configuration first; if a
  required credential is absent, a delegated read-only inventory of the
  user-owned development-server repository. Secret values never enter agent
  summaries, model context, the qualification report, or ordinary logs; any
  delegated transfer is a non-echoing copy directly into mode-0600
  service-manager credential files.
- Pinned git dependencies for `llm-agent-kernel`, `provider-runtime`, and
  `llm-tools` that do not touch the user's local worktrees.
- Upgrade `llm-tools` in its own repository to expose qualified public pure
  argument validation, frozen-profile tightening, `HostTable` publication, and
  async durable executor/recorder seams; pin the resulting revision before any
  Jarvis runtime implementation.
- Qualification of the kernel's exact `AgentRuntime` request/lifecycle,
  context, session-reference, input-checkpoint, polling, dispatch, admission,
  cancellation, and optional observability ports plus its multi-run conformance
  suite. Confirm it owns no database schema, connector, product authority, or
  duplicate provider/tool implementation.
- Live `llm-tools` Brave-search and safe-public-Web-read canaries, including
  private-destination, unsafe-redirect, and credential-egress rejection.
- Linux qualification of the pinned Codex SDK/runtime containment request,
  `JsonSchemaAgentOutput`, open/run/close and resume behavior, and fail-stop on
  native tool-use or permission-request events.
- A restricted embedding API key plus a live negative generative-call test.
- Live Gmail checks for draft-send and reconciliation behavior on new and reply
  threads.
- The verified owner-only Calendar ID set plus a live client-generated event-ID,
  duplicate-response, and get-by-ID check.
- A dated, sanitized qualification report carrying the owner's explicit
  sign-off after review of the observed results.

Exit: every required external surface and credential has a known owner,
interface, and test strategy, every live check passes, and the owner signs off
the resulting report. Authorization to run this slice is not advance acceptance
of unknown findings. No Slice 1 implementation starts before this exit.

## Slice 1: conversation skeleton

Deliver:

- Python project, lockfile, PostgreSQL, and migrations.
- Pinned `llm-agent-kernel` integration with Jarvis-owned product-context,
  session-reference, input-checkpoint, and terminal-finalization adapters.
- Conversational main output contract plus closed structured output contracts
  for isolated recaller, rememberer, and dreamer one-shot runs.
- `message` table, owner/source identity, and durable `processing_attempts`.
- Existing Discord ingress/egress restricted to one configured channel, with no
  model-callable Discord tools.
- Inbound deduplication.
- Bounded owner-message catch-up after downtime.
- Persist-before-send assistant messages using null `source_message_id` as the
  delivery watermark.
- Deterministic 20-character Discord nonce derivation, `enforce_nonce=true` on
  every create, same-nonce retry, and bounded history reconciliation before a
  delayed retry.
- Narrow typed Discord REST v10 Create Message binding over `httpx`; retain
  `discord.py` for Gateway/interactions.
- `processed_at` turn completion and interrupted-turn recovery.
- Prompt typing state, stop/pause/resume, and no streaming.
- Jarvis product-context selection feeding provider-neutral kernel continuation
  and bootstrap projections rendered with `llm-tools` typed prompt sections.
- Subscription-backed main Codex definition in `continuing` mode with `say` and
  `finish`, one atomically persisted session reference and agent-definition
  fingerprint, compatible resume through `provider-runtime`, and cold bootstrap
  after a fingerprint change or session loss; successful stores advance the
  expected generation and a stale compare-and-set stops before dispatch or
  settlement.
- Exclusive non-empty claim over messages, host-selected full or scheduled-wake
  read-only plan, ordered watermark, mid-loop compatible-input polling, stop
  preemption, and atomic conclusion/`processed_at` settlement. Incompatible work
  remains unclaimed; cleanup never arms a successor.
- Host-authored poison-input conclusions, durable reclaim ceiling, and a
  content-free atomically replaced rolling-admission journal that caps provider
  turns, reported tokens, no-progress attempts, and cognitive concurrency at
  one.
- A fake stateless adapter test proving bootstrap context contains no Codex SDK
  types and carries the current owner message exactly once.
- Kernel conformance fixtures for session loss, invalid protocol, cancellation,
  a crash between session-reference advancement and canonical settlement, an
  compatible input arriving mid-loop, ordinary input arriving during final
  settlement, stop preemption, poison input, crash reclaim, rolling admission,
  and exhausted bounds.
- Deployment ownership lock and in-process provider mutex.

Exit: natural conversation in one channel survives compatible session resume
and deliberate session loss, lost Discord acknowledgement and delayed-restart
fixtures each leave exactly one visible response, an interrupted effect-free
turn is safely replayed, and input racing with idle is never stranded.

## Slice 2: read tools

Deliver:

- Jarvis-owned application declarations/bindings, product policy, and frozen
  role plans composed through `llm-tools`; the library retains schema,
  validation, prompt-section, budget, and execution ownership.
- No Discord declarations in the model tool catalog; conversation delivery stays
  in the adapter.
- Kernel-owned strict `call_tool | say | finish` schema, complete semantic and
  pure-argument validation before mutation, exactly one serial call with no
  model-authored ID or prose, bounded corrective feedback, and a separate `say`
  only after the model observes its result.
- `gmail.search` and `gmail.read_thread` bindings.
- `calendar.list_events` and `calendar.get_event` bindings.
- `maps.search_places`, `maps.get_place`, and `maps.directions` bindings.
- Pinned `llm-tools` `web.search` and `web.read` bindings under Jarvis-owned
  credentials, information-flow policy, and budgets.
- One bounded completed observation or durable suspension per call; the Jarvis
  dispatch adapter retains product authority and supplies original validated
  call evidence on later resolution.
- Confined Codex drift tests.

Exit: Jarvis answers a natural compound question using Gmail, Calendar, Maps,
public-Web search, and a fetched public page without exposing credentials to
Codex or granting the Codex child native network access.

## Slice 3: raw memory and recall

Deliver:

- Exact `memory_log` schema and append-only database enforcement.
- Host-owned rememberer commit with `remembered_at` in the same transaction.
- Full-text search and nullable OpenAI embeddings.
- Memory search/open tools for the recaller only.
- Fresh `SessionMode.isolated` kernel recaller before every owner input and fresh
  isolated rememberer after every eligible completed turn; both use one-shot
  execution, touch no input-checkpoint or saved-session port, and return closed
  structured `finish.result` payloads.
- Stable external-reference convention.
- Fifteen-case owner-authored redacted recall evaluation set.
- Bounded retry sweep for completed unremembered `role = owner` turns only.

Exit: a durable preference and linked external matter are recalled in a fresh
provider session, and memory persistence creates no action row or duplicate text.

## Slice 4: dreaming and summaries

Deliver:

- Exact `memory_summary` schema with raw lineage.
- Fresh `SessionMode.isolated` kernel dreamer one-shot search/open profile with a
  closed structured `finish.result` mutation batch.
- Structured final summary-mutation batch and host-owned transaction.
- Simple idle/system timer with one dreamer at a time.
- Full derived-memory rebuild command.
- Contradiction, unsupported-summary, lineage, and pre/post rebuild tests.

Exit: wiping every summary and embedding and rebuilding from raw memory preserves
or improves the recall evaluation result.

## Slice 5: automatic writes and proactivity

Deliver:

- Exact minimal `action` schema, including immutable `execution_contract` and
  executor-entry `attempts`, unversioned tool names, seven statuses, and
  terminal-for-execution `uncertain` semantics.
- `gmail.create_draft` and `gmail.update_draft` bindings.
- `calendar.create_event`, `calendar.update_event`, and
  `calendar.delete_event` bindings.
- Action-derived Calendar create IDs plus get-and-compare reconciliation for
  create/update/delete ambiguity.
- Automatic/approval classification owned by host code.
- Owner-requested `schedule_wake` with closed create/cancel variants, exact
  due-time and restart behavior; no generic quiet hours, connector polling, or
  autonomous inbox/calendar monitor.
- Idempotent due-wake host messages rendered from immutable stored instructions,
  plus visible model/fallback delivery and atomic scheduled-action completion.
- Bounded external timeouts and startup reconciliation of `executing` actions;
  `uncertain` only after the complete tool-specific automatic procedure is
  exhausted, without leases or blind retry. The attempt count records each
  executor entry and never authorizes another.
- `action.id` mapping to both `llm-tools` `InvocationPosition` and `EffectId`,
  with the per-row contract binding tool/policy/plan revisions, effect/replay
  declarations, and canonical input digest.
- Interrupted turns that already created an action close without model replay.
- Base idempotent host-authored action-resolution messages for outcomes that
  cannot return to a live originating loop, keyed by action ID plus resolved
  state, with startup repair, visible deterministic fallback, and checkpoint
  processing through the existing `message` table.

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
- Bounded Gmail draft/Sent re-reads before terminal uncertainty, with evidence
  presented for owner inspection.
- Free-form approval rejection and terminal uncertainty reporting.
- Approval-specific action-resolution and fallback fixtures using the Slice 5
  existing-table mechanism.

Exit: Deny sends nothing; Approve sends the exact rendered email once; a shared
calendar change is also rendered exactly; an ambiguous result is reconciled or
reported without blind retry.

## Slice 7: production acceptance

Deliver:

- Always-on Linux deployment.
- Secret and configuration procedure.
- Daily encrypted backup and off-host copy.
- Clean-host restore test.
- Agent-definition-compatible Codex session resume through `provider-runtime`
  plus recovery after deleting every provider session reference.
- Restart/crash qualification for poison attempts, no automatic rearm, rolling
  admission settlement, corrupt-journal fail-closed behavior, and explicit
  operator reset on a clean restore.
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

- Reuse Jarvis product context selection, the canonical message store, and the
  kernel bootstrap/context ports.
- Add a `provider-runtime` adapter rather than a second context-selection or
  agent-loop path.
- Decide credentials, continuation, compaction, cost, and fallback policy in a
  dedicated ADR before implementation.

### Task-scoped delegation

- Add only after a real Jarvis task demonstrates that fixed main/recaller/
  rememberer/dreamer roles cannot handle it efficiently.
- Require a task ID and parent ID, explicit role and objective, strictly narrowed
  capability plan, child budgets and deadline, structured terminal result,
  observe/join/cancel, and cancellation propagation.
- Do not use persistent same-authority peer agents or treat the fixed memory
  roles as a delegation system.
- Add no v1 tool, table, or column in anticipation.

### Program agents / CodeAct

- Evaluate direct serial `call_tool` against a model-generated program surface only
  after compound tasks show excessive model round trips.
- Measure completion quality, calls, tokens, latency, invalid programs, recovery,
  duplicate-effect behavior, and approval behavior before selecting Lua,
  JavaScript, Python, or another constrained runtime.
- Keep any interpreter/sandbox in a separate optional library; do not make it a
  transitive requirement of `llm-agent-kernel` or Jarvis.
- Require every effect to cross `llm-tools`; do not suspend a program while
  waiting for Discord approval.

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

### Broader tools and autonomous monitoring

- Add Gmail labels, archive, trash, attachment download, or other mailbox
  organization only after actual use identifies a specific burden.
- Add local-filesystem access only with an observed use case and an explicit
  confined root and operation set; never start from generic file authority.
- Add inbox/calendar monitoring, connector polling, notification policy, or
  quiet hours only after requested wakes prove insufficient and observed noise
  defines the policy.

## Changes requiring an ADR

- A fifth application table.
- A semantic memory field or explicit personal-domain model.
- A workflow framework or general agent platform beyond `llm-agent-kernel`.
- Task-scoped delegation, persistent peer agents, or a model-generated program
  runtime.
- A graph or separate vector/search service.
- Slash commands or a general control surface.
- More than one Jarvis Discord channel, Discord threads or direct messages, or
  model-callable Discord management.
- A cognitive provider other than subscription-backed Codex.
- Direct model credentials, MCP execution authority, or generic shell access.
- Destructive raw-memory consolidation or administrative erasure.
- Android or an application service beyond the frozen v1 catalog.

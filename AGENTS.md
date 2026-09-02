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
- Use Python 3.12, PostgreSQL, the pinned `llm-agent-kernel` library,
  subscription-backed Codex through `provider-runtime`, and the `llm-tools`
  tool-contract and execution library.
- Do not add DBOS, Temporal, Restate, Celery, another workflow framework, a
  general agent framework beyond the approved bounded kernel, or speculative
  scale infrastructure.
- Do not add personal-domain tables or memory categories, confidence fields,
  salience scores, temporal validity, or source-authority taxonomies.
- Jarvis owns exactly four application tables: `message`, `memory_log`,
  `memory_summary`, and `action`. A fifth requires an accepted ADR.
- The three additional irreducible durability fields are
  `message.processing_attempts`, `action.execution_contract`, and
  `action.attempts`. Do not expand them into a generic workflow/version system.
- Do not add slash commands, speculative components, Android, or deferred
  integrations in v1. Natural Discord conversation plus Approve and Deny is the
  interface.
- Discord v1 is exactly one configured guild channel. Do not add Discord
  threads, direct messages, channel organization, reactions, broad message
  management, or model-callable Discord tools.
- Use `discord.py` 2.7.1 for Gateway/interactions and the narrow host-owned
  `httpx` REST v10 Create Message binding for enforced nonces. Do not depend on
  private `discord.py` internals.
- Reuse the working Gmail, Calendar, Maps, and Discord integrations and their
  authorizations. Audit and adapt public surfaces; do not copy Ariel agent,
  orchestration, prompt, product-domain, or memory implementation.
- The v1 model tool catalog is exactly SPEC section 7.3. Use the pinned
  `llm-tools` `web.search` and `web.read`; do not add local-filesystem, Gmail
  organization, tool-discovery, Discord, or other model tools.

## Conversation invariants

- `message` is canonical conversation history; Discord and provider sessions are
  delivery/runtime surfaces.
- Normally continue and resume one main Codex session, but treat its reference,
  history, compaction, and cache state as disposable. Jarvis must supply the
  product context selected from canonical messages, plus recall for owner input,
  through the `llm-agent-kernel` reconstruction ports.
- Resume the main session only when its immutable agent-definition fingerprint
  matches; the fingerprint is rebuildable runtime state, not a table column or
  tool version.
- Recaller, rememberer, and dreamer invocations use fresh isolated sessions.
- The kernel owns the exact `say | call_tool | finish` model-step grammar,
  validates the entire step and pure arguments before dispatch, and permits
  exactly one serial call per step. `call_tool` carries no user-facing text or
  model-authored call/effect ID. Internal one-shot roles use plans containing no
  `ToolEffect.Write` and closed structured `finish.result` contracts.
  Definitions hold maximum capability envelopes; each run gets a proven frozen
  tightening, with scheduled-wake runs narrowed to reads. Jarvis—not the
  kernel—selects priority, compatibility, batching, and the plan.
  `llm-tools` owns typed prompt sections and tool contracts/execution;
  `provider-runtime` owns provider calls and native session lifecycle. Do not
  duplicate those layers in Jarvis.
- Persist and source-deduplicate owner input and required host-authored action
  resolutions before processing them.
- Increment `message.processing_attempts` when an admitted claim begins provider
  work. Deterministic poison stops consume the row; cleanup never automatically
  rearms it. Startup/recovery scans canonical null-`processed_at` rows under the
  attempt ceiling and rolling admission.
- Poll compatible owner input before provider turns, dispatch, after tool
  completion, and before settlement. Stop/pause preempts. An ordinary follow-up
  racing after the final poll gets the already-valid answer first and its own run
  next.
- Set a waking message's `processed_at` only in the transaction that records its
  durable turn conclusion. Never replay an interrupted owner turn that already
  created an action.
- Persist an assistant response before delivery. A null `source_message_id` is
  the outbound retry watermark; fill it with the adapter's ID after delivery or
  history reconciliation.
- Derive the Discord nonce from `message.id` exactly as SPEC section 4.3 states,
  set `enforce_nonce=true`, and reuse it for every retry. A delayed retry must
  reconcile bounded history first; an incomplete check leaves the row pending.
- `remembered_at` distinguishes a completed rememberer run, including a valid
  decision to store nothing, from one that never completed.
- Retry memory formation only for `role=owner`; host action-resolution and
  scheduled-wake rows never enter the rememberer sweep.
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

- Models never receive connector, Brave, or embedding credentials or direct
  execution authority.
- V1 uses the real `AgentRuntime` lane with the closed JSON-schema output,
  private empty read-only cwd, disabled built-ins/Web/network/environment/MCP,
  and approval deny. Any native tool-use or permission-request event fails and
  discards the session.
- Host code validates and classifies calls; effectful application tools execute
  through `llm-tools` and use one durable `action` row.
- Reads and canonical message/memory transactions create no action rows.
- Catalogued reads, memory work, email drafts, personal calendar management,
  scheduled wakes, and normal responses in the configured Discord channel are
  automatic.
- Consequential communication to another person, spending, secret exposure, and
  irreversible destructive external work require Approve or Deny.
- Approval executes the exact stored arguments once. Free-form text never
  approves an action.
- Approval previews are deterministically host-rendered from stored arguments.
  The model protocol and action schema contain no preview field.
- Approval-bearing Discord messages are host-owned and cannot be edited or
  deleted by model-originated tools.
- Keep canonical `tool_name`, `arguments`, and `origin_message_id` immutable.
  Also keep the host-authored `execution_contract` immutable. V1 tool names are
  unversioned; the contract snapshot binds the occupied position's tool, policy,
  plan, effect/replay declarations, and input digest. Revalidate both before
  approval rendering and execution; drain non-terminal actions before an
  incompatible tool change.
- Action states are exactly `queued`, `awaiting_approval`, `executing`,
  `succeeded`, `failed`, `uncertain`, and `cancelled`.
- The single deployment owner reconciles rows left `executing` after a timeout or
  restart. Increment `action.attempts` immediately before actual executor entry;
  the count records, but never authorizes, an evidence-proven safe repeat. Do not
  add action leases, intent keys, client references, multi-call vectors, or a
  general version registry without measured need and a new ADR.
- Use `action.id` as deterministic provider effect identity where the provider
  supports it, including Calendar create IDs, and as both the `llm-tools`
  `InvocationPosition` and `EffectId` for every `Write`.
- `uncertain` is terminal and non-retryable, and is allowed only after the
  complete tool-specific automatic reconciliation procedure is exhausted.
  Present the evidence to the owner; later evidence may resolve the outcome but
  may never trigger execution.
- An action outcome that cannot return to its live originating model loop creates
  one idempotent host-authored waking `message`, keyed by `action.id` plus
  resolved status; do not reuse the turn-local model call ID as durable
  correlation or rewrite an earlier uncertain resolution.
- Host action-resolution and scheduled-wake inputs must produce a visible
  `say` or deterministic host-rendered assistant fallback; never process them
  silently. Due-wake input is rendered from immutable stored arguments.
- Host-matched `stop`, `pause`, and `resume` controls do not involve the model.
- Only an owner-requested due `schedule_wake` starts a user-facing proactive
  turn. Do not add generic quiet hours, connector polling, or autonomous
  inbox/calendar monitoring in v1.

## Engineering rules

- Prefer plain functions, explicit data flow, and database transactions.
- Jarvis owns product context selection, its kernel port adapters, Discord,
  memory, connectors, policy, approvals, actions, scheduling, and credentials.
  Do not move product authority into `llm-agent-kernel`.
- Use one deployment-level PostgreSQL advisory lock and ordinary in-process
  scheduling; do not invent redundant workflow coordination.
- Require host rolling admission before provider I/O. Keep the private journal
  content-free, settle it on every exit, cap concurrency at one, and fail closed
  on corrupt state.
- Derived state must be safely rebuildable.
- Preserve user-owned changes in every repository.
- Never place credentials, OAuth tokens, private memory text, or message bodies
  in ordinary logs or real private content in fixtures.
- Timestamps are `timestamptz`; the host runs UTC. Each cognitive session
  receives the configured owner IANA timezone once when it opens. Each owner
  input batch or background job receives one host-generated `as_of`; a batch
  appended mid-loop gets its own. Embedding and tool-only continuations do not
  receive a repeated clock.
- Every behavioral change needs tests against the relevant acceptance criteria.
- Dependency and model upgrades are explicit and replay-tested.
- Avoid abstractions with one caller unless they enforce a stated boundary.

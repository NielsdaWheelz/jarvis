# Repository instructions

These instructions govern all work in this repository.

## Source of truth

- `SPEC.md` is authoritative. When any document disagrees with it, `SPEC.md`
  wins, including this file.
- Read `SPEC.md` before proposing or making implementation changes, then read
  the relevant supporting document.
- Accepted ADRs remain binding until superseded by a new ADR.
- [adr 0065](docs/decisions/0065-native-agent-supervision.md) owns the current
  native main, request/control journals, owner-permit admission and separate
  contained stock endpoint. it supersedes affected step/session/rolling-capacity
  rules below; isolated role contracts remain. its temporary integration/live
  checks are the scoped testing exception. adr 0064's worker tools use the same
  native dispatch lane and immutable action capture; no retired thread loop.
- adr 0053 retains only the selected deployment release and one temporary
  installation candidate. do not keep rollback or migration releases indefinitely.
- adr 0046 governs the owner-approved testing reset. all previous test and
  qualification execution gates are suspended pending the subsequent redesign;
  runtime safeguards and product requirements remain binding.
- [universal memory](docs/universal-memory.md) is the consolidated accepted
  target, adopted by SPEC and most recently simplified by
  [adr 0063](docs/decisions/0063-simplify-memory-policy-and-retrieval.md).
  it supersedes affected baseline rules below when implemented: nine tables,
  automatic activation and whole-event capture, source-only size/age extraction with no overlap, direct
  lineage, pending-note dreaming, shared rank-fused search and no recaller or
  forgetting. historical import/provenance remain deferred.
- preserve atomic archive/checkpoint, notes/bookmark and summaries/pending commits.
  rememberer/dreamer use disposable kernel inference and dreamer run-local read
  receipts: interrupted paid computation may repeat under new admission. no
  durable background replay scopes. main/gate journals, external effect recovery,
  main paid-read barriers and shared capacity accounting remain unchanged.
- agents choose their procedure from context, tools, goals and quality constraints.
  no mandatory first tool/search, minimum call count or scripted research sequence;
  dreamer seed-only/empty completion is valid. host authority, grants, protocol,
  lineage and atomic completion are still enforced.
- make shared policy global: one definition per constant, one settings/client/pool
  composition, shared limits across callers and no per-profile tuning/allowances.
  reuse existing primitives and remove duplicate implementations. preserve scoped
  provenance/permissions/progress and fresh per-run execution state; do not replace
  these facts with mutable global turn state. operator status stays in the cli.
- external `memory_save_note` requires lane admission and connection. optional
  conversation identity is caller-reported; never require discovery. main's
  internal `memory.save_note(text)` uses the same append under jarvis admission,
  its existing model-decision position as invocation/effect identity, and the
  narrow local-write `read_position` recovery. this exact write bypasses the
  gate/action rules; no scheduled/background grant or native cognition mcp.
  archive memory-tool prose as content-free references to prevent feedback.
- retain two small regression groups: capture/retry and memory completion. no
  standing per-feature review machinery or restoration of the retired suite;
  the wider testing redesign remains open. no runtime change is implied by docs.
- [adr 0052](docs/decisions/0052-cut-worker-control-to-current-skid.md) governs
  installed worker control; [adr 0064](docs/decisions/0064-simple-worker-orchestration.md)
  owns the implemented next target contract and current qualification record.
  the owner explicitly authorized source implementation and temporary
  integration/live checks; installed cutover remains separate. both use
  the skid cli and private three-peer config. adr 0052 supersedes the worker
  transport, roster, refs and receipt codecs of
  adrs 0044/0045/0048/0049; cognition remains on the same existing Codex
  appserver/daemon and its deployment repair is separate.
- preserve captured target kind/ref and independent interruption/closure facts
  through admission and execution. require current owner input before target lookups.
  worker writes are billed once, with one lifetime executor entry. finalized
  retired worker rows remain opaque; unfinished retired rows block activation.
- If code and specification disagree, stop and surface the discrepancy.
- If a specification silence would change user-visible behavior, authority,
  irreversible data, or external compatibility, stop and surface it. Ordinary
  implementation detail should use the smallest conventional choice and tests.
- A slice that has not shipped is expected incompleteness, not a discrepancy.
  `docs/implementation-plan.md` is the single active roadmap and delivery plan.
  detailed feature contracts own behavior; do not recreate a separate work order.
  retired plans, cleanup logs and qualification reports live in git history,
  not a duplicate archive tree or new execution gates.

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
- Jarvis owns exactly six application tables: `message`, `memory_log`,
  `memory_summary`, `action`, `model_decision`, and `read_position` (ADR 0040).
  Additional application tables require an accepted ADR.
- The four additional irreducible durability fields are
  `message.processing_attempts`, `message.processing_parked_at`,
  `action.execution_contract`, and `action.attempts`. Do not expand them into a
  generic workflow/version system.
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
  tool version. Supply the required owner-controlled
  `session_compatibility_revision` from the checked-in role/application contract
  revision and exact dependency pins.
- Recaller, rememberer, dreamer, and AutomaticWriteGate invocations use fresh
  isolated sessions.
- The kernel owns the exact model-step grammar, validates the entire step and
  pure arguments before dispatch, and permits exactly one serial call per step.
  Active Main uses the kernel's structured-output path, so it has no `say`
  terminal and returns one closed `finish.result` for host rendering.
  `call_tool` carries no user-facing text or model-authored call/effect ID.
  Internal one-shot roles use plans containing no `ToolEffect.Write` and closed
  structured `finish.result` contracts.
  The kernel also owns the Codex-compatible provider-wire envelope and strict
  decoding of its JSON-string tool arguments; Jarvis consumes logical steps and
  MUST NOT duplicate or bypass that wire adapter.
  Definitions hold maximum capability envelopes; each run gets a proven frozen
  tightening, with scheduled-wake runs narrowed to reads. Jarvis—not the
  kernel—selects priority, compatibility, batching, and the plan.
  `llm-tools` owns typed prompt sections and tool contracts/execution;
  `provider-runtime` owns provider calls and native session lifecycle. Do not
  duplicate those layers in Jarvis.
- Persist and source-deduplicate owner input and required host-authored action
  resolutions before processing them.
- Preflight rolling capacity under the execution mutex, then increment
  `message.processing_attempts` atomically when the checkpoint port returns its
  claim. It deliberately counts a crash or configuration failure after claim,
  without hidden coupling to the later admission port. Deterministic poison
  stops consume the row; cleanup never automatically rearms it.
  Startup/recovery scans canonical null-`processed_at`,
  null-`processing_parked_at` rows under the attempt ceiling and rolling
  admission.
- A configuration defect uses the checkpoint `park` operation to stamp
  `message.processing_parked_at` and open the single cognitive circuit. Claims
  exclude parked rows. Only operator correction explicitly clears the park;
  never hide scheduling control solely in `trace`.
- Poll compatible owner input before provider turns, dispatch, after tool
  completion, and before settlement. Stop/pause preempts. An ordinary follow-up
  racing after the final poll gets the already-valid answer first and its own run
  next.
- Set a waking message's `processed_at` only in the transaction that records its
  durable turn conclusion. Put the same run/checkpoint/conclusion identity in
  bounded `trace` on every consumed waking row. Never replay an interrupted
  owner turn named by an action's admitted-input lineage.
- Persist an assistant response before delivery. A null `source_message_id` is
  the outbound retry watermark; fill it with the adapter's ID after a successful
  create response.
- Derive the Discord nonce from `message.id` exactly as SPEC section 4.3 states,
  set `enforce_nonce=true`, and reuse it for every retry. Historical responses
  may omit nonce; a delayed bounded retry may rarely repeat ordinary text under
  ADR 0022, but cannot duplicate an action effect.
- `remembered_at` distinguishes a completed rememberer run, including a valid
  decision to store nothing, from one that never completed. Remember once per
  settled input group and advance every consumed owner row transactionally;
  fall back to per-row sweep only when grouping trace is unavailable.
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
- Recall runs before every owner-authored human input. It begins with exactly one
  kernel-dispatched deterministic `memory.search` typed observation, followed by
  the isolated recaller's adaptive `memory.search` and `memory.open` calls.
- Stable external references live in natural-language memory text, not object
  tables.

## Authority invariants

- Models never receive connector, Brave, or embedding credentials or direct
  execution authority.
- V1 uses the real `AgentRuntime` lane with the closed JSON-schema output,
  private empty read-only cwd, disabled built-ins/Web/network/environment/MCP,
  and approval deny. Production consumes `stream_turn`, never the
  event-discarding `run_turn` projection. Any native tool-use or
  permission-request event fails and discards the session.
- Before rendering or I/O, every frozen plan is proven internally consistent
  with its exact catalog view and to tighten its maximum envelope in full; a
  profile-only comparison is insufficient.
- Every binding has a non-empty owner-controlled implementation revision.
  Jarvis-owned bindings initially use the SPEC section 7.3 convention; bump an
  affected revision when handler/transitive behavior changes unless revisioned
  policy inputs already capture the change.
- Host code validates and classifies calls; effectful application tools execute
  through `llm-tools` and use one durable `action` row.
- Before any action insert or approval display, every validated model-proposed
  `Write` runs through the isolated AutomaticWriteGate. It has no tools and sees
  only current owner input plus a bounded host-normalized effect descriptor—no
  recall, connector/Web/tool result, rationale, history, payload prose, or
  credential. Denial or failure creates no action.
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
- V1 renders every supported approval as one bounded host-generated UTF-8 text
  attachment containing the action ID, canonical tool name, and exact validated
  stored arguments. The component message identifies it as complete and has
  exactly Approve and Deny; rendering failure presents no functional component.
- Approval-bearing Discord messages are host-owned and cannot be edited or
  deleted by model-originated tools.
- An approval component binds the action and internal approval-message IDs.
  Accept it only from the configured owner/guild/channel when its Discord
  message ID matches that stored row and the action is still awaiting approval.
  Commit the claim or denial before acknowledging through a component-disabling
  interaction edit, and disable again during startup recovery before executing
  an approved action that never reached its executor.
- Keep canonical `tool_name`, `arguments`, and `origin_message_id` immutable.
  Also keep the host-authored `execution_contract` immutable. V1 tool names are
  unversioned; the contract snapshot binds the occupied position's tool, policy,
  plan, effect/replay declarations, and input digest. Revalidate both before
  approval rendering and execution; drain non-terminal actions before an
  incompatible tool change.
- The execution contract also stores finite `max_attempts`, claim ID,
  through-checkpoint, model-step ordinal, ordered admitted input IDs, and
  write-gate supporting owner IDs. Recovery uses this lineage, never
  `origin_message_id` alone.
- Action states are exactly `queued`, `awaiting_approval`, `executing`,
  `succeeded`, `failed`, `uncertain`, and `cancelled`.
- The single deployment owner reconciles rows left `executing` after a timeout or
  restart. Increment `action.attempts` immediately before actual executor entry;
  require it to remain below the immutable lifetime ceiling. The count records,
  but never authorizes, an evidence-proven safe repeat. At the ceiling, proved
  absence fails and unresolved evidence becomes uncertain. Do not add action
  leases, intent keys, client references, multi-call vectors, or a general
  version registry without measured need and a new ADR.
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
- Gmail send re-fetches and exactly compares the known draft before dispatch.
  Ambiguous recovery makes three observations at fixed `0`, `2`, and `8` second
  backoffs. Each reads that draft, fetches the known thread as minimal metadata,
  and fetches at most one hundred enumerated messages individually as raw. The
  procedure permits at most 102 provider reads per observation, sixteen MiB of
  response bodies, and thirty seconds. Excluding only the current live draft
  message ID, one unique observed exact effect-header/content match after every
  selected bounded message is processed proves success even when the thread has
  an unprocessed tail; no Gmail label is required. Duplicate, conflicting,
  malformed, or partially processed evidence is not success. A repeat requires
  three complete observations proving the exact unchanged draft and complete
  thread contain no matching non-draft message, plus remaining attempt capacity.
  An original mutation
  timeout alone authorizes neither retry nor uncertainty; expiry of the separate
  reconciliation elapsed bound exhausts that bounded procedure with incomplete
  evidence and becomes terminal uncertainty.
- Host action-resolution and scheduled-wake inputs must produce a visible
  structured terminal or deterministic host-rendered assistant fallback; never
  process them silently, except adr 0064's unmixed wait-observation batch with no
  owner input. worker observations grant no new write authority; after the original
  owner turn closes they permit reads/integration/notification only. Due-wake input is rendered from immutable stored
  arguments.
- Host-matched `stop`, `pause`, and `resume` controls do not involve the model.
- Only an owner-requested due `schedule.wake` action starts a user-facing
  proactive turn. Do not add generic quiet hours, connector polling, or
  autonomous inbox/calendar monitoring in v1.
- The separate durable waking-message source remains exactly
  `message.source = schedule_wake`; it is not a model tool ID.
- A schedule create keeps an immutable `result.creation_receipt` that the durable
  recorder replays independently of later queued/executing/terminal status;
  later lifecycle writes only `wake_outcome`. Cancellation is its own gated
  action and can target only a queued original.

## Engineering rules

- Prefer plain functions, explicit data flow, and database transactions.
- Jarvis owns product context selection, its kernel port adapters, Discord,
  memory, connectors, policy, approvals, actions, scheduling, and credentials.
  Do not move product authority into `llm-agent-kernel`.
- Use one deployment-level PostgreSQL advisory lock and ordinary in-process
  scheduling; do not invent redundant workflow coordination.
- Require host rolling admission before provider I/O. Durably reserve maximum
  root/serial-child turns and reported-token allowance plus one root slot. Clean
  exits settle/refund; startup releases orphaned slots without refunding their
  rolling capacity charge. Admission denial does not increment input attempts;
  owner work is retried at reset with one notice for delays of at least 60
  seconds, while background work defers silently. Fail closed on corrupt state.
- Serialize active provider turns and host-tool dispatches. A nested write gate
  runs only while the main run is paused and shares capacity already reserved by
  the root; no provider calls overlap.
- Construct one fresh `llm-tools.BudgetState` after the selected frozen plan is
  validated, through the kernel's plan-aware budget factory. Its limits must
  exactly equal `plan.profile.run_limits`; never preconstruct or share it.
- Treat `KernelLimits.max_cooperative_seconds` as a safe-boundary/provider-turn
  control, not an end-to-end SLA, and `max_new_context_bytes` as newly rendered
  kernel material, not total provider-native context. Bound and qualify the
  omitted host/provider surfaces separately; never place a blunt outer timeout
  around a `Write`.
- Derived state must be safely rebuildable.
- Preserve user-owned changes in every repository.
- Never place credentials, OAuth tokens, private memory text, or message bodies
  in ordinary logs or real private content in fixtures.
- Timestamps are `timestamptz`; the host runs UTC. Each cognitive session
  receives the configured owner IANA timezone once when it opens. Each owner
  input batch or background job receives one host-generated `as_of`; a batch
  appended mid-loop gets its own. Embedding and tool-only continuations do not
  receive a repeated clock.
- during the testing reset, run `scripts/verify` for static and build checks and
  report behavioral verification as not run. do not restore old tests or add a
  replacement harness before the separately requested testing redesign. adr 0054's
  small universal-memory regression groups are the scoped exception, once implemented.
- Library dependency and model upgrades remain explicit; their former replay
  qualification gate is suspended under adr 0046. Native
  Codex tracks latest stable through the host installer under ADR 0042; protocol
  and authority checks remain strict, with no native version admission gate.
- Avoid abstractions with one caller unless they enforce a stated boundary.

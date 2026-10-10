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
  [adr 0066](docs/decisions/0066-optchat-memory-adoption.md) adds automatic
  compressed orientation over all admitted history in fresh jarvis context and
  replaces selective automatic note extraction with chronological compression,
  and retains associative dreaming as a distinct function seeded automatically
  by new admitted archive material and retained optional explicit notes.
  [adr 0067](docs/decisions/0067-nexus-owner-chat-memory.md) adds one distinct
  nexus-owner backend client for a configured authenticated viewer's chat
  send/rerun/regenerate operations and tagged native/nexus note provenance.
  it preserves the sixteen capture lanes and adds no nexus conversation capture.
  declare complete nexus processor chains before granting tools; other viewers
  and automated helpers receive none. private provisioning is separate.
  dreaming is required in the first delivery. it quietly appends attributed
  synthesis notes with supporting references into the shared tree/view/search;
  previous syntheses can be retrieved but create no new seed work. corrections
  append; no dream-triggered main turn or notification. legacy flat summaries
  remain preserved; new output uses the shared note append. new authored notes
  enter the automatic view with their canonical provenance.
  each bounded dream also receives a small random sample of older conversational
  originals/explicit notes as optional context, with no seed progress or extra
  runs. keep shared retrieval ranking unchanged and dream notes outside automatic
  sampling; deliberate retrieval remains available.
  nightly idle dreaming uses a bounded new-material tree view since successfully
  consumed progress, retaining missed days/late capture and excluding synthesis
  leaves from new seeds. one `dream_through` cursor and nightly attempt marker
  govern progress; closed bounds/references are in the consolidated contract.
  a standalone non-jarvis library hosted in jarvis owns archive/tree/view,
  compression and search/navigation. bounded source parts and notes are ordinary
  leaves; event identity survives splitting. no private oversized-leaf reduction.
  use aligned binary/free nodes, corrected inclusive-end priority, batched views
  and persisted frontiers/shrink state. jarvis supplies admission, inference,
  scheduling and mcp/http; archive/checkpoint commits stay atomic.
  all admitted events/notes share one tree and view-allocation policy; original
  conversation identities remain for attribution, search and reopening evidence.
  immutable central arrival order determines positions; retain source dates
  separately. receipt order alone decides neither chronology nor instruction precedence.
  available admitted native worker/child histories and reports remain in the archive
  and shared tree; reasoning and jarvis's internal cognition stay excluded.
  fork copies are omitted only with native lineage and complete retained-original
  coverage; uncertain/missing proof retains eligible copies within the fork's boundary.
  central ingest proves direct source coverage; native reads stay unfiltered.
  checkpoint id/digest advance atomically over inserted or verified omitted events,
  even with zero new source rows. no transitive skip ledger or fabricated originals.
  originals and broad fork parentage suffice; no per-occurrence omission map or
  archive-only reconstruction guarantee for skipped inherited occurrences.
  supplied instruction/environment/compaction/other context is reference-only in
  archive/tree; preserve native reference metadata, never body prose or summaries.
  identity/digest binds the native event before suppression; missing bodies remain explicit.
  retain tool-result archive text under a permanent 30,000-character head/tail
  cap with explicit omissions and source identity; canonical recovery receipts
  stay intact. jarvis reconstructs each new top-level turn from a fixed admitted
  view plus exact current requests/receipts; its active tool loop stays together.
  codex/claude/nexus retain native chats and choose shared memory reads. use
  bounded tool-free compaction, ready queues and dependency/retry progress.
  email enters memory through actual tool observations, without wholesale inbox
  capture. retain exposed attachment text plus references; durable originals
  remain in the attachment delivery. tools/basic inspection ship first; a
  dedicated browser/export is deferred. product/schema/integration contracts are
  complete for the core; nexus access is chats only, excluding automated helpers.
  nexus account/client integration still needs its
  [consumer handoff](docs/issues/nexus-memory-client.md). implementation and
  qualification remain. one serial tool-free
  compactor uses existing inference; no jobs table or extra daemon.
  ordinary implementation details do not require another preference interview.
  it supersedes affected baseline rules below when implemented: six memory tables
  after the native nine, adding `memory_leaf`, `memory_node`, `memory_state` to
  the three archive tables; automatic
  activation and whole-event capture, chronological compression replacing the
  rememberer, optional direct saves, archive/note-seeded dreaming,
  shared rank-fused search and no recaller or
  forgetting. canonical messages/receipts commit before recoverable archive
  projection; immutable message/attempt eligibility bits exclude old or unadmitted
  material. fresh top-level leases preserve entered-effect dispatchers. historical
  import/provenance remain deferred.
- for the accepted, unimplemented universal-memory target, preserve atomic
  archive/checkpoint and synthesis-note/reference/tree-position/consumed-seed
  completion commits. extraction bookmarks are
  retired; compactor nodes/views persist while interrupted inference may repeat.
  dreamer uses disposable kernel inference and run-local read
  receipts: interrupted paid computation may repeat under new admission. no
  durable background replay scopes. main/gate journals, external effect recovery,
  main paid-read barriers remain. current-owner permits govern cognition; there
  is no rolling paid-capacity reservation or background replay ledger.
- in that memory target, agents choose their procedure from context, tools,
  goals and quality constraints.
  no mandatory first tool/search, minimum call count or scripted research sequence;
  dreamer seed-only/empty completion is valid. host authority, grants, protocol,
  lineage and atomic completion are still enforced.
- make shared policy global: one definition per constant, one settings/client/pool
  composition, shared limits across callers and no per-profile tuning/allowances.
  reuse existing primitives and remove duplicate implementations. preserve scoped
  provenance/permissions/progress and fresh per-run execution state; do not replace
  these facts with mutable global turn state. operator status stays in the cli.
- in that memory target, external `memory_save_note` requires lane admission and
  connection. optional conversation identity is caller-reported; never require
  discovery. main's
  internal `memory.save_note(text)` uses the same append under jarvis admission,
  its existing native-invocation position as invocation/effect identity, and the
  narrow local-write `read_position` recovery. this exact write bypasses the
  gate/action rules; no scheduled/background grant or native cognition mcp.
  archive memory-tool prose as content-free references to prevent feedback.
- once that memory target is implemented, retain two small regression groups:
  capture/retry and memory completion. no standing per-feature review machinery
  or restoration of the retired suite;
  the wider testing redesign remains open. no runtime change is implied by docs.
- [adr 0052](docs/decisions/0052-cut-worker-control-to-current-skid.md) governs
  installed worker control; [adr 0064](docs/decisions/0064-simple-worker-orchestration.md)
  owns the implemented next target contract and current qualification record.
  the owner explicitly authorized source implementation and temporary
  integration/live checks; installed cutover remains separate. both use
  the skid cli and private three-peer config. adr 0052 supersedes the worker
  transport, roster, refs and receipt codecs of
  adrs 0044/0045/0048/0049. cognition uses adr 0065's separate contained stock
  endpoint; its production activation is separate from worker fleet installation.
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
- Jarvis owns nine application tables: `message`, `memory_log`,
  `memory_summary`, `action`, `model_decision`, `read_position`, `native_attempt`,
  `native_invocation`, and `native_input_delivery` (adrs 0040/0065). universal
  memory adds six when implemented; the future work table needs its own adr.
  other application tables require an accepted adr.
- Preserve SPEC section 9's exact request/control, invocation and action fields.
  `processing_attempts` retains historical values; native main does not use it
  as a claim counter. operator quarantine and finite action executor-entry
  ceilings remain. do not add a generic workflow/version system.
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
- Reuse main's healthy compatible native lease only within its current process.
  connection, process or owner loss fences old callbacks. recover an original
  sealed terminal locally, or restart reasoning in a fresh thread from canonical
  unfinished requests and original receipts. no saved-session reference or CAS.
  native history, compaction and caches remain disposable.
- Match the complete immutable definition fingerprint before live reuse. derive
  compatibility from checked-in role/application revisions and exact pins; the
  kernel owns its base-instruction revision/digest. no manual duplicate adapter.
- Recaller, rememberer, dreamer, and AutomaticWriteGate invocations use fresh
  isolated sessions.
- main uses the kernel's native callback supervisor. persist original accepted
  invocation before dispatch and original result/model reply before delivery.
  callback IDs correlate replies, never authorize effects. duplicate callbacks
  preserve original lineage and receipts; changed proposals fail closed.
- main validates phase-aware `JarvisNativeMessage`; progress persists prose
  without settling requests, and final `JarvisTerminal` dispositions explicitly
  complete, continue or wait delivered requests. seal native evidence before
  product decoding; no prose fallback may replace malformed output.
- Isolated one-shot roles retain the kernel's strict serial `call_tool | finish`
  grammar, plans without `ToolEffect.Write`, and closed `finish.result` contracts.
  the kernel owns their Codex wire envelope/JSON-string decoding. jarvis does not
  duplicate provider or isolated-step adapters.
  Definitions hold maximum capability envelopes; each run gets a proven frozen
  tightening, with scheduled-wake runs narrowed to reads. Jarvis—not the
  kernel—selects priority, compatibility, batching, and the plan.
  `llm-tools` owns typed prompt sections and tool contracts/execution;
  `provider-runtime` owns provider calls and native session lifecycle. Do not
  duplicate those layers in Jarvis.
- Persist and source-deduplicate owner input and required host-authored action
  resolutions before processing them.
- Admission requires the dedicated deployment-lock connection, current canonical
  request state and immutable owner permit. lost ownership cannot reconnect or
  borrow another owner's permit. startup fences old attempts and recovers
  pending requests while preserving original action/read barriers.
- Input scans exclude operator-parked rows. only explicit operator correction
  clears `processing_parked_at`; never hide scheduling control solely in `trace`.
  configuration failures preserve evidence and require repair.
- Keep input/control responsive during native reasoning and callback waits.
  compatible input steers; incompatible input queues durably. new topics retain
  unfinished requests. stop/pause fences dispatch before entered effects settle.
- Commit owner completion/stopped state or handled host facts with their canonical
  disposition/response/control and bounded settlement trace. an approval proposal
  alone does not complete a request. fresh reasoning cannot replay an unknown
  effect or billed-once read.
- Persist an assistant response before delivery. A null `source_message_id` is
  the outbound retry watermark; fill it with the adapter's ID after a successful
  create response.
- Derive the Discord nonce from `message.id` exactly as SPEC section 4.3 states,
  set `enforce_nonce=true`, and reuse it for every retry. Historical responses
  may omit nonce; a delayed bounded retry may rarely repeat ordinary text under
  ADR 0022, but cannot duplicate an action effect.
- `remembered_at` distinguishes a completed rememberer run, including a valid
  decision to store nothing, from one that never completed. Remember once per
  explicitly completed owner request/group and advance its owner rows
  transactionally;
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
- Cognition uses the separately contained stock 0.160.0 endpoint and the
  provider-owned restricted startup catalogue, with public host preflight,
  private empty read-only cwd and approval deny. native shell/files/Web/network,
  MCP, subagents and unsolicited approvals remain disabled. main consumes
  prepared-turn events; isolated roles consume `stream_turn`, never the
  event-discarding `run_turn`. undeclared native authority or permission events
  fail-stop and discard the session; declared host callbacks remain permitted.
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
- the execution contract also stores finite `max_attempts`, `claim_id`,
  `through_checkpoint`, `model_step_ordinal`, ordered admitted input ids and
  write-gate supporting owner ids. on the native path, the retained `claim_id`
  field contains the native attempt id and `model_step_ordinal` its callback
  ordinal. recovery uses this lineage, never `origin_message_id` alone.
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
  memory integration, connectors, policy, approvals, actions, scheduling and
  credentials. the accepted memory target moves archive/tree/view/retrieval
  mechanisms into the standalone memory library; jarvis hosts it and supplies
  admitted inference. do not move product authority into the memory library or
  `llm-agent-kernel`.
- Use one deployment-level PostgreSQL advisory lock and ordinary in-process
  scheduling; do not invent redundant workflow coordination.
- Require current-owner admission before provider I/O and effect entry. main's
  cumulative tool/model quotas are absent; finite per-operation, transport and
  buffer bounds remain. usage is observational, not authority. background memory
  work retains foreground precedence and its actual isolated-role bounds.
- Serialize actual callback/approved-action dispatch. a nested write gate uses
  its parent invocation and the same current owner while main dispatch waits;
  the native reader, ingress, consent and outbox remain live.
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
- Library dependency and model upgrades remain explicit. the contained cognition
  endpoint pins stock 0.160.0 and its provider-owned startup catalogue under
  adr 0065; updates require explicit qualification. unrelated coding hosts retain
  their own installation policy. old replay gates remain suspended under 0046;
  current native protocol/authority contracts remain strict.
- Avoid abstractions with one caller unless they enforce a stated boundary.

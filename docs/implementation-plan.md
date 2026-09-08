# V1 implementation plan

Each slice is a small vertical increment. The plan names intended sequence, not a
workflow system or calendar schedule.

## Slice 0: audit and qualification

Status: complete and owner-approved on 2026-09-03. The dated
[qualification report](qualification/2026-09-02-slice-0.md) is the durable
record of observed results, accepted trade-offs, and deferred owning-slice
gates.

Deliver:

- Delegated summaries of the existing Discord, Gmail, Calendar, and Maps
  integration surfaces without importing unrelated Ariel design.
- The exact canonical tool manifest, schemas, typed observations, and live
  automatic/approval classification from SPEC section 7.3.
- The configured Discord guild/owner/channel IDs, observed effective authority,
  required four operational permissions, prohibited management authority,
  minimal Gateway intents, and bounded history-catch-up behavior.
- Live Discord confirmation that `enforce_nonce` returns the existing message
  for the same recent bot nonce, plus an honest record of whether history and
  exact-message reads expose that optional nonce.
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
- The active implemented public kernel pin
  `21084bec674023ea572950a18dde464506ea37ad`, with exact
  `provider-runtime` and `llm-tools` dependency pins and deterministic suite
  recorded in the qualification evidence. The signed Slice 0 report preserves
  the earlier qualified revision; ADR 0027 records the compatible Slice 2
  Web deadline and extraction corrections, invocation-local provider usage,
  and superseding pins. The exact invocation-local usage-fix pair preserves the
  existing session-compatibility revision under its upstream-certified atomic
  exception. ADR 0035 records the later provider transport and kernel base
  instruction containment pair; it preserves that application revision while
  the fingerprinted kernel instruction cold-bootstraps all roles. Because
  Jarvis intentionally commits the AutomaticWriteGate definition fingerprint
  into Write binding policy, the containment release also rotates affected
  main catalogs, profiles, plans, and HostTables without changing tool
  contracts or implementations.
- The completed `llm-tools` upgrade exposing qualified public pure
  argument validation, frozen-plan/catalog consistency and full tightening,
  exact `HostTable` publication, and async durable executor/recorder seams; pin
  the qualified revision before any Jarvis runtime implementation.
  Qualification includes adversarial cross-catalog
  effect/schema/handler-implementation/replay-policy/revision substitution and
  proves implementation identity appears in the frozen grant and HostTable.
- Qualification of the kernel's exact `AgentRuntime` request/lifecycle,
  context, session-reference, input-checkpoint, polling, dispatch, admission,
  cancellation, and optional observability ports plus its multi-run conformance
  suite. Confirm it owns no database schema, connector, product authority, or
  duplicate provider/tool implementation.
- The intended compatibility-revision, plan-aware budget, admission overshoot,
  provider-native context-sizing, and durable checkpoint-park mappings, with
  their production proofs assigned to the slices that build them.
- Qualify an isolated structured one-shot with a genuinely empty `HostTable`
  plan for AutomaticWriteGate; do not add a dummy capability to satisfy a
  library limitation.
- Record the exact expected-provider-failure matrix, including which failures
  permit the one safe cold bootstrap and which do not.
- Prove that the public `llm-tools` recorder surface can represent the intended
  Jarvis action and schedule-creation receipt mapping; the production adapter
  conformance fixture gates Slice 5.
- Select and record a finite lifetime executor-entry ceiling and complete
  automatic reconciliation procedure for every v1 write tool; no unbounded
  default is permitted.
- Live `llm-tools` Brave-search and safe-public-Web-read canaries, including
  private-destination, unsafe-redirect, and credential-egress rejection.
- Linux qualification of the pinned Codex SDK/runtime containment request,
  `JsonSchemaAgentOutput`, open/stream/close and resume behavior, and fail-stop
  on native tool-use or permission-request events. Prove production consumes
  `stream_turn` and never calls the event-discarding `run_turn` projection.
- A restricted embedding API key plus a live negative generative-call test.
- One replacement Google offline consent using exactly the minimal scope set in
  SPEC section 8, followed by encrypted import under Jarvis-owned associated
  data; do not carry forward legacy Drive or redundant Gmail/Calendar scopes.
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

Status: complete and qualified on 2026-09-03. The dated
[qualification report](qualification/2026-09-03-slice-1.md) records the exact
revisions, deterministic gates, paid Codex probes, live Discord results, and
accepted trade-offs.

Deliver:

- Python project, lockfile, PostgreSQL, and migrations.
- Pinned `llm-agent-kernel` integration with Jarvis-owned product-context,
  session-reference, input-checkpoint, and terminal-finalization adapters.
- Conversational main output contract plus closed structured output contracts
  for isolated recaller, rememberer, and dreamer one-shot runs.
- Provider-terminal fixtures using the kernel-owned closed nullable wire
  envelope, including JSON-string `call_tool.arguments`; Jarvis must not decode
  or validate that wire independently.
- `message` table, owner/source identity, durable `processing_attempts`, and
  nullable `processing_parked_at`.
- Existing Discord ingress/egress restricted to one configured channel, with no
  model-callable Discord tools.
- Inbound deduplication.
- Bounded owner-message catch-up after downtime.
- Persist-before-send assistant messages using null `source_message_id` as the
  delivery watermark.
- Deterministic 20-character Discord nonce derivation, `enforce_nonce=true` on
  every create and retry, and a small finite delivery retry/backoff policy that
  accepts the documented rare delayed conversational duplicate.
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
- Checked-in canonical session-compatibility manifest and required
  `session_compatibility_revision` on every continuing and isolated definition.
  Pin or application-contract changes normally rotate it; ADR 0027's one exact
  atomic provider-usage correction pair preserves it. Dynamic input and subset
  plans do not rotate it. ADR 0028 records the exact qualified local-account
  model set separately; the selected model already participates in the
  definition fingerprint.
- One plan-aware `ToolBudgetFactoryPort` implementation creating fresh exact
  budgets after plan validation for every plan selectable in Slice 1.
- Exact Slice 1 `llm_tools.RunLimits`, finite route-qualified one-turn token
  overshoot, and provider-native context sizing for system/developer material,
  schema overhead, retained history, and compaction.
- Exclusive non-empty claim over messages, host-selected full or scheduled-wake
  read-only plan, ordered watermark, mid-loop compatible-input polling, stop
  preemption, and atomic conclusion/`processed_at` settlement. Incompatible work
  remains unclaimed; cleanup never arms a successor.
- Shared run/checkpoint/conclusion trace on every consumed waking row and
  immutable kernel dispatch lineage available to later action slices.
- Host-authored poison-input conclusions, durable reclaim ceiling, and a
  content-free atomically replaced rolling-admission journal that reserves
  finite maximum root/serial-child provider turns, reported tokens, no-progress
  attempts, and one root concurrency slot before provider I/O. Clean exit
  settles/refunds; startup releases an orphaned slot without refunding its
  rolling turn/token charge.
- Checkpoint `park` implemented as one PostgreSQL transaction that stamps the
  claimed unprocessed batch, records a bounded reason code, and opens the single
  cognitive circuit. Claims exclude parked rows; a documented operator repair
  clears them without resetting attempts.
- Admission preflight deferral that leaves input and `processing_attempts`
  untouched, automatically rescans at reset/startup, emits one deterministic
  assistant notice for owner/action-resolution delays of at least 60 seconds,
  and silently defers background memory work. After preflight, claim increments
  the attempt atomically; a later inconsistent capacity result raises
  `AdmissionStateDefect` and parks rather than coupling the checkpoint and
  admission adapters.
- A fake stateless adapter test proving bootstrap context contains no Codex SDK
  types and carries the current owner message exactly once.
- Kernel conformance fixtures for session loss, invalid protocol, cancellation,
  a crash between session-reference advancement and canonical settlement, a
  compatible input arriving mid-loop, ordinary input arriving during final
  settlement, stop preemption, poison input, crash reclaim, rolling admission,
  plan-budget mismatch and parking, compatibility rotation, provider-native
  context sizing, cooperative-time overshoot, and exhausted bounds.
- The three paid Codex consumer probes against the exact pinned kernel and
  provider-runtime revisions on every exact qualified model, with sanitized
  results in the qualification ledger. At least one currently supported
  ChatGPT-local-account route must pass; the qualified model count is not
  permanently fixed.
- Deployment ownership lock and an in-process execution mutex serializing
  provider turns and host-tool dispatches.

Exit: natural conversation in one channel survives compatible session resume
and deliberate session loss, lost Discord acknowledgement and delayed-restart
fixtures each leave exactly one visible response, an interrupted effect-free
turn is safely replayed, and input racing with idle is never stranded.

## Slice 2: read tools

Status: complete and qualified on 2026-09-04. The strengthened original nine-read
compound-linkage gate and final verifier passed. The dated
[qualification report](qualification/2026-09-04-slice-2.md) records the exact
dependencies, frozen identities, deterministic verification, sanitized live
provider evidence, and accepted trade-offs.

Deliver:

- Jarvis-owned application declarations/bindings, product policy, and frozen
  role plans composed through `llm-tools`; the library retains schema,
  validation, prompt-section, budget, and execution ownership.
- Exact read-plan `RunLimits` and plan-aware factory conformance before any read
  plan becomes selectable.
- No Discord declarations in the model tool catalog; conversation delivery stays
  in the adapter.
- Kernel-owned strict `call_tool | say | finish` schema, complete semantic and
  pure-argument validation before mutation, exactly one serial call with no
  model-authored ID or prose, bounded corrective feedback, and a separate `say`
  only after the model observes its result.
- `gmail.search` and `gmail.read_thread` bindings.
- `calendar.list_calendars` v1, `calendar.list_events` v4, and
  `calendar.get_event` v2 bindings after ADR 0037 superseded the original
  primary-only v3 list. List exposes no calendar ID and aggregates the bounded
  live reader-or-better CalendarList host-side. Normal observed
  ends are a required direct timed/all-day/unspecified tagged union. Google's
  true flag discards its compatibility end and returns the payload-free
  unspecified variant, while false or missing requires a parsed end. The final
  live read gate requests 50 events and proves at least three sanitized
  qualified-account unspecified-end cases.
- `maps.search_places`, `maps.get_place`, and `maps.directions` bindings.
- Pinned `llm-tools` `web.search` and `web.read` bindings under Jarvis-owned
  credentials, information-flow policy, and budgets.
- One bounded completed observation or durable suspension per call; the Jarvis
  dispatch adapter retains product authority and supplies original validated
  call evidence on later resolution.
- Confined Codex drift tests.
- Exact configuration rejection of retired or unqualified local-account model
  IDs before ingress, admission, provider I/O, or tool I/O, plus paid consumer
  qualification of every model in the current compatibility manifest. At least
  one currently supported route must pass.

Exit: Jarvis answers a natural compound question using Gmail, Calendar, Maps,
public-Web search, and a fetched public page without exposing credentials to
Codex or granting the Codex child native network access. The final exact-code
evidence includes valid Calendar unspecified-end observations, recomposed
frozen identities, and a cold-bootstrapped Main session under role contract v3.

## Slice 3: raw memory and recall

Status: complete and qualified on 2026-09-05. The dated
[qualification report](qualification/2026-09-05-slice-3.md) records the exact
deterministic and product evidence, the corrected historical provider-schema
blocker, the unchanged frozen evaluator's final 17/17 result, and all accepted
trade-offs.

Deliver:

- Exact `memory_log` schema and append-only database enforcement.
- Host-owned rememberer commit with every consumed owner row's `remembered_at`
  in the same transaction.
- Full-text search and nullable OpenAI embeddings.
- Memory search/open tools for the recaller and rememberer only in Slice 3;
  never for the main agent.
- Fresh `SessionMode.isolated` kernel recaller before every owner input and fresh
  isolated rememberer after every eligible completed turn; both use one-shot
  execution, touch no input-checkpoint or saved-session port, and return closed
  structured `finish.result` payloads.
- Exactly one kernel-dispatched deterministic `memory.search` typed observation
  starts each owner-input recall before the recaller adaptively searches or opens
  memory.
- Exact recaller and rememberer `RunLimits` plus plan-aware factory conformance
  before those plans become selectable.
- Stable external-reference convention.
- At least fifteen owner-authored or explicitly owner-approved redacted,
  synthetic-safe recall evaluation cases.
- Bounded retry sweep for completed unremembered `role = owner` turns only.
- Settled-run/conclusion trace grouping for one rememberer invocation per input
  group, with a safe per-row fallback when grouping metadata is absent.

Exit: a durable preference and linked external matter are recalled in a fresh
provider session, and memory persistence creates no action row or duplicate text.

## Slice 4: dreaming and summaries

Status: complete and qualified on 2026-09-05. The dated
[qualification report](qualification/2026-09-05-slice-4.md) records exact
deterministic, paid, rebuild, and product evidence plus every accepted trade-off.

Deliver:

- Exact `memory_summary` schema with raw lineage.
- Fresh `SessionMode.isolated` kernel dreamer one-shot search/open profile with a
  closed structured `finish.result` mutation batch.
- Exact dreamer `RunLimits` and plan-aware factory conformance before its plan
  becomes selectable.
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
- Restricted, empty-plan AutomaticWriteGate as an isolated kernel one-shot for
  every validated write proposal before action creation, with adversarial
  memory/connector/Web injection fixtures and direct-owner-request usability
  fixtures.
- `gmail.create_draft` and `gmail.update_draft` bindings.
- `calendar.create_event`, `calendar.update_event`, and
  `calendar.delete_event` bindings.
- Action-derived Calendar create IDs plus get-and-compare reconciliation for
  create/update/delete ambiguity.
- Automatic/approval classification owned by host code.
- Owner-requested `schedule.wake` with closed create/cancel variants, exact
  due-time and restart behavior; no generic quiet hours, connector polling, or
  autonomous inbox/calendar monitor.
- Immutable schedule `creation_receipt` plus separate `wake_outcome`; recorder
  replay remains the creation receipt at every later lifecycle state. Schedule
  cancellation is its own gated action and a receipt-less queued wake never
  fires.
- Idempotent due-wake host messages rendered from immutable stored instructions,
  plus visible model/fallback delivery and atomic scheduled-action completion.
- Bounded external timeouts and startup reconciliation of `executing` actions;
  `uncertain` only after the complete tool-specific automatic procedure is
  exhausted, without leases or blind retry. The attempt count records each
  executor entry and never authorizes another; the immutable execution contract
  supplies a finite lifetime ceiling, after which no requeue is possible.
- `action.id` mapping to both `llm-tools` `InvocationPosition` and `EffectId`,
  with the per-row contract binding tool/policy/plan revisions, effect/replay
  declarations, canonical input digest, finite attempt ceiling, claim/checkpoint,
  model-step ordinal, ordered admitted-input IDs, and gate-supporting owner IDs.
- Production action-backed recorder conformance, schedule-creation receipt
  replay, automatic-write suspension evidence, and exact automatic-write plan
  budgets before any write plan becomes selectable.
- Interrupted turns that already created an action close exactly the stored
  admitted input prefix without model replay.
- Base idempotent host-authored action-resolution messages for outcomes that
  cannot return to a live originating loop, keyed by action ID plus resolved
  state, with startup repair, visible deterministic fallback, and checkpoint
  processing through the existing `message` table.

Exit: Jarvis performs a draft, personal calendar change, and scheduled proactive
message in the configured channel without unnecessary approval or workflow
framework.

## Slice 6: Approve and Deny

Deliver:

- Approval suspension/resolution conformance and exact approval-bearing plan
  budgets before those plans become selectable.
- Gmail send as draft-send by stored `draftId`, with the exact stable MIME
  `X-Jarvis-Effect-ID` derived from the draft-creation action ID preserved
  through updates and stored in the immutable send snapshot.
- Gmail pre-send re-fetch and exact snapshot comparison, followed on ambiguity
  by three fixed observations of the known draft and known thread. Each thread
  read uses minimal metadata followed by at most one hundred individual raw
  message reads, with no mailbox search or ordering assumption. Excluding only
  the current live draft message ID, one unique observed exact
  effect-header/content match proves success after every selected bounded
  message is processed, even if the thread has a later unprocessed tail; no
  Gmail label is required. Duplicate, conflicting, malformed, or partially
  processed evidence cannot.
- Approval execution for shared/unknown-calendar and attendee-bearing Calendar
  create/update/delete, while verified owner-only no-attendee work remains
  automatic.
- Closed host preview renderers for Gmail send and approval-required Calendar
  writes, with no model preview field or action preview column. Every supported
  approval uses one bounded deterministic UTF-8 JSON attachment containing every
  validated stored argument, including complete long bodies and all Calendar
  writable values.
- Host-owned component messages containing only Approve and Deny, with opaque
  IDs binding the action and internal approval-message row.
- Exact owner/guild/channel/Discord-message/action/internal-message/stale-state
  validation, followed by an atomic decision and immediate interaction-response
  edit that disables both components before slow work.
- `approval_message_id`, atomic claim, duplicate-click protection, and
  durable main-turn suspension that retains no blocked worker or provider
  session while the owner decides.
- Startup repair of missing approval delivery and missing action-resolution
  input, plus recovery of an approved action interrupted before executor entry;
  recovered execution first disables the known Discord components.
- Bounded Gmail reconciliation before evidence-proven repeat or terminal
  uncertainty: `0`/`2`/`8` second observation backoffs, at most 102 provider
  reads per observation, sixteen MiB, and thirty seconds. Repeat requires three
  complete observations proving an unchanged draft and a complete thread with
  no matching non-draft message; the original mutation timeout decides nothing
  by itself.
- Free-form approval rejection and terminal uncertainty reporting.
- Approval-specific action-resolution and fallback fixtures using the Slice 5
  existing-table mechanism.

Exit: Deny sends nothing; Approve sends the exact rendered email once; a shared
calendar change is also rendered exactly; an ambiguous result is reconciled or
reported without blind retry.

Slice 7 deployment, seven-day owner acceptance, and final
production sign-off remain outside this slice.

## Slice 7: production acceptance

Status: deployed and all pre-observation gates passed on 2026-09-08. The
[production deployment report](qualification/2026-09-08-production-deployment.md)
is the durable evidence. The required seven-day owner acceptance period is in
progress and cannot complete before 2026-09-15.

Deliver:

- Host-native systemd deployment on the existing Hetzner `dev-server` under a
  dedicated `jarvis` account, with immutable releases under `/opt/jarvis`,
  durable state under `/var/lib/jarvis`, root-owned configuration under
  `/etc/jarvis`, and no public listener.
- A documented ownership boundary: the `dev-server` repository converges UTC,
  system packages, PostgreSQL/pgvector availability, the service account, and
  base directories; Jarvis owns releases, credentials, database roles,
  migrations and service lifecycle. Nexus production remains
  untouched.
- Secret and configuration procedure that uses the release's pinned Codex SDK,
  not the host's mutable global Codex installation.
- Explicit verification that no v1 backup role, credential, timer, or restore
  command exists, with the owner-accepted total-loss trade-off recorded.
- Pre-deployment housekeeping with exact targets, active CI/container checks,
  disk-headroom acceptance, UTC convergence, recorded PostgreSQL/pgvector
  versions, and a recorded pending-kernel reboot deferred to an owner-selected
  maintenance window without interrupting current tmux/Codex work.
- systemd restart/resource controls and verification that development/rootless
  Docker lifecycle operations do not own or restart Jarvis.
- Agent-definition-compatible Codex session resume through `provider-runtime`
  plus recovery after deleting every provider session reference.
- Restart/crash qualification for poison attempts, no automatic rearm, rolling
  admission settlement, corrupt-journal fail-closed behavior, and explicit
  operator reset while the service is stopped.
- Complete acceptance run.
- Seven-day owner acceptance period.
- Dated acceptance report.

Exit: every non-waived mandatory criterion in `docs/acceptance.md` passes and the
owner signs off. The seven-day period starts only after the exact production
release is enabled and every preceding Slice 7 gate passes.

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

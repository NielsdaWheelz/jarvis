# Jarvis

Jarvis is a personal, persistent AI assistant for one user. It lives in one
configured private Discord channel, uses the user's existing Gmail, Google
Calendar, Google Maps, and Discord integrations plus bounded public-Web tools,
and develops durable memory through a simple remember/retrieve/dream loop.

this repository is specification-first. native cognition and worker orchestration
are implemented and qualified; production cutover and owner acceptance remain
separate. the [feature roadmap](docs/implementation-plan.md) owns remaining
product work, missing specs, external repository handoffs and operational tasks.
backup and restore remain deferred.

the native main cutover in [adr 0065](docs/decisions/0065-native-agent-supervision.md)
replaces the bounded main loop and file-backed control. it preserves isolated
memory roles and existing connectors. see the [integration handoff](docs/native-agent-integration.md)
for the stopped migration, current qualification and dependency-pin status.

accepted target, not yet shipped: [universal memory](docs/universal-memory.md)
is the single current implementation contract; [adr 0063](docs/decisions/0063-simplify-memory-policy-and-retrieval.md)
records its latest simplification. shared keyword/semantic search uses deterministic
rank fusion; agents choose their retrieval steps. admitted native lanes activate
automatically after a complete inventory. capture and memory completion are atomic,
while interrupted background inference may repeat paid work. main's durable
recovery and direct-note idempotency remain.
[adr 0066](docs/decisions/0066-optchat-memory-adoption.md) adopts a standalone
memory library hosted in jarvis: archive, binary summary tree, persisted bounded
views, and search/navigation. ordinary source-part/note leaves replace private
large-event reduction; tool-result archive text keeps at most 30,000 characters
from head/tail with explicit omissions. all admitted worker histories share the
tree, with original identity/dates and linked report occurrences. context remains
reference-only. jarvis reconstructs each new top-level turn from the view and
exact current requests/receipts; native codex/claude/nexus chats retain their own
context management and use shared memory through mcp/api. optional notes remain;
first-delivery nightly dreaming starts from a new-material tree view and quietly
appends attributed synthesis notes to the same tree, without creating new seeds
or main turns. email uses ordinary tool capture; attachments retain exposed text
and references. durable originals and a dedicated memory browser remain later
work. product and implementation contracts are complete; delivery and
qualification remain. the prototype uses one serial compactor and the existing
postgres/process, with no separate memory service.
the descriptions below record the current native runtime and existing memory,
not the unshipped universal-memory target.

## current product

jarvis converses naturally in discord, uses connected services, and asks for
approve or deny before consequential external work. current memory still uses
isolated recall, remembering and dreaming; raw notes are permanent and summaries,
embeddings and indexes are rebuildable.

main uses native declared host callbacks through `llm-agent-kernel`,
`provider-runtime` and `llm-tools`. public prose progress persists before delivery;
final dispositions explicitly complete, continue or wait each owner request.
independent work can continue while an action awaits approval. tools execute
serially through existing validation, gate, action and read-recorder boundaries.
new effects still require current owner intent; event-wide autonomy is future work.

a healthy compatible session may continue within one process. connection or owner
loss fences old callbacks and recovers original sealed results or fresh reasoning
from canonical requests/receipts. no saved-session recovery, rolling paid-capacity
reservation or arbitrary main cutoff remains. finite operation limits and effect
uncertainty barriers remain. skid owns independent worker launch/control; jarvis
owns durable observation and integration.

jarvis owns nine application tables:

```text
message
memory_log
memory_summary
action
model_decision
read_position
native_attempt
native_invocation
native_input_delivery
```

## Authoritative documents

1. [V1 specification](SPEC.md) — normative product and engineering contract.
2. [Architecture](docs/architecture.md) — runtime, component, data, and tool
   boundaries.
3. [Memory](docs/memory.md) — exact rememberer, recaller, and dreamer behavior,
   plus the physical schema and rebuild contract.
4. [Acceptance](docs/acceptance.md) — the definition of done, and the single
   completion predicate for v1.
5. [Roadmap and implementation plan](docs/implementation-plan.md) — the single
   active handoff for memory, orchestration and subsequent product slices.
6. [Decision records](docs/decisions/) — why the current design exists.

When documents disagree, `SPEC.md` wins. Changing a frozen decision requires an
ADR that also updates every affected normative document in the same change.

the [integrated roadmap and plan](docs/implementation-plan.md) brings approved
product direction, delivery dependencies, open decisions and acceptance together.
it distinguishes the accepted memory contract from v2 slices still needing their
own specification. retired v1 plans, qualification reports and the completed cleanup
log live in git history; current contracts and operations remain in the working tree.

## Status

the owner-approved [testing reset](docs/decisions/0046-reset-testing.md) removes
the old standing suite. native and worker changes completed explicitly authorized
temporary integration/live qualification; the broader
[testing redesign](docs/issues/testing-redesign.md) remains separate. historical
receipts qualify only their named artifacts and boundaries.

- status as of 2026-10-04: native main and worker-v7 composition merged in pr 49;
  exact artifact qualification is recorded in the integration handoff; production
  systemd activation and physical google/discord integration remain unrun
- Intended deployment: isolated host-native service on the existing Hetzner
  `dev-server`, with native loopback PostgreSQL; no v1 backup
- Primary client: one configured channel in a dedicated private Discord server
- Agent runtime: pinned `llm-agent-kernel`, using subscription-backed Codex
  through `provider-runtime` and host tools through `llm-tools`
- worker contract: [adr 0064](docs/decisions/0064-simple-worker-orchestration.md),
  skid cli and private macbook/devbox/arch client configuration; coordinated
  orchestration release/fleet installation remains separate
- cognition: [adr 0065](docs/decisions/0065-native-agent-supervision.md), a separate
  contained stock endpoint and the existing personal host account

## Development and verification

Development uses the CPython 3.12.13 pin in `.python-version`; supported runtimes
are 3.12.13 or later in the 3.12 series. with `uv` 0.11.28 installed, run:

```sh
scripts/verify
```

this runs frozen-dependency, formatting, lint, type, documentation-link,
dependency-audit, and package build/install checks. no database, docker, or
provider credentials are needed. it runs no behavioral tests, migrations,
dependency suites, or live qualifications.

running the application still requires postgres with pgvector. `compose.yaml`
provides the local development database used by `.env.example` and
`.env.migration.example`; start it with `docker compose up -d --wait`.
see [the operations guide](docs/operations.md) for private state initialization,
deployment, migrations, restart recovery, and operator-only release of parked input.
production retains only the selected release after activation; a new installation
temporarily stages one candidate and replaces any abandoned candidate.

## Explicit non-goals

- A general multi-user assistant platform
- A visible society of named agents
- General subagent delegation or a model-generated program runtime in v1
- A project-management database or personal knowledge graph
- A workflow-engine deployment
- A mobile application in v1
- Authenticated browsing, browser automation, or unrestricted Web access
- Rebuilding integrations that already work
- Broad speculative integration work
- Multiple Discord channels, threads, direct messages, or server organization in
  v1

## Stated trade-offs

These are accepted knowingly, not overlooked.

- Service shutdown is cooperative: stop new ingress, let admitted operations
  reach their safe stopping point, drain callbacks/workers, then close clients
  and release database ownership. Startup/recovery work already underway may
  delay stopping. A first SIGINT retains exit status 130; the existing 360-second
  systemd deadline or a second interrupt can force termination and crash recovery.
  Shutdown does not stop independently running Codex workers or shared servers.
- Discord is a third-party processor for every conversation, every quoted
  memory, every summarized email, and every approval preview.
- The complete raw memory corpus and every semantic-search query are disclosed
  to the embedding processor; see
  [ADR 0008](docs/decisions/0008-embedding-source.md). Ingestion, backfill, and
  query-embedding calls are metered by that processor.
- One subscription pool is a single point of total conversational outage, with
  no fallback by design.
- Every owner-authored foreground turn needs recall plus the main-agent call,
  while remembering follows asynchronously. This is slower and more expensive
  than a stateless chat response.
- Embedding failures leave committed raw memories with null vectors. Those rows
  remain lexically searchable and a bounded later sweep retries them, but
  semantic recall is incomplete during the outage.
- Raw memory grows indefinitely in v1. There is deliberately no deletion,
  redaction, forgetting, or destructive consolidation path; storage and search
  cost grow with use until a later accepted design addresses every durable copy.
- Every proposed write adds a small isolated AutomaticWriteGate call. It sharply
  reduces authority laundering from recalled or retrieved text, but it is a
  model judgment rather than formal proof and can falsely deny or allow
  adversarially phrased owner text.
- Conversation, approvals, and proactive notices interleave in one Discord
  channel. Multiple channels are deferred until that produces a measured
  problem.
- The reused Discord role has 25 inherited permissions beyond the four Jarvis
  needs. V1 accepts that dormant authority by owner choice: Administrator and
  management/moderation authority remain prohibited, Discord is absent from the
  model tool catalog, and the narrow host adapter suppresses mentions and link
  embeds. A compromised bot token or host process nevertheless has more Discord
  authority than Jarvis needs.
- Public search queries are disclosed to Brave, and public page reads disclose
  the requested URL and host IP to the destination. The tools send no connector
  credentials or cookies and do not provide authenticated or JavaScript browsing.
- web search permits one external attempt and selectable page reads retain
  finite per-operation bounds. transient search failures and unusually large
  individual reads can fail; main has no cumulative tool-output quota.
- Calendar events with a provider-declared unspecified end expose a payload-free
  tagged domain variant rather than Google's compatibility end. This preserves
  truth but requires consumers to handle the third observed-end variant; plan/
  session fingerprints prevent reuse with an incompatible get-event contract.
- Calendar event listing uses host-owned bounded pagination and returns typed
  completeness rather than a model-selected limit or truncation guess. Its v6
  result returns at most 1,500 compact overview items in 512 KiB; full details
  require explicit `calendar.get_event` reads. It may use more Google requests
  and still reports unusually dense ranges as partial at the fixed
  page/event/byte/deadline bounds.
- main persists typed public progress as prose without completing owner requests.
  final output separately renders an answer, partial result, question, failure
  or silence, with explicit request dispositions. malformed structured output
  fails locally while original native terminal evidence remains intact.
- Codex session history, compaction, and cache behavior are non-canonical
  optimizations. A changed session-scoped contract or lost session takes a cold
  context bootstrap, and no cost saving is guaranteed. Rotating or discarding
  Jarvis's local reference does not prove deletion of provider-retained session
  data.
- Dreaming runs from a process-local 24-hour timer. It can drift or miss runs
  across downtime; raw memory remains searchable and one stopped manual command
  is available. Summary creation and full rebuild add metered Terra and embedding
  work, while nullable derived vectors remain possible during ordinary outages.
- Extracting the generic run loop adds a third pinned local-library boundary.
  It also required a small `llm-tools` public-API upgrade. In return,
  crash/race semantics, strict protocol handling, provider
  containment, and reconstruction have one reusable conformance contract instead
  of becoming Jarvis-specific orchestration.
- A valid answer is not discarded when an ordinary follow-up races with final
  settlement; the answer is delivered and the follow-up runs next. Stop/pause
  remains an immediate host preemption path.
- native callbacks and approved actions share one actual-dispatch lane. the
  reader, ingress, consent and outbox remain responsive during reasoning or an
  isolated gate. serial effects simplify recovery at the cost of throughput.
- main publishes native tool declarations and phase-aware structured output.
  genuine isolated roles retain the kernel's serial logical-step wire adapter;
  jarvis duplicates neither provider lowering nor tool schemas.
- Structured one-shot results must compile into the provider's supported closed
  schema subset. Arbitrary result mappings are rejected; variable-key data uses
  arrays of closed key/value records. This is less ergonomic but fails before
  provider I/O rather than during a paid run.
- native request/control fields and three journals retain original submission,
  invocation, input-delivery and terminal facts. legacy `processing_attempts`
  values remain historical; operator quarantine and immutable action contracts/
  finite executor-entry ceilings remain. there is no general workflow registry.
- isolated kernel time is cooperative at safe boundaries, not an end-to-end response
  deadline, and its context-byte limit covers newly rendered material rather
  than all provider-native history and overhead. Jarvis separately monitors and
  qualifies those omitted surfaces instead of claiming a stronger bound.
- effects carry immutable attempt/checkpoint/input/callback lineage in the
  existing execution-contract json. the retained `claim_id` field contains the
  native attempt id and `model_step_ordinal` its callback ordinal. this avoids
  replaying the wrong subset of a request after steering.
- owner permits replace paid-capacity reservations. usage is observational and
  there is no cumulative main spend ceiling. reasoning can repeat after loss;
  original effect and billed-read barriers prevent that repetition from
  authorizing an unknown external effect or paid read.
- Every action has a finite lifetime executor-entry ceiling. A proven-absent
  effect can end failed when that capacity is exhausted rather than retrying
  forever.
- Raw memory grows without bound and model-made memories can be wrong.
  Correction is by append; v1 deliberately has no erasure mechanism.
- Discord deduplicates a stable per-message nonce only within a recent window,
  and historical responses may omit that nonce. V1 therefore accepts that an
  ambiguous acknowledgement followed by a sufficiently delayed bounded retry
  can rarely repeat ordinary conversational text. This cannot duplicate an
  approval decision or external action.
- Discord transport uses `discord.py` for Gateway/interactions and one direct
  REST create binding because the qualified client does not expose enforced
  nonces; this small split remains until its public API can replace the binding.
- Some providers cannot prove whether every timed-out external effect committed.
  Jarvis exhausts provider-specific automatic reconciliation first, then records
  terminal `uncertain` and asks the owner to inspect rather than retrying blindly.
- A one-user system has no second reviewer. The owner is simultaneously the
  builder, the auditor, and the beneficiary, which instrumentation mitigates and
  nothing removes.

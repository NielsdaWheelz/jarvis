# Jarvis

Jarvis is a personal, persistent AI assistant for one user. It lives in one
configured private Discord channel, uses the user's existing Gmail, Google
Calendar, Google Maps, and Discord integrations plus bounded public-Web tools,
and develops durable memory through a simple remember/retrieve/dream loop.

This repository is specification-first. Slices 0 through 6 implement and
qualify the bounded conversation skeleton, automatic reads and gated writes,
permanent raw memory, isolated recall/remembering/dreaming, requested wakes,
and Approve/Deny execution. Slice 7 owns production deployment, recovery
qualification, and the seven-day owner acceptance period. Backup and restore
are deliberately deferred beyond v1.

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
the descriptions below record the existing v1 baseline, not the unshipped target.

## V1 in one paragraph

Jarvis converses naturally in Discord, recalls relevant memories before every
human turn, uses connected tools, acts automatically for reads and ordinary
reversible work, asks for a simple Approve or Deny decision before consequential
communication to another person, and appends useful memories after interactions.
Conversation history is centralized independently of Discord. Raw memories are
permanent. Summaries, embeddings, and indexes are rebuildable. One main Codex
session normally continues across turns and restarts, while a provider-neutral
kernel reconstruction path can restore it from canonical messages and recalled
memory.
Jarvis is the first consumer of the independent `llm-agent-kernel` library:
Jarvis chooses product context and policy, while the library supplies the
contained Codex session lifecycle, strict one-call-at-a-time loop, mid-loop
steering, and cross-run bounds around `provider-runtime` and `llm-tools`.
Every model-proposed write is checked by a fresh, tool-less internal gate using
only current owner text and a restricted effect descriptor before Jarvis creates
an action or approval.

Jarvis owns exactly six application tables:

```text
message
memory_log
memory_summary
action
model_decision
read_position
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
the old suite and qualification machinery. historical reports in git do
not establish current behavioral verification. the next pr begins the
[testing redesign](docs/issues/testing-redesign.md).

- Baseline date: 2026-09-07
- Status: v1 specification frozen; Slices 0 through 6 complete and qualified;
  Slice 7 production acceptance remains
- Intended deployment: isolated host-native service on the existing Hetzner
  `dev-server`, with native loopback PostgreSQL; no v1 backup
- Primary client: one configured channel in a dedicated private Discord server
- Agent runtime: pinned `llm-agent-kernel`, using subscription-backed Codex
  through `provider-runtime` and host tools through `llm-tools`
- Worker control: the installed skid CLI with a private macbook/devbox/arch
  client config; [ADR 0052](docs/decisions/0052-cut-worker-control-to-current-skid.md)
  defines the current worker boundary. cognition remains on the existing Codex
  appserver/daemon; its deployment repair is separate.

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
- Slice 2 gives up Brave's second automatic search attempt and caps a selectable
  Web-read observation at 64 KiB and aggregate tool output at 768 KiB. This keeps
  billed-once search completion and native context within their hard boundaries,
  but transient search failures and unusually large compound reads fail sooner.
- Calendar events with a provider-declared unspecified end expose a payload-free
  tagged domain variant rather than Google's compatibility end. This preserves
  truth but requires consumers to handle the third observed-end variant; the
  Main session cold-bootstraps once for the corrected get-event v2 contract.
- Calendar event listing uses host-owned bounded pagination and returns typed
  completeness rather than a model-selected limit or truncation guess. Its v6
  result returns at most 1,500 compact overview items in 512 KiB; full details
  require explicit `calendar.get_event` reads. It may use more Google requests
  and still reports unusually dense ranges as partial at the fixed
  page/event/byte/deadline bounds.
- Production Main returns a typed structured terminal which Jarvis renders as an
  answer, partial result, question, failure, or silence. Discord typing is the
  only synchronous progress signal; there is no terminal in-progress promise.
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
- V1 serializes model tool calls and has no model-authored progress narration.
  This trades some read latency for a much smaller partial-effect and recovery
  state machine; Discord typing state indicates activity.
- Codex's strict structured-output subset requires a closed, all-required root
  object, so the kernel transports the logical step through a nullable wire
  envelope. Tool arguments cross that provider boundary as a strict JSON-object
  string and are decoded and independently validated before dispatch. This adds
  output tokens and prevents native per-tool argument-schema enforcement, while
  retaining the authoritative host validation and closed logical protocol.
- Structured one-shot results must compile into the provider's supported closed
  schema subset. Arbitrary result mappings are rejected; variable-key data uses
  arrays of closed key/value records. This is less ergonomic but fails before
  provider I/O rather than during a paid run.
- Four durability fields survive the simplification pass:
  `message.processing_attempts` bounds poison recovery,
  `message.processing_parked_at` makes operator quarantine durable, while
  `action.execution_contract` and `action.attempts` make an occupied write
  position replayable and auditable. They do not create a general workflow or
  tool-version system.
- Kernel time is cooperative at safe boundaries, not an end-to-end response
  deadline, and its context-byte limit covers newly rendered material rather
  than all provider-native history and overhead. Jarvis separately monitors and
  qualifies those omitted surfaces instead of claiming a stronger bound.
- Multi-message effects carry immutable claim/checkpoint/input/step lineage in
  that existing execution-contract JSON. This is more metadata per action, but
  avoids replaying the wrong subset of a turn after mid-loop steering.
- Rolling admission reserves worst-case turn/token capacity before provider I/O
  and retains that charge after a crash. Useful work can therefore be deferred
  even when the process died before consuming the reservation; this is the cost
  of a durable spend ceiling without a workflow database.
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

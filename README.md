# Jarvis

Jarvis is a personal, persistent AI assistant for one user. It lives in one
configured private Discord channel, uses the user's existing Gmail, Google
Calendar, Google Maps, and Discord integrations plus bounded public-Web tools,
and retains admitted history through a shared archive, compressed view, retrieval
and quiet dreaming.

this repository is specification-first. native cognition and shared memory are
installed and owner-resumed. the online memory rollout is qualified with the
[named profile deferrals](docs/implementation-plan.md#memory-installed-rollout);
installed worker observation remains separate. the [feature roadmap](docs/implementation-plan.md) owns remaining
product work, missing specs, external repository handoffs and operational tasks.
backup and restore remain deferred.

the native main cutover in [adr 0065](docs/decisions/0065-native-agent-supervision.md)
replaces the bounded main loop and file-backed control. it preserves isolated
memory roles and existing connectors. see the [integration handoff](docs/native-agent-integration.md)
for the stopped migration, current qualification and dependency-pin status.

[universal memory](docs/universal-memory.md) is the source implementation contract.
this branch hosts the standalone `universal-memory` library in the existing
process/database. it owns append-only originals, a binary summary tree, bounded
views and shared navigation/rank-fused search. jarvis supplies admission,
inference, embeddings, scheduling and a private mcp/http endpoint; provider-runtime
owns native decoding and dev-server owns collectors/profile configuration.

canonical requests and receipts commit before recoverable memory projection.
each new top-level jarvis turn gets a fixed admitted view plus exact operative
requests/receipts. its active loop and compatible steering stay together. native
codex/claude/nexus chats manage their own context and choose shared reads. the
[current memory delivery](docs/memory-delivery.md) adds future-only automatic
capture of the configured owner's nexus librarian runs and completes the live
jarvis/native/nexus integration paths. durable pending exports survive transcript
deletion until central acknowledgement; capture adds no revision or deletion sync.
source and isolated functional proof are complete. the
[latest source evidence](docs/universal-memory.md#native-memory-rollout-source-qualification)
records the qualified dependency repairs, nineteen native/jarvis lanes and
service access boundaries. [adr 0072](docs/decisions/0072-native-memory-rollout.md)
authorizes macbook/devbox installation; arch is deferred and nexus waits for its
next release. [installed evidence](docs/universal-memory.md#native-memory-installed-qualification)
records actual jarvis memory use, quiet dreaming, native capture, private client
access and outage/restart recovery, with the named profile deferrals.
optional notes use the same append-only tree. nightly dreaming quietly
appends attributed syntheses, which create no new seeds or proactive turns.
realistic-load
and usefulness evaluation belongs to a [later pr](docs/issues/memory-usefulness-evaluation.md),
as does broader personal acceptance; this delivery adds no backup or history import.

## implemented source

[one-main events](docs/one-main-events.md) implements the first v2 slice. owner
and host events use one full main plan, with honest attribution and explicit
request state. main chooses useful work, a response or silence. this describes
source behavior; installed activation is separate.
[todos and scheduling](docs/work-records.md#implementation-evidence) adds atomic
current work records and one timer publishing ordinary main inputs. deadlines
remain separate from wakes; recurring rows remain active between occurrences.
originals are permanent; derived memory nodes, views, embeddings and indexes are
rebuildable. legacy notes and flat summaries remain searchable without backfill
or invented provenance.

main uses native declared host callbacks through `llm-agent-kernel`,
`provider-runtime` and `llm-tools`. public progress persists before delivery;
final dispositions complete, continue, wait or stop named delivered requests.
independent work can continue while another request awaits approval. ordinary
`stop` reaches main; exact administrative pause/resume remains host-owned.

deterministic tool policy distinguishes automatic and consent-needed work.
main interprets canonical owner conversation and records approve/deny through
one atomic local callback. the first decision receipt survives retries; it proves
a decision, not execution success. buttons, preview attachments and the separate
model write gate are removed. immutable action arguments, serial execution,
original receipts and causal effect/read barriers remain.

a fresh lease serves each top-level turn. connection or owner loss fences old
callbacks and recovers original sealed results or fresh reasoning from canonical
requests/receipts. no saved-session recovery, rolling paid-capacity
reservation or arbitrary main cutoff remains. finite operation limits and effect
uncertainty barriers remain. skid owns independent worker launch/control; jarvis
owns durable observation and integration.

current source owns eighteen application tables: the native nine, six
library-owned memory tables, `work` (`0010`), `attachment` (`0011`) and
`event_cursor` (`0012`). migration `0013` preserves full read text in postgres
json without adding a table:

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
memory_lane
source_conversation
source_record
memory_leaf
memory_node
memory_state
work
attachment
event_cursor
```

## remaining v2 target

[adr 0071](docs/decisions/0071-simple-event-driven-v2.md) adopts the product
contract. slice 1 supplies the common main lifecycle, conversational decisions
and scoped stop. slice 2 adds work records/wakes; slices 3–4 add qualified skid
follow-through and private native files; slice 5 adds qualified inbound
attachments, and slice 6 adds qualified mail/calendar event sources. slices 1–6
have source qualification; their contracts distinguish isolated proof from
separate candidate qualification. source implementation does not authorize activation.

one work table holds current work and optional one-time or repeated
wakes; due dates remain separate. source main now uses a private native git
checkout for ordinary notes and files; inbound originals use private r2 storage. existing
asynchronous skid observation already delivers events without repeated model
polling. slice 1 removes the old scheduler; outstanding reminders remain private
cutover obligations until slice 2 accounts for them. unattended activation is
disabled while the selected slices and those obligations remain incomplete.
slice 4's [private workspace](docs/private-notes-and-rolodex.md) also holds runnable
helpers, components, charts and self-contained interactive files. production
bootstrap/acceptance remains at final v2 cutover. browser and
credential products, interactive hosting/television integration and a separate ui
are deferred. the shared-memory delivery remains separate and unchanged; selected
dream wakes and work-informed dreaming are outside this cut. budget and broader
memory/maps/fleet search remain later work.

[adr 0075](docs/decisions/0075-v2-completion-and-subscription-model.md) adds three
[finishing prs](docs/implementation-plan.md#v2-finishing-prs):
[complete mail/calendar/web reads](docs/mail-calendar-web-reads.md#implementation-evidence)
has source and separate candidate qualification. native/discord reliability and
integrated acceptance still needs a spec, as does the owner's
`gpt6astra-max` target (`gpt-6-astra`, reasoning `max`) through his personal codex
subscription and provider library. current model/runtime pins are unchanged.
no new orchestrator, persona system or inbox housekeeping is included; final
production cutover follows combined qualification.

## Authoritative documents

1. [specification](SPEC.md) — normative baseline and accepted product targets.
2. [Architecture](docs/architecture.md) — runtime, component, data, and tool
   boundaries.
3. [memory](docs/universal-memory.md) — archive, tree/view, retrieval, admission,
   dreaming, schema and atomic completion contracts; [current delivery](docs/memory-delivery.md)
   owns implemented nexus capture and the remaining installed handoff.
4. [Acceptance](docs/acceptance.md) — the definition of done, and the single
   completion predicate for v1.
5. [Roadmap and implementation plan](docs/implementation-plan.md) — the single
   active handoff for memory, orchestration and subsequent product slices.
6. [Decision records](docs/decisions/) — why the current design exists.

When documents disagree, `SPEC.md` wins. Changing a frozen decision requires an
ADR that also updates every affected normative document in the same change.

the [integrated roadmap and plan](docs/implementation-plan.md) brings approved
product direction, delivery dependencies, open decisions and acceptance together.
it distinguishes accepted memory and v2 targets from implemented source, installed
behavior and later contracts. retired v1 plans, qualification reports and the completed cleanup
log live in git history; current contracts and operations remain in the working tree.

## Status

the owner-approved [testing reset](docs/decisions/0046-reset-testing.md) removes
the old standing suite. native and worker changes completed explicitly authorized
temporary integration/live qualification; the broader
[testing redesign](docs/issues/testing-redesign.md) remains separate. historical
receipts qualify only their named artifacts and boundaries.

- source status as of 2026-11-15: memory and worker-v10 source checks pass;
  native main retains its recorded functional proof. full static/build/install
  checks and the registry audit pass.
  the [online memory rollout](docs/implementation-plan.md#memory-installed-rollout)
  passes with named profile deferrals. installed physical connector and worker
  observation checks remain separate.
- [one-main events](docs/one-main-events.md#implementation-evidence) records slice 1
  source implementation and its exact qualification artifacts. this intermediate
  events source is not deployed; selected slices and retained reminder obligations
  must be accounted for before activation.
- deployment administration runs from the operator workstation through the
  separately keyed `dev-server-deploy` ssh alias with `sudo -n`. `dev-server`
  is the unprivileged developer connection; it has no administrative fallback.
- Intended deployment: isolated host-native service on the existing Hetzner
  `dev-server`, with native loopback PostgreSQL; no v1 backup
- Primary client: one configured channel in a dedicated private Discord server
- Agent runtime: pinned `llm-agent-kernel`, using subscription-backed Codex
  through `provider-runtime` and host tools through `llm-tools`
- worker contract: [adr 0064](docs/decisions/0064-simple-worker-orchestration.md),
  skid cli and live installed computer state (`JARVIS_AGENT_STATE_DIRECTORY`);
  [adr 0072](docs/decisions/0072-native-memory-rollout.md) adopts the enrolled
  `macbook|dev-server|arch` worker names and a read-only id-mapped state mount.
  memory provenance still uses `devbox`.
  [installed service-state reads](docs/universal-memory.md#native-memory-installed-qualification)
  pass on both online hosts; worker observation remains separately qualified
- cognition: [adr 0065](docs/decisions/0065-native-agent-supervision.md), a separate
  contained stock endpoint and the existing personal host account; its public
  host mapping has a read-only file bind, preserving private directory access

## Development and verification

Development uses the CPython 3.12.13 pin in `.python-version`; supported runtimes
are 3.12.13 or later in the 3.12 series. with the qualified `uv` 0.13.4 installed, run:

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

these bound the present product; adr 0071 adopts the named v2 expansions above
without adopting every later roadmap contract.

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

these describe current source trade-offs; installed behavior is qualified separately.

- Service shutdown is cooperative: stop new ingress, let admitted operations
  reach their safe stopping point, drain callbacks/workers, then close clients
  and release database ownership. Startup/recovery work already underway may
  delay stopping. A first SIGINT retains exit status 130; the existing 360-second
  systemd deadline or a second interrupt can force termination and crash recovery.
  Shutdown does not stop independently running Codex workers or shared servers.
- Discord is a third-party processor for every conversation, every quoted
  memory, every summarized email, and ordinary consent conversation.
- The complete raw memory corpus and every semantic-search query are disclosed
  to the embedding processor; see
  [ADR 0008](docs/decisions/0008-embedding-source.md). Ingestion, backfill, and
  query-embedding calls are metered by that processor.
- One subscription pool is a single point of total conversational outage, with
  no fallback by design.
- fresh top-level turns reconstruct historical orientation and exact operative
  facts. compression may delay dispatch until a complete fitting view exists.
  summaries can lose detail; source opening remains available.
- Embedding failures leave committed raw memories with null vectors. Those rows
  remain lexically searchable and a bounded later sweep retries them, but
  semantic coverage is incomplete during the outage. a failed query embedding
  returns a typed error; there is no lexical-only fallback search.
- Raw memory grows indefinitely in v1. There is deliberately no deletion,
  redaction, forgetting, or destructive consolidation path; storage and search
  cost grow with use until a later accepted design addresses every durable copy.
- main interprets conversational consent using canonical owner messages. host code
  proves owner identity, current admission and the immutable first decision; it
  does not prove that the model interpreted the owner's meaning correctly.
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
- [mail/calendar/web reads](docs/mail-calendar-web-reads.md) use explicit bounded
  pages and full-text byte chunks. main chooses calendars and depth; live changes
  require explicit restart. web search caches one disposable page, and stale
  local cursors fail without another paid fetch. strict calendar snapshots remain
  separate from text evidence. deeper reads use more calls and context.
- main persists typed public progress as prose without completing owner requests.
  final output separately renders an answer, partial result, question, failure
  or silence, with explicit request dispositions. malformed structured output
  parks affected live requests for repair while original native terminal evidence
  remains intact; no host input is silently marked handled.
- Codex session history, compaction, and cache behavior are non-canonical
  optimizations. A changed session-scoped contract or lost session takes a cold
  context bootstrap, and no cost saving is guaranteed. Rotating or discarding
  Jarvis's local reference does not prove deletion of provider-retained session
  data.
- nightly idle dreaming processes one bounded pending prefix and makes at most
  one attempt per owner-local occurrence. backlog can exceed nightly throughput;
  stopped manual work is available. interrupted background inference may repeat
  paid work. completed nodes, original receipts and consumed progress persist.
- Extracting the generic run loop adds a third pinned local-library boundary.
  It also required a small `llm-tools` public-API upgrade. In return,
  crash/race semantics, strict protocol handling, provider
  containment, and reconstruction have one reusable conformance contract instead
  of becoming Jarvis-specific orchestration.
- A valid answer is not discarded when an ordinary follow-up races with final
  settlement; the answer is delivered and the follow-up runs next. administrative
  pause preempts globally; conversational stop settles only named requests and
  cannot cancel an effect that already entered.
- native callbacks and approved actions share one actual-dispatch lane. the
  reader, ingress, consent and outbox remain responsive during reasoning. serial
  effects simplify recovery at the cost of throughput.
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
- Discord deduplicates a stable per-message nonce only within a recent window,
  and historical responses may omit that nonce. V1 therefore accepts that an
  ambiguous acknowledgement followed by a sufficiently delayed bounded retry
  can rarely repeat ordinary conversational text. This cannot duplicate an
  approval decision or external action.
- Discord transport uses `discord.py` for Gateway input and one direct
  REST create binding because the qualified client does not expose enforced
  nonces; this small split remains until its public API can replace the binding.
- Some providers cannot prove whether every timed-out external effect committed.
  Jarvis exhausts provider-specific automatic reconciliation first, then records
  terminal `uncertain` with the original evidence. main explains the limitation;
  uncertainty never authorizes another executor entry.
- a one-user system has one accountable human operator. independent agent review
  helps challenge changes; it does not transfer the owner's responsibility.

# V1 architecture

This document expands [SPEC.md](../SPEC.md). `SPEC.md` wins if they disagree.

the accepted [universal-memory target](universal-memory.md) extends this baseline
with stateless host collectors, a private capture api and pull-only mcp reads
inside the existing central process. its ownership, schema and capability changes
are not yet implemented.

## System shape

```text
configured Discord #general
          │
          ▼
 Discord adapter ───────────────► message
          │                          │
          ▼                          ▼
 fresh recaller ──────► Jarvis context/checkpoint/session adapters ◄── memory
                                     │
                                     ▼
                             llm-agent-kernel
                     contained serial run + admission
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
       provider-runtime / Codex                 call_tool dispatch
                    │                                 │
            structured terminal                Jarvis policy
                    │                                 │
                    ▼                       Write? ─► isolated
          message / Discord                 AutomaticWriteGate
                                                      │
                                                      ▼
                                                  llm-tools
                                                      │
                                   ┌──────────────────┴──────────────┐
                                   ▼                                 ▼
                             queued action                   awaiting approval
                                   │                                 │
                                   ▼                           host-rendered
                               executing                    Approve / Deny
                                   │                                 │
                                   ▼                                 ▼
                           existing integration                  executing

completed owner turn ──► fresh rememberer ─► host transaction ─► memory_log

simple timer ──────────► fresh dreamer ─────► host transaction ─► memory_summary
```

Jarvis is one Python application and one PostgreSQL database. Components below
are code boundaries, not independently deployed services unless an existing
integration requires one.

## Physical deployment

V1 runs on the existing Hetzner `dev-server`, never on the Nexus production
host. Jarvis is a host-native systemd service under a dedicated `jarvis` Unix
account. Immutable releases live at `/opt/jarvis/releases/<git-commit>` and an
atomic `/opt/jarvis/current` symlink selects one release. Runtime state lives in
`/var/lib/jarvis`; root-owned configuration and credentials live in
`/etc/jarvis`. The application opens no public listener and is administered
only over the host's existing tailnet boundary.

The host's native PostgreSQL 16 remains loopback-only. Jarvis receives its own
database plus separate migrator and runtime roles. It does not share schemas,
roles, or credentials with another application. V1 deliberately has no backup
or restore path and accepts possible total loss of local Jarvis state. The
dev-server convergence repo
owns only common host prerequisites, UTC, the service account, and base
directories. Jarvis owns releases, its exact locked environment, database
lifecycle, migrations, service definition, and recovery.

Development and CI workloads share the host but not Jarvis's Unix identity,
release tree, service lifecycle, or database roles. This accepted v1 coupling
is bounded with systemd resource controls and disk-headroom checks. The release
attaches only to the host-owned Codex services and carries no private SDK
runtime or bundled Codex binary.

Native Codex tracks latest stable through the host installer (ADR 0042), without
version admission or version-only install-triggered restart. The schema-2 host mapping contains only
operational configuration; protocol/authority checks and library locks remain strict.

`llm-agent-kernel` is a pinned independent library, not another service or
state owner. It supplies contained Codex session choreography, strict serial
protocol, mid-loop polling, settlement, and bounded run machinery.
`provider-runtime` remains the provider/session implementation. It owns the
WebSocket-over-Unix-socket Codex App Server client behind the stable
`AgentRuntime` API and closed-world native event/request classification. `llm-tools`
remains the prompt-section, contract, implementation-identity, grant,
validation, and tool-execution implementation. Jarvis owns every product and
persistence adapter.

## Discord adapter

The adapter:

- Receives the owner's messages only from the configured guild and channel and
  ignores direct messages, threads, other channels, and other users.
- Deduplicates gateway re-delivery by Discord message ID.
- Boundedly catches up owner messages after the latest stored Discord message ID
  when Gateway resume cannot cover downtime.
- Matches `stop`, `pause`, and `resume` before model work.
- Persists inbound messages before processing.
- Delivers pending assistant messages and records Discord message IDs.
- Starts typing state promptly while a turn runs.
- Renders host-owned Approve and Deny messages from stored action arguments.
- Delivers the complete deterministic UTF-8 JSON approval payload as one bounded
  text attachment; arbitrary payload text never becomes message Markdown.
- Accepts only opaque components binding the action and internal approval-message
  IDs from the configured owner, guild, and channel, then verifies the live
  Discord message ID against that stored relationship.
- Atomically claims or denies component interactions, then immediately
  acknowledges them by disabling both components before external work.
- Prevents model tools from editing host-owned approval messages.
- Exposes no model-callable Discord tools. Ingress, terminal delivery, typing state,
  host approval presentation, and editing Jarvis's own approval message are
  adapter operations.

The adapter renders model output as ordinary text/Markdown. The reused role has
broader inherited permissions than the adapter needs, including `EMBED_LINKS`,
but no model-callable Discord tool exists. Every outbound create suppresses
embeds and all creates/content edits disable mention parsing. Gateway ingress,
typing, and component interactions use `discord.py`. Outbound Create Message
uses a narrow host-owned Discord REST v10 `httpx` binding because the qualified
`discord.py` 2.7.1 send API does not expose `enforce_nonce`; no private library
API is used.

## Message lifecycle

### Inbound

```text
Discord event
→ insert owner message with processed_at null using unique source identity
→ if already present, stop
→ enqueue/start its turn
```

### Outbound

```text
validated structured terminal or host-rendered response
→ insert assistant message with source_message_id null
→ derive deterministic nonce from message.id
→ create with the same nonce and enforce_nonce=true
→ store Discord message ID as source_message_id
```

On startup, the adapter retries assistant messages whose `source_message_id` is
null. Every retry reuses the same enforced nonce. Discord deduplicates the
recent case, but its history and exact-message reads may omit nonce, so a delayed
retry cannot reliably adopt the prior message. Subject to a small finite
retry/backoff policy, it may resend and rarely repeat ordinary conversational
text. The nonce is derived from the internal message ID and requires no durable
field. This transport trade-off cannot duplicate an action effect.

Approval messages follow the same persistence rule. The action's
`approval_message_id` references the internal message row; that row acquires the
Discord delivery ID. A component interaction must match both.

## Turn coordinator

For each owner message:

1. Check the paused flag.
2. Persist/deduplicate the inbound message.
3. Acquire the in-process execution mutex and preflight rolling admission. A
   denial defers without claiming or incrementing the input.
4. Atomically increment the oldest input's `processing_attempts`, claim one
   non-empty bounded compatible unparked batch, and choose its frozen plan.
5. Prove that plan against its exact catalog and definition envelope, then use
   the plan-aware factory to create a fresh tool budget whose limits equal the
   plan's `RunLimits` exactly.
6. Durably reserve the complete finite root/child provider allowance before
   provider I/O. Because the preflight and claim ran under the same execution
   mutex, the adapter raises `AdmissionStateDefect` for a later inconsistent
   capacity result and the kernel parks the claim.
7. Snapshot one host `as_of` instant and start the fresh isolated read-only
   kernel recaller one-shot. The kernel first dispatches exactly one deterministic
   `memory.search` typed observation, then continues the recaller's adaptive
   search/open loop.
8. Through the context adapter, select canonical product context and give the
   kernel a provider-neutral continuation or bootstrap package.
9. The kernel opens/resumes the real contained `AgentRuntime` session, consumes
   its observable event stream, and runs its bounded serial loop. It polls for
   compatible owner input before provider and tool boundaries and for
   stop/preemption before settlement.
10. For a validated write proposal, pause the main loop and run the isolated
   AutomaticWriteGate over only current owner text and a restricted effect
   descriptor synchronously under the same root ownership before action creation
   or effect dispatch.
11. Through the checkpoint adapter, atomically persist the conclusion, set
   consumed waking rows' `processed_at`, and place the same run/checkpoint/
   conclusion identity in their bounded traces. Ordinary later input runs after
   commit; cleanup never rearms by itself.
12. Settle/refund admission, deliver pending responses, and release the execution
   mutex.
13. Run the rememberer later through a fresh admitted isolated kernel run,
    yielding to new owner work.

A turn is eligible for remembering after any valid Main terminal or creation of
an action awaiting approval. This includes a turn whose visible response is a
host-rendered approval message rather than model-authored prose.

At startup, a waking owner or host row with null `processed_at` and null
`processing_parked_at` is an interrupted turn. A host action-resolution row is
safe to replay. If no action execution
contract names an owner row among its admitted input IDs, it may be reclaimed
only within its durable attempt ceiling and rolling admission. If a contract
does name it, the host resumes or reconciles the action and closes exactly that
contract's input IDs through its stored checkpoint with an interruption notice,
without replaying the model. For several actions from one run it handles every
action and closes the union once through the greatest compatible stored
checkpoint. `origin_message_id` is a convenient root pointer, not the recovery
proof. Protocol/budget/quota/stop poison exits persist a
host-authored stopped conclusion and consume the input instead of buying a fresh
run. This is the turn-level duplicate-effect and runaway-work barrier.

An action outcome that cannot return to its still-live originating model loop
idempotently inserts one host-authored waking `message` keyed by
`(source = action, source_message_id = action.id + ":" + status)`. It carries the
action ID, tool, resolved state, and safe normalized result. A later evidence-
based transition from `uncertain` to `succeeded` or `failed` therefore earns a
new resolution row rather than rewriting history. The main drain processes it
through the same checkpoint path and may explain the outcome naturally; it never
relies on a model-authored call ID. The host row carries the action ID, tool,
original validated arguments, resolution, and safe evidence. Startup repairs a missing required
resolution row from terminal action state before becoming idle.

Action-resolution and scheduled-wake host inputs require visible delivery. If
Main returns `silent` or fails before a renderable terminal, Jarvis finalization
persists a deterministic assistant fallback from the host row's safe fields and
processes both together. The fallback for uncertainty includes reconciliation
evidence; the fallback for a wake includes the stored reminder instruction.

The application holds one PostgreSQL advisory lock for deployment ownership. A
second Jarvis instance refuses to start. Because only one process runs, turn and
provider scheduling inside that process use ordinary locks and queues rather
than additional database workflow machinery.

The exclusive claim, ordered bounded waking batch, opaque consumed watermark,
poll, and atomic terminal checkpoint implement the kernel
`InputCheckpointPort` over `message`. `processing_attempts` is the counter needed
to bound recovery across process crashes; `processing_parked_at` is the separate
durable operator-quarantine timestamp. Normal claims and scans exclude parked
rows. `park` stamps the complete claimed unprocessed batch and a bounded trace
reason in one database transaction, then ends claim ownership. Any parked row
opens the single cognitive circuit until operator repair explicitly clears it;
the circuit is derived from PostgreSQL, not duplicated in the private journal.
Delivery and mandatory reconciliation of an already-started effect remain
available. Owner and action-resolution work receives the full plan and outranks
a scheduled wake;
the latter is claimed separately under the read-only plan. Incompatible input
remains unclaimed. Idempotent cleanup releases ownership without scheduling a
successor. Null `processed_at` plus null `processing_parked_at` and
startup/recovery scanning remains the durable work signal.

The kernel dispatch adapter receives an immutable claim ID, through-checkpoint,
ordered admitted input IDs, and model-step ordinal. Every action copies these
facts into its execution contract before executor entry. Thus a write proposed
after mid-loop input is durably linked to the complete input prefix that could
have influenced it.

If compatible owner input arrives during the loop, polling appends it once to
the healthy session. Stop/pause signals cancellation immediately. If ordinary
input arrives after the final poll, the valid current answer commits and the
new input runs next; v1 deliberately does not suppress and regenerate the first
answer.

## Context and session lifecycle

Jarvis's application context adapter selects model-visible product context from
canonical state before any provider-specific encoding. Its plain structured
package contains:

- Stable instructions.
- Bounded completed canonical messages, excluding the current owner row.
- The current event with its source timestamp.
- Recalled memories with IDs, timestamps, and summary lineage.
- The capability descriptions granted to the role and turn.
- The configured owner IANA timezone.
- One host-generated `as_of` instant.

The current event appears exactly once. `llm-agent-kernel` coordinates the
continuation/bootstrap projection and `llm-tools` typed prompt sections render
it. XML-like markup is useful structure and provenance, not a prompt-injection
security boundary. Provider adapters translate the rendered package into native
inputs; selection code does not construct provider-private transport objects.

The configured Discord channel owns one main Codex session. Its
`AgentSessionRef` and immutable agent-definition fingerprint live in an
atomically replaced private runtime-state file, not PostgreSQL, behind Jarvis's
kernel `SessionRefPort` adapter. The fingerprint covers stable instructions,
model and reasoning configuration, output contract, credential-profile identity,
cwd/directories/MCP configuration, `PermissionPolicy`, native options, the
session capability envelope, and the required owner-controlled
`session_compatibility_revision`. Jarvis derives that revision from a checked-in
canonical manifest containing the role ID, an owner-bumped application
session-contract revision, and the exact kernel, provider-runtime, and llm-tools
pins. Manifest schema v3 also records the exact qualified local-account model
set, currently only `gpt-5.6-terra`. Model-set membership does not enter the
session revision because the selected model already enters the immutable
definition fingerprint. Secret bytes, current input, host time, and per-run
subset plans do not rotate the session.
Schema v3 has no predecessor normalization or compatibility reader. Every pin
participates literally, so this hard cut invalidates old definition
fingerprints and cold-bootstraps the next cognition session. The
AutomaticWriteGate fingerprint remains a Write-binding policy input, so its
rotation also recomposes affected main profiles, plans, and HostTables.
Configuration accepts only an exact model in the manifest and rejects the
retired `gpt-5.4` route before ingress, admission, or provider/tool I/O. The
qualified set has no fixed cardinality, but release qualification requires at
least one currently provider-supported ChatGPT local-account route to pass
live.
An ordinary restart or compatible deployment
attempts resume through `provider-runtime`. A fingerprint mismatch, invalid
reference, or resume failure discards the reference and opens a fresh session.
References are scoped by application thread and fingerprint; a generation
compare-and-set prevents a stale run from overwriting a newer reference.
Generation never expires a compatible reference. Codex owns automatic context
compaction within that same thread; Jarvis retains its per-run and rolling
limits without estimating retained native history. See [ADR 0043](decisions/0043-retain-main-thread-through-native-compaction.md)
for the large-input failure trade-off and recovery boundary.
Every stored reference returns the generation expected by the next model step.
A stale store stops before dispatch or canonical settlement; Jarvis never acts
on a response whose provider state it failed to save.
After a crash with unprocessed canonical input, Jarvis discards a speculatively
advanced reference unless alignment can be proved and cold-bootstraps before
replay. On a valid terminal response, the generation-checked reference advances
before the canonical conclusion/checkpoint transaction. If the latter is
interrupted, null `processed_at` exposes the unresolved input and makes that
reference unsafe to reuse.

A continuation projection sends the current event, current capabilities,
`as_of`, and fresh recall only for owner input; stable session context, including
owner timezone, and native history carry prior turns. A bootstrap projection
prepends stable instructions and bounded canonical history. That same bootstrap
package is the required boundary for a future stateless or API-backed provider.
V1 does not implement the second provider. The current batch appears only on its
first call in one provider session; later tool/protocol continuations carry only
new observations or corrections. A replacement cold bootstrap includes
unresolved input once in the replacement session.

Recaller, rememberer, dreamer, and AutomaticWriteGate calls always open fresh
isolated sessions. Their agent definitions use kernel `SessionMode.isolated`;
they never load or save a session reference or reuse the main session or one
another's history, and their frozen plans contain no `ToolEffect.Write`. The
first three have memory reads; AutomaticWriteGate has an empty plan and does not
receive the general context package. The main definition uses
`SessionMode.continuing`. Source-message timestamps remain attached to their
content. Each fresh session receives the timezone once only when relevant; each
newly admitted input batch or background job receives one host-supplied `as_of`.
A compatible batch appended mid-loop receives its own; tool-only continuations
and embedding requests receive no repeated clock.

Session history, native compaction, and cache behavior are disposable
optimizations. A cold bootstrap need not recreate provider reasoning or
compaction byte-for-byte; it must restore useful conversational continuity from
canonical messages plus recall. Discarding a local reference does not prove
deletion of provider-retained session history.

Checkpoint finalization maps the terminal conversational conclusion and
consumed-input checkpoint into the same Jarvis transaction. It writes the same
run ID, checkpoint, nullable conclusion-message ID, and conclusion outcome into
bounded `message.trace` on every consumed waking row. Read observations and
protocol correction remain turn-local; effectful outcomes are already durable
in `action` through its `llm-tools` position/recorder mapping. The kernel
`EventSinkPort` is optional best-effort observability, not a canonical event
store. Emission is attempted before reuse but failure is nonfatal. Exact
provider requests and normalized events remain provider/runtime audit data;
Jarvis stores only bounded IDs, counts, usage, duration, and outcome, not another
event table.

An atomically replaced content-free runtime journal enforces the rolling
admission window. A root reservation includes maximum turn/token allowance for
the foreground run and its possible serial recaller/write-gate children;
background one-shots reserve independently. Clean exit settles actual usage
and refunds unused capacity. Startup under the deployment lock marks orphaned
reservations interrupted and releases their live slot while retaining their
rolling capacity charge until expiry. Corruption fails closed.

## Cognitive roles

These are five immutable kernel agent definitions, not a general subagent or
persistent-peer system. The main role is a continuing thread run with a closed
structured terminal contract and a maximum envelope equal to the exact main
catalog. Recaller, rememberer, dreamer, and AutomaticWriteGate are fixed isolated
one-shot runs with closed structured output contracts. The first three have
memory-read envelopes; the gate has none. Jarvis supplies a frozen subset plan
per run; owner/action-resolution runs use the full Main plan and scheduled-wake
runs narrow the same continuing definition to external reads. One-shot plans
contain no `ToolEffect.Write`. One-shot runs use no application checkpoint or
saved session-reference port; host code commits or recomputes their results.

### Recaller

The recaller opens a fresh session and receives the owner input, bounded recent
context, owner timezone, and the turn's `as_of`. Its frozen capability plan
contains only memory search and memory open. Recall begins with exactly one
kernel-dispatched deterministic `memory.search` call and its schema-validated
typed observation. From that observation, the recaller may adaptively issue
further searches or open exact rows. It returns a schema-valid `finish.result`
bundle of raw memories and summaries, or an explicit empty bundle.

### Main agent

The main agent normally continues the channel's existing session. It receives
fresh recalled memory on owner turns and the capability descriptions exposed
for every turn. It emits the strict structured step grammar defined once in
[SPEC section 7.4](../SPEC.md#74-model-step-protocol-and-bounded-drain).

Main alone receives the owner-approved conversational voice in its role
instructions and the stable owner profile in its `owner_context`. The other
cognitive roles receive neither. A change to either value changes Main's
definition fingerprint and role-contract revision, causing a cold bootstrap;
it does not change a tool plan or database schema. Public-Web search is
model-callable only when the current owner input explicitly requests it.

The pinned kernel projects that logical grammar into Codex's closed nullable
provider-wire envelope and converts the selected payload back before semantic
validation. Tool arguments are one strictly decoded JSON-object string at that
boundary because the provider schema cannot represent arbitrary object keys;
Jarvis receives only the validated logical call. Structured role result schemas
compile before provider I/O, and contracts outside the supported closed subset
are rejected during definition construction.

The main agent never owns credentials or policy classification. Host code
supplies product dispatch and policy. The kernel validates the whole step and
the pure `llm-tools` seam validates its one proposed call before dispatch. Calls
execute serially. `call_tool` carries no user-facing text; after the model
observes the bounded result, it may issue one truthful structured terminal.

### AutomaticWriteGate

For each validated main-agent `Write`, this role opens a fresh isolated session
while the main run is paused before effect dispatch. It runs synchronously under
the same root ownership; its empty frozen plan permits no tool call. It sees
only current owner-authored input IDs/text, the canonical proposed tool ID, and a
host allowlist of authority-relevant operation/target/audience/time scalars. The
trusted time scalars include owner timezone and batch `as_of` only when needed to
check relative wording; free-form payloads are represented by length and digest. It never sees recall,
tool or Web observations, connector content, main-model rationale/history, or
credentials.

Its closed result is `allow | deny` plus supporting current owner IDs. The host
accepts allow only for a direct, scope-matched current request and stores those
IDs in the action execution contract. Every other result fails closed with no
action or approval message. The role neither grants a capability nor classifies
approval; deterministic Jarvis policy remains authoritative.

### Rememberer

The rememberer opens a fresh session and receives the persisted completed turn,
material tool observations, source timestamps, and relevant existing memory. It
can search/open memory and returns a schema-valid `finish.result` list of zero or
more raw memory strings.

Host code performs one transaction that:

- Appends the new `memory_log` rows.
- Sets `remembered_at` on every owner message in the settled input group.

The rememberer does not call a memory write tool and creates no action rows. A
failed or cancelled run leaves every target `remembered_at` null for a bounded
retry sweep. Shared settlement trace reconstructs the normal group. If grouping
metadata is absent, the sweep processes owner rows individually and relies on
memory search/model judgment to limit redundant append.

### Dreamer

The dreamer opens a fresh session, searches and opens memory, then returns a
schema-valid `finish.result` batch of summary insertions and removals. Host code
applies the batch transactionally.

Only one dreamer runs at once. It yields the execution mutex when owner input is
waiting. Missing a dream run cannot break conversational correctness because raw
memory remains directly searchable.

The process-local timer waits 24 hours by default before its first attempt and
has no durable scheduling row. Manual dreaming and full derived-memory rebuild
reuse deployment ownership and therefore refuse to overlap the service. Once a
validated mutation batch enters its short database transaction, foreground work
waits for that transaction to commit or roll back atomically.

## Tool execution

The complete tool manifest and authority classification live in
[SPEC section 7.3](../SPEC.md#73-tool-contracts-and-exact-catalog). Jarvis owns the
Gmail, Calendar, Maps, schedule, and memory declarations and bindings. The pinned
`llm-tools` revision owns the reusable `web.search` and `web.read` declarations
and implementations; Jarvis explicitly composes, configures, and grants them.
Discord is the conversation adapter and has no model-callable declarations.

Capability plans are closed by role:

- Main: the catalogued Gmail, Calendar, Maps, Web, and `schedule.wake` tools.
- Recaller, rememberer, and dreamer: `memory.search` and `memory.open` only.
- AutomaticWriteGate: no tools.

There are no local-filesystem, Gmail organization, progressive-discovery, or
Discord tools in a v1 capability plan.

The implemented Slice 6 maximum catalog contains exactly the ten Gmail,
Calendar, Maps, and public-Web reads; `memory.search` and `memory.open`; and all
seven v1 writes. The selected Main plan contains the ten external reads plus
`gmail.create_draft`, `gmail.update_draft`, `gmail.send_draft`, the three
Calendar writes, and `schedule.wake`. The scheduled-wake plan contains only the
ten external reads. Recaller, rememberer, and dreamer contain only the two
memory reads, and AutomaticWriteGate has an empty plan. The approval-bearing
Main plan is selectable only after its exact catalog, HostTable, tightening,
budget, durable suspension, rendering, resolution, and recovery paths qualify.

The host:

- Gives every Jarvis-owned binding the non-empty implementation revision from
  SPEC section 7.3; portable Web bindings retain their `llm-tools` revisions.
- Freezes a capability plan for each cognitive role and turn, proving the exact
  catalog view—including handler implementation identity—before rendering or
  I/O.
- Supplies that plan and its product dispatch adapter to `llm-agent-kernel`.
- Supplies one plan-aware budget factory that creates a fresh `BudgetState`
  after validation, with limits exactly equal to the selected plan's
  `profile.run_limits`; budget state is never shared across runs.
- Uses the qualified pure `llm-tools` seam to validate canonical tool IDs and
  closed arguments before dispatch-side mutation.
- Runs AutomaticWriteGate for every validated `Write` before inserting an action
  or rendering approval.
- Classifies calls using the fixed automatic/approval policy.
- Owns connector credentials.
- Executes reads through `llm-tools` without action rows.
- Inserts an `action` before every effectful tool call.
- Supplies the action ID as both durable `InvocationPosition` and `EffectId`.
- Copies kernel dispatch lineage and the gate's supporting owner IDs into the
  immutable action execution contract.
- Returns one bounded completed `ToolResult` or one durable suspension through
  the kernel dispatch port.

Canonical message persistence, raw-memory append, and summary replacement are
application transactions. They are not model tools and do not pass through
`llm-tools`; terminal conversation persistence is exposed to the agent kernel
only through Jarvis's checkpoint adapter.

Slice 2 constructs a fresh non-durable read recorder and exact plan budget for
each run under the existing execution mutex. Its definition maximum is exactly
10 calls, 223 external attempts, 73,768 input bytes, 1,638,400 output bytes, one
in-flight model-tool call, and 205 seconds. Selectable plans retain all ten calls
but tighten `web.search` to one attempt, `web.read` to 65,536 output bytes, and
the aggregate to 222 attempts and 786,432 output bytes. A Web secret gate recursively
checks raw and percent/query-decoded string leaves before recorder, budget,
executor, or provider entry. Reads terminalize only in run-local state and never
insert `action`.

Calendar normal observations carry a required direct tagged end: timed,
all-day, or payload-free `type=unspecified`. A missing or false Google flag
requires a concrete parsed end. True produces the unspecified variant and
discards Google's compatibility end, for every normal event type; start remains
required. Sparse cancelled events remain separate. The three-branch observed
projection is deliberately not a future create/update input, which retains the
unchanged two-branch concrete end and address-required attendees. Calendar
discovery lists every non-deleted reader-or-better CalendarList entry, including
hidden entries, with a hard 50-calendar bound. Aggregate event reads page in
deterministic calendar-ID rounds with concurrency ten, a 250-event provider page,
100 event-page requests, a 55-second connector deadline inside the 60-second
executor fence, and 202 total external attempts including discovery and refresh.
They project compact overview records, merge globally in chronological order,
and return at most 1,500 whole items inside the 524,288-byte canonical envelope.
Overview items retain exact IDs, status, summary, start, observed end, and
location; `calendar.get_event` supplies description, recurrence, people,
reminders, etag, and update metadata on demand. A typed coverage value reports
calendar/page/failure/count/byte/deadline incompleteness; exact fields are never
shortened. Discovery is binding v1, aggregate list is v6, and get remains v2.
Recomposed catalog/profile/plan/HostTable and Main output/role identities force
a continuing-session cold bootstrap without changing isolated roles or database
state.

Google OAuth, Google API, Maps, Brave, and Discord each use a dedicated
host-owned HTTP client with environment proxy trust and automatic redirects
disabled. Connector credentials are applied only by their owning binding; the
public reader opens direct pinned-peer sockets and receives no shared cookie,
default-auth, or connector state.

## Kernel protocol and drain

`llm-agent-kernel` parses exactly `say`, `call_tool`, or `finish`. Jarvis's
active Main definition uses the existing structured-output contract, so `say`
is unavailable and a terminal is one validated `finish.result`. A
`call_tool` contains one canonical ID and arguments and no prose, preview,
authority, approval instruction, or model-authored call/effect ID. Unknown
fields fail. `provider-runtime` first enforces the declared JSON schema; the
kernel then validates the complete semantic step, output contract, frozen plan,
and pure arguments before any display, recorder mutation, budget reservation,
or dispatch. Protocol-invalid output executes nothing and receives only bounded
corrective context.

Calls execute one at a time. A bounded completed observation returns to the
next provider turn, and only a later structured terminal can describe its actual
outcome. A
durably accepted approval or reconciliation need returns `suspended(host_ref,
waiting_for)`, settles the proposing input, and releases live resources. A
later action-resolution host row contains the action ID, tool, original
validated arguments, state, and safe evidence. Jarvis action semantics—not the
kernel—interpret approved, denied, failed, or terminal uncertain outcomes.

For `Write`, the main run pauses at this dispatch boundary while the separately
admitted AutomaticWriteGate one-shot runs. Its denial becomes a typed policy
observation. Only an allow can proceed to durable action creation and ordinary
deterministic approval classification.

`KernelLimits` own provider turns, protocol repairs, cooperative elapsed time at
safe boundaries, normalized provider usage, and cumulative newly rendered
kernel context bytes for the current invocation. The remaining cooperative time
is a hard provider-turn deadline, not an end-to-end SLA: host ports, tools,
settlement, parking, and cleanup can return later. The kernel never wraps a
`Write` in an unsafe outer timeout. `max_new_context_bytes` excludes provider
system/developer material, schema transport, retained native history, and
provider compaction. Jarvis bounds static material separately; native Codex
owns retained-history compaction under ADR 0043. `llm_tools.RunLimits` alone
own tool calls, attempts, bytes, `max_in_flight = 1`, and tool elapsed limits. V1
has no parallel or multi-call path and no model-authored progress narration;
Discord typing state is host activity. A run-local evidence value records only
typed incomplete-collection reasons and counts. At settlement, the host renders
the closed `answered | partial | needs_input | failed | silent` Main result and
conservatively promotes `answered` or `silent` to a visible partial result when
Calendar evidence is incomplete. It never reparses model prose.

## Action lifecycle

```text
automatic tool call       approval-bearing tool call
        │                           │
        ▼                           ▼
      queued                awaiting_approval
        │                           │
        └──────────────┬────────────┘
                       ▼
                   executing
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
   succeeded         failed          uncertain

queued ─────────────────────────► cancelled
awaiting_approval ──────────────► cancelled
```

`cancelled` prevents any further effect lifecycle. For denied approval it occurs
before binding execution; for a queued schedule it occurs after the durable
creation receipt but before the requested wake runs.

`queued`, `awaiting_approval`, and `executing` are non-terminal. `uncertain` is
terminal for execution and does not prevent a later new action with identical
arguments.

When a terminal outcome cannot return to the still-live originating model loop
(including approval/denial, uncertainty, or crash reconciliation), host code
inserts the idempotent action-resolution message before considering notification
complete. Automatic actions whose result returns as an ordinary live tool
observation do not create a second resolution turn.

Execution claims commit before the effectful binding call. There is no action
lease: one deployment process owns all work. Every execution contract stores a finite
`max_attempts >= 1`. `attempts` increments atomically immediately before actual
effectful binding executor entry and only if capacity remains. A bounded request
timeout and startup scan reconcile any row left `executing` using tool-specific
evidence and bounded provider re-reads. Only proof that the effect did not happen,
a repeat is safe, and lifetime capacity remains can return it to `queued`; the
attempt count records that repeat but never authorizes it. At the ceiling,
proved absence becomes `failed` and unresolved evidence becomes `uncertain`.
`uncertain` is otherwise written only after the complete automatic
reconciliation procedure is exhausted and the evidence still cannot decide; a
timeout alone is insufficient.

Gmail draft-create recovery is the tool-specific no-repeat case. It performs
three fixed observations with `0`, `2`, and `8` second backoffs. Each observation
enumerates at most five unfiltered pages of eight draft IDs, without assuming
listing order, and fetches at most forty unique candidates as bounded raw
messages. A thirty-second whole-procedure deadline, sixteen-MiB aggregate body
budget, and the shared two-MiB per-response cap bound the work. Pagination
evidence records only whether `nextPageToken` was absent, present, invalid, or
unknown. The procedure never sends `q` and never relies on Gmail search indexing.
One observed exact effect header and normalized-content match, with no observed
duplicate or conflict, proves success even when pagination is incomplete. An
observed conflict always settles `uncertain`. Without positive proof, malformed
or incomplete evidence, transient failure, or no match—including after a
complete enumeration—also settles `uncertain`, creates the idempotent host
resolution, and never returns the action to `queued`.

Gmail draft-update recovery normally decides from the known draft. If that draft
has disappeared, it fetches the known thread as minimal metadata and then reads
up to one hundred enumerated messages individually as raw. It assumes no
ordering and performs no mailbox search. One unique effect-header and exact
desired-content match in a fully processed bounded observation proves the
outcome; duplicate, conflicting, malformed, or incompletely processed evidence
does not. The read shape and ceiling are revisioned policy inputs: this provider
correction rotates the binding identity while retaining the unshipped v1 public
tool and implementation revision.

`tool_name`, `arguments`, `execution_contract`, and `origin_message_id` never
change after insertion. V1 tool names have no mandatory version suffix. The
closed host-authored execution contract records the exact tool, policy, plan,
effect/replay declarations, canonical input digest, finite attempt ceiling,
claim ID, through-checkpoint, model-step ordinal, ordered admitted input IDs, and
write-gate supporting owner IDs that occupy the `llm-tools` position. The
executor and approval renderer revalidate both it and the stored arguments. This
is per-effect recovery evidence, not a general version registry. An incompatible
tool change drains or cancels non-terminal actions; a versioned successor is
introduced only when coexistence is required.

## Approval rendering

The model step contains a canonical tool call and arguments only. When policy
requires approval:

1. Resolve the selected declaration and host renderer, and render the exact
   validated arguments before creating durable state.
2. Insert the action and host-owned approval message in one transaction, storing
   the internal message ID as `approval_message_id` and settling the proposing
   turn as a durable user-waiting suspension.
3. At outbox delivery, reload the action, revalidate its immutable arguments and
   execution contract, verify Gmail draft-creation lineage when applicable, and
   reproduce the same host rendering.
4. Attach one UTF-8 text file, bounded to 1,000,000 bytes, whose deterministic JSON
   contains the action ID, canonical tool name, and every validated stored
   argument. It therefore shows all Gmail To/Cc/Bcc recipients, subject, and
   complete body, or the real Calendar, attendees, title, description, location,
   start/end/timezone, recurrence, reminders, and notification choice.
5. Deliver the short identifying message with exactly Approve and Deny. Their
   custom IDs bind the action and internal approval-message IDs.

On a click, the Gateway validates configured owner/guild/channel identity and
parses the closed component ID. The action transaction verifies the Discord
message ID against the stored approval message and atomically moves Approve to
`executing` or Deny to `cancelled`. A public interaction-response edit
acknowledges the click and disables both components before the execution mutex
admits slow work. Duplicate and racing clicks fail the state claim. Free-form
messages never enter this path.

Startup disables a delivered incompatible approval before cancelling and
reporting it. If it was never delivered, startup cancels it and the outbox sends
the unchanged canonical approval message with a complete cancelled-payload
attachment and disabled components before the cancellation resolution. This
keeps the delivery watermark truthful without exposing a functional approval.

There is no model preview field and no stored preview column.

## Calendar effect identity and recovery

`calendar.create_event` derives a provider event ID from the action ID using the
fixed algorithm in SPEC section 7.3. The binding supplies that ID on the first
insert and every reconciliation; the model cannot select it. A timeout or
duplicate response triggers `events.get` for that exact ID. The binding compares
a normalized projection of writable event fields with the stored action
arguments: a match proves success, while a conflict is never overwritten or
blindly retried.

Calendar update and delete already target a provider event ID. Reconciliation
reads that resource: intended state proves success, proved unchanged state may
permit a safe retry, and conflicting or unknowable state exhausts to
`uncertain`.

## Gmail send recovery

Email is prepared as a Gmail draft with a stable `X-Jarvis-Effect-ID` derived
from the draft-creation action ID exactly as specified in SPEC section 5.5.
Gmail owns the RFC `Message-ID`; updates preserve the Jarvis header, and the
separate send action stores it with the `draftId`, thread identity, and exact
recipient/subject/body snapshot before approval. After approval and before
dispatch, the executor fetches the live draft. A mismatch fails without sending
and requires a new proposal. After an ambiguous send:

1. Make three observations separated by fixed `0`, `2`, and `8` second backoffs.
   Inspect the known draft first; an exact unchanged draft is evidence toward
   absence, while changed or malformed state is not.
2. In each observation, fetch the known thread with `format=minimal`, select at
   most one hundred enumerated IDs without assuming ordering, and fetch each
   selected message with `messages.get(format=raw)`. The whole procedure permits
   at most 102 provider reads per observation, sixteen MiB of accepted response
   bodies, the ordinary two-MiB per-response cap, and thirty seconds.
3. Compare each selected message carrying the exact Jarvis effect header with
   the normalized immutable snapshot, excluding only the current live draft's
   message ID. Once every selected bounded message is processed, one unique
   observed exact header-and-content match proves success even when the draft
   remains or the thread has an unprocessed tail beyond one hundred messages.
   No Gmail label is required. Duplicate observed matches or any observed
   conflict do not prove success.
4. Repeat only when all three observations prove that the exact unchanged draft
   remains and the complete thread has no matching non-draft message, repeating
   is safe, and immutable attempt capacity remains. Malformed, transient, partially
   processed, duplicate, or conflicting evidence cannot prove absence.
5. The original send timeout merely starts reconciliation. Expiry of the
   separate thirty-second reconciliation bound exhausts that procedure with
   incomplete evidence; it does not act as proof of absence. A still-undecidable
   completed or elapsed-bound procedure becomes terminal `uncertain`, presents
   only safe evidence, and asks the owner to inspect Gmail.

Qualification validates the exact behavior for new and reply threads. The
bounded raw-message expansion can make an ambiguous send expensive—up to 306
provider reads across three observations—but avoids Gmail search-index
correctness assumptions. A positive match within a fully processed hundred-row
selection remains decisive; absence beyond that ceiling remains unknowable.

## Persistence

PostgreSQL owns exactly:

- `message`
- `memory_log`
- `memory_summary`
- `action`
- `model_decision`
- `read_position`

Existing integration state stays with its current owner. Configuration owns the
owner ID, Discord guild and channel IDs, timezone, paused flag, model
configuration, and credential locations. A private runtime-state file owns the
non-canonical main session reference and immutable agent-definition fingerprint
behind Jarvis's `SessionRefPort` adapter. A separate atomically replaced,
content-free private journal owns the rolling cognitive-admission window. A
reservation records run/root IDs, windows, counters, timestamps,
reserved/actual capacity, and state but no user payload. Clean exit refunds
unused capacity. Startup under the deployment lock marks orphaned reservations
interrupted and releases the live slot while retaining turn/token charge until
window expiry. The six-hour production ceiling holds two complete foreground
envelopes plus one Rememberer allowance while retaining one-live-root serial
execution. Missing, incompatible, or corrupt admission state fails closed
pending explicit operator reset. Alembic may own its bookkeeping table.

## Provider containment

Codex cognition runs under the exact policy in [SPEC section 7.5](../SPEC.md#75-codex-containment):
the real `AgentRuntime` lane attached to the Personal host-owned App Server over
WebSocket on a Unix socket, `JsonSchemaAgentOutput`, an empty non-secret
group-readable/traversable asserted-empty read-only cwd, no additional directories, network, or MCP,
deny-mode approval, disabled native built-ins and Web, and no connector, Brave,
or embedding credentials. The compatibility API's `allowed_tools=("*",)` sentinel is
not authority.

The kernel prepends its qualified contained-structured-agent base instruction
to every provider request and fingerprints its identity. Jarvis separately
bounds the combined kernel and application system material. This instruction is
defense in depth, not the authority boundary.

The confined Codex child still has no native network or Web search. A structured
`web.search` or `web.read` request returns to the Jarvis host, which applies the
frozen capability plan and dispatches the bounded `llm-tools` binding outside
the child through `llm-agent-kernel`.

The application consumes normalized provider events:

- Production drives `AgentRuntime.stream_turn`; the terminal-only `run_turn`
  convenience projection is forbidden because it discards these events.
- Only the provider's audited bounded/redacted inert lifecycle, reasoning,
  warning, status, and planning whitelist survives as `AgentNative`.
- Command, file, MCP, custom/dynamic, collaboration, Web, image, sleep, and hook
  activity becomes `AgentToolUse`; permission and elicitation requests are
  denied and become `AgentPermissionRequest`.
- Any authority event, unknown request/item/notification, identity mismatch, or
  terminal after authority activity fails the confined turn.
- A failed session is discarded and no terminal is returned to the Jarvis loop.
- Streaming text is not delivered; only a validated terminal structured step
  from a fully inspected clean stream crosses into Jarvis.

An attempted native tool can therefore fail a turn even when the sandbox denied
its effect. The event is the drift signal; containment is the sandbox and process
boundary. Code Mode is contained/detected rather than asserted impossible before
its first observable event. Protocol drift intentionally becomes an availability
failure. Jarvis turns that failure into host-owned visible text and never accepts
the model terminal.

Production environment files are root-owned mode 0600. systemd reads them for
the Jarvis host; the `jarvis` identity cannot read them directly. Jarvis becomes
non-dumpable before opening a provider connection and systemd exposes only a
ptraceable `/proc` subset. The shared development-UID App Server retains its
profile's Codex login. A dedicated local group grants Jarvis only socket access
and grants the server traversal of empty cognition directories, never Jarvis
application state. Read-only provider containment alone is not a general
host-confidentiality boundary.

## peer agent control

main uses nine owner-directed tools: `agent.list`, `agent.info`, `agent.start`,
`agent.read`, `agent.send`, `agent.text`, `agent.keys`, `agent.stop`, and
`agent.close`. [adr 0052](decisions/0052-cut-worker-control-to-current-skid.md)
owns the current contract; adr 0044's provider/authority boundaries remain.

`agent_control.py` invokes one fixed skid cli with a private peer configuration,
bounded pipes and explicit argv. skid owns opaque refs, gateway routing,
provider methods and live target validation. jarvis projects consumed results
into `agent_tools.py`; it neither decodes refs nor repeats the provider codec.
the installed cli is root-owned, separate from the development user's home.

terminal authority addresses an exact tmux/process lifetime. conversation
authority addresses the captured provider conversation and, for native stop,
its captured turn. `info` explicitly selects either target. native write previews
inspect the original conversation even after terminal reassociation or deletion;
a terminal name can ground that preview only when it still tracks the same
conversation. a fresh observation never replaces a pending action's ref. native
unavailability refuses native input; explicit terminal input remains a separate
capability. compound close reports native halt and exact terminal closure
separately.

reads retain the durable recorder; writes remain billed-once with one executor
entry and no retry. preflight or spawn refusal is not-sent. after possible
dispatch, lost or malformed replies settle uncertain. valid receipts preserve
partial creation, unknown write outcomes and partial fleet inventory. native
acceptance and terminal dispatch do not establish task completion. subprocess
stdout is capped at 1 mib for inventory and 64 kib otherwise; stderr goes
directly to the null device. a valid owned stdout receipt survives early stdin
closure or delayed process exit. existing tool budgets cover preflight calls.

finalized old worker actions are opaque archives before current tool lookup or
receipt decoding. common immutable record invariants still apply; raw arguments
and results remain stored. current malformed receipts are defects. old unfinished
actions block activation. no historical worker reader, execution adapter, worker
table, scheduler, transcript copy or reference cache remains. worker control is
independent of jarvis's shared cognitive app-server contract.

## Scheduling

No workflow framework exists. The kernel's bounded in-process drain does not
persist a workflow graph, own product state, or wait durably for approvals.

- A small timer selects queued `schedule.wake` action rows whose `execute_after`
  is due.
- A schedule-create binding atomically stores an immutable `creation_receipt` in
  `result` while leaving product status queued. The action-backed `llm-tools`
  recorder replays that receipt for the original occupied tool position
  regardless of later wake status. A queued schedule with no valid receipt is
  reconciled and never fires.
- A requested wake becomes eligible at its stored instant, or on startup when
  that instant passed during downtime; no generic quiet-hours transform exists.
- Claiming a due wake atomically marks it `executing` and inserts one idempotent
  host waking message keyed by `(message.source = schedule_wake, action.id)`,
  rendered from the immutable stored instruction and requested instant. The
  proactive run or its
  deterministic visible fallback processes that row and marks the action
  `succeeded` in one transaction, adding closed
  `wake_outcome.concluded(conclusion_message_id, recorded_at)` without replacing
  the creation receipt. Cancellation and local failure use the other closed
  outcome variants and matching statuses; schedule lifecycle never becomes
  uncertain.
- Cancelling creates a separate gated action with its own position, finite
  attempt ceiling, and receipt. Its transaction succeeds that cancel action,
  changes only a queued original to `cancelled`, and records cancellation in the
  original's `wake_outcome`.
- No periodic connector tick or autonomous inbox/calendar monitor starts turns.
- A timer may invoke dreaming when the execution mutex is idle.
- Startup reconciles every action left `executing`; ordinary external calls use
  bounded timeouts while the process is alive.

Each path is an ordinary function over explicit database state.

## Failure behavior

- Recaller failure: continue without recalled memory.
- Main-agent failure: report a concise host-authored error and discard the
  failed session through `provider-runtime`. Only a missing, incompatible, or
  unresumable reference during continuing-session acquisition permits the one
  safe cold bootstrap; a provider failure after a turn starts does not.
- Protocol, run-budget, subscription-quota, explicit-stop, or repeated-provider
  exhaustion: persist a host-authored stopped conclusion and consume the input;
  never automatically rearm it.
- Process interruption: leave canonical input visible, increment its attempt on
  an admitted reclaim, and stop before provider I/O once the ceiling is exceeded.
- Configuration, plan-budget, checkpoint, or admission-journal defect: stamp
  the claimed batch's durable park, open the cognitive circuit, and fail closed
  for explicit operator correction and release.
- Admission capacity denial: leave owner/action-resolution input unprocessed and
  automatically rescan at the declared reset instant; for delays of at least 60
  seconds, insert one deterministic host-rendered assistant notice. Background
  memory work defers silently.
- Rememberer failure: leave `remembered_at` null and retry later.
- Dreamer failure: retain raw memory and existing summaries.
- Embedding failure: leave the vector null; lexical recall continues.
- Discord delivery failure: retain the assistant row with null
  `source_message_id`; retry with the same enforced nonce under the finite
  Slice 1 retry/backoff policy. A delayed recovery may rarely repeat ordinary
  text but cannot duplicate an action effect.
- Approval-rendering failure: create no functional Approve component.
- Approval decision committed but acknowledgement interrupted: leave the action
  durable, disable the known components during startup recovery, then resume or
  reconcile without replaying the originating model turn.
- Interrupted turn with no effect: replay; interrupted turn with an originating
  action: resume/reconcile without model replay.
- Action left `executing`: reconcile before any repeat.
- External outcome still unprovable after complete automatic reconciliation:
  record terminal `uncertain`, present the evidence, and ask the owner to inspect
  provider state.

## Inspection

A message trace should make this path reconstructable without storing private
payloads in ordinary logs:

```text
owner message
→ recalled candidate IDs
→ selected memory IDs
→ appended memory IDs
→ run ID, provider trace IDs, turns/tokens, duration, outcome
```

The bounded trace lives on every waking row consumed by a settlement. Each gets
the same run/checkpoint/conclusion identity plus only relevant IDs and counters.
Action rows carry correctness-critical claim/checkpoint/input/step lineage in
their immutable execution contract; `origin_message_id` is only the stable root
pointer. Private payloads and model prose are not duplicated into trace. Trace
details are implementation diagnostics and rememberer-group reconstruction,
never a memory-ranking signal in v1.


## Shared-kernel durable recovery

[ADR 0040](decisions/0040-shared-kernel-durable-decisions.md) adds two narrowly
owned records: `model_decision` preserves exact paid inference and host validation
evidence; `read_position` implements the existing llm-tools recorder for Reads.
Main and every recoverable isolated role use stable original work identities.
Unknown dispatch stops automatic retry. The original Write action remains the
sole effect owner and is recovered before any model decision can replay.

Every store in production uses the same dedicated deployment-lock connection for
short serialized transactions. Losing it blocks inference admission, read dispatch,
action acceptance, memory mutation, and result publication; it never reconnects.
The exact authenticated catalog selection is frozen into role definitions and
therefore session fingerprints. Application prompts remain application-owned;
the shared containment instruction remains owned by llm-agent-kernel.

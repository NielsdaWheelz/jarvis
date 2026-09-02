# V1 architecture

This document expands [SPEC.md](../SPEC.md). `SPEC.md` wins if they disagree.

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
               say / finish                    Jarvis policy
                    │                                 │
                    ▼                                 ▼
          message / Discord                        llm-tools
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

`llm-agent-kernel` is a pinned independent library, not another service or
state owner. It supplies contained Codex session choreography, strict serial
protocol, mid-loop polling, settlement, and bounded run machinery.
`provider-runtime` remains the provider/session implementation and `llm-tools`
remains the prompt-section, contract, grant, validation, and tool-execution
implementation. Jarvis owns every product and persistence adapter.

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
- Atomically claims or denies component interactions, then immediately
  acknowledges them and disables their components before external work.
- Prevents model tools from editing host-owned approval messages.
- Exposes no model-callable Discord tools. Ingress, `say` delivery, typing state,
  host approval presentation, and editing Jarvis's own approval message are
  adapter operations.

The adapter renders model output as ordinary text/Markdown. It may render links,
but the bot lacks `EMBED_LINKS`, so Discord does not automatically unfurl them.
Gateway ingress, typing, and component interactions use `discord.py`. Outbound
Create Message uses a narrow host-owned Discord REST v10 `httpx` binding because
the qualified `discord.py` 2.7.1 send API does not expose `enforce_nonce`; no
private library API is used.

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
validated say or host-rendered response
→ insert assistant message with source_message_id null
→ derive deterministic nonce from message.id
→ reconcile delayed retry through bounded Discord history when required
→ create with the same nonce and enforce_nonce=true
→ store Discord message ID as source_message_id
```

On startup, the adapter retries assistant messages whose `source_message_id` is
null. A normal retry reuses the same enforced nonce. A delayed retry first reads
history after the nearest known preceding Discord ID and adopts a matching bot
message. With no anchor it scans backward to the pending row's creation time.
An interval that cannot be checked completely leaves the row pending rather than
risking a duplicate outside Discord's recent nonce window. The nonce is derived
from the internal message ID and requires no durable field.

Approval messages follow the same persistence rule. The action's
`approval_message_id` references the internal message row; that row acquires the
Discord delivery ID. A component interaction must match both.

## Turn coordinator

For each owner message:

1. Check the paused flag.
2. Persist/deduplicate the inbound message.
3. Acquire the in-process provider mutex.
4. Claim one non-empty bounded compatible batch, increment its durable
   `processing_attempts`, choose its frozen plan, and obtain rolling admission.
5. Snapshot one host `as_of` instant and run the recaller in a fresh isolated
   read-only kernel one-shot run.
6. Through the context adapter, select canonical product context and give the
   kernel a provider-neutral continuation or bootstrap package.
7. The kernel opens/resumes the real contained `AgentRuntime` session and runs
   its bounded serial loop. It polls for compatible owner input before provider
   and tool boundaries and for stop/preemption before settlement.
8. Through the checkpoint adapter, atomically persist the conclusion, set
   consumed waking rows' `processed_at`, and report whether later input remains.
   Ordinary later input runs after commit; cleanup never rearms by itself.
9. Settle admission usage, deliver pending responses, and release the provider
   mutex.
10. Run the rememberer later through a fresh admitted isolated kernel run,
    yielding to new owner work.

A turn is eligible for remembering after `say`, `finish`, or creation of an
action awaiting approval. This includes a turn whose visible response is a
host-rendered approval message rather than model-authored prose.

At startup, a waking owner or host row with null `processed_at` is an interrupted
turn. A host action-resolution row is safe to replay. If an owner row has no
originating action, it may be reclaimed only within its durable attempt ceiling
and rolling admission. If it already produced an action, the host resumes or
reconciles the action, persists an interruption notice, and closes the turn
without replaying the model. Protocol/budget/quota/stop poison exits persist a
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
the main model finishes silently or fails before `say`, Jarvis finalization
persists a deterministic assistant fallback from the host row's safe fields and
processes both together. The fallback for uncertainty includes reconciliation
evidence; the fallback for a wake includes the stored reminder instruction.

The application holds one PostgreSQL advisory lock for deployment ownership. A
second Jarvis instance refuses to start. Because only one process runs, turn and
provider scheduling inside that process use ordinary locks and queues rather
than additional database workflow machinery.

The exclusive claim, ordered bounded waking batch, opaque consumed watermark,
poll, and atomic terminal checkpoint implement the kernel
`InputCheckpointPort` over `message`. `processing_attempts` is the one new
column needed to bound recovery across process crashes. Owner and
action-resolution work receives the full plan and outranks a scheduled wake;
the latter is claimed separately under the read-only plan. Incompatible input
remains unclaimed. Idempotent cleanup releases ownership without scheduling a
successor. Null `processed_at` plus startup/recovery scanning remains the durable
work signal.

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
inputs; selection code does not construct Codex SDK message objects.

The configured Discord channel owns one main Codex session. Its
`AgentSessionRef` and immutable agent-definition fingerprint live in an
atomically replaced private runtime-state file, not PostgreSQL, behind Jarvis's
kernel `SessionRefPort` adapter. The fingerprint covers stable instructions,
model and reasoning configuration, output contract, credential-profile identity,
kernel/runtime revisions, cwd/directories/MCP configuration,
`PermissionPolicy`, native options, and the session capability envelope; secret
bytes and per-run subset plans do not rotate the session.
An ordinary restart or compatible deployment
attempts resume through `provider-runtime`. A fingerprint mismatch, invalid
reference, or resume failure discards the reference and opens a fresh session.
References are scoped by application thread and fingerprint; a generation
compare-and-set prevents a stale run from overwriting a newer reference.
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

Recaller, rememberer, and dreamer calls always open fresh isolated sessions.
Their agent definitions use kernel `SessionMode.isolated`; they never load or
save a session reference or reuse the main session or each other's history, and
their frozen plans contain no `ToolEffect.Write`. The main definition uses
`SessionMode.continuing`. Source-message timestamps remain attached to their
content. Each fresh session receives the timezone once; each newly admitted
input batch or background job receives one host-supplied `as_of`. A compatible
batch appended mid-loop receives its own; tool-only continuations and embedding
requests receive no repeated clock.

Session history, native compaction, and cache behavior are disposable
optimizations. A cold bootstrap need not recreate provider reasoning or
compaction byte-for-byte; it must restore useful conversational continuity from
canonical messages plus recall.

Checkpoint finalization maps the terminal conversational conclusion and
consumed-input checkpoint into the same Jarvis transaction. Read observations
and protocol correction remain turn-local; effectful outcomes are already
durable in `action` through its `llm-tools` position/recorder mapping. The kernel `EventSinkPort` is optional
best-effort observability, not a canonical event store. Emission is attempted
before reuse but failure is nonfatal. Exact provider requests and normalized
events remain provider/runtime audit data; Jarvis stores bounded run IDs,
provider trace IDs, turns, available token usage, duration, and outcome in
`message.trace`, not another event table. An atomically replaced content-free
runtime journal enforces the rolling admission window for every cognitive role
and fails closed if corrupt.

## Cognitive roles

These are four immutable kernel agent definitions, not a general subagent or
persistent-peer system. The main role is a continuing thread run with a
conversational output contract and a maximum envelope equal to the exact main
catalog. Recaller, rememberer, and dreamer are fixed isolated one-shot runs with
memory-read envelopes and closed structured output contracts. Jarvis supplies a
frozen subset plan per run; owner/action-resolution runs use the full Main plan
and scheduled-wake runs narrow the same continuing definition to external
reads. One-shot plans contain no `ToolEffect.Write`. One-shot runs use no
application checkpoint or saved session-reference port; host code commits or
recomputes their results.

### Recaller

The recaller opens a fresh session and receives the owner input, bounded recent
context, owner timezone, and the turn's `as_of`. Its frozen capability plan
contains only memory search and memory open. It may issue several queries and
returns a schema-valid `finish.result` bundle of raw memories and summaries, or
an explicit empty bundle.

### Main agent

The main agent normally continues the channel's existing session. It receives
fresh recalled memory on owner turns and the capability descriptions exposed
for every turn. It emits the strict step grammar defined once in
[SPEC section 7.4](../SPEC.md#74-model-step-protocol-and-bounded-drain).

The main agent never owns credentials or policy classification. Host code
supplies product dispatch and policy. The kernel validates the whole step and
the pure `llm-tools` seam validates its one proposed call before dispatch. Calls
execute serially. `call_tool` carries no user-facing text; after the model
observes the bounded result, it may issue a separate truthful `say`.

### Rememberer

The rememberer opens a fresh session and receives the persisted completed turn,
material tool observations, source timestamps, and relevant existing memory. It
can search/open memory and returns a schema-valid `finish.result` list of zero or
more raw memory strings.

Host code performs one transaction that:

- Appends the new `memory_log` rows.
- Sets `remembered_at` on the triggering owner message.

The rememberer does not call a memory write tool and creates no action rows. A
failed or cancelled run leaves `remembered_at` null for a bounded retry sweep.

### Dreamer

The dreamer opens a fresh session, searches and opens memory, then returns a
schema-valid `finish.result` batch of summary insertions and removals. Host code
applies the batch transactionally.

Only one dreamer runs at once. It yields the provider mutex when owner input is
waiting. Missing a dream run cannot break conversational correctness because raw
memory remains directly searchable.

## Tool execution

The complete tool manifest and authority classification live in
[SPEC section 7.3](../SPEC.md#73-tool-contracts-and-exact-catalog). Jarvis owns the
Gmail, Calendar, Maps, schedule, and memory declarations and bindings. The pinned
`llm-tools` revision owns the reusable `web.search` and `web.read` declarations
and implementations; Jarvis explicitly composes, configures, and grants them.
Discord is the conversation adapter and has no model-callable declarations.

Capability plans are closed by role:

- Main: the catalogued Gmail, Calendar, Maps, Web, and `schedule_wake` tools.
- Recaller, rememberer, and dreamer: `memory.search` and `memory.open` only.

There are no local-filesystem, Gmail organization, progressive-discovery, or
Discord tools in a v1 capability plan.

The host:

- Freezes a capability plan for each cognitive role and turn.
- Supplies that plan and its product dispatch adapter to `llm-agent-kernel`.
- Uses the qualified pure `llm-tools` seam to validate canonical tool IDs and
  closed arguments before dispatch-side mutation.
- Classifies calls using the fixed automatic/approval policy.
- Owns connector credentials.
- Executes reads through `llm-tools` without action rows.
- Inserts an `action` before every effectful tool call.
- Supplies the action ID as both durable `InvocationPosition` and `EffectId`.
- Returns one bounded completed `ToolResult` or one durable suspension through
  the kernel dispatch port.

Canonical message persistence, raw-memory append, and summary replacement are
application transactions. They are not model tools and do not pass through
`llm-tools`; terminal conversation persistence is exposed to the agent kernel
only through Jarvis's checkpoint adapter.

## Kernel protocol and drain

`llm-agent-kernel` parses exactly `say`, `call_tool`, or `finish`. A
`call_tool` contains one canonical ID and arguments and no prose, preview,
authority, approval instruction, or model-authored call/effect ID. Unknown
fields fail. `provider-runtime` first enforces the declared JSON schema; the
kernel then validates the complete semantic step, output contract, frozen plan,
and pure arguments before any display, recorder mutation, budget reservation,
or dispatch. Protocol-invalid output executes nothing and receives only bounded
corrective context.

Calls execute one at a time. A bounded completed observation returns to the
next provider turn, and only a later `say` can describe its actual outcome. A
durably accepted approval or reconciliation need returns `suspended(host_ref,
waiting_for)`, settles the proposing input, and releases live resources. A
later action-resolution host row contains the action ID, tool, original
validated arguments, state, and safe evidence. Jarvis action semantics—not the
kernel—interpret approved, denied, failed, or terminal uncertain outcomes.

`KernelLimits` own provider turns, protocol repairs, wall time, normalized
provider usage, and cumulative model-visible context. `llm_tools.RunLimits`
alone own tool calls, attempts, bytes, `max_in_flight = 1`, and tool elapsed
limits. V1 has no parallel or multi-call path and no model-authored progress
narration; Discord typing state is host activity.

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

`cancelled` terminates an action before execution, whether the owner denied an
approval or cancelled queued scheduled work.

`queued`, `awaiting_approval`, and `executing` are non-terminal. `uncertain` is
terminal for execution and does not prevent a later new action with identical
arguments.

When a terminal outcome cannot return to the still-live originating model loop
(including approval/denial, uncertainty, or crash reconciliation), host code
inserts the idempotent action-resolution message before considering notification
complete. Automatic actions whose result returns as an ordinary live tool
observation do not create a second resolution turn.

Execution claims commit before the external call. There is no action lease: one
deployment process owns all work. `attempts` increments atomically immediately
before actual executor entry. A bounded request timeout and startup scan
reconcile any row left `executing` using tool-specific evidence and bounded
provider re-reads. Only proof that the effect did not happen and a repeat is safe
can return it to `queued`; the attempt count records that repeat but never
authorizes it. `uncertain` is written only after the complete automatic
reconciliation procedure is exhausted and the evidence still cannot decide; a
timeout alone is insufficient.

`tool_name`, `arguments`, `execution_contract`, and `origin_message_id` never
change after insertion. V1 tool names have no mandatory version suffix. The
closed host-authored execution contract records the exact tool, policy, plan,
effect/replay declarations, and canonical input digest that occupy the
`llm-tools` position. The executor and approval renderer revalidate both it and
the stored arguments. This is per-effect recovery evidence, not a general
version registry. An incompatible tool change drains or cancels non-terminal
actions; a versioned successor is introduced only when coexistence is required.

## Approval rendering

The model step contains a canonical tool call and arguments only. When policy
requires approval:

1. Insert the action and host-owned approval message in one transaction.
2. Store the internal message ID as `approval_message_id`.
3. Load the action's immutable validated arguments.
4. Resolve the current declaration, revalidate the stored arguments and
   execution contract, and select the host renderer for `tool_name`.
5. Render every recipient, audience, and transmitted value.
6. Deliver the pending message with Approve and Deny.

For content exceeding one Discord message, the renderer may split the material
or attach a host-generated text file. The final component-bearing message states
that the entire preceding payload is what Approve executes.

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

Email is prepared as a Gmail draft. Its `draftId`, thread identity, and exact
recipient/subject/body snapshot are stored before approval. After approval and
before dispatch, the executor fetches the live draft. A mismatch fails without
sending and requires a new proposal. After an ambiguous send:

1. Check whether the draft still exists.
2. If absent, inspect Sent mail using the available thread, recipients, subject,
   and provider response evidence.
3. Perform the binding's bounded re-read sequence before deciding.
4. Repeat only when evidence proves the send did not occur and repeating is safe.
5. Otherwise record terminal `uncertain`, present the evidence, and ask the owner
   to inspect Gmail.

Slice 0 validates the exact behavior of the existing Gmail integration for new
and reply threads.

## Persistence

PostgreSQL owns exactly:

- `message`
- `memory_log`
- `memory_summary`
- `action`

Existing integration state stays with its current owner. Configuration owns the
owner ID, Discord guild and channel IDs, timezone, paused flag, model
configuration, and credential locations. A private runtime-state file owns the
non-canonical main session reference and immutable agent-definition fingerprint
behind Jarvis's `SessionRefPort` adapter. A separate atomically replaced,
content-free private journal owns the rolling cognitive-admission window. A
missing or corrupt admission journal fails closed pending explicit operator
reset. Alembic may own its bookkeeping table.

## Provider containment

Codex runs under the exact policy in [SPEC section 7.5](../SPEC.md#75-codex-containment):
the real `AgentRuntime` lane with `JsonSchemaAgentOutput`, a private empty
read-only cwd, no additional directories, network, copied environment, or MCP,
deny-mode approval, disabled native built-ins and Web, and no connector, Brave,
or embedding credentials. The SDK-required `allowed_tools=("*",)` sentinel is
not authority.

The confined Codex child still has no native network or Web search. A structured
`web.search` or `web.read` request returns to the Jarvis host, which applies the
frozen capability plan and dispatches the bounded `llm-tools` binding outside
the child through `llm-agent-kernel`.

The application consumes normalized provider events:

- Normal lifecycle, reasoning, warning, and planning passthrough events do not
  fail a turn.
- Any `AgentToolUse` or `AgentPermissionRequest` fails the confined turn.
- A failed session is discarded.
- Streaming text is not delivered; only a validated terminal structured step
  crosses into Jarvis.

An attempted native tool can therefore fail a turn even when the sandbox denied
its effect. The event is the drift signal; containment is the sandbox and process
boundary.

## Scheduling

No workflow framework exists. The kernel's bounded in-process drain does not
persist a workflow graph, own product state, or wait durably for approvals.

- A small timer selects queued `schedule_wake` rows whose `execute_after` is due.
- A requested wake becomes eligible at its stored instant, or on startup when
  that instant passed during downtime; no generic quiet-hours transform exists.
- Claiming a due wake atomically marks it `executing` and inserts one idempotent
  host waking message keyed by `(schedule_wake, action.id)`, rendered from the
  immutable stored instruction and requested instant. The proactive run or its
  deterministic visible fallback processes that row and marks the action
  `succeeded` in one transaction.
- No periodic connector tick or autonomous inbox/calendar monitor starts turns.
- A timer may invoke dreaming when the provider mutex is idle.
- Startup reconciles every action left `executing`; ordinary external calls use
  bounded timeouts while the process is alive.

Each path is an ordinary function over explicit database state.

## Failure behavior

- Recaller failure: continue without recalled memory.
- Main-agent failure: report a concise host-authored error; discard the failed
  session through `provider-runtime` and let the kernel cold-bootstrap at most
  once before a successful terminal and never after a host effect dispatch.
- Protocol, run-budget, subscription-quota, explicit-stop, or repeated-provider
  exhaustion: persist a host-authored stopped conclusion and consume the input;
  never automatically rearm it.
- Process interruption: leave canonical input visible, increment its attempt on
  an admitted reclaim, and stop before provider I/O once the ceiling is exceeded.
- Configuration or admission-journal defect: park input and fail closed for
  operator correction.
- Rememberer failure: leave `remembered_at` null and retry later.
- Dreamer failure: retain raw memory and existing summaries.
- Embedding failure: leave the vector null; lexical recall continues.
- Discord delivery failure: retain the assistant row with null
  `source_message_id`; retry with the same enforced nonce, using history
  reconciliation first when the recent nonce window may have elapsed.
- Approval-rendering failure: create no functional Approve component.
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

The bounded trace lives on the originating message and contains only those IDs
and counters.
Action rows already carry tool and outcome lineage through `origin_message_id`;
private payloads and model prose are not duplicated into trace. Trace details are
implementation diagnostics, never a memory-ranking signal in v1.

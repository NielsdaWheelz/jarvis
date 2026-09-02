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
                         bounded run + exclusive drain
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
      provider-runtime / Codex                 call_tools dispatch
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
state owner. It supplies the reusable protocol and bounded run/drain machinery.
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
4. Snapshot one host `as_of` instant and run the recaller in a fresh isolated
   read-only kernel one-shot run.
5. Through the Jarvis context adapter, select canonical product context and give
   the kernel a provider-neutral continuation or bootstrap package.
6. The kernel continues the healthy main session, asks `provider-runtime` to
   resume a compatible reference, or opens a fresh session, then runs the
   bounded whole-step loop.
7. Through Jarvis's checkpoint adapter, settle the consumed watermark: in one
   transaction persist the durable conclusion, set each consumed waking
   message's `processed_at`, and test for newer input. Settlement returns
   continue, idle, or deferred. A later same-class input may continue the drain.
   A different-class input, or exhausted limits, makes the adapter arm the
   correct next run before releasing ownership; the public outcome is
   `pending_input`.
8. Deliver any pending response and release the provider mutex after the drain
   settles.
9. Run the rememberer in the background through a fresh isolated kernel run,
    yielding to new owner work.

A turn is eligible for remembering after `say`, `finish`, or creation of an
action awaiting approval. This includes a turn whose visible response is a
host-rendered approval message rather than model-authored prose.

At startup, a waking owner or host row with null `processed_at` is an interrupted
turn. A host action-resolution row is safe to replay. If an owner row has no
originating action, it may also be replayed. If it already produced an action,
the host resumes or reconciles the action, persists an interruption notice, and
closes the turn without replaying the model. This is the turn-level duplicate
effect barrier.

An action outcome that cannot return to its still-live originating model loop
idempotently inserts one host-authored waking `message` keyed by
`(source = action, source_message_id = action.id + ":" + status)`. It carries the
action ID, tool, resolved state, and safe normalized result. A later evidence-
based transition from `uncertain` to `succeeded` or `failed` therefore earns a
new resolution row rather than rewriting history. The main drain processes it
through the same checkpoint path and may explain the outcome naturally; it never
reuses the original turn-local call ID. Startup repairs a missing required
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

The exclusive-drain claim, ordered waking snapshot, opaque consumed watermark,
atomic terminal checkpoint, and compare-and-set idle behavior implement the
kernel `InputCheckpointPort` over existing `message` state. They add no table or
column. The adapter derives `interactive` for owner and action-resolution rows
and `proactive-read` for scheduled-wake rows, binds each class to its frozen
plan, and exposes only the maximal contiguous prefix of one class. An initial
class mismatch or a newer different-class row arms the correct run before
declining or releasing the claim, even when budget remains. Idempotent
error/cancellation release arms recovery before relinquishing any still-
unprocessed row. Null `processed_at` remains the restart-recovery signal.

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
model and reasoning configuration, kernel/runtime revisions, containment, and
the session capability envelope; per-run subset plans do not rotate the session.
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
their frozen plans contain only non-effectful memory reads. The main definition
uses `SessionMode.continuing`. Source-message timestamps remain
attached to their content. Each fresh session receives the timezone once; each
claimed owner-input batch or background job receives exactly one host-supplied
`as_of`, reused unchanged through its tool loop. Embedding requests receive no
clock.

Session history, native compaction, and cache behavior are disposable
optimizations. A cold bootstrap need not recreate provider reasoning or
compaction byte-for-byte; it must restore useful conversational continuity from
canonical messages plus recall.

Checkpoint finalization maps the terminal conversational conclusion and
consumed-input checkpoint into the same Jarvis transaction. Read observations
and protocol correction remain turn-local; effectful outcomes are already
durable in `action` and through `llm-tools`. The kernel `EventSinkPort` is optional
best-effort observability, not a canonical event store. Emission is attempted
before reuse but failure is nonfatal. Exact provider requests and normalized
events remain provider/runtime audit data; Jarvis stores only bounded provider
trace IDs in `message.trace`, not another event table.

## Cognitive roles

These are four immutable kernel agent definitions, not a general subagent or
persistent-peer system. The main role is a continuing thread run with a
conversational output contract and a maximum envelope equal to the exact main
catalog. Recaller, rememberer, and dreamer are fixed isolated one-shot runs with
memory-read envelopes and closed structured output contracts. Jarvis supplies a
frozen subset plan per run; `interactive` owner/action-resolution runs use the
full Main plan and `proactive-read` scheduled-wake runs narrow the same
continuing definition to external reads. One-shot plans are read-only. One-shot
runs use no application checkpoint or saved session-reference port; host code
commits or recomputes their results.

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
`llm-tools` validates every call before any call dispatches. Independently
classified reads may run concurrently within the turn budget; effectful calls
run in order and a stopping outcome prevents later calls from starting.
`call_tools` carries no user-facing text; after the model observes correlated
outcomes, it may issue a separate truthful `say`.

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
- Uses `llm-tools` to validate canonical tool IDs and closed arguments.
- Classifies calls using the fixed automatic/approval policy.
- Owns connector credentials.
- Executes reads through `llm-tools` without action rows.
- Inserts an `action` before every effectful tool call.
- Supplies the action ID as the durable effect identity.
- Returns typed observations through the kernel dispatch port, correlated by
  turn-local `call_id`.

Canonical message persistence, raw-memory append, and summary replacement are
application transactions. They are not model tools and do not pass through
`llm-tools`; terminal conversation persistence is exposed to the agent kernel
only through Jarvis's checkpoint adapter.

## Kernel protocol and drain

`llm-agent-kernel` parses exactly `say`, `call_tools`, or `finish`. Unknown
fields fail. It validates the entire response and every call before any
dispatch, so a malformed later call cannot leave an earlier partial effect.
Protocol-invalid output executes nothing and returns bounded corrective context.
This is atomic validation, not a claim that separately committed external
effects form one transaction.

`call_tools` carries no user-facing text. Tool observations are correlated by
unique turn-local call IDs, and only a later `say` can describe their actual
outcomes to the owner. The kernel loops only within configured model-step,
tool-call, wall-time, and usage budgets.

Jarvis's dispatch adapter returns `executed`, `pending_approval`, `denied`,
`failed`, or `uncertain`; the kernel never chooses authority. A
`pending_approval` or `uncertain` outcome settles the proposing input with a
host-referenced waiting conclusion. A terminal action later creates an
idempotent host-authored action-resolution message and a new input batch.
Approval, execution, and reconciliation remain host-owned action behavior.

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
deployment process owns all work. A bounded request timeout and startup scan
reconcile any row left `executing` using tool-specific evidence and bounded
provider re-reads. Only proof that the effect did not happen and a repeat is safe
can return it to `queued`. `uncertain` is written only after the complete
automatic reconciliation procedure is exhausted and the evidence still cannot
decide; a timeout alone is insufficient.

`tool_name`, `arguments`, and `origin_message_id` never change after insertion.
V1 tool names have no mandatory version suffix. The executor and approval
renderer both resolve the current declaration and revalidate the same stored
arguments, so no input digest or parallel contract revision record is needed.
An incompatible tool change drains or cancels non-terminal actions before
deployment; a versioned successor is introduced only when coexistence is
actually required.

## Approval rendering

The model step contains a canonical tool call and arguments only. When policy
requires approval:

1. Insert the action and host-owned approval message in one transaction.
2. Store the internal message ID as `approval_message_id`.
3. Load the action's immutable validated arguments.
4. Resolve the current declaration, revalidate the stored arguments, and select
   the host renderer for `tool_name`.
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
behind Jarvis's `SessionRefPort` adapter. Alembic may own its bookkeeping table.

## Provider containment

Codex runs under the exact policy in [SPEC section 7.5](../SPEC.md#75-codex-containment):
empty read-only working directory, no network, deny-mode approval, disabled native
feature set, no MCP, and no connector, Brave, or embedding credentials.

The confined Codex child still has no native network or Web search. A structured
`web.search` or `web.read` request returns to the Jarvis host, which applies the
frozen capability plan and dispatches the bounded `llm-tools` binding outside
the child through `llm-agent-kernel`.

The application consumes normalized provider events:

- Normal lifecycle, reasoning, warning, and planning passthrough events do not
  fail a turn.
- Any `AgentToolUse` fails the confined turn.
- A permission request fails closed.
- A failed session is discarded.

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
  session through `provider-runtime` and let the kernel retry at most once from a
  canonical context bootstrap, never after an effect completed.
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
→ provider trace IDs
```

The bounded trace lives on the owner message and contains only those identifiers.
Action rows already carry tool and outcome lineage through `origin_message_id`;
private payloads and model prose are not duplicated into trace. Trace details are
implementation diagnostics, never a memory-ranking signal in v1.

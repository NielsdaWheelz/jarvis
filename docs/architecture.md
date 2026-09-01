# V1 architecture

This document expands [SPEC.md](../SPEC.md). `SPEC.md` wins if they disagree.

## System shape

```text
dedicated Discord server
          │
          ▼
 Discord adapter ───────────────► message
          │
          ▼
      recaller ─────────────────► memory search/open
          │
          ▼
  main Codex agent
          │
          ├── say / finish
          │
          └── call_tool ────────► host policy + llm-tools
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
                   queued action               awaiting approval
                         │                             │
                         ▼                             ▼
                     executing                host-rendered preview
                         │                             │
                         ▼                       Approve / Deny
                 existing integration                 │
                                                      ▼
                                                  executing

completed owner turn ──► rememberer ──► host transaction ──► memory_log

simple timer ──────────► dreamer ─────► host transaction ──► memory_summary
```

Jarvis is one Python application and one PostgreSQL database. Components below
are code boundaries, not independently deployed services unless an existing
integration requires one.

## Discord adapter

The adapter:

- Receives the owner's Discord messages.
- Deduplicates gateway re-delivery by Discord message ID.
- Matches `stop`, `pause`, and `resume` before model work.
- Persists inbound messages before processing.
- Delivers pending assistant messages and records Discord message IDs.
- Shows acknowledgement and typing state while a turn runs.
- Renders host-owned Approve and Deny messages from stored action arguments.
- Atomically claims or denies component interactions, then immediately
  acknowledges them and disables their components before external work.
- Prevents model tools from editing host-owned approval messages.
- Exposes the permitted channel, thread, message, attachment, and reaction
  operations through Jarvis-owned `llm-tools` declarations.

The adapter renders model output as ordinary text/Markdown. It may render links,
but the bot lacks `EMBED_LINKS`, so Discord does not automatically unfurl them.

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
→ send to Discord
→ store Discord message ID as source_message_id
```

On startup, the adapter retries assistant messages whose `source_message_id` is
null.
Conversational delivery is at-least-once. A rare duplicate after an ambiguous
Discord send is acceptable; losing or duplicating an effectful tool action is
not.

Approval messages follow the same persistence rule. The action's
`approval_message_id` references the internal message row; that row acquires the
Discord delivery ID. A component interaction must match both.

## Turn coordinator

For each owner message:

1. Check the paused flag.
2. Persist/deduplicate the inbound message.
3. Acquire the in-process provider mutex.
4. Run the recaller.
5. Build context from stable instructions, recent centralized messages, recalled
   memory, the current instant, and the owner's timezone.
6. Run the bounded main-agent step loop.
7. Persist the durable conclusion and set the owner message's `processed_at` in
   the same transaction.
8. Deliver any pending response and release the provider mutex.
9. Run the rememberer in the background, yielding to new owner work.

A turn is eligible for remembering after `say`, `finish`, or creation of an
action awaiting approval. This includes a turn whose visible response is a
host-rendered approval message rather than model-authored prose.

At startup, an owner row with null `processed_at` is an interrupted turn. If it
has no originating action, it may be replayed. If it already produced an action,
the host resumes or reconciles the action, persists an interruption notice, and
closes the turn without replaying the model. This is the turn-level duplicate
effect barrier.

The application holds one PostgreSQL advisory lock for deployment ownership. A
second Jarvis instance refuses to start. Because only one process runs, turn and
provider scheduling inside that process use ordinary locks and queues rather
than additional database workflow machinery.

## Cognitive roles

### Recaller

The recaller receives the owner input and bounded recent context. Its frozen
capability plan contains only memory search and memory open. It may issue several
queries and returns a compact bundle of raw memories and summaries, or nothing.

### Main agent

The main agent receives recalled memory and the capability descriptions exposed
for the turn. It emits the strict step grammar defined once in
[SPEC section 7.4](../SPEC.md#74-model-step-protocol).

The main agent never owns credentials or policy classification. Host code
validates the whole step before executing any call. Independent calls in one
step may run concurrently within the turn budget.

### Rememberer

The rememberer receives the persisted completed turn, material tool observations,
and relevant existing memory. It can search/open memory and returns a structured
final list of zero or more raw memory strings.

Host code performs one transaction that:

- Appends the new `memory_log` rows.
- Sets `remembered_at` on the triggering owner message.

The rememberer does not call a memory write tool and creates no action rows. A
failed or cancelled run leaves `remembered_at` null for a bounded retry sweep.

### Dreamer

The dreamer searches and opens memory, then returns a structured batch of
summary insertions and removals. Host code applies the batch transactionally.

Only one dreamer runs at once. It yields the provider mutex when owner input is
waiting. Missing a dream run cannot break conversational correctness because raw
memory remains directly searchable.

## Tool execution

Jarvis owns every Gmail, Calendar, Maps, Discord, local, and memory-read tool
declaration and binding. `llm-tools` supplies the kernel, not those integrations.

The host:

- Freezes a capability plan for each cognitive role and turn.
- Validates versioned canonical tool IDs and closed arguments.
- Classifies calls using the fixed automatic/approval policy.
- Owns connector credentials.
- Executes reads directly through the kernel without action rows.
- Inserts an `action` before every effectful tool call.
- Supplies the action ID as the durable effect identity.
- Returns typed observations to the model.

Canonical message persistence, raw-memory append, and summary replacement are
application transactions. They are not tools and do not pass through the kernel.

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

Execution claims commit before the external call. There is no action lease: one
deployment process owns all work. A bounded request timeout and startup scan
reconcile any row left `executing` using tool-specific evidence. Only proof that
the effect did not happen can return it to `queued`; ambiguous outcomes become
`uncertain`.

`tool_name`, `arguments`, and `origin_message_id` never change after insertion.
The tool name carries its contract version. The executor and approval renderer
both consume the same stored arguments, so no input digest or parallel contract
revision record is needed.

## Approval rendering

The model step contains a canonical tool call and arguments only. When policy
requires approval:

1. Insert the action and host-owned approval message in one transaction.
2. Store the internal message ID as `approval_message_id`.
3. Load the action's immutable validated arguments.
4. Select the host renderer for the versioned `tool_name`.
5. Render every recipient, audience, and transmitted value.
6. Deliver the pending message with Approve and Deny.

For content exceeding one Discord message, the renderer may split the material
or attach a host-generated text file. The final component-bearing message states
that the entire preceding payload is what Approve executes.

There is no model preview field and no stored preview column.

## Gmail send recovery

Email is prepared as a Gmail draft and the Gmail `draftId` is stored before
approval. After an ambiguous send:

1. Check whether the draft still exists.
2. If absent, inspect Sent mail using the available thread, recipients, subject,
   and provider response evidence.
3. Repeat only when evidence proves the send did not occur and repeating is safe.
4. Otherwise record terminal `uncertain` and tell the owner.

Slice 0 validates the exact behavior of the existing Gmail integration for new
and reply threads.

## Persistence

PostgreSQL owns exactly:

- `message`
- `memory_log`
- `memory_summary`
- `action`

Existing integration state stays with its current owner. Configuration owns the
owner ID, Discord server ID, timezone, paused flag, model configuration, and
credential locations. Alembic may own its bookkeeping table.

## Provider containment

Codex runs under the exact policy in [SPEC section 7.5](../SPEC.md#75-codex-containment):
empty read-only working directory, no network, deny-mode approval, disabled native
feature set, no MCP, and no connector credentials.

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

No workflow framework exists.

- A small timer selects queued `schedule_wake` rows whose `execute_after` is due.
- Quiet hours move the effective due time to their end.
- A periodic connector tick may start a read-only proactive turn.
- A timer may invoke dreaming when the provider mutex is idle.
- Startup reconciles every action left `executing`; ordinary external calls use
  bounded timeouts while the process is alive.

Each path is an ordinary function over explicit database state.

## Failure behavior

- Recaller failure: continue without recalled memory.
- Main-agent failure: report a concise host-authored error; retry at most once on
  a fresh session and never after an effect completed.
- Rememberer failure: leave `remembered_at` null and retry later.
- Dreamer failure: retain raw memory and existing summaries.
- Embedding failure: leave the vector null; lexical recall continues.
- Discord delivery failure: retain the assistant row with null
  `source_message_id` for retry.
- Approval-rendering failure: create no functional Approve component.
- Interrupted turn with no effect: replay; interrupted turn with an originating
  action: resume/reconcile without model replay.
- Action left `executing`: reconcile before any repeat.
- Unprovable external outcome: record terminal `uncertain` and tell the owner.

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

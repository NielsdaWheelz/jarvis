# V1 architecture

This document expands the architecture required by [SPEC.md](../SPEC.md). It is
descriptive unless it uses MUST or MUST NOT. `SPEC.md` remains authoritative.

## Design objective

Jarvis should feel like one capable assistant while remaining mechanically
simple enough to understand in one sitting.

```text
dedicated Discord server
          │
          ▼
  Discord ingress/egress
          │
          ├────────────────────────────► append/read message history
          ▼
 recall before every human input ──────► PostgreSQL memory
          │                               log + summaries
          ▼
  main Codex reasoning loop
          │
          ▼
 host-owned llm-tools executor ────────► existing integrations
          │                               Discord / Gmail /
          │                               Calendar / Maps
          ▼
      action ledger
          ├── ready ───────────────────► execute automatically
          └── awaiting approval ───────► Approve / Deny ─► execute once

completed interaction
          │
          ▼
      rememberer ──────────────────────► append memory_log

simple periodic timer
          │
          ▼
        dreamer ───────────────────────► rebuild memory_summary
```

## Runtime components

The components are logical roles. They MAY initially run in one deployment and
one Python package.

Recaller, rememberer, and dreamer are bounded agents. They may reason across
multiple Codex turns, make decisions, call their allowed tools repeatedly, issue
new searches based on earlier results, and decide when to stop. Their capability
profiles differ; they are not single-shot prompt functions and do not share the
main agent's external tools.

### Discord adapter

Responsibilities:

- Receive events from the existing dedicated Discord server.
- Accept control only from the configured owner Discord ID.
- Preserve Discord message, channel, thread, and server identifiers.
- Persist inbound and outbound conversation messages centrally.
- Send normal responses and proactive messages.
- Render Approve and Deny components for actions awaiting approval.
- Permit Jarvis to manage its dedicated server.

It does not perform model reasoning or decide tool authority.

### Turn coordinator

The turn coordinator is ordinary application code, not a workflow engine.

For each owner-authored human input it:

1. Inserts the inbound message idempotently using its Discord source identity.
2. Acquires the conversation turn lock.
3. Builds a recaller request from the human input and centralized recent context.
4. Runs the recaller.
5. Builds the main-agent context with the recalled memory bundle.
6. Runs the host-mediated model/tool loop until answer, action proposal, silence,
   failure, or a bounded turn limit.
7. Stores any Jarvis response in `message` and delivers it through Discord.
8. Invokes the rememberer with the completed useful working context.
9. Releases the turn lock.

Once a Jarvis response has been decided, centralized message storage survives a
client-delivery failure. A process crash MUST NOT duplicate an externally
approved effect.

### Recaller

The recaller is a Codex session with access only to memory search and memory-open
operations. It has no connector or write tools.

It returns a bounded memory bundle containing selected text, IDs, timestamps,
and summary lineage where relevant. It may return no memories.

### Main agent

The main agent is Jarvis's visible reasoning role. It receives:

- The current human input.
- Recent working conversation context.
- Recalled memories.
- Concise stable Jarvis instructions.
- The capability descriptions exposed for the turn.
- Typed observations from previous tool steps.

It does not receive connector credentials or a writable repository checkout.

The main agent emits one structured step at a time:

```text
read
  canonical tool name
  arguments

answer
  Discord-ready text

propose_action
  canonical tool name
  exact arguments
  human-readable preview

finish_silent
  optional internal reason
```

The application, not the model, determines whether a tool is automatic or must
await approval in `action`.

### Rememberer

The rememberer is a Codex session with read-only access to relevant memories and
one append operation. It receives the completed working context and produces
zero or more concise raw memories.

It cannot create summaries or execute external actions.

### Dreamer

The dreamer is invoked by a systemd timer or a small timer loop. It can search
and open raw memories and rebuild summary rows. It cannot mutate the raw log or
use external action tools.

Dreaming is opportunistic. A missed dream run must not affect conversational
correctness; the raw log remains searchable directly.

### Tool executor

All application tools are declared through `llm-tools`.

The host:

- Selects a closed capability plan for each role.
- Validates tool arguments and results.
- Supplies the correct existing integration binding.
- Owns credentials and connector state.
- Persists every tool call that mutates an external integration or local
  workspace in `action` before execution.
- Classifies the call as automatic or approval-required.
- Reports typed observations back to the model.

The tool executor MUST NOT accept an arbitrary tool name or schema invented by a
model response.

Reads and canonical `message`/memory transactions do not create action rows.

### Action and approval handler

The approval handler operates independently of the active model session.

`action` minimally contains:

```text
id
tool_name
arguments
status
created_at
decided_at
completed_at
result
```

An automatic write starts as `ready`; an approval-gated write starts as
`awaiting_approval`. Approve performs an atomic `awaiting_approval -> executing`
transition. Only the winner of that transition may execute the operation. Deny
transitions it to `denied`.

The remaining statuses are `succeeded`, `failed`, and `uncertain`. Retries
reconcile an uncertain prior result before repeating an irreversible provider
call. The action ID is the stable effect and idempotency identity.

For email, reconciliation SHOULD use a stable generated `Message-ID` to inspect
Sent mail after an ambiguous timeout. If the existing integration cannot prove
whether the message was sent, Jarvis reports uncertainty instead of retrying
blindly.

This one table replaces separate pending-action, effect, execution, and receipt
tables. It is application mechanics, not a workflow system.

## Persistence

PostgreSQL is the only new required state service.

It stores:

- `message`.
- `memory_log`.
- `memory_summary`.
- `action`.

These are the only Jarvis application tables. Existing connector state remains
in its current owned stores. Deployment configuration owns the user, server, and
credential settings. Migration tooling may create its own bookkeeping table.

PostgreSQL full-text search and pgvector serve memory retrieval. No other search,
queue, graph, cache, or vector service is required.

Large raw email bodies, attachments, and map data SHOULD remain in their source
systems. Memory stores concise recollections and stable references, not mirrors
of connected services.

## Existing integration boundary

Gmail, Calendar, Maps, and Discord are already working and are inputs to this
system, not greenfield connector projects.

The integration audit should expose each existing operation as one of:

- Read operation: automatic.
- Reversible personal write: automatic.
- Consequential outward action: pending approval.
- Unsupported in v1.

Adapters should be thin. They MUST preserve existing authentication and stable
provider IDs where possible. They MUST NOT expose generic access to the host
machine or unrelated Ariel internals.

## Process and deployment boundary

The preferred deployment has:

- One Jarvis Python service for Discord, coordination, memory roles, and tool
  policy.
- One PostgreSQL database.
- A confined `provider-runtime` Codex child process/session mechanism.
- Existing connector modules or small adapter processes as required by their
  current implementation.

Separate services are justified only by an existing integration boundary or a
credential/process-isolation requirement. They are not a goal.

The production target is Linux because the current `provider-runtime` security
tests contain Linux-specific assumptions. Development on macOS is allowed, but
security acceptance occurs on Linux.

## Context construction

Context should be compact and rebuilt from owned state:

```text
stable Jarvis instructions
+ recent centralized message history
+ recaller memory bundle
+ relevant live tool observations
+ current human input
```

Provider-native session history is a performance aid, not the canonical copy of
conversation or memory. Jarvis must be able to start a fresh session from
`message` plus recalled memory. Discord history is likewise a client copy, not
the canonical conversation store.

Untrusted email, calendar, map, and Discord content is presented as data. It may
influence the answer but cannot grant tool authority or alter system rules.

## Bounded execution

Each foreground turn MUST have configurable bounds on:

- Model turns.
- Tool invocations.
- Retrieved memory candidates.
- Returned memory text.
- Wall-clock duration.

Exhaustion produces an honest partial result or failure. It does not silently
expand authority or switch providers.

## Logging and inspection

Operational records SHOULD allow an engineer to reconstruct:

```text
centralized input message ID
→ recalled memory IDs
→ model steps
→ tool names and redacted arguments
→ automatic/approval decision
→ provider outcome
→ centralized output message ID
→ Discord delivery
→ appended memory IDs
```

Ordinary logs MUST NOT contain credentials, full private messages, raw email
bodies, or complete memory text. Development inspection tools may retrieve those
from their owned stores under explicit local access.

## Failure behavior

- Recaller failure: continue with no recalled memory and say nothing unless it
  materially affects the answer.
- Rememberer failure: preserve the completed user response; retrying memory
  formation MAY occur later but MUST NOT duplicate known rows blindly.
- Dreamer failure: retain existing summaries and raw log.
- Read-tool failure: main agent may retry within bounds or report uncertainty.
- Action storage failure: do not execute a write or present a functional Approve
  button.
- Approved-action uncertainty: do not blindly retry; reconcile or report it.
- Discord delivery failure: preserve the centralized message and report or retry
  delivery within bounds.

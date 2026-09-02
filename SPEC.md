# Jarvis v1 specification

Status: **Frozen baseline**

Date: **2026-09-01**

Audience: product, engineering, design, operations, and future coding agents

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

## 1. Product definition

Jarvis is a persistent personal assistant for one user. It exists to return the
user's attention by remembering relevant context, using connected services, and
performing ordinary work without requiring supervision.

Jarvis is one visible assistant. Recaller, rememberer, dreamer, and other model
calls are internal cognitive roles, not user-facing personalities.

## 2. Goals

V1 MUST:

1. Provide a natural ongoing relationship in one configured private Discord
   channel.
2. Reuse the user's working Discord, Gmail, Google Calendar, and Google Maps
   integrations without avoidable reauthorization.
3. Use bounded public-Web search and page reading when live external evidence is
   needed.
4. Persist conversation history independently of Discord and provider sessions.
5. Recall relevant durable memory before every owner-authored human input.
6. Append useful durable memories after completed owner turns.
7. Preserve raw memories while treating summaries, embeddings, and indexes as
   rebuildable.
8. Combine keyword and semantic memory search.
9. Use tools to answer and act rather than merely explain how work could be done.
10. Act automatically for reads, ordinary reversible work, and work confined to
   the user's resources.
11. Ask only for Approve or Deny at the defined external-authority boundary.
12. Remain inspectable enough to diagnose bad recall, failed tools, and duplicate
    or uncertain actions.
13. Remain small enough that one engineer can understand the complete system.

## 3. Non-goals

V1 MUST NOT add:

- Multiple users, tenancy, or public hosting.
- Android or another custom client.
- Voice interaction.
- A visible organization of agents.
- People, project, task, commitment, decision, episode, claim, procedure, or
  knowledge-graph domain models.
- A workflow framework or general agent platform beyond the bounded
  `llm-agent-kernel` library.
- General subagent delegation, persistent peer agents, or model-generated
  program execution.
- A general-purpose remote shell, SSH, terminal, or unconstrained browser agent.
- OnePassword, Nexus, or Skidbladnir integration.
- Autonomous purchasing, financial activity, credential changes, or destructive
  remote execution.
- Slash commands, dashboards, or speculative action components.
- Multiple Jarvis channels, Discord threads or direct messages, and Discord
  server organization.
- An API-backed cognitive provider. The v1 product-context selection and kernel
  reconstruction ports remain provider-neutral so a later provider does not
  require new canonical context machinery.
- Autonomous modification of prompts, permissions, code, or deployment.

Deferred integrations are recorded in the implementation plan.

## 4. User experience

### 4.1 Discord is Jarvis's home

Jarvis MUST live in one configured private Discord text channel, conventionally
`#general`, in a dedicated server owned by the user. Deployment configuration
contains exactly one owner Discord user ID, guild ID, and channel ID.

Jarvis accepts owner messages and approval interactions only in that channel. It
MUST ignore direct messages, Discord threads, other channels, and every other
user. The server MAY contain explicitly trusted supporting bots, but they cannot
control Jarvis.

Discord is a host-owned conversation transport, not a model-callable tool
family. The adapter MAY:

- Receive and boundedly catch up owner messages from the configured channel.
- Start typing state promptly while a turn runs.
- Deliver ordinary text, Markdown, links, and code snippets produced by `say`.
- Deliver proactive messages under section 4.4.
- Deliver host-rendered approval messages and plain-text payload attachments.
- Edit its own approval message to disable Approve and Deny after a decision.

These transport operations create no `action` rows. Jarvis has no v1 capability
to create, rename, reorder, archive, or delete channels or threads; manage other
messages; add reactions; or organize the server.

The bot role grants exactly:

- `VIEW_CHANNEL`
- `SEND_MESSAGES`
- `ATTACH_FILES`
- `READ_MESSAGE_HISTORY`

The integration enables exactly the `GUILDS`, `GUILD_MESSAGES`, and
`MESSAGE_CONTENT` Gateway intents. Direct-message, member, presence, and reaction
intents are absent; host filtering rejects thread events. Invite, role, webhook,
ban, kick, moderation, message-management, and guild-management authority are
absent. `ADMINISTRATOR`, `MANAGE_CHANNELS`, `MANAGE_THREADS`, `MANAGE_MESSAGES`,
thread creation and send permissions, `ADD_REACTIONS`, and `EMBED_LINKS` are
deliberately absent.

Without `EMBED_LINKS`, Discord does not automatically unfurl links Jarvis posts;
ordinary clickable links still work. Normal model output is text. Host code MUST
NOT translate a model-supplied rich-content object into an embed, attachment, or
interaction component. The host-owned approval renderer in section 5.3 is the
deliberate exception for a plain-text payload attachment and Approve or Deny
components.

### 4.2 Conversation is natural

The owner speaks naturally. Jarvis replies naturally using the Discord formats
appropriate to the content.

V1 has no slash commands. The only custom action components are:

- **Approve**
- **Deny**

Reliability outranks personality. Jarvis SHOULD be direct, calm, resourceful,
and willing to act. It SHOULD avoid ceremonial progress reports, needless menus,
agent theatre, and notifications without plausible benefit. Silence is a valid
result.

### 4.3 Central conversation history

Discord is a client and delivery surface, not the canonical conversation store.
Every owner message and every Jarvis response MUST be persisted in `message`.
The main Codex session is normally continued and resumed, but it remains
disposable and reconstructable through the kernel context ports from centralized
messages plus recalled memory.
Losing it MUST cause a cold context bootstrap, not conversation or memory loss.

Inbound owner messages are stored with `processed_at = NULL` before processing
and deduplicated by their source identity. On startup, the adapter MAY use
Discord history after the latest stored source message ID for bounded catch-up.
A terminal action also creates the idempotent host-authored waking row specified
in section 5.4. Owner and host rows share the same checkpoint mechanism; only
owner-authored Discord text is eligible for stop/pause/resume interception.
Jarvis derives an immutable run class from existing row fields rather than a new
column: owner rows and `source = action` resolution rows are `interactive`,
while `source = schedule_wake` rows are `proactive-read`. `interactive` binds to
the full Main plan; `proactive-read` binds to the read-only proactive plan. One
drain consumes only a maximal contiguous prefix of one class.
A turn reaches a durable conclusion when it produces a persisted assistant
response, finishes silently, or persists
an approval proposal. The host sets `processed_at` in the same transaction as
that conclusion.

Outbound Jarvis messages use a persistent, provider-deduplicated outbox:

1. Insert the assistant message with `source_message_id = NULL`.
2. Derive its Discord nonce as the unpadded base64url encoding of the first 15
   bytes of `SHA-256(UTF-8("jarvis-discord-v1:" + canonical_text(message.id)))`.
   This is a deterministic 20-character value and is not stored separately.
3. Create the Discord message with that nonce and `enforce_nonce = true`.
4. Store the returned Discord message ID in `source_message_id`.
5. Reuse the identical nonce for every retry.

In these derivations, `canonical_text(id)` means the lowercase, whitespace-free
PostgreSQL text representation of the persisted ID.

The qualified `discord.py` 2.7.1 public send API accepts `nonce` but does not
expose `enforce_nonce`. V1 therefore uses one small host-owned `httpx` binding to
Discord REST v10 for Create Message. Gateway ingress, typing, and component
interactions remain on `discord.py`; Jarvis does not call private `discord.py`
internals.

Discord enforces nonce uniqueness for the same author only within its recent
deduplication window. Before a delayed or post-restart retry that may fall
outside that window, the adapter MUST boundedly read channel history after the
nearest known preceding Discord message and look for its own message with the
same nonce. With no preceding anchor, it scans backward no earlier than the
pending row's `created_at`, subject to the same bound. If found, it stores that
Discord ID without sending. If the required interval cannot be checked
completely, the row remains pending; it is not blindly resent. If the check
completes without a match, the adapter sends with the same enforced nonce.

A null `source_message_id` remains the only outbound retry watermark. The nonce
derives from existing state, so this rule adds no column. V1 does not accept a
known duplicate-delivery path; a Discord service defect or inconsistent history
remains outside the guarantee. External tool effects and approval-bearing
actions have their independent action-level barriers.

On startup, an owner row with `processed_at = NULL` and no action originating
from it MAY be replayed. If an action already originates from the interrupted
turn, the host MUST reconcile or resume that action and MUST NOT replay the model
turn automatically. It persists a host-authored interruption notice and closes
the turn instead. This deliberately prefers a recoverable partial interaction to
duplicating an effect.

The host promptly shows a typing indicator before model work. V1 does not stream
partial structured model output into Discord; a `say` step is delivered only
after its schema is valid.

### 4.4 Proactivity and stop control

V1 has one user-facing proactive trigger: a due `schedule_wake` action created
from the owner's natural-language request. A wake becomes eligible at its exact
requested instant; if Jarvis was offline, it becomes eligible on startup. There
are no generic quiet hours, periodic connector polls, notification batching,
urgency classification, or autonomous inbox/calendar monitoring in v1.

When an eligible queued wake is claimed, host code atomically moves it to
`executing` and inserts one waking `message` with `role = host`,
`source = schedule_wake`, `source_message_id = canonical_text(action.id)`, the
configured conversation ID, and `processed_at = NULL`. Its text is rendered from
the immutable validated action arguments and includes the original instruction
and requested instant. This is distinct from an action-resolution message and is
idempotent across restart. The main run receives the normal read-only proactive
capability plan. Persisting its visible conclusion (or the deterministic fallback
below) and marking the wake `succeeded` occur in the same transaction; an
interrupted due-wake row is safe to resume without recreating the action.

Inbound email, calendar changes, Maps data, and non-owner Discord activity do not
directly start model turns. A proactive turn receives the scheduled-wake event
and the catalogued read tools only; it does not invoke the owner-input recaller.
It cannot perform writes or propose approval-bearing actions. Its only possible
external output is a normal message to the owner in the configured channel.

Dreaming may run silently on an idle/system timer. It is derived-memory
maintenance, not a user-facing proactive turn.

Before recall or any model call, host code matches an owner message whose trimmed
content is exactly `stop` or `pause`, case-insensitively, and persists a paused
flag. While paused, Jarvis performs no tools, actions, proactive turns, or
dreaming. `resume` clears the flag. These controls do not involve the model.

## 5. Authority and approvals

### 5.1 Automatic operations

Jarvis acts without approval for:

- The exact read tools in section 7.3.
- Memory retrieval, append, summary maintenance, and index rebuilding.
- Canonical message, action, and deployment bookkeeping in Jarvis's own database
  and private runtime state.
- `gmail.create_draft` and `gmail.update_draft`, without sending.
- Creating, editing, moving, or deleting no-attendee events on an owner-only
  calendar.
- Creating or cancelling a `schedule_wake`.
- Normal Jarvis responses and proactive owner notices through the configured
  Discord transport.

This list is exhaustive for v1 automatic writes. There is no local-filesystem
tool and no Gmail label, archive, trash, delete, or other organization tool.

An owner-only calendar is one whose live ACL grants access only to the owner.
The deployment records the verified owner-only calendar IDs. A calendar write
whose ACL is shared or unknown requires approval. Calendar write schemas carry an
explicit IANA timezone and reject naive datetimes.

### 5.2 Approval-required operations

Jarvis asks for Approve or Deny before:

- Sending an email or message to another person outside Jarvis's server.
- Adding, removing, or notifying another calendar attendee.
- Spending money or committing the owner to a purchase.
- Revealing or transmitting a credential or secret.
- Irreversibly deleting or overwriting meaningful external data outside the
  explicit automatic list.
- Running a destructive command on another machine.

V1 implements approval renderers for Gmail send and for calendar writes that are
not confined to a verified owner-only calendar. Other approval categories in
this section define the boundary but need no v1 tool; an unsupported request
fails closed.

### 5.3 Approval presentation

The model emits tool arguments, never the preview the owner approves.

For each approval-bearing tool, host code MUST own a deterministic renderer that
reads the validated stored arguments. There is no preview field in the model
step and no preview column in `action`.

For email, the host-rendered material shows every To, Cc, and Bcc address, the
subject, and the complete body. Long content MAY be split across host-owned
messages or placed in a host-generated attachment; the final host-owned message
carries Approve and Deny and clearly identifies the preceding material as the
complete payload.

An approval-bearing tool without a host renderer fails closed. A model rationale
MAY be shown as separately labelled commentary but never substitutes for the
rendered action.

Messages carrying Approve or Deny are host-owned. Model-originated tool calls
cannot edit or delete them. After the host claims or denies the interaction, it
disables the components before any slow external work begins.

### 5.4 Approval execution

Approval is deliberately simple:

1. Validate the proposed tool and arguments.
2. Insert one `action` row as `awaiting_approval`, plus its host-owned approval
   `message`, in one transaction.
3. Store that message's internal ID as `approval_message_id` and render the exact
   action from the immutable stored arguments.
4. On Approve or Deny, validate the context and atomically claim or resolve the
   stored row.
5. Immediately acknowledge the Discord interaction and disable its components.
6. Execute an approved action at most once and store its result.
7. Insert one idempotent host-authored action-resolution `message` and let the
   main agent report success, denial, failure, or uncertainty naturally.

The invoking Discord user, guild, and channel must match deployment
configuration. The interaction's Discord message ID must match the `message`
referenced by `approval_message_id`. Free-form text never counts as approval.

Action states are exactly:

```text
queued
awaiting_approval
executing
succeeded
failed
uncertain
cancelled
```

Automatic and scheduled writes begin `queued`. Approval-bearing writes begin
`awaiting_approval`. Approve atomically moves an action to `executing`; Deny moves
it to `cancelled`. The owner may also cancel a queued scheduled action.

The deployment-level lock guarantees that only one Jarvis process can execute
actions. An external request has a bounded timeout. After a timeout, or on
startup when an action remains `executing`, the host uses tool-specific evidence
and bounded provider re-reads to reconcile it automatically. It may return the
action to `queued` only when evidence proves the effect did not occur and
repeating it is safe. It records `succeeded` or `failed` when provider evidence
establishes the outcome. Only after the tool-specific reconciliation procedure
is exhausted and available evidence genuinely cannot decide does it record
terminal-for-execution `uncertain`. A timeout alone is never evidence for a
retry or for uncertainty. There is no blind retry, attempt counter, or execution
lease.

Repeated calls with identical arguments are permitted. Duplicate prevention
comes from source-message deduplication, atomic action state transitions, the
action ID as a provider idempotency key where supported, and tool-specific
reconciliation—not a guessed semantic intent key.

An uncertain result includes the safe evidence Jarvis has and asks the owner to
inspect the provider state. Later evidence MAY amend the recorded result and
mark it succeeded or failed, but it MUST never cause automatic re-execution.

Every action outcome that cannot return to its still-live originating model loop
is reintroduced to the conversation as one host-authored waking `message` with
`role = host`, `source = action`,
`source_message_id = canonical_text(action.id) + ":" + status`, the configured
`source_conversation_id`, and `processed_at = NULL`. Its bounded text contains
the action ID, tool name, resolved state, and safe normalized result; it contains
no credential or approval instruction. The source identity makes each resolved
state idempotent while allowing later evidence to supersede `uncertain` with a
new `succeeded` or `failed` resolution. Startup inserts any missing resolution
row before declaring recovery complete. This existing-table path is the durable
correlation between an approval/reconciliation and a later kernel run; the
original model `call_id` remains turn-local. Its kernel resolution state maps
`succeeded` to `executed`, an owner-denied `cancelled` action to `denied`, and
the remaining terminal action states directly; other cancellations use
`cancelled`.

An action-resolution input must produce a visible owner notice. If the main
model returns `finish` or fails before `say`, Jarvis's terminal-finalization
adapter persists a deterministic host-authored assistant fallback rendered from
the action ID, tool, resolved state, and safe normalized result, then processes
the host row. For `uncertain`, that fallback includes the safe reconciliation
evidence and the required request for owner inspection. The same rule applies to
a scheduled-wake input, whose fallback includes the stored reminder instruction.
Thus silence remains valid for ordinary owner turns, but never silently consumes
an asynchronous result or requested reminder.

### 5.5 Gmail send

Gmail send uses the provider's draft flow:

1. Create the exact draft automatically.
2. Persist its Gmail `draftId`, known thread identity, and exact envelope,
   subject, and body snapshot in the action arguments.
3. Render and request approval for that immutable snapshot.
4. Immediately before sending, fetch the live draft and require it to match the
   snapshot exactly; a mismatch fails the action and requires a new proposal.
5. Send by `draftId` after approval.
6. On an ambiguous result, perform bounded re-reads: check whether the draft
   remains and inspect Sent mail using the known identity before deciding whether
   a repeat is proved safe.

The exact reconciliation behavior for new and existing threads MUST be verified
against the live integration in Slice 0. Only if the complete reconciliation
procedure cannot establish an outcome does the action become terminal
`uncertain`; Jarvis presents its evidence and asks the owner to inspect Gmail.

## 6. Memory

### 6.1 Principle and schema

Memory is natural-language memory plus learned retrieval, not an ontology.

The canonical schema is exactly:

```text
memory_log
  id
  text
  created_at
  embedding

memory_summary
  id
  text
  source_memory_ids
  created_at
  embedding
```

Raw memories are permanent under normal v1 operation. V1 provides no redaction,
forgetting, or destructive consolidation mechanism. Administrative erasure is a
deferred design that must account for every copy, including messages, actions,
provider state, backups, Discord, and external systems.

Summaries, embeddings, full-text indexes, and vector indexes are derived and
rebuildable. The system adds no memory type, category, importance, confidence,
salience, source-authority, validity, conflict, project, person, or procedure
field.

### 6.2 Raw memory

The rememberer produces zero or more concise, self-contained natural-language
memories from completed working context. Host code appends them to `memory_log`
and sets the originating owner message's `remembered_at` in one transaction.

Memory persistence is host-owned canonical bookkeeping, not an `llm-tools` tool
effect. It creates no `action` row and does not duplicate memory text into the
action ledger.

Normal operation never updates or deletes raw `id`, `text`, or `created_at`.
Only the derived `embedding` may be filled, cleared, or rebuilt.

Raw memory text may contain stable natural-language references:

```xml
<refs>
  <ref uri="gmail://account/message/id">Related email</ref>
  <ref uri="gcal://account/event/id">Related event</ref>
  <ref uri="maps://place/id">Related place</ref>
  <ref uri="discord://server/channel/message">Original discussion</ref>
</refs>
```

References do not create object tables or special relationship semantics. A
correction is another natural-language memory; the recaller and dreamer resolve
it through ordinary search and reasoning.

Host code rejects unmistakable credential material such as private-key blocks
and known API-token prefixes before memory insertion. Broader entropy, payment
number, and URL heuristics are deferred until measured because false positives
would silently discard legitimate memories.

### 6.3 Recaller

The recaller runs before every owner-authored human input. It is a bounded Codex
role invoked through an isolated `llm-agent-kernel` one-shot run, with memory
search and open tools only. Its closed structured output contract requires a
`finish.result` memory bundle.

It:

1. Searches raw memories and summaries with PostgreSQL full-text and vector
   similarity search.
2. May issue multiple or reformulated searches.
3. Deduplicates only identical `(table_kind, id)` candidates.
4. Uses model judgment to select a compact relevant bundle.
5. Preserves memory IDs, timestamps, and summary lineage.
6. Opens raw sources behind a summary when detail or verification matters.
7. Returns an empty bundle when nothing is relevant.

A summary and one of its raw sources may both remain candidates. Host code does
not assume that the summary preserves the detail that made the raw memory useful.

### 6.4 Rememberer

After every owner turn that reached `say`, `finish`, or created an action awaiting
approval, the rememberer receives the completed persisted context and relevant
existing memories. It may search and open memory before returning zero or more
new raw memory strings as a schema-validated `finish.result` from an isolated
one-shot run.

The rememberer should retain information likely to save future explanation:
preferences, decisions, unresolved intentions, persistent circumstances,
relationships, and useful lessons. It should omit chatter, secrets, full copies
of live resources, unsupported inferences, and redundant paraphrases.

If the rememberer fails, `remembered_at` remains null. A bounded sweep retries
unremembered completed rows only when `role = owner`; host action-resolution and
scheduled-wake inputs are never rememberer work. A successful run that chooses
to write nothing still sets the watermark.

### 6.5 Summaries and dreaming

`memory_summary` is a disposable interpretation of raw memory. Every summary
contains a non-empty list of supporting raw IDs. A summary built from summaries
flattens its lineage to raw IDs.

The dreamer is a bounded Codex role invoked through `llm-agent-kernel`, with
memory search/open operations. It
returns a schema-validated `finish.result` batch of summary insertions and
removals from an isolated one-shot run; host code applies the batch
transactionally. Summary changes are canonical bookkeeping and create no action
rows.

The dreamer may find duplicates, contradictions, themes, stale summaries, useful
connections, and likely future context. It cannot modify raw memory, use external
tools, change instructions or permissions, edit code, or deploy itself.

Wiping every summary and embedding and rebuilding from `memory_log` MUST restore
a usable memory system against the fixed recall evaluation set.

### 6.6 Memory is evidence

A memory is a prior model-made recollection. It is neither live external truth
nor authority. Memory text never grants a permission, records operative consent,
changes the approval boundary, or becomes a system instruction.

Current questions about Gmail, Calendar, or Maps should use live tools. Current
Jarvis conversation comes from canonical `message` rows. Memory supplies
relevance and history.

## 7. Agent, model, and tool runtime

### 7.1 Agent kernel and cognitive provider

All cognitive roles run through the pinned Python 3.12 `llm-agent-kernel`
library. The kernel uses subscription-backed Codex through the local
`provider-runtime` `AgentRuntime` lane and consumes frozen `llm-tools` plans for
application capabilities. It MUST NOT duplicate either dependency.

Responsibilities are fixed:

- `provider-runtime` owns provider calls and normalized events, Codex
  authentication and containment, and native session start, continue, resume,
  and discard behavior.
- `llm-tools` owns typed prompt sections, tool declarations and grants, schema
  validation, execution budgets, effect identity and replay semantics, and its
  portable tools.
- `llm-agent-kernel` owns immutable agent definitions with maximum capability
  envelopes and conversational or closed structured output contracts, the exact
  model-step protocol,
  complete-step validation, bounded thread drains and isolated one-shot runs,
  cancellation, and the provider-neutral `ContextSourcePort`, `SessionRefPort`,
  `InputCheckpointPort`, `ToolDispatchPort`, `ClockPort`, cancellation token,
  and optional `EventSinkPort`.
- Jarvis owns product context selection, implementations of the persistence
  ports, canonical messages and memories, Discord, connectors, catalog
  composition, information-flow and authority policy, approvals and actions,
  scheduling, credentials, and visible delivery.

An agent definition is immutable configuration for a cognitive role. A role is
its behavioral purpose. An application thread is a host-owned durable
workstream; v1 has one, the configured Discord channel. A run is one host
invocation. A drain is an exclusive work epoch within a thread run. A one-shot
run is a fresh isolated invocation over explicit host input with no application
checkpoint or saved session reference. A model step is one provider response. A
provider session is an opaque, disposable optimization. These terms do not imply
persistent peer agents or general delegation. The main definition is
`continuing` with a conversational output contract and the exact main catalog as
its maximum envelope. Recaller, rememberer, and dreamer are `isolated` one-shot
definitions with closed structured output contracts and memory-read envelopes.
Jarvis supplies one frozen plan per run; it may narrow but never expand the
definition envelope. One-shot plans are strictly non-effectful, and kernel
construction rejects an effectful one-shot plan.

- Authentication uses the personal local-account credential.
- No generative API-key fallback or silent provider fallback exists.
- Kernel revision, model IDs, reasoning levels, prompts, SDK, and runtime
  versions are pinned per deployment.
- Upgrades pass recorded replay and containment tests before activation.
- Quota exhaustion produces a fixed host-authored notice and no provider change.

The configured Discord channel maps to one continuing main Codex session. The
kernel coordinates provider lifecycle through an opaque `SessionRefPort`; its
Jarvis adapter persists the `AgentSessionRef` and immutable agent-definition
fingerprint in private, atomically replaced runtime state outside PostgreSQL.
The fingerprint covers stable instructions, model and reasoning configuration,
kernel and runtime revisions, containment, and the session capability envelope;
per-run subset plans do not rotate the session.
`provider-runtime` performs the actual start, continue, resume, and discard. An
ordinary restart or compatible deployment attempts resume. A fingerprint
mismatch, invalid reference, or resume failure starts a fresh session. The
adapter scopes references by application thread and fingerprint and uses a
generation compare-and-set so a stale run cannot overwrite a newer reference.
Every successful store returns the next expected generation. A stale store
stops before tool dispatch or canonical settlement and fails the run; Jarvis
does not continue on provider state it failed to save.
After a crash leaves canonical input unprocessed, Jarvis discards any
speculatively advanced reference before replay unless alignment can be proved;
cold bootstrap is always the safe fallback. For a valid terminal model step,
the reference advances before the canonical conclusion/checkpoint transaction,
so a crash cannot commit history while leaving the next continuation behind it.

Recaller, rememberer, and dreamer invocations use fresh isolated sessions. They
MUST NOT share the main session or one another's history.

Jarvis owns product context selection and supplies canonical application data to
the kernel `ContextSourcePort`: stable instructions, bounded completed message
history, the current event and source timestamp, recalled memories with IDs and
timestamps when the owner-input recaller ran, granted capability descriptions,
the owner IANA timezone, and one host-generated `as_of` instant. The kernel
coordinates continuation and bootstrap assembly from these inputs. Rendering
uses `llm-tools` typed prompt sections; XML-like structure is presentation and
provenance, never a security boundary. Provider SDK message types appear only at
the provider-adapter boundary.

For a healthy main session, the continuation projection sends the current event,
current capabilities, `as_of`, and fresh recall only for owner input; stable
session context, including the owner timezone, and native history carry prior
turns. For a fresh Codex session, the bootstrap projection also includes stable
instructions and bounded canonical history. The same bootstrap projection MUST
remain usable by a future stateless or API-backed provider without replacing
product context selection. V1 implements no such second provider. The current
batch is sent only on its first provider call in that session; later
tool/protocol continuations send new observations or corrections without
repeating it. A replacement cold bootstrap includes unresolved input exactly
once in the replacement session.

The current owner message appears exactly once and is excluded from completed
history. Source messages retain `created_at`. A cognitive session receives the
owner timezone once when it opens. Each owner turn or background job receives one
authoritative `as_of`; tool-loop continuations and embedding calls receive no
repeated clock. Stable prompt material precedes dynamic time in a rendered
provider request.

Native session history, compaction, and cache behavior are optimizations, not
canonical state or guaranteed cost properties. Canonical messages plus recall
MUST always be sufficient to start again.

For the main application thread, Jarvis implements the kernel
`InputCheckpointPort` using existing message state and single-process
coordination. A claim carries the row-derived `interactive` or `proactive-read`
run class and its bound frozen plan. It receives only the maximal contiguous
ordered waking-input prefix of that class plus an opaque consumed watermark. If
the requested class does not match the first unprocessed row, the adapter arms
the correct class and returns `pending_input` without a provider call. A
terminal conclusion and `processed_at` checkpoint commit atomically. Before the
drain becomes idle, a compare-and-set transition verifies whether later waking
input arrived beyond the watermark. Compatible same-class input may continue;
an incompatible class forces an atomically armed defer even when limits remain.
If compatible input exists but limits are exhausted, Jarvis likewise arms its
in-process run queue before releasing the claim. Restart recovery still derives
the correct class from unprocessed owner or host-authored `message` rows and
scans them before the service can become idle. Checkpoint settlement returns
`continue`, `idle`, or `deferred`; an armed handoff produces `pending_input`.
Pending or uncertain actions conclude their proposing input but do not lock the
whole thread: compatible already-arrived input may continue and incompatible
input is handed off. This mechanism adds no table or column. Idempotent
cancellation/error cleanup applies the same arm-before-release rule whenever
the claim still owns an unprocessed waking row.
Jarvis's checkpoint finalization maps the terminal conversation conclusion and
`processed_at` to the existing atomic transaction. Read observations and
protocol correction stay turn-local; effectful outcomes are already durable
through `action` and `llm-tools`. The optional kernel event sink is best-effort
observability, not a canonical event store; emission is attempted before reuse,
but sink failure is nonfatal.

### 7.2 Embeddings

Embeddings use the `provider-runtime` OpenAI embedding port with a separate API
key restricted by the OpenAI project to the required embedding endpoint. The key
is unavailable to every Codex child and cognitive role.

Slice 0 MUST prove with a live negative test that the key cannot invoke a
generative endpoint. If that cannot be enforced, implementation stops for a new
decision rather than weakening the rule silently.

The deployment config pins one embedding model and vector dimension. V1 does not
store model identity per memory row and does not perform online mixed-model
migration. To change models:

1. Stop Jarvis.
2. Clear every embedding in one transaction.
3. Change the configured model and vector dimension through a migration if
   necessary.
4. Re-embed the complete corpus.
5. Run recall evaluation, then restart Jarvis.

An interrupted rebuild leaves null vectors and keeps the service stopped; it
cannot serve a mixed vector space. Lexical retrieval remains available during
ordinary embedding outages.

The complete memory corpus is disclosed to the embedding processor at ingestion
and rebuild time and incurs API cost. This is an accepted v1 trade-off.

### 7.3 Tool contracts and exact catalog

V1 exposes exactly the following canonical model tools:

| Tools | Granted role | Authority |
|---|---|---|
| `gmail.search`, `gmail.read_thread` | Main | Read; automatic |
| `gmail.create_draft`, `gmail.update_draft` | Main | Write; automatic |
| `gmail.send_draft` | Main | Write; approval required |
| `calendar.list_events`, `calendar.get_event` | Main | Read; automatic |
| `calendar.create_event`, `calendar.update_event`, `calendar.delete_event` | Main | Automatic only for a no-attendee event on a verified owner-only calendar; otherwise approval required |
| `maps.search_places`, `maps.get_place`, `maps.directions` | Main | Read; automatic |
| `web.search`, `web.read` | Main | Public-Web read; automatic |
| `schedule_wake` | Main | Write; automatic |
| `memory.search`, `memory.open` | Recaller, rememberer, dreamer | Read; automatic |

The table defines each role definition's maximum capability envelope. An
`interactive` owner-input or action-resolution main run receives the full Main
plan. A `proactive-read` scheduled-wake run uses the same continuing definition
but receives only the catalogued Gmail, Calendar, Maps, and public-Web reads.
Each internal one-shot plan contains exactly `memory.search` and `memory.open`.
Every plan is frozen for its run and may never exceed its envelope.

The main agent receives recalled memory but no memory tool. Internal cognitive
roles receive no Gmail, Calendar, Maps, Web, scheduling, or Discord capability.
No role receives `tool.search`, `tool.read`, a local-filesystem tool, a Gmail
organization tool, or a model-callable Discord tool.

Jarvis declares and binds its Gmail, Calendar, Maps, schedule, and memory tools
in this repository. The pinned `llm-tools` revision already supplies the
portable `web.search` declaration and Brave binding plus the bounded public-Web
`web.read` declaration and reader. Jarvis composes and grants those Web tools and
owns their credential, information-flow policy, and run budgets.

`web.search` sends a bounded query to Brave. `web.read` accepts one public
HTTP(S) URL and returns bounded inert text; it sends no cookies or application
credentials, executes no JavaScript, loads no subresources, persists no page,
and rejects credential-bearing URLs, private/link-local/loopback destinations,
unsafe redirects, unsupported media, and oversized responses. Web observations
are untrusted evidence, never instructions or authority. Unmistakable credential
material is rejected from Web arguments rather than sent. V1 does not implement
authenticated browsing, browser automation, or JavaScript rendering.

`gmail.send_draft` arguments contain the provider draft ID, known thread
identity, and the exact To/Cc/Bcc, subject, and body snapshot shown for approval.
Immediately before send, the host verifies that the live draft still matches
that snapshot; a mismatch fails the action and requires a new proposal.

For `calendar.create_event`, the host derives the Google event ID as the first
32 lowercase hexadecimal characters of
`SHA-256(UTF-8("jarvis-calendar-v1:" + canonical_text(action.id)))`. The
resulting 128-bit identifier satisfies Google's event-ID alphabet and is neither
model-authored nor stored as a new field. A timeout or provider duplicate
response is reconciled by reading that exact event ID and comparing the
binding's normalized writable event projection with the immutable action
arguments. A match is success; a conflict is never overwritten or retried
blindly. Calendar update and delete reconcile through their known provider event
ID and live state under the same rule.

`schedule_wake` uses one closed tagged schema: create with an exact
`execute_after` instant and instruction, or cancel with the target queued wake's
action ID. Cancellation cannot target an executing or terminal action.

`llm-tools` supplies contracts, capability profiles, typed prompt sections,
validation, tool-execution budgets, effect identity, replay semantics, and the
two portable Web tools. It does not supply Jarvis's application-specific
integrations or the agent run loop.

Reads need no action row. Effectful tool calls create an `action` before
execution and use its ID as their durable effect identity. Canonical message and
memory transactions are host bookkeeping and do not pass through `llm-tools`.

### 7.4 Model step protocol and bounded drain

The kernel accepts exactly one strict discriminated step per model response:

```text
call_tools
  calls:
    unique turn-local call_id
    canonical granted tool ID
    validated arguments

say
  Discord-ready text

finish
  optional internal reason
  result required only by a closed structured output contract
```

Unknown fields are rejected. The kernel and `llm-tools` validate the complete
step and every contained call before any call dispatches; there is no partial
`say` or partial effect from a structurally invalid step. Protocol-invalid
output performs no effect and becomes bounded corrective context. Exhausting
the correction or run budget fails the run with a typed terminal outcome. The
main conversational definition forbids `finish.result`. Each internal
structured definition forbids `say` and requires `finish.result` to match its
frozen closed schema.

`call_tools` contains no user-facing text. It returns typed observations
correlated by `call_id`, then the kernel continues the model loop within
configured step, tool-call, wall-time, and usage bounds. Only after observing
those outcomes may the model produce a separate truthful `say`. A `say` step
concludes the current input visibly. `finish` concludes it silently
or returns the validated result of an isolated structured role to host code.
The model never classifies a call as automatic or approval-bearing. Jarvis host
policy classifies every granted tool and supplies the kernel dispatch port. An
ungranted or malformed call fails before integration code. Dispatch outcomes
are `executed`, `pending_approval`, `denied`, `failed`, or `uncertain`; the
kernel does not select them. `pending_approval` and `uncertain` produce a
host-referenced waiting conclusion for the proposing input. Jarvis persists and
resolves actions outside the model loop; its later host-authored resolution
message starts a new input batch correlated by action ID.

The grammar has no approval preview. Host rendering is specified in section 5.3.

### 7.5 Codex containment

Codex receives no connector, Brave, or embedding credentials, generic shell,
writable project checkout, MCP server, or direct execution-authority tool
channel.

Sessions use the pinned native feature-disable option, an empty read-only working
directory, disabled network, approval mode `deny`, no MCP, and the allowed-tools
sentinel required by the pinned route. The native Codex web-search option remains
disabled.

An `AgentToolUse` event fails the confined turn. Native passthrough events such
as reasoning deltas and planning items do not. An attempted-and-denied native
tool event may therefore end a healthy confined session; it performs no effect.

The Linux deployment SHOULD run Codex under a dedicated unprivileged OS user.

### 7.6 Concurrency

Exactly one Jarvis service instance owns a deployment. A PostgreSQL advisory lock
at startup prevents overlap.

Within that one process, an ordinary in-process mutex allows at most one
cognitive run at a time, and the kernel input-checkpoint port grants at most one
exclusive drain for the main application thread. Foreground owner work takes
precedence over rememberer and dreamer work. Kernel cancellation stops
background cognitive work at a defined boundary; the work may be retried if
owner input arrives.

No second PostgreSQL conversation lock is required while the global ownership
lock holds.

## 8. Technology choices

- Server language: Python 3.12.
- Agent runtime: pinned `llm-agent-kernel`, imported as `llm_agent_kernel`.
- Database: PostgreSQL with full-text search and pgvector.
- HTTP/schema: FastAPI and Pydantic v2 when a new HTTP surface is needed.
- Persistence: Psycopg 3, SQLAlchemy 2, and Alembic.
- Discord: reuse the working single-channel transport; use `discord.py` 2.7.1
  for Gateway and interactions, and a narrow `httpx` Discord REST v10 Create
  Message binding for `enforce_nonce` until a qualified public client API exposes
  it.
- Google: reuse the working Gmail, Calendar, Maps, OAuth, and client stack.
- Public Web: reuse `llm-tools` `web.search` with its Brave adapter and
  `web.read` with its bounded safe reader.
- Scheduling: systemd timer or a small ordinary process timer.
- Testing: pytest, Hypothesis where useful, library-supplied test doubles, and
  synthetic or redacted connector fixtures.
- Deployment: one always-on Linux host and PostgreSQL.

Do not add DBOS, Temporal, Restate, Celery, LangChain, LlamaIndex, CrewAI,
AutoGen, another general agent framework, a program-agent runtime, Redis, Kafka,
Kubernetes, Elasticsearch, Neo4j, a separate vector database, or a general MCP
bridge in v1.

Initial dependency baseline:

- `llm-agent-kernel`:
  `d691f066142586a5a79c381d97163d90e66d8d76`
- `llm-calling` / `provider-runtime`:
  `a5d9c8e0c1c851daee0731554e0a4a326d3c2819`
- `llm-tools`: `8df458a199703120005296ae12f997b39d208fed`

All three MUST be git dependencies, not path dependencies. Jarvis MUST NOT modify or
restore the user's existing library worktrees.

The host and PostgreSQL run in UTC. Owner-local time comes from required IANA
timezone configuration included once when each cognitive session opens. The
context port adds one host-generated `as_of` instant per claimed owner-input
batch or background job and reuses it unchanged through that batch's tool loop;
embedding calls receive none. Stable prompt material precedes the changing
instant.

## 9. Persistence

Jarvis owns exactly four application tables.

```text
message
  id
  role
  text
  source
  source_conversation_id
  source_message_id
  created_at
  processed_at
  remembered_at
  trace

memory_log
  id
  text
  created_at
  embedding

memory_summary
  id
  text
  source_memory_ids
  created_at
  embedding

action
  id
  tool_name
  arguments
  status
  execute_after
  origin_message_id
  approval_message_id
  created_at
  decided_at
  completed_at
  result
```

These are the exact v1 application columns. Database-generated search columns
and Alembic's migration bookkeeping are physical infrastructure, not application
state. Changing this roster, adding an application table, or adding a semantic
memory field requires an ADR.

### 9.1 Message

`message` is canonical conversation history.

- `role` is exactly `owner`, `assistant`, or `host`; `host` is reserved for
  application-authored waking facts such as action resolutions and is never
  presented as owner speech.
- `(source, source_message_id)` is unique when a source ID exists.
- Owner messages are inserted before their turn with `processed_at = NULL`.
- Host action-resolution messages are inserted idempotently from terminal
  `action` state with `processed_at = NULL` and are never delivered to Discord as
  if the owner authored them.
- `processed_at` is set on a waking owner or host row only when its response,
  silent finish, or approval proposal is durably recorded.
- Assistant messages are inserted before delivery. A null `source_message_id` is
  the outbound retry watermark; a successful adapter delivery or history
  reconciliation fills it with the source platform's ID. The Discord nonce is
  deterministically derived from `message.id` and needs no column.
- `remembered_at` records completion of memory formation for an owner turn,
  including a successful decision to write no memories.
- `trace` is bounded JSON on the owner row containing only recall candidate IDs,
  selected memory IDs, created memory IDs, and provider trace IDs. It contains no
  prompts, model prose, message copies, tool arguments, or private payloads.
- Tool payloads do not belong in conversation text solely for debugging.

V1 has no internal `conversation_id` and no `conversation` table. Recent local
context groups by `(source, source_conversation_id)`; in v1 the source
conversation ID is the one configured Discord channel. The field remains useful
as delivery provenance and a future client boundary without creating current
routing behavior. Durable memory is global. A future multi-client product may
add an internal conversation mapping when a second client demonstrates the need.

### 9.2 Action

`action` is the single ledger for effectful tool calls, scheduled wakes,
approval, execution, reconciliation, and receipts.

- Reads create no action row.
- Message persistence creates no action row.
- Raw memory and summary transactions create no action row.
- Automatic tool writes begin `queued`.
- Approval-bearing writes begin `awaiting_approval`.
- `id` is the durable effect identity.
- `tool_name` is a stable canonical identifier such as `gmail.send_draft`; v1
  does not require version suffixes.
- `tool_name`, `arguments`, and `origin_message_id` are immutable after insert.
- `arguments` is the sole source of the model-proposed and user-visible effect
  payload used for approval rendering and execution. `id` is the only additional
  input to a deterministic provider effect identity such as the Calendar event
  ID; it cannot change the approved payload.
- Host code resolves the current declaration and validates stored arguments
  again before approval rendering and immediately before execution.
- `execute_after` is nullable; null means immediately eligible, while a timestamp
  supports `schedule_wake` without another table.
- `approval_message_id` is nullable and unique when present. It points to the
  host-owned approval `message` and is required while status is
  `awaiting_approval`.
- State claims commit before external calls.
- `decided_at` records an owner approval, denial, or cancellation decision.
  `completed_at` is set when the action reaches `succeeded`, `failed`,
  `uncertain`, or `cancelled`.
- `result` stores a typed provider receipt, failure evidence, cancellation
  reason, or uncertainty evidence without secrets.

Queued or approval-bearing rows whose `tool_name` is unsupported or whose stored
arguments no longer validate fail closed as `cancelled` and are reported. An
existing name MUST remain backward-compatible while a non-terminal action uses
it. Before an incompatible schema or semantic change, the deployment owner
resolves or cancels those actions. A future incompatible implementation MAY earn
a distinct versioned successor name; v1 stores no general version registry or
contract digest. Because immutable arguments remain available, derived hashes
can be computed later if measured need justifies them.

The action ledger must not become a duplicate message or memory store.

### 9.3 Other state

Existing connector credentials, cursors, and adapter state remain in their
current owned stores. Owner/guild/channel identity and the paused flag live in
deployment or host configuration. The main `AgentSessionRef` and immutable
agent-definition fingerprint live in private runtime state outside PostgreSQL
through the kernel `SessionRefPort`. Provider session state is non-canonical,
rebuildable, and excluded from required backups. Alembic may own its migration
table.

## 10. Existing integrations

V1 reuses the working Discord, Gmail, Google Calendar, and Google Maps
integrations.

Slice 0 records for each reused connector and the Web family:

- Callable operations and schemas, with Discord limited to configured-channel
  transport operations rather than a model tool family.
- Credential location and owning process.
- Safe credential reuse or handoff.
- Read and write behavior.
- Existing tests.
- The smallest Jarvis-owned `llm-tools` declaration and binding for each
  application tool integration, plus the exact composed `llm-tools` Web
  bindings.
- The pinned `llm-agent-kernel` port/conformance contract and the Jarvis-owned
  product-context, session-reference, input-checkpoint, dispatch, and event
  adapters.

The qualification report MUST also contain the exact v1 tool manifest from
section 7.3, live authority classification, Discord enforced-nonce/history
findings, Calendar ACL and client-ID findings, Gmail draft/send/reconciliation
findings, credential ownership and handoff plan, and proof that Codex cannot
access connector, Brave, or embedding credentials.
Implementation MUST NOT proceed beyond Slice 0 until the owner signs off that
report. Authorization to perform Slice 0 is not acceptance of findings that have
not yet been observed.

Credential discovery first inspects Ariel's existing operator configuration,
without importing Ariel application code. If a required credential is absent
locally, a delegated read-only audit MAY inspect the user-owned repository on the
development server and return only credential locations and integration shape,
never secret values in model context or ordinary logs. An operator or delegated
execution agent transfers selected credentials by a non-echoing filesystem or
service-manager operation directly into Jarvis's mode-0600 credential files.
If a required credential is absent from both locations, Slice 0 remains open;
Jarvis does not silently create a provider account or authorization.

Each credential has one owning process. Jarvis MUST NOT share one Discord bot
token with another running Gateway client, and two autonomous agents MUST NOT act
on the same mailbox or calendar concurrently.

Jarvis does not port unrelated Ariel agent, memory, prompt, orchestration, or
product-domain code.

## 11. Operations and quality

- Secrets remain outside model context, PostgreSQL, fixtures, and ordinary logs.
- PostgreSQL and private service ports are not publicly exposed.
- Backups run at least daily, include all four application tables and required
  connector state, and retain an encrypted off-host copy.
- A restore test occurs before acceptance and proves raw memory plus conversation
  history survive and derived memory can be rebuilt.
- A database backup alone is insufficient to act as the owner; credentials are
  re-supplied separately.
- Jarvis uses live tools for current external state and distinguishes that state
  from recalled memory.
- External success comes from a provider receipt or reconciliation evidence,
  never a model assertion.
- Failed and uncertain actions are reported honestly.
- Ordinary logs exclude credentials, private message bodies, raw email bodies,
  and complete memory text.

## 12. Definition of done

V1 is complete when every mandatory criterion in
[docs/acceptance.md](docs/acceptance.md) passes on the intended Linux deployment
using the real personal integrations and subscription-backed Codex account.

Acceptance includes:

- Natural single-channel Discord conversation, compatible-session resume, and
  lost-session context reconstruction.
- Live Gmail, Calendar, and Maps use.
- Live public-Web search and page reading.
- Memory formation, fresh-session recall, dreaming, and complete rebuild.
- Automatic personal calendar work.
- Host-rendered approval and one exactly-once approved email send.
- At least seven days of owner use producing genuine cognitive offloading.

## 13. Change control

Frozen decisions:

- One visible Jarvis and natural Discord interaction.
- One configured Discord channel with no v1 server-organization tools.
- Exactly four application tables.
- Central conversation history with a persistent, provider-deduplicated Discord
  outbox and delayed history reconciliation.
- Product-selected canonical context through the provider-neutral kernel ports;
  reusable but non-canonical provider sessions.
- Existing Google and Discord integrations are reused.
- The exact minimal v1 tool catalog in section 7.3.
- Only owner-requested `schedule_wake` actions initiate user-facing proactive
  turns.
- Python, PostgreSQL, pgvector, `llm-agent-kernel`, `provider-runtime`, and
  `llm-tools`.
- Immutable raw memory plus rebuildable summaries and indexes.
- No action rows for canonical message or memory transactions.
- No explicit personal-domain object model.
- No workflow framework, general agent platform, task delegation, or
  model-generated program runtime beyond the bounded kernel.
- Host-rendered approval previews and the stated autonomy boundary.
- Unversioned canonical v1 tool names with immutable stored calls and
  deployment-time compatibility discipline.
- No v1 redaction or destructive memory consolidation.
- No Android, OnePassword, Nexus, Skidbladnir, or other unlisted application
  integration.

Changing one requires an ADR stating observed evidence, migration impact, and
the acceptance criteria affected.

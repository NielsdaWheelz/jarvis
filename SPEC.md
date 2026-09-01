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

1. Provide a natural ongoing relationship in a dedicated Discord server.
2. Reuse the user's working Discord, Gmail, Google Calendar, and Google Maps
   integrations without avoidable reauthorization.
3. Persist conversation history independently of Discord and provider sessions.
4. Recall relevant durable memory before every owner-authored human input.
5. Append useful durable memories after completed owner turns.
6. Preserve raw memories while treating summaries, embeddings, and indexes as
   rebuildable.
7. Combine keyword and semantic memory search.
8. Use tools to answer and act rather than merely explain how work could be done.
9. Act automatically for reads, ordinary reversible work, and work confined to
   the user's resources.
10. Ask only for Approve or Deny at the defined external-authority boundary.
11. Remain inspectable enough to diagnose bad recall, failed tools, and duplicate
    or uncertain actions.
12. Remain small enough that one engineer can understand the complete system.

## 3. Non-goals

V1 MUST NOT add:

- Multiple users, tenancy, or public hosting.
- Android or another custom client.
- Voice interaction.
- A visible organization of agents.
- People, project, task, commitment, decision, episode, claim, procedure, or
  knowledge-graph domain models.
- A workflow or agent framework.
- A general-purpose remote shell, SSH, terminal, or unconstrained browser agent.
- Web search or web browsing.
- OnePassword, Nexus, or Skidbladnir integration.
- Autonomous purchasing, financial activity, credential changes, or destructive
  remote execution.
- Slash commands, dashboards, or speculative action components.
- Autonomous modification of prompts, permissions, code, or deployment.

Deferred integrations are recorded in the implementation plan.

## 4. User experience

### 4.1 Discord is Jarvis's home

Jarvis MUST live in a dedicated private Discord server owned by the user. The
server contains only the owner, Jarvis, and explicitly trusted supporting bots.

Jarvis MAY automatically:

- Create, rename, reorder, and archive channels or threads.
- Send, edit, organize, and delete messages it authored, except host-owned
  approval messages.
- Use ordinary text, Markdown, links, and code snippets.
- Proactively message the owner under section 4.4.

Jarvis MUST archive rather than delete channels or threads in v1. The server is
small and private; accumulating archived channels is an accepted cost.

The bot MUST NOT hold `ADMINISTRATOR`, membership, invite, role, webhook, ban,
kick, moderation, or guild-management permissions. Its role grants exactly:

- `VIEW_CHANNEL`
- `SEND_MESSAGES`
- `SEND_MESSAGES_IN_THREADS`
- `CREATE_PUBLIC_THREADS`
- `CREATE_PRIVATE_THREADS`
- `MANAGE_THREADS`
- `MANAGE_CHANNELS`
- `MANAGE_MESSAGES`
- `ATTACH_FILES`
- `READ_MESSAGE_HISTORY`
- `ADD_REACTIONS`

`EMBED_LINKS` is deliberately absent, so Discord does not automatically unfurl
links Jarvis posts. Jarvis may still post ordinary clickable links. Normal model
output is text; host code MUST NOT translate a model-supplied rich-content object
into an embed, attachment, or interaction component. The host-owned approval
renderer in section 5.3 is the deliberate exception for a plain-text payload
attachment and Approve or Deny components.

Jarvis identifies the owner by stable Discord user ID. A message or component
interaction from any other identity MUST NOT control tools or approvals.

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
Provider sessions are disposable and reconstructable from centralized messages
plus recalled memory.

Inbound owner messages are stored before processing and deduplicated by their
source identity.

Outbound Jarvis messages use simple at-least-once delivery:

1. Insert the assistant message with `delivered_at = NULL`.
2. Deliver it through Discord.
3. Store the Discord message ID and set `delivered_at`.
4. Retry undelivered assistant rows after restart.

A crash after Discord accepts the message but before step 3 may produce duplicate
conversational text. This is accepted in v1. It MUST NOT duplicate an external
tool effect or approval-bearing action.

The host acknowledges an owner message and shows a typing indicator before model
work. V1 does not stream partial structured model output into Discord; a `say`
step is delivered only after its schema is valid.

### 4.4 Proactivity and stop control

V1 supports two non-human triggers:

- A due `schedule_wake` action.
- A periodic connector reconciliation tick.

Inbound email, calendar changes, Maps data, and non-owner Discord activity do not
directly start model turns. A proactive turn receives read and memory tools only.
It cannot perform writes or propose approval-bearing actions. Its only possible
external output is a normal message to the owner in the dedicated server.

Configured quiet hours delay proactive turns until quiet hours end. No mandatory
activity channel, batching subsystem, urgency classifier, or notification-budget
framework exists in v1.

Before recall or any model call, host code matches an owner message whose trimmed
content is exactly `stop` or `pause`, case-insensitively, and persists a paused
flag. While paused, Jarvis performs no tools, actions, proactive turns, or
dreaming. `resume` clears the flag. These controls do not involve the model.

## 5. Authority and approvals

### 5.1 Automatic operations

Jarvis acts without approval for:

- Internal and external reads.
- Memory retrieval, append, summary maintenance, and index rebuilding.
- Writes inside Jarvis's configured local workspace and database.
- Creating and editing email drafts without sending them.
- Ordinary email organization exposed by the reused integration.
- Creating, editing, moving, or deleting no-attendee events on an owner-only
  calendar.
- Discord messages and server organization within section 4.1.
- Other reversible housekeeping confined to the owner's own resources.

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
2. Insert one `action` row as `awaiting_approval`.
3. Render the exact action from the stored arguments.
4. On Approve or Deny, validate the context and atomically claim or resolve the
   stored row.
5. Immediately acknowledge the Discord interaction and disable its components.
6. Execute an approved action at most once and store its result.
7. Report success, failure, or uncertainty naturally.

The invoking Discord user, guild, and channel must match the stored action
context. Free-form text never counts as approval.

`executing` is lease-held. When a lease expires, the reconciler determines what
happened before any retry. `uncertain` is a terminal, non-retryable outcome for
an action whose external result cannot be proved. It does not block a later new
action with identical arguments.

The active states used by intent deduplication are only:

```text
ready
awaiting_approval
executing
```

Terminal states are:

```text
succeeded
failed
uncertain
denied
expired
superseded
```

Later evidence MAY amend the recorded result of an uncertain action and mark it
succeeded or failed, but it MUST never cause automatic re-execution.

### 5.5 Gmail send

Gmail send uses the provider's draft flow:

1. Create the exact draft automatically.
2. Persist its Gmail `draftId` and known thread identity on the action.
3. Request approval for sending that stored draft.
4. Send by `draftId` after approval.
5. On an ambiguous result, check whether the draft remains and inspect Sent mail
   before retrying.

The exact reconciliation behavior for new and existing threads MUST be verified
against the live integration in Slice 0. If reconciliation cannot establish an
outcome, the action becomes terminal `uncertain` and Jarvis tells the owner.

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
role with memory search and open tools only.

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
new raw memory strings as structured final output.

The rememberer should retain information likely to save future explanation:
preferences, decisions, unresolved intentions, persistent circumstances,
relationships, and useful lessons. It should omit chatter, secrets, full copies
of live resources, unsupported inferences, and redundant paraphrases.

If the rememberer fails, `remembered_at` remains null. A bounded sweep retries
unremembered completed turns. A successful run that chooses to write nothing
still sets the watermark.

### 6.5 Summaries and dreaming

`memory_summary` is a disposable interpretation of raw memory. Every summary
contains a non-empty list of supporting raw IDs. A summary built from summaries
flattens its lineage to raw IDs.

The dreamer is a bounded Codex role with memory search/open operations. It
returns a structured batch of summary insertions and removals; host code applies
the batch transactionally. Summary changes are canonical bookkeeping and create
no action rows.

The dreamer may find duplicates, contradictions, themes, stale summaries, useful
connections, and likely future context. It cannot modify raw memory, use external
tools, change instructions or permissions, edit code, or deploy itself.

Wiping every summary and embedding and rebuilding from `memory_log` MUST restore
a usable memory system against the fixed recall evaluation set.

### 6.6 Memory is evidence

A memory is a prior model-made recollection. It is neither live external truth
nor authority. Memory text never grants a permission, records operative consent,
changes the approval boundary, or becomes a system instruction.

Current questions about Gmail, Calendar, Maps, or Discord should use live tools.
Memory supplies relevance and history.

## 7. Model and tool runtime

### 7.1 Cognitive provider

All cognitive roles use subscription-backed Codex through the local
`provider-runtime` `AgentRuntime` lane.

- Authentication uses the personal local-account credential.
- No generative API-key fallback or silent provider fallback exists.
- Model IDs, reasoning levels, prompts, SDK, and runtime versions are pinned per
  deployment.
- Upgrades pass recorded replay and containment tests before activation.
- Quota exhaustion produces a fixed host-authored notice and no provider change.

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

### 7.3 Tool kernel

Jarvis declares its Gmail, Calendar, Maps, Discord, local, and memory-read tool
families in this repository and executes effectful application capabilities
through the pinned `llm-tools` kernel.

`llm-tools` supplies contracts, capability profiles, validation, budgets,
effect identity, and replay semantics. It does not supply Jarvis's integration
tools.

Reads need no action row. Effectful tool calls create an `action` before
execution and use its ID as their durable effect identity. Canonical message and
memory transactions are host bookkeeping and do not pass through the tool
kernel.

### 7.4 Model step protocol

The main agent returns one strict schema-validated step:

```text
call_tool
  calls:
    canonical granted tool ID
    validated arguments
  optional say text

say
  Discord-ready text

finish
  optional internal reason; sends nothing
```

The model never classifies a call as automatic or approval-bearing. Host code
classifies every granted tool. An ungranted or malformed call fails before its
binding.

The grammar has no approval preview. Host rendering is specified in section 5.3.

### 7.5 Codex containment

Codex receives no connector credentials, generic shell, writable project
checkout, MCP server, or direct execution-authority tool channel.

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

Within that one process, an ordinary in-process provider lease allows at most one
Codex turn at a time. Foreground owner work takes precedence over rememberer and
dreamer work. Background cognitive work may be cancelled and retried if owner
input arrives.

No second PostgreSQL conversation lock is required while the global ownership
lock holds.

## 8. Technology choices

- Server language: Python 3.12.
- Database: PostgreSQL with full-text search and pgvector.
- HTTP/schema: FastAPI and Pydantic v2 when a new HTTP surface is needed.
- Persistence: Psycopg 3, SQLAlchemy 2, and Alembic.
- Discord: reuse the working integration; prefer `discord.py` for new Gateway
  code if the existing integration has no established library.
- Google: reuse the working Gmail, Calendar, Maps, OAuth, and client stack.
- Scheduling: systemd timer or a small ordinary process timer.
- Testing: pytest, Hypothesis where useful, library-supplied test doubles, and
  synthetic or redacted connector fixtures.
- Deployment: one always-on Linux host and PostgreSQL.

Do not add DBOS, Temporal, Restate, Celery, LangChain, LlamaIndex, CrewAI,
AutoGen, Redis, Kafka, Kubernetes, Elasticsearch, Neo4j, a separate vector
database, or a general MCP bridge in v1.

Initial library pins:

- `llm-calling` / `provider-runtime`:
  `a5d9c8e0c1c851daee0731554e0a4a326d3c2819`
- `llm-tools`: `8df458a199703120005296ae12f997b39d208fed`

Both are git dependencies, not path dependencies. Jarvis MUST NOT modify or
restore the user's existing `llm-tools` checkout.

The host and PostgreSQL run in UTC. Owner-local time comes only from required
IANA timezone configuration, which is included in every model context.

## 9. Persistence

Jarvis owns exactly four application tables.

```text
message
  id
  conversation_id
  role
  text
  source
  source_conversation_id
  source_message_id
  created_at
  delivered_at
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
  intent_key
  tool_name
  arguments
  input_digest
  contract_revisions
  status
  attempts
  not_before
  lease_expires_at
  origin_message_id
  client_ref
  created_at
  decided_at
  completed_at
  result
```

Mechanical columns may change without creating a personal-domain model, but a
new application table or semantic memory field requires an ADR.

### 9.1 Message

`message` is canonical cross-client conversation history.

- `(source, source_message_id)` is unique when a source ID exists.
- Owner messages are inserted before their turn.
- Assistant messages are inserted before delivery and use `delivered_at` as the
  retry watermark.
- `remembered_at` records completion of memory formation for an owner turn,
  including a successful decision to write no memories.
- `trace` contains a bounded redacted record of recalled IDs, selected IDs,
  model steps, tool names, classifications, and appended memory IDs.
- Tool payloads do not belong in conversation text solely for debugging.

V1 needs no separate `conversation` table; conversation lists derive from
message rows.

### 9.2 Action

`action` is the single ledger for effectful tool calls, scheduled wakes,
approval, execution, reconciliation, and receipts.

- Reads create no action row.
- Message persistence creates no action row.
- Raw memory and summary transactions create no action row.
- Automatic tool writes begin `ready`.
- Approval-bearing writes begin `awaiting_approval`.
- `id` is the durable effect identity.
- `arguments` stores the exact validated call and is the sole source for approval
  rendering.
- `intent_key` is unique only across active states.
- `not_before` supports `schedule_wake` without another table.
- State claims commit before external calls.
- An expired execution lease triggers reconciliation, never blind retry.
- `result` stores the receipt or evidence supporting failure or uncertainty.

The action ledger must not become a duplicate message or memory store.

### 9.3 Other state

Existing connector credentials, cursors, and adapter state remain in their
current owned stores. Owner/server identity and the paused flag live in deployment
or host configuration. Provider session state is non-canonical. Alembic may own
its migration table.

## 10. Existing integrations

V1 reuses the working Discord, Gmail, Google Calendar, and Google Maps
integrations.

Slice 0 records for each:

- Callable operations and schemas.
- Credential location and owning process.
- Safe credential reuse or handoff.
- Read and write behavior.
- Existing tests.
- The smallest Jarvis-owned `llm-tools` declaration and binding.

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

- Natural Discord conversation and restart recovery.
- Live Gmail, Calendar, and Maps use.
- Memory formation, fresh-session recall, dreaming, and complete rebuild.
- Automatic personal calendar work.
- Host-rendered approval and one exactly-once approved email send.
- At least seven days of owner use producing genuine cognitive offloading.

## 13. Change control

Frozen decisions:

- One visible Jarvis and natural Discord interaction.
- Exactly four application tables.
- Central conversation history with at-least-once conversational delivery.
- Existing Google and Discord integrations are reused.
- Python, PostgreSQL, pgvector, `provider-runtime`, and `llm-tools`.
- Immutable raw memory plus rebuildable summaries and indexes.
- No action rows for canonical message or memory transactions.
- No explicit personal-domain object model.
- No workflow or agent framework.
- Host-rendered approval previews and the stated autonomy boundary.
- No v1 redaction or destructive memory consolidation.
- No Android or new service integrations.

Changing one requires an ADR stating observed evidence, migration impact, and
the acceptance criteria affected.

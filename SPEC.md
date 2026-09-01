# Jarvis v1 specification

Status: **Frozen baseline**

Date: **2026-09-01**

Audience: product, engineering, design, operations, and future coding agents

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

## 1. Product definition

Jarvis is a persistent personal assistant for one user. Its purpose is to return
the user's attention by remembering relevant context, using connected services,
performing ordinary work autonomously, and involving the user only when human
judgment or external authority is genuinely required.

Jarvis is one visible assistant. Rememberer, recaller, dreamer, and any other
specialized model calls are internal cognitive roles, not user-facing personas.

## 2. Goals

V1 MUST:

1. Provide a natural, useful ongoing relationship in a dedicated Discord server.
2. Reuse the user's already-working Discord, Gmail, Google Calendar, and Google
   Maps integrations without requiring avoidable reauthorization.
3. Recall relevant durable memory before every human input.
4. Append useful durable memories after completed interactions.
5. Consolidate memory into rebuildable summaries without losing raw memories.
6. Use keyword and semantic retrieval together.
7. Use tools to answer and act rather than merely explaining how the user could
   do the work.
8. Act automatically for reads, ordinary reversible work, and work confined to
   the user's own Jarvis environment.
9. Ask only for Approve or Deny when an action crosses the defined approval
   boundary.
10. Be inspectable enough to diagnose bad recall, bad memories, failed tools,
    and duplicate or unauthorized action execution.
11. Preserve centralized conversation history independently of any one client
    so future clients such as Android can share the same conversations.
12. Remain small enough that one engineer can understand the complete system.

## 3. Non-goals

V1 MUST NOT attempt to provide:

- Multi-user accounts, tenancy, or public hosting.
- A mobile application.
- Voice interaction.
- A visible agent organization or configurable cast of assistants.
- Explicit people, project, task, commitment, decision, episode, claim, or
  knowledge-graph domain models.
- A workflow framework or distributed workflow service.
- A general-purpose remote shell, SSH, terminal, or unconstrained browser agent.
- OnePassword, Nexus, or Skidbladnir integration.
- Autonomous purchasing, financial activity, credential changes, or destructive
  remote execution.
- A dashboard, command center, slash-command system, or speculative controls.
- Autonomous modification of prompts, permissions, code, or deployment.

The non-goal integrations are recorded as future slices, not rejected forever.

## 4. User experience

### 4.1 Discord is Jarvis's home

Jarvis MUST live in a dedicated private Discord server owned by the user. The
server is a workspace Jarvis may organize rather than a single fixed chat box.

Jarvis MAY automatically:

- Create, rename, reorder, archive, and delete channels or threads.
- Send, edit, organize, and delete its own messages.
- Use ordinary Discord text, Markdown, links, attachments, embeds, and code
  snippets when they improve communication.
- Proactively message the user when it judges the interruption worthwhile.

The bot MAY receive Discord Administrator permission in this dedicated server.
This is an accepted v1 trade-off. The server MUST contain only the user, Jarvis,
and explicitly trusted supporting bots. Adding other people changes the trust
assumption and requires review.

Jarvis MUST identify the owner by stable Discord user ID. Messages or component
interactions from any other identity MUST NOT control tools or approvals.

### 4.2 Conversation is natural

The user talks to Jarvis in ordinary language. Jarvis responds in ordinary
language appropriate to the content.

V1 MUST NOT introduce slash commands. A slash command may be added only after a
repeated real interaction demonstrates that natural language is materially
worse.

The only interactive action components in v1 are:

- **Approve**
- **Deny**

### 4.3 Behavior

Jarvis SHOULD be direct, calm, resourceful, and willing to act. It SHOULD avoid
ceremonial progress reports, needless menus, repeated confirmation, agent
theatre, and notifications without a plausible user benefit.

Reliability outranks personality. Silence is a valid outcome when nothing needs
the user's attention.

### 4.4 Centralized conversation history

Discord is a client and delivery surface, not the canonical conversation store.
Jarvis MUST persist every owner message and every Jarvis response in PostgreSQL.

The same conversation MAY later span Discord, Android, or another client using
one internal `conversation_id`. Provider-native sessions are disposable and MUST
be reconstructable from centralized messages plus recalled memory.

V1 does not need a separate `conversation` table. Conversation lists and history
are derived from `message` rows. A `conversation` table may be added later only
when concrete title, membership, archival, or empty-conversation requirements
justify it.

## 5. Authority and approvals

### 5.1 Automatic operations

Jarvis MUST perform the following without asking for approval when needed to
fulfil a request or an enabled proactive behavior:

- Internal and external reads.
- Keyword and semantic memory retrieval.
- Appending raw memories and rebuilding derived memory state.
- Writes inside Jarvis's own local workspace and database.
- Creating and editing email drafts without sending them.
- Ordinary email organization when exposed by the reused integration.
- Creating, editing, moving, or deleting personal calendar events that have no
  attendees other than the user.
- Discord messages and organization inside Jarvis's dedicated server.
- Other reversible housekeeping confined to the user's own resources.

### 5.2 Approval-required operations

Jarvis MUST request Approve or Deny before:

- Sending an email or message to another person outside the Jarvis server.
- Adding, removing, or notifying another attendee on a calendar event.
- Spending money or committing the user to a purchase.
- Revealing or transmitting a credential or secret.
- Irreversibly deleting or overwriting meaningful external data.
- Running destructive commands on another machine.

The explicit automatic-operation list is authoritative: management of Jarvis's
dedicated Discord server and the user's no-attendee calendar events remains
automatic even when an operation deletes or reorganizes those resources.

V1 SHOULD expose as few approval-bearing capabilities as possible. Initially,
email send may be the only such tool.

### 5.3 Approval semantics

Approval is deliberately simple:

1. Jarvis stores the exact proposed tool name and arguments in `action` with
   status `awaiting_approval`.
2. Jarvis renders a human-readable preview from the stored arguments and presents
   it with Approve and Deny buttons.
3. Approve atomically claims and executes that stored action at most once.
4. Deny marks it denied and performs no external action.
5. Success or failure is reported naturally in Discord.

For email, an ambiguous provider timeout MUST be reconciled against Sent mail
before any retry. The reused integration SHOULD attach a stable generated
`Message-ID` when it supports doing so.

Free-form text MUST NOT count as approval. The owner identity and action ID are
sufficient; v1 does not require a cryptographic action-hash protocol.

## 6. Memory

### 6.1 Principle

Jarvis memory is natural-language memory plus learned retrieval, not a hand-built
ontology. Raw memories are permanent; summaries and indexes are rebuildable.

The canonical schema is:

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

`embedding` is derived even though it is stored with its row. It MAY be null
during ingestion or a rebuild. Full-text indexes are also derived.

The system MUST NOT add memory categories, fact types, importance fields,
salience scores, source-authority scores, confidence dimensions, validity
intervals, conflict states, or personal-domain foreign keys in v1.

Recaller, rememberer, and dreamer are bounded agents, not single-shot prompt
transformations. Each MAY think across multiple Codex turns, make decisions,
invoke its allowed tools repeatedly, reformulate searches, and stop when it has
done enough. Their different tool sets enforce their roles.

### 6.2 Raw memories

The rememberer MUST only append to `memory_log`. A raw memory is a concise,
self-contained natural-language statement produced from working context because
it may improve future behavior.

Normal operation MUST NOT update or delete raw memory rows. Administrative data
erasure, if ever required, is outside the normal memory and consolidation path.

Raw memory text MAY contain stable external-resource references:

```xml
<refs>
  <ref uri="gmail://account/message/id">Related email</ref>
  <ref uri="gcal://account/event/id">Related calendar event</ref>
  <ref uri="maps://place/id">Related place</ref>
  <ref uri="discord://server/channel/message">Original discussion</ref>
</refs>
```

References are part of the natural-language memory, not foreign keys to Jarvis
domain tables. Recognized references SHOULD be openable through existing tools.
Malformed or unavailable references remain readable text and MUST NOT make the
memory unusable.

### 6.3 Summaries

`memory_summary` is a disposable materialized interpretation of `memory_log`.
Summary rows MAY be inserted, replaced, or deleted at any time.

Every summary MUST:

- Be supported by raw memories.
- Contain a non-empty set of `source_memory_ids`.
- Resolve directly to raw `memory_log` IDs.
- Flatten any summary-of-summary lineage to raw IDs.
- Preserve material disagreement or uncertainty present in its sources.

Deleting every summary and rebuilding from `memory_log` MUST restore a usable
memory system.

### 6.4 Recaller

The recaller MUST run on every owner-authored human input before the main agent.
It MUST:

1. Search both raw memories and summaries using PostgreSQL full-text search and
   semantic vector similarity.
2. Reformulate or issue multiple searches when useful.
3. Select or rerank the combined candidates using a Codex model call.
4. Return a small relevant context bundle, or an empty bundle.
5. Preserve memory IDs and timestamps.
6. Open supporting raw memories behind a summary when detail, conflict, or
   verification warrants it.

The main agent MAY receive explicit memory search/open tools later if observed
failures demonstrate that pre-turn recall is insufficient.

### 6.5 Rememberer

After a completed interaction, the rememberer receives the useful working
context and relevant existing memories. It returns zero or more raw memory texts.

The rememberer SHOULD preserve information with likely future utility: user
preferences, ongoing concerns, decisions, plans, relationships, useful tool
lessons, and context needed to interpret later events. It SHOULD omit ephemeral
chatter, redundant paraphrases, and information already adequately remembered.

The rememberer uses Codex and structured output, but the stored memory itself is
ordinary natural language. It MAY search and open existing raw memories and
summaries repeatedly before deciding to append zero or more raw memories.

### 6.6 Dreamer

The dreamer runs periodically after inactivity or on a simple system schedule.
It is an agentic Codex loop that may search and open raw memories and summaries
repeatedly before writing, replacing, or deleting derived summaries.

The dreamer MAY:

- Find duplicate, related, contradictory, or stale memories.
- Build or rebuild summaries.
- Connect distant memories.
- Prepare likely future context.
- Distill recurring preferences or successful procedures into natural-language
  summaries.
- Evaluate the quality of current recall and summaries.

The dreamer MUST NOT modify raw memory, execute external actions, alter
permissions, change prompts, edit code, or deploy itself.

## 7. Model and tool runtime

### 7.1 Provider

All v1 cognitive roles MUST use the Codex provider through the local
`provider-runtime` distribution from `llm-calling`.

- Authentication MUST use the personal subscription-backed Codex account.
- API-key fallback or silent provider fallback MUST NOT be introduced.
- Model IDs and reasoning levels are deployment configuration.
- A deployment MUST pin its selected model and runtime versions.
- Upgrades MUST pass replay and runtime-containment tests before becoming active.

### 7.2 Tool kernel

The local `llm-tools` library MUST define and execute Jarvis capabilities.

It owns:

- Canonical tool names and closed schemas.
- Capability exposure.
- Input and output validation.
- Budgets and invocation positions.
- Stable effect identity and replay behavior for writes.

Jarvis owns credentials, persistence, approvals, reconciliation, and user-facing
tool results.

### 7.3 Model boundary

Codex is a reasoning process, not the credential holder or execution authority.
The main agent SHOULD use a strict host-mediated step protocol:

```text
read | answer | propose_action | finish_silent
```

Host code validates the step, executes permitted tools through `llm-tools`, and
returns typed observations to the next model turn.

V1 MUST NOT give Codex generic shell access, a writable project checkout,
connector credentials, or direct write-authority MCP tools. Any unavoidable
native Codex tool event in the confined reasoning lane MUST be treated as runtime
drift and fail the turn safely.

## 8. Technology choices

### 8.1 Server

- Language: Python 3.12.
- Database: PostgreSQL with native full-text search and pgvector.
- API/schema layer: FastAPI and Pydantic v2 where a new HTTP surface is needed.
- Persistence: Psycopg 3, SQLAlchemy 2, and Alembic.
- Discord: reuse the working integration; `discord.py` is preferred for new
  Gateway code if the existing integration does not already choose a library.
- Google: reuse the working Gmail, Calendar, Maps, OAuth, and client stack.
- Scheduling: systemd timers or a small ordinary process timer.
- Telemetry: structured redacted logs and OpenTelemetry-compatible traces.
- Tests: pytest, Hypothesis where stateful or property testing pays for itself,
  and recorded/mocked connector fixtures.

Exact dependency versions belong in the eventual lockfile. They MUST be pinned
and updated deliberately.

### 8.2 Existing local libraries

Initial known-good references:

- `llm-calling` / `provider-runtime`: commit
  `a5d9c8e0c1c851daee0731554e0a4a326d3c2819`
- `llm-tools`: commit `8df458a199703120005296ae12f997b39d208fed`

The current local `llm-tools` checkout has user-owned staged deletions. Jarvis
implementation MUST use a clean worktree or pinned dependency and MUST NOT
restore, overwrite, or otherwise disturb that checkout.

The Codex runtime and SDK MUST remain lock-pinned until their effective native
tool, sandbox, environment, and event behavior has been qualified together.

### 8.3 Explicitly rejected v1 dependencies

- DBOS, Temporal, Restate, Celery, or other workflow frameworks.
- LangChain, LlamaIndex, CrewAI, AutoGen, or similar agent frameworks.
- Redis, Kafka, Kubernetes, Elasticsearch, Neo4j, or a separate vector database.
- A general MCP bridge unless measured tool-loop limitations justify it.

## 9. Persistence

Jarvis owns exactly four application tables:

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
  created_at
  decided_at
  completed_at
  result
```

### 9.1 Message

`message` is the canonical cross-client conversation history.

- `conversation_id` groups messages into a conversation without requiring a
  separate conversation record.
- `role` is `user` or `assistant` in v1.
- `source` identifies the originating client, initially `discord` and later
  potentially `android` or another client.
- `source_conversation_id` and `source_message_id` preserve external identity.
- `(source, source_message_id)` MUST be unique when `source_message_id` is
  present, preventing duplicate ingestion.
- Every inbound owner message MUST be inserted before its turn begins.
- Every Jarvis response MUST be inserted centrally as part of delivery.
- Tool calls and results do not belong in `message`; they belong in `action`.
- Learned context does not belong in `message`; it belongs in memory.

### 9.2 Action

`action` is the single durable ledger for tool calls that mutate an external
integration or local workspace. Reads do not create action rows. Canonical
transactions that append `message`, `memory_log`, or `memory_summary` do not
create redundant action rows.

Allowed statuses are:

```text
ready
awaiting_approval
executing
succeeded
failed
uncertain
denied
```

- Automatic writes begin as `ready` and execute without user input.
- Approval-required writes begin as `awaiting_approval`.
- Execution atomically claims either `ready` or `awaiting_approval` as
  `executing`; approval is what permits the latter transition.
- `id` is the stable effect/idempotency identity.
- `arguments` stores the exact validated call.
- `result` stores the final receipt or redacted result needed for recovery.
- State transitions MUST be atomic.
- A completed, denied, or already executing action MUST NOT execute again because
  of a retry or duplicate Discord interaction.

The action table replaces separate pending-action, tool-effect, execution, and
receipt tables.

### 9.3 Other technical state

Existing connector credentials, cursors, and adapter state remain in their
existing owned stores. Configuration, owner identity, and Discord server identity
SHOULD live in deployment configuration. Provider sessions remain in the
provider runtime's state and are non-canonical.

Migration tooling may create its own bookkeeping table. PostgreSQL indexes and
internal catalogs are not Jarvis application tables.

This section MUST NOT be used to recreate a structured model of the user's life
outside the four-table schema.

## 10. Existing integrations

V1 MUST reuse the working integrations for:

- Discord.
- Gmail.
- Google Calendar.
- Google Maps.

The first implementation slice MUST audit these integration surfaces through a
delegated review and document:

- Callable operations and schemas.
- Current authentication and credential location.
- Which credentials can be safely reused.
- Read and write behavior.
- Existing tests.
- The smallest adapter needed for `llm-tools`.

It MUST NOT ingest or port unrelated Ariel agent, memory, prompt, or orchestration
code. It SHOULD temporarily depend on a stable existing integration surface when
that avoids a risky rewrite or fresh provider authorization.

## 11. Operations

V1 targets one always-on Linux host.

- Provider and connector secrets MUST remain outside model context and ordinary
  logs.
- The Codex worker SHOULD use an empty, read-only workspace and isolated state.
- PostgreSQL and private service ports MUST not be publicly exposed.
- Backups MUST include centralized messages, raw memory, summaries, actions, and
  required connector state.
- A restore test MUST be completed before v1 acceptance.
- Summary and embedding rebuilds MUST be testable from preserved raw memory.
- A crash or retry MUST NOT send the same approved email twice.

The system does not need Kubernetes, multi-host failover, or formal SLOs in v1.

## 12. Quality rules

Jarvis MUST:

- Prefer using a relevant tool over guessing current external state.
- Distinguish retrieved memories from live service results.
- Avoid presenting a memory as proof that a current email, event, or place still
  exists unchanged.
- Preserve uncertainty expressed in memories.
- Avoid storing ordinary secrets in memory.
- Avoid flooding Discord or creating gratuitous channel structure.
- Surface failed or uncertain external actions honestly.
- Never claim that an external action succeeded solely because a model said so.

## 13. Definition of done

V1 is done only when every mandatory criterion in
[docs/acceptance.md](docs/acceptance.md) passes on a clean Linux deployment using
the existing personal integrations and subscription-backed Codex account.

Passing unit tests alone is insufficient. Acceptance includes a real end-to-end
conversation persisted independently of Discord, memory formation and recall,
summary reconstruction, automatic calendar behavior, and an exactly-once
approved email send.

## 14. Change control

The following are frozen architectural decisions:

- Natural Discord interaction with no slash commands.
- One visible Jarvis.
- Existing Google and Discord integrations are reused.
- Python, `provider-runtime`, `llm-tools`, PostgreSQL, full-text search, and
  pgvector.
- Exactly four application tables: `message`, `memory_log`, `memory_summary`,
  and `action`.
- Centralized conversation history independent of Discord and provider sessions.
- One append-only raw memory log plus rebuildable summaries and indexes.
- No explicit personal-domain object model.
- No workflow or agent framework.
- Automatic ordinary work; Approve/Deny only at the stated external-authority
  boundary.
- Android and new service integrations are deferred.

Changing one requires a new ADR describing observed evidence, the rejected
alternatives, migration impact, and corresponding acceptance-test changes.

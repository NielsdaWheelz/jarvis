# Jarvis v1 specification

status: **native runtime; frozen domain baseline**

date: **2026-10-02**

Audience: product, engineering, design, operations, and future coding agents

accepted native-agent cutover (2026-10-02):
[adr 0063](docs/decisions/0063-native-agent-supervision.md) adopts the shared
kernel native contract and its n4 application requirements. it supersedes the
affected baseline rules below: main uses native host-tool callbacks and public
progress, explicit per-input dispositions and three native journal tables;
stop/pause is canonical message control and cancels unentered approvals;
healthy sessions may be reused in-process, but owner/connection loss fences old
callbacks and cold-restarts reasoning. existing action/read uncertainty remains
a reconciliation barrier. cumulative native quotas and rolling paid-capacity
reservations are removed; operation limits, current owner authority, containment,
isolated cognitive roles and memory behavior remain. no memory or delegation
upgrade is included. all new behavior requires its target integration proof.

accepted universal-memory target (2026-10-01): the consolidated
[implementation contract](docs/universal-memory.md) defines the current target,
**not shipped behavior**. [adr 0062](docs/decisions/0062-simplify-memory-policy-and-retrieval.md)
records its latest simplification; adrs 0051 and 0053–0061 retain earlier rationale.
implement this contract directly rather than reconstructing an override chain.
the [single roadmap and implementation plan](docs/implementation-plan.md) owns
delivery order and cross-system dependencies; broader v2 direction there does not
silently supersede this specification. where affected, the memory contract
supersedes baseline sections 4–9, 11 and 13 as follows:

- one undivided corpus; independently declared lane admission and connection.
  three added tables (`memory_lane`, `source_conversation`, `source_record`),
  twelve total after the native cutover, with internal conversation identities
  and direct note provenance.
  one stateless collector per host, native histories as the local recovery source,
  one private listener inside jarvis and a bounded read-only database pool.
- automatic online activation after complete per-conversation baselining; immutable
  boundaries and complete-event uploads with atomic archive/checkpoint commits.
  native codecs validate consumed fields and ignore unrelated additive metadata;
  identities/digests exclude that ignored metadata too. unexpected rewrites or
  oversized events park capture for repair. no multipart upload or automatic historical reread.
- source-only, tool-free rememberer; native conversations batch by size/age into
  independent nonoverlapping episodes. atomic notes/bookmark replaces
  `message.remembered_at`, immediate extraction and per-row fallback.
- daily dreaming begins with bounded pending-note batches; summary mutations and
  clearing `memory_log.dream_pending` commit together, including empty success.
  rememberer and dreamer use transient kernel decisions; dreamer reads use
  run-local receipts. interrupted background computation may repeat and be charged
  again under normal admission. no frozen background scopes or paid-call recovery
  barrier. main/gate durable evidence and external effect recovery remain;
  current-owner permits replace paid-capacity accounting. canonical commit
  fencing still rejects late results.
- shared keyword/semantic candidates, identity deduplication and deterministic
  reciprocal-rank fusion through bounded search/open. callers choose when to search; remove the recaller,
  automatic pre-input recall and its isolated inference work. main's full and
  scheduled read-only plans can search/open; dreamer reads only notes/summaries.
  main's paid-read recorder and uncertainty barriers remain. required-stage
  failures are typed errors, not fallback ranking. no learned reranker or mcp
  status tool. search permits one external embedding attempt; the same client and
  inference gate serve queries/indexing/rebuild. one search rate limit covers all
  actual callers, while stored receipt replay costs no new service execution.
- agent definitions specify context, tools, goals and quality; agents choose
  their method. remove mandatory first searches, minimum call counts and scripted
  research/delegation procedures, including the dreamer completion gate. zero-call
  seed-only or empty success is valid. host protocol, authority, current-owner
  grounding, approvals, valid lineage and commit requirements remain binding.
- policy values and service ownership are global: declare shared constants once,
  reuse existing primitives and construct one set of settings/clients/pools at
  composition. no per-profile tuning or capacity allowances. provenance,
  permissions, progress and invocation receipts remain correctly scoped; each
  run receives fresh execution state from the common policy. current-owner
  permits remain the cognitive admission boundary.
- external `memory_save_note` and main's internal `memory.save_note(text)` use
  one canonical append. external saves require admit+connect and optional
  caller-reported conversation association; main saves require jarvis admission
  and host-owned identity. neither needs native activation or proven source range.
  internal save alone is exempt from 5.1/5.4/7.4's gate/action rules: `Write +
  ReDispatchable`, zero external attempts, existing native invocation position as
  invocation/effect id, narrow `read_position` recovery. recover committed saves
  before deadline checks; retry only proven absence with the original identity.
  no scheduled/background save grant or native cognition mcp access.
- all sources remain evidence, never authority. memory tool calls/results that
  could echo stored prose become content-free archive references. no forgetting,
  conversation exclusion, tombstones or erasure path. revocation stops new
  admission, not storage, recall or processing of existing material.
- one local pre-migration snapshot; historical imports/provenance reconstruction,
  off-machine backup and disabling native automatic memories remain deferred.
  preserve existing messages/notes/summaries. future work context is read-only
  dreamer input, not summary evidence; main owns work changes.
- retain only small capture/retry and memory-completion regression groups after
  focused verification. this scoped adr 0046 exception restores no old suite and
  leaves the general testing redesign open.

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

testing reset (2026-09-17): [adr 0046](docs/decisions/0046-reset-testing.md)
removes the existing tests, fixtures, evaluation corpus, and qualification
machinery. during this owner-accepted gap, earlier requirements to run automated
tests, repeated acceptance trials, replay proofs, or live qualification are
suspended as change/release gates. product behavior, runtime validation,
containment, authority, and recovery requirements remain binding. static and
build checks are the current verification surface; they do not establish
behavioral or live acceptance. the subsequent pr begins the
[testing redesign](docs/issues/testing-redesign.md).

the owner separately authorized the native cutover's temporary red/green/live
proofs under adr 0063. its shared N001–N020 acceptance and current evidence are
linked from [docs/acceptance.md](docs/acceptance.md#native-cutover-acceptance).
this exception restores no standing retired suite and claims no production
deployment or universal-memory acceptance.

retired delivery checklists, qualification reports and the completed cleanup log
live in git history. deleting those copies changes no runtime requirement or
acceptance result; current contracts, operations and unresolved issues remain.

integration contracts: [adr 0040](docs/decisions/0040-shared-kernel-durable-decisions.md)
retains isolated inference and read receipts; [adr 0052](docs/decisions/0052-cut-worker-control-to-current-skid.md)
owns current skid worker control. [adr 0063](docs/decisions/0063-native-agent-supervision.md)
replaces main's step loop, saved-session CAS, paid-capacity arithmetic and shared
cognition host with the native contract below. earlier adrs retain historical
rationale; they do not reinstate retired execution paths.

## 1. Product definition

Jarvis is a persistent personal assistant for one user. It exists to return the
user's attention by remembering relevant context, using connected services, and
performing ordinary work without requiring supervision.

Jarvis is one visible assistant. Recaller, rememberer, dreamer,
AutomaticWriteGate, and other model calls are internal cognitive roles, not
user-facing personalities.

## 2. Goals

V1 MUST:

1. Provide a natural ongoing relationship in one configured private Discord
   channel.
2. Reuse the user's working Discord, Gmail, Google Calendar, and Google Maps
   integrations without avoidable reauthorization.
3. Use bounded public-Web search only when the owner explicitly requests a Web
   search, and bounded page reading when the owner supplies or requests a page.
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
14. Bound provider work across crashes and repeated runs, not only inside one
    model loop.
15. Require every model-proposed write to be grounded in current owner-authored
    input before it can create an action or cross an approval boundary.

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
- A peer-agent ownership graph, task schema, completion scheduler, or general
  execution framework. owner-directed terminal agent interaction uses section 7.3.
- A general-purpose remote shell, SSH, terminal, or unconstrained browser agent.
- OnePassword or Nexus integration. skid owns terminals and agents on each host;
  jarvis consumes its current cli without a shell or duplicate provider control.
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
- Deliver ordinary text, Markdown, links, and code snippets from the
  host-rendered Main terminal result.
- Deliver proactive messages under section 4.4.
- Deliver host-rendered approval messages and plain-text payload attachments.
- Edit its own approval message to disable Approve and Deny after a decision.

These transport operations create no `action` rows. Jarvis has no v1 capability
to create, rename, reorder, archive, or delete channels or threads; manage other
messages; add reactions; or organize the server.

The bot must have these operational permissions:

- `VIEW_CHANNEL`
- `SEND_MESSAGES`
- `ATTACH_FILES`
- `READ_MESSAGE_HISTORY`

The reused deployment may retain its existing inherited non-management
permissions; exact role-level least privilege is not a v1 gate. It MUST NOT have
`ADMINISTRATOR`, guild/channel/message/thread/role/webhook management,
moderation, kick, or ban authority. This accepted overbreadth is not application
authority: no model-callable Discord tool exists, and the adapter implements no
invite, reaction, thread, poll, event, voice, application, membership, or
server-organization operation.

The integration enables exactly the `GUILDS`, `GUILD_MESSAGES`, and
`MESSAGE_CONTENT` Gateway intents. Direct-message, member, presence, and reaction
intents are absent; host filtering rejects thread events. Every Create Message
and content-bearing edit uses `allowed_mentions = {"parse": []}`. Every Create
Message sets Discord's `SUPPRESS_EMBEDS` flag; content-bearing edits retain it.
Ordinary clickable links still work, but Jarvis requests no displayed unfurl.
Normal model output is text. Host code MUST NOT translate a model-supplied
rich-content object into an embed, attachment, or interaction component. The
host-owned approval renderer in section 5.3 is the deliberate exception for a
plain-text payload attachment and Approve or Deny components.

### 4.2 Conversation is natural

The owner speaks naturally. Jarvis replies naturally using the Discord formats
appropriate to the content.

V1 has no slash commands. The only custom action components are:

- **Approve**
- **Deny**

Reliability outranks personality. Main's visible prose MUST use the owner-approved
voice: informal, thoughtful, dry, terse, precise, candid, willing to disagree,
explicit about uncertainty, and erudite when the subject warrants it. Prose is
lowercase except for all-caps emphasis and deliberate initial-letter
capitalization. Exact quotations, code, identifiers, URLs, names, titles, and
other case-sensitive source material retain accurate casing. Main MUST NOT use
horizontal rules or emojis. Bluntness MUST remain proportionate rather than
becoming reflexive abuse. Jarvis SHOULD avoid ceremonial progress reports,
needless menus, agent theatre, and notifications without plausible benefit.
Silence is a valid result.

Main MUST NOT call `web.search` unless the current owner input explicitly asks
for a Web search. It MAY automatically inspect authorized private sources such
as memory, Gmail, Calendar, and Maps when needed to answer or act. This is a
product-use rule in addition to the host's fixed capability and authority
boundaries.

main uses declared native callbacks and public commentary. useful progress and
partial findings commit to the canonical outbox before delivery; they do not
settle owner requests. typing remains an additional activity signal. main has no
`say`/`call_tool`/`finish` step decoder.

the closed `JarvisTerminal` root contains `response` and `input_outcomes`.
`response.type` is `answered`, `partial`, `needs_input`, `failed`, `silent`, or
`waiting`. the host renders it deterministically. `answered` has non-empty
`text`; `partial` has non-empty `text`, a
non-empty at-most-500-character `limitation`, and a nullable non-empty
at-most-500-character `question`; `needs_input` has at-most-1000-character
`context` and one non-empty at-most-500-character `question`; `failed` has one
non-empty `explanation`; and `silent` has only
`reason = owner_needs_no_response`; `waiting` has non-empty `text`. text and
explanation retain the existing
Discord response limit. The host renders complete answers unchanged and owns
the fixed labels for every other visible branch, checking the final rendered
Discord bound before persistence. model text is never silently cropped to fit.

final dispositions name delivered inputs as `complete`, `continue`, or `waiting`;
omitted requests keep their state. only `complete` closes a request. `waiting`
names an actual
`approval`, `external_reconciliation`, `owner_input`, or `configuration` blocker;
the first two require exact action references belonging to that request.
the host validates these references against current canonical state. topic
changes and partial answers retain unfinished work. host events and action
resolutions provide evidence, never fresh owner intent.

An incomplete typed collection observation cannot be rendered as `answered` or
`silent`. Jarvis conservatively renders it as a visible partial result with a
host-owned limitation. Semantic prose quality remains prompt- and
evaluation-governed; Jarvis MUST NOT add a phrase matcher or second-model critic.
The run-local evidence value contains only typed incompleteness reasons and
counts and is discarded at settlement/release. Visible terminal variants settle
as `conclusion_kind = conversation` with their type as the trace outcome;
`silent` settles as kind/outcome `silent`. Every settled owner variant remains
eligible for remembering.

### 4.3 Central conversation history

Discord is a client and delivery surface, not the canonical conversation store.
Every owner message and every Jarvis response MUST be persisted in `message`.
main may reuse a compatible healthy native session within one process. after
connection, process or owner loss, old callbacks are fenced and reasoning starts
in a fresh session from canonical requests, messages, recalled memory and
original tool receipts. native history is disposable.

Inbound owner messages are stored with `processed_at = NULL` before processing
and deduplicated by their source identity. On startup, the adapter MAY use
Discord history after the latest stored source message ID for bounded catch-up.
A terminal action also creates the idempotent host-authored waking row specified
in section 5.4. Owner and host rows share the same checkpoint mechanism; only
owner-authored Discord text is eligible for stop/pause/resume interception.
the native input adapter selects one bounded, non-empty batch and its frozen plan:
owner rows and `source = action` resolution rows receive the full Main plan,
while a `source = schedule_wake` row receives the read-only proactive plan.
Owner work has priority. Incompatible rows remain unclaimed for a later run;
the kernel has no run-class abstraction and never infers authority from text.
the original native terminal commits before application decoding. validated
input dispositions and any response commit atomically; an approval proposal
alone never completes its owner request. the transaction writes the settled run ID,
through-checkpoint, nullable conclusion-message ID, and conclusion kind/outcome
into bounded `trace` on every waking row consumed by the checkpoint. This is
diagnostic grouping metadata; immutable action lineage, not trace, governs
effect recovery.

Outbound Jarvis messages use a persistent outbox with recent-window provider
deduplication:

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
deduplication window. Slice 0 established that history and exact-message reads
may omit the nonce, so v1 does not claim nonce-based delayed-history
reconciliation. A retry believed to remain inside the window is automatic. A
later retry MAY resend the same persisted text with the same enforced nonce,
subject to a small finite retry/backoff policy selected and tested in Slice 1.

A null `source_message_id` remains the only outbound retry watermark. The nonce
derives from existing state, so this rule adds no column. Conversational
delivery is at least once: an ambiguous accepted create followed by a retry
outside Discord's window may rarely repeat ordinary text. This accepted failure
mode does not grant effect authority. Approval-bearing actions and external tool
effects retain their independent action-level barriers, so repeated presentation
cannot repeat an action.

on startup, fence old attempts before accepting callbacks. recover original
sealed terminals locally before current model/catalog/tool construction; later
stop/resume prevents stale product settlement. absent a seal, automatically
restart reasoning for pending requests under the current owner. this may repeat
model computation, never an unknown action or billed-once read. original
accepted actions and complete receipts remain authoritative even outside the
recent-observation window. `origin_message_id` is a stable root pointer, not
sufficient recovery authority. parked input remains operator-only.

public commentary and final output use distinct persisted messages. malformed
structured terminal output cannot be replaced with valid-looking final prose.

### 4.4 Proactivity and stop control

V1 has one user-facing proactive trigger: a due `schedule.wake` action created
from the owner's natural-language request. A wake becomes eligible at its exact
requested instant; if Jarvis was offline, it becomes eligible on startup. There
are no generic quiet hours, periodic connector polls, notification batching,
urgency classification, or autonomous inbox/calendar monitoring in v1.

Only a queued wake with a valid immutable `creation_receipt` in `result` is
eligible. When one is claimed, host code atomically moves it to
`executing` and inserts one waking `message` with `role = host`,
`source = schedule_wake`, `source_message_id = canonical_text(action.id)`, the
configured conversation ID, and `processed_at = NULL`. Its text is rendered from
the immutable validated action arguments and includes the original instruction
and requested instant. This is distinct from an action-resolution message and is
idempotent across restart. The main run receives the normal read-only proactive
capability plan. Persisting its visible conclusion (or the deterministic fallback
below) and marking the wake `succeeded` occur in the same transaction; an
interrupted due-wake row is safe to resume without recreating the action.
The terminal transaction appends a separate `wake_outcome` to `result`; it never
overwrites the creation receipt returned by the original tool call.

The canonical tool and `action.tool_name` are `schedule.wake`. The distinct
host protocol discriminator remains exactly `message.source = schedule_wake`.

Inbound email, calendar changes, Maps data, and non-owner Discord activity do not
directly start model turns. A proactive turn receives the scheduled-wake event
and the catalogued read tools only; it does not invoke the owner-input recaller.
It cannot perform writes or propose approval-bearing actions. Its only possible
external output is a normal message to the owner in the configured channel.

Dreaming may run silently on an idle/system timer. It is derived-memory
maintenance, not a user-facing proactive turn.

At ingress, host code matches an owner message whose trimmed content is exactly
`stop` or `pause`, case-insensitively, commits canonical control, targets the
current unfinished requests, fences old callback authority and cancels queued
work and unentered approvals in the same conversation/action lock order used by
consent and effect entry. it signals cancellation and persists the stopped
notice without a model call. entered effects still settle or reconcile truthfully.
while paused, no new reasoning, tools, actions, proactive turns or dreaming start;
ingress, delivery and entered-effect recovery remain available. `resume` restores
eligible requests through canonical control. cancelled approval identities never
execute later; resumed work requires fresh consent. no file-backed pause exists.

## 5. Authority and approvals

### 5.1 Automatic operations

Every model-proposed `Write` passes the owner-grounding gate below before Jarvis
creates an action, displays an approval, or enters an executor. Approval policy
is a later independent host check; requiring approval never bypasses this gate.

Jarvis acts without approval for:

- The exact read tools in section 7.3.
- Memory retrieval, append, summary maintenance, and index rebuilding.
- Canonical message, action, and deployment bookkeeping in Jarvis's own database
  and private runtime state.
- `gmail.create_draft` and `gmail.update_draft`, without sending.
- Creating, editing, moving, or deleting no-attendee events on an owner-only
  calendar.
- Creating or cancelling a `schedule.wake`.
- owner-directed `agent.start`, `agent.send`, `agent.text`, `agent.keys`,
  `agent.stop` and `agent.close`, grounded by `AutomaticWriteGate`; explicit
  terminal input may answer worker permission dialogs under existing host-user
  authority. stop mode and close scope distinguish captured native work from
  exact terminal input and closure.
- Normal Jarvis responses and proactive owner notices through the configured
  Discord transport.

This list is exhaustive for v1 automatic writes. There is no local-filesystem
tool and no Gmail label, archive, trash, delete, or other organization tool.

An owner-only calendar is one whose live ACL grants access only to the owner.
The deployment records the verified owner-only calendar IDs. A calendar write
whose ACL is shared or unknown requires approval. Calendar write schemas carry an
explicit IANA timezone and reject naive datetimes.

The `AutomaticWriteGate` is a fixed Jarvis-owned isolated
`llm-agent-kernel` one-shot with an empty tool plan and a closed result:

```text
decision = allow | deny
supporting_owner_message_ids = ordered list of current owner input IDs
```

it runs only after the native callback, frozen binding, and arguments validate, and
before any `action` insert. It receives only:

- The ordered text and IDs of owner-authored inputs admitted through the current
  checkpoint. Host action-resolution and scheduled-wake text do not count as
  authority.
- The canonical proposed tool ID.
- A bounded host-normalized descriptor containing only allowlisted scalar fields
  needed to judge the operation, target, audience, and timing, including the
  owner timezone and current batch `as_of` when relative wording must be checked.
  Arbitrary bodies, connector text, and other free-form payloads are replaced by
  length and digest.

It receives no recalled memory, connector or Web result, tool observation,
model rationale, provider history, credential, or unbounded proposed payload.
`allow` is accepted only when the write is directly entailed by current owner
input, remains within its requested scope, and names a non-empty subset of the
actual current owner IDs. `deny`, ambiguity, invalid output, quota/admission
denial, or gate failure creates no action and dispatches nothing.
for agent writes, a completed denial or absent current owner input returns the
declared `AgentFailure` with `code=policy_denied` and `dispatch=not_sent`.
an unavailable preflight or failed gate returns `code=write_check_unavailable`
with the same dispatch classification. other writes retain their existing
common `ToolUnavailable` result. content-free diagnostics identify the stage,
tool, model decision, gate outcome or exception class; never exception text,
owner input, arguments, or provider content. this scoped 2026-09-13 correction
distinguishes agent authorization from availability without changing authority.

The gate cannot widen the frozen plan or override deterministic policy such as
owner-only Calendar ACLs and approval requirements. Its contract/prompt/model
revision is covered by `policy_revision`, and an allowed action stores the
supporting owner IDs in its immutable execution contract. This second model is
an intentionally narrow prompt-injection defense, not a proof system: directly
adversarial or ambiguously quoted owner text can still cause a false allow or
false deny. V1 accepts the added write latency and evaluates this boundary
adversarially rather than building a provenance type system.

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
callback input and no preview column in `action`.

For email, the host-rendered material shows every To, Cc, and Bcc address, the
subject, and the complete body. Long content MAY be split across host-owned
messages or placed in a host-generated attachment; the final host-owned message
carries Approve and Deny and clearly identifies the preceding material as the
complete payload.

The v1 implementation uses one bounded host-generated UTF-8 text attachment for
every supported approval, including short ones. It contains a deterministic
JSON rendering of the action ID, canonical tool name, and every validated stored
argument; JSON string escapes preserve the exact stored text. The short
component-bearing message identifies that attachment as the complete payload.
The attachment is limited to 1,000,000 bytes. Oversize or non-exact rendering
fails before action creation or functional component presentation.

An approval-bearing tool without a host renderer fails closed. A model rationale
MAY be shown as separately labelled commentary but never substitutes for the
rendered action.

Messages carrying Approve or Deny are host-owned. Model-originated tool calls
cannot edit or delete them. After the host claims or denies the interaction, it
disables the components before any slow external work begins.

### 5.4 Approval execution

Approval is deliberately simple:

1. Validate the proposed tool and arguments.
2. Run `AutomaticWriteGate`; stop with no action unless current owner input
   directly supports the proposed effect.
3. Insert one `action` row as `awaiting_approval`, including its immutable
   execution contract, plus its host-owned approval `message`, in one
   transaction.
4. Store that message's internal ID as `approval_message_id` and render the exact
   action from the immutable stored arguments.
5. On Approve or Deny, validate the context and atomically claim or resolve the
   stored row.
6. Immediately acknowledge the Discord interaction and disable its components.
7. Execute the approved action through its occupied durable position and store
   its result; repeat only after reconciliation proves the effect absent.
8. Insert one idempotent host-authored action-resolution `message` and let the
   main agent report success, denial, failure, or uncertainty naturally.

The invoking Discord user, guild, and channel must match deployment
configuration. The interaction's Discord message ID must match the `message`
referenced by `approval_message_id`. Each opaque custom component ID binds the
action ID, internal approval-message ID, and exactly one of Approve or Deny. Host
code validates that complete relationship and the current `awaiting_approval`
state before accepting a decision. Free-form text never counts as approval.

The durable state transition commits before the Discord acknowledgement. The
acknowledgement is a public `discord.py` interaction-response edit that disables
both components. Only then may slow external execution begin. If the process
stops after the claim or the acknowledgement fails, startup first disables the
known message through the narrow host Discord REST binding and then resumes the
approved action through its existing durable position; it does not replay the
originating model turn.

If a pending approval is incompatible at startup, a delivered message is first
disabled and the action is then cancelled and reported. An undelivered one is
cancelled without a Discord edit; its existing canonical outbox row is delivered
once with the complete former payload and only disabled Approve and Deny
components, followed by the ordinary cancellation resolution. It can never
become executable, and no pending outbox row is falsified or stranded.

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
actions. Every immutable execution contract contains a finite integer
`max_attempts >= 1`, selected per tool during Slice 0. Immediately before each
actual effectful binding executor entry, host code atomically requires
`attempts < max_attempts` and increments `attempts`. Reconciliation reads do not
increment it. An external request has a bounded timeout. After a timeout, or on
startup when an action remains `executing`, the host uses tool-specific evidence
and bounded provider re-reads to reconcile it automatically. It may return the
action to `queued` only when evidence proves the effect did not occur, repeating
it is safe, and lifetime attempt capacity remains. It records `succeeded` or
`failed` when provider evidence establishes the outcome. If the ceiling is
exhausted, proved absence becomes `failed`; unresolved evidence becomes
terminal-for-execution `uncertain`. Only after the tool-specific reconciliation
procedure is exhausted and available evidence genuinely cannot decide does it
otherwise record `uncertain`. A timeout alone is never evidence for a retry or
for uncertainty. There is no blind retry or execution lease; `attempts` records
the rare evidence-authorized repeat rather than authorizing one, and no tool may
configure an unlimited ceiling.

Ambiguous `gmail.create_draft` recovery is deliberately stricter. Each of three
observations, separated by fixed `0`, `2`, and `8` second backoffs, enumerates at
most five unfiltered `users.drafts.list` pages with `maxResults=8`, collects at
most forty unique draft IDs without assuming provider ordering, and fetches at
most those forty candidates with `drafts.get(format=raw)`. The whole procedure is
limited to thirty seconds, sixteen MiB of accepted response bodies in aggregate,
and the ordinary two-MiB per-response cap. It records whether enumeration ended
with an absent, present, invalid, or unknown `nextPageToken`, but never records
the token itself and never uses `q` or another Gmail search-index query. Exactly
one observed `X-Jarvis-Effect-ID` plus matching normalized immutable content,
with no observed duplicate or conflict, proves success even if pagination was
incomplete. Multiple observed matches or a matching header with conflicting
content exhaust to terminal `uncertain`. Without that positive proof, malformed
or transient evidence, an incomplete enumeration, and zero matches also exhaust
to terminal `uncertain`; even a complete bounded enumeration cannot prove
non-creation. Gmail draft-create reconciliation therefore never returns
`absent`, requeues the action, or authorizes another create request.

If `gmail.update_draft` recovery finds that the known draft disappeared, it
fetches the known thread once with `format=minimal` and then fetches up to one
hundred enumerated messages individually with `messages.get(format=raw)`. It
does not search the mailbox or assume an ordering. One unique, fully processed
effect-header and desired-content match proves the update's outcome; duplicate,
conflicting, malformed, or incompletely processed evidence cannot. The bounded
thread-read shape and message ceiling are revisioned binding-policy inputs, so
changing them rotates the binding identity without inventing a new public tool
or implementation name.

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
model supplies no durable call ID. The later kernel input contains the action ID
as opaque host reference, canonical tool name, original validated arguments,
resolved action state, and safe result/evidence. This is sufficient to continue
after provider-session loss without replaying the original write.

An action-resolution input must produce a visible owner notice. If Main returns
`silent` or fails before a renderable terminal, Jarvis's terminal-finalization
adapter persists a deterministic host-authored assistant fallback rendered from
the action ID, tool, resolved state, and safe normalized result, then processes
the host row. For `uncertain`, that fallback includes the safe reconciliation
evidence and the required request for owner inspection. The same rule applies to
a scheduled-wake input, whose fallback includes the stored reminder instruction.
Thus silence remains valid for ordinary owner turns, but never silently consumes
an asynchronous result or requested reminder.

### 5.5 Gmail send

Gmail send uses the provider's draft flow:

1. During `gmail.create_draft`, compute `jarvis_effect_id` as the full lowercase
   hexadecimal encoding of `SHA-256(UTF-8("jarvis-gmail-v1:" +
   canonical_text(create_action.id)))`, where `create_action` is that
   draft-creation action row. Set the MIME header
   `X-Jarvis-Effect-ID: {jarvis_effect_id}` and create the exact draft
   automatically. Gmail owns the RFC `Message-ID`; updates preserve the Jarvis
   header, and the later send action stores it rather than deriving a second one.
2. Persist its Gmail `draftId`, known thread identity, and exact envelope,
   subject, body, and `jarvis_effect_id` snapshot in the action arguments.
3. Render and request approval for that immutable snapshot.
4. Immediately before sending, fetch the live draft and require it to match the
   snapshot exactly; a mismatch fails the action and requires a new proposal.
5. Send by `draftId` after approval.
6. On an ambiguous result, perform three observations separated by fixed `0`,
   `2`, and `8` second backoffs. Each observation inspects the known draft,
   fetches the known thread with `format=minimal`, and fetches at most one
   hundred enumerated messages individually with `messages.get(format=raw)`.
   The whole reconciliation procedure is bounded to thirty seconds, sixteen
   MiB of accepted response bodies, the ordinary two-MiB per-response cap, and
   at most 102 provider reads per observation. It performs no mailbox search
   and assumes no thread-message ordering.
7. Compare every selected message carrying the exact `X-Jarvis-Effect-ID` with
   the immutable normalized snapshot, excluding only the current live draft's
   message ID. After every message in the selected bounded observation is
   validly processed, one unique exact header-and-content match proves success
   even when the draft remains or the thread contains an unprocessed tail beyond
   one hundred messages. No Gmail label is required. Multiple observed matches
   or any observed conflicting match do not prove success.
8. Repeat only when all three observations show the exact unchanged draft and
   a complete known thread with no matching non-draft message, repetition is
   safe, and immutable attempt capacity remains. Malformed, transient, partially
   processed, duplicate, or conflicting evidence cannot prove absence. If the
   reconciliation elapsed bound ends the procedure with incomplete evidence,
   or the complete procedure otherwise cannot decide, record terminal
   `uncertain`, present safe evidence, and ask the owner to inspect Gmail. The
   original mutation timeout alone decides neither retry nor uncertainty.

The exact reconciliation behavior for new and existing threads MUST be verified
against the live integration.

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
forgetting, or destructive consolidation mechanism. adr 0060 retains that rule
for the universal-memory prototype; forgetting is not a planned v2 feature.

Summaries, embeddings, full-text indexes, and vector indexes are derived and
rebuildable. The system adds no memory type, category, importance, confidence,
salience, source-authority, validity, conflict, project, person, or procedure
field.

### 6.2 Raw memory

The rememberer produces zero or more concise, self-contained natural-language
memories from one completed settled input group. Host code appends them to
`memory_log` and sets `remembered_at` on every consumed owner message in that
group in one transaction.

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

Each owner-input recall begins with exactly one kernel-dispatched deterministic
`memory.search` call under the frozen recaller plan. Its schema-validated typed
result is the recaller's first observation. The recaller then adaptively searches
or opens memory as needed; Jarvis does not bypass kernel dispatch for the initial
read. The query is the trimmed canonical owner input when it fits both 2,048
Unicode code points and 4,096 UTF-8 bytes. Otherwise Jarvis deterministically
keeps UTF-8-safe head and tail portions separated by ` ... `, removing complete
Unicode code points from the larger encoded portion until both bounds hold.

It:

1. Starts from the deterministic search's raw-memory and summary candidates,
   produced through PostgreSQL full-text and vector similarity search.
2. May issue multiple or reformulated searches after that initial observation.
3. Deduplicates only identical `(table_kind, id)` candidates.
4. Uses model judgment to select a compact relevant bundle.
5. Preserves memory IDs, timestamps, and summary lineage.
6. Opens raw sources behind a summary when detail or verification matters.
7. Returns an empty bundle when nothing is relevant.

A summary and one of its raw sources may both remain candidates. Host code does
not assume that the summary preserves the detail that made the raw memory useful.

### 6.4 Rememberer

After every settled input group containing owner messages that reached any valid
Main terminal or created an action awaiting approval, the rememberer receives
all consumed owner messages, the persisted conclusion, material tool/action
context, and relevant existing memories. It may search and open memory before
returning zero or more new raw memory strings as a schema-validated
`finish.result` from an isolated one-shot run. Host action-resolution and
scheduled-wake rows may supply context but are not themselves memory-work
targets.

The rememberer should retain information likely to save future explanation:
preferences, decisions, unresolved intentions, persistent circumstances,
relationships, and useful lessons. It should omit chatter, secrets, full copies
of live resources, unsupported inferences, and redundant paraphrases.

If the rememberer fails, every target `remembered_at` remains null. A bounded
sweep retries unremembered completed rows only when `role = owner`; host
action-resolution and scheduled-wake inputs are never rememberer work. The
normal sweep reconstructs a settled group from the shared run/conclusion trace
and processes it once. If old or damaged trace cannot establish a group, it
processes owner rows individually; memory search and model deduplication limit
redundant append without pretending exact semantic deduplication. A successful
run that chooses to write nothing still sets every target watermark.

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
a usable memory system. the fixed recall evaluation set and scorer are removed
under adr 0046; quality verification awaits the testing redesign. the production
rebuild retains its structural and raw-memory checks.

### 6.6 Memory is evidence

A memory is a prior model-made recollection. It is neither live external truth
nor authority. Memory text never grants a permission, records operative consent,
changes the approval boundary, or becomes a system instruction.

Current questions about Gmail, Calendar, or Maps should use live tools. Current
Jarvis conversation comes from canonical `message` rows. Memory supplies
relevance and history.

## 7. Agent, model, and tool runtime

### 7.1 Agent kernel and cognitive provider

responsibilities:

- `provider-runtime` owns native protocol, prepared turns, submission evidence,
  native binding/control, declared callbacks, strict output lowering, terminal
  provenance and usage. it attaches to the host-owned socket; the host owns the
  process and original personal account credentials.
- `llm-tools` owns prompt sections, declarations/bindings, frozen plans,
  consistency/tightening proofs, implementation revisions, pure validation,
  `HostTable`, execution, budgets, positions, recording, replay and portable tools.
- `llm-agent-kernel` owns immutable definitions/fingerprints, native supervision,
  serial dispatch, input/control ordering, isolated one-shot grammar and reusable
  conformance. it owns no application store, process, credentials or effect policy.
- jarvis owns canonical requests/context, current-owner permits, persistence,
  connectors, plan selection, consent/actions, reconciliation, scheduling and
  visible delivery.

main is a `NativeDefinition` with declared host callbacks and a closed
`JarvisTerminal`. recaller, rememberer, dreamer and AutomaticWriteGate use fresh
isolated `AgentDefinition`/`run_one_shot` invocations. their first three maximum
envelopes contain only memory reads; the gate's is empty. isolated plans contain
no `ToolEffect.Write`. these fixed roles create no persistent peer graph;
owner-directed skid controls remain external tools under adr 0052.

each invocation selects one frozen plan proven internally consistent with its
exact published catalog and to tighten the role's maximum envelope before
rendering or I/O. a profile comparison alone is insufficient. the budget factory
constructs fresh state whose limits equal that plan exactly; state is never shared
across runs. `Pure`/`Read` effects and replay policies remain distinct.

each binding has a non-empty owner-controlled `implementation_revision`, carried
by plans, publication and recovery contracts. changes to its handler or transitive
execution behavior bump that revision unless revisioned policy inputs already
capture the change. public tool names do not acquire version suffixes.

cognition uses the original personal local-account credential through the
separate contained host. the compatibility manifest admits exactly
`gpt-5.6-terra`; main uses reasoning `high`. retired `gpt-5.4`, model aliases,
generative API-key substitution and silent provider fallback are rejected before
I/O. changing the admitted set requires an explicit manifest update and genuine
selected-model qualification against the immutable installed artifacts.

the manifest's application/role revisions and exact library pins participate in
session compatibility. the selected model/reasoning, role/output, kernel-owned
base instruction and complete provider containment policy participate in the
definition fingerprint. secret bytes, clock and current inputs do not. schema-v3
session compatibility has no predecessor exceptions; schema-4 host mapping is a
separate operational contract.

main may reuse a healthy compatible native lease within its current process.
there is no saved-session file, resume-on-restart or session-reference CAS.
connection, process or owner loss permanently fences old callback authority.
recover an original sealed terminal locally before constructing current
definitions/catalog/tools. otherwise restart reasoning in a fresh native thread
from canonical unfinished requests and original receipts. accepted actions and
unknown billed-once reads retain their recovery barriers. repeated computation
is permitted; invented non-submission or repeated unknown effects are not.

native bindings, submitted requests, input deliveries, invocation contracts and
terminal seals are durable evidence. replacing a session neither deletes that
evidence nor asserts deletion of third-party native history. native compaction
and cache behavior remain provider optimizations, never canonical state or
guaranteed cost properties.

jarvis supplies canonical product context: stable instructions and owner profile,
bounded completed history, unfinished requests and original action/read receipts,
current input timestamps, recalled memories, the frozen capabilities, owner IANA
timezone and host `as_of`. typed `llm-tools` sections express provenance; they are
not an authority boundary. each current input is supplied once within its native
delivery; queued steering acceptance is distinct from a recorded native item.
ambiguous delivery fences the old turn before fresh reconstruction. a new topic
arrives promptly while retaining older unfinished requests. host action resolutions
supply facts and never grant fresh owner intent. scheduled wakes use a separate
read-only plan; they are not appended to an interactive turn.

main terminal sealing precedes output decoding and product settlement. final
dispositions name delivered requests; omissions retain their state. the
transaction writes canonical
request state, response and bounded trace together; a stale stop/resume cannot
publish an old completion. public commentary commits its own outbox row without
completing requests. original sealed output can recover locally after an encoder
failure with zero provider calls.

owner admission requires the live dedicated deployment-lock connection,
canonical request state and an immutable current permit. a gate's permit also
names its current parent native invocation. losing ownership stops admission;
it cannot reconnect or borrow another owner's token. no rolling journal,
cumulative main model/tool quota or arbitrary main elapsed cutoff remains.
isolated roles retain their actual finite operation bounds. finite tool deadlines,
message/frame/queue limits, serial effect entry and explicit owner stop remain.
usage is observational, including missing usage; it never grants authority.

configuration defects retain original evidence and require repair. native
submission uncertainty never authorizes replay of the old submission. reasoning
recovery occurs only after fencing its old tool authority. effect reconciliation
and entered-effect settlement remain available while paused. AutomaticWriteGate
receives only the restricted current-owner/effect projection in section 5.1,
never general main history or observations.

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

when the universal-memory target ships, adr 0056 additionally grants main's full
plan `memory.save_note(text)` under its [exact contract](docs/universal-memory.md#jarvis-main-note-tool).
adr 0058 additionally grants `memory.search` and `memory.open` to main's full and
scheduled-wake read-only plans; all three stores use the shared retrieval path.
adrs 0059/0062 remove the recaller and hard-cut search/open to the shared
bounded contract with deterministic rank fusion. the dreamer can access only notes/summaries; the rememberer has
no tools. search is a tool pipeline, never a nested agent.
the baseline catalog below otherwise retains its meaning.

| Tools | Granted role | Authority |
|---|---|---|
| `gmail.search`, `gmail.read_thread` | Main | Read; automatic |
| `gmail.create_draft`, `gmail.update_draft` | Main | Write; automatic |
| `gmail.send_draft` | Main | Write; approval required |
| `calendar.list_calendars`, `calendar.list_events`, `calendar.get_event` | Main | Read; automatic |
| `calendar.create_event`, `calendar.update_event`, `calendar.delete_event` | Main | Automatic only for a no-attendee event on a verified owner-only calendar; otherwise approval required |
| `maps.search_places`, `maps.get_place`, `maps.directions` | Main | Read; automatic |
| `web.search`, `web.read` | Main | Public-Web read; automatic |
| `schedule.wake` | Main | Write; automatic |
| `agent.list`, `agent.info`, `agent.read` | Main | peer agent read; automatic |
| `agent.start`, `agent.send`, `agent.text`, `agent.keys`, `agent.stop`, `agent.close` | Main | peer agent control; automatic only when grounded in current owner input |
| `memory.search`, `memory.open` | Recaller, rememberer, dreamer | Read; automatic |

worker control follows [adr 0052](docs/decisions/0052-cut-worker-control-to-current-skid.md).
all inputs are closed; refs are opaque strings of 1–4096 characters. machines
are `macbook|devbox|arch`; profiles are `personal|work|work2|claude-work`.
start retains the existing name grammar and optional cwd bound.

| tool | required mode and additional input | fixed skid command |
| --- | --- | --- |
| agent.list | optional machine | list [--machine …] |
| agent.info | ref, target: terminal or conversation | info --ref or inspect --ref |
| agent.start | machine, profile, name, cwd? | start name --machine … --profile … [--cwd …] |
| agent.read | ref, source: latest/history/terminal, maxBytes default 16384, maximum 32768 | read --ref [--history or --terminal] --max-bytes … |
| agent.send | ref, text | send --ref --input peer --stdin |
| agent.text | ref, text | text --ref --stdin |
| agent.keys | ref, 1–16 keys | keys --ref key… |
| agent.stop | ref, mode: native or terminal | stop --ref [--terminal] |
| agent.close | ref, scope: conversation_and_terminal or terminal_only | close --ref [--terminal-only] |

all commands include fixed `--config` and `--json`, argv without a shell, minimal
`PATH=/usr/bin:/bin` environment, and text through stdin. text is nonempty,
at most 32768 utf-8 bytes and contains no nul. keys are exactly enter, escape,
ctrl-c, up, down, left, right, tab, backspace, page-up and page-down. start sends
no initial prompt and promises no readiness. no user native input, queue,
interrupt or kill alias remains; native unavailability never selects terminal input.

skid owns opaque refs, target lifetime validation, native methods and result
semantics. jarvis consumes their current closed shapes at `agent_tools.py`.
`info target=conversation` uses the cli's captured-target inspection projection:
`{label,machine,target:{ref,conversation,turn?},inspection:{ok,result|error},observedRef?}`.
its target preserves the original ref even when inner inspection fails; outer
admission failure has no target. a successful observation must match its captured
conversation. `observedRef` exists only on success and is never substituted into
an existing action. terminal reassociation or deletion does not invalidate a
captured conversation; terminal operations require their exact original lifetime.

before preparatory lookups, every worker write requires current owner input.
native operations inspect their captured target successfully. optional terminal
info grounds the owner's worker name only if its conversation equals the captured
one; a missing/reassociated terminal cannot deny explicit conversation authority.
terminal operations inspect their original terminal. compound close describes
both original targets; an unavailable native halt may still permit explicitly
authorized exact terminal closure. only normalized identity facts enter the gate,
never worker prose. execute the original arguments once; gateway validation owns
races after preflight. do not renew refs or retry through a replacement action.

parse `{ok:true,result}` or `{ok:false,error:{code,dispatch,conversation?}}`
before exit status. optional absence, read method/scope/truncation, unavailable
peers, partial inventory, known creation and separate close outcomes survive.
partial inventory and unconfirmed results can exit nonzero. each subprocess has
a twenty-second budget around skid's fifteen-second budget. drain stdout
concurrently with stdin delivery, capped at one mib inventory or 64 kib otherwise.
discard stderr at the file descriptor; capture and log no diagnostic bytes.
early stdin closure does not erase a valid owned stdout receipt. tool bounds are twenty seconds for reads/start, forty-five for
text/keys and sixty-five for native send/stop or compound close with two
preflight reads. cleanup terminates only that cli child.

writes retain `BilledOnce`, one entry and max_attempts=1. preflight and spawn
failure are not_sent. after spawn, lost/malformed replies, timeout and stdout
overflow are unknown unless a valid owned receipt proves otherwise. stage known partial facts as `agent_control_v4` before settling
uncertain; a creation refusal carrying a created conversation is partial even
when terminal creation was not_sent. unconfirmed native or close outcomes settle
uncertain, never success. native input accepted means admission, completion
unconfirmed; terminal written means dispatched bytes. unsupported is not idle.

old finalized worker rows become opaque archives before current tool lookup,
argument/receipt/evidence decoding or uncertainty rendering. old agent
implementation revisions v1–v5 and the retired codex family preserve their raw
records after common immutable digest/effect/lineage/state/time checks. render
only action id, tool, recorded status and `receipt details unavailable after
cutover`. remove both retired codecs. current malformed receipts remain defects;
old nonterminal rows block activation. old code must settle/reconcile unfinished
work and drain required action resolutions and delivery before activation.
partial fleet evidence retains the existing incompleteness path and restoration.

The Slice 2 Jarvis-owned read result unions are exactly:

| Tool | Declared errors |
|---|---|
| `gmail.search` | `InvalidQuery`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `gmail.read_thread` | `ThreadNotFound`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `calendar.list_calendars` | `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `calendar.list_events` | `InvalidRange`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `calendar.get_event` | `EventNotFound`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `maps.search_places` | `InvalidQuery`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `maps.get_place` | `PlaceNotFound`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |
| `maps.directions` | `NoRoute`, `InvalidLocation`, `InvalidDepartureTime`, `RateLimited`, `ProviderUnavailable`, `ProviderResponseTooLarge` |

The table defines each tool-bearing role definition's maximum capability
envelope. An
owner-input or action-resolution main run receives the full Main plan. A
scheduled-wake run uses the same continuing definition but receives only the
catalogued Gmail, Calendar, Maps, and public-Web reads.
the accepted adr 0058 target also includes memory search/open in both main plans;
it adds no write to the scheduled-wake plan.
Recall, remember, and dream one-shot plans contain exactly `memory.search` and
`memory.open`; AutomaticWriteGate has an empty plan. Every plan is frozen for its
run and may never exceed its envelope.
Owner-input recall begins by having the kernel dispatch exactly one deterministic
`memory.search` call under that recaller plan and provide its typed observation;
the recaller may then adaptively call `memory.search` or `memory.open`.

`calendar.list_events` takes only aware `time_min`, aware `time_max`, and an IANA
`time_zone`. It exposes neither a provider calendar ID nor a model-selected
result bound. The host reads `users/me/calendarList` with reader-or-better
access, non-deleted entries, hidden entries included, and a hard 50-calendar
bound, then reads the requested range from every returned calendar. Jarvis MUST
NOT ask the owner for a provider calendar ID. `calendar.list_calendars` exposes
that same bounded live set, with an exact stable ID, nullable display name and
IANA time zone, access role, and primary/hidden/selected flags, so a human
calendar name can be resolved for targeted reads or writes. Neither result is
persisted.

Every Jarvis-owned entry above initially declares
`implementation_revision = "jarvis-<canonical-tool-id>-v1"`, replacing dots
with hyphens. Calendar discovery is `jarvis-calendar-list_calendars-v1`; the
Calendar list binding is `jarvis-calendar-list_events-v6` after ADR 0038's
bounded pagination, compact overview, and coverage hard cut; the Calendar get
binding remains `jarvis-calendar-get_event-v2` after ADR 0029's observed-end
correction. The model-facing tool IDs remain unversioned.
Reviewers MUST reject
a behavior-changing handler or transitive dependency change that neither bumps
the affected implementation revision nor records the behavior in revisioned
policy inputs.

the baseline main agent receives recalled memory but no memory tool; the accepted
target adds `memory.save_note`, `memory.search` and `memory.open` as described above. internal cognitive
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
The pinned reader binding implementation is `llm-tools-web-read-v3`. Its
model-visible `extraction` identifier is `plain-text-v2` for literal plain text
and `html-visible-text-v2` for visible HTML/XHTML text. These projections decode
character references exactly once; plain text is never treated as markup.

The production Brave binding uses the pinned `llm-tools`
`operation_deadline_seconds=12.0` policy. the current main and scheduled-read
plans retain one external search attempt and `BilledOnce`, with one serial
callback. cumulative call/attempt/byte/elapsed limits are null. each operation
retains its finite declared bounds; jarvis adds no second deadline wrapper.

The eight Jarvis-owned connector reads declare `ProviderResponseTooLarge` in
addition to their tool-specific failures. Provider JSON is rejected before
parsing when its decoded body exceeds two mebibytes. Stable identifiers and
values are never truncated: an overlong provider ID, email address, timestamp,
URI, MIME type, Calendar recurrence or event value, or other exact field returns
`ProviderResponseTooLarge`. Only the explicitly presentation-oriented Gmail
snippet and decoded message text may be shortened, and their enclosing
`truncated` flag MUST report it. Bounds apply to UTF-8 bytes as well as schema
characters. Every success carries an aware UTC `observed_at`; ordinary logs
contain no connector body.

`gmail.search` performs one `users.threads.list` request and returns at most 20
`{thread_id: string[1..1024], snippet: string[0..1000 bytes]}` records. It sets
`truncated` for provider pagination or a shortened snippet and performs no
per-hit expansion. `gmail.read_thread` performs one
`users.threads.get(format=full)` request and returns at most 50 messages. Each
message contains exact bounded message/thread IDs, sender, To/Cc/Bcc mailboxes,
nullable exact RFC Message-ID, subject, aware UTC internal timestamp, decoded
inert `body_text`, a `body_truncated` flag, and bounded attachment metadata
`(filename, media_type, size_bytes)`. The newest `max_messages` are selected and
returned oldest to newest. Mailbox
names are at most 320 bytes, addresses are exact and at most 320 bytes, subjects
and RFC Message-IDs are exact and at most 998 bytes, each decoded text is at
most 16 KiB, aggregate
returned text is at most 64 KiB, and at most 50 mailboxes per address field and
50 attachment records per message are returned. Inline `text/plain` is
preferred; inline HTML is converted to inert text only as fallback. Jarvis does
not fetch a Gmail `attachmentId`, execute HTML, or load a subresource.

Calendar reads return a closed tagged event union. List obtains at most 50
reader-or-better CalendarList entries, including hidden calendars, and reads
their event ranges with at most ten concurrent Google requests. The model
supplies no calendar ID or result bound. Event reads use pages of 250 and follow
`nextPageToken` in deterministic calendar-ID rounds, with at most 100 event-page
requests and a connector-owned 55-second deadline inside the executor's
60-second fence. Including discovery and the existing refresh behavior, the
tool permits at most 202 external attempts. A normal compact list item has exact
`calendar_id` and `event_id` strings of at most 1024 bytes,
`status = confirmed | tentative`, an exact summary up to 1024 bytes, a required
timed aware or all-day start, a required observed end, and nullable exact
location up to 4096 bytes. A sparse cancelled list item contains only its type
and exact bounded calendar/event IDs. A list returns the scanned Calendar
references, at most 1,500 globally chronological whole compact items, an
explicit bounded per-calendar failure list, and a closed `coverage` value.
Sparse cancelled events sort last. The canonical success envelope is at most
524,288 bytes. Stable list fields are never shortened; whole items are omitted
at a count or byte bound. Description, recurrence, attendees, organizer,
reminders, etag, and update metadata remain available through
`calendar.get_event`; Main MUST use the list's exact IDs before relying on those
omitted full details.

Calendar coverage contains `complete`, sorted unique `reasons`,
`calendars_discovered`, `calendars_completed`, and nullable `matched_events`.
Reasons are exactly `calendar_limit`, `calendar_failure`, `event_page_limit`,
`event_limit`, `output_byte_limit`, and `deadline`. `complete` is true exactly
when reasons are empty: discovery is untruncated, every selected page is
exhausted, every selected Calendar succeeds, and no result bound clips the
observation. `matched_events` is non-null only when every in-scope event page was
exhausted. One failed calendar does not erase truthful completed observations
from other calendars, but makes coverage partial. A get may return either
variant; event fields are never shortened.
The observed end is a direct closed union of the existing `TimedEventTime` and
`AllDayEventTime` plus payload-free
`UnspecifiedEventEnd {type = unspecified}`; all three share the `type`
discriminator. Google's missing or false `endTimeUnspecified` requires a valid
parsed timed or all-day end. True returns `UnspecifiedEventEnd` and causes
Jarvis to discard Google's compatibility end without parsing it. This rule
applies to every normal event type, including `fromGmail`; start remains
required. A non-boolean flag, or an absent or malformed end when false or
missing, is malformed upstream. The observed projection is not a create/update
input: future Calendar write inputs retain the unchanged two-branch concrete
`EventTime` end and an address-required attendee shape.
An observed-only `CalendarParticipant` has nullable exact `name` and `address`
fields, each bounded to 320 UTF-8 bytes; a provider participant with both fields
null is preserved. Normal-event attendees and organizer use this shape. This
does not weaken Gmail or future Calendar-write
`Mailbox`, whose address remains required. An over-bound present participant
field is `ProviderResponseTooLarge`.
For a timed event, Jarvis preserves a valid provider IANA `timeZone` when one is
present. An offset-free `dateTime` is localized with that `ZoneInfo`; an
ambiguous fall-back time deterministically uses `fold=0`, while a nonexistent
spring-forward time is malformed upstream. If Google omits `timeZone` for an
already-aware `dateTime`, Jarvis preserves the instant and emits canonical
`UTC`; an offset-free value without a zone is malformed. Normalization performs
no additional provider request.
The Calendar get contract and binding remain v2. Discovery is v1. The Calendar
list contract and binding are v6 because its fixed host bound, paging, compact
overview, typed coverage, and result schema replace v5. Affected catalogs,
maximum and selected profiles, plans, HostTables, role/output contracts, and
definition fingerprints are recomposed. ADR 0038's Main terminal contract
already advanced the
application session revision; the v6 binding rotates the definition fingerprint
and cold-bootstraps without a second manual compatibility bump. Unaffected
isolated roles do not change. Event
aggregation permits at most 202 external attempts and retains the 60-second
executor fence; discovery permits two attempts and 15 seconds. main and
scheduled reads have no aggregate response/context quota. these finite
per-operation bounds still apply to each call; recorded results are replayed
without another executor charge.

Maps place records expose canonical `maps_uri`, a nullable bounded absolute
HTTPS URI of at most 4096 bytes. Production requests the qualified Places wire
field `googleMapsLinks.placeUri` and normalizes it to `maps_uri`; it does not
request the legacy `googleMapsUri`, but normalization accepts that legacy wire
field from compatible provider payloads. Place IDs have the accepted local exact cap
of 1024 bytes. Search and details use the same closed shape: exact `place_id`
from 1 through 1024 bytes, exact `display_name` from 1 through 512 bytes,
nullable exact `formatted_address` through 1024 bytes, nullable finite
latitude/longitude, at most 32 exact type strings from 1 through 128 bytes, and
the nullable exact `maps_uri`. Search returns at most ten results; details reads
one fresh stable ID. Place results have no field-truncation flag, so an
over-bound value returns `ProviderResponseTooLarge` rather than a shortened
success. The fixed endpoint, field mask, result-count, and normalization
projection are revisioned policy inputs.

The production Places search field mask is exactly
`places.id,places.displayName,places.formattedAddress,places.location,places.types,places.googleMapsLinks.placeUri`.
The production place-details field mask is exactly
`id,displayName,formattedAddress,location,types,googleMapsLinks.placeUri`.

`maps.directions` sets `computeAlternativeRoutes=false`, requests exactly one
route, and requests no polyline field. A success contains exactly one route with
bounded non-negative `distance_meters`, the provider duration ceiling-rounded
to non-negative integer `duration_seconds`, a nullable description of at most
1000 bytes, and a required list of at most ten warnings of at most 1000 bytes
each. Zero routes is `NoRoute`; more than one route or an oversized exact route
value is `ProviderResponseTooLarge`. No encoded polyline is model-visible.
`departure_at`, when supplied, is offset-aware. A past departure is valid only
for transit, and transit must lie between seven days before and 100 days after
the authoritative host instant used for the call. A violation returns declared
`InvalidDepartureTime` before Maps I/O.
The production Routes response field mask is exactly
`routes.distanceMeters,routes.duration,routes.description,routes.warnings`.
Returned warnings are required display notices. The Maps binding instructions
require every non-empty warning to appear in the user-facing route answer; the
warning array is never dropped or rewritten by normalization.

`gmail.send_draft` arguments contain the provider draft ID, known thread
identity, stable `jarvis_effect_id`, and the exact To/Cc/Bcc, subject, and body
snapshot shown for approval. The effect identity is the full lowercase hexadecimal
encoding of `SHA-256(UTF-8("jarvis-gmail-v1:" +
canonical_text(create_action.id)))`, where `create_action` is the original
`gmail.create_draft` action. It is written once as `X-Jarvis-Effect-ID`,
preserved by updates, and copied into the separate send action's arguments.
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

`schedule.wake` uses one closed tagged schema: create with an exact
`execute_after` instant and instruction, or cancel with the target queued wake's
action ID. A create action's closed `result` has two independently managed
members:

```text
creation_receipt
  action_id
  execute_after
  arguments_digest
  recorded_at

wake_outcome = null | terminal persisted-wake outcome
```

The closed non-null `wake_outcome` variants are:

```text
concluded(conclusion_message_id, recorded_at)
cancelled(cancellation_action_id, recorded_at)
failed(reason_code, recorded_at)
```

They map the original schedule status to `succeeded`, `cancelled`, or `failed`
respectively; a local schedule lifecycle never becomes `uncertain`.

The host records `creation_receipt` atomically when the schedule binding accepts
the queued action; a queued row without that receipt is not eligible to fire and
is reconciled first. The Jarvis `llm-tools` durable-recorder adapter treats that
receipt as completion of the original tool effect and replays it for the
occupied position regardless of the later action status. Due execution changes
only lifecycle status and `wake_outcome`; it never overwrites
`creation_receipt`.

Cancellation is a separate gated `schedule.wake` cancel action with its own ID,
position, attempt ceiling, and closed
`cancelled(target_action_id, recorded_at)` receipt. In one transaction it targets
a queued original, records the cancel action as succeeded, moves the original to
`cancelled`, and writes cancellation evidence to the original `wake_outcome`.
It cannot target an executing or terminal original.

`llm-tools` supplies contracts, capability profiles and frozen plans,
`HostTable` publication, typed prompt sections, pure input validation,
tool-execution budgets, invocation positions, effect identity, recorder and
replay semantics, execution, and the two portable Web tools. Before Jarvis
implementation, Slice 0 upgrades and pins the public dependency seams required
by the kernel; Jarvis and the kernel MUST NOT duplicate them privately.

Reads need no action row. Effectful tool calls create an `action` before
execution and use its ID as their durable effect identity. Canonical message and
memory transactions are host bookkeeping and do not pass through `llm-tools`.

### 7.4 Native main and isolated steps

main uses the shared `run_native` contract:

1. validate exact capabilities, model/reasoning, strict output and frozen plan;
   prepare without provider submission.
2. commit the exact original request/provider attempt before native entry.
3. submit once and bind its native identity before dispatch.
4. for each declared callback, validate pure input, commit immutable invocation,
   enter the existing read recorder or write gate/action boundary, then commit
   the original `ToolResult` and exact model reply before wire delivery.
5. commit original native terminal/seal, failure and usage before application
   validation; validate input dispositions and publish through current fences.

the reader and control path stay live while callbacks execute serially.
callback transport IDs correlate replies; they are not effect authority.
a duplicate keeps its original input lineage, validated arguments and reply.
changed identity/arguments fail closed. a known invalid input retains raw
evidence and receives a typed rejection without executor entry; two identical
invalid proposals under distinct call IDs stop no-progress. an undeclared tool
or native authority event fences the attempt.

external writes publish the exact `ActionRequest` envelope:
`request_ref`, nullable `existing_action_ref`, and original typed `arguments`.
the action ledger stores that entire envelope; consent/classification render the
operation payload. only a canonical delivered owner request can authorize a new
effect. restarted old requests may reuse accepted actions; a new callback ID
does not authorize a duplicate write. pending approval yields a durable receipt
and independent reasoning continues. its eventual resolution is a host fact.

an authoritative provider non-submission proof settles locally. timeout,
exception, missing native ID, local stop or absent usage do not prove
non-submission. native evidence, local control outcome and product acceptance
remain separate. cleanup cannot replace an original safe failure or valid seal.

isolated roles retain the actual strict `call_tool | finish` step protocol.
`call_tool` proposes one canonical granted tool and closed arguments with no
prose, model-authored effect ID or approval field. `finish.result` matches that
role's closed output schema; `say` is unavailable. the kernel owns the Codex
wire envelope and JSON-string argument decoder; jarvis does not copy it.
unsupported output schemas fail before provider I/O. whole-step and pure input
validation precede output, recording, budgets and dispatch.

isolated `KernelLimits` retain their finite turn/repair/time/context bounds;
`llm_tools.RunLimits` alone own executor accounting. main's cumulative call,
attempt, input/output-byte and elapsed values are null with
`max_in_flight = 1`; per-tool `ToolLimits` remain finite. neither layer
double-charges a replay. no outer timeout falsely interrupts an entered write.
commentary and final structured output have separate bounded rendering and
persistence contracts.

### 7.5 Codex containment

main and isolated cognition attach to the separate personal stock
`0.160.0` app-server. the provider materializes its complete versioned
restricted model catalogue at HOST STARTUP: direct declared callbacks, inherited
clock/native user-input selectors removed, original vendor models retained.
public initialize version and config/read startup-origin checks qualify that
exact host before thread creation. per-thread catalogue overrides cannot supply
this boundary. unsupported versions fail closed; updates require explicit
qualification rather than latest-stable admission.

each cognition cwd is private, empty, read-only, non-secret and mode `0750`
beneath the jarvis-owned mode-`02750` cognition parent. the client group permits
only traversal/read of these directories and connection to the socket. native
shell/files/Web/network, MCP, subagents and unsolicited approvals are disabled.
host callbacks execute only the frozen application bindings. no connector,
Brave, embedding, Discord, database or Google credential reaches native
cognition or its account home.

the kernel owns each role's exact base instruction and fingerprints its immutable
identity. application instructions follow it and never widen authority.
main consumes prepared-turn events; isolated roles consume `stream_turn`
directly. the event-discarding `run_turn` projection is forbidden. declared
callback/terminal/commentary events remain distinct from native authority.
permission/native-tool activity, unknown active items or malformed identities
fail-stop and invalidate the session. raw vendor tool evidence cannot be hidden
as inert CodeMode activity. a malformed output payload cannot be replaced with
valid-looking final text.

systemd owns `jarvis-codex-contained.service`, its original host-only account
home and private mount namespace. it binds its own
`/run/jarvis-contained` source to stock's physical
`/tmp/codex-daemon-HOSTUID` inside that namespace. startup keeps the source
`0700`; after public qualification, publication uses source `0710`, physical
socket `0660` and relative `app-server.sock` alias. the fixed rendezvous is
`unix:///run/jarvis-contained/app-server.sock`. cleanup removes only the owned
alias and restores private permissions; stock owns stale physical-socket rebind.
no shared coding daemon, RPC relay, copied credential or app/kernel process
supervisor is involved.

the root-owned schema-4 `/etc/jarvis/codex-host.json` mapping contains exactly
the personal endpoint and explicit host/app/group/cwd identities. mapping
changes require stopped jarvis and same-release host operations before
activation. read-only release verification checks the loaded immutable
`ExecStart`, exact provider version and startup policy. application environment
files remain root-owned mode `0600`; jarvis marks itself non-dumpable before
provider attachment. host-qualified mechanics are not an installed production
service receipt.

### 7.6 Concurrency

one jarvis service owns a deployment through its dedicated PostgreSQL advisory
lock. one dispatch lane serializes callbacks and approved actions. the native
reader, ingress, consent and outbox tasks remain responsive while a callback or
write gate awaits completion.

AutomaticWriteGate runs a fresh isolated one-shot within its parent callback,
using the same current owner and explicit parent invocation permit. main cannot
enter another effect while that dispatch is active; native observation/control
continues. foreground work takes precedence over rememberer/dreamer work.
background cancellation preserves canonical source/progress and does not
automatically rearm paid inference.

accepted codex/claude worker sessions run independently on their selected hosts
after the existing skid tool dispatch. their terminal output grants no new jarvis
authority and consumes no main callback lease. this cutover adds no worker graph,
completion scheduler or application process supervisor.

## 8. Technology choices

- Server language: CPython >=3.12.13,<3.13; development/CI pin 3.12.13.
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
- Backup and restore: deliberately deferred beyond v1. Loss of the devbox,
  database, or disk can permanently lose Jarvis state; adding backup later does
  not require an application-schema change.
- verification: static/package checks plus the explicitly authorized native
  integration/live proof; the wider adr 0046 testing redesign remains separate.
- Deployment: one host-native systemd service on the existing Hetzner
  `dev-server`, plus a dedicated database and least-privilege roles in its
  native loopback-only PostgreSQL 16. Jarvis opens no public listener. It MUST
  NOT run on the Nexus production host or share Nexus application state.

Because the reused refresh grant is revoked, the one replacement offline OAuth
consent MUST request only:

```text
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.compose
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/calendar.calendarlist.readonly
https://www.googleapis.com/auth/calendar.acls.readonly
```

`gmail.compose` already manages drafts and sends mail; pairing it with
`gmail.readonly` avoids the label/archive/trash authority of `gmail.modify` and
makes a separate `gmail.send` grant redundant. Calendar free/busy and legacy
Drive scopes are outside the v1 catalog. An ACL read denied for a calendar makes
its sharing state unknown and therefore keeps its writes behind approval.

Do not add DBOS, Temporal, Restate, Celery, LangChain, LlamaIndex, CrewAI,
AutoGen, another general agent framework, a program-agent runtime, Redis, Kafka,
Kubernetes, Elasticsearch, Neo4j, a separate vector database, or a general MCP
bridge in v1.

V1 dependency lock:

- `llm-agent-kernel`:
  `8f6f15e39a99ed25f1a9cf8a1a50f5c4a76b6342`
- `llm-calling` / `provider-runtime`:
  `69d41d38a3d290e7ae3bde9b57556dda41e1b2f1`
- `llm-tools`: `9e6d155f3b64f03495911435b7cae8b8d131f9a2`

the separate contained cognition host requires stock 0.160.0 and the
provider-owned restricted complete catalogue at HOST STARTUP. `provider-runtime`
checks public initialize version and config origin before creating a thread.
unsupported native versions fail closed before submission. catalogue/binary
updates require explicit qualification. this endpoint supersedes adr 0042's
latest-stable rule without changing unrelated coding services. the application
owns its host unit; neither kernel nor worker owns native credentials/processes.

the root-owned schema-4 codex host mapping contains only the contained personal
endpoint and explicit host/app/group/cwd identities. worker routing comes only
from the
explicit skid settings, `JARVIS_AGENT_CLI_PATH` and
`JARVIS_AGENT_CLIENT_CONFIG_PATH` (adr 0052). deployment owns this mapping;
worker launcher fields do not belong to it.

The checked-in compatibility manifest schema v3 records
`qualified_models = ["gpt-5.6-terra"]`. Startup accepts only those exact model
IDs. At least one recorded model MUST pass the paid consumer probes through the
personal local-account credential against the exact code and dependency lock
being qualified.

The `llm-tools` value is the qualified implementation lock for public
validation, plan/catalog-consistency and full-plan-tightening, exact
`HostTable`, binding implementation identity, and async durable-recorder seams.
It is published on the configured durable remote; ordinary dependency
installation MUST lock the exact commit rather than import a sibling worktree.

All three MUST be git dependencies, not path dependencies. Jarvis MUST NOT modify or
restore the user's existing library worktrees.

The `dev-server` host and PostgreSQL run in UTC. Owner-local time comes from
required IANA timezone configuration included once when each cognitive session
opens. The context port adds one host-generated `as_of` instant per newly admitted input
batch or background job; a compatible batch appended mid-loop gets its own
instant. Tool-only continuations and embedding calls receive no repeated clock.
Stable prompt material precedes dynamic time.

The physical deployment uses a dedicated `jarvis` Unix account,
`/opt/jarvis/releases/<git-commit>` with an atomic `/opt/jarvis/current`
symlink, durable state under `/var/lib/jarvis`, and root-owned configuration
mode 0600 under `/etc/jarvis`. the application attaches only to the separately
contained host and never starts or bundles a native runtime. systemd owns its
additional host unit from the same immutable release. the
`dev-server` repository owns shared host prerequisites and base directories;
this repository owns releases, configuration, credentials, database roles and
migrations, and the systemd unit. Co-location grants no access
to Nexus credentials, files, database, or services.

Production activation requires the installed PostgreSQL and pgvector identities
to be recorded and qualified against the release. It does not require a host
reboot: a pending newer kernel is recorded and applied only during a later
owner-selected maintenance window. V1 creates no backup credentials, backup
role, backup timer, snapshot, or restore promise. Development/CI, PostgreSQL,
and Jarvis share one failure domain; bounded systemd resources, disk-headroom
checks, and explicit acceptance of possible total state loss are the v1
controls.

## 9. Persistence

jarvis owns nine application tables: the six records from adr 0040 and three
native journals from adr 0063. the separately accepted universal-memory target
adds three more; it is not part of this cutover.

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
  processing_attempts
  processing_parked_at
  remembered_at
  request_state
  wait_reason
  control_kind
  control_sequence
  control_targets
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
  execution_contract
  status
  attempts
  execute_after
  origin_message_id
  approval_message_id
  created_at
  decided_at
  completed_at
  result
  supersedes_action_id

model_decision
  decision_id
  scope_key
  thread_id
  first_input_id
  ordinal
  request_fingerprint
  request
  terminal
  submission
  host_evidence
  created_at
  completed_at

read_position
  position
  contract
  state
  reservation
  result
  settlement
  created_at
  updated_at

native_attempt
  id
  conversation_id
  attempt_seq
  owner_epoch
  request_fingerprint
  request
  native_binding
  submission_evidence
  local_outcome
  terminal
  product_outcome
  created_at
  armed_at
  fenced_at
  terminal_at

native_invocation
  id
  attempt_id
  ordinal
  native_call_id
  request_message_id
  tool_id
  proposal_digest
  proposal
  frozen_contract
  validation
  validation_error
  read_position
  action_id
  reply_receipt
  reply_recorded_at

native_input_delivery
  attempt_id
  message_id
  ordinal
  delivery_id
  mode
  state
  provider_evidence
  created_at
  updated_at
```

these are the current application columns. generated search columns, the control
sequence and Alembic bookkeeping are physical infrastructure. a new application
table or semantic memory field requires an accepted ADR.

### Durable inference and Read recovery

`model_decision` records recoverable isolated inference: its exact original
request/provider attempt, submission facts, original terminal and bounded host
validation evidence. recall is keyed by owner message identity, rememberer by its
settled owner group, gate by its parent native invocation, and dreamer by the
canonical raw/summary snapshot. unknown original submission blocks redispatch.
diagnostics may explicitly select transient inference; they establish no restart
proof. the later universal-memory target separately makes its background
inference disposable.

`native_attempt` preserves original prepared request, output schema/input lineage,
provider attempt, native binding and independent submission/local/native/product
facts. scope sequence is allocated under the conversation lock; only one
unfenced unresolved attempt may own that scope. local stop and missing IDs never
become seals. recovery checks the original attempt and authoritative native seal
and decodes against its frozen output contract before current definitions/tools.
an encoder failure repeats local work with original terminal/usage retained.

`native_invocation` preserves exact callback identity, original proposal and
lineage, frozen contract, validation and original read/action reference. known
invalid arguments remain raw evidence with their rejected reply. completed
duplicates replay the original reply; changed arguments or authority fail closed.
native call IDs never replace the host's stable invocation/effect identity.

`native_input_delivery` distinguishes prepared, sent, queued, recorded and
rejected delivery. queued RPC acceptance never proves native recording or request
completion. ambiguous delivery fences its old turn before fresh reasoning.

`read_position` uses the existing llm-tools recorder. original complete results
replay; unknown billed-once dispatch cannot execute again. restored reservations/
settlements preserve original per-operation accounting; main has no aggregate
quota. action recovery retains its existing original effect authority.

all stores use the dedicated deployment-lock connection for short serialized
transactions. lost ownership cannot reconnect or admit work. no transaction
spans provider, tool or delivery I/O. native truth commits before product
validation; current request/source/consent fences govern publication separately.

### 9.1 Message

`message` is canonical conversation history.

- `role` is exactly `owner`, `assistant`, or `host`; `host` is reserved for
  application-authored waking facts such as action resolutions and is never
  presented as owner speech.
- `(source, source_message_id)` is unique when a source ID exists.
- Every waking owner or host message is inserted before its turn with
  `processed_at = NULL`, non-negative integer `processing_attempts = 0`, and
  `processing_parked_at = NULL`.
- Host action-resolution messages are inserted idempotently from terminal
  `action` state with `processed_at = NULL` and are never delivered to Discord as
  if the owner authored them.
- `request_state` is `pending | waiting | completed | stopped` on ordinary owner
  requests; `wait_reason` exists only for waiting. validated final dispositions
  and canonical controls mutate them under the conversation lock. an omitted
  disposition retains state. a pending approval alone never completes a request.
- `processed_at` records completed/stopped owner requests or handled host facts,
  atomically with their canonical response/control/disposition.
- `processing_attempts` retains historical non-negative values; native main
  admits through current-owner permits, not this retired claim counter.
- `processing_parked_at` is nullable `timestamptz` and canonical
  operator-quarantine control. ordinary input scans exclude parked rows until
  explicit operator repair clears them.
  `trace` may record a bounded reason code but is never queried as control state.
- `control_kind`, monotonic `control_sequence` and exact `control_targets` record
  owner stop/pause/resume. pause truth lives in these canonical rows, not a file.
- Assistant messages are inserted before delivery. A null `source_message_id` is
  the outbound retry watermark; a successful adapter delivery or history
  reconciliation fills it with the source platform's ID. The Discord nonce is
  deterministically derived from `message.id` and needs no column.
- `remembered_at` records that its owner row participated in a completed
  rememberer group, including a successful decision to write no memories.
- `trace` is bounded JSON containing recall candidate IDs,
  selected/created memory IDs, and compact run summaries: run ID, provider trace
  IDs, provider turns, normalized token usage when reported, duration, and
  terminal outcome. Settlement writes the same run ID, through-checkpoint,
  nullable conclusion-message ID, and conclusion kind/outcome to every consumed
  waking row. It contains no prompts, model prose, message copies, tool
  arguments, results, or private payloads.
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
- `tool_name`, `arguments`, `execution_contract`, and `origin_message_id` are
  immutable after insert.
- `arguments` preserves the complete original `ActionRequest` envelope. its inner
  `arguments` is the sole operation payload for approval and execution.
  `request_ref` names its canonical owner request; `existing_action_ref` permits
  exact accepted-action reuse. `id` is the only additional
  input to a deterministic provider effect identity such as the Calendar event
  ID; it cannot change the approved payload.
- `execution_contract` is non-null closed host-authored JSONB containing the
  exact `tool_contract_revision`, `implementation_revision`,
  `policy_revision`, `plan_revision`, `ToolEffect`, `ReplayPolicy`, canonical
  `input_digest`, finite `max_attempts`, `claim_id`, canonical
  `through_checkpoint`, `model_step_ordinal`, ordered `input_message_ids`, and
  `write_gate_supporting_owner_message_ids`. It is not a model field or general
  version registry. on the native path, `claim_id` is the native attempt and
  `model_step_ordinal` is its callback ordinal; these retained column spellings
  do not create a main-step decoder. host code verifies it before every approval
  rendering,
  executor entry, replay, or reconciliation.
- Within that contract, `policy_revision` covers the deterministic authority
  policy and the AutomaticWriteGate definition fingerprint, including its
  prompt, model configuration, and output contract.
- `origin_message_id` is the exact delivered owner request named by `request_ref`.
  recovery also validates the complete original admitted-input/native lineage.
- `attempts` is a non-negative integer that starts at zero and increments
  atomically immediately before each actual effectful binding executor entry,
  only while below the immutable finite `max_attempts`. Reconciliation reads do
  not increment it, and a count never authorizes a retry.
- Host code resolves the current declaration and validates stored arguments and
  execution contract again before approval rendering and execution.
- `execute_after` is nullable; null means immediately eligible, while a timestamp
  supports `schedule.wake` without another table.
- `approval_message_id` is nullable and unique when present. It points to the
  host-owned approval `message` and is required while status is
  `awaiting_approval`.
- State claims commit before external calls.
- `decided_at` records an owner approval, denial, or cancellation decision.
  `completed_at` is set when the action reaches `succeeded`, `failed`,
  `uncertain`, or `cancelled`.
- `result` stores a typed provider receipt, failure evidence, cancellation
  reason, or uncertainty evidence without secrets. A create-schedule result
  preserves an immutable `creation_receipt` while its separate `wake_outcome`
  moves from null to the later terminal wake result.
- `supersedes_action_id` links a fresh-consent successor to its cancelled original;
  the original arguments, contract and receipts remain immutable. stopping
  cancels unentered work, never an entered effect's settlement obligation.

Queued or approval-bearing rows whose `tool_name` is unsupported or whose stored
arguments or execution contract no longer validate fail closed as `cancelled`
and are reported. before an incompatible cutover, the original release reconciles
entered/unknown effects; unentered work is cancelled and requires fresh consent.
after cutover there is one current decoder/executor, with no legacy fallback or
compatibility path. historical terminal rows retain their original bytes and
receipts. the per-row contract makes one occupied effect replay-safe; it is not
a registry for dispatching multiple implementation versions.

The action ledger must not become a duplicate message or memory store.

### 9.3 Other state

existing connector credentials, cursors and adapter state remain in their
owned stores. canonical pause is a postgres control message. native request,
attempt, invocation and input-delivery facts use the existing database and owner
lock; provider sessions/history are disposable. no local pause/session/admission
journal survives cutover. the original sealed terminal includes its frozen output
schema and input lineage, so local product settlement does not reconstruct a
current plan or repeat a model call. current request/owner fences still govern
publication. alembic owns its migration table.

The qualified mode-0600 Google handoff stores each OAuth token as
`aesgcm.v1.<base64url(nonce || AES-GCM ciphertext)>`, with a 12-byte nonce. Its
metadata names `AES-256-GCM`, key version `<version>`, and associated-data
namespace `jarvis.connector.google:<version>`. Access and refresh tokens bind
respectively to the full associated data
`jarvis.connector.google:<version>:access_token` and
`jarvis.connector.google:<version>:refresh_token`. Jarvis base64url-decodes
`JARVIS_CONNECTOR_ENCRYPTION_SECRET`, adding padding for decoding; a decoded
value of exactly 32 bytes is the key, and every other decoded length is reduced
with SHA-256. A refresh atomically replaces state in this same format.

V1 has no backup or restore path. the live main provider lease,
provider-native state, embeddings, summaries, and indexes are noncanonical or
derived, and memory rebuild remains available while the local raw log survives.
If backup is added later, its exact canonical state, credential exclusions, and
cross-resource consistency contract require a new accepted ADR and restore
test.

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
- the pinned native/isolated kernel contracts and jarvis-owned canonical context,
  current-owner admission, journal/input, dispatch and publication adapters.
- The intended plan-aware tool-budget, compatibility-revision, admission,
  context-sizing, checkpoint-park, and operator-release mappings, with each
  production proof assigned to the implementation slice that owns it.
- The upgraded public `llm-tools` pure-validation, plan/catalog-consistency and
  full-plan-tightening, exact `HostTable`, and async durable-recorder/executor
  seams consumed by the pinned kernel implementation.
- The intended action-backed durable-recorder mapping, including replay of a
  schedule's immutable creation receipt while its product lifecycle remains
  queued or executing; its production conformance proof belongs to Slice 5.
- The exact finite executor-entry ceiling and complete reconciliation procedure
  for every v1 write tool.
- The exact expected-provider-failure matrix, including which failures permit
  the kernel's one safe cold bootstrap and which fail without retry.
- A real isolated structured one-shot with an empty `HostTable` plan for
  AutomaticWriteGate; inability to represent no tools holds Slice 0 open.

The qualification report MUST also contain the exact v1 tool manifest from
section 7.3, live authority classification, Discord enforced-nonce/history
findings, Calendar ACL and client-ID findings, Gmail draft/send/reconciliation
findings, credential ownership and handoff plan, and proof that Codex cannot
access connector, Brave, or embedding credentials.
Implementation MUST NOT proceed beyond Slice 0 until the owner signs off that
report. Authorization to perform Slice 0 is not acceptance of findings that have
not yet been observed.

Slice 0 qualifies dependencies and external surfaces before application code
exists. It records rather than fabricates evidence for Jarvis-owned adapters.
Checkpoint/session/admission/parking/delivery and paid consumer probes gate
Slice 1; read plans gate Slice 2; memory plans gate Slices 3–4; the action
recorder and automatic-write plans gate Slice 5; approval suspension and plans
gate Slice 6. A plan MUST pass before it becomes selectable. Final acceptance
still requires every criterion in section 12.

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

- A service's first SIGINT requests cooperative shutdown; it MUST NOT inject
  task cancellation into ownership-bound database work. Startup work already
  underway may finish before stopping, but a pending shutdown MUST NOT open
  Discord ingress or start the worker loop. No new startup action-recovery pass
  begins after the stop request is observed.
- Normal shutdown closes ingress admission, signals existing cooperative
  cancellation, and joins the worker, timers, and admitted Discord callbacks
  before closing their clients and releasing deployment ownership. In-progress
  writes retain their existing durable settlement/recovery contract; a claimed
  approval waiting for execution does not start a new effect during shutdown.
  Genuine ownership loss and unexpected task failures remain defects.
- Shutdown has no new application-level timeout around writes. The existing
  systemd 360-second stop deadline or a repeated operator interrupt may force
  termination; this requires crash recovery and is not graceful-shutdown success.
- Secrets remain outside model context, PostgreSQL, fixtures, and ordinary logs.
- PostgreSQL and private service ports are not publicly exposed.
- V1 has no backup or restore mechanism. Operations record the accepted risk
  that host, disk, or database loss may permanently destroy Jarvis state.
- Production activation does not reboot the shared devbox. A pending kernel
  update remains explicit operational debt for an owner-selected maintenance
  window; worker terminals and their live processes are not treated as
  recoverable across that reboot.
- Jarvis uses live tools for current external state and distinguishes that state
  from recalled memory.
- public commentary and useful partial answers persist before delivery without
  settling unfinished requests. validated final dispositions govern completion;
  collection completeness comes from typed host evidence, never model prose.
- External success comes from a provider receipt or reconciliation evidence,
  never a model assertion.
- Failed and uncertain actions are reported honestly.
- Ordinary logs exclude credentials, private message bodies, raw email bodies,
  and complete memory text.
- provider work requires the current owner permit and canonical authority.
  ownership loss fences old callbacks; missing usage grants no authority.
  original terminal/action/read evidence survives restart and remains authoritative.

## 12. Definition of done

adr 0046 suspends the old verification machinery. native acceptance uses the
explicit adr 0063 integration/live exception and shared N001–N020 evidence;
whole-product deployment/domain/owner acceptance below remains separate.
static/build success alone establishes neither.

V1 is complete when every mandatory criterion in
[docs/acceptance.md](docs/acceptance.md) passes on the intended Linux deployment
using the real personal integrations and subscription-backed Codex account.

Acceptance includes:

- natural single-channel Discord conversation, compatible in-process reuse and
  fresh-session reasoning recovery after owner/connection/process loss.
- Live Gmail, Calendar, and Maps use.
- Live public-Web search and page reading.
- Memory formation, fresh-session recall, dreaming, and complete rebuild.
- Automatic personal calendar work.
- Host-rendered approval and one approved email send protected by draft identity,
  reconciliation, and honest terminal uncertainty rather than a universal
  exactly-once claim.
- At least seven days of owner use producing genuine cognitive offloading.

## 13. Change control

Frozen decisions:

- One visible Jarvis and natural Discord interaction.
- native public progress plus one host-rendered typed terminal with explicit
  per-input dispositions; incomplete typed evidence is visibly partial.
- One configured Discord channel with no v1 server-organization tools.
- exactly nine application tables, including isolated decisions, read positions
  and the three native journals; universal memory separately adds three.
- Central conversation history with a persistent Discord outbox, recent-window
  enforced-nonce deduplication, and explicitly bounded delayed ambiguity.
- Product-selected canonical context through the provider-neutral kernel ports;
  reusable but non-canonical provider sessions.
- Existing Google and Discord integrations are reused.
- The exact minimal v1 tool catalog in section 7.3.
- Host-owned bounded Calendar pagination and machine-readable coverage, with no
  model-selected result limit or legacy truncation boolean.
- Only owner-requested `schedule.wake` actions initiate user-facing proactive
  turns.
- Python, PostgreSQL, pgvector, `llm-agent-kernel`, `provider-runtime`, and
  `llm-tools`.
- Immutable raw memory plus rebuildable summaries and indexes.
- No action rows for canonical message or memory transactions.
- No explicit personal-domain object model.
- No workflow framework, general agent platform, persistent delegation graph,
  or model-generated program runtime beyond the bounded kernel and the five
  owner-directed agent controls.
- Host-rendered approval previews and the stated autonomy boundary.
- A restricted AutomaticWriteGate grounds every model-proposed write in current
  owner-authored input before action creation, without granting new authority.
- Unversioned canonical v1 tool names with immutable stored calls and
  per-action execution contracts plus deployment-time compatibility discipline.
- Finite lifetime executor-entry ceilings and action-backed schedule creation
  receipts that remain replayable across the later wake lifecycle.
- No v1 redaction or destructive memory consolidation.
- No Android, OnePassword, Nexus, Skidbladnir source/API, or other unlisted
  application integration. worker terminals and conversations remain skid-owned.

Changing one requires an ADR stating observed evidence, migration impact, and
the acceptance criteria affected.

# Jarvis v1 specification

Status: **Frozen baseline**

Date: **2026-09-02**

Audience: product, engineering, design, operations, and future coding agents

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

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
- General subagent delegation, persistent peer agents, or model-generated
  program execution beyond the five owner-directed Codex controls in section
  7.3.
- A general-purpose remote shell, SSH, terminal, or unconstrained browser agent.
- OnePassword or Nexus integration, or Skidbladnir source/API changes. Ordinary
  worker tmux sessions remain visible through unchanged Skidbladnir.
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

Main has no model-visible conversational `say` terminal. It uses the kernel's
existing structured-output path and returns exactly one closed terminal result:
`answered`, `partial`, `needs_input`, `failed`, or `silent`. The host renders
that result deterministically. No terminal variant means work is still in
progress. A terminal response MUST NOT imply future work unless a durable action
has already been committed and the kernel suspended on that reference. Discord
typing is the only synchronous progress indication.

The closed `JarvisTerminal` root contains one `response` discriminated by
`type`: `answered` has non-empty `text`; `partial` has non-empty `text`, a
non-empty at-most-500-character `limitation`, and a nullable non-empty
at-most-500-character `question`; `needs_input` has at-most-1000-character
`context` and one non-empty at-most-500-character `question`; `failed` has one
non-empty `explanation`; and `silent` has only
`reason = owner_needs_no_response`. Text and explanation retain the existing
Discord response limit. The host renders complete answers unchanged and owns
the fixed labels for every other visible branch, checking the final rendered
Discord bound before persistence.

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
The claim adapter selects one bounded, non-empty batch and its frozen plan:
owner rows and `source = action` resolution rows receive the full Main plan,
while a `source = schedule_wake` row receives the read-only proactive plan.
Owner work has priority. Incompatible rows remain unclaimed for a later run;
the kernel has no run-class abstraction and never infers authority from text.
A turn reaches a durable conclusion when it produces a persisted assistant
response, finishes silently, or persists
an approval proposal. The host sets `processed_at` in the same transaction as
that conclusion. The same transaction writes the settled run ID,
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

On startup, an owner row with `processed_at = NULL`,
`processing_parked_at = NULL`, and no action whose immutable execution-contract
lineage contains that row MAY be reclaimed only while its durable
`processing_attempts` remains within the configured ceiling and rolling
admission permits more work. A parked row is operator-only and never reclaimed
automatically. If any action records the row among its admitted
input IDs, the host MUST reconcile or resume that action and MUST NOT replay the
model turn automatically. It closes exactly the execution contract's admitted
input rows through its stored checkpoint and persists a host-authored
interruption notice. When several actions name overlapping prefixes from one
run, recovery handles every action and closes the union once through the
greatest compatible stored checkpoint. `origin_message_id` remains the stable
root pointer but is not sufficient recovery lineage. An exhausted or poison input receives a
deterministic host-authored stopped conclusion and is consumed; cleanup never
silently creates a fresh-budget successor.

The host promptly shows a typing indicator before model work. V1 does not stream
partial structured model output into Discord; the host delivers only a complete,
validated, rendered Main terminal.

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
`stop` or `pause`, case-insensitively, persists a paused flag, and immediately
signals the active kernel cancellation token. At its next safe boundary, the
host settles the interrupted input and control row with a deterministic stopped
conclusion so neither replays. Cancellation cannot undo an external effect that
already committed; such an action proceeds through reconciliation. While paused,
Jarvis performs no tools, actions, proactive turns, or dreaming. `resume` clears
the flag and is processed entirely by the host. These controls never involve the
model.

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

It runs only after the main step, frozen binding, and arguments validate, and
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
denial, or gate failure creates no action and dispatches nothing; the main loop
receives a typed policy denial and may ask the owner to restate the request.

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
step and no preview column in `action`.

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
forgetting, or destructive consolidation mechanism. Administrative erasure is a
deferred design that must account for every copy, including messages, actions,
provider state, backups, Discord, and external systems.

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

- `provider-runtime` owns Codex local-account authentication, shared Unix-socket
  WebSocket attachment to host-owned Codex App Servers behind the stable
  `AgentRuntime` open/stream/close interface, server-request denial,
  `PermissionPolicy`, native
  options, structured-output lowering, closed-world event normalization and
  usage, quota exhaustion, and opaque session references. Production consumes
  `stream_turn`; it never uses the terminal-only `run_turn` convenience
  projection because that hides authority events.
- `llm-tools` owns typed prompt sections, declarations, bindings, frozen
  profiles and plans, plan/catalog consistency and tightening proofs,
  owner-controlled binding implementation revisions, pure schema validation,
  `HostTable`, `ToolEffect`, `ReplayPolicy`, tool execution budgets, invocation
  positions, recorder semantics, execution, and portable tools.
- `llm-agent-kernel` owns immutable definitions and containment fingerprints,
  exact-plan/catalog tightening enforcement before rendering or I/O, the exact
  model-step protocol, semantic whole-step validation, bounded serial thread
  and isolated one-shot loops, mid-loop input polling, run admission
  enforcement, cancellation, session and checkpoint choreography, typed
  outcomes, and reusable conformance tests.
- Jarvis owns product context selection, implementations of the persistence
  and admission ports, canonical messages and memories, Discord, connectors,
  catalog composition, plan selection, information-flow and authority policy,
  approval/action/effect identity and reconciliation, scheduling, credentials,
  and visible delivery.

An agent definition is immutable configuration for a cognitive role. A role is
its behavioral purpose. An application thread is a host-owned durable
workstream; v1 has one, the configured Discord channel. A run is one host
invocation. A drain is an exclusive work epoch within a thread run. A one-shot
run is a fresh isolated invocation over explicit host input with no application
checkpoint or saved session reference. A model step is one provider response. A
provider session is an opaque, disposable optimization. These terms do not imply
persistent peer agents or general delegation. The five exact Codex controls are
owner-directed top-level worker operations outside the cognitive decoder; they
add no peer graph, completion callback, scheduler, transcript store, or worker
ownership state. The main definition is
`continuing` with a closed structured terminal contract and the exact main
catalog as its maximum envelope. Recaller, rememberer, dreamer, and AutomaticWriteGate are
`isolated` one-shot definitions with closed structured output contracts. The
first three have memory-read envelopes; AutomaticWriteGate has an empty tool
envelope. Jarvis supplies one frozen plan per run; it may narrow but never expand
the definition envelope. Before any plan rendering or I/O, the qualified public
proof MUST establish that the plan is internally consistent with the exact
catalog view being published and tightens the definition envelope in full; a
comparison of profiles alone is insufficient. Kernel construction rejects any
one-shot plan containing `ToolEffect.Write`. `Pure` and `Read` remain distinct
effects with independent replay policies.

Every binding has a non-empty internal `implementation_revision`. Jarvis-owned
bindings use `jarvis-<canonical-tool-id>-v1` initially; portable bindings use
the revision supplied by `llm-tools`. A handler or transitive
behavior-affecting dependency change MUST bump every affected implementation
revision unless revisioned `policy_inputs` already represent the change. This
is a hidden plan/recovery fingerprint, not public tool-name versioning. Frozen
profiles, plans, HostTable publication, and action execution contracts carry
it.

- Authentication uses the personal local-account credential.
- No generative API-key fallback or silent provider fallback exists.
- The checked-in compatibility manifest records the exact qualified
  ChatGPT-local-account model IDs. The current set is exactly
  `gpt-5.6-terra`; `gpt-5.4` is retired on this authentication path and MUST be
  rejected during configuration, before ingress, admission, provider I/O, or
  tool I/O. V1 requires at least one exact model that is currently supported by
  the provider to pass the paid local-account qualification. The size of this
  set is not a permanent product invariant; adding, replacing, or removing a
  route requires current live evidence and an explicit compatibility-manifest
  update.
- Kernel revision, model IDs, reasoning levels, prompts, host/runtime revisions,
  output contract, `PermissionPolicy`, cwd scope, MCP configuration, and native
  options are pinned per deployment and covered by the definition fingerprint.
- Every definition supplies a non-empty `session_compatibility_revision`
  derived from a checked-in canonical manifest containing its role ID, an
  owner-bumped Jarvis session-contract revision, and the exact
  `llm-agent-kernel`, `provider-runtime`, and `llm-tools` pins. The manifest
  excludes secrets, input, host time, and per-run subset plans. Normally every
  pin participates exactly in the revision. Schema v3 has no predecessor
  normalization or compatibility exception: this hard cut rotates every
  affected definition and cold-bootstraps its next cognition session.
- Qualified-model membership does not participate in
  `session_compatibility_revision`. The exact selected model already
  participates in the immutable agent-definition fingerprint, so a model
  change cold-bootstraps without manually rotating the application session
  contract. Removing the retired, unselected `gpt-5.4` route therefore does not
  invalidate an otherwise compatible `gpt-5.6-terra` session.
- Upgrades pass recorded replay and containment tests before activation.
- Quota exhaustion produces a fixed host-authored notice and no provider change.

The configured Discord channel maps to one continuing main Codex session. The
kernel coordinates provider lifecycle through an opaque `SessionRefPort`; its
Jarvis adapter persists the `AgentSessionRef` and immutable agent-definition
fingerprint in private, atomically replaced runtime state outside PostgreSQL.
The fingerprint covers every session-scoped semantic and containment value,
including the values listed above and the owner-controlled compatibility
revision. Changing the manifest's application contract, selected role contract,
or a dependency pin rotates the revision, except that the one exact atomic
provider-usage correction pair above uses its certified predecessor values.
Changing only `qualified_models` does not rotate the revision because the
selected model is already fingerprinted. Credential secret bytes, current input,
host time, and per-run subset plans do not rotate the session.
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
Discarding, replacing, or rotating a local reference does not assert deletion
of provider-retained native history; provider account retention remains a
separate third-party property.

Recaller, rememberer, dreamer, and AutomaticWriteGate invocations use fresh
isolated sessions. They MUST NOT share the main session or one another's
history. Main alone receives the stable owner profile and conversational voice.
Internal roles retain narrow task-specific instructions and MUST NOT inherit
either.

Jarvis owns product context selection and supplies canonical application data to
the kernel `ContextSourcePort`: Main's stable owner profile, stable instructions,
bounded completed message
history, current admitted inputs and source timestamps, recalled memories with
IDs and timestamps when the owner-input recaller ran, granted capability
descriptions, the owner IANA timezone, and one host-generated `as_of` instant. The kernel
coordinates continuation and bootstrap assembly from these inputs. Rendering
uses `llm-tools` typed prompt sections; XML-like structure is presentation and
provenance, never a security boundary. Provider SDK message types appear only at
the provider-adapter boundary.

For a healthy main session, the continuation projection sends newly admitted input,
current capabilities, `as_of`, and fresh recall only for owner input; stable
session context, including the owner timezone, and native history carry prior
turns. For a fresh Codex session, the bootstrap projection also includes stable
instructions and bounded canonical history. The same bootstrap projection MUST
remain usable by a future stateless or API-backed provider without replacing
product context selection. V1 implements no such second provider. The current
batch is sent only on its first provider call after admission; later
tool/protocol continuations send new observations or corrections without
repeating it. A replacement cold bootstrap includes unresolved input exactly
once in the replacement session.

Every newly admitted owner input appears exactly once and is excluded from
completed history. Source messages retain `created_at`. A cognitive session
receives the owner timezone once when it opens. Each newly admitted input batch
or background job receives one authoritative `as_of`; a batch appended mid-loop
gets its own. Tool-only continuations and embedding calls receive no repeated
clock. Stable prompt material precedes dynamic time in a rendered provider
request.

Native session history, compaction, and cache behavior are optimizations, not
canonical state or guaranteed cost properties. Canonical messages plus recall
MUST always be sufficient to start again.

AutomaticWriteGate does not receive this general product-context projection. It
receives only the restricted owner-input/effect projection in section 5.1. This
restriction applies on cold and healthy main sessions alike.

For the main application thread, Jarvis implements the kernel
`InputCheckpointPort` using existing message state and single-process
coordination. A claim contains one non-empty bounded input batch, its opaque
watermark, stable claim ID, ordered stable input message IDs, the host-selected
frozen plan, and the oldest logical input's durable `processing_attempts` value.
Owner and action-resolution work takes priority and receives the full Main plan.
A scheduled wake is claimed separately with the read-only proactive plan.
Incompatible work remains unclaimed.

Before every provider turn, before tool dispatch, after tool completion, and
before settlement, Jarvis lets the kernel poll the canonical message store.
New compatible owner input is appended in order and sent to the healthy session
exactly once. Stop/pause input preempts. A scheduled wake is never appended to
an interactive run, and interactive work arriving during a scheduled wake may
preempt it. An ordinary follow-up that arrives after the final poll does not
discard the valid answer already produced: Jarvis commits that answer and
processes the follow-up in the next run.

A terminal conclusion and `processed_at` watermark commit atomically and
idempotently. The same transaction gives every consumed waking row the same run
ID, through-checkpoint, nullable conclusion-message ID, and conclusion
kind/outcome in bounded `trace`. If settlement reports later input, Jarvis
signals a later run only after commit. Startup and recovery scan the same
canonical null-`processed_at` rows, so correctness does not depend on an atomic
transaction spanning PostgreSQL and an in-process wake signal. Cleanup `release`
never arms a successor by itself.

A kernel `park` for a configuration defect is different from cleanup release.
The checkpoint transaction sets `processing_parked_at` on every claimed,
unprocessed row, records only a bounded reason code in `trace`, and ends claim
ownership. Claim and startup/recovery scans exclude parked rows. Because v1 has
one application thread, any parked row opens the cognitive circuit for all new
cognitive work; delivery and operator repair remain available. Only an operator
who has corrected the defect clears the timestamp. Mandatory reconciliation of
an already-started external effect also remains available. The PostgreSQL row
is the single canonical circuit state, avoiding a transaction across the database and
the private runtime journal. Release is a local host maintenance operation, not
a Discord or model tool. It runs with the service stopped or while holding the
deployment ownership lock, names explicit message IDs, and does not reset
attempt history.

Protocol exhaustion, kernel-budget exhaustion, subscription quota exhaustion,
owner stop, and repeated provider failure persist a deterministic host-authored
stopped conclusion and consume the claimed input. A process interruption may
leave it unconsumed; the next successful claim increments
`processing_attempts`, and exceeding the configured ceiling stops it before
provider I/O. The increment occurs atomically when a claim is acquired after
the capacity preflight; it conservatively counts a crash or configuration
failure after claim. Configuration defects park the input and pause cognitive
work for operator correction rather than entering a retry loop.

After Jarvis selects and the kernel validates the claimed frozen plan, Jarvis's
`ToolBudgetFactoryPort` constructs one fresh `BudgetState` from that plan. Its
limits MUST exactly equal `plan.profile.run_limits`; it MUST NOT reuse state,
select policy, or inspect input. A mismatch parks a thread claim or rejects an
isolated one-shot before rendering, admission, provider I/O, or tool I/O. Every
selectable full Main, read-only proactive, memory-read, and empty gate plan is
qualified. All budget mutation remains on the dependency's async durable path.

Before claiming/incrementing an input, Jarvis preflights rolling admission under
its single-process execution mutex. The checkpoint claim transaction then
increments `processing_attempts`; no later cross-port callback or transaction is
required. Before provider I/O the kernel's admission port durably reserves one
root work slot plus the finite maximum provider turns and configured reported
token allowance for that work and its possible serial child one-shots. Recaller
and any AutomaticWriteGate calls in a foreground turn receive child admission
tokens against that reservation; the parent is paused and cannot perform
provider or tool I/O while a child runs. Rememberer and dreamer jobs obtain their
own root reservations.

The atomically replaced private journal records bounded reservation IDs, run
IDs, windows, counters, timestamps, reserved/actual capacity, and
`active | settled | interrupted` state—never prompts or user payloads. A clean
exit settles actual usage and refunds unused turn/token capacity in `finally`.
Process death conservatively leaves the full reservation charged. On startup,
while holding the exclusive deployment lock, Jarvis marks orphaned active
reservations interrupted and releases their live concurrency slot, but retains
their turn/token charge until the rolling window expires. Missing or corrupt
state fails closed until explicit operator reset. Finite window and capacity
values, including allowances for each admitted child role, are mandatory
configuration. The six-hour production ceiling contains exactly two complete
worst-case foreground envelopes plus one Rememberer allowance: one full
foreground reservation can coexist with up to one foreground envelope of prior
settled actual use. Individual run limits and the one-live-root rule are
unchanged. The subscription AgentRuntime lane has no normalized priceable
`CallMeta`; Jarvis does not invent a dollar estimate.

Preflight capacity denial performs no provider I/O and does not claim or
increment an input. Under the same execution mutex, the later kernel admission
reservation MUST NOT return a capacity denial after that successful preflight;
the adapter raises `AdmissionStateDefect` for an inconsistent journal so the
kernel parks the claim rather than returning ordinary deferral.
Owner/action-resolution work remains unprocessed and is eligible at the
journal's reset instant through one ordinary process timer plus the startup
scan. If the delay is at least 60 seconds, Jarvis inserts at most one
host-rendered assistant notice for `(oldest_input_message_id, reset_at)`, using a
deterministic application UUID as `message.id`; shorter delays are silent.
Background rememberer and dreamer work always defers silently. Poison-attempt
exhaustion is not deferred: it consumes the input with the existing visible
stopped conclusion.

Jarvis's checkpoint finalization maps the conversation conclusion and
`processed_at` to the existing atomic transaction. Read observations and
protocol correction stay turn-local; write outcomes are durable through
`action` and the `llm-tools` recorder mapping. The optional kernel event sink is
best-effort private observability, not a canonical event store, and sink failure
is nonfatal.

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
| `calendar.list_calendars`, `calendar.list_events`, `calendar.get_event` | Main | Read; automatic |
| `calendar.create_event`, `calendar.update_event`, `calendar.delete_event` | Main | Automatic only for a no-attendee event on a verified owner-only calendar; otherwise approval required |
| `maps.search_places`, `maps.get_place`, `maps.directions` | Main | Read; automatic |
| `web.search`, `web.read` | Main | Public-Web read; automatic |
| `schedule.wake` | Main | Write; automatic |
| `codex.list`, `codex.read` | Main | Native worker read; automatic |
| `codex.start`, `codex.prompt`, `codex.interrupt` | Main | Native worker control; automatic only when grounded in current owner input |
| `memory.search`, `memory.open` | Recaller, rememberer, dreamer | Read; automatic |

Codex controls require an explicit `personal | work | work2` profile and exact
opaque native handles. `codex.start` validates bounded lexical input, asks the
closed host helper to resolve an existing canonical host-permitted cwd, creates
a prompt-free native thread there, unsubscribes the Jarvis control connection,
creates and observes one ordinary tmux session through the closed host helper,
then submits the bounded prompt. The stock TUI attaches asynchronously; Started
does not claim TUI readiness. Jarvis never answers worker-native approvals.

`codex.prompt` exposes Codex 0.153.4's native Submit operation, which atomically
starts or steers and returns the accepted turn handle without distinguishing the
two. Explicit Steer includes the expected turn handle. Interrupt uses the pinned
exact-turn App Server precheck and reports Interrupted, natural Finished, Stale,
or Unknown; it is never retried or knowingly redirected to an observed
successor. Strict idle-only NewTurn and a core interrupt CAS are not v1 claims.
Writes use `ReplayPolicy.BilledOnce`, one executor entry, typed surviving launch
prefixes, and terminal uncertainty after ambiguous dispatch. No absent status,
name, cwd, newest thread, or original input permits redispatch.

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
The pinned reader binding implementation is `llm-tools-web-read-v2`. Its
model-visible `extraction` identifier is `plain-text-v2` for literal plain text
and `html-visible-text-v2` for visible HTML/XHTML text. These projections decode
character references exactly once; plain text is never treated as markup.

The production Brave binding uses the pinned `llm-tools`
`operation_deadline_seconds=12.0` policy. Each selectable Slice 2 frozen plan
tightens `web.search` to one external attempt and retains `BilledOnce`; its
aggregate limits are ten calls, 222 external attempts, 73,768 input bytes,
786,432 output bytes, one in-flight model-tool call, and 205 seconds. The
maximum role definition permits 223 attempts and 1,638,400 output bytes.
Jarvis adds no second deadline wrapper.

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
executor fence; discovery permits two attempts and 15 seconds. The read and
scheduled-read aggregate output ceiling is 786,432 bytes, leaving 262,144 bytes
for follow-up detail reads after one maximum list result. Slice 5 and active Main
selected output ceilings are 1,249,280 and 1,708,032 bytes. The Slice 2
new-context ceiling is 706,144 bytes; active Main retains its sufficient
600,000-byte ceiling.
Provider-turn, model-call, and write-gate ceilings do not change, so the rolling
admission journal requires no migration.

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

### 7.4 Model step protocol and bounded drain

The kernel accepts exactly one strict logical discriminated step per model
response:

```text
say
  Discord-ready text

call_tool
  canonical granted tool ID
  arguments

finish
  optional internal reason
  result required only by a closed structured output contract
```

Unknown fields are rejected. `provider-runtime` enforces the declared JSON
schema and the kernel independently revalidates the complete semantic step,
output contract, exact frozen-plan binding, and pure `llm-tools` arguments before
visible output, position occupation, recorder mutation, budget reservation, or
dispatch. Protocol-invalid output performs no effect and becomes bounded
corrective context. Exhaustion persists a host-authored stopped conclusion and
cannot obtain a new correction budget through automatic rearming.

The Codex provider wire is a kernel-owned transport projection, not a second
logical protocol. It is one closed root object with four required fields:
`type`, `say`, `call_tool`, and `finish`. `type` selects exactly one non-null
closed payload; every other payload is null. Optional logical values such as
`finish.reason` are required-but-nullable on the wire. For `call_tool`, the wire
`arguments` field is a string containing one strict JSON object. The kernel
rejects duplicate keys, non-JSON constants, non-object roots, malformed branch
selection, and invalid logical/tool arguments before dispatch. Jarvis MUST NOT
decode, manufacture, or bypass this envelope.

A `StructuredOutput` compiles its result schema into the provider-supported
closed subset when the immutable definition is built, before provider I/O.
Unsupported contracts fail with `UnsupportedStructuredOutputError`. Arbitrary
result mappings are unsupported; variable-key results use arrays of closed
key/value records. Provider-wire compilation never replaces the independent
Pydantic logical-result validation.

`call_tool` contains no user-facing text, model-authored call/effect ID,
preview, authority label, approval instruction, or delivery instruction. It
proposes exactly one serial call. The host creates or resolves a durable
`action` before any `Write` executor entry only after AutomaticWriteGate allows
the validated proposal. It uses `action.id` as both the `llm-tools`
`InvocationPosition` and `EffectId`. Gate denial becomes a typed policy
observation with no action or dispatch. The executor returns a bounded completed
`ToolResult`, which becomes input to the next model turn, or Jarvis durably
accepts the work and returns a suspension waiting for the owner or system
reconciliation. Only after a completed observation may Main make a separate
truthful structured terminal.

The Main definition forbids `say` and requires `finish.result` to match the
closed `JarvisTerminal` schema from section 4.2. Jarvis consumes the kernel's
existing `StructuredConclusion`, applies the run-local incomplete-observation
policy, and host-renders the result before canonical settlement. Each internal
structured definition likewise forbids `say` and requires `finish.result` to
match its own closed schema. Internal `Pure`/`Read` calls may use attempt-scoped
positions and non-durable recording; consequently a `Read + BilledOnce`
operation may be billed again after a crash. V1 accepts that bounded cost
instead of a generic durable observation store.

The main model never classifies authority. Jarvis policy selects the plan,
requires current-owner grounding, and maps an allowed write into its product
action lifecycle. A suspension settles the proposing input and releases the
provider session lease. A later host-authored message
starts a new input batch containing the action ID, tool name, original validated
arguments, resolution state, and safe evidence. Terminal `uncertain` remains a
Jarvis action result after tool-specific reconciliation, not a kernel retry
signal.

`KernelLimits` own provider turns, protocol repairs, cooperative elapsed time at
safe boundaries, normalized provider usage, and cumulative bytes of
kernel-rendered model-visible material newly submitted in the current
invocation. `max_cooperative_seconds` supplies a hard remaining deadline to a
provider turn but is not an end-to-end latency guarantee: host ports, dispatch,
settlement, parking, and cleanup may finish later, after which the next safe
boundary prevents further work. Jarvis MUST NOT put a blunt outer timeout around
a `Write`. `max_new_context_bytes` excludes provider system/developer material,
output-schema transport overhead, retained native history, and provider
compaction; Jarvis bounds and qualifies those surfaces separately. The
kernel-owned contained-agent base instruction counts inside Jarvis's independent
system-material ceiling and its exact identity is qualified. The frozen
`llm_tools.RunLimits` alone own tool calls, attempts, input/output bytes,
concurrency, and tool deadlines, with `max_in_flight = 1`. Jarvis and the kernel
MUST NOT double-charge these budgets. V1 has no parallel dispatch,
multi-call step, or model-authored progress narration; Discord typing state is
the progress indicator. The kernel retains its general `say` branch for other
consumers, but the Jarvis Main definition makes that branch unavailable. Jarvis
adds no second model protocol.

The grammar has no approval preview. Host rendering is specified in section 5.3.

### 7.5 Codex containment

Codex receives no connector, Brave, or embedding credentials, generic shell,
writable project checkout, MCP server, or direct execution-authority tool
channel.

Jarvis uses only `provider_runtime.agent_runtime.AgentRuntime` with
`JsonSchemaAgentOutput`. Its pinned provider owns a protocol-bound WebSocket
connection to the profile's host-owned Unix-socket App Server; `transport="sdk"`
is the closed agent-transport discriminator, not a claim that a Python SDK owns
request handling. Every cognition session uses an empty absolute cwd
beneath the dedicated non-secret host parent. That asserted-empty directory is
mode `0750`, granting the shared-runtime group only read/traverse so the
development-UID server can enter it; no Jarvis application state is shared. Cognition retains
read-only filesystem policy, no additional directories, disabled network,
approval mode `deny`, no MCP servers,
`CodexNativeOptions(builtin_tools="disabled")`, and disabled native Web search.
The Codex `allowed_tools=("*",)` sentinel required by the compatibility API is present
only for runtime compatibility; it grants no Jarvis authority.

The kernel prepends its immutable 682-byte contained-structured-agent
instruction to every new, resumed, reconstructed, threaded, isolated, and
initial-Read request. Application instructions remain separate and cannot
remove it. The exact instruction identity is
`llm-agent-kernel-contained-structured-agent-v1:sha256:1817c90f24bf9149f20f94b69f825d9be0b78df8bb46b1d24ed2691cf71b80e7`.
Prompt obedience is defense in depth; typed provider events and host policy own
authority.

The provider adapter MUST drive and inspect the public `stream_turn` event
stream. It MUST NOT call `AgentRuntime.run_turn` in production: that convenience
method projects only the terminal and discards the intermediate events needed
to enforce this boundary.

The provider recognizes only its audited inert notification/item whitelist.
Command, file, MCP, dynamic/custom, collaboration/sub-agent, Web, image,
generation, sleep, hook, and defensive function-output activity becomes
`AgentToolUse`. Permission, user-input, and MCP-elicitation requests are denied
and become `AgentPermissionRequest`. An unknown request receives JSON-RPC
`-32601`; any unknown item, notification, lifecycle transition, malformed or
mismatched identity, or terminal following authority activity is a fatal
`ProtocolDefect`. Generic `AgentNative` fallback is forbidden.

An `AgentToolUse`, `AgentPermissionRequest`, or `ProtocolDefect` fails the confined turn,
taints and discards the session, returns no terminal to the Jarvis loop, and
permits no host dispatch or model-authored conclusion. Native passthrough events
are limited to the audited bounded/redacted inert set. Streaming `AgentText` is
never delivered or executable; only the provider-selected completed
`final_answer` and then the kernel-validated structured step from a fully
inspected clean stream can become a Jarvis response. A stopped provider turn
produces a truthful host-authored visible failure and never accepts a model
terminal.

Native Code Mode is contained and detected, not claimed impossible before its
first observable event. The exact Codex 0.153.4 server/TUI, disabled features,
no-network/read-only sandbox, empty shared-runtime-traversable cwd, closed event
classifier, and fail-stop session invalidation are one qualified unit. Protocol
drift deliberately breaks availability until audited.

The Linux deployment runs Jarvis as the dedicated unprivileged `jarvis` account
and the three shared Codex services as the development account. Root-managed
environment files remain mode 0600 and systemd injects their values only into
the Jarvis host. Before opening any provider connection, Jarvis marks itself
non-dumpable. A dedicated local group grants only App Server socket access and
traversal of empty cognition directories; it grants no Jarvis home, database,
connector, or environment-file access. Shared-server containment is not a
general host-confidentiality boundary.

### 7.6 Concurrency

Exactly one Jarvis service instance owns a deployment. A PostgreSQL advisory lock
at startup prevents overlap.

Within that one process, an ordinary in-process execution mutex permits at most
one active Jarvis cognition turn or Jarvis host-tool dispatch at a time, and the kernel
input-checkpoint port grants at most one exclusive root work epoch for the main
application thread. AutomaticWriteGate is a serial child: the main run is paused
before effect dispatch while the isolated gate one-shot runs synchronously under
the same root ownership; the parent performs no provider or tool I/O and no two
provider calls overlap. Foreground owner work takes precedence over
rememberer and dreamer work. Kernel cancellation stops background cognitive work
at a defined boundary; recomputation occurs only on a later explicitly admitted
schedule, never by unconditional cleanup rearming.

Accepted Codex workers execute independently in the three host-owned App
Servers after dispatch. Their native event streams never enter the serial
cognition decoder, consume its provider lease, or grant new Jarvis authority.
The launch action terminates at truthful native/host acceptance; Jarvis neither
waits durably for worker completion nor schedules a successor from it.

No second PostgreSQL conversation lock is required while the global ownership
lock holds. The root admission reservation owns one concurrency slot; a gate
child shares it only because its parent is paused and its maximum usage was
reserved. Normal cleanup settles/refunds in `finally`; startup releases an
orphaned slot without refunding its still-live rolling turn/token charge.

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
- Backup and restore: deliberately deferred beyond v1. Loss of the devbox,
  database, or disk can permanently lose Jarvis state; adding backup later does
  not require an application-schema change.
- Testing: pytest, Hypothesis where useful, library-supplied test doubles, and
  synthetic or redacted connector fixtures.
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
  `6c0acdc541b21ef6bb0f4626cd957f0101324573`
- `llm-calling` / `provider-runtime`:
  `834ea544f1d7437ce2a32b17d4cc813e75a06fa2`
- `llm-tools`: `9e6d155f3b64f03495911435b7cae8b8d131f9a2`

The Devbox host pins `@openai/codex@0.153.4` for all three services and stock
TUI clients. Jarvis and the kernel carry no Python Codex SDK or bundled Codex
executable; `provider-runtime` declares its WebSocket client directly. A Codex
pin or wire change requires explicit host, provider-runtime, kernel, and Jarvis
requalification before activation.

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
mode 0600 under `/etc/jarvis`. The release MUST attach only to the host-declared,
pinned shared Codex services rather than start or bundle a private runtime. The
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
  processing_attempts
  processing_parked_at
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
- Every waking owner or host message is inserted before its turn with
  `processed_at = NULL`, non-negative integer `processing_attempts = 0`, and
  `processing_parked_at = NULL`.
- Host action-resolution messages are inserted idempotently from terminal
  `action` state with `processed_at = NULL` and are never delivered to Discord as
  if the owner authored them.
- `processed_at` is set on a waking owner or host row only when its response,
  silent finish, or approval proposal is durably recorded.
- `processing_attempts` atomically increments when the checkpoint port acquires
  a claim after successful rolling-capacity preflight and before plan-budget or
  provider work. It deliberately counts a crash or configuration defect after
  claim. It is not a retry instruction; it is the durable poison-input ceiling
  across crashes and process restarts.
- `processing_parked_at` is nullable `timestamptz` and canonical
  operator-quarantine control. The kernel
  checkpoint `park` transaction stamps it on the claimed unprocessed batch;
  ordinary claims and recovery scans exclude parked rows, and any parked row
  opens the v1 cognitive circuit until explicit operator repair clears it.
  `trace` may record a bounded reason code but is never queried as control state.
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
- `arguments` is the sole source of the model-proposed and user-visible effect
  payload used for approval rendering and execution. `id` is the only additional
  input to a deterministic provider effect identity such as the Calendar event
  ID; it cannot change the approved payload.
- `execution_contract` is non-null closed host-authored JSONB containing the
  exact `tool_contract_revision`, `implementation_revision`,
  `policy_revision`, `plan_revision`, `ToolEffect`, `ReplayPolicy`, canonical
  `input_digest`, finite `max_attempts`, `claim_id`, canonical
  `through_checkpoint`, `model_step_ordinal`, ordered `input_message_ids`, and
  `write_gate_supporting_owner_message_ids`. It is not a model field or general
  version registry. Host code verifies it before every approval rendering,
  executor entry, replay, or reconciliation.
- Within that contract, `policy_revision` covers the deterministic authority
  policy and the AutomaticWriteGate definition fingerprint, including its
  prompt, model configuration, and output contract.
- `origin_message_id` is the first waking message in the original claim and
  remains a convenient stable root pointer. Recovery uses the execution
  contract's complete admitted-input lineage, not that one pointer alone.
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

Queued or approval-bearing rows whose `tool_name` is unsupported or whose stored
arguments or execution contract no longer validate fail closed as `cancelled`
and are reported. An existing name MUST remain backward-compatible while a
non-terminal action uses it. Before an incompatible schema or semantic change,
the deployment owner resolves or cancels those actions. A future incompatible
implementation MAY earn a distinct versioned successor name; v1 stores no
general version registry. The per-row execution contract exists to make one
occupied effect position replay-safe, not to dispatch multiple implementation
versions.

The action ledger must not become a duplicate message or memory store.

### 9.3 Other state

Existing connector credentials, cursors, and adapter state remain in their
current owned stores. Owner/guild/channel identity and the paused flag live in
deployment or host configuration. The main `AgentSessionRef` and immutable
agent-definition fingerprint live in private runtime state outside PostgreSQL
through the kernel `SessionRefPort`. Provider session state is non-canonical and
rebuildable. A second atomically replaced
private runtime journal stores the bounded rolling admission window for all
cognitive work. It contains reservation/run IDs, windows, counters, timestamps,
reserved/actual capacity, and state only—no prompts or user content. Clean exits
settle and refund unused capacity. Startup under the deployment lock marks
orphaned reservations interrupted, releases their concurrency slots, and
retains their conservative turn/token charge until window expiry. Missing or
corrupt state fails closed until an explicit operator reset. Alembic may own its
migration table.

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

V1 has no backup or restore path. The main provider session reference,
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
- The pinned `llm-agent-kernel` port/conformance contract and the Jarvis-owned
  product-context, session-reference, input-checkpoint, admission, dispatch, and
  event adapters.
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

- Secrets remain outside model context, PostgreSQL, fixtures, and ordinary logs.
- PostgreSQL and private service ports are not publicly exposed.
- V1 has no backup or restore mechanism. Operations record the accepted risk
  that host, disk, or database loss may permanently destroy Jarvis state.
- Production activation does not reboot the shared devbox. A pending kernel
  update remains explicit operational debt for an owner-selected maintenance
  window; tmux sessions and their live processes are not treated as recoverable
  across that reboot.
- Jarvis uses live tools for current external state and distinguishes that state
  from recalled memory.
- Discord typing is the only synchronous progress signal. A persisted Main
  terminal is final unless it names an already committed suspended action;
  collection completeness comes from typed host evidence, never model prose.
- External success comes from a provider receipt or reconciliation evidence,
  never a model assertion.
- Failed and uncertain actions are reported honestly.
- Ordinary logs exclude credentials, private message bodies, raw email bodies,
  and complete memory text.
- Provider work is admitted through the durable rolling journal; corrupt state
  fails closed, orphaned concurrency is released without refunding reserved
  rolling capacity, and poison inputs cannot renew their budget across restarts.

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
- Host-rendered approval and one approved email send protected by draft identity,
  reconciliation, and honest terminal uncertainty rather than a universal
  exactly-once claim.
- At least seven days of owner use producing genuine cognitive offloading.

## 13. Change control

Frozen decisions:

- One visible Jarvis and natural Discord interaction.
- One host-rendered typed Main terminal with no production `say` or in-progress
  variant; incomplete typed evidence is visibly partial.
- One configured Discord channel with no v1 server-organization tools.
- Exactly four application tables.
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
  owner-directed Codex controls.
- Host-rendered approval previews and the stated autonomy boundary.
- A restricted AutomaticWriteGate grounds every model-proposed write in current
  owner-authored input before action creation, without granting new authority.
- Unversioned canonical v1 tool names with immutable stored calls and
  per-action execution contracts plus deployment-time compatibility discipline.
- Finite lifetime executor-entry ceilings and action-backed schedule creation
  receipts that remain replayable across the later wake lifecycle.
- No v1 redaction or destructive memory consolidation.
- No Android, OnePassword, Nexus, Skidbladnir source/API, or other unlisted
  application integration. Worker terminals are ordinary tmux sessions visible
  through unchanged Skidbladnir.

Changing one requires an ADR stating observed evidence, migration impact, and
the acceptance criteria affected.

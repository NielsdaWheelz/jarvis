# architecture

This document expands [SPEC.md](../SPEC.md). its accepted native cutover and
[native integration contract](native-agent-integration.md) govern main execution;
the frozen baseline governs unchanged domain behavior.

accepted target, not yet implemented: [universal memory](universal-memory.md) is
the single current implementation contract; [adr 0063](decisions/0063-simplify-memory-policy-and-retrieval.md)
records the latest simplification. admitted collectors activate native lanes
online from complete inventories and submit complete events for atomic capture.
one shared search implementation fuses keyword and semantic ranks deterministically;
agents choose when to search. disposable background inference may repeat paid work,
but notes/bookmarks and summaries/pending flags commit atomically. main's durable
recovery remains. the memory roadmap remains unimplemented; native main retains the existing
recaller until that separately authorized cutover.

shared policy values have one checked-in owner and one implementation, including
the search/embedding client and search gate across main, dreamer and mcp callers.
lane provenance, admission, connection and progress remain scoped; executor budgets
and mutable turn state remain per run. agent prompts state goals, available context
and evidence requirements, leaving useful steps to the agent. host protocol,
permissions and effect preconditions still bind every step. native readers validate
mapped fields and ignore unrelated additions; model and api schemas stay closed.

## System shape

```text
Discord ingress -> canonical requests/controls -> native runtime
                     ^                            |         |
                     |                       progress    callbacks
                     |                            |         |
                  context                    outbox    kernel validation
                     ^                            |         |
                     |                         Discord   read recorder
               original receipts                         / write gate
                     ^                                      |
                     |                                action/approval
                     |                                      |
                     +------------ original results <--- executor
```

one Python application and PostgreSQL database own product state. the shared
kernel supervises native input/callback/control ordering; provider-runtime owns
the native protocol; llm-tools owns declarations, plans, validation and execution.
existing memory roles and connectors retain their owners.

## Physical deployment

V1 runs on the existing Hetzner `dev-server`, never on the Nexus production
host. Jarvis is a host-native systemd service under a dedicated `jarvis` Unix
account. Immutable releases live at `/opt/jarvis/releases/<git-commit>` and an
atomic `/opt/jarvis/current` symlink selects one release.
`/opt/jarvis/releases` retains that selected release, with one temporary candidate
during installation. successful activation removes every other installed release;
rollback requires rebuilding its exact commit. deployment commands share one
host file lock. Runtime state lives in
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
attaches to the separately contained personal Codex endpoint and carries no
private SDK runtime or bundled Codex binary. systemd owns the additional host.

this endpoint requires stock `0.160.0` and the provider-owned complete restricted
catalogue at host startup. public version/config checks run before thread
creation; catalogue updates require explicit qualification. adr 0065 supersedes
adr 0042's latest-stable rule here without changing unrelated coding services.
the root-owned schema-4 `/etc/jarvis/codex-host.json` declares only its personal
endpoint and explicit host/app/group/cwd identities.

`llm-agent-kernel` is a pinned independent library, not another service or
state owner. it supplies native supervision and serial dispatch plus the actual
isolated one-shot protocol, input/control ordering, containment and conformance.
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

1. persist/deduplicate inbound messages; controls update request/action authority.
2. acquire the dedicated database owner and one conversation claim. freeze the
   exact main or scheduled-read-only plan.
3. build canonical context from messages, recall and original tool receipts.
   retain every unfinished request and its accepted actions.
4. invoke the shared native supervisor. reader, ingress, input polling and outbox
   stay live while one callback executes.
5. validate and commit each immutable invocation before entering the read recorder
   or write gate/action ledger. writes identify the original delivered request.
6. commit the original result and exact model reply before native delivery.
   pending approval returns a receipt; independent reasoning continues.
7. commit the original sealed terminal before decoding per-request dispositions.
   publication completes only explicitly completed requests.
8. deliver persisted messages and enqueue existing memory work. usage is
   observational; no rolling capacity store or arbitrary main cutoff remains.

controls, consent and actual effect entry share the existing conversation lock
order. callbacks and approved actions share one dispatch lane. ingress, outbox and
approval processing use independent service tasks. stop cancels unentered work;
entered effects retain truthful settlement/reconciliation obligations.

## Context and session lifecycle

main retains a healthy compatible live lease only in the current process.
fingerprints cover exact provider policy, native base instruction, role/output,
plan/bindings and owner-controlled revisions. changed identity opens a fresh
session. saved native bindings are evidence, never a session cache.

connection/process/owner loss fences old callbacks permanently. a fresh process
restores reasoning from canonical requests/context and original tool receipts.
computation may repeat; unknown entered actions or billed-once reads cannot.
old accepted actions replay/reconcile through their existing owner; new native
call ids cannot authorize equivalent effects again.

original sealed terminals settle locally under a new owner without provider I/O.
later stop/resume refuses stale product settlement while preserving terminal and
usage. local stop and missing native ids never prove non-submission.

recaller, rememberer, dreamer and AutomaticWriteGate remain fresh isolated roles,
using owner permits instead of paid-capacity reservations. the empty-plan gate
uses its parent's owner and invocation identity; only restricted effect facts
and owner input enter its context, never the main session history.

## Cognitive roles

These are five immutable kernel agent definitions, not a general subagent or
persistent-peer system. The main role is a native callback turn with a closed
structured terminal contract and a maximum envelope equal to the exact main
catalog. Recaller, rememberer, dreamer, and AutomaticWriteGate are fixed isolated
one-shot runs with closed structured output contracts. The first three have
memory-read envelopes; the gate has none. Jarvis supplies a frozen subset plan
per run; owner/action-resolution runs use the full Main plan and scheduled-wake
runs narrow the same native definition to external reads. One-shot plans
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

main uses `NativeDefinition`, serial declared host callbacks and strict
`JarvisNativeMessage` wire output. commentary validates as `Progress(type, text)`
with empty `input_outcomes`; only its bounded prose becomes canonical public
text. final output uses final-only `JarvisTerminal` complete/continue/waiting
dispositions. [spec section 4.2](../SPEC.md#42-conversation-is-natural) owns this
phase contract. the kernel validates declarations and pure inputs before durable
dispatch. progress cannot settle requests or grant action authority.

main alone receives the owner-approved voice/profile. their revisions participate
in its fingerprint. it owns no credentials, policy or effect identity. owner input
grounds writes; Web retains its existing explicit-owner-request admission.

host-rendered model text stays separate from original executor results. kernel
submits that projection unchanged. immutable replies replay original text instead
of rendering it against current state.

### AutomaticWriteGate

For each validated main-agent `Write`, this role opens a fresh isolated session
while the main callback awaits effect dispatch. it runs synchronously under
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
- returns the original bounded `ToolResult` or durable pending-action receipt;
  commits it and the exact model reply before native delivery.

Canonical message persistence, raw-memory append, and summary replacement are
application transactions. They are not model tools and do not pass through
`llm-tools`; terminal conversation persistence is exposed to the agent kernel
through its isolated checkpoint or native journal boundary.

native reads use original durable read positions and fresh plan-derived budgets.
main cumulative limits are null; operation bounds remain. the Web secret gate
checks raw and decoded string leaves before recorder/executor/provider entry.
reads never create action rows.

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

`run_native` supervises one admitted turn and all callbacks. ordering:
validate -> immutable invocation -> host/executor acceptance -> original result ->
immutable reply -> provider delivery. dispatch is serial; reader/control remain
live. unknown tools, changed identities, lost ownership and protocol defects fence
the attempt. pending approval yields a durable wait receipt.

the action owner projects each validated stored action to its original tool
result. the recorder, callback journal and `existing_action_ref` dispatch reuse
that projection; journal reads stay inside their current transaction. wait and
schedule lifecycle outcomes and private worker-control evidence remain separate
from the immutable callback result.

main has no cumulative call/token/byte or elapsed cutoff. finite operation limits,
in-flight/frame/message bounds and provider/control timeouts remain. llm-tools
owns tool budgets and settlement exactly once. usage never grants authority.

isolated roles retain `run_one_shot` and its strict serial step protocol. this is
an actual separate role, not a fallback main path.

main commentary checks current authority under the conversation/attempt lock:
stale commentary is an atomic no-op; live commentary validates the whole strict
wire message and persists prose plus its exact raw-message digest. only validated
final dispositions settle requests. original binding and observations of already
prepared deliveries may commit after fencing; new preparation still requires
live authority. these facts renew neither dispatch nor product authority.
recovery decodes the original sealed terminal against its frozen output schema
before final-only validation,
without current definitions or another provider call.

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
native attempt ID, through-checkpoint, callback ordinal, ordered admitted input IDs, and
write-gate supporting owner IDs that occupy the `llm-tools` position. The
executor and approval renderer revalidate both it and the stored arguments. This
is per-effect recovery evidence, not a general version registry. An incompatible
tool change drains or cancels non-terminal actions; a versioned successor is
introduced only when coexistence is required.

## Approval rendering

the native callback supplies the declared tool and exact `ActionRequest` envelope:
`request_ref`, nullable `existing_action_ref`, and typed operation `arguments`.
the action stores the complete envelope; authority and approval render its inner
payload. when policy requires approval:

1. Resolve the selected declaration and host renderer, and render the exact
   validated arguments before creating durable state.
2. Insert the action and host-owned approval message in one transaction, storing
   the internal message ID as `approval_message_id`. return its durable pending
   receipt while retaining the request and allowing independent reasoning.
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

PostgreSQL owns `message`, `memory_log`, `memory_summary`, `action`,
`model_decision`, `read_position`, `native_attempt`, `native_invocation` and
`native_input_delivery`. existing integration state remains with its owner.
message owns request/control state; action remains the sole effect ledger.
native rows retain original requests, lineage, provider facts and immutable
replies. product publication is separate from the provider terminal commit.

configuration owns identity, channel, timezone, models and credential locations.
stop/pause is canonical message control. no session-reference file, rolling
capacity journal or file-backed pause writer remains. stopped `cutover-native`
and migration 0005 reject unresolved legacy effects/reads, retain historical
facts and require fresh approval for unentered old work.

## provider containment

cognition attaches to the separate personal stock app-server over its private
unix socket. the provider-owned 0.160.0 catalogue is restricted at host startup
to direct declared callbacks, with inherited clock and native user-input removed.
the provider verifies exact native version and startup configuration before
thread creation. thread policy disables built-ins, native web/network, mcp,
subagents and permission grants; its cwd is empty, read-only and non-secret.
per-thread catalogue settings cannot supply the host ceiling.

main consumes native turn events and declared callbacks through the shared
supervisor. stock strict output applies to both message phases, so the wire schema
includes one explicit progress case. live phase validation rejects raw prose and
final-shaped commentary; stale commentary publishes nothing. no fallback or
terminal-envelope extraction exists.
the shared native base v3 permits the application's commentary format and
automatically rotates definition fingerprints through its revision/digest.
only canonical progress prose reaches delivery; the validated final terminal
alone carries request dispositions. isolated roles use `stream_turn` and
accept only their strict completed output. every native authority event,
permission request, unknown active item or identity defect fail-stops the turn.
raw tool visibility prevents a hidden vendor CodeMode wrapper from passing as
inert activity. callback arguments validate before host execution and original
results/replies commit before wire delivery.

host web tools execute the frozen `llm-tools` binding outside the model session;
no native browser or network authority is granted. the kernel owns its base
instructions and containment fingerprints. application prompts supply role and
content, never native credentials or an alternative authority boundary.

systemd owns the separate native process and isolated physical socket root.
only the group-readable socket and empty cognition directories cross identities.
root-owned application secrets stay unreadable by the service account; jarvis
becomes non-dumpable before provider connection and exposes a restricted `/proc`
view. the development account retains its personal authentication. changing this
endpoint cannot alter the owner's existing coding server.

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

- owner/connection loss fences old callbacks. fresh reasoning restores unfinished
  requests; unknown entered effects and billed-once reads still block.
- original native seals survive local validation/publication failure. replay uses
  original evidence with current owner/publication fences.
- unsupported configuration/schema/authority fails before provider/effect entry.
  protocol faults stop the attempt; they never select fallback routes.
- stop cancels unentered approvals/work and retains entered settlement.
- malformed terminal output cannot complete requests or replace provider truth.
- rememberer failure leaves its source eligible; dreamer failure retains notes
  and summaries; embedding failure retains existing lexical behavior.
- delivery retries original persisted identity under existing bounds. delayed
  text may rarely duplicate; action effects cannot.
- committed consent survives interrupted acknowledgement. startup disables old
  components and resumes/reconciles the original action without model replay.
- executing actions reconcile before repeat. unresolved external outcomes retain
  safe evidence and require owner reconciliation.

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

the bounded trace records each settled input's original run/checkpoint/conclusion
identity plus relevant IDs and counters. progress alone completes no request.
action rows carry correctness-critical native attempt/checkpoint/input/callback lineage in
their immutable execution contract; `origin_message_id` is only the stable root
pointer. Private payloads and model prose are not duplicated into trace. Trace
details are implementation diagnostics and rememberer-group reconstruction,
never a memory-ranking signal in v1.


## Shared-kernel durable recovery

[ADR 0040](decisions/0040-shared-kernel-durable-decisions.md) adds two narrowly
owned records: `model_decision` preserves exact paid inference and host validation
evidence; `read_position` implements the existing llm-tools recorder for Reads.
recoverable isolated roles use stable model-decision identities. native main
uses its own attempt/invocation/input-delivery records.
Unknown dispatch stops automatic retry. The original Write action remains the
sole effect owner and is recovered before any model decision can replay.

Every store in production uses the same dedicated deployment-lock connection for
short serialized transactions. Losing it blocks inference admission, read dispatch,
action acceptance, memory mutation, and result publication; it never reconnects.
The exact authenticated catalog selection is frozen into role definitions and
therefore session fingerprints. Application prompts remain application-owned;
the shared containment instruction remains owned by llm-agent-kernel.

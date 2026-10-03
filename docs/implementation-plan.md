# jarvis: roadmap and implementation plan

updated 2026-10-01. this is the ONE active roadmap and delivery plan, combining
universal memory and the approved v2 direction. implementation/activation of
these targets is not established by this document. no code or deployment changes
are authorized merely by documenting their order.

[SPEC.md](../SPEC.md) remains normative. the
[universal-memory contract](universal-memory.md) supplies its accepted schemas,
apis, bounds and acceptance; other v2 slices still need their owning adr/spec
changes before implementation. [operations](operations.md) owns deployment and
repair. [adrs](decisions/README.md) preserve rationale; retired delivery checklists,
qualification reports and completed cleanup logs live in git history.

## destination and rules

one visible jarvis remembers context, keeps useful working records and carries
ordinary work forward across personal, scientific, creative and practical life.
one undivided memory serves all admitted/connected machines and profiles. the
owner should not have to repeat context or repeatedly initiate obvious follow-up.

- agents receive context, tools, goals and quality constraints; they choose their
  method. delegation and retrieval guidance are prompt defaults, not mandatory
  tool sequences, a routing engine or a prescribed agent organization.
- policy is global: shared constants/configuration have one owner; callers reuse
  clients, pools, admission, search, append functions and validators. preserve
  subject-specific provenance/permissions/progress and fresh invocation state.
- provider-runtime owns native transport; the kernel supervises cognition;
  llm-tools owns tool contracts/execution; jarvis owns product context, authority,
  persistence, events and continuation. dev-server owns fleet configuration;
  skid owns worker launch/control. reuse their existing public primitives.
- one main, one deployment lock and ordinary scheduling. no workflow framework,
  descendant graph, worker-consumption accounting, duplicate state ledger,
  speculative service, generic shell bridge or compatibility fallback.
- durable effects, canonical commits, truthful outcomes and reliable stop remain
  host responsibilities. new background memory computation is disposable.
- hard-cut replaced paths, preserve canonical data, and state costs in the owning
  contract. distinguish source merged, dependency pinned, fleet installed, live
  behavior verified and owner-resumed service.

## current position and immediate work

the native cutover has nine application tables: the original six plus three
native journal tables. accepted universal memory adds three; the later work
slice adds one. derive migration dependencies from the actual predecessor;
do not hard-code a stale total into independently developed slices.

adr 0052 is the current skid worker boundary. its recorded source/client work does
not establish current cognition activation. the latest
[cognition activation issue](issues/codex-private-process.md) records jarvis
disabled, stopped and durably paused on 2026-09-29. confirm live state before
deployment. adr 0063 selects a separate contained stock endpoint using the
existing host-owned personal account; unrelated coding servers stay intact.

| immediate item | owner / what it blocks |
| --- | --- |
| [claude retention](issues/claude-transcript-retention.md) | dev-server; preserve native recovery history before memory capture activation; verify every configured home |
| [shared cognition](issues/codex-private-process.md) | provider-runtime/dev-server/jarvis; jarvis live activation, including full memory acceptance; does not block independent codec/storage development |
| [nexus dispatch contract](issues/nexus-generation-dispatch-contract.md) | shared provider/kernel o3–o4; distinguish proven non-submission, accepted terminal and unresolved submission; nexus consumer adoption is independent of jarvis product o5–o9 |
| [embedding attempts](issues/embedding-retry-accounting.md) | jarvis shared embedding client; one actual attempt must match reported search usage |
| [skid cli mismatch](issues/skid-terminal-flags.md) | jarvis adapter; preserve captured refs/mode while removing obsolete read/stop flags; can land before new delegation |
| [adr numbering](issues/adr-number-collision.md) | docs integration; preserve both independent 0053 records and renumber references when merging with current main |
| [verification scope](issues/testing-redesign.md) | separately requested testing redesign; memory retains its narrow exception, orchestration cannot borrow it |

these are separate small repairs/decisions, not a new prerequisite mega-pr.
check their issue records for evidence and resolution criteria; do not infer
completion from a plan, a date or an unmerged local file.

existing operator follow-ups also remain recorded: [admission journal cutover](issues/admission-journal-cutover.md),
[connector environment cutover](issues/connector-keyring-cutover.md),
[hosted ci billing](issues/github-actions-billing.md) and
[old qualification resources](issues/qualification-residue.md). confirm current
state before closing them; removing their old reports does not resolve them.

## delivery map

preserve the approved priority on orchestration. start fleet launch and native
callback work independently; design work-history semantics alongside them.
memory codecs/storage can proceed in parallel where files/contracts do not
conflict. memory completion is not a prerequisite for delegation, and native
callbacks are not a prerequisite for native transcript capture.

ids below identify work units, not github pr numbers or a fixed pr count. the
existing orchestration prs 1–9 map to o1–o9. owners may split a unit at a real
public boundary; do not add speculative plumbing to make work parallel.

| unit | owner / useful result | depends on |
| --- | --- | --- |
| o1 | skid: raw launch options, defaults and initial prompt | current skid contract |
| o2 | dev-server: publish/pin/install that launch release on the fleet | o1 |
| o3 | provider-runtime: contained native host-tool callbacks and live control | installed-provider proof |
| o4 | kernel: native-turn supervision using existing dispatch/execution | o3; public llm-tools seam only if needed |
| o5 | jarvis: durable native main and owner-controlled interruption | o4; shared cognition repaired before live activation |
| o6 | jarvis: one main capability set for all supported event origins | o5; separate authority adr/spec cutover |
| o7 | jarvis: one work table with history/current view and durable stop | work-state decision; independent of o3–o6 implementation |
| o8 | jarvis: richer start and nonblocking `agent.wait` | o2, o6 and cli repair; NOT o7 |
| o9 | jarvis: continuation and prompt-led coordination | o5–o8 |
| m1 | provider-runtime: native archive codecs, identity and echo suppression | capture contract; retention before activation |
| m2 | jarvis: source schema, automatic baseline, atomic capture/collector | m1 public contract; provider proof before live capture |
| m3 | jarvis/llm-tools: source-only extraction and pending-note dreaming | m2; production transient read recorder |
| m4 | jarvis: shared search/open/save and private mcp | m2; shared embedding policy; sdk contract |
| m5 | jarvis/dev-server: one memory cutover and fleet activation | m1–m4, retention, lane declarations and shared cognition |

native-loop and authority changes remain separate releases: proving transport
and effect recovery first costs an intermediate release but makes failures
attributable. memory's review units converge on its one stopped schema/legacy
cutover; they do not authorize partial fleet claims or an old/new runtime fallback.

## orchestration delivery

### o1–o2: fleet launch

extend skid start with machine/profile, provider-compatible raw model/effort,
cwd and optional freeform initial prompt. profile determines provider/account;
provider convenience selection must resolve a compatible profile. keep one launch
configuration declaration, including compatible profile defaults; explicit start
values override those defaults, otherwise retain provider-home defaults. jarvis
supplies its configured machine/profile when omitted. unsupported pairs fail;
no capability tiers, hidden model substitution or shell interpolation.

skid owns readiness and initial prompt submission. preserve the created terminal
ref if submission fails or is unknown; never relaunch after ambiguous creation.
creation, submitted prompt and completed work are distinct facts. retain ordinary
start without a prompt. dev-server pins the immutable release/configuration and
verifies the intended artifact on each peer without replacing jarvis cognition.

exit: literal prompts survive quotes/newlines; defaults/overrides work; partial
launch remains inspectable without replay; fleet-installed identity is recorded.

### o3–o4: native transport and supervision

provider-runtime exposes declared tools, correlated callback requests/results,
thread/turn/call identity, final output, usage, steering and interrupt during a
stream. the codex adapter lowers them to native declarations and `item/tool/call`;
it imports no jarvis authority or llm-tools policy. the kernel publishes the
frozen catalog, validates callbacks, dispatches serially through its existing
host port and validates the final structured outcome. codex owns the inner loop.

reuse llm-tools schemas, validation/execution and recorder interfaces; add a public
projection seam there only if missing. accepted-invocation/checkpoint ports must
work before a native final answer. the input/control port stays live even when
no callback arrives: steer compatible input, durably queue other input, observe
owner stop promptly. an admitted write reaches settlement/reconciliation before
interruption releases the lane. retain separate isolated one-shot memory roles.

exit: multiple callbacks within one native turn; exact declared tools only;
undeclared shell/file/web/network and permission paths remain unavailable;
interrupt/disconnect/resume preserve call/result identity and catalog; invalid
calls cannot execute. experimental transport needs installed-provider evidence,
not a shell/http bridge or private-process fallback. see
[native callbacks](issues/native-tool-callbacks.md).

nexus supplies a second consumer for this shared work; its
[dispatch contract](issues/nexus-generation-dispatch-contract.md) is part of
o3–o4. validate incompatible requests before native submission, retain bounded
original diagnostics, and preserve valid native terminal evidence before product
acceptance. prove authoritative non-submission, accepted failure and successful
strict-json research with actual tools; possible submission without a terminal
remains uncertain. current exception names and missing acceptance events do not
prove absence. introducing new submission evidence requires coordinated
provider/kernel adr and spec changes, not a consumer exception workaround.

the accepted shared native spec now replaces both application tool bridges with
the same frozen native declarations and callback execution contract. nexus's
remote-shell route is deleted at its native cutover. domain connectors and
authority remain application-owned. nexus adoption does not depend on jarvis
product o6–o9. [adr 0063](decisions/0063-native-agent-supervision.md) and the
[integration handoff](native-agent-integration.md) govern jarvis's current cutover.
its queue, metadata schema, publication and short deadline stay nexus-owned.
old uncertain admissions retain their existing recovery obligations.

### o5: native main

cut main to the new pins with an adr/spec change and session-compatibility rotation.
initially preserve current event authority. persist each accepted invocation before
dispatch and its result before the native reply, using the three native journal
tables plus existing `read_position` and `action`. `model_decision` remains only
for genuine isolated inference. native call ids correlate replies; durable host
ids own effects. reuse the same reads, writes, approvals and reconciliation.

replace main's eighteen-turn/nineteen-call loop with native execution until
completion, a genuine blocker, required input or owner stop. no arbitrary elapsed
cutoff or cumulative usage quota. operation and transport deadlines remain.
pending approval returns a durable receipt while independent reasoning continues;
later action-resolution input resumes the original request without another effect.
callback reply/interrupt ordering belongs in this slice.

o5 records a truthful interrupted conclusion without inventing a continuation
registry; o9 adds follow-through. current owner permits replace capacity
reservations. preserve per-tool byte/deadline/effect-attempt bounds.

exit: several tools in one native turn, live steering/stop, pending approval that
releases the turn, safe crash/reconnect and distinct timeout versus explicit stop.
no second main. live activation also requires shared cognition repair and explicit
owner resumption; this plan does not resume a stopped service.

### o6: one main for every event

owner messages, action results and scheduled wakes receive the same main tools
and approval rules. background origin alone is not read-only and need not invent
fresh owner input or obtain a new standing instruction. jarvis may initiate
ordinary work and schedules, or do nothing. consequential effects still await
exact-action approval; do not add another permission conversation before preparing
that approval. source identity stays honest and cannot elevate permissions.

replace current-owner-only write grounding, the read-only wake plan and affected
action lineage together in the authority adr. preserve immutable arguments,
classification, reconciliation and stop. define the common entry path for worker
results, email and internal suggestions; migrate supported sources now. new
source adapters/cursors belong to later source slices, not a second event engine.

specify visibility: ambient events may be silent; requested reminders, action
outcomes, failures and approval requests need an explicit notification contract.
compatible input steers the live native turn; incompatible input queues durably;
stop uses the control path. equal authority does not itself implement email ingress.

exit: equivalent owner/wake/action events get equal capabilities; automatic writes
need no fabricated owner text; consequential writes retain approval; incoming text
cannot change authority; unrelated input remains serviceable during a long run.

### o7: one work table and four attention states

one table covers tasks, projects, commitments and things to track; descriptive
project detail may live in a linked markdown note. jarvis automatically decides
whether an event warrants work and manages it without approval.

| active state | meaning |
| --- | --- |
| doing now | actually being worked on; reasonably clear completion estimate |
| blocked | named owner and specific blocker; daily review until actionable |
| next up | at most three priorities; invest definition/design here, without inventing work to fill empty slots |
| backlog | lightweight capture; do not pre-plan everything |

start from title, attention state, content and possibly due date plus necessary
identity/bookkeeping. owners, blockers, estimates and links stay prose unless a
required operation needs a field. due date and next review time differ.

**unresolved:** the owner requested both automatic crud and “append-only for now.”
settle stable identity, retained history/current view, completion/cancellation/
archive/deletion and durable continuation-enabled/stopped semantics before schema
implementation. append-only revisions in one table are a candidate, not a decision.
see [work-state semantics](issues/work-state-semantics.md).

reuse an item for the same work. keep its top-level coordinator ref, brief,
estimate and results there; no row for every specialist. work owns whether a job
may continue; actions own wait registration/outcome; the scheduler owns timed-wake
eligibility. a prose link alone cannot enforce stopped state after restart.

exit: the chosen history survives update/finish; active views obey the four
states; stopped work remains stopped after restart. ordinary read/list supplies
the later dreamer snapshot; daily new-note batching does not depend on o7.

### o8: richer start and asynchronous wait

extend existing `agent.start`; add register/cancel on `agent.wait` in the same
family. retain `agent.send` and ordinary observation/stop/close. freeform prompts
and worker output; no task packet, output schema or mandatory work id.

reuse schedule-style `action` durability: an immutable registration receipt returns
`watching` immediately; an out-of-mutex host watcher calls skid wait/read on the
captured target and persists a later outcome plus ONE source-deduplicated ordinary
action-resolution message. restart resumes observations and repairs delivery,
never resends the worker prompt. a changed target is an outcome, not permission
to follow its replacement. work linkage is optional context, not a second ledger.

specify overall timeout and bounded observation retries; the currently inspected
skid wait caps a call at one hour. chunk timeouts continue host observation without
scheduled model polling. accept fast completion before registration against the
available native observation boundary. terminal idle can be stale: report terminal
evidence honestly, never successful completion of a newly sent request. preserve
raw prose and action/ref/status metadata. cancel stops observation, not the worker.

repair obsolete `--terminal` read/stop flags without losing requested mode or
captured ref; `--history` is native-only. see [cli repair](issues/skid-terminal-flags.md)
and [wait contract work](issues/agent-wait.md).

exit: register, serve another owner message, receive one later result; repeat
across restart. distinguish fast completion, stale idle, timeout, target change,
interruption and unavailable evidence. no mutex held while waiting.

### o9: continuation and coordination

after connection loss and effect reconciliation, eligible unfinished work
gets another run from canonical context and captured refs. explicit stop first
disables continuation durably, then interrupts. queued events and startup respect
that state; only explicit resumption rearms stopped work. native session loss
cannot erase work or authorize replaying an effect. use the existing scheduler
and o7 work state, not a continuation service.

prompt default: owner → jarvis → coordinator → specialists. substantial work
normally gets one coordinator; a simple job can use one worker. research,
inspection and explanation qualify alongside coding. prefer `gpt-6-astra` with
`xhigh` for coordination and `gpt-6-sol` with `xhigh` for individual work. these
are declared prompt defaults, not capability classes or mandatory choices.
jarvis/coordinator choose model, freeform brief, fanout and verification. the owner
can inspect/interact directly through skid; jarvis remains available.

submission is not completion; a native turn ending is not proof of task success.
no hierarchy-depth policy, descendant registry, child budgets, worker accounting
or subtree cancellation is introduced. exit: observed results integrate into
normal main turns; unfinished work continues safely; explicitly stopped work
stays stopped across restart and pending approval never repeats an effect.

## memory delivery

one corpus contains source evidence, append-only notes and derived summaries.
all connected agents can search/open; admitted connected agents and jarvis main
can save notes directly. no recaller or context push. personal/work labels never
partition recall. source-only extraction batches separate conversations by size
or age; dreaming begins with pending notes and MAY search. both use disposable
inference and atomic progress. use the detailed
[contract](universal-memory.md), not duplicated schema/API prose here.

| unit | implementation boundary / done when |
| --- | --- |
| m1 | provider-runtime `agent_runtime/archive.py` and codecs: complete listing/heads, read-only complete events, stable capture-relevant identity/digest, internal marking and memory-tool echo suppression; validate consumed fields while tolerating unrelated metadata; prove installed-provider mappings |
| m2 | jarvis `memory_sources.py`, collector/api, schema/migration: atomic automatic activation and event/checkpoint commits, stateless host collectors, parked errors and operator status; retry/crash preserves boundaries and stored evidence |
| m3 | `memory.py`, workers, rebuild and embeddings: one append, direct source lineage, bounded nonoverlapping extraction and pending-note summary settlement; public production llm-tools transient read recorder; zero-search/empty completion, bounded fresh retries and no background replay journal |
| m4 | retrieval, tool adapters and composition: one keyword/vector rank-fusion pipeline, global policy/client/pool/gates, one-attempt embedding, shared search/open/save, main save identity/recovery, private mcp and admission; resolve the pinned mcp-sdk constraint, not a reranker-selection phase |
| m5 | messages/checkpoints/service/migration + dev-server: drain old memory work, preserve existing rows, cut old remembered_at/recaller paths, install private endpoint/collectors/profile config and activate admitted lanes online; no historical import or dual reader |

m2–m4 can be developed against frozen public contracts; live capture requires m1
proof. revise one shared policy/primitive at its owner, not copies in each unit.
retain complete parent and child archives and tool payloads: those feature cuts
were considered but NOT approved. keep source/identity suppression before capture
and one undivided corpus with independent admission/connection permissions.

m5 uses one local pre-migration dump/runtime copy and the existing stopped cutover.
its exact restore limits and admission-charge drain are in the memory contract.
no backup platform, native-memory disablement or automatic history import. full
acceptance includes all declared hosts/profiles; disabled/unqualified lanes are
reported, not passed off as universal coverage.

### memory and native-main integration

these tracks share invocation identity, source publication, library pins and
composition, not a new agent layer. coordinate shared-file changes and serialize
their release cutovers; do not maintain two implementations to support arbitrary
merge order.

- o4/o5 preserve a host-owned accepted-invocation position BEFORE every callback
  dispatch and a recorded result BEFORE replying. this supplies internal note
  idempotency and search recovery. raw native call ids are not durable effect ids.
- source publication must reconstruct consumed/produced messages and source tool
  observations from durable host evidence under either deployed execution model.
  retrieved memory/save bodies remain content-free references; cognition remains
  excluded at native capture. update that ONE adapter during the native cutover.
- memory retains current write authority, including main's full-plan canonical-note
  exception: action-resolution turns can save without owner grounding. scheduled
  turns remain read-only. o6 extends capabilities to scheduled/new origins outside
  that full plan; amend affected grants there, never silently in m4.
- native main changes only main's loop. rememberer/dreamer retain their isolated
  transient path; callbacks do not require restoring background inference journals.
- universal memory reaches twelve tables after the native nine; o7 contributes
  the one work table. sequence actual migrations and revalidate owner permits and
  definition revisions against the deployed predecessor, preserving canonical rows.

## subsequent product slices

these are approved direction, with the listed design still due. none is a
prerequisite for delegation or initial universal memory. accept a focused contract
when its implementation begins; do not turn every open question into present code.

### private notes repository and rolodex

jarvis owns a private github markdown repository with automatic read/create/edit/
move/organize/delete, including self-initiated work. git records revisions; no
notes approval. support project briefs, procedures, research, drafts and one
natural-language document per person; no people table.

specify confined access, search/listing, stable cross-links, move/delete behavior,
revision/history and git sync. memories/work/documents can link each other without
duplicating current task state. editable notes confer no authority; no generic
filesystem access, general document platform or implied drive/docs integration.

### complete and continuable searches

support further pages and continued scans across runs, especially gmail, notes
and work. specify collection/time scope, changing-source behavior, cursor/progress
ownership and truthful omissions. larger hit limits do not establish completion;
never promise snapshots a connector lacks. duplicate delivery/continuation cannot
duplicate task capture or effects. reuse ordinary search/read and durable context.

### event sources, suggestions and recurring work

build actual email ingress, polls, timers and internal suggestions on o6's common
event path. neither equal capabilities nor a prompt implements a source adapter.
rememberer/dreamer may originate useful thoughts, but main decides whether to act,
record work, schedule, seek exact approval or ignore them. route independent
background suggestions through durable main messages; if an actual host invocation
already exists, its ordinary result may carry them. this introduces no callable
rememberer/dreamer tool or competing coordinator.

specify sources/cursors and deduplication; recurrence, timezone, overdue/downtime
behavior; daily blocked-item review; finite recurring spend under global admission;
notification versus silence; cancellation and pending-approval relationships;
stop/pause/resume across new triggers and running work; and prevention of loops
from unchanged polls, repeated suggestions or jarvis's own outputs. work, action
and scheduler each retain one canonical responsibility. no lesser background agent.

### dreamer work context

after m3 and o7, add a bounded dated projection of doing now, blocked and next up
through ordinary work reads, fixed for one invocation with explicit omissions.
a retry can read current state. work is attention context, not summary evidence;
summary lineage still ends at notes. main alone changes work and rechecks its
current state before acting on a suggestion. no work tool grant or task planning
inside memory roles. work changes do not trigger dreaming; daily blocked review
is a separate main duty. preserve personal, scientific and creative coverage.

### attachments and original storage

accept discord/gmail images and documents, initially including receipt photos,
pdfs, text and common document formats. enumerate exact formats/limits, visual
versus text reading, durable capture/access, retention and failure behavior.
retain addressable originals in private cloudflare storage; r2 is the candidate,
not a provisioned service. preserve page/source references. expiring transport
links are not durable originals or backup of jarvis state. link binaries from
notes/memory rather than putting them into the markdown repository.

jarvis uses ordinary tools to interpret, summarize, save, capture work or prepare
a reply. conventions should avoid repeated instructions; ask when intended handling
or source detail is unclear. audio and harder attachments remain v3+.

### budget integration

when specifying this slice, **spawn the owner-requested subagent** to inspect the
current budget repository/api/ingestion surfaces. do not reuse the stale claim that
it only supports load/save, or expose private finance data/credentials. this is a
specific investigation requirement, not a mandatory runtime agent procedure.

the budget app owns records, arithmetic and reconciliation. define supported
reads/writes, duplicate handling, source-linked receipts, ambiguity/correction and
replay. journey: upload → retain original → extract → record expense once through
its actual api → linked confirmation. expense bookkeeping does not authorize a
payment; consequential financial actions keep the defined approval boundary.
no competing ledger in notes or memory.

### deferred from universal memory

separately specify historical imports (pre-activation lanes, legacy codex homes,
old canonical jarvis messages and old-note lineage), including deduplication,
provenance, extraction cost and order; off-machine backup; and disabling or
reconciling native automatic memories. retained native history preserves an import
opportunity, not proof of capture. preserve existing messages/notes in the meantime.

forgetting/exclusion is outside the prototype and is not promised v2 work.
automatic external context injection was rejected, not deferred; future push
would require a new authority design. learned reranking may be reconsidered only
from measured retrieval failures; keep one current ranking path.

other earlier ideas remain uncommitted/outside this delivery: extra discord
channels, api-backed cognition, model-generated program execution, selected
onepassword access, jarvis-to-nexus product integration, android and generic
computer use. nexus's shared provider/kernel contract work remains in o3–o4.
revisit other ideas only for an observed need with their own contract. notes do
not imply a google-drive integration.

## decisions and verification

remaining decisions have owners; do not reopen settled broad autonomy, automatic
notes, cloudflare originals, nonblocking waits, freeform delegation or explicit-stop
precedence merely because their implementation is incomplete.

| before implementing | decision / evidence owner |
| --- | --- |
| o3–o5 | installed native callback containment, outstanding-call/reply/interrupt behavior and shared-cognition connection |
| o6 | replacement authority/lineage and notification rules for equal-capability turns |
| o7 | append-only versus crud, current view, terminal/deletion semantics, continuation/stop representation |
| o8 | exact register/cancel inputs, observation boundary, overall timeout and partial evidence |
| o9 / new event sources | recurring eligibility/spend, notification, cancellation/approval coupling, stopped work and self-trigger suppression |
| m1–m5 | actual provider mappings/internal markers, declared lane controllers/sharing, mcp sdk compatibility, shared embedding retry repair |
| notes / attachments / budget | stable references/sync; formats/storage/retention; fresh budget api audit and ingestion contract |

[adr 0046](decisions/0046-reset-testing.md) remains in force. run `scripts/verify`
for static/build checks; do not claim behavioral acceptance from it. memory's
scoped exception permits only its small capture/retry and memory-completion checks
plus focused synthetic live boundary evidence. orchestration must obtain its own
authorized verification scope through the testing redesign or an explicit scoped
contract; it cannot borrow memory's exception. other repos follow their own rules.
no old suite, replacement framework or recurring fleet qualification is added here.

integrated acceptance journeys, when their owning verification is authorized:

- one client's new conversation/direct note becomes searchable from another host;
  capture/extraction/dreaming interruptions do not lose or duplicate committed work.
- jarvis delegates substantial research through skid, stays responsive, receives
  one asynchronous observation after restart and distinguishes evidence from success.
- a native connection is lost: fence callbacks, reconcile effects and recover eligible work; explicit
  stop survives restart and prevents continuation or repeated effects.
- an email or memory-role suggestion may create useful work without forged owner
  input; irrelevant input creates no make-work; consequential communication still
  waits for exact approval.
- project review reflects real active work/estimates, named blockers with daily
  review, at most three next priorities and completed work outside the active view.
- a receipt survives as an addressable original and becomes one source-linked
  expense through the budget app, including repeated delivery and correction.

promote slices through their own adr/spec changes, exact pins and removal of old
paths. inspect shared-library impact. qualify transport, then effect durability,
then authority, then restart/stop behavior. preserve existing user work. stop
admission and reconcile outstanding effects before incompatible pins/migrations;
code rollback never reverses external effects or new canonical data. use the
operations runbook and the memory contract's exact cutover rules.

## recorded integration evidence

these are earlier observations, not current release assertions. refresh them in
the owning slice: codapt2 was inspected at
`38452c8d6b14ac6ea0d180f4450350946a092fcd` (fetched main
`c0e79fb566d8fc0be8a0e562750f09355254eac3`); its native turn, six-hour interruption
and stop precedence informed o3–o5. do not copy its shell/workspace-http bridge.
skid source was `564d32fe1743d9ba5d8478d6ef2095633b1dd240`, installed client
v0.10.7 / `240141b`; source and installed bytes differed. inspect `../skid-v1`,
not the stale `skidbladnir` checkout. current live facts belong in issue/qualification
records, not duplicated status claims throughout the roadmap.

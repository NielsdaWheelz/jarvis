# jarvis: roadmap and implementation plan

updated 2026-11-15; simple event-driven v2 adopted by
[adr 0071](decisions/0071-simple-event-driven-v2.md). shared memory remains a
separate delivery. notes, searches, events, attachments and budget have focused
contracts; the selected v2 cut and later work are distinguished below.
this is the ONE active feature roadmap and delivery plan. native cognition and
worker control are implemented foundations; the remaining product direction and
operational cutovers are distinguished below. a roadmap entry authorizes no
runtime change, release, deployment or resumption.

[SPEC.md](../SPEC.md) remains normative. the
[universal-memory contract](universal-memory.md) supplies its accepted schemas,
apis, bounds and acceptance. adr 0071 adopts the selected v2 feature contracts;
later search, dreamer-context and budget amendments remain separately scoped.
[operations](operations.md) owns deployment and
repair. [adrs](decisions/README.md) preserve rationale; retired delivery checklists,
qualification reports and completed cleanup logs live in git history.

## terminal-only worker cutover — source implemented and isolated-qualified

[adr 0069](decisions/0069-terminal-only-workers.md) and the linked skid spec
own terminal-only worker control, closed schemas and opaque retired-row loading.
[adr 0072](decisions/0072-native-memory-rollout.md) advances the binding to v10
and adopts enrolled `macbook|dev-server|arch` names without aliases; memory's
`devbox` identity stays unchanged. fourteen actual cli/postgres checks pass.
the read-only mounted state boundary and actual installed service-uid reads pass
on both online hosts; [installed evidence](universal-memory.md#native-memory-installed-qualification)
does not replace the separate worker observation journey.

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
- durable effects, canonical commits, truthful outcomes and deployment pause/shutdown remain
  host responsibilities. new background memory computation is disposable.
- hard-cut replaced paths, preserve canonical data, and state costs in the owning
  contract. distinguish source merged, dependency pinned, fleet installed, live
  behavior verified and owner-resumed service.

## current position

the source has fifteen application tables: the native nine plus six memory
tables. migration `0008` adds no table. the later work
slice adds one including scheduling, events add one cursor table and attachments
add one. there is no separate recurring-wake table. derive migration dependencies from the actual predecessor;
do not hard-code a stale total into independently developed slices.

source refresh 2026-11-14: memory delivery and current main are composed, retaining
the existing provider/kernel/tools pins and adopting the shared claude-work2
account contract. targeted registry fixes resolve the later dependency audit;
full `scripts/verify` passes. [current source evidence](universal-memory.md#native-memory-rollout-source-qualification)
records the exact pins, migration/worker checks and restricted service-boundary
proof. the [online installed rollout](universal-memory.md#native-memory-installed-qualification)
now passes with its named profile deferrals; broader product acceptance remains separate.

the native provider/kernel/tools work is merged. jarvis [pr 49](https://github.com/NielsdaWheelz/jarvis/pull/49)
merges native main and worker-v7 composition. [adr 0065](decisions/0065-native-agent-supervision.md)
and the [integration handoff](native-agent-integration.md) own the current runtime:
declared callbacks, owner permits, public prose progress, explicit request
dispositions, independent reasoning during approval, durable stop and fresh-thread
reasoning recovery. there is no six-hour cutoff, rolling paid-capacity reservation,
saved-session recovery or main structured-step loop. existing effect/read barriers
remain. the separate contained stock endpoint replaces the old shared cognition
direction. current qualification is recorded in [acceptance](acceptance.md#native-cutover-acceptance).

skid [pr 61](https://github.com/NielsdaWheelz/skidbladnir/pull/61) implements launch
options/input and concise controls. jarvis [adr 0064](decisions/0064-simple-worker-orchestration.md)
introduced immutable captured targets and asynchronous wait/cancel. current
[adr 0068](decisions/0068-generalized-skid-consumer.md) uses live installed state
and profile-owned provider options; [adr 0069](decisions/0069-terminal-only-workers.md)
owns terminal-only worker control; adr 0072 adds v10 and enrolled host names.
those completed
source handoffs do not need another worker-protocol specification.

the authorized rollout started from stopped/paused production at schema `0004`.
the current owner's skid `v0.24.2` artifact reads actual live state through the
installed read-only mount. matching host/application/cli installation and owner
resumption and online memory acceptance are complete within the named profile
deferrals. installed worker observation remains separate work.

pending worker search may inspect only retained terminal history through
`agent.read`; it cannot promise complete saved conversations or route silently
to provider-native archives/shared memory. independent memory retrieval remains
its own explicitly selected capability.

## operational cutovers and upkeep

| item | owner / remaining result |
| --- | --- |
| skid release and fleet cutover (o2) | matching cli and read-only live-state mount are installed; qualify launch/control/observation while preserving existing gateways/membership; [cutover issue](issues/skid-terminal-flags.md) |
| native jarvis activation | same-release host/application, stopped conversion, owner resume and normal memory turn pass; [installed evidence](universal-memory.md#native-memory-installed-qualification). remaining physical google checks stay in their [issue](issues/codex-private-process.md) |
| installed worker observation | jarvis repeats the relevant receipt/restart/notification journey against the coordinated installed fleet; [wait deployment issue](issues/agent-wait.md) |
| claude retention | dev-server manages long retention on every configured home before memory capture activation; [issue](issues/claude-transcript-retention.md) |
| current memory artifacts | source dependency fetch/build/audit and online installed rollout pass with named profile deferrals; nexus image/runtime qualification waits for its next release; [image handoff](issues/nexus-memory-image-qualification.md) |
| standing verification design | separately scope the [testing redesign](issues/testing-redesign.md); completed native/worker exceptions do not create a standing suite |

these are independent release, repair or policy tasks, not another prerequisite
mega-pr. preserve [old qualification-resource disposition](issues/qualification-residue.md) and
nexus's [historical job disposition](issues/nexus-generation-dispatch-contract.md)
with their owners. none is resolved merely by merging a new runtime.

## delivery map

the roadmap is organized by useful product behavior. legacy o/m labels remain
cross-references for existing handoffs, not github pr numbers or a fixed pr count.
o1, o3–o5 and o8 are implemented foundations; o2 is the operational cutover above.

| feature | contract / specification work | owner and dependencies |
| --- | --- | --- |
| one main for every event (o6) | [contract and evidence](one-main-events.md) implemented and isolated-qualified; installed activation pending | jarvis; builds on native main; source adapters remain separate |
| useful work records (o7) | [contract](work-records.md) adopted by 0071; mutable todos with optional one-time/repeated wakes unimplemented | jarvis; one table and existing timer |
| delegated follow-through (o9) | [contract](delegated-follow-through.md) source behavior implemented with o6; installed skid observation remains slice 3 | jarvis; o6 plus installed skid observation; o7 supplies optional bookkeeping |
| universal memory (m1–m5) | [completion contract](memory-delivery.md) implemented and installed on the online jarvis/native fleet with named profile deferrals; nexus waits for its next release | memory library, jarvis, provider-runtime, llm-tools, dev-server and nexus-web; [memory delivery](#memory-delivery) |
| private notes and rolodex | [contract](private-notes-and-rolodex.md) adopted by 0071; unimplemented | jarvis plus kernel/provider native-access handoff; ordinary private checkout, agent-chosen git, prose people records |
| event sources and recurring work | [contract](event-sources-and-recurring-work.md) adopted by 0071; email/calendar ingress and ordinary internal append unimplemented; recurrence belongs to o7 | jarvis; o6, source references/cursors; no memory amendment |
| attachments and durable originals | [contract](attachments-and-durable-originals.md) adopted by 0071; unimplemented | jarvis plus dev-server; one table/private bucket, ordinary native tools; notes native access prerequisite |
| complete and continuable searches — later | settled [contract](complete-and-continuable-searches.md) retained; adoption/implementation separate, including uncapped ranked memory | jarvis, memory library, llm-tools and skid/provider history; deliver only necessary source/attachment references within the selected v2 slices |
| dreamer work context — later | [contract](dreamer-work-context.md) retained outside this cut; selected dream wakes also deferred | jarvis; m3 and o7; quiet memory delivery unchanged |
| budget integration — later | settled [contract](budget-integration.md) retained; full bookkeeping authority and larger originals need separate adoption/implementation | jarvis plus budget-app; existing ledger/api, private object storage and attachment/native-reading prerequisites |

the work view and delegated follow-through do not wait for full memory. its
separate pr retains its own source/integration handoffs and stopped cutover.
do not respec completed foundations or reconstruct memory's superseded adr chain.

### v2 reviewable pr slices

these are implementation boundaries, not opened prs or deployed work.
each completes its scoped behavior and proportionate checks; intermediate slices
need not be independently usable. upstream changes stay in the repository that
owns their public interface.

the documentation baseline landed in pr 60 (`8c0bf36`). for each slice, audit and
finish its owning spec against current source; hand it to an implementation
agent; review the diff/evidence, resolve gaps and land the implementation.
prepare the next spec against that updated system. refine existing feature
contracts in place rather than introducing parallel work orders.

| order | review unit | completion and dependency |
| --- | --- | --- |
| 1 | common main and conversational consent | [source-audited spec](one-main-events.md): common request lifecycle, full plan, atomic conversational consent, scoped stop and recovery; remove gate, component approval and old scheduler; installed worker outcomes are proved in 3 |
| 2 | todos and scheduled turns | o7: CRUD, optional one-time/repeated wake, atomic publication and conversion of retained reminder obligations; replaces scheduling removed in 1 |
| 3 | installed skid follow-through | reuse adr 0072's qualified state mount, use current terminal-only start/control/wait and prove installed asynchronous result/restart delivery; depends on 1 and matching artifacts, not a new worker protocol |
| 4 | ordinary private repo | notes: minimal kernel/provider native-access handoffs, persistent checkout, native files/git and small file deliverables; isolated memory roles retain their existing posture |
| 5 | attachment originals and reading | discord/email ingress, private r2, stable references and image/pdf/file inspection; depends on 4 and necessary email attachment manifests, not the entire later search overhaul |
| 6 | external event sources | email/calendar cursor adapters publish ordinary inputs while main is busy; depends on 1; daily review is an ordinary todo from 2 |

independent investigation of 4's upstream needs and 6's source interfaces may
proceed alongside earlier units; finalize their specs after prior work lands.
the owner accepts incomplete intermediate slices. remove replaced paths in their
own slice; do not retain a compatibility scheduler or make each pr independently
deployable. keep reminder obligations in the private cutover inventory until 2;
unattended activation waits for the selected slices and accounted-for commitments.
3 reuses existing observation source and is installation/repair work unless proof
exposes a missing primitive. source review of 1 does not claim installed o9
acceptance; 3 supplies its fleet/discord/restart evidence before that behavior is
called delivered. no implementation, live test or cutover is performed
by this documentation update.

v2 includes ordinary progress, blocker questions, approvals and completed results
inside these journeys. it does not add standalone components for them. approval
meaning is main's judgment; reuse the existing action decision transition, with
no exact-prose matching or additional consent system. defer browser control, new
credential handling, interactive deliverables/television and a separate ui.

## external specifications and handoffs

jarvis owns product intent and consumer obligations. each external unit gets a
bounded repository handoff from its owning contract: public inputs/outputs,
identity and failure semantics, limits/costs, acceptance evidence and the exact
consumer adoption. record prepared, handed off, implemented and adopted as distinct
facts; writing this roadmap sends no assignment to another agent.

| repository owner | remaining handoff | specification source / status |
| --- | --- | --- |
| skid / jarvis deployment owner | install the enrolled owner's exact current cli at the fixed service path | [terminal-only contract](decisions/0069-terminal-only-workers.md), [rollout amendment](decisions/0072-native-memory-rollout.md); v0.24.2 task-mount reads and v10 source decoding pass; installed proof remains |
| skid, search | page worker inventory and retained terminal text before response fencing; preserve terminal-only control and explicit retained-screen limits | [search composition](complete-and-continuable-searches.md#receipts-and-external-composition); later handoff, not implemented; provider archives and shared memory remain separately selected capabilities |
| dev-server | selected cli/collector installation, long claude retention, private routing, client/capture credentials and native mcp configuration; arch deferred | memory [ownership](universal-memory.md#2-ownership-and-admission), [collector](universal-memory.md#collector-and-normalization) and [retrieval](universal-memory.md#6-retrieval) contracts adopted in its spec; source and isolated host reconciliation qualified; installed fleet handoff remains |
| llm-calling (`provider-runtime` package) | m1 archive enumeration/heads/events, capture identity, internal marking and memory-tool echo suppression | [native capture contract](universal-memory.md#3-native-capture); public archive api/codecs implemented and source/live-qualified; actual fleet admission separate |
| llm-calling (`provider-runtime` package), notes | native built-ins plus declared callbacks in one session, both declared authority postures and host qualification | [notes public contract](private-notes-and-rolodex.md#public-contracts-and-deployment); bounded handoff prepared here, not handed off or implemented |
| kernel, notes | frozen application-owned cwd/native configuration, retained checkout lifecycle, native activity alongside host callbacks | [notes public contract](private-notes-and-rolodex.md#public-contracts-and-deployment); bounded handoff prepared here, not handed off or implemented; no llm-tools change |
| jarvis deployment owner on dev-server, notes | persistent private checkout, ordinary git authentication, host permissions and hard-cut host mapping | [notes deployment contract](private-notes-and-rolodex.md#public-contracts-and-deployment); source changes stay in jarvis's existing deploy files; operator bootstrap/install remains separate |
| memory library | existing archive/tree/view/search; add explicit nexus source values and atomic export append/duplicate proof through shared insertion primitives | [core](universal-memory.md), [completion handoff](memory-delivery.md#non-overlapping-implementation-boundaries); uncapped ranked [search amendment](complete-and-continuable-searches.md#uncapped-ranked-memory) remains a separate delivery |
| kernel + llm-tools | production transient read recorder for disposable dreaming using the existing recorder/executor seam | [daily dreaming](universal-memory.md#daily-dreaming); production recorder published; coordinated kernel/tools/provider pins adopted; request-fit and strict json fixes qualified |
| llm-tools, search | portable web-search paging/provider boundaries and complete supported extracted-text chunks, retaining web safety | [search surface contract](complete-and-continuable-searches.md#exact-surface-changes); bounded handoff prepared, not handed off/implemented; no kernel redesign |
| budget-app | broaden existing write authority to all bookkeeping, reuse shared planner calculation through an api, and support independent originals up to 100 mib through private r2 | [budget api handoff](budget-integration.md#budget-api-handoff); fresh `7b7a9c2` source audit complete; bounded handoff prepared, not assigned or implemented |
| budget deployment owner and dev-server | budget private bucket/cors/storage secrets; jarvis configured budget origin/owner/read/write credentials and native cache access | [budget delivery](budget-integration.md#nonoverlapping-delivery-and-hard-cutover); provisioning and installed qualification remain separate |
| nexus-web | configured owner's librarian tools and future-only durable capture; terminal snapshot/outbox/publisher, current call identity and native internal marking; no automated-helper tool grants | [completion handoff](memory-delivery.md), [client issue](issues/nexus-memory-client.md); adr 0070 source and isolated current-route qualification complete; nexus release deferred |

the [completion evidence](universal-memory.md#memory-completion-source-qualification)
qualifies the implemented nexus capture and isolated native/jarvis journeys.
the [latest source evidence](universal-memory.md#native-memory-rollout-source-qualification)
adds registry, profile and deployment-boundary repairs. neither establishes
installed client acceptance. dev-server owns native private configuration;
nexus credentials/publication wait for its next release.

downstream jarvis code consumes the published public surfaces and qualified pins;
the external agents do not own jarvis authority, work state or continuation.
the memory library owns its memory schema under the accepted deployment contract;
jarvis owns the composed migration and canonical request/effect schema.
new shared-library work is requested only for an identified missing primitive.
there is no further generic kernel/skid orchestration redesign in this roadmap.

one mcp server lives inside jarvis. dev-server configures native codex/claude
clients and installs the capture collectors; it does not implement another memory
server. nexus's application agents require their own client bindings, distinct
from developer agents working in the nexus repository. adr 0070 explicitly adds
its distinct account-owned capture source; adr 0072 declares nineteen native/jarvis
lanes, including each host's separate claude-work2 home.

## orchestration delivery

### o1–o2: fleet launch

o1 is implemented. current worker v10 start accepts machine/profile and optional
name/cwd/group/freeform initial prompt. the configured profile command owns
provider/account/model/effort; creation has no model/effort overrides. jarvis
chooses an available machine/profile. preserve one launch configuration owner,
literal input and explicit refusal for unsupported targets.

skid owns readiness and initial prompt submission. preserve the created terminal
ref if submission fails or is unknown; never relaunch after ambiguous creation.
creation, submitted prompt and completed work are distinct facts. retain ordinary
start without a prompt. dev-server pins the immutable release/configuration and
verifies the intended artifact on each peer without replacing jarvis cognition.

source qualification covers literal prompts, configured profiles and inspectable
partial launch without replay. o2 still publishes/pins/installs the coordinated
artifact and records each peer's installed identity. use the existing fleet
release contract; no additional launch design is due.

### o3–o4: delivered native transport and supervision

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

the shared native contract and N001–N020 qualification are complete. multiple
callbacks, frozen declarations, contained authority, live control and original
result/terminal evidence are delivered public library behavior. use the current
[acceptance evidence](acceptance.md#native-cutover-acceptance); retired candidate
containment failures and missing-callback claims do not reopen this work.

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
product o6–o9. [adr 0065](decisions/0065-native-agent-supervision.md) and the
[integration handoff](native-agent-integration.md) govern jarvis's current cutover.
its queue, metadata schema, publication and short deadline stay nexus-owned.
old uncertain admissions retain their existing recovery obligations.

### o5: delivered native main

main has adopted the qualified native pins under adr 0065 and preserves current
event authority. it persists each accepted invocation before
dispatch and its result before the native reply, using the three native journal
tables plus existing `read_position` and `action`. `model_decision` remains only
for genuine isolated inference. native call ids correlate replies; durable host
ids own effects. reuse the same reads, writes, approvals and reconciliation.

native execution replaces the former main step loop and runs until
completion, a genuine blocker, required input or owner stop. no arbitrary elapsed
cutoff or cumulative usage quota. operation and transport deadlines remain.
pending approval returns a durable receipt while independent reasoning continues;
later action-resolution input resumes the original request without another effect.
callback reply/interrupt ordering belongs in this slice.

o5 already owns canonical request continuation, operational fencing and fresh-thread
reasoning recovery. o9 adds discretionary delegation/content and retires chat
stop interception. current owner permits replace capacity reservations; per-tool
byte/deadline/effect-attempt bounds remain.

frozen worker-v7/native composition is qualified, including independent reasoning
while approval waits, prose progress, steering, stop and recovery. installed
production cutover, physical google/discord integration and explicit owner
resumption remain operational work; this plan resumes no stopped service.

### o6: one main for every event

the [o6 implementation contract](one-main-events.md), adopted by adr 0071, owns
common input, ordinary conversational consent, lifecycle and stopped cutover.
source implementation and isolated integration/live qualification are complete;
the contract records exact evidence. installed worker proof remains slice 3.
the old scheduler is removed; slice 2 must supply scheduled todos before the
selected product resumes. this intermediate branch is not the memory rollout release.

owner messages, action results and scheduled wakes receive the same main tools
and approval rules. background origin alone is not read-only and need not invent
fresh owner input or obtain a new standing instruction. jarvis may initiate
ordinary work and schedules, or do nothing. consequential effects still await
owner consent interpreted in conversation; clear prior consent need not be asked
again. source identity stays honest; an external fact is not owner consent.

replace current-owner-only write grounding, the read-only wake plan and affected
action lineage together in the authority adr. preserve immutable arguments,
classification, reconciliation and stop. define the common entry path for worker
results, email and internal suggestions; migrate supported sources now. new
source adapters/cursors belong to later source slices, not a second event engine.

main chooses useful progress, blocker questions and results in ordinary prose;
routine events may be silent. no notice-policy field or separate notification
feature. verify that requested reminders and useful outcomes actually reach the owner.
compatible input steers the live native turn; incompatible input queues durably;
conversational stop uses main's judgment as specified by o9. equal authority does
not itself implement email ingress.

exit: equivalent owner/wake/action events get equal capabilities; automatic writes
need no fabricated owner text; consequential writes retain approval; incoming text
cannot change authority; unrelated input remains serviceable during a long run.

### o7: one work table and four attention states

the accepted [work-record contract](work-records.md) owns schema, CRUD tools,
optional scheduling, content and focused acceptance. owner decisions: mutable current rows,
physical deletion, agent-managed bookkeeping. one table covers todos, projects,
commitments and things to track; jarvis manages records automatically.

| active state | meaning |
| --- | --- |
| doing now | actually being worked on; useful context/estimate when known |
| blocked | named unblocker and specific condition |
| next up | at most three priorities; invest definition/design here, without inventing work to fill empty slots |
| backlog | lightweight capture; do not pre-plan everything |

the same state field adds done/cancelled outside the active view. title/content,
optional due date, next wake/repeat and ordinary identity/timestamps suffice.
due date is a deadline; a wake starts a turn. owners, blockers, estimates and
refs stay prose. no history, tombstones or separate lifecycle.

reuse an item for the same work; no row for each specialist. changing/deleting
records does not stop workers or cancel pending effects. completing/cancelling/
deleting the todo disables its future wakes; already-published inputs remain.
attention states inform agent judgment. daily review is an ordinary repeating
todo. [work-state record](issues/work-state-semantics.md) tracks implementation
evidence; later dreamer work context is outside this cut.

exit: automatic CRUD persists across restart; active views obey the four states
and three-next-up cap; deletion physically removes the row; old callbacks cannot
recreate it. a due wake publishes context once across restart and never implies
task completion; missed recurrence coalesces. no workflow controller is added.

### o8: richer start and asynchronous wait

[contract](worker-launch-observation.md) consolidates current
[adr 0069](decisions/0069-terminal-only-workers.md): optional launch input,
terminal targets with immutable capture, bounded terminal inspection/control and
durable nonblocking wait/cancel. v10 source and enrolled-label proof are complete; earlier
[native qualification](native-agent-integration.md#qualification) describes its
recorded predecessor only. o6 owns broader event authority; o7 records and o9
discretionary follow-through remain separate.

remaining: qualify installed observation and actual delivery. the
[live service-state boundary](universal-memory.md#native-memory-installed-qualification)
and matching artifacts now pass under the jarvis service uid. the old
private-client/file-pause installer design is retired. [cli cutover](issues/skid-terminal-flags.md)
and [wait acceptance](issues/agent-wait.md) own remaining evidence. no worker
protocol redesign or new table.

exit: coordinated installed launch/control; register, serve another owner message,
receive one deduplicated later observation, repeat across restart. preserve
partial/uncertain effects, original receipts, deadlines, target changes,
unavailable/truncated output and cancellation facts.

### o9: continuation and coordination

[contract](delegated-follow-through.md) owns the 2026-10-06 owner correction:
every admitted event reaches the same agent with the same capabilities. jarvis
chooses work, delegation, observation, integration and useful follow-ups.
todos inform judgment, not permissions; stop/interruption are interpreted intent
and ordinary tool actions. no work controller, links, eligibility or stop guarantee.

o5/o6/o8 provide the machinery; o7 supplies useful bookkeeping. implementation is
main content/composition plus removal of exact chat-stop interception. keep
deployment controls and ordinary conversational consent. exit: useful delegated results
integrate across events/restart, ordinary stop reaches main, and claims match
original receipts/evidence. no new library or worker protocol.

## memory delivery

one standalone memory library, hosted in jarvis, owns archive, tree, persisted
views, compression and search/navigation over the shared admitted corpus. jarvis
supplies capture/admission, inference/embedding execution, scheduling and mcp/http.
jarvis starts fresh top-level turns from the view and exact current requests/
receipts; codex/claude/nexus keep their native chats and choose memory reads.
no recaller, selective extractor or external client context replacement.

bounded source parts and notes are ordinary leaves in one arrival-ordered binary
tree, retaining source event identity and dates. long text needs no private leaf
reduction. tool-result archive text is capped at 30,000 characters, head/tail with
explicit omission; canonical execution receipts remain exact. worker histories
share the tree and linked report occurrences remain distinct. supplied context
stays reference-only. views use corrected merge priority and persisted batched
shrink; waiting targets a fixed admitted cutoff. shared search remains available.
email capture uses actual tool observations, without wholesale inbox ingestion.
retain exposed attachment text and references; durable files/image access remain
in the attachment feature. shared tools/basic inspection ship first; a dedicated
memory browser/export interface is deferred.

optional notes remain an accepted addition. associative dreaming is required in
the first memory delivery as a jarvis function over the library. new archive
material and explicit notes seed it; it appends attributed synthesis notes with
supporting references into the shared tree. prior dreams can be retrieved but
create no new seeds. nightly idle runs start from a bounded tree view of eligible
new material since successful progress; missed days and late capture stay pending.
saving is quiet under the accepted core; ordinary turns may surface findings.
selected-finding wakes are deferred outside the adr 0071 cut; the
[event contract](event-sources-and-recurring-work.md) does not change m3.
each bounded run also receives a small random sample of older original events/
explicit notes for optional exploration; shared search ranking is unchanged.
the closed output/progress contract is complete. implementation
proceeds in dependency order, but a core-only release does not complete this
delivery. use the [contract](universal-memory.md), not duplicated schema/api prose here.
ordinary algorithm defaults and resource tuning need coherent implementation
contracts, not a separate owner decision for every parameter.

the accepted [completion contract](memory-delivery.md), adopted by
[adr 0070](decisions/0070-nexus-capture-and-memory-delivery.md), adds future-only
nexus capture and current functional proof. it owns the exact schema/api/content
delta; the units below describe the existing core, not new implementation work.

| unit | implementation boundary / done when |
| --- | --- |
| m1 | provider-runtime `agent_runtime/archive.py` and codecs: complete listing/heads, read-only complete events, stable capture-relevant identity/digest, reference-only context suppression after digest binding, optional exact native inherited-origin proof, internal marking and memory-tool echo suppression; do not filter inherited prefixes; validate consumed fields while tolerating unrelated metadata; prove installed-provider mappings |
| m2 | library archive/schema plus jarvis capture/collector/api: atomic activation and event/checkpoint commits, direct archived-origin proof, independent checkpoint digest/all-copy progress, stateless collectors and status; preserve admission and source identity across the package boundary |
| m3 | library tree/compactor/views: ordinary source-part/note leaves, aligned binary/free nodes, corrected priority and persisted batched views, bounded contextual compression, fixed-cutoff readiness and repair. jarvis supplies inference/scheduling and fresh-turn integration. first-delivery dreaming atomically appends attributed synthesis notes/references/positions with consumed-seed progress; one physical cursor, no self-seeding, waking output or background paid-call replay journal |
| m4 | library navigation/search/open/note append plus jarvis adapters: one keyword/vector rank-fusion pipeline and shared clients/pools; frozen view pages, zoom/date and paged originals, main save recovery, private mcp and admission; select/qualify server pins |
| m5 | messages/checkpoints/service/migration + dev-server: drain old memory work, preserve existing rows, cut old remembered_at/recaller paths, install private endpoint/collectors/profile config and activate admitted lanes online; no historical import or dual reader |

m1–m5 source boundaries and isolated checks are complete for the 2026-10-09
baseline, including first-delivery dreaming and nexus's owner-chat consumer. the
[integration evidence](universal-memory.md#12-integration-evidence) owns exact
pins and qualification; the [repair record](universal-memory.md#memory-repair-source-candidate)
owns the later repairs. the completion delta and isolated functional proof are complete. actual fleet
install/admission, private client/capture credentials and production cutover
remain operational handoffs.

m2–m4 follow the completed product and engineering contracts. use one serial
compactor and existing postgres/process; no separate daemon or durable job ledger.
live capture requires m1 proof. revise one shared policy/primitive at its owner, not copies in each unit.
retain admitted parent/child messages and reports under the common capture policy:
long text becomes source-linked parts; tool results use the accepted head/tail cap.
reference-only context and proved inherited-copy omission remain explicit policies.
keep source/identity suppression before capture
and one undivided corpus with independent admission/connection permissions.

m5 uses one local pre-migration dump/runtime copy and the existing stopped cutover.
its exact restore limits and owner-fenced drain are in the memory contract.
no backup platform, native-memory disablement or automatic history import. full
acceptance includes all declared hosts/profiles; disabled/unqualified lanes are
reported, not passed off as universal coverage.

### memory completion delivery

[completion contract](memory-delivery.md) owns the bounded nexus schema/transport,
content, files and acceptance. [repair contract](memory-repairs.md) retains the
presentation/codec/client guarantees. production installation/activation remain
separate. preserve owner changes and current consumer dependency compositions.

1. adopt bounded handoffs in the owning repositories. designers supply schema
   examples; independent reviewers challenge admission, content and failure
   boundaries. freeze shared source values before adapters diverge.
2. write temporary red end-to-end/live cases for missing behavior; preserve
   already-green core cases. use the completion contract's non-overlapping
   library, jarvis-capture, jarvis-cognition, nexus, fleet and integration owners.
   cognition repair can proceed while capture owners implement the shared seam.
3. compose one qualified memory pin into current consumers. the integration lead
   alone owns shared locks/manifests/composition; do not downgrade nexus to the
   october stack. propagate exact role/dependency fingerprints and remove replaced
   paths. prove green, independently review, refactor and recheck affected behavior.
4. prove every current api/mcp operation and actual jarvis/native/nexus journeys,
   including the durable export failure matrix. complete static/build/audit gates.
   independently review cleanup, then delete only new temporary probes/helpers.
   record exact artifacts, commands, results and gaps in existing evidence/issues.
5. prepare the exact fleet/client/image handoff. adr 0072 authorizes the current
   jarvis/native rollout; nexus waits for its next release. each selected installed host/client
   must pass its live smoke before claiming universal delivery. broader
   [usefulness/load evaluation](issues/memory-usefulness-evaluation.md) is a later pr.

no production v1 capture exists; use clean task-owned v2 qualification state.
discovering real old capture blocks cutover rather than authorizing reset/backfill.
the contract states encoding cost, uncertain-save and deleted-test tradeoffs.

### memory installed rollout

owner-authorized execution, 2026-11-14; online qualification complete 2026-11-15
within the named profile deferrals. scope: repair the dependency audit, integrate
qualified source and install/verify jarvis plus macbook/devbox native memory.
nexus code is preserved but its images, migration, credentials, publication and
activation wait for the next nexus release. [arch is offline and explicitly deferred](issues/arch-memory-activation.md).
all configured personal/work/work2 profiles may share with jarvis and one another;
the owner confirms control of their content. capture starts from new activation
boundaries, never history import. the existing separate events task owns the subsequent migration;
its intermediate source is not a deployable release and stays out of this rollout.
the owner now authorizes immediate macbook daemon refresh and
[per-conversation baselines](decisions/0073-per-conversation-memory-baselines.md):
healthy/new histories proceed while unreadable or unstable histories stay pending.
this supersedes the earlier whole-profile capture deferrals. actual model checks for
[devbox claude-personal](issues/devbox-claude-personal-model-check.md) and
[macbook claude-personal](issues/macbook-claude-personal-model-check.md) remain
deferred until provider login. [macbook claude-work2's model check](issues/macbook-claude-work2-model-check.md)
waits for its provider quota reset. those profiles are installed; preserve every
established cut. [devbox's missing native sources](issues/devbox-work2-native-source.md)
remain unresolved. their conversations will establish cuts only after successful
native recovery; no pre-cut activity is imported or identity omitted.

| step / owner | action and completion evidence |
| --- | --- |
| 1 / integration lead | source composed with current main and its security fixes; memory adr consolidated as 0070, original worktrees preserved. archive-only provider maintenance, kernel composition and selected target are published with no cognition/model upgrade; source integration is recorded in [jarvis pr 61](https://github.com/NielsdaWheelz/jarvis/pull/61) and [dev-server pr 215](https://github.com/NielsdaWheelz/dev-server/pull/215) |
| 2 / dependency writer | complete: targeted registry repairs, four actual consumer probes and full frozen `scripts/verify` pass with zero reported index findings; no suppression |
| 3 / native configuration writer | installed: the distinct claude-work2 profile uses the shared contract and existing renderer; eighteen native lanes plus jarvis. one private sharing declaration, scoped credentials and per-host bundles enable macbook/devbox capture+connect and jarvis capture only; arch disabled, nexus null |
| 4 / deployment writer | production transition passes: schema `0008`, runtime schema-read grant, validated retired-worker archival handling and exact predecessor empty drain. original columns remain unchanged after owner resumption; unfinished/unknown authority still rejects |
| 5 / service integration | installed: read-only id-mapped live state and actual cli reads under jarvis's identity reach both online gateways; source atomic-publication/write-denial proof remains applicable. same-release stock `0.160.0` host, public mapping bind and restricted-thread/service containment pass |
| 6 / integration lead | installed target with the existing release lock; temporary bridge pruned. canonical pause imported before owner discord resume. actual main reads/save, archive projection and quiet memory pass. repaired unpaused restart and the final six-table original-state comparison pass; one selected release remains |
| 7 / fleet writer + integration lead | complete within named deferrals: existing installers/private routing, all twelve sdk connections, nine model journeys, five quiet daemon adoptions and all ten eligible capture cuts. all eleven selected originals, all six tools collectively, grant denial, exact replay and outage/restart recovery pass; claude retention is installed on all six online homes |
| 8 / independent reviewer | complete: source and installed boundaries independently reviewed; temporary probes/fixtures, accepted transition snapshots and the obsolete copied worker-client credential removed after preserved-data proof. existing regression groups and operational credentials remain. arch/nexus and the five profile exceptions remain explicitly deferred |

the recorded starting snapshot is stopped/paused on `0004`; three
retired terminal-uncertain worker results already have processed resolution
messages, all paid reads/model decisions are terminal, and eleven unremembered owner rows are ineligible control/stop settlements: the
exact migration sweep predicate finds zero pending groups. the initial deployment
lacked cognition-host and memory configuration. the immutable bridge
`d9968b6b09699cf9c12d05a7b4c51b4443198192` was never resumed and is now pruned.
the first target migrated to `0008` but misclassified four finalized worker
receipts. the corrected immutable release
`a3afcdc353029a8ea82425791cdc68fd42c5f759` passed initial activation and owner resume:
activation reports three compatible archived uncertain rows, no incompatible
authority and no in-flight work. all six original table projections remained
byte-identical after migration, excluding only the deliberately retired
`message.remembered_at` column.

all twelve native profiles and both collectors are installed at that revision.
the selected central release is now `33674139c82ca5d2d7d0988de0b8ed771f1d4fd4`:
the actual unpaused restart exposed a discord-readiness race and the canonical-pause
replacement deadlock. the repaired release requires initialized canonical control
and preserves it; it retains all native/ownership/action checks. actual gateway
catch-up, authenticated https and same-release containment pass with zero restarts.
four startup-composition and nineteen real-postgres activation checks passed, were
independently reviewed, and their temporary probes/fixtures were deleted. the
collectors retain the exact qualified artifact through unchanged public contracts.
the separate stock `0.160.0` host was restarted after profile publication. actual
restricted-thread qualification sees the installed memory server disabled, with
zero tools and zero model turns. service secret/process restrictions and actual
skid reads pass on macbook/devbox; arch remains unavailable and deferred.

private https now uses the existing tailnet listener on `8443`: memory owns only
`/v1/memory` and `/v1/mcp`; skid's root and other handlers are unchanged. the failed
`443` memory handler is removed. actual authenticated requests from both hosts
return `200`, and all twelve installed sdk clients initialize and list the exact
six tools. one final installer convergence records the selected release and
active configuration digests without replacing unchanged profile files.
all ten eligible capture cuts are committed; nine native model journeys pass
save/search/open. three model-waived sdk journeys pass save/exact-open, with search
also proved on two. five quiet codex daemons now load
the six-tool catalog; macbook work2's daemon was subsequently refreshed as recorded
below. both collectors
have restarted once. the final comparison preserves all ten cuts and 4,783 existing
source identities/cuts, with no checkpoint regression, duplicates or parks. all
eleven required native conversations are captured and reopened through installed
mcp; both pre-cut prefixes stay excluded and all 39 memory-tool archive records
remain reference-only. the owner
sent discord resume; the synthetic main journey completes all six memory tools
with durable receipts and delivered output. automatic quiet dreaming appends one
attributed synthesis without a wake; serial compaction and original-state
preservation pass. [installed receipts](universal-memory.md#native-memory-installed-qualification)
record those results and the unchanged original-table projections after recovery.
[source evidence](universal-memory.md#native-memory-rollout-source-qualification)
does not waive those transition requirements.

costs: retained shared copies are available across personal/work profiles;
claude's existing 36,500-day retention consumes disk. id-mapping relies on the
qualified linux kernel/filesystem/mount implementation but avoids privilege or
permission changes to the source account. a temporary migration predecessor and
local transition snapshots are needed for this existing deployment; this adds no ongoing
backup service. dependency security fixes tighten malformed-input handling.
new tests are temporary by owner choice; existing approved regressions remain.

acceptance is observed installed behavior on macbook/devbox, not merely clean
builds. record the exact selected release, lock, migration head, host/catalogue,
active lane boundaries and loaded client results without credentials or private
bodies. an unavailable lane, unresolved original effect or failed containment
check stays visibly blocked; never reset history or broaden authority to pass.
full load/usefulness evaluation, historical import, backup/restore, nexus release,
arch activation and unrelated v2 features remain outside this rollout.

#### per-conversation capture amendment

owner-authorized follow-up, 2026-11-15. the macbook codex-work2 daemon has now
restarted once through its normal profile bootstrap. stock 0.169.0, remote-control
settings and profile/configuration bytes and inodes are unchanged. all six memory
tools load; an actual native `memory_open` reopens the synthetic verification note.
the normal collector is restored. daemon adoption is complete; capture proof
below remains separate.

| owner | remaining delivery and proof |
| --- | --- |
| provider-runtime | native-archive.v3: complete identity inventory with per-entry head errors; one stable `archive_head`; ordinary native reads/event identity unchanged; upstream merge plus immutable stock-0.160-compatible artifact |
| universal-memory | one nullable baseline_error, atomic initial inventory and one-time resolution, pending ingest denial, explicit status; preserve every established cut/checkpoint/original |
| jarvis | closed baseline sync request, pending retries independent of native hints; migration 0008a after installed 0008, with unactivated 0009 following it; keep six tools unchanged |
| integration | merge source into main; build a memory-only patch of installed 3367413, preserving v1 and stock 0.160; qualify fresh migration and populated 0008→0008a separately; replace service and both collectors together |
| independent review | review each contract and its temporary HTTP/native/postgres proof; verify installed healthy/new capture, pending counts, exact reopening and restart preservation; remove new probes after success |

the installed database is still 0008 and current main contains incomplete v2.
the patch therefore excludes 0009 and all v2 behavior; immutable release tags
retain compatible artifacts without standing maintenance branches. an existing
history's missing head is never an empty cut. permanently unreadable histories
can remain pending indefinitely; their earlier activity will remain absent even
if they recover later. this is the owner's accepted coverage trade-off.

### memory and native-main integration

these tracks share invocation identity, source publication, library pins and
composition, not a new agent layer. coordinate shared-file changes and serialize
their release cutovers; do not maintain two implementations to support arbitrary
merge order.

- o4/o5 preserve a host-owned accepted-invocation position BEFORE every callback
  dispatch and a recorded result BEFORE replying. this supplies internal note
  idempotency and search recovery. raw native call ids are not durable effect ids.
- canonical messages/callback receipts commit before archive projection. immutable
  message/attempt eligibility bits and stable message/call/reply ids recover missing
  projections without another journal or source-time cutoff. one ongoing jarvis
  conversation replaces settlement groups; memory-tool prose stays reference-only.
  fresh runner calls use new leases, retaining entered-effect dispatchers. one
  publication adapter consumes current native evidence, never the retired step loop.
- memory retains current write authority, including main's full-plan canonical-note
  exception: action-resolution turns can save without owner grounding. scheduled
  turns remain read-only. o6 extends capabilities to scheduled/new origins outside
  that full plan; amend affected grants there, never silently in m4.
- native main retains original attempt, invocation and action/read evidence.
  compactor/dreamer inference and dreamer read receipts are disposable; the
  completed nodes, synthesis notes and progress commit in the memory store.
- memory adds six tables to the native nine: fifteen total. the contract defines
  leaf mapping, completed nodes and singleton progress beside the three archive
  tables. o7 separately contributes the one work table. sequence actual migrations and revalidate owner permits and
  definition revisions against the deployed predecessor, preserving canonical rows.

## subsequent product slices

these have focused contracts. notes, attachments and event sources are adopted
v2 work; search, dreamer context and budget remain later scoped amendments.
none is a prerequisite for delegation or initial universal memory.

### private notes repository and rolodex

the [notes contract](private-notes-and-rolodex.md) settles one persistent ordinary
private github checkout: native read/create/edit/move/delete and search; agent-chosen
commit/pull/push. advisory folders hold briefs, procedures, research, drafts and
one prose document per person. no notes service, schema or sync worker.

main becomes a trusted native domain; conversational connector consent governs
connector calls only. this replaces the earlier confined-access direction.
kernel/provider mixed native-callback support and borrowed cwd lifecycle are
bounded upstream work, not already supplied by the current pins. adr 0071 adopts
the authority amendment; qualify the same dedicated host before activation.
ordinary git history/relative links have no synchronization or stable-link
guarantee. memories/work/documents link without mirroring current task state.

### complete and continuable searches

the [search contract](complete-and-continuable-searches.md) settles unrestricted
total traversal through bounded pages/chunks. main may inspect all accessible
historical mail, including full textual bodies; binary attachment content stays
with attachments. remove discarded cursors, unrecoverable clipping and application
candidate/item/page horizons, including memory's top-50-per-mode search ceiling.

main composes pages, calendars and progress through ordinary tools/context.
native notes remain ordinary commands. provider-ranked web/places limits, live
source changes, indexing gaps and unavailable content remain explicit; no
snapshot/completeness fiction or scan controller. jarvis owns connector/fresh-read
composition; llm-tools owns web, memory library owns ranking, skid consumes existing
provider history. adopt the affected contracts and hard-cut their old schemas.

### event sources, suggestions and recurring work

[contract](event-sources-and-recurring-work.md) owns the accepted v2 target:
new incoming mail including archived mail; all readable calendar changes and
approximate upcoming attention; one-minute polling; simple recurring schedules
with coalesced missed runs; and an ordinary daily 09:00 review todo.
one new table holds source cursors; the work table owns all one-time/repeated
wakes. reuse the timer, worker waits, main and receipt paths.

trusted internal producers can use the same append with actual source identity.
selected dream wakes remain deferred; memory's quiet completion is unchanged.
no new suggestion generator, controller or per-work execution gate. main chooses
action, notification or nothing.
disable/cancel stops future publication; already published work remains ordinary
main context. implement source adapters independently of the later work projection.

### dreamer work context

outside this v2 cut, the [contract](dreamer-work-context.md) proposes one shared work query and a dated,
bounded prompt section after m3 and o7. doing now, blocked and next up guide
attention; omit backlog and disclose record/content omissions. freeze context
for one invocation; later attempts read current state. preserve personal,
scientific and creative dreaming and m3's settled evidence/output contract.
main rechecks current work before dependent action. no new tool, table,
scheduler or work-triggered dream. daily review belongs to ordinary scheduled
todos; selected-note delivery is deferred. query failure uses the ordinary dream
failure policy. neither amendment is part of the separate memory pr.

### attachments and original storage

the [contract](attachments-and-durable-originals.md) settles automatic owner
discord capture, gmail on fetch, indefinite private r2 originals and file deletion
with conversational consent. one table holds source identity/bytes/hash; ordinary native tools
and installed utilities read images, pdf, text, docx and csv. no reader ui,
extraction pipeline or multimodal wire redesign. notes' trusted-native cutover
and dev-server storage/cache/utility setup remain prerequisites.

expiring links, internal extraction text and derivatives are not durable
originals. notes/memory keep references/published observations; binaries stay
outside git. deletion removes our original/cache, not source copies or prior
memory. budget accounting and outgoing file sharing remain separate.

### budget integration

the [contract](budget-integration.md) follows the owner-requested independent
audit of freshly pulled budget-app `7b7a9c2`. its ledger, evidence inbox,
reports, revision checks and durable command api already exist. jarvis adds typed
tools and uses those owners; no competing financial table, arithmetic or importer.

the owner selected full automatic bookkeeping, including plans, manual entries,
corrections/voids and evidence repairs, plus attachment-compatible formats and
100-mib originals. budget broadens its existing write credential, exposes its
shared planner calculation and replaces bytea/base64 with independent private r2
originals. payments, bank access and currency conversion stay outside this slice.
budget originals survive jarvis attachment deletion. exact command replay and
current financial truth remain distinct; preserve receipts and revisions.

### deferred from universal memory

separately specify historical imports (pre-activation lanes, legacy codex homes,
old canonical jarvis messages and old-note lineage), including deduplication,
provenance, extraction cost and order; nexus historical import; backup/restore;
broader [usefulness/load evaluation](issues/memory-usefulness-evaluation.md); and disabling or
reconciling native automatic memories. retained native history preserves an import
opportunity, not proof of capture. preserve existing messages/notes in the meantime.

forgetting/exclusion is outside the prototype and is not promised v2 work.
automatic external context injection was rejected, not deferred; future push
would require a new authority design. learned reranking may be reconsidered only
from measured retrieval failures; keep one current ranking path.

browser control, new credential handling/brokering, interactive deliverables,
credential-entry forms and television/artifact hosting are explicitly deferred
from v2. small prose/file outputs use the ordinary repo and existing access.
progress, blockers and completed results are not deferred features: they are
ordinary main behavior, with no separate subsystem.

other earlier ideas remain uncommitted/outside this delivery: extra discord
channels, api-backed cognition, a separate application program-execution api, selected
onepassword access, jarvis-to-nexus product integration, android and generic
computer use. nexus's shared provider/kernel contract work remains in o3–o4.
revisit other ideas only for an observed need with their own contract. notes do
not imply a google-drive integration.

## decisions and verification

remaining decisions have owners; do not reopen settled broad autonomy, automatic
notes, cloudflare originals, nonblocking waits, freeform delegation or latest owner
intent merely because their implementation is incomplete.

| feature or cutover | remaining decision / evidence owner |
| --- | --- |
| native/worker activation | existing qualified contracts; exact production artifact/configuration, stopped cutover, physical delivery and owner resumption |
| o6 | [contract](one-main-events.md) source and isolated functional proof complete; selected-slice cutover and installed activation remain |
| o7 | [work-record contract](work-records.md) adopted by 0071; todo/schedule implementation and focused proof remain |
| o8 | [contract](worker-launch-observation.md), adr 0069 and 0072 own terminal-only v10; source/state-boundary qualified; installed effect/observation delivery remains |
| o9 | [contract](delegated-follow-through.md) content/composition and conversational stop source complete; installed skid proof remains slice 3 |
| new event sources | [contract](event-sources-and-recurring-work.md) adopted by 0071; cursor/adapters and same-main proof remain; recurrence belongs to o7, dream wakes deferred |
| m1–m5 | source and online jarvis/native rollout complete with the named [profile deferrals](#memory-installed-rollout); nexus waits for its next release |
| notes | [contract](private-notes-and-rolodex.md) adopted by 0071; kernel/provider handoffs, persistent checkout and live native/git proof remain |
| search | owner choices settled in [contract](complete-and-continuable-searches.md); full message text, uncapped ranked memory, library/skid handoffs and cross-turn page/chunk proof remain |
| attachments | [contract](attachments-and-durable-originals.md) adopted by 0071; table/ingress/tools, private storage/native setup and live file journeys remain |
| budget | owner choices settled in [contract](budget-integration.md); budget authority/storage/calculation handoff, jarvis tool/recovery adoption and three focused proof journeys remain |

[adr 0046](decisions/0046-reset-testing.md) remains in force. run `scripts/verify`
for static/build checks; do not claim behavioral acceptance from it. native and
worker work completed their explicitly authorized temporary acceptance under
adrs 0064/0065. memory's scoped exception permits its small capture/retry and
memory-completion groups plus focused synthetic live boundary evidence. future
features specify their own proportionate verification scope with the owning
contract; the standing testing redesign remains separate. other repos follow
their own rules.
no old suite, replacement framework or recurring fleet qualification is added here.

integrated acceptance journeys, when their owning verification is authorized:

- one client's new conversation/direct note becomes searchable from another host;
  capture/compression/dreaming interruptions do not lose or duplicate committed work.
- jarvis delegates substantial research through skid, stays responsive, receives
  one asynchronous observation after restart and distinguishes evidence from success.
- a native connection is lost: fence stale callbacks, reconcile recorded connector effects and recover
  requests with original receipts; fresh reasoning sees latest owner intent,
  including semantic stop, without repeating unknown effects.
- an email or trusted internal event may create useful work without forged owner
  input; irrelevant input creates no make-work; consequential connector communication still
  uses conversational consent.
- main edits useful project/person documents through native tools and chooses
  ordinary git operations; checkout/dirty changes survive lease loss and native
  effects are inspected rather than blindly replayed.
- main traverses beyond old item/candidate horizons and reads the last text chunk
  across turns; source changes/provider limits are explicit and original paid-read
  uncertainty is preserved.
- project review reflects real active work/estimates, named blockers with daily
  review, at most three next priorities and completed work outside the active view.
- a receipt survives as an addressable original and becomes one source-linked
  expense through the budget app, including repeated delivery and correction.

implement adopted slices through exact pins and removal of old paths; adopt
later amendments separately. inspect shared-library impact. qualify transport, then effect durability,
then authority, then restart/stop behavior. preserve existing user work. stop
admission and reconcile outstanding effects before incompatible pins/migrations;
code rollback never reverses external effects or new canonical data. use the
operations runbook and the memory contract's exact cutover rules.

## reconciliation evidence

2026-10-04: clean jarvis/kernel/tools/skid/dev-server main checkouts were pulled
with `--ff-only` and were current. provider-runtime's clean maintenance branch
was preserved; fetched `origin/main` supplied its current contract/source evidence.
jarvis is `f3b4dc3`, skid `ab9e0ac`, kernel `465470e`, tools `593de5d`, provider
main `09c5203` and dev-server `3080886`. qualified runtime pins remain those in
jarvis's lockfile; naming a newer merge commit does not authorize an upgrade.

the canonical skid checkout is `skidbladnir`; the old `skid-v1` path and v0.10.7
observations are historical. codapt's earlier six-hour behavior supplied design
evidence, not the current native contract. current acceptance/artifact identities
belong in the owning handoffs and issue records. this reconciliation changes
documentation only and claims no provider, database, fleet or service operation.

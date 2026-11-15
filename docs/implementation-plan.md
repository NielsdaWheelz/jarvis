# jarvis: roadmap and implementation plan

updated 2026-11-14; memory completion/nexus capture, notes, searches, events,
dreamer work context, attachments and budget have focused contracts.
this is the ONE active feature roadmap and delivery plan. native cognition and
worker control are implemented foundations; the remaining product direction and
operational cutovers are distinguished below. a roadmap entry authorizes no
runtime change, release, deployment or resumption.

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
- durable effects, canonical commits, truthful outcomes and deployment pause/shutdown remain
  host responsibilities. new background memory computation is disposable.
- hard-cut replaced paths, preserve canonical data, and state costs in the owning
  contract. distinguish source merged, dependency pinned, fleet installed, live
  behavior verified and owner-resumed service.

## current position

the native cutover has nine application tables: the original six plus three
native journal tables. accepted universal memory adds six; the later work
slice adds one, events add two and attachments add one. derive migration dependencies from the actual predecessor;
do not hard-code a stale total into independently developed slices.

source refresh 2026-10-13: this checkout incorporates merged memory repair
source and exact dependency pins, preserving pending product contracts in local
commits. the 2026-11-14 completion source and isolated functional proof are now
complete; [current evidence](universal-memory.md#memory-completion-source-qualification)
records exact pins and passing static/build checks. full `scripts/verify` remains
red only at the pre-existing dependency audit. installation and activation remain
separate.

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
implements immutable captured targets and asynchronous wait/cancel. the earlier
correctness defects and adr-number collisions are resolved. these are completed
source handoffs, not new feature-spec assignments.

production activation remains separate. the last recorded jarvis state is stopped
and paused; this reconciliation inspected no running service. skid's current
published/dev-server pin is v0.13.0, from before the orchestration merge. publishing
and installing the matching generation is still o2. a current source checkout is
not an installed fleet receipt.

## operational cutovers and upkeep

| item | owner / remaining result |
| --- | --- |
| skid release and fleet cutover (o2) | skid publishes the immutable orchestration generation; dev-server pins/installs matching gateways and cli; jarvis installs its matching private client/configuration; [cutover issue](issues/skid-terminal-flags.md) |
| native jarvis activation | jarvis deployment owner installs the same-release contained host/application, performs [stopped state conversion](issues/admission-journal-cutover.md), verifies physical integration and records explicit owner resumption; [activation issue](issues/codex-private-process.md), [native cutover](operations.md#native-cutover) |
| installed worker observation | jarvis repeats the relevant receipt/restart/notification journey against the coordinated installed fleet; [wait deployment issue](issues/agent-wait.md) |
| claude retention | dev-server manages long retention on every configured home before memory capture activation; [issue](issues/claude-transcript-retention.md) |
| current memory artifacts | anonymous current arm64 targets pass; build/qualify the deployment architecture and private installed access; [image handoff](issues/nexus-memory-image-qualification.md) |
| standing verification design | separately scope the [testing redesign](issues/testing-redesign.md); completed native/worker exceptions do not create a standing suite |

these are independent release, repair or policy tasks, not another prerequisite
mega-pr. preserve [connector cutover](issues/connector-keyring-cutover.md),
[old qualification-resource disposition](issues/qualification-residue.md) and
nexus's [historical job disposition](issues/nexus-generation-dispatch-contract.md)
with their owners. none is resolved merely by merging a new runtime.

## delivery map

the roadmap is organized by useful product behavior. legacy o/m labels remain
cross-references for existing handoffs, not github pr numbers or a fixed pr count.
o1, o3–o5 and o8 are implemented foundations; o2 is the operational cutover above.

| feature | contract / specification work | owner and dependencies |
| --- | --- | --- |
| one main for every event (o6) | owner choices settled in [contract](one-main-events.md); spec/adr adoption and implementation due | jarvis; builds on native main; source adapters remain separate |
| useful work records (o7) | mutable todos/physical deletion settled in [contract](work-records.md); adoption/implementation due | jarvis; one bookkeeping table |
| delegated follow-through (o9) | owner settled agent judgment/semantic stop in [contract](delegated-follow-through.md); adoption/implementation due | jarvis; o6 plus installed worker control; o7 supplies optional bookkeeping |
| universal memory (m1–m5) | [completion contract](memory-delivery.md) implemented; isolated current api/mcp/main/native/nexus proof passes; installed activation and pre-existing audit findings remain open | memory library, jarvis, provider-runtime, llm-tools, dev-server and nexus-web; [memory delivery](#memory-delivery) |
| private notes and rolodex | owner choices settled in [contract](private-notes-and-rolodex.md); adoption/implementation due | jarvis plus kernel/provider native-access handoff; ordinary private checkout, agent-chosen git, prose people records |
| complete and continuable searches | owner choices settled in [contract](complete-and-continuable-searches.md); adoption/implementation due, including uncapped ranked memory | jarvis, memory library, llm-tools and skid/provider history; bounded pages/chunks without total application ceilings |
| event sources, suggestions and recurring work | owner choices settled in [contract](event-sources-and-recurring-work.md); adoption/implementation due, including selected dream wakes | jarvis; o6, complete-search references, o7 for daily review and memory for dreaming |
| dreamer work context | focused [contract](dreamer-work-context.md) written; adoption/implementation due; suggestion delivery belongs to the event contract | jarvis; m3 and o7; one work query and run-local context, not summary evidence |
| attachments and durable originals | owner choices settled in [contract](attachments-and-durable-originals.md); adoption/implementation due | jarvis plus dev-server; one table/private bucket, ordinary native tools; notes native access prerequisite |
| budget integration | owner choices settled in [contract](budget-integration.md); full bookkeeping authority and larger originals require budget-side adoption/implementation | jarvis plus budget-app; existing ledger/api, private object storage and attachment/native-reading prerequisites for the upload journey |

preserve orchestration priority: adopt and implement the settled o6/o7/o9 contracts.
prepare memory's external handoffs alongside them;
m2–m4 can develop against agreed public contracts while m1 and host work proceed.
notes, search, events, dreamer work context, attachments and budget have focused contracts;
implement them in dependency order. the work view and delegated follow-through do not wait for full
memory; native callbacks alone do not provide archive capture.

accepted direction is not an accepted schema or authority change. write missing
contracts before their implementation; do not respec completed foundations or
reconstruct memory's superseded adr chain. memory's review units converge on one
stopped schema/legacy cutover, without an old/new runtime fallback.

## external specifications and handoffs

jarvis owns product intent and consumer obligations. each external unit gets a
bounded repository handoff from its owning contract: public inputs/outputs,
identity and failure semantics, limits/costs, acceptance evidence and the exact
consumer adoption. record prepared, handed off, implemented and adopted as distinct
facts; writing this roadmap sends no assignment to another agent.

| repository owner | remaining handoff | specification source / status |
| --- | --- | --- |
| skid | publish the completed launch/control generation and its immutable artifact | existing [paired contract](https://github.com/NielsdaWheelz/skidbladnir/blob/ab9e0acf0c01e2a94d785016cd9500e20bac1787/docs/jarvis-orchestration.md); implementation done, release handoff due |
| skid, search | page worker inventory and retained native/terminal text before response fencing; consume provider-owned archive/history codecs | [search composition](complete-and-continuable-searches.md#receipts-and-external-composition); bounded consumer handoff prepared, not handed off/implemented; existing m1 provider handoff supplies history primitives |
| dev-server | pin/install that skid generation; long claude retention; memory collector units on all three hosts, private routing, client/capture credentials and generated codex/claude profile mcp configuration/instruction | memory [ownership](universal-memory.md#2-ownership-and-admission), [collector](universal-memory.md#collector-and-normalization) and [retrieval](universal-memory.md#6-retrieval) contracts adopted in its spec; source and isolated host reconciliation qualified; installed fleet handoff remains |
| llm-calling (`provider-runtime` package) | m1 archive enumeration/heads/events, capture identity, internal marking and memory-tool echo suppression | [native capture contract](universal-memory.md#3-native-capture); public archive api/codecs implemented and source/live-qualified; actual fleet admission separate |
| llm-calling (`provider-runtime` package), notes | native built-ins plus declared callbacks in one session, both declared authority postures and host qualification | [notes public contract](private-notes-and-rolodex.md#public-contracts-and-deployment); bounded handoff prepared here, not handed off or implemented |
| kernel, notes | frozen application-owned cwd/native configuration, retained checkout lifecycle, native activity alongside host callbacks | [notes public contract](private-notes-and-rolodex.md#public-contracts-and-deployment); bounded handoff prepared here, not handed off or implemented; no llm-tools change |
| jarvis deployment owner on dev-server, notes | persistent private checkout, ordinary git authentication, host permissions and hard-cut host mapping | [notes deployment contract](private-notes-and-rolodex.md#public-contracts-and-deployment); source changes stay in jarvis's existing deploy files; operator bootstrap/install remains separate |
| memory library | existing archive/tree/view/search; add explicit nexus source values and atomic export append/duplicate proof through shared insertion primitives | [core](universal-memory.md), [completion handoff](memory-delivery.md#non-overlapping-implementation-boundaries); uncapped ranked [search amendment](complete-and-continuable-searches.md#uncapped-ranked-memory) remains a separate delivery |
| kernel + llm-tools | production transient read recorder for disposable dreaming using the existing recorder/executor seam | [daily dreaming](universal-memory.md#daily-dreaming); production recorder published; coordinated kernel/tools/provider pins adopted; request-fit and strict json fixes qualified |
| llm-tools, search | portable web-search paging/provider boundaries and complete supported extracted-text chunks, retaining web safety | [search surface contract](complete-and-continuable-searches.md#exact-surface-changes); bounded handoff prepared, not handed off/implemented; no kernel redesign |
| budget-app | broaden existing write authority to all bookkeeping, reuse shared planner calculation through an api, and support independent originals up to 100 mib through private r2 | [budget api handoff](budget-integration.md#budget-api-handoff); fresh `7b7a9c2` source audit complete; bounded handoff prepared, not assigned or implemented |
| budget deployment owner and dev-server | budget private bucket/cors/storage secrets; jarvis configured budget origin/owner/read/write credentials and native cache access | [budget delivery](budget-integration.md#nonoverlapping-delivery-and-hard-cutover); provisioning and installed qualification remain separate |
| nexus-web | configured owner's librarian tools and future-only durable capture; terminal snapshot/outbox/publisher, current call identity and native internal marking; no automated-helper tool grants | [completion handoff](memory-delivery.md), [client issue](issues/nexus-memory-client.md); adr 0068 source and current-route qualification complete; installed private access remains |

[current memory qualification](universal-memory.md#memory-completion-source-qualification)
covers current source, nexus capture and isolated clients. historical records
retain their exact original scope. dev-server owns the implemented capture
declaration/publisher credential; installed fleet receipts remain separate.

downstream jarvis code consumes the published public surfaces and qualified pins;
the external agents do not own jarvis authority, work state or continuation.
the memory library owns its memory schema under the accepted deployment contract;
jarvis owns the composed migration and canonical request/effect schema.
new shared-library work is requested only for an identified missing primitive.
there is no further generic kernel/skid orchestration redesign in this roadmap.

one mcp server lives inside jarvis. dev-server configures native codex/claude
clients and installs the capture collectors; it does not implement another memory
server. nexus's application agents require their own client bindings, distinct
from developer agents working in the nexus repository. adr 0068 explicitly adds
its distinct account-owned capture source; the sixteen native/jarvis lanes remain.

## orchestration delivery

### o1–o2: fleet launch

o1 is implemented. skid start accepts machine/profile, provider-compatible raw model/effort,
cwd and optional freeform initial prompt. profile determines provider/account;
provider convenience selection must resolve a compatible profile. keep one launch
configuration declaration; explicit model/effort fields override native account
defaults and omitted fields preserve them. no extra skid profile-default layer.
jarvis chooses the machine/profile. unsupported pairs fail;
no capability tiers, hidden model substitution or shell interpolation.

skid owns readiness and initial prompt submission. preserve the created terminal
ref if submission fails or is unknown; never relaunch after ambiguous creation.
creation, submitted prompt and completed work are distinct facts. retain ordinary
start without a prompt. dev-server pins the immutable release/configuration and
verifies the intended artifact on each peer without replacing jarvis cognition.

source qualification covers literal prompts, defaults/overrides and inspectable
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

the proposed [o6 implementation contract](one-main-events.md) specifies schemas,
authority, selective notices, lifecycle, hard cutover and temporary acceptance.
it supersedes this outline's details when adopted by spec/adr; no runtime change
is implied by this document.

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
conversational stop uses main's judgment as specified by o9. equal authority does
not itself implement email ingress.

exit: equivalent owner/wake/action events get equal capabilities; automatic writes
need no fabricated owner text; consequential writes retain approval; incoming text
cannot change authority; unrelated input remains serviceable during a long run.

### o7: one work table and four attention states

the proposed [work-record contract](work-records.md) owns schema, CRUD tools,
content and temporary acceptance. owner decisions: mutable current rows,
physical deletion, agent-managed bookkeeping. one table covers todos, projects,
commitments and things to track; jarvis manages records automatically.

| active state | meaning |
| --- | --- |
| doing now | actually being worked on; useful context/estimate when known |
| blocked | named unblocker and specific condition |
| next up | at most three priorities; invest definition/design here, without inventing work to fill empty slots |
| backlog | lightweight capture; do not pre-plan everything |

the same state field adds done/cancelled outside the active view. title/content,
optional due date and ordinary identity/timestamps suffice. owners, blockers,
estimates and refs stay prose. no history, tombstones or separate lifecycle.

reuse an item for the same work; no row for each specialist. changing/deleting
records does not stop workers or cancel actions/wakes. attention states inform
agent judgment; recurrence owns daily review. later dreamer integration
uses ordinary reads. [work-state record](issues/work-state-semantics.md) tracks
spec/adr adoption and implementation evidence.

exit: automatic CRUD persists across restart; active views obey the four states
and three-next-up cap; deletion physically removes the row; old callbacks cannot
recreate it. no execution machinery is added to this todo-table slice.

### o8: richer start and asynchronous wait

[contract](worker-launch-observation.md) consolidates accepted [adr 0064](decisions/0064-simple-worker-orchestration.md):
optional launch input/options, short targets with immutable private capture,
bounded inspection/control and durable nonblocking wait/cancel. source and scoped
provider/postgres/service/cognitive checks are complete; [qualification](native-agent-integration.md#qualification)
owns evidence. o6 owns broader event authority/notices; o7 records and o9
discretionary follow-through remain separate.

remaining: publish/install paired artifacts, replace dev-server's retired pause
file guard with the qualified target release's public `check-paused`, prepare
native state before that check, then qualify installed observation and actual
delivery. [cli cutover](issues/skid-terminal-flags.md) and [wait acceptance](issues/agent-wait.md)
own blockers. no worker protocol redesign or new table.

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
deployment controls and exact connector approvals. exit: useful delegated results
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
the [event contract](event-sources-and-recurring-work.md) separately adds optional
selected-finding wakes after its spec/adr adoption; it does not silently change m3.
each bounded run also receives a small random sample of older original events/
explicit notes for optional exploration; shared search ranking is unchanged.
the closed output/progress contract is complete. implementation
proceeds in dependency order, but a core-only release does not complete this
delivery. use the [contract](universal-memory.md), not duplicated schema/api prose here.
ordinary algorithm defaults and resource tuning need coherent implementation
contracts, not a separate owner decision for every parameter.

the accepted [completion contract](memory-delivery.md), adopted by
[adr 0068](decisions/0068-nexus-capture-and-memory-delivery.md), adds future-only
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
owns the later repairs. the completion delta and isolated functional proof are
complete, with exact artifacts in the current evidence. actual fleet
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
separate. preserve owner changes and current consumer dependency compositions. steps 1–4
are complete for isolated functional proof; the full audit retains its recorded
pre-existing findings. step 5 is the remaining operational handoff.

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
5. prepare the exact fleet/client/image handoff. installation and production
   activation stay separately authorized; each selected installed host/client
   must pass its live smoke before claiming universal delivery. broader
   [usefulness/load evaluation](issues/memory-usefulness-evaluation.md) is a later pr.

no production v1 capture exists; use clean task-owned v2 qualification state.
discovering real old capture blocks cutover rather than authorizing reset/backfill.
the contract states encoding cost, uncertain-save and deleted-test tradeoffs.

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

these have focused contracts. none is a prerequisite for delegation or initial universal memory.
adopt each focused contract before implementation; do not turn every open question
into present code.

### private notes repository and rolodex

the [notes contract](private-notes-and-rolodex.md) settles one persistent ordinary
private github checkout: native read/create/edit/move/delete and search; agent-chosen
commit/pull/push. advisory folders hold briefs, procedures, research, drafts and
one prose document per person. no notes service, schema or sync worker.

main becomes a trusted native domain; connector `Approve`/`Deny` governs connector
calls only. this explicitly replaces the earlier confined-access direction.
kernel/provider mixed native-callback support and borrowed cwd lifecycle are
bounded upstream work, not already supplied by the current pins. adopt the
authority amendment and qualify the same dedicated host before activation.
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

[contract](event-sources-and-recurring-work.md) owns the settled 2026-10-09 target:
new incoming mail including archived mail; all readable calendar changes and
approximate upcoming attention; one-minute polling; simple recurring schedules
with coalesced missed runs; and a quiet daily 09:00 active-work review.
two small tables hold source cursors and recurring wakes. existing one-shot
reminders, worker waits, main, authority and receipt paths are reused.

useful dream findings may nominate one newly saved note to wake main; note append,
seed progress and the canonical input commit together. this expressly supersedes
memory's quiet-only completion after adoption. synthesis references create no new
dream seed; semantic novelty remains agent judgment. no new suggestion generator,
controller or per-work execution gate. main chooses action/notification/nothing.
disable/cancel stops future publication; already published work remains ordinary
main context. implement source adapters independently of the later work projection.

### dreamer work context

the [contract](dreamer-work-context.md) adds one shared work query and a dated,
bounded prompt section after m3 and o7. doing now, blocked and next up guide
attention; omit backlog and disclose record/content omissions. freeze context
for one invocation; later attempts read current state. preserve personal,
scientific and creative dreaming and m3's settled evidence/output contract.
main rechecks current work before dependent action. no new tool, table,
scheduler or work-triggered dream; daily review and selected-note delivery keep
their existing owners. query failure uses the ordinary dream failure policy.

### attachments and original storage

the [contract](attachments-and-durable-originals.md) settles automatic owner
discord capture, gmail on fetch, indefinite private r2 originals and exact-approved
file deletion. one table holds source identity/bytes/hash; ordinary native tools
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
| o6 | owner choices settled in [contract](one-main-events.md); authority/spec adoption and focused implementation proof remain |
| o7 | owner choices settled in [work-record contract](work-records.md); table/spec/adr adoption and focused implementation proof remain |
| o8 | [contract](worker-launch-observation.md) consolidates implemented adr 0064; source qualification complete; canonical-pause installer repair, paired installed cutover and external delivery remain |
| o9 | owner decisions settled in [contract](delegated-follow-through.md); behavior/spec adoption and chat-stop cutover due |
| new event sources | owner choices settled in [contract](event-sources-and-recurring-work.md); tables/tools/spec adoption, polling/recurrence and selected-dream proof remain |
| m1–m5 | [completion delta](memory-delivery.md) source and isolated functional proof complete; source integration, private provisioning and installed fleet/admission/cutover remain |
| notes | owner choices settled in [contract](private-notes-and-rolodex.md); authority adoption, kernel/provider handoffs, persistent checkout and live native/git proof remain |
| search | owner choices settled in [contract](complete-and-continuable-searches.md); full message text, uncapped ranked memory, library/skid handoffs and cross-turn page/chunk proof remain |
| attachments | owner choices settled in [contract](attachments-and-durable-originals.md); table/ingress/tool adoption, private storage/native setup and live file journeys remain |
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
- an email or memory-role suggestion may create useful work without forged owner
  input; irrelevant input creates no make-work; consequential connector communication still
  waits for exact approval.
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

promote slices through their own adr/spec changes, exact pins and removal of old
paths. inspect shared-library impact. qualify transport, then effect durability,
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

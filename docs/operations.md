# production operations

jarvis is one cpython 3.12 process, one postgres database, a separate contained
native host and one configured discord channel. it hosts the shared memory
endpoint on loopback; dev-server owns private tailnet routing and native client
configuration. [universal memory](universal-memory.md) owns the core contract;
[current delivery](memory-delivery.md) owns nexus capture and remaining integration
qualification. historical evidence qualifies only its named artifacts.
source implementation and isolated qualification do not authorize production
activation or fleet installation.

all owner and host requests use one full main plan with shared memory reads
and optional note saving. the isolated dreamer receives memory reads; compactor
has an empty plan. canonical receipts commit before recoverable archive projection.
archive checkpoints and memory completion are atomic; interrupted background inference
may repeat. main's durable read/effect barriers remain.

one stopped-maintenance sharing declaration owns admission, recipients, named
processors and bearer hashes. admission and connection are independent, omitted
lanes deny, and bearer rotation is explicit. native lanes activate online after
complete inventory; incomplete inventory retries without inventing a boundary.
oversized/conflicting history parks without moving its checkpoint. operator
status is cli-only. no ongoing backup or separate memory daemon is added.

nexus capture is future-only for new admitted owner-librarian runs. its durable
pending export retains the approved question/answer, saved citation/attachment
excerpts and available persisted tool receipts before source deletion can lose
them. retry delivery with the same identity/content; remove the export only after
central acknowledgement. source deletion neither deletes central originals nor
cancels pending delivery. no revision/remove sync or historical import is added.
reads, optional note saves and capture have distinct grants under the shared
private declaration. automated helpers and other viewers receive no memory tools.

## accepted v2 target and operational scope

[adr 0071](decisions/0071-simple-event-driven-v2.md) adopts the product target.
[one-main source](one-main-events.md) implements its first slice; it has not been
installed or activated. these instructions describe that source. the active
installed memory release retains older event behavior; settle obligations under its
original contracts before the cutover below.

owner and host events share the full main plan and retain source attribution.
main chooses work, notification or silence and interprets conversational consent
through `approval.respond`. deterministic tool policy, immutable action arguments,
original receipts and effect reconciliation remain. ordinary `stop` reaches main;
its final dispositions stop only named delivered requests. exact administrative
`pause` and `resume` remain host-owned.

the old scheduler and approval components are removed. intermediate source slices
need not be independently usable. retain outstanding reminders in the private
stopped inventory for slice 2; never resume this incomplete release or silently
drop those commitments. the owning contract defines migration, local decision
receipts and scoped request stopping.

optional one-time/repeated wakes belong to work records, replacing separate
schedule/recurring-wake products. due dates remain distinct. keep the existing
asynchronous skid observer and separately prove its installed event delivery;
no new callback service or repeated model polling is proposed. future native
notes/files require the persistent private checkout; inbound originals require
private r2 storage. activation must use the eventual qualified artifacts and
their cutover instructions, reconciling entered effects before incompatible
changes. this section supplies no new migration command or deployment authority.

the [implementation plan](implementation-plan.md) owns those handoffs. shared
memory delivery and quiet dreaming remain unchanged. browser/credential products,
interactive deliverables, a separate ui, selected dream wakes and work context
remain outside this cut; later search and budget contracts are not adopted here.

## Approved production target

Slice 7 deployed the exact accepted release as a host-native systemd service
on the existing Hetzner `dev-server`. The target uses a dedicated `jarvis` Unix
account, immutable releases under `/opt/jarvis/releases`, durable state under
`/var/lib/jarvis`, root-owned configuration under `/etc/jarvis`, and a
dedicated database and roles in native loopback-only PostgreSQL 16. Jarvis opens
no public listener and is not part of the rootless Docker lifecycle.

The dev-server convergence repository owns shared host prerequisites, UTC, the
service account, and base directories. This repository owns application
release/rollback, its locked dependencies, credentials,
database roles and migrations, the systemd unit, and recovery.
nexus owns its application state and pending exports; jarvis owns central corpus
admission. nexus installation remains in its release process, with the cross-system
receipts required by the [memory delivery](memory-delivery.md).

the [2026-09-08 deployment report in git history](https://github.com/NielsdaWheelz/jarvis/blob/42f1fa21c3d2f687a3f3fafc9366fea41023e0cb/docs/qualification/2026-09-08-production-deployment.md)
records that release's housekeeping, host qualification and activation, not current
readiness. [current installed evidence](universal-memory.md#native-memory-installed-qualification)
records the native/memory cutover and owner resumption; remaining physical google
checks have a separate [issue](issues/codex-private-process.md). no completed
seven-day owner acceptance is established.
The pending host reboot is explicitly deferred:
Jarvis does not require it, and a reboot would terminate the owner's current
tmux sessions and live Codex processes. V1 deliberately has no backup or restore
path and accepts possible total loss of local Jarvis state.

each fresh top-level main turn gets one fixed admitted view plus exact operative
requests/receipts. active steering retains the running loop. callers choose their
shared retrieval steps; there is no automatic recaller or rememberer.

historical reminder inventory uses `action.tool_name = schedule.wake` and
`message.source = schedule_wake`. preserve those original identities; current
source exposes no schedule tool or timer.

## Install and configure

The production cutover is split into preparation, installation, and activation.
None of the preparation scripts starts Jarvis. First converge and verify the
shared host boundary from the `dev-server` repository. An apply may report a
deferred reboot while operator tmux sessions exist; record it and leave the host
running until the owner selects a separate maintenance window.

the host must provision the jarvis account, `codex-clients` group, the private
skid client and the empty mode-02750 cognition parent. main and isolated cognition
use a separate contained personal endpoint; the existing coding server is unchanged.
install that host from the same immutable application release with
`deploy/install-contained-host`. supply the explicit non-secret schema-4 mapping
through `JARVIS_SOURCE_CODEX_HOST_CONFIG`; it names the development account, its
existing personal account home, exact stock binary, client group and cognition
parent. the installed mapping is `/etc/jarvis/codex-host.json`. the host unit exposes
that single public file at `/run/jarvis-contained/codex-host.json` through a
read-only bind; `/etc/jarvis` keeps its private traversal permissions.

the contained endpoint requires stock 0.160.0 and the provider-owned complete
restricted model catalogue at HOST STARTUP. unsupported versions and missing
startup policy fail before thread creation. per-thread overrides do not provide
containment. catalogue updates require explicit qualification; this supersedes
adr 0042's latest-stable rule for this endpoint only. the native host unit owns
its private mount namespace and publishes only its relative socket alias at
`/run/jarvis-contained/app-server.sock`. the worker receives no native credentials.
no change to the shared coding daemon, rpc relay or copied account is involved.

From a clean, committed Jarvis checkout, provision the dedicated database and
transfer only the already-qualified private application state:

```sh
deploy/provision-database
deploy/install-private-state
```

`deploy/provision-database` creates `jarvis_migrator` and `jarvis_runtime`, a
database owned by the migrator, and two split root-owned mode-0600 credential
files. The service identity cannot read either file directly. systemd reads
`database-runtime.env` for the service and a bounded transient migration unit
reads `migration.env`. It refuses a partial credential state or an existing
database whose credentials are unknown.

`deploy/install-private-state` defaults to the ignored, mode-0600 qualified
files under `.secrets/`. It validates the exact key roster, builds the static
production settings, and installs root-owned mode-0600
`/etc/jarvis/jarvis.env`, encrypted Google
connector state and the stable installation identity without printing their
values. Override its `JARVIS_SOURCE_*` paths only to name an equivalent private
source. Codex authentication and native history remain exclusively in the
authoritative personal development-user account home; never copy either into Jarvis state.

remove the retired `JARVIS_CONNECTOR_ENCRYPTION_KEYS` entry from the private
source and installed environment before deploying; the installer rejects it.
keep `JARVIS_CONNECTOR_ENCRYPTION_SECRET` and
`JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION` unchanged. no ciphertext migration is
needed. source and installed environments passed this cutover in the
[current rollout](universal-memory.md#native-memory-installed-qualification).

the private installer validates `JARVIS_SOURCE_MEMORY_CONFIG` before copying it
to `/etc/jarvis/memory.json` as jarvis-owned mode 0600. its default is the checked-in
[deny-all example](../deploy/memory-config.example.json), not an implicit grant.
set `JARVIS_MEMORY_CONFIG_PATH=/etc/jarvis/memory.json`,
`JARVIS_MEMORY_HTTP_PORT=8768` and `JARVIS_MEMORY_NIGHTLY_TIME=03:00` in the private
service environment. the nightly time is owner-local. remove
`JARVIS_DREAM_INTERVAL_SECONDS`; its presence now rejects configuration.
dev-server generates client/capture credentials and native profile files from its
single private bundle. nexus's backend declaration is separate from native profile
credentials; only its named runtime consumers receive it. qualify current image
targets and grants, not the retired private-dependency build-secret arrangement.
keep credentials out of repository files and command output.

The qualified Google client, connector-encryption, Maps, Brave, Discord, and
embedding settings remain host-owned and never enter model context or the Codex
child environment. `JARVIS_EMBEDDING_OPENAI_API_KEY` is the qualified OpenAI
project key restricted to embeddings. The deployment fixes
`text-embedding-3-small` at 1,536 dimensions. Changing either requires the
stopped rebuild procedure in SPEC 7.2.

set `JARVIS_VERIFIED_OWNER_ONLY_CALENDAR_IDS` only to unique calendar ids whose
live acls the operator verified as owner-only. calendar writes for those ids,
without attendees or notification, are automatic. other calendar writes require
ordinary conversational consent recorded by main through `approval.respond`.

the production deployment exists. install an exact committed release without
activating it. migration requires a stopped, owner-paused deployment and the
private snapshot/inventory below. a systemd one-shot injects the root-only
environment after changing to the `jarvis` identity. this intermediate release
refuses activation:

for an existing deployment, prepare a clean stop and the
[native cutover](#native-cutover). install the contained host before activation;
the worker catalog switch follows the [skid-only cutover](#skid-only-worker-cutover).

```sh
deploy/install-release
deploy/activate-release "$(git rev-parse HEAD)"
deploy/verify-containment
```

`install-release [FULL_GIT_COMMIT]` archives the exact commit (default `HEAD`), installs the exact
`.python-version` interpreter inside the release, and builds with `uv sync
--frozen --no-dev --no-editable --link-mode copy`. After root-owning the tree,
it verifies the release-contained interpreter, dependency identity and CLI as
the actual `jarvis` service identity before recording the commit/tree/lock
digest. It never writes the global service unit. Rechecking an existing receipt
also requires that service-identity proof; an unusable release is rejected, not
repaired in place. Each release carries its own interpreter/package bytes:
additional disk use buys independence from private account homes and writable
builder caches. It refuses tracked changes.

the existing builder identity must have git read access to the public
`NielsdaWheelz/universal-memory` repository before installation. the installer
checks that access before pruning a candidate. ci and local builds fetch the
immutable public git pin without a private-dependency credential.

release/contained-host installation, activation and pruning share
`/opt/jarvis/.deploy.lock`. retain only the
selected release and one temporary installation candidate; rebuild any discarded
release from its exact commit. pruning checks both the running jarvis process and
the contained host's loaded `ExecStart`. if that host still selects another
release, cleanup refuses before deleting files. cleanly stop or install the host
for the retained release before retrying; no extra rollback release is retained.

`deploy/activate-release` deliberately refuses this intermediate one-main
release. slice 1 removes the scheduler; slice 2 supplies scheduled todos. restore
activation only after the selected slices and retained reminder obligations are
accounted for. installation, private stopped snapshots and isolated qualification
remain available. source completion does not imply deployment or owner resumption.

the qualified routine-activation primitive remains in memory merge `50611a3`.
this source retains its initialized-control checks and preserves canonical
pause/resume. startup action recovery remains available; new main reasoning and
background memory wait for validated discord catch-up.

the contained unit masks the native account's `AGENTS.md` and `AGENTS.override.md`;
the original coding files remain unchanged. optional absent paths remain absent.
an outside atomic replacement exposes the new file to an already-running mount
namespace; later creation of an absent file is also unmasked. stop the application
and contained host before profile publication, then restart the same-release host
and application paused. never treat these file mounts as protection from live
configuration changes.
after memory settings are installed, qualify an actual restricted thread: the
effective configuration contains the memory registration, but every inherited
mcp server must report disabled with zero tools. startup-catalogue qualification
alone does not establish that thread boundary.


`jarvis check-activation` remains a read-only inspection of the current schema,
initialized canonical control, unfinished authority and recorded effects. an unfinished action
with a retired execution contract blocks admission. terminal historical contracts
remain opaque evidence, never an execution route. old unknown paid reads and
unfinished isolated cognition require their original release's disposition.
current unknown effects retain their existing reconciliation and causal barriers.

for a fresh database, migrate and run `jarvis initialize-state` once under the
runtime identity/environment. this creates canonical paused state, with no
provider call or action. repeated initialization refuses rather than resetting
existing requests. later release activation preserves that control state. never
edit database request rows or synthesize an empty execution journal to bypass a
failed check.

`verify-containment` runs after activation without printing secret values. It
proves the three environment files are root-owned mode 0600 and unreadable by
the service identity, verifies the active systemd `/proc` and core-dump
controls, and confirms a same-identity process cannot read the non-dumpable
Jarvis parent environment before accepting the deployment. It tolerates only
the bounded service-start interval before Python establishes that process-local
control; no provider connection is opened before the control succeeds. the
service receives the non-secret cognition profile/socket view, with no provider
account-home access. the earlier copied skid client-file path is retired.
the [authorized rollout](implementation-plan.md#memory-installed-rollout) qualifies
a root-managed read-only id-mapped view of the enrolled owner's live skid state.
the cli must match that installed state contract. preserve source modes and
ownership; the service receives no mount capability. actual installed cli/service
reads pass on both online hosts; [evidence](universal-memory.md#native-memory-installed-qualification)
keeps worker observation and offline arch qualification separate.

forward repair is required after new canonical effects are admitted; code rollback
alone cannot restore old semantics over new receipts.

## native cutover

while the original release still owns its executable contracts, pause and stop it
cleanly. reconcile entered effects and paid reads; settle original native seals.
disable old discord approval components and explicitly drain or cancel incompatible
unentered actions under that release. never renew those approvals or rewrite an
original execution contract. retain undelivered canonical prose and original
arguments, times, effect identities and receipts.

before migration, take one private database/runtime snapshot using the existing
stopped snapshot procedure. `jarvis cutover-native` now only writes
`one-main-cutover.json` in the private runtime directory, mode 0600. it requires
canonical administrative pause and holds deployment ownership. the inventory
contains outstanding effects/approvals, original schedules, waiting/stopped/parked
requests, unsettled attempts and undelivered results. it changes no request,
action, approval or deployment state. inventory is evidence, not completion.
retained reminder purpose, time and source references belong to slice 2's todo
conversion; there is no temporary reminder table or executable old scheduler.

the merged migration chain is memory `0007`, then one-main `0008`.
the one-main migration adds immutable causal parentage, gives host requests the
same lifecycle and removes the component-required action constraint. it reconstructs
parents only by joining canonical action identities; ambiguous historical host
settlement or parentage is parked for named repair, never inferred complete.
source times remain original; historical first-observation time remains unknown
where no canonical evidence exists.

retired local pause/session/admission files must be explicitly dispositioned under
the original release before current admission. the new runtime neither imports
those files nor creates successor approvals. `release-parked MESSAGE_ID...` repairs
only the named live configuration-parked requests and returns them to pending;
it cannot revive completed or conversationally stopped requests. administrative
resume only releases its own accumulated pause targets. ordinary chat `stop`
reaches main and affects only its explicitly named delivered requests.

## universal memory cutover

the existing `0004` installation first uses an immutable temporary native
predecessor to reach `0005` and import its canonical pause. it is never resumed.
its cutover validates terminal retired worker evidence through the existing
archive contract; unfinished workers and unknown effects still refuse. the
imported pause is a truthful completed control, not an owner task for old memory
extraction. the predecessor exists only for this transition and is removed after
acceptance. the one-time helper supplies an inert retired worker-setting field
to the old settings parser; neither helper dispatches workers or restores a
legacy configuration to the target runtime.

migration `0006` requires a stopped, canonically paused native `0005` deployment
with drained old remembering and resolved old memory cognition. run the stopped
helper through the selected predecessor's exact frozen interpreter and libraries;
the target runtime contains no old memory roles. parked work or
unknown old submissions refuse migration and require repair under that predecessor.

before the memory migration, use the selected predecessor runtime and
`deploy/prepare-memory-cutover` to drain and take one private recovery artifact at `/var/lib/jarvis-memory-cutover/<target-commit>`.
it contains a custom-format database dump, `/var/lib/jarvis`, `/etc/jarvis` and the
predecessor release receipt. the helper requires the deployment lock, canonical
pause and resolved drained work; it verifies the dump listing and preserves file
ownership/modes. dump and listing receive the same database environment so the
installed postgres wrappers select matching client versions. it refuses an
existing or recursively copied artifact.

migration `0008` follows the unchanged published `0006`/`0007` migrations. it
adds the configured claude-work2 account and grants the runtime only schema
identity reads. activation accepts existing `0006`, `0007` and `0008` installations;
unknown revisions refuse. the `0005` predecessor receives that same schema-read
grant under stopped ownership before its drain. no old migration is rewritten.

migration preserves canonical message/note/summary ids, text, dates and legacy
summary lineage, checking before/after counts and digests. legacy eligibility is
false and provenance stays absent. six memory tables start empty; only a declared
admitted jarvis lane activates. native collectors subsequently establish online
baselines. no historical import or metadata reconstruction occurs.

before the target's first start, recovery restores the database, runtime and
configuration together and rebuilds/selects the predecessor's exact release.
after first start, repair forward: restoring the old snapshot would erase new
canonical data. delete the single artifact after acceptance. activation does not
retain an extra rollback release. a fresh database must migrate and initialize
paused state before release activation; activation itself accepts only schema
`0005`, `0006`, `0007` or `0008`.

## admission journal cutover

historical: adr 0047's rolling-capacity journal and transitional normalizer are
retired by the native cutover. do not install the normalizer or recreate
`admission.json`. native admission uses current ownership, not cumulative usage
reservations. isolated roles retain their actual operation limits.

## herdr cutover (pr 4)

historical; superseded by [the skid-only cutover](#skid-only-worker-cutover).
adr 0048 and its recorded qualification retain the historical decision.

## herdr gate cutover (pr 5)

historical evidence remains in adr 0049. its transport is retired; use the
[current worker boundary](#skid-only-worker-cutover).

## skid-only worker cutover

[adr 0052](decisions/0052-cut-worker-control-to-current-skid.md) retains the
historical worker transition. current v10 contracts are terminal-only. settled old
worker rows remain opaque evidence; unfinished incompatible contracts block
admission and require disposition under their original release.

`JARVIS_AGENT_CLI_PATH` and `JARVIS_AGENT_STATE_DIRECTORY` select the qualified
skid cli and enrolled computer's live state. `deploy/install-agent-client`
installs the matching executable and prepares `/run/jarvis-skid-state` as a
root-owned read-only id-mapped mount. the service keeps its own uid, empty
capabilities, `ProtectHome` and `NoNewPrivileges`. current filesystem publication
remains visible without copying identity or membership; replacing the source
root requires a stopped remount. actual restricted reads pass on `macbook` and
`dev-server`; memory provenance retains `devbox`. offline `arch` is owner-deferred.
[adr 0072](decisions/0072-native-memory-rollout.md) owns this installed boundary.

`deploy/verify-agent-client` accepts an explicit installed-state directory for
that qualified boundary. `deploy/verify-containment` checks installed
owners/modes, `ProtectHome` and read-only worker access under the production
restrictions. source fixtures and artifact pins establish no installed-fleet pass.
contained cognition has its own prerequisite and qualification.

use the stopped one-main inventory and snapshot procedure before incompatible
changes. `deploy/activate-release` refuses this intermediate source. reconcile
entered effects, retain unknown effects, and explicitly drain or cancel incompatible
unentered work before any future activation. after new receipts, repair forward;
older readers cannot be made safe by erasing facts or resurrecting retired codecs.
selected-only release retention remains governed by adr 0053.

## conversational decisions

consequential tool policy creates one immutable `awaiting_approval` action. main
uses the configured owner's canonical conversation as consent evidence. an earlier
clear decision can suffice; otherwise main asks an ordinary question. it need not
ask again merely because the action was recorded later. main supplies the action,
approve/deny decision and actual owner-message id to `approval.respond` during a
current admitted turn.

the action transition and original local callback receipt commit atomically.
approval queues the stored arguments; denial cancels without an external effect.
the receipt proves the decision, not execution success. repeats return the first
successful decision without requeueing; a contrary decision is rejected. no
component, preview attachment or interaction handler exists in current source.
never decide an action directly in postgres.

scoped stop cancels all proven unentered work of its named request, including
pending approvals. entered effects still reconcile. a late event preserves its
stopped parent's state and cannot revive it. administrative pause covers all
waking requests; resume releases only its accumulated pause targets and never
resurrects cancelled actions or conversational stops.

Gmail send is available only for a draft with immutable Jarvis draft-creation
lineage. Immediately before send, Jarvis fetches the known draft and compares
its thread, effect header, recipients, subject, and complete body with the
approved snapshot. Any mismatch sends nothing. Ambiguous recovery reads the
known draft in three observations separated by fixed `0`, `2`, and `8` second
backoffs. Each observation fetches the known thread with `format=minimal` and
fetches at most one hundred enumerated messages individually with
`messages.get(format=raw)`; it never performs a mailbox search or assumes thread
ordering. Excluding only the current live draft message ID, one unique observed
exact effect-header/content match proves success after every selected bounded
message is processed, even when the draft remains or the thread has an
unprocessed tail beyond one hundred messages; no Gmail label is required.
Repetition requires three complete observations proving that the exact unchanged
draft remains and the complete thread has no matching non-draft message, plus
remaining immutable attempt capacity. Duplicate,
conflicting, malformed, transient, or partially processed evidence cannot prove
absence. The original send timeout decides nothing by itself. Expiry of the
separate thirty-second, sixteen-MiB reconciliation procedure is bounded
exhaustion with incomplete evidence and yields safe terminal uncertainty for main to explain with its original evidence.

This path can issue up to 102 provider reads per observation and 306 across all
three. That bounded latency and quota cost is accepted to avoid relying on Gmail
search indexing or undocumented list ordering. Gmail draft-update recovery uses
the same minimal-thread plus at-most-one-hundred raw-message expansion if its
known draft disappears; that read shape and ceiling are revisioned policy
inputs, while the unshipped v1 implementation name remains unchanged.

## verification

```sh
scripts/verify
```

the command checks the frozen environment, formatting, lint, types, documentation
links, package build/install, and installed dependency vulnerabilities. it needs
no database and runs no behavioral tests.

hosted verification resumed on 2026-10-01 after the earlier billing restriction;
[the urllib3 upgrade run](https://github.com/NielsdaWheelz/jarvis/actions/runs/36797257323)
passed the complete static/build/audit workflow for that revision. this is
historical evidence, not current behavioral or activation qualification.

[adr 0046](decisions/0046-reset-testing.md) removes the test suites, fixtures,
evaluation corpus, and qualification harnesses. their execution gates are
suspended pending the [testing redesign](issues/testing-redesign.md). dated
qualification reports in git remain evidence for their recorded revisions;
static and build success does not establish current behavioral qualification.

the owner separately authorized temporary native integration/live proofs under
adr 0065. use the [current native acceptance](acceptance.md#native-cutover-acceptance)
and its exact installed evidence; delete those feature probes after final green.
this exception restores no retired suite or unrun production acceptance.

## shared runtime and fleet control

within one active top-level turn, main retains its compatible native thread until
that turn ends, is stopped or loses its connection/owner. the next top-level turn
gets a fresh lease and admitted view. connection loss fences old callbacks, then restarts reasoning
from canonical requests and durable results in a fresh thread. recorded effects
remain authoritative; unresolved action/read outcomes retain their barriers.
provider history is disposable. a sealed original terminal is settled locally
before current model/plan reconstruction, with current request/publication fences.

set `JARVIS_CODEX_HOST_CONFIG_PATH=/etc/jarvis/codex-host.json`. the schema-4
root-owned mapping names only the contained personal endpoint and the mode-02750
cognition parent. no native authentication belongs in jarvis state or environment.
main has no arbitrary elapsed cutoff or cumulative model/tool quota. per-operation
bounds, finite callback queues and owner stop still apply.

peer agent control uses the explicitly configured `JARVIS_AGENT_CLI_PATH` and
`JARVIS_AGENT_STATE_DIRECTORY`. skid owns installed auth/routing and refresh;
jarvis retains its personal machine/profile enums. the installed service reads
the enrolled development user's same live state through the qualified read-only
id-mapped mount. root manages that mount; application permissions remain narrow.
no copied client-json reader, second ref codec or fallback transport remains.

the target-release tools are agent.list/info/start/read/send/text/keys/stop/close/
wait/cancel_wait. addressed inputs use short `{machine,handle}`; current v10 accepts
only `t-` plus 16 lowercase hex digits. the host captures the original terminal
ref before action admission and retains it through delay/restart. terminal
loss/reassociation never silently renews that target. worker-native conversation
handles, history and controls are removed; native cognition and memory archive
access remain separate capabilities.

terminal send is guarded input for both providers. start accepts name, cwd, group
and literal optional stdin; the configured
profile command owns provider options. model/effort launch fields are rejected. creation/input and interruption/closure facts remain
independent, including nonzero partial results. terminal written means dispatched;
it proves neither provider acceptance nor completion. unknown writes
enter once and never replay; conclusive owned receipts settle without re-entry.

wait registration returns watching immediately; a separate durable outcome/event
observes the original ref outside main's mutex. cancellation stops observation,
not execution. a matched state and later bounded text are separate evidence.
worker observations enter the same full main plan and may settle silently.
original effect/read barriers and stopped-parent intent remain in their causal
context; a factual event never turns source prose into owner consent. partial
inventory, unavailable/truncated text and lost receipts remain material limits. old finalized worker rows retain only recorded status and opaque
receipt details; their raw records remain unchanged.

future activation follows [the skid-only cutover](#skid-only-worker-cutover).
worker control reuses durable actions and asynchronous observation, adding no
history store, provider client or cognition lane. the active plan and paired spec distinguish
passed local acceptance from remaining installed-fleet/production qualification;
the latter must pass before claiming this target release activated.

`gpt-5.4` is deliberately rejected during configuration because OpenAI retired
it from ChatGPT-authenticated Codex on 2026-08-31. The negative final-code probe
that exposed that retirement is preserved in ADR 0028; do not retry it as a
supported route or switch Jarvis to API-key authentication.

## memory operations

inspect the live service without taking its ownership lock:

```sh
uv run jarvis memory status
```

status reports all declared/omitted lanes, activation/checkpoints/parks, canonical
projection backlog, tree frontiers and dream progress. the new nexus capture
handoff adds central registration/progress here; nexus's own
`memory-capture-status` and `memory-capture-retry` commands own pending exports
and parked diagnostics. do not claim those surfaces are deployed before their
implementation. status prints counts
and identities, never memory text. the shared mcp endpoint has no operator status tool.

before installation, record selected jarvis/nexus commits, each frozen dependency
lock and built image digest, then advance dev-server's collector release pin to
the qualified jarvis artifact. old four-pin equality and old qualification do not
qualify current consumers. source, artifact publication, installation, capture
activation and owner resumption require distinct receipts. hard-cut replaced
paths without rewriting originals or moving activation boundaries backward.

repair and retry only while the service is stopped, after correcting the cause:

```sh
uv run jarvis memory retry-capture SOURCE_CONVERSATION_UUID
uv run jarvis memory retry-compression
uv run jarvis rebuild-memory --node START+COUNT
uv run jarvis rebuild-memory
uv run jarvis dream
```

capture retry clears only its diagnostic; it preserves the original activation
boundary and checkpoint. compression retry clears only the parked construction.
node rebuild invalidates affected ancestors and reconstructs persisted frontiers.
full rebuild also reindexes all three searchable stores and clears/rebuilds
vectors. it requires `JARVIS_MIGRATION_DATABASE_URL` for the same configured
database: reindex needs object ownership, which the runtime role deliberately
lacks. inject that environment privately, never through a command argument.

repair preserves originals, leaf positions, completed capture and dream progress.
it does not regenerate authored syntheses, re-admit history or run a dream.
failed embedding repair exits nonzero with derived work still pending. repair the
cause and rerun; there is no private background replay journal to reset.

nightly idle dreaming defaults to 03:00 in the owner timezone. one persisted
attempt marker prevents repeated same-occurrence attempts, even after empty or
failed work. each successful run consumes one fitting prefix since
`dream_through`; late capture and missed days remain pending. foreground input
interrupts reasoning while entered transactions finish atomically. one manual
stopped command processes a bounded prefix and prints counts only. syntheses
append quietly, never seed another dream or create a main turn/notification.

migrations grant narrow original append/update privileges to `jarvis_runtime`.
original text/identity/date and note provenance are immutable; only derived
vectors and specified checkpoint/state fields may change. legacy flat summaries
remain readable/searchable and receive no new writes.

## Restart and recovery

Startup first reconciles every queued or executing action whose original turn
cannot safely resume. Each exact current binding and immutable execution
contract must still match. Provider reads never increment executor entries;
re-execution occurs only after tool-specific evidence proves absence and safety
and both immutable ceilings still permit it. Unresolved evidence becomes
terminal `uncertain`; registered worker waits resume observation without
repeating their registration. Missing action-resolution inputs are
inserted idempotently before ordinary message work begins.

`gmail.create_draft` is never repeated after an ambiguous provider result. Its
three bounded observations use `users.drafts.list` without `q`, traverse at most
five pages of eight unordered IDs per observation, and fetch at most forty raw
candidates. The entire procedure is capped at thirty seconds and sixteen MiB of
accepted response bodies, in addition to the shared two-MiB response cap. An
observed exact effect-header and normalized-content match without an observed
duplicate or conflict proves success even if pagination is incomplete; every
unresolved path, including a complete enumeration with no match, becomes
terminal `uncertain` and produces the ordinary idempotent action-resolution message.
`nextPageToken` is recorded only as absent, present, invalid, or unknown, never by
value. Operators must inspect Gmail before choosing to make a later, distinct
owner-requested action; recovery never requeues the original create.

startup fences old native callback owners and settles original sealed terminals
locally before new cognition. it then performs bounded Discord catch-up, retries
persisted outbox rows with null `source_message_id`, and scans canonical pending,
unparked requests and host facts. reasoning uses a fresh native session from
canonical context and original action/read receipts; unknown entered work cannot
redispatch. there is no saved main-session reference or rolling charge.
after foreground work yields, the serial background worker completes ready
chronological nodes, indexes eligible missing vectors and performs an admitted
nightly dream. canonical publication retries eligible missing source events;
eligibility is independent of settlement groups or host/owner role. background
work waits for the serial lane and requires its current-owner permit; no
capacity-reset timer exists.
isolated roles retain finite invocation/tool bounds; main has no cumulative
model/tool quota or arbitrary elapsed cutoff.

a committed approval receipt survives a lost callback reply or process death.
startup recovers the queued action through its original current contract; only
actual executor entry increments `attempts`. an entered effect always follows
its bounded reconciliation procedure before a proven safe repeat. a local decision
receipt does not suppress the eventual external outcome event. unresolved retired
contracts block admission rather than renewing an approval.

newly resolved action facts are published once with their original outcome time,
source identity and causal parent. publication and rearming exact action waiters
share one transaction. main may answer or remain silent; both require explicit
request dispositions. malformed sealed output parks every affected live request
for named repair and emits one deterministic failure notice. it never marks the
host facts handled or replaces the original seal with fallback prose.

Successful outbox delivery drains every current batch. A row that exhausts its
finite delivery retry schedule remains pending and stops that drain; the next
startup or ingress signal retries it with the same persisted UUID and nonce.
Catch-up selects Discord's newest bounded page after the canonical owner cursor,
then persists eligible owner messages in chronological order. If downtime
traffic exceeds that bound, the oldest overflow is intentionally skipped; this
prevents a full page of bot or non-owner traffic from permanently hiding a later
owner message without adding non-canonical cursor state.

`pause` and `resume` are exact, case-insensitive administrative controls.
repeated pause retains prior targets and adds newly pending requests; a completed
resume ends that accumulation. ordinary `stop` reaches main unchanged and only
its named delivered requests stop. process termination cannot undo an external
effect; original actions reconcile before any repeat.

the historical deployment report records that release's always-on service.
native host installation/activation and the seven-day owner acceptance require
their own actual receipts; source or local topology proof establishes neither.

If a configuration defect parks input, first stop the service and correct the
defect. Then clear only the reviewed UUIDs while the command owns the deployment
lock:

```sh
jarvis release-parked MESSAGE_ID [MESSAGE_ID ...]
```

This does not reset `processing_attempts` and does not arm hidden successor
work. Never edit `trace` to control scheduling.

if canonical request/attempt state is corrupt, stop admission and inspect its
original records. preserve receipts and unresolved barriers. never reset a paid
attempt, action or request to make it look undispatched. there is no rolling
admission file to repair.

## Data durability and logs

the [target cutover](universal-memory.md#9-migration-and-hard-cutover) takes one
local pre-migration `pg_dump` with the necessary runtime/configuration copy. this
is a cutover recovery artifact, not ongoing or off-machine backup. follow the
current contract's restore limits; do not treat code rollback as data rollback.
activation stays in postgres. sources and notes stay append-only; revocation
stops new capture/direct saves without removing already admitted material.
V1 has no backup, restore command, Restic repository, R2 credential, backup
database role, or backup timer. There is no `jarvis-restic-password`; do not
invent or provision one. Loss or unrecoverable corruption of the devbox, its
disk, or the Jarvis database can permanently lose conversation, memory, action,
and runtime state. This is an explicit one-user-prototype trade-off. Add backup
as a later slice when retained production state justifies its operational and
qualification cost; doing so does not require another application table.

Ordinary logs contain event types, bounded IDs, counts, and reason codes
only—not messages, prompts, memory text, tool payloads, tokens, or credentials.

Raw memory is permanent and grows without a deletion path in v1. Embeddings and
full-text indexes are derived and can be rebuilt while the local raw log exists.
Embedding ingestion, rebuilds, and semantic search queries disclose their input
text to the metered embedding processor. An embedding outage leaves new vectors
null and the bounded indexing sweep retries later. query embedding failure makes
shared search unavailable; it does not select a lexical-only fallback. original
opening and tree navigation require no embedding call.

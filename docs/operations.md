# production operations

at schema `0016`, two cpython 3.12 services run one selected release against
the same postgres database. `jarvis.service` owns the configured discord channel,
canonical work and derived memory jobs. it uses the separate contained native
host for cognition. `jarvis-memory.service` owns external capture, the shared
memory endpoint on loopback port 8768 and the private search/index socket.
its os identity, database role, lock and cgroup let reads, capture and note
saves continue while the assistant and native host are stopped.

dev-server owns private tailnet routing on port 8443 and native client
configuration. [universal memory](universal-memory.md) owns the archive
contract. [memory delivery](memory-delivery.md) owns nexus capture.
[adr 0086](decisions/0086-native-recovery-and-memory-availability.md) defines
the two stopped release cuts. candidate evidence and production acceptance
are recorded separately.

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
status is cli-only. the private cutover copy covers the stopped transition.

nexus capture is future-only for new admitted owner-librarian runs. its durable
pending export retains the approved question/answer, saved citation/attachment
excerpts and available persisted tool receipts before source deletion can lose
them. retry delivery with the same identity/content; remove the export only after
central acknowledgement. source deletion neither deletes central originals nor
cancels pending delivery. no revision/remove sync or historical import is added.
reads, optional note saves and capture have distinct grants under the shared
private declaration. automated helpers and other viewers receive no memory tools.

## accepted v2 target and operational scope

[f2](runtime-reliability-and-integration.md), under
[adr 0077](decisions/0077-production-acceptance-and-fresh-reset.md) and
[adr 0078](decisions/0078-fresh-corpus-first-acceptance.md), owns isolated proof →
stopped v2 cutover → preliminary fresh reset → real production acceptance → final
fresh reset. f2 records the completed preliminary reset and current journey
evidence. the final reset follows installed acceptance.
the real channel/token/mailbox actor is exclusive. an irreproducible historical
native incident may remain explicitly open; new demonstrated defects require repair.
both resets clear discord/jarvis/all central shared history and commitments while
preserving private repos, credentials, real google data and original native chats.
the exact source-cut, attachment and recovery constraints are in the f2 contract.
retain one verified current `0013` recovery artifact before each wipe; verify its
successor before disposing of an older full artifact, retaining original receipt/
manifest hashes. original reviewed historical uncertainties remain unknown and
non-replayable. fresh-corpus proof leaves large-backlog preparation latency unqualified.

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
need not be independently usable. slice 2 implements todos and their timer;
retain outstanding reminders in the private stopped inventory until supervised
conversion. selected slices and accounted-for commitments govern activation.
the owning contracts define migration, local decision receipts and scoped stopping.

optional one-time/repeated wakes belong to work records, replacing separate
schedule/recurring-wake products. due dates remain distinct. keep the existing
asynchronous skid observer and separately prove its installed event delivery;
no new callback service or repeated model polling is proposed. native notes/files
use the persistent private checkout; inbound originals use private r2 storage.
activation must use the qualified artifacts and
their cutover instructions, reconciling entered effects before incompatible
changes. this section supplies no new migration command or deployment authority.

the [implementation plan](implementation-plan.md) owns those handoffs. shared
memory delivery and quiet dreaming remain unchanged. browser/credential products,
interactive hosting, a separate ui, selected dream wakes and work context
remain outside this cut; later search and budget contracts are not adopted here.

### attachment handoff

[slice 5](attachments-and-durable-originals.md#implementation-evidence) is
implemented with separate candidate qualification: database/native host, private
r2 bucket and cache. its evidence distinguishes live provider paths, controlled
faults and resource disposition. preserve production's selected release and
endpoint until the qualified final v2 cutover; installation/activation follow f2.
the private bucket and scoped object-only standby credentials are provisioned;
the linked evidence owns their location and controls. production environment
publication remains deferred. final cutover publishes that private configuration
and exposes only the app-owned original cache for native read access; bucket public
access and expiry remain disabled.
the native uid receives neither storage credentials nor the app's private state.

slice 5 has seventeen application tables at migration `0011`; its attachment
table follows work's `0010`. the event cursor brings current source to eighteen
at `0012`. the application writes the shared
`/var/cache/jarvis/attachments` cache; the native host mounts it read-only. originals
and their private staging never belong in the notes repo. restart discards the
app-owned cache contents and rematerializes verified r2 bytes on demand; it does
not replace the mounted cache root.

`jarvis attachment-reconcile ATTACHMENT_ID [--after-manual-cleanup]` now observes
one registered key/cache under exclusive deployment ownership. run it with the
configured runtime identity/environment while the service is stopped. it requires
no canonical `pause` and creates no pause/resume cycle; separate authority-change
and final-cutover pause requirements still apply. it neither repeats an unknown
put nor performs operator cleanup. absent evidence cannot prove that an entered
put will never complete.

without intervening manual mutation, positive evidence can reconcile the original
action and publish its normal outcome while preserving its original callback
receipt. a failed preflight with no prior provider entry, or a definite rejection
of the first provider attempt, fails the action. earlier staged attempts still
require reconciliation. conflicting metadata never authorizes deletion.
an unresolved entered deletion remains
`deleting`/`DeleteUnresolved` with an uncertain action. `CacheCleanupFailed` is a
failed partial deletion: the remote original is proved absent, but local cache
cleanup failed. the row remains `deleting`; never reset it to ready or describe
the entire deletion as complete.

if ordinary operator tools have changed this key/cache, the
`--after-manual-cleanup` flag is required. it records factual storage/cache state
without upgrading an original failed or uncertain action to success, rewriting
its native receipt or clearing an existing uncertainty barrier. independently
authorized new owner work remains possible. deletion removes our original/cache,
not source mail/discord, scratch copies, open handles, conversation, notes or
memory. no public links, upload website, extraction service or backup promise is
added.

### email/calendar source handoff

[slice 6 evidence](event-sources-and-recurring-work.md#implementation-evidence)
qualifies source and its separate combined candidate against the landed attachment
helpers/migrations. production remains unchanged; the installed event-source
cutover is still deferred. final cutover initializes quiet account-scoped
baselines; expired provider cursors leave explicit unknown coverage. no historical
mail/calendar reconstruction, push subscription or additional daemon is added.

source polling starts only after validated discord catch-up and respects pause
and family switches. disabling a family preserves progress and already published
work. after repairing a blocked source, a fresh `events.configure(enabled=true)`
re-arms it without clearing its outage until a complete scan succeeds; exact
action replay never repeats that mutation. daily review is ordinary work data,
created once during supervised setup, never recreated at startup.

### private workspace handoff

[f3](subscription-model-runtime.md#implementation-evidence) implements and qualifies
main astra/max, memory sol/xhigh and native-child/per-session skid model choices.
its separate candidate preserved production's runtime and private mapping. the
v11 worker cutover settles/cancels pending v10 waits and publishes outcomes with
the original release; no old watcher, model fallback or effect replay is added.

[slice 4](private-notes-and-rolodex.md) implements general files/commands/git in
the new private `NielsdaWheelz/jarvis-notes` checkout, including helpers and visual
artifacts. source and a separate temporary candidate are qualified with the
schema-5 mapping; production acceptance remains separate. final v2 cutover
bootstraps the persistent checkout and host git access, installs the qualified
host/application pair and preserves dirty work thereafter. existing authority-
change pause/stopped checks apply; ordinary release pruning never deletes the repo.

candidate proof uses a separate temporary native unit/endpoint/mapping, checkout,
database and runtime state. do not use `install-contained-host` to rewrite the
running production host for that proof. host-account authentication must work
inside the actual service environment; a developer shell proves no such access.
hosting, television integration and a separate artifact ui remain deferred.
stock drains active child turns/admissions on native-host stop. the existing
ten-second host deadline may force-kill it; sigint and sigterm share that path.
inspect checkout/git after restart; neither control acceptance nor bounded stop
proves every native command or child terminated gracefully.

final bootstrap requires an existing private `NielsdaWheelz/jarvis-notes` remote
with a `main` branch and a brief readme. creating that remote is a separate final-
cutover operation, never an installer/runtime action. `codex-host bootstrap-notes`
uses the same clean host `HOME`/`PATH`/account environment as native startup:
ordinary ssh authentication must work without forwarded `SSH_AUTH_SOCK`, copied
credentials or login. it first proves selected-origin existence/access with
authenticated git, then requires anonymous github api status 404 for the exact
repository. a public 200, redirect, rate limit or network uncertainty blocks
bootstrap; git failure alone proves no privacy. this avoids a second api token,
at the cost of requiring both git and the anonymous visibility check to be
available during installation.

`install-contained-host` runs bootstrap in a temporary unit derived from the
same rendered host unit, preserving identity, namespace, instruction masks and
privilege restrictions before replacing the final mapping/units. it renders and
installs both host and application units from the same immutable release; the
application remains stopped until f2's separate qualified activation.
new checkout
root `/var/lib/jarvis-notes` belongs to the native uid and `codex-clients` with
mode 02750; only its new `.git` directory gets client traversal/read. existing
checkout files, dirty state, branch, origin and modes are preserved. ownership,
mode, origin, privacy or authentication mismatches require explicit repair;
the installer never pulls, resets, cleans, rewrites origin or recursively changes
permissions. a failed bootstrap leaves the application/host stopped and
retains any checkout files for inspection. never delete this directory while
pruning releases. app preflight needs read/traversal of the root and `.git`
directories, not access to every git file. native writes may remain mode 0600.

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
source exposes no legacy schedule tool or timer. its single work timer publishes
`work_wake` inputs through the common native path.

## administrative transport

run deployment entrypoints from the operator workstation, where the separate
`dev-server-deploy` ssh key already lives. privileged remote operations use
`ssh -T -o BatchMode=yes -o ForwardAgent=no dev-server-deploy 'sudo -n …'`; entrypoints use that
fixed alias and never fall back to `dev-server` or prompt for a sudo password.
for an administrative session, open `ssh dev-server-deploy` from that workstation
and use `sudo -n` for the server commands below. do not run the privileged phase
from a developer agent on the server, copy the deployment key there, restore
niels sudo/group membership or install a replacement privileged wrapper.

`dev-server` remains the unprivileged niels development connection. niels may
build under its ordinary identity when the deployment process explicitly selects
it; it cannot administer the host. development docker uses niels's separate
rootless engine. system docker belongs to root-controlled nexus production and
must not be used for jarvis development fixtures. jarvis remains the existing
`jarvis` systemd service with native postgres 16, its established runtime identity,
release directories, locks and private configuration.

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
`deploy/install-contained-host`. supply the explicit non-secret schema-5 mapping
through `JARVIS_SOURCE_CODEX_HOST_CONFIG`; it names the development account, its
existing personal account home, exact stock binary, client group and cognition
parent and required canonical `notes_repository` path `/var/lib/jarvis-notes`.
schema 4 is rejected. the installed mapping is `/etc/jarvis/codex-host.json`. the host unit exposes
that single public file at `/run/jarvis-contained/codex-host.json` through a
read-only bind; `/etc/jarvis` keeps its private traversal permissions.

the contained endpoint requires stock 0.160.0 and the provider-owned complete
restricted model catalogue at HOST STARTUP. unsupported versions and missing
startup policy fail before thread creation. per-thread overrides do not provide
containment. catalogue updates require explicit qualification; this supersedes
adr 0042's latest-stable rule for this endpoint only. the native host unit owns
its private mount namespace. `/run/jarvis-contained` stays mode 0710;
its owned `exec` directory stays 0700 and is bound as the ancestor `/tmp` in the
native namespace. stock creates its physical `codex-daemon-uid` child at 0700;
never bind that reserved child directly or widen its permissions. after private
qualification, only the socket becomes 0660. private alias
`exec/app-server.sock` points relatively to `codex-daemon-uid/hashedsocket`, so
the root service manager resolves the same inode outside that namespace.

globally `/run/jarvis-contained/app-server.sock` is an empty regular mode-000
placeholder. it is never a public socket, symlink or hardlink. root-owned
`jarvis.service` binds only the private socket FILE read-only over that endpoint
inside the application namespace. native commands see the placeholder and the
private alias targets stock's masked daemon child; actual native authority proof
remains required. provider handshake proves application access; `os.access(W_OK)`
is redundant and may return true even for the read-only socket bind.

application `BindsTo` and `After` depend on the native host. host loss/replacement
stops the application through its existing graceful SIGINT/settlement path;
the operator must explicitly restart the application after host recovery to
mount the new socket inode. there is no automatic application start, proxy,
root publisher, idmap, `PartOf` or `Upholds`. stopped release/host replacement
preserves canonical waits, seals and entered effects; inspect original evidence
and issue an explicit repair wake where needed. never replay native commands.
bootstrap derives the same host mount layout while that host is stopped and
creates no active control endpoint. cleanup removes only owned ephemeral aliases
and placeholder; the notes checkout is untouched. the worker receives no native credentials.

native host uses default `ProcSubset=all` so installed bwrap can read the kernel's
overflow uid/gid metadata before sandbox startup; application keeps
`ProcSubset=pid`. this exposes ordinary additional readonly kernel/system metadata
to the trusted native domain. `ProtectKernelTunables=true`,
`ProtectProc=ptraceable`, no-new-privileges and empty capabilities remain.
no change to the shared coding daemon, rpc relay or copied account is involved.

for an empty installation, bootstrap with the a–c release and its existing
private installer before the two-release memory cut below. no-argument
`deploy/provision-database` creates the migrator and assistant runtime roles
and installs their root-owned mode-0600 environment files.

on an established `0016` deployment, `deploy/install-private-state` publishes
an explicit private-configuration change with both services stopped and the
recorded pause in force. use the qualified workstation `.secrets/jarvis.slice0.env`
(or `JARVIS_SOURCE_ENVIRONMENT`) as the input. this is one private project file
containing the installer's required secret/authority assignments, including
the embedding project key. the installer supplies the static model, dimension,
database-independent paths and listener port, then separates the service
environments. `.env.example` and `.env.memory.example` show the two **runtime**
environments for local development. the private project file has its own key
roster in `deploy/install-private-state`. use the matching current
`JARVIS_SOURCE_GOOGLE_STATE` and original `JARVIS_SOURCE_MEMORY_CONFIG` for a
private-state publication. the `0015→0016` cut reads the installed files directly.

remove the retired `JARVIS_CONNECTOR_ENCRYPTION_KEYS` entry from the private
source and installed environment before deploying; the installer rejects it.
keep `JARVIS_CONNECTOR_ENCRYPTION_SECRET` and
`JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION` unchanged. no ciphertext migration is
needed. source and installed environments passed this cutover in the
[current rollout](universal-memory.md#native-memory-installed-qualification).

the private installer validates `JARVIS_SOURCE_MEMORY_CONFIG` before copying it
to `/etc/jarvis/memory.json` as root:jarvis-memory mode 0640. its default is the checked-in
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

[adr 0086](decisions/0086-native-recovery-and-memory-availability.md) owns the
owner-approved, verified stopped `0013→0015` incident repair. only that exact cut
may preserve the last actual control when the stalled release cannot record a pause.
the later `0015→0016` grant/service cut requires the ordinary recorded pause and
both writers stopped. the adr also defines memory command locks. installed acceptance
is pending.

### stopped memory cut from 0015 to 0016

use the separately qualified a–c release for the first incident cut. its
[original instructions](decisions/0086-native-recovery-and-memory-availability.md#delivery-ownership-and-cost)
bind the stopped `0013` source and preserve existing control. this release accepts
`0015` as its migration source and requires the latest recorded control to be
pause. select the exact qualified a–c and d commits on the operator workstation.

for the earlier incident cut, rehearse the exact production snapshot privately
before migrating the live database. restore its verified dump to a separate
postgres database, migrate that copy to `0015`, and run the a–c release's stopped
`check-activation --fit-pending-mail 0d3bcc75-749d-4014-a0df-3cdf545366b3`
there with the same source declaration, original scope and qualified native
catalog. use only the scratch database credentials. check both the actual
ready-view fit and every unfinished action verdict. the isolated candidate had
a different ready prefix. a genuine predecessor `work.create` failed on that
target because its frozen main plan changed. preserve the actual action and
resolve any refusal before committing the live migration.

1. install d inactive. drain work where feasible, record the owner's pause
   through discord and cleanly stop the assistant. if memory already has a unit,
   stop it too. leave the original recovery copies and selected release in place.
2. prepare a private snapshot. provision the memory login and os identity under
   that verified stopped cut. this stages the three memory environment files.
   the selected `0015` release keeps its existing settings and declaration access.
3. run `--migrate` before replacing the native host. snapshot verification and
   migration share one transaction holding both database keys, assistant first.
   after commit, the helper verifies `0016`, publishes shared declaration access
   and removes the embedding key from the assistant environment. it can repeat
   this handoff with the staged credentials after an interruption. install the
   same-release native host and activate with both exact commits. both services
   start from the selected release with the same pause and preserved original-row
   digests across all eighteen tables.
   the unchanged tailnet proxy forwards to the memory listener on loopback 8768.

   ```sh
   deploy/install-release "$to"
   deploy/activate-release --prepare "$from" "$to"
   deploy/provision-database "$from" "$to"
   deploy/activate-release --migrate "$from" "$to"
   deploy/install-contained-host "$to"
   deploy/activate-release "$from" "$to"
   deploy/verify-containment
   ```

   if a check fails before start, keep the hold and inspect its diagnostic. an
   interrupted snapshot may leave an unpublished private `.incomplete-*`
   directory. repeat prepare to take or verify the named snapshot. after a
   committed migration, retry `--migrate` to finish the credential handoff,
   then install the host and activate with the original two receipts. the
   verified copy stays in `/var/lib/jarvis-cutover/adr0086/$to`. pg_restore
   traverses the dump at creation. verification checks the full dump checksum,
   copied declarations/state and original receipt, checkpoint and retry facts.

4. check that the paused assistant and memory each have a live pid in the same
   release. stop the assistant and native host to verify authenticated memory
   save/open and capture. start the host, then the assistant to remount its socket.
   resume through ordinary owner conversation after checking retained control.

for subsequent same-schema updates, cleanly stop both services, install the
target and its native host, then run `deploy/activate-release "$to"`. routine
activation preserves canonical control. pruning retains the selected artifact
and one candidate while checking each running process.

the memory unit runs as `jarvis-memory` using the login `jarvis_memory`.
`/etc/jarvis/database-memory.env`, `memory.env` and `embedding.env` supply its
role, declaration/listener settings and embedding project respectively. the
assistant uses `database-runtime.env` and `jarvis.env`. systemd reads the
root-owned credential files. the assistant reaches private search and indexing
through `/run/jarvis-memory/internal.sock`, mode 0660 in a service-owned mode
0750 directory. only the assistant and memory identities have the group.
memory stays online through assistant/native host stops. its process restart
invalidates disposable cursors. new originals can open while ready coverage
and indexing lag. verify the memory pressure limit and postgres headroom before
production acceptance on the actual host.

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

for a fresh database, use a–c to migrate through `0015`, load the deployment
channel and memory declaration, and run its `jarvis initialize-state` once.
that creates the canonical initial pause. supply the same
`JARVIS_DISCORD_CHANNEL_ID` to the d migration environment. advance to `0016`
only after provisioning the memory login. the same sequence applies to isolated
test databases. never initialize or reset an existing populated database.

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

the current source migration chain continues from memory `0008` through
per-conversation baselines `0008a`, one-main `0009`, work `0010`, attachments
`0011`, event sources `0012` and lossless read-result storage `0013`.
work adds the mutable todo table and its current schedule; attachments add
one original-metadata table and immutable upload manifests. old messages without
manifests retain their text/archive digests. runtime admission requires the exact
`0013` schema head; this is not an installed-production migration receipt.
the one-main migration adds immutable causal parentage, gives host requests the
same lifecycle and removes the component-required action constraint. it reconstructs
parents only by joining canonical action identities. native committed products
and exact canonical inline conclusions preserve proven host completion; ambiguous
historical settlement or parentage is parked for named repair.
source times remain original; historical first-observation time remains unknown
where no canonical evidence exists.

### supervised todo setup

the installed cutover reached schema `0013`. the private original inventory
`retired-one-main-cutover.json` (sha256
`f0b30e8c3df8519958a410690e05c5f1cd6e8b4907aa3708cde08991421c3086`)
contained zero reminders, three reviewed historical actions, zero undelivered
messages and zero unsettled attempts. genuine owner resume sequence 9 preceded
the real fixture todo and wake. the preliminary reset created no daily review.
the later restart with a pending timer remains part of f2.

the [two selected fresh resets](decisions/0078-fresh-corpus-first-acceptance.md) clear every todo/reminder/wait
and supersede daily-review creation for those resets. do not recreate one on startup;
future ordinary owner work can request it. the original setup procedure below
remains the source contract outside this one-off decision.

account for each retained reminder in the private cutover inventory before the
selected v2 release resumes unattended. give main its original purpose, intended
time and source reference through ordinary conversation. recreate future
obligations through `work.create`; present overdue obligations as explicit current
inputs describing their original timing. verify committed receipts/current rows
against the inventory. retain historical receipts unchanged; do not replay old
schedule actions or infer completion from their terminal status.

during supervised setup, ask main once to create `review active work`, initially
backlog, with content `review active work, especially blockers; choose useful
follow-through.`, no deadline and a daily `09:00` rule in the configured owner
timezone. choose a future lower bound and verify the committed next local time
and zone. this is an ordinary todo: restart never installs it, and deleting it
ends the commitment until deliberately created again.

deadlines alone do not wake main. timer publication leaves recurring rows active
and advances only their schedule cursor. pause suppresses publication; resume
coalesces missed occurrences into one latest-due input. an admitted schedule may
already be overdue by executor entry and then wake late. get/list observations
are fresh; old wake snapshots and mutation receipts retain their original facts.
complete/cancel/delete clears future scheduling without retracting published
inputs or stopping an entered effect. operator failures preserve invalid schedule
evidence for repair rather than skipping it.

retired local pause/session/admission files must be explicitly dispositioned under
the original release before current admission. the new runtime neither imports
those files nor creates successor approvals. `release-parked MESSAGE_ID...` repairs
only the named live configuration-parked requests and returns them to pending;
it cannot revive completed or conversationally stopped requests. administrative
resume only releases its own accumulated pause targets. ordinary chat `stop`
reaches main and affects only its explicitly named delivered requests.

## universal memory cutover

historical memory migration completed before the current v2 transition. the
installed per-conversation capture patch uses schema `0008a` and
`native-archive.v3`; its exact receipts remain in the
[installed memory evidence](universal-memory.md#native-memory-installed-qualification).
the earlier temporary native predecessor and rememberer-drain helper are retired.
reconstruct an old release from its exact commit only for an explicitly selected
recovery; current source supplies no legacy execution branch.

normal future-only native capture preserves established cuts. unavailable
conversations retain explicit pending baselines and take a fresh cut on their
first readable head. ordinary upgrades do not reset those cuts. the
[two stopped resets](decisions/0078-fresh-corpus-first-acceptance.md) are the sole selected exceptions; the f2 contract owns
its complete inventory, quiescence, finite wipe and new capture boundaries.

before the target's first start, recovery must restore database, runtime and
configuration together and rebuild/select the exact predecessor release. after
first start, repair forward: restoring an older snapshot would discard newer
canonical data and might repeat external effects. retain only the selected
release after successful acceptance; recovery artifacts are separate from an
installed rollback release.

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
historical worker transition. current v11 contracts are terminal-only. settled old
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

[slice 3](delegated-follow-through.md#temporary-qualification-and-acceptance) uses
a temporary candidate, task database/runtime state and real installed skid under
service restrictions. production's release, database and canonical control remain
unchanged. its controlled ingress and actual outbox proof do not close physical
owner gateway or selected-production restart acceptance; retain those for final
v2 cutover with the [todo handoff](operations.md#supervised-todo-setup).

`deploy/verify-agent-client` accepts an explicit installed-state directory for
that qualified boundary. `deploy/verify-containment` checks installed
owners/modes, `ProtectHome` and read-only worker access under the production
restrictions. source fixtures and artifact pins establish no installed-fleet pass.
contained cognition has its own prerequisite and qualification.

use the stopped one-main inventory and snapshot procedure before incompatible
changes. activation applies the current schema/contract checks above. reconcile
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

set `JARVIS_CODEX_HOST_CONFIG_PATH=/etc/jarvis/codex-host.json`. the schema-5
root-owned mapping names the personal endpoint, mode-02750 disposable cognition
parent and persistent notes checkout. main gets native workspace writes and
unrestricted network with approval denied, web disabled and no mcp. `.git` is its
only additional writable root. compactor/dreamer retain disposable empty read-only
directories and disabled native/network tools. no native authentication belongs
in jarvis state or environment. native commands have host account access and no
connector action/replay guarantees; inspect files/git after interruption.
main has no arbitrary elapsed cutoff or cumulative model/tool quota. per-operation
bounds, finite callback queues and owner stop still apply.

peer agent control uses the explicitly configured `JARVIS_AGENT_CLI_PATH` and
`JARVIS_AGENT_STATE_DIRECTORY`. skid owns installed auth/routing and refresh;
jarvis retains its personal machine/profile enums. the installed service reads
the enrolled development user's same live state through the qualified read-only
id-mapped mount. root manages that mount; application permissions remain narrow.
no copied client-json reader, second ref codec or fallback transport remains.

the target-release tools are agent.list/info/start/read/send/text/keys/stop/close/
wait/cancel_wait. addressed inputs use short `{machine,handle}`; current v11 accepts
only `t-` plus 16 lowercase hex digits. the host captures the original terminal
ref before action admission and retains it through delay/restart. terminal
loss/reassociation never silently renews that target. worker-native conversation
handles, history and controls are removed; native cognition and memory archive
access remain separate capabilities.

terminal send is guarded input for both providers. start accepts name, cwd, group,
literal optional stdin and native model/effort overrides. profiles retain
provider/account/executable defaults; qualified skid v0.24.4 lowers options only
for plain forwarding codex/claude commands. absent options preserve defaults;
unsupported forms refuse before creation. creation/input and interruption/closure facts remain
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

outside `jarvis.service`, cognitive operator commands `jarvis check-activation`,
`jarvis dream` and `jarvis rebuild-memory` (including `--node`) must run in
root-managed units with the existing application identity/private environment
and restrictions, `BindsTo=jarvis-codex-contained.service`,
`After=jarvis-codex-contained.service` and
`BindReadOnlyPaths=/run/jarvis-contained/exec/app-server.sock:/run/jarvis-contained/app-server.sock`.
the global endpoint is only a placeholder; these commands open the native
channel for catalog selection or isolated inference. capture/status/retry-only
commands do not open that runtime and need no native socket bind.
`install-contained-host` and `verify-containment` already give their verification
units this dependency and file bind. no additional wrapper or cli option is used.

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

use matching os and database identities for maintenance commands. ordinary
service stops are independent. select the owning service before stopping it.

| operation | stop and acquire | process and credentials |
| --- | --- | --- |
| `memory status` | neither | read-only status |
| `release-parked`, `dream`, `memory retry-compression`, `initialize-state`, `check-paused`, `cutover-native`, `check-activation`, `attachment-reconcile` | assistant | jarvis with runtime login. manual dream uses the online private search socket |
| `memory retry-capture SOURCE_CONVERSATION_UUID` | memory for external sources, assistant for jarvis projection | use the corresponding service's identity and login. revalidate the source under its key |
| schema/grants, declaration changes, authorized resets, `rebuild-memory [--node START+COUNT]` | both, assistant key then memory key | offline rebuild runs as jarvis with `embedding.env`. full rebuild also needs the migrator for reindexing |

the private unix socket is available to assistant jobs in group `jarvis-memory`.
the memory service owns the one embedding slot and search-rate limit. failure
after possible transmission retains paid-read uncertainty. while the memory
unit is down the assistant can still open committed originals locally.

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

[adr 0077](decisions/0077-production-acceptance-and-fresh-reset.md) and
[adr 0078](decisions/0078-fresh-corpus-first-acceptance.md) authorized the two
completed f2 resets. after calendar revisions reappeared, the owner authorized
[one stopped correction retaining the google cursors](decisions/0085-preserve-google-cursors-during-correction.md).
the owner retired that correction after the installed check reproduced replay.
the [f2 procedure](runtime-reliability-and-integration.md#e-fresh-history-resets)
owns its inventory, isolated proof and installed verification. ordinary
append-only guards continue to apply.
private recovery snapshots/manifests remain outside live memory; source cuts and
pending exports must be coordinated before writers resume.

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

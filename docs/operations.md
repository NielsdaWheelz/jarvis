# Production operations

Jarvis is one CPython 3.12.13-or-later process within the 3.12 series,
one PostgreSQL database, a separate contained native host, and one
configured Discord guild channel. It has no HTTP listener. Its maximum catalog
is the exact v1 catalog in SPEC 7.3. The selected Main plan contains thirteen
external/native reads and thirteen writes. Gmail send and shared, unknown-calendar, or
attendee-bearing Calendar writes use the host-owned approval path; the six Slice
5 writes retain their documented automatic cases. The isolated memory roles
receive only `memory.search` and `memory.open`, AutomaticWriteGate has an empty
plan, and scheduled-wake turns retain the original ten external reads without
Codex control. Run Jarvis as a
dedicated unprivileged OS user in UTC.

accepted target, not yet implemented: [universal memory](universal-memory.md) is
the single current implementation contract; [adr 0063](decisions/0063-simplify-memory-policy-and-retrieval.md)
records its latest simplification. use that contract for capture, background
memory recovery and cutover. the operations below otherwise describe the v1
baseline; main's effect recovery and paid-search barriers remain unchanged.

the target keeps one sharing declaration referenced by lanes and generates their
bearers, which remain stable until explicit rotation. complete events commit
atomically; oversized or conflicting history parks capture for repair, never
automatic truncation or checkpoint reset. background rememberer/dreamer runs may
repeat paid inference after interruption, within bounded retries and global
admission. their notes/bookmarks and summaries/pending flags commit atomically.
these rules do not weaken direct-note idempotency or main's durable recorder.

an admitted collector activates its native lane online only after obtaining a
complete inventory; receipt and conversation baselines commit atomically. there
is no activation file, manual activation command or jarvis stop. an incomplete
inventory may require a quiet native lane before retry. operator cli diagnostics
remain; the shared mcp has no status tool. search uses one shared client and gate
for all callers, with common policy values owned once in checked-in code and no
per-lane tuning or reranker provider/configuration.

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
Nexus production state is out of scope even though both systems are owned by the
same user.

the [2026-09-08 deployment report in git history](https://github.com/NielsdaWheelz/jarvis/blob/42f1fa21c3d2f687a3f3fafc9366fea41023e0cb/docs/qualification/2026-09-08-production-deployment.md)
records that release's housekeeping, host qualification and activation, not current
readiness. the [shared-cognition issue](issues/codex-private-process.md) records
the later stopped state; no completed seven-day owner acceptance is established.
The pending host reboot is explicitly deferred:
Jarvis does not require it, and a reboot would terminate the owner's current
tmux sessions and live Codex processes. V1 deliberately has no backup or restore
path and accepts possible total loss of local Jarvis state.

For every owner input, recall begins with exactly one kernel-dispatched
deterministic `memory.search` call and its typed observation. The isolated
recaller may then adaptively use `memory.search` and `memory.open`; operations
must not replace the initial kernel dispatch with a host-side repository read.

Jarvis names the requested-wake model tool and durable action
`schedule.wake`. Operational queries must use that exact value for
`action.tool_name`. The host-authored due input deliberately retains the
distinct protocol value `message.source = schedule_wake`; do not migrate or
rewrite that source value.

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
parent. the installed mapping is `/etc/jarvis/codex-host.json`.

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
needed. track completion in the [environment cutover issue](issues/connector-keyring-cutover.md).

The qualified Google client, connector-encryption, Maps, Brave, Discord, and
embedding settings remain host-owned and never enter model context or the Codex
child environment. `JARVIS_EMBEDDING_OPENAI_API_KEY` is the qualified OpenAI
project key restricted to embeddings. The deployment fixes
`text-embedding-3-small` at 1,536 dimensions. Changing either requires the
stopped rebuild procedure in SPEC 7.2.

Set `JARVIS_VERIFIED_OWNER_ONLY_CALENDAR_IDS` only to unique calendar IDs whose
live ACLs the operator verified as owner-only. Jarvis automatically executes
Calendar writes only for those IDs, without attendees or notification, after
AutomaticWriteGate allows the current owner request. Every other case requires
Approve or Deny.

The production deployment exists. Install the exact committed release without
activating it, then, with the service stopped and owner-paused, migrate in a
systemd one-shot that injects the root-only environment after changing to the
`jarvis` identity, select the release and start it:

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

release/contained-host installation, activation and pruning share
`/opt/jarvis/.deploy.lock`. retain only the
selected release and one temporary installation candidate; rebuild any discarded
release from its exact commit. pruning checks both the running jarvis process and
the contained host's loaded `ExecStart`. if that host still selects another
release, cleanup refuses before deleting files. cleanly stop or install the host
for the retained release before retrying; no extra rollback release is retained.

`activate-release FULL_GIT_COMMIT` never stops jarvis. it requires an installed
release, regular root-owned environment files and a cleanly stopped service
(`ActiveState=inactive`, `Result=success`, `MainPID=0`). it migrates the stopped
database, runs the target's `cutover-native`, then read-only `check-activation`
under the existing deployment lock. missing legacy files are correct after this
cut; the scripts do not require or recreate them.
before migration, activation requires the contained unit active and the selected
release's read-only host qualifier to pass, including exact loaded release,
stock version and startup catalogue. host installation remains a separate
explicit stopped-application operation.

cutover validates original entered work before converting proven unentered
legacy authority. pending approvals receive fresh consent; queued writes re-enter
the current gate. unknown effects or paid reads refuse cutover. canonical pause
lives in postgres. `check-activation` rejects incompatible unfinished authority,
entered uncertainty and stale active contracts; deliverable historical resolutions
and known terminal facts remain readable by paused startup. it does not require
an empty outbox. the target then installs its unit, selects the immutable release
and starts paused. ingress and outbox recovery precede an explicit owner resume.

for a fresh database, migrate and run `jarvis initialize-state` once under the
runtime identity/environment. this creates canonical paused state, with no
provider call or action. repeated initialization refuses rather than resetting
existing requests. activation uses the same pause check. never edit database
request rows or synthesize an empty execution journal to bypass a failed check.

`verify-containment` runs after activation without printing secret values. It
proves the three environment files are root-owned mode 0600 and unreadable by
the service identity, verifies the active systemd `/proc` and core-dump
controls, and confirms a same-identity process cannot read the non-dumpable
Jarvis parent environment before accepting the deployment. It tolerates only
the bounded service-start interval before Python establishes that process-local
control; no provider connection is opened before the control succeeds. the
service then receives the non-secret cognition profile/socket view and the
private skid client file. it receives no provider account-home access.
`deploy/verify-containment` checks the root cli and mode-0600 jarvis-owned client
and reads all three peers under the real identity and relevant service restrictions;
an unreachable host fails it. full gateway bearers replace ssh command allowlists,
an accepted cost rather than a new credential-scope boundary.

Do not activate an older release across an incompatible migration. A
same-schema rollback requires rebuilding with `deploy/install-release <commit>`
from the clean maintained checkout, then `deploy/activate-release <commit>` only
after the service is stopped, and only
to a release that carries `check-activation`; older releases are refused, not
skipped. That release's check then judges each unfinished action against its
own plan.

ADR 0035 rotates the AutomaticWriteGate fingerprint and therefore every Write
binding policy that commits to it. Before this cutover, prove the production
action ledger contains no `queued`, `awaiting_approval`, or `executing` row made
under the predecessor identity. A terminal historical action remains evidence
and is never rewritten.

## native cutover

pause the existing owner task, reconcile entered effects and paid reads, and stop
the service cleanly. preserve a local pre-cutover database/state copy. install the
qualified target and separate contained host, then activate as above. an entered
unknown action cannot be made safe by stopping its reasoning or deleting its
record. main's original requests, action receipts and historical observations
remain canonical throughout cutover.

migration 0005 creates the native request/attempt/invocation tables. the stopped
`cutover-native` command imports the old deployment pause, cancels only proven
unentered legacy authority and removes the replaced local session/pause/admission
files. no new acceptance evidence is invented for old records. a partial or
unresolved legacy state refuses and stays stopped.

## admission journal cutover

historical: adr 0047's rolling-capacity journal and transitional normalizer are
retired by the native cutover. do not install the normalizer or recreate
`admission.json`. native admission uses current ownership, not cumulative usage
reservations. isolated roles retain their actual operation limits.

## herdr cutover (pr 4)

historical; superseded by [the skid-only cutover](#skid-only-worker-cutover).
adr 0048 and its recorded qualification retain the historical decision.

## herdr gate cutover (pr 5)

historical; superseded by [the skid-only cutover](#skid-only-worker-cutover).
adr 0049 retains historical evidence; its ssh gate must not be installed again.

## skid-only worker cutover

[adr 0052](decisions/0052-cut-worker-control-to-current-skid.md) changes the entire
main catalog/plan. stage source and private inputs before activation. the accepted native cutover adds the separate contained cognition endpoint.
worker source and herdr retirement do not qualify that endpoint or production
activation. actual deployment remains separately authorized and verified.

1. use the existing owner pause control. old code must settle or explicitly
   reconcile every nonterminal action, finish or park unfinished turns, materialize
   required action resolutions, and drain their processing and delivery. discard
   permission applies only to herdr workers, never unrelated actions or approvals.
2. cooperatively stop jarvis. require systemd ActiveState=inactive, Result=success,
   MainPID=0 and canonical postgres pause. a failed or
   killed stop needs operator inspection; activation never stops the service.
3. stage the admitted devbox skid artifact through dev-server; its root cli and
   gateway share artifact/pin. changing either cli bytes or client configuration
   requires the pause and clean stop before switching; identical apply is inert.
4. supply the existing human-provisioned, three-peer private file explicitly:

   ```sh
   JARVIS_SOURCE_AGENT_CLIENT_CONFIG=/absolute/private/client.json deploy/install-agent-client
   ```

   the worker installer copies a mode-0600 candidate under /etc/jarvis and validates it
   through the installed skid cli under the service's relevant restrictions.
   partial inventory proves config admission only. invalid config leaves the
   installed file unchanged. identical apply is inert only for a regular,
   non-symlink, jarvis:jarvis mode-0600 file. replacement is atomic and requires
   the prepared pause/clean-stop checks;
   a symlink is replaced, while an existing directory is refused and preserved.
   no bearer minting or peer table.
   `deploy/install-private-state` composes this step when all application and
   connector private state also needs installation. `deploy/verify-agent-client`
   qualifies all three peers as the service identity while jarvis is stopped;
   it does not require cognition to be running.
5. `deploy/activate-release COMMIT` migrates, runs stopped native cutover and
   checks compatibility under the deployment lock. incompatible active authority
   and entered uncertainty refuse. known historical terminal resolutions and new
   native approvals remain deliverable by paused startup. finalized old worker
   rows remain opaque archives; no legacy decoder or replay exists.
6. before an explicitly requested resume, run `deploy/verify-containment`. it
   checks regular-file owners/modes, ProtectHome and each production gateway via
   read-only skid list as jarvis under the restrictions governing file access and
   tls. an unavailable host fails; absent cognition remains a separate prerequisite
   for starting jarvis. no service/fleet pass follows from source or an artifact pin.

rollback retains private code/config/artifact inputs while stopped. after herdr
worker discard, rollback cannot restore their running state. repair compatible
skid/jarvis state or leave jarvis down; never replay unknown effects or resurrect
the ssh adapter. credentials, terminal content and provider history stay private.

for v7, paired code/config/artifact rollback before new receipts follows ordinary
stopped checks. selected-only retention under adr 0053 requires rebuilding any
discarded jarvis release from its exact commit. after new canonical receipts,
older readers are unqualified: pause and retain
records for forward repair. whole-state restore must account for new data and
external effects; code rollback alone is not data rollback. never add a legacy
reader or erase new actions merely to make rollback start.

## Approval operation

Approval is available only while `jarvis serve` owns the deployment. A current
owner request first passes AutomaticWriteGate. Host policy then renders the
validated Gmail send or approval-required Calendar arguments, atomically stores
the `awaiting_approval` action plus its assistant outbox row, and durably
suspends the model turn. No provider session or worker remains blocked while
waiting.

Every approval is delivered with one host-generated UTF-8 text attachment. The
attachment is the complete deterministic JSON payload and is bounded to 1,000,000
bytes. Inspect it in full; the short message's only components are Approve and
Deny. The attachment includes all To/Cc/Bcc recipients, subject, and complete
email body, or every Calendar writable value. Free-form replies such as `yes`,
`approve`, or `send it` never decide the action.

Only the configured owner may click in the configured guild/channel. Jarvis
checks the component's action and internal-message IDs, the live Discord message
ID, and current action state. It atomically records the decision, acknowledges
by disabling both components, and only then enters slow execution. Deny records
`cancelled` and performs no external operation. Approval messages are
host-owned; never edit them or decide an action directly in PostgreSQL.

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
exhaustion with incomplete evidence and yields safe terminal uncertainty plus an
owner-inspection request.

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

main retains a compatible live native thread until it ends, is stopped or loses
its connection/owner. connection loss fences old callbacks, then restarts reasoning
from canonical requests and durable results in a fresh thread. recorded effects
remain authoritative; unresolved action/read outcomes retain their barriers.
provider history is disposable. a sealed original terminal is settled locally
before current model/plan reconstruction, with current request/publication fences.

set `JARVIS_CODEX_HOST_CONFIG_PATH=/etc/jarvis/codex-host.json`. the schema-4
root-owned mapping names only the contained personal endpoint and the mode-02750
cognition parent. no native authentication belongs in jarvis state or environment.
main has no arbitrary elapsed cutoff or cumulative model/tool quota. per-operation
bounds, finite callback queues and owner stop still apply.

peer agent control uses `/usr/local/libexec/skidbladnir` (regular root:root 0755)
and `/etc/jarvis/agent-client.json` (regular jarvis:jarvis 0600), configured by
`JARVIS_AGENT_CLI_PATH` and `JARVIS_AGENT_CLIENT_CONFIG_PATH`. all three existing
peers come from human fleet provisioning. no development-home symlink,
JARVIS_HERDR setting, jarvis ref codec or provider-home table remains.

the target-release tools are agent.list/info/start/read/send/text/keys/stop/close/
wait/cancel_wait. addressed inputs use short `{machine,handle}`; t-handles select
terminal mechanisms, c-handles explicit native capabilities. the host captures
original refs before gate/action admission and retains them through delay/restart.
native capture preserves the original target separately from observation and
optional observedRef. matching optional name/profile facts provide consent context;
terminal loss/reassociation never renews native authority.

terminal send is guarded input for both providers; native claude input remains
unavailable. start options use explicit overrides then native defaults, with
literal optional stdin. creation/input and interruption/closure facts remain
independent, including nonzero partial results. native accepted means admitted,
terminal written means dispatched; neither proves completion. unknown writes
enter once and never replay; conclusive owned receipts settle without re-entry.

wait registration returns watching immediately; a separate durable outcome/event
observes the original ref outside main's mutex. cancellation stops observation,
not execution. a matched state and later bounded text are separate evidence.
unmixed wait-only observations may stay internal. after the original owner turn
closes, worker events confer reading/integration/notification only; new writes or
wait registration need new current owner authority. broader follow-through is
separate. partial inventory, unavailable/truncated text and lost receipts remain
material limits. old finalized worker rows retain only recorded status and opaque
receipt details; their raw records remain unchanged.

activate only through [the skid-only cutover](#skid-only-worker-cutover). this
worker change reuses the existing action scheduler and adds no history store,
provider client or cognition lane. the active plan and paired spec distinguish
passed local acceptance from remaining installed-fleet/production qualification;
the latter must pass before claiming this target release activated.

`gpt-5.4` is deliberately rejected during configuration because OpenAI retired
it from ChatGPT-authenticated Codex on 2026-08-31. The negative final-code probe
that exposed that retirement is preserved in ADR 0028; do not retry it as a
supported route or switch Jarvis to API-key authentication.

## memory maintenance

the [current dreamer contract](universal-memory.md#daily-dreaming) selects pending
notes, not a date window. manual dreaming performs one bounded batch and reports
the backlog; no pending notes skips provider i/o. stopped rebuild atomically wipes
summaries and rearms notes before one bounded pass. disposable inference leaves
no journal or unknown-paid-call barrier to clear. later daily sweeps drain the
remainder. the command descriptions below record the v1 baseline and retain their
stopped-service rule.

Run one manual dream only while the service is stopped. It takes the deployment
lock, skips provider I/O when raw memory is empty, and prints counts only:

```sh
uv run jarvis dream
```

The process-local timer defaults to 86,400 seconds and does not run immediately
at startup. `JARVIS_DREAM_INTERVAL_SECONDS` may set a value of at least 60
seconds; production should retain the 24-hour default. The timer can drift or
miss intervals across downtime, and foreground owner work preempts Dreamer
reasoning while an already-started summary transaction finishes atomically.

Run the complete derived-memory rebuild only while the service is stopped:

```sh
uv run jarvis rebuild-memory
```

The command takes the deployment lock, atomically deletes summaries and clears
every vector, proves raw lexical recall, re-embeds raw rows, runs exactly one
Dreamer pass, and embeds regenerated summaries. It never starts the service.
Failure exits nonzero; inspect and retain its private journal, keep the service
stopped, and rerun from immutable raw memory after correcting the cause.

these structural/raw checks remain runtime safeguards. recall-quality scoring
and its former release gate are suspended under adr 0046; a successful rebuild
does not prove recall quality.

Migrations own application objects and grant only the required DML to
`jarvis_runtime`. That role cannot delete or truncate `memory_log`, cannot
update its canonical columns, and can update only the derived `embedding`.
The append-only trigger remains enabled as defense in depth against accidental
owner-side mutation.

## Restart and recovery

Startup first reconciles every queued or executing action whose original turn
cannot safely resume. Each exact current binding and immutable execution
contract must still match. Provider reads never increment executor entries;
re-execution occurs only after tool-specific evidence proves absence and safety
and both immutable ceilings still permit it. Unresolved evidence becomes
terminal `uncertain`; receipt-backed scheduled wakes resume their local
lifecycle and never become uncertain. Missing action-resolution inputs are
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
After foreground work yields, the background worker boundedly retries completed,
unremembered owner groups and null embeddings. It groups normal rows by their
shared settlement identity and falls back to one owner row only when old or
damaged trace cannot establish a group. background work waits for the serial
lane and requires its current-owner permit; no capacity-reset timer exists.
host action-resolution and scheduled-wake rows are never memory-work targets.
isolated roles retain finite invocation/tool bounds; main has no cumulative
model/tool quota or arbitrary elapsed cutoff.

An undelivered approval outbox row remains pending with null
`source_message_id`; startup rerenders it from the action and reuses the same
enforced nonce. A delivered `awaiting_approval` row remains safely clickable
after restart because the component contains durable action/internal-message
identity and the Gateway revalidates the stored Discord message relationship.
Startup cancels and reports a pending action whose renderer, arguments,
draft-creation basis, or execution contract is no longer compatible. It first
disables an already-delivered approval. An undelivered one is cancelled without
a Discord edit, then its canonical outbox row delivers once with a complete
cancelled-payload attachment and disabled Approve and Deny before the ordinary
cancellation resolution. No delivery ID is invented and no functional component
is shown.

If Approve committed but the process stopped before executor entry, the action
remains `executing` with zero attempts. Startup first disables the known Discord
components through the narrow REST binding, then resumes that occupied action;
the executor increments `attempts` only at its actual entry. A later
interruption uses the complete tool-specific reconciliation path before any
evidence-proven repeat. Denial and every terminal approval result use the
ordinary idempotent action-resolution row and visible model or deterministic
fallback.
Successful outbox delivery drains every current batch. A row that exhausts its
finite delivery retry schedule remains pending and stops that drain; the next
startup or ingress signal retries it with the same persisted UUID and nonce.
Catch-up selects Discord's newest bounded page after the canonical owner cursor,
then persists eligible owner messages in chronological order. If downtime
traffic exceeds that bound, the oldest overflow is intentionally skipped; this
prevents a full page of bot or non-owner traffic from permanently hiding a later
owner message without adding non-canonical cursor state.

`stop` and `pause` are exact, case-insensitive owner messages handled by the
host. `resume` clears the durable pause. Ordinary process termination cannot
undo an external effect; Jarvis reconciles effectful action rows before any
repeat.

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
this section otherwise records the v1 baseline.

V1 has no backup, restore command, Restic repository, R2 credential, backup
database role, or backup timer. There is no `jarvis-restic-password`; do not
invent or provision one. Loss or unrecoverable corruption of the devbox, its
disk, or the Jarvis database can permanently lose conversation, memory, action,
and runtime state. This is an explicit one-user-prototype trade-off. Add backup
as a later slice when retained production state justifies its operational and
qualification cost; doing so does not require changing the nine application
tables.

Ordinary logs contain event types, bounded IDs, counts, and reason codes
only—not messages, prompts, memory text, tool payloads, tokens, or credentials.

Raw memory is permanent and grows without a deletion path in v1. Embeddings and
full-text indexes are derived and can be rebuilt while the local raw log exists.
Embedding ingestion, rebuilds, and semantic search queries disclose their input
text to the metered embedding processor. An embedding outage leaves new vectors
null; lexical recall remains available and the bounded backfill retries later.

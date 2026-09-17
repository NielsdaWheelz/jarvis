# Production operations

Jarvis is one CPython 3.12.13-or-later process within the 3.12 series,
one PostgreSQL database, and one
configured Discord guild channel. It has no HTTP listener. Its maximum catalog
is the exact v1 catalog in SPEC 7.3. The selected Main plan contains thirteen
external/native reads and thirteen writes. Gmail send and shared, unknown-calendar, or
attendee-bearing Calendar writes use the host-owned approval path; the six Slice
5 writes retain their documented automatic cases. The isolated memory roles
receive only `memory.search` and `memory.open`, AutomaticWriteGate has an empty
plan, and scheduled-wake turns retain the original ten external reads without
Codex control. Run Jarvis as a
dedicated unprivileged OS user in UTC.

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

The dated [production deployment report](qualification/2026-09-08-production-deployment.md)
records the completed exact-target housekeeping, UTC convergence, installed
PostgreSQL/pgvector qualification, containment correction, and activation. The
seven-day owner acceptance period remains in progress. The pending host reboot is explicitly deferred:
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

That host convergence must also report one active operational `codex.runtime`
identity, three healthy profile sockets, the installed skid cli/client config, and
the mode-02750 empty cognition parent. A differing active identity is an
operator drain/restart action, never an ordinary-apply restart. Before the hard
cut, stop Jarvis, drain every non-terminal Codex control action and old private
provider session, then activate the shared services without killing manual tmux
sessions or deleting native history.

Native Codex tracks latest stable during explicit host install/update (ADR 0042).
the closed host mapping must be schema 3, retaining cognition fields and dropping
`tmux`, `launcher_socket`, and profile `work_roots`; deploy it with this consumer.
version-only apply leaves
healthy servers running; normal crash recovery may load the newer binary.
Record the installed CLI and each running server
separately when qualifying; a config value is not observed runtime evidence.
Planned shared-service restart requires an explicit operator decision and may
interrupt turns. Upstream incompatibility fails closed until repaired; there is
no version allowlist, automatic restart, or private fallback.

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
three development-user account homes; never copy either into Jarvis state.

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

Install the exact committed release without activating it, then atomically run
migrations and initialization in systemd one-shots that inject the root-only
environment after changing to the `jarvis` identity. Finally select the release
and enable the service:

```sh
deploy/install-release
deploy/activate-release "$(git rev-parse HEAD)"
deploy/verify-containment
```

`install-release` archives only tracked `HEAD`, installs the exact
`.python-version` interpreter inside the release, and builds with `uv sync
--frozen --no-dev --no-editable --link-mode copy`. After root-owning the tree,
it verifies the release-contained interpreter, dependency identity and CLI as
the actual `jarvis` service identity before recording the commit/tree/lock
digest and installing the inactive service unit. Rechecking an existing receipt
also requires that service-identity proof; an unusable release is rejected, not
repaired in place. Each release carries its own interpreter/package bytes:
additional disk use buys independence from private account homes and writable
builder caches. It refuses tracked changes. `activate-release` requires
both split database credentials, migrates as `jarvis_migrator`, initializes
content-free runtime state once, atomically changes `/opt/jarvis/current`, and
starts the service. A PostgreSQL advisory lock makes a second process fail
rather than overlap.

`verify-containment` runs after activation without printing secret values. It
proves the three environment files are root-owned mode 0600 and unreadable by
the service identity, verifies the active systemd `/proc` and core-dump
controls, and confirms a same-identity process cannot read the non-dumpable
Jarvis parent environment before accepting the deployment. It tolerates only
the bounded service-start interval before Python establishes that process-local
control; no provider connection is opened before the control succeeds. The
service then receives the non-secret cognition profile/socket view and its private
skid peer configuration;
it receives no Codex credential or development-user account-home access.

Do not activate an older release across an incompatible migration or a
non-terminal action contract. A same-schema rollback may select an already
installed release through `deploy/activate-release <commit>` only after the
service is stopped and the action ledger is inspected.

ADR 0035 rotates the AutomaticWriteGate fingerprint and therefore every Write
binding policy that commits to it. Before this cutover, prove the production
action ledger contains no `queued`, `awaiting_approval`, or `executing` row made
under the predecessor identity. A terminal historical action remains evidence
and is never rewritten.

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

[adr 0046](decisions/0046-reset-testing.md) removes the test suites, fixtures,
evaluation corpus, and qualification harnesses. their execution gates are
suspended pending the [testing redesign](issues/testing-redesign.md). dated
qualification reports remain historical evidence for their recorded revisions;
static and build success does not establish current behavioral qualification.

## shared runtime and fleet control

Main retains its compatible native thread across owner requests and process
restarts; Codex owns automatic compaction (ADR 0043). Jarvis does not expire
references by generation or estimate retained history from billing counters.
Per-request and rolling budgets still apply. An oversized continuation can fail
at the native context boundary; existing failure/reconstruction handling does
not authorize replay of an unknown paid decision or effect.

set `JARVIS_CODEX_HOST_CONFIG_PATH=/etc/codex-shared/profiles.json`; that root-owned
mapping must name the running shared services and exact mode-02750 cognition
parent. never copy Codex authentication into the checkout or process environment,
and never start a private app server for jarvis.

peer agent control requires the installed skid cli and a private mode-0600 peer
configuration readable by jarvis. the fleet operator distributes the configured
hosts' existing bearers; provider credentials remain on their hosts. refresh
these copies after bearer rotation. there is no fleet hub or credential daemon.

before activating the nine-tool catalog, drain non-terminal agent actions bound
to the previous tool implementation. stage matching skid and jarvis releases,
then switch callers together. no old grammar/target compatibility mode remains.
preserve native cognition, busy provider services, canonical action history and
private peer configuration; no provider restart is needed for worker-interface work.

jarvis uses list/info to resolve owner requests naming a session. the gate sees
name/machine metadata from one bounded info call and the original ref. metadata
failure prevents mutation; info's refreshed ref cannot replace the originally
submitted effect target. unknown writes are never repeated. phone grouping is
removed by the coordinated skid cutover, not by jarvis cleanup.

the service retains `JARVIS_AGENT_CLI_PATH=/usr/local/libexec/skidbladnir` and
`JARVIS_AGENT_CLIENT_CONFIG_PATH=/etc/jarvis/agent-client.json`. it invokes ordinary
commands with `--config` and `--json`; send text goes to `--stdin`. the executable's
administrative basename is unchanged. nine worker tools share the existing 19-call
run allowance; this release changes neither admission journals nor kernel budgets.

`gpt-5.4` is deliberately rejected during configuration because OpenAI retired
it from ChatGPT-authenticated Codex on 2026-08-31. The negative final-code probe
that exposed that retirement is preserved in ADR 0028; do not retry it as a
supported route or switch Jarvis to API-key authentication.

## memory maintenance

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

Startup then performs bounded Discord catch-up, retries persisted assistant rows
whose `source_message_id` is null, releases orphaned admission concurrency
without refunding its rolling charge, and scans unprocessed, unparked waking
rows. A compatible main-session reference is resumed. A missing, incompatible,
or invalid provider session cold-bootstraps from canonical message history.
After foreground work yields, the background worker boundedly retries completed,
unremembered owner groups and null embeddings. It groups normal rows by their
shared settlement identity and falls back to one owner row only when old or
damaged trace cannot establish a group. Background admission delay is silent;
the service schedules the next capacity reset rather than requiring new owner
traffic. Host action-resolution and scheduled-wake rows are never memory-work
targets.

Production rolling admission holds two complete worst-case foreground
envelopes plus one Rememberer allowance in each six-hour window. This lets one
full reservation coexist with up to one foreground envelope of already-settled
actual use. The all-calendar release recognizes only its exact preceding Slice
6 envelope and atomically enlarges retained foreground reservations by one
isolated write-gate allowance while the service is stopped. An already-current
journal is unchanged. Every other changed configuration fails closed; preserve
it for diagnosis rather than guessing or deleting capacity evidence.

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

The production service is now always-on. Final v1 sign-off remains separate
until the owner completes the seven-day personal acceptance criteria.

If a configuration defect parks input, first stop the service and correct the
defect. Then clear only the reviewed UUIDs while the command owns the deployment
lock:

```sh
jarvis release-parked MESSAGE_ID [MESSAGE_ID ...]
```

This does not reset `processing_attempts` and does not arm hidden successor
work. Never edit `trace` to control scheduling.

If the admission journal is missing, corrupt, or has a changed configuration,
Jarvis fails closed. With the service stopped, preserve the bad journal for
diagnosis, verify that no cognitive process owns the deployment, and explicitly
replace only `admission.json` with a freshly initialized journal using the same
checked-in limits. Do not delete the session reference, pause state, or database
rows as part of that repair.

## Data durability and logs

V1 has no backup, restore command, Restic repository, R2 credential, backup
database role, or backup timer. There is no `jarvis-restic-password`; do not
invent or provision one. Loss or unrecoverable corruption of the devbox, its
disk, or the Jarvis database can permanently lose conversation, memory, action,
and runtime state. This is an explicit one-user-prototype trade-off. Add backup
as a later slice when retained production state justifies its operational and
qualification cost; doing so does not require changing the six application
tables.

Ordinary logs contain event types, bounded IDs, counts, and reason codes
only—not messages, prompts, memory text, tool payloads, tokens, or credentials.

Raw memory is permanent and grows without a deletion path in v1. Embeddings and
full-text indexes are derived and can be rebuilt while the local raw log exists.
Embedding ingestion, rebuilds, and semantic search queries disclose their input
text to the metered embedding processor. An embedding outage leaves new vectors
null; lexical recall remains available and the bounded backfill retries later.

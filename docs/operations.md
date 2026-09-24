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
identity, three healthy profile sockets, jarvis's herdr gate directory
`/etc/jarvis-herdr`, and the mode-02750 empty cognition parent. A differing active identity is an
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

for an existing deployment, complete the
[admission journal cutover](#admission-journal-cutover) before activation. the
herdr catalog switch followed the [herdr cutover](#herdr-cutover-pr-4) runbook; the
herdr gate switch follows the [herdr gate cutover](#herdr-gate-cutover-pr-5).

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
digest. It never writes the global service unit. Rechecking an existing receipt
also requires that service-identity proof; an unusable release is rejected, not
repaired in place. Each release carries its own interpreter/package bytes:
additional disk use buys independence from private account homes and writable
builder caches. It refuses tracked changes.

`activate-release FULL_GIT_COMMIT` never stops Jarvis. It refuses, each with its
own line, unless the release is installed, the three environment files exist and
are not symlinks, `jarvis.service` shows `ActiveState=inactive`,
`Result=success` and `MainPID=0`, `paused.json` reads exactly `{"paused": true,
"schema_version": "jarvis-paused.v1"}`, and `admission.json` exists. It never
initializes state. It then runs the target release's `jarvis check-activation`
in a one-shot unit with `database-runtime.env`, `jarvis.env` and the
`codex-clients` group, under the deployment lock and before migration. The check
composes the target release's main plan exactly as `serve` does, from the live
Codex model catalog, so a stopped Codex app-server blocks activation. It writes
nothing. It classifies every `queued`, `awaiting_approval` and `executing`
action and prints one content-free line per row, `action <id> <status> <tool>
<verdict>`, then `activation check: compatible=N incompatible=N in_flight=N`.
An `executing` row is `in_flight`, whether entered, a claimed reminder, or
approved but not entered. Any other row is `compatible` only when the target
release loads it, its stored execution contract matches the target plan, a
pending approval still renders, and a Gmail send still has its Jarvis draft
basis; otherwise it is `incompatible` with `does_not_load`, `binding`, `render`
or `gmail_basis`. Any `in_flight` or `incompatible` row, a deployment lock held
by another process (`another jarvis process owns the deployment`), or a failed
check refuses with `activation check did not pass; leave service stopped`.
There is no override, cancellation, restamping or replay: compatible rows stay
untouched for startup recovery, which revalidates them. A verdict holds only
while the Codex catalog row and the environment stay unchanged; if either
changes before `serve` starts, startup recovery's own validation runs and may
cancel. A release that predates `check-activation` fails the one-shot and is
refused, not skipped. A release that changes the `action` schema activates only
with no unfinished actions, because the check runs before migration and every
row then fails to load and the check fails. Decisions and read positions are not
inspected. It then
migrates as `jarvis_migrator`, installs the
selected release's own `deploy/jarvis.service` and reloads systemd, atomically
changes `/opt/jarvis/current` and starts the service, which starts paused. A killed, crashed or timed-out stop is refused with
`jarvis.service did not stop cleanly`; inspect it, then run `sudo systemctl
reset-failed jarvis.service` explicitly before activating. A PostgreSQL advisory
lock makes a second process fail rather than overlap.

a fresh deployment is a separate manual procedure outside `activate-release`:
after migration, run `jarvis initialize-state` once in the same systemd one-shot
shape with `database-runtime.env` and `jarvis.env`, then install the unit, select
the release and start it by hand. initialized state is unpaused, which
`activate-release` rejects by design.

`verify-containment` runs after activation without printing secret values. It
proves the three environment files are root-owned mode 0600 and unreadable by
the service identity, verifies the active systemd `/proc` and core-dump
controls, and confirms a same-identity process cannot read the non-dumpable
Jarvis parent environment before accepting the deployment. It tolerates only
the bounded service-start interval before Python establishes that process-local
control; no provider connection is opened before the control succeeds. The
service then receives the non-secret cognition profile/socket view and its herdr
gate key and ssh configuration; it receives no Codex credential or
development-user account-home access. the script also checks
`/etc/jarvis-herdr` (directory root:jarvis 0750, `id_ed25519` jarvis 0600,
`ssh_config` and `known_hosts` root:jarvis 0640) and, as jarvis, that each of
devbox, macbook and arch answers `agent list` through its gate and refuses
`status --json` with exactly `herdr-gate: command refused`; an unreachable host
fails it.

Do not activate an older release across an incompatible migration. A
same-schema rollback may select an already installed release through
`deploy/activate-release <commit>` only after the service is stopped, and only
to a release that carries `check-activation`; older releases are refused, not
skipped. That release's check then judges each unfinished action against its
own plan.

ADR 0035 rotates the AutomaticWriteGate fingerprint and therefore every Write
binding policy that commits to it. Before this cutover, prove the production
action ledger contains no `queued`, `awaiting_approval`, or `executing` row made
under the predecessor identity. A terminal historical action remains evidence
and is never rewritten.

## admission journal cutover

startup and manual dreaming accept only the current admission configuration
under [adr 0047](decisions/0047-require-current-admission-journals.md). before
activating this cut, validate or normalize the stopped deployment's journal
through release `51f62c86322a66224d1576395b5795ae823c1f75`.

if absent, install that exact commit with `deploy/install-release` from a clean
checkout of it. that commit's installer also overwrites the global service unit;
it does not select the release or start it, and target activation reinstalls the
target's unit. never activate the transitional release or run its service or
dream command.

run the following on the deployment host through an operator allowed to use
sudo. it reads only the configured database url, runtime directory and batch
size; keep those settings unchanged through target activation. the existing
normalizer preserves identities and expiry, enlarges predecessor reservations
conservatively, and leaves settled actual usage intact. orphan recovery releases
only live slots; ordinary rolling-window expiry still applies. no provider or
connector is constructed.

```sh
prior_release=/opt/jarvis/releases/51f62c86322a66224d1576395b5795ae823c1f75
sudo test -f "$prior_release/RELEASE.json" &&
sudo systemctl stop jarvis.service &&
sudo systemd-run --quiet --wait --pipe --collect \
  --unit=jarvis-admission-cutover \
  --property=Type=oneshot \
  --property=User=jarvis \
  --property=Group=jarvis \
  --property="WorkingDirectory=$prior_release" \
  --property=EnvironmentFile=/etc/jarvis/database-runtime.env \
  --property=EnvironmentFile=/etc/jarvis/jarvis.env \
  "$prior_release/.venv/bin/python" - <<'PY'
import asyncio
import os
from pathlib import Path

from jarvis.admission import (
    RollingAdmissionPort,
    current_admission_limits,
    pre_agent_control_slice6_admission_limits,
    pre_all_calendar_slice6_admission_limits,
    slice5_admission_limits,
)
from jarvis.db import create_engine
from jarvis.ownership import deployment_ownership
from jarvis.process_security import deny_same_identity_process_inspection


async def prepare():
    deny_same_identity_process_inspection()
    directory = Path(os.environ["JARVIS_RUNTIME_STATE_DIRECTORY"])
    batch = int(os.environ.get("JARVIS_MAXIMUM_BATCH_SIZE", "20"))
    if not directory.is_absolute() or not 1 <= batch <= 100:
        raise ValueError("invalid admission configuration")
    path = directory / "admission.json"
    limits = current_admission_limits(batch)
    engine = create_engine(os.environ["JARVIS_DATABASE_URL"])
    try:
        async with deployment_ownership(engine):
            RollingAdmissionPort.migrate_limits(
                path,
                previous=(
                    pre_agent_control_slice6_admission_limits(batch),
                    pre_all_calendar_slice6_admission_limits(batch),
                    slice5_admission_limits(batch),
                ),
                current=limits,
            )
            await RollingAdmissionPort(path, limits).recover_orphans()
    finally:
        await engine.dispose()


try:
    asyncio.run(prepare())
except Exception:
    raise SystemExit("admission preparation failed; leave service stopped") from None
print("admission journal current; orphan slots released without refund")
PY
```

continue with target activation only after success. an unknown, missing or corrupt
journal leaves the service stopped for investigation. do not reset, delete or
replace it with an empty journal to bypass this prerequisite. repository checks
and synthetic fixtures do not establish that the private deployment journal is
ready; the outstanding deployment work is tracked in
[admission journal cutover](issues/admission-journal-cutover.md).

after successful preparation, install the target release normally;
`deploy/activate-release` installs the selected release's unit and reloads
systemd.

## herdr cutover (pr 4)

this switch activates the herdr-aligned catalog of
[adr 0048](decisions/0048-align-with-the-herdr-fleet-cli.md). the changed catalog
rotates the shared plan and the gate fingerprint participates in every write
binding, so every nonterminal action is incompatible, not only agent actions. no
old grammar or target compatibility mode remains. run the steps in order. a
failed step leaves jarvis on the old release or stopped for repair; nothing
retries.

step 1. while the old release runs, take a read-only inventory. `serve` holds the
deployment lock, so this one-shot takes no lock and prints counts only:

```sh
sudo systemd-run --quiet --wait --pipe --collect \
  --unit=jarvis-cutover-inventory \
  --property=Type=oneshot \
  --property=User=jarvis \
  --property=Group=jarvis \
  --property=WorkingDirectory=/opt/jarvis/current \
  --property=EnvironmentFile=/etc/jarvis/database-runtime.env \
  /opt/jarvis/current/.venv/bin/python - <<'PY'
import os

from sqlalchemy import create_engine, text

from jarvis.db import normalize_database_url
from jarvis.process_security import deny_same_identity_process_inspection

PENDING = "status in ('queued', 'awaiting_approval', 'executing')"
QUERIES = (
    ("actions", f"select status, count(*) from action where {PENDING} group by 1"),
    (
        "action kinds",
        "select tool_name || ':' || status, count(*) from action "
        f"where {PENDING} group by 1",
    ),
    (
        "input",
        "select case when processing_parked_at is null then 'waking' "
        "else 'parked' end, count(*) from message "
        "where role in ('owner', 'host') and processed_at is null group by 1",
    ),
    (
        "decisions",
        "select case when d.terminal is null then 'open' "
        "else 'completed_unsettled' end, count(*) from model_decision d "
        "left join message m on m.id = d.first_input_id "
        "where d.terminal is null "
        "or (d.first_input_id is not null and m.processed_at is null) group by 1",
    ),
    (
        "reads",
        "select state, count(*) from read_position "
        "where state <> 'completed' group by 1",
    ),
)

deny_same_identity_process_inspection()
engine = create_engine(normalize_database_url(os.environ["JARVIS_DATABASE_URL"]))
try:
    with engine.connect() as connection:
        for label, query in QUERIES:
            rows = sorted(connection.execute(text(query)).all())
            print(label, " ".join(f"{key}={count}" for key, count in rows) or "none")
finally:
    engine.dispose()
PY
```

`actions` and `action kinds` exhaust the status query, including mail and
calendar approvals and receipt-backed `schedule.wake` reminders that startup
recovery selectors omit. nonzero counts hold activation. finish or reconcile
each action, or obtain the owner's explicit denial or cancellation through the
existing operations, then rerun the inventory. the plan rotation makes every
such row incompatible under the target release's check, so activation proceeds
only at zero. never change action rows by sql, and never cancel an `executing`
action whose external effect is uncertain. preserve lineage and history: never
restamp contracts, reset attempts or silently lose reminders.

tell the owner, per item, what was cancelled, that it performed no external
effect, and that nothing replaces it; a new approval or reminder needs a fresh
owner request. for example: "The reminder set for 2026-09-30 was cancelled for
the upgrade and will not fire. Nothing replaces it; ask again to set a new
one."

unknown dispatch may have taken effect. it is never retried: inspect current
state with list or info, then decide any new action deliberately; this action
will not be repeated automatically.

`input` counts unprocessed owner and host rows: `waking` rows await a turn,
`parked` rows stay parked until an operator releases them. `decisions` counts
paid model decisions with no terminal (`open`) and completed decisions whose
first input never settled (`completed_unsettled`). `reads` counts read
positions not `completed`. these need not reach zero: let the old release
finish the turn, or the owner's `stop` settles it with a stopped conclusion.
what remains keeps its fail-closed recovery and is never replayed under the
new plan; a main run whose stored observations include an old-shape
`agent.list` success fails closed, so finish or cancel such runs first.
attributing a remaining row to a turn is manual owner-guided inspection of
`message.created_at`, `processing_attempts` and `processing_parked_at`,
`model_decision.scope_key`, `ordinal` and `completed_at`, and
`read_position.state` and `updated_at`; never print text, request, terminal,
result, contract or trace columns.

step 2. close phone and interactive fleet callers. the owner sends `pause`. verify
the durable pause, then stop jarvis cooperatively and confirm how it stopped:

```sh
sudo cat /var/lib/jarvis/runtime/paused.json
sudo systemctl stop jarvis.service
sudo systemctl show --property=ActiveState,Result,MainPID jarvis.service
```

`paused` must be true, and the service must show `ActiveState=inactive`,
`Result=success` and `MainPID=0`. the stop sends SIGINT, and the host joins its
worker before exiting, so a clean stop is the evidence that no turn is still
running. step 6 checks every unfinished action again in this stopped state with
the target release's `check-activation`, which for this cutover passes only at
zero. attribute any remaining `open` decision with the manual
owner-guided inspection from step 1. a killed, crashed or timed-out stop
(`failed`, or another `Result`) ends the procedure: inspect it, and do not
replace the unit, cli or release. only after that inspection may
`sudo systemctl reset-failed jarvis.service` clear it; `deploy/activate-release`
refuses until then. run no dream, rebuild or other operator process until step 8.

step 3. if not already done, run the [admission journal cutover](#admission-journal-cutover);
the target requires it. its `systemctl stop` is now a no-op.

step 4. from a clean checkout of the full target commit, install the inactive
release. it no longer writes the global unit:

```sh
deploy/install-release
```

step 5. from the same pinned dev-server checkout, apply devbox
(`./devbox apply`), then arch and macbook (`./workstation apply` on each).
verify each host before moving to the next. devbox apply replaces
`/usr/local/libexec/skidbladnir`, so jarvis MUST already be stopped. then check
fleet and cli identity. from the macbook's skid checkout,
`SKIDBLADNIR_DEV_SERVER_CHECKOUT=<that dev-server checkout> scripts/fleet verify`
must pass for macbook, devbox and arch. every peer must run the pinned skid
release that carries truthful stop partials (skid pr 4); an earlier peer
reports a rejected close as `not_attempted`, which this release's stop copy
reads as "no close was sent". on devbox,
`sudo /usr/local/libexec/skidbladnir version` must print the pinned tag and
source commit, `sudo stat -c '%a %U' /etc/jarvis/agent-client.json` must print
`600 jarvis`, and the file keeps its three peers.

step 6. just before activating, record the database clock for the rollback
check. it prints one timestamp:

```sh
sudo systemd-run --quiet --wait --pipe --collect \
  --unit=jarvis-activation-clock \
  --property=Type=oneshot \
  --property=User=jarvis \
  --property=Group=jarvis \
  --property=WorkingDirectory=/opt/jarvis/current \
  --property=EnvironmentFile=/etc/jarvis/database-runtime.env \
  /opt/jarvis/current/.venv/bin/python - <<'PY'
import os

from sqlalchemy import create_engine, text

from jarvis.db import normalize_database_url
from jarvis.process_security import deny_same_identity_process_inspection

deny_same_identity_process_inspection()
engine = create_engine(normalize_database_url(os.environ["JARVIS_DATABASE_URL"]))
try:
    with engine.connect() as connection:
        print(connection.scalar(text("select now()")).isoformat())
finally:
    engine.dispose()
PY
```

then activate the target. activation runs the target release's `jarvis
check-activation` in the stopped state under the deployment lock, before
migration, prints its per-action verdicts and summary, releases the lock, and
refuses with `activation check did not pass; leave service stopped` unless every
row is compatible. the plan rotation makes every pending row incompatible, so
for this cutover it passes only at zero. like `serve`, the check reads the live
codex catalog, so the codex app-server must be running:

```sh
deploy/activate-release FULL_TARGET_COMMIT
```

the service starts paused. startup recovery runs before ingress, so a paused
start is not a read-only audit. an active service is not live qualification;
the owner sends `resume` only after `deploy/verify-containment` passes.

step 7. run `deploy/verify-containment`.

step 8. the owner sends `resume`. the live codex and claude journey belongs to
isolated qualification before skid publication
([pr 4 qualification](qualification/2026-09-23-herdr-pr4.md)); nothing in this
procedure qualifies it, and production's first turn is observed, not qualified.

### rollback

rollback is the same command with the previous commit, only to a release that
carries `check-activation`; older releases are refused, not skipped. this
cutover's predecessor (production `f4e2ce6129c0add09ddb50355a8997a1c589d3d1`)
predates the check, so rollback to it is unavailable through
`activate-release`: jarvis stays stopped and repair goes forward. a later rollback target runs after the
owner pauses and the service stops cleanly as in step 2; a failed stop needs the
same inspection and explicit `reset-failed`. it installs that release's own
unit. the previous skid cli returns only through the previous dev-server apply,
also with jarvis stopped. before this release has written durable work, a
qualified same-schema previous release may return with its matching cli and
unit. count that work, including updates to rows that predate activation;
replace `ACTIVATED_AT` with the timestamp step 6 printed:

```sh
sudo systemd-run --quiet --wait --pipe --collect \
  --unit=jarvis-rollback-inventory \
  --property=Type=oneshot \
  --property=User=jarvis \
  --property=Group=jarvis \
  --property=WorkingDirectory=/opt/jarvis/current \
  --property=EnvironmentFile=/etc/jarvis/database-runtime.env \
  /opt/jarvis/current/.venv/bin/python - ACTIVATED_AT <<'PY'
import os
import sys
from datetime import datetime

from sqlalchemy import create_engine, text

from jarvis.db import normalize_database_url
from jarvis.process_security import deny_same_identity_process_inspection

CHANGED = (
    (
        "action",
        "created_at >= :since or decided_at >= :since or completed_at >= :since",
    ),
    ("model_decision", "created_at >= :since or completed_at >= :since"),
    ("read_position", "created_at >= :since or updated_at >= :since"),
    ("message", "processed_at >= :since"),
)

deny_same_identity_process_inspection()
since = datetime.fromisoformat(sys.argv[1])
engine = create_engine(normalize_database_url(os.environ["JARVIS_DATABASE_URL"]))
try:
    with engine.connect() as connection:
        for table, changed in CHANGED:
            count = connection.scalar(
                text(f"select count(*) from {table} where {changed}"),
                {"since": since},
            )
            print(f"{table}={count}")
finally:
    engine.dispose()
PY
```

any nonzero count is new durable work. then activate only a release qualified to
read its `agent_control_v2` receipts, positions and decisions; otherwise keep
jarvis stopped and repair forward. the rollback target must also be qualified
against the current admission journal
([adr 0047](decisions/0047-require-current-admission-journals.md)), or jarvis
stays stopped. never rewind the database, delete or rewrite rows, or reset
budgets.

### what activation does not prove

- activation proves one selected release, unit and `current` agree and the
  service stayed running for ten seconds without restart. it is not a model
  turn, fleet control or containment.
- `activation check: compatible=N incompatible=0 in_flight=0` covers actions
  only, and only when it ran. unsettled input, decisions and reads stay
  fail-closed and are not inspected by the gate. a codex catalog or environment
  change before `serve` starts can still let startup recovery cancel a row the
  check called compatible.
- a passing `scripts/fleet verify` shows versions and reachability, not that
  jarvis can control a worker; the live journey is still `NOT_RUN`.

## herdr gate cutover (pr 5)

this switch activates the herdr gate catalog of
[adr 0049](decisions/0049-drive-herdr-through-an-ssh-gate.md): jarvis stops
calling the skid cli and drives each host's herdr through its ssh forced-command
gate. the catalog, gate descriptor and both role revisions change, so the plan
rotates and every nonterminal action is incompatible, not only agent actions.
it is forward only: the new release cannot use the skid cli, and the previous one
cannot use the gate. a failed step leaves jarvis on the old release or stopped for
forward repair; nothing retries.

step 0. prerequisites, with the old release still running. dev-server's pr 5
step 1 is applied on all three hosts: each owner account has
`~/.local/libexec/herdr-gate` and its `restrict,command=` line for the committed
`assets/herdr/jarvis-gate.pub`, devbox has `/etc/jarvis-herdr`, the pinned herdr
server runs on every host, and skid is unchanged. prove the gate as jarvis, which
is read-only and needs no stop:

```sh
for machine in devbox macbook arch; do
  sudo -u jarvis env -i PATH=/usr/bin:/bin /usr/bin/ssh \
    -F /etc/jarvis-herdr/ssh_config "$machine" 'agent list'
  sudo -u jarvis env -i PATH=/usr/bin:/bin /usr/bin/ssh \
    -F /etc/jarvis-herdr/ssh_config "$machine" 'status --json'
done
```

each `agent list` prints one `agent_list` envelope and each `status --json` fails
with exactly `herdr-gate: command refused`. a host key, key or gate failure is a
dev-server repair; do not continue. an unreachable arch holds this cutover,
because containment requires all three hosts.

step 1. take the read-only inventory of the
[pr 4 step 1](#herdr-cutover-pr-4) one-shot unchanged, and finish, reconcile or
obtain the owner's explicit denial or cancellation of every counted action under
the same rules and owner notices. activation proceeds only at zero. a main run
whose stored observations include an old-shape `agent.list` success fails closed
under the new release, so finish or stop such turns first; never change rows by
sql.

step 2. the owner sends `pause`; verify the durable pause, stop jarvis
cooperatively and confirm a clean stop exactly as in
[pr 4 step 2](#herdr-cutover-pr-4): `paused` true, then
`ActiveState=inactive`, `Result=success`, `MainPID=0`. any other stop ends the
procedure for inspection; only then may an explicit `reset-failed` clear it. run no
dream, rebuild or other operator process until step 6.

step 3. from a clean checkout of the full target commit, install the new settings
and the inactive release:

```sh
deploy/install-private-state
deploy/install-release
```

the environment now carries `JARVIS_HERDR_SSH_CONFIG_PATH` and
`JARVIS_HERDR_MACHINES` instead of the skid cli paths, which is why the old
release cannot return. dev-server keeps `/usr/local/libexec/skidbladnir` and
`/etc/jarvis/agent-client.json` until its pr 5 step 4; nothing reads them.

step 4. activate. `deploy/activate-release` runs the target release's `jarvis
check-activation` in the stopped state under the deployment lock, before
migration, and refuses with `activation check did not pass; leave service
stopped` unless every row is compatible; for this cutover that means zero pending
actions. the check reads the live codex catalog, so the codex app-server must be
running:

```sh
deploy/activate-release FULL_TARGET_COMMIT
```

the service starts paused, and startup recovery runs before ingress.

step 5. run `deploy/verify-containment`. besides the existing boundary it checks
`/etc/jarvis-herdr`'s modes and that jarvis reaches every gate for `agent list`
and is refused `status --json`. a failure leaves jarvis paused for forward repair.

step 6. the owner sends `resume`. the first owner-directed agent turn is observed,
not qualified; the isolated qualification of this codec is recorded in adr 0049.

### what the gate cutover does not prove

- activation proves the selected release, unit and `current` agree and the service
  stayed up for ten seconds. `activation check` covers actions only.
- `verify-containment` proves reachability and refusal through each gate, not that
  a codex or claude agent starts, answers or stops on the real hosts; that live
  journey is `NOT_RUN`.
- herdr's readiness is trusted as is: codex's sign-in and trust screens read idle
  and ready, so a send can land on a menu. read before send.

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

peer agent control drives each host's herdr through its ssh forced-command gate
([adr 0049](decisions/0049-drive-herdr-through-an-ssh-gate.md)). dev-server owns
jarvis's side on devbox, `/etc/jarvis-herdr/` (jarvis's key, generated on devbox
and never copied off; `ssh_config` naming `devbox`, `macbook` and `arch`;
committed `known_hosts`), and each owner account's gate and
`restrict,command=` line. provider credentials stay on their hosts; jarvis's
process never reads them. there is no fleet hub, bearer or credential daemon.

the service reads `JARVIS_HERDR_SSH_CONFIG_PATH=/etc/jarvis-herdr/ssh_config` and
`JARVIS_HERDR_MACHINES=devbox=/home/niels,macbook=/Users/nnandal,arch=/home/nnandal`,
the label and owner home of each host; the profiles' account homes are relative to
that home. every call is `/usr/bin/ssh -F <ssh_config> <label> <herdr argv>`.
an unreachable host makes list partial and fails any call addressed to it
before it writes.

jarvis uses list/info to resolve owner requests naming a worker. every addressed
call re-reads its target (`agent get` for an agent ref, one machine scan for a
terminal ref) and requires the same name and `terminal_id`, once before the gate
and again just before the write. the gate sees machine, agent name, current pane and
the stop/kill closure-scope disclosure. a changed target prevents mutation; a
successor is never substituted. unknown writes are never repeated; the owner
notice says to inspect current state. nine worker tools share the existing
19-call run allowance with 256 kib control envelopes and a 1 mib inventory; this
release changes neither admission journals nor kernel budgets.

the herdr gate catalog is activated only through the
[herdr gate cutover](#herdr-gate-cutover-pr-5) runbook.

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
actual use. only the current journal configuration is accepted. an older journal
requires the stopped [admission journal cutover](#admission-journal-cutover).
preserve charged capacity rather than guessing or deleting its evidence.

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

If the admission journal is missing or corrupt,
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

# ADR 0033: Defer v1 backups and the host reboot

- Status: Accepted
- Date: 2026-09-07
- Supersedes: ADR 0032 in full; the backup, restore, and mandatory-reboot parts
  of ADR 0031
- Amends: SPEC sections 8, 9.3, and 11; acceptance A7; Slice 7
- Owner approval: the owner explicitly chose no v1 backup and no deployment
  reboot on 2026-09-07

## Context

Jarvis is a one-user prototype whose canonical data is currently confined to
one PostgreSQL database plus small private runtime files. The earlier Slice 7
design added Restic, Cloudflare R2, another database role, two more credential
files, two systemd units, a restore program, retention policy, and a clean-host
qualification gate before the owner had accumulated valuable production state.
None of that machinery is difficult to add without changing the four-table
schema or the agent architecture.

The devbox also has a newer installed kernel than the running kernel. Applying
it requires a reboot. A reboot is not required to install or run Jarvis, while
the host currently contains attached tmux sessions and live Codex processes.
tmux cannot preserve running processes across a host reboot; session-restoration
plugins can at most recreate layouts and restart commands.

No Jarvis Restic password, R2 environment file, backup repository, or snapshot
was created. Restic and the unused backup database role were provisioned during
deployment preparation only.

## Decision

Jarvis v1 deploys on the current running devbox kernel. The pending kernel reboot
is recorded as operational debt and occurs only in an owner-selected maintenance
window. It is not a deployment or seven-day-acceptance gate.

V1 has no application backup, restore command, Restic dependency, R2 credential,
backup database role, or backup systemd unit. The four application tables and
private runtime state remain local to the devbox. Backup becomes a later slice
when the owner decides the accumulated state is valuable enough to protect.
Adding it later must preserve the four-table application schema and require an
explicit recovery contract and restore test.

Deployment qualification still covers immutable releases, least-privilege
runtime and migration roles, loopback PostgreSQL, exact dependency identities,
systemd isolation, restart/crash recovery, derived-memory rebuild, and the
seven-day owner acceptance period.

## Consequences

Benefits:

- V1 removes an unproven storage provider, credential family, database role,
  timer, restore path, and their qualification burden.
- Deployment does not interrupt current tmux or Codex work.
- Backup can be added later without a data-model migration.

Accepted costs:

- Loss or unrecoverable corruption of the devbox, its disk, or the Jarvis
  database can permanently lose conversation history, memories, actions, and
  local runtime state.
- Until a maintenance reboot, the host does not run the newest installed kernel
  and therefore lacks fixes present only in that kernel.
- tmux is not a reboot-recovery mechanism. A future reboot requires the owner to
  finish or deliberately resume interactive Codex work afterward.

## Migration

Remove the unactivated backup units and scripts, the unused `jarvis_backup`
database role and credential files, and the Restic package installed solely for
Jarvis. Do not create a replacement secret. Preserve ADR 0032 as historical
rationale, marked superseded, and preserve prior qualification reports
byte-for-byte.

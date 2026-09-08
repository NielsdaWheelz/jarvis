# ADR 0031: Deploy v1 on the existing devbox

- Status: Accepted
- Date: 2026-09-07
- Amends: SPEC sections 8, 11, and 12; acceptance A1 and A7; Slice 7
- Amended by: ADR 0033 removes the backup/restore and mandatory-reboot portions
- Owner approval: the owner approved the existing Hetzner devbox as Jarvis's
  v1 production host on 2026-09-07

## Context

Jarvis needs one always-on Linux process, PostgreSQL with pgvector, outbound
access to its qualified providers and durable local state. The owner already
operates a private Hetzner devbox over Tailscale.
That host has four CPUs, 7.6 GiB RAM, native PostgreSQL 16 bound to loopback,
and sufficient capacity after ordinary housekeeping.

The Nexus production host is a separate public production boundary. At the
time of this decision it has two CPUs, 1.9 GiB RAM, less than 600 MiB readily
available memory, active swap pressure, and a root filesystem above 90%
utilization. Its deployment contract also owns an exact closed service set.
Putting Jarvis there would couple a private experimental assistant to the
availability, resource envelope, and release boundary of a public product.

A third small server would improve failure-domain isolation, but would add a
recurring bill and another host to patch, monitor, back up, and recover before
v1 use has demonstrated that the separation is valuable.

## Decision

Jarvis v1 runs on the existing Hetzner `dev-server` host. It does not run on the
Nexus production host, and v1 does not create another server.

The physical shape is:

```text
Hetzner dev-server (tailnet-administered; no Jarvis listener)
├── dedicated jarvis Unix service account
├── /opt/jarvis/releases/<git-commit>/
├── /opt/jarvis/current -> one immutable release
├── /var/lib/jarvis/                 durable runtime state
├── /etc/jarvis/                     root-owned configuration and credentials
├── jarvis.service                   host-native systemd unit
└── native PostgreSQL 16 on loopback
    └── dedicated Jarvis database and least-privilege roles
```

Jarvis runs host-native under systemd, not in the developer's rootless Docker
daemon. It receives no public inbound port; Discord is Gateway/outbound, and
administration remains tailnet-only. The release uses its locked Python
environment and exact `openai-codex==0.144.4`; it does not depend on or replace
the devbox's mutable user-global Codex installation.

The `dev-server` repository owns only shared host convergence: UTC host time,
required system packages, the dedicated service account and base directories,
and compatible PostgreSQL/pgvector availability. Jarvis owns its immutable
application release, virtual environment, configuration contract, credentials,
database and roles, migrations, systemd service definition, and application
health/recovery procedures. Neither repository reads
or mutates Nexus application state.

The host and PostgreSQL run in UTC. Jarvis continues to render owner-local time
from its configured IANA timezone. Deployment must qualify the exact installed
pgvector version used in production; it must not silently treat an older Ubuntu
package as equivalent to the version exercised by the accepted release.

Before deployment, bounded housekeeping removes only proved-stale CI/test
artifacts and package caches. Active containers, Git worktrees, qualification
evidence, credentials, Docker identity, SSH identity, and Tailscale identity
are preserved unless an exact operator-approved cleanup names them.

## Consequences

Benefits:

- No additional monthly server cost or new fleet surface is introduced.
- The devbox already has private administration, outbound connectivity,
  PostgreSQL, and materially more headroom than Nexus production.
- A dedicated account, release tree, database, and service keep Jarvis
  operationally separate without inventing orchestration.
- Moving later remains possible by adding a deliberate export/restore contract.

Accepted costs:

- Development, CI, and Jarvis share one machine and failure domain.
- A devbox outage, reboot, disk-pressure event, or runaway test can delay
  Jarvis; systemd resource controls and disk headroom reduce but do not remove
  that coupling.
- Host-native PostgreSQL is shared infrastructure, although Jarvis has a
  separate database and roles.
- The pending kernel update remains unapplied until an owner-selected reboot.
- V1 has no backup; devbox or database loss can permanently lose Jarvis state.

## Rejected alternatives

- Deploy on Nexus production: rejected because it couples Jarvis to a public,
  resource-constrained, closed production stack and creates the highest blast
  radius.
- Buy another Hetzner server now: rejected because isolation does not yet repay
  recurring cost and operational overhead for a one-user prototype.
- Run Jarvis in the developer's rootless Docker daemon: rejected because CI and
  test-stack cleanup/restarts would become application lifecycle operations.
- Share the Nexus database or credentials: rejected because co-location is not
  integration and grants no useful capability.

## Migration and acceptance

Slice 7 must prove a clean immutable install on `dev-server`, one active
instance, process restart recovery, loopback-only database access, exact
dependency and pgvector identities, and bounded resource use. It records the
pending host reboot and accepted no-backup risk. The seven-day owner acceptance
period starts after those gates pass and the production service is enabled.

Historical Slice 0–6 qualification reports remain byte-identical. This ADR
chooses the production target; it does not retroactively claim Linux deployment
or final acceptance for earlier slices.

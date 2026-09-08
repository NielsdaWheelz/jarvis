# Production deployment qualification — 2026-09-08

Status: production deployment gates passed; seven-day owner acceptance is in
progress and is not claimed by this report.

## Qualified release

Jarvis is active on the existing Hetzner `dev-server` as the host-native
`jarvis.service`. Nexus production was not touched and no additional server was
created.

| Identity | Exact value |
|---|---|
| Jarvis release | `13e941b58a6dda81489f4a2c3234e325d18e2d1c` |
| Jarvis tree | `1a3e74c92fd8a267871d21c8261ab052f4f854d2` |
| `uv.lock` SHA-256 | `a20bc529aece840d145a40ff8362f23ac21c98f087b948a26272b52d106d2230` |
| `llm-agent-kernel` | `21084bec674023ea572950a18dde464506ea37ad` |
| `provider-runtime` | `4ddced3bb5487ce988858c4c6d45d2e5ee0acad9` |
| `llm-tools` | `9e6d155f3b64f03495911435b7cae8b8d131f9a2` |
| `openai-codex` / bundled CLI | `0.144.4` |
| Session manifest SHA-256 | `81ae6e212e48576dcfc71cc6159788b2c6ff458a954be27ee97a2c6b51680e8b` |
| Kernel base instruction | `llm-agent-kernel-contained-structured-agent-v1:sha256:1817c90f24bf9149f20f94b69f825d9be0b78df8bb46b1d24ed2691cf71b80e7` |
| Qualified route | `local_account / gpt-5.6-terra` |

The production main definition fingerprint is
`42d6641b2a3123b722c4a98801285ff74893ae238f03666dae1052343f374bf4`.
The first accepted production run left its session at generation 2. Jarvis's
application session revision remains
`f4f195437e7af8a1fa56c90f246b1550ff03243369ac33189a099e785d3f4851`;
the new kernel instruction changed the definition fingerprint and caused the
required cold bootstrap without a redundant application revision bump.

## Deterministic release gates

The complete exact-source verifier passed against a fresh PostgreSQL database:

| Gate | Result |
|---|---|
| Jarvis | 707 passed |
| `llm-agent-kernel` | 211 passed; 8 paid tests deselected |
| `provider-runtime`, Linux all-extras | 1,016 passed; 2 skipped; 60 paid tests deselected |
| `llm-tools` | 203 passed; 2 paid tests deselected |
| Ruff / Pyright | clean / zero errors and warnings |
| Alembic | empty upgrade through `0003`; zero drift |
| Package | wheel and sdist built; clean Python 3.12 wheel/CLI smoke passed |
| Dependency audit | no known PyPI vulnerabilities; three Git projects are outside the PyPI advisory index |
| Documentation | 50 files and all local links passed |

The suite includes the retained custom-`exec` classification, rejection of
authority and unknown protocol events, no terminal after a poisoned turn,
kernel base-instruction identity and byte accounting, visible host-authored
provider failure, immutable session compatibility, and the production
credential/process boundary.

## Paid consumer qualification

The exact Jarvis lock passed the paid `gpt-5.6-terra` consumer probe:

- Four continuing conversational turns, compatible close/reopen, automatic
  generation rotation, and deliberate session-reference loss/reconstruction.
- One closed structured-output turn.
- One validated JSON-string tool-argument scenario completed in two provider
  turns.
- Seven provider turns reported 113,291 input and 467 output tokens in total.
- The resulting definition fingerprint changed while the application session
  revision stayed exact.

The release carries forward the provider/kernel paid adversarial shell/exec
qualification because Jarvis uses the exact certified policy and route. It
caused zero host effect and exposed no connector credential environment. The
retired `gpt-5.4` route and unavailable quota-exhaustion account were not used.

## Production host and containment

| Property | Observed result |
|---|---|
| Host timezone / clock | `UTC`; network synchronized |
| Python | 3.12.3 |
| PostgreSQL | 16.15; loopback only |
| pgvector | 0.8.6 |
| Running kernel | 6.8.0-138-generic; newer installed kernel deferred until an owner-selected reboot |
| Release layout | immutable `/opt/jarvis/releases/<commit>` plus atomic `/opt/jarvis/current` |
| Service | dedicated `jarvis` user; active and enabled; zero automatic restarts |
| Idle service use | approximately 164 MB and 6 tasks at observation time |
| Headroom | approximately 33.2 GB root free and 5.0 GB memory available |
| Application schema | exactly `action`, `memory_log`, `memory_summary`, `message` |

The three environment files are regular `root:root` mode-0600 files. The
`jarvis` account cannot read them. systemd injects the runtime files into the
host process and uses a separate transient unit for the migrator file. Jarvis
becomes non-dumpable before opening a provider child; the live check proved a
same-identity process could not read `/proc/<main-pid>/environ`. The child
receives a replacement environment. Its own Codex local-account files remain
readable by design; encrypted Google connector state is not usable without the
host-only encryption credential.

The immediate check after a `Type=simple` restart once ran before Python had
established non-dumpability. It was a trusted local verifier, emitted no bytes,
and no provider child can start before the hardening call. The verifier now
waits within a fixed five-second startup bound and accepts only after the
control is present. A subsequent exact check passed.

The unit additionally has no-new-privileges, an empty capability bound,
read-only system protection, private devices and temporary files, protected
kernel/control-group surfaces, a ptraceable process view, PID-only `/proc`,
restricted address families, core dumps disabled, a two-CPU quota, 2 GiB memory
high watermark, and 3 GiB hard memory limit. Jarvis opens no listener.

No Jarvis backup role, backup unit, Restic binary, R2 credential, snapshot, or
restore promise exists. This is the owner-approved v1 data-loss trade-off.

## Real Discord catch-up and restart

The owner message sent while Jarvis was stopped remained in Discord. On first
activation the bounded catch-up scanned one and accepted one. The exact
contained Main path performed one host-controlled Calendar request, completed
in two provider turns, persisted and delivered one non-empty Discord response,
then reached no-work. It created zero actions and emitted no provider-native
authority or protocol defect. The owner row was processed and remembered; no
delivery remained pending. This report stores no message or Calendar content.

A service-only restart—not a host reboot—then passed:

- the opaque session-reference file was preserved byte-for-byte;
- Gateway catch-up scanned one and accepted zero duplicates;
- the service returned active with zero automatic restarts;
- the connector-secret/process-inspection boundary passed again;
- zero input and zero assistant deliveries remained pending.

The approved Slice 6 Gmail, Calendar, Maps, Web, memory, dreaming, write,
approval, reconciliation, scheduling, and Discord integration evidence remains
the owning qualification for those unchanged layers. External write probes were
not repeated merely because the provider transport and kernel instruction
changed.

## Accepted trade-offs and remaining gate

- Code Mode is contained and detected; absence before the first observable
  event is not claimed. The typed provider boundary, sandbox, and fail-stop
  handling own authority—not the kernel prompt.
- Unknown App Server protocol activity deliberately causes availability loss
  until audited.
- The provider child must retain its own Codex local-account credential.
- AutomaticWriteGate's changed definition fingerprint intentionally rotated
  affected Write binding policies, main profiles, plans, HostTables, and future
  execution contracts. The production action ledger contained zero nonterminal
  actions at cutover.
- Development, CI, PostgreSQL, and Jarvis share the devbox failure domain.
- There is no v1 backup, and the host runs an older kernel until a later reboot.
- Terra is the sole qualified model route.
- The three exact Git dependencies cannot be correlated automatically with the
  PyPI vulnerability database.

All pre-observation Slice 7 deployment gates pass. The seven-day personal
acceptance period starts on 2026-09-08 and cannot be signed before 2026-09-15.
Acceptance A9.1–A9.7 remains an owner judgment; this report does not pre-claim
it.

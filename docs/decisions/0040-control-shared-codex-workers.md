# ADR 0040: Control shared Codex workers

- Status: **Accepted**
- Date: **2026-09-09**
- Owner approval: the owner approved the cross-repository control plan and its
  asynchronous-TUI amendment on 9 September 2026.
- Supersedes in part: ADRs 0014, 0031, 0035, and 0038

## Context

Jarvis must start and control top-level Codex workers on the devserver through
the owner's Personal, Work, and Work2 subscriptions. Those workers must appear
as ordinary tmux sessions in unchanged Skidbladnir. Codex remains the native
owner of thread history; Jarvis must not add a worker table or transcript store.

Pinned Codex 0.153.4 source and generated schemas establish that remote resume
subscribes the requesting client, approvals fan out to current thread
subscribers, the first response wins, and pending requests replay to a client
that resumes later. They expose neither a cross-client TUI-ready notification
nor an exclusive approval-owner lease. The owner therefore approved a truthful
asynchronous attachment boundary instead of a proxy, custom TUI, terminal
parsing, delay, or private Codex fork.

The prior private-process design also conflicts with one App Server shared by
the development user: kernel-created cognition directories are owner-only, so
the server cannot traverse them. Shared transport therefore requires one
explicit, empty, non-secret, group-traversable cognition-directory posture. It
does not make Jarvis application state group-readable.

## Decision

Deploy exactly one supervised Codex 0.153.4 App Server for each configured
account home. `provider-runtime` attaches through profile-selected Unix sockets;
it no longer starts, enrolls, or kills Codex App Server processes. Personal is
shared by Jarvis cognition, manual sessions, and workers. Work and Work2 serve
their corresponding manual sessions and workers. Account choice is explicit;
there is no API-key, account, process, or private-server fallback.

Add exactly five Main tools: `codex.list`, `codex.read`, `codex.start`,
`codex.prompt`, and `codex.interrupt`. This is an owner-directed control surface,
not general model-generated delegation: no schedules, completion callbacks,
workflow graph, worker ownership, generic shell, arbitrary environment, or new
durable table is added. Existing authority, current-input grounding, action,
and immutable execution-contract machinery remains authoritative.

`codex.start` validates an explicit profile, bounded lexical cwd, name, and
prompt; asks the host helper to resolve an existing canonical permitted cwd;
creates one native thread there; unsubscribes its control connection;
asks the host launcher to create and immediately observe one exact ordinary tmux
session; then submits one initial input through Codex's native start-or-steer
operation. `Started` means those three native/host
operations were accepted. It does not claim that the stock TUI has completed
attachment. If an approval occurs first, Codex retains and replays it when the
TUI resumes. Jarvis never answers worker approvals. Trusted clients must not
subscribe to a worker they do not intend to operate because upstream provides
no exclusive reviewer lease.

`codex.prompt` calls that same native Submit operation and returns its accepted
turn handle. Codex 0.153.4 has no atomic reject-if-busy parameter and does not
report whether `turn/start` started or steered, so this tool does not claim
idle-only NewTurn semantics. Explicit Steer retains its expected-turn check.
Interrupt uses the pinned App Server exact-turn precheck and observes the
terminal outcome; natural completion racing the interrupt is reported as
Finished or Stale, never retried, and never knowingly redirected to an observed
successor. Strict NewTurn admission and a core successor token are deferred
until upstream exposes them.

The non-secret profile document is root-owned mode `0644`; account credentials
remain only in private development-user homes and sockets/runtime directories
remain group-restricted. This lets already-running development shells consume
new routing without a supplementary-group refresh. The host launcher is a socket-activated, closed protocol running as the
development user. It authenticates the Jarvis peer before reading one bounded
request. `ResolveCwd` accepts only `{profile, cwd}` and returns the canonical
permitted existing directory before any native creation. `LaunchTerminal`
accepts only `{profile, thread_handle, cwd, tmux_name}` and revalidates that
exact path. The helper selects
the configured endpoint and stock remote-resume command itself. Prompt,
environment, executable, socket, account home, and arbitrary argv are not caller
inputs. The helper reports only an exact tmux observation; it never claims TUI
readiness. App Server runtime parents and sockets are normalized after bind to
the dedicated shared-client group because upstream 0.153.4 creates them as
`0700`/`0600`; this is a bounded permission operation, not a proxy.

Codex write actions use `ReplayPolicy.BilledOnce`, one executor entry, typed
`Rejected`/`Partial`/`Unknown` outcomes, and exact surviving prefixes. Once a
mutation may have been sent, cancellation, disconnect, timeout, or restart
never resends it and the original input cannot create a replacement action.
Only exact native handles may be reconciled.

Jarvis cognition remains read-only, no-network, native-tools-disabled, and
fail-closed on every native authority event. Its empty per-session cwd is
created beneath the host-owned shared cognition parent with mode `0750`: owner
read/write/traverse and shared-runtime-group read/traverse. The directory is
asserted empty and non-secret. This narrow kernel option defaults off and changes no
other application directory, credential, connector, database, or process
environment. Worker cwd and workspace-write policy are fixed by the host
profile; worker output supplies no new Jarvis authority.

Workers execute independently after accepted dispatch. Jarvis cognition and
host-tool dispatch remain serial. A worker's native events never enter the
structured cognitive decoder. `Started` is a terminal result for the launch
action, not completion of worker work and not a promise of later notification.

## Acceptance

- Public external-protocol tests prove shared attachment, control
  unsubscription, thread-scoped approval policy, exact-handle routing,
  disconnect-only cleanup, and bounded failure classification.
- Real Jarvis action/dispatch tests prove the five-tool catalog, authority,
  BilledOnce settlement, prefix preservation, and no redispatch or replacement
  action after ambiguity.
- Host tests prove the exact pin, closed launcher/helper schemas, safe argv,
  profile routing, permissions, host selection, and second-apply quiescence.
- One separately approved Linux real-stack journey proves all three profiles,
  stock asynchronous TUI resume, pending approval delivery, ordinary tmux/Skid
  visibility, and coexistence with contained cognition. Missing live boundaries
  remain `NOT_RUN`, never pass.

## Migration

Hard-cut the private Codex App Server runtime, private Codex-home enrollment,
server-killing cleanup, and Devbox latest-channel Codex selection. Drain
incompatible Jarvis actions and private sessions before activation without
killing existing manual tmux sessions or native history. Pin package, consumers,
and compatibility records to 0.153.4. The subsequently approved host-deployment
extension in `dev-server/SPEC.md` owns installation on MacBook and Arch too;
Jarvis control remains Devbox-local and Claude remains unchanged. Human commands
are transparent account selectors: native shared discovery retains upstream
exceptions, while Jarvis always uses the explicitly configured shared transport.

## Trade-offs

- Three shared services reduce lifecycle duplication but create account-local
  shared failure, version, resource, and trusted-client boundaries.
- `Started` can precede TUI attachment. This is observable and honest, and
  pending approval replay preserves the human decision path, but attachment
  failure requires manual inspection/resume.
- Approval exclusivity is policy, not server enforcement. This is accepted for
  the single-user trusted-client prototype; a future upstream attachment/role
  lease is preferable to a local fork.
- Submit may steer a concurrently active turn, and interrupt cannot claim a
  core-level compare-and-swap. Exposing native semantics avoids a racy pre-read;
  callers use exact Steer when the distinction matters.
- A dedicated Unix group gains read/traverse of asserted-empty cognition
  directories and access to App Server sockets. It gains no Jarvis state or
  secret-file access.
- Root-owned profile paths and digests are locally readable because they are
  deliberately non-secret; keeping them group-only would make activation depend
  on refreshing long-lived development-user group membership.
- BilledOnce refuses automatic recovery after ambiguity, favoring duplicate
  prevention over availability.
- Codex App Server and remote TUI support are pinned experimental dependencies,
  not vendor-supported production infrastructure.

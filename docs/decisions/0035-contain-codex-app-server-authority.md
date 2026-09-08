# 0035: Own and fail closed on the complete Codex App Server authority surface

Status: Accepted, 2026-09-08

## Context

The first production deployment accepted an owner question about the following
day. Instead of emitting the kernel's structured `calendar.list_events` call,
Codex attempted a provider-native custom call named `exec`. The host sandbox
prevented the intended effect, but the pinned provider normalized the activity
as inert native telemetry and later allowed a model terminal. Jarvis therefore
settled a silent response. Sanitized evidence retained the shared native call
identity and lengths only; no private input, output, or arguments enter this
record.

Audit then showed that the public Python SDK consumed and answered
server-initiated approvals and unknown requests internally. A notification-only
adapter could not observe the complete authority surface, so neither a Jarvis
special case nor a kernel-only patch could prove the required boundary.

## Decision

Pin `provider-runtime` to
`4ddced3bb5487ce988858c4c6d45d2e5ee0acad9`, published under the immutable
`codex-app-server-containment-2cfed97-v1` tag, and pin
`llm-agent-kernel` to
`21084bec674023ea572950a18dde464506ea37ad`.

The provider owns the documented Codex App Server stdio JSON-RPC transport
directly while preserving the public `(backend="codex", transport="sdk")`
route. It classifies every audited 0.144.4 request, notification, and item;
denies server requests; turns every native authority surface into typed
`AgentToolUse` or `AgentPermissionRequest`; and treats unknown or inconsistent
protocol activity as `ProtocolDefect`. No terminal after authority activity can
be accepted. The kernel keeps its existing rejection behavior and prepends its
immutable contained-structured-agent instruction to every provider request.

Jarvis keeps its existing application and role
`session_compatibility_revision` values. The kernel instruction identity enters
every definition fingerprint, so old sessions cold-bootstrap without a second
manual compatibility rotation. Jarvis counts the kernel instruction inside its
system-material ceiling and emits a host-owned visible provider-failure message.

For production credential isolation, environment files become root-owned mode
0600 and are read only by systemd. Jarvis marks itself non-dumpable before it
opens a provider child. The child receives a replacement environment and cannot
read the parent environment through `/proc`; it retains access only to its own
Codex authentication state and encrypted/non-secret service files.

## Consequences

- Native Code Mode is contained and detected, not claimed impossible before its
  first observable event. Typed transport enforcement—not prompt obedience—is
  the authority boundary.
- Protocol drift deliberately causes availability loss until the new surface is
  audited and pinned.
- Every existing provider session cold-bootstraps once because the kernel base
  instruction changes definition fingerprints. Canonical messages and memory
  reconstruct context; no database migration is needed.
- Jarvis commits the AutomaticWriteGate definition fingerprint into each Write
  binding policy. That role's intentional fingerprint rotation therefore
  rotates affected main catalogs, profiles, plans, HostTables, and execution
  contracts even though tool code and contracts are unchanged. Activation
  requires the current production action ledger to contain no nonterminal
  action made under the predecessor identity.
- The base instruction spends 682 system bytes and some input tokens on every
  session.
- The provider child can read its required Codex account state. The service-user
  boundary plus non-dumpability protects host credentials, but read-only
  provider containment is not a general confidentiality boundary for every file
  readable by that Unix identity.
- The direct provider transport is certified against exactly Codex 0.144.4.
  Upgrading it requires a fresh closed-world protocol audit and live
  qualification.
- The application schema remains exactly four tables.

## Rejected alternatives

- Special-case `exec` in Jarvis: misses other current and future authority
  methods and acts after the owning abstraction leaked.
- Rely on disabled native-tool configuration or the kernel prompt alone:
  neither proves the provider will never emit native authority activity.
- Continue through unknown native events: converts provider drift into an
  unreviewed authority expansion.
- Accept the public SDK's default approval handler: server requests remain
  invisible and some are automatically accepted.
- Add a new workflow, broker, container, or service solely for this correction:
  unnecessary for the v1 boundary once the provider owns the transport and the
  host files/process are isolated.

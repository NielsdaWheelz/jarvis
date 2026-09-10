# ADR 0042: Track latest stable native Codex

- Status: **Accepted**
- Date: **2026-09-09**
- Owner approval: latest stable is preferred for this one-user prototype;
  occasional upstream breakage and prompt repair are accepted.
- Supersedes: ADR 0041's native executable pin, not its control or authority contract.

## Evidence and decision

An installed CLI upgrade to 0.154.0 was rejected by the host's 0.153.4 equality
check before terminal creation, while the existing shared servers kept running.
Jarvis reported a thread-only partial launch and sent no initial prompt. Version
equality had become an availability gate independent of actual protocol support.

The existing `dev-server` install/update workflow resolves npm's stable `latest`
channel once per apply and installs that candidate using ordinary npm integrity
checks. No launch-time download, updater daemon, private-server fallback, or
native version allowlist is added. Native versions are diagnostic observations,
not admission policy. Python dependencies and library Git revisions remain locked.

The closed host document becomes schema 2: existing operational/account/path
fields, without `version` or `package`. Schema 1 and extra fields are rejected.
Human commands remain transparent account selectors. Jarvis retains explicit
shared attachment, permitted roots, fixed worker policy, peer authentication,
contained cognition, strict protocol validation, and non-retryable uncertainty.

## Migration and trade-offs

Deploy host schema 2 and its consumer together, after draining incompatible
actions. The changed host-policy fingerprint and exact library revisions rotate
affected frozen contracts. No state migration, dual reader, or automatic replay
is introduced. A version-only apply does not restart healthy App Servers;
planned restart is an explicit operator action that can interrupt active turns. The
first operational-schema cutover also requires this coordinated restart.
Normal service-manager crash recovery may load the newly installed binary.

CLI and server versions may differ until restart. No full compatibility or
containment guarantee for unseen upstream changes is claimed. Actual protocol
drift continues to fail closed; changed semantics require inspection and the
owning behavioral proof, not a relaxed parser. Live evidence names the observed
runtime and cannot be inherited solely because a version was accepted.

## Acceptance

- Host: latest-stable install, unchanged argv/account routing and closed launcher;
  version-only updates preserve active services, explicit restart remains effective.
- Runtime: a different well-formed native version connects; malformed protocol,
  authority events and ambiguous mutations retain their existing failure behavior.
- Jarvis: only schema 2 is accepted; existing authority and BilledOnce proofs pass.
- Routine gates run without provider, tmux, device or service mutations. Existing
  real-stack acceptance remains separately authorized and is not replaced by them.

# skid installed-state access for the jarvis service

decision, 2026-10-21: the owner authorized terminal-only skid pr integration,
release and deployment. jarvis must remain STOPPED pending separate live-state
access-boundary work and qualification. no new privilege bridge or copied state
is authorized by this decision.

problem: the generalized skid cli reads the enrolled computer's live installed
state directory. jarvis runs as `jarvis`; the devbox installation belongs to
`niels`, whose state directory is `0700` with `0600` private files. jarvis also
uses `ProtectHome=true`, `ProtectSystem=strict` and `NoNewPrivileges=true`.
there is no existing worker cli privilege boundary that can read that state.

impact: source adapters accept `JARVIS_AGENT_STATE_DIRECTORY`, but installed
worker cutover is BLOCKED pending a separate deployment integration. copying
`identity.json`, `host-state.json` and `resolved.json` into service-owned storage
would stop following the host's automatic configuration/membership updates.
the retired private `client.json` provisioner cannot satisfy the new contract.

evidence: `src/jarvis/agent_control.py` invokes the fixed cli directly, with only
`PATH=/usr/bin:/bin`. `deploy/jarvis.service` declares the restrictions above.
the old `deploy/install-agent-client` copied owner-supplied credentials only on
an explicit deployment; no runtime refresh mechanism existed. local disposable
subprocess/schema tests qualify the new source adapter, without installation,
service-uid qualification, providers or fleet changes.

resolution: separately choose and qualify a narrow deployment access boundary
for the same live enrolled computer identity, preserving the service's other
containment and future membership/revocation updates. no global user change,
copied stale state, new device kind or generic delegated service is authorized.
prove the real service uid can run the matching installed cli through that
boundary, adopt a new member and revocation without manual credential copies,
retain exact targets and never replay an uncertain write. then complete the
paused/stopped release qualification before worker activation.

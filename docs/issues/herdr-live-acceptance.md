# herdr live acceptance

problem: the live codex and claude journey required by
[adr 0048](../decisions/0048-align-with-the-herdr-fleet-cli.md) and skid's pr 3
specification (start → info → agent ref → readiness/read → one submission →
observed response → follow-up → interrupt, on an isolated gateway/herdr with
test-owned workers) has not run. it is `NOT_RUN`, not a pass.

impact: the consumer is proven only against the real merged cli codec driven by
a scripted loopback gateway, the unmodified cli's grammar/usage behavior, and
the real jarvis controller, dispatcher, recorder and isolated postgres. actual
readiness recognition, terminal-mode override after inspection, provider
interrupt delivery and linked-group closure refusal on a real herdr host remain
unobserved; behavior may fail during first use and need live repair.

evidence (2026-09-23, development macbook): no `herdr` binary is installed
(`command -v herdr` empty; nothing under `~/.local/share/skidbladnir`); the
fleet peers still serve the pre-herdr v0.6.0 gateway because skid pr 4 is
undeployed; the cli's peer origin check accepts only `https://HOST:8443`, and
8443 on this host is production's tailscale serve for the live gateway that
must not be touched. a local private-ca path is itself an accepted skid pr 2
waiver. pr 4's jarvis slice added activation safety and a temporary source
proof that the three stop failure shapes settle correctly through the real
controller, dispatcher and isolated postgres; that is not this journey.

known blockers, in the spec's order: a nonproduction linux host with a trusted
https front on 8443 that does not serve production; isolated herdr, skid gateway
and jarvis postgres/runtime state on that host, never production's; and
test-owned codex and claude workers whose provider spend the owner approves.
this journey gates skid publication and fleet activation under the
[herdr cutover](../operations.md#herdr-cutover-pr-4) runbook, not the reverse.

resolved when one linux codex + claude journey through the actual jarvis tools
records versions, boundaries and verdicts (never prompts, terminal bytes or
credentials) in a dated qualification report, including ordinary-send refusal
under unconfirmed readiness followed by deliberate terminal mode after
inspection. skid pr 4 owns the fleet; this record does not reopen pr 2 waivers.

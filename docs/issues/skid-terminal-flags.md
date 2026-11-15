# skid worker client acceptance

updated: 2026-11-15. [o8](../worker-launch-observation.md) owns worker v10;
[slice 3](../delegated-follow-through.md) qualifies a temporary candidate against
installed skid. production acceptance remains at final v2 cutover.

problem: qualified candidate launch, control and truthful partial/uncertain
outcomes do not establish the selected production journey. source fixtures and
candidate ingress cannot establish that boundary.

impact: an artifact/schema mismatch can reject a valid receipt after an effect;
an unsupported claim about launch or interruption can misstate what work exists.

known evidence: [adr 0069](../decisions/0069-terminal-only-workers.md) records v9
source/integration proof; [adr 0072](../decisions/0072-native-memory-rollout.md)
adds worker v10, the enrolled `dev-server` label and actual live-state access.
[installed receipts](../universal-memory.md#native-memory-installed-qualification)
record skid `v0.24.2`, the root-managed read-only id-mapped mount and restricted
service-uid reads on macbook/dev-server. the old private-client/file-pause installer
and access blocker are resolved; do not restore them. immutable current captures
and finalized opaque retired receipts remain required.

candidate evidence: [slice 3](../delegated-follow-through.md#implementation-evidence--2026-11-15)
records actual native/service-uid launch and terminal interaction over installed
skid and the live read-only mount, ending on signed `v0.24.3`
(`0c2874f9f9e33bb4037afa310f16ef6e0c584db8`).
codex produced useful source evidence on both online machines. both claude-work
routes hit their monthly spend limit before useful execution; main reported that
limit honestly and recorded blocked state. a created terminal with undelivered
initial input was retained and deliberately inspected/interacted with rather than
relaunching it. controlled unknown-effect recovery performed no mutation replay.

resolved upstream defects: the wrapped-footer parser cap left a completed codex
terminal `layout_unknown`. [skid pr 203](https://github.com/NielsdaWheelz/skidbladnir/pull/203)
repairs the owning decoder and grammar. signed artifact construction then exposed
build-identity metadata being mistaken for a mac runtime code change;
[pr 204](https://github.com/NielsdaWheelz/skidbladnir/pull/204) repairs the existing
comparison after signature verification. source/live red/green and negative cases
pass. the owner-approved signed release and gateway-only installation are complete
on macbook/dev-server. original runtime starts, service definitions, existing
session/pane refs and the read-only mount remained unchanged. the same captured
terminal now matches `idle/none/recognized` through the actual service-uid cli.
independent installed review passes. worker wire/meaning remains v10; its
fingerprint does not purport to pin the external executable.

next: qualify the production handoff below at final v2 cutover. useful claude-work execution
remains `NOT_RUN` after both configured routes reached their account limit; the
owner explicitly selected unavailable status for this delivery. obtain that
evidence after quota availability.

resolved when: the final selected-production journey passes
with its exact artifact/host/profile evidence. [wait acceptance](agent-wait.md)
owns event continuation/restart; [operations](../operations.md#skid-only-worker-cutover)
owns eventual activation. intermediate activation stays disabled. offline arch
and untested profile combinations remain explicitly unqualified; no compatibility
reader, copied state, privilege bridge or new worker protocol.

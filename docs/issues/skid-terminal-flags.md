# skid worker client acceptance

updated: 2026-11-15. [o8](../worker-launch-observation.md) owns worker v10;
[slice 3](../delegated-follow-through.md) qualifies a temporary candidate against
installed skid. production acceptance remains at final v2 cutover.

problem: matching artifacts and service-uid reads are qualified; real launch,
control and truthful partial/uncertain outcomes through the v2 composition remain
unproved. source fixtures cannot establish installed behavior.

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
v0.24.2 (`d4afbfcec963b1f231fc117675120eff1685e881`) and the live read-only mount.
codex produced useful source evidence on both online machines. both claude-work
routes hit their monthly spend limit before useful execution; main reported that
limit honestly and recorded blocked state. a created terminal with undelivered
initial input was retained and deliberately inspected/interacted with rather than
relaunching it. controlled unknown-effect recovery performed no mutation replay.

remaining installed defect: at 80×24 a wrapped codex status footer can exceed the
gateway's three-row parser cap, leaving a completed worker `layout_unknown` and
timing out its idle wait. [skid pr 203](https://github.com/NielsdaWheelz/skidbladnir/pull/203)
repairs the owning decoder and grammar; guarded actual-source red/green, authored
frame boundaries, existing corpus and host checks pass. pr 203 merged after normal checks and the owner approved signed publication and gateway-only updates. installed repair proof is still open: signed v0.24.3 construction exposed a normalized mac terminal-runtime difference, so publication/installation are held for build diagnosis. no comparator bypass or terminal-runtime restart is authorized. retain v10's unchanged public wire/meaning, not a jarvis workaround or
an invented claim that its fingerprint pins the external executable.

next: qualify the signed gateway-only update without replacing/restarting an
unchanged terminal runtime, rerun installed status/wait, and obtain useful
claude-work evidence after quota availability; the owner explicitly selected unavailable status for this delivery. finish slice 3's final content and
cleanup checks. all production cutover work below remains open.

resolved when: candidate proof and the final selected-production journey pass
with their exact artifact/host/profile evidence. [wait acceptance](agent-wait.md)
owns event continuation/restart; [operations](../operations.md#skid-only-worker-cutover)
owns eventual activation. intermediate activation stays disabled. offline arch
and untested profile combinations remain explicitly unqualified; no compatibility
reader, copied state, privilege bridge or new worker protocol.

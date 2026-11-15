# asynchronous agent wait acceptance

updated: 2026-11-15. [o8](../worker-launch-observation.md) owns existing wait
transport; [slice 3](../delegated-follow-through.md) owns candidate qualification
and demonstrated repairs. full-plan result events are implemented in source.

problem: source and isolated proof do not establish actual skid follow-through
from the v2 candidate or selected production release. the owner selected candidate
qualification now and production acceptance at final v2 cutover.

impact: until each boundary passes, do not claim real worker observation,
restart/continuation or complete production gateway/discord delivery from source
checks, artifact pins or read-only fleet access.

evidence: [adr 0064](../decisions/0064-simple-worker-orchestration.md) and
[adr 0069](../decisions/0069-terminal-only-workers.md) retain their historical
postgres/cli/fixture-gateway proofs. [slice 1](../one-main-events.md#implementation-evidence)
qualifies common event authority and scoped stop; slice 2 qualifies scheduled
todos. [adr 0072's installed boundary](../universal-memory.md#native-memory-installed-qualification)
qualifies the matching cli and real service-uid reads through the live read-only
state mount. none of those results proves the remaining worker journey.

candidate evidence: [slice 3](../delegated-follow-through.md#implementation-evidence--2026-11-15)
records real native/service-uid worker launch, unrelated input while watching,
original receipt/ref/deadline across a candidate process restart and useful
event-driven continuation/todo mutation through the actual discord outbox.
controlled real-postgres race, atomic publication, pause/deadline, park, shutdown,
watching replay and unknown-effect no-replay checks pass. private worker captures
and opaque retired callback payloads were removed from fresh model context while
preserving original evidence. ingress/catch-up were controlled, not physical owner
gateway acceptance.

next: finish final content/cleanup qualification, install and qualify the reviewed
skid wrapped-footer repair under its approved gateway-only boundary, and obtain
useful claude execution when the configured profile's account quota permits it; the owner selected explicit unavailable status for this delivery.
the installed v0.24.2 gateway can miss an ordinary idle codex terminal whose footer
wraps past three rows; the source repair alone does not close that installed gap.
keep unavailable boundaries explicit and retain the production handoff below.

resolved when: the candidate proof passes and final authorized v2 cutover repeats
real owner gateway → main → worker → observation → useful continuation → discord,
including selected-service restart. preserve original receipts, latest stopped
intent and effect recovery. production migration/reminder accounting belongs to
[the existing todo cutover](work-installed-cutover.md); candidate success does not
close this issue. arch remains deferred. no new callback protocol or standing
behavioral harness is required.

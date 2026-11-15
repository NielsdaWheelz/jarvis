# asynchronous agent wait acceptance

updated: 2026-11-15. [o8](../worker-launch-observation.md) owns existing wait
transport; [slice 3](../delegated-follow-through.md) owns candidate qualification
and demonstrated repairs. full-plan result events are implemented in source.

problem: qualified candidate follow-through does not establish the selected
production journey. the owner selected candidate qualification now and production
acceptance at final v2 cutover.

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

candidate qualification passes on installed skid `v0.24.3`, including the repaired
wrapped-footer observation, actual scheduled delegation, registered-wait process
restart, supported result and independent content review. both configured
claude-work routes exhausted their monthly quota; useful claude execution is
`NOT_RUN`, explicitly accepted as unavailable by the owner. an earlier safely
parked [unexplained native defect](native-protocol-diagnostics.md) remains a
diagnostic follow-up, not a resolved failure.

next: qualify the production handoff below at final v2 cutover. obtain useful
claude execution when its quota permits; retain the explicit unavailable boundary.

resolved when: final authorized v2 cutover repeats
real owner gateway → main → worker → observation → useful continuation → discord,
including selected-service restart. preserve original receipts, latest stopped
intent and effect recovery. production migration/reminder accounting belongs to
[the existing todo cutover](work-installed-cutover.md); candidate success does not
close this issue. arch remains deferred. no new callback protocol or standing
behavioral harness is required.

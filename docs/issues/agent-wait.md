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

next: use slice 3's temporary candidate, real online workers, native cognition,
actual outbox and controlled ingress. prove immediate watching plus unrelated
input, event-driven follow-up without another owner message, original ref/deadline
and watching receipt across restart, one atomic outcome/event and truthful
cancellation/timeout/partial-result handling. use focused fault checks for races
and unknown-effect no-replay. mark controlled/unavailable boundaries explicitly;
update the owning spec's evidence, not a new report tree.

resolved when: the candidate proof passes and final authorized v2 cutover repeats
real owner gateway → main → worker → observation → useful continuation → discord,
including selected-service restart. preserve original receipts, latest stopped
intent and effect recovery. production migration/reminder accounting belongs to
[the existing todo cutover](work-installed-cutover.md); candidate success does not
close this issue. arch remains deferred. no new callback protocol or standing
behavioral harness is required.

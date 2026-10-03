# asynchronous agent wait

recorded: 2026-09-30. approved behavior; binding and recovery details remain open.

problem: jarvis has no `agent.wait`. simply awaiting skid inside tool dispatch
would hold main; scheduling repeated model turns would not implement the chosen
register-now/result-event-later behavior.

impact: workers cannot yet return observations asynchronously while jarvis stays
available, including across restart. [o8](../implementation-plan.md#o8-richer-start-and-asynchronous-wait)
owns this integration; it does not depend on the work-table migration.

evidence: current `src/jarvis/agent_tools.py` has no wait binding. skid's
`internal/fleetclient/wait.go` captures a target, samples immediately and every
five seconds, and returns matched/timeout/target-changed evidence. its one-hour
maximum and immediate state match are not themselves a durable next-result
subscription. terminal idle is not native turn completion.

resolved when: `agent.wait` durably records an immutable registration receipt in
`action` and immediately returns watching. a host watcher outside main's mutex
observes/reads the exact target and persists one later outcome plus the ordinary
idempotent action-resolution message. startup resumes observation without
resending work. define register/cancel arguments, observation boundary, overall
timeout, and bounded retries using existing action/scheduling machinery.

prove fast completion before registration, stale previous idle, target changes,
restart between observation and event persistence, cancellation, and unavailable
output. preserve raw worker prose and honest native-versus-terminal evidence.
chunk timeouts may continue host observation; they must not generate repeated
model polling. never reread a replacement target after the captured one changes.

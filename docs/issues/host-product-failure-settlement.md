# host product-failure settlement

problem: `_fail_native_product` renders only `hosts[0]`, then marks every host
input processed and finishes each due wake. failed/malformed native processing
can therefore consume reminders or outcomes the owner never received.

impact: later required events are lost; a processing error is recorded as wake
fulfillment. host events cannot retain the same recovery state as owner requests.

evidence: `src/jarvis/native_runtime.py:602` uses first-host rendering and the
host loop stamps `processed_at` / calls `finish_schedule_conclusion`. source audit
`f3b4dc3`, 2026-10-04; no behavioral execution in this documentation task.

reproduction: deliver a batch containing two distinct required wakes, then
malformed final output. inspect both host states/wake outcomes and the outbox:
only the first reminder is framed while both are consumed.

resolved when o6 atomically parks all affected live owner/host requests as
waiting/configuration with null processed time and stamped `processing_parked_at`,
retains unfinished requests/seal/action evidence and emits one truthful
batch-failure notice without claiming requested work succeeded. this needs no
notification-policy field. repaired configuration releases only
configuration waits; late stopped/fenced output changes none. cutover inspects
prior failed products for false consumption; unresolved retained commitments
need explicit disposition, and original receipts remain unchanged. the todo
timer's future publication does not itself mean task completion. prove with a
temporary real-database/native-settlement integration case and delete it after
accepted final-tree qualification. [o6](../one-main-events.md) owns the repair.

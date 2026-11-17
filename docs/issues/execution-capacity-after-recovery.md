# executor capacity remains occupied after recovery handoff

status: OPEN. the source repair has independently reviewed isolated functional
proof; installed verification is pending. the calendar outcome remains a separate
uncertainty until its own verified recovery.

on 2026-11-17, main's calendar creation entered at 12:36:48 utc, then returned
`recovery_required` / `waiting_for=system`. `work.create` failed at 12:37:11 with
`BudgetExceeded` and zero executor entries. its canonical arguments were 2,767
bytes, below its 65,536-byte payload limit and 65,792-byte action wrapper limit.
a later web search also failed before entry,
with no recorded reservation. the calendar eventually became `uncertain`, with
`conflicting-event-at-effect-id`; two recorded external attempts can include the
account-profile read and one event post. they do not prove two creations.

the pinned llm-tools `662a63a` charges active capacity during `reserve` and releases
it only during `settle`. an entered redispatchable write's ambiguous timeout
raises `RecoveryRequired` without a terminal result or settlement. jarvis returns
the required suspended receipt and releases its serial dispatch lane. the native
attempt retains one shared budget, whose only finite run ceiling is
`max_in_flight=1`; its occupied slot then rejects unrelated work and reads.
later action reconciliation uses another budget and cannot repair that old slot.

this is an executor-capacity leak, not exhausted cumulative quota or oversized
work input. source owners are `llm_tools.execution.ToolExecutor` and
`llm_tools.budgets.RunBudgetState`; durable effect and cost evidence remain owned
by the existing jarvis recorders. the independent exact-event observation at
12:47:37 isolated discarded fractional seconds in both event times, with other
writable fields equal; the [calendar precision issue](calendar-subsecond-precision.md)
owns that separate cause.

the selected repair releases only active executor capacity when an accepted
invocation exits. it retains calls/input charges, unresolved attempt/output
reservations, original receipts and unknown-effect barriers. terminal settlement
still owns actual cost. no fresh per-callback budget, higher concurrency ceiling,
fake settlement or automatic effect replay is permitted.

the temporary proof uses the actual executor and jarvis action/work/read stores
on disposable postgres `0013`, with controlled http transport. one entered
calendar timeout retains its full original row bytes and two-attempt reservation;
independent work and a billed-once read then succeed with the same serial budget.
the original calendar posts once, and completed read replay charges nothing.
separate executor cases cover cancellation, defects, finite cumulative cost,
forbidden replay, concurrent duplicate claims, verified abandoned re-entry and
settled replay. retaining unknown maxima can still exhaust a finite cumulative
quota; releasing execution capacity does not waive that quota.

qualified tools commit: `b25bd5f08bc82eb47eb4384139cfb2623ad12a68`.
ten temporary executor cases, seven jarvis/postgres checks and all 206 existing
nonlive tools tests passed. lint, formatting, typing, package builds and dependency
audit passed. the temporary proof uses synthetic accepted authority rows; it
does not claim a new native supervisor/model or real-account journey. concise
private receipts retain red failures, exact source/probe hashes and green results.

the compatibility owner will rotate the existing application session revision
alongside exact tools/kernel pins. this common recorder/executor admission repair
changes no individual handler, argument/result schema, effect identity or replay
policy, so it does not require nominal revisions for every binding. calendar's
separate timestamp projection repair retains its own revised binding policy.

closure requires real-executor and isolated postgres proof that a calendar
recovery handoff permits independent work and a paid read with the same serial
budget, while original action bytes, digest and entry count remain unchanged and
the original write cannot redispatch. cancellation, defects, normal settlement,
capacity reacquisition and replay must preserve the same distinction. after
source qualification, separately verify the exact installed dependency graph and
the genuine owner journey. temporary proof is then deleted; concise private
receipts retain the actual failure and verification scope.

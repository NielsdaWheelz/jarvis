# background ownership defects

problem: memory background work converts deployment ownership failures into
ordinary no-progress results. this contradicts spec section 11: genuine ownership
loss and unexpected task failures remain defects.

impact: a failed owner can appear idle instead of terminating through the service
lifecycle. queued rememberer preparation can also discard its in-process group.
database access still rejects the lost owner; the reproduction established no
unauthorized effect or persisted data loss.

evidence: on 2026-09-17 at `d1295d6`, a temporary integration reproduction acquired
the real advisory lock in a disposable postgres database, then closed its actual
sqlalchemy owner connection. direct `RemembererWorker.run_one` selection raised
`DeploymentOwnershipDefect`; the same path through
`JarvisService._run_background_once` returned `False`. immediate group preparation,
embedding writes, and attempt-trace writes also swallowed the defect. the ownership
context reported the loss on exit. no provider calls or table mutations occurred.

reproduce: acquire `deployment_ownership`, close its connection, then invoke the
rememberer directly and through the service coordinator. compare raised defects
with returned work results. repeat at immediate preparation and memory-write
boundaries with synthetic input only.

repair scope: let ownership defects propagate through memory worker database
catches, memory read dispatch, and background coordination. removing only the
coordinator catch is insufficient. retain expected model/provider failure results,
cooperative cancellation, and commit-finally cleanup. investigate other unexpected
exceptions separately rather than inventing a new failure framework here.

resolved when disposable-database checks prove ownership loss reaches the service
lifecycle from selection, memory reads, commits, and trace writes; no group or
watermark advances after loss; and ordinary memory/provider failures and shutdown
retain their specified behavior.

blocker: implementation paused under the repository's code/spec discrepancy rule;
the owner has been asked whether to repair to the existing spec next or defer this
issue while continuing unrelated cleanup.

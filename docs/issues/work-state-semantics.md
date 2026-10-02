# work history and stopped state

recorded: 2026-09-30. unresolved design before the work-table migration.

problem: the approved v2 direction asks for automatic work crud and also says
"append-only for now." the four attention states do not explain completed,
cancelled, or archived work. long-running continuation also needs a durable way
to distinguish explicitly stopped work from unfinished eligible work.

impact: [o7](../implementation-plan.md#o7-one-work-table-and-four-attention-states) cannot choose an
in-place mutation or terminal-state schema silently. a skid link in prose is
useful context but cannot enforce stop precedence after restart.

evidence: [the work-record direction](../implementation-plan.md#o7-one-work-table-and-four-attention-states)
records both instructions. no work table has been implemented by this plan.

resolved when: the owning adr settles stable item identity, retained history,
current-view selection, completion/cancellation/archive and deletion semantics,
plus the smallest continuation-enabled/stopped representation. append-only
revisions in the one table are a candidate, not an already accepted schema.
the migration and focused acceptance then demonstrate those choices.

keep captured top-level refs and task context with work. pending waits and their
outcomes belong to existing action rows; timed wakes retain their scheduler
ownership. do not introduce a worker table, child graph, or duplicate watch state.

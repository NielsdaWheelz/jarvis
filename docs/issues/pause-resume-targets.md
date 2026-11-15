# pause and resume targets

problem: a second pause selects only currently pending/waiting requests and
replaces the active pause's targets. requests already stopped by the first pause
are omitted; resume uses only the latest target set.

impact: repeated pause can strand unfinished requests rather than resume them.

evidence: source `8c0bf36`, `MessageStore._apply_control` in
`src/jarvis/messages.py:225–384`; read-only audit, 2026-11-14.

reproduction: persist a pending request, pause, pause again, then resume. inspect
the latest control targets and original request state. no behavioral probe run.

resolved when [slice 1](../one-main-events.md) retains accumulated targets within
one paused period, includes newly paused owner/host requests and resumes only
that set. conversationally stopped requests stay stopped; cancelled actions do
not requeue. use existing control records. prove repeated pause/resume in the
temporary control journey, then delete this record.

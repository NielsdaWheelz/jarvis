# skid reports a rejected close as not_attempted

problem: skid's stop reports `partial.terminal: not_attempted` even when the
native close was attempted and rejected with a code other than
`ClosureConfirmationRequired` (skid `internal/agentcontrol/actions.go`,
`stopFailure`). the stored jarvis evidence therefore reads "not attempted" for a
close that happened to be refused upstream.

impact: jarvis copy treats `not_attempted` as an unconfirmed close, never as
proof that no close was tried; settlement is unaffected (such failures are
`sent` and settle failed with the partial retained).

evidence: skid 056d491 `internal/agentcontrol/actions.go:115-134`.

resolved when skid distinguishes attempted-and-rejected from not-attempted in
its stop partial, or documents the current meaning; jarvis then narrows its copy.

# skid documents an unemitted launch_submitted start stage

problem: skid's pr 1 contract (`docs/herdr-pr1.md`, "retained gateway
operations") names a `launch_submitted` stage in start partials, but the merged
host emits only `resource_created` and `identified`
(`internal/sessions/mutations.go`).

impact: jarvis's closed start partial accepts only the two emitted stages; a
future host that starts emitting the documented third stage would make that
failure uncertain (invalid partial after child start) instead of a known partial.

evidence: skid 056d491 `internal/sessions/mutations.go` (stages set at
`resource_created`/`identified` only); no `launch_submitted` in `internal/` or `cmd/`.

resolved when skid either drops the stage from its contract or emits it, and
jarvis's `AgentStartPartial` matches the settled contract.

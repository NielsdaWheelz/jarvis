# isolated compactor configuration stop loses its cause

status: open, observed 2026-11-17; kernel source repair qualified and published as
`36f9c6b8e4674916d185eb14e522e77d21c3f86f`; production application cleanly stopped.

kernel `run_one_shot` collapses several caught configuration, provider, protocol
and invariant exceptions into `OneShotStopped(configuration_error)`. its public
outcome retains only type and metrics, and the existing default outcome event
does not identify the exception or source location. the compactor therefore parks
without enough evidence to identify the responsible layer.

production run `da07ca83-482e-4b5c-af34-1e6933e75478` parks address `4040+8` at
`2026-11-17T19:32:57.291815Z`. safe log fields are `reason=kernel_stopped` and
`stop_kind=configuration_error`; stored error is `invalid_completion`. the
transient isolated reply and initiating exception were not retained. this does
not prove malformed output, quota exhaustion, authentication failure or an
instruction-file cause.

the application and observer stop cleanly at `19:34:14Z`, retaining resume 9,
the actual pending mail fact, 13,224 admitted leaves, coverage 4,106 and original
nodes/frontiers retained for the retry comparison. no main attempt, action, read,
todo or outbound
reply is unfinished. private `compactor-4040-stopped.json` and
`compactor-4040-rejection.json` retain the stopped state and original rejection.

the qualified repair extends the kernel's existing outcome event with closed failure identity and
bounded installed-owned source coordinates, emitted before usage accounting or
cleanup can replace the initiating exception. consume only that metadata through
a narrow host logger. it retains current stop/park/retry contracts; no transcript,
raw exception prose, new journal or automatic retry.

resolution requires controlled end-to-end proof that distinct responsible paths
remain distinguishable and private payloads stay absent, independent review,
qualified installed diagnostics, then one explicit stopped operator retry and
observed progress through the original node. current account/model observations
can narrow current conditions but cannot reconstruct the lost historical cause.
if the failure recurs, repair its demonstrated cause before acceptance.

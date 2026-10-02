# skid terminal flag mismatch

recorded: 2026-09-30. current source/cli incompatibility, separate from the new
delegation features. no runtime repair or live effect was attempted.

problem: jarvis's `AgentController.read` emits `--terminal` for terminal-source
reads, and `stop` emits it for terminal mode. current skid accepts that flag only
for start; read/stop select terminal or native behavior through their captured ref.

impact: those calls fail argument parsing before reaching the intended target.
the asynchronous wait plan cannot reuse the terminal-read adapter unchanged.
adr 0052's historical client qualification does not establish compatibility with
the currently inspected cli.

evidence: `src/jarvis/agent_control.py` builds those arguments. skid source
`internal/agentcli/run.go` rejects `--terminal` when the operation is not start.
the installed v0.10.7 `skid --help` describes ref-based read/stop selection and
native-only `--history`. deployed jarvis cli bytes were not inspected this turn.

resolved when: the adapter follows the current cli while retaining the requested
terminal/native authority and exact captured ref; native history alone uses
`--history`. update affected binding revisions/contracts under adr 0052 and
qualify against the intended installed artifact. do not silently recapture a
different conversation. [o8](../implementation-plan.md#o8-richer-start-and-asynchronous-wait)
owns this repair; it can land earlier as an independently requested small fix.

# discord login failure exits the service

problem: `serve` exits 1 when discord's login fails, on a connect timeout or a
resolution failure. a cooperative stop while the login is still pending waits
for that failure and also ends `Result=failure`, not the clean SIGINT exit 130.

impact: during a discord or dns outage at startup, `Restart=on-failure` with
`StartLimitBurst=3` in 900 s leaves the unit failed until an operator runs
`reset-failed`. a stop in that window is unclean, so `deploy/activate-release`
refuses until the same inspection and `reset-failed`. with discord reachable
the login completes and a stop is the ordinary clean path. afaict this predates
herdr pr 4.

evidence (2026-09-24, isolated linux qualification of `2a59355`, no discord
reachable): with discord hosts sunk in `/etc/hosts`, a stop during the pending
login took about 30 s and exited 1; with a resolver that never answers and
default timeouts the service crash-looped about 10 s after each start; with a
resolver that hangs 30 s per attempt the stop took 123 s and ended
`ExecMainStatus=130 Result=success`, which is why round 3's clean stop held.

resolved when: a decision exists on whether startup retries the discord login
with backoff while staying stoppable, or exits; and a stop during a pending or
failing login ends `Result=success` in an isolated proof.

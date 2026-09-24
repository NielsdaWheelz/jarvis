# activate-release fails after mutating state on a host whose unit was never loaded

problem: `deploy/activate-release` runs `systemctl reset-failed jarvis.service`
after installing the unit file and switching `/opt/jarvis/current`. on a host
where `jarvis.service` has never been enabled the unit is not loaded, so the
command fails with `Unit jarvis.service not loaded.` and the script exits 1
before `enable --now`, leaving the new unit and pointer in place and nothing
started. the earlier precondition (`ActiveState=inactive Result=success
MainPID=0`) is satisfied by systemd's defaults for an unknown unit, so the
failure is not a refusal but a `systemctl` error after mutation.

impact: none for the herdr cutover: production's unit is enabled, so it is
loaded and `reset-failed` is a no-op there (a failed unit is already refused by
the precondition). a fresh deployment is a manual procedure per
`docs/operations.md`, and this is one more reason it stays manual.

evidence (2026-09-23): the isolated systemd proof in
`docs/qualification/2026-09-23-herdr-pr4.md` (round 3, "fresh host" row):
two identical attempts, then the same script activated cleanly once the unit
was installed and enabled by hand.

resolved when: the line is dropped (the precondition already excludes a failed
unit) or guarded on `LoadState=loaded`, and an isolated fresh-host activation
passes with the unmodified precondition. delete this file with that change.

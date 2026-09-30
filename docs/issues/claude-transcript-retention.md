# claude transcript retention

problem: claude code deletes session transcripts, subagent transcripts and
tool-result files older than `cleanupPeriodDays`, which defaults to 30 days.
dev-server owns only `statusLine`, `autoUpdatesChannel` and `minimumVersion` in
claude settings, so nothing raises it.

impact: every day before the change removes another day of claude history. the
[universal memory contract](../universal-memory.md) captures from activation
onward and recovers missed events from native history, so retention also bounds
recovery after a collector or service outage. deferred v2 backfill can only
import what survives.

evidence (2026-09-28, macbook): `cleanupPeriodDays` is unset in `~/.claude` and
`~/.claude-work`. `~/.claude-work/projects` was created 2026-05-14; its oldest
surviving transcript was last modified 2026-08-28. per claude code's settings
documentation, 0 has been invalid since 2.1.89.

direction: dev-server manages a long `cleanupPeriodDays` on every claude profile
on macbook, arch and devbox, amending its specification's list of managed claude
keys. the setting also retains other claude application data, so its cost is
disk. this lands separately, before universal memory.

resolved when: every claude profile on the three hosts reads the managed value,
and a dated dev-server record names the value, hosts and revision.

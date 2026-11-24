# historical compaction parked on a native event burst

the installed range recovered on november 23. [adr 0093](../decisions/0093-subscription-model-refresh.md)
records the separate transport qualification.

on 2026-11-20 at 14:16:34 utc, production release `e7f5916` parked compaction
at `8112+8`. run `3fd97c10-6e07-421a-bc23-f701adfbc1b5` had eight tasks,
one provider turn and 154.169 seconds elapsed. both token counters were absent.
at 15:13 utc the same park persisted. the ready prefix ended at 8,184 of
50,435 admitted positions. this affects the [historical capacity observation](memory-usefulness-evaluation.md).

the `jarvis.service` journal recorded `protocol_defect` in provider `f42d6cf`,
`codex_sdk.py`, `_read` line 2679 → `_publish` line 2744. that branch fires
when either the pending event count or the aggregate queued bytes exceeds its
bound. the trace does not distinguish those conditions. jarvis recorded
`configuration_error` and persisted `invalid_completion` at the node. the
contained stock logs showed an active stream. the account charge is unknown.
[provider source](https://github.com/NielsdaWheelz/llm-calling/blob/f42d6cf/src/provider_runtime/agent_runtime/codex_sdk.py#L2743)

inspect the original diagnostics with `journalctl -u jarvis.service --since
'2026-11-20 14:16:30 UTC' --until '2026-11-20 14:16:38 UTC'` on dev-server.
resolve when both predecessor limits have independent reproductions, the
candidate drains the qualifying burst in order, and installed readback proves
the parked parent completed and later historical construction advanced. the
historical trigger remains unknown unless further incident evidence identifies
it. [implementation and acceptance](../compactor-burst-recovery.md)

the predecessor's count and byte failures and the candidate's ordered
drain passed independent socket and ordinary compactor checks. the isolated
`7e9d887` guest closed synthetic `0+8` after one clear, with xid 1179
followed by independent xid 1180. [candidate evidence](../decisions/0093-subscription-model-refresh.md#candidate-evidence)

at 19:38 utc on november 23, a repeatable-read production snapshot found
the original `invalid_completion` at `8112+8`, its parent `(3,1014)`
absent, 8,184 of 80,291 positions covered, and 16,308 committed nodes.
the retained syslog includes the original failed run. across that log and
its successor there was no later compaction preparation, inference or
commit before this check. the two november 23 writer stops correspond to
the google credential changes. the mac retains the original run in
`~/.local/state/jarvis/qualification/adr0093-production-20261123/original-incident.log`
(sha-256 `f97a07448a46eb4917024761b333f7715f48b6aa3ad3b76e67e330a10d820a2c`).

the owner authorized the exact rehearsed `7e9d887` release and one
conditional retry. web pause 29 committed at 20:39:24 utc. the stopped
cut retained schema `0018`, the pause, the park and the 8,184-position
prefix. the application remounted the new stock socket. with memory serving
and the assistant stopped, the 20:42:24 read found the exact park and absent
parent. the operator ran `memory retry-compression` once. stopped readback
found a clear error, 8,184 covered and 84,472 admitted. the assistant
restarted under pause 29. the mac evidence directory above holds the
original before and after reads in `retry-once.log`.

the producer now names the mac reader `sha256:4c6ceba20b63c0b6890cc385c3601609fe0dd7311fce9d17728e38e2388eafcf`
for the target dependency lock. backup `20261123T204311624338Z-d92d8d041e5e4d39bd9b23f363f78fbb`
restored from r2 in 105.258 seconds and from the held copy in 51.114 seconds.
both reopened an original event and a note at coverage 8,184/84,472.
the 12-hour backup timer is enabled again.

owner web resume 30 committed at 20:54:35.211 utc. the first eight-task
attempt was interrupted after 5.838 seconds of inference. foreground work
ran for 8.587 seconds, then the scheduler prepared the batch again.
the commit logged at 20:55:06.811 included `8112+8`, level 3 index 1014,
transaction `2399982`. the 20:55:25.205 commit included the disjoint
historical parent `8148+4`, level 2 index 2037, transaction `2400027`.
at 20:55:26.475 the prefix was 8,204, up from 8,184, with 16,365 nodes,
84,996 admitted positions and a clear error. the selected release was
`7e9d887` at schema `0018`. capture received the resume and recovery notices.

zero turns reported a recovered buffer wait from resume through verification.
production burst handling under pressure remains unwitnessed. the november
20 trace still cannot distinguish the count limit from the byte limit.
the mac evidence includes `recovery-reads.ndjson`, `recovery-node-xids.json`
and `recovery-commit-journal.log`. [busy and quiet capacity measurement](memory-usefulness-evaluation.md#installed-terra-observation)

at 20:57:50 the worker parked at a different address after a completed
model turn returned the wrong address set. both recovery transactions
remained visible. [new park at 8232+8](compactor-address-mismatch.md)

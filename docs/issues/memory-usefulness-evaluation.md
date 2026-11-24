# memory usefulness and realistic-load evaluation

the 2026-11-19 [freshness design](../decisions/0092-memory-freshness.md) takes
on recent correction recall, index coverage and historical capacity. broader
usefulness under ordinary work remains open.

the [private replay](../decisions/0092-memory-freshness.md#partial-private-replay)
ran for 17 minutes with the fixed model under favorable idle conditions. leaves
arrived faster than the prefix advanced before an uncertain model outcome ended
the authorized run. the full burst remains unqualified. installed measurement
still requires a predeclared ordinary busy day and its following quiet period.

## installed capacity observation

the predeclared busy interval is `2026-11-20T17:00Z` to `2026-11-21T02:00Z`
(friday 09:00–18:00 pacific). the quiet interval ends `2026-11-21T17:00Z`
(saturday 09:00 pacific). judge whether the actual activity was representative
before interpreting the result.

the transient read-only observer `jarvis-0092-capacity-20261120.service`
is scheduled to record all three samples in its journal. preflight at `2026-11-20T05:45:55Z`
confirmed release `d16a5077`, schema `0018`, resume 20 and an unparked compactor.
5,801 of 49,006 admitted leaves were covered, leaving 43,205 leaves and 86,427
aligned nodes pending. the oldest uncovered arrival was almost 30 hours old.
preflight is outside the measurement window. use the [operations procedure](../operations.md#chronological-capacity-observation)
to assess scheduler time and the fixed cutoff after the final sample.

on november 23 the original observer samples were recovered from dev-server's
rotated `/var/log/syslog.1`. all three ran on `e7f5916` under web resume 24
and recorded the park. the busy interval admitted 11,169 positions, from
56,303 to 67,472. at busy end the observer counted 8,184 covered positions
and 16,308 of 134,938 aligned nodes through that cutoff. none of the 118,630
missing nodes committed in the next 15 hours. 59,288 busy-end positions
remained uncovered and the oldest aged from 49h59m40s to 64h59m40s. 122
later positions arrived. the observer counted zero owner web requests in
both intervals. this window measures the parked release. the mac retains
the samples in `~/.local/state/jarvis/qualification/adr0093-production-20261123/20261120-observer.log`
(sha-256 `764fbc39f9741c9568a02fbde06744b2e7899192483726c34cbb5a488ef4d367`).

the same syslog covers the predecessor before the park, from 05:53:00 to
14:16:35 utc on november 20. its 172 commits built 2,383 leaves and 2,352
parents. of 28,795 seconds offered to the compactor, 28,674 seconds were
inside native inference, including setup and cleanup. preparation took 8
seconds and commits took 78. the 193 observed turns included 21 without
output usage. the installed terra rate still needs its own observation.

## installed terra observation

on november 23, before the first sample, the operator selected tuesday
november 24, 09:00–18:00 pacific as the busy period and wednesday 09:00
as quiet end. the three utc boundaries are november 24 17:00, november 25
02:00 and november 25 17:00. freeze the admitted count at the second
boundary. report the oldest uncovered age, complete aligned-node count,
later arrivals and actual scheduler time. judge representativeness from
the observed workload and record any capture release or catch-up burst.
the read-only transient `jarvis-0093-capacity-20261124.service` was armed
on dev-server at 20:47:33 utc on november 23. its invocation is
`93e88d5228a843d297f7a32032f0cd11`. the unit retains each phase snapshot
and hourly scheduler journals under `/var/lib/jarvis-0093-capacity-20261124/`.

the dates were confirmed after recovery of `8112+8`. before the window,
terra ran for just over three minutes under resume 30. eight commits built
61 free leaves, 77 free parents, 24 inferred leaves and 40 inferred parents.
the prefix advanced by 85 positions. of 185.292 seconds offered to the
compactor, inference occupied 180.985, preparation 0.495 and commits 3.531.
the tenth model turn completed with a [mismatched address set](compactor-address-mismatch.md)
and parked the worker. this short interval supplies a timing breakdown.
the day and night observer remains armed to measure admissions and parked
time at the declared boundaries. the capture operator confirmed the
november 23 mac replay added zero central records.

the november 24 calendar cut selected `43ed919/0019` at 01:32:13 utc,
before the first scheduled sample. at 01:34:15 utc the same sampler
invocation was active with zero phase files. production was under web
pause 31 with 93,770 admitted positions, 8,269 covered and 16,510 built
nodes. the packaged compactor was still terra/medium v6. its [second
park](compactor-address-mismatch.md) survived the cut. at 01:36:43 utc
the exact query from the running sampler succeeded as its postgres user on
`0019`. all three scheduled samples remained pending. this separate mac
preflight is `window/sampler-prewindow-43ed919.json`, sha-256
`ea9e96a7561f3d0cb3ddf2357e33cc347cb40a7057760cb06978f63eea488276`.
keep the original schedule and attribute each boundary and interval to
the actual release and control state. the recovered `7e9d887` interval above has its own
timing evidence. the capture team's separate `0019` baseline uses the
same dates to count incoming records and retained bytes.

the [adr 0100](../decisions/0100-host-bound-summary-fields.md#c-production-recovery-and-capacity)
fixture exercised the same postgres snapshot query. it held cutoff 8 through
quiet end, with prefix 8 and 14 of 15 aligned nodes. the one-parent deficit
and three later arrivals were measured separately. the
candidate's production window waits for a separately verified recovery.

the generation-2 archive was selected on `58b9ebe/0021` at 04:13:25 utc,
before the first scheduled sample. at 04:15:05 it contained 18,507 active
positions, 88,640 retired records, zero nodes and a clear mark under owner
web pause 33. keep the pre-window rewrite in the observation record.
compare quiet-end progress only within the same generation. measure
construction on the actual selected release and annotate any later switch.

## broader usefulness evaluation

after the [conversation capture cut](../decisions/0098-conversation-capture.md),
count external retrievals at the memory service during a predeclared observation
window. capture-side tool rows cease to measure them. use content-free counts or
mark the metric unavailable. measure admitted bytes and positions separately from
actual model usage and report the coverage of each window.

problem: current integration qualification cannot establish whether memory remains
useful under the owner's realistic mixture and volume of scientific, personal,
creative and coding work. bounded tree coverage and successful tool calls do not
prove that useful detail survives compression or reaches an answer.

impact: relevant old evidence, corrections or preferences may be missed or
outcompeted; compression/capture backlogs may impair ordinary use. current work
must report integration behavior without claiming those broader outcomes.

evidence: [memory delivery](../memory-delivery.md) deliberately scopes current
acceptance to live api/mcp/jarvis/native/nexus composition, content-contract cases
and recovery. no realistic-load or usefulness evaluation has been run here.

the earlier rollout exposed a startup cost: one host collector serializes
complete native baselines and initial source reads. macbook codex-personal
activated at `2026-11-15T06:51:10Z`; its first normal inventory finished at
`07:04:07Z`, before codex-work's baseline could run. new activity in already-active
claude lanes waited behind that scan. this is observed rollout behavior, not a
steady-state latency measurement. later evaluation should distinguish initial
baselining, cold collector recovery and ordinary polling; no throughput or latency
claim follows from those early functional checks. the subsequent
[discovery repair](memory-cold-start-scan.md) has separate normal-turn latency
evidence; it does not complete this broader evaluation.

the reported 102-minute production window added 4,597 leaves while startup
coverage advanced by 374. a read-only check of the retained interval
`[14997,19594)` found 4,018 tool-call/result parts and 234 source parts eligible
for embeddings. 879 source parts exceeded the 2,048-byte free-copy bound before
framing, including 819 tool-result parts. at the reported cutoff, 45 of 1,103
eligible source parts had vectors. of 311 distinct owner text messages, 287
were wholly beyond startup coverage `[0,1561)` and had no embedded part. their
originals remained available for keyword matching and direct reads. recall of
a particular correction was untested.

at `2026-11-19T05:57:52Z` the construction frontier was 2,222 of 21,221, with
no recorded compaction park. the first source outside it had arrived at
`2026-11-18T19:59:49Z`. 45 of 1,217 eligible source parts had vectors.

at `2026-11-19T08:04:08Z` the frontier was 2,832 of 25,252 with no park.
45 of 1,375 eligible source parts had vectors. the oldest eligible part still
missing a vector had been admitted 14 hours earlier. across the original
4,597-leaf interval, treating each position as a possible startup cutoff, the
last 32 leaves contained no owner text at 2,912 cutoffs. the longest run
without owner text reached 636 leaves. this measures selection under tool load.

resolved when: a separately scoped later pr evaluates representative owner-approved
content and activity, records missed evidence and operational costs, and states
what the results support. use a small meaningful evaluation; no framework or
standing model tournament is implied. [historical import](memory-historical-import.md)
and [backup/restore](memory-backup-restore.md) remain separate deferred work.

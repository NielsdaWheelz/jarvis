# unexplained native defect during candidate qualification

status: open; accepted for [f2 reliability/integration](../implementation-plan.md#v2-finishing-prs)
under adr 0075. retain bounded content-free diagnostics, reproduce and repair the
owning layer; the [contract](../runtime-reliability-and-integration.md#b-native-diagnostics-and-repair)
records implemented diagnostics and isolated fault proof. the selected stack
subsequently completed representative worker, workspace and restart journeys.
the original exceptions remain unknown.

[adr 0077](../decisions/0077-production-acceptance-and-fresh-reset.md) permits final
acceptance with this issue explicitly OPEN if safe diagnostics and representative
actual reproduction cannot identify the historical cause. new demonstrated defects
still require repair. this is an accepted residual risk, not issue closure.

problem: one native turn failed after accepted callbacks, but retained evidence
identifies only `NativeDefect`; its exact cause cannot be reconstructed.

impact: the request safely parks and needs named operator repair. the missing
cause prevents an owning-layer fix or a claim that this failure was resolved.
it is not a proved model-output defect. later passing journeys qualify their
own paths; they do not make this failed run green.

evidence: slice 3 candidate `c0272689a7657e31344ecb6175615fe78e427503`, attempt
`652a219d-9b0b-4422-a9b2-6b6ae30ca4fb`, 2026-11-15 19:19 utc. `agent.info`,
one `agent.start` and one `work.update` have original durable replies. no terminal
seal or wait registration followed. the host fenced the attempt, parked the wake
and delivered its failure notice. ordinary logs retain the class; the ephemeral
contained thread cannot be reopened. the separately demonstrated loss of
host/path/timing from the authored todo brief has its own content repair and is
not established as this exception's cause.

named operator release followed explicit owner correction. accepted effects were
preserved; the obsolete wake/todo was stopped/deleted without replaying launch.
a task-only private diagnostic wrapper rethrows future failures unchanged and
records only controlled error/frame/schema coordinates. the corrected scheduled
journey reached worker observation across restart; final evidence belongs to
[slice 3](../delegated-follow-through.md#implementation-evidence--2026-11-15).
temporary diagnostics were removed after qualification, not installed as a feature.

slice 4 adds two retained failures under candidate `a649e58`: attempts
`27504691-87c7-4d88-b6f0-7b692a8d3216` and
`504fc190-b269-477f-ad53-8f700d85b488`, 2026-11-16 utc. the first retained its
native local commit; the second left an actual git merge conflict. a temporary
forwarding-only diagnostic narrowed the second to kernel `run_native` line 510,
jarvis `NativeRunner.record` line 309 and `PostgresNativeJournal.record` lines
1105–1107: `public progress violates its message contract`, with pydantic root
`value_error`. the actual validator was not retained; duplicate input ids and
nonempty progress dispositions are distinct candidates. the application already
requires progress `input_outcomes=[]`. this is no basis for relaxing validation
or claiming the older slice-3 failure has the same cause.

explicit named operator release and a new inspect-state owner request completed
the existing merge without replaying its original edit/commit. both original
attempt/fence snapshots and callback replies remained unchanged. final successful
continuation qualifies that path, not the failed turns. see [slice 4 evidence](../private-notes-and-rolodex.md#implementation-evidence--2026-11-15).

resolved when: reproduce with sufficient content-free evidence to identify the
actual owning layer, repair any demonstrated defect there and verify the affected
path, fencing and original-effect preservation. no guessed exception-text
logging, automatic unpark, effect replay or fallback output closes this issue.

f2 source repair (2026-11-16): the two candidate root validators now use distinct
static codes. all eight selected validator conditions/messages/order and exact
`model_json_schema()` bytes are preserved. one bounded content-free projection
logs before run parking, terminal failure persistence and provider command
failure propagation. its fixed class/code/location/source-coordinate allowlists
exclude private messages, inputs, extra property names and unknown classes/codes;
provider public error roots now exit nonzero without raw tracebacks.

isolated proof uses the actual native runner/kernel, a controlled public
app-server socket and disposable postgres at migration `0013`. after one accepted
billed-once read callback, duplicate input dispositions and nonempty progress
dispositions produce distinct diagnostics; a malformed sealed terminal retains
its original seal and reports the terminal boundary. all three fence/park their
requests, reject stale callback authority, ignore late malformed commentary and
retain original replies/read receipts byte-exact across recovery, with one read
executor entry. this proves paid-read preservation, not a write-callback fault
or historical cause. command subprocess probes reproduce the old provider-message/
cause leak and verify the new safe exit; bounded helper probes cover unknown
property/code/class names, cause cycles, all limits and valid json. source static
checks pass. the f2 contract owns final artifacts and temporary-probe disposition.

the [installed write/restart journey](../runtime-reliability-and-integration.md#recovered-final-and-reset-disposition)
reused the original worker, workspace and send receipt. those successful paths
and the separate explicit usage, lineage and cross-root incidents did not
reproduce the historical exceptions. the diagnostic issue remains open under
adr 0077.

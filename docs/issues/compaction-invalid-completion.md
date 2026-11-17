# compaction parked without a discriminating rejection reason

status: open, 2026-11-17.

problem: the compactor's original `invalid_completion` park combined a stopped
kernel run, caller result-schema rejection and dynamic batch-address rejection.
the diagnostic gap is now repaired and installed; the historical cause remains
unknown and recovery has started. the generic durable park stays unchanged.

evidence: the operator observed production at 09:11:49 utc with
`compaction_error={"start":2112,"count":64,"code":"invalid_completion"}`,
`view_through=2233`, `leaf_count=3039`, zero native main attempts and the genuine
owner request `2487c506-4aef-4f2e-9018-554ada7377d0` still pending. the original
reply is unavailable through the pinned public ephemeral one-shot contract.
the actual cause is unknown; none of these rejection branches is established.

impact: complete memory preparation and main dispatch remain pending, so the real
combined journey cannot begin. qualified source `c544f68` is installed on both
host/application. one supported stopped-operator `memory retry-compression`
clears only the park, preserving source/node/leaf fingerprints, coverage 2,233,
genuine `resume` sequence 9 and the pending owner request; the command makes no
model call. this adds no automatic or outer retry and waives no failure.

the source diagnostic now records the host run id/requested address and a closed
`kernel_stopped` reason with public `OneShotStopKind`, `result_schema`,
`address_duplicate` or `address_set_mismatch`. it retains no input, output,
exception text or provider transcript and leaves the durable park unchanged.
temporary isolated `0013` postgres/runtime-role and actual-kernel checks cover
protocol/quota stops, duplicate/missing/wrong addresses and successful completion;
the defensive caller-schema branch uses explicitly controlled result corruption
after actual kernel completion. every rejection preserves originals and commits
zero paid/free nodes or frontier progress. these checks do not explain production.

at 09:47:54 utc the level-6/index-33 node (`2112+64`) is absent; at 09:49:15 it is
present, coverage reaches 2,241 and `compaction_error` is null. this proves genuine
parent recovery. zero main native attempts and the pending owner request still
leave preparation/journey acceptance open. the original cause remains unknown.
the [f2 implementation evidence](../runtime-reliability-and-integration.md#compaction-rejection-diagnostic-and-observed-recovery)
owns exact source/ci/installation and fixture-disposition details.

resolution still requires qualified execution past the blocked preparation, not
just clearing the park or building one parent. classify and repair any newly
reproduced rejection before another explicit retry. the installed diagnostic and
recovery observations do not recover or explain the original rejected reply.

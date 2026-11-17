# compaction parked without a discriminating rejection reason

status: open, 2026-11-17.

problem: the compactor's `invalid_completion` park combines a stopped kernel run,
caller result-schema rejection and dynamic batch-address rejection. the existing
park preserves its failed address but does not distinguish those boundaries.

evidence: the operator observed production at 09:11:49 utc with
`compaction_error={"start":2112,"count":64,"code":"invalid_completion"}`,
`view_through=2233`, `leaf_count=3039`, zero native main attempts and the genuine
owner request `2487c506-4aef-4f2e-9018-554ada7377d0` still pending. the original
reply is unavailable through the pinned public ephemeral one-shot contract.
the actual cause is unknown; none of these rejection branches is established.

impact: required memory preparation is blocked, so the real combined journey
cannot begin. preserve the park until the qualified diagnostic repair is
installed. one explicit stopped-operator `retry-compression` is authorized for
diagnostic recovery; this adds no automatic or outer retry and waives no failure.
classify and repair any newly reproduced failure before another retry. the
unrecoverable original cause remains unknown even if recovery succeeds.

the source diagnostic now records the host run id/requested address and a closed
`kernel_stopped` reason with public `OneShotStopKind`, `result_schema`,
`address_duplicate` or `address_set_mismatch`. it retains no input, output,
exception text or provider transcript and leaves the durable park unchanged.
temporary isolated `0013` postgres/runtime-role and actual-kernel checks cover
protocol/quota stops, duplicate/missing/wrong addresses and successful completion;
the defensive caller-schema branch uses explicitly controlled result corruption
after actual kernel completion. every rejection preserves originals and commits
zero paid/free nodes or frontier progress. these checks do not explain production.

resolution requires the qualified content-free diagnostic at the actual rejection
boundary, installed observation of the explicit diagnostic recovery and qualified
execution past the blocked preparation. any newly observed rejection also needs
its responsible repair. source proof alone does not settle the operational
blocker or recover or explain the original rejected reply.

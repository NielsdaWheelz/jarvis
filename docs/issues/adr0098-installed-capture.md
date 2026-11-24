# one macbook chat remains parked after the capture rollout

on november 24 at 04:21 utc the installed `0021` service still reported
`unsupported` for top-level `macbook/claude-work2` conversation
`b7e727d1-b408-444c-8ee8-8ddb3a5b62fe`. newer speech from this chat will
wait at its existing checkpoint. 31 live parts remain after historical
cleanup. the other 39 named claude recoveries closed under v3.

v3 rejected two command results containing nul. a read-only replay through
`403b1f7` matched the original checkpoint digest, skipped both results,
and reached the end of the 34-event suffix with 13 eligible records.
the v3 recovery excluded this separate chat. the v4 rollout preserved
its park. [installed capture](../decisions/0098-conversation-capture.md#installed-cut-november-24-2026)

close when the ordinary retry of this conversation advances from its saved
checkpoint, the collector acknowledges the suffix, and a later utterance
reopens once with no raw tool records. the private `known-work2-nul-*`
receipts are in `qualification/capture-production-20261124/` on macbook.
[retry procedure](../operations.md#memory-operations)

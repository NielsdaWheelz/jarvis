# contained host imports consume its stop and start budgets

two starts of the selected x64 candidate timed out in the stock unit's
20-second publish window on a heavily contended mac guest. cleanup also
reached its 10-second deadline. the same installed bytes started when
contention fell. the ordinary installer succeeded after the operator recorded
the failures and reset only the stock unit's start limit.

`deploy/codex-host` imports the provider and httpx before selecting its
command. cleanup needs neither. four fresh interpreters on the same guest
loaded the predecessor in 7.67 and 8.68 seconds and the candidate in 9.01
and 7.06. they shared the guest page cache. these measurements identify
avoidable work. the journal does not isolate which phase caused the timeouts.

close when cleanup loads neither dependency, the verified start path
retains its catalog and tier checks, and the ordinary unit completes stop
and start under representative contention with measured time to spare.
the private 0093 release evidence retains both failed journals,
`paired-stock-imports/imports.json` and the quiet cycle. [operations](../operations.md#install-and-configure)

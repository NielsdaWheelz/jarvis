# unfinished codex tool items are treated as permanent codec errors

priority: p2; native occurrence remains unconfirmed. reviewed 2026-10-11 against
provider-runtime `d9550d9` and merged `5aecc2b`.

status: source fixed in the isolated v2 candidate; qualification remains open.

problem: `_codex_archive.py:660` rejects an `inProgress` tool item as
`unsupported` when its enclosing turn is interrupted/terminal. the accepted
capture contract requires stopping at an unfinished item and returning the
stable preceding prefix, without skipping forward.

impact: this native state would discard a usable prefix from the read and cause
the collector to park permanently, rather than wait for a later complete read.

evidence: a synthetic completed answer followed by an interrupted turn containing
an unfinished mcp tool item makes the entire codec read fail. no live stock
0.160.0 observation establishes that it persists this combination; confirm its
occurrence before claiming a reproduced fleet incident.

source repair: both native history shapes return the stable prefix before an
unfinished tool item; completion preserves preceding ids/digests. controlled
cases pass. real capture/retry and stock native persistence remain unrun;
non-occurrence does not establish impossibility. see the
[candidate evidence](../universal-memory.md#memory-repair-source-candidate).

resolved when: the codec preserves completed preceding events and reports an
unfinished tail as not caught up. never skip the unfinished item to capture later
events. record actual stock persistence separately, including an unconfirmed result.

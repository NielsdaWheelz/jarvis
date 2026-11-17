# oversized memory-view pages reenter captured history

status: open, observed 2026-11-17; narrow repair in isolated qualification.

normal claude startup orientation spills a roughly 63-kb `memory_view` response
to its native tool-result file. reading that file to finish orientation produces
an ordinary `Read` result. the archive recognizes direct memory-tool results as
content-free references, but retains this reread as ordinary tool output. the
shared tree therefore receives copies of its own summaries.

exact native call/result lineage and central tree membership prove two cases:

- devbox conversation `1a613a98-3b9d-4b57-88b5-5194b19f3083`, call
  `toolu_01LWtEQaXU8rRhhvPmWRipTE`: four parts at positions 5528–5531,
  30,085 retained bytes, 32,509 omitted characters.
- macbook conversation `cee38868-5441-4143-ae06-91ad6392fbff`, call
  `toolu_016LXDa5VENXEVZauxBmHNiw`: four parts at positions 5980–5983,
  30,147 retained bytes, 33,066 omitted characters.

private `saved-memory-view-tree-membership.json`, sha256
`4b113a40191c68cf0353d8e297aab854b35aff5a7f21f5dbfece9a15a56e9f93`,
binds the retained parts to actual tree leaves. original native transcripts bind
the direct memory-view spill to the exact saved-file reread. this proves those
eight leaves contain feedback; it does not measure their share of preparation
latency. no numeric client token threshold is established by the spill notice.

the proposed responsible-layer repair lowers only view-page packing to 16 kib,
preserving whole nodes, frozen coverage and opaque cursor continuation. retain
the common 64-kib result/admission bound and complete open/zoom availability:
valid originals can require roughly 57 kib. the trade-off is more page reads.

resolution requires real-postgres red/green proof of bounded actual framing,
complete frozen pagination through appends/cutoffs/stale cursors, unchanged
larger-original reads, independent source review, and a representative actual
claude consumer completing the view inline without saved-result rereads. the
planned consumer uses strict fixture-only mcp, only `memory_view`, disabled
builtins and no session persistence; its result qualifies that restricted client,
not the default tool catalogue or a numeric spill threshold. remove only the new
temporary probes after qualification. large exact reads and
voluntary copies can still spill or reenter history; this repair does not claim
general taint tracking or eliminate every possible memory feedback path.

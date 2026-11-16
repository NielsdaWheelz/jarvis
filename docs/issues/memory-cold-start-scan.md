# memory initial-inventory and long-read latency

status: ordinary discovery starvation repaired and live-qualified on macbook and
dev-server, 2026-11-15. indivisible initial inventory and individual native-read
cost remain documented limitations; broader load evaluation stays deferred.

problem: full native baseline inventory and a single archive operation can still
take longer than the collector's cooperative 30-second content slice. paging
reduces round trips but retains complete prefix/identity validation. initial lane
activation remains one atomic inventory, with no per-head persisted progress.

impact: a slow native operation can delay the next discovery cycle. initial
activation delays its future-only cut; earlier activity is excluded. this does
not mean healthy established lanes remain blocked by unreadable conversations.

evidence: before repair, dev-server work2's first inventory took about 3 hours
41 minutes, establishing 190 boundaries and retaining 21 unavailable baselines.
a completed normal turn then remained undiscovered for over an hour. the provider
performed roughly one rpc per item, and the collector read old histories before
discovering later conversations/homes. macbook had 2,184 old claude-work histories
ahead of later profiles; hourly hints could expire during the sweep itself.

merged provider paging preserves forward barriers and exact digests. reverse
traversal was rejected because a later oversized item could incorrectly park a
readable prefix before an unfinished barrier. an isolated stock fixture reduced
total calls 261→23 without changing events; that is not a fleet latency claim.
paging alone still yielded approximately 792/415-second model→archive-receipt
delays for fresh macbook/dev-server turns.

installed b6cf4b3 now discovers all active homes before a cooperative content
slice, alternating recent activity with oldest waiting work. pending head repair
gets one operation; failed/parked work cannot produce a false caught-up hint.
one rotating pending-lane activation follows active work. the trade-off is more
metadata requests and slower background drainage for prompt new discovery.
12 temporary scheduling cases, two real authenticated http/postgres/native-file
journeys, retained regressions, full checks and independent review pass.

one fresh normal turn per online host then passes exact capture, checkpoint,
search and actual native mcp opening. stored archive receipts follow model
completion by 67.49 seconds on macbook and 64.63 on dev-server; committed visibility
is observed within 23.91/30.05 seconds of inventory observation. these are
observation bounds, not exact commit clocks or a sub-minute end-to-end guarantee.
all old cuts/originals are preserved. see the
[installed evidence](../universal-memory.md#installed-collector-repair-qualification).

remaining: measure a fresh initial inventory when another approved lane is
activated, and inspect any concretely observed long single operation. no new
whole-fleet benchmark, reset, backfill, second collector or weakened validation
is authorized by this record. resolve this residual issue when the ordinary
activation/read journey demonstrates acceptable delay with identity coverage,
immutable cuts and exactly-once ingestion intact, or adopt a specific further
requirement from observed evidence. one passing small turn does not establish
large-backlog or fresh-inventory performance.

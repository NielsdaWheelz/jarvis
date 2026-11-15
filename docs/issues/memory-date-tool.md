# memory date tool overlap

status: deferred interface question; owner chose to keep the current tools,
2026-11-15.

problem: `memory_date` may overlap timestamp metadata already available when
opening source records and notes. a separate operation adds a tool-selection
choice; no observed retrieval failure establishes that it should be removed.

evidence: the [retrieval contract](../universal-memory.md#6-retrieval) defines
`memory_date(position)` as a lookup of source occurrence and central receipt
times, identifying note creation time separately. it is not date-range search.
its direct tree-position lookup differs from opening a record by identity, so
overlapping metadata alone does not prove complete redundancy.

resolved when: a later interface review decides whether that distinct lookup
earns its place, retaining it with a clear rationale or explicitly approving a
consolidation that preserves position lookup and the meaning of each timestamp.
this issue authorizes no removal, renaming, schema change or implementation work;
all six memory tools remain unchanged.

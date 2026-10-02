# adr 0059: replace the recaller with shared reranked search

[adr 0062](0062-simplify-memory-policy-and-retrieval.md) supersedes learned reranking, its extra attempt allowance and model-selection requirement.
see the [current contract](../universal-memory.md) for implementation.

[adr 0061](0061-simplify-memory-recovery-and-capture.md) supersedes this record's
background dreamer read recovery (main paid-read barriers remain). the
[current contract](../universal-memory.md) consolidates the implementation target.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved removing the recaller and upgrading the shared
  search tool with keyword/semantic retrieval, deduplication and reranking.
- supersedes adr 0058's retained automatic recaller and no-reranker choices,
  adr 0057's first-search arguments, and the affected baseline recall, admission,
  tool-budget and retrieval rules in SPEC 4/6/7/9. replaces the earlier partial
  search fallback with explicit failure of any required retrieval stage.

## decision

remove the recaller, its automatic pre-input pass and its reserved capacity.
main's full and scheduled read-only plans use `memory.search` and `memory.open`;
external agents use their mcp equivalents. the caller owns query formulation,
evidence interpretation and follow-up. no mandatory search on each message,
context fork, `memory.recall` wrapper or replacement search agent.

one service function retrieves keyword and semantic candidates, deduplicates
exact identities, reranks them with one fixed configured model, and returns
bounded evidence. a reranker changes order, never stored wording or provenance.
the shared api is query, optional filters and `limit` (default 10, maximum 20).
candidate pools, model selection and limits are server policy. open supplies
exact records and paged lineage. internal and mcp callers share the bounded
result format; retire internal full-text/one-mib results.

search remains one `Read + BilledOnce` invocation internally, covering embedding
and reranking. preserve existing receipts and uncertainty barriers; no stage
journal or automatic retry. a required-stage failure is an error, never empty
success or an alternate ranking path. empty successful retrieval skips reranking.
open remains available independently. the [contract](../universal-memory.md#6-retrieval)
owns exact bounds, tool grants and hard cutover.

the rememberer and dreamer retain their distinct jobs. the dreamer uses the same
search pipeline, restricted to notes/summaries; its first search returns at most
two results. main alone keeps direct saving in its full plan.

## costs and selection

main gains retrieval responsibility and consumes context/tool calls itself;
automatic recall is no longer guaranteed. removing the recaller saves its model
pass and summary, while reranking adds inference latency, cost and a dependency.
ranking cannot recover evidence excluded from the initial candidate pool and
does not establish truth, authority or current state. bounded previews require
more opens. outages now fail search instead of silently changing the pipeline.

root selects one model/runtime using the small designer-owned query set and
records quality, latency, cost and supported input bounds before implementation.
if hosted, name its account/project in the existing processor declarations before
any corpus disclosure. no second jarvis service, provider router or fallback.
the former model-selection issue was retired by adr 0062, which defers this
requirement. the text below records the earlier decision, not current work.

## implementation and acceptance

root removes role/context/trace wiring and only the recaller's admission terms,
retaining canonical history reconstruction and write-gate reservations. the hard
cut drains unknown old calls and waits for old rolling charges to expire before
writing an empty journal under the new limits; it never resets live charges.
c owns shared retrieval/reranking and focused checks, d the shared bindings,
root main dispatch/integration, f query/result guidance and selection examples.

verify absence of the recaller, both main plans, role restrictions, retrieval
versus ranking quality, actual rendered bounds, failures and paid-search replay
within the existing scoped regression groups. no new harness, action, table or
runtime change is introduced by this documentation update.

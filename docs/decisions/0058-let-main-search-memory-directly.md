# adr 0058: let main search memory directly

[adr 0062](0062-simplify-memory-policy-and-retrieval.md) supersedes ranking and common retrieval-policy requirements.
see the [current contract](../universal-memory.md) for implementation.

amended before implementation by
[adr 0059](0059-replace-recaller-with-reranked-search.md): remove the automatic
recaller and add shared reranking. its retrieval and budget contract supersedes
the affected choices below; direct main read access remains accepted.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved giving main the existing memory search/open
  tools during the universal-memory walkthrough.
- amends SPEC 7.1/7.3, adr 0056's unchanged scheduled-read envelope, and the v2
  roadmap's proposed on-demand `memory.recall` agent wrapper.

## decision

grant `memory.search` and `memory.open` to main's full and scheduled-wake
read-only plans. preserve the automatic isolated recaller before owner input.
main may follow up whenever new information warrants it, within its existing
tool, context and admission budgets. `memory.save_note` stays full-plan only.

search is an ordinary retrieval function: keyword and vector queries, existing
per-mode ordering, identity deduplication and bounded results. the caller decides
whether to reformulate, open sources or stop. no search agent, model reranker,
`memory.recall` tool or nested model invocation is added. main, recaller and
external clients use the same retrieval implementation over the shared corpus;
jarvis uses its internal bindings, never its own mcp listener.

route main's calls through the existing automatic-read dispatcher and durable
read recorder. retain binding replay policy, paid-query uncertainty barriers,
serial execution and evidence-only results. keep the isolated dispatcher and
its candidate tracking scoped to isolated roles. add no action or table.

## evidence and costs

v2 already proposed on-demand recall, but through a fresh recaller invocation.
the existing search implementation does database retrieval and query embedding,
not agent reasoning. main already has the context needed to choose follow-up
queries. reusing those primitives avoids another model call, nested admission
and an extra summary between main and its evidence.

the cost is that main spends its own context and tool calls on retrieval; the
automatic recaller can duplicate some of that work. semantic queries retain their
embedding cost. a delegated retrieval agent could isolate long investigations,
but is deferred until a measured need justifies its extra contract.

## implementation and acceptance

root owns main grants, automatic-read routing, prompt/compatibility revision and
integration; package d owns shared bindings, c existing retrieval and replay
checks, f concise search/open guidance. verify both main plans can search/open,
scheduled turns still cannot save, paid reads replay without another embedding
call, unknown reads do not redispatch, and results confer no write authority.
use the existing scoped regression groups; no separate harness. this decision
changes docs only.

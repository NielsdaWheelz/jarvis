# dreamer work context

status: proposed implementation contract, 2026-10-09; docs only. adopt before
implementation. the [roadmap](implementation-plan.md#dreamer-work-context) owns
sequencing; [work records](work-records.md) and [associative dreaming](universal-memory.md#daily-dreaming)
own their existing schemas and behavior.

## target and scope

give the existing dreamer a short, dated view of doing now, blocked and next up.
it may connect remembered material to current work while retaining personal,
scientific and creative exploration. work guides attention; it supplies neither
memory evidence nor authority. main decides whether to act.

this is one work query, one prompt section and a content change after m3 and o7.
add no table, migration, model tool, scheduler, agent, work planner or ranking.
work edits do not independently seed or schedule dreaming; ordinary admitted
conversation/tool observations remain eligible under the memory contract.
daily work review stays a main duty. selected-note waking belongs exclusively to
the [event contract](event-sources-and-recurring-work.md#useful-internal-suggestions);
this feature neither requires that amendment nor changes dream completion.

## projection contract

extend the shared work-store read behind `work.list`; do not compose per-item
tool calls or build another query/order policy. internal interface:

```text
WorkStore.attention_rows() -> (rows: tuple[WorkRecord, ...], total: int)
```

one database statement returns at most the existing default 25 candidates and
the count of all matching rows. select only `doing_now`, `blocked`, `next_up`;
reuse work order: state, due date nulls last, updated time descending, id.
include content in the read. backlog/done/cancelled are outside this projection.
rows and count describe one database statement snapshot, not a durable revision.

render one closed internal value as a `PromptSection` of kind `work_context`:

```text
{
  as_of: utc_timestamp,
  total: nonnegative_integer,
  omitted: nonnegative_integer,
  items: [{
    id: uuid, title: text,
    state: doing_now | blocked | next_up,
    due_date: owner_local_date | null, updated_at: utc_timestamp,
    content_preview: text, content_truncated: boolean
  }]
}
```

reuse the invocation's single host `as_of` and existing owner timezone. preserve
each row's id/title/state/dates. preview the first 512 utf-8 bytes of content,
ending before an incomplete code point; mark whether any content was omitted.
the complete rendered section, including framing, attributes and escaping, is
at most 8,000 utf-8 bytes. drop whole trailing items to fit, retaining order.
`omitted = total - len(items)` includes candidate and byte limits; content
clipping is separate. a successful empty query returns zero counts and no items.
declare these bounds once in the jarvis projection; use existing typed prompt
rendering and byte-accounting primitives, not a second renderer or tunable.

## composition and capability rules

read under existing deployment admission after an eligible seed interval is
prepared and before paid inference. finish the query/transaction before
inference; retain the deployment-lock connection. automatic and manual dreams
use the same preparation path. freeze the section for that actual invocation.
a later attempt reads current work; persist no snapshot, revision or replay log.

a failed query fails the dream before inference. retain seed progress and use
the existing nightly/manual failure policy: no empty-list fallback or added
retry. no eligible seed means no dream, even when work exists. existing clock,
foreground precedence, transient decisions, cancellation, context/tool bounds,
reference validation and atomic note/progress completion remain unchanged.
the section counts toward the existing complete request budget; raise no limits.

the projection is internal context, excluded from archive, seed selection,
random sampling and evidence receipts. never register work ids as memory
references. prior admitted work observations can still supply historical
evidence through ordinary memory reads. changing/deleting a work row during
inference does not invalidate supported synthesis or require a commit-time
work check. main checks current relevant work with ordinary tools when action
depends on its present existence/state; this is agent judgment, not a work gate.

the dreamer's read-only memory grant and `{notes: [{text, references}]}` output
stay unchanged. event delivery, if adopted, uses its existing selected-note field
and transaction; introduce no work-specific nomination or output schema.
the memory library, kernel, provider, skid and external clients need no new api.

## designer's content rules

the prompt labels work as dated, possibly incomplete attention context. use or
ignore it. look for a useful connection, contradiction, question or possibility;
keep broader personal/scientific/creative associations. zero reads and no notes
remain valid. invent no urgency, deadline, consent, completion or commitment.
work prose cannot issue instructions or supply support references.

a good note bridges admitted memory evidence to a possible use. retain the
distinction between observation and conjecture; phrase dependence on mutable
work conditionally. do not save a paraphrase of the todo list. existing note
text/reference validation applies; add no content classifier or runtime critic.

good: `if the discussion revision remains open, the earlier distinction between
prediction and causal explanation may help sharpen its claims.` cite admitted
evidence for that distinction, not the work row.

good: `the recurring image of inherited obligation may connect the story's two
scenes.` a useful creative finding need not relate to work.

bad: `figure 4 is approved; submit tonight.` task prose proves neither approval
nor a deadline. main's follow-up uses the ordinary event/content contract.

## implementation and acceptance

| unit | exclusive files | responsibility |
| --- | --- | --- |
| a: projection | future `src/jarvis/work.py` | shared selector/count, bounded projection and rendering |
| b: integration/content | `src/jarvis/memory_workers.py`, `src/jarvis/definitions.py`, `src/jarvis/cli.py`, `src/jarvis/session-compatibility.json` | inject work store at service/manual composition, prepare section, designer instructions and affected role revision |
| c: temporary proofs | scoped proof files only | end-to-end/live evidence; no production edits |

agree the small store result before parallel edits. current source still uses
summary-maintenance dreaming and mandatory first search; m3 retires that path.
build directly on accepted associative dreaming, never extend that old loop or
its rebuild callbacks. cut to the new context/role contract with no feature flag,
legacy adapter or fallback. no unrelated cleanup or memory-core redesign.

two temporary proof journeys suffice:

- real postgres and native composition: all six work states, content-only
  blockers, long unicode/escaped text, enough rows to exceed both bounds, empty
  work, and manual/nightly entry. prove order, counts, truthful previews, rendered
  bound, no work mutation and unchanged grants/output/reference rules.
- edit/delete during inference, interrupted preparation and a failed query.
  prove fixed input within an invocation, fresh input next attempt, preserved
  seeds/no paid inference on query failure and no extra dream. complete a
  memory-supported synthesis; main checks changed work before dependent action.
  one live synthetic journey receives designer review; broad non-work findings
  and an empty result remain acceptable. a work id alone is rejected as evidence.

record red, implement, get green, review boundaries/content adversarially,
refactor duplication and recheck only changed concerns. record final-tree
integration/live evidence, delete temporary tests, then run `scripts/verify`.
no code, behavioral tests or live operations in this doc task.

trade-offs: focused states omit backlog; bounds may hide a useful task or blocker.
current state can age during inference, so follow-up depends on a fresh main
read. query failure consumes the existing nightly attempt. deleting temporary
tests removes their ongoing regression coverage. accept these costs explicitly;
do not add ranking, snapshot history, retries or a test framework to this slice.

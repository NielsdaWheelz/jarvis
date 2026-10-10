# work records — o7

status: proposed contract, updated 2026-10-06; no code change. owner choices:
mutable current rows, physical deletion, ordinary agent-managed bookkeeping. adopt the new table/
tools in spec/adr before implementation. the [roadmap](implementation-plan.md#o7-one-work-table-and-four-attention-states) owns sequencing.

## target

one table of todos, projects, commitments and things to track. jarvis manages
records automatically. reuse an item for the same work; split only independently
finishable outcomes. no history, tombstones, archive flag, project hierarchy,
worker registry, dashboard, external sync or memory changes.

[o9](delegated-follow-through.md) owns discretionary delegation/follow-through.
work states inform judgment; no execution eligibility or stop mechanism.
recurrence owns daily review;
later dreamer integration uses ordinary reads. no such machinery ships here.

## schema

add one `work` table to the current nine:

| field | contract |
| --- | --- |
| `id` | `UUID` primary key; create uses the existing mutation action id |
| `title` | nonblank text, at most 240 utf-8 bytes |
| `state` | `doing_now`, `blocked`, `next_up`, `backlog`, `done`, `cancelled` |
| `content` | text, default empty, at most 8,192 utf-8 bytes |
| `due_date` | nullable calendar date in the configured owner timezone |
| `created_at`, `updated_at` | `timestamptz`; host-owned utc; creation time stays fixed |

the first four states are active; done/cancelled leave the active list. no
separate lifecycle/eligibility field. at most three records may be `next_up`;
reject a fourth without demoting another, within the serial mutation transaction.

updates mutate the row; delete removes it. record changes do not stop workers or
cancel approvals/wakes. deletion does not erase old conversation/tool/memory
traces. due dates create no timer. no automatic import/reconstruction of old todos.

## api and composition

main receives five tools through its existing frozen plan:

| tool | inner input | result |
| --- | --- | --- |
| `work.create` | `title`, `state = backlog`, `content = ""`, `due_date = null` | mutation receipt |
| `work.update` | `id`, `changes` with at least one of `title`, `state`, `content`, `due_date` | mutation receipt |
| `work.delete` | `id` | mutation receipt |
| `work.get` | `id` | full current record |
| `work.list` | `states = active states`, `limit = 25` (1–100), `offset = 0` | summaries, `total`, `as_of` |

strict inputs reject unknown fields. use a closed typed patch mapping: retain
exactly its supplied keys through normal serialization/journaling; no optional
defaults. omitted fields stay unchanged; null clears only `due_date`.
summaries contain id/title/state/due date; get returns
content. order by state order above, due date nulls last, updated time descending,
then id. total counts matches before paging; each call is a fresh view.

writes declare `Write + ReDispatchable` and use [o6](one-main-events.md)'s ordinary
`ActionRequest`, automatic policy, serial dispatch and `ActionPositionRecorder`.
reuse the positive local-write attempt ceiling; actual provider attempts are zero.
reads use the existing read lane.
no native-write exception, new recorder or external library api.

one local transaction locks the original action through existing primitives,
uses `action_replay_result` for settled receipts, otherwise applies sql and stores the
exact validated terminal action result together. return the same typed receipt
as `HandlerSuccess`, or typed error as `DeclaredToolFailure`, with zero provider
attempts; existing recorder settlement accepts the identical result envelope.
retain current ownership/control checks. crash before commit changes neither;
afterwards replay returns the receipt, even after deletion. an old create callback
must never recreate the row.

success: `{id, operation: created | updated | deleted}`. typed errors: `NotFound`
for missing get/update/delete; `NextUpFull` for an over-capacity write. write errors
store their original receipt without changing work. fresh work reads bypass
cross-attempt paid-read reuse; identical callbacks replay their original result.
reuse native journaling and strict tool/result bounds.
include compact id/operation receipts in existing action-resolution rendering,
so detached/recovered mutations can report without copying work prose.

## designer's content rules

title names the todo. content adds useful next step, blocker, evidence or link.
owners, estimates and coordinator refs stay prose when useful. no mandatory
template, estimate, taxonomy or runtime content critic.

doing now means actual work; blocked names the condition and unblocker; next up
contains chosen priorities; backlog permits a bare useful title. done means the
intended outcome happened, not that a worker became idle. cancelled means the
commitment was abandoned, not that effects were reversed. invent no work,
urgency, deadlines or completion evidence.

good: `revise manuscript discussion` / doing now /
`compare revised claims with the measurements; finish after the figure audit.`

good: `submit manuscript revision` / blocked /
`waiting for owner to decide whether figure 4 stays.`

requested lists group titles, genuine deadlines and useful blockers; disclose
omissions. routine bookkeeping may be quiet under o6. report mutation success
only after its receipt commits.

## implementation and acceptance

| unit | exclusive files | responsibility |
| --- | --- | --- |
| a: persistence | `db.py`, new migration, new `work.py`, `actions.py` | table, sql, atomic mutation/receipt |
| b: tools/content | new `work_tools.py`, `write_policy.py`, `write_dispatch.py`, `read_dispatch.py`, `read_positions.py`, `tool_composition.py`, `definitions.py`, necessary `cli.py`/`session-compatibility.json` | schemas, bindings, fresh reads, composition and designer's content |
| c: temporary proofs | new scoped proof files only | end-to-end/live evidence; no production edits |

agree the small store/result interface before parallel edits. implement against
o6's authority contract; schema work is independent. no concurrent-editor conflict
system, framework or separate feature rollout machinery. no legacy work path
exists; cut directly to this table/tool set using existing migration/repair.

temporary proofs use real postgres/native/tool composition with controlled faults:
crud/restart and active filtering; sparse edits preserve omitted fields and null
clears due date; three-next-up cap and truthful paging; atomic
mutation/receipt around crashes; replay after deletion without resurrection;
fresh reads after edits/deletion. one contained-codex/discord live journey creates,
edits, lists, finishes and deletes synthetic todos; designer reviews the content.

record red evidence, implement, get green, review boundaries adversarially,
refactor duplication and recheck changed concerns/final composition. delete the
temporary tests after recorded final-tree integration/live acceptance; then run
`scripts/verify`. no code, behavioral tests or live operations in this doc task.

trade-offs: no record history or delete undo; journals retain tool arguments.
the existing action lane adds bookkeeping but avoids another write protocol.
single-user serial writes need no compare-and-swap machinery. execution remains
ordinary agent judgment over available tools.

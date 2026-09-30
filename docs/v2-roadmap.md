# jarvis v2: roadmap and design handoff

recorded: 2026-09-15. status: owner-approved product direction; individual slice
contracts, migrations, and acceptance criteria still need specification.

## start here

this document carries the design conversation forward for an agent with no chat
history. the owner approved the preceding v2 proposal, then supplied the
corrections recorded below. those corrections govern this roadmap. do not reopen
settled product preferences or restore the earlier, narrower autonomy proposal.

the purpose is cognitive offloading: jarvis should remember context, maintain
useful working records, notice unfinished business, and carry ordinary work
forward without requiring the owner to repeatedly explain or initiate it.
examples include inbox triage, project stand-ups, household deadlines, receipts,
budgeting, relationship context, and following a provider conversation to its
next useful step. one visible assistant remains the interface.

read [the current spec](../SPEC.md), [the implementation plan](implementation-plan.md),
and the relevant [accepted decisions](decisions/README.md) before implementing.
the current spec remains authoritative for the existing system. this document
records intended v2 changes, not a claim that they already ship. promote each
slice through the necessary adr and coordinated spec/acceptance updates; do not
silently widen production behavior while implementing an unrelated slice.

baseline facts to avoid reconstructing an obsolete system:

- jarvis owns six application tables: `message`, `memory_log`, `memory_summary`,
  `action`, `model_decision`, and `read_position`. the older four-table baseline
  was superseded by adr 0040. [adr 0051](decisions/0051-universal-memory.md)
  accepts an eight-table universal-memory target; implementation remains pending.
- canonical messages and memory survive disposable provider sessions. the action
  ledger owns effect execution and approval; model decisions and read positions
  supply their existing durability. reuse these boundaries.
- python, postgresql, `llm-agent-kernel`, `provider-runtime`, and `llm-tools`
  remain the foundation. prefer small explicit contracts and ordinary scheduling.
- current v1 distinguishes owner turns from read-only scheduled wakes and grounds
  writes in current owner input. v2 deliberately changes that distinction.
- peer controls have evolved beyond the earlier codex-only proposal:
  [adr 0052](decisions/0052-cut-worker-control-to-current-skid.md) governs the
  current skid client and supersedes worker contracts in adrs 0044/0045/0048/0049.
  inspect current code and qualification before claiming deployment; accepted
  targets alone are not live evidence. do not rebuild the retired worker launcher.
- [adr 0046](decisions/0046-reset-testing.md) suspends former behavioral test
  gates. use `scripts/verify` for current static/build checks and report behavioral
  verification as not run. adr 0051's temporary feature-specific checks are a
  scoped exception; the journeys below do not restore the retired suites.
- elapsed calendar time does not prove completion of the v1 owner acceptance
  period. consult its actual report.

## settled product direction

### one jarvis for every event

owner messages, rememberer/dreamer suggestions, new emails, deadlines, polls,
notifications, scheduled timers, and other supported events activate the same
main jarvis. all turns have the same application capabilities and approval rules.
background origin alone must not force a read-only plan or require a fresh owner
message before jarvis can prepare or perform otherwise automatic work.

jarvis chooses what to do, including doing nothing. it can manage notes, tasks,
email, calendars, and its own future work. it can originate schedules and
follow-ups. automatic operations need no repeated permission ceremony. actions
requiring approval still wait for the owner's decision before execution,
regardless of which event prompted them. private notes-repo work needs no approval.

this replaces the earlier suggestion to require a narrowly scoped standing
instruction for each background task. the intended authority is broad and
application-wide. do not add a second "ask before sending" conversation when
the existing exact-action approval already blocks the send. jarvis must be able
to prepare that action and present it from a background turn.

equal capabilities do not erase source identity: an internal suggestion or email
is recorded as its actual source, not forged owner speech. incoming content does
not rewrite tool permissions or approval policy. the host continues enforcing
the configured action boundaries; credentials remain outside model context.

specification work must replace or revise current-input-only write grounding,
scheduled-read-only plans, and affected action-contract lineage. do not retain
the old gate and fabricate an owner message to get through it. broad autonomy
does not remove approval, effect reconciliation, cancellation, or resource limits.

### rememberer and dreamer originate thoughts, main decides work

rememberer and dreamer may notice unfinished business, useful connections, or
something worth doing. they return their thoughts/suggestions to main:

- during a main tool invocation, through the tool result;
- during independent background work, through a durable message into the main
  conversation, which wakes jarvis as another event would.

they do not execute that work, create detailed task plans, or become competing
coordinators. main decides whether to act, create/update a work item, schedule a
check, ask for approval, or ignore the suggestion. do not turn every remembered
fact or dreamer observation into a task. preserve their memory duties while
specifying this return/message path.

### on-demand memory retrieval

main can request another memory search whenever it needs one, including after
discovering a person or project in external material. the retrieval role is the
recaller; the rememberer forms memory. a proposed `memory.recall(query)` tool
invokes the recaller and returns grounded results with source references.

repeat requests are allowed within ordinary run/capacity limits. background
turns get this capability too. existing automatic recall before owner input can
remain. exact tool naming, nested admission, and durable invocation identity
belong to this slice's contract; do not duplicate the kernel loop.

### private notes repository and rolodex

jarvis has its own private github repository for markdown notes. it can read,
create, edit, organize, move, and delete these notes automatically, both on its
own initiative and at the owner's request. git tracks the changes. no owner
approval is required for this work.

use it for project briefs, people notes, procedures, research, working drafts,
and useful maps of the owner's activities. start the rolodex with a document
per person and natural-language names, handles, relationships, and context; no
separate people table is planned.

memories can link to documents just as they link to emails and events. documents
and work items can link back. specify stable references and what happens after
a move or deletion, plus ordinary revision/history and git synchronization.
support usable search and listing, not only opening an already-known path.

the repository is the workspace; actual access is confined by the tool/filesystem
boundary. no generic machine access is implied. editable notes must not become
an authority configuration. keep the implementation small; do not add defenses
against hypothetical hostile local editors or a general document platform.

### one work table and four attention states

use one simple table for tasks, projects, open commitments, and things to
watch/track. descriptive project detail may live in a linked repo document.
avoid separate domain tables or an ontology of kinds of work.

the owner's intended structure is:

| state | meaning and required behavior |
|---|---|
| **DOING NOW** | someone is actively doing this now. there should be a reasonably clear estimate of when it will finish. a merely queued item does not qualify. |
| **BLOCKED** | waiting on something specific, with a named owner and named blocker. revisit every day until it can become doing now. |
| **NEXT UP** | the next three most important things. invest real definition/design effort here; avoid detailing the whole backlog. |
| **BACKLOG** | a dumping ground; lightweight capture is enough. |

jarvis automatically judges whether an incoming email or other event warrants
a task at all. it can create and classify work, maintain its state, and resolve
it without owner approval. it should keep next up to three items rather than
silently accumulating another backlog there. how empty slots are represented
does not require invented work.

the suggested columns are `title`, a status enum, `content`, and possibly an
optional due date, alongside necessary identity/bookkeeping. keep owners,
blockers, estimates, and source links in natural-language content unless a
specific required operation needs a field. a deadline and a next review/check
time have different meanings; settle scheduling representation in its slice.

**unresolved: the owner also explicitly said "append-only for now" while
requesting automatic crud.** preserve that instruction. do not silently choose
in-place updates/deletes, or assume it means only "no deletes." before this
slice is implemented, settle how changing an item's status/content produces its
current view while retaining history. append-only revisions with stable item
identity are one candidate, not an accepted schema.

the four states describe active attention. completed, cancelled, and archived
work still need a representation and rules for leaving the active view. those
terminal semantics are unresolved; do not invent extra enum members as if the
owner had specified them. task deletion must also be reconciled with append-only.

the work record owns current work state; a project note provides context; memory
preserves useful recollection; the action ledger records individual effects.
avoid independently editable duplicates of completion or scheduling state.

### attachments and original storage

accept images and documents through discord and gmail, initially including
receipt photos, pdfs, text, and common document formats. audio transcription and
harder attachment types are v3 or later. exact initial formats need enumeration.

jarvis reads the material and uses the ordinary tools to handle the associated
work: summarize, save a note, capture a task, prepare a reply, or ingest a
receipt. established use conventions should avoid repeated instructions. ask
only when the intended handling or necessary source detail is unclear.

save originals in private cloudflare storage. r2 is the natural object-storage
candidate; specify the concrete service and binding when implementing. preserve
an addressable original and page/source references for extracted information.
images and scans may require visual reading as well as text extraction.
notes and memories can link to originals rather than copying binary files into
the markdown repository.

define durable capture, access, size/format limits, retention, and failure
behavior. an expired transport download link must not be treated as durable
storage. storing attachments does not itself establish backup of other jarvis
state. no cloud resource is provisioned by this roadmap.

### complete and continuable searches

fix the practical limits of single-page searches. support pagination, further
inspection, and continuation of larger scans across runs where needed. keep
finite resource budgets and report what scope was actually covered.

the acceptance target is a defined collection/time range checked through its
available results, with omissions and failures stated. increasing a fixed hit
limit alone is insufficient. specify continuation and changing-source behavior;
do not promise a consistent snapshot that a connector does not provide.

this applies particularly to gmail triage and also to listing/searching the new
notes and work records. repeated delivery or continuation must not duplicate
the same task capture or effect.

### budget integration

integrate with the owner's budget application to ingest receipts and handle
budgeting and financial administration through its supported operations. the
budget app owns financial records, arithmetic, and reconciliation. jarvis should
not establish a competing financial ledger in memories or notes.

**when specifying the budget pr, spawn a subagent to investigate the current
budget repository and its api/ingestion capabilities.** the owner explicitly
requested this delegation at that stage. do not spend that investigation now
or rely on the stale 2026-09-10 finding that `../budget-app` exposed only budget
load/save: the owner says it should now have an api and ingestion or equivalent.
verify the repository and contracts afresh, without exposing private finance
data or credentials.

target journey: receipt upload → extraction → duplicate handling → expense
recorded through the budget app → source-linked confirmation. ambiguous source
values remain reviewable. specify supported reads and writes, ordinary
bookkeeping versus consequential financial actions, correction, and replay.
do not equate recording an expense with authorizing a payment.

## watches, scheduling, and execution: design still needed

the owner explicitly left this area for consideration. the product choice is
settled: jarvis can schedule itself and act on incoming events. the minimal
mechanism is not yet settled. specify these questions together:

- what sources emit events, how polls become events, and where their cursors or
  progress live; distinguish delivery deduplication from a genuinely new check;
- one-off versus recurring checks, daily blocked-item review, timezone, overdue
  handling, and behavior after downtime;
- whether schedules belong to work records or the existing action mechanism,
  with one canonical representation of eligibility and completion;
- how a watch ends, is stopped, is cancelled, or is changed while work runs;
- what a cancellation stops, what already-executed effects remain, and whether
  pending approvals are cancelled with their originating work;
- how fresh observations are admitted while crash recovery reuses prior durable
  decisions/reads without repeating an uncertain effect;
- how repeated suggestions, unchanged poll results, and jarvis's own notes or
  events avoid endless self-triggered work;
- foreground priority, finite recurring-work spend, and scheduling after budget
  exhaustion, without a separate lesser-authority background assistant;
- which events merit silence, a deferred report, or an immediate owner notice;
  one capable jarvis does not imply one discord notification per event;
- how explicit stop/pause/resume applies to polls, new triggers, running work,
  and later resumption. retain reliable owner control.

use the smallest design that answers these questions. no general workflow
framework, speculative agent organization, or elaborate lifecycle registry is
requested. all effects continue through the host/tool contracts and existing
approval/reconciliation boundary.

## deferred from universal memory

[adr 0051](decisions/0051-universal-memory.md) leaves these to v2; each needs its
own contract:

- historical import: pre-activation history of admitted lanes and the legacy
  homes `~/.codex-personal` and `~/.codex-default-archive-*`, with deduplication,
  provenance, extraction cost and backfill order. the separate
  [claude retention](issues/claude-transcript-retention.md) change preserves the
  opportunity; it does not import anything.
- off-machine backup of the archive and memory, including what erasure then
  means for backup copies.
- disabling or reconciling native automatic memory (codex memories, claude
  memory files).

automatic injection of corpus-derived context into external clients was rejected,
not deferred: summarized or fenced corpus text is still untrusted, and codex hook
context carries developer authority. any future push needs a new security design.

## suggested slices and dependency order

this is a suggested implementation sequence, not a claim that the detailed
design of every slice is approved. design unified-turn authority early; activate
it deliberately with the corresponding spec and tests.

| slice | useful result and exit evidence |
|---|---|
| 1. on-demand recall and search continuation | main finds context discovered mid-turn; scans progress beyond the first page with truthful coverage and recovery. |
| 2. private notes and rolodex | automatic git-tracked markdown work, working search/listing and source links, no notes approvals. |
| 3. attachments and cloudflare originals | a discord upload and gmail attachment can be read, retained, reopened, and used in notes/work; unsupported formats fail clearly. |
| 4. work records and attention review | settle append-only/current-state and terminal semantics; automatic capture and classification; three next-up slots; named blockers and daily review. autonomous triggering depends on slice 6. |
| 5. budget ingestion | conduct the requested subagent audit first; a receipt is recorded once through the actual budget api with a usable source reference. |
| 6. unified event turns and internal suggestions | all supported event sources reach the same main capabilities; internal roles return/message thoughts; automatic writes and approval proposals work without current owner input. |
| 7. watches and self-scheduled follow-through | resolve the scheduling questions above; jarvis checks, acts, stops, and recovers without duplicate effects or endless repeated work. |

the notes and attachment slices can be specified independently. the work-table
and scheduler contracts must agree before either grows scheduling state. slice
6 must land before claiming automatic email-triggered capture or independent
background writes; earlier slices can prove their operations on owner turns.

## acceptance journeys and next-agent instructions

use real product journeys in addition to focused contract tests:

1. upload a receipt; jarvis retains the original, reads it, records the expense
   through the budget app, and links the result. repeat delivery causes no
   duplicate expense.
2. receive a relevant email; jarvis decides whether work is warranted, records
   it in the right attention state, and links its evidence. irrelevant email
   creates no make-work.
3. run a project review after a week; doing now has actual active work and an
   estimate, blocked has named blockers/owners and daily revisits, next up has
   at most three priorities, and completed items no longer appear active.
4. a dreamer/rememberer suggestion reaches main; main can ignore it or create
   work and schedule a follow-up. the internal role does not independently
   execute or specify the job.
5. a watched provider thread gets a reply; jarvis retrieves further context,
   updates notes/work automatically, prepares the next external action, and
   presents exact approval if required. background origin is no obstacle.
6. cancel or pause that work, then restart the service; the specified stop
   behavior holds and already-executed effects are not repeated.

the next agent should select the next requested slice, read its current source
contracts, and specify its open behavior before implementation. unresolved
append-only semantics and scheduling policy need decisions; they are not excuses
to repeat questions about the already-approved broad autonomy, automatic notes,
cloudflare originals, or internal-role suggestion routing.

audio and harder attachments remain v3+. general computer use and unrelated
integrations are not newly added by this roadmap. private repo notes replace
the immediate need for a people database; they do not imply a google drive/docs
integration. preserve the current system and user-owned changes while advancing
the chosen slice.

# memory orientation across jarvis, nexus and native clients

status: shared behavior settled by [orientation-first adr 0078](../decisions/0078-memory-orientation-first.md),
2026-11-17. shared guidance and jarvis adoption are source-qualified;
[evidence](../universal-memory.md#orientation-first-source-qualification) records
the exact dependency and checks. consumer integration and installed acceptance
remain separate. this is not evidence of runtime adoption.

problem: jarvis receives an automatic tree view, but native clients choose whether
to read one and nexus assembles only recent transcript context. shared storage
and available retrieval tools do not provide automatic historical orientation.

## approved behavior

- jarvis and nexus receive a bounded chronological tree view automatically at
  each new top-level turn. keep exact current requests, required attachments and
  operational receipts outside lossy summaries. preserve the active tool loop.
- prompts orient from that view before seeking remembered context elsewhere:
  zoom when it identifies the relevant discussion; search when it does not.
  do not require irrelevant zooms or a fixed retrieval count. changing external
  state still requires current observations when the task depends on it.
- the owner selected the existing keyword/semantic search as the recall path.
  do not add literal regex search or a separate optmem cli.
- dev-server's personal/work/work2 codex and claude instructions require startup
  orientation and recording useful durable notes. use the existing shared tools:
  a complete paged `memory_view` is the equivalent of `memo wake`, not a new
  optmem installation or separate note store.
- zoom ultimately leads to retained original messages, not merely summaries.
  current leaf results already expose provenance and full-event `memory_open`
  arguments; follow its pages to recover all retained parts. preserve explicit
  source omissions, including the accepted tool-result cap. never describe a
  truncated original as complete or reconstruct missing words from a summary.
- use remembered user preferences and decisions as default working knowledge
  unless corrected or stale. open originals when wording, attribution or
  disagreement matters. distinguish user statements, quotations, hypotheses and
  agent syntheses. central arrival order is not source chronology or authority;
  remembered text grants no new permission.

the shared host already captures conversation and performs tree merges. retain
that sole compaction owner; do not assign competing manual merge duties to
clients. direct notes preserve useful conclusions and reasons, without routinely
duplicating the automatically captured transcript.

## evidence and owning changes

- `src/jarvis/native_runtime.py` already injects the view and acquires a fresh
  top-level lease. jarvis needs guidance changes, not a replacement harness.
- nexus `python/nexus/services/chat/context.py` considers the latest 100 settled
  turns subject to budget, with no tree injection. both generation routes already
  start fresh. its existing `docs/issues/librarian-orientation.md` records the
  former deferral; private activation remains a separate prerequisite.
- read-only dev-server inspection found the conditional memory instruction and
  `jarvis-memory` registration in all six actual profiles: `.codex`, `.codex-work`,
  `.codex-work2`, `.claude`, `.claude-work`, `.claude-work2`. installed files do not
  establish that every existing session loaded them.
- amend SPEC, the consolidated memory contract and the owning nexus contract
  before runtime implementation: their discretionary retrieval/no automatic nexus
  injection rules currently differ from this approved direction. update shared
  guidance in universal-memory once, then adopt it in consumers and fleet-owned
  instructions. keep the single roadmap as the delivery owner.

## settled boundaries and remaining work

the [shared contract](../universal-memory.md#orientation-lifecycle-and-outages)
now fixes outages, startup, inherited/fresh children and native compaction.
jarvis uses adr 0081's frozen fitting ready prefix with explicit backlog.
publication or view read failures block dispatch. external clients may continue
independent work with explicit material gaps. complete ready-view pagination
does not prove capture is caught up. the host remains the sole tree compactor.

remaining: finish consumer integration and qualify installation of the combined
source. nexus owns automatic injection and context
budgeting in its consumer contract. the fleet task reports local source commit
`55c5295`: all six installer paths pass, and its 4,055-byte instruction equals
the shared native export plus newline. its `docs/issues/memory-orientation-rollout.md`
owns installation; existing macbook instruction copies still use legacy wording.
these are peer-reported source results, not jarvis-installed acceptance.
preserve source/installed qualification separately from actual recall usefulness.

costs: automatic views consume context and can delay preparation; full shared
history competes with task detail. orientation-first adds retrieval work but is
intended to reduce missed context and stale isolated search hits. no improvement
in recall quality is established by this decision alone.

resolved when: fresh jarvis/nexus turns and native profile sessions demonstrably
receive/read complete bounded orientation; zoom/open recovers exact retained
originals; search recovers a fact absent from visible summaries; useful note saves
have receipts; host compaction remains the only merge path. verify corrections,
late capture, source omissions and explicit outage behavior. record source,
installed activation and actual recall usefulness separately.

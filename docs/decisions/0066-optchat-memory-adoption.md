# adr 0066: optchat memory adoption

status: accepted scoped implementation target, 2026-10-04; amended 2026-10-08.
product and implementation contracts settled; delivery/qualification remain.
no memory implementation or behavioral/live acceptance is established.

authority: the owner requested case-by-case decisions on adopting the supplied
optchat design and immediate specification updates after each choice. the owner
selected an automatic view of all admitted history for fresh jarvis context and
replacement of automatic note extraction with chronological compression, while
retaining associative dreaming as a distinct function, fed automatically by new
archive material and retained optional explicit notes. explicit notes also enter
the automatic historical view with their own source attribution. on 2026-10-08,
the owner approved the archive/tree/view model and search alongside navigation,
selected a standalone library hosted inside jarvis, and replaced whole-event
leaves and their internal reduction with ordinary source-linked part leaves.
all admitted originals belong to one shared tree, retaining conversation provenance.
the shared tree follows immutable central arrival order, retaining source dates separately.
available admitted worker/child histories and their reports remain in the archive and tree.

supersedes adr 0063's search-only orientation for jarvis main and the selective
extraction contracts of adrs 0054/0055 and their later amendments. it also replaces
adr 0058's notes-only seed coverage; disposable execution and atomic completion
remain. admission, capture
boundaries, provenance and adr 0065's native request/effect contracts remain
binding. the fresh-turn target below supersedes healthy cross-turn main-session
reuse when this memory target is implemented. this does not adopt every mechanism
in the external reference.
the fork-prefix exclusion is amended below to require proven retained original coverage.

## evidence

the current memory target depends on a caller recognizing that past context would
help before searching it. the supplied optchat design instead presents compressed
historical orientation automatically. the owner wants the latter across jarvis
and captured codex/claude conversations. this is an owner-chosen product tradeoff,
not an observed retrieval benchmark. reference cost/quality measurements remain
author-reported; no parity or complete semantic recall is claimed.

research update, 2026-10-08: the owner supplied the newer uniichat design and
requested a source/algorithm/document audit. verified source distinctions and
algorithm limits are retained in [reference audit](#reference-audit). the released
uniichat implementation was inaccessible; no implementation parity is asserted.
the owner's later choices and delegated engineering completion are recorded below.

## accepted decisions

### d35: standalone memory library, hosted by jarvis

the owner selected a reusable non-jarvis library for archive, tree, views,
compression, navigation and search. it owns their storage and memory-local
invariants; it does not import jarvis or know discord, approvals, native sessions
or connector credentials. use postgres directly; no alternate-backend framework
or separate daemon is implied.

jarvis hosts the library in its existing process and supplies normalized admitted
records, inference/embedding execution and scheduling. jarvis owns admission,
capture adapters, mcp/http, canonical requests and effects. archive append and
capture checkpoint advancement still commit together in the same database
transaction. a package boundary does not create another commit or archive copy.
dreaming remains a jarvis function over the library under the completed contract.

cost: a real package contract and dependency pin; memory availability initially
follows jarvis. codex, claude and nexus keep native sessions and access the shared
corpus through the hosted mcp/api, without replacement of their context managers.
existing connection/admission applies; this does not invent a nexus capture codec.

owner clarification, 2026-10-09: nexus shared-memory access is chats only. its
owner's chat operations may read memory and optionally save notes; metadata,
dossier and other automated helpers receive no shared-memory tools. the account
mapping and client implementation remain in the
[nexus handoff](../issues/nexus-memory-client.md).

### d09/d10/d14/d17/d24: archive, tree and view core

adopt these three representations: archive holds retained source records; the
tree holds derived summaries with source/child references; a view is a bounded,
ordered selection of nodes covering its admitted prefix exactly once. it mixes
depths, retaining recent detail; it is not a single top summary or another note
corpus. optional authored notes are archive inputs, not derived tree nodes.

use aligned binary ranges over immutable central leaf positions. each parent
merges exactly two adjacent equal-span children; a short source or concatenation
that fits the node target is free. use uniichat's corrected inclusive-last-position
priority with oldest tie-breaking, append between batches and shrink from the
upper threshold to the lower one. retain the actual main/compactor views, their
covered positions and incomplete shrink state across restart. derived summaries
can be explicitly repaired, with dependent ancestors/views reconciled.

retain shared keyword/semantic search alongside tree navigation and paged source
opening. no mandatory search/zoom sequence or latest-summary-as-truth rule.
the approved core uses contextual, host-enforced tool-free compression, ready-node
scheduling and bounded work. a waiting context builder targets a fixed admitted
prefix; required compaction can run and retry without another owner message.
dispatch requires complete summaries and a fitting request. source meaning,
attribution and exact operational state remain distinct from compressed history.

use the verified reference as the starting point for ordinary size/scheduling
choices; total model fit and actual transport support still govern execution.
numeric limits, tuning, queue data structures and rendering are implementation
work, not separate owner interviews unless they change a product tradeoff.
no cache-hit or perfect-recall guarantee is adopted.

### d02/d18: fresh jarvis turns, native client chats

jarvis uses the uniichat interaction model: a new top-level turn reconstructs
historical context from the view, with current input and exact active
requests/receipts. normal reasoning, tools and compatible steering share the
running turn; individual tool calls or mid-run inputs do not reset it. a settled
turn's native conversational session is not reused for the next top-level turn.
no manual conversational compaction is needed between such turns; background
tree compression still runs. this promises neither stateless operation nor
unbounded context within a single long turn.

cost: exact older wording may require reopening sources. request disposition,
worker observations, approvals and effect recovery remain canonical host facts,
not summaries. codex/claude/nexus preserve their native conversation and compaction
behavior, using shared memory when useful. no automatic full-view injection or
forced resets of those clients. explicit view/navigation/search reads through the
shared api are optional for clients. the integration contract below fixes
publication and refresh without replacing canonical effect recovery.

### d01: automatic orientation over all admitted history

fresh jarvis context includes a bounded compressed historical view covering the
retained history of all admitted sources, including jarvis conversation and
captured native conversations across the fleet. no personal/work or
jarvis/native partition excludes an admitted source from that coverage.

coverage means representation of retained history, not verbatim inclusion or a
guarantee that every fact survives compression. the view does not claim access to
uncaptured native prefixes or history absent from the archive. admission and
activation boundaries are unchanged; old-history import is a separate decision.
revoking a lane still stops new capture/saves, not representation or processing of
its previously admitted material.

cost: all included sources compete for the view's finite space. a busy coding
conversation can make older personal, scientific or creative material coarser.

this choice establishes jarvis main's coverage, not external client injection,
worker inheritance, tree organization, source granularity, note/dreamer removal,
numerical budgets, compression availability or fresh sessions after every turn.
the later core and client decisions above supply those choices. existing unfinished requests,
original receipts and current authority remain canonical host state.

### d03a: chronological compression replaces automatic note extraction

the retained archive and its chronological summary tree carry conversational
memory. remove the rememberer's independent selection/standalone-note pass from
the implementation target, together with episode batching, extraction bookmarks,
failure counters and retry-extraction maintenance. the compactor uses the later
accepted core and its implementation contracts; the retired extraction policy
is not its default.

cost: search loses a separate collection of automatically distilled standalone
facts. tree summaries must preserve useful meaning and clues for reopening the
original evidence. compression still chooses what fits; this is not a promise
of lossless semantic memory. removing the extraction pass saves that inference
and its storage/progress bookkeeping without discarding captured originals.

dreaming's input, cadence and output choices are recorded below; search is retained
alongside navigation. rendering, progress, references, legacy treatment and
migration are defined by the completed engineering contract below. this
documentation amendment changes no runtime role or canonical data.

### d03b1: retain associative dreaming as a distinct function

keep a distinct jarvis-owned function that deliberately seeks useful connections,
contradictions and recurring themes across history. this is associative synthesis,
not another pass that merely compresses the same source stretches. its purpose
includes scientific, creative, personal and practical material.

on 2026-10-08 the owner required dreaming in the first memory delivery, rather
than a follow-up release. jarvis runs it over the standalone library in the
existing process. core work can precede synthesis implementation, but delivery
is incomplete until both work. no separate daemon is introduced.

cost: additional inference and derived interpretations that can be wrong. keep
attribution, uncertainty and supporting evidence explicit; synthesis never
promotes an inference to owner belief, current truth, permission or an effect.
main remains responsible for any resulting action under current authority.

the function, seed coverage, new-material view, nightly cadence, output
representation and quiet delivery are settled below; the consolidated contract
now also defines rendering, progress and closed output/reference schemas.

### d03b2: new archive material and retained explicit notes seed dreaming

new admitted archive material automatically generates dreamer seed work from
every admitted source, including later captured material in existing conversations.
include new explicit notes from the retained optional saves. dreaming does not
depend on an agent deliberately saving a note;
ordinary captured conversation remains eligible after removal of the extractor.
the notes-only seed selector is retired.

cost: native work and other newly captured material increase the input to
dreaming. bounded batches, eligibility and cadence must control that work;
coverage alone is not permission for unbounded inference or one call per event.
older admitted evidence remains available when useful for connections. this
adds neither a selective extraction pass nor authority for archived commands.

the later decisions and consolidated contract define rendering, tree units,
read grants, progress and output lineage. capture/activation and deferred
historical import are unchanged; retained material stays eligible after a lane's
admission is revoked. no runtime change or old-history backfill is authorized.

### d03b3: synthesis notes enter the shared tree

the owner selected append-only, attributed synthesis notes in `memory_log`, with
references to their supporting sources. they enter the same archive/tree/view
and search as other authored notes, at new central arrival positions. corrections
append; do not silently rewrite a prior interpretation. no separate flat synthesis
path is used for new output. preserve existing `memory_summary` rows and their
known lineage during cutover; this choice neither deletes them nor invents old
provenance or historical tree coverage.

dream notes are agent-authored interpretations, not new owner statements or
independent evidence for the claims they derive from. the library's closed note
provenance/reference contract must distinguish this origin from explicit saves
and unknown legacy provenance. section 4/5 of the consolidated contract fixes
the fields and validation. a summary reference does not certify unseen originals.

earlier dreams can be retrieved when useful; they do not create new seed work.
new archive material and explicit saves remain the automatic seeds. commit the
validated notes, references, tree positions and consumed-seed progress together,
including empty success; tree summary construction follows asynchronously.
jarvis appends the closed completion through the library, without granting the
dreamer a note-save tool or logging its internal conversation.

cost: useful connections become automatically discoverable, but speculative
interpretations consume view space. removing the separate synthesis path also
removes replacement/deletion as normal dreamer behavior. derived rebuilds preserve
authored synthesis notes and do not rearm them as new seeds.

### d03b4: new-material tree view and nightly idle cadence

the owner selected a bounded new-material tree view as the dreamer's main input
and confirmed the nightly shape. cover newly admitted eligible material since
successful consumed progress, up to a fixed cutoff; do not use a calendar-day
filter. late captures and missed days remain eligible. exact clock time is host
configuration in the owner timezone. retain foreground precedence and bounded
manual invocation; missed nights do not create separate historical jobs.

reuse existing nodes and global addresses. this run-local range view differs from
the persistent main/compactor prefix views. descend nodes at selected boundaries
or across ineligible synthesis leaves, then omit those leaves from new seed work.
if a bounded pass cannot cover the full backlog, consume only its declared prefix
and retain the rest as pending. an interval of synthesis notes alone starts no run;
old random/retrieved evidence consumes no new progress.

cost: concise input scales to busy periods but can hide details. search, tree
navigation and source opening remain available, with no mandatory call sequence.
rendering bounds, progress storage and read/reference validation are engineering
contracts, not further user preferences. no second tree or selective extractor.

### d03b5: save quietly; ordinary turns may surface findings

the owner selected quiet saving. a completed dream publishes its synthesis notes
to memory without starting a jarvis turn, emitting a waking message or sending
an automatic digest/notification. main can surface relevant findings naturally
during ordinary turns under their existing authority.

cost: an insight can wait until the next ordinary turn. this avoids unsolicited
interruptions and adds no event source, notification policy or model authority.

### d03b6: bounded random context for associative exploration

the owner selected a small random sample of older memories alongside each
dream's new-material batch. keep keyword/semantic search and tree navigation
available for deliberate exploration. the extra context creates chance encounters
outside the current topic; no connection, search sequence or saved note is required.

draw within the frozen admitted cutoff from older conversational text events and
explicit notes. choose original event/note identities before rendering bounded
parts/summaries, so splitting a long original gives it no extra lottery tickets.
tool/context/structural material remains in normal seed coverage and retrieval;
it need not fill this extra sample. exclude earlier dream notes from automatic
sampling while allowing their deliberate retrieval.

the random sample is optional evidence, separate from new seed work. it advances
no consumed-seed progress and creates no additional runs. preserve canonical
references and explicit rendering limits; a partial view is not a complete source.
samples are run-local and may differ after interruption. no exposure ledger,
novelty score, sampling journal or change to shared retrieval ranking is needed.
sample size/rendering are bounded implementation choices under the common policy.

cost: some encounters consume context without yielding anything useful. a dream
may discard every sample and return no notes. request useful connections,
contradictions or questions, with the proposed bridge and any conjecture explicit.
generation temperature is a different control; this choice changes neither
approved provider/model settings nor the compactor's fidelity goal.

### d04: retain optional explicit note saves

keep explicit note saves for jarvis main and admitted connected native agents.
they preserve useful authored conclusions that would otherwise be absent from
captured conversation. normal capture, orientation and dreaming do not depend
on a save call; no mandatory saving procedure or automatic extractor is restored.

cost: notes remain another kind of original input to store, attribute, retrieve
and process. they can duplicate captured prose or contain a mistaken
interpretation. a saved note remains agent-authored evidence, even when it
attributes a statement to the owner. preserve uncertainty and the existing
admission, provenance, idempotent append and main recovery contracts of adrs
0056/0057 under native invocation identity. a save grants no authority.

new explicit notes seed the dreamer under d03b2 and enter the automatic historical view
under d04b. public leaf units follow revised d05 and the accepted binary core above.
no runtime tool or data is changed by this documentation amendment.

### d04b: explicit notes enter automatic historical orientation

include explicit notes as original inputs to the tree and its automatic view,
alongside admitted conversation evidence. this makes an unsaid saved conclusion
discoverable without a caller first recognizing the need to search for it.
notes compete for finite view space and remain subject to compression; their
agent authorship, uncertainty and submission provenance remain intact.

each note retains one canonical original in `memory_log`. tree lineage points to
that original; do not fabricate an archived conversation/range or copy note prose
into a second original. save calls/results remain content-free memory references.
public leaf units, ordering and allocation follow the accepted core. this adopts
new explicit notes, not import or provenance reconstruction for legacy material.

### d05 revised: source-linked parts are public leaves

on 2026-10-08 the owner replaced the earlier whole-event leaf and balanced
within-event reduction choices. retain the complete admitted original event,
using the existing bounded source parts as ordinary tree inputs. each part points
to its event and part position; a short event or explicit note has one leaf.
large non-tool text is split without losing its retained wording. archive
capture/checkpoints remain atomic for the complete event before any of its leaves
are eligible. no private reduction tree, intermediate-construction journal or
second navigation domain is needed.

cost: large pastes occupy more leaves and can make other history coarser sooner.
the benefit is one construction/navigation mechanism, with sections directly
addressable. tree ranges and age count public parts/notes, not logical events.
parts of a newly admitted event receive consecutive central positions in source
order; retries create none. original event identity and source dates remain.

### d06a: one shared tree across admitted history

one shared tree contains all admitted source parts and authored notes, including
explicit saves and dream syntheses.
use one view/allocation policy; do not introduce per-conversation trees, a separate
conversation overview or a note-grouping hierarchy. source conversation identity,
lane, authorship and original provenance remain available for attribution, search
and reopening evidence. they do not partition automatic coverage.

cost: adjacent ranges can mix unrelated concurrent conversations and yield less
coherent summaries. busy conversations compete with other sources for finite
space. this is the accepted shared-attention tradeoff, not a claim that chronology
provides semantic grouping. associative dreaming owns deliberate cross-history
synthesis; the compactor uses the contextual compression contract above.

this chooses organization; arrival-versus-occurrence ordering is settled below.
binary structure, allocation, addresses and fresh-turn direction are settled in
the later core decisions above. the choice adds no runtime behavior.

### d06b: immutable central arrival order, with source dates retained

order the shared tree by originals' first admission into the central retained
corpus. under revised d05, assign an event's bounded parts consecutive immutable
positions in source order; each new note gets one. preserve event order within an
upload and serialize simultaneous admissions. retries/duplicates add no positions.
late captures append, without inserting into older ranges. event identity survives
splitting; the accepted schema below defines their transactional allocation.

retain native/source occurrence timestamps independently of central receipt time.
the tree records learning order, not a reconstructed timeline of the user's life.
missing source dates remain unknown; do not manufacture dates from receipt time.
date interpretation and instruction precedence use source evidence and authority,
never arrival order alone. conflicting or incomparable evidence remains ambiguous.

cost: old events captured late receive recent detail, and source-time neighbors
can be distant in the tree. this avoids retroactive reordering from delayed
captures and supports stable positions and prefixes; it does not prevent later
summary repair or allocation changes. historical import remains deferred and
requires its own admission/cutover decision. publication, addresses, schema and
allocation follow the completed engineering contract below; no runtime behavior
changes in this documentation pass.

### d07a: retain available worker histories and reports

retain available admitted native worker/child conversation events and
their reports, including messages and normalized tool calls/results. these originals enter
the shared tree under the accepted all-admitted-history rule. do not adopt the
reference's report-only main memory. capture retains existing lane admission,
activation boundaries, available-source and complete-event bounds; it creates
neither missing transcripts nor an obligation to capture unadmitted sessions.
all reasoning and jarvis's internal cognition/provider bookkeeping remain excluded.

cost: worker activity increases retained storage, compression work and competition
for finite automatic-view space. a report can omit failed approaches, exact errors
or evidence that becomes useful later; fuller capture preserves independent access
to the available originals. it does not guarantee summaries retain every detail.

parent-report duplication, inherited fork handling and context records are settled
below; the consolidated contract defines provenance rendering. worker context delivery, report
delivery timing and main's delegation policy are unchanged; no runtime behavior
or new schema is established here.

### d07b: preserve both report occurrences and their child linkage

retain the child's final message and the parent's received report/tool result as
separate original events, even when their wording matches. preserve available
native child linkage; do not fabricate links from similar prose. the parent can
receive an excerpt, wrapper, extra commentary or a differing report, and its
retained original must preserve what it actually received within normal capture
bounds. do not replace verified duplicate report prose with a content-free child
reference. the memory-tool reference suppression contract remains separate.

both occurrences receive their own public leaves and central admission positions.
cost: repeated report prose increases storage, compression work and attention
pressure. its repetition is a handoff or echo of the same evidence, not independent
corroboration, a fresh discovery or human authorship. preserve that relationship
in compression and retrieval rather than promoting the copied claims. the
consolidated contract defines rendering/priorities; this decision changes no
runtime data.

### d07c: omit inherited copies only with proven archived coverage

omit an inherited fork copy only when native lineage proves inheritance and the
corresponding complete original is already retained centrally. native ancestry
alone, a parent conversation row/head or similar wording is insufficient. missing
or uncertain lineage/coverage means capture the eligible available copy from the
admitted fork, within its own activation and checkpoint boundaries. do not read
an unadmitted parent, backfill parent history or bypass an existing fork boundary.

this replaces the planned blanket exclusion of every native-proven inherited
prefix. cost: checking original coverage adds work, and uncertain/missing evidence
can retain duplicate history that competes in the shared tree. it prevents losing
eligible inherited context solely because its parent was never archived. previously
retained copies remain immutable; later proof does not delete or reorder them.

provider-runtime owns native inheritance evidence; jarvis owns proof of complete
central retention and the omission decision. keep originals and existing
checkpoint validation atomic. a proven omitted copy creates no new original or
public leaf. provider reads remain unfiltered within their activation/checkpoint
boundaries. emitted inherited events may carry closed native proof naming the
same-provider original conversation/event and pre-redaction digest. jarvis's ingest
transaction omits only a direct match to an already committed complete source-part
set. unavailable lineage/coverage recaptures conservatively. a missing direct
origin is not resolved through an earlier omission or an alias graph; native proof
of a retained earlier origin can match directly. retained copy attributes preserve
the closed proof; ordinary report events are not inherited fork copies.

the checkpoint becomes the last fully accounted-for native event, whether inserted
or omitted. add independently stored `checkpoint_native_digest`, paired with its
id, so inclusive checkpoint validation does not require a source row. insertion/
omission and checkpoint evidence commit together. all-copy batches advance with
zero new source rows/leaves; retries/empty batches cannot choose another cursor.
failed commits advance nothing; lost responses recover through central progress.
no skipped unfinished event, weakened conflict check, generic deduplication or
workflow ledger is authorized. this saves storage/compression, not native read or
upload traffic. the consolidated contract owns exact closed fields. no runtime
behavior or deployed migration changes.

### d07c2: original coverage and broad fork parentage suffice

retain matched originals and broad native fork parentage; do not preserve a
per-occurrence map for omitted fork copies. after native history disappears,
omitted occurrences are not independently addressable or exactly reconstructable
from central storage. their matched original evidence remains available under
its original identities. parentage alone cannot reconstruct a missing mapping.

cost: jarvis may not prove precisely which inherited events a given fork received.
the owner accepts that limit rather than adding reference records and open/rebuild
rules for exact inherited-occurrence tracing. this does not restore excluded
context bodies/reasoning or weaken direct-coverage omission proof. no extra
inheritance field, alias graph, mapping table or runtime change is introduced.

### d07d: retain supplied context as references only

retain available supplied instructions, environment context and native
compaction/replacement history as context references, not stored prose. apply this
to the provider's `context` event class, including recognized `other` context.
preserve context kind, available native name/reference, time and provenance;
where no external reference exists, the native conversation/event identity is
still a reference. these complete reference events enter the shared tree under
the existing event-unit rule. they are not fresh owner input, independent
confirmation or current authority. all reasoning remains excluded.

this replaces the planned capture of context bodies. native identity/digest still
binds the complete capture-relevant native event before body suppression; do not
store snippets, body-derived summaries or inferred contents in the reference.
ordinary messages, tool results and attachment text have their separate capture
contracts. retain context references even when their target is unavailable,
clearly indicating that body text was not retained.

cost: jarvis cannot recover former context wording from this archive if the file
or native transcript changes/disappears. a path or event id is a finding clue, not
an immutable copy or proof of present contents. this reduces repeated context
prose in storage, compression and the view. it grants no filesystem read, native
session replay or current-policy authority. exact rendering follows the later
provenance/retrieval choices; no runtime behavior changes.

### d08a revised: bounded tool-result archive text

on 2026-10-08 the owner replaced full-result retention with uniichat's permanent
30,000-character head/tail cap. retain both ends, an explicit omission marker and
the native source reference. the cap applies to the memory representation of
result text, not canonical tool/action receipts used for execution and recovery.
unchanged text below the cap remains intact. retain source identity/digest from
before this suppression so changed native content remains detectable.

cost: search and zoom cannot recover the omitted middle from the archive; only
an independently available original source may still contain it. smaller retained
results reduce storage and compression work. declared normalization occurs before
the normalized-event bound and central part splitting; it does not relax native
reader/transport bounds. no post-capture pruning of existing immutable records
or automatic history migration is authorized.

### d08b: retain exposed attachment text and references

the owner selected text already exposed by the native conversation plus its
source reference, within the ordinary bounds for the event kind. preserve known
text availability and omissions; do not claim a full document from an excerpt.
this capture adds no download, ocr or binary-copy step.

cost: retained text stays searchable after source loss, but the original image,
layout and unexposed content may remain unavailable. attachment text carried as a
tool result still follows the ordinary tool-result cap.

### d08c: durable originals belong to the attachment delivery

the owner kept original-file storage and image/document access in the planned
attachment feature, outside the first memory delivery. first delivery retains
exposed text and references; it does not copy attachment binaries. the existing
private-original-storage roadmap remains, without provisioning a service here.

cost: references may expire or disappear before that feature exists. this limits
later access to uncaptured content; a stored reference is not a durable original.

### d30: tools and basic inspection before a dedicated browser

the owner selected shared memory tools and basic operator inspection for first
delivery. a dedicated human-facing tree browser or export interface is deferred.
users can ask jarvis or a native client to navigate nodes and open sources through
the common tools; first delivery adds no separate visual browsing application.

cost: direct visual exploration of the tree waits, while the core remains
inspectable through its ordinary read operations and operator diagnostics.

### d36: email capture through actual tool observations

the owner confirmed existing email access through tools and rejected wholesale
inbox capture. actual email observations enter ordinary admitted capture under
its result limits. add no mailbox backfill, whole-inbox archive or new polling as
part of memory. separate event-source work does not implicitly widen that scope.

cost: email never observed through the existing path is absent from this memory;
retrieval can still use the live connector when needed.

## engineering completion, 2026-10-08

authority: after settling product choices, the owner said to proceed and emphasized
single-user prototype simplicity. these are engineering resolutions within that
scope, not additional features or runtime activation.

the consolidated [implementation contract](../universal-memory.md) now owns the
complete schema, public functions/tools, progress and execution boundaries:

- six memory tables: the three archive tables plus `memory_leaf`, `memory_node`
  and singleton `memory_state`. total fifteen after native main. allocate gap-free
  positions in the existing writer transaction; nodes are completed derived text.
  persist both frontiers, shrink flags, a parked error and one dream cursor.
- add immutable eligibility bits to canonical `message` and `native_attempt`.
  canonical receipts commit before archive projection. stable ids recover missing
  projections without another journal; legacy/disabled-period rows stay excluded.
  the library owns memory SQL and accepts caller transactions; jarvis owns the
  composed migration, admission and canonical publication.
- one serial no-tool compactor on the existing qualified model. 512-byte target,
  2,048-byte hard node bound, bounded feedback/transient attempts, explicit parking.
  retain 64–128 kb main and 16–32 kb compactor views. incomplete compact-frontier
  shrink cannot stall prefix progress; task context uses a fitting whole prefix.
  required construction runs while main awaits its frozen cutoff.
- closed `view`, `zoom`, `date`, `search`, `open` and note-save surfaces. external
  view pages use a small bounded in-memory snapshot cache, not durable client
  sessions. source-part zoom links to full-event opening; search stays independent.
- one fresh provider lease per top-level native runner call. exact current inputs
  and operational state remain outside lossy history; in-turn steering and
  entered-effect dispatchers retain their existing lifetimes. eager publication
  can put the current input in both the view and its exact operative presentation,
  under one canonical source identity.
- dreaming uses a 64-kb new-material view, four original-identity random samples
  within 8 kb, and one physical consumed cursor. output is 0–8 bounded attributed
  notes with run-supported record/range references. atomically append notes/leaves
  and advance progress. nightly attempt bookkeeping prevents repeated empty or
  failed attempts that night; backlog survives. manual dreaming remains available.
- explicit stopped derived repair preserves originals, positions, syntheses and
  dream progress. legacy notes/summaries remain searchable without historical
  import. no job tables, durable background replay, generic backend, live node
  versioning, separate service or model upgrade.

these choices deliberately retain postgres and jarvis's existing authority and
kernel boundaries. cheaper models, eight concurrent compactors and reference
cache percentages are not prerequisites. provider archive readers and llm-tools'
production transient read recorder still require implementation; their missing
public surfaces are delivery dependencies, not unsettled product choices.

the prior `mcp<2` blocker was stale: jarvis's actual lock contains no mcp, fastapi
or claude-agent-sdk. select and qualify compatible server pins during integration.

## reference audit

the public [optmem repository](https://github.com/VictorTaelin/OptMem), inspected
at [`1fb164cf`](https://github.com/VictorTaelin/OptMem/commit/1fb164cf39028047781f72ac3bb1e5a691c1dcb0),
is an explicit note tool. its
[source](https://github.com/VictorTaelin/OptMem/blob/1fb164cf39028047781f72ac3bb1e5a691c1dcb0/memo)
uses 280-byte notes, a default 96-line alpha-refitted wake view, raw blocks through
16 notes, binary merges above them, regex recall and zoom. the cli makes no model
calls; the agent supplies notes and summaries. it is not the pasted automatic
chat harness.

the supplied uniichat document is the newer design reference. its
[installer](https://uniichat.com/install.sh) and release endpoints could not be
retrieved in the original audit, and no installer was executed. release identity,
code parity, production quality and reported cache rates remain unverified.

the newer design corrects pair-start age to inclusive-last-position age, batches
128,000-to-64,000-byte view shrink, persists the actual frontier, gives compaction
its own 16,000–32,000-byte view and replaces historical rescans with ready queues.
it also changes prompts, size guidance, scheduling and cache marks. the accepted
contract adopts the useful mechanisms, with explicit bounded execution, independent
search and exact host authority. it does not treat the latest summary as truth.

for child span `n`, pair start `s` and prefix count `T`:

```text
due = (T - s - 2*n + 1) / n
```

the inclusive endpoint matters. at `T=10`, view `0+4,4+4,8+1,9+1`, the corrected
score is 0.75 for the old pair and 1 for the recent pair. start-based age picks the
old pair instead. the original scratch audit reproduced rollback-list equivalence
through 20,001 states with equal costs, ready parents and oldest tie-breaking;
the old rule matched only 481. this does not prove semantic optimality or behavior
under variable summary lengths and delayed construction.

its separate 30,000-event toy cache simulation found about fourfold lower priced
line-input cost for batching at similar average view size. real tokenization,
pauses, provider routing and summary quality were absent. batching preserves the
priority rule, not necessarily merge order: at different `T`, relative due scores
can change. the reference's 98.6%/96.2% cache figures are simulations, not jarvis
telemetry. official [openai](https://developers.openai.com/api/docs/guides/prompt-caching)
and [anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
contracts differ; only actual supported controls and measured usage apply here.

## migration and acceptance impact

this amends the unshipped target, with no runtime or canonical-data change.
implementation must demonstrate complete declared coverage, useful attribution,
bounded/fitting context, restart progress and unchanged current authority/effect
recovery. static documentation checks are not behavioral acceptance.

the consolidated [memory contract](../universal-memory.md) owns behavior and the
[roadmap](../implementation-plan.md#memory-delivery) owns delivery. the completed
interview inventory is removed; accepted decisions and research are retained here.

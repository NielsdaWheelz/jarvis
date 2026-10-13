# complete and continuable searches

status: owner choices settled, 2026-10-09; docs only. adopt in spec/an adr before
implementation, including the memory-search amendment below. the
[roadmap](implementation-plan.md#complete-and-continuable-searches) owns sequencing.

## target and boundaries

main can enumerate/search/list/fetch/read as many accessible items as it chooses,
across calls and turns. pages/chunks bound responses, not total coverage. no
application total-hit, candidate, historical-age, page-count or scan-duration
ceiling. existing admission, per-operation deadlines, physical resource bounds,
provider limits and permissions remain. no automatic exhaustive scan.

all historical gmail messages and their full available textual bodies are in
scope, including body text behind `attachmentId`. binary attachment content,
pdf/image interpretation and durable originals stay in the attachment feature.
calendar, places, web, shared memory, work and available worker history follow the
same principle. native notes use ordinary commands; no notes search service.

main chooses scope, depth, further queries, merging, deduplication and resumption.
use ordinary context/work/notes for query, cursor, completed-item progress and
remaining work when useful. no scan table, snapshot service, importer, background
scanner, search agent, compulsory procedure or completion controller.
observed emails enter memory through its existing rules, not a mailbox archive.

## result and continuation rules

retain closed per-tool schemas and source-specific rows. common meanings below
are a contract, not a new paging framework:

| field | meaning |
| --- | --- |
| `scope` | host-normalized source/account, selectors and filters; changing them requires a new traversal |
| `observed_at` | utc observation time; replay preserves the original |
| `items`, `order` | actual item unit and ordering; message/thread/file/event/record are distinct |
| `next_cursor` | nullable opaque next-call continuation; bound to tool/source/scope; not authority |
| `boundary` | `more`, `exhausted`, `provider_limit`, `unknown`; unknown may offer a next-page probe |
| counts | exact count, provider estimate or unknown explicitly distinguished; no estimate presented as exact |
| limitations | material exclusions, missing content/indexing, retained-history scope and live-source behavior |

provider-paginated google collections return ONE complete provider page or a declared `OutputTooLarge`
failure without advancing continuation. caller retries the same page with a
smaller page size. never discard an unread suffix and return the provider's next
page token. previews may clip with `clipped` plus an openable identity; exact
identifiers cannot clip. a single valid compact reference must fit. calendar/
place/calendar-list display prose becomes clipped previews, not exact-field
validation that can block enumeration; full values remain openable.

page sizes are batch controls, never total limits. defaults: 20 items; accept the
provider's supported per-page range. retained local collections use 1–100.
these defaults apply to changed APIs; work retains its existing limit/offset/
total/as_of contract, which already supplies continuation and observation facts.
fit the complete canonical success envelope, including escaping/framing, before
return. use a 64-kib jarvis page/chunk envelope and 32-kib input bound, tightened
through existing plans. maintain owner-library constants once; no per-profile
tuning. oversized exact detail goes through text chunks, not silent clipping.

text chunks contain source identity, projection revision, full projection
`digest`, `offset`, `end_offset`, `total_bytes`, `text`, nullable `next_offset`
and observation time. offsets address utf-8 bytes at character boundaries.
`max_bytes` defaults to 8,192, range 1–32,768; shrink to fit the full envelope.
positive progress or eof is required; too-small requests return `InvalidInput`.
offset zero starts a read; later offsets require `expected_digest`. no mixed
revisions: changed sources return `SourceChanged` before emitting new content.

reuse private automatically unlinked temporary files for large fetched/projection content, one current
source per adapter instance; replace/close removes them. they are disposable
working files, not originals/archive storage. after eviction/restart, a
redispatchable read may refetch and verify the expected digest. paid cached-source
continuations instead return `StaleCursor` before I/O; explicit new observations
cost a new fetch. parsing may
materialize one provider object; spooling alone is not constant-memory parsing.
never retain a corpus of fetched objects. storage/parse/deadline failures are
typed unavailable results, never a shortened success. preserve responsive ingress.

collections are live unless their owner already provides an actual frozen view.
empty pages can have continuation. invalid/expired/mismatched cursors fail
explicitly; no silent restart. live edits/indexing can cause overlap or gaps.
exhaustion means this supported traversal ended, not a point-in-time snapshot,
all relevant evidence found, or all returned content read.

## exact surface changes

existing selection arguments remain unless explicitly replaced here. all added
inputs/results are closed. initial cursor defaults null. opaque provider cursors
carry normalized-selector digest and original provider token; no cursor rows.

| tool | input / target result |
| --- | --- |
| `gmail.search` | hard-cut thread hits to message refs `{message_id, thread_id}` from `messages.list`; `query = null` means all, `include_spam_trash = true`, `page_size` 1–500, cursor; expose provider estimate separately; retire `max_results` |
| `gmail.read_thread` | `thread_id`, page size/cursor → paged message-id manifest from minimal `threads.get`; cursor binds manifest digest and offset; no bodies/newest-50 selection; retire `max_messages` |
| `gmail.read_message` | new: `message_id`, `section = message | body_part`, nullable `part_id`, offset/max bytes/expected digest → text chunk; body_part requires exact native part id and `text_view = decoded | readable`, message forbids those fields |
| `calendar.list_calendars` | page size 1–250/cursor → readable, nondeleted entries including hidden; preserve stable ids/access roles |
| `calendar.list_events` | required discovered `calendar_id`, existing time bounds/zone, page size 1–2,500/cursor → one provider event page; include hidden invitations; preserve single-event expansion and compact identities/times/status |
| `calendar.get_event`, `maps.get_place` | require `projection = snapshot | text`; snapshot branch takes existing ids, text branch ids plus chunk arguments; maps also requires `read_id: UUID`; tagged closed snapshot/text results share one fetch adapter |
| `maps.search_places` | add `search_id: UUID`, page size 1–20/cursor; request and expose `nextPageToken`; original query/bias remain fixed; retire `max_results` |
| `web.search` | add `search_id: UUID`, page size 1–20/cursor; llm-tools maps page offsets 0–9 and exposes provider continuation uncertainty/limit |
| `web.read` | existing url plus offset/max bytes/expected digest → chunks of complete supported extracted text; retain original destination/media/evidence checks |
| `work.list`, `work.get` | reuse [o7](work-records.md)'s unbounded sequence of bounded offset pages/current full record; changing work can shift offsets; no snapshot promise |
| `agent.list`, `agent.read` | add paging/text continuation through the bounded skid handoff below; preserve unavailable peers, target/source/output evidence |
| `memory.search`, `memory_search` | same shared ranked API amended below; existing view/zoom/open already navigate/page retained originals |

snapshot views preserve current exact normalized fields and strict write-sized
contracts. text views contain lossless canonical json of the SAME supported
normalized fields before presentation length/array validation, not new provider
fields/reviews. no automatic fallback. text is read evidence, never a weakened
write snapshot; mutation schemas remain strict.

gmail's message section projects all available header prose in native order,
including duplicates, plus a complete mime-part manifest: exact part id, media
type, filename/disposition, size and status: `container`, `text`, `empty`, `excluded_binary`,
`unsupported`, `unavailable`; last two include a reason. text/empty include the
exact next-call part reference, including a valid empty native root-part id.
containers have no body-read reference; retain their child structure/order.
empty means an empty supported textual leaf.
large headers/recipient/attachment inventories are text chunks, never fixed
998-byte/50-item reasons to block a body. body_part selects ONE textual leaf,
never a multipart subtree. supported textual mime parts remain readable regardless
of filename/disposition: `text/*`, `application/json`, `application/xml`.
decoded view preserves complete charset-decoded source text, including html markup;
readable view reuses inert visible-html extraction and otherwise preserves text.
both have distinct projection revisions/digests. preserve alternative part
references; never execute html or fetch subresources.
fetch only the requested external text part per operation, not every part in one
bounded call. malformed/unsupported text is an explicit omission/error. no separate
binary attachment request, decoding/output/interpretation or durable retention;
full-message json can incidentally contain inline binary data, discarded from
the retained projection. [provider body contract](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments).

replace the ordinary-mail 2-mib full-object ceiling with dedicated private
fetch/projection files and resource-aware per-message/part processing. ordinary
content reads must not change `MAX_PROVIDER_BODY_BYTES` imported by write
reconciliation. no invented source-size guarantee: Gmail permits large imports
and documents no ranged message/attachment get. [large imports](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import).
available space/process limits
and finite fetch deadlines remain genuine constraints, reported honestly.

calendar main discovers ids and iterates calendars/pages itself; never ask the
owner for ids. cross-calendar ordering becomes agent composition. retire host
fanout/aggregate 50-calendar/100-page/1,500-event cutoffs and permanent partial-turn
tracking: a page with continuation is normal, not an unresolved coverage failure.
retain exact timezone/end/cancelled-event parsing and independent fleet failures.
use the actual [event time/paging semantics](https://developers.google.com/workspace/calendar/api/v3/reference/events/list):
lower bound tests event end, upper bound tests start; an empty page may continue.
recurrence expansion uses a chosen finite time interval, with no global age/window
ceiling. an infinitely recurring future is not a finite collection to exhaust.

Brave freezes provider count in the cursor: changing count starts a new traversal.
its adapter retains only the current bounded provider page, serving byte-fitted
whole-hit prefixes with digest-bound within-page continuation BEFORE advancing
provider offset. lost cache is `StaleCursor`, never a hidden paid refetch. this
avoids losing hits or shrinking the provider's reachable horizon just to fit a
response. [brave paging](https://api-dashboard.search.brave.com/api-reference/web/search/get).
remove the client-side combined-result `limit` slice: all recognized web/news
hits returned by that page remain reachable. count/offset governs web results;
boxed news coverage is separately labeled, not a promised news pagination api.
report actual effective provider query/freshness selectors, including alterations.

places and brave are ranked provider searches, not exhaustive geography/web
enumerators. Places currently exposes up to 60 results per query; Brave has ten
page positions and may overlap. [places ceiling](https://developers.google.com/maps/documentation/places/web-service/text-search),
[brave limits](https://api-dashboard.search.brave.com/api-reference/web/search/get).
reaching their boundary reports the provider
limit/unknown, never complete web coverage. preserve web's current wire/decoded
safety bounds: `TooLarge` is unavailable content, not a completed document.

## uncapped ranked memory

this explicitly replaces [memory's](universal-memory.md#shared-search-and-open)
top-50 lexical/top-50 semantic horizon when adopted. preserve granted filters,
caller cutoff, english/simple full-text search, exact cosine scans, eligibility,
identity deduplication, attribution, tie order and equal-weight rrf constant `60`.

input: existing query/filters, required `search_id: UUID`, `page_size` 1–100
(default 20), nullable cursor. one postgres statement per page:

1. rank ALL eligible lexical matches by lexical rank descending and ALL eligible
   vectors by cosine ascending under the frozen admitted cutoff.
   preserve per-mode storage-time-descending then `(store,id)`
   ties; source storage time is `received_at`. no pre-fusion candidate limit.
2. join by `(store,id)`. with both ranks, compute one quotient
   `((60+l)+(60+s))/((60+l)*(60+s))`; with one, `1/(60+r)`.
   use numeric arithmetic before rank addition and one shared 80-decimal-place
   ordering key, sufficient for bigint ranks; cast numerator/denominator to
   `numeric(120,80)` before division. equal rational scores must tie; separately
   rounded reciprocal sums/integer division are wrong. sort score descending,
   then `(store,id)` bytewise.
3. apply keyset after last score/identity and `LIMIT page_size+1` AFTER fusion.
   preserve exact sql numeric scores as decimal strings, never rounded floats.
4. fetch previews only for selected rows, fit the result and advance after the
   LAST actually returned row. whole identities beyond the byte bound remain
   reachable. full prose/lineage remains `memory.open`.

retain at most 32 query contexts in the existing library instance: search id,
normalized selectors, actual cutoff and fixed embedding identity/vector; no
cached ranked sets. first
page embeds once; continuations use the same vector with zero external attempts.
cursor holds query identity plus exact last score/identity, at most 512 ascii
characters. first page freezes a cutoff within the caller's grant; a later higher
grant retains that original cutoff. changed query/filters under the same id or a
grant below the frozen cutoff fails. touch lru retention on each continuation;
the same context never embeds twice. recheck grants on every call.
restart/eviction returns `StaleCursor`; model may explicitly start a new scan/id.
no durable cursor table, held database transaction, timer or new service.

shared search throttle counts accepted pages, retaining 30 calls/60 seconds;
replay counts none. retain one client, inference semaphore and read-only pool.
ranking recomputes over the eligible corpus per page and can sort/spill in postgres.
qualify query/deadline against representative retained volume; timeout is typed
unavailable, never top-k or lexical-only fallback. indexing can move ranks even
within a fixed admitted cutoff; expose live-ranking limitations/missing vectors.
counts/limitations describe the current statement, not immutable scan totals.
unchanged-source traversal reaches every candidate, not every relevant fact.

## receipts and external composition

reuse current native journals, `ReadPositionRecorder`, `ToolExecutor`, grants,
`ToolLimits`, canonical-json measurement, transport/parsers and ordinary context.
one original callback replays its original result; continuation is a new callback.
redispatchable mutable reads on new invocations are fresh, not reused merely
because old unfinished requests had identical arguments.

paid memory/web/places search starts use explicit `search_id` as observation
identity, not permission. completed original observations can replay, while a
deliberately new id starts a new paid observation. do not auto-restart on failure.
maps detail's `read_id` similarly identifies one captured provider observation:
snapshot/text/chunk branches share it, fetching once; cache loss is explicit stale.
new ids cannot bypass an unresolved matching `BilledOnce` read. persist the
normalized source operation in existing `read_position.contract` before provider
entry, alongside its unchanged exact contract/input digest; no new columns.
its closed descriptor identifies provider/account, operation, selectors and
source position: query/filter/cutoff/seek for memory; original query/bias/provider
token for Places; query/freshness/actual frozen-count page window for Brave; exact
resource/field projection for paid detail. owning adapters derive this descriptor
from validated arguments, decoded cursor and frozen caller context before I/O.
exclude observation ids and local rendering/offset/size when they do not change
source I/O. original same-position proof remains byte-exact; this descriptor only
matches cross-attempt unknown barriers. preserve original positions/arguments/
receipts; never clear or redispatch an unknown slot. no extra ledger/quota.

skid adds `list --page-size/--cursor` and `read --cursor` with existing max-bytes.
new wire facts use existing camel-case style: `nextCursor`, `observedAt`, and
read source digest/native position plus text range. preserve wire omission rather
than null for absent optional fields; model schemas retain nullable cursor inputs.
retire read's terminal clipping flag as the continuation signal: normal unread
pages and genuine missing-history limitations are distinct.
inventory filtering/paging happens before transport fencing; deterministic
machine/handle order, live collection. native history reuses provider-owned
archive/history codecs and event/within-event continuation under a retained-prefix
boundary; no second transcript parser, resume/load or central-memory routing.
latest reads page the captured output revision; newer output needs a fresh read.
terminal reads page available retained/visible text with offsets/digest; changed
anchors fail explicitly. buffer exhaustion is not lifetime-history completeness.
keep target capture, writes, waits and operational controls unchanged.

## designer's content rules

results make scope, available continuation and material omissions intelligible.
ids support tools; prose supports decisions. snippets are previews, estimates
are estimates, ranked hits are candidates. distinguish enumerated, fetched and
actually examined material. provide useful progress for long requested scans;
silence/notice remains [o6](one-main-events.md)'s policy.
account for main's own work mutations: advancing an offset after completing or
deleting preceding rows can skip items. retain seen identities and restart from
zero when needed, or gather identities before changing membership/order. this is
agent judgment, not a prescribed scan controller.

good: `read 842 messages in the requested date range, including archive and
spam/trash. three text parts were unavailable. attachments were not examined.`
good: `reviewed 20 ranked matches; more remain. i stopped because the cited
originals answer the question.` no compulsory wording/report template or critic.

## non-overlapping delivery and acceptance

| owner / unit | exclusive files / result |
| --- | --- |
| jarvis connector contracts | `read_tools.py`, `connectors.py`, small new content-read helper if needed: gmail/calendar/maps pages/projections/errors; preserve write recovery |
| jarvis worker adapters | `agent_tools.py`, `agent_control.py`: new skid read/list schemas and command arguments |
| jarvis composition/presentation | `definitions.py`, `tool_composition.py`, `read_dispatch.py`, `read_positions.py`, `terminal.py`, `native_runtime.py`, `session-compatibility.json`, exact dependency pins: grants, freshness, original receipts, content and retired calendar aggregate tracking |
| memory library | shared public retrieval/schema module and postgres query implementation: uncapped ranking/query contexts; jarvis internal and mcp adapters consume one api |
| llm-tools | `web/contracts.py`, `web/brave.py`, `web/tools.py`, `web/reader.py`: portable web paging/chunks; consolidate repeated utf-8 slicing/envelope-fitting primitives where genuinely shared |
| skid + provider-runtime | skid `internal/agentcli/run.go`, `fleetclient/`, `gateway/`, `agentcontrol/`, necessary sessions/tmux read paths; provider `agent_runtime/archive.py` and existing native codecs: retained history pages without duplicate parser/store |
| deployment | dev-server publishes/pins/installs the matching helper/gateway/cli through existing fleet machinery; jarvis consumes qualified library pins |
| temporary proofs / designer | scoped integration/live files only; boundary/content evidence, no production edits by proof writer |

agree public contracts first. external units own transport/mechanisms; jarvis owns
product composition/authority. no new kernel api, application table or notes/work
service. update maximum envelopes/frozen grants together, advancing affected tool
contract/implementation/policy and composed definition/session revisions.
integrate shared files with one writer. adopt memory/search and affected
calendar/worker contracts together; drain/reconcile occupied old positions before
incompatible pins. preserve finalized evidence as opaque history. delete retired
clipped handlers, aggregate bookkeeping and old schema acceptance; no dual decoder,
fallback provider, alternate ranking or old/new tool path.

temporary red/green integration plus controlled synthetic live journeys prove:

1. more than 20 gmail hits/50 thread members, 50 calendars/1,500 events, 10
   places/web hits, 100 memory candidates and 32-kib worker output stay reachable;
   provider ceilings/empty pages with tokens are honest. unchanged fixtures have
   no missing/duplicated identities. include older mail, spam/trash and work pages.
2. last text suffix after 16/64 kib, >2-mib valid email, oversized headers and
   many external text parts, including named text/empty root ids, are readable;
   no separate binary attachment fetch/output. escaped/multibyte
   envelope fitting and byte-fit retries preserve unread content/items.
3. full rank-fusion ordering beyond former horizons, including equal rational
   scores at rank pairs `(60,60)` and `(20,180)`; one query embedding reused;
   missing vectors, stale contexts, altered scope/content and indexing changes
   are explicit. query cost fits representative volume, without hidden top-k.
4. identical callback replay, fresh new reads, continuation across main turns,
   explicit restart after stale cursors and original paid unknown barriers,
   including changed observation ids/rendering/cursor encodings. work mutations
   during scans do not cause avoidable self-skips; Brave byte fitting retains all
   hits under its frozen provider count.
   requested progress/finals describe actual coverage; more pages alone do not
   force a permanent partial terminal. no changed write/approval authority.

review contracts adversarially before implementation, then evidence/content after
green and after refactor. reuse existing primitives, remove actual duplication,
record final-tree integration/live evidence, delete temporary tests as requested
and run `scripts/verify`. this task changes docs only; behavioral/live checks are
not run. standing verification redesign and retained memory regression groups
keep their separate scope.

costs: more calls/time/inference; exact deep ranking can be expensive; calendar
composition moves to main; live collections can overlap/change; cursor/cache loss
can require a new scan and paid embedding; temporary content may need refetch and
large-object parsing uses memory/storage. provider/safety/availability limits can
leave explicit gaps. temporary test deletion leaves less regression coverage.

gmail enumeration/manifest reuse [message pages](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
and unpaged [thread get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get).

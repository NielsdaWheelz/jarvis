# complete mail/calendar/web reads

status: f1 implementation contract under [adr 0075](decisions/0075-v2-completion-and-subscription-model.md).
docs only, 2026-11-16; implementation and qualification pending. the
[roadmap](implementation-plan.md#v2-finishing-prs) owns sequence; this document
owns f1's interfaces and acceptance. no production activation.

source audit: jarvis `bbfeb47`, including landed slice 5; event candidate
`e704715` supplies the expected slice-6 profile/refresh composition. audit its
actual merged successor before implementation. llm-tools web is pinned at
`8989f3a`. the [older search proposal](complete-and-continuable-searches.md) is
reference only; its selected-domain schemas are superseded here.

## goal, boundaries and decisions

jarvis can keep reading accessible mail, calendars and supported web sources
through bounded calls. responses limit batch size, not total reachable items or
text. main chooses queries, depth, calendars, delegation and when to stop.
original callbacks replay original receipts; deliberate new observations can
read current state. provider limits and unavailable content remain explicit.

- keep existing mail drafts/replies/sends and calendar mutations, authority,
  immutable arguments and effect recovery. add correct incoming `Reply-To` reads.
- reuse slice 5's message/file manifests and attachment originals. replace the
  clipped `gmail.read_thread`; do not create another thread-manifest interface.
- no mailbox mirror, durable search cache, scan controller, new table, compulsory
  research sequence, additional orchestrator or model/runtime upgrade.
- no inbox housekeeping, new invitation responses, outgoing files, maps, worker
  history, memory ranking/capture changes, browser/javascript execution, web pdf
  interpretation or authenticated browsing. existing memory text caps remain.
- the owner selected disposable web result pages: after eviction/restart, an
  unread cached suffix returns `StaleCursor`; main may deliberately fetch again.
  no hidden paid repeat. no other product preference is outstanding.

trade-offs: deeper reads use more calls/context; per-calendar composition moves
work from host fanout to main. live collections can move during traversal; changed
pages/projections require explicit restart. large mail uses temporary disk and
may materialize one provider object in memory. web search retains one current
page, so interleaved searches can evict an unread suffix. these are explicit
resource/freshness limits, not shortened successes or snapshot guarantees.

## shared contract

reuse existing `ToolSpec`/`ToolBinding`, success/failure envelopes, execution
context, admission, clients, journals, canonical-json measurement and UTC clock.
inputs/results are closed; reject extra fields. native inputs explicitly supply
every declared field, including nulls. starting values below are documentation
guidance, not a normalization step before immutable invocation recording.

| value | contract |
| --- | --- |
| ids | message/thread/calendar/event ids retain 1..1024 utf-8 bytes; MIME part ids also permit the empty root id. never clip an id, address or url into a different identity |
| new input/result envelope | 32 kib / 64 kib, including full canonical-json framing and escaping; unchanged manifest/snapshot contracts retain their existing bounds |
| offsets/totals | strict integers 0..2^53−1; utf-8 byte offsets at character boundaries |
| chunk inputs | `offset`, `max_bytes`, `expected_digest`; start `0,8192,null`; max_bytes 1..32768; offset > 0 requires lowercase sha-256 |
| text result | `{source, projection, digest, observed_at, offset, end_offset, total_bytes, text, next_offset}`; closed source type per tool |
| digest | sha256 of canonical json `{source,projection,text_sha256}`; text_sha256 hashes complete projected utf-8 bytes. exclude observation time |
| continuation | emit positive progress or eof; shrink text to fit the complete envelope. offset beyond eof, inside a codepoint, or too-small max_bytes fails `InvalidInput`; offset at eof returns empty text and null next_offset |
| freshness | offset 0 with null digest starts a fresh observation; a supplied digest binds a continuation, including offset 0. mismatch returns `SourceChanged` before emitting content |

all text projections have a fixed revision in their binding/policy identity.
chunks of a json projection may split json syntax; concatenate matching byte
ranges before parsing. source identities stay complete in every envelope.
metadata and body text are untrusted evidence, never instructions or consent.

portable utf-8 slicing/envelope fitting belongs in llm-tools as small pure
primitives reused by web and google readers. source identity, projections and
provider cursors stay with their owners; no generic pagination framework.

## google pages

use slice 6's shared verified `GoogleProfile`, token-refresh serialization and
token-aware invalidation. one account is fixed for the running composition;
private-account replacement follows its stopped reconfiguration contract.
verify identity before starting a traversal or accepting an account-bound cursor;
never derive account from `me`, settings filenames or caller prose. resource gets
must match requested message/calendar/event ids before publishing observations.

one call fetches at most one provider collection page. keep all representable
items reachable: emit the largest whole-item prefix fitting the envelope, then
continue the same page before advancing its provider token. no internal page
draining, cross-calendar fanout, total-hit/page/age limit or hidden restart.

opaque base64url canonical-json cursor, at most 16 kib, closed fields:

```text
{version:1, tool, account, scope_digest, page_size,
 provider_page_token:null|string, item_offset, page_digest:null|sha256}
```

scope binds normalized selectors and fixed provider flags. page_size is frozen
for that traversal. offset zero starts a provider page; a local suffix requires
its complete projected-page digest, including its next provider token. refetch
that same page and verify before returning a suffix; changes return
`SourceChanged`. no durable page cache is needed. advancing uses the next
provider token with local offset zero. cursor parsing is not authority: recheck
account, tool, scope and field bounds before provider access.

never retry the same provider token with a different page size: calendar requires
the same request except `pageToken`. a new size means a new traversal.
[provider pagination](https://developers.google.com/workspace/calendar/api/guides/pagination)

google results need only nullable `next_cursor`; null means this live provider
traversal ended. empty pages can continue. counts are not inferred from page
length. malformed/expired/mismatched cursors fail explicitly. exact compact
references must fit; source prose is a labelled preview with a full read path.

## mail

| tool | explicit input | success payload |
| --- | --- | --- |
| `gmail.search` | `query:null|string` (existing 512-byte bound), `include_spam_trash:bool`, `page_size:1..500`, `cursor:null|string`; start null/true/20/null | `{account,query,include_spam_trash,messages:[{message_id,thread_id}],result_size_estimate:null|int,next_cursor,observed_at}` |
| `gmail.list_thread_messages` | unchanged landed `thread_id,offset,limit,expected_digest` | unchanged exact message-id manifest; lexical order, not chronology |
| `gmail.list_attachments` | unchanged landed inputs | unchanged descriptors/digest/pages; no duplicate file discovery |
| `gmail.read_message` | `message_id,section:message|body_part,part_id:null|string,text_view:null|decoded|readable,offset,max_bytes,expected_digest` | text result; source `{account,message_id,thread_id,section,part_id,text_view}` |

search uses `users.messages.list`, not thread search or per-hit thread fetches.
null query omits `q`; empty strings are invalid. the model may choose narrower
filters. preserve exact message and thread ids and the provider's estimate as an
estimate. provider order is unspecified; Gmail API search does not promise the
UI's alias expansion or thread-wide matching.
[message search](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list),
[search differences](https://developers.google.com/workspace/gmail/api/guides/filtering)

`section=message` requires part_id/text_view null and projects complete canonical
json, without ordinary-mail presentation/count limits:

```text
{message_id, thread_id, internal_at,
 headers:[{name,value}],
 reply_to_addresses:{status:absent|valid|invalid, addresses:[{name,address}],
                     reason:null|duplicate|empty|parse_error},
 parts:[{part_id,filename,media_type,charset,advertised_size,is_file,
         content_kind:text|empty|binary|unsupported|unavailable,
         reason:null|unsupported_type|unsupported_charset|invalid_metadata|missing_body}]}
```

headers retain all provider name/value strings in their original order, including
duplicates. reply routing is separate normalized evidence: absent has no values;
valid requires one well-formed nonempty header and a complete address list;
invalid has a reason and no suggested addresses. retain original evidence for
inspection; source display names/address lists do not inherit write-sized caps.
invalid routing must not silently become `From` fallback. existing
write `content.reply_to` remains the parent/thread identity, not this address
field. main selects recipients through the unchanged write contract.
[reply routing](https://www.rfc-editor.org/rfc/rfc5322.html#section-3.6.2)

reuse the landed MIME/header/base64 primitives. separate syntax traversal from
attachment policy, including the 100-mib decoding, 500-part/depth and header-display
bounds; no second walker or silent truncation. retain every leaf reference,
including a valid empty root part id. container reconstruction is unnecessary.
malformed optional metadata/unsupported charset marks that leaf unavailable;
headers and valid siblings remain readable. duplicate/unusable part identities
or structure that prevents trustworthy enumeration fail the whole projection.
filename/media_type/charset/advertised_size may be null when absent or unusable;
an invalid-metadata leaf retains exact part_id with unavailable/invalid_metadata,
never invented placeholder values.
raw MIME/header evidence cannot be rejected merely because a display name or
recipient array exceeds write-sized limits.

`section=body_part` requires exact part_id and text_view. fetch only that textual
leaf, including a body stored behind `attachmentId`. support `text/*`,
`application/json`, `application/xml`, `application/xhtml+xml`, regardless of
filename/disposition.
decoded view preserves complete charset-decoded source; readable view uses the
same inert HTML projection as web for html/xhtml and otherwise preserves text.
use standard MIME/codec rules, including text's default US-ASCII, JSON's UTF-8
and XML declaration/BOM encoding rules;
unsupported or invalid encoding fails explicitly, without replacement characters
or guessed alternate encodings. each view has a distinct projection revision.
never merge alternative parts, execute html or fetch subresources. file retention
and binary inspection remain attachment operations.
[message parts](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages),
[external bodies](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments)

## calendar

| tool | explicit input | success payload |
| --- | --- | --- |
| `calendar.list_calendars` | `page_size:1..250,cursor`; start 20/null | `{account,calendars:[CalendarPreview],next_cursor,observed_at}` |
| `calendar.read_calendar` | `calendar_id,offset,max_bytes,expected_digest` | text result; source `{account,calendar_id}`; complete canonical-json defined metadata projection |
| `calendar.list_events` | `calendar_id,time_min,time_max,time_zone,page_size:1..2500,cursor`; start 20/null | `{account,calendar_id,time_min,time_max,time_zone,events:[EventPreview],next_cursor,observed_at}` |
| `calendar.get_event` | `calendar_id,event_id,projection:snapshot|text,offset:null|int,max_bytes:null|int,expected_digest` | snapshot: `{projection:snapshot,event:existing read_tools.CalendarEventSnapshot,observed_at}`; text: `{projection:text,chunk:TextChunk}` with source `{account,calendar_id,event_id}` |

snapshot requires all chunk inputs null; text uses normal chunk inputs. preserve
strict read snapshot fields/limits, including cancelled/unspecified-end/addressless
variants; this is not the stricter write_tools snapshot. retain etags,
writable-state digest and mutation checks.
an overlarge snapshot returns `SnapshotTooLarge`; main may explicitly request
text, which is evidence, not a relaxed mutation snapshot. no automatic fallback.

CalendarPreview retains existing CalendarReference fields, replacing display_name
with `display_name_preview` (1024 utf-8 bytes) and `display_name_truncated`.
read_calendar uses `calendarList.get` and returns the original supported fields:
`calendar_id,display_name,time_zone,access_role,primary,hidden,selected`, without
display clipping. this is the full-value path for long calendar labels, not new
calendar management. enumerate every nondeleted reader-or-better calendar,
including hidden calendars, using the existing access-role vocabulary.
[calendar detail](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/get)

EventPreview is the existing normal/cancelled list union; normal adds
`status:confirmed|tentative`, and replaces summary/location with
`summary_preview,summary_truncated,location_preview,location_truncated`
(1024/4096 utf-8 bytes; location may be null). other identity/time fields stay.
text get_event is canonical json `{event,attendees_omitted}`: event has the read
snapshot's supported fields before string/array presentation limits. no new
RSVP/conferencing fields. `attendees_omitted` is the provider's boolean flag;
absent means false, malformed means `InvalidContent`. true makes snapshot mode
return `SnapshotIncomplete`, distinct from size failure.

repair the same omission in write_connectors._calendar_snapshot: reject true or
nonboolean `attendeesOmitted` before constructing its strict snapshot. reuse
existing unavailable/reconciliation handling; incomplete state must neither
authorize a mutation nor prove its result. public write schemas and effect
recovery stay unchanged; bump affected binding revisions. the
[source issue](issues/calendar-omitted-attendees.md) stays open until proved.

main discovers ids and composes calendars; never ask the owner for machine ids.
retain finite requested intervals, single-event recurrence expansion, cancelled
event semantics and hidden invitations. no fixed historical-age/window ceiling.
all-day values remain civil dates; unspecified end remains unspecified. timeMin
tests event end, timeMax tests event start. remove old 50-calendar/100-page/
1500-event/aggregate-deadline clipping and permanent partial-calendar tracking.
[event semantics](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)

## web: owning-library handoff

llm-tools owns the public schemas, Brave adapter, safe reader, evidence and
portable text helpers. jarvis consumes a pinned release; no copied web client.

| tool | explicit input | success payload |
| --- | --- | --- |
| `web.search` | `query` (existing 2..400 characters/50 words), `freshness:null|pd|pw|pm|py|date_range`, `page_size:1..20,cursor`; start null/20/null | `{scope,results:[WebSearchHit],provider,provider_request_id,observed_at,next_cursor,boundary,evidence}` |
| `web.read` | `url,offset,max_bytes,expected_digest` | text result plus `title,evidence`; source is exactly `{source_uri,final_url,media_type}` (no duplicate top-level identities) |

freshness date_range is valid inclusive `YYYY-MM-DDtoYYYY-MM-DD`, start ≤ end.
it is the provider's page-age filter, not a promised publication date. remove
`freshness_days`: its current rounding silently changes requested periods.
scope is the normalized OUTGOING `{source,query,freshness,country,search_lang,
safe_search,spellcheck,extra_snippets,result_filter,count:20}`. source is the fixed
composition-owned `{provider:brave,endpoint}`; credential bytes and caller-created
identities never enter it. hash this scope only. returned query alterations are
page evidence, never pre-I/O scope or authority. result_filter is null unless an
explicit fixed binding policy requests it; preserve existing wire defaults.
[Brave contract](https://api-dashboard.search.brave.com/api-reference/web/search/get)

Brave provider count stays 20; page_size only controls local result batches and
may change between continuations. offsets are 0..9. retain every recognized
web/news hit in provider order; news boxes are not a separate paginated news API.
WebSearchHit retains existing fields and limits, except rank becomes positive
page-local rank without the old maximum10. add `source_kind:web|news` and
`truncated_fields:[title|display_url|snippet|extra_snippets|published_at|source_name]`
(unique); extra_snippets marks clipping of any member or of the list itself;
urls stay exact. preserve mixed provider ordering, then append unreferenced
recognized hits. each page also returns `provider_offset,provider_count:20,
more_results_available:null|bool,provider_query:{original,altered,cleaned}`
(nullable strings) and `omissions:[{source_kind,provider_index,reason}]`, where
reason is `invalid_item|missing_url|unrepresentable_url`. disclose unusable hits;
do not drop valid hits to fit. retain existing search evidence
`{type:web.search,provider:brave,provider_request_id}`. page metadata must fit
exactly; unrepresentable metadata is an explicit upstream failure, not clipping.

one immutable current provider page per bound search adapter, identified from
its original ExecutionContext.position. no caller-generated search_id. cursor
is a closed opaque tagged value, including scope digest:

```text
items:    {version:1,kind:items,scope_digest,page_id,page_digest,next_index}
provider: {version:1,kind:provider,scope_digest,count:20,offset:0..9}
```

items cursor may ONLY read that cached page, with zero external attempts;
eviction/restart returns `StaleCursor`. emit a provider cursor only after all
current-page hits are returned. using a provider cursor is a deliberate live
provider-page observation, even if used by an earlier callback. initial null
cursor similarly starts a fresh observation. original callback replay remains
journal-owned. no hidden fetch after a local cursor or implicit retry.

boundary is `more|exhausted|provider_limit|unknown`: cached suffix is more;
otherwise use the provider's explicit more-results flag. short/empty pages alone
do not prove exhaustion. missing flag allows the next offset with unknown;
offset 9 with no explicit exhaustion reports provider_limit and null cursor.
overlap/ranking/provider ceilings prevent an exhaustive-web claim.

web.read retains existing allowed media, DNS/peer/redirect checks and wire2-mib/
decoded4-mib/deadline bounds. keep one complete extracted document in memory;
remove both 64-kib text clipping and output-fit prefix loss. plain text/json
preserve whitespace; HTML uses the existing inert visible-text projection,
exported for mail reuse. no scripts, browser, auth or format expansion.
cache miss can refetch a redispatchable text read, but must verify the complete
projection digest before emitting a continuation. preserve honest fetch times.
`evidence.content_sha256` continues to identify upstream decoded bytes; the new
projection digest is distinct. policy/evidence locators carry the full text range
and projection revision; do not call an unread suffix an extracted omission.

## recovery, resources and failures

add only f1's new/changed google and web.read tools to scoped fresh-read handling.
do not put paid web.search into the early `FRESH_READ_IDS` bypass. preserve
unchanged memory/maps/worker policies. new callbacks are fresh; exact original
invocations/results remain immutable. continuations are new callbacks.

llm-tools exports a pure `web_search_source_operation(value, policy)` helper
shared by its request builder and jarvis's recovery adapter. tool_composition
binds the SAME immutable provider options once for the binding and helper, and
passes the bound helper to the existing recorder. no separately reconstructed
query/cursor normalization. from validated arguments, decoded cursor and policy
it returns null for items-only reads, otherwise:

```text
{type:brave_search_page,source,query,freshness,count:20,offset,
 country,search_lang,safe_search,spellcheck,extra_snippets,result_filter}
```

persist `web_source_operation` as this closed object or null in the existing
read_position.contract BEFORE provider entry, alongside its unchanged base
contract/input digest. stage it by immutable invocation position during native
read recovery and merge/validate it when occupying that position. no extra table,
generic execution hook or mutable global turn state. unknown paid operations on
the causal component match this source operation, excluding local batch sizes,
cache ids and rendering arguments; changing those cannot authorize a repeat.
known completed results do not suppress a deliberately new search. a stored null
proves a network-free items path; an absent field does not. unresolved old paid
positions on outstanding resumable causal components block incompatible cutover;
settle or explicitly disposition those requests through existing operations.
historical stopped/completed components retain opaque evidence and never replay;
they do not create a new deployment gate. do not backfill source-operation proof.
same-position original replay preserves exact full contract equality.
if read_position.result committed before the native reply, recover that original
result BEFORE cache lookup or network, even after eviction/restart.

web.search remains BilledOnce; local cache reads/stale errors settle zero actual
external attempts. public web.read and google remain redispatchable. count each
real provider attempt through existing execution context before entry; retain
admission checks, cancellation and provider errors. no network during validation.

google collection/snapshot operations use a 30-second work deadline; text uses
300 seconds, with 10-second connect/60-second text inactivity limits. share one
deadline across profile/resource/body requests. grant at most four external
attempts for profile+page/detail, six for profile+message+selected external body,
including permitted authentication retries. no page-draining loop. web retains
existing fetch/search operation bounds and actual-attempt accounting.

google full-text reads have no fixed source-byte ceiling: use private automatically
unlinked spools and existing joined blocking-work primitives for standard json,
base64 and projection work. retain at most one current google text projection;
replace/close cleans it. disk/memory/parse/deadline failures are explicit, never
shortened success. parsing may materialize one source object; cancellation joins
entered blocking work before releasing its files and can outlast the deadline.
keep ingress responsive. attachment100-mib/transport policy and write
reconciliation's 2-mib bound remain unchanged. large imports are possible.
[Gmail import](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import)

retain existing provider/not-found/auth/rate-limit failures. added closed failures
are tag-only `InvalidCursor`, `AccountChanged`, `SourceChanged`,
`UnsupportedContent`, `InvalidContent`, `ResourceUnavailable`, `DeadlineExceeded`,
`SnapshotTooLarge`, `SnapshotIncomplete` and web `StaleCursor`, where applicable;
reuse existing types.
invalid caller ranges/field combinations use existing input rejection.
never log credentials, message bodies, raw exceptions or cursor payloads.

## ownership, removal and implementation order

| boundary | owned changes; do not overlap |
| --- | --- |
| portable web/content | llm-tools `web/contracts.py`, `brave.py`, `reader.py`, `tools.py`, exports; public schemas/cursors/evidence, operation helper, inert HTML and UTF-8 helpers; no jarvis policy |
| google reads | jarvis `read_tools.py`, `connectors.py` and one focused content helper if needed; source-specific schemas/cursors/MIME/projections/spools; consume landed event profile/refresh and attachment primitives; narrow omitted-attendee guard in `write_connectors.py` |
| recovery/composition | jarvis `read_positions.py`, `read_dispatch.py`, `tool_composition.py`, `definitions.py`, `session-compatibility.json`, dependency lock; source-operation persistence, fresh reads, exact catalog/bindings and ordinary prompt guidance |
| obsolete coverage | `terminal.py`, native presentation/dispatch callers; remove only retired aggregate-calendar obligations and types after auditing consumers; factual scope disclosures remain main's job |
| integration/content | one integrator coordinates shared pins/catalog; tests actual combined paths and preserves attachment/event/write behavior; f2/f3 keep native reliability and model/runtime ownership |

start with the red journeys below. library and google work can proceed in
separate files after contracts settle; composition adopts the published upstream
commit. preserve unrelated upstream changes. remove old thread reader/types,
newest-50/body clipping, host calendar fanout/aggregate coverage machinery,
discarded page tokens, web result/text slicing and freshness-days approximation.
retain only parsers/constants still used by writes, attachment or event owners.
no legacy tools, compatibility wrappers or silent fallbacks. bump changed binding,
tool/role/projection revisions and exact dependency pins; audit every catalog and
prompt reference. native publication must expose exactly the resulting schemas.

## content and acceptance

each feature's implementer pairs with a content designer and an independent
adversary. review schemas before code, red evidence, green journeys and final
refactor. no standing review service or compulsory model procedure.

| surface | good content |
| --- | --- |
| mail | exact message/thread/part identity, source date and honest routing; whole headers and alternatives remain reachable; no suggestion that reading text inspected attachments |
| calendar | named calendar with exact ids, typed times/status, useful previews and full-value reads; no invented midnight/end/attendee completeness |
| web | ranked hits distinguished from fetched evidence; exact source links, range/digest and useful source text; no complete-web claim |
| owner response | findings first, useful citations; disclose only omissions material to the conclusion. keep cursors/provider ids out of ordinary prose. success claims follow actual receipts |

examples: “reviewed 84 messages; two text parts were unavailable; attachments
were not examined.” “found three conflicts in work; personal was unavailable.”
“the draft uses maya's reply-to address and original thread; it is not sent.”
counts must follow observed evidence, not provider estimates.

| temporary proof | acceptance |
| --- | --- |
| mail depth | reach a hit after20, message after50 and controlled textual tail beyond100mib; externally stored text, alternative/html parts, long/duplicate headers and valid text beside a problematic binary sibling remain reachable; malformed Reply-To is distinct from absent |
| google paging | pass old calendar/event horizons using controlled provider pages; empty continuing pages, intra-page suffixes, expired/mismatched cursors, account change and live-page edits cannot silently lose/mix items |
| calendar detail | long descriptions/labels and large attendee arrays readable in text; complete representable observations support unchanged write inputs; omitted attendees cannot authorize mutation or prove its result; all-day/DST/unspecified-end/cancelled cases remain truthful |
| web | reach later provider pages and every local suffix; fixed provider count20, explicit more/unknown/limit, overlapping hits, exact freshness and full supported text; preserve security/resource failures |
| bytes | utf-8 boundaries, escaping-heavy text, envelope fit, empty/eof/invalid ranges, nonprogress and changed digest; unchanged bytes reassemble exactly |
| freshness/recovery | new google/web observations see mutations across turns; original callback receipts replay byte-identically, including crash after read-result commit but before native reply; cache eviction returns explicit stale or digest-checked refetch according to tool |
| paid uncertainty | crash after Brave entry; changed local page size/cache identity cannot repeat matching unknown IO. local-only cursor path enters no network and cannot create a false unknown-charge barrier |
| live usefulness | temporary candidate uses real authorized Gmail/Calendar/Brave/public page; reads useful mail/calendar/source material, creates a controlled unsent threaded draft and a disposable owner-only calendar event using unchanged writes; verify exact receipts/state and clean task-owned resources |
| composition | real main sees the published schema/prompt, follows continuation, makes a sourced conclusion and stays responsive to new input; verify attachment/event reads and receipt recovery after restart |

use synthetic controlled fixtures for huge/malformed/crash cases; never copy
private mail into fixtures or ordinary logs. no third-party sends/invitations,
production activation or broad benchmark. preserve the original native failure
issue if encountered; f1 success does not resolve it by assertion.

red → implement at the owning layer → green → refactor/re-run affected journeys →
adversarial review. run `scripts/verify` and required upstream checks; preserve
approved memory regression groups. record exact commits, exercised boundaries,
limitations and cleanup here, then delete only these temporary probes/resources.
final f2 combined acceptance and stopped production cutover remain separate.

# 0124 · cited sources and work in the viewer

source and controlled candidate qualified. installed acceptance is open. amends [0091](0091-source-backed-reports.md) and the reader in [0118](0118-chat-reading-and-approvals.md). mail editing belongs to [0119](0119-owner-gmail-draft-editor.md), exact draft history to [0121](0121-exact-chat-draft-revisions.md) and file custody to [0120](0120-drive-files.md). use [0122’s contextual back](0122-chat-sidebar-and-phone-alerts.md) and [0123’s artifact library](0123-artifact-library.md) on their cuts. only deliberately published pages enter that library. a citation or expanded table stays with its message.

## what the owner gets

“friday’s review moved to 2:30 pm pacific.” **maya's email · nov 25** opens the passage jarvis read with its surrounding text. **design review · nov 27** opens that occurrence, its time zone and when jarvis saw it. either takes one tap. an existing verified pdf link can open the cited page. verified files and google docs use 0120’s file surface when available. ordinary web citations keep their external links. desktop keeps chat beside the source. on a phone, back returns to the exact citation with the unsent reply intact. “show me maya’s email” may open it directly in the asking web tab under the existing presentation rules. other tabs, polling and notifications leave the reader in place.

| request | result |
|---|---|
| which quote is cheaper? | answer with both comparable totals, units and difference in chat. a small table can stay there. |
| compare fourteen bids | give the deciding finding and exceptions in chat. **expand table** shows the same rows full width. use a named, revision-pinned private page for interactive comparison. a requested working spreadsheet gets a verified file in the requested format. |
| explain the discrepancy / write the report | a full explanation can stay in chat. a portable report has a title, date, findings, limitations and sources beside its claims. keep the actionable conclusion, decisive caveats and their sources in chat. |
| inspect a photo, attachment or draft | link the original, exact page, or verified draft by name. suggested email wording can stay in chat. a real draft opens from its verified link. once 0119 is enrolled and qualified, its trusted editor owns reviewed send. |

the owner selected prospective citation binding. old replies retain their original links. a failed binding leaves the answer visible with **source unavailable** at the citation. reports may include short supporting quotations where needed with source name and date. keep complete private mail at its source. a quote already placed in a report can travel with that report even if its private citation later closes. creating a report never sends it or widens its audience. shared destinations follow 0120. opening a source is read-only.

## reply and evidence contract

add an ordered `sources` array to the [native final and seal](../../src/jarvis/native_protocol.py). progress and silence use `[]`.

```text
source = {request_id, kind: "mail"|"event", item, reads: [original_invocation_uuid,…], passage: string|null}
```

`request_id` names one delivered input disposition. `item` is the observed gmail message or calendar event id. get original ids from `native-invocation:<uuid>`. mail may supply an exact lookup quote. each route emits the same closed wire schema. a structurally invalid native final follows normal protocol recovery. wrong, missing or unprovable evidence in a well-formed final fails only its slot. inspect at most 32 slots, eight distinct reads per slot and 512 utf-8 bytes per quote. invalid or excess slots render **source unavailable**. preserve slot numbers and the answer. long mail can therefore be an excerpt.

place a normal markdown link beside the claim, e.g. label “maya’s email · nov 25”, destination `#source-1`. its one-based positive decimal selects a slot on this final. only a parsed link node with a bound slot opens a source. code, image syntax and owner text confer no access. explicit `present={request_id,ref:{kind:"source",slot}}` uses that slot’s request id and existing tab/lineage checks. the host resolves it to the new reply’s address. reserve source refs for reading and final presentation. an explicit target precedes automatic draft presentation.

bind during the existing [final settlement](../../src/jarvis/native_journal.py) transaction, for both live and recovered seals. validate against the exact current locally enrolled workspace grant and the reply’s owner conversation, named input and successful delivered observation. match request_id to a named, delivered, unstopped input.

- require a nonempty intersection of the callback's recorded inputs with the named input's causal component. every other recorded input must also be a named, delivered, unstopped disposition of this same final. otherwise the slot is unavailable. a later steer does not invalidate an earlier read.
- reuse [workspace receipt joins](../../src/jarvis/workspace_checks.py), [original read positions and causal scope](../../src/jarvis/receipt_tools.py) and the callback's recorded result reference. verify an accepted callback with a recorded successful result reference delivered for this attempt and eligible input. a recovered callback can reference an earlier original. alternatively accept this attempt’s successful scoped `receipt.read` pages for the named input reopening that original (`open`, part `result`, one digest, full byte coverage). a listing, partial reopen or memory never suffices.
- a new top-level follow-up can revisit an old reply’s existing link. binding a new slot requires its own eligible observation and may cost another provider read. keep standing-check evidence and restricted-recovery grants independent. restricted recovery may expose only independently admitted evidence for its named input and never auto-present. settlement does no provider i/o. replay under the same grant produces the same slots. replay after a fence cannot restore access.

use the following rules on successful, recognized [workspace read results](../../src/jarvis/workspace_reads.py). render provider text literally. expose only the selected item.

- **mail.** `gmail.get_message` pages metadata as json bytes. decode only contiguous [0,total) under one digest. show present from, to, cc, date, subject and reply-to in that order, then observed filenames. incomplete metadata says **metadata partial** and contributes no fields. valid independent body ranges still render. join on grant, account and message. group ranges by part, text representation, digest and total. validate byte bounds and overlap. mark unread ranges between adjacent excerpts of the same part and digest at their actual location, using one-based byte positions in the viewer. never splice versions. prefer observed readable text for html. if only decoded html was read, label it source text and render it literally. a separately cited `gmail.search` preview for the exact message can supply sender, subject and date when returned. use a complete observed header for a field when present. a preview can fill a field with no observed header. a disagreement within either evidence tier omits the disputed field. thread member ids supply no body. missing fields stay absent. label metadata only, excerpt, missing ranges and unsupported parts honestly. identify disputed fields in omissions. a single part never proves the whole message was read.
- **passage.** ask main for one distinctive clause. locate a unique literal match in a contiguous observed body range. different whitespace or a line wrap can miss. store its part/digest and utf-8 start/end. open there, with surrounding observed text. if the mail itself verifies but the passage is absent or ambiguous, open the recorded excerpt and say **exact passage unavailable**. no fuzzy match. a verified read proves provenance, not whether the model interpreted the words correctly. store offsets in the presentation index.
- **calendar.** one event slot represents one observation. multiple observations require separately dated slots. reject a multi-read event slot. require a null passage and one selected item of `calendar.get_event` or `calendar.list_events`. bind its calendar from the invocation and its exact event id. return the observed title, start/end and zones or all-day dates, status, location, description, attendees and recurrence identity when present. keep cancellation, missing fields and the original start of a moved occurrence. show observation time separately from a provider update time. never substitute the series or a later observation.

store `message.home.sources_v1` atomically with the final. a slot contains the grant id, subject, kind, item selector, original read ids and verified range, or an unavailable sentinel. batch distinct original ids at settlement. history reads return slot metadata only. the original receipt owns the text. the native seal can retain the lookup quote.

**access and outages.** on each open, and again before release of content, check the agent token manager’s local `enrollment()` identity. ordinary token refresh keeps its grant. known disconnect or replacement closes old previews, even after same-account reenrollment with a new grant. on each existing visible refresh revalidate the open slot with a bounded request. on timeout, failed check or access loss clear private fields and provider link, preserve typing and offer retry. discard late responses. recheck before redisplay on resume/back. store only the locator in history. the owner accepts blanking during temporary outages. a provider-side revocation remains unknown until jarvis learns of it. chat, receipts, shared memory, search, derived findings and backups retain their existing custody. published editions and notes git history survive withdrawal and disconnect. exported drive files or sent reports can outlive both. the [data-use determination](../issues/google-workspace-retention.md) must cover these copies, destinations, human replay and the bounded quote before directing real workspace material there.

## private client contract

| owner read | response |
|---|---|
| existing message list and detail | `sources:null` on pre-cut rows, otherwise ordered `[{slot,kind,state}]`. `available` means bound and locally permitted. open rechecks the evidence. a missing slot label is unavailable only on a new final. |
| `GET /api/messages/{reply}/sources/{slot}` | owner-scoped, private/no-store on both clients. wrong pair 404. bound but damaged, unavailable or fenced returns 200 `{state:"unavailable"}` with no data or provider link. transport failure offers local retry. |
| `/m/{reply}/source/{slot}` | trusted shell or native reader, independently openable. no mutation, general receipt endpoint, editor grant, inference or google call. |

```text
available = {state:"available",kind,observed_at,coverage,fields,segments,focus,original_url}
coverage = {kind:preview|excerpt|event,omissions:[text],passage:matched|missing|unrequested}
field = {label,value}                         # ordered literal strings
segment = {part,digest,observed_at,start,end,text}
focus = {part,digest,start,end} | null        # half-open utf-8 byte offsets
```

`observed_at` is UTC, latest included read. retain individual observation times when they differ. unknown optional values are null. keep every value inert, including literal html in a source-text excerpt and event descriptions. never render provider markup or fetch remote assets. exclude partial header json, unrelated result rows and transport metadata. **open current in gmail/calendar** is an explicit secondary link from the recorded, resource-validated url when available.

- extend the 0118 web and compose readers once. recognize actual gfm table nodes. show **expand table** on a wide table that overflows its available column. `/m/{message}/table/{n}/{digest}` displays the one-based parsed table from the existing exact-message read. reuse the same semantic renderer including headers and bound citations. no new table api, file, generation or data conversion. bind the ordinal to the full lowercase sha256 of its source block (utf-8, crlf/cr normalized to lf, complete original lines including indent and excluding the final newline). mismatched ordinal or digest shows unavailable. both clients must resolve nested and same-heading tables at the same source lines. wait for or co-deliver 0118’s reading slice. the current link scanners do not parse tables.
- use existing browser history and android visit state. restore the source message, originating link or expand control, view-relative offset and focus on warm back. a citation opened in an expanded table returns to its cell and local scroll first. cold entry offers **back to message**. keep native editor handoff and draft protection distinct. refresh preserves local focus, selection and typing. at 320px and enlarged text only the wide block scrolls sideways.

## ownership and delivery

each feature has a content designer before its implementer. freeze one good, one misleading and one failed specimen against the schemas above. record what the reader must be able to recover. one writer per path. freeze the wire examples before client work. serialize shared client, route and handler changes against the actual 0118/0120/0122/0123 merges.

| unit | exclusive files and work | designer's specimen and failure |
|---|---|---|
| a · evidence and reply | `src/jarvis/{terminal,native_protocol,native_journal,workspace_checks,receipt_tools,home_refs}.py` and a small `citation_sources.py` if it absorbs the shared selection/reading rules. own binding, projection types, seal change and recovered reads. reuse existing tool results and association checks. | two same-title events. only friday's moved occurrence is cited. a search preview saying “meeting” cannot vouch for the new time. missing evidence yields a visible unavailable citation. |
| b · owner read | `home_reads.py`, `home_http.py` and service/cli wiring under `src/jarvis/`. consume a's projection. wire a local enrollment-status reader. own the scoped route, private response, 426 checks on the named api handlers, list/detail parity and access loss. use content-free reason codes in existing diagnostics. | “excerpt jarvis read · wed 10:14”. a foreign id, disconnected account or broken range yields no private fields. |
| c · web | `src/jarvis/static/home/`. extend 0118 parser/navigation, reuse file/view/draft links and the existing history/focus owners. | two sources on one sentence. expand the second of two tables with the same headers, inspect a cell’s source, go back twice. no polling-driven jump. |
| d · android | `android/app/`, including `Routes.kt`, `MainActivity.kt`, `Home.kt`, `HomeApi.kt` and manifest. reuse compose reader, private auth and saved visit stack. | same specimens with large text, talkback, keyboard open and a half-written follow-up. source opens read-only in the app. back restores the same trigger. |
| e · work delivery and release | `definitions.py`, `session-compatibility.json`, `native_cutover.py`, necessary release/preflight wiring and documents. owns prompt, integrated contract size, cut and evidence. no new artifact service. | “hold the payment. two invoices were already paid.” the portable reconciliation covers every invoice, source and uncertainty. a private interactive page is never described as a downloadable spreadsheet. unknown creation or unverified contents is reported as such. |

e replaces the conflicting full-report prompt. use “open the draft from its link” until 0119’s production enrollment is verified. the editor rollout owns send instructions.

the owner selected private source detail in the linked chat reply. put names, dates and short quotes in the publication. first deliver a new sourced report edition from the final containing those citations, so 0123’s **open chat message** reaches them. opening from a later chat returns to that actual reply. a preexisting edition keeps its recorded first delivery. never give its frame a receipt lookup or navigation bridge. at the 0123 cut, use its verified passive `artifact_links` for published editions and its title metadata. reserve `present` for the asking tab.

keep file links named by the known filename/page. remove duplicate result links. keep 0118’s single destination classifier per client and retire its predecessor `prose()` / `Prose()` scanners with that cut. reuse [published private pages](0087-private-web-home.md#authored-canvas) for interaction and existing verified original/page links. a standalone report must carry human-readable source names/dates and enough evidence to travel, including where private links cannot open for its recipient. 0120 owns actual downloadable/generated files and their verification. keep the original format and audience. an html view or local path cannot satisfy an explicit csv/pdf request. if a required format cannot be delivered, say so. ordinary chat includes a useful conclusion even if publication fails. leave the home selection alone. 0119 production enrollment, check and matched release stay on its [existing rollout](../issues/owner-gmail-editor-live.md).

## acceptance and hard cut

1. for each unit, run temporary end-to-end checks through the real entry point, observe the specific old failure, implement, pass, simplify and replay. on macbook use the detached rehearsal wrapper, actual main/final settlement, postgres, web browser, native app and controlled google. verify a fresh callback, an earlier original legitimately delivered during recovery, sealed replay, unrelated/foreign/failed/revoked reads and no provider or model call on open/back. prove partial mail, changed occurrence, missing quote and duplicate link occurrence with literal hostile-looking markup. inspect traffic and actual returned content. time maximum-size binding under the existing conversation lock on macbook and record the duration. a known partial receipt reopen cannot bind.
2. on desktop and phone run the designers' linked journeys, a cold link, hidden/second tab, failed local read and disconnect while open. verify zero focus theft and an intact composer. compare both tables cell-for-cell and exercise links from the expanded table. use a one-line price answer and a six-item handover with a payment warning. include a ragged input with an extra field. authored tables must preserve that field under a named column or flag it in the answer. open the resulting deliverable independently and recover every finding, unit, source and caveat. a requested file must reopen with the verified format/content. use 0120's existing proof when integrated.
3. obtain independent opus review of each final feature and its evidence. keep named evidence outside scratch, reopen and hash it, record cleanup separately, then delete only the temporary probes/fixtures. controlled runs can exercise races. they cannot prove the real account or signed handset. the owner selected **a separately authorized check on their account** with named synthetic mail/event fixtures, real subscribed main, desktop and signed phone. agree on setup, any event change and fixture cleanup at that time. no live data or production action is authorized by this design.
4. rotate the main binding and advance the native output name from `jarvis_home_message_v3` to the next unused revision across every active provider and sealed-settlement path. on each selected route (personal codex, google neon, agy neon), verify the actual prepared instructions and schema fit, the tool return exposes the original ref, and a controlled end-to-end produces bound mail, bound event and empty-source finals. record unavailable routing as unqualified. inventory and settle incompatible in-flight and sealed products on their original release before switching. stage service, web and signed android together. require `x-jarvis-viewer-contract: cited-sources-v1` on message list/detail/submission and the new evidence endpoint. missing/stale gets 426 before any effect. use one selected contract value across 0120 integration, rotating it again if that later release changes the wire. close/reload/update before resuming under [0104](0104-maintenance-without-owner-pause.md). retire replaced reader/prompt branches with their matched cut. no parallel decoder, renderer, URL-guessing bridge or historical rewrite. preserve unrelated proposal, scheduled-check, receipt and draft behavior. report source, candidate and installed results separately.

## implementation evidence

candidate `4dfc7b2598b38bcf71f7668f21974ad5f5334b3c` composes 0122 and
0123 through `0e0c1f7`. exact macbook rehearsals passed the static/build
checks and 27 controlled integration assertions. chrome and the android
emulator opened retained evidence through the real http routes and postgres.
the browser followed the first chat delivery from a sandboxed pinned report.
the previous native app received the update state. stale web submissions
received 426 before execution. both readers matched all 20 gfm table cases.
the largest binding fixture, 32 sources with eight 32,768-byte reads each,
took about 0.13 seconds.

the matched cut uses request v8, native output v5, main binding v31 and
`cited-sources-v1`. every provider prepared the new contract within its
existing limits and replayed its own synthetic seal format. putting the new
policy and the verbatim recovery instructions in the developer channel kept
the unrelated main wording intact. the native drive ref now requires a
nullable page and todo results require a nullable file ref. codex requires
every output key. owner file links retain their existing input contract.

opus passed the controlled candidate at `f6d1972` and closed the unread-range
and header-precedence findings at `4dfc7b2`. receipts and the retained evidence
index are under `~/.local/state/jarvis/qualification/adr0124-implementation.dTElGg6R/`.
the checks and fixture removals have separate receipts. temporary drivers and
the debug emulator were removed after review. the
[installed and live qualification](../issues/citation-viewer-live.md) remains
open.

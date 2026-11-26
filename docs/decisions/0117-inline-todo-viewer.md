# adr 0117. read todos inline in the viewer

**source implemented and isolated candidate qualified · november 26, 2026**

the owner wants to scan the whole active list and open a few items alongside one another. today the web header and sidebar both offer todos. opening a title puts the record in the sidebar, which covers the list on a phone. android opens a separate screen. both clients initially hide all but two backlog titles and page the index in groups of 50. the viewer already has a todos destination on both clients. [web shell](../../src/jarvis/static/home/index.html) · [android home](../../android/app/src/main/java/dev/niels/jarvis/Home.kt)

this decision supersedes the list disclosure, paging controls and record presentation in [0097](0097-todo-home.md), [0105](0105-native-android.md) and [0115](0115-web-home-address.md). the service still owns the order and owner-local dates. conversation owns edits and completion. [work contract](../work-records.md)

## what the owner sees

- **one todos tab.** put it in the main viewer and show when it is selected. it is reachable from a published home and on a narrow screen. remove the web sidebar’s todos button and record pane. a todo reference in a chat message still works. android uses its existing workspace controls.
- **one scrollable list.** show every active title once, initially collapsed on a fresh list visit. keep the existing groups and their order, with due work first. each summary shows a disclosure chevron, the full title, and the deadline or state information the group heading does not already convey. there is no backlog fold, “show more,” or list pager.
- **one fold per todo.** the entire summary toggles its row. a second tap folds it. opening one leaves the others as the owner set them. the summary is a keyboard-operable disclosure with an exposed expanded state. focus stays on the summary when toggled. a toggle sends no message, opens no composer, and creates no browser history or android navigation entry.
- **details under the title.** show the existing notes, scheduled jarvis check and dated linked results. distinguish a check time from a deadline. results keep their existing paging within that row. following a result opens its exact message. expose the todo’s exact link in the expanded row so the owner can still copy or share it. choose `discuss` to bring the todo into chat. web uses the tab’s composer and offers a choice if the draft references something else. android opens a new saved draft referencing this todo.

## addresses and return

| entry or action | result |
| --- | --- |
| open home or choose todos | home resolves the selected publication once, falling back to todos. choosing todos in the web viewer selects the list at `/`, including over a custom home. an incoming web `/overview` still selects todos and replaces its address with `/`. android retains its home and overview entry points. |
| open `/t/{id}` from a message, a requested presentation or a saved link | keep the exact address or native target. select the todos viewer, expand the addressed row and bring its title into view once. read the target directly even if home or the index is slow or unavailable. when the active index arrives, show an active target in its normal place exactly once. |
| open an exact link to a done or cancelled todo | show the addressed row above the active groups with its actual state and results. it remains available for this exact visit. ordinary list visits show active work only. a confirmed missing target shows “this todo is no longer available” at that address. a failed read offers retry. |
| fold the addressed row | keep the address and honor the fold through refresh. opening that link anew reveals it again. a fresh reader of a copied link always sees the target expanded. |
| follow a result, open chat or return to the viewer | restore the open ids, each open row’s result position, scroll anchor and focus for that visit. this includes web reload/back/forward, phone chat dismissal and android activity recreation. a newly opened tab gets its own state. an explicit link followed inside jarvis returns to its actual origin on back, even if that address occurs earlier in history. web retains 0115’s cold-link return to home when the owner uses the app’s return control. platform back keeps its normal cold-entry behavior. |

show the direct target or its error independently of the active list. if that target becomes inactive while open, move it to the addressed position and retain its state. in an ordinary list, remove a newly inactive or deleted row at the next successful refresh. if the removed row owned focus or anchored the viewport, use its nearest surviving neighbor, or the list heading if empty. refreshes and late reads respect later folds and navigation.

## read contract

both new clients request `GET /api/todos?all=true`. extend the existing authenticated handler and `WorkStore.web_list`. return the existing envelope with `offset = 0`, all active summaries, and `total = items.length`. read the complete snapshot in one transaction under the existing writer lock and one owner-local date for all sections. reuse the existing section and tie-break ordering. each item contains only `id`, `title`, `state`, `due_date` and `section`. the query returns the full list. stitching successive live pages together can miss or duplicate an item that moved between reads. [http handler](../../src/jarvis/home_http.py) · [ordered read](../../src/jarvis/work.py)

the owner selected a hard cut for this rollout. accept the literal `all=true` as the sole query parameter. other queries, including an empty query and the retired offset selector, receive 422. remove the old page query. an older service can ignore the selector. clients require zero offset and the advertised number of distinct rows before accepting a snapshot. a short or failed response keeps the last good list and check time, or shows a retry if this is the first read. only a successful empty snapshot earns “no active todos.”

load the existing exact-record and linked-result reads when a row opens. collapsed rows require only their summary. key open rows and result cursors by todo id, so refresh can reorder the list without moving state to another title. keep web’s visible-view refresh and android’s resume/manual refresh. a detail or results failure stays beside the affected row with retry. other rows, already loaded content and the draft remain usable. a late reply for a closed row cannot reopen it or move focus. [linked results](0105-native-android.md#c-linked-results-and-draft-evidence)

each refresh reads the complete summary snapshot. the response grows with
the active list, while closed rows need no content or results. this keeps
the server’s ordering atomic and gives the reader the whole list in one
request. linked results keep their page limit because each row can accrue
answers independently. disclosure and reading position belong to the visit
on that device. a copied link carries only the todo identity.

## acceptance

1. seed 53 active todos, including a due item, a future deadline, a blocked item and at least three backlog titles. on desktop web, narrow web and android, reach the final title by scrolling. compare the ordered ids with the service, check each occurs once, and observe zero record or result reads before expansion. check that the former default and offset queries fail with 422. exercise a short response and a successful empty list.
2. open two rows, read linked results in one and fold the other. move one between groups during refresh. preserve the reader’s open rows, cursor, focus and scroll anchor. on web, check the address and history depth across toggles. on android, one back leaves the destination. delay a detail read until after collapse and fail one results read while another row is open.
3. enter through a custom home and an old `/overview` link. open active, done, cancelled and missing exact links, including after sign-in. delay home and index reads. check the target appears once, remains readable, and honors a subsequent fold. copy its link into a fresh reader. navigate message a → todo b → linked result a → back and verify the return to b.
4. use `discuss` from an open row with a draft already referencing a different item. check web’s draft choice and native creation of a separate referenced draft. return to the same reading position. reload the web tab and recreate the android activity. verify both the saved reading state and draft ownership.

the [roadmap](../implementation-plan.md#private-web-home) owns delivery order and evidence.

## qualification

the macbook integration used the real fastapi service and postgresql 16.12
at schema `0025` with isolated records. the predecessor returned 50 of 53
summaries and accepted the retired request forms. the final service passed all
22 checks for snapshot completeness, ordering, validation and exact reads.
the empty snapshot and model-facing paging also passed.

the six predecessor browser checks failed at the former sidebar and detail
interaction. the final chromium and webkit checks passed 34 each across
desktop and narrow viewports. the wheel contains the same service and web
files. response faults, sign-in retry and timing were controlled at the browser
boundary.

the s22+ ran a separately identified candidate app against the same service.
the predecessor used the retired paged request. the candidate reached the last
of 53 titles in service order, fetched details on expansion, returned from
repeated message links and maintained independent drafts. the handset exposed
two reading-position defects that the final candidate corrected. first, a
late index moved a distant exact target offscreen. second, an inserted result
moved the reader within an open todo. a deep result viewport retained its
screen position across insertion and activity recreation, including when the
index was unavailable. handset sign-in and response faults used an isolated
fixture.

evidence is under `~/.local/state/jarvis/qualification/adr0117/`. the browser,
service and handset receipts record the tested artifacts, outcomes and
cleanup. the paired production cut and installed acceptance remain pending.

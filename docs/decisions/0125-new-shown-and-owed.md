# adr 0125. new, shown and owed in chat

**accepted design · november 26, 2026 · both cuts implemented in source.** the owner cannot tell which of jarvis' messages he has seen. web and android will mark what is new, open where he left off, and say in words what jarvis is waiting on. this amends chat presentation in [0087](0087-private-web-home.md), [0105](0105-native-android.md), [0118](0118-chat-reading-and-approvals.md) and [0122](0122-chat-sidebar-and-phone-alerts.md). the second cut adds one table. a working [specimen](https://claude.ai/artifact/8TUX4PyFsNugUXq9YfW4K7) shows the marks and movement; where it differs from this text, this text governs.

## what is wrong today

- nothing records what has been on the owner's screen. `read_position` is tool replay and unrelated.
- web chat opens pinned to the bottom. a message above the fold, or one that arrives while he is scrolled up or away, carries no sign. hidden tabs do not poll. [merge and refresh](../../src/jarvis/static/home/home.js)
- on narrow web the chat is `display: none` while messages merge. by reading, the panel then opens at the oldest loaded message. witness this on a device before fixing it.
- the android conversation opens at the top of the newest fifty and never scrolls to the latest. it reads only on resume or manual refresh, and paging replaces the page. [conversation](../../android/app/src/main/java/dev/niels/jarvis/Home.kt)
- a push posts a notification while he is looking at chat, and nothing ever cancels one. [push](../../android/app/src/main/java/dev/niels/jarvis/Push.kt)
- nothing separates "this is new" from "jarvis is waiting for your answer".

## words

| word | meaning |
| --- | --- |
| tracked | an assistant row visible in the [chat projection](../../src/jarvis/home_reads.py), excluding `native_progress`. only tracked messages are marked or counted. |
| shown | the whole message was on screen while the owner was attending. a claim about display. no client or document says "read". |
| new | tracked and not shown. |
| owed | jarvis is waiting on the owner because of this message. independent of shown. |
| attending | the owner is at this client. web: the document is visible, the window has focus, and there was pointer, key, wheel or touch input in the document within the last 120 seconds. android: the activity is resumed and its window has focus; the screen timeout bounds absence. |
| on screen | the conversation has layout and the message's line is inside the scrollport, which excludes the composer, keyboard and ledge. |
| visit | a stretch of attending. it ends after five minutes without attending. whether chat is open plays no part, so opening the narrow panel never starts a visit. |

"unseen" stays with [0097](0097-todo-home.md), where it means a proposal not yet presented.

## shown

a client records a tracked message as shown when the owner is attending and both of its ends have been on screen.

- **both ends.** the first line and the last line have each been on screen for one second, cumulative, while he was attending, within one visit. a message that fits satisfies both at once. a taller one needs time at its start and at its end. a fast scroll fails by construction.
- **direct evidence waives the wait.** activating a link or control inside the message, pressing reply on its proposal, or sending from the chat composer while the message is wholly on screen.
- **never evidence.** a notification delivered, expanded, dismissed or tapped. an opened url, including `/m/{id}`. a share-sheet send. page load, a poll, or reaching the bottom.
- **assistive reading.** android accessibility focus and web document focus resting inside the message for one second count, whatever the geometry. a web screen reader’s virtual reading cursor uses the ordinary on-screen rule because the document cannot observe that cursor.

timing state is keyed by message id and survives any rebuild of the message's article.

**clear** is the one explicit declaration: every new message up to the newest one on this client is dealt with. it is recorded as `cleared`, never as observed.

the gate is deliberately liberal. a mark may dry on something he did not read if it arrived within two minutes of his last input. the opposite error, a mark that stays wet beside text he is looking at, is the original complaint. obligation is carried separately, so a wrongly dried mark cannot hide a question. a lost report leaves the message new.

## what the owner sees

**mark.** each new message hangs a small lozenge in the gutter beside its stamp row. it is a 0.45rem square rotated 45°, with a 1.5px border and fill in `--ink`. it sits outside the article box, centred 0.825rem before the content edge and 0.42rem below the article's top, with no flow height. it is sticky at 1rem inside its article, so it rides beside a message taller than the screen. a selected article offsets it past the selection bar. it is the closed form of the todo chevron and shares no shape with the selection or proposal bars.

**drying.** when the message is shown the fill becomes transparent and the border `--muted`, over 700ms with `cubic-bezier(0.22, 0.61, 0.36, 1)`. the other motion is specified in [adr 0126](0126-presence.md#what-the-owner-sees). reduced motion makes it instant. the hollow mark stays until the visit ends and is absent on the next. if it proves unused after a month, delete that one rule.

**standing.** a mark appears only once a message has been new for 1.5 seconds. a reply shown as it lands gets its receipt and never a mark. only messages that carried a mark leave a hollow one.

**boundary.** one per visit, placed before the first new message found when the visit began. a 1px rule runs from the rail's edge through the gutter to a caption in the time column: `new since {time of the preceding message}`, then a quiet `clear`. rule and caption are `--ink` while anything is new, then `--muted` and `--line`. it never moves during a visit and carries no count.

**ledge.** a strip attached to the foot of the transcript, above the composer and any google approval. it exists only while it has something to say.

| side | text | action |
| --- | --- | --- |
| start | lozenge and `3 new below`, `3 new above`, or `5 new, above and below` | go to the nearest new message off screen, below first, placed with the inset. |
| end | `1 needs a reply` or `2 need a reply`, in `--rubric` | go to the next owed message off screen, cycling. one outside the loaded pages opens as `/m/{id}`, an explicit return. |
| start, after clear | `40 cleared` and `undo`, for five seconds | undo restores every mark. nothing has been sent yet. |

the counts come from the marks on loaded messages. new messages older than every loaded page are added to "above" as `max(0, new_total − loaded new)`.

**owed.** the stamp row reads `jarvis` then `needs a reply` in `--rubric`, 0.78rem, regular weight. it is independent of the mark and outlives it. it clears when the wait settles, never because he looked.

**one red.** add `--rubric: light-dark(#a33b25, #ee9a83)`. it means owed and nothing else: no errors, no links, no decoration. new-ness is ink. the existing sage accent keeps links, focus, selection and proposals.

**elsewhere.** the narrow chat button reads `chat`, a lozenge and `new_total`, with accessible name `open chat, 3 new`. the favicon is a lozenge in three files served from `static/home/`: hollow at rest, filled when anything is new, `--rubric` when anything is owed. there is no title count, pill, badge api or sound.

**assistive.** state is shape and words, never colour alone. a new article is prefixed with a visually hidden `new`. the boundary is a named separator. arrivals produce at most one polite announcement per ten seconds, such as `3 new from jarvis, one needs a reply`. arrival and drying never move focus.

## what moves

the viewport moves by itself only on opening or from the pinned state. it never leaves a position the owner placed. an explicit return beats the boundary: [0122](0122-chat-sidebar-and-phone-alerts.md)'s warm back, `/m/{id}`, a revision return and reload restoration.

- **visit start.** on first load, or when he is attending again after at least five minutes. re-read every loaded page, compute the boundary and drop hollow marks. re-place the viewport only on first load or if it was pinned when he stopped attending.
- **opening.** `scrollTop = min(bottom, top(boundary) − inset)`, where the inset is about 4.5 line-heights of the preceding message. with nothing new, open at the bottom. on narrow web, defer placement until the chat has layout.
- **loading.** page back contiguously from the latest until the first new message is loaded, to at most three pages. beyond that, open at the oldest loaded message; the ledge reports the remainder as above. pages never leave a gap.
- **arrival, pinned and attending.** follow to `min(bottom, top(first new message on screen or arriving) − inset)`. never scroll upward and never past the top of a new message.
- **arrival, pinned and not attending.** hold at the first tracked arrival. later ones stack below it and the ledge counts them.
- **arrival, placed.** nothing moves. the ledge counts it.
- **sending.** a send from the chat composer scrolls to the bottom.

android follows the same rules. its list keeps a state object, anchors by message id and offset as [the todo viewer](../../android/app/src/main/java/dev/niels/jarvis/TodoViewer.kt) does, prepends earlier pages and reads every three seconds while resumed.

## owed

every `GET /api/messages` response gains, beside its items, `owed`: the ids of every owed message in the conversation, newest first, and `owed_total`, their number. clients label loaded messages from that list, so a label never goes stale on an older page. a message is owed when one of these holds:

- **approval.** it is a `native_final`, as in `proposal_presented`, whose `home.proposal_ids` holds an `awaiting_approval` action whose origin request is not parked and is not waiting on `configuration`. the label stays on the message that carries the card however often jarvis wakes for other reasons. a failure notice that repeats the proposal is not owed, because a parked request cannot take a decision.
- **owner input.** it is a `native_final` whose `trace.native_attempt_id` equals that of a request row in the conversation with `request_state = 'waiting'` and `wait_reason = 'owner_input'`. the [terminal contract](../../src/jarvis/terminal.py) rejects an owner-input wait without a visible question, so the latest attempt to leave that wait always has such a final. [settlement](../../src/jarvis/native_journal.py)

and, in either case, no owner message dated after it is still `pending`. once he has replied the label goes at once; when jarvis has processed the reply it either settles the wait or asks again in a newer final, which then carries the label.

the rule reads existing columns through `ix_message_unresolved_request` and needs no schema. it draws jarvis' recorded wait, not every question mark. a question asked in a reply that jarvis then completed is not owed. `configuration` and `external_reconciliation` waits are not owed. an owner-input request requeued for retry is not owed until the retry asks again, which a new final and a new alert then carry. an approval that was never presented has no message to label. shown state never creates, settles or reads a wait, an action or an approval.

## notifications

titles, channels and the fcm payload are unchanged. no message text travels through fcm. [0122](0122-chat-sidebar-and-phone-alerts.md)'s delivery rule stands: the service sends every notice.

- **foreground.** while the conversation is resumed and on screen, android withholds the post. it first persists the held notice. it posts it when the conversation leaves the screen, or at next start, unless the message has been shown by then.
- **replies.** one group with a summary `jarvis · n new`, counting the phone's own active reply notifications. a burst alerts once.
- **questions.** posted individually on their existing channel and never folded into the group.
- **sweep.** on resume and after each successful message read, look only at the messages in the returned page. cancel a reply notification when its message is not new. cancel a question notification when its message is neither new nor owed, so a question that was never shown keeps its alert even if jarvis recorded no wait. the tag is `uuid5(message_id, "jarvis-home-notice:reply")` for both kinds. never touch scheduled-check notifications or a message outside the page.
- **first cut.** "not new" means this phone itself recorded the message as shown. the phone knows nothing of the laptop until the second cut.

## service contract

read state and owed state travel beside the messages, never inside one, so a mark can dry and a label can clear without the article under his eye being rebuilt. the message item and `GET /api/messages/{id}` are unchanged.

```sql
CREATE TABLE owner_shown (
  message_id uuid PRIMARY KEY REFERENCES message(id),
  shown_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  via text NOT NULL CHECK (via IN ('observed', 'cleared', 'cutover'))
);
GRANT SELECT, INSERT ON owner_shown TO jarvis_runtime;
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='jarvis_backup') THEN
    GRANT SELECT ON owner_shown TO jarvis_backup;
  END IF;
END $$;
```

receipts are never updated or deleted. the runtime has no grant to do either. merging devices is set union. "mark unread" is therefore inexpressible, by design.

| route | contract |
| --- | --- |
| `GET /api/messages[?before=…]` | from the first cut the envelope gains `owed` and `owed_total`. from the second it also gains `new`, the ids among this page's items that are new, and `new_total`. |
| `POST /api/shown` | `{ids}` with 1–200 canonical uuids. 204. inserts `observed` for ids that are tracked rows in this conversation and have no receipt. other ids are ignored. idempotent. one statement, no conversation lock. |
| `POST /api/shown/clear` | `{through}`, the id of the newest tracked message the client has rendered. 204. inserts `cleared` for every new message at or before it in chat order. a message that arrived afterwards stays new. 422 when `through` is not a tracked message of this conversation. |
| `GET /api/shown` | `{new_total, owed_total}`. a hidden web tab calls it every 60 seconds for the favicon. beyond that a hidden tab only flushes reports it already holds. |

- **one read.** the service's single serialized connection makes a page, its sets and its totals one consistent read. [ownership](../../src/jarvis/ownership.py)
- **stale pages.** the newest page is read every three seconds. older loaded pages are re-read at visit start, on return to visibility or resume, and whenever `new_total` is smaller than the number of loaded marks.
- **clear and undo.** the client holds the request for five seconds and shows the marks hollow. undo cancels it. if the page hides or the app pauses inside the window, it is sent at once. if it fails, the marks return and the existing connection notice applies.
- **reports.** a client batches reports for one second and flushes with a keepalive request when the page hides or the app pauses. a failed report retries while the client lives. before `PUT /api/messages/{id}` a client awaits its pending report. the submission body is unchanged.
- **android sign-in.** unlike other writes today, a 401 from these routes refreshes the bearer and retries once in [the api client](../../android/app/src/main/java/dev/niels/jarvis/HomeApi.kt). a second failure is dropped. a background report never raises sign-in.
- **stale clients.** the three `/api/shown` routes join the message reads under the viewer contract header. the second cut sets one new exact value in service, shell and app together, as [0120](0120-drive-files.md) did. stale clients receive 426.
- **migration.** it requires schema `0027` installed, since the cut tooling verifies the drive map only at that exact revision. it takes both writer locks and inserts a `cutover` receipt for every existing assistant row. add the `Table` and move `APPLICATION_SCHEMA_REVISION` in `db.py`; add the table to `STOPPED_TABLE_KEYS` and move `SCHEMA_REVISION` in [`memory_snapshot.py`](../../deploy/memory_snapshot.py); extend the cut verifier in `deploy/prepare-cutover`.
- **clean slate.** at the second cut every earlier message counts as not new and both local stores are deleted. marks restart from the cut. owed labels are unaffected. the owner reads what is new before the cut; the rollout says so.
- message rows are not touched, so memory capture and the archive see nothing.

## the first cut keeps the set on the device

the first cut ships every behavior above with no schema. the service adds only `owed` and `owed_total`, which older clients ignore. each client owns one small module holding the shown set behind three operations: is this new, record these, clear. on web the store is `localStorage`; on android, private preferences. both hold a start time and at most 2,000 ids. a message is new when it is tracked, dated after the start time and absent from the set. when the set is full, drop the oldest ids and advance the start time to the newest dropped message's time. clear advances the start time to the time of its `through` message, which also covers new messages that were never loaded. phone and laptop therefore disagree until the second cut, which replaces the inside of that module with the service contract. for exact local totals, clients count tracked rows back through the device’s start time using the existing page cursor. the three-page opening limit applies to the transcript; older pages scanned for counts do not extend it. the limitation is stated to the owner at rollout.

the device-local cut rehearses the shown rule before receipts become permanent. on november 26 the owner waived the week of use. proceed after the installed first-cut smoke and verified drive custody at `0027`, with the controlled second-cut checks below. the owner accepts proceeding without tuning the rule through a week of use. the local sets are discarded at the shared cut.

## invariants

safety:

1. an `observed` receipt exists only if a client met every condition of shown.
2. a receipt is never updated or deleted.
3. no approval, action, wait, request-state or notice-delivery path reads a receipt.
4. a message is in `owed` only while its approval or owner-input wait is recorded.
5. the viewport never leaves a placed position without an owner act.
6. a notification is cancelled only for a message in a page the service returned, and only when that message is not new (reply) or neither new nor owed (question). in the first cut "not new" is this phone's own record.
7. no client shows a mark for a message whose state it has not been told, and none shows "read" or a shown time.
8. every notice that reaches the phone is posted, dropped by the phone's own notification settings, or matched by a receipt.

liveness:

1. a client reports a display within two seconds of the gate being met. a lost report leaves the message new.
2. every other client reflects a receipt after its next read of that message's page.
3. an owed label clears on every loaded message after the next read following its wait's settlement or the owner's reply.

## implement and qualify

| owner | exclusive boundary | proves |
| --- | --- | --- |
| a · projection and service | `home_reads.py`, `home_http.py`, the table in `db.py`, the migration, `deploy/memory_snapshot.py`, `deploy/prepare-cutover` | `owed` across approval, owner-input, re-waited, answered, settled and never-waiting cases. page `new` sets, totals, clear through a message, 426 for a stale contract, restore with receipts. |
| b · web | `static/home/`: one new module for the set, timing and marks; the existing merge, message read and refresh paths; styles; three favicon files | marks, boundary, ledge and movement at desktop and 320–390px, in both colour schemes, with enlarged text and a screen reader. |
| c · android | `Home.kt` conversation list, one new file for the set and timing, `Push.kt`, `HomeApi.kt` | the same journeys on the signed s22+ candidate with talkback, plus foreground hold, grouping and sweep. |

freeze the `owed` rule and the `/api/shown` shapes before client work. serialize shared web and android paths against the actual merges of 0118, 0122, 0123 and 0124. every child of the transcript carries an order key and a stable id, and marks and labels are re-applied after any article is rebuilt.

use dev-server's `scripts/rehearse-worktree` on macbook, real browsers and the signed handset against an isolated service and database. for each journey author a temporary check, witness the old failure, implement, prove it and delete the probe. save named evidence outside scratch and verify its hash.

1. away with three new messages, one taller than the screen and one owed. the conversation opens at the boundary with context above. the tall message dries only after its end has been on screen. the owed words remain.
2. forty new across three days, two owed. the transcript is contiguous, the ledge counts are exact, each owed message is reachable from the ledge, and clear with undo works. a question that arrives inside the undo window stays new.
3. more than 150 new. the view opens at the oldest loaded message, the remainder is reported above, and earlier pages still load.
4. a quick exchange of six replies. no mark appears and nothing blinks.
5. the window unfocused while five messages and two progress rows arrive. the view holds at the first arrival, progress rows carry no mark and no count, and returning dries only what is on screen.
6. tap the newest of fourteen notifications. that message is selected, the thirteen older stay new, and the mark clears the selection bar.
7. a proposal changes status while its message is half read. timing continues and the mark survives the rebuild.
8. read a report to its middle, open a file, return within five minutes. the position is kept. return after ten minutes having left unpinned: still kept. on narrow web, read a file for six minutes with chat closed, then open chat: no new visit begins.
9. android in chat when a push arrives: no notification. leave before one second: it posts. a burst of eight replies and one question: one group, one alert, the question separate.
10. owed. a proposal awaits approval; an unrelated mail event wakes jarvis, once with a plain reply and once silently. the label stays on the proposal's message and its alert stays. the owner replies: the label goes at once. jarvis asks again: the newer final carries it. a parked request's failure notice repeats the proposal and is not labelled. a request requeued for retry loses its label until the retry asks again.
11. a question notice for a message jarvis recorded no wait for. its alert stays until the message has been shown.
12. second cut only. read on the laptop, then open the phone: marks agree and stale reply notifications go while an owed question stays. with three pages loaded on the phone, clear on the laptop: the phone's older pages lose their marks. a push landing during a read is not cancelled. an old client receives 426. a database restore carries the receipts.

the [implementation plan](../implementation-plan.md#new-shown-and-owed-in-chat) owns sequence and rollout.

## first-cut qualification

source composes the landed 0123 and 0124 readers at `79a1108`. the first cut
stays on `0027` and uses the matched `cited-sources-v1` viewer header. the
owed query runs on the existing serialized connection for each message page.
this spends a scoped read on each poll and keeps waits, actions and display
receipts independent.

web starts its local window on first load. android starts it at first-cut
package installation, so a push can wake the app without making the new
message historical. older alerts need positive local evidence before a sweep.
android’s full-screen composer returns to the bottom after acceptance.
document focus is observable on web. a screen reader’s virtual cursor uses
ordinary on-screen evidence there.

notification group titles use android’s active reply records. the app protects
just-issued children from an empty snapshot and reconciles after a burst. an
unusually slow or rejected post can leave a summary until the next read or
explicit dismissal. an explicit saved chat position can require reading past
the three opening pages. if an older read fails, the phone displays the available
history with its existing connection notice.

the macbook candidate is `3e4937d8d91685eb14bc0c4487d4c7be817014e9`.
detached rehearsals witnessed the predecessor failures and checked the repair.
real http and migrated postgres passed seven projection checks, including a
canonical owner submission. chrome and webkit passed 24 browser assertions
and two further empty-history checks. chrome also exercised the matched
service through projection, settlement and browser submission. 24 android
emulator checks passed, including native virtual accessibility focus, an
8-reply group and separate question, and restoration at the original pixel
position after process death. the temporary phone app used controlled notice
data. the exact release build passed `scripts/verify` and produced the wheel,
source archive and signed version 8 apk. the apk certificate matches the
predecessor’s trusted release certificate.

named receipts and artifact hashes are under
`~/.local/state/jarvis/qualification/adr0125-implementation/`.
the [installed follow-up](../issues/new-shown-owed-installed.md) owns the
first-cut rollout, the owner’s dedicated-check waiver, the real firebase tap
and the owner trial. the stopped shared-receipt cut follows the installed smoke and drive custody.

## not in this decision

- **mark unread.** it is an intention, not an observation. receipts cannot express it, and todos or a sentence to jarvis own intentions.
- **a single read-up-to-here position.** chat order is not commit order, as [the reply-order issue](../issues/web-control-reply-order.md) showed, and a tapped notification reads out of order. one position must lie about one or the other. clear is the one place a position is used, as an explicit owner declaration.
- **telling jarvis what was shown.** [held](../issues/crossed-questions.md).
- **retracting or skipping pushes once shown.** [held](../issues/stale-phone-alerts.md).
- **shown times, per-device state, observation logs, summaries of the unread span, triage states and snooze.**

# adr 0127. set the conversation as a daybook

**accepted design · 26 november 2026.** the conversation is
the surface the owner uses most. it has no typography, no receipt for a send,
and on android no composer beside the text it answers. web and android will
set it as one dated page in two hands. the owner approved this design, its
[study](../research/daybook-study.html) and the rulings recorded here on 26
november 2026. where the study differs, this text governs.

this amends:

- [0087](0087-private-web-home.md): the private host keeps its cache policy
  with one exception for successful content-addressed chat font responses;
- the composer sentence in [spec](../../SPEC.md): enter sends only where the
  primary pointer is fine. the sentence changes in the same merge as the code;
- [0105](0105-native-android.md): the colour scheme, the conversation and the
  composer. in its share contract, "a second share gets a new draft", "save
  and return" and "return to the source app on receipt" end: a share appends
  to the one draft and opens the conversation. shared text stays a removable
  original, so a shared `pause` stays inert. the send states are in flight
  and held. a 409 leaves the draft editable under a fresh send id;
- [0116](0116-chat-composer-attachments.md): the composer's look and drop
  target. `discard` ends "clear only the draft that owns a confirmed receipt".
  the empty-draft tab and digest-less uncertain drafts are no longer handled.
  the submission contract stands;
- [0118](0118-chat-reading-and-approvals.md): "use existing typography and
  compact headings". the column keeps its width and both speakers keep markdown;
- [0122](0122-chat-sidebar-and-phone-alerts.md): the reading gutter is 1.5rem;
- [0125](0125-new-shown-and-owed.md): the lozenge's block position, the
  selected offset, the owed label's type, the proposal's sage bar, and
  android's full-screen composer. the boundary caption stays in the time
  column, which is now the inline end of every stamp;
- [0126](0126-presence.md): its never-animated list gains one exception, the
  page advance at a receipt, and the tail's `jarvis` is visually hidden. the
  tick, beats, tail and handoff stand. the provisional italic and final roman
  rule describes jarvis's hand.

## what is wrong today

- **no reading face.** the stylesheet leads with `Inter`, which was never
  bundled, so text is system sans. [styles](../../src/jarvis/static/home/home.css)
- **labels where letterforms would do.** every message carries `you` or
  `jarvis` and a full date. between two speakers both say nothing.
  [renderMessage](../../src/jarvis/static/home/home.js)
- **link piles.** files, references, drafts and artifacts hang under a message
  as a column of `open …` links in default styles.
- **the composer is a form.** a two-row box with a resize handle. the send
  button reads `retry send` during an ordinary first send.
- **effect precedes cause.** after a 201 the composer empties and the tail says
  `received` above no message. the owner's row waits two more round trips.
- **three ways to lose work.** the PUT carries no abort, so a hung socket
  freezes the composer for good. a file dropped outside `#composer` replaces
  the page. a retry that is permanently refused (422) can never be cleared.
- **phone browsers cannot type a newline.** enter sends.
- **android hides jarvis while you answer him.** writing swaps the whole screen
  for `DraftComposer`. [home](../../android/app/src/main/java/dev/niels/jarvis/Home.kt)
- **android's scheme was never finished.** dividers are material's
  purple-grey, dialogs lavender, errors a second red. `open exact message` and
  a divider follow every message.

## goals and non-goals

goals: a page that disappears in use; a send whose fate is always visible and
always actionable; one composer beside the record on both clients; less code
and fewer controls than today.

not in this decision:

- viewer typography. todos, files, the shelf and the mail editor keep their
  faces on both clients. owner ruling: chat only.
- transport. no streaming, long-poll or faster tick. 0126's 3 s tick stands.
- table column alignment, citation superiors, syntax highlighting, a sticky
  day head, a jump-to-latest control, type-to-focus, android ripple restyling,
  the spinners of android's other panes.
- the study's rejected ideas: an occasion line, a lemma at heading rank, a
  sans hand for the owner, a bundled mono.
- any new stored field, table or migration.

## words

| word | meaning |
| --- | --- |
| hand | the letterform that says who speaks. jarvis is roman, the owner italic. |
| stamp | the one small line that opens every message: hidden speaker, optional owed words, time. |
| stroke | the owner's marginal mark, a short rule beside the first line. |
| head | a day's heading in the transcript. |
| apparatus | the kind-and-entry rows under a message's text. |
| slip | a staged reference or file in the composer. |
| receipt | the service's answer that it holds a message: its id and its stored row. |
| crossing | the moment a message leaves the composer and enters the record. it happens at a receipt and at no other time. |
| held | a send whose fate is unknown. it stays in the composer. |
| murmur | interface text in muted Cormorant italic. |

## rules

1. **one writer.** the transcript shows only rows the service projected, from
   a read or from a receipt. no client composes a row.
2. **one place.** the owner's words are in the composer until a receipt and in
   the record after it. never both, and never neither except by `discard`.
3. **a motion is a receipt.** every animation is caused by one confirmed fact.
   nothing loops. text, layout properties and the owner's scroll never animate.
4. **heights are final at insertion.** the stamp has one height on every
   message. faces load before the first placement. only a change the service
   reports may alter a placed row, under 0125's anchor.
5. **the tail's top margin equals the margin its reply will take.** 0126's
   handoff and 0125's movement rules hold unchanged.
6. **one red.** `--rubric` means owed. problems are ink and words.
7. **shape and words.** every message names its speaker to assistive
   technology and to the clipboard. no state is colour alone.
8. **the measure stays.** the rail is 23rem. nothing here widens it.
9. **one composer per client, one draft per device.** web keeps one draft per
   tab, as today.
10. **no legacy.** everything listed under delete leaves in the same change.
    no flag, fallback or compatibility path remains.

## what the owner sees

### the page

tokens are scoped to `#sidebar`. palette values do not change.

| token | value |
| --- | --- |
| `--text` | `Literata, Charter, Georgia, serif`. weight 400, 380 in the dark scheme, 600 for strong. `font-optical-sizing: auto; font-synthesis: none` |
| `--display` | `"Cormorant Garamond", Georgia, serif`, display and murmurs only |
| `--mono` | `ui-monospace, "SF Mono", Menlo, Consolas, monospace` |
| `--gutter`, end padding | 1.5rem, 1rem |
| `--u` | .75rem, the vertical unit |

| element | face | size / leading | colour | setting |
| --- | --- | --- | --- | --- |
| jarvis text | Literata roman | 1rem / 1.5rem | ink | `text-wrap: pretty; hyphens: auto; hyphenate-limit-chars: 10 4 4`, old-style proportional figures |
| owner text | Literata italic | 1rem / 1.5rem | ink | `text-wrap: wrap; hyphens: manual; white-space: pre-wrap`. `em` is roman. code stays upright |
| progress note (`native_progress`) | Literata roman | .875rem / 1.3125rem | muted | |
| stamp | Literata | .75rem / 1rem, .2rem below | muted | time in old-style tabular figures, tracked .04em |
| owed words | Literata small caps | .75rem | rubric | `needs a reply`, tracked .06em |
| head | Cormorant roman | 1.3125rem / 1.5rem | ink | |
| murmur | Cormorant italic | 1.06rem; 1.14rem for the tail and placeholder | muted | boundary, ledge, captions, receipts |
| apparatus | Literata | .875rem / 1.3125rem | kind muted small caps, entry ink | |
| code | mono | .86em inline, .875rem in blocks | ink | never hyphenated |
| tables | Literata | .875rem / 1.3125rem | ink | lining tabular figures |

small capitals are real (`font-variant-caps: all-small-caps`), never synthesized
and never tracked lowercase.

**spacing.** an article sits 2u below the one before it. an owner message sits
2.5u below. a jarvis message directly after an owner message sits .5u below,
so an exchange reads as a unit. a head has 4u above it and .5u below. the tail
takes the margin its reply will: .5u when the last transcript child is an
owner message, else 2u, by one css rule
(`#messages:has(> article[data-role="owner"]:last-child) + #presence-tail`).

**stamp.** `div.stamp` holds, in order: a visually hidden `strong` (`you` or
`jarvis`), 0125's `needs a reply` when owed, then `time` at the inline end.
the time reads `HH:MM`, 24-hour, in the device zone, from the formatter
`presence.js` already has. it carries a full ISO `datetime` and a full local
date as its `title`. the stamp is built once and never rebuilt. the tail uses
the same stamp, with 0126's elapsed time in the time slot.

**stroke.** a .6rem by 1.5px `--muted` rule, 1.125rem before the content edge,
on the x-height of the owner's first text line. the composer carries the same
stroke beside its first line.

**heads.** one before the first loaded message of each local day:
`thursday 26 november`, lowercase, with the year appended when it is not the
current one, built from date parts and not a locale's punctuation.

- a head is derived, never stored. it is a transcript child with id
  `day-YYYY-MM-DD`. after every merge one pass makes each head the immediate
  previous sibling of its day's first article and removes a head with none,
  inside the same anchor-preserving step. it is never sticky.
- when the boundary belongs before a day's first article it sits before the
  head: boundary, head, message.
- code that wants "the preceding message" walks back to the previous `article`
  past any head or boundary. today that is `insetPosition` in `home.js` and
  `openBoundary` in `chat-attention.js`, which reads the previous sibling's time.
- android builds heads as list items keyed `day-YYYY-MM-DD` in the key list
  that already carries `earlier`, `boundary` and `tail`. anchors stay message ids.

**0125's marks.** the lozenge keeps its inline position and its sticky rule.
its block position moves to the first text line, level with the stroke; owner
messages never carry one. the boundary caption and the ledge are murmurs, with
0125's words. the ledge's owed count stays rubric small caps.

**selected.** a 2px `--accent` rule at the rail's inner edge, the full height
of the article. no padding, no text shift, no reflow.

**controls.** every control in the rail is a lowercase word with no box:
`earlier messages`, `back`, `clear`, `reply`, `attach`, `send`, `retry`,
`discard`, `stop waiting`, `×`. hover is `--ink`; focus is 0122's accent ring.
where the pointer is coarse each has a 44px target, 48dp on android.

### the reader

markdown-it and the hand-built dom stay as 0118 and 0124 left them. styles only.

- blocks sit 1u apart with no indent. a list item's inner paragraph has no
  margin, which makes tight lists tight. lists indent 1.25em; markers are muted.
- headings do not look like headings: every level is 1rem. h1 to h3 are small
  caps; h4 to h6 are weight 600.
- links are ink with a 1px accent underline.
- a blockquote has a 1px muted rule and stays roman at full size.
- code has no fill or pill. a block has a hairline above and below and bleeds
  to the rail's end edge, so a clipped glyph is the scroll cue.
- tables are booktabs: ink rules at head and foot, a `--line` rule under the
  header, header cells in muted small caps at regular weight.
- `hr` is a 3rem hairline, flush left.
- only `pre` and tables scroll sideways.

### the apparatus

one function maps a message to rows. the order is fixed. a kind is printed
once for consecutive rows. there are no verbs.

| message field | kind | entry | note |
| --- | --- | --- | --- |
| `ref` | `about` | its label; a link when it has a route | |
| `files[]` | `file` | name, or `unnamed file` | the existing origin status, or `file unavailable` |
| `drafts[]`, editable | `draft` | subject or `(no subject)`, numbered when subjects repeat | |
| `drafts[]` not editable, and `draft_revision_id` | `revision` | subject, or `draft revision` | `failed integrity checks` when the error is `integrity` |
| `artifact_links[]` and `present.ref`, when not already linked | `artifact` for a view, `file` for a file or drive file, `todo` for a todo | its label | page number when present |

an entry is ink with a hairline underline that turns accent on hover. a link's
accessible name is kind, entry and note.

**proposal.** a block under the apparatus, indented 1.1rem for life.

- title: roman 1rem, regular weight. detail: .875rem.
- its own rows: `revision`, and once the owner has decided, `you` with
  `approved` or `denied` linking to his reply.
- last line: `reply` at the start, in the owner's italic with an accent
  underline; the status at the end in muted small caps.
- a rubric `¶` stands in the indent only while the proposal is owed: its
  message is in `owed` and its status is `awaiting_approval`. the indent is
  reserved, so the mark leaving shifts no text. the sage bar is deleted.

### the foot

the composer is the unruled foot of the same page: no box, radius or shadow.
its top edge is a 1px `--line` rule that turns `--ink` and gains 1px while the
field has focus, over 120 ms. dom order is visual order: slips, field, problem
line, foot.

- **field.** the owner's italic at the transcript's measure and left edge, so
  plain prose keeps its line breaks when it crosses. one line at rest. it
  grows with its content to `min(12lh, 38dvh)`, then scrolls. growth is never
  tweened. while the transcript is pinned, a change in the composer's height
  keeps the bottom.
- **placeholder.** `to jarvis`, a murmur.
- **foot.** `attach` at the start, the caption in the middle, `send` at the end.
  `send` is always present: muted and inert with nothing to send or while
  files are being read, ink when armed. fine pointers show `↵` beside it.
- **slips.** a reference reads `about · {label}` with `×`. a file is a 2.75rem
  row: a reserved 2.5rem cell (thumbnail, or the extension), the name, the
  size, `×` named `remove {name}`. the reserved cell ends the shift when a
  thumbnail arrives. 0116's change-of-reference question stays, set as words
  in the slip's place.
- **drop.** the whole rail is the target, tinted 8% accent with the caption
  `drop to attach`. a file dropped anywhere else in the document is ignored and
  never navigates.

| state | when | look | words |
| --- | --- | --- | --- |
| resting | empty draft | placeholder, `send` muted | `to jarvis` |
| armed | text or files, nothing being read or missing | `send` ink | |
| in flight | from the press until an answer | text at 58% ink, read-only, no caret. `attach` and `send` hidden. focus moves to the field and stays | nothing for 400 ms, then `sending…`. the timer starts at the press. files are hashed when staged, before the send can arm. from 10 s, the word `stop waiting` |
| held | any answer that is not a receipt, a refusal or a conflict: a network failure, 5xx, a sign-in redirect, `stop waiting` | text at full ink, read-only, a still muted ring. `retry` and `discard` | `checking whether your message arrived…`, then `no receipt yet. retry is safe: it cannot arrive twice.` |
| refused | 400, 413, 422 or 426 on a first attempt | editable again | 0116's three strings; for 426 the existing upgrade notice |
| conflict | 409 | editable again, with a new id | `a different message already used this send. it is in the conversation.` |
| discarding | `discard` pressed | the foot becomes the question; focus on `keep`; escape keeps | `discard these words? a send that did arrive stays in the conversation.` `keep` `discard` |

- `stop waiting` aborts the request and enters held without raising the
  offline notice. a sign-in redirect or 5xx raises 0122's notice as today.
- a refused retry stays held, as today; `discard` is its way out.
- a reload or a killed app during flight returns held and checks its receipt.
- a draft that needs an original file again keeps 0116's `reselect`.
- `discuss` while in flight or held says `settle the earlier message first.`

**keys.** where the primary pointer is fine, enter sends and shift-enter breaks
the line. where it is coarse (`(hover: none) and (pointer: coarse)`), enter
breaks the line. ctrl-enter and cmd-enter send everywhere. input-method
composition is untouched. escape answers one layer per press: a drag, the
discard or reference question, then the narrow panel. it never clears text.

**google approvals.** `#workspace-approval` sits in the rail unstyled today. it
takes the same vocabulary: the prompt in roman .875rem, its expiry as a
murmur, its choices as words.

### crossing

1. press. the field enters in flight. 0125's send rules run as landed: the
   transcript is pinned to the bottom and `attention.sent()` records evidence.
2. the receipt arrives. in one task, keeping today's bookkeeping (the receipt
   failure cleared, `armed.request` set, `present()` called): the draft resets
   and the field is editable; the receipt's row enters the transcript through
   the same merge a page read uses; the tail shows `received`. if the
   transcript is still pinned it scrolls to the bottom. if the owner has
   placed it since the press, nothing moves.
3. **the page advance.** only when step 2 scrolled: the transcript and the
   tail play one transform from the distance the content rose to none,
   `min(420, 140 + .5·|dy|)` ms on `cubic-bezier(.2,0,0,1)`. measure `dy` on
   the last article that existed before the receipt. it does not play when
   the document is hidden or motion is reduced. code that changes layout or
   scroll finishes it first. 0125's 100 ms sampler records nothing while it runs.
4. the existing `refresh()` runs. the receipt's row equals the page read of
   that instant, so for a text-only send the poll changes nothing. a file's
   status may still change as it is filed.

a held message that is later found by its receipt crosses by the same steps.
arrival is not touched: a reply still takes the tail's place by 0126's
handoff and nothing above it moves.

### android

the same page, built natively. differences are deliberate.

- **faces.** Literata from `res/font` as two variable files. one `Font` per
  weight with explicit `FontVariation` settings, since compose does not derive
  optical size. the faces and their text styles are local to the conversation
  and the dock; the material type scale and every other pane are untouched.
  body 17sp, line height 1.5em, so font scale cannot collapse the leading. the
  two places that convert a line height to pixels use font size times 1.5.
  jarvis text uses `LineBreak.Paragraph` and `Hyphens.Auto`; owner text
  `LineBreak.Simple` and `Hyphens.None`.
- **scheme.** the colour scheme is app-wide and finished once: `outlineVariant`
  is `--line`, the surface containers are the surface, `error` is ink. rubric
  and line are defined in one place.
- **conversation.** one stamp composable serves messages and the tail. the
  stroke and lozenge are drawn in the gutter. spacing is per-item top padding
  chosen from the previous item's role. apparatus rows and the proposal block
  follow the tables above, with 48dp rows. its first-load state is still
  words, not a spinner.
- **the dock.** the composer is a sibling below the list, never an overlay: a
  `BasicTextField` of one to six lines, the same words and states as web,
  `attach` through the system document picker. enter breaks the line. the
  activity draws edge to edge; when the keyboard shrinks a pinned list it
  holds the bottom, and a placed list does not move.
- **one draft.** the store holds one draft, in `noBackupFilesDir/draft`.
  one atomic manifest owns the send id, words, reference and staged files.
  share appends and text edits preserve each other under the store's lock.
  nothing reads the old `drafts` directory, which the owner reports empty.
  `reply` and `discuss` set the draft's reference and focus the dock; a
  different reference over existing text asks 0116's question, as web does.
- **share.** the share and process-text intents append to the draft and start
  `MainActivity` with one boolean extra, `chat`, which opens the conversation
  with the dock focused. files become slips. shared text or a url stays one
  removable text original, as 0105 has it. while a send is in flight or held
  the share copies nothing and says `settle the earlier message first.` the
  existing limits apply to the sum.
- **crossing.** `ChatHistory` gains one sorted insert for a receipt's row,
  beside its page reads. the list goes to the bottom if still pinned and the
  field clears in the same frame. there is no page advance.
- **haptics.** through `LocalHapticFeedback`, so a probe can record them:
  `Confirm` once at a receipt, and one `TextHandleMove` tick when an awaited
  reply hands off while the conversation is resumed. nothing at the press, on
  a beat, on unawaited arrivals, or on failure.

### delete

web: the `Inter` declaration; visible names and per-message dates; the
controls pile and its `open …` and `discussed ·` verbs; bordered buttons and
the filled `send` in the rail; the resize handle and second row; the dashed
drag outline; `.proposal`'s bar; `.selected`'s padding and 0125's selected
offset; `retry send`; `#uncertain-help` and `open an empty draft`;
`oldUpload()`, which no draft this code creates can satisfy; `sentPlacement`,
which a row merged at the receipt makes dead; the words "submission" and
"recover" in owner-facing copy.

android: `DraftComposer` and its outlined `instruction` field; `DraftList`,
the `drafts` destination, `save and return`, `discard draft` and its dialog;
both `new message` buttons; `open exact message` and the divider under each
message; the share screen's composer and its spinner; the stored `Conflict`
and `Received` draft states; the second rubric definition. `refresh` stays:
it serves every pane.

## capability contract

| the owner can | provided by | guarantee |
| --- | --- | --- |
| read the record | `GET /api/messages`, unchanged | rule 1 |
| write one message with files and a reference | `PUT /api/messages/{submission_id}`, idempotent by id | at most one message per id |
| know a send's fate | the receipt | in flight, on the record, or held; never unknown and unshown |
| settle a held send | `GET /api/submissions/{id}`, `retry`, `discard` | retry cannot duplicate; discard removes only the device's copy |
| answer a proposal | `reply`, which sets the draft's reference | unchanged from 0118 |

### the receipt

```
PUT /api/messages/{submission_id}     → 201 created | 200 replayed
GET /api/submissions/{submission_id}  → 200 | 404
body: {"id": "<message uuid>", "message": <Message>}
```

`Message` is exactly the object `GET /api/messages/{id}` returns for that id
at that instant, with `sources` and `proposals`, encoded the same way. it is
required: `submit` commits before it returns and an owner web message is
always in the chat projection, controls and workspace refreshes included.
a failed projection after commit holds the send. a missing projection for a
known id returns 503. a receipt lookup reserves 404 for an absent submission.
both routes use the same projection and encoding as the exact message read.
errors, limits and the origin check stay the same. 0125's shared shown cut
owns the `shown-v1` header and schema `0028`. the daybook adds one field to
the receipt without another contract or schema change. callers that read only
`id` still work with the current header.

successful web font binaries under `/static/home/fonts/` use
`private, max-age=31536000, immutable`. each filename includes the first
eight hex digits of its sha256, including the existing cormorant faces.
everything else stays `no-store`.

### composition

```
submit → PUT ─┬─ 201/200 ────────────────→ accepted(receipt)
              ├─ 400/413/422/426, 409 ───→ refused | conflict
              └─ anything else ──────────→ held → GET submissions ─┬─ 200 → accepted(receipt)
                                                                   └─ 404 → retry | discard
accepted(receipt): today's bookkeeping → reset draft → merge([receipt.message])
                   → presence.accepted() → bottom if pinned → page advance → refresh()
```

a receipt clears only the draft that owns its submission id. it closes that
draft's discard question. a receipt for an already discarded send can still
supply its stored row. before projecting a page that might contain an unresolved
send, resolve its exact submission. read the receipt after the page snapshot:
a 404 then proves that the snapshot excluded this send. let a live PUT settle
first so its refusal or conflict retains precedence. defer the new projection
if the receipt check fails.

android follows the same graph in `Drafts`, ending in `ChatHistory`'s insert,
then the bottom if pinned, then the haptic.

## files and owners

each unit has one owner and an exclusive boundary. d and a start first and in
parallel. b and c start when a's shapes and d's files are frozen, and run in
parallel. the units merge when green and reviewed. assets and their consuming css share a merge so the fonts stay available.

| unit | exclusive boundary | work |
| --- | --- | --- |
| d · faces | `src/jarvis/static/home/fonts/`; `android/app/src/main/res/font/literata*`; `android/app/src/main/res/raw/literata_ofl.txt` | subset upstream Literata roman and italic, both axes, to Latin, Latin-1, Latin Extended-A and general punctuation, with every layout feature kept (`pyftsubset --layout-features='*'`; the default drops small caps and figure styles). woff2 for web at 125 kB or less each, ttf for android, web names include a content hash. the licenses sit beside their faces. the cormorant files and their css references ship together. record the upstream tag, the command and each sha256 in this adr. |
| a · receipt | `src/jarvis/home_http.py`: `put`, `submission`, the cache line in `private` | return the receipt above, read through `visible_message` after `submit` returns. serve fonts immutable. |
| b · web | `src/jarvis/static/home/`: `index.html`, `home.css`, `home.js`; in `presence.js` only the export of its `HH:MM` formatter; in `chat-attention.js` only the previous-article lookup, the boundary's place before a head, and the sampler's pause during the advance; the composer sentence in `SPEC.md` | two passes by one owner. first the page: tokens, faces, preload, stamp, heads, apparatus, proposal, reader, 0125 marks, selected. then the foot: composer dom, states, keys, drop, abort, discard, `accepted(receipt)`, the page advance. composer code stays in `home.js`; no new script. |
| c · android | `android/app/src/main/java/dev/niels/jarvis/`: `Home.kt`, `ChatShown.kt`, `ShareActivity.kt`, `Drafts.kt`, `Presence.kt`, `MessageMarkdown.kt`, `HomeApi.kt`, `MainActivity.kt`, new `Paper.kt` (scheme, faces, conversation styles) and `Composer.kt` (the dock); the manifest | everything under android above. the signed candidate is version code 12, after the shared shown cut's v11. |
| e · documents | pointers in the amended adrs, the decisions index, the implementation plan, `docs/issues/daybook-installed.md` | written by the lead when b merges; the installed issue owns rollout and the handset. |

first placement on web waits for both Literata faces, for at most 1.5 s. if a
face lands later and the owner has not scrolled, the opening placement runs
again; otherwise the anchor is restored once.

## content and its designers

each unit has a designer who freezes its content before red and writes down
what good means for it. the schemas are fixed here; the content is theirs.

| unit | content | the floor for "good" |
| --- | --- | --- |
| d | the subset and a specimen sheet: every row of the type table at true size, both schemes | real small caps and old-style figures render; no fallback glyph in the specimen; the stamp is legible at .75rem in the dark scheme |
| a | json specimens: a first receipt, a replay, one with files and a reference, a 409, a 404 | each `message` equals the page read of the same id and instant in canonical json |
| b | a fixture conversation in the `GET /api/messages` schema, and the copy deck | the fixture holds each case once: both hands; a one-line and a fifteen-line owner message, one of them all code; a long reply with a list, a table, a block and a quote; a progress note; a failure; three days, one in an earlier year, one whose first message is also the first new one; every apparatus kind; an owed and a settled proposal; a selected message. no real private content. copy is lowercase, at most a dozen words, says what is known and what the owner can do, and never says "submission", "recover" or "error" |
| c | the same fixture, and the android strings | identical words to web; legible at font scale 1.0, 1.3 and 2.0 |

## acceptance

temporary end-to-end probes per the [testing reset](0046-reset-testing.md).
for each journey: write the probe, witness the old failure, implement, go
green, refactor to these rules, delete the probe, and record cleanup
separately. run on macbook with dev-server's `scripts/rehearse-worktree`
against the real service and postgres. web in chromium and webkit, desktop and
320 to 390px, both schemes, reduced motion on and off. save named evidence
outside scratch, reopen it and verify its hash. `scripts/verify` stays static
only. independent opus review of this text before red and of the evidence
before each merge.

**a · receipt**

1. a first PUT returns 201 and a `message` equal to `GET /api/messages/{id}`.
2. the same PUT again returns 200 and a `message` equal to the exact message read at the replay.
3. `GET /api/submissions/{id}` returns the same body; an unknown id is 404.
4. a send with a file and a reference returns both in `message`.
5. a client that sends today's header and reads only `id` still succeeds.
6. a font file answers `immutable`; `home.js` still answers `no-store`.

**b · web**

1. the fixture renders in two hands. only owner messages carry a stroke. every
   stamp has the same height. each message exposes its speaker to the
   accessibility tree, and a copied range contains the speakers.
2. three heads; the earlier-year one shows its year. loading an earlier page
   moves a head without moving the viewport. a message merged into the end of
   an earlier day lands above the next day's head. the boundary reads the
   preceding message's time and sits above a head it shares a message with.
3. every apparatus kind renders with no verb and no repeated kind. a proposal
   shows `¶` only while owed, and its title's left edge is the same before
   and after it settles.
4. with the font fetch delayed by 1 s, opening places the boundary at 0125's
   inset. delayed by 3 s with no scroll, the same position holds once it lands.
5. a text-only send with a fine pointer, message reads blocked by the probe:
   the in-flight look at once; `sending…` only after 400 ms; the row is in the
   transcript in the task that handles the receipt; exactly one transform runs
   on the transcript, for at most 420 ms; the field is empty and focused.
   reads unblocked: the next poll mutates nothing.
6. cut the network during the PUT: held. the words are in the composer and
   absent from the transcript. restore and `retry`: one crossing, one row.
   scroll up while held, then let the receipt be found: the row enters and
   the viewport does not move.
7. a stalled PUT offers `stop waiting` at 10 s and enters held with no offline
   notice. a reload during flight returns held.
8. a retry answered 422 stays held; `discard` then `discard` empties the
   composer, and `keep` or escape does not. a 409 leaves the text editable
   under a new id. a 426 leaves it editable beside the upgrade notice.
9. a file dropped on the transcript is staged. a file dropped on the viewer
   does nothing. neither navigates.
10. with a coarse pointer, enter inserts a newline and `send` sends.
    ctrl-enter sends with either pointer.
11. the field grows to its limit and then scrolls; a pinned transcript stays at
    the bottom throughout.
12. 0125 and 0126 hold: the lozenge beside the first line and sticky on a tall
    message; ledge counts; a message on screen for 1 s around a send dries as
    it did before; a tail handoff with the previous article's offset
    unchanged, after an owner message and after a progress note; no transform
    under reduced motion.
13. a send that makes jarvis present an artifact still opens it in the viewer.
    `discuss` while held shows its words and changes nothing.
14. measured contrast for muted and rubric on the rail is at least 4.5:1 in
    both schemes. selecting a message changes no line break. at 320px nothing
    scrolls sideways and `send` has a 44px target.

**c · android**, on an android 35 emulator with the candidate build

1. the fixture renders in two hands at font scale 1.0, 1.3 and 2.0 with no
   clipped text, with heads, and with every other pane's type unchanged.
2. the dock: type while jarvis's last message stays readable. the keyboard
   opening keeps a pinned list at the bottom and leaves a placed list alone.
   restoring a saved position still lands on the same message with heads present.
3. send: the row appears from the receipt, the list is at the bottom, the
   field is clear, and a recording `LocalHapticFeedback` saw `Confirm` once.
4. with the network off: held, `retry`, `discard` and its question in place.
   kill the app during flight: it returns held.
5. share an image with an editing draft: a new slip, the conversation open,
   the dock focused. share the text `pause` into an empty draft and send: it
   arrives as a text original and jarvis is not paused. process-text does the
   same. share while in flight or held: the refusal, and nothing copied.
6. `reply` on a proposal and `discuss` from a file set the reference slip.
7. talkback names the speaker of each message; `send`, `attach` and each `×`
   are labelled 48dp targets.
8. at animator scale zero nothing moves beyond 0126's own rules.
9. no spinner in the conversation or share screen; a divider's pixel is `--line`.
10. the deleted destinations and buttons are gone; `refresh` remains.

**installed.** after the next web release and signed v12 app update, one send
through crossing and handoff on each client, on the s22+ with talkback. the
installed issue records the release identities.

## decisions and their costs

- **italic for life.** the first reviewer wanted italic only until
  acceptance. in roman the two voices are nearly indistinguishable at this
  measure. the cost: a long paste is set in italic. 0126's "provisional is
  italic, final is roman" still holds for jarvis, whose provisional is a
  Cormorant murmur.
- **markdown still renders at the crossing.** 0118's owner choice stands, so a
  typed list, fence or emphasis changes shape as it crosses. plain prose does not.
- **the page advance** is a third sanctioned motion, on web only. android gets
  the haptic and no transform.
- **the receipt carries the row.** about ten lines of service code and one
  read inside the PUT, for a row that appears one round trip after the press
  where it took three. the wire grows by one additive field.
- **an unresolved send fences new chat reads.** a fresh page can already
  contain the owner's send. its companion receipt read costs one lookup when a
  draft is held. a failed lookup leaves the last checked page readable until
  settlement or discard. a page taken before a crossing is read again.
  presence keeps its tick, with the new owner tail held until the receipt.
- **staging hashes the original once.** a large file takes its read time at
  attachment. the send id and all original digests can then survive a reload
  from the moment the button is pressed.
- **fonts are the one cached response.** every other response stays
  `no-store`. a changed face takes a new content hash in its name.
- **one draft on the phone.** an unconfirmed send blocks new writing until
  `retry` or `discard`, and a share during it must be repeated. a share no
  longer returns to its source app: it lands in the conversation.
- **shared text is not typed text.** the owner chose "text on a new line" for
  shares. this text keeps 0105's removable original instead, because typed
  text can be a control word and a shared `pause` must not pause jarvis.
- **`discard` can throw away words that did arrive.** they stay in the record;
  the question says so.
- **heads are siblings, not part of a message.** that keeps a message's own
  geometry fixed, at the price of two lookups in 0125's module.
- **two faces, 246,020 bytes once.** both axes are kept so small sizes and the
  dark scheme are drawn, not faked. scripts outside the subset fall back to the
  system serif. hyphenation is english only. fallback faces get no small caps.
- **old-style figures in fixed-width cells.** the upstream face switches to
  lining figures when tabular widths are requested. fixed cells retain the
  old-style design and the literal clock string on both clients.
- **chat only.** a serif rail beside a sans viewer is a visible seam. the
  android colour scheme is the exception: it is one object and is fixed whole.
- **24-hour times in the device zone**, to match 0126's.
- **no test is left behind**, per 0046. this text and review are the only guard.
- **`open exact message` goes without a replacement** on android. exact
  messages still open from alerts, the ledge and owner-reply links.
- **merge when green.** the next install witnesses 0125, 0126 and this
  together. a regression found there needs a bisect to assign.
- **the signed candidate takes v12.** the first shown cut used v10. the shared
  shown cut reserves v11. the controlled daybook candidate uses the same
  sources with the test's loopback origin.

## differences from the study

- it fakes small capitals with tracked capitals and loads its faces from a
  public host with `swap`.
- it has no `discard`, no `stop waiting` and no discard question.
- its reference slip reads `discussing ·`; the word is `about ·`.
- it shows a `source` apparatus kind; citations stay inline as 0124 has them.
- it right-aligns a table's last column; alignment is not in this decision.
- its `set my hand in roman` toggle shows the alternative the owner declined.

this text replaces each of those.

## review before red

an independent opus review of the first draft returned conditional with
fifteen findings. it verified against source that an owner message is visible
at the receipt, that the three `id`-only callers tolerate the new field, and
that `oldUpload()` and `sentPlacement` are dead. its findings changed this
text: shared text stays an original; a late crossing never moves a placed
viewport; the sampler pauses during the advance; heads, the boundary and the
android key list are specified; `ChatShown.kt` joined unit c and the spec
sentence joined unit b; `refresh` stays; sign-in, 426, reload and process
death have states; android's faces are local to the conversation; fonts are
cacheable. it could not verify the compose api names or the subset sizes.

## face provenance

the source is the [literata 3.103 release](https://github.com/googlefonts/literata/releases/tag/3.103)
at `0c2761b727a1b3a7cffd313c37f0f5163dfc7a63`. the release zip hashes to
`f7fb973cafb26cf785cbebaeaf51c18f87c15a3bcf4d82a7d4857564db5b056d`.
its ofl text is shipped beside the fonts, with trailing whitespace removed.

use fonttools 4.61.1 and brotli 1.2.0. for each hand, set `input` to
`fonts/variable/Literata[opsz,wght].ttf` for roman or
`fonts/variable/Literata-Italic[opsz,wght].ttf` for italic. substitute that
hand for `HAND`.

```sh
pyftsubset "$input" --unicodes="U+0000-017F,U+2000-206F" \
  --layout-features="*" --output-file=literata_3_103_HAND.ttf
fonttools varLib.instancer literata_3_103_HAND.ttf wght=380:600 opsz=7:20 \
  --no-recalc-timestamp -o HAND-web.ttf
pyftsubset HAND-web.ttf --unicodes="U+0000-017F,U+2000-206F" \
  --layout-features="*" --flavor=woff2 --output-file=HAND.woff2
```

the android subset retains both full axes. a web subset with full axes
costs about 180 kb per hand. the 125 kb ceiling keeps both axes within the
web styles' weight range and a 7–20 pt optical range. a larger browser
default font size uses the 20 pt design. the unicode subset removes rules
with no remaining inputs, including the greek-only `ss01` and combining-mark
`mark`. roman `rvrn` becomes active above weight 650, outside the web range.
small caps, old-style and lining figures, proportional and tabular figures,
and the other applicable rules remain.

| file | bytes | sha256 |
| --- | ---: | --- |
| `literata-3.103-roman-1ab05c52.woff2` | 123812 | `1ab05c52caf96b013e5fc7ba46648a6ff7973523f42c25f2ae3ecb73d59bc482` |
| `literata-3.103-italic-01e71417.woff2` | 122208 | `01e71417f403ca512f38be8379a8b8c73117f1f2c9bd634cef9c6c8c25d6911a` |
| `literata_3_103_roman.ttf` | 386308 | `db950d28d7e75f845a4afd380fb84b2837b3bd5ae86336168fcaf1c3c27fe367` |
| `literata_3_103_italic.ttf` | 370004 | `365718f2e9625b7d8ed190542221e519c5dc37de2eeefa6e94d35fde1599682a` |
| literata ofl, both copies | 4388 | `72ef68216a08669b2a977fe788a4aea6114636adbbe0bc6aa9192f63f8d400d0` |
| `cormorant-regular-982538ce.woff2` | 22896 | `982538ce965491bddd0cd96f81c7c694ce19a3f4af7efbc9316ead7820b34c14` |
| `cormorant-italic-c80b489f.woff2` | 23660 | `c80b489f34b4bb27a716682b8f8a5c3efec50fb8156e1088a43ed206003b6951` |

the second opus review used the rebased source at `3b0d61a`. it identified
the signed v10 collision, the cache exception and file identity requirements,
the post-commit projection boundary, and ownership of draft settlement. the
daybook keeps its original path. the decisions index distinguishes it from the
other 0127 by title, following its existing practice for 0078 and 0114.

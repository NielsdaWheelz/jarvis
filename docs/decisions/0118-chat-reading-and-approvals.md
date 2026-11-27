# adr 0118. reading and deciding in chat

the [daybook](0127-the-daybook.md#the-reader) sets the conversation's type, apparatus, and proposal presentation.

**design only · november 26, 2026.** web and android render both speakers’ sent messages as markdown. the desktop column keeps its current width. an action card belongs to its recorded proposal. jarvis’s draft viewer owns exact email inspection. this amends the presentation rules in [0091](0091-source-backed-reports.md), [0097](0097-todo-home.md), [0105](0105-native-android.md) and [0107](0107-google-workspace.md).

## reading

history and exact-message views share a reader per client. render paragraphs, six heading levels, emphasis, strong, nested lists with ordered starts, quotes, thematic breaks, links, inline/block code and pipe tables. use existing typography and compact headings. wrap prose, urls and filenames. preserve selectable code whitespace, table headers and column order. only wide blocks scroll sideways.

use commonmark plus gfm tables. recognize html tokens on both parsers and emit their literal source as text, including markdown inside an html block. prohibit html rendering sinks and webviews. display soft and hard breaks as newlines, and image descriptions as inert text. an unclosed fence ends at message end. render cards outside that body. captured fields, emails, filenames, statuses and google prompts stay literal. [commonmark](https://spec.commonmark.org/0.31.2/) · [tables](https://github.github.com/gfm/#tables-extension-)

parse message `text` on content change. package pinned markdown-it with the web shell; pin commonmark-java and its table extension for compose. map their nodes to DOM or native text/blocks. two dependencies require shared parity examples, but avoid a custom rich-text API and repeated server parsing on polls. storage, submissions and archive keep the source. [web parser](https://github.com/markdown-it/markdown-it) · [native parser](https://github.com/commonmark/commonmark-java)

disable optional linkify extensions. classify markdown destinations and bare citations with one function per client. scan decoded plain inline text outside code, html tokens and links; retain balanced parentheses, exclude trailing punctuation. bare `attachment:<uuid>` opens the original.

| destination | behavior |
| --- | --- |
| `/`, `/overview`, `/m/{uuid}`, `/t/{uuid}`, `/f/{uuid}[?page=N]`, `/v/{slug}[/{rev}]` | reuse normal navigation. uuid is canonical lowercase, page is a positive decimal without leading zeros up to 2^53−1, slug and revision follow [home page identities](../../src/jarvis/home_pages.py). only the file route takes that one query. current and pinned publications keep their existing behavior. |
| absolute url at the configured jarvis origin | apply the same route grammar. fragments, extra query parameters and unknown paths stay inert. use [android routes](../../android/app/src/main/java/dev/niels/jarvis/Routes.kt) and the web origin/navigation primitives. |
| external http(s) with a host and no userinfo | open on activation in the browser. preserve modifier-click and back. reject protocol-relative urls, credentials, other schemes (including email autolinks) and unrecognized relative paths. rejected labels stay readable. prose never submits a request on the owner’s behalf. |

## deciding

both `GET /api/messages[?before=…]` and `GET /api/messages/{id}` return batched `proposals[]`. replace `detail` with ordered `fields:[{label:string,value:string,before?:string}]` and require `status_label`. retain `action_id,title,status` and paired optional `decision,owner_message_id`. render values literally, showing before → value when present. identical action evidence yields identical fields in both reads. keep current write, persistence and authority contracts. [projection](../../src/jarvis/home_reads.py) · [approval](../one-main-events.md#conversational-approvals)

one card per action in server order. show operation, target, consequences, status and **reply about this**. the ordinary composer carries `{kind:"proposal",message_id,action_id}`. main interprets owner words. link the actual decision message, including prior consent on an owner row. a general question has no card.

| recorded evidence | status shown |
| --- | --- |
| `awaiting_approval` / `queued` | awaiting your reply / waiting to apply. prefix queued with “approved” only with a recorded approve decision. |
| `executing` | applying. a recognized `workspace_ack_v1` changes this to “google acknowledged · checking result.” |
| `succeeded` | use the operation’s completed verb. for workspace take verification and reason from the recognized success receipt. unverified reads “google acknowledged · result unverified” with the recorded reason. |
| `failed` / `uncertain` | show operation failure and known reason / “unknown whether [operation happened].” |
| `cancelled` | “denied” with the first successful deny decision, otherwise “cancelled.” |

derive labels from `action.status`, the first successful `approval.respond` and the recognized result envelope’s `value.verification` and `value.reason` for workspace writes. use [action receipt semantics](../../src/jarvis/actions.py). preserve opaque finalized tool/id/status/decision, absent evidence and the existing integrity error for unresolved unknown bindings.

| action | good content |
| --- | --- |
| calendar | “move team check-in · this occurrence.” show calendar, changed values, old/new start and end with their recorded zone, guest addresses and explicit notification choice. distinguish single event, occurrence and series. retain date-only all-day values. a deletion identifies what disappears. preserve material captured fields including recurrence, location and reminders. |
| original deletion | “delete original · estimate.pdf.” identify the frozen original id so duplicate filenames remain distinguishable. |
| mail | name the actual operation. a discard identifies its exact old draft and any verified replacement. a recorded send shows subject, to/cc/bcc and ordered files. respect the current connector’s drafts-only contract. an ordinary saved draft or suggested reply has no approval status of its own. |

**mail ships in two steps.** the chat cut keeps literal inspection via exact-message reads and `?mail_body=true`. retain `read_email,mail_body?` and detail-only saved draft/integrity fields. scope each disclosure to its action or saved revision and preserve it on refresh.

at the viewer cut, **open draft revision** takes the presenting message id (either speaker) plus one action id or saved draft ref. the draft viewer owns routes, lookup, content and editing. validate association and frozen identity; distinguish unavailable, integrity failure and unrelated ref. never redirect to a newer edit. opening writes nothing; retained snapshots issue zero gmail calls. discard retains metadata and digest only. qualify an exact source for actionable discards; label settled missing bytes “exact revision unavailable.” replace both inline readers and retire their exclusive body fields together. [handoff](../issues/chat-draft-revision-inspection.md)

**google permission.** in authenticated open chat, display the live round’s product, operation, literal prompt, offered labels, expiry and cancel. long prompts and choices scroll within available height. `GET /api/workspace/approvals` returns zero or one round. `POST /api/workspace/approvals/{id}` carries `{choice:offered_value|null}`. 204 records input, 409 means unavailable, 410 expired. after lost acknowledgement show “choice unconfirmed.” refresh; only an explicit choice on a freshly confirmed open round can retry. failed reads leave the last-known round unconfirmed and disabled. fence late responses by id. android back collapses to “google is waiting · open.” only explicit cancel posts null. reopening or navigating sends nothing. refresh on return, remove on confirmed absence, present a new round independently. a request can expire while the owner is away. [round contract](0107-google-workspace.md#a--google-transport-and-required-owner-input)

## implement and qualify

before code, assign a content designer to each feature. reading supplies a short exchange and a cited report. action supplies calendar, delete, mail, prior consent and uncertain outcomes. permission supplies exact provider copy, long choices and receipt states. layout supplies narrow and large-text specimens. each names the facts the reader must recover and what each control does.

| engineering owner | exclusive edit boundary |
| --- | --- |
| action projection | `src/jarvis/home_reads.py`. adapt the existing binding-aware formatters and receipt projection. return labeled fields directly. inspect `workspace_write_models.py`, `home_refs.py` and `approval_tools.py` for contracts. |
| web | `static/home/` under `src/jarvis/`. own the parser asset, DOM presenter, `renderMessage`, `merge`, `discuss`, `workspaceApproval` and scoped css. reuse delegated navigation, deep-link anchors and bottom pinning. update dynamic controls in place keyed by message/action/round. |
| android | `android/app/build.gradle.kts`, `Home.kt`, `Workspace.kt` and the native markdown presenter. reuse `MessageEntry` in list/detail, `Routes`, existing saved pane state, material theme and the scoped composer. key local state by its displayed identity. |

delete both link-only chat renderers. share each platform’s destination classifier with active non-chat callers. retain literal readers where their field contract requires one. list refresh must preserve exact-detail evidence. exclude width changes, prompt changes, syntax highlighting, markdown actions and historical rewrites.

use dev-server’s `scripts/rehearse-worktree` on macbook for a detached rehearsal. use real web clients and a signed s22+ candidate against an isolated service/database and controlled google peer. per feature: author temporary end-to-end checks, witness the old failure, implement, prove green, refactor, replay and obtain independent opus review. preserve passing controls. save named evidence outside scratch, reopen and verify its hash, then delete the temporary probes. record fixture cleanup separately.

1. both speakers, history and an older exact link: nested list, code, wide table, parenthesized citation, query containing `&amp;`, page-six original, an html block containing emphasis, image and a literal `###approval-card###`. verify semantic blocks, exact targets, zero passive fetches, copyable code and zero invented proposals. re-open a pre-cut row unchanged. keep citations beside their findings.
2. two actions plus an ordinary question: reply to one, keep the other pending, resolve one action once. inspect a prior-consent receipt, acknowledged/unverified and unknown outcomes. put markdown and punctuation in literal fields. open the correct immutable mail revision through the current reader, then back. at the viewer cut repeat after a later edit. verify the draft, card, reading place and execution count.
3. at 320/390px, either side of 720px, desktop and enlarged native text: with a draft already referencing one proposal, reply to a second with a long unbroken title. keep/use and send remain reachable. assert shell/chat/composer fit, every character remains reachable, only deliberately wide blocks scroll sideways. first open starts at the message top. on polling, paging, reload or return retain the appropriate reading anchor. a status-only refresh preserves focus, selection, expanded state and local block scroll.
4. present a long google challenge to both clients. reach the final choice and cancel. back sends zero posts, the waiting row opens the same round, which is still available on return before expiry. distinguish 204, competing client/409, expiry/410, failed get and lost post. deliver a late response after the next round appears. check the actual id, value and single consumption. no inferred action success.

freeze the projection first. qualify the service and both clients together. stage the matched signed app and shell, close old clients, switch the service, update the phone and reload web before resuming use. the hard cut requires a coordinated update. the later mail cut inventories linked records by binding/class using counts only. rehearse each present readable class, including verified 0105 draft, workspace create/replacement and historical send, plus missing bytes and integrity failure. resolve any unclassified previously readable binding before removing the inline readers. the chat cut can ship independently.

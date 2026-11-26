# adr 0123. a private library of published work

**design for implementation · 26 november 2026.** this changes the navigation in
[0115](0115-web-home-address.md) and [0117](0117-inline-todo-viewer.md) and the
publication interface in [0087](0087-private-web-home.md#authored-canvas).
the work is complete when the owner can find a named work, reopen an exact
edition and reach its recorded delivery on desktop and phone.

## product and addresses

an artifact is a page deliberately published from private notes. one slug
names the work. a full commit id names an edition within that work. title
changes preserve the slug. the owner can publish a static comparison or an
interactive instrument. ordinary answers live in chat. stored documents and
downloads belong to [files](0120-drive-files.md). scope ends at browsing,
publication metadata and the return to chat. search, tags, thumbnails, saved
slider positions, a general activity feed and off-host backup are separate.

| private address | promise |
| --- | --- |
| `/` | the wordmark. resolve selected home once per fresh visit, pin locally at `/`, or show todos after a successful empty selection. a failed home read offers retry. |
| `/todos` | always show the existing inline list. `/t/{id}` still opens the exact row, including completed work. |
| `/artifacts` | one row per visible work. title opens the exact edition shown as current in that list read. an editions disclosure opens in place. |
| `/artifacts/{slug}` | resolve current once and replace this visit with its full pinned address. |
| `/artifacts/{slug}/{rev}` | read that edition directly, independently of home or shelf. copy its exact address. a later publish leaves the reader in place. |

retire `/overview` and both `/v/…` shell routes, their native app-link
registrations, generators and classifiers. old literal links return 404
after authentication. old structured `{kind:"view",slug,rev}` references
render at the new address. original messages, digests and receipts stay
immutable. keep the existing slug and full 40/64 lowercase hex revision
grammar. the new routes take no query, fragment or extra segments in
internal link classification. the browser does not send fragments to http.

## a · publication and conversion

the native publisher is the sole catalog writer. keep the existing notes root,
commit eligibility, 16 mib utf-8 export, directory lock, atomic replacement
and application read permissions. keep `jarvis-page publish SLUG COMMIT
[--home]`, `resolve SLUG [REV]` and `withdraw SLUG`. publish returns the same
receipt fields with the new pinned url. resolve still returns a bare view ref.

```text
catalog = {format:2, home:slug|null, works:{slug:{current:rev, editions:[edition,…]}}}
edition = {rev, title, description:null|string, change:null|string, published_at:null|utc}
```

read the committed html head once as inert text. take the first title,
optional meta description and optional meta named `jarvis-change`. collapse
whitespace. use the slug words if the title is blank. bound display copies to
160 unicode code points for the title and 240 per optional field, truncating
an overflow with a terminal ellipsis within the bound. blank optional values
become null. render all three as text. newly authored pages should supply a title. a designer's
specimen is “bench vise”, “jaw travel at two screw pitches”, “added the fine
screw”. a hash as a title or “improved experience” as a change fails the
content review. absent optional copy costs no line in the ui.

append each newly admitted revision once under the lock, with server utc
publication time. preserve its metadata on repeat. publishing a → b → a
makes a current and retains both dates and their order. home refers to a
member work, current to a member edition. withdrawal atomically removes
the work and all its editions from the catalog and clears a matching home.
raw and framed access check membership. a deliberate later publish admits
only its selected edition, with a new admission date. that identity's exact
links and qualifying earlier delivery can then reopen. private bytes may
survive withdrawal. the library shows presently published editions.

convert once during the [0104 stopped cut](0104-maintenance-without-owner-pause.md).
exclude every publisher and use its directory lock and native ownership.
freeze the old catalog and hashes of member exports outside scratch. carry
exact membership, order, home, current and html bytes. use the same metadata
extractor on member exports, including a later deliberate republication. old dates
are null. never infer publication from git time, mtime or loose exports.
invalid pointers, duplicate revisions, unreadable or invalid member bytes,
and ambiguous missing catalog stop before replacement. close every publisher
host before taking the snapshot. the application identity checks that same
snapshot before replacement. initialize an explicitly verified
new empty installation. target runtime treats a missing catalog as an error.
bind preimage and validated target digests to the named cut before replacement.
enter the existing `applying` phase before the first mutation, even at the
same database schema. do not use a database migration for the filesystem cut.
use the existing fsync/replace primitive and publisher uid/group. reopen with application access
and compare membership and hashes. interrupted conversion recognizes the
verified source or target under that same hold. runtime reads format 2 only.
postgres recovery excludes these files.

## b · private reads and conversation

reuse `HomePages` for catalog membership and `ViewRef` for references between
systems. return complete metadata lists. cost grows with the owner's library.
the service orders both collections. one read per catalog response,
under the existing owner access and private/no-store headers. include the
configured iana `timezone` beside `items` or `editions` for the existing client
date formatters. timestamps are rfc 3339 utc strings. `current` is the rev.

| get | response |
| --- | --- |
| `/api/artifacts` | `{items:[{slug,current,title,description,edition_count,last_published_at}]}`. title and description belong to current. last_published_at is the greatest known admission time for the work. newest first, undated last, ties by ascii slug. |
| `/api/artifacts/{slug}` | `{slug,current,editions:[edition,…]}`. reverse admission order, including undated editions. direct readers use this without the collection. |
| `/api/artifacts/{slug}/{rev}/discussion` | `{message_id:uuid|null}` for a member. returns the assistant message for `/m/{id}`. unavailable discussion storage affects this control alone. |

the shell serves well-formed deep links after authentication. unknown work
returns api 404. an absent pin in a successful work response is unavailable;
its content and discussion reads return 404. a service/catalog failure gets
503 with retry. list success with zero works gets
the empty state. failed reads get retry. retire both old `/api/views` reads.
keep the bare ref for `/api/home`, internal reference validation and native
resolve, and the existing isolated bytes at `/content/{slug}/{rev}`.

give the existing visible progress/final response contract one passive field,
`artifact_links: ViewRef[]`, empty for no delivery. silent has no links.
main puts edition handoffs here instead of typing their urls into prose.
at live progress or live/sealed final settlement validate the ordered refs
against one catalog snapshot. on an already-visible reply also append the
proposed `present.ref` if it is a published view, even when its request
fails the presentation lineage check. only a valid explicit presentation
can take over the asking visit. never promote a withdrawn ref or create a
reply for a suppressed outcome. deduplicate by slug and revision and store
them in `message.home.artifact_links` in the same message transaction.
expose them on both existing chat reads as ordinary exact links. include
nonempty admitted links as host metadata in the existing input/archive
projection, so a later reference to “that comparison” retains its pin.
preserve historical projection bytes. an equal
replay returns the original message. a withdrawn target is omitted from the
links and logged with its reason. catalog i/o errors use normal retry/recovery.
render an identical explicit presentation and passive link once. artifact
auto-open still requires an armed request and lineage-checked `present`. passive links carry
no request id and cannot move a tab or change a draft. the extra typed field
costs a main contract revision. rotate its output name and owning binding. verify the actual
prepared prompt and schema budgets. an earlier message without that field has
zero passive deliveries. keep its existing structured presentations.

use visible assistant messages in the configured conversation. match the
exact structured `(kind=view,slug,rev)` and take the first in the transcript's
`(created_at,id)` order. accept either a recorded passive link or presentation.
the answer's `message.id` is the link target. `present.request_id` identifies
the owner's request. a later presentation can be the first surviving
delivery. label the action **open chat message**. historical prose links,
owner references and a matching title cannot establish delivery. omit the
control after a successful null result. browsing, copying and this backlink
start zero assistant turns. the designer's two editions price the repair at
$1,460 then $2,220 against a $2,100 replacement. the second reply must
explain why the recommendation changed. opening the first must recover the
$640 saving and its own reply.

## c · web reader

use ordinary destination links beside the wordmark, with the selected section
underlined and exposed via `aria-current`. use the existing paper, ink, serif
titles and focus ring. show files when its own viewer ships. follow the
[chat sidebar design](0122-chat-sidebar-and-phone-alerts.md) on desktop and
narrow screens. wrap the destinations below the wordmark when needed. long
titles wrap. title and edition disclosure are separate keyboard targets.
folding changes neither the url nor the draft. show an owner-local date with
year where needed, a distinct current marker, and the authored change when
present. identify undated/same-day editions by a distinguishing revision
prefix when needed. a copy action always uses the full pinned https address.

retain tab-local drafts, file selections, requested-presentation arming and
navigation-version fencing. refresh visible membership with the existing
reader tick. retain a successful snapshot on transient failure and mark it
stale. authentication loss clears private content and invokes sign-in. a confirmed withdrawal removes the frame and shows unavailable in
place. a new current pointer offers a link and never moves an open pin.
use the existing opaque, network-isolated iframe. keep edition controls and
discussion outside it. back restores actual origin, open disclosures, row
focus and scroll. cold app return from a pinned edition goes to the shelf.
native browser back retains normal history. the home reader keeps `/` and
offers its displayed edition link. preserve inline todo and exact-message
behavior, including drafts with a different reference. “discuss this edition”
uses the existing pinned ref and keep/use choice. link-only chat delivery
appears as a normal named link. use a readable slug plus distinguishing pin
when a historical chat link has no stored title. opening and copying work
with native link gestures. “no published artifacts” requires a successful
empty catalog. a lone edition needs no disclosure.

replace the web `todosCanvas` address workaround and `/overview` rewrite.
reuse `objectPath` for generated links and one route classifier for navigation,
chat destinations and reader dispatch. select the file reader only on a file
route. retain visit state used for scroll, draft and home pinning. replace
android's `Route.Overview` with the explicit todos destination.

## d · android reader

compose lists the same ordered works and editions. use the existing route
parser/builder, verified app links, authenticated read client, saved visit
state and draft store. exact entry reads the work directly. resolve current
once. hand off only that pin to the existing browser custom tab. give the
native pane its exact-edition open/retry and discuss actions. never pass a
native credential into the browser. browser sign-in must return to the pin.
system back from the browser returns to the native visit. retain shelf
position, expanded work and draft through activity recreation. avoid
relaunch on resume/recreation. a fresh intentional open can launch again.
an unavailable browser leaves a retry. talkback names the work, edition,
current state and actions. render `artifact_links` in native transcript and
exact-message detail as passive links, once alongside an identical presentation.
the pinned native pane offers **open chat message** for the verified assistant
id. back from that visit returns to the pane without launching the browser.
preserve independent android drafts.

## ownership and temporary proof

| unit and exclusive implementation owner | content designer's red → green journey |
| --- | --- |
| a · `home_pages.py`, publisher cli and one-shot catalog conversion | designer authors the bench vise baseline and fine-screw revision with labeled units and a keyboard input. publish from real committed private notes. try repeat, concurrent/failing publish, select a → b → a, withdraw and republish b. convert dated/undated fixtures with orphan exports and a corrupt member. verify locks, membership, bytes, ownership and interrupted conversion. |
| b · `home_http.py`, `home_reads.py`, `terminal.py`, `native_protocol.py`, `native_journal.py`, `input_framing.py`, `definitions.py`, `session-compatibility.json` | designer writes the two microscope replies. have subscribed main publish and deliver with the typed field and no duplicate artifact url in prose. through real service/postgres prove passive delivery after denied lineage, requested presentation, sealed replay, scope, timestamp tie, missing association and retired routes. a shared commit under a second slug yields its own message. |
| c · `static/home/{index.html,home.js,home-dom.js,home.css}` and web link classification | designer supplies empty, undated, changed and withdrawn examples. desktop and narrow browser open r1, edit an unsent draft, publish r2, copy/reload r1 in a fresh tab, open its exact reply and return. verify focus, scroll, draft, delayed reads, auth return, withdrawal and zero automatic navigation on an ordinary delivery. |
| d · android manifest, `Routes.kt`, `Home.kt`, `HomeApi.kt`, visit state in `MainActivity.kt` and android link classification | designer adapts the work for touch and talkback. on the s22+ open r1 from its passive reply, return from the browser, open its chat message from the native pane and go back. repeat cold through sign-in, rotate/recreate, verify draft, scroll, a failed handoff with retry and the retired app links. |
| integration · `deploy/{prepare-cutover,activate-release,verify-containment}`, native cutover inventory, operations runbook and combined proof | rehearse the stopped cut on macbook. old literal urls fail, old structured refs render with new urls, files/todos/mail still return to their origin, application reads only admitted exports. verify both isolated raw and framed reads. |

freeze the shared shapes first. a and b define producer/consumer examples.
c and d can build against them independently. integrate on the selected
drive, chat and sidebar baseline. whichever of 0120, 0123 and
adr 0124 lands later rebases shared
files on the earlier main revision and rotates the main binding, output name
and viewer header once for the composed cut. stopped activation and sealed
recovery verify the exact output schema. b owns the artifact authoring and handoff prompt changes.
preserve integrated source slots and the unrelated draft
presentation when composing `message.home`. each feature's designer freezes good and
bad examples before red. run temporary end-to-end tests against the actual
predecessor, then target, then simplified target. use real git, service,
postgres, browsers and handset for the named journeys. inject faults only
at their boundary. use dev-server's `scripts/rehearse-worktree` for detached
rehearsal on macbook. independent opus reviews each feature's contract and
evidence. reopen and hash named evidence outside scratch, delete this
feature's probes and fixtures after green, and report cleanup separately.
the standing tests stay. deleting the feature probes trades ongoing automated
coverage for the retained evidence of this cut. the physical and installed journeys require their
own observations.

before stopping, resolve uncertain sends with their existing receipt and
preserve device drafts. a browser draft with attached bytes or an unconfirmed
editor save needs owner disposition before closing that tab. reload other
browser tabs in place. under operator custody reconcile pending incompatible
native submissions or seals under their original contract, convert and verify
before the matched service, publisher, shell and signed app serve. use one
successor `x-jarvis-viewer-contract` value across web, android and service.
reuse 0120's exact-header check on message list/detail, submission and
receipt reads, extending it to home and the new artifact api. a stale client
gets 426 and a reload/update instruction. ordinary shell/app links and
sandboxed content keep browser authentication without this header. retired
routes remain 404. co-delivered 0124 uses that same contract value. remove
superseded routes and private navigation branches in the same cut. ship one
catalog decoder and one exact-ref codec per client. a failed changed cut
repairs forward under the hold. at the separately authorized installed
smoke, publish two disposable editions without selecting home, deliver one
in ordinary chat, reopen both pins on desktop and handset, check the exact
delivery and withdraw the specimen. compare the preexisting home and
membership and record any incomplete cleanup.

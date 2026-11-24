# adr 0087. the private jarvis home

next release design against `ae487ca`, postgres `0016` and
[adr 0086](0086-native-recovery-and-memory-availability.md). this contract owns
behavior and acceptance. the [roadmap](../implementation-plan.md) owns delivery order.

## what opens

open `jarvis.nielseriknandal.com`, sign in with google, and land on the page jarvis
has chosen as home. chat, decisions and todos share a narrow sidebar. jarvis owns the
main area. it can publish a reading list, a parts diagram, or two designs side by
side from ordinary files in its private notes repo. a release of jarvis is unnecessary.

- **conversation.** speak, upload, approve, pause and resume on the web. discord sends
  a short link for every visible final reply and every decision, even with the site
  open. the owner accepts the phone noise. the native app and push belong to the next pr.
- **attention.** an explicitly requested result opens once in the tab that asked.
  other work offers a link. a new tab opens the current shared home. an existing tab
  keeps its object, scroll position and draft when another tab or jarvis changes home.
- **interaction.** a slider or star belongs to the open view. ask jarvis in chat to
  save a choice by naming it, e.g. “save four stars for the odyssey.” on a phone the canvas fills the screen, one labelled control opens
  the sidebar, and back returns to the object. opening a decision never executes it.
- **withdrawal.** “take this down” closes the page and all its revision links. the
  private git source survives. a person who already received bytes can keep them.

this supersedes the discord client/readiness/delivery rules in
[0011](0011-single-channel-discord.md) and the hosting deferral in
[0071](0071-simple-event-driven-v2.md). retain one main, conversational approval and
the independent memory unit. public sharing, additional users, arbitrary server
programs, a widget catalogue and television integration are outside this release.

## conversation, records and decisions

`jarvis.service` owns the web listener and the existing canonical inbox. serve after
deployment ownership, canonical control and startup effect/native recovery are ready.
pause accepts speech and exact trimmed, case-insensitive `pause` and `resume`. treat
only bare control text as a command. conversational `stop` goes to main. entered
effects retain their recovery rights. when jarvis is stopped an open tab keeps its
draft and offers retry. a cold link may show the edge outage. memory remains available.

give every relevant reader, writer and maintenance command immutable `owner_scope`
and `owner_archive_key` settings. use the existing stored channel scope and the exact
`discord:<guild>:<channel>` archive key for this installation. changing that key
would republish old memory. new owner speech has `source=web`. preserve historical
discord attribution and keep the notice destination independent of both identities.

migration `0017` adds one immutable nullable `message.home` jsonb and the notice table
below. owner web rows carry `{request_sha256,ref}`. visible assistant rows may carry
`{present:{request_id,ref}}`. otherwise use sql null. reuse `message.trace`'s existing
attachment manifest. under the conversation lock, check `(web,submission_uuid)` first.
hash canonical json of exact text, normalized ref or null, and ordered file descriptors
(name, measured size and sha256). the host determines file type. equal replay returns the original id
even after withdrawal/deletion. changed reuse returns 409. validate current target
availability only on first insert. only that insert stamps time, wakes main or applies a control.

carry references as labelled metadata through opening, steer, native recovery and
canonical archive projection. preserve original owner text and historical digests.
new native progress/terminal output admits nullable `present` on a visible response.
main uses it for an explicitly requested ready file or published revision. validate
the canonical web request id under the settlement lock *before* applying dispositions.
the current attempt must have received the web request itself or a descendant with
proven `parent_request_id` links back to it. a completed parent remains eligible for a
later worker result. a stopped lineage, unrelated event or unparented wake can offer
a link. if a request lacks that lineage or the target disappeared, keep the reply and
its dispositions and omit automatic navigation. presentation confers no execution authority. retain bounded chat prose and
put longer work in a document. rotate affected fingerprints and prove provider fit.

the sidebar reads visible owner/assistant messages, excluding the synthetic initializer.
`work` owns todos. `action` owns approval status and immutable arguments. show current
`owner_input` waits as one decision per question, keyed by the terminal message uuid.
use the committed attempt's input outcomes and the inputs' current wait/settlement
identity. a later wait on the same input cannot resurrect an earlier question.
a new seal with an owner-input wait requires `needs_input` or `partial` with a question.
for a historical unlinked wait, use its origin input id and label the missing question.
keep the decision link readable after settlement. a reply supplies the reference to
main's existing `approval.respond`. [approval contract](../one-main-events.md#conversational-approvals)

render consent-bearing calls from their captured arguments. show send-draft subject
and to/cc/bcc, calendar create/update/delete summary, calendar, times, affected
attendees and notification choice, or delete-original uuid and its attachment row's name. for a historical
unrecognized receipt show its recorded tool, status and conversation link. leave raw
journals private. the sidebar never synthesizes a successful action from an answer.

## web interface

one same-origin fastapi/uvicorn api and packaged html/css/javascript. reuse nexus
composer behavior where it fits. poll while visible and on return. an update can lag
one poll, and reconnect needs only ordinary reads. merge by canonical
id and fill missed history before moving the displayed boundary. keep the text, ref
and submission uuid per tab through login or reload. after an uncertain send, look
up that uuid before asking for file reselection. pending local files may require
reselection after reload. there is no second offline inbox.

| route | request and result |
| --- | --- |
| `PUT /api/messages/{submission_uuid}` | json `{text,ref?}` or multipart with one json `message` part and ordered `file` parts. 201 durable first receipt or 200 equal replay, both `{id}`. 409 changed reuse, 413 size, 422 invalid, 503 unready. allow blank text with files. |
| `GET /api/submissions/{uuid}` | `{id}` for a committed web submission, otherwise 404. an in-flight request can still commit. retry the same uuid. |
| `GET /api/messages[?before=…]`, `/api/messages/{id}` | `{items,next_before}`, 50 in reading order, keyset on time and id. detail `{id,role,source,at,text,files,ref?,present?}`. reads carry no delivery receipt. |
| `GET /api/todos[?offset=…]`, `/api/todos/{id}` | reuse `WorkStore.list(ACTIVE_WORK_STATES,50,offset)` and `get` including their as-of time. |
| `GET /api/decisions[?before=…]`, `/api/decisions/{kind}/{id}` | open decisions, 50, keyset on date/kind/id. `{items,next_before}`. detail `{kind,id,at,title,status,detail,origin_message_id}`. kind is `action` or `question`. |
| `GET /api/files/{id}` | stream a verified ready original. 404 unknown, 409 pending/unavailable, 410 deleted. shell link `/f/{id}` accepts `?page=N` for a pdf. |
| `GET /api/home`, `/api/views/{slug}[/{rev}]` | home returns `{view:ref|null}`. view lookup returns the exact published `ref` or 404. `GET /content/{slug}/{rev}` serves only its published html bytes. |

a `ref` is exactly one of `{kind:"view",slug,rev}`, `{kind:"file",id,page?}` (one-based),
`{kind:"todo",id}` or `{kind:"decision",type,id}` with type `action` or `question`. ids are canonical uuids.
validate in owner scope. display “discuss this” as a removable composer reference.
let the owner specify a pdf page when the native viewer cannot report one.
`/m/{id}`, `/d/{kind}/{id}`, `/t/{id}`, `/f/{id}` and `/v/{slug}[/{rev}]` open the shell at their
target after login. render historical `attachment:<uuid>` into a link at display time.

## originals

accept ten files and 90 mib of encoded body per submission, below the configured
edge limit. cap text at 16 kib utf-8 and its encoded json envelope at 128 kib,
including in multipart. this admits fully escaped text without buffering a file-sized message. stream and bound actual bytes, independently
of headers. preserve source filenames as display data. each web original has
`{kind:"web",submission_id,slot}` with zero-based slot and a deterministic attachment
uuid. extend the existing source-key, db manifest and capture contracts. gmail keeps
its existing retention path and 100 mib per-original limit.

before committing, fsync finished uploads and their directory under private durable
`/var/lib/jarvis`. stage by submission, slot and digest. racing equal sends may
publish identical bytes. commit owner message, manifest and pending attachment rows
with their byte facts in one transaction. incomplete requests produce no speech.
the existing capture worker owns transfer to r2. transient pre-put reads keep the
source. try each pending row once per pass and retry on a later tick. after put
entry, observe/reconcile under the existing one-put rule. a permanent rejection,
byte mismatch or uncertain result retains the
spool for repair. release committed bytes only after verified storage or explicit
stopped disposition. stopped cleanup reclaims orphan staging and leftovers for
ready/deleted rows. a delete request while capture is pending returns pending.
after capture the owner can request the ordinary approved deletion.

reuse `AttachmentStore.open`'s verified read. stream from a held descriptor, with a
safe filename and `nosniff`. inline verified pdf and supported raster images. offer
other types, including html/svg, as downloads. show the capture state and native
print/download. the preview checks the verified original for its headers and checks it
again when serving the bytes. this costs a second hash on a ready local file. a read admitted before deletion may finish.

## authored canvas

main invokes the running native release's `deploy/jarvis-page` executable.
`publish SLUG COMMIT [--home]` reads the regular utf-8 blob `site/SLUG/index.html`
from a full commit reachable from a local notes branch. one self-contained html file, embedded assets,
16 mib maximum. slug matches `[a-z0-9]+(-[a-z0-9]+)*` up to 64 characters. return
`{slug,rev,url,is_home}`. publishing selects the new current revision for that slug.
`--home` also selects the shared front page. local publication requires no remote
push. `resolve SLUG [REV]` returns the published view reference, using the current
revision when omitted. an unavailable work or revision exits nonzero. resolving an
old revision leaves the current revision and home in place. use this read when an
owner requests an existing publication. `withdraw SLUG` atomically removes every
published revision and clears home if selected. only a deliberate later publish can reopen a revision.

the installer creates `/var/lib/jarvis-notes/.git/jarvis-pages` inside the already
granted native git root. native uid and group `codex-clients` own the directory.
use 0750 directories and 0640 files despite native umask 0077. jarvis has group
read access. no new writable root, setgid or change to existing source permissions.
the standalone publisher needs no database or secrets. under one shared writer lock,
write/fsync immutable exports first, then atomically replace and fsync the catalog
`{home:slug|null,works:{slug:{current:rev,revisions:[rev,…]}}}`. compare and update
under that lock. repeated operations are idempotent. a failed publication leaves the
old catalog usable. every lookup, including raw bytes, checks current membership. withdrawal closes the
links immediately. private immutable exports and git source remain on disk.

resolve `/` and latest links once to a pinned URL using browser history. an empty
home offers the composer. an unpublished link says “this page is no longer available.”
on the next successful visibility check, remove a withdrawn frame from an open tab.
show that state in place. changing the latest revision never moves an open reader.
only the sending document arms auto-open. match its submission receipt's canonical
id to `present.request_id`, including when the presentation arrives first. manual
navigation or a later send disarms it. a historical link never claims focus.

**published data.** the owner selected dated snapshots. a custom chart labels when
jarvis prepared its data. republishing updates it. the sidebar always reads current
todos and decisions.

the shell owns real files, chat and decisions. published html runs in an opaque-origin
iframe with `sandbox="allow-scripts"`. apply the same restrictions on direct raw reads
via the response header below. the shell forbids framing. only trusted shell controls
may send, approve or discuss. [browser sandbox](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/sandbox)

```http
Content-Security-Policy: sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'
```

## alerts, ingress and cutover

in the transaction creating a visible final, public terminal failure, control
acknowledgement or new awaiting-approval action, insert a `home_notice`.
columns are `id uuid primary key`, `kind text not null`, unique nullable `message_id`
and `action_id` fks, `created_at timestamptz not null` and nullable `discord_message_id text`.
check that `reply` and `question` have only a message fk, `approval` only an action fk.
derive id from kind and target. a question final issues one decision
notice. a distinct approval and final earn one each. progress and silent outputs
issue none. the existing delivery task drains on startup, commit and retry. pass the
notice uuid through `discord_nonce` for its existing 20-character enforced nonce.
store the returned discord id only on the notice. no historical backfill.

send “jarvis replied” with `/m/…` or “jarvis needs a decision” with `/d/…`, without
mentions or link previews. outage leaves alerts pending and the web usable. a lost
ack retried beyond discord's deduplication window can duplicate the phone alert.
[discord create message](https://docs.discord.com/developers/resources/message#create-message)

protect the entire hostname with cloudflare access, google-only login and an allow
rule for the exact owner email. require `access.required`, `teamName` and this app's
`audTag` on the dedicated tunnel route. deny unmatched hosts. only the connector can
open the jarvis unix socket (private directory/group). requests need no bearer
token in client code. check exact public `Origin` on writes, disable cross-origin
api reads, bypass edge caching and send `private, no-store`. api fetches use
`redirect:"manual"`. on an opaque redirect or 401/403, offer top-level login back to
the exact URL. on outage, show last successful read and retry. never expose memory,
credentials or a public origin port. [cloudflare connector](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/)
· [google identity](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/)
· [fetch redirects](https://fetch.spec.whatwg.org/#concept-filtered-response-opaque-redirect)

one stopped cut follows isolated proof. use the old release to acknowledge the final
discord `pause`. settle its full-text outbox, pending discord file captures and
incompatible native seals/actions under their original contracts. verify the
snapshot, control, effect receipts, archive positions, originals, work and google
cursors. stop both writers. retain both migration locks. change `0016`'s environment
lookup for the existing pause check to `JARVIS_OWNER_SCOPE`. for a fresh database,
provision the memory role and migrate to `0015`. the new release's `initialize-state`
must check that exact revision and an empty message table under deployment ownership,
then use `initialize_paused` once. its bootstrap check replaces the runtime head check
in that command. migrate `0016→0017` with both writers stopped and the same recorded
pause. ordinary upgrades start at `0016` and retain existing control and history.

remove the gateway sdk/fork, intents, typing, catch-up, discord intake/download
and full-transcript outbox/index. retain historical decoders and only the REST
sender's channel and credential. start the same-release memory and application units.
the first authenticated web `resume` is canonical. during an ingress outage an
operator can stop `jarvis.service` using existing deployment access. keep it stopped
until ingress is repaired. restart observes the recorded control and reconciles
entered effects. a process stop neither creates a pause nor recalls an entered effect.

## ownership and proof

one integrator (a) fixes the shared interfaces first and owns migrations and service wiring. b owns http
routes and calls c's upload reader and d's catalog reader. e owns operating-system
configuration and installation, d owns the publisher. b–e can then proceed in
parallel. each designer writes examples and failure copy within the unit's schema
before its first red test. each unit gets independent adversarial opus review.
use temporary failing end-to-end/live tests at real boundaries, implement, pass,
refactor to the repository's house style and rerun. delete only these probes.
keep evidence and existing regression groups. all five units ship in one cut.

| unit and files | designer's acceptance | required proof |
| --- | --- | --- |
| a. conversation — `db.py`, `0016/0017`, `messages.py`, `actions.py`, `service.py`, `cli.py`, `settings.py`, `native_*.py`, `terminal.py`, `input_framing.py`, `definitions.py`, `session-compatibility.json`, memory config and package pins | “received”, a question and a confirmed result mean different things. show one question per decision. | real postgres and native runtime. concurrent replay, changed bytes, pause/restart, a delegated result after its owner request completed, a stopped parent, unrelated wake, stable archive identity, one effect, opening/schema fit including the 16 kib instruction ceiling. |
| b. browser and read api — new `home_http.py` and packaged `static/home/`. reuse `work.py` and captured action arguments. | keyboard and phone navigation preserve place. name the affected person or object. show useful empty, stale, signed-out and offline states. | real desktop/phone browsers, two tabs, deep links, lost receipt, all five consent-bearing tools, a settled decision, safe text rendering, exact pdf on the owner’s phone and desktop. |
| c. originals — `attachments.py`, `attachment_sources.py`, `attachment_tools.py` and upload reader | identify the actual file, capture state and pdf page. print the original. | captionless upload, duplicate names, size limit, changed bytes vs changed mime hint, restart before and after put, original digest, deletion and active-type downloads. |
| d. canvas — `home_pages.py` and `deploy/jarvis-page` | an assembly viewer names the moving part and units. two designs can be compared on a phone. keyboard controls work. | real native uid/umask. two revisions, concurrent/failed publish, change home with tabs open, withdrawal, republish one revision, direct and framed isolation. |
| e. alerts and installation — send-only `discord.py`, `deploy/` units/install/verify and operations docs | one discreet line opens the exact reply or decision, including after it is settled. | recent lost REST ack, discord outage, access expiry, wrong account, protected raw/files, installed upload limit, socket ownership, cold bootstrap and populated migration. |

**installed journey.** from a discord alert on a signed-out phone, sign in, open
and print an original pdf. send a captionless photo. interrupt a chat send and
recover one copy. request a viewer then a comparison. keep another tab on its pdf.
open two pinned revisions, withdraw the work, and verify both links close. answer a
real decision on the web and inspect the receipt and its alert. verify zero discord
intake, stable memory coverage and readiness after restart. record source, candidate
and installed outcomes separately. production mutation needs its own authorization.

**design review.** conversation, canvas and browser designers reviewed the boundaries.
after two rounds of corrections against `ae487ca`, claude opus 5.5 accepted the
snapshot design for implementation. runtime and installed proofs belong to delivery.

## implementation evidence

the branch starts at `ae487ca`. the following checks used isolated fixtures.

- **conversation and notices.** postgres 16 with the runtime role accepted concurrent
  equal submissions once. reusing the id with different text returned a conflict. one
  control generated one acknowledgement and notice. a real http sink created an alert,
  then closed the connection before acknowledging it. the bounded rest retry reused the
  nonce. the web committed a second control during the outage. recovery delivered both
  distinct alerts with their exact links and no mentions or previews.
- **migration.** a fresh database advanced to `0015`, recorded its initial pause and
  reached `0017`. a populated `0016` fixture refused both a held memory writer and an
  undelivered predecessor reply. after settlement the migration preserved every original
  message field and produced zero historical notices. the runtime role cannot update
  either the new reference metadata or historical discord message ids.

- **web.** real chromium and mobile-sized webkit exercised two tabs, pinned revisions,
  withdrawal, keyboard navigation, lost receipts, signed-out return and pdf page selection.
  a duplicated tab formerly cleared a different draft on conflict. granting an id at send
  and preserving the conflicting draft fixed it. postgres verified all five consent
  projections, a settled question, a retired argument shape and the 50-message boundary.
  phone-sized webkit exercised the native-print link. the physical print is still open.
  chrome 157 reproduced a chat citation opening `/collection_(east` (404). after
  repair, clicking it loaded the evidence at `/collection_(east)`. ordinary, nested,
  adjacent and escaped links reached their exact destinations. attachment links and
  literal message text survived. the temporary browser probe was deleted.
- **originals.** postgres 16 and a disposable s3-compatible server received captionless
  files with duplicate names. changed mime hints replayed and changed bytes conflicted.
  the parser rejected a streamed body one byte over 90 mib despite its claimed length.
  interrupting the process after the put produced one stored original across restart.
  a missing committed spool failed visibly, transient reads left the row pending, and
  a stuck row allowed its sibling to finish. a deletion returned 410 while a reader
  already holding the descriptor finished. linux verified the digest and 0640 cache
  under the real user/group boundary. retry staging can consume space until the next
  exclusive startup. unrecognized formats, including heic, download as originals.
- **publication.** 80 concurrent operations on two works retained both revision sets.
  interrupting publication after the export and before catalog replacement left the old
  home intact. exact retry succeeded. withdrawal closed both revision links, and deliberate
  republication reopened only the selected revision. stock codex 0.160.0 on linux,
  under the native sandbox and umask 0077, published
  `29a50ac231da03787b19c6b402dc3d719b201567` in a disposable notes checkout.
  the application identity read the 0640 catalog. the shell, native validation and
  publisher all use the same installed notes root.
- **delivery boundaries.** a first web send previously returned 500 after its receipt
  committed when archive publication failed. the committed send now returns 201 and
  equal replay returns its id. archive projection follows on the worker. a real 429
  with a 90-second retry horizon formerly retried in two seconds. it now observes
  that horizon. a permanent channel rejection leaves its notice pending, logs the
  status and backs off for one minute. an outage preserves notification order.
- **installation rehearsal.** a stopped linux postgres 16.16 database was dumped,
  restored and migrated. the cut refused a synthetic initializer as the final owner
  pause. repeated preparation checked the same state. an independent cold bootstrap
  under the application uid refused a second initialization. the pinned 2026.10.4
  connector validated its generated rule, matched the private socket and rejected an
  unrelated hostname. these checks used disposable resources. [production cut](#production-cut-2026-11-19-utc)

- **native conversation.** opening, steer and replay kept owner speech apart from its
  typed object. a descendant could present an already completed owner's result.
  stopped or unrelated lineages and unavailable objects kept their valid replies with
  no automatic navigation. two inputs waiting on one question produced one decision,
  and a later wait left the old link settled. repeating archive projection added zero
  duplicates after 62 new fixture records. historical message digests stayed identical.
- **native wire format.** the integrated app unexpectedly completed an explicit
  request in silence. the first isolated probe had sorted the output schema's
  properties. the native service sends them in declaration order. using the captured
  input, model and resolver, changing only the order to put the response type first
  changed silence to an answer with the requested canonical id and revision.
  v12 rotates the main fingerprint because the canonical schema digest ignores order.
  48 tools fit. the longest supported zone used 16,334 of 16,384 instruction bytes.
  the output schema used 6,088 of 32,768. changing instructions requires remeasuring.
- **operator rehearsal.** native linux authoring failed when only the stock codex
  executable was installed. the matching 0.160.0 helper enabled the same stock
  session to issue native file and shell operations. an isolated x86-64 installation
  qualified fresh install, missing-helper repair and a warm run without a download.
  the production binary's dedicated directory was root-owned, mode 0755, on the
  read-only preflight. installing the pair is part of the authorized stopped cut.

### authored pages

stock main wrote, committed and published a mechanical vise viewer at
`4cc89b9cc71b137a3358f3ff711aaea472c2def7` in disposable private notes. the
dated viewer named the moving jaw, displayed travel in millimetres, and responded
to the keyboard in 0.25 mm increments. v12 then authored the comparison at
`dc2a48b5b076c52036ffa53d6271e5b4f23949e1` and selected it as home. its visible final
named that exact revision and the supplied synthetic request id. desktop chromium and mobile-sized webkit rendered both pins inside the production iframe
policy. eight turns gave 16 and 12 mm of travel. sixteen turns gave 32 and 24 mm.
both engines kept the page within the viewport and made zero external requests.
the clean interaction produced zero browser or content-policy errors.

### combined candidate, 2026-11-19 utc

two isolated linux runs exercised normal application and memory entry points, postgres
16 at `0017`, stock codex 0.160.0 on the personal subscription, s3-compatible originals
and an https notification receiver. the first observed the unmodified native socket
traffic. the second used the direct socket at `05849c6`.

- a captionless png/pdf submission returned 201, equal replay 200 and changed bytes
  409. the browser retrieved the original bytes. after web resume, stock returned
  the exact requested revision for owner input `73bc7a51-7766-4602-b4a2-d59306148d87`.
  reply `9398d72e-435d-5b2e-b577-629f15218654` opened it only in the sending tab.
  a second tab retained its pdf and draft. withdrawal closed both revision links.
- the decision linked to `37e8eb07-1530-44fb-8fd4-73b1b212b7c2` showed the actual
  filename and remained readable after settlement. the exact owner answer authorized
  one delete executor entry. the image returned 410 and the retained pdf returned 200.
  five committed notices matched five private posts to the isolated receiver.
- stopping the application under its canonical pause yielded 503 while the independent
  memory unit still answered 200. the direct run's before/after snapshot digest was
  `d1e54a60ba3f2f5a4f8437602828a5e01abf05897b94ba950ffc28fc4428f205`.
  it retained receipts, scope, archive identity, originals and the pause. all 17
  admitted memory leaves remained, with 15 in the ready view. replay after deletion
  returned the original id. a fresh native request read words supplied only by the
  retained pdf and cited its page and original id. an earlier provider-capacity
  failure parked inputs with zero executor entries and preserved the undecided action.
- the repository build, clean wheel install, lint, typing and documentation checks
  passed. the retained jarvis capture/retry check and all four checks from the pinned
  memory dependency passed against disposable postgres. the dependency audit had no
  known findings. its public index cannot assess the three private git packages.

independent opus 5.5 reviews accepted all five units at the source and candidate
boundaries. the temporary probes and isolated services were removed after the final
checks. the retained regression groups remain in their owning repositories.

### production cut, 2026-11-19 utc

the owner observed cloudflare denying the other account. the access audit recorded
google admitting the owner. signed-out home, raw content and original-file routes
challenged through the same access application and preserved their return paths. the zone accepts
100 mb and bypasses shared caching for this hostname.

discord pause 17 drained at `0016`. rehearsal from its private postgres dump
rejected two retired discord sender settings. release `9b96667` removes them in
both the stopped conversion and the private installer. both paths passed their
configuration probes and independent opus review. a fresh restore migrated and
passed runtime activation with zero incompatible or in-flight actions. both
snapshots matched on all 18 original table inventories and both private copies.
the installed migration verified those inventories again at `0017`, before
either writer restarted. selected dump sha256
`62c92c7d0a8e2effea6e168156a8c1da44e8568538a75290e883271e426c9fe4`.

assistant and memory started on that release under the same pause. the connector
identity fetched the retained 125,791-byte pdf over its private socket with the original sha256. the native memory
client reopened a pre-cut owner record and read all nine pages of its frozen
view, covering 2,978 of 26,726 admitted leaves. containment passed on macbook
and dev-server with arch unavailable. the workstation declaration matches the
installed owner identities and credentials. the bot's message-content intent is
off. the owner sent `resume` in discord after cutover. zero owner messages from
discord were admitted after the new service became active. the subsequent web
`resume` at 16:47 utc committed as control 18, input `8bdbb816-4b89-481f-a632-6e75f7fdc914`.
its canonical reply `6b144c91-50d7-5896-acaf-b7a82587247b` produced one notice
with a discord message receipt. a later web request for the pdf produced a final
reply referencing the retained original. all eight reply notices had discord receipts.

### owner acceptance and closeout, 2026-11-20 utc

the owner accepted the installed web home and requested closure. the physical
print and interrupted-send retry have no separate production receipt. captionless
uploads, two-tab revision withdrawal and a conversational approval carry their
candidate proofs. production had zero web-upload rows and zero decision notices
at closeout. the source and installed evidence above retain those boundaries.

the selected recovery dump passed its sha256 and a full archive read. both private
copies matched their recorded hashes. across both snapshots, the original 18 table
inventories, owner scope, pause and private-copy hashes matched. the superseded
`344abf9` rehearsal snapshot was removed and the selected copy was checked again.
[adr 0105](0105-native-android.md#installed-phone-follow-up-on-november-24-utc) records later discord retirement.

final review found that cancelling an automatic action could make its id look like
an approval. release `95423ff` requires an open approval, a proposal message or
notice, a recorded wait for approval, or a successful approval response. historical
cancellations with only a timestamp do not qualify. no installed row depended on
the timestamp alone. thirteen action histories passed both detail lookup and chat
reference submission against disposable postgres. the open list and independent
opus review passed. the same-schema replacement preserved web resume 18. the
installed reader excluded a real automatic action, served chat and decisions,
and the memory service reopened a pre-cut owner record.

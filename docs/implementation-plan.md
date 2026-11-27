# jarvis: roadmap and implementation plan

updated 2026-11-16; simple event-driven v2 adopted by
[adr 0071](decisions/0071-simple-event-driven-v2.md), with three finishing review
units adopted by [adr 0075](decisions/0075-v2-completion-and-subscription-model.md).
shared memory remains a separate delivery. the selected scope, pending specs,
qualified source and later work are distinguished below.
this is the ONE active feature roadmap and delivery plan. native cognition and
worker control are implemented foundations; the remaining product direction and
operational cutovers are distinguished below. a roadmap entry authorizes no
runtime change, release, deployment or resumption.

[one main and workspace recovery](decisions/0132-one-main.md) has a source
candidate. units a–c own cognition, connector effects and workspace blockers.
unit d composes them, migrates the predecessor and qualifies the matched
clients. the november 27 controlled rehearsals covered one-main admission,
blocked work and intake recovery, the `0029` migration, a readable encrypted
backup and the signed android upgrade in an emulator. the owner waived
physical handset checks. the [live draft discard failure](issues/google-workspace-mcp.md)
holds activation. production still runs `0028`. the selected-release journeys
for native routes and gmail intake remain pending. implementation evidence
and cleanup receipts are under
`~/.local/state/jarvis/qualification/adr0132-one-main-implementation/` on macbook.

on november 27 independent opus 5.5 passed all four design units on spec blob
`fb65225d0fa4021550896d361dca62d621dc6062` after closing nine initial findings,
the 0118 presentation conflict and the batched-read resume ambiguity. the
reopened review rounds, final spec and sha256 manifest are on macbook under
`~/.local/state/jarvis/qualification/adr0132-one-main-design/fb65225/`.

[the daybook](decisions/0127-the-daybook.md) owns the web and android chat
typography, inline phone draft and message-bearing send receipts.
[installed acceptance](decisions/0127-the-daybook.md#installed-acceptance) records the web and android
release pair and handset journey.

[native antigravity design 0111](decisions/0111-native-antigravity-neon.md) selects the official sdk for the second main route, with fresh children, next-turn follow-ups and an offline shell. the provider, kernel, jarvis routing and recovery, and isolated linux release composition passed synthetic checks. the owner deferred the paid trial. production activation requires a separate cut. [qualification evidence](issues/agy-native-parity.md#release-qualification).

[automatic foreground recovery 0114](decisions/0114-automatic-foreground-recovery.md)
has [source and detached qualification](decisions/0114-automatic-foreground-recovery.md#source-qualification)
at `a922811/0025`. installed recovery precedes separately authorized historical
disposition.

[direct google quota recovery](decisions/0110-neon-quota-recovery.md) reconciles the 0108/0109 standby branch with the merged 0107 workspace contract. the adr assigns four feature owners, their designer specimens, temporary red/green/refactor proof and the historical release. qualify the stock-to-google transport and data eligibility before real paid routing. opus 5.5 passed the design on november 25 (adr sha-256 `955fbf068b3ac515c47605cf5b0ddeeb319727318cd6484100f2dab1e2706e94`). the owner later approved translating interleaved trusted instructions into google’s system channel with source positions. a fresh personal opening leaves inputs owned by a safe, pinned neon continuation alone. [open live qualification](issues/neon-live-qualification.md)

[SPEC.md](../SPEC.md) remains normative. the
[universal-memory contract](universal-memory.md) supplies its accepted schemas,
apis, bounds and acceptance. adr 0071 adopts the selected v2 feature contracts;
adr 0075 adds focused mail/calendar/web reads, reliability/integration and the
subscription model/runtime target. broader search, dreamer context and budget
remain separately scoped.
[operations](operations.md) owns deployment and
repair. [adrs](decisions/README.md) preserve rationale; retired delivery checklists,
qualification reports and completed cleanup logs live in git history.

[adr 0104](decisions/0104-maintenance-without-owner-pause.md) owns named deployment
custody, stopped work compatibility and adoption through existing commands.
implementation starts from the verified installed `ea2b825` composition, which
already includes main's chat-order fix. installed acceptance requires its own cut.

[adr 0094](decisions/0094-worker-tools-and-native-context.md) builds on the
committed adr 0093 candidate. qualify existing worker behavior independently,
then the typed provider seal, jarvis settlement and the combined live journey.
on 2026-11-20, claude opus 5.5 passed both designs at spec sha256
`6fec2a248511e6bbfb93e7e97d62164293f5d005877e02264705716849438d7d`.
the accepted text was amended after review to record the reproduced late-seal and opening-framing defects.
the adr records source and isolated macbook qualification, with the installed cut separate.

[adr 0095](decisions/0095-context-cost.md) assigns mail, native steering,
shared orientation and schema publication to separate owners. freeze the
selected adr 0093/0094 base, qualify each unit against it, then qualify one
integrated hard cut. native field references and the smaller shared view have
explicit evidence gates. on 2026-11-20 independent claude opus 5.5 passed all
four designs and the cut at spec sha256
`46445c60bd81b086644bee2fcfc5bc9680a4f442d7c519bbac4d38f298814651`.
the [implementation evidence](decisions/0095-context-cost.md#implementation-evidence)
records all four source units, the b–d candidate and mail's authenticated
google check. production activation remains separate.

[adr 0096](decisions/0096-calendar-on-demand.md) assigns calendar and gmail
source changes to one owner and background reply behavior to another. integrate
both against the selected schema, main manifest and home transport. on
2026-11-22 independent claude opus 5.5 passed both designs and the stopped cut
at spec sha256 `179dd9956107a5549574131cadcf1e7a8752db72d779fac70d255c978414706b`.
the predecessor can still send a message while draining its calendar queue.
the implementation and isolated qualification are recorded in
[0096 evidence](decisions/0096-calendar-on-demand.md#implementation-evidence).
the [live calendar check](decisions/0096-calendar-on-demand.md#live-google-calendar) passed. production selected `43ed919/0019`, and gmail polled after owner resume 32. [installed cut](decisions/0096-calendar-on-demand.md#installed-calendar-cut)

## skid worker placement

[adr 0114](decisions/0114-skid-worker-placement.md) specifies the v14 cut from
the v13 worker binding. source and the paired macbook candidate are qualified.
the installed cut committed on schema `0025`. the restricted fleet checks and
the scoped owner-interface desktop assignment passed, including the exact
reply and acknowledgement.

1. **skid cli.** add the id selector to start parsing, help and fleet-client
   routing. use the existing machine-handle parser, peer lookup and start
   operation. prove a label that spells another computer's id still selects
   by name with `--machine` and by identity with `--machine-id`.
2. **jarvis worker binding.** remove the enum across tool inputs, wire decoders
   and result projections. move target resolution from the observer to write
   admission. reuse the private action contract for start, fresh assignment
   and `after`. enforce the same causal scope as answer reads for follow-ups.
   update start receipt validation, action recovery, historical
   receipt reads, retirement checks and the deployment verifier. publish the
   revised catalog and binding together.
3. **prove the paired artifacts on macbook.** use dev-server's
   `scripts/rehearse-worktree` for the detached rehearsal. exercise the real
   cli, worker action store and restart path against a temporary enrolled fleet.
   retain named evidence outside scratch, reopen and hash it, and record
   fixture teardown separately.

   | exercise | evidence required |
   | --- | --- |
   | add a fifth, offline peer with an unseen name | the two required hosts remain readable. the fifth is present with its error. the service verifier succeeds, then fails when a required host is missing or down |
   | request an absent name, then enroll it. separately inject an ambiguous status reply, a malformed reply and a status outage | the original unknown-name request stays rejected. the ambiguous reply reports ambiguity. malformed and unreadable replies report roster unavailable. each leaves zero worker actions and zero dispatches |
   | accept a job for a, move its name to b, restart before dispatch. lose the submit reply and restart after result commit before ack | a receives the original job uuid. b receives zero job calls. recovery, result paging and ack address a. exactly one wake commits for the original job |
   | accept a start for a, then rename or remove a before execution | rename permits one start on a and its new label in the receipt. removal sends nothing to b. a lost reply or wrong machine id stays uncertain and causes zero repeat starts |
   | name a prior job from another causal component in the same conversation | registration rejects it before insertion. a related job uses the original handle even after a rename |
   | request an unsupported profile on an enrolled host | skid's refusal reaches jarvis for the selected host. no alternate host or profile runs the brief |
   | retire v13 with a completed job awaiting ack | preflight and startup both hold the cut. settle under v13, reopen v12 and v13 public receipts, and page an answer over 8 kib byte-for-byte. the private ref stays private |

4. **release and verify.** publish and pin the qualified skid cli. under the
   existing named maintenance procedure, confirm the selected artifacts, drain
   incompatible worker obligations under their owning release and
   check the stopped source. activate v14 and the verified cli together through
   the existing operator-workstation `deploy/activate-release` path with its
   `--agent-client` manifest.
   return to the source release only when custody and source activation checks
   establish a safe return. otherwise keep the hold. after new effects,
   reconcile or repair forward. verify existing required workers through the
   restricted jarvis service identity. list desktop from jarvis, then run one
   scoped assignment on an applied
   desktop profile, read its answer and confirm its acknowledgement. observe
   an offline desktop as a partial inventory with required hosts still healthy.
   record the two artifact identities, source proof, installed observations and
   cleanup separately. [deployment procedure](operations.md#skid-only-worker-cutover)

## terminal-only worker cutover — source implemented and isolated-qualified

[adr 0069](decisions/0069-terminal-only-workers.md) and the linked skid spec
own terminal-only worker control, closed schemas and opaque retired-row loading.
[adr 0072](decisions/0072-native-memory-rollout.md) advances the binding to v10
and adopts enrolled `macbook|dev-server|arch` names without aliases; memory's
`devbox` identity stays unchanged. fourteen actual cli/postgres checks pass.
the read-only mounted state boundary and actual installed service-uid reads pass
on both online hosts; [installed evidence](universal-memory.md#native-memory-installed-qualification)
does not replace the separate worker observation journey.

[adr 0089](decisions/0089-native-capture-repair.md) owns the independent native
collector cut and its installed recovery evidence. the [claude reader repair](claude-data-flow-capture.md)
owns the november 23 metadata parks and their recovery before the v4 worker cut.
the [codex rewind repair](codex-history-recovery.md) follows historical
archive cleanup. the [installed recovery](codex-history-recovery.md#installed-closure) passed at schema `0022`.

[adr 0105](decisions/0105-native-android.md) owns the android and discord cut.
qualify access and the release signer first. handset, linked results and push
use their frozen interfaces in parallel. the final integration composes the
new schema and both clients against the selected predecessor. the
[installed handoff](issues/mobile-share-handoff.md) records the verified phone journey, backup restores, discord retirement and remaining handset checks.

## destination and rules

one visible jarvis remembers context, keeps useful working records and carries
ordinary work forward across personal, scientific, creative and practical life.
one undivided memory serves all admitted/connected machines and profiles. the
owner should not have to repeat context or repeatedly initiate obvious follow-up.

- agents receive context, tools, goals and quality constraints; they choose their
  method. delegation and retrieval guidance are prompt defaults, not mandatory
  tool sequences, a routing engine or a prescribed agent organization.
- policy is global: shared constants/configuration have one owner; callers reuse
  clients, pools, admission, search, append functions and validators. preserve
  subject-specific provenance/permissions/progress and fresh invocation state.
- provider-runtime owns native transport; the kernel supervises cognition;
  llm-tools owns tool contracts/execution; jarvis owns product context, authority,
  persistence, events and continuation. dev-server owns fleet configuration;
  skid owns worker launch/control. reuse their existing public primitives.
- one main, one deployment lock and ordinary scheduling. no workflow framework,
  descendant graph, worker-consumption accounting, duplicate state ledger,
  speculative service, generic shell bridge or compatibility fallback.
- durable effects, canonical commits, truthful outcomes and deployment pause/shutdown remain
  host responsibilities. new background memory computation is disposable.
- hard-cut replaced paths, preserve canonical data, and state costs in the owning
  contract. distinguish source merged, dependency pinned, fleet installed, live
  behavior verified and owner-resumed service.

## google workspace access

[owner draft editor 0119](decisions/0119-owner-gmail-draft-editor.md) adopts
the exact revision reader from 0121. candidate `b23c185` passed the detached
chrome journey against the actual home server, postgres and controlled gmail,
26 browser cases, and the android debug build and emulator journey. opus
passed the final candidate. the stopped restore procedure and immutable
historical routes passed separately. the [live issue](issues/owner-gmail-editor-live.md)
tracks real gmail, the physical phone and installed acceptance.

[workspace connector design](decisions/0107-google-workspace.md) splits the february 2027 google cut into a synthetic-data connector pr and a following [history-permission decision](issues/google-workspace-retention.md). keep ordinary history, fresh mail search/read, draft management, incoming mail and event creation, reading, editing and deletion. qualify [five-minute pending-label reception](issues/gmail-mcp-arrivals.md), the 1,000-unit foreground reserve and draft safety before full cutover. real-account rollout also waits for the history decision.

independent claude opus 5.5 passed the original design, its calendar and draft amendments, and the five-minute reception and quota amendment at sha256 `aa3862bc78b5b7174a309d8392f8430c1a8d3a110761a52522134c24e81d23f6`. the scoped reviews and verified rechecks are in `~/.local/state/jarvis/qualification/workspace-mcp-design/`. for temporary proof, cancel the consent round on native interruption or timeout, serialize workspace calls, and check that a match tap never acknowledges a nonexistent outbox row. measure raw attachment access and draft byte limits on the qualified server. prove the visible generic alert in actual android doze and an ordinary overnight sample. notification settings may suppress it, and repeated invisible high-priority pushes may affect delivery. accept best-effort delivery without adding a handset status service. inconclusive checks appear on the todo. the subscribed-model run is mandatory. missing google-hosted evidence holds installed acceptance.

## drive files

[adr 0120](decisions/0120-drive-files.md) implements the agent connector, file custody, owner viewer and stopped cut at schema `0027` with [0119's standard client](decisions/0119-owner-gmail-draft-editor.md). controlled qualification passed. [live qualification](issues/drive-files-live.md), [production activation](issues/drive-files-deploy.md) and [document backup](issues/drive-document-backup.md) remain open.

## private web home

[artifact library 0123](decisions/0123-artifact-library.md) implements the
library, pinned editions, recorded deliveries, and the stopped catalog cut.
the matched release combines drive and sidebar and rotates the viewer header
and main output once. [isolated proof](decisions/0123-artifact-library.md#implementation-evidence)
passed. the [named cut](operations.md#artifact-library-cut) and [installed
acceptance](issues/artifact-library-installed.md) are separate.

[inline todo viewer](decisions/0117-inline-todo-viewer.md) is implemented
for web and android. the isolated candidate passed. installed acceptance is
pending.

1. replace the existing todo collection page with the complete summary
   response. verify the new ordered snapshot and rejection of retired queries.
2. implement the web and android viewers against that contract. in the packaged
   web shell, remove the sidebar record pane, duplicate todos control, backlog
   fold and list pager. make ordinary rows disclosures and route exact links to
   the viewer. in android, reuse the overview list and the existing detail
   content in one scroll surface. preserve the calling visit when following a
   result to a previously visited message. both clients load details on demand.
3. exercise the adr’s four journeys on macbook with a real service, postgres,
   desktop and narrow browsers, then the android candidate on the handset.
   use isolated data. for a new detached rehearsal use dev-server’s
   `scripts/rehearse-worktree`, retain named evidence outside scratch, reopen
   and hash it, and record fixture cleanup separately.
4. coordinate the release of the complete collection read, packaged web shell
   and android apk in one maintenance window. have the updated apk ready
   before switching the service. reload open web tabs and update the handset
   before using todos. the change uses the current database schema. return
   the service and web shell together if rollback is needed. a handset that
   already updated needs a matching client installed as an in-place update
   with the same signer and a higher version code. keep todo use on hold
   until those artifacts match. record installed checks against the actual
   release identities.

[stable web home address](decisions/0115-web-home-address.md) keeps home and
todos at the bare domain. qualify its home, address and history behavior on
macbook. use 0117’s journeys for todo rows, exact todo links and return.

the owner conversation, browser, originals, authored canvas and notifications share
schema `0017`. [adr 0087](decisions/0087-private-web-home.md#implementation-evidence)
records the source, candidate and stopped `0017` production proofs. the owner
accepted the installed web home. [adr 0105](decisions/0105-native-android.md#installed-phone-follow-up-on-november-24-utc) records discord retirement.
[adr 0097](decisions/0097-todo-home.md) owns the independent todo home cut.
qualify the todo read and conversational proposals, then the integrated web shell.
on 2026-11-23 utc, independent claude opus 5.5 at max passed all three designs
and the cut at spec sha256 `fe949056736aba332b7a3fc449c253a7bf414946c560943dd68f1073cecd7a1a`.
the macbook receipt is `~/.local/state/jarvis/qualification/adr0097/design-fe949056.txt`.
source and isolated macbook qualification passed at `ed310a9` on schema `0019`,
composed with 0095 `bc47458` and 0096 `0639f73`. the packaged browser and https
journeys used the frozen wheel. authenticated stock proved the mixed answer and
consent question, one executor entry, prior consent and recovery of the original
mail proposal after parking. main v20 uses 15,994 of 16,384 instruction bytes
at the longest installed owner zone. independent opus 5.5 accepted source and evidence.
the macbook receipt is `~/.local/state/jarvis/qualification/adr0097-implementation/acceptance.json`,
sha256 `71551bec10b68e435c77aa354cfbe3c2a0958b98f92267e197bfc586895b586d`.
the sibling `cleanup.json`, sha256 `cbf8393ccbddc9c6a3ee66d0791afd14ac74e9389ad2c11d683f8076c95d3e20`,
records probe and fixture deletion. the [november 24 cleanup](decisions/0094-worker-tools-and-native-context.md#rehearsal-cleanup-on-november-24) confirmed removal of the intermediate checkout.
the [installed issue](issues/default-home-work.md) stays open through acceptance.
the [private android client](decisions/0105-native-android.md#installed-phone-follow-up-on-november-24-utc) handles sharing and push. iphone uses web access.

## chat sidebar and phone alerts

[adr 0122](decisions/0122-chat-sidebar-and-phone-alerts.md) records the matched
client and service change. the [installed check](issues/chat-sidebar-phone-alerts-installed.md)
remains open.

1. start from 0117's single viewer todos control. in the packaged web shell,
   remove the ordinary sidebar header, phone disclosure and their exclusive
   styles and handlers. keep one conditional back button on the existing
   history and focus path. exercise the adr's desktop and narrow return journeys.
2. in android's native home, replace the alerts screen and global warning
   with the inline enrollment and repair action. reuse the permission flow,
   firebase registration and slot readback in `Push.kt`. decouple address
   maintenance from channel muting. check fresh, denied and in-place upgrades.
3. once both clients have dropped manual disconnect, retire the delete handler
   in `home_http.py` and its branch in `phone.py`. exercise the adr's
   replacement, stale-address and old-client checks against an isolated slot.
4. for rollout, stage the packaged shell, service and same-signer android
   update. coordinate with the 0117 client/service cut if still pending.
   old tabs adopt the new shell on ordinary reload after any active draft is
   safe. an old client attempting disconnect receives 405. verify the upgraded
   handset retains enrollment and opens a real reply alert, and check the
   installed sidebar on wide and narrow web. record candidate and installed
   outcomes separately.

## new, shown and owed in chat

[adr 0125](decisions/0125-new-shown-and-owed.md) records the accepted design.
both cuts are installed. schema `0028` shares display receipts across the
web and android. the [installed acceptance](decisions/0125-new-shown-and-owed.md#installed-acceptance)
records the matched release and recovery check.

serialize both against the actual merges of
[0118](decisions/0118-chat-reading-and-approvals.md),
[0122](decisions/0122-chat-sidebar-and-phone-alerts.md),
[0123](decisions/0123-artifact-library.md) and
[0124](decisions/0124-citations-and-viewer-delivery.md). they own the same
transcript, sidebar, android list and client files. [0126](decisions/0126-presence.md)
shares the poll and movement paths and already owns the common owed query.
build on the landed reader and sidebar.

on november 26, independent claude opus 5.5 at high effort held the first
draft on eight findings, chiefly an owed rule that followed the latest
attempt, an undo that permanent receipts could not support, and a sweep that
cancelled unshown question alerts. it closed all eight on the revision and
set three conditions, applied as worded: failure notices and parked requests
are not owed, a retry is not owed until it asks again, and an owed message
outside the loaded pages opens by its exact link. it accepted the clean slate
at the second cut as a stated tradeoff. reviewed adr sha256
`de5336c452291d3ffdc1fb796e4a94649933f741692834ebf129e9ae21646350`. both
reviews and the frozen drafts are in
`~/.local/state/jarvis/qualification/adr0125-design/`. after review, the
owner approved scanning beyond the displayed pages for exact local totals
and using document focus for the web assistive-reading gate.

first cut, no schema:

1. witness the two opening faults on real clients before changing them:
   narrow web opening at the oldest loaded message, and android opening at
   the top of the newest fifty.
2. add `owed` and `owed_total` beside the items in `home_reads.py`. freeze
   the rule with examples for approval, owner input, a wait re-recorded by an
   unrelated wake, an answered question, a question with no wait, a parked
   request whose failure notice repeats the proposal, and a retry.
3. web: one new module under `static/home/` owns the shown set, the timing
   and the marks, backed by `localStorage`. wire it into the existing merge,
   message read and refresh paths. add the boundary, the ledge, the owed
   words, the `--rubric` token and the opening and arrival rules. fix
   narrow-web placement and scroll to the bottom on send.
4. android: give the conversation a list state anchored by message id,
   prepend earlier pages and read every three seconds while resumed. add the
   same set, timing, marks, boundary and ledge, backed by private
   preferences. in `Push.kt`, hold a notice while chat is on screen, group
   replies, keep questions separate and sweep on resume from the local set.
5. qualify journeys 1–11 against an isolated service. the owner waived
   dedicated physical sessions for the first cut. stage the packaged shell,
   service and same-signer android update together. check one real firebase
   tap during ordinary use. phone and laptop can disagree until the second cut.
6. record the installed smoke. on november 26 the owner waived the week of
   device-local use before permanent receipts.

second cut, stopped:

1. wait for the [drive files cut](issues/drive-files-deploy.md): schema
   `0027` must be installed first. then add `owner_shown` at the next free
   migration with its guarded grants and the `cutover` receipts. add the
   `Table` and move `APPLICATION_SCHEMA_REVISION` in `db.py`, extend
   `STOPPED_TABLE_KEYS` and `SCHEMA_REVISION` in `deploy/memory_snapshot.py`,
   and add a cut verifier. rehearse a restore on macbook.
2. add the page `new` set and `new_total`, `POST /api/shown`, clear through
   a message and the narrow hidden-tab read. set a new viewer contract value,
   serialized with any value 0123 sets.
3. replace the inside of each client's set module with the service contract
   and delete both local stores. android sweeps notifications from the page
   it was served. the web shell serves the three favicon files.
4. qualify journey 12 and repeat 1–11. stage service, shell and the signed
   app. the owner reads what is new first, because marks restart from the
   cut. close old clients, switch the service, update the phone and reload
   web before resuming use. record candidate and installed outcomes
   separately.

two follow-ups stay open and outside both cuts:
[stale phone alerts](issues/stale-phone-alerts.md) and
[crossed questions](issues/crossed-questions.md).

## chat composer attachments

[adr 0116](decisions/0116-chat-composer-attachments.md) owns the interaction,
draft recovery and acceptance criteria. both clients passed [source and isolated
acceptance](decisions/0116-chat-composer-attachments.md#implementation-evidence--november-26-2026).

use the normal web release and signed app update for delivery. record
one installed gesture-to-receipt check on each client. both use the existing
api and can be released independently.

## presence

[adr 0126](decisions/0126-presence.md) owns the states, words, motion and
acceptance and [candidate evidence](decisions/0126-presence.md#qualification-on-macbook).
adr 0125 (new, shown and owed) owns the red, favicon, arrival
announcements, hidden-tab reads and transcript movement that presence relies
on. presence is additive: no schema, prompt, model binding or stopped cut.
one writer per path. freeze the read specimens before client work.

1. **design review.** independent opus re-review of the corrected adr. fix
   findings before red.
2. **a · service.** new `src/jarvis/presence.py` (record and read),
   `service.py` (owns the record, clears the attempt), `native_runtime.py`
   (arming, the combined stock hook, `NativeRunOutcome.deferral`), `kernel.py`
   (last personal allowance), `write_dispatch.py` (effect entry and exit),
   `home_reads.py` (0125's owed query, if presence lands first), `cli.py`
   (wiring), `home_http.py` (route, etag). freeze json specimens for
   idle, owner work, a steered follow-up, silent mail work, an approved effect,
   owed, quota and non-quota standby, paused and workers. prove acceptance 1 on
   macbook against postgres 16 with temporary probes.
3. **b · web.** `static/home/{index.html,home.js,home-dom.js,home.css}` and
   `static/home/fonts/` (cormorant garamond regular and italic, latin subset,
   ofl). make `refresh()` read presence before chat. build against the frozen
   specimens and a stub, then the real service. prove acceptance 2.
4. **c · android.** `Home.kt` (header, after-send route, tail), `HomeApi.kt`,
   a `Presence.kt` for the mark and poller, and `res/font`. prove acceptance 3
   on an emulator, then the S22+.
5. **integration.** rebase on whichever of 0123, 0124 and 0125 lands first.
   they own the destinations, viewer and transcript paths that b and c attach
   to. the rule legend anchors to the header bar, not the wordmark, so wrapped
   destinations need no special case. if 0125 has not landed, define
   `--rubric` with its values. run `scripts/verify` and opus review of the
   evidence, then delete probes and record cleanup.
6. **release.** normal service release, which carries the web shell, and a
   signed app update with a higher version code. either may lead: an old client
   never reads presence, and a new client treats 404 as unknown. record the
   installed journeys in `docs/issues/presence-installed.md` until observed.

## exact draft revisions from chat

apply [adr 0121](decisions/0121-exact-chat-draft-revisions.md) to the later mail
presentation cut. integrate the revision controls with the matching chat
projection before staging the service, browser shell and signed app. repeat
the stopped mail inventory and record the
[remaining acceptance](issues/chat-draft-revision-inspection.md).

## full answers in web chat

[adr 0124](decisions/0124-citations-and-viewer-delivery.md) owns evidence
inspection, full-width tables and work delivery. its reading prerequisite
ships with this slice. use 0120 for verified downloadable files. use
0122's contextual back and 0123's passive edition links on their matched
cuts. 0119's production editor enrollment is tracked independently.
the [installed and live check](issues/citation-viewer-live.md) records the
remaining account, provider and signed phone work.
the [controlled candidate record](decisions/0124-citations-and-viewer-delivery.md#implementation-evidence)
binds the code, receipts, opus closure and fixture removal.

the selected artifacts determine the release order. finish the stopped drive
cut in #129 first, or repeat its migration, custody and client proof on the
exact combined release. drain incompatible outputs on the original selected
release before switching. preserve the installed and candidate request name,
output name and schema digest, prepared prompt and schema digests, main
revision and client contract. a reused name with different bytes holds the
cut. use one matched viewer contract for chat, evidence, file submission and
the artifact library. the v4/v7 or v30 identities from independent candidates
cannot name the combined release.

[chat reading and approvals](decisions/0118-chat-reading-and-approvals.md)
delivered its reading slice through 0124 and the daybook. [0132 unit c](decisions/0132-one-main.md#c-workspace-blockers-and-attended-recovery)
owns the remaining decision-card and google-permission surfaces in the one
matched viewer cut. old proposal cards follow their historical receipts.
include an uncertain action followed by a late verified acknowledgement.
noncanonical internal links, including uppercase ids, display as text.
the [draft revision reader](decisions/0121-exact-chat-draft-revisions.md) is
source-qualified. the [matched installation](issues/chat-draft-revision-inspection.md)
remains pending.

on november 26, independent claude opus 5.5 at high effort passed the revised
design at sha256 `d1eb74b7341d43d21cb6bc496bf92f0bd09a7f6ebcb2b67547aa2c5b7eb9cf22`.
the first review held six points covering mail handoff and proof, html and
link parity, receipt labels and android dismissal. the final review closed
all six. both reviews are under `~/.local/state/jarvis/qualification/adr0118-chat-design/`.

[adr 0091](decisions/0091-source-backed-reports.md#implementation-evidence)
records the qualified source and isolated stock candidate. it removes the old
final-reply limit and preserves reading position on direct message links.
installed acceptance remains separate.
independent opus 5.5 at max accepted the revised design on web-chat main
`c9a9c67`, spec sha256 `f3c2e3e73cbf329ea5a8f8548f36913768d46089178072fe9f3626ad636d9e39`.

## storage and central memory recovery

[adr 0088](decisions/0088-storage-and-memory-recovery.md) owns the independent
mac rehearsal workflow, host capacity signal and jarvis backup/restore units.
deliver against the installed memory baseline. qualify the first isolated
off-host restore before enabling the recurring job. the source and isolated
journeys passed, and local disk sampling is installed. the first production recovery and
[seven scheduled backups](decisions/0088-storage-and-memory-recovery.md#scheduled-production-backups) are verified.

## shared memory freshness

[adr 0098](decisions/0098-conversation-capture.md) specifies the prospective
capture cut. freeze the source and storage contracts, qualify native conversation
capture, main built-in observations and nexus exports, then integrate on the
actual collector and service pins. installation and the
[historical cleanup](decisions/0102-historical-capture-cleanup.md) ship in order. the latter scans all records at deployment after the v4 filter is active. the
macbook claude data-flow preflight identified four parked top-level chats and
30 child/workflow sessions. reconcile these by proven identity at the cut.
[installed verification](claude-data-flow-capture.md#installed-verification) subsequently closed all 39 cases, including the four roots.

the owner selected the 30,000-character cap on new built-in call arguments.
independent claude opus 5.5 at max passed that design at sha256
`d24004728e6765ee420f4d5a3844e212675d9c270d5e13d043168f337d9b3bfa`.
the design at handoff includes the reviewer’s clarification that the closed readers
expose call and result fields, sha256
`e4db88b0d88c38425eac143019d63ca2504196c1761db632df38ae4f02aefd71`.
the macbook receipt is `~/.local/state/jarvis/qualification/adr0098/final-readback.md`,
sha256 `58b03df1c794044ea1664541807cf2b1610b48a52ee68d554c5f838d3da54de8`.

[adr 0092](decisions/0092-memory-freshness.md#installed-cut) records the
separate `0018` release for the startup view and service-owned indexing.
historical capacity and genuine installed recall earn separate evidence.

[adr 0100](decisions/0100-host-bound-summary-fields.md) owns the compactor form
and single batch correction. its current-main candidate follows the separate
`0020` capture rollout and [archive rewrite](decisions/0102-historical-capture-cleanup.md).
the old `8232+8` replay is retired. the armed november 24–25 samples keep their
actual generation. [installed writer progress and blinded recall](decisions/0100-host-bound-summary-fields.md#installed-writer-recovery) passed. [overnight capacity](issues/memory-usefulness-evaluation.md#installed-terra-observation) is still under observation.

[adr 0101](decisions/0101-outgoing-mail-attachments.md) owns outgoing gmail files. integrate file intake, draft revisions and approved send in that order. three content designers supplied the feature contracts. independent claude opus 5.5 at max effort passed the design at sha256 `20f4beb484dd0a6a90e54879980a8a90dd81ec62bae87cb2e8dd8a9e564db97b`. the macbook receipt is `~/.local/state/jarvis/qualification/adr0101/design-20f4beb484dd.txt`, sha256 `c1ec88e4d51fb066618f46d3ebc809947c6992a17847276b47f3750d0922deca`.

source and the detached macbook rehearsal passed. the isolated candidate passed
the actual phone upload, approval, approved-content send during a gmail edit,
and 25,000,000-byte self-bcc reply with lost-ack recovery. the adr records
scanner and service measurements. the [production cut and installed smoke](decisions/0101-outgoing-mail-attachments.md#production-cut)
passed on schema `0022` after adr 0103.

## subscription model refresh

[adr 0093](decisions/0093-subscription-model-refresh.md) sequences provider
qualification, role selection and startup recovery, then the isolated release
build and upgrade rehearsal. the delivery boundary is a cutover-ready
candidate at schema `0018`. the [qualified x64 release](decisions/0093-subscription-model-refresh.md#candidate-evidence)
is `7e9d887`, with terra/medium for compaction. installed activation and readback are separate.
three feature designers defined the content and evidence. independent claude
opus 5.5 at high effort accepted all three units on 2026-11-20, spec sha256
`7eee4ab18fb79c1891df52ea4246e85027004999c719d4d9d44ab4aefde668c3`.


## native recovery and memory availability

[adr 0108](decisions/0108-codex-quota-standby.md) owns the provider allowance
and no-effect evidence, jarvis admission and recovery, and the staged contained
account cut. qualify provider, jarvis and deployment independently, then the
immutable combined candidate. [adr 0109](decisions/0109-existing-codex-credits.md)
authorizes existing credits and governs account billing checks. independent
entitlement and provider confirmation belong to enrollment evidence. installed
cut is separately authorized.

[adr 0106](decisions/0106-interrupted-answers-and-parked-work.md) owns
interrupted final answers, grouped parking notices and operator inspection.
provider-runtime owns the protocol rule. qualify the exact provider, kernel and
jarvis pins in isolation before the separately authorized installed cut.

[adr 0086](decisions/0086-native-recovery-and-memory-availability.md) owns the
interfaces, schemas, file boundaries, trade-offs and per-unit acceptance.
integrate a (bounded recovery), b (provider → kernel → jarvis retry), then c
(receipt content and reader). qualify them together before the first stopped
cutover and normal admission of the pending owner work. d (independent memory)
owns the next stopped cutover after its isolated all-client proof. each unit
has a content designer, independent opus challenge and temporary red/green/refactor
proof. the two source releases implement a–c at `0015` and d at `0016`.
the first production cut preserved the original resume. the second used
ordinary owner pause 15. the original mail request settled and discord
acknowledged its qualified answer. production verified the original note and
a new source record while the assistant and its host were stopped.
[installed receipts](decisions/0086-native-recovery-and-memory-availability.md#production-cutover-evidence)

## memory orientation

[orientation-first adr 0078](decisions/0078-memory-orientation-first.md) and the
[shared contract](universal-memory.md#orientation-lifecycle-and-outages) settle
orientation, original navigation, outages and native-session boundaries first.
delivery order: shared universal-memory guidance and immutable upstream pin;
jarvis prompt/mcp adoption; separately owned nexus injection and dev-server
native-profile instruction adoption; then installed acceptance and usefulness
checks. the [open issue](issues/memory-orientation.md) tracks those remaining
consumer and installation boundaries. retain jarvis context assembly, host
compaction, existing keyword/semantic ranking and paged open throughout.
the [source evidence](universal-memory.md#orientation-first-source-qualification)
identifies the original orientation graph. production `34d1620` retains its
installed f2 qualification. the integrated orientation source requires separate
installed acceptance.

## current position

production runs `34d1620` at schema `0013`. the eighteen tables comprise
the nine native tables, six memory tables, work, attachment and event cursor.
migrations `0010`–`0012` added the last three. `0013` changed read-result
storage. todos carry their own wake fields. the [installed f2 evidence](runtime-reliability-and-integration.md#recovered-final-and-reset-disposition)
records the completed journey on this composition.

source refresh 2026-11-14: memory delivery and current main are composed, retaining
the existing provider/kernel/tools pins and adopting the shared claude-work2
account contract. targeted registry fixes resolve the later dependency audit;
full `scripts/verify` passes. [current source evidence](universal-memory.md#native-memory-rollout-source-qualification)
records the exact pins, migration/worker checks and restricted service-boundary
proof. the [online installed rollout](universal-memory.md#native-memory-installed-qualification)
now passes with its named profile deferrals; broader product acceptance remains separate.

the native provider/kernel/tools work is merged. jarvis [pr 49](https://github.com/NielsdaWheelz/jarvis/pull/49)
merges native main and worker-v7 composition. [adr 0065](decisions/0065-native-agent-supervision.md)
and the [integration handoff](native-agent-integration.md) own the current runtime:
declared callbacks, owner permits, public prose progress, explicit request
dispositions, independent reasoning during approval, durable stop and fresh-thread
reasoning recovery. there is no six-hour cutoff, rolling paid-capacity reservation,
saved-session recovery or main structured-step loop. existing effect/read barriers
remain. the separate contained stock endpoint replaces the old shared cognition
direction. current qualification is recorded in [acceptance](acceptance.md#native-cutover-acceptance).

skid [pr 61](https://github.com/NielsdaWheelz/skidbladnir/pull/61) implements launch
options/input and concise controls. jarvis [adr 0064](decisions/0064-simple-worker-orchestration.md)
introduced immutable captured targets and asynchronous wait/cancel. current
[adr 0068](decisions/0068-generalized-skid-consumer.md) uses live installed state
and profile-owned provider options; [adr 0069](decisions/0069-terminal-only-workers.md)
owns terminal-only worker control; adr 0072 adds v10 and enrolled host names.
those completed
source handoffs do not need another worker-protocol specification.

the earlier rollout started from paused production at schema `0004`.
slice 3 records the installed skid upgrade from `v0.24.2` to `v0.24.3` and
service-uid reads through the read-only mount. f2 qualified the actual
worker observation on installed `v0.24.4`. the named profile deferrals remain.

pending worker search may inspect only retained terminal history through
`agent.read`; it cannot promise complete saved conversations or route silently
to provider-native archives/shared memory. independent memory retrieval remains
its own explicitly selected capability.

## operational cutovers and upkeep

| item | owner / remaining result |
| --- | --- |
| skid release and fleet cutover (o2) | matching cli and read-only live-state mount installed. the [selected worker journey](runtime-reliability-and-integration.md#installed-lineage-and-stopped-restart-window) used the original target throughout |
| native jarvis activation | same-release host/application, stopped conversion, owner resume and normal memory turn pass; [installed evidence](universal-memory.md#native-memory-installed-qualification). remaining physical google checks stay in their [issue](issues/codex-private-process.md) |
| installed worker observation | [installed restart and notification](runtime-reliability-and-integration.md#restart-catch-up-and-original-send) consumed the same registered wait and independently read the worker report |
| claude retention | dev-server manages long retention on every configured home before memory capture activation; [issue](issues/claude-transcript-retention.md) |
| current memory artifacts | source dependency fetch/build/audit and online installed rollout pass with named profile deferrals; nexus image/runtime qualification waits for its next release; [image handoff](issues/nexus-memory-image-qualification.md) |
| standing verification design | separately scope the [testing redesign](issues/testing-redesign.md); completed native/worker exceptions do not create a standing suite |

these are independent release, repair or policy tasks, not another prerequisite
mega-pr. preserve [old qualification-resource disposition](issues/qualification-residue.md) and
nexus's [historical job disposition](issues/nexus-generation-dispatch-contract.md)
with their owners. none is resolved merely by merging a new runtime.

## delivery map

the roadmap is organized by useful product behavior. legacy o/m labels remain
cross-references for existing handoffs, not github pr numbers or a fixed pr count.
o1, o3–o5 and o8 are implemented foundations; o2 is the operational cutover above.

| feature | contract / specification work | owner and dependencies |
| --- | --- | --- |
| one main for every event (o6) | [contract and evidence](one-main-events.md) implemented and isolated-qualified. installed main processed owner, timer, worker, mail and calendar events | jarvis; builds on native main; source adapters remain separate |
| useful work records (o7) | [contract](work-records.md) adopted by 0071; mutable todos and one-time/repeated wakes implemented in source | jarvis, one work table and timer. the installed journey rescheduled and consumed a one-time wake |
| delegated follow-through (o9) | [slice 3](delegated-follow-through.md#implementation-evidence--2026-11-15) qualified source and candidate. [f2](runtime-reliability-and-integration.md#restart-catch-up-and-original-send) qualified the production codex worker journey | jarvis; o6/o7 and existing o8 observation |
| universal memory (m1–m5) | [completion contract](memory-delivery.md) implemented and installed on the online jarvis/native fleet with named profile deferrals; nexus waits for its next release | memory library, jarvis, provider-runtime, llm-tools, dev-server and nexus-web; [memory delivery](#memory-delivery) |
| private workspace | [slice 4 source](private-notes-and-rolodex.md#implementation-evidence--2026-11-15) qualified source and candidate. production notes and dirty checkout verified. [installed helper/git](issues/private-workspace-installed-cutover.md) remains open | jarvis plus kernel/provider native access; ordinary private checkout, documents/helpers/visuals and agent-chosen git |
| event sources and recurring work | [source-audited spec](event-sources-and-recurring-work.md) qualified source and candidate. installed mail and calendar attention verified. [conversational controls](issues/event-sources-installed-cutover.md) remain open. recurrence belongs to o7 | jarvis; one cursor table/poll task, normal main admission and shared connector helpers; no memory schema change |
| attachments and durable originals | [slice 5 evidence](attachments-and-durable-originals.md#implementation-evidence): source and separate private-storage/native-host candidate qualified. the production journey retained and reopened the original pdf | jarvis plus dev-server; one table/private bucket, exact mail discovery and native file reading; reuses qualified slice 4 access |
| mail/calendar/web read completion | [f1 contract and evidence](mail-calendar-web-reads.md#implementation-evidence) source and separate candidate qualified. selected production reads are recorded in f2. wider [search proposal](complete-and-continuable-searches.md) is reference material | jarvis connector/fresh-read composition and llm-tools web; integrate landed slices 5–6 |
| reliability and integrated acceptance | [f2 contract/evidence](runtime-reliability-and-integration.md#implementation-evidence): integrated source, isolated repairs and installed journey qualified. the final reset, twelve native cuts and capture of the genuine owner resume are verified. the [installed cursor check](runtime-reliability-and-integration.md#stopped-google-cursor-correction) reproduced 80 old revisions. the owner retained the corpus and ended cleanup. the strict no-republication criterion remains unmet | discord lifecycle/native diagnostics, owning-layer repairs, stopped production cutover/live acceptance and owner-selected fresh history reset |
| subscription model/runtime and delegated choices | [f3 evidence](subscription-model-runtime.md#implementation-evidence) source/candidate qualified | main astra/max, memory sol/xhigh via personal codex; native-child choices and bounded upstream skid launch extension |
| broader complete searches — later | remaining [proposal](complete-and-continuable-searches.md) retained; memory ranking, maps and worker-history expansion remain deferred | memory library, jarvis, llm-tools and skid; no wholesale search-contract adoption |
| dreamer work context — later | [contract](dreamer-work-context.md) retained outside this cut; selected dream wakes also deferred | jarvis; m3 and o7; quiet memory delivery unchanged |
| budget integration — later | settled [contract](budget-integration.md) retained; full bookkeeping authority and larger originals need separate adoption/implementation | jarvis plus budget-app; existing ledger/api, private object storage and attachment/native-reading prerequisites |

the work view and delegated follow-through do not wait for full memory. its
separate pr retains its own source/integration handoffs and stopped cutover.
do not respec completed foundations or reconstruct memory's superseded adr chain.

### v2 reviewable pr slices

these are implementation boundaries, not opened prs or deployed work.
each completes its scoped behavior and proportionate checks; intermediate slices
need not be independently usable. upstream changes stay in the repository that
owns their public interface.

the documentation baseline landed in pr 60 (`8c0bf36`). for each slice, audit and
finish its owning spec against current source; hand it to an implementation
agent; review the diff/evidence, resolve gaps and land the implementation.
specs may be prepared while the preceding slice is implemented, against its
explicit public contract; audit the landed predecessor before implementing the
next slice. refine existing feature contracts in place, with no parallel work
orders.

| order | review unit | completion and dependency |
| --- | --- | --- |
| 1 | common main and conversational consent | [source-audited spec](one-main-events.md): common request lifecycle, full plan, atomic conversational consent, scoped stop and recovery; remove gate, component approval and old scheduler; installed worker outcomes are proved in 3 |
| 2 | todos and scheduled turns | [implementation spec](work-records.md): ordinary CRUD, atomic local receipts, fresh reads, calendar/interval wakes and busy-main publication; accepts queued-late schedules; depends on 1 and converts retained reminder obligations |
| 3 | skid follow-through | [source and candidate qualified](delegated-follow-through.md#implementation-evidence--2026-11-15): real skid, full-plan continuation/restart/content proof and bounded repairs; depends on 1–2 and matching artifacts; production acceptance at final v2 cutover |
| 4 | ordinary private repo | [source and candidate qualified](private-notes-and-rolodex.md#implementation-evidence--2026-11-15): borrowed checkout, mixed native/callback tools, documents/helpers/visuals and native git; isolated memory roles retain containment; separate temporary native-host proof, production at final cutover |
| 5 | attachment originals and reading | [source and candidate qualified](attachments-and-durable-originals.md#implementation-evidence): automatic discord/selected gmail capture, private r2, stable references, fresh native paths and scoped deletion; includes necessary mail discovery, reuses qualified 4; production at final cutover |
| 6 | external event sources | [source-audited spec](event-sources-and-recurring-work.md): email/calendar cursors publish ordinary inputs while main is busy; source work can overlap 5, integrated proof consumes its merged shared helpers; daily review belongs to 2; production cutover separate |

independent investigation of 4's upstream needs and 6's source interfaces may
proceed alongside earlier units; their implementation adopts landed interfaces.
the owner accepts incomplete intermediate slices. remove replaced paths in their
own slice; do not retain a compatibility scheduler or make each pr independently
deployable. keep reminder obligations in the private cutover inventory until 2;
unattended activation waits for the selected slices and accounted-for commitments.
3 reused existing observation source for its qualified candidate and demonstrated
repairs. the owner selected real installed workers with a temporary candidate;
`claude-work` remains unavailable by owner decision; useful execution is NOT_RUN.
temporary resources are removed; its evidence distinguishes the live candidate
from subsequent memory-mainline integration.
keep production's release/database/control state and intermediate activation
refusal unchanged. its evidence labels controlled ingress and actual discord
outbox separately. physical-owner gateway and selected-production restart/complete
journey remain final-cutover acceptance in the existing worker issues. neither
source review of 1 nor candidate proof of 3–4 establishes that production result.
source and candidate qualification do not authorize intermediate production cutover.

v2 includes ordinary progress, blocker questions, approvals and completed results
inside these journeys. it does not add standalone components for them. approval
meaning is main's judgment; reuse the existing action decision transition, with
no exact-prose matching or additional consent system. defer browser control, new
credential handling, interactive hosting/television integration and a separate ui;
slice 4 can already author/run ordinary helpers and self-contained visual files.

### v2 finishing prs

accepted scope under adr 0075; [f1 is source/candidate qualified](mail-calendar-web-reads.md#implementation-evidence).
[f3 is source/candidate qualified](subscription-model-runtime.md#implementation-evidence)
under the owner's [role/delegation refinement](decisions/0076-role-models-and-delegated-choices.md).
[f2](runtime-reliability-and-integration.md#implementation-evidence) has isolated
reliability/deployment proof under the owner's
[production/reset refinement](decisions/0077-production-acceptance-and-fresh-reset.md),
reordered by [fresh-corpus adr 0078](decisions/0078-fresh-corpus-first-acceptance.md).
[adr 0081](decisions/0081-ready-memory-for-main.md) additionally adopts shared
frozen ready orientation for main with explicit historical backlog, preserving
canonical inputs/effect recovery and existing idle compression. source proof and
installed foreground dispatch and the subsequent combined journey passed.
[adr 0082](decisions/0082-ready-seeds-and-nightly-priority.md) additionally adopts
ready-prefix dream seeds, full admitted reads and the existing due-nightly
priority after foreground work. f2 verified the committed seed progress and
quiet synthesis notes on the selected release.
[adr 0083](decisions/0083-dreamer-cumulative-input-budget.md) raises only the
dreamer cumulative input ceiling to 1,000,000 after measured live exhaustion;
the selected production dream completed within the amended bounds.
f2 records the exact installed composition and both reset boundaries.
f1 used the owner-approved unmerged event stack at `945dc62`; its evidence
records the exact artifact, pins and temporary candidate. f2 owns the production
reads and cutover evidence.
these labels preserve the original six slices and do not imply opened prs.

| unit | scope and owner | contract and status |
| --- | --- | --- |
| f1: complete mail/calendar/web reads | jarvis owns complete supported mail/calendar traversal/text, incoming `Reply-To` and fresh deliberate mutable observations; llm-tools owns web search continuation and full supported extracted-text chunks. bounded responses with explicit provider/live-source limits; retain original callback receipts and paid-read barriers. existing writes stay. | [contract and evidence](mail-calendar-web-reads.md#implementation-evidence); source and separate candidate qualified on the audited owner-approved event stack |
| f2: reliability and installed integration | interruptible discord login/readiness retry, owned asynchronous DNS and clean stop; safe native diagnostics and owning-layer repairs. qualify the actual composition, restore the activation primitive, perform the preliminary fresh reset, run the production journey, then perform the final reset. historical irreproducible native incidents may remain explicitly open. | [contract](runtime-reliability-and-integration.md); [isolated discord evidence](runtime-reliability-and-integration.md#implementation-evidence) qualifies that repair; the [historical native issue](issues/native-protocol-diagnostics.md) remains open |
| f3: subscription model/runtime and delegated choices | main `gpt-6-astra/max`; fixed compactor/dreamer `gpt-6.1-sol/xhigh`, through the personal codex subscription and `provider-runtime`. main chooses native-child and per-session skid model/effort. qualify actual catalog keys, auth, effort, runtime/pins and the bounded upstream skid extension; no substitute for fixed-role selections. | [contract and evidence](subscription-model-runtime.md#implementation-evidence); source/candidate qualified with unchanged cognition pins and installed skid v0.24.4 on macbook/dev-server |

specification can proceed in parallel. implement f1 after auditing the merged
5–6 interfaces; do not race their google/attachment changes. f2's isolated native
diagnosis and discord repair can proceed alongside f1/f3; its final integration
phase waits for all selected artifacts. f3 can investigate/qualify the selected
subscription model independently; source support does not prove availability on
the actual authenticated route. unsupported target availability is a blocker,
not permission to downgrade. one integration owner reconciles shared pins,
configuration and prompt/catalog changes before final qualification.

each unit gets one spec, with any necessary upstream repository handoffs inside
that spec. fixes belong to the existing owner; no parallel provider wrapper or
orchestration framework. f1 owns connector/web read surfaces, f2 service/native
failure handling, f3 model/auth selection and compatible runtime/pins. f1/f2 own
any necessary upstream fixes and adoption; coordinate shared pins explicitly.
f3's owner-selected worker launch extension is a separate implementation boundary
within its contract; preserve terminal-only control and asynchronous observation.
preserve existing useful prompt/personality,
native subagents and skid; change only demonstrated omissions. each spec includes
proportionate content design, adversarial review and temporary end-to-end/live
red/green/refactor proof, followed by deletion of its temporary probes.

f2's installed journey must cross real boundaries: incoming self-fixture email → full message
and attachment inspection → useful sourced research/delegation → an appropriate
existing draft/calendar action → scheduled follow-through → restart-safe
continuation. verify native child results and skid outcome integration rather
than treating launch/idle as completion. test the exact final model/runtime and
published tools, preserve original effect receipts, and state unrun boundaries.
no comparative performance claim or standing benchmark framework follows.

after isolated reliability proof and qualified f3 are integrated with f1/slices
1–6, f2 performs the stopped production cutover, preliminary fresh reset and actual
installed journey under the fresh-corpus decision.
the preliminary reset is complete. [adr 0079](decisions/0079-bounded-serial-compaction.md)
adds exact 2,048-byte free copies and up to eight independent inferred nodes per
serial batch after substantial genuine new capture. qualify that amendment at
the library/caller boundary and installed composition before completing the
journey. preserve originals, fixed models, cuts and complete main coverage; the
memory contract owns atomic addressed completion and request limits.
[adr 0080](decisions/0080-first-valid-compaction.md) subsequently adopts first
valid hard-fitting summaries while retaining the 512-byte prompt target and
existing ceilings. qualify its stopping boundary, then continue the same installed
journey; no additional reset, model, schema or memory-source change.
reconcile pending effects/waits and account for reminders; migrate/provision the
selected release, then prove physical owner ingress/consent and restart continuation
through existing operations. source success alone does not activate production.
the owner permits an explicitly open irreproducible historical native issue;
current demonstrated defects still require repair. no intermediate activation.

apply the fresh-corpus decision's stopped reset procedure before the journey and again
after acceptance: configured discord/jarvis/ALL central shared history and todos/
reminders/waits. preserve private repos, credentials, real google data, original
native/nexus chats and unknown-effect receipts. retain verified current `0013`
recovery, replacing predecessors only after verification. coordinate the 18 tables,
source cuts and attachment disposition; no old-history republication or automatic
daily-review seed. after the second operation republished old revisions,
[adr 0085](decisions/0085-preserve-google-cursors-during-correction.md) authorized
one stopped correction retaining the google cursors. its installed preflight
reproduced prior revisions under genuine pause 13. the operator preserved the
corpus and existing snapshot. the owner retired the correction for this delivery.
the strict no-republication criterion remains unmet. fresh-corpus acceptance leaves the
[39,873-leaf preparation backlog](runtime-reliability-and-integration.md#historical-preparation-limit) unqualified
for latency and throughput.

trade-offs: deeper retrieval uses more calls/context; provider and per-operation
limits remain. main `max` and memory `xhigh` can increase latency and subscription
usage; compaction may delay foreground preparation.
the historical native cause may remain unknown; f2 adds asynchronous DNS and any
demonstrated websocket repair. production testing incurs downtime; the fresh reset
discards useful shared history and commitments too. f3 adds a bounded skid launch-contract
change; arbitrary profile shell commands cannot silently ignore overrides.
inbox housekeeping, new invitation
response tools, outgoing files, browser/credential products, hosted interactive
deliverables, memory/maps/fleet search expansion and budget stay outside these prs.

## external specifications and handoffs

jarvis owns product intent and consumer obligations. each external unit gets a
bounded repository handoff from its owning contract: public inputs/outputs,
identity and failure semantics, limits/costs, acceptance evidence and the exact
consumer adoption. record prepared, handed off, implemented and adopted as distinct
facts; writing this roadmap sends no assignment to another agent.

| repository owner | remaining handoff | specification source / status |
| --- | --- | --- |
| skid / jarvis deployment owner | selected-production codex worker follow-through qualified against the installed cli and live-state mount | [terminal-only contract](decisions/0069-terminal-only-workers.md), [slice 3 evidence](delegated-follow-through.md#implementation-evidence--2026-11-15); the v0.24.3 candidate proof predates the [selected production journey](runtime-reliability-and-integration.md#restart-catch-up-and-original-send) |
| skid, search | page worker inventory and retained terminal text before response fencing; preserve terminal-only control and explicit retained-screen limits | [search composition](complete-and-continuable-searches.md#receipts-and-external-composition); later handoff, not implemented; provider archives and shared memory remain separately selected capabilities |
| dev-server | selected cli/collector installation, long claude retention, private routing, client/capture credentials and native mcp configuration; arch deferred | memory [ownership](universal-memory.md#2-ownership-and-admission), [collector](universal-memory.md#collector-and-normalization) and [retrieval](universal-memory.md#6-retrieval) contracts adopted in its spec; source and isolated host reconciliation qualified; installed fleet handoff remains |
| llm-calling (`provider-runtime` package) | m1 archive enumeration/heads/events, capture identity, internal marking and memory-tool echo suppression | [native capture contract](universal-memory.md#3-native-capture); public archive api/codecs implemented and source/live-qualified; actual fleet admission separate |
| llm-calling (`provider-runtime` package), workspace | mixed built-ins/callbacks, inherited-mcp suppression and actual returned thread-policy verification; preserve other consumers | [slice 4 public contract](private-notes-and-rolodex.md#public-contracts-and-deployment); implemented at combined provider `ea9f820` |
| kernel, workspace | optional borrowed cwd, immutable authority/fingerprint, ownership-aware cleanup and native activity alongside callbacks | [slice 4 public contract](private-notes-and-rolodex.md#public-contracts-and-deployment); implemented at combined kernel `9f5f951`; no llm-tools change |
| jarvis deployment owner on dev-server, notes | persistent private checkout, ordinary git authentication, host permissions and hard-cut host mapping | [notes deployment contract](private-notes-and-rolodex.md#public-contracts-and-deployment); source changes stay in jarvis's existing deploy files; operator bootstrap/install remains separate |
| memory library | existing archive/tree/view/search; add explicit nexus source values and atomic export append/duplicate proof through shared insertion primitives | [core](universal-memory.md), [completion handoff](memory-delivery.md#non-overlapping-implementation-boundaries); uncapped ranked [search amendment](complete-and-continuable-searches.md#uncapped-ranked-memory) remains a separate delivery |
| kernel + llm-tools | production transient read recorder for disposable dreaming using the existing recorder/executor seam | [daily dreaming](universal-memory.md#daily-dreaming); production recorder published; coordinated kernel/tools/provider pins adopted; request-fit and strict json fixes qualified |
| llm-tools, web reads | portable web-search continuation/provider boundaries and complete supported extracted-text chunks, retaining web safety | [f1 web handoff and evidence](mail-calendar-web-reads.md#implementation-evidence) implemented, adopted at exact pins and qualified; no kernel runtime redesign |
| llm-calling (`provider-runtime`), kernel and jarvis model composition | personal-subscription main astra/max, memory sol/xhigh and compatible native/runtime pins | [f3 evidence](subscription-model-runtime.md#implementation-evidence); actual personal route and fixed roles qualified with unchanged cognition pins; jarvis activation belongs to f2 |
| skid and jarvis launch adapter | per-session model/effort, exact native lowering and worker v11 cutover | [f3 handoff](subscription-model-runtime.md#implementation-evidence); v11 source/candidate qualified; signed skid v0.24.4 published/adopted on macbook/dev-server, with terminal-only evidence and existing waits |
| budget-app | broaden existing write authority to all bookkeeping, reuse shared planner calculation through an api, and support independent originals up to 100 mib through private r2 | [budget api handoff](budget-integration.md#budget-api-handoff); fresh `7b7a9c2` source audit complete; bounded handoff prepared, not assigned or implemented |
| budget deployment owner and dev-server | budget private bucket/cors/storage secrets; jarvis configured budget origin/owner/read/write credentials and native cache access | [budget delivery](budget-integration.md#nonoverlapping-delivery-and-hard-cutover); provisioning and installed qualification remain separate |
| nexus-web | configured owner's librarian tools and future-only durable capture; terminal snapshot/outbox/publisher, current call identity and native internal marking; no automated-helper tool grants | [completion handoff](memory-delivery.md), [client issue](issues/nexus-memory-client.md); adr 0070 source and isolated current-route qualification complete; nexus release deferred |

the [completion evidence](universal-memory.md#memory-completion-source-qualification)
qualifies the implemented nexus capture and isolated native/jarvis journeys.
the [latest source evidence](universal-memory.md#native-memory-rollout-source-qualification)
adds registry, profile and deployment-boundary repairs. neither establishes
installed client acceptance. dev-server owns native private configuration;
nexus credentials/publication wait for its next release.

downstream jarvis code consumes the published public surfaces and qualified pins;
the external agents do not own jarvis authority, work state or continuation.
the memory library owns its memory schema under the accepted deployment contract;
jarvis owns the composed migration and canonical request/effect schema.
new shared-library work is requested only for an identified missing primitive.
there is no further generic kernel/skid orchestration redesign in this roadmap.

one mcp server lives inside jarvis. dev-server configures native codex/claude
clients and installs the capture collectors; it does not implement another memory
server. nexus's application agents require their own client bindings, distinct
from developer agents working in the nexus repository. adr 0070 explicitly adds
its distinct account-owned capture source; adr 0072 declares nineteen native/jarvis
lanes, including each host's separate claude-work2 home.

## orchestration delivery

### o1–o2: fleet launch

o1 is implemented. current worker v11 start accepts machine/profile and optional
name/cwd/group/freeform initial prompt/model/effort. profiles retain
provider/account/executable defaults; [f3](subscription-model-runtime.md#implementation-evidence)
qualifies explicit native overrides. jarvis chooses available supported selections.
preserve one launch configuration owner,
literal input and explicit refusal for unsupported targets.

skid owns readiness and initial prompt submission. preserve the created terminal
ref if submission fails or is unknown; never relaunch after ambiguous creation.
creation, submitted prompt and completed work are distinct facts. retain ordinary
start without a prompt. dev-server pins the immutable release/configuration and
verifies the intended artifact on each peer without replacing jarvis cognition.

source qualification covers literal prompts, configured profiles and inspectable
partial launch without replay. o2 still publishes/pins/installs the coordinated
artifact and records each peer's installed identity. use the existing fleet
release contract; no additional launch design is due.

### o3–o4: delivered native transport and supervision

provider-runtime exposes declared tools, correlated callback requests/results,
thread/turn/call identity, final output, usage, steering and interrupt during a
stream. the codex adapter lowers them to native declarations and `item/tool/call`;
it imports no jarvis authority or llm-tools policy. the kernel publishes the
frozen catalog, validates callbacks, dispatches serially through its existing
host port and validates the final structured outcome. codex owns the inner loop.

reuse llm-tools schemas, validation/execution and recorder interfaces; add a public
projection seam there only if missing. accepted-invocation/checkpoint ports must
work before a native final answer. the input/control port stays live even when
no callback arrives: steer compatible input, durably queue other input, observe
owner stop promptly. an admitted write reaches settlement/reconciliation before
interruption releases the lane. retain separate isolated one-shot memory roles.

the shared native contract and N001–N020 qualification are complete. multiple
callbacks, frozen declarations, contained authority, live control and original
result/terminal evidence are delivered public library behavior. use the current
[acceptance evidence](acceptance.md#native-cutover-acceptance); retired candidate
containment failures and missing-callback claims do not reopen this work.

nexus supplies a second consumer for this shared work; its
[dispatch contract](issues/nexus-generation-dispatch-contract.md) is part of
o3–o4. validate incompatible requests before native submission, retain bounded
original diagnostics, and preserve valid native terminal evidence before product
acceptance. prove authoritative non-submission, accepted failure and successful
strict-json research with actual tools; possible submission without a terminal
remains uncertain. current exception names and missing acceptance events do not
prove absence. introducing new submission evidence requires coordinated
provider/kernel adr and spec changes, not a consumer exception workaround.

the accepted shared native spec now replaces both application tool bridges with
the same frozen native declarations and callback execution contract. nexus's
remote-shell route is deleted at its native cutover. domain connectors and
authority remain application-owned. nexus adoption does not depend on jarvis
product o6–o9. [adr 0065](decisions/0065-native-agent-supervision.md) and the
[integration handoff](native-agent-integration.md) govern jarvis's current cutover.
its queue, metadata schema, publication and short deadline stay nexus-owned.
old uncertain admissions retain their existing recovery obligations.

### o5: delivered native main

main has adopted the qualified native pins under adr 0065 and preserves current
event authority. it persists each accepted invocation before
dispatch and its result before the native reply, using the three native journal
tables plus existing `read_position` and `action`. `model_decision` remains only
for genuine isolated inference. native call ids correlate replies; durable host
ids own effects. reuse the same reads, writes, approvals and reconciliation.

native execution replaces the former main step loop and runs until
completion, a genuine blocker, required input or owner stop. no arbitrary elapsed
cutoff or cumulative usage quota. operation and transport deadlines remain.
pending approval returns a durable receipt while independent reasoning continues;
later action-resolution input resumes the original request without another effect.
callback reply/interrupt ordering belongs in this slice.

o5 already owns canonical request continuation, operational fencing and fresh-thread
reasoning recovery. o9 adds discretionary delegation/content and retires chat
stop interception. current owner permits replace capacity reservations; per-tool
byte/deadline/effect-attempt bounds remain.

frozen worker-v7/native composition is qualified, including independent reasoning
while approval waits, prose progress, steering, stop and recovery. installed
production cutover, physical google/discord integration and explicit owner
resumption remain operational work; this plan resumes no stopped service.

### o6: one main for every event

the [o6 implementation contract](one-main-events.md), adopted by adr 0071, owns
common input, ordinary conversational consent, lifecycle and stopped cutover.
source implementation and isolated integration/live qualification are complete;
the contract records exact evidence. slice 3 records candidate proof against
installed skid. [f2](runtime-reliability-and-integration.md#restart-catch-up-and-original-send) records production worker acceptance.
the old scheduler is removed; slice 2 supplies scheduled todos. selected slices
and retained obligations still govern resumption. this branch is not the
installed memory rollout release.

owner messages, action results and scheduled wakes receive the same main tools
and approval rules. background origin alone is not read-only and need not invent
fresh owner input or obtain a new standing instruction. jarvis may initiate
ordinary work and schedules, or do nothing. consequential effects still await
owner consent interpreted in conversation; clear prior consent need not be asked
again. source identity stays honest; an external fact is not owner consent.

replace current-owner-only write grounding, the read-only wake plan and affected
action lineage together in the authority adr. preserve immutable arguments,
classification, reconciliation and stop. define the common entry path for worker
results, email and internal suggestions; migrate supported sources now. new
source adapters/cursors belong to later source slices, not a second event engine.

main chooses useful progress, blocker questions and results in ordinary prose;
routine events may be silent. no notice-policy field or separate notification
feature. verify that requested reminders and useful outcomes actually reach the owner.
compatible input steers the live native turn; incompatible input queues durably;
conversational stop uses main's judgment as specified by o9. equal authority does
not itself implement email ingress.

exit: equivalent owner/wake/action events get equal capabilities; automatic writes
need no fabricated owner text; consequential writes retain approval; incoming text
cannot change authority; unrelated input remains serviceable during a long run.

### o7: one work table and four attention states

the accepted [work-record contract](work-records.md) owns schema, CRUD tools,
optional scheduling, content and focused acceptance. owner decisions: mutable current rows,
physical deletion, agent-managed bookkeeping. one table covers todos, projects,
commitments and things to track; jarvis manages records automatically.

| active state | meaning |
| --- | --- |
| doing now | actually being worked on; useful context/estimate when known |
| blocked | named unblocker and specific condition |
| next up | at most three priorities; invest definition/design here, without inventing work to fill empty slots |
| backlog | lightweight capture; do not pre-plan everything |

the same state field adds done/cancelled outside the active view. title/content,
optional due date, next wake/repeat, schedule identity, nominal civil cursor and
ordinary identity/timestamps suffice.
due date is a deadline; a wake starts a turn. owners, blockers, estimates and
refs stay prose. no history, tombstones or separate lifecycle.

reuse an item for the same work; no row for each specialist. changing/deleting
records does not stop workers or cancel pending effects. completing/cancelling/
deleting the todo disables its future wakes; already-published inputs remain.
attention states inform agent judgment. daily review is an ordinary repeating
todo that remains active between runs. admitted schedule changes delayed past
their time wake late with truthful context. the
[implementation evidence](work-records.md#implementation-evidence) records source
qualification; the [installed handoff](operations.md#supervised-todo-setup) retains
reminder conversion and supervised setup. later dreamer work context is outside
this cut.

exit: automatic CRUD persists across restart; active views obey the four states
and three-next-up cap; deletion physically removes the row; old callbacks cannot
recreate it. a due wake publishes context once across restart and never implies
task completion; missed recurrence coalesces. no workflow controller is added.

### o8: richer start and asynchronous wait

[contract](worker-launch-observation.md) consolidates current
[adr 0069](decisions/0069-terminal-only-workers.md): optional launch input,
terminal targets with immutable capture, bounded terminal inspection/control and
durable nonblocking wait/cancel. v10 source and enrolled-label proof are complete; earlier
[native qualification](native-agent-integration.md#qualification) describes its
recorded predecessor only. o6 owns broader event authority; o7 records and o9
discretionary follow-through remain separate.

the [live service-state boundary](universal-memory.md#native-memory-installed-qualification)
and matching artifacts passed under the jarvis service uid. the
[installed journey](runtime-reliability-and-integration.md#restart-catch-up-and-original-send)
retained the wait registration across restart and delivered the worker
outcome through discord. useful claude-work execution remains `NOT_RUN`
under the selected availability boundary.

exit: coordinated installed launch/control; register, serve another owner message,
receive one deduplicated later observation, repeat across restart. preserve
partial/uncertain effects, original receipts, deadlines, target changes,
unavailable/truncated output and cancellation facts.

### o9: continuation and coordination

[slice 3 spec](delegated-follow-through.md) owns the adopted behavior:
every admitted event reaches the same agent with the same capabilities. jarvis
chooses work, delegation, observation, integration and useful follow-ups.
todos inform judgment, not permissions; stop/interruption are interpreted intent
and ordinary tool actions. no work controller, links, eligibility or stop guarantee.

o5/o6/o8 provide the implemented machinery; o7 supplies bookkeeping. full-plan
events and conversational stop are already source-qualified. slice 3's source
repairs and temporary candidate are qualified for useful delegation, asynchronous
continuation, restart and honest content against installed skid. `claude-work`
remains unavailable by owner decision; useful execution is NOT_RUN. the
[unexplained native defect](issues/native-protocol-diagnostics.md) remains open.
production activation/acceptance stays at final v2 cutover. no new library or
worker protocol.

## memory delivery

one standalone memory library, hosted in jarvis, owns archive, tree, persisted
views, compression and search/navigation over the shared admitted corpus. jarvis
supplies capture/admission, inference/embedding execution, scheduling and mcp/http.
jarvis starts fresh top-level turns from the view and exact current requests/
receipts; codex/claude/nexus keep their native chats and choose memory reads.
no recaller, selective extractor or external client context replacement.

bounded source parts and notes are ordinary leaves in one arrival-ordered binary
tree, retaining source event identity and dates. long text needs no private leaf
reduction. archived tool results and new jarvis main built-in call arguments each
retain up to 30,000 characters, head/tail with explicit omission. canonical
execution receipts remain exact. [adr 0098](decisions/0098-conversation-capture.md)
keeps pre-cut worker history and limits new capture to the delivered report. supplied context
stays reference-only. views use corrected merge priority and persisted batched
shrink. main consumes a frozen fitting ready view under adr 0081. adr 0082 gives
dreaming committed-ready seeds and the existing due-nightly priority after main;
full admitted reads, unbuilt seed backlog and strict maintenance preparation
remain. shared search
retains the full admitted read scope.
email capture uses actual tool observations, without wholesale inbox ingestion.
retain exposed attachment text and references; durable files/image access remain
in the attachment feature. shared tools/basic inspection ship first; a dedicated
memory browser/export interface is deferred.

optional notes remain an accepted addition. associative dreaming is required in
the first memory delivery as a jarvis function over the library. new archive
material and explicit notes seed it; it appends attributed synthesis notes with
supporting references into the shared tree. prior dreams can be retrieved but
create no new seeds. nightly idle runs start from a bounded tree view of eligible
new material since successful progress; missed days and late capture stay pending.
saving is quiet under the accepted core; ordinary turns may surface findings.
selected-finding wakes are deferred outside the adr 0071 cut; the
[event contract](event-sources-and-recurring-work.md) does not change m3.
each bounded run also receives a small random sample of older original events/
explicit notes for optional exploration; shared search ranking is unchanged.
the closed output/progress contract is complete. implementation
proceeds in dependency order, but a core-only release does not complete this
delivery. use the [contract](universal-memory.md), not duplicated schema/api prose here.
ordinary algorithm defaults and resource tuning need coherent implementation
contracts, not a separate owner decision for every parameter.

the accepted [completion contract](memory-delivery.md), adopted by
[adr 0070](decisions/0070-nexus-capture-and-memory-delivery.md), adds future-only
nexus capture and current functional proof. it owns the exact schema/api/content
delta; the units below describe the existing core, not new implementation work.

| unit | implementation boundary / done when |
| --- | --- |
| m1 | provider-runtime `agent_runtime/archive.py` and codecs: complete listing/heads, read-only complete events, stable capture-relevant identity/digest, reference-only context suppression after digest binding, optional exact native inherited-origin proof, internal marking and memory-tool echo suppression; do not filter inherited prefixes; validate consumed fields while tolerating unrelated metadata; prove installed-provider mappings |
| m2 | library archive/schema plus jarvis capture/collector/api: atomic activation and event/checkpoint commits, direct archived-origin proof, independent checkpoint digest/all-copy progress, stateless collectors and status; preserve admission and source identity across the package boundary |
| m3 | library tree/compactor/views: ordinary source-part/note leaves, aligned binary/free nodes, corrected priority and persisted batched views, bounded contextual compression, fixed-cutoff readiness and repair. jarvis supplies inference/scheduling and fresh-turn integration. first-delivery dreaming atomically appends attributed synthesis notes/references/positions with consumed-seed progress; one physical cursor, no self-seeding, waking output or background paid-call replay journal |
| m4 | library navigation/search/open/note append plus jarvis adapters: one keyword/vector rank-fusion pipeline and shared clients/pools; frozen view pages, zoom/date and paged originals, main save recovery, private mcp and admission; select/qualify server pins |
| m5 | messages/checkpoints/service/migration + dev-server: drain old memory work, preserve existing rows, cut old remembered_at/recaller paths, install private endpoint/collectors/profile config and activate admitted lanes online; no historical import or dual reader |

m1–m5 source boundaries and isolated checks are complete for the 2026-10-09
baseline, including first-delivery dreaming and nexus's owner-chat consumer. the
[integration evidence](universal-memory.md#12-integration-evidence) owns exact
pins and qualification; the [repair record](universal-memory.md#memory-repair-source-candidate)
owns the later repairs. the completion delta and isolated functional proof are complete. actual fleet
install/admission, private client/capture credentials and production cutover
remain operational handoffs.

m2–m4 follow the completed product and engineering contracts. use one serial
compactor and existing postgres/process; no separate daemon or durable job ledger.
live capture requires m1 proof. revise one shared policy/primitive at its owner, not copies in each unit.
retain admitted parent/child messages and reports under the common capture policy:
long text becomes source-linked parts; tool results use the accepted head/tail cap.
reference-only context and proved inherited-copy omission remain explicit policies.
keep source/identity suppression before capture
and one undivided corpus with independent admission/connection permissions.

m5 uses one local pre-migration dump/runtime copy and the existing stopped cutover.
its exact restore limits and owner-fenced drain are in the memory contract.
no backup platform, native-memory disablement or automatic history import. full
acceptance includes all declared hosts/profiles; disabled/unqualified lanes are
reported, not passed off as universal coverage.

### memory completion delivery

[completion contract](memory-delivery.md) owns the bounded nexus schema/transport,
content, files and acceptance. [repair contract](memory-repairs.md) retains the
presentation/codec/client guarantees. production installation/activation remain
separate. preserve owner changes and current consumer dependency compositions.

1. adopt bounded handoffs in the owning repositories. designers supply schema
   examples; independent reviewers challenge admission, content and failure
   boundaries. freeze shared source values before adapters diverge.
2. write temporary red end-to-end/live cases for missing behavior; preserve
   already-green core cases. use the completion contract's non-overlapping
   library, jarvis-capture, jarvis-cognition, nexus, fleet and integration owners.
   cognition repair can proceed while capture owners implement the shared seam.
3. compose one qualified memory pin into current consumers. the integration lead
   alone owns shared locks/manifests/composition; do not downgrade nexus to the
   october stack. propagate exact role/dependency fingerprints and remove replaced
   paths. prove green, independently review, refactor and recheck affected behavior.
4. prove every current api/mcp operation and actual jarvis/native/nexus journeys,
   including the durable export failure matrix. complete static/build/audit gates.
   independently review cleanup, then delete only new temporary probes/helpers.
   record exact artifacts, commands, results and gaps in existing evidence/issues.
5. prepare the exact fleet/client/image handoff. adr 0072 authorizes the current
   jarvis/native rollout; nexus waits for its next release. each selected installed host/client
   must pass its live smoke before claiming universal delivery. broader
   [usefulness/load evaluation](issues/memory-usefulness-evaluation.md) is a later pr.

no production v1 capture exists; use clean task-owned v2 qualification state.
discovering real old capture blocks cutover rather than authorizing reset/backfill.
the contract states encoding cost, uncertain-save and deleted-test tradeoffs.

### memory installed rollout

owner-authorized execution, 2026-11-14; online qualification complete 2026-11-15
within the named profile deferrals. scope: repair the dependency audit, integrate
qualified source and install/verify jarvis plus macbook/devbox native memory.
nexus code is preserved but its images, migration, credentials, publication and
activation wait for the next nexus release. [arch is offline and explicitly deferred](issues/arch-memory-activation.md).
all configured personal/work/work2 profiles may share with jarvis and one another;
the owner confirms control of their content. capture starts from new activation
boundaries, never history import. the existing separate events task owns the subsequent migration;
its intermediate source is not a deployable release and stays out of this rollout.
the owner now authorizes immediate macbook daemon refresh and
[per-conversation baselines](decisions/0073-per-conversation-memory-baselines.md):
healthy/new histories proceed while unreadable or unstable histories stay pending.
this supersedes the earlier whole-profile capture deferrals. actual model checks for
[devbox claude-personal](issues/devbox-claude-personal-model-check.md) and
[macbook claude-personal](issues/macbook-claude-personal-model-check.md) remain
deferred until provider login. [macbook claude-work2's model check](issues/macbook-claude-work2-model-check.md)
waits for its provider quota reset. those profiles are installed; preserve every
established cut. [devbox's missing native sources](issues/devbox-work2-native-source.md)
remain unresolved. their conversations will establish cuts only after successful
native recovery; no pre-cut activity is imported or identity omitted.

#### initial rollout evidence

the following records the earlier schema-0008 rollout and its then-current
deferrals. the [per-conversation amendment](#per-conversation-capture-amendment)
below owns the subsequent releases, both online activations and completed
normal capture checks.

| step / owner | action and completion evidence |
| --- | --- |
| 1 / integration lead | source composed with current main and its security fixes; memory adr consolidated as 0070, original worktrees preserved. archive-only provider maintenance, kernel composition and selected target are published with no cognition/model upgrade; source integration is recorded in [jarvis pr 61](https://github.com/NielsdaWheelz/jarvis/pull/61) and [dev-server pr 215](https://github.com/NielsdaWheelz/dev-server/pull/215) |
| 2 / dependency writer | complete: targeted registry repairs, four actual consumer probes and full frozen `scripts/verify` pass with zero reported index findings; no suppression |
| 3 / native configuration writer | installed: the distinct claude-work2 profile uses the shared contract and existing renderer; eighteen native lanes plus jarvis. one private sharing declaration, scoped credentials and per-host bundles enable macbook/devbox capture+connect and jarvis capture only; arch disabled, nexus null |
| 4 / deployment writer | production transition passes: schema `0008`, runtime schema-read grant, validated retired-worker archival handling and exact predecessor empty drain. original columns remain unchanged after owner resumption; unfinished/unknown authority still rejects |
| 5 / service integration | installed: read-only id-mapped live state and actual cli reads under jarvis's identity reach both online gateways; source atomic-publication/write-denial proof remains applicable. same-release stock `0.160.0` host, public mapping bind and restricted-thread/service containment pass |
| 6 / integration lead | installed target with the existing release lock; temporary bridge pruned. canonical pause imported before owner discord resume. actual main reads/save, archive projection and quiet memory pass. repaired unpaused restart and the final six-table original-state comparison pass; one selected release remains |
| 7 / fleet writer + integration lead | complete within named deferrals: existing installers/private routing, all twelve sdk connections, nine model journeys, five quiet daemon adoptions and all ten eligible capture cuts. all eleven selected originals, all six tools collectively, grant denial, exact replay and outage/restart recovery pass; claude retention is installed on all six online homes |
| 8 / independent reviewer | complete: source and installed boundaries independently reviewed; temporary probes/fixtures, accepted transition snapshots and the obsolete copied worker-client credential removed after preserved-data proof. existing regression groups and operational credentials remain. arch/nexus and the five profile exceptions remain explicitly deferred |

the recorded starting snapshot is stopped/paused on `0004`; three
retired terminal-uncertain worker results already have processed resolution
messages, all paid reads/model decisions are terminal, and eleven unremembered owner rows are ineligible control/stop settlements: the
exact migration sweep predicate finds zero pending groups. the initial deployment
lacked cognition-host and memory configuration. the immutable bridge
`d9968b6b09699cf9c12d05a7b4c51b4443198192` was never resumed and is now pruned.
the first target migrated to `0008` but misclassified four finalized worker
receipts. the corrected immutable release
`a3afcdc353029a8ea82425791cdc68fd42c5f759` passed initial activation and owner resume:
activation reports three compatible archived uncertain rows, no incompatible
authority and no in-flight work. all six original table projections remained
byte-identical after migration, excluding only the deliberately retired
`message.remembered_at` column.

all twelve native profiles and both collectors are installed at that revision.
the selected central release is now `33674139c82ca5d2d7d0988de0b8ed771f1d4fd4`:
the actual unpaused restart exposed a discord-readiness race and the canonical-pause
replacement deadlock. the repaired release requires initialized canonical control
and preserves it; it retains all native/ownership/action checks. actual gateway
catch-up, authenticated https and same-release containment pass with zero restarts.
four startup-composition and nineteen real-postgres activation checks passed, were
independently reviewed, and their temporary probes/fixtures were deleted. the
collectors retain the exact qualified artifact through unchanged public contracts.
the separate stock `0.160.0` host was restarted after profile publication. actual
restricted-thread qualification sees the installed memory server disabled, with
zero tools and zero model turns. service secret/process restrictions and actual
skid reads pass on macbook/devbox; arch remains unavailable and deferred.

private https now uses the existing tailnet listener on `8443`: memory owns only
`/v1/memory` and `/v1/mcp`; skid's root and other handlers are unchanged. the failed
`443` memory handler is removed. actual authenticated requests from both hosts
return `200`, and all twelve installed sdk clients initialize and list the exact
six tools. one final installer convergence records the selected release and
active configuration digests without replacing unchanged profile files.
all ten eligible capture cuts are committed; nine native model journeys pass
save/search/open. three model-waived sdk journeys pass save/exact-open, with search
also proved on two. five quiet codex daemons now load
the six-tool catalog; macbook work2's daemon was subsequently refreshed as recorded
below. both collectors
have restarted once. the final comparison preserves all ten cuts and 4,783 existing
source identities/cuts, with no checkpoint regression, duplicates or parks. all
eleven required native conversations are captured and reopened through installed
mcp; both pre-cut prefixes stay excluded and all 39 memory-tool archive records
remain reference-only. the owner
sent discord resume; the synthetic main journey completes all six memory tools
with durable receipts and delivered output. automatic quiet dreaming appends one
attributed synthesis without a wake; serial compaction and original-state
preservation pass. [installed receipts](universal-memory.md#native-memory-installed-qualification)
record those results and the unchanged original-table projections after recovery.
[source evidence](universal-memory.md#native-memory-rollout-source-qualification)
does not waive those transition requirements.

costs: retained shared copies are available across personal/work profiles;
claude's existing 36,500-day retention consumes disk. id-mapping relies on the
qualified linux kernel/filesystem/mount implementation but avoids privilege or
permission changes to the source account. a temporary migration predecessor and
local transition snapshots are needed for this existing deployment; this adds no ongoing
backup service. dependency security fixes tighten malformed-input handling.
new tests are temporary by owner choice; existing approved regressions remain.

acceptance is observed installed behavior on macbook/devbox, not merely clean
builds. record the exact selected release, lock, migration head, host/catalogue,
active lane boundaries and loaded client results without credentials or private
bodies. an unavailable lane, unresolved original effect or failed containment
check stays visibly blocked; never reset history or broaden authority to pass.
full load/usefulness evaluation, historical import, backup/restore, nexus release,
arch activation and unrelated v2 features remain outside this rollout.

#### per-conversation capture amendment

owner-authorized follow-up, 2026-11-15. the macbook codex-work2 daemon has now
restarted once through its normal profile bootstrap. stock 0.169.0, remote-control
settings and profile/configuration bytes and inodes are unchanged. all six memory
tools load; an actual native `memory_open` reopens the synthetic verification note.
the normal collector is restored. daemon adoption is complete; capture proof
below remains separate.

| owner | delivery and proof scope |
| --- | --- |
| provider-runtime | native-archive.v3: complete identity inventory with per-entry head errors; one stable `archive_head`; ordinary native reads/event identity unchanged; upstream merge plus immutable stock-0.160-compatible artifact |
| universal-memory | one nullable baseline_error, atomic initial inventory and one-time resolution, pending ingest denial, explicit status; preserve every established cut/checkpoint/original |
| jarvis | closed baseline sync request, pending retries independent of native hints; migration 0008a after installed 0008, with unactivated 0009/0010 following it; six tools unchanged; merged work-record source passes fresh 0→0010, frozen verification and retained capture/completion checks |
| integration | merge source into main; build a memory-only patch of installed 3367413, preserving v1 and stock 0.160; qualify fresh migration and populated 0008→0008a separately; replace service and both collectors together |
| independent review | review each contract and its temporary HTTP/native/postgres proof; verify installed healthy/new capture, pending counts, exact reopening and restart preservation; remove new probes after success |

the starting installed database was 0008 and current main contains incomplete v2.
the patch therefore excludes 0009 and all v2 behavior; immutable release tags
retain compatible artifacts without standing maintenance branches. an existing
history's missing head is never an empty cut. permanently unreadable histories
can remain pending indefinitely; their earlier activity will remain absent even
if they recover later. this is the owner's accepted coverage trade-off.

earlier installed transition: release `0fc3d6444231484f1762c14c83f15d8b166b7fd6`, tag
`memory-partial-baselines-2026-11-15-r2`, activated on schema `0008a` with zero
service restarts. the same-release contained stock-0.160 host qualifies. the
stopped migration comparison preserves all 11 prior lane receipts, 4,811
conversation rows, 4,820 originals, 26 notes and 4,836 leaves exactly, including
all cuts/checkpoints. canonical resume sequence 4 is unchanged; activation
converts no actions and accepts only the three already-finalized compatible
worker records. old release 3367413 is pruned; one installed release remains.

both collectors then selected the same 0fc3d64 revision and authenticate native-archive.v3.
all thirty protected profile, instruction and private-input files retain exact
bytes, inodes and modes; no native daemon restart occurs during this replacement.
an actual native mcp open reopens the known synthetic note with its exact marker.
containment and both online worker reads pass; arch remains deferred.

macbook work2 activates at 18:49:48 utc with 192 registered conversations:
188 established and four explicit unavailable baselines. a new normal-wrapper
codex turn then captures its owner prompt and assistant reply exactly once, each
as one complete part with one leaf. the actual installed mcp reopens the exact
77-byte synthetic reply, unclipped, with matching native identity/digest and
macbook/codex-work2 provenance. capture starts at the beginning of this new
conversation, with neither baseline nor capture error. the macbook profile activation issue
is resolved; pending conversations retain the accepted individual policy.

the resumed preservation comparison also passes: all original 11 lane receipts,
4,811 conversation cuts, 4,820 originals, 26 notes and 4,836 leaves remain exact.
three prior checkpoints changed without resetting or changing a digest under
the same id. appended material is allowed; there are no duplicate parts/sequences,
incomplete events or pending conversations with originals. this snapshot does not
establish checkpoint ordering by itself.

at the earlier source merge, dev-server work2's initial inventory had not
committed after more than 100 minutes. its eventual activation and subsequent
capture-delay repair are recorded below; its normal model→capture→mcp journey
has now passed; the scheduling repair and fresh measurements follow below. restart
qualification uses the actual replacement's preserved
old cuts plus the exact frozen native/http/postgres proof for new-cut replay;
there is no second full cold-start experiment in that baseline qualification.
the owner subsequently reopened the observed
[cold-start scan delay](issues/memory-cold-start-scan.md) as the functional repair
below; broader performance/usefulness evaluation remains deferred.

#### native capture read repair

owner-authorized investigation and completion, 2026-11-15. dev-server work2's
first inventory took about 3 hours 41 minutes. it established 190 modern native
boundaries and retained 21 unavailable baselines. the collector then reread the
excluded prefixes; a new completed synthetic conversation was still undiscovered
an hour later. the one-item native paging cost, serial sweep and hourly hint
expiry explain why this is unfinished functional delivery, not a passed load test.

repair the responsible provider reader first: batch modern native items within
the existing response bounds, shrinking an oversized page at the same opaque
cursor until it fits or reaches the existing single-item refusal. retain forward
normalization, full-prefix validation, exact native identities, checkpoint checks
and unfinished-item semantics. legacy full-turn paging stays unchanged. this
reduces repeated native lineage resolution and round trips; full-prefix decoding,
small-item-page limits and fresh-baseline costs remain explicit limitations.
no scheduler framework, new cache/table, historical import or runtime upgrade is
included. adversarial review rejected reverse traversal because an oversized
later item could otherwise park a readable prefix before an unfinished barrier.

| owner | non-overlapping work |
| --- | --- |
| provider-runtime | temporary red/green protocol and native proof; bounded forward native item pages; upstream merge and qualified stock-0.160-compatible artifact |
| composition | kernel provider pins; jarvis pins/fingerprints/session manifest/lock in current main and the installed memory-only composition; frozen checks; dev-server collector pin |
| integration | update this contract and cold-start issue; install the qualified composition through existing workflows, preserving schema 0008a, canonical control, cuts and originals; no v2 activation |
| independent review | adversarial design/code/proof review, including compound boundaries, missing/changed checkpoints, unfinished-before-malformed suffixes, exact codec equivalence, oversized-page recovery and total rpc reduction |
| live qualification | finish the already-created dev-server synthetic; after repair, measure a fresh normal turn through discovery, archive and exact mcp opening; compare preserved state and retain pending histories explicitly |

use the existing temporary proof method, then delete new probes after green.
provider [pr 56](https://github.com/NielsdaWheelz/llm-calling/pull/56), kernel
[pr 28](https://github.com/NielsdaWheelz/llm-agent-kernel/pull/28), jarvis
[pr 68](https://github.com/NielsdaWheelz/jarvis/pull/68) and dev-server
[pr 217](https://github.com/NielsdaWheelz/dev-server/pull/217) are merged. installed
release 5bc88ab uses provider 6582551 and kernel 42e7ecd, preserving stock 0.160,
schema 0008a and all registry versions. 27 temporary protocol cases per dependency
composition, full required checks and independent review pass. an isolated real
stock-0.169 fixture preserved exact events/digests while reducing total calls,
including initialization/reconnects, from 261 to 23. this is not a fleet latency
claim. installation preserves all 13 lanes, 5,249 conversations, 11,109 originals,
28 notes and 11,127 leaves exactly, with canonical resume sequence 4 unchanged.

#### collector discovery and fairness repair

the repaired reader's normal journey exposed the separate scheduling defect.
collectors restarted at 23:39 utc; fresh normal work2 turns completed at 23:44:53
on macbook and 23:44:54 on dev-server. neither was registered at 23:46:22. macbook
was still reading 1,963 of 2,184 old claude-work conversations before later homes;
dev-server had read 87 of 190 old work2 prefixes. a faster native reader does not
make discovery independent of a full host sweep.

change only the existing collector and its contract: complete every active home's
metadata/sync phase first, then alternate recent ready activity and oldest waiting
work within a cooperative 30-second content slice. retain first-seen/last-attempt
age and one alternation flag; failures remain eligible and cannot starve older
work. one operation per conversation per discovery cycle replaces the former
whole-fleet round requirement. pending-head repair is one operation; capture uses
its fresh canonical receipt on a later cycle. a permanent park is not caught-up
success and must not suppress an explicit retry with an unchanged native hint.
at most one indivisible pending-lane activation follows active work, with a
rotating index that advances on failure. no concurrent capture, durable queue,
new schema/api, shortened validation or longer revisit interval is introduced.

trade-offs: more metadata requests and slower background drainage buy prompt
new/changed discovery; one native operation, listing or activation can still
exceed the slice. the existing 60-second post-discovery target is not a hard
wall-clock guarantee. measure terminal→discovery and discovery→capture/open
separately, and do not hide remaining delay behind the distinction.

implementation owns collector code and deterministic red/green fairness checks;
an independent reviewer owns real http/postgres/native-file proof and adversarial
review. root owns this contract and installed replacement. the existing live
worker owns the three already-created synthetics and subsequent fresh proof;
never duplicate uncertain launches. preserve all prior cuts/originals through the
memory-only release and keep v2 unactivated. qualify hot/cold/pending fairness,
metadata-before-content, failure/retry eligibility and exact checkpoint reuse,
then delete only the new probes. broader usefulness/load evaluation stays deferred.

source qualification passes in both current-main and installed-compatible
compositions: 12 temporary scheduling cases, retained capture/retry and full
`scripts/verify`. an independent real authenticated http/runtime-role postgres/
native-claude-file probe reproduces two predecessor failures and passes both
repairs: head recovery gets one quantum with the recovery gap excluded; explicit
retry works with an unchanged native hint. restart preserves exact cuts,
checkpoints and originals without duplicates. independent source/test/contract
review passes. the new probes and disposable databases are removed after this
evidence; installed replacement and fresh latency proof are complete.

jarvis pr 69 and dev-server pr 218 are merged. central and both online collectors
run b6cf4b3 on unchanged schema 0008a and stock cognition 0.160; no v2 activation.
normal fresh work2 turns on macbook/dev-server reach stored archive receipts in
67.49/64.63 seconds after model completion, with exact native mcp opening and
shared search. preserved-state comparisons pass before/after replacement and
after live capture. all selected source changes are merged; compatible artifacts
remain immutable tags, without maintenance branches. the owning
[installed evidence](universal-memory.md#installed-collector-repair-qualification)
records observation bounds, original preservation and cleanup.

no further implementation is outstanding for this online rollout. 21 dev-server
missing-source histories and [two unresolved macbook baselines](issues/macbook-work2-pending-baselines.md)
remain explicit coverage gaps under the approved healthy/new policy. arch, nexus,
three claude model checks and the other named deferrals remain outside completion;
initial baseline/long-operation latency remains documented, with no broader load
claim.

### memory and native-main integration

these tracks share invocation identity, source publication, library pins and
composition, not a new agent layer. coordinate shared-file changes and serialize
their release cutovers; do not maintain two implementations to support arbitrary
merge order.

- o4/o5 preserve a host-owned accepted-invocation position BEFORE every callback
  dispatch and a recorded result BEFORE replying. this supplies internal note
  idempotency and search recovery. raw native call ids are not durable effect ids.
- canonical messages/callback receipts commit before archive projection. immutable
  message/attempt eligibility bits and stable message/call/reply ids recover missing
  projections without another journal or source-time cutoff. one ongoing jarvis
  conversation replaces settlement groups; memory-tool prose stays reference-only.
  fresh runner calls use new leases, retaining entered-effect dispatchers. one
  publication adapter consumes current native evidence, never the retired step loop.
- memory retains current write authority, including main's full-plan canonical-note
  exception: action-resolution turns can save without owner grounding. scheduled
  turns remain read-only. o6 extends capabilities to scheduled/new origins outside
  that full plan; amend affected grants there, never silently in m4.
- native main retains original attempt, invocation and action/read evidence.
  compactor/dreamer inference and dreamer read receipts are disposable; the
  completed nodes, synthesis notes and progress commit in the memory store.
- memory adds six tables to the native nine: fifteen before v2 additions. the contract defines
  leaf mapping, completed nodes and singleton progress beside the three archive
  tables. work and attachments bring current source to seventeen at `0011`;
  the event cursor remains later. sequence actual migrations and revalidate owner permits and
  definition revisions against the deployed predecessor, preserving canonical rows.

## subsequent product slices

these have focused contracts. notes, attachments and event sources are adopted
v2 work. f1 selects only mail/calendar/web read completion; broader search,
dreamer context and budget remain later scoped amendments.
none is a prerequisite for delegation or initial universal memory.

### private notes repository and rolodex

the [slice 4 spec](private-notes-and-rolodex.md) settles one persistent ordinary
private `NielsdaWheelz/jarvis-notes` checkout: native read/create/edit/move/delete,
search, execution and agent-chosen git. a brief readme starts a general workspace
for documents, people/context, helpers, components and visual/interactive files.
no imposed folder tree, notes service, schema, sync worker or hosting integration.

main becomes a trusted native domain; conversational connector consent governs
connector calls only. this replaces the earlier confined-access direction.
kernel/provider mixed native-callback support and borrowed cwd lifecycle are
implemented upstream work, supplied by the qualified pins recorded in slice 4. adr 0071 adopts
the authority amendment; separate temporary host/candidate proof precedes final
production cutover. preserve isolated roles, canonical callbacks and internal
cognition exclusion. no production mapping/unit/bootstrap changes in this slice.
ordinary git history/relative links have no synchronization or stable-link
guarantee. memories/work/documents link without mirroring current task state.

### complete and continuable searches

the [earlier proposal](complete-and-continuable-searches.md) remains reference
material. adr 0075 selects only mail/calendar/web completion for f1: bounded
continuation, full available supported text, correct reply routing and fresh
deliberate observations. main composes scope/depth/progress through ordinary
tools/context; original callback receipts and paid-read barriers remain intact.
provider limits, live-source changes and unavailable content remain explicit.
there is no snapshot promise, compulsory exhaustive scan or scan controller.

the [focused contract](mail-calendar-web-reads.md) replaces clipped thread reads
with landed manifests and explicit message/part chunks. consume merged event
profile/refresh interfaces; the older selected-domain schemas are superseded. memory ranking, maps and worker inventory/retained-history expansion
remain later work. native notes stay ordinary commands. binary originals belong
to attachments; inbox housekeeping, new invitation responses and outgoing files
are not part of f1.

### event sources, suggestions and recurring work

[contract](event-sources-and-recurring-work.md) owns the accepted v2 target:
new incoming mail including archived mail; all readable calendar changes and
approximate upcoming attention; one-minute polling; simple recurring schedules
with coalesced missed runs; and an ordinary daily 09:00 review todo.
one new table holds source cursors; the work table owns all one-time/repeated
wakes. one poll task reuses the existing notify/wait pattern while work timers,
worker waits and delivery remain independent. the source-audited slice 6 contract
owns closed progress/payload/tool schemas, resumable gmail prefixes, fixed calendar
sync queries, shared-token repair and account-qualified echo receipts. consume
attachment's actual merged profile/fresh-read helpers; do not overwrite its work.
three temporary integration/live journeys get designer/adversarial review,
red/green/refactor and probe deletion. source and the separate combined
migration/native candidate are qualified;
final production activation is separate.

trusted internal producers can use the same append with actual source identity.
selected dream wakes remain deferred; memory's quiet completion is unchanged.
no new suggestion generator, controller or per-work execution gate. main chooses
action, notification or nothing.
disable/cancel stops future publication; already published work remains ordinary
main context. implement source adapters independently of the later work projection.

### dreamer work context

outside this v2 cut, the [contract](dreamer-work-context.md) proposes one shared work query and a dated,
bounded prompt section after m3 and o7. doing now, blocked and next up guide
attention; omit backlog and disclose record/content omissions. freeze context
for one invocation; later attempts read current state. preserve personal,
scientific and creative dreaming and m3's settled evidence/output contract.
main rechecks current work before dependent action. no new tool, table,
scheduler or work-triggered dream. daily review belongs to ordinary scheduled
todos; selected-note delivery is deferred. query failure uses the ordinary dream
failure policy. neither amendment is part of the separate memory pr.

### attachments and original storage

the [implemented contract](attachments-and-durable-originals.md#implementation-evidence)
qualifies automatic owner discord capture, main-selected gmail retention,
indefinite private r2 originals
and deletion with conversational consent. the source builds on audited merged
`d93b84d`: atomic caption/host-manifest ingress, one metadata table, two narrow
gmail discovery reads, three attachment tools, storage-specific recovery and
fresh native paths. slice 4 supplies qualified native access; source and a
separate private-storage/native-host candidate are qualified. the linked evidence
owns actual versus controlled paths and resource disposition. no reader ui,
extraction pipeline, full search overhaul or multimodal wire redesign.

its file-ownership boundaries separate ingress, source/storage, composition and
host setup. temporary red/green/refactor journeys cover discord/storage, selected
gmail and actual native reading, with content design and adversarial review at
each stage, then probe deletion. migration `0011` follows work's `0010`.
production activation stays at final v2 cutover.

expiring links, internal extraction text and derivatives are not durable
originals. notes/memory keep references/published observations; binaries stay
outside git. deletion removes our original/cache, not source copies or prior
memory. budget accounting and outgoing file sharing remain separate.

### budget integration

the [contract](budget-integration.md) follows the owner-requested independent
audit of freshly pulled budget-app `7b7a9c2`. its ledger, evidence inbox,
reports, revision checks and durable command api already exist. jarvis adds typed
tools and uses those owners; no competing financial table, arithmetic or importer.

the owner selected full automatic bookkeeping, including plans, manual entries,
corrections/voids and evidence repairs, plus attachment-compatible formats and
100-mib originals. budget broadens its existing write credential, exposes its
shared planner calculation and replaces bytea/base64 with independent private r2
originals. payments, bank access and currency conversion stay outside this slice.
budget originals survive jarvis attachment deletion. exact command replay and
current financial truth remain distinct; preserve receipts and revisions.

### deferred from universal memory

separately specify [historical imports](issues/memory-historical-import.md)
(pre-activation lanes, legacy codex homes,
old canonical jarvis messages and old-note lineage), including deduplication,
provenance, extraction cost and order; nexus historical import;
broader [usefulness/load evaluation](issues/memory-usefulness-evaluation.md); and disabling or
reconciling native automatic memories. retained native history preserves an import
opportunity, not proof of capture. preserve existing messages/notes in the meantime.

forgetting/exclusion is outside the prototype and is not promised v2 work.
automatic external context injection was rejected, not deferred; future push
would require a new authority design. learned reranking may be reconsidered only
from measured retrieval failures; keep one current ranking path.

browser control, new credential handling/brokering, interactive hosting/presentation,
credential-entry forms and television integration are explicitly deferred
from v2. ordinary repo files can already include runnable helpers, components
and self-contained visualizations; they use existing repository access.
progress, blockers and completed results are not deferred features: they are
ordinary main behavior, with no separate subsystem.

other earlier ideas remain uncommitted/outside this delivery: extra discord
channels, api-backed cognition, a separate application program-execution api, selected
onepassword access, jarvis-to-nexus product integration, android and generic
computer use. nexus's shared provider/kernel contract work remains in o3–o4.
revisit other ideas only for an observed need with their own contract. notes do
not imply a google-drive integration.

## decisions and verification

remaining decisions have owners; do not reopen settled broad autonomy, automatic
notes, cloudflare originals, nonblocking waits, freeform delegation or latest owner
intent merely because their implementation is incomplete.

| feature or cutover | remaining decision / evidence owner |
| --- | --- |
| native/worker activation | [installed journey](runtime-reliability-and-integration.md#installed-lineage-and-stopped-restart-window) verifies the selected host/application, worker and physical delivery |
| o6 | [contract](one-main-events.md) qualified. main admitted and settled owner and host inputs through the installed restart |
| o7 | the [installed cutover](operations.md#supervised-todo-setup) accounted for prior reminders. the real journey consumed the fixture todo wake and closed the same row |
| o8–o9 | after restart main read the completed checker's report from the same installed skid terminal and consumed the wait timeout. useful execution on `claude-work` remains owner-deferred. [evidence](runtime-reliability-and-integration.md#restart-catch-up-and-original-send) |
| new event sources | installed fixture mail arrival and calendar attention qualified. [conversational source control](issues/event-sources-installed-cutover.md) remains open |
| m1–m5 | source and online jarvis/native rollout complete with the named [profile deferrals](#memory-installed-rollout). nexus waits for its next release |
| notes | production checkout, note and git-state inspection qualified. a genuine [helper/git task](issues/private-workspace-installed-cutover.md) remains open |
| f1 reads | [source and candidate](mail-calendar-web-reads.md#implementation-evidence) qualified. selected production reads passed in f2. broader search remains deferred |
| f2 reliability/integration | the [contract and evidence](runtime-reliability-and-integration.md#implementation-evidence) owns the isolated faults, actual installed journey and final reset |
| f3 model/runtime | [source and candidate](subscription-model-runtime.md#implementation-evidence) qualified. f2 records installed main astra/max, memory sol/xhigh and the native-child and skid choices |
| attachments | [source and candidate](attachments-and-durable-originals.md#implementation-evidence) qualified. the actual fixture pdf was retained, reopened across restart and removed at the stopped reset |
| budget | owner choices settled in [contract](budget-integration.md); budget authority/storage/calculation handoff, jarvis tool/recovery adoption and three focused proof journeys remain |

[adr 0046](decisions/0046-reset-testing.md) remains in force. run `scripts/verify`
for static/build checks; do not claim behavioral acceptance from it. native and
worker work completed their explicitly authorized temporary acceptance under
adrs 0064/0065. memory's scoped exception permits its small capture/retry and
memory-completion groups plus focused synthetic live boundary evidence. future
features specify their own proportionate verification scope with the owning
contract; the standing testing redesign remains separate. other repos follow
their own rules.
no old suite, replacement framework or recurring fleet qualification is added here.

integrated acceptance journeys, when their owning verification is authorized:

- one client's new conversation/direct note becomes searchable from another host;
  capture/compression/dreaming interruptions do not lose or duplicate committed work.
- jarvis delegates substantial research through skid, stays responsive, receives
  one asynchronous observation after restart and distinguishes evidence from success.
- a native connection is lost: fence stale callbacks, reconcile recorded connector effects and recover
  requests with original receipts; fresh reasoning sees latest owner intent,
  including semantic stop, without repeating unknown effects.
- an email or trusted internal event may create useful work without forged owner
  input; irrelevant input creates no make-work; consequential connector communication still
  uses conversational consent.
- main edits useful project/person documents through native tools and chooses
  ordinary git operations; checkout/dirty changes survive lease loss and native
  effects are inspected rather than blindly replayed.
- main traverses beyond old item/candidate horizons and reads the last text chunk
  across turns; source changes/provider limits are explicit and original paid-read
  uncertainty is preserved.
- project review reflects real active work/estimates, named blockers with daily
  review, at most three next priorities and completed work outside the active view.
- a receipt survives as an addressable original and becomes one source-linked
  expense through the budget app, including repeated delivery and correction.

implement adopted slices through exact pins and removal of old paths; adopt
later amendments separately. inspect shared-library impact. qualify transport, then effect durability,
then authority, then restart/stop behavior. preserve existing user work. stop
admission and reconcile outstanding effects before incompatible pins/migrations;
code rollback never reverses external effects or new canonical data. use the
operations runbook and the memory contract's exact cutover rules.

## reconciliation evidence

2026-10-04: clean jarvis/kernel/tools/skid/dev-server main checkouts were pulled
with `--ff-only` and were current. provider-runtime's clean maintenance branch
was preserved; fetched `origin/main` supplied its current contract/source evidence.
jarvis is `f3b4dc3`, skid `ab9e0ac`, kernel `465470e`, tools `593de5d`, provider
main `09c5203` and dev-server `3080886`. qualified runtime pins remain those in
jarvis's lockfile; naming a newer merge commit does not authorize an upgrade.

the canonical skid checkout is `skidbladnir`; the old `skid-v1` path and v0.10.7
observations are historical. codapt's earlier six-hour behavior supplied design
evidence, not the current native contract. current acceptance/artifact identities
belong in the owning handoffs and issue records. this reconciliation changes
documentation only and claims no provider, database, fleet or service operation.

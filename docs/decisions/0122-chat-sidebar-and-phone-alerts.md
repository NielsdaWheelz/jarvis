# adr 0122. give the sidebar to chat and simplify phone alerts

the [daybook](0127-the-daybook.md#the-page) gives the chat rail a 1.5rem reading gutter.

**implemented · november 26, 2026 · installed acceptance pending**

the installed web shell at `22e9d2a` has a workspace title above chat, todos
and phone controls. [adr 0117](0117-inline-todo-viewer.md) moved todos and
their records into the viewer. on `main` at `eb5fe71`, a chat title and a row
for phone alerts survive. the two rows measured 119 css pixels in the installed
layout and 108 on main in local chromium with sample data. the owner wants
that space for reading. the browser's “one phone is connected” reports a
stored push address. it cannot establish that a notification reached the phone.

## web conversation

- in ordinary desktop use, start the sidebar with the transcript, including
  “earlier messages” when available. remove the visible title and navigation
  row, their reserved space and both dividers. keep the named conversation
  landmark, reading gutter, approvals and anchored composer. the viewer
  header owns the single todos control. todo links inside messages still
  open their addressed row.
- on narrow web, the viewer's “chat” button opens the full-screen conversation.
  show one compact, keyboard-accessible “back” button above the transcript.
  the same control appears on desktop when reading an exact message. otherwise
  the transcript starts at the top even after resizing from a phone layout.
- reuse the shell's history. back from a warm visit restores its actual origin,
  including the file page or expanded todo and the reading position. the tab
  keeps the current draft, including edits made while chat was open. back
  from a cold `/m/{id}` opens home at `/`. browser back retains normal history
  behavior. opening chat by keyboard focuses its back control. escape dismisses
  narrow chat. return focus to the originating control or restored reading
  target without scrolling it away. [home addresses](0115-web-home-address.md) ·
  [todo return](0117-inline-todo-viewer.md#addresses-and-return)

## android enrollment

remove the web phone disclosure, the android “alerts” destination, its global
status banner and both manual disconnect controls. the accepted tradeoff is
that a lost phone may continue receiving generic alerts until replaced or its
address expires. clearing a push address never revoked the jarvis login.
this supersedes the manual disconnect and status presentation in
[adr 0105](0105-native-android.md#d-alerts-and-registration).

- **first use or replacement.** on the ordinary signed-in native home, offer
  “enable alerts on this phone” as an optional inline action while this
  installation is unenrolled. remember a home visit through resolution and
  activity recreation. show the action on the resolved native home, including
  the native page visible on returning from a publication's browser tab. an
  exact link to that same publication is a different visit. keep chat, exact
  links, share and composing free of setup prompts. the owner can return home
  to enable later. if another installation holds the address, say that
  enabling here moves future alerts to this phone. only an explicit tap can
  claim an empty address or replace the existing phone.
- **after enrollment.** verified enrollment removes the setup action. the
  existing android permission and reply, question and scheduled-check channels
  govern display. respect any combination of mutes, including all alerts off.
  toggling them leaves the registration intact. reserve the permission prompt
  for a setup gesture. [android notification controls](https://developer.android.com/design/ui/mobile/guides/home-screen/notifications)
- **repair.** keep a failed setup and its next action together on home. offer
  sign-in for expired access, android notification settings when permission
  is blocked, or retry after a failed registration. a denied prompt stays
  quiet on resume. after a confirmed loss of enrollment the same home action
  can enroll again. if an ordinary read fails, retry quietly on the next home
  visit or resume. if an explicit setup attempt was interrupted, offer retry
  there and read back the slot before attempting another change. normal
  reading continues while enrollment is unknown.

## service and upgrade

retain authenticated `GET` and generation-checked `PUT /api/push/phone`,
the strong etag and `no-transform`. android needs these for enrollment,
address rotation and readback after a lost response. keep the installation id
and address hash check. an sdk address stored locally is insufficient evidence
of enrollment. refreshes on resume and firebase callbacks can update only
this installation's active address. bind the setup tap to the slot generation
shown, including across the android permission prompt and firebase registration.
on conflict or lost acknowledgement, a read matching this installation and
address settles success. show a changed occupant and require a fresh tap
before claiming the new generation. [android registration](../../android/app/src/main/java/dev/niels/jarvis/Push.kt) ·
[phone slot](../../src/jarvis/phone.py)

retire the http `DELETE` and its manual clearing branch. a signed-in,
same-origin request using the retired method gets 405 and leaves the slot
intact. keep the sender's internal clearing operation for firebase
`UNREGISTERED`, conditional on the generation actually attempted. ordinary
replies and questions stay pending until provider acceptance. scheduled
workspace hints keep their existing single opportunity to deliver. an
already submitted push can still reach the previous phone.
[delivery paths](../../src/jarvis/home_notices.py)

an in-place upgrade uses the existing installation id, firebase preferences
and server slot. a matching enrollment stays quiet and usable. an empty or
different slot requires explicit enrollment. preserve pending notices,
channel choices and sign-in. this cut needs no database or slot-file migration.

## acceptance

1. on desktop, verify the transcript starts at the top of a normal sidebar.
   open a todo from chat, follow a linked reply, then go back to the same row
   and focus. on narrow web, open chat over a file page with a draft, use back
   and escape on successive visits, and verify the page and draft. check a cold
   message link, keyboard focus and resizing to desktop with chat open. the
   web shell makes zero phone-management requests.
2. on android, skip setup, return home and enroll. try both a todos home and
   a published home. after closing the publication's browser and recreating
   the activity, setup is reachable on the home visit. a cold link to the
   same publication opens only that publication. exercise an unavailable first
   read, permission denial, settings and explicit retry. upgrade a previously
   enrolled installation in place. mute one channel and then all channels, resume and re-enable
   them. there should be no enrollment prompt or address change on the
   enrolled phone. check an ordinary notification opens its exact reply.
3. use an isolated slot for replacement and failure cases. lose a successful
   enrollment response and recover by readback. change the occupant while
   setup is awaiting permission and verify the old tap cannot take it over.
   replace phone a with b, then deliver a late callback and an old-generation
   unregistered response for a.
   b stays selected. verify current-generation invalidation, explicit repair,
   and a retired client disconnect returning 405 without changing the slot.

the [implementation plan](../implementation-plan.md#chat-sidebar-and-phone-alerts)
owns sequence and rollout.

## qualification on macbook

the web shell uses the existing browser history entries. a return restores a
chat link only when coming back from the visit it opened, including when two
links have the same address. the selected canvas stays mounted through chat.
this preserves the draft and live reading position with no second navigation
stack. a cold message returns to `/` and retains the tab's resolved home.

the android home visit saves its resolved address. an exact visit to that
address carries its own navigation entry. interrupted setup persists a repair
hint and needs another tap once the slot is known. the permission result itself
carries no claim across activity destruction. firebase publishes its verified
address before waiting on slot reads or writes. the service owns the slot
generation and rejects a claim after a changed generation.

the packaged predecessor failed the retired delete checks. the wheel from
`130c938a5cf5d37c03df6a6969f96ce55e9dbf7d` passed 58 product checks and two
fixture teardown checks over loopback http with postgresql 16 at schema
`0026`. a controlled firebase transport covered current and stale
invalidation, retry of pending notices, and single-attempt workspace hints.
a dropped http response was recovered by installation and address hash.

chromium and webkit passed 30 checks against the packaged frontend. the
checks exercised desktop and narrow back, exact todo and message links,
browser traversal, keyboard focus, mail editor cancellation, draft and file
position, publication scroll and resize. the browser made zero phone
management requests. the final wheel's assets match the exercised bytes.

on an isolated android 35 emulator, the predecessor let an old permission
gesture replace an intervening phone. the candidate fenced this through the
permission dialog and delayed sdk callback. it recovered lost responses,
failed reads and interrupted setup, retained an existing installation on
upgrade, and refreshed its own address under system mutes. a controlled
incoming message became a system notification and opened the exact reply on
tap. a real chrome custom tab returned to the saved native home after process
recreation. warm and cold exact publication links offered no setup.

the exact source passed `scripts/verify`. android v7 was built locally and
verified with the v6 package identity and signer. the signed install and real
firebase journey on the owner's handset remain in the
[installed check](../issues/chat-sidebar-phone-alerts-installed.md).

evidence is under `~/.local/state/jarvis/qualification/adr0122/` and
`~/.local/state/jarvis/qualification/adr0122-android-AR3osv/`. the service
and browser ran the same wheel, sha-256
`5feb30575aa44b58efd832100cee07a2b158b4c8cb25e4dd7caf64d962203101`.
the local signed apk has sha-256
`8133a824b490d744059be1fe44b9a9c8b0e27724df0c33d3ff80a17c7d4097ea`.
the detached receipt and the client cleanup records cover the removed probes
and isolated resources.

### drive integration

the integrated revision `953f6c21d3ad1152442e9ddbc2a9f99530e25642`
includes [adr 0120](0120-drive-files.md). chat and exact messages preserve the
drive viewer visit underneath them. back preserves the loaded document and
list. leaving the viewer ends its outstanding work. separate visits to a
shared file-list address keep their own selectors.

sixteen chromium and webkit checks covered the packaged reader, including
rendered pdf pages, draft and scroll retention, back focus, list navigation
and late responses. the android build and nine isolated checks covered drive
and the home-only enrollment surface, including actual chrome return and the
matched drive request header. the packaged service passed 25 loopback checks
covering the combined shell, phone generation and retired method, and the
drive viewer fence. `scripts/verify` passed. these checks retain the existing
installed acceptance boundary.

evidence is under `~/.local/state/jarvis/qualification/adr0122/` in
`integration/` and `drive-merge.3nizJy/`, and under
`~/.local/state/jarvis/qualification/adr0122-android-drive-merge-2IS9Iu9o/`.
the rehearsals removed their temporary probes and fixtures.

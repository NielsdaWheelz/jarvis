# adr 0122. give the sidebar to chat and simplify phone alerts

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

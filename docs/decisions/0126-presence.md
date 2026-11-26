# adr 0126. show when jarvis is working

**implemented · 26 november 2026 · installed acceptance open.**

this amends the following contracts.

- client freshness in [0087](0087-private-web-home.md), [0105](0105-native-android.md)
  and [0122](0122-chat-sidebar-and-phone-alerts.md);
- [0108](0108-codex-quota-standby.md)'s rule against a new client wire for
  standby. presence reports the standby and its reported reset, once per change,
  never as a message;
- the activity-signal sentence in spec §4.2;
- one sentence of [0125](0125-new-shown-and-owed.md) (new, shown and owed): its drying mark stops being
  the application's only animation.

0125 keeps the red, the favicon, arrival announcements, hidden-tab reads and
every rule about what moves the transcript. the owner approved this design and
its [study](../research/presence-study.html) on 26 november 2026. where they
differ, this text governs.

## what is wrong today

after a send, the web shell refreshes once and shows the owner's message. from
then until a reply arrives, nothing says whether jarvis is working, queued
behind other work, out of quota or paused. android then opens the owner's own
message. silent work from mail, reminders, scheduled checks and worker results
is invisible until it speaks, or it ends without a trace.

the service already records most of the facts: the active `native_attempt`,
its `native_input_delivery` rows, unanswered `native_invocation` rows and the
action ledger. the rest is in memory: the current stock tool, the last main
deferral and live google choices.
[service loop](../../src/jarvis/service.py) · [native runner](../../src/jarvis/native_runtime.py)

## principles

1. **only the process doing the work reports it.** uvicorn serves the home app
   inside the worker process that runs main, with no extra workers
   ([cli](../../src/jarvis/cli.py)). a new process starts with an empty presence
   record. a leftover attempt row therefore never reads as work, and the first
   unpaused drain fences it. if the process dies, the read dies with it and the client
   goes stale.
2. **motion is evidence.** each successful read that confirms work produces one
   beat. nothing loops. when reads stop, motion stops.
   - a beat means "work is armed in the live serving process". it does not mean
     tokens are flowing: the kernel gives the host tool calls, stock tool use,
     children and terminals, but no reasoning events
     (`llm_agent_kernel.native.run_native`).
   - presence therefore makes no "stalled" claim. elapsed time is the honest
     measure of a long turn.
3. **unknown is shown as unknown.** a client that cannot confirm the state
   removes the mark and says when it last heard. it never animates on stale data.
4. **category, never content.** presence names a trigger and a tool family. it
   never carries a subject, sender, event title, query, file name or progress
   text. progress the model chooses to say already lands in chat.
5. **presence is not conversation.** it creates no chat row, notice or push. it
   settles and grants nothing. memory compaction and dreaming are never shown,
   because spec §4.4 says dreaming is not a user-facing turn.
6. **presence text never takes layout space.** navigation owns the header's
   geometry, including the destinations adr 0123 adds beside the wordmark.

## what the owner sees

the mark is a point set after the wordmark like a full stop: `jarvis.`. its
cell keeps its width in every state, including idle and stale, so nothing
beside it moves when it appears.

| condition | mark | words on the rule | tab title while visible |
|---|---|---|---|
| idle | none | none | `jarvis` |
| received | accent ring, still | none (the tail says it) | `received · jarvis` |
| working for the owner | accent point, one beat and ink bloom per confirmation | on hover or focus only | `reading mail · jarvis` |
| working on its own, or workers running | near-full grey point, one beat and grey echo per confirmation | always: `from mail · checking the calendar`, `2 workers running` | `· jarvis` |
| owed | `--rubric` `¶`, still; activating it goes to the next owed message or open google choice | `waiting on you` | `¶ waiting on you · jarvis` |
| out of quota, or model unreachable | muted ring, still | `out of quota · reset reported 14:10`, `can't reach the model`, with `· next try 14:10` only when known | `out of quota · jarvis` |
| retrying | muted ring, still | `next try 14:10` | `retrying · jarvis` |
| paused | muted ring, still | `paused`, or `pausing` while work drains | `paused · jarvis` |
| stale | none; wordmark fades to `--muted` over 600 ms | `last heard 14:02` | `offline · jarvis` |

states differ first by shape, then size, then motion, then colour. they read
across a room and under deuteranopia.

- green means "for you". silent work never uses it.
- `--rubric` keeps 0125's meaning, owed, and its values.
- loudness runs from owed, to working for the owner, to working on its own, to
  idle. no change may invert that order.
- header precedence: paused, owed, working for the owner, standby or retrying,
  working on its own or workers, received, idle.
- while the tab is hidden, the title is `jarvis`. it makes no claim it cannot
  refresh. 0125's favicon reports new and owed replies to a hidden tab.

**the rule legend.** words are written on the header's bottom hairline at the
wordmark's inline start, on a small paper-coloured patch in muted italic serif.
they are positioned absolutely, anchored to the header bar rather than the
wordmark. tabs and destinations never move, and wrapped destination rows cannot
collide. the patch overhangs the content below by about half a line. owner work
shows its words only on hover or focus, because the chat tail already says them.

**the chat tail.** while presence reports owner work in progress, a provisional
jarvis row sits at the end of the transcript, after any progress rows.

- its stamp reads `jarvis`. the time slot is blank, then shows elapsed `m:ss`
  in tabular figures from 20 s.
- below it are the tail mark and the words, in muted italic serif. the
  provisional is italic and the final is roman.
- words crossfade (140 ms out, 220 ms in).
- the tail covers received, working, standby, retrying and paused.
- owed is not a tail state. the reply that asks carries 0125's `needs a reply`.

an existing tail keeps its words and freezes its elapsed time from a
`you: null` presence read until the chat read ordered after it. a failed
paired chat read applies the stale rule to the tail.

when the reply arrives it takes the tail's place. the words fade over 160 ms
while the prose fades in over 280 ms in the same grid cell. the elapsed time
becomes the reply's time, and nothing above moves. if the owner's message
settles with no visible reply, the tail fades over 200 ms. 0125's movement rules
govern scrolling, with the tail counted as part of the bottom.

**words.** lowercase, terse, never cute.

| activity (family · mode) | words |
|---|---|
| none | thinking |
| gmail · read / write | reading mail / writing mail |
| calendar · read / write | checking the calendar / updating the calendar |
| drive or docs · read / write | reading drive / writing to drive |
| maps | checking maps |
| memory · read / write | searching memory / taking a note |
| web (journalled or stock) | reading the web |
| work · read / write | checking todos / updating todos |
| agent | working with a worker |
| receipt | rereading a source |
| stock shell | running a command |
| anything else | working |

- **silent work** prefixes its trigger: `from mail`, `from your todos`,
  `a result came back`, `recovering`.
- **received:** the label for `queued`. it reads `received · after current work`
  when other work runs first.

**send.** keep 0116's submission and recovery contract and the existing
`refresh()` after acceptance.

- `#receipt` owns transport only. it shows `sending…` only after 400 ms.
- on acceptance it says nothing. `received` lives in the tail.
- presence announces only `received.` and the first entry into standby,
  retrying or paused. arrivals and owed belong to 0125's announcer. activity,
  elapsed time, beats, silent work and queue counts are never announced.
- the mark is a button labelled with the full sentence, e.g. "jarvis is reading
  mail for you". the same text describes the wordmark.

**motion.** this amends 0125's "only animation" rule. presence beats are the
second motion. all motion uses transform and opacity.

- **owner beat:** 1200 ms. scale 1 → 1.34 at 11% on `cubic-bezier(.2,0,0,1)`,
  then back on `cubic-bezier(.3,0,.1,1)`.
- **owner bloom:** 1800 ms. scale 1 → 4.4 and opacity .85 → 0 on
  `cubic-bezier(.15,.6,.25,1)`.
- **silent beat:** 1600 ms. scale .86 → 1.06 at 14%.
- **silent echo:** 2000 ms. scale 1 → 3 and opacity .5 → 0.
- **restarting a beat:** alternate two identical keyframe names so no reflow is
  needed.
- **never animated:** layout, the owner's own scroll, the title, message text
  and elapsed digits.
- **reduced motion** (`prefers-reduced-motion`, android animator scale 0):
  - owner work dips opacity 1 → .45 → 1 over 900 ms per confirmation.
  - silent work is static.
  - crossfades take 120 ms.

**type.** self-host latin subsets of Cormorant Garamond regular and italic
(SIL OFL, licence beside the files) under `static/home/fonts/`. android bundles
the same faces in `res/font`.

**narrow web.** with chat closed, the workspace header carries the mark and
legend. in 0122's full-screen chat, the mark and legend sit at the inline end of
the compact back row.

**android.**

- **header.** a serif `jarvis` with the mark opens the top destination row, and
  the legend sits on the divider beneath it.
- **the mark.** a `Canvas` driven by a confirmation counter that the poller
  increments. a `LaunchedEffect` keyed on the counter runs the beat through
  `Animatable`, and a parallel `Animatable` runs the bloom.
- **no `InfiniteTransition`.** a loop is the lie this design forbids.
- **shapes.** switch with `Crossfade(tween(240))`.
- **tail.** shown in the conversation. the handoff uses `AnimatedContent`.
- **after a receipt.** open the conversation at its end, not the owner's own
  message (`Home.kt`). this matches 0125's "sending scrolls to the bottom".
- **no ongoing notification.** it would show the phone as busy while a server
  does the work.

## state and derivation

a new `presence.py` owns one in-memory record. `JarvisService` owns the
instance and `home_http` reads it.

| field | set | cleared |
|---|---|---|
| `attempt_id` | when the runner arms an attempt | in the `finally` of `_drain` that clears `_active_cancellation`. a `no_work` pass never sets it. |
| `effects` | an action id on entry to `execute_recorded_action` when `decided_at` is set ([write dispatch](../../src/jarvis/write_dispatch.py)). approved writes run on a detached task started by `approval.respond`, which can outlive its attempt. | in that function's `finally` |
| `stock` | open stock calls keyed by `tool_call_id` | on each call's `completed` phase, or when the attempt ends |
| `deferral` | replaced by every run outcome, null unless every cohort was deferred | when an attempt arms |

**stock hook.** the runner always passes one synchronous `on_stock_tool`. it
updates `stock` and forwards to the stock observation writer only when memory
admits jarvis.

**deferral.** `NativeRunOutcome` today carries only `status` and `retry_at`. the
route selector's reason is dropped, and `blocked` also covers causes that are
not deferrals.

- add `deferral: DeferredRoute | None` to the outcome. report the first cohort
  deferred in the pass, only when every cohort was deferred. a cohort abandoned
  after a failed opening counts as deferred, with reason `unavailable` and null
  `until`.
- `RouteSelector` keeps the last `observe_personal` result, whether an allowance
  or a deferral ([kernel](../../src/jarvis/kernel.py)).
- the reason is `quota` when either of these holds:
  - personal is `included_exhausted`, `credits_available` or
    `workspace_limit`, and paid is deferred or absent;
  - paid reports `prepaid_depleted`.
- every other reason is `unavailable`.
- `until` is the personal `reset_at` only when personal exhaustion caused that
  cohort's deferral. otherwise it is null.

**the read.** `presence.read()` copies the record, then runs one database
transaction. that transaction:

- reads the pause control;
- checks the attempt's row is active: `fenced_at is null and product_outcome is
  null`, the predicate of `uq_native_attempt_active`;
- derives everything below.

**work.** there is work when the attempt is active, or when `effects` is
non-empty.

- **attempt inputs.** its `native_input_delivery` rows whose state is not
  `rejected`. steers count, so a follow-up sent mid-turn joins that turn.
- **triggers.** only rows with `was_waking`, mapped through the message's role
  and source, owner first:
  - owner `web` → `you`
  - `email_event`, `event_status` → `mail`
  - `work_wake` → `todo`
  - `action` → `result`
  - `recovery_catchup` → `recovery`
- **an effect** is work for the owner, because the owner approved it.
- **activity** comes from the earliest unanswered invocation of the attempt
  (`reply_recorded_at is null`). otherwise it is the most recently opened stock
  call. otherwise it is null (thinking). an effect uses its action's tool.
- **family** is the tool-id prefix. `docs` maps to `drive`. stock shell is
  `shell`, stock web is `web`.
- **mode** is `write` iff the invocation's `frozen_contract->>'effect' =
  'Write'`. an effect is always `write`.

**state.** precedence is `paused` > `working` > `standby` > `retrying` > `queued`
> `idle`.

- `paused` carries `draining` while work finishes.
- `standby`: a `deferral` with nothing running. it carries the `reason` and
  `until` defined above, and `until` may be null.
- `retrying`: nothing running, and every pending input has
  `native_retry_after` > now. `until` is the earliest of those times, the next
  attempt.
- `queued`: unparked pending inputs outside the attempt.

**owner work, `you`.** this is the state of the owner's newest unparked web
message that is either pending, or waiting on an approval where some waiting
action is `queued` or `executing` and none is `awaiting_approval`. the action
set is the request's recorded wait references.

- that second case reads `working` in the tail. until the executor enters,
  the tail says `working` with no elapsed time. only process-local work arms
  the header and its beat.
- a denied action is `cancelled` and matches neither case.
- the values are `queued`, `working`, `standby`, `retrying` and `paused`.
- `ahead` counts pending inputs before it in the existing `pending_inputs`
  order.
- `you` is null when no message qualifies.

**owed.** presence does not restate adr 0125's rule.

- it reuses 0125's `owed` ids, from the same `home_reads.py` query and within
  this transaction. entries are newest first, each with `href` `/m/{id}`.
  this includes 0125's clause that an owner reply still pending clears the
  label.
- each live `WorkspaceApprovals.pending()` choice is added as `google`.
- if presence lands first, it implements that query exactly as 0125 specifies,
  and 0125 reuses it.

**workers.** `registered_delegation()` actions with `status='queued'`, under
the scope join used by `active_delegations`
([actions](../../src/jarvis/actions.py)). jobs awaiting acknowledgement have
already finished, so they don't count.

**chat token.** an opaque change token over the chat projection's newest
`(at, id)` cursor and its row count. it is read in the same transaction. a reply
that commits with an earlier `at` than the current head still changes it.

## read contract

`GET /api/presence` takes no query. it uses the existing owner authentication
and `private, no-store` headers.

- it returns 200 with a strong `ETag` over the body without `as_of`.
  clients send `If-None-Match` explicitly. 304 confirms the retained state
  and produces one beat when that state is work.
- the read is additive. it is not one of 0123's or 0124's contract-gated
  handlers and needs no contract value.
- an older client never calls it.
- for a newer client, 404 means unsupported, not failed. it shows no mark,
  legend or stale words, and the title stays `jarvis`. it tries again on the
  next resume or reload.
- no schema, prompt, model binding or stopped cut.

```json
{"as_of":"2026-11-26T19:20:44Z",
 "state":"working","until":null,"reason":null,"draining":false,
 "work":{"since":"2026-11-26T19:20:31Z","triggers":["you","mail"],
         "activity":"gmail","mode":"read"},
 "you":{"state":"working","ahead":0},
 "queued":{"you":0,"other":0},
 "workers":0,
 "owed":[{"kind":"approval","href":"/m/…"}],
 "chat":"…"}
```

- `work.since` is the attempt's `armed_at`, or the earliest running effect's
  entry time.
- clients compute elapsed as `as_of − since` plus local time since that read,
  which avoids clock skew.
- owed `kind` is `approval`, `owner_input` or `google`. a `google` entry has
  `href: null`, meaning open chat, where its choices live.

**order.** every tick requests presence, then requests chat only after the
presence response arrives. today `refresh()` issues its reads in parallel. a
chat read therefore contains everything the presence read saw. a tail decision
that depends on presence uses only a chat read sent after that presence response
arrived. if a chat read is already in flight, the tick waits for it, then sends
one more.

a chat read with a `native_final` or `native_failure` id the previous chat read
lacked starts an immediate tick. the tail retires only on a presence read whose
`you` is null. in the chat read paired with that presence read, the last final
or failure the tail has not seen takes its place. if there is none, the tail
fades. otherwise new rows land above the tail, which stays. progress and owner
rows never retire it. clients compare the `chat` token only for equality.

**web.** run the existing 3 s tick, plus the visibility and `online` refreshes,
while visible. hidden tabs make no presence read; 0125's hidden read owns that
time.

**android.** one 3 s tick while resumed: presence, then chat. 0125 introduces
the 3 s chat read. before it lands, refresh chat when the token changes or
`you` becomes null. the 1.5 s workspace approval poll is unchanged.

**stale.** after three consecutive failed or missing reads (about 9 s), or any
401 or redirect:

- clear the mark;
- freeze and dim the elapsed time;
- show `last heard hh:mm`.

the next successful read restores the state without replaying beats.

## acceptance

use temporary end-to-end probes per the [testing reset](../issues/testing-redesign.md).
designers freeze good and bad json specimens before red. delete probes after
green, then record cleanup separately.

1. **service truth**, against the real service and postgres 16 on macbook:
   - a `no_work` pass never reads as working;
   - an active attempt row with an empty record reads idle;
   - killing the worker mid-attempt fails the read, and the restarted service
     reads idle until its drain arms anew;
   - a follow-up sent mid-turn, into a silent mail turn, reads as owner work in
     that turn;
   - an approved calendar write that outlives its attempt reads working with
     effects only, activity `calendar` · `write`, and `you.working`. its result
     turn reads as owner work with triggers `you` and `result`, then idle;
   - an approval waiter after its action leaves `awaiting_approval` never reads
     owed;
   - each waking source maps to its trigger;
   - activity is non-null only while an invocation or stock call is open, with
     two overlapping stock calls;
   - quota and non-quota deferrals produce different `reason`;
   - workers ignore finished jobs awaiting acknowledgement;
   - a reply committed with an earlier `at` changes the chat token;
   - idle reads return 304;
   - an `email_event` body contains no subject or sender bytes.
2. **web journey**, in chromium and webkit, desktop and narrow, both schemes,
   reduced motion on and off:
   - send, receipt, tail and handoff, with no shift above the tail and no
     destination movement when the mark or a legend appears;
   - a reply between the presence and chat reads never strands the tail;
   - the tail holds after an idle presence read, then hands off in place when
     its paired chat read finds the reply;
   - an owner message queued behind a workspace check keeps its tail when the
     check's final lands;
   - a silent mail turn: grey mark and legend, no chat row, no announcement;
   - an owed approval: rubric `¶` that goes to it;
   - network cut: no beat after the last read, stale after about 9 s;
   - the announcement log exactly matches presence's set.
3. **android journey**, on the S22+ with a candidate build:
   - send, then the conversation end, the tail and the handoff;
   - TalkBack order and announcements;
   - animator scale 0;
   - backgrounding stops reads.
4. **installed.** after the normal web release and signed app update, observe
   one owner journey on each client and one real silent mail turn. record the
   release identities.

independent opus review of this text before red and of evidence before release.

## differences from the study

- the study echoes before acceptance and announces arrivals.
- it lets a progress line replace the tail's words.
- it shows owed in the tail.
- it animates a corner on a J favicon and keeps a title while hidden.
- it mirrors the mark in a sidebar title row that 0122 removed.

this text replaces each of those.

## implementation decisions

- presence reads the same owed projection as 0125. it follows the request's
  exact action references, including an action created by a causal child.
  between approval and executor entry the tail may say `working`, while the
  header has no live work to confirm.
- the chat token counts all projected rows as well as hashing the newest
  cursor. the count costs a scan of the scoped chat and catches a commit
  behind the head. a late reply keeps its canonical position. web animates
  an unpainted reply in that cell. android fades the old tail when the reply
  sorts above it. an already-painted browser reply stays opaque.
- the settling read can cost another chat round trip. web bounds reads and
  clears freshness after nine seconds without confirmation, including a held
  socket. a 304 keeps the original elapsed-time anchor and confirms state.
- web reserves one line for transport status. android keeps the mark's 48 dp
  target and 8 dp of rule clearance even when idle. android uses ttf for the
  same licensed latin faces that ship as woff2 on web. at animator scale zero,
  presence uses its own short opacity transitions and still silent work.
- the signed candidate uses version code 9, after the 0125 version-8
  reservation. the release needs the artifact and citation client contract
  installed first. [installed acceptance](../issues/presence-installed.md)

## qualification on macbook

opus held red on paired ordering, tail retirement, deferral replacement and
the retired gmail-send witness. the amended specification passed that gate.
the temporary probes then witnessed the missing route, the missing browser
tail, and the android exact-message navigation. the calendar journey used a
controlled google transport held after the real detached approval path entered.

the detached wheel from `8f46ee7852c8116e41b97ba974d30c6501f8c4b5`
passed 19 service checks against postgres 16.15 and loopback http. its
sha256 is `0806eae052ca49dd200272e59cc649b6fa2f420cb1cf39c006f1e3a7c490a4d7`.
the same wheel passed 182 checks across chromium and webkit, desktop and
narrow, both schemes and both motion settings. each browser also passed five
journeys through the real service and database. the mail trigger was a
synthetic event backed by the real journal.

`scripts/verify` passed at `def8c9392f8962d22637ec68e1d8fe30f34f0b4b`.
only android source and assets differ between those two commits. the detached
android 35 replay passed 13 checks against an isolated http fixture. it
observed both read-order races, preserved scroll after redirect recovery, and
measured the configured 120 ms shape and word fades and 900 ms owner dip at
animator scale zero. the matching signed v9 apk has sha256
`97fda1f58727b68c8ebbbee4621e88cef2303a3b58669c19387b961d0c32eb05`.

the source reviews, commit-bound receipts, hashes and separate cleanup
receipts are in
`~/.local/state/jarvis/qualification/adr0126-implementation.EqNnxsCX/`.
the [installed check](../issues/presence-installed.md) carries the physical
handset, spoken talkback and production journeys.

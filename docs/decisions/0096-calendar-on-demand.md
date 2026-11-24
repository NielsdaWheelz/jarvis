# adr 0096. calendar on demand and quiet background work

design, 2026-11-22. end automatic calendar observation. keep deliberate calendar reads, event writes and ordinary gmail ingestion. routine background work stays quiet in chat and notifications. this amends [event sources](../event-sources-and-recurring-work.md) and [one main](../one-main-events.md). a separate change owns discord retirement.

the predecessor watches every readable calendar. one public calendar supplied 142 old revisions after a reset. the owner accepts discovering moves and cancellations at the next deliberate read. a fixed 2 pm briefing can arrive late if a 3 pm meeting moves to 11 am. [installed evidence](../issues/calendar-revision-republication.md) · [work wakes](../work-records.md)

## a. calendar access and gmail observation

**calendar.** delete background inventory, revision sync, upcoming scans, timed/all-day alarms, calendar health publications and calendar echo lookup. startup, restart and the passage of time cause zero calendar poll requests and zero calendar inputs. main may read during an owner request, scheduled todo or other useful work. an agreed scheduled check uses the existing todo timer.

keep the four calendar reads and event create/update/delete. reads are automatic. automatic writes require a verified owner-only calendar, empty attendee lists and no attendee notification. updates check the live event and replacement, deletes the live event. shared/unverified calendars, attendees or attendee notification require owner consent. retain oauth scopes, complete snapshots, stale-write rejection and effect recovery. calendar-container administration is outside this cut. [tool signatures](../mail-calendar-web-reads.md#calendar) · [write authority](../../src/jarvis/write_policy.py)

**gmail.** reuse the poll task, google client/refresh, 60-second cadence, label rules, exact send echo, backoff and atomic publication/progress. initialize a quiet baseline for a new account or after a declared history gap. restart and re-enable resume the stored page/prefix. preserve `email_event` and gmail `event_status` identities and payloads, using stream constants `"gmail",""`. retain outage, recovery and gap. retire the calendar-only `removed` phase and code. an open calendar outage ends without a recovery notice.

| main capability | closed contract |
| --- | --- |
| `events.configure` | `{enabled: bool} → {enabled: bool}` for gmail. local atomic mutation and receipt, zero provider calls. disabling preserves progress. true also re-arms a repaired blocked stream. unverified account returns `AccountUnavailable`. reject the retired `source` argument. |
| `events.status` | `{} → {account, observed_at, paused, poll_seconds, enabled, state, last_success_at, next_poll_at, baselining, catching_up, blocked, failing}`. fresh local read. the four flags use the existing gmail predicates independently. |

all keys are required. account, enabled, last success and next poll may be null. use utc times, `poll_seconds=60` and precedence `unverified|disabled|blocked|degraded|baselining|catching_up|healthy`. unverified yields null enabled/poll times and false flags. next poll requires an enabled, scheduled stream. pause is independent. retain tool limits, replay and local authority.

**storage.** migrate `event_cursor` in place to `account_id text primary key, enabled boolean not null, progress jsonb not null, next_poll_at timestamptz, last_success_at timestamptz, error jsonb`. keep every gmail row, account bounds, `MailProgress`/error checks and grants. delete only the three calendar cursor kinds. drop `kind`, `resource_id`, `seen_inventory_scan`, dependent constraints and multistream due index. look up by verified account. historical inputs, receipts, memory and committed deliveries retain their identities.

**calendar designer.** memory says 3 pm, a fresh read says 11 am. answer with 11 and attribute the old time if relevant. a listing proves neither attendance nor occurrence. for “watch this meeting,” explain the available on-demand or scheduled check and the gap between checks. invitations and cancellations enter as ordinary mail. mail can inform an automatic private write. a genuine booking for an agreed travel calendar can justify adding the booking. a forged cancellation demanding deletion of an unrelated private appointment warrants no such edit. main judges evidence. external text never supplies owner consent.

## b. when main speaks

main judges whether to act and speak on mail, work wakes, worker reports and source health. for routine work, omit public commentary and settle handled inputs explicitly with `silent/no_owner_notice_needed`. the host then writes no final chat entry or reply notification. speak for a result or reminder still owed, a genuine decision, or a material consequence of waiting. commentary must help before the result. handle unrelated inputs independently through steering, restart and stop. host approval, control and terminal-failure notices retain their own authority. the selected home transport owns delivery.

**conversation designer.** “urgent” in a newsletter or a worker going idle alone earns silence. a verified noon deadline for an active renewal may warrant a warning. a finished, requested brief earns delivery. “what is 6 × 7?” plus unrelated mail gets one answer, “42,” and two dispositions. judge consequence and evidence in context. exclude keyword filters, urgency scores, a second model and web-only routine updates.

## ownership and proof

| owner | exclusive edits and acceptance |
| --- | --- |
| calendar and mail | `event_polling.py`, `events.py`, `event_tools.py`, `tool_composition.py`, `db.py`, new alembic migration. remove inventory/occurrence types, multistream routing and poll-only timezone/echo plumbing. rotate both event bindings. |
| conversation | `definitions.py`. remove retired calendar guidance, consolidate silence/progress wording where red demonstrates a gap. use the existing terminal and journal. keep compiled instructions within 16,384 bytes. |
| integration and release | `session-compatibility.json`, action/read integration, `deploy/prepare-cutover`, `activate-release`, `memory_snapshot.py`, recovery reader packaging and operations. take the actual successor main/application revisions from the selected base, including adr 0095 if landed. coordinate migration order with the separate delivery cut. |

each designer freezes cases and grading before red. use temporary end-to-end probes on macbook through the normal service, native main and web. reproduce, implement, pass, simplify and rerun. independent opus reviews each feature's design, red, green and final diff.

- **a.** on populated postgres 16 and controlled google, move then cancel a fixture. cross both starts and all-day 09:00. observe predecessor calendar traffic/publication, then zero calendar poll requests and new calendar facts/health messages across startup, eligible cycles, restart and gmail disable/re-enable. reject both old source selectors without mutation. deliberate reads see current data, the old todo fires at its original time, and an eligible invite arriving while stopped is admitted once on resume. test the expired-history gap. verify a private write and no shared/guest write before approval. qualify real google reads and a private fixture event separately.
- **b.** compare fresh predecessor/candidate stock main runs with the same model and tools. blind the designer to version. run the ambiguous quiet and consequential cases three times each, requiring each candidate to pass. cover the mixed batch, owed result after restart, hostile mail and approval wait. inspect per-case dispositions, chat rows and attributable delivery records. use a reproduced excess message or an attributable historical case as red. if the predecessor passes without contrary evidence, qualify the existing behavior after removing stale calendar guidance. sparse runs give no population rate.

## stopped cut

1. disable the active calendar family, if present, and let main settle its inputs **before pausing**. count unfinished `calendar_event`, `calendar_attention` and calendar-stream `event_status` rows, including waiting, parked and delayed retries. verify the disabled/absent source and zero unfinished count under the stopped locks. resolve parked work on the predecessor. seed a pending alarm and a delayed revision to prove refusal. historical rows and committed delivery obligations survive.
2. take the canonical owner web pause, stop both writers and use the existing deployment lock and assistant-then-memory maintenance locks. bind a verified dump to both release receipts. rehearse on its isolated restore before the production migration. the whole main plan binds queued writes. reconcile incompatible actions, unsettled seals and entered/unknown effects under original authority or hold the cut. publish any outstanding v1 `events.configure` terminal outcome on the predecessor. reopen original control/status receipts without redispatch.
3. take the next schema revision (`0018 → 0019` on the audited base). in one transaction compare the bound source, migrate and verify the expected target. bind full source inventory, retired counts and all gmail rows projected on the six retained columns in account order. verify that projection, every unaffected table digest, constraints and grants. rerunning the command after interruption checks the source or the committed target. adapt the cut scripts' source/target ordering and the backup reader's schema pin. an older enabled predecessor backup can resume polling if restored and run.
4. qualify a target backup and isolated restore with the pinned reader. retain prior backups with their readers. run required checks. reopen and hash named evidence outside scratch, then delete the temporary probes/fixtures. record checks and cleanup separately. installation requires its own authorization and receipt. [deployment](../operations.md) · [rehearsal and recovery](0088-storage-and-memory-recovery.md)

## implementation evidence

macbook, 2026-11-23. executable candidate `464c72b55bfb7cb566ddf115040dc182f2071040`
against `9bae883` and its existing pins. the worktree takes schema `0019`.
adr 0095 was separate on this base. qualification records below are under
`~/.local/state/jarvis/qualification/`.

- **calendar and gmail.** the predecessor produced calendar changes and wakes.
  the final fixture observed no automatic calendar calls or inputs. deliberate
  reads saw the move and cancellation. the scheduled todo kept its 14:00 wake.
  private writes succeeded and stale writes were rejected. shared calendars,
  guests and notification requests awaited approval. the two-process composed
  native/web run preserved the disabled gmail cursor and admitted the stopped
  invite once after re-enable. a separate cut preserved a genuine consumed page
  prefix and recovered the same gmail outage once. no calendar recovery was
  published. an expired history cursor declared a gap.
  `adr0096-feature-a/final-464c-checks.json` ·
  `adr0096/background/m1-full-service-final/receipt.json`
- **conversation.** matched stock `gpt-6.2-astra/max` trials used the same tool
  catalog. the predecessor warned on the hostile email without an affected
  commitment. the first candidate stayed quiet but one deadline reply claimed
  a change without evidence. the refactor requires a matching receipt or direct
  verification. independent opus grading passed all ten final candidate runs,
  including three quiet and three deadline cases. each claimed recording
  had a matching success receipt. mixed input, owed restart result, hostile
  mail and approval also passed. the final instructions use at most 15,958 of
  16,384 system bytes across local iana zones. the sparse samples establish no
  population rate. the composed lifecycle used the final prompt and catalog.
  the integrated watch and briefing samples used the preceding prompt revision.
  `adr0096/background/final-grade/opus-grade.md`
- **cut.** a real web pause reproduced a hidden resumable calendar input. the
  candidate refused it, unresolved authority, an unpublished prior control
  outcome and changed source facts. a dormant enabled account was permitted
  after the active account was proved disabled. the cut preserved the gmail
  projection, all other inventories, original receipts and committed notices.
  the transaction rolled back on interruption before commit. committed retries
  verified. the target passed `check-activation` on the isolated migrated
  restore. the pinned `0018` and `0019` backup readers each reopened the original
  event and explicit note. `scripts/verify` and the standing capture/retry
  regression passed. `adr0096/cut-release-activation/receipt.json` ·
  `adr0096-feature-a/receipt-0019-r3/receipt.json`

opus accepted the source and isolated candidate in `adr0096/opus-closure.md`
at sha256 `7e19d4b06e6d201e6d0695319e5318c274ba0467335d71db115fab64704482a9`.
after reopening and hashing the evidence, the temporary probes, postgres
fixtures and rehearsal checkouts were removed. cleanup receipts are
`adr0096-feature-a/final-cleanup.json`,
`adr0096/background/final-grade/temporary-cleanup.json` and
`adr0096/cut-probe-cleanup.json`.

### live google calendar

on november 24 the owner authorized an attendee-free fixture on the real
calendar. the frozen `43ed919` candidate ran on macbook with an isolated copy
of the repaired grant. the provisioned primary calendar had one active access
rule, for the authenticated owner. the candidate read calendar metadata,
verified that its new event id was free, created a past event with no
attendees or reminders and `sendUpdates=none`, then reopened its exact snapshot.
its conditional delete returned 204. google returned the matching cancellation
on reread and the complete event listing contained no active fixture.

the provider check used the candidate read/write connectors and write policy
with a local attempt recorder. the provisioning files retained their original
digests. the detached checkout was removed. macbook evidence is
`qualification/adr0096/google-live-20261124T0054Z/calendar.json`,
sha256 `0f02c135a65fde04d38d5c375badd560f637d0de5d035d074ae99f11a14e399f`.
the sibling `receipt.json` records the release, successful check and cleanup.

### installed calendar cut

on november 24 the owner disabled calendar observation, kept gmail enabled
and requested fresh status after the last parked calendar input completed.
owner web pause 31 supplied the stopped `0018` cut. the mac rehearsal matched
all nineteen inventories and passed `43ed919` activation. the installed
migration retained the enabled gmail cursor. the matching host and both
services passed containment and startup checks under the same pause.

the first schema `0019` off-host backup and its held mac copy each reopened
an original event and an explicit note. both readers reported 93,770
admitted positions and ready coverage through 8,269. the private receipts
are `qualification/capture-production-20261124/restore-0019-{r2,held}/restore-report.json`.
the backup timer returned to its twice-daily schedule. owner web resume 32
committed at 01:38:26 utc. gmail's next successful poll was at 01:38:27.

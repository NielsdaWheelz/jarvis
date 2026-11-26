# adr 0114 · automatic foreground recovery

**accepted for implementation · 2026-11-25 pacific.** implementation started
from the selected `0584972` at schema `0024` and integrates upstream
`5647824` at `0025`. recovery adds no migration. production activation and
disposition of historical inputs remain separate operations.

## decision

jarvis recovers unfinished work automatically. it waits for transient capacity,
settles original effects from evidence, and does independent work while a
consequential effect remains unknown. the owner hears about a decision only
when jarvis has exhausted the permitted checks and that decision changes what
can safely happen next. an operator hold remains available for an actual
invariant failure or needed intervention.

production `70522de` left 93 inputs parked across 64 attempts. 84 were mail
events from personal quota failures and five were mail events from backend
failures. those 89 inputs had no recorded write. that absence does not prove
the original native sessions were effect-free. the remaining four inputs shared
a turn that successfully created and updated one calendar event but failed to
publish an answer. all 93 lacked a retry time. [inventory](../issues/foreground-parked-backlog.md) · [calendar evidence](../issues/native-steer-interrupted-message.md)

this decision amends [0086 §b](0086-native-recovery-and-memory-availability.md#b-native-admission-rejection-and-one-fresh-retry), [0106 §§b–c](0106-interrupted-answers-and-parked-work.md), and [0110 §§c–d](0110-neon-quota-recovery.md) for eligible recovery and notice scope. ordinary events still use one full main plan. the narrower plan applies only to recovery after failure. existing route, processor, authority, stop, effect and operator-custody rules continue to govern.

## recovery and admission

the native journal owns the following transitions. fence the abandoned
attempt before new admission. settle a usable original seal locally under its
original authority. for the remainder, bind each decision to its original
attempt, input delivery, current control and effect receipts. settle entered
actions through the existing recovery mechanism with executor entry disabled.
retain the original effect identities, sealed failures, usage and replies.

| evidence | automatic outcome |
| --- | --- |
| proved pre-entry refusal or deferred capacity | keep inputs pending. use the existing wake and route selector. a reset timestamp schedules observation. only fresh authenticated capacity permits an opening. waiting does not spend a fault retry. |
| every original input and effect accounted for | reopen the ordinary plan when no effect entered and the existing retry contract permits it. when an effect entered, reuse its receipt and finish the answer under the restricted plan. an already-authorized pending action continues through its own identity and lifecycle. honor the required route pin. |
| incomplete effect evidence, independently answerable work | admit only the supported answer or observation through the restricted plan below. emit the known result and identify any missing material portion. wait on the unresolved effect separately where lineage supports that distinction. |
| remaining work depends on an unresolved effect or needs owner authority | retain the affected input on hold. record the exact unresolved operation and evidence. use an existing approval or owner wait when its contract applies. unrelated inputs proceed. |
| permanent source loss, expired informational work or exhausted retry | record the actual disposition and coverage. preserve a still-actionable owner request with its specific blocker. background facts that already received a truthful terminal disposition do not keep retrying. |

a quota label, failed seal, missing tool log, text match, or provider deadline
alone proves no effect outcome. only original receipt evidence, authenticated
pre-entry evidence or authoritative verification of the original operation can
license a stronger disposition. keep ambiguous sends, writes and billed-once
reads behind their existing execution barriers. known read failure may be
retried only under that binding's existing contract.

reuse `native_retry_after` and the validated retry evidence in
`trace.native_retry`. add only a closed continuation kind where the existing
record cannot identify a restricted opening. verify its scope and original
attempt/delivery under the conversation lock. ordinary admission cannot turn a
restricted continuation into a full session, even if it failed. retain the
existing one fresh fault opening per affected input and the existing capacity
probe cadence. automatic wait, fencing or process restart cannot reset either
allowance. schedule the next due check through the existing service wake.

at selection and again before dispatch and settlement, check the current
owner/permit, stop/pause, grants, superseding input or disposition, and the
original causal evidence. apply the existing late-seal rules. a newer valid
disposition prevents obsolete output from committing. use existing batch and
request-fit limits. keep foreground input responsive and independent work
eligible. compaction and nightly dreaming retain their existing capacity and
schedule rules.

if its grant changes after a restricted opening, a still-live matching input
gets a scoped hold. the original outcome cannot publish or rearm on the new
grant. stopped or superseded inputs keep their established disposition.
generic operator release treats restricted holds as inspection-only.

## restricted continuation

jarvis reuses the contained native session and frozen capability plan used
by [workspace checks](0107-google-workspace.md). recovery supplies its own
exact input and original-attempt lineage. a standing check's grant provides
no authority for recovery. verify the effective backend policy before native
entry. admit only scoped reads needed for the unfinished result, including
original receipts and current connector or public-web reads where applicable.
disable native shell, files, browser control, children and worker dispatch.
grant no product write, approval, consent change or connector mutation.
use fresh read authority only for the named inputs and current grant, honor
the existing background gmail quota, and yield to owner work through the same
serial admission. a backend that cannot enforce the policy cannot run this plan.

main owes the useful result it can establish, with sources and limits. record
per-input dispositions against the frozen input ids. for an owner request,
complete only when its requested outcome is satisfied under the original
receipts and the new answer. a report can complete independently while an
unresolved effect stays explicit on its originating request. incidental mail
facts can settle when their read-only handling is complete, including a
terminal source-unavailable outcome. finish useful portions before escalating
a blocker. routine waits stay quiet. publish one notice for a material
remaining blocker or a completed catch-up, through the existing private
outbox. commit dispositions and that logical output together. preserve old
notices and original effects. a restarted worker can repeat eligible model
computation and reads under their existing constraints. it cannot republish a
committed logical result.

## existing backlog

inventory under the existing named stopped custody when authorized. freeze
exact current ids and park stamps with their matching original deliveries and
notices. the observed counts are a baseline, not a selector. exclude changed,
new, stopped and unrelated rows. publish one bounded host input in the
existing conversation, keyed by owner scope and the digest of the authorized
inventory, so normal admission can deliver one read-only catch-up after
startup. references to old mail are observation inputs and carry no prior
executor authority. revalidate their scope, park stamps and control at claim
and commit. do not clear the parks when enqueuing the report.

cover the 91 mail events, including the two from the calendar turn for
informational coverage only. a mail input with its own unresolved original
action also has informational scope. its action and request stay linked.
group surviving messages by thread and report
actionable items, actual coverage and unavailable originals together.
verify current access with the enrolled connector. 36 ids returned gmail
`not found` in the review. count a current authoritative `not found` by exact
id without claiming deletion. preflight the historical input and read budget
for one report. report any coverage gap and leave still-retryable items
eligible within the existing bounds. when the report commits, retire the
authorized, covered mail facts outside the four-input hold as handled or
unavailable. keep their original attempt and park history. retirement
disposes of the mail notification, and settles no original effect.

the [november 24 four-input hold](../issues/native-steer-interrupted-message.md)
has its own owner disposition under 0106. require explicit approval for any
change to those rows. the proposed disposition is to reuse both original
calendar receipts, deliver the missing sizing research separately if still
wanted, and record the overdue appointment request from the verified receipts.
the visit date has passed. make zero new calendar writes and preserve the
original unsealed answer as evidence without publishing it as a valid final.

## implementation and proof

1. **journal and admission.** `native_journal.py`, `native_runtime.py`,
   `messages.py` and the existing route selector own the transitions above.
   run a normal-entry failure probe against the selected predecessor first.
   show a quota refusal waits through reset, an accepted mid-turn quota loss
   cannot open an unsafe full retry, a late valid seal settles once, and a
   held cohort leaves unrelated work live. include restart and stop races.
2. **restricted result.** extend the existing native plan tightening in
   `native_protocol.py` and its dispatcher and product settlement. prove
   effective containment on each backend used by this feature, with attempts
   to call a write, shell or child rejected before entry. drive two successful
   calendar writes and a lost final through the real entry path with synthetic
   effects. prove the answer can finish with zero additional writes and an
   unresolved sibling effect remains held. prove a multi-thread catch-up with
   duplicate input, a missing message, a retryable read error and process
   death around result commit. check receipt identities, input dispositions
   and exactly one logical delivery.
3. **integration and cut.** keep the existing schema, deployment lock,
   service, journals and outbox. `jarvis-native-request.v5` binds original
   recovery lineage and grant to the restricted opening. both main routes
   include v5 in their session compatibility fingerprint. settle predecessor
   executable attempts and retries under their original release. keep old
   receipts readable as evidence. precede implementation with the selected-base
   compatibility audit. qualify the integrated candidate on macbook using
   dev-server's `scripts/rehearse-worktree` for detached rehearsal. reopen and
   hash named evidence outside scratch and report fixture cleanup separately.
   a separately authorized [0104 cut](0104-maintenance-without-owner-pause.md)
   verifies the installed recovery journey before the historical disposition.
   match the fresh inventory to the adopted scope before changing any park.

## trade-offs

- recovery spends at most the existing fault opening for each input. an
  owner interruption after entry can leave an unfinished partial result.
  the scoped session can explain effects and finish reads. additional
  writes require the existing action lifecycle or fresh owner authority.
- the service uses one wake deadline for the next eligible retry or capacity
  observation. it can interrupt idle memory work when foreground work is
  due. the existing periodic wake remains the observation cadence for
  unverified availability.
- the catch-up uses one private report. one temporary read failure can
  delay the report, while earlier proved reads remain available through
  their original receipts, including after a fenced unsealed loss has been
  settled. absent observations stay outstanding. a changed
  frozen inventory holds only the catch-up input and requires a fresh
  selection.
- the v5 cut requires predecessor executable work to settle under its
  original release. retained attempts and receipts preserve their original
  evidence. the design uses the existing serial main, journals and outbox
  without a workflow framework, new table, quota purchase or wider processor
  policy.

## source qualification

the macbook red rehearsals at `0584972` reproduced the missing service wake,
discarded paid retry deadline and acceptance of an unsettled retired seal.
postgres probes reproduced quota and transport parks. independent review also
reproduced grant replacement rearming, generic release widening authority,
historical web access and a completed read becoming eligible again after an
unsealed loss. the corresponding restricted controls passed before the cut.

detached candidate `26a6442` passed on postgres 16 with schema `0024`.
the integrated `a922811` passed again at `0025`, with the upstream desktop
memory pin. the real journal and product paths kept both synthetic calendar
write receipts at one entry each and delivered one restricted result. a
process killed with the catch-up outbox transaction open left zero committed
reports or retirements. two fresh processes subsequently settled it once.
the existing capture/retry probe passed. stock codex `0.171.0` opened both
personal and neon configurations against synthetic inference, delivered one
allowed callback per run and entered zero shell, child or write effects.
the release's static, dependency-lock and package checks passed.

the installed read-only inventory verified 91 canonical mail identities,
deliveries and park notices, including two informational-only mixed-owner
facts. the event and inventory encoding occupied 47,172 bytes before the
fixed task text. the check issued no production write or model call.

the detached out-of-tree receipt is
`~/.local/state/jarvis/qualification/adr0113/composed-a922811/receipt.json`.
all six evidence files were reopened and their sha-256 digests matched.
the rehearsal checkout and disposable postgres fixture were removed.
the temporary probes were deleted after verification. installed acceptance
and the historical disposition remain separate.

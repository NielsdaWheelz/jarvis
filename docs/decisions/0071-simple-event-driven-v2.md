# adr 0071: simple event-driven v2

status: accepted documentation target, 2026-11-14. source implementation,
dependency adoption, installed qualification and activation remain separate.

## context

the owner narrowed v2 after the [competitor research](../research/personal-agents-2026-11/README.md).
the useful product is an agent that follows through with context, files and tools.
the existing proposals split that behavior into work records, separate recurring
schedules, notification obligations and exact approval presentation. the owner
selected a simpler model and explicitly relaxed the approval invariant: trust
ordinary conversation, avoid spending code or prompt context on consent ceremony.

native main, canonical journals and asynchronous skid observation already exist.
their remaining installation evidence is not a reason to invent another runtime
or worker callback service. the current memory completion is a separate pr.

## decision

1. every admitted event starts or steers the same main with its normal tools.
   jarvis chooses action, delegation, notification or silence. remove the
   current-owner-only model write gate and read-only wake plan. preserve source
   identity, deployment ownership, canonical requests and effect recovery.
2. work records are the existing proposed todo table. optional one-time/repeated
   wake data lives on that row; its content holds context and references. a due
   wake publishes an ordinary event. deadlines remain separate from wake times;
   firing does not complete the todo. no `recurring_wake` table, separate schedule
   product, execution controller or per-occurrence workflow.
3. private notes are an ordinary persistent private git repo and directory with
   trusted native tools. no notes service, forced document layout or git cadence.
4. retain uploaded discord and selected email attachments as private r2 originals,
   with stable references and native reading of images, pdfs and supported files.
   use the existing attachment contract's one metadata table. prose belongs in
   the repo; original binary files belong in object storage.
5. delegate through skid. its existing asynchronous wait publishes a canonical
   event when observation completes; main need not poll sessions to discover it.
   qualify the installed path and repair demonstrated gaps before proposing a
   new callback protocol. worker idle and task success remain different facts.
6. approvals, progress, blockers and results use ordinary conversation. main
   interprets consent, including clear consent already given, and uses one narrow
   callback to the existing action approval/denial transition. no buttons,
   host-rendered argument attachment, exact prose/payload matching, extra
   classifier or notification-policy field. immutable stored arguments and
   recovery remain execution requirements, not a semantic consent proof.
7. small deliverables are normal prose and repo files through existing access.
   defer browser control, new credential handling/brokering, interactive
   deliverables, credential forms, television/artifact hosting and a separate ui.
   existing connector/storage deployment credentials remain operational necessities.

the detailed contracts are [one main](../one-main-events.md),
[todos and scheduling](../work-records.md), [event sources](../event-sources-and-recurring-work.md),
[delegation](../delegated-follow-through.md), [notes](../private-notes-and-rolodex.md)
and [attachments](../attachments-and-durable-originals.md). they are adopted by
this decision and spec; the [single roadmap](../implementation-plan.md) owns pr
sequence. this adr adds three application tables across those slices: `work`,
`event_cursor` and `attachment`. derive migrations from the actual memory/native
predecessor rather than asserting a second fixed total.

shared memory, capture and quiet dreaming retain adrs 0066, 0067 and 0070. selected dream
wakes and dreamer work context are outside this v2 cut. the existing complete-search
and budget contracts remain later scoped work; this decision neither adopts their
additional schemas/authority nor deletes their owner choices.

## supersession and migration

this decision supersedes the affected target portions of adrs 0003/0009/0011
(mandatory component/preview approval), 0014 (closed tool catalog), 0015/0030
(owner-only one-shot proactivity and separate schedule tool), 0019 (model write
gate and current-owner-only grounding), 0035/0065 (main containment once trusted
native notes is delivered), and 0059/0064/0065 (read-only waking authority and
host conversational-stop interception). unrelated channel, transport, isolated
role, lifecycle and effect-recovery contracts remain binding. the event/notes
cutovers replace only their affected paths; this is not a general dependency
upgrade or permission to relax connector reconciliation.

the earlier proposed parent/notice and exact-approval successor machinery is
replaced by the smaller [o6 contract](../one-main-events.md). retain the causal
parent reference needed for action continuation; add no notice ledger or semantic
consent framework. current code's old behavior remains the implemented baseline
until the corresponding cutover. expected target incompleteness is not a claim
that those old paths have already been removed.

use existing stopped migration and revision rotation. inventory pending effects,
approvals, reminders and worker waits; settle or explicitly disposition old
executable state and disable retired components. recreate retained reminders as
scheduled todos with truthful original timing/context, preserving historical
receipts. no dual scheduler, rewritten historical receipt or silently lost
commitment. notes requires the explicit kernel/provider native-access handoff;
the current contained endpoint does not already provide it.

## consequences and verification

main has more discretion. conversational consent depends on model judgment;
there is no deterministic proof that its question conveyed every argument.
trusted native commands and workers also do not inherit connector action
guarantees. the owner accepts these prototype trade-offs. preserve concrete
recovery correctness without building a generalized consent or intent system.

recurrence coalesces missed occurrences and initiates reasoning rather than a
guaranteed workflow. notifications depend on useful agent behavior. private notes
are mutable; memory observations and original execution receipts retain their
own history. attachments are durable originals, not a backup promise.

this change is documentation only. run static/build/document checks; no source,
behavioral/live execution, deployment or service resumption is included. future
implementation uses the focused outcomes in the owning contracts and
[acceptance](../acceptance.md#accepted-v2-outcome-checks), sized to actual risks.
adr 0046's testing reset and the separate memory verification exception remain.

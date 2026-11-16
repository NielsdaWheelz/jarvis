# adr 0071: simple event-driven v2

status: accepted documentation target, 2026-11-14. source implementation,
dependency adoption, installed qualification and activation remain separate.

implementation: [slice 1](../one-main-events.md#implementation-evidence) and
[slice 2](../work-records.md#implementation-evidence) now have source and isolated
functional proof. slices 3–4 have source and separate candidate qualification
under their contracts. [slice 5](../attachments-and-durable-originals.md#implementation-evidence)
now implements attachments with separate private-storage/native-host candidate
qualification. remaining slices and installed activation are pending; scheduled
todos replace the retired scheduler. production activation stays at final v2
cutover, independently of source/candidate evidence and resource disposition.

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
   slice 1 refines this into one owner/host lifecycle, a causal message reference
   for recovery, a `stop` disposition for named delivered requests and an atomic
   local decision receipt in the existing native journal. no new table or role.
   slice 6's source audit specifies mail/calendar producers: one independent poll
   task and cursor table, bounded resumable gmail prefixes, fixed calendar sync
   selectors and approximate attention. source metadata is ordinary host history;
   bodies/files require deliberate reads. controls reuse local action receipts;
   shared connector refresh and account-qualified echo evidence stay at their
   owning layer. candidate qualification is separate from final production cutover.
2. work records are the existing proposed todo table. optional one-time/repeated
   wake data lives on that row; its content holds context and references. a due
   wake publishes an ordinary event. deadlines remain separate from wake times;
   firing does not complete the todo. no `recurring_wake` table, separate schedule
   product, execution controller or per-occurrence workflow.
   slice 2's owner refinement accepts schedules delayed past their time in the
   dispatch queue and wakes late. schedule replacement identity and the next
   nominal civil date live on that same row. recurring rows are standing
   commitments; completing one occurrence does not end them. the three work
   mutation tools remain local bookkeeping during external-effect uncertainty.
3. private notes are an ordinary persistent private git repo and directory with
   trusted native tools. no notes service, forced document layout or git cadence.
   the 2026-11-15 owner refinement selects a new private
   `NielsdaWheelz/jarvis-notes` repo, initially one brief readme with no import.
   this is a general workspace for documents, custom helpers, components,
   visualizations and self-contained interactive files. native authoring/execution
   belongs to slice 4; hosting/presentation and television integration remain later.
4. retain uploaded discord and selected email attachments as private r2 originals,
   with stable references and native reading of images, pdfs and supported files.
   use the existing attachment contract's one metadata table. prose belongs in
   the repo; original binary files belong in object storage.
   slice 5 implements raw captions plus immutable host manifests,
   attachment-only ingress, narrowly scoped gmail discovery and the shared native
   cache. one entered upload per original prevents late resurrection; bounded
   delete retries are safe because completed originals' keys are never reused.
   its detailed contract owns schemas, atomic receipts and qualified candidate proof;
   this is not adoption of the later search overhaul or production activation.
5. delegate through skid. its existing asynchronous wait publishes a canonical
   event when observation completes; main need not poll sessions to discover it.
   qualify the installed path and repair demonstrated gaps before proposing a
   new callback protocol. worker idle and task success remain different facts.
   the 2026-11-15 owner refinement scopes slice 3 to a temporary candidate against
   the installed fleet; production acceptance waits for final v2 cutover.
   preserve the intermediate activation refusal and existing reminder handoff.
6. approvals, progress, blockers and results use ordinary conversation. main
   interprets consent, including clear consent already given, and uses one narrow
   callback to the existing action approval/denial transition. no buttons,
   host-rendered argument attachment, exact prose/payload matching, extra
   classifier or notification-policy field. immutable stored arguments and
   recovery remain execution requirements, not a semantic consent proof.
7. small deliverables are normal prose and repo files through existing access,
   including the workspace's generated code and interactive files.
   defer browser control, new credential handling/brokering, interactive
   hosting/presentation, credential forms, television integration and a separate ui.
   existing connector/storage deployment credentials remain operational necessities.

the detailed contracts are [one main](../one-main-events.md),
[todos and scheduling](../work-records.md), [event sources](../event-sources-and-recurring-work.md),
[delegation](../delegated-follow-through.md), [notes](../private-notes-and-rolodex.md)
and [attachments](../attachments-and-durable-originals.md). they are adopted by
this decision and spec; the [single roadmap](../implementation-plan.md) owns pr
sequence. this adr adds three application tables across those slices: `work`,
`event_cursor` and `attachment`. derive migrations from the actual memory/native
predecessor rather than asserting a second fixed total. current source has
seventeen tables: native nine, six memory tables, work at `0010` and attachments
at `0011`; the event cursor remains a later slice.

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
commitment. notes' kernel/provider native-access handoff is source/candidate
qualified by slice 4; the installed endpoint still awaits final v2 activation.

the owner subsequently confirmed that intermediate slices need not be usable.
slice 1 removes the old scheduler; slice 2 replaces it. retain reminder obligations
in the private cutover inventory until conversion; do not keep old execution
paths merely to make intermediate prs deployable. unattended activation waits
for the selected slices and accounted-for commitments.

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

the original adr review changed documentation only. subsequent owner-authorized
implementation uses the focused outcomes in the owning contracts and
[acceptance](../acceptance.md#accepted-v2-outcome-checks), sized to actual risks;
source/candidate evidence does not authorize production activation or resumption.
the owner selected temporary integration/live red/green/refactor for slices 1–6,
with designer and adversarial review per feature/stage, then probe deletion.
that scoped implementation exception does not restore a standing suite under
adr 0046 or change memory's separate checks. their linked evidence owns exact
artifacts, provider versus controlled proof and resource disposition.

owner receipt amendment, 2026-11-16: direct gmail-send/calendar-create/update
successes require verified account before effect entry. exact effect recovery may
return success with null account qualification; these receipts cannot suppress
echoes. the missing qualifier never makes a proved effect uncertain. preserve
existing bounded reconciliation and action schema, with no new durable account
recovery mechanism or repeat of an effect. the event contract owns proof.

# jarvis baseline for competitive research

snapshot: 2026-11-14, checkout `ce6f48870ca2968f8c57375b7bdcadba133d8973`, including
the owner's existing uncommitted roadmap and budget documents. this is a reading
of current repository contracts and recorded delivery evidence, not a fresh code
audit or deployment inspection.

this preserves the baseline read before the subsequent owner scope decision.
[adr 0071](../../decisions/0071-simple-event-driven-v2.md) now adopts the simpler
v2 target: conversational consent, scheduled todos and ordinary event handling.
selected dream wakes remain deferred. linked feature contracts have since been
updated; the historical comparisons below do not override their current status.

jarvis already has substantial memory and execution foundations. the remaining
v2 direction also covers much of the product surface marketed by personal-agent
vendors. the central comparison is which useful journeys those foundations
actually deliver together. counting proposed features as shipped would conceal
the main uncertainty.

## current contract and recorded implementation

the [spec](../../../SPEC.md) and its accepted native/memory amendments govern.
the [roadmap's current-position section](../../implementation-plan.md#current-position)
distinguishes source completion, qualification, installation and activation.

| capability | current contract or recorded source state | comparison implication |
| --- | --- | --- |
| one personal assistant | one owner and one private discord text channel; canonical conversation independent of discord | continuity exists at the product level; this is not a multi-client or team product |
| responsive native main | source implements native callbacks, public progress, request dispositions and steering; unfinished requests survive topic changes | compare observed responsiveness and follow-through, not just whether a vendor says “agent” |
| durable effects | immutable actions and exact approvals; provider-specific reconciliation; uncertain effects cannot blindly repeat | a competitor's “retry” or “undo” needs precise semantics before comparing it with this contract |
| memory | core and repair source recorded as implemented; admitted originals, shared chronological compression, search/navigation, optional notes and quiet dreaming | source presence does not prove real capture activation or useful retrieval in daily operation |
| memory clients | admitted native codex/claude histories and a distinct nexus owner-chat client; native clients choose shared reads | shared memory does not imply shared native sessions, all-client automatic injection or nexus conversation capture |
| worker control | source implements skid launch, steering, inspection, asynchronous wait and cancellation | coordinated fleet release/install and installed observation remain separate obligations |
| connected work | gmail reading/drafts/approved sending; owner-only calendar work; maps; bounded web tools | native broad browser access and an arbitrary connector marketplace are outside this baseline |
| proactivity | owner-requested one-shot wakes; restricted wake authority; quiet memory dreaming | this is narrower than background monitoring, recurring commitments or independent external action |
| control and inspection | deployment ownership, host stop/pause/resume, request/action/read journals and cli status | visible product explanations can improve without inventing another execution ledger |

memory specifics come from the [consolidated memory contract](../../universal-memory.md)
and [repair contract](../../memory-repairs.md). worker/native implementation and
qualification are recorded in [the native handoff](../../native-agent-integration.md)
and [acceptance](../../acceptance.md#native-cutover-acceptance).

the roadmap last records the deployment as stopped and paused. that is a dated
repository statement, not a finding that it remains stopped today. this pass made
no service query. outstanding cutovers are already owned by the
[operational section](../../implementation-plan.md#operational-cutovers-and-upkeep)
and its linked issues.

## v2 direction already written

these are settled owner choices in proposed contracts, with adoption and
implementation still required unless the owning document states otherwise. they
do not silently supersede the current spec.

| proposed behavior | owning document | material difference from the baseline |
| --- | --- | --- |
| one main for every event | [o6](../../one-main-events.md) | owner messages, wakes and results use the same capabilities; remove the owner-grounding model gate; preserve deterministic connector approvals and effect recovery |
| useful work records | [o7](../../work-records.md) | one mutable table for work, with doing now, blocked, next up and backlog; bookkeeping does not become execution authority |
| delegated follow-through | [o9](../../delegated-follow-through.md) | main chooses delegation, integration and further work; conversational stop becomes interpreted intent; operational pause remains separate |
| private notes and people records | [notes](../../private-notes-and-rolodex.md) | an ordinary persistent git checkout and native tools; a deliberate expansion to trusted native execution, not a repo-only sandbox |
| continuable searches | [search](../../complete-and-continuable-searches.md) | bounded pages/chunks without application-wide traversal ceilings; no invented completeness when the provider is incomplete |
| event sources and recurrence | [events](../../event-sources-and-recurring-work.md) | incoming mail, calendar changes/attention, recurring schedules, daily work review and selected dream suggestions wake the same main |
| work-informed dreaming | [dreamer context](../../dreamer-work-context.md) | current active work informs a bounded dream; it is context, not summary evidence or a second work controller |
| durable attachments | [attachments](../../attachments-and-durable-originals.md) | exact private originals, ordinary native reading and explicit deletion; outgoing sharing and a dedicated reader remain separate |
| budget bookkeeping | [budget](../../budget-integration.md) | integrate the existing ledger and command api; automatic bookkeeping does not include payments, banking or purchases |

these contracts matter to the research. for example, comparing a competitor's
automatic email triage with jarvis's current wake restrictions identifies a real
present gap, but not a missing v2 idea. comparing browser purchasing with the
budget proposal would conflate bookkeeping and spending.

## product boundaries to preserve in interpretation

the [roadmap](../../implementation-plan.md#deferred-from-universal-memory) explicitly
leaves generic computer use, android, extra discord channels, selected
onepassword access, api-backed cognition and wider nexus product integration
outside the present delivery. the current spec also excludes voice, a visible
agent organization, tenancy and autonomous purchasing. research can challenge
these choices; it cannot change them by calling a competitor feature standard.

three boundaries deserve particular care:

1. the proposed notes environment permits native access under the host account.
   its effects do not inherit connector action-journal or approval guarantees.
   compare it with a competitor's remote computer as a distinct authority domain.
2. immutable conversational memory and mutable authored notes serve different
   purposes. deleting a proposed note file does not erase committed git history
   or captured observations; revoking memory admission does not remove retained
   material. a competitor's editable “memory” may be a preference file, a summary,
   a task record or retained conversation. those are not interchangeable.
3. a task record, a scheduled wake, a delegated worker and a committed external
   effect have different lifetimes. “stop”, “delete” and “done” must specify which
   one they concern. a polished chat acknowledgement cannot settle that question.

## questions the comparison should answer

- which owner outcomes need a genuinely new capability, and which need the
  already-written contracts integrated and activated?
- where does a broad computer interface unlock useful work that the connected
  service tools cannot perform? what authority and recovery contract would change?
- which context belongs in retained evidence, working documents or current work?
- which events deserve work, a notification, a quiet update or no response?
- can the owner tell what completed, what remains blocked and what requires a
  decision without opening an operator console?
- which proposed improvements reduce the owner's supervision enough to justify
  another component, persistent state or interaction surface?

these are inputs to the later roadmap review. this baseline adds no delivery
sequence, implementation task or new qualification gate.

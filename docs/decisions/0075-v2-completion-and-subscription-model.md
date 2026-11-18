# adr 0075: v2 completion and subscription model

status: accepted scope, 2026-11-16. [f1](../mail-calendar-web-reads.md) now owns
the read-completion schemas and acceptance; [f3](../subscription-model-runtime.md)
has source and separate candidate qualification. [f2](../runtime-reliability-and-integration.md)
has qualified integrated source and isolated reliability/deployment proof;
production acceptance and reset remain pending.
implementation, qualification and production activation remain separate.

[adr 0076](0076-role-models-and-delegated-choices.md) supersedes this adr's original
shared main/memory model decision: main astra/max, memory sol/xhigh, with deliberate
native-child and per-session skid model/effort choices. the original decision
below remains its historical rationale; other finishing scope is unchanged.

[adr 0077](0077-production-acceptance-and-fresh-reset.md) subsequently makes f2 own
final stopped production activation/installed proof and a post-acceptance fresh
history reset. an irreproducible historical native incident may remain explicitly
open; new demonstrated defects still require repair. those decisions supersede
the affected historical sequencing/acceptance statements below.
[adr 0078](0078-fresh-corpus-first-acceptance.md) subsequently changes only the reset
order and full recovery-artifact replacement: preliminary reset → real journey →
final reset, with verified current recovery retained.

f1 owner refinement: web result pages are disposable; eviction/restart requires
an explicit fresh observation. original paid-read uncertainty is not retry
permission. the focused contract supersedes the earlier proposal's mail/calendar/
web schemas and reuses landed attachment manifests.

## evidence and decision

the six v2 slices establish the product foundation. the final source audit found
non-continuable gmail/calendar reads, clipped web results/text, missing incoming
`Reply-To` and deliberate mutable reads that can reuse earlier observations.
main already has no aggregate tool-call/time quota. its prompt already supplies
the owner's personality/goals and tool guidance; native subagents and skid supply
delegation. the [native failure](../issues/native-protocol-diagnostics.md) remains
open. [f2's isolated evidence](../runtime-reliability-and-integration.md#implementation-evidence)
now qualifies the discord startup/stop repair; installed acceptance remains separate.

the owner accepts three separately specified review units. the
[roadmap](../implementation-plan.md#v2-finishing-prs) alone owns sequencing:

1. complete mail/calendar/web reads through bounded continuation, full supported
   source text, correct reply routing metadata and fresh deliberate observations.
   preserve original callback receipts and paid-read barriers. keep existing
   draft/reply/send and calendar writes. inbox housekeeping, new invitation
   responses, outgoing attachments, memory ranking, maps and worker-history
   expansion are outside this unit.
2. repair discord startup/stop resilience and diagnose/reproduce/repair native
   failures at their owning layer. then qualify the combined useful journey and
   actual prompt/tool composition. no replacement persona, orchestration service,
   relaxed validation, automatic unpark or blind effect replay.
3. pin jarvis cognition to the owner's `gpt6astra-max`: authenticated codex
   dispatch model `gpt-6-astra`, reasoning `max`, through the existing personal
   codex subscription and the owner's provider library (`provider-runtime` in
   `llm-calling`). select the actual authenticated catalog row; the shorthand is
   not an invented wire model key. no model substitution, api-key generation
   route or fallback. preserve one shared selection for main and isolated memory
   roles; skid profiles retain their own choices. qualify exact library/runtime
   pins and subscription/model/effort evidence before activation. unavailable
   target support blocks that qualification; it does not select another model.

## scope and supersession

this supersedes adr 0071's search deferral only for the selected mail/calendar/web
capabilities, not the whole [search proposal](../complete-and-continuable-searches.md)
or its proposed schemas. each review unit gets one implementation spec next;
these decisions do not preempt that design or start implementation.

the model target supersedes the fixed `gpt-5.6-terra/high` selection at its future
qualified cutover, including affected adr 0065/SPEC model and runtime pins.
current source and historical qualification retain their exact old artifacts.
keep the existing kernel/provider ownership, authority and recovery contracts.
model-driven runtime/dependency upgrades belong to f3; f1/f2 still own necessary
upstream read/failure repairs and their adoption. one integration owner reconciles
shared pins before combined qualification.

browser control, credential products, hosted interactive deliverables/television,
broader search, budget and memory expansion remain deferred. incoming attachments
and event adapters keep their existing owners. no new framework or table is
adopted here.

## consequences and proof

deeper reading costs more calls/context when chosen; provider limits, unavailable
content, live-source changes and finite operation bounds remain explicit. it
does not promise exhaustive web coverage. `max` reasoning may increase latency
and background-role duration; qualify useful behavior within actual deadlines.
native diagnostics are bounded work; the root-cause repair size is still unknown.

each forthcoming spec scopes temporary end-to-end/live red/green/refactor proof,
content design and adversarial review, then deletes only its temporary probes.
preserve approved memory checks and `scripts/verify`; no new standing suite.
integrated acceptance consumes slices 5–6, the completed reads and the qualified
target model/runtime. stopped production conversion/activation remains a separate
final operation. competitor parity remains unproved by feature inventories or
jarvis-only journeys.

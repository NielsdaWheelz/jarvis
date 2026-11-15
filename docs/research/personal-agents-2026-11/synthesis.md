# what the competitive research means for jarvis

assessment as of 2026-11-14. these are design judgments from public evidence,
not benchmark results or accepted implementation decisions. the
[method](method.md) defines evidence limits; the [jarvis baseline](jarvis-baseline.md)
distinguishes current contracts from proposed v2 behavior.

the subsequent owner review is adopted by
[adr 0071](../../decisions/0071-simple-event-driven-v2.md). current scope is one
main for events, the existing todo concept with optional scheduled wakes, a private
repo, durable attachments and skid follow-through. approvals/results remain
ordinary conversation. browser control, credential features and interactive
television/artifacts are deferred; shared memory stays in its separate pr.
the [roadmap](../../implementation-plan.md#v2-reviewable-pr-slices) owns delivery.
the research judgments below remain hypotheses, not additional scope.

the useful competitive target is work the owner can leave with the system and
trust to return in a useful state. that requires continuity, access, judgment
about when to act, and an intelligible account of the result. a large feature
catalog does not establish that these work together.

## the product choices worth comparing

the dossiers show several ways to package persistent agency:

| product | useful design emphasis | evidence to inspect |
| --- | --- | --- |
| dots | one visible relationship coordinating work across execution contexts | [delegation, context and activity controls](openai-dots.md) |
| duet | preparation and triage, with visible tasks and decisions | [task surfaces, periodic attention and connector limits](claude-duet.md) |
| muse | personal context and a customizable interface around ongoing work | [memory files, spaces, local access and permissions](meta-muse.md) |
| grok bot | responsibilities distributed among persistent bots | [role memory, routines and shared execution resources](grok-bot.md) |
| instinct | ordinary communication as the front door to errands | [text, calls, payments and evidence limits](instinct.md) |

these emphases are our interpretation. each product overlaps the others. no
evidence in this pass establishes which one completes this owner's work best.

for jarvis, the strongest immediate research finding is the overlap with existing
v2 intent at the level of responsibilities. event-driven continuation, useful work records, recurring review,
authored notes and durable originals already have
[focused contracts](../../implementation-plan.md#delivery-map). assess those
contracts against concrete journeys before replacing their architecture. this
overlap establishes neither equivalent usability nor comparable outcomes.

several differences remain substantial:

| product question beyond current delivery | evidence to study | what would justify expansion |
| --- | --- | --- |
| voice and ordinary messaging access | the dossiers' channel inventories | useful requests currently lost or deferred because capture is awkward |
| outbound calls and personal errands | grok and instinct call workflows | valuable tasks that require speaking with a person or a phone-only business |
| broader browser access and credential brokerage | each product's execution and login contracts | repeated useful work blocked by missing integrations, with understood authority costs |
| persistent interactive results | muse spaces and instinct files | directly manipulating a result saves more effort than further chat |
| payment execution | the distinct wallet and saved-card routes | a justified owner need beyond bookkeeping, with explicit spending and recovery rules |
| assistance involving other people | grok team bots and instinct groups | enough benefit to justify changing the single-owner audience and authority model |

these are open product evaluations, not commitments to copy the surfaces. source
details and feature ids are in the [comparison](comparison.md).

## distinctions that determine whether the system works

**remembering evidence and managing current work are separate jobs.** a retained
conversation explains how a decision arose. a work record says what remains to
be done. an editable brief expresses current intent. their update and deletion
rules differ. jarvis's proposed separation among memory, notes and work is useful;
the question is whether the agent can use it coherently. competitor memory
features are documented at different levels, so editable files, generated
preferences and historical retrieval should not share one undifferentiated
checkmark. jarvis deliberately retains historical evidence: deleting an authored
note does not erase git history or captured observations, and revoking admission
does not erase existing memory. see the five dossiers' memory sections.

**availability does not imply continuous inference.** background responsibility
can be implemented by event delivery, periodic checks, timers and resumed work.
the important product facts are what triggers attention, what survives downtime,
and how pending work returns. much of the competitors' internal scheduling is
undisclosed. jarvis already has owners for
[event ingestion and recurrence](../../event-sources-and-recurring-work.md).

**access, permission and completion are distinct facts.** a working login permits
entry to a service. it does not settle whether an operation is authorized. an
approval authorizes a particular operation; it does not prove that the merchant,
mail server or calendar accepted it. preserve these distinctions in both code
and the owner's view. payment and credential chapters in the dossiers provide
concrete examples.

**permission to execute does not settle permission to disclose.** a task may
require reading private evidence and producing a public result. decide separately
which information may cross that boundary. the
[muse](meta-muse.md#disclosed-execution-mechanism),
[duet](claude-duet.md#authority-confidentiality-and-credentials) and
[dots](openai-dots.md#authority-is-route-specific) disclosures describe different
controls and gaps. they do not prove that jarvis needs the same machinery. the
settled trusted-native proposal remains an intentional authority expansion;
understanding its consequences is distinct from reopening that choice.

**a broad computer is an execution domain.** it brings filesystem, network,
browser-session and process authority. it cannot be treated as just another
connector when those paths bypass connector policy. the
[notes contract](../../private-notes-and-rolodex.md#authority-and-composition)
already states this consequence explicitly. adding a remote browser later would
need equally clear ownership, access and effect semantics.

**parallel work needs integration.** worker count says little about the finished
result. the owner benefits when someone resolves inconsistent findings, notices
missing evidence, carries useful work forward and reports the actual outcome.
jarvis's [delegated follow-through contract](../../delegated-follow-through.md)
already places that responsibility with main. specialist interfaces are optional;
integration is not.

**interruption names a scope.** current reasoning, delegated work, schedules,
credentials and entered effects have different lifetimes. the comparison should
ask what each control actually stops and what continues. jarvis's current host
controls and proposed semantic conversational stop are different contracts;
their tradeoff is already explicit in o9. do not infer stronger guarantees from
a reassuring acknowledgement.

## interactions worth examining closely

these are candidates for evaluation, not a list of features to implement.

| interaction | owner benefit to test | smallest relevant jarvis surface |
| --- | --- | --- |
| “what needs me?” | decisions and blockers become visible without rereading every conversation | current work, approvals and concise conversation |
| a prepared decision | the owner receives alternatives, evidence and the specific choice that remains | ordinary research, notes and conversational questions |
| visible completion evidence | the owner can distinguish a draft, an attempted operation and confirmed completion | original receipts, artifacts and response content |
| correction of enduring guidance | one correction improves later work without rewriting historical evidence | proposed notes plus current memory provenance |
| interruption with a truthful result | the owner knows what stopped, what is still settling and what remains scheduled | existing controls/receipts and the chosen future stop contract |
| an artifact worth reopening | compare direct editing/manipulation with further chat | notes/attachments supply documents; a persistent interactive surface is a separate product question |
| quiet recurring attention | unattended work advances without generating a feed of trivial notices | proposed events, recurrence and main's judgment |
| cheap capture from daily life | a thought, file or request reaches the same continuing context with little effort | first assess discord/file journeys; voice or another channel is a separate choice |

concrete examples of these surfaces are linked in the
[comparison](comparison.md). their presence establishes an interaction pattern,
not its usefulness to this owner.

## less obvious hypotheses worth testing

**measure attention returned.** for a few real tasks, record the owner's active
minutes, interventions, repeated context and corrections. include time spent
checking the agent. wall-clock task duration and tool counts miss much of the
value. a short manual record is enough to learn whether more autonomy helps.

**make understanding a deliverable.** for scientific and architectural work,
return the result with the few assumptions and pieces of evidence that govern
it. let the owner reopen the source. this fits the owner's stated preference for
retaining understanding and can be tested through output quality before adding
any mechanism.

**use a living brief.** try a short editable document describing what matters
now, what changed and which questions remain open. memory supplies history;
the brief supplies a readable present interpretation. the existing notes proposal
can host this without another ontology or mandatory template. judge whether it
reduces repeated explanations.

**look for missing decisions.** a useful dream or periodic review may discover
that work has stalled because no one made a small consequential choice. compare
such findings with generic summaries. an ordinary scheduled todo can review
blockers now; dreamer work context and selected dream wakes remain later work.
do not create a second planning agent merely to try the idea.

**study interruptions before expanding integrations.** label the handful of
times the owner intervened: missing access, missing context, unclear intent,
approval, incorrect work or absent follow-through. this reveals whether the next
connector would remove a real constraint. it requires observation, not an
analytics platform.

**test portability as a comprehension exercise.** ask whether another capable
agent could understand an active project from its brief, sources and current
work without reading the whole transcript. that probes the clarity of jarvis's
records while also exposing lock-in. credentials, execution authority and live
effects must remain outside any casual handoff.

each hypothesis has a cheap initial form. none requires a marketplace, a visible
agent organization, a workflow framework or a new client before its value is
demonstrated.

## using the research during delivery

start with a few representative owner journeys: a research brief with conflicting
sources; delegated code work followed across a restart; a changing calendar
commitment; a receipt turned into an accurate budget record; and an ordinary
personal errand. describe the result and acceptable intervention burden before
choosing features.

then map each missing behavior to an existing contract, a delivery/activation
gap, or a genuinely new product choice. keep those categories separate. revisit
the one [implementation plan](../../implementation-plan.md), adopting changed
contracts where needed. the owner has now selected a first cut and reviewable pr
slices there; this research adds no independent sequencing or pr commitments.

the principal unresolved evidence is actual behavior under comparable conditions:
task success, repeated guidance, delayed events, exhausted allowance, changed
instructions and ambiguous external effects. the
[behavior-verification issue](../../issues/personal-agent-behavior-verification.md)
records that gap. proprietary details can remain unknown; jarvis needs a justified
contract for its own behavior, not an invented reconstruction of a competitor.

# personal agent feature and mechanism comparison

as of 2026-11-14. this compares documented capability and disclosed design, not
measured quality. “unknown” means the reviewed evidence does not settle it.
availability restrictions remain in the dossiers; a short cell does not remove
them. feature ids refer to their source-linked inventory rows.

| dossier | inventory |
| --- | --- |
| dots | [DOT-01 onward](openai-dots.md#feature-inventory) |
| duet | [DUET-01 onward](claude-duet.md#feature-inventory) |
| muse | [MUSE-01 onward](meta-muse.md#feature-inventory) |
| grok bot | [GROK-01 onward](grok-bot.md#feature-inventory) |
| instinct | [INST-01 onward](instinct.md#feature-inventory) |

## relationship and continuing work

| dimension | dots | duet | muse | grok bot | instinct |
| --- | --- | --- | --- | --- | --- |
| visible organization | personal dot; delegated work (01, 16) | topic channels (06) | main and topic chats (01) | named bots (09) | personal; distinct group agent (01, 20) |
| conversation surfaces | app/web; workplace/texting restrictions (04, 10–13) | app/web (02) | app/web/mac/whatsapp (02) | desktop/mobile/x (01, 17, 40) | text, call, email (01–05) |
| voice and calls | inbound voice; outbound planned (08) | voice; outbound absent (04, 31) | voice rollout (03) | voice; approved us calls (12, 16) | concierge calls announced (07) |
| continuing attention | research plus assigned follow-up (20–21) | periodic checks (09) | goals/ideas (07) | offers/check-ins (27) | recurring coordination examples (16) |
| scheduled work | schedules and selected triggers (18–19) | routines mentioned; exact controls unknown | time/location/recurrence (08–09) | schedules and event routines (23–26) | behavior announced; scheduler unknown (16, 32) |
| context organization | selected memory and notes (22) | shared claude context (07, 28) | editable memory/identity files (05) | per-bot plus shared facts (10) | personalization; internals unknown (31–32) |
| memory portability/control | granular controls absent (24) | account import/export (29) | chat import, editing, best-effort forget (05–06) | chat correction/forget; import (10; portability section) | deletion controls; reset scope unclear (30–31) |
| owner attention surface | activity and decisions (14) | task list (11) | activity/upcoming (24) | attention/notification routing (49) | conversation; full status contract unknown (32) |

numbers in each product column use that product's prefix: “16” under dots means
`DOT-16`. duet's routine disclosure is in its
[security source](https://claude.com/resources/articles/claude-duet-safety-privacy-and-security);
its dossier deliberately leaves detailed scheduling semantics unresolved.

## execution reach and control

| dimension | dots | duet | muse | grok bot | instinct |
| --- | --- | --- | --- | --- | --- |
| cloud execution | persistent computer (27) | cloud computer/browser (10, 18) | linux workspace (10) | shared computer, separate screens (19) | own computer; internals undisclosed (01, 32) |
| local execution | opt-in computers (28) | unavailable (30) | chrome/mac (12–13) | separately gated (39) | current shipped scope unresolved |
| integration expansion | plugins (25) | inherited plugins (07, 14) | custom connectors (14) | mcp/api wrapping (20, 32) | partner routes; public extension api unknown (06, 27) |
| delegated execution | background/codex work (16–17) | code sessions; delegation unknown (23, 38) | subagents disclosed (10) | bot coordination/cloud agents (15, 32) | personal-agent network (15, 17) |
| credentials | secure forms/service (29) | isolated browser/proxy; 1password (22) | surrogates; 1password (30) | vault/forms/1password (33–35) | vault/authenticator/1password (11–14) |
| purchases | biometric wallet consent (37–38) | approved scoped cards (20–21) | approved purchases (19) | route-dependent approval (36) | checkout or funded allowance (23–25) |
| interruption | separate worker/schedule controls (39) | steer; full stop contract unknown (34) | browser stop; broader scope unknown (11) | redirect; reset survivors (14, 51) | general guarantee unknown (32) |
| independent email identity | provisioning unclear (45) | connected mail (31) | agent address (20) | roster address (22) | agent address (04–05) |

credential secrecy, login reuse, purchase permission and authority inside an
existing website session are separate dimensions. the payment cells name routes,
not universal guarantees. in particular, the grok dossier preserves conflicting
card-visibility statements, while instinct's balance differs from per-checkout
approval. inspect those chapters before drawing a security conclusion.

## outputs and interaction with others

| dimension | dots | duet | muse | grok bot | instinct |
| --- | --- | --- | --- | --- | --- |
| durable result surface | files/results (14, 32) | make tab (12) | library/artifacts (16) | library/pages (29–31) | interactive files (19) |
| direct manipulation | annotations (31) | exact artifact controls unresolved | editable spaces (17) | page controls (30) | interactive pages announced (19) |
| other participants | owner-directed engagement (33) | artifact collaboration unknown (39) | shared spaces exploratory (17) | team bots/meetings (43–48) | trusted contacts/group agent (15, 20–22) |
| operational inspection | enterprise audit limits (42) | task pages (34) | activity/system files (24) | enterprise recording (54) | complete audit contract unknown (32) |

an editable document, a downloadable file, an interactive report, and a live
application are different deliverables. this matrix deliberately does not mark
all four as equivalent “artifact support.”

## what is actually known about implementation

these are vendor disclosures. implementation detail does not establish comparative
robustness. the linked sections contain exact sources, qualifications and gaps.

| product | disclosed boundary worth studying | consequential unknown |
| --- | --- | --- |
| [dots](openai-dots.md#disclosed-mechanisms-and-their-limits) | execution separated from coordination/safeguards | coverage across routes; effect recovery |
| [duet](claude-duet.md#disclosed-mechanisms-and-their-limits) | isolated browser and credential substitution | duet-specific durability beyond related-product lineage |
| [muse](meta-muse.md#disclosed-execution-mechanism) | runtime cell; host permission services | reconciliation and cancellation during effects |
| [grok bot](grok-bot.md#disclosed-architecture-and-its-limits) | shared user microvm; separate role context | external-effect recovery beyond computer restoration |
| [instinct](instinct.md#disclosed-implementation-and-its-limits) | separate monitors; partner credential/payment systems | orchestration, memory and execution persistence |

some vendors disclose more engineering than others. a longer mechanism section
therefore measures public visibility, not automatically better engineering.
none of these dossiers establishes a complete production runtime from public
source code.

## cost and availability cannot be flattened into one score

the dossiers record dated plans, regions, previews and limits. subscriptions,
shared model allowances, product-specific tokens, background usage, extra credit
and merchant purchases are different costs. a nominal monthly price cannot
establish cost per completed owner task. compare
[dots](openai-dots.md#pricing-limits-and-evidentiary-quality),
[duet](claude-duet.md#price-limits-and-failure-visibility),
[muse](meta-muse.md#reliability-privacy-price-and-limits),
[grok](grok-bot.md#product-boundary-and-availability) and
[instinct](instinct.md#privacy-interruption-and-economics) in their own units.

the same caution applies to reliability. advertised availability, a successful
demo, a vendor evaluation and an owner's repeatable outcome are different
evidence. [behavioral comparison remains unperformed](../../issues/personal-agent-behavior-verification.md).

## mapping the comparison to jarvis

| competitive capability | existing jarvis owner or boundary | question left for planning |
| --- | --- | --- |
| continuation and delegation | native main/worker foundations; proposed o6/o9 | integrated outcome and installed behavior |
| proactive attention | proposed event sources, recurrence and selected dreams | useful work and notification quality |
| current work | proposed o7 records | whether the owner can understand progress and intervene cheaply |
| long-term context | accepted memory source plus proposed authored notes | useful retrieval, correction and clear retention consequences |
| file work | proposed attachments/native notes | actual supported journeys and output handling |
| interactive results | no equivalent accepted client surface | whether direct manipulation earns new product scope |
| broad browsing, credentials, calls and payments | beyond current delivery, except trusted-native notes expansion | concrete unmet need and explicit authority contract |
| groups and teams | single-owner boundary | benefit sufficient to justify a different product |

the [baseline](jarvis-baseline.md) links each owning contract. the
[synthesis](synthesis.md) develops the implications without creating another
roadmap.

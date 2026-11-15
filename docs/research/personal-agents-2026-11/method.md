# research scope and evidence

this is a public-evidence comparison of openai dots, anthropic claude duet, meta
muse, xai grok bot and instinct, collected on 2026-11-14. its purpose is to inform
a later jarvis product decision. it changes no accepted requirement, authority,
dependency, deployment or delivery order. [the implementation plan](../../implementation-plan.md)
remains the only roadmap; [the spec](../../../SPEC.md) remains authoritative.

the later owner decision is recorded separately in
[adr 0071](../../decisions/0071-simple-event-driven-v2.md). adopting jarvis's own
target does not strengthen any claim about a competitor's internals or behavior.

## what the evidence establishes

each product dossier separates the following:

| evidence | what it establishes |
| --- | --- |
| documented behavior | an official guide describes a usable feature, configuration or limitation; this is a product contract, not our successful execution |
| disclosed mechanism | the vendor or another directly responsible implementer explains a specific mechanism; it remains a disclosure, not an independent audit |
| vendor claim | marketing, a demonstration or a performance assertion; availability and reliability need separate evidence |
| third-party observation | an attributed report of a particular experience; neither universal behavior nor hidden architecture follows from it |
| inference | our explanation or design interpretation; the premises are linked and the conclusion is explicitly qualified |
| unknown | the reviewed public material does not establish the answer; this does not mean the feature is absent |

availability is a separate axis: documented available, beta/preview, restricted,
announced, historical or unresolved. a detailed architecture description can
still describe an unshipped capability. conversely, a shipped capability can
have no disclosed implementation.

the dossiers retain their own concise evidence labels and source ids. stable
feature ids permit comparisons without recopying the underlying evidence.

## source selection and currency

prefer official product guides, support articles, release notes, security
descriptions, legal terms and directly responsible integration vendors. use news
and user reports to find questions and describe attributed experiences. technical
implementation claims require primary evidence. an adjacent model, sdk, acquired
product or coding agent supplies no proof about the named product unless a
primary source connects them.

read source bodies before accepting claims. search snippets can lag current
pages. preserve dated differences between launch announcements and current
support; do not combine incompatible limits or entitlements into a fictional
universal plan. record publication/update dates only when the source states
them. an access date is not a publication date. prices and release restrictions
are snapshots, not forecasts.

link evidence beside claims and retain a source ledger in each dossier. summarize
rather than reproduce source text. an inaccessible page supplies an explicit gap,
not a guessed answer. public documentation is not a description of every private
implementation detail; undocumented schedulers, databases, model routing and
retry protocols remain unknown.

## comparison coverage

the common investigation covers:

- product identity, availability, cost, limits and onboarding;
- conversation surfaces, voice, continuity and personalization;
- memory, retrieval, files, durable artifacts and portability;
- proactive work, event sources, schedules and ongoing commitments;
- connectors, browsers, computers, credentials and payments;
- delegation, concurrency, collaboration and sharing;
- approvals, interruption, recovery, observability and privacy;
- concrete workflows and the interaction details that reduce owner effort.

this is a broad pass over the discovered official corpus, not a claim to enumerate
every private beta, undisclosed feature or undocumented edge case. coverage and
gaps belong with each product. feature counts measure inventory size, not product
quality.

## what this pass does not measure

no competitor accounts were provisioned or connected to personal services. no
paid tasks, purchases, calls, messages, destructive operations or controlled
failure trials were run. public demonstrations are identified as such.

we therefore cannot rank actual task success, latency, cost per completed job,
memory quality, notification quality or recovery reliability. comparative
judgments in the synthesis are design hypotheses, grounded in documented
capabilities. they are not benchmark results.

jarvis's baseline is a repository/document snapshot. source implementation,
accepted target, proposed contract and installed behavior are different facts.
this research did not inspect the running deployment or repeat its qualification.

## handoff to later planning

a useful candidate must name an owner outcome, the existing jarvis capability it
uses or changes, the smallest missing mechanism, and the evidence that would
justify delivery. competitor parity alone is insufficient. settle any authority
or product change in the existing spec/adr process before implementation; do not
turn these research files into a second roadmap.

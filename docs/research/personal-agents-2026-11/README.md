# personal agent competitive research

public-evidence snapshot, 2026-11-14. five product dossiers investigate features,
user interactions, disclosed mechanisms, commercial limits and unresolved
questions. the research itself changes no product contract or runtime.
the subsequent owner review is now adopted in
[adr 0071](../../decisions/0071-simple-event-driven-v2.md) and the single
[roadmap](../../implementation-plan.md#v2-reviewable-pr-slices). dossiers remain
the dated public-evidence snapshot, not implementation or comparative acceptance.

start with the [comparison](comparison.md), then the
[synthesis for jarvis](synthesis.md). the main finding is that jarvis's existing v2
contracts already address many of the same responsibilities. this is no proof
of comparable experience: broader execution access, everyday communication and
interactive results remain substantive product differences. useful comparison
separates these choices from unfinished integration and activation. public
documentation cannot establish comparative reliability.

## product dossiers

| product | dossier focus |
| --- | --- |
| [openai dots](openai-dots.md) | persistent relationship, delegation, cloud/local work, selected context, action review and wallet |
| [anthropic claude duet](claude-duet.md) | preparation, tasks, connected work, isolated credentials/browser, payments and consumer memory |
| [meta muse](meta-muse.md) | personal context, editable memory, spaces, device access, schedules and disclosed execution boundaries |
| [xai grok bot](grok-bot.md) | persistent bot roles, shared resources, routines, integrations, collaboration and controls |
| [instinct](instinct.md) | text/call interaction, personal errands, partner integrations and the limits of its sparse public documentation |

each dossier has stable feature ids, evidence links beside claims, a dated source
ledger, and explicit unknowns. a vendor description of a mechanism is not an
independent demonstration that it works reliably.

## comparison and context

- [feature and mechanism comparison](comparison.md): common dimensions, meaningful
  differences and the source feature ids behind them.
- [jarvis baseline](jarvis-baseline.md): the pre-decision snapshot of contracts,
  recorded implementation and then-proposed v2 slices, with links to their owners.
- [synthesis](synthesis.md): architectural distinctions, interaction hypotheses
  and questions for later planning.
- [research method](method.md): scope, evidence labels, source currency and limits.
- [unverified product behavior](../../issues/personal-agent-behavior-verification.md):
  the remaining gap between public claims and comparable observed results.

the [implementation plan](../../implementation-plan.md) remains the only active
roadmap. its current v2 scope supersedes the research's earlier planning questions;
the budget contract remains later scoped work.
the [spec](../../../SPEC.md) remains authoritative.

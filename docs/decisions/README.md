# Architecture decision records

Accepted ADRs are permanent records of why Jarvis is shaped this way. They are
not implementation suggestions.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-small-personal-agent.md) | One small personal agent system | Accepted; trace amended by 0010/0019; internal gate added by 0019 |
| [0002](0002-optmem-inspired-memory.md) | Immutable raw memory and rebuildable views | Accepted |
| [0003](0003-natural-discord-and-autonomy.md) | Natural Discord and a narrow approval boundary | Accepted; server organization superseded by 0011; generic local-write scope superseded by 0014 |
| [0004](0004-python-codex-and-tool-kernel.md) | Python, Codex, `provider-runtime`, and `llm-tools` | Accepted; session/context amended by 0012; portable-Web ownership by 0014; generic loop by 0017; exact provider boundary by 0018 |
| [0005](0005-reuse-integrations.md) | Reuse working integrations; defer new ones | Accepted; Discord tool scope superseded by 0011; public Web amended by 0014; revoked Google grant re-consent amended in place |
| [0006](0006-no-workflow-framework.md) | No v1 workflow framework | Accepted; bounded agent-kernel distinction clarified by 0017 |
| [0007](0007-central-messages-and-unified-actions.md) | Central messages and one action ledger | Accepted; schemas superseded by 0010; session by 0012; delivery by 0016; action-resolution by 0017; recorder/cross-run mapping by 0018/0019 |
| [0008](0008-embedding-source.md) | Embedding through an embedding-scoped OpenAI credential | Accepted; amends 0004 |
| [0009](0009-least-privilege-discord-and-host-rendered-approval.md) | Least-privilege Discord and a host-rendered approval preview | Accepted; Discord permissions superseded by 0011; approval remains |
| [0010](0010-minimal-durable-state.md) | Minimal message and action durable state | Accepted; tool naming amended by 0013; delivery amended by 0016; cross-run/recorder facts amended by 0018 and 0019 |
| [0011](0011-single-channel-discord.md) | One configured Discord channel, transport only | Accepted; supersedes Discord organization/tool scope in 0003, 0005, and 0009 |
| [0012](0012-resumable-session-and-context.md) | Resumable main session over provider-neutral context | Accepted; amends 0004 and 0007; implementation/polling/admission amended by 0017–0019 |
| [0013](0013-unversioned-v1-tools.md) | Unversioned v1 tool names | Accepted; occupied-position evidence amended by 0018 and 0019 |
| [0014](0014-minimal-v1-tool-catalog.md) | Exact minimal v1 tool catalog with portable Web tools | Accepted; supersedes parts of 0003 and 0004; amends 0005 |
| [0015](0015-explicit-v1-proactivity.md) | User-facing proactivity only through requested wakes | Accepted; schedule receipt semantics amended by 0019 |
| [0016](0016-provider-native-idempotency.md) | Provider-native idempotency before terminal uncertainty | Accepted; supersedes delivery semantics in 0007 and 0010; schema cost amended by 0018; attempt ceiling by 0019 |
| [0017](0017-extract-agent-kernel.md) | Extract the reusable bounded agent kernel | Accepted; corrected provider/loop/admission contract incorporated; durable mapping in 0018; final seams in 0019 |
| [0018](0018-serial-kernel-and-bounded-recovery.md) | Map the serial kernel and bounded recovery into four tables | Accepted; amends 0010, 0012, 0013, and 0017; final seams amended by 0019 |
| [0019](0019-ground-writes-and-close-recovery-seams.md) | Ground writes and close the remaining recovery seams | Accepted; amends 0010, 0012, 0015, and 0018 |

To supersede an ADR, add a new ADR that names it, provides observed evidence,
documents migration impact, and updates the normative specification and tests.

ADRs 0001 through 0006 were written on the same day as the specification they
justify. They are founding rationale rather than records of decisions taken under
observed pressure. That is worth knowing when reading SPEC section 13's
"observed evidence" bar for future ADRs: the bar applies to changing these
decisions, not to how they were originally reached.

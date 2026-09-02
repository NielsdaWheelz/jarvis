# Architecture decision records

Accepted ADRs are permanent records of why Jarvis is shaped this way. They are
not implementation suggestions.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-small-personal-agent.md) | One small personal agent system | Accepted; trace amended by 0010 |
| [0002](0002-optmem-inspired-memory.md) | Immutable raw memory and rebuildable views | Accepted |
| [0003](0003-natural-discord-and-autonomy.md) | Natural Discord and a narrow approval boundary | Accepted; server organization superseded by 0011; generic local-write scope superseded by 0014 |
| [0004](0004-python-codex-and-tool-kernel.md) | Python, Codex, `provider-runtime`, and `llm-tools` | Accepted; session/context amended by 0012; portable-Web ownership amended by 0014; generic loop ownership amended by 0017 |
| [0005](0005-reuse-integrations.md) | Reuse working integrations; defer new ones | Accepted; Discord tool scope superseded by 0011; public Web amended by 0014 |
| [0006](0006-no-workflow-framework.md) | No v1 workflow framework | Accepted; bounded agent-kernel distinction clarified by 0017 |
| [0007](0007-central-messages-and-unified-actions.md) | Central messages and one action ledger | Accepted; schemas superseded by 0010; session lifecycle amended by 0012; duplicate-delivery semantics superseded by 0016; action-resolution correlation amended by 0017 |
| [0008](0008-embedding-source.md) | Embedding through an embedding-scoped OpenAI credential | Accepted; amends 0004 |
| [0009](0009-least-privilege-discord-and-host-rendered-approval.md) | Least-privilege Discord and a host-rendered approval preview | Accepted; Discord permissions superseded by 0011; approval remains |
| [0010](0010-minimal-durable-state.md) | Minimal message and action durable state | Accepted; tool-name versioning superseded by 0013; duplicate-delivery cost superseded by 0016 |
| [0011](0011-single-channel-discord.md) | One configured Discord channel, transport only | Accepted; supersedes Discord organization/tool scope in 0003, 0005, and 0009 |
| [0012](0012-resumable-session-and-context.md) | Resumable main session over provider-neutral context | Accepted; amends 0004 and 0007; implementation boundary amended by 0017 |
| [0013](0013-unversioned-v1-tools.md) | Unversioned v1 tool names | Accepted; supersedes part of 0010 |
| [0014](0014-minimal-v1-tool-catalog.md) | Exact minimal v1 tool catalog with portable Web tools | Accepted; supersedes parts of 0003 and 0004; amends 0005 |
| [0015](0015-explicit-v1-proactivity.md) | User-facing proactivity only through requested wakes | Accepted |
| [0016](0016-provider-native-idempotency.md) | Provider-native idempotency before terminal uncertainty | Accepted; supersedes delivery semantics in 0007 and 0010 |
| [0017](0017-extract-agent-kernel.md) | Extract the reusable bounded agent kernel | Accepted; amends 0004, 0007, and 0012; clarifies 0006 |

To supersede an ADR, add a new ADR that names it, provides observed evidence,
documents migration impact, and updates the normative specification and tests.

ADRs 0001 through 0006 were written on the same day as the specification they
justify. They are founding rationale rather than records of decisions taken under
observed pressure. That is worth knowing when reading SPEC section 13's
"observed evidence" bar for future ADRs: the bar applies to changing these
decisions, not to how they were originally reached.

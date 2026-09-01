# Architecture decision records

Accepted ADRs are permanent records of why Jarvis is shaped this way. They are
not implementation suggestions.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-small-personal-agent.md) | One small personal agent system | Accepted |
| [0002](0002-optmem-inspired-memory.md) | Immutable raw memory and rebuildable views | Accepted |
| [0003](0003-natural-discord-and-autonomy.md) | Natural Discord and a narrow approval boundary | Accepted |
| [0004](0004-python-codex-and-tool-kernel.md) | Python, Codex, `provider-runtime`, and `llm-tools` | Accepted |
| [0005](0005-reuse-integrations.md) | Reuse working integrations; defer new ones | Accepted |
| [0006](0006-no-workflow-framework.md) | No v1 workflow framework | Accepted |
| [0007](0007-central-messages-and-unified-actions.md) | Central messages and one action ledger | Accepted |

To supersede an ADR, add a new ADR that names it, provides observed evidence,
documents migration impact, and updates the normative specification and tests.

# cleanup map

this is an implementation map and work queue, not a replacement specification.
the initial audit found implementation history embedded in runtime construction,
mixed service responsibilities, and duplicate construction. it did not establish
that the six specified tables or their columns are unnecessary.

| slice | implementation owners | contract to preserve |
|---|---|---|
| role and capability construction | `definitions.py`, `read_composition.py`, `write_composition.py`, `kernel.py` | exact role, catalog, plan, and session identities |
| conversation and context | `messages.py`, `checkpoints.py`, `context.py`, `history.py`, `terminal.py`, `JarvisThreadRunner` | canonical input, atomic settlement, truthful output |
| service and discord | `service.py`, `discord.py`, `cli.py` | single-channel ingress, outbox, shutdown, foreground priority |
| provider sessions and capacity | `session.py`, `codex_config.py`, `admission.py`, `state.py` | disposable sessions, bounded provider work, ownership |
| paid decision and read recovery | `decisions.py`, `read_positions.py`, read dispatchers | original decisions and receipts replay without redispatch |
| memory storage and retrieval | `memory.py`, `memory_retrieval.py`, `memory_tools.py`, `embeddings.py` | immutable raw memory, rebuildable derived state |
| memory work and rebuild | `memory_workers.py`, `rebuild.py`, recall probes | isolated cognition, transactional commit, cancellation |
| connector reads | `read_tools.py`, `connectors.py`, `read_dispatch.py` | bounded observations, exact identifiers, typed completeness |
| writes and recovery | `write_tools.py`, `write_connectors.py`, `write_dispatch.py`, `actions.py` | immutable effects, finite attempts, evidence-based recovery |
| grounding and approvals | `write_gate.py`, `write_policy.py`, `approval.py`, `approval_runtime.py` | current owner authority and exact approved payload |
| scheduled wakes | `schedule_tools.py`, schedule transactions in `actions.py`, `proactivity.py` | immutable creation receipt, one durable waking input |
| worker control | `agent_tools.py`, `agent_control.py` | opaque references, bounded cli operations, no blind replay |
| schema and deployment | `db.py`, `ownership.py`, `migrations/`, `deploy/` | six application tables, one deployment owner |

each pr follows: trace callers and specification, verify a concrete finding,
characterize the affected path, make one coherent change, independently review,
run required checks, remove temporary characterization, commit, push, merge,
and remove its branch/worktree. existing behavioral regressions remain.
synthetic provider transports and disposable postgres establish local integration
behavior; they are not evidence of live provider or production acceptance.

the first cut retires the obsolete pre-approval write runtime. its qualifier uses
the current catalog and plan while retaining its five explicit draft/calendar
operations. current production identities remain unchanged. historical admission
values remain in admission sizing used by migration and the stopped proactivity
qualifier; no old runtime constructor is needed to describe those numbers.

follow-ups are recorded individually under [issues](issues/):
[direct role construction](issues/direct-role-construction.md),
[read construction](issues/read-construction.md),
[wake notification](issues/wake-notification.md),
[discord retries](issues/discord-delivery-retries.md), and
[admission predecessors](issues/admission-predecessors.md).

[hosted verification](issues/github-actions-billing.md) is separately blocked by
the github account billing restriction.

# cleanup map

this is an implementation map and work queue, not a replacement specification.
the initial audit found implementation history embedded in runtime construction,
mixed service responsibilities, and duplicate construction. it did not establish
that the six specified tables or their columns are unnecessary.

| slice | implementation owners | contract to preserve |
|---|---|---|
| role and capability construction | `definitions.py`, `tool_composition.py`, `kernel.py` | exact role, catalog, plan, and session identities |
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

memory workers now own rememberer and dreamer execution in `memory_workers.py`.
stopped memory maintenance constructs only the dreamer and its two memory
bindings. it retains shared settings validation but no longer validates unused
external connector construction. current role and plan identities are unchanged.
current runtime construction now builds each role directly, without constructing
and replacing older roles. slice3/4 constructors and result bundles are removed;
their qualification consumers use current roles. slice1/2 test runtimes and the
remaining obsolete read catalog are removed. the conversation runner requires
its current memory ports and one checkpoint-aware dispatcher factory. tests use
the current catalog; role-only tests construct only their selected role.
the duplicated slice3 read catalog is deleted after its consumers moved to the
memory-only or current full catalog; no shared factory is needed.
current python names describe roles and tool composition; durable profile ids
retain their historical strings. the unused `proactive` plan alias is removed,
leaving the explicit `scheduled_wake` selection.

discord delivery now has one response/retry policy for ordinary messages,
approval attachments, and disabling approval components. each operation keeps
its request construction; disabling still requires the exact requested id.
the small request callback replaces duplicated policy, with no generic retry
framework or new state.

follow-ups are recorded individually under [issues](issues/):
[wake notification](issues/wake-notification.md),
and [admission predecessors](issues/admission-predecessors.md).

[hosted verification](issues/github-actions-billing.md) is separately blocked by
the github account billing restriction.

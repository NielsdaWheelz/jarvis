# cleanup map

this is an implementation map and work queue, not a replacement specification.
the initial audit found implementation history embedded in runtime construction,
mixed service responsibilities, and duplicate construction. it did not establish
that the six specified tables or their columns are unnecessary.

| slice | implementation owners | contract to preserve |
|---|---|---|
| role and capability construction | `definitions.py`, `tool_composition.py`, `kernel.py` | exact role, catalog, plan, and session identities |
| conversation and context | `messages.py`, `checkpoints.py`, `context.py`, `history.py`, `terminal.py`, `thread_runtime.py` | canonical input, atomic settlement, truthful output |
| service and discord | `service.py`, `discord.py`, `cli.py` | single-channel ingress, outbox, shutdown, foreground priority |
| provider sessions and capacity | `session.py`, `codex_config.py`, `admission.py`, `state.py` | disposable sessions, bounded provider work, ownership |
| paid decision and read recovery | `decisions.py`, `read_positions.py`, read dispatchers | original decisions and receipts replay without redispatch |
| memory storage and retrieval | `memory.py`, `memory_retrieval.py`, `memory_tools.py`, `embeddings.py` | immutable raw memory, rebuildable derived state |
| memory work and rebuild | `memory_workers.py`, `rebuild.py` | isolated cognition, transactional commit, cancellation |
| connector reads | `read_tools.py`, `connectors.py`, `read_dispatch.py` | bounded observations, exact identifiers, typed completeness |
| writes and recovery | `write_tools.py`, `write_connectors.py`, `write_dispatch.py`, `actions.py` | immutable effects, finite attempts, evidence-based recovery |
| grounding and approvals | `write_gate.py`, `write_policy.py`, `approval.py`, `approval_runtime.py` | current owner authority and exact approved payload |
| scheduled wakes | `schedule_tools.py`, schedule transactions in `actions.py`, `proactivity.py` | immutable creation receipt, one durable waking input |
| worker control | `agent_tools.py`, `agent_control.py` | opaque references, bounded cli operations, no blind replay |
| schema and deployment | `db.py`, `ownership.py`, `migrations/`, `deploy/` | six application tables, one deployment owner |

each pr follows: trace callers and specification, verify a concrete finding,
make one coherent change, independently review, and run the current required
checks. [adr 0046](decisions/0046-reset-testing.md) removes the old tests,
fixtures, and qualification machinery. static/build checks do not establish
behavioral, live provider, or production acceptance. the separate
[testing redesign](issues/testing-redesign.md) defines the replacement.

runtime construction builds the five current roles directly. the conversation
runner requires its memory ports and one checkpoint-aware dispatcher factory.
role-only consumers construct their selected role.
current python names describe roles and tool composition. durable profile ids
retain their historical strings, preserving current role and plan identities.

the service requires its memory workers, scheduled wakes, action recovery, and
approval handler. context requires recall, the run cancellation token, and its
authoritative batch clock. these constructors describe the complete application;
absent-feature modes from earlier slices are removed. gateway and timer binding
still resolve the real callback cycles during startup.

`thread_runtime.py` owns main-run construction, its observation evidence, and the
handoff to remembering. `service.py` owns ingress, delivery, and work scheduling.
the cli constructs both explicitly; provider-runtime construction always verifies
the frozen dependencies.

conversation settlement has one required callback for transferring an owner group
to remembering. checkpoint state retains consumed ids for metrics and callback
deduplication; it no longer exports unused owner-id history or stores an unused
owner token. unused message queries and the unowned transaction wrapper are gone.

memory workers own rememberer and dreamer execution in `memory_workers.py`.
stopped maintenance constructs only the dreamer and its two memory bindings.
it retains shared settings validation without constructing unused connectors.

host recall and memory tools use the same repository implementation for exact-id
reads. the host still validates the model's selection, reopens the stored rows,
and rejects an incomplete or reordered result before rendering prompt sections.
this read projection contains text, timestamps, and summary lineage; it does not
load embeddings. memory writes remain owned by `MemoryStore` transactions.

memory creation and embedding queues return only the metadata their callers use.
embedding update queries return only an id to detect a missing row, avoiding a
round trip of the stored vector. vector validation, database columns, and raw-memory
immutability remain unchanged.

new memories and embedding backfill share one batch-write loop. it reports
partial progress to background scheduling and stops between writes on cancellation
or failure. the embedding adapter always uses provider-runtime with the managed
http client; its unused alternate runtime injection is removed.

discord delivery now has one response/retry policy for ordinary messages,
approval attachments, and disabling approval components. each operation keeps
its request construction; disabling still requires the exact requested id.
the small request callback replaces duplicated policy, with no generic retry
framework or new state.

action storage exposes only the entrypoints used by production. recovered actions
settle their admitted input union through one grouped transaction; due wakes
complete inside the message settlement transaction. unused action methods and a
connector serializer are removed, and schedule conclusion owns its transaction
body directly.

the wake timer emits a parameterless work notification. requested time remains
in the scheduled action; the timer uses its clock only to decide when to notify.

historical admission values remain only where journal migration still uses them.
removing those predecessors requires the
live-state evidence recorded under
[admission predecessors](issues/admission-predecessors.md).

[hosted verification](issues/github-actions-billing.md) is separately blocked by
the github account billing restriction.

the database owner reports disconnection during queries and commit as ownership
loss. memory workers, dispatch, and approval handling preserve that defect;
background coordination lets unexpected failures reach the service lifetime.
ordinary memory failures retain their retry behavior. this replaces silent idle
results with process failure and the existing restart recovery path.

google token encryption uses the qualified single secret and key version. the
unused keyring parser, setting, and secret matching entries are removed. deployment
still requires the [environment cutover](issues/connector-keyring-cutover.md);
existing token ciphertext needs no migration.

read dispatchers depend directly on the recorder protocol and keep that recorder
private. their unused accessors and supporting generic parameters are removed;
execution, recovery, and evidence remain unchanged.

the next verified slice is [optional approval ports](issues/optional-approval-ports.md).

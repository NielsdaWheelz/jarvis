# production transient memory read recorder

status: upstream implementation dependency, inspected 2026-10-08.

problem: disposable dreaming needs llm-tools' ordinary executor with run-local,
nondurable read receipts. the pinned package exposes its in-memory implementation
only as `llm_tools.testing.InMemoryPositionRecorder`, whose default is durable.

impact: the accepted [dreamer contract](../universal-memory.md#daily-dreaming)
cannot consume a supported production helper yet. importing tests or duplicating
executor semantics in jarvis would give this small boundary two owners.

evidence: installed tools revision `2adb9790` defines the public `PositionRecorder`
protocol but keeps that helper in `testing.py`. kernel revision `9d57e894` already
provides `TransientModelDecisions` and pins tools/provider dependencies exactly.
no new kernel inference API is needed.

resolved when: llm-tools publishes a production transient recorder with
`durable=False` fixed and read-only scope, the coordinated kernel/tools pins are
adopted, and jarvis's focused memory-completion checks demonstrate run-local
receipts, discarded interrupted runs and unchanged main paid-read barriers.

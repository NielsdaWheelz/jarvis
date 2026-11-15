# compactor prompt omits accepted priorities and numeric target

status: source gap found during the 2026-10-13 optmem/uniichat comparison.

problem: `build_compactor` omits the accepted ordering: owner wording/reasons,
then lasting changes/failures, then findings, then tool-step descriptions.
it says to aim for the supplied byte target, but the initial task supplies only
a 512-dash ruler, not the numeric 512-byte target.

impact: host validation still bounds node size, but cannot enforce editorial
priorities. corrections/preferences can compete with tool noise, and size
retries lack a fully explicit initial instruction. this is a prompt/spec gap,
not observed proof of bad summaries or unbounded storage.

evidence: [compression contract](../universal-memory.md#source-parts-and-binary-construction)
and [content contract](../universal-memory.md#7-content-contract);
`src/jarvis/definitions.py:build_compactor` and
`src/jarvis/memory_workers.py:MemoryWorker.compact_one`.
inspect the effective role text and `compaction_source` payload: neither supplies
the ranking or numeric target. the host separately checks `NODE_TARGET_BYTES`.

resolved when: express the accepted priorities in the central compactor role and
supply the numeric target from the existing shared constant. verify the actual
rendered first-candidate request, then qualify synthetic owner corrections/reasons
amid tool noise, exact identifiers, omissions and truthful completion states
through the existing [live content qualification](memory-live-qualification.md).
preserve tool-free authority, grounding, bounds and fresh isolated retries;
no new policy knob, schema or evaluation framework is required.

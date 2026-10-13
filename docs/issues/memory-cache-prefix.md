# volatile memory framing defeats prefix caching

priority: p2. reviewed 2026-10-11 against universal-memory `d824d33`, jarvis
`89f9249`, and its pinned kernel/tools rendering path.

status: source fixed in the isolated candidate; live cache qualification is open.

problem: two placements invalidate the historical prefix. library
`tree.render` prepends changing `coverage [0,through)` metadata to every main and
compactor view. jarvis additionally places changing compaction source/address/
feedback before the historical view. kernel and tools preserve section order.

impact: append-only growth still changes the prompt before the historical nodes.
batched frontiers therefore fail to provide the intended cross-turn cache benefit;
compactor calls also cannot reuse their contextual view prefix.

evidence: using the exact consumer renderer, appending one node to an otherwise
unchanged 89,178-byte view leaves only 75 common prefix characters because the
coverage header changes from 400 to 401. two compaction tasks with identical
21,000-character context share 624 source-section prefix characters; putting
context first gives 21,676. these are rendered-prefix checks, not provider cache
telemetry or a promised hit rate.
sources: `universal-memory/src/universal_memory/tree.py:58`,
`jarvis/src/jarvis/memory_workers.py:112`, kernel `context.py:132`,
tools `prompt_sections.py:129`.

source repair: stable tool plans/view nodes precede changing footers, tasks and
clocks in the actual kernel request. controlled rendered-prefix and jarvis
composition cases pass. qualified-route cache counters remain unobserved. see the
[candidate evidence](../universal-memory.md#memory-repair-source-candidate).

resolved when: volatile coverage/interval metadata follows the stable view and
the compactor view precedes its task/feedback. whole-node size accounting must
still count all framing. verify long rendered-prefix preservation between merges
and then observe cache usage on the qualified route.

# retained terminal controls block memory readiness

priority: p1. reviewed 2026-10-11 against jarvis `89f9249` and universal-memory
`d824d33`, using the exact pinned consumer dependencies.

status: source fixed in the isolated candidate; database/live qualification is open.

problem: archive and node validation accept non-nul utf-8 control characters,
but jarvis's `memory_view_size` wraps their rendered text in `PromptText`, which
rejects xml presentation controls. short ansi-colored tool output becomes a free
node and fails during `advance_views`; its node transaction rolls back.

impact: an admitted leaf can never become ready. required main preparation and
background construction can raise an uncaught `ValueError`; no compaction error
is parked. restarting retains the offending original and repeats the failure.

evidence: synthetic `"\x1b[31merror\x1b[0m"` is accepted by `normalize_event` and
produces a 280-byte free source. calling the actual host view-size callback from
tree coarsening raises `prompt value contains text outside the XML-like
presentation set`. no database or provider was used in the reproduction.
inspection also identifies the same noncharacter mismatch in exact read
observations and older dream samples: canonical json can retain literal
`u+fffe`/`u+ffff`, which the subsequent `PromptText` rejects. sample selection
and host presentation must use the same safe json presentation boundary.
sources: jarvis `src/jarvis/tool_results.py:25`,
`src/jarvis/memory_workers.py:82`; universal-memory `src/universal_memory/tree.py:49`
and `:507`; llm-tools `src/llm_tools/prompt_sections.py:169` at `73056df`.

fix at the shared memory presentation boundary: visibly encode supported retained
controls, and use that exact presentation for sizing, main, compactor and dream
views. preserve original text and keep navigation addresses stable.

source repair: one shared json presentation encoder protects retained text;
observations preserve original strings and older samples remain arrays. controlled
presentation/composition cases pass, including typed irreducible-cover blocking
with no inference. actual database readiness, stopped repair preservation and
ordinary fitting reconstruction pass. live model content remains open in
[live qualification](memory-live-qualification.md). see the
[candidate evidence](../universal-memory.md#memory-repair-source-candidate).

resolved when: a colored tool result, an explicit note and a summary containing
supported controls can complete nodes and enter a fitting view; zoom/open return
the exact originals and older dream samples render safely. record temporary
acceptance evidence under the repair contract; the existing regression groups remain.

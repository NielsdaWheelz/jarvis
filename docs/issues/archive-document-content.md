# claude document content is omitted from capture and digest

priority: p2. reviewed 2026-10-11 against provider-runtime `d9550d9`; unchanged
at merged `5aecc2b`.

problem: `_claude_archive.py:484` accepts document source type `content`, but
the projection reads `source.data` and ignores `source.content`. the installed
official anthropic schema supports `content` as text or a content-block iterable.

impact: exposed attachment text disappears from the archive/tree/search, and
rewriting that text does not change the native digest. the accepted exposed-text
capture and changed-history checks both fail.

evidence/reproduce: pass two synthetic documents with different `source.content`
text through the codec. both produce empty retained text,
`text_availability="none"` and the same native digest. no live provider was used.
source: `llm-calling/src/provider_runtime/agent_runtime/_claude_archive.py:484`.

planned repair: [native capture contract](../memory-repairs.md#native-capture-contract).

resolved when: supported document content forms retain exposed text and its
availability, and the complete capture-relevant content binds the digest before
suppression. cover changed text and supported text/image blocks in temporary
repair qualification, preserving the existing capture/retry group.

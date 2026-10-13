# claude document content is omitted from capture and digest

priority: p2. reviewed 2026-10-11 against provider-runtime `d9550d9`; unchanged
at merged `5aecc2b`.

status: source fixed in the isolated v2 candidate; qualification remains open.

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

source repair: supported string and ordered text/image content retain exact text,
availability and complete capture-relevant digest input. controlled cases pass;
actual codec→collector→http→postgres and native persistence remain unrun. see the
[candidate evidence](../universal-memory.md#memory-repair-source-candidate).

resolved when: supported document content forms retain exposed text and its
availability, and the complete capture-relevant content binds the digest before
suppression. cover changed text and supported text/image blocks in temporary
repair qualification, preserving the existing capture/retry group.

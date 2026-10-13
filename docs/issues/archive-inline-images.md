# inline codex images park capture

priority: p2. reviewed 2026-10-11 against provider-runtime `d9550d9`; the same
archive code is present at merged `5aecc2b`.

status: source fixed in the isolated v2 candidate; qualification remains open.

problem: `_codex_archive.py:430` applies the generic 4,096-byte string limit to
an image url before recognizing a `data:` uri and replacing it with a short native
reference.

impact: an ordinary inline image raises `ArchiveError("unsupported")` and the
collector parks its conversation, preventing subsequent capture. binary original
storage is deferred, but references to these images must remain capturable.

evidence/reproduce: normalize a synthetic `userMessage` image with a valid
5,000-character data uri through the provider codec. it fails; a short uri succeeds.
the input is far below the native transport bound. this used no provider or file.
source: `llm-calling/src/provider_runtime/agent_runtime/_codex_archive.py:430`;
collector permanent-error handling is `jarvis/src/jarvis/collector.py:232`.

source repair: inline data is recognized before the ordinary-reference bound and
fully digested before suppression. controlled size/digest cases pass; real
collector/http/postgres and native image persistence remain unrun. see the
[candidate evidence](../universal-memory.md#memory-repair-source-candidate).

resolved when: inline image content is validated under the appropriate native
bound, digested before suppression, and archived as its bounded reference.
prove normal inline images do not park capture and changed native content changes
identity evidence. record temporary integration/live acceptance evidence under
the repair contract; the existing capture/retry group remains.

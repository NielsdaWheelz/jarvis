# nexus memory transport failures abort chats

priority: p2. reviewed 2026-10-11 against nexus-web `39dfa9456`.

problem: the memory handler catches `MemoryError`, while mcp initialization and
calls can raise transport/protocol errors inside a task-group exception. these
escape the portable dispatcher and generation failure classifier.

impact: an unavailable endpoint aborts the chat instead of returning a bounded
memory `unavailable` result. the tool-call completion path is skipped. revoked
credentials rejected during initialization have the same classification gap.

evidence/reproduce: dispatch valid `memory.view` through the actual handler,
mcp initialization and portable dispatcher, replacing only the http transport
with an in-memory transport that raises `httpx2.ConnectError`.
`ExceptionGroup [ConnectError]` escapes. no sockets, provider, database or private
credentials were used.
sources: `nexus-web/python/nexus/services/tools/memory.py:173`,
`nexus-web/python/nexus/services/tools/run.py:329`.

still present in inspected source at nexus `82eb4bab`; no new live probe ran.
planned repair: [nexus client contract](../memory-repairs.md#nexus-client-and-local-build-contract).

resolved when: the backend client maps expected connection/authentication/protocol
failures to the shared typed memory failure, preserves cancellation and exact
save identity, and settles the existing tool call. exercise both model routes;
do not add a blind retry or a second dispatcher.

# native tool callback integration

recorded: 2026-09-30. planned implementation, not a current production regression.

problem: the chosen native-main design needs dynamic host-tool callbacks. current
provider-runtime/kernel pins reject native tool use; the documented app-server
callback surface is experimental. transport support alone does not prove the
contained cognition and durable-effect boundary.

impact: [o3–o5](../implementation-plan.md#delivery-map) cannot be activated on the
strength of documentation or codapt's different shell/http tool bridge.

evidence: provider-runtime's `codex_app_server.py` rejects `item/tool/call`; the
kernel rejects native tool-use events. the official
[app-server documentation](https://learn.chatgpt.com/docs/app-server#dynamic-tool-calls-experimental)
describes dynamic declarations and correlated replies. no live probe of the
proposed jarvis path has run.

resolved when: the owning library changes prove multiple callbacks within one
native turn, only declared host tools available, final structured output, and
correct outstanding-call behavior on interrupt/disconnect/resume. jarvis must
persist invocation/result positions before dependent effects/replies, reconcile
ambiguous writes, and release turns awaiting approval. record exact installed
provider and dependency revisions. a failed containment probe blocks activation;
it does not authorize native shell or a replacement private appserver.

related blocker: [shared cognition connection](codex-private-process.md).
jarvis verification still follows [the testing reset](testing-redesign.md).

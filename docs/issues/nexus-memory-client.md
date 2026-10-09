# nexus shared-memory client handoff

status: consumer contract incomplete, identified 2026-10-09.

problem: the [memory contract](../universal-memory.md) includes nexus as a client,
but its lane declaration names only fifteen native homes and jarvis. client
bearers bind to those lanes. it defines neither nexus's application-account
mapping nor which nexus operations receive memory tools.

impact: dev-server's codex/claude mcp configuration connects developer agents,
including agents working on nexus. it does not connect nexus's own chats or
background model jobs. library upgrades alone cannot supply that integration.
the core archive/tree/view design remains ready for implementation; nexus access
must not be reported complete on that basis.

evidence: memory sections 1, 2 and 6 promise client access, enumerate the closed
lane set and bind credentials to lanes. nexus-web's locally cached `origin/main`
at `167773ac1` uses operation-selected portable tools for both provider functions
and native callbacks (`docs/modules/llms.md`,
`python/nexus/services/tool_runtime/plans.py`).
the local `nexus-web` checkout at `a494f743e` predates that cutover; its retired
shell/http bridge is not the integration target.

recommended boundary: nexus's backend connects to jarvis's one mcp endpoint and
exposes memory through its existing portable tool bindings and executor. keep the
credential in the backend, preserve nexus's history management, and introduce no
second memory server/store or generic kernel feature. this is a recommendation
pending the consumer contract, not an expansion of the current grants.

settle the owner/account-to-client mapping and whether access covers owner chats
only or also automated helpers. then specify read/save grants, retry identity for
optional saves, and credential/private connectivity provisioning. no other nexus
account inherits the personal corpus. access does not imply automatic capture of
nexus conversations; that source adapter remains unspecified.

resolved when: the owning nexus contract and jarvis client declaration agree,
the approved operations can use the shared tools through their real execution
paths, and a different nexus account cannot receive the corpus. record the exact
client/capture scope and adopted dependency/configuration revisions. dev-server
owns required host configuration; nexus owns its application bindings and secrets.

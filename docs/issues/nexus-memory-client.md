# nexus shared-memory client handoff

status: chats-only scope accepted 2026-10-09; account/client contract incomplete.

problem: the [memory contract](../universal-memory.md) includes nexus as a client,
but its lane declaration names only fifteen native homes and jarvis. client
bearers bind to those lanes. nexus's application-account mapping and concrete
client integration are not yet defined.

accepted scope: the owner selected chats only. shared reads and optional note
saves belong to the owner's chat sends, reruns and regenerations. metadata,
dossier and other automated helpers receive no shared-memory tools. preserve
this grant across provider-function and native-callback routes; no other nexus
account inherits the personal corpus.

impact: dev-server's codex/claude mcp configuration connects developer agents,
including agents working on nexus. it does not connect nexus's own chats.
library upgrades alone cannot supply that integration.
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

settle the owner/account-to-client mapping, client bindings and retry identity for
optional saves, and credential/private connectivity provisioning. access does not
imply automatic capture of nexus conversations; that source adapter remains
unspecified.

resolved when: the owning nexus contract and jarvis client declaration agree,
the owner's chat operations can use the shared tools through their real execution
paths, automated helpers receive no memory grant, and a different nexus account
cannot receive the corpus. record the exact
client/capture scope and adopted dependency/configuration revisions. dev-server
owns required host configuration; nexus owns its application bindings and secrets.

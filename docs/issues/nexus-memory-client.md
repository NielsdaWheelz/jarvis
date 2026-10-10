# nexus shared-memory client handoff

status: owner-chat client contract accepted in adr 0067, 2026-10-09; isolated
source implemented, frozen and qualified; private provisioning remains.

problem: installed nexus chats do not yet use the hosted memory endpoint.
the former closed-lane/account ambiguity is resolved by
[adr 0067](../decisions/0067-nexus-owner-chat-memory.md): one distinct backend
client, one configured authenticated viewer, complete declared processor chains
and canonical nexus note attribution. the sixteen capture lanes remain unchanged.

accepted scope: the owner selected chats only. shared reads and optional note
saves belong to the owner's chat sends, reruns and regenerations. metadata,
dossier and other automated helpers receive no shared-memory tools. preserve
this grant across provider-function and native-callback routes; no other nexus
account inherits the personal corpus.

impact: dev-server's codex/claude mcp configuration connects developer agents,
including agents working on nexus. it does not connect nexus's own chats.
library upgrades alone cannot supply that integration.
the core archive/tree/view implementation does not establish nexus access.
source client proof and actual private provisioning remain distinct.

evidence: memory sections 1, 2 and 6 promise client access, enumerate the closed
lane set and bind credentials to lanes. nexus-web's locally cached `origin/main`
at `167773ac1` uses operation-selected portable tools for both provider functions
and native callbacks (`docs/modules/llms.md`,
`python/nexus/services/tool_runtime/plans.py`).
the local `nexus-web` checkout at `a494f743e` predates that cutover; its retired
shell/http bridge is not the integration target.

accepted boundary: nexus's backend connects to jarvis's one mcp endpoint and
exposes memory through its existing portable tool bindings and executor. keep the
credential in the backend, preserve nexus's history management, and introduce no
second memory server/store or generic kernel feature. adr 0067 makes this the
accepted consumer contract.

source handoff: adopt the client in nexus's governing llm module contract before
code; compose its owner chat plan at send/rerun/regenerate and recheck principal/
processor authority at handler entry. reuse `ToolPositionRecord.id` for exact
optional-save retry identity and the host-known chat uuid as caller-reported
association. dev-server owns the private owner uuid, bearer and connectivity
handoff. access adds no automatic capture of nexus conversations.

source evidence: the real chat send/cancel/rerun/regenerate paths, canonical
executor and hosted mcp/postgres pass. provider-function checks use synthetic
api responses through the real codec; two native runs use contained stock
0.160.0. the final source is `5b282f2ec35a7624140a5935acc7a8d9b33b8524`, with
four immutable library pins and a passing full static/build gate. the current
v7 binding also proves read-only owner grants, exclusion of
another viewer and undeclared processor chains, and revocation before dispatch.
final nul api/native recovery checks fail before sql without new provider/mcp
entry. these source checks do not establish installed private access.

private handoff: dev-server renders a separate nexus client file. nexus's
publisher validates it before host work and captures an immutable read-only file
path in the release environment. only api and interactive workers receive it.
the first release must publish an explicit absent file when access is disabled;
there is no missing-file compatibility path. connected local containers need a
private copy readable by their uid/gid 10001. no credential is published to
background workers or native coding homes.

resolved when: the owning nexus contract and jarvis client declaration agree,
the owner's chat operations can use the shared tools through their real execution
paths, automated helpers receive no memory grant, and a different nexus account
cannot receive the corpus. record the exact
client/capture scope and adopted dependency/configuration revisions. dev-server
owns required host configuration; nexus owns its application bindings and secrets.

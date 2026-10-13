# adr 0067: owner chat memory client for nexus

status: accepted, 2026-10-09; source implementation authorized, deployment separate.

authority: the owner limited nexus shared-memory access to chats in documentation
commit `2cd2946`, then approved a distinct owner-only backend credential and nexus
note attribution, restricted to one configured viewer's send/rerun/regenerate
operations. the owner uuid and secrets are private deployment configuration.

## decision

keep the sixteen native/jarvis capture lanes unchanged. add one optional
`nexus-owner` client in the stopped sharing declaration, with configured
`owner_user_id`, controller/authorization, independent `connect` and `admit`
switches, and one separately scoped bearer hash. omission denies access.
connection permits reads; admission permits explicit notes only, never nexus
conversation capture. external saves require both, including retries.

include `nexus-owner` among corpus recipients and declare the complete selected
nexus model processor chains in `processors.nexus_model_processors`. use nexus's
existing frozen processor-chain labels. grant memory only when the selected
chain is completely declared; no implicit permission for every configured api.
the common sharing-declaration digest and controller authorization cover this
recipient/processor change. no new ranking model or second memory server exists.

nexus selects its memory-enabled chat plan only for the configured authenticated
viewer, on send/rerun/regenerate. its handler rechecks that principal against the
existing durable tool-position authority. automated helpers and other viewers
retain their existing grants. enforce this across provider functions and native
callbacks through the portable tools/executor, rather than a transport-specific
bridge. the credential stays in the backend.

## note contract

`agent_submission` is a closed tagged union. native/jarvis submissions are exactly
`{kind:"native", machine, account, provider, submission_id,
native_conversation_id}`. nexus submissions are exactly
`{kind:"nexus", client:"nexus-owner", owner_user_id, submission_id,
native_conversation_id}`. tags are required; this unreleased schema cuts over
without accepting the former untagged shape. preserved legacy notes still have
null submission provenance.

the nexus host supplies the owner uuid from authenticated client configuration;
model arguments cannot select a principal. the uuid identifies the authorized
viewer, not human authorship. notes remain agent-authored. native source
provider/machine/account fields are null for nexus notes; the canonical submission
variant supplies their attribution. no native lane or archive conversation is
fabricated.

reuse nexus's existing `ToolPositionRecord.id` as `submission_id`. associate the
host-known chat conversation uuid as the caller-reported `native_conversation_id`,
using the existing bounded/secret/nul validation without native discovery. native
note identity remains unchanged. nexus note identity is
`uuid5(NAMESPACE_URL, "urn:jarvis:memory-save-note:" +
canonical_json(["nexus-owner", owner_user_id, submission_id]))`, with canonical
uuid spelling. exact text/provenance retries return the original receipt;
conflicting reuse fails. one ordinary note leaf, receipt and append transaction
serve both variants; there is no receipt table or compatibility path.

## ownership and proof

universal-memory owns the public producer union and append/recovery mechanics.
jarvis owns client authentication, sharing validation and server attribution.
nexus owns chat grants, principal/processor checks, durable submission identity
and its backend client. dev-server owns the private provisioning handoff and
connectivity. adopt these contracts in each repository before its source change.

prove owner chat reads and exact save retries through the existing executor,
including both transports; deny other viewers, undeclared processor chains,
automated helpers and forged producer fields. qualification uses isolated
synthetic state. actual private credential installation, fleet connection and
production activation remain separate and cannot be inferred from source proof.

cost: one explicit backend client and note-producer variant. this preserves native
capture identity, account attribution and independent credential revocation.

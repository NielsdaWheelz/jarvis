# live drive files qualification

open for [adr 0120](../decisions/0120-drive-files.md). the test project
`jarvis-workspace-test-20261124` has the four drive/docs services and google
sign-in configured. the full isolated probe has yet to reach google. it
requires an eligible isolated account, its empty private fixture folder, two
distinct desktop clients and both loopback consents. account for cleanup in
that folder. [google setup](https://developers.google.com/workspace/guides/configure-mcp-servers)

the combined controlled rehearsal covers all eleven tools, the 100 mib boundary, two durable-ack crash windows, stopped import and restore, held or revoked authority, and the browser and android data interfaces. the source review passed with live evidence still required. the live probe and its usage notes are retained in the named local qualification directory.

verify the eleven operations through the selected agent composition, both reader lanes, max byte transport, stale etag and docs revision rejection, consent and revocation. verify the signed physical handset, stopped import and separate restored database on the selected release. close after the evidence is independently reviewed and disposable files and grants are accounted for.

on november 26 the [sample-only importer check](google-workspace-retention.md#sample-only-importer-check)
passed on the owner's existing account. the existing operator transport
created one 44-byte synthetic file in its own private folder and verified
the exact bytes through drive rest. google confirmed both generated objects
were trashed and accepted revocation. the disposable client, local export
and temporary harness were removed. the test project remains in testing.
the full probe still needs evidence including account-wide `drive.recent`,
mcp and the independent human reader. receipt and digest are under
`~/.local/state/jarvis/qualification/adr0120-account-fixture/`.

on november 26 the published create tool accepted a supplied id for blobs and
folders. the published mcp catalog still exposed no tool that issues those ids.
compare the actual authenticated catalog to the checked-in pin before running
writes. keep the current recovery contract pending that evidence.
[create tool](https://developers.google.com/workspace/drive/api/reference/mcp/tools_list/create_file) · [catalog](https://developers.google.com/workspace/drive/api/reference/mcp)

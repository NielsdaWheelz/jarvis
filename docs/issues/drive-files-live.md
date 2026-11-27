# live drive files qualification

open for [adr 0120](../decisions/0120-drive-files.md). the test project
`jarvis-workspace-test-20261124` has the four drive/docs services and google
sign-in configured. [0127](../decisions/0127-drive-prototype-qualification.md)
authorizes this check on the owner's account. use an empty private fixture
folder and separate disposable writer and read-only clients. account for
cleanup in that folder. [google setup](https://developers.google.com/workspace/guides/configure-mcp-servers)

the combined controlled rehearsal covers all eleven tools, the 100 mib boundary, two durable-ack crash windows, stopped import and restore, held or revoked authority, and the browser and android data interfaces. the source review passed with live evidence still required. the historical probe remains with its original digest. the staged driver
under `~/.local/state/jarvis/qualification/adr0120-full-provider/` now requires
the exact viewed sample in recent, proves private owner permissions and
records provider checks separately from folder trash and project-wide
revocation. twenty offline checks passed. use its `--preflight` for local
inputs and `--large` for the full provider run.

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

### owner-account provider result

both exact grants, both authenticated catalogs and the owner-only folder
passed. the live writer verified pdf creation and copy. google acknowledged
the native doc and returned valid file metadata. its docs server returned
a developer-preview tool error for the same created doc with
`commentsIncluded: false` and with that option omitted. google's setup
lists docs as generally available, while its preview application excludes
personal gmail addresses. clearance requires an actual read and verified
revision-controlled edit on the intended account with the pinned client.
the remaining live cases have yet to pass.

both disposable folders were confirmed in trash. google accepted project
revocation, both cloud clients and local exports were removed, and the
recovery inventories were retired. reopened facts and hashes are in the
`live-owner-01`, `live-owner-02`, and `diagnose-owner-doc-02` directories
under `~/.local/state/jarvis/qualification/adr0120-full-provider/`.
[docs read tool](https://developers.google.com/workspace/docs/api/reference/mcp/tools_list/read_doc)
· [developer preview application](https://docs.google.com/forms/d/e/1FAIpQLSd7BiMXXHDlUDkF7G0TSY5zfJbQwFNH3m6K_ZYFi3vCHLFbng/viewform)

on november 26 the published create tool accepted a supplied id for blobs and
folders. the published mcp catalog still exposed no tool that issues those ids.
compare the actual authenticated catalog to the checked-in pin before running
writes. keep the current recovery contract pending that evidence.
[create tool](https://developers.google.com/workspace/drive/api/reference/mcp/tools_list/create_file) · [catalog](https://developers.google.com/workspace/drive/api/reference/mcp)

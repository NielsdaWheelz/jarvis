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

on november 26 the sample-only importer check passed on the owner's existing
account. the existing operator transport created one 44-byte synthetic file in its own private folder and verified
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
personal gmail addresses. [0128](../decisions/0128-docs-rest.md) replaces
that path with the standard docs api.

the direct api and the typed jarvis adapter both passed on the intended
account. the adapter verified tab and revision reads, an ordinary edit,
stale rejection and the exact saved suggestion without a change to base
text. the integrated check then verified pdf create and copy and stopped
on a folder-search assertion before it reached recent, downloads or blob
revision. the failed search assertion does not identify which returned
page property differed. the wider provider check remains open.

the integrated fixture was verified in trash and google accepted revocation.
both test clients and the local exports were removed. the revised disposable
runner records the search page's coverage, count and fixture membership
before asserting. the reopened live receipt and hash are under
`~/.local/state/jarvis/qualification/adr0120-integrated-provider/live-owner-01/`.
the macbook package checks passed. the connector red/green and final uncertain-server-error check are in
`~/.local/state/jarvis/qualification/adr0120-docs-wire-ESg9WY/`.

### integrated drive result

the next two runs followed the folder cursor and found the expected pdf.
both found the exact recently viewed sample and verified the agent and human
pdf downloads. the second run also verified a normal blob revision. a
separate check used jarvis's streamed write envelope with a stale etag.
google returned an error and kept the rival etag and exact bytes. the error
carried no structured google status, so jarvis recorded an uncertain effect.
the fixture was verified in trash and google accepted revocation. the
reopened `live-rollout-stale-02/facts.json` has sha256
`c4c9ee5117a0b29e806af6c88be74b2bab841553f24df363459899e5d25481fc`.

the third integrated run verified the native pdf export and stopped during the 100 mib
create before a validated acknowledgement. the exact synthetic file was
absent from the folder when checked in drive. this leaves the result uncertain and
does not establish a provider size limit. record the upload status separately
from the acknowledgement and byte-verifying readback on the next run. the
folder was verified in trash, both grants were disconnected, and google
accepted revocation. the reopened `live-rollout-03/facts.json` under
`~/.local/state/jarvis/qualification/adr0120-integrated-provider/` has sha256
`e62e272cb3e6be27718f5a505f33c721fba6545ee3d7dda569d1233013008ea5`.

the isolated mcp retry yielded all 139,810,646 wire bytes. google returned
http 400 and an unstructured tool error before an acknowledgement. the
standard drive api on the same grant uploaded exactly 104,857,600 decoded
bytes in 36.2 seconds. a separate download in 8.7 seconds matched the
sha-256 and file version. both disposable folders were verified in trash
and google accepted both revocations. reopened receipts in the same
directory are `live-rollout-max-01/facts.json` with sha256
`ab7c09bf3ca72ffaa14e6c1dd66bfc83e70c095471747917e9ece04751c6644f` and
`live-rollout-rest-01/facts.json` with sha256
`8657e2b622484fea1ae6029fd7b9a3d9929cb0f75700e1889effa7a9e81fd64c`.
[0129](../decisions/0129-drive-blob-rest.md) selects the standard byte path.
the matched jarvis client, binary revision boundary and installed cut
remain to be qualified.

the 100 mib mcp revision also received http 400 after all 139,810,632
wire bytes were sent. the exact preceding etag survived. the standard
drive v3 api returned neither a metadata nor a media etag on the test
blob, so its test attempted no conditional update. both fixtures were
verified in trash and the test grants revoked. the reopened receipts are
`live-rollout-max-revision-01/provider/facts.json` with sha256
`b1bd142dc5ae31fb83dbb3bc291fc2c6a6d99249f6a6751aac39e83a91f0cdcc` and
`live-rollout-rest-conditional-01/facts.json` with sha256
`af7bdb07e8353b7b639a4f980943a9877b9af3cdeae3742d3ea01da90c032551`.
keep revision gated pending a provider-enforced condition at the full
attachment size.

the first matched jarvis run passed docs and stopped before the binary pdf
upload. a narrower check found that google returned a successful upload
session uri with extra query fields. jarvis rejected the uri before sending
bytes. the connector now preserves the opaque query on google's exact upload
endpoint. both fixtures went to trash and google accepted both revocations.
the reopened failures are `live-rollout-jarvis-rest-01/provider/facts.json`
with sha256 `7e59878d5df663013cd3b7a96781ba01e4ba9ecfd4b0b0ccf72100266f76787d`
and `live-rollout-jarvis-transport-01/facts.json` with sha256
`7b297487c5d302a11a31bc03761f44d0604071c9e3d678d0f6fb89d77b1e84b3`.

the next matched run verified ordinary pdf create, copy and both readers,
an explicit native export, and exact empty-file create and download. the
100 mib fixture used an octet-stream file. the human preview correctly
refused that type after the matched agent read. use a valid 100 mib pdf
to exercise both readers. the test runner revoked the grants ahead of the
manual trash check. the exact folder was then verified in drive trash.
evidence under `live-rollout-jarvis-rest-02/provider/` is `facts.json` with
sha256 `3233414011de90bed4bcebb600c4a3ef6bf0290005f200ab42c35b8366718e5e`
and `trash-ui.json` with sha256
`c432105b05f14e87581e7bf37eded6574a32c4f19bd38a03f8c7857c209cbf57`.

direct drive v2 media updates passed a current-tag 100 mib write and
returned http 412 for the exact old tag. an in-flight stale write also
returned 412 after a rival update. the rival's bytes, v2 tag and head
revision survived. the diagnostic's broader v3 version check failed,
so its overall outcome remains incomplete. [0130](../decisions/0130-drive-conditional-revision.md)
uses the v2 tag and head revision for this contract. both folders were
verified in trash and grants revoked. reopened evidence is
`live-rollout-rest-v2-media-02/facts.json` with sha256
`93507794b8fc52802d5504e8997f7863e6246d76c23136dd4a0ba1906182131b` and
`live-rollout-rest-v2-in-flight-01/facts.json` with sha256
`e6a26fb05fbb2c1bd7ff9ab691b3288a034e9518f0a60b2aa5d8f2f3274cfc29`.

### matched connector qualification

the default jarvis composition at `a93e83bd18950f78587e5c043a72422908822680`
passed the owner-account fixture. the 100 mib pdf filed and both readers
matched its bytes. a separate 100 mib revision used the tag returned by
`drive.get` and verified the exact acknowledged head and bytes. a small
revision changed the mime with name and parent preserved. a stale put
returned the expected refused precondition and kept the newer bytes.
search, recent, permissions, text, copy, empty blobs, native pdf export,
docs reads, edit and suggestion passed in the same run.

the fixture was verified in trash, both grants disconnected and google
accepted revocation. the detached checkout and temporary connector probes
were removed. named evidence under `live-rollout-jarvis-conditional-01/`
has `provider/facts.json` sha256
`9ea0d77743fe3fac9faf46ae42685acc538f9cb919512f20534104a0a92dbb12`
and `retired-probes.json` sha256
`bd87f0ead1a7adf9aea1e92ce18b3f1ce9f3f52fa878357265743b980928c9c2`.
the package check also passed and its scratch was removed. the signed
handset, stopped export, production restore and installed journeys remain
open in the [cut issue](drive-files-deploy.md).

### earlier retired probes

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

# 0129 · transfer drive blobs through the standard drive api

**implementation target · 2026-11-26.** google's drive mcp server received
the full encoded request for a 100 mib synthetic blob and returned http
400 with a tool error. the folder was empty on later inspection. on the
same account and with the same scoped agent client, the standard drive
api accepted all 104,857,600 bytes and returned the reserved file id. a
separate download matched the exact sha-256 and the version stayed fixed.
the file was absent between session creation and byte upload.

amend [0120](0120-drive-files.md) for two operations. create file-backed
blobs with drive's resumable upload and fetch original blob bytes with
`files.get?alt=media`. route by operation and source, independent of file
size. native creation, inline authored text, explicit native export,
metadata, permissions, search, copy and conditional blob revision retain
their existing drive mcp contracts.

use the existing owner agent grant, audience decision, request budget and
acknowledgement journal. reserve the id, open one upload session, recheck
authority and the destination audience, and send the bytes once. the
session stays in memory. after an ambiguous submission, keep the existing
uncertain receipt and never retry the write. hold a validated exact-id
acknowledgement before fenced readback. the extra requests buy direct byte
transfer and an exact acknowledgement. they add no stored state.

pin media fetches to the exact file id and preserve the existing before
and after metadata checks, decoded-size bound and scratch custody. compute
the digest while streaming. keep the grant and precondition contracts for
all operations. deployed cutover and the 100 mib original limit stay as
specified in 0120 and [0125](0125-new-shown-and-owed.md).

the standalone live receipts and cleanup are recorded in the
[drive qualification issue](../issues/drive-files-live.md). qualify the
matched jarvis path and release host before opening the production gates.
[resumable uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
· [original media](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get)

# 0130 · condition drive revisions on the exact file tag

**implementation target · 2026-11-26.** drive mcp rejected a 100 mib
revision after receiving its entire encoded request. drive v3 supplied no
strong tag in either metadata or media headers. drive v2 supplied a strong
`File.etag`, accepted a 100 mib media put under that exact tag, and rejected
a stale put with http 412. a second test paused the stale 100 mib put after
one mib and verified a rival edit through a separate connection. the stale
put returned 412 after transmission. the rival's exact bytes, file tag and
head revision survived. the v3 version counter advanced during this test.

amend [0120](0120-drive-files.md) and [0129](0129-drive-blob-rest.md) for
binary revision. use the drive v2 media endpoint for that operation at
every size. the latest drive api supplies the byte transport in 0129.
the published v2 endpoint supplies the strong conditional file tag and
head revision needed here. probe evidence covers the media put.

`drive.get` reports the observed v2 file tag for a revisable blob. collection
rows carry their existing display fields. submit `drive.revise` with that
exact file id and tag. send the tag unchanged in `If-Match` after the usual
audience and authority checks. retain the exact file id, new tag and head
revision in the existing acknowledgement. verify that head and tag again
with the expected bytes. classify http 412 as a refused precondition. keep
an ambiguous response uncertain and never resend the entered put.

one exact metadata read obtains the edit token. keep the internal mcp tag
for the other mcp metadata and byte-consistency checks. retire the mcp
revision path. retain existing grants, file size, viewer and schema.
the [qualification issue](../issues/drive-files-live.md) owns matched live
evidence and the stopped cut. [file resource](https://developers.google.com/workspace/drive/api/reference/rest/v2/files)
· [media update](https://developers.google.com/workspace/drive/api/reference/rest/v2/files/update)

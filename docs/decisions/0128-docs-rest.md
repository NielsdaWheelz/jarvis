# 0128 · read and edit through the standard docs api

**accepted · 2026-11-26.** google accepted native document creation but its
docs mcp server refused to read the resulting doc on the owner's account,
with comments explicitly disabled and with the field omitted. the owner
authorized the standard docs api if it proved the same behavior on that
account. one private native doc verified a tab and revision read, an
ordinary edit, a real suggestion with matching inline evidence, and rejection
of an old required revision without changing the doc.

replace the docs wire transport in [0120](0120-drive-files.md) with the
standard docs api. retain the typed docs tools, verified owner drive grant,
drive audience and approval checks, bounded reads, effect acknowledgement
and read-only recovery. use the exact document id for the read and write.
read tabs and suggestions inline. send the exact current revision and
explicit edit or suggest mode in the write. keep a returned acknowledgement
when the final result cannot be verified. an unsuccessful suggestion is
never reported as applied. do not retry an entered write.

drive discovery and operations still use drive mcp. retire docs mcp
discovery, schema pins and wire handling. no alternate docs path, new
grant, client, schema or feature mode. comments remain outside the
qualified contract. no change to the viewer or chat release order.

the direct provider receipt and checksum are under
`~/.local/state/jarvis/qualification/adr0120-docs-rest/live-owner-01/`.
the matched runtime still needs the [full drive checks](../issues/drive-files-live.md).
[documents.get](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/get)
· [documents.batchupdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate)

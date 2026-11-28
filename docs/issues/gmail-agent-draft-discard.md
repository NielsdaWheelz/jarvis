# gmail agent draft deletion and replacement

open, november 27, 2026. the owner deferred both operations to a future pr.
jarvis can create drafts. the owner can edit and approve individual sends in
the mail viewer. a new draft leaves the original in gmail. use the viewer to
edit the original in place. replacement needs deletion to retire the old draft.
[release scope](../decisions/0133-viewer-approved-send.md#draft-deletion)

in the enrolled gmail mcp test, `trash_message` returned an ambiguous error.
an exact read found the same draft and message still active. a separate
agent-marked test client verified `gmail.modify` and entered
`apply_sensitive_message_label(TRASH)` once on a synthetic draft. google
returned an unstructured error without an approval form. the exact draft was
still `DRAFT` with neither `TRASH` nor `SENT`; the independent message read was
withheld. no second connector write ran. the operator removed that fixture in
gmail and removed the temporary oauth client. the sealed evidence is under
`~/.local/state/jarvis/qualification/adr0132-one-main-implementation/b-live-draft-trash-readback-v2/`
on macbook. [trash tool](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/trash_message) ·
[sensitive label tool](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/apply_sensitive_message_label)

resolve against a supported governed operation. prove the issued scope, a
fresh exact draft and message revision, exclusion of a concurrent editor
change, one entered write, provider acknowledgment and exact readback showing
the old draft gone without a send. for replacement, also verify the new draft
before removing the old one. an unknown acknowledgment permits readback only.
any expanded agent grant must preserve the owner-approved viewer as the sole
application send path.

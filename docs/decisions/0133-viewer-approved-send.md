# adr 0133. approve email sends in the viewer

**owner decision, november 27, 2026.** amend [adr 0132](0132-one-main.md)
and [the gmail editor](0119-owner-gmail-draft-editor.md). jarvis may ask
to send a verified draft. the owner approves every individual send in the
existing mail viewer. a send-capable google scope is acceptable for a
qualified draft operation when the journaled owner send remains the sole
application send path.

## one approval interaction

chat has a short request and a **review email** link to the verified draft.
the viewer shows the exact from, to, cc, bcc, subject, body, quote and ordered
attachments. draft creation itself does not mean send approval. google forms
and email sends use one approval presentation contract and one web component.
android opens the same mail viewer. google owns its choices and deadlines.
the signed-in owner answers jarvis's send request in the viewer.

save any edits before review. a browser-only request for review reads the
current exact version and returns the draft and a five-minute approval id
bound to that version, grant, draft and editor epoch. review creates no send
receipt. the approve button submits the approval id and explicit choice.
the server checks the binding and freshly reads the draft before entry.
any edit requires fresh review. store and execute the exact reviewed content
through the existing single-operation mail editor receipt. a lost response
uses the receipt lookup. an entered send with unknown outcome never retries.
a service restart expires unsubmitted approvals. existing send receipts
remain queryable. the superseded editor operation accepts saves only.

## draft deletion

draft deletion should run without a jarvis confirmation when a supported
google agent operation can discard the exact draft. use the enrolled agent
transport, an exact draft/message revision, and the editor's same-draft
write boundary. google still controls its own consent. the existing live
test left the exact draft active. direct gmail rest deletion requires a
send-capable scope, and the agent transport has no documented direct
draft-delete method. keep deployment held until a supported wire operation
qualifies against the enrolled provider. independent send approval development
can proceed. [provider evidence](../issues/google-workspace-mcp.md) ·
[google agent terms](https://workspace.google.com/terms/ai-tools/)

## proof

check a verified chat link, exact viewer fields, a common approval interaction,
cancel, expiry, changed draft, wrong origin and account, replay across clients,
and an unknown acknowledgment. prove that a legacy, model or worker call cannot
dispatch a send. run the existing isolated rehearsal and independent review.
qualified scope names alone do not prove deletion. record the real deletion,
readback and fixture cleanup independently before selecting a release.

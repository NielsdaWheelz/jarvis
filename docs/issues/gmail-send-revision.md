# an edit can change the message after send approval

the sender checks the live draft against the approved recipients and content, then sends only the stable draft id. a second gmail client can replace the message in that interval. the success receipt records the digest of the approved content. [sender](../../src/jarvis/write_connectors.py#L694) · [send contract](../../SPEC.md#55-gmail-send)

an offline provider fixture at `cfd82ec` returned the approved text on the draft read and replaced it before handling the send. the actual connector posted only `id`. the fixture's send-as-is operation selected the edit. this reproduces the request sequence locally. production occurrence is unknown.

close when an observed edit causes jarvis to stop before sending, and an edit after the check cannot substitute different recipients, text or files in the request. qualify the approved-content send on a real draft. google supports supplying the draft id and replacement mime together. its documented send has no draft-revision precondition, so the contract must state what happens to a racing edit. [google draft guide](https://developers.google.com/workspace/gmail/api/guides/drafts#send_drafts)

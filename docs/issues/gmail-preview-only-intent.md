# a preview-only request created a gmail draft

during the november 27 utc installed rollout check on `45fe785`, a request
explicitly authorized preparing a proposal only for one disposable
self-addressed draft. main invoked the existing `gmail.create_draft` tool,
which directly creates an unsent draft under the current write policy.
gmail acknowledged creation. main surfaced the discrepancy. the draft
stayed unsent.

reproduce with a scoped owner request for a draft preview that explicitly
withholds creation authority. verify that main shows an ordinary
conversational preview and waits when the owner asks it to, while a request
to create a normal unsent draft retains its existing behavior. preserve the
[conversational approval model](../decisions/0071-simple-event-driven-v2.md).

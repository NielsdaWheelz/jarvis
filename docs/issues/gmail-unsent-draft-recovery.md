# recovery can report an unsent draft as sent

after an ambiguous send, a failed draft lookup leaves the live draft message id unknown. the thread scan can then count that same unsent message as evidence of a successful send. the owner can be told an email went out while it is still in drafts. [recovery decision](../../src/jarvis/write_connectors.py#L1139) · [thread read](../../src/jarvis/write_connectors.py#L1275)

an offline provider fixture at `cfd82ec` returned 429 for the draft lookup. the known thread contained one message with the matching effect header and exact content. its sole label was `DRAFT`. three reads produced `succeeded` with `one-exact-message-in-known-thread`. the fixture had no sent message. production occurrence is unknown.

close when recovery requires evidence that positively distinguishes a matching sent message from an unsent draft. a failed lookup must retain uncertainty if the remaining evidence cannot distinguish them. verify both the unsent case and a successful send whose acknowledgement was lost, preserving the existing conditions for any repeat. [send contract](../../SPEC.md#55-gmail-send)

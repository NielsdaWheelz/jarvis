# private web home installed acceptance

on 2026-11-19 utc, release `0e6e1ac` was staged on the production host. `e6ebc31`
still serves discord at schema `0016`, with the assistant and memory services active.
the dedicated `jarvis-home` tunnel, exact-email allow policy and hostname cache
bypass were created and verified. the zone accepts 100 mb uploads. the access
organization has no google identity provider. the home has no dns record.

register the google web client with the access team's callback. bind the google
provider and existing policy to the whole hostname, install the connector for that
audience, then publish dns. verify the edge challenge and wrong-account denial
before collecting the final discord pause. follow the [stopped cut](../operations.md#stopped-web-cut-from-0016-to-0017).
close this issue when the preserved state and the owner's login, phone notification,
pdf print, upload, web resume and decision pass the [installed journey](../decisions/0087-private-web-home.md#ownership-and-proof).

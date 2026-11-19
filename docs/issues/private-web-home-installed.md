# private web home installed acceptance

on 2026-11-19 utc, release `0e6e1ac` was staged on the production host. `e6ebc31`
still serves discord at schema `0016`, with the assistant and memory services active.
the dedicated `jarvis-home` tunnel, exact-email allow policy and hostname cache
bypass were created and verified. the zone accepts 100 mb uploads. the whole
hostname now uses the supplied google client and the sole owner policy. the
proxied dns record reaches the dedicated healthy tunnel. signed-out requests to
`/`, `/content/{slug}/{rev}` and `/api/files/{id}` each returned 302 to the correct
access audience with the exact return path. the login page offered the registered
google client and callback. the assistant has not switched to web intake.

observe cloudflare denying an unrelated google account, then collect the final
discord pause and follow the [stopped cut](../operations.md#stopped-web-cut-from-0016-to-0017).
close this issue when the preserved state and the owner's login, phone notification,
pdf print, upload, web resume and decision pass the [installed journey](../decisions/0087-private-web-home.md#ownership-and-proof).

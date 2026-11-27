# verify the installed daybook

[the daybook](../decisions/0127-the-daybook.md#acceptance) needs an installed
send, receipt and reply handoff on web and the s22+. the phone witness includes
talkback attribution and control labels. the daybook candidate uses v12 and
requires the shared shown cut's `shown-v1` service at schema `0028`.

record the release commit and schema, app version and signer, and exact
message identities for the two journeys. verify the selected message,
transcript position and draft on the phone upgrade. check the two cache
classes through the private edge. close when these observations are recorded.


the isolated candidate at `350ffb2` passed the service, browser and emulator
replays. the staged apk and wheel are under
`~/.local/state/jarvis/qualification/daybook-signed-v12-350ffb2/`. installed
acceptance awaits the authorized cut. the preceding cut records stock
`3f9989d` on schema `0028` and signed v11 on the s22+. daybook uses that
schema and viewer contract. [shared shown installed evidence](../decisions/0125-new-shown-and-owed.md#installed-acceptance)

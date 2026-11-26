# finish the new, shown and owed cutover

[adr 0125](../decisions/0125-new-shown-and-owed.md) requires a device-local
first cut and at least one week of owner use before adopting permanent shared
receipts. until then, a message shown on one device can still appear new on
another. the first cut keeps the current viewer contract and needs no migration.

the owner waived dedicated physical screen-reader, s22+ and talkback sessions
for this first-cut trial. emulator and browser evidence qualify the source.
during ordinary use, tap one real firebase alert and confirm that it opens the
exact reply.

the read-only check on november 26 selected the running release `22e9d2a`,
which expects schema `0025`. the matched source expects `0027`. the
[drive files rollout](drive-files-deploy.md) owns that predecessor cut.

- record the installed first cut and the owner’s week of use. include cases
  where marks dried too soon or remained after display. settle any change to
  the gate before adopting permanent receipts.
- verify the installed [drive files cut](drive-files-deploy.md) at `0027`.
  land and qualify the stopped shared-receipt cut, including restore, stale
  clients and cross-device notification sweeps. the owner reviews remaining
  new messages before the cut resets those marks. owed labels survive it.

close after both matched cuts and their installed witnesses are recorded.

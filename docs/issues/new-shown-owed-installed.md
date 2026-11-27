# finish the new, shown and owed cutover

[adr 0125](../decisions/0125-new-shown-and-owed.md) uses a device-local first
cut before permanent shared receipts. until the shared cut, a message shown
on one device can still appear new on another. on november 26 the owner
waived the week of use. the installed smoke still precedes the shared cut.

the owner waived dedicated physical screen-reader, s22+ and talkback sessions
for this first-cut trial. emulator and browser evidence qualify the source.
during ordinary use, tap one real firebase alert and confirm that it opens the
exact reply.

the read-only check on november 26 selected the running release `22e9d2a`,
which expects schema `0025`. the matched source expects `0027`. the
[drive files rollout](drive-files-deploy.md) owns that predecessor cut.

- record the installed first cut and the real notification tap.
- verify the installed [drive files cut](drive-files-deploy.md) at `0027`.
  land and qualify the stopped shared-receipt cut, including restore, stale
  clients and cross-device notification sweeps. the owner reviews remaining
  new messages before the cut resets those marks. owed labels survive it.

close after both matched cuts and their installed witnesses are recorded.

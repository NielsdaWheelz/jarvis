# stopped native state cutover

updated 2026-11-14. adr 0065 retires rolling paid-capacity admission. this issue
tracks actual host conversion/removal, not preservation or validation of a new
rolling journal.

problem: stopped native conversion and migration through `0008` have completed,
but activation classifies four finalized old worker actions as
`retired_pending_events`. three already have processed, exactly keyed host
resolutions; the succeeded send was returned inline before a delivered answer.
the source repair validates its claim-bound canonical conclusion identity and
complete captured-input settlement without interpreting retired worker payloads.
installed activation with that repair remains pending.

impact: incomplete legacy conversion refuses current startup; deleting files
without importing pause and reconciling entered effects would lose canonical
control or recovery obligations.

evidence: candidate `dd212e2` completed `cutover-native` with zero action conversions
after the bridge imported canonical pause. post-migration count/hash checks match
all retained original columns across six tables. the selected bridge has not run
against the new schema; jarvis remains stopped with `MainPID=0` and a clean stop.
59 temporary real-postgres cases pass. a read-only source probe against the actual
database reduces missing retired reports from one to zero and classifies the three
already-reported uncertain rows independently as compatible; all action hashes
remain unchanged. this source probe does not replace installed qualification.

resolution: follow the [native cutover](../operations.md#native-cutover). the
original release reconciles entered effects/unknown paid reads; current
`cutover-native` imports old pause, cancels only proven unentered authority,
re-pends eligible requests and removes retired files. no normalizer, refund,
charge preservation or new `admission.json` is part of native admission.

resolved when an operator records successful production conversion, retained
original requests/receipts and pause truth, absence of retired execution files,
and current startup under owner permits. unresolved entered effects block
conversion; finalized historical facts do not authorize replay.

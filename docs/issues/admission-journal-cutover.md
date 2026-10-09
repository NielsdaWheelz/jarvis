# stopped native state cutover

updated 2026-10-04. adr 0065 retires rolling paid-capacity admission. this issue
tracks actual host conversion/removal, not preservation or validation of a new
rolling journal.

problem: production has no recorded stopped native state conversion. legacy
pause/session/admission files and old execution authority must be handled by the
current cutover before activation; repository removal does not prove host removal.

impact: incomplete legacy conversion refuses current startup; deleting files
without importing pause and reconciling entered effects would lose canonical
control or recovery obligations.

evidence: on 2026-09-17 the active host selected release
`f4e2ce6129c0add09ddb50355a8997a1c589d3d1`. this session could not read
`/var/lib/jarvis/runtime/admission.json`, and `no_new_privs` prevented sudo.
synthetic current-journal and prior-normalizer checks do not replace that evidence.

resolution: follow the [native cutover](../operations.md#native-cutover). the
original release reconciles entered effects/unknown paid reads; current
`cutover-native` imports old pause, cancels only proven unentered authority,
re-pends eligible requests and removes retired files. no normalizer, refund,
charge preservation or new `admission.json` is part of native admission.

resolved when an operator records successful production conversion, retained
original requests/receipts and pause truth, absence of retired execution files,
and current startup under owner permits. unresolved entered effects block
conversion. this documentation change inspected or altered no private host state.

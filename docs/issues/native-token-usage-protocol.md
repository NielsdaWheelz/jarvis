# native token-usage protocol mismatch

status: open, 2026-11-17 owner-local date. actual main startup fails while the
provider decodes native token usage. this is separate from the historical
[unexplained native incidents](native-protocol-diagnostics.md) and the now
qualified stopped quiet dream.

on installed `650eb7cb5db3604358906771dff472003232bfa0`, main attempt
`5f10be1d-781f-475b-8704-655ca148cd79`, thread
`01a1ec22-55a0-7761-894d-4ec900658613`, fails with `source_protocol` before a
terminal seal. the closed command diagnostic retains `ProtocolDefect` and
provider coordinates `_notification_event:1405` → `_token_usage:1832` →
`_decode_token_usage:1836` → `_usage_member:1881`. the exact installed source line rejects a cumulative total unequal to
input plus output. the raw values and producer cause are unknown.
private `650eb7c-startup-protocol-fence-journal.log` has sha256
`4e20e0af214e702e1f2dc6f19d8f3b6497289196d9c9c0542447127bcbf7fffe`.

startup catch-up scans six messages and accepts one: genuine owner continuation
`36f388f2-be2a-4f3c-8d17-f4264d1122c5`, body sha256
`69c51f3dcba15413cf802b2aca5a315d2a0645c17b7064cbd2b37029aaf5dba1`.
the original attempt is fenced and unsealed. systemd restarts once; subsequent
attempt `cb1cb8c6-910b-45b7-b6aa-8c7c8887f602` is cancelled/stale at the clean
service stop. no new action is created, the old work stays blocked and journey
clocks have not started. all 97 previously released messages remain pending
and unparked; canonical `resume` sequence 9 is preserved. do not infer additional
row counts from the closed journal or describe the unfinished request as done.

existing fresh-start recovery owns the unsealed attempt: `recover_native_products`
fences unsettled callback owners and settles only retained sealed terminals;
`PostgresNativeJournal.recover` returns no recovery for an unsealed attempt.
this source contract supports fresh reasoning from canonical unfinished requests
and original receipts; it does not authorize fabrication of a terminal or replay
of an uncertain effect. no additional recovery machinery is indicated.

resolve by identifying the actual supported native usage shape, repairing and
qualifying the owning provider decoder without weakening usage validity or
losing reported accounting, then qualifying installed main startup/continuation.
preserve the original attempt/fence and any accepted receipts, reject stale
callbacks, retain canonical control and verify no duplicated effects. the
combined journey and final reset remain required. do not attribute this failure
to earlier unknown incidents, model output, quota or the resolved dreamer caps.

[provider source qualification](../runtime-reliability-and-integration.md#native-usage-accounting-repair)
reproduced the old check and qualifies the repaired accounting and resume races.
installed `c5392be` sealed the native failure with its reported usage.
the [context-window failure](native-steering-context.md) now owns the remaining
continuation blocker.

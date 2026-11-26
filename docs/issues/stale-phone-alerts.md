# phone alerts stay after the message was shown elsewhere

under [adr 0125](../decisions/0125-new-shown-and-owed.md) the phone removes a stale
reply notification only when the app is next opened. a message read on the
laptop therefore keeps its entry in the phone's shade until then. grouping
reduces this to one summary line and one swipe.

two cheaper-looking remedies were reviewed on november 26, 2026 and held:

- **skip the push when the message is already shown.** this contradicts
  [0122](../decisions/0122-chat-sidebar-and-phone-alerts.md), where ordinary
  replies and questions stay pending until provider acceptance, and the spec's
  rule against a host notification policy. a skipped notice also needs a new
  terminal state in the `home_notice` constraint.
- **a silent push telling the phone to cancel.** fcm does not order messages.
  a cancel that arrives before its alert does nothing, and the alert then
  posts. preventing that needs a persisted per-device set. invisible
  high-priority pushes also risk fcm demotion.

an owed question must never be retracted because it was glimpsed. it leaves
the phone only when its wait settles.

no incident is recorded; this is a known cost of the accepted design. reopen
if, after the second cut, the owner still finds stale alerts on the lock
screen bothersome. resolve by an owner decision amending 0122 and the spec
rule, a design that survives the reordering case, and an s22+ check under
doze showing no stale and no ghost alert.

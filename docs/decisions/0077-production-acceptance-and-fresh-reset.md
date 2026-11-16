# adr 0077: production acceptance and fresh reset

status: accepted target, 2026-11-16. owner decisions during f2 specification;
no implementation, production change or deletion has occurred.

## decision

the [f2 contract](../runtime-reliability-and-integration.md) owns reliability
repairs, final installed acceptance and a subsequent one-off fresh reset.

- qualify faults in isolation and consume the qualified f3 artifacts first.
  then perform the stopped v2 cutover and the useful live journey on the actual
  production service/channel. no concurrent candidate gateway or autonomous
  mailbox/calendar actor; no temporary discord channel or test bot.
- the owner authorizes one synthetic self-addressed email with a small test pdf
  for real arrival testing. deliver it outside jarvis's own action history so
  its send receipt does not suppress the event. other sends in the journey still
  use ordinary consent; no third-party recipient is needed.
- safe diagnostics and bounded representative reproduction are required. if the
  historical native failure remains irreproducible, installed acceptance may pass
  with that issue explicitly OPEN. do not claim its cause was fixed. any current
  defect reproduced during qualification still requires an owning-layer repair.
- after installed acceptance, clear the configured discord history, jarvis
  history and ALL central shared history, including other agents' admitted chats
  and notes. the owner selected a completely fresh start: clear todos, reminders
  and waits; do not carry commitments forward or recreate a daily-review todo.
- preserve private notes/source repositories, credentials, real google data and
  original native/nexus chats. quiesce capture and establish fresh source cuts so
  the reset does not automatically import old history again.

this supersedes earlier f2 candidate-only/final-cutover separation and the
requirement for a diagnosed historical native repair as an unconditional acceptance
gate. it also grants a one-time operator exception to append-only/history-retention
and established-capture-cut rules for this explicit reset. runtime append-only
guards, effect recovery and ordinary source admission remain unchanged. no model
deletion tool, general redaction feature, reset endpoint or permanent privilege
relaxation is adopted.

## constraints and consequences

restore and qualify the existing activation primitive; do not run an intermediate
or partly integrated release in production. original-release disposition and the
existing stopped snapshot precede migration. no code rollback pretends to undo
data migration. source/candidate evidence keeps its original scope.

record acceptance evidence before cleanup. cancel old commitments through their
existing transitions; finish/reconcile entered work before removing its live
recovery records. no reset may conceal a failed test or authorize an effect repeat.
preserve a private reset inventory/recovery snapshot outside the live corpus.
retained real attachment bytes require a recoverable private manifest; delete
only proved fixture files unless broader file deletion is explicitly selected.

production testing incurs downtime and can leave synthetic google/discord/worker
history until cleanup. the unexplained failure could recur and park a real request.
the fresh reset deliberately loses useful central history too. preserved source
chats/files can be quoted in later new material: this is a fresh corpus/capture
boundary, not a guarantee that old facts can never be learned again.

the [roadmap](../implementation-plan.md#v2-finishing-prs) remains the only delivery
sequence. implementation follows scoped temporary integration/live red → green →
refactor → delete, with content design and independent adversarial review.

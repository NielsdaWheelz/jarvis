# nexus memory outage continuation

status: open for current live proof, reconciled 2026-11-14.

historical defect (2026-10-11, nexus `39dfa9456`): transport/protocol failures from
mcp initialization/calls escaped the portable dispatcher, aborting chats before
tool completion. the actual-sdk reproduction used an injected `ConnectError`,
not a live provider or canonical database row.

october source repair normalized expected stateless-json failures without
swallowing defects/cancellation or resubmitting tools. socket checks also repaired
uncached streamed request bytes. controlled mcp/postgres proved uncertain saves,
exact-id replay, conflict and revocation. current source retains that client
boundary; it does not itself establish current live librarian behavior.

resolved when: real current librarian send/failed-or-cancelled retry settles the
canonical tool row with typed errors and continues through each applicable
provider/native route. cover initialization and call-time auth, rate limiting,
network/remote failures and malformed envelopes; preserve cancellation, lost
authority and unknown defects. exact `call.id` replay must preserve save identity;
a missing success receipt may mean the note committed. no blind retry, fallback
endpoint or second dispatcher. record proof in
[live qualification](nexus-memory-live-qualification.md) under
[memory delivery](../memory-delivery.md).

# adr 0047: require current admission journals

- status: accepted; implements the owner's 2026-09-17 instruction to hard-cut
  legacy paths and backward compatibility.
- supersedes: only adr 0037's automatic recognition and enlargement of the
  preceding admission envelope at stopped startup. its calendar decisions and
  rejection of unknown journal configurations remain binding.

## decision

service startup and manual dreaming accept only the current admission-journal
configuration. remove the three historical limit factories and automatic
migration calls; construct current limits directly. current capacity, validation,
reservation, settlement and orphan-recovery behavior are unchanged.

the historical factories have no remaining consumer except those two migration
calls. keeping them makes current runtime construction carry deployment history.
the owner-directed hard cut moves that one-time responsibility to stopped
deployment preparation using the existing prior release, as described in
[operations](../operations.md#admission-journal-cutover).

## cutover and verification

an older journal now prevents startup until prepared. merge does not establish
that the private production journal is ready, and activation remains conditional
on that evidence. preparation preserves reservation identities, expiry and
charged capacity; it never initializes an empty replacement to bypass rejection.

temporary synthetic checks compare all supported current limit outputs, exercise
reserve/child/settle/reopen and conservative crash accounting, reject old or
invalid journals unchanged, and prove the pinned prior normalizer preserves
identities and never reduces charges. no production migration or private-journal
inspection occurs in this change. adr 0046 continues to govern retained checks.

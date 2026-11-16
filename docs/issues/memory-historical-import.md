# memory historical import

status: owner-deferred; not required for future capture or the online rollout.

problem: material before a lane's activation or a recovered conversation's cut
is intentionally absent. no historical importer is implemented or qualified.

impact: shared memory cannot answer from excluded history unless evidence was
admitted through another source. retaining native files is not proof of import.

evidence: [adr 0070](../decisions/0070-nexus-capture-and-memory-delivery.md) and
[adr 0073](../decisions/0073-per-conversation-memory-baselines.md) retain future-only
capture and explicitly exclude recovery gaps. native, old jarvis and nexus
history would need a separately selected scope.

resolved when: an owner-approved later import defines provenance, deduplication
and ordering, then proves exact admission without moving established cuts or
duplicating originals; or the owner explicitly retires this deferred capability.
no old-history repair or backfill is authorized by this issue.

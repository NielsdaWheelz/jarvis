# installed todo cutover

problem: qualified work-record source is not installed. the last recorded
production memory release uses schema `0008a`; events/work require `0009`/`0010`.

impact: source acceptance does not provide production todos or preserve live
reminder obligations by itself. unattended v2 activation remains refused.

evidence: [work qualification](../work-records.md#implementation-evidence) proves
isolated postgres, native cognition, wall-clock wakes and discord delivery.
production database/service and retained reminder inventory were not changed.

resolved when the selected v2 release follows the existing stopped cutover,
accounts for every retained reminder, and records the selected artifact, migrated
head, commitment disposition and explicit owner resumption in
[operations](../operations.md#supervised-todo-setup). adr 0077 permits cancelling
old commitments through their original transitions for the selected fresh reset;
it explicitly forbids recreating the daily review. entered or unknown effects
still require their original recovery disposition before any reset.
the roadmap owns slice sequencing; this adds no separate execution gate.

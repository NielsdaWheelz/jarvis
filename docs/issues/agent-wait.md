# asynchronous agent wait deployment acceptance

updated: 2026-10-06. [adr 0064](../decisions/0064-simple-worker-orchestration.md)
owns the implemented scope; [o8 contract](../worker-launch-observation.md)
consolidates remaining delivery. current source keeps post-turn authority narrow:
reads/integration/notification only; new writes or waits need current owner input.
[o6](../one-main-events.md) owns the separately specified broader policy cutover.

problem: local live qualification has not been repeated against the paired
installed fleet and production notification transport. production activation is
separate from this source implementation.

impact: current-source correctness does not prove deployed artifact/configuration
agreement, service containment or delivered Discord notifications.

evidence: 39 real postgres/process-exit/restart cases pass registration, staged
receipt recovery, atomic outcome/event commit, first-commit cancellation and
original watching replay; baseline fails 19 of the original 27. eleven actual
service/public-cli lifecycle checks pass immediate registration, owner ingress
and settlement during a pending stock-provider read, outcome commit outside the
main mutex, bounded matched read, pause/quarantine deadlines, cancel/shutdown
joins, fresh service-process observer restart and shutdown blocked on a real
postgres outcome commit. those eleven checks use controlled cognition/notification
ports. a separate actual main/gate/recaller scenario registers one wait and silently
integrates the later event with the original capture/receipt and zero extra effects;
its public tool plan is tightened to reads/wait and embedding/Discord controlled.
four separate native cognitive consent cases pass.
source audit defects are corrected; no worker effect is replayed. merged pr 49's
worker-v7/native composition separately qualifies original callback replies and
wait/product/observer/stop behavior; [native evidence](../native-agent-integration.md#qualification)
owns those exact artifact identities.

contract: original ref/deadline are immutable; watcher uses 15-second chunks under
20-second fences and a separate bounded read. cancellation stops observation.
only unmixed wait-event batches without owner rows may settle silently. startup
and replay never turn watching receipts into new worker work.

resolved when: the paired immutable release is installed and authorized service
qualification repeats receipt/input coexistence, restart, deduplication,
partial/unavailable text, target changes, overall timeout and cancellation through
the production boundaries. prove mixed/owner/scheduled visibility and actual
notification delivery while preserving narrow authority and contained cognition.

blockers: paired skid release/install, contained endpoint/application activation
and authorized external delivery. local checks do not assert production repair.
no behavioral suite or general harness is retained.

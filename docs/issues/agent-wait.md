# asynchronous agent wait deployment acceptance

updated: 2026-11-14. [adr 0064](../decisions/0064-simple-worker-orchestration.md)
owns durable observation, amended by [generalized installed state](../decisions/0068-generalized-skid-consumer.md)
and [terminal-only worker v9](../decisions/0069-terminal-only-workers.md).
[o8 contract](../worker-launch-observation.md)
consolidates remaining delivery. current source keeps post-turn authority narrow:
reads/integration/notification only; new writes or waits need current owner input.
[adr 0071](../decisions/0071-simple-event-driven-v2.md) and
[o6](../one-main-events.md) now adopt the broader policy target: the existing
asynchronous wait delivers an event to the same full-plan main, which judges
follow-through and whether to respond. that target is unimplemented; it adds no
callback service or repeated model polling.

problem: worker source and isolated qualification do not establish installed
observation/restart/notification behavior. v10's actual service-uid reads now pass
through the qualified [live-state boundary](../universal-memory.md#native-memory-installed-qualification)
on both online hosts. jarvis is owner-resumed; the production observation journey
remains open and belongs to the coordinated worker/events delivery.

impact: current-source correctness does not prove deployed artifact/configuration
agreement, service containment or delivered Discord notifications.

historical evidence consolidated 2026-10-06 for the adr 0064/0065 worker-v7 generation: 39 real
postgres/process-exit/restart cases passed registration, staged
receipt recovery, atomic outcome/event commit, first-commit cancellation and
original watching replay; baseline failed 19 of the original 27. eleven actual
service/public-cli lifecycle checks passed immediate registration, owner ingress
and settlement during a pending stock-provider read, outcome commit outside the
main mutex, bounded matched read, pause/quarantine deadlines, cancel/shutdown
joins, fresh service-process observer restart and shutdown blocked on a real
postgres outcome commit. those eleven checks use controlled cognition/notification
ports. a separate actual main/gate/recaller scenario registers one wait and silently
integrates the later event with the original capture/receipt and zero extra effects;
its public tool plan is tightened to reads/wait and embedding/Discord controlled.
four separate native cognitive consent cases passed.
source audit defects were corrected; no worker effect was replayed. merged pr 49's
worker-v7/native composition separately qualified original callback replies and
wait/product/observer/stop behavior; [native evidence](../native-agent-integration.md#qualification)
owns those exact artifact identities.

current evidence, 2026-10-21: adr 0069 records 13 distinct disposable checks across actual
postgresql 16.15, the public skid cli engine, signed fixture state and an
authenticated tls gateway with isolated tmux. these qualify terminal discovery,
reads/replay, captured send, wait/cancel, changed-pane refusal, lost-successful-reply
no-replay and retired v8 archival/activation rules. they do not qualify installed
fleet networking, stock providers, the service uid or discord delivery. v9 has no
worker-native target/history route and no start model/effort overrides; independent
provider archives and memory remain available through their own contracts.

contract: original ref/deadline are immutable; watcher uses 15-second chunks under
20-second fences and a separate bounded read. cancellation stops observation.
in the implemented baseline, only unmixed wait-event batches without owner rows
may settle silently. the v2 target replaces that visibility/authority split with
ordinary main judgment. startup
and replay never turn watching receipts into new worker work.

resolved when: the live-state access issue is resolved, the matching terminal-only
release is installed and authorized real service-uid
qualification repeats receipt/input coexistence, restart, deduplication,
partial/unavailable text, target changes, overall timeout and cancellation through
the production boundaries. prove mixed/owner/scheduled visibility and actual
notification delivery under the exact selected release's authority and native
configuration. baseline qualification preserves its narrow authority; a later
v2 release must separately prove same-main event continuation under adr 0071.
identify and fix any installed artifact/observer defects found there rather than
infer that a new observation mechanism is required.

remaining: installed observation/restart and external delivery under the selected
worker contract. live state access, matching cli, contained endpoint and owner
resumption are qualified; no copied-state or retired client installer workaround.
the memory rollout's read-only worker checks do not qualify worker effects.
no behavioral suite or general harness is retained.

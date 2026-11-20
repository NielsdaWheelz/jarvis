# memory backup and restore

status: open. [adr 0088](../decisions/0088-storage-and-memory-recovery.md)
defines the target. source and isolated recovery passed. production recovery
remains open.

problem: current production memory still lacks a proved off-host recovery
point for the canonical archive, notes and capture progress.

impact: loss of the central store can lose admitted evidence and its capture
boundaries. native files and rebuildable summaries are not equivalent backups.

evidence: [memory delivery](../memory-delivery.md) deferred host-loss recovery.
the [cutover rehearsal](../decisions/0086-native-recovery-and-memory-availability.md#production-cutover-evidence)
restored the migration copy. the [isolated drill](../decisions/0088-storage-and-memory-recovery.md#implementation-evidence)
proved the source path with test data.

blockers: provision the dedicated cloudflare bucket and independent key kit,
connect the two hosted checks to owner email, and authorize the separate
stopped production provisioning window. the backup timer remains uninstalled.

resolved when the installed backup runs on schedule and the adr 0088 drill
recovers a current generation on an isolated second machine. record actual cut
age, time to verified reads, inventory and checkpoint comparisons, independent
configuration recovery, external freshness reporting and the retained proven copy.

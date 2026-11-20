# memory backup and restore

status: open. [adr 0088](../decisions/0088-storage-and-memory-recovery.md)
defines the accepted target. implementation and installed recovery proof are pending.

problem: this delivery provides no qualified backup-and-restore path for the
canonical memory archive, notes and capture progress.

impact: loss of the central store can lose admitted evidence and its capture
boundaries. native files and rebuildable summaries are not equivalent backups.

evidence: [memory delivery](../memory-delivery.md) deferred host-loss recovery.
the [cutover rehearsal](../decisions/0086-native-recovery-and-memory-availability.md#production-cutover-evidence)
restored the migration copy. recovery from current off-host material remains unverified.

resolved when the installed backup runs on schedule and the adr 0088 drill
recovers a current generation on an isolated second machine. record actual cut
age, time to verified reads, inventory and checkpoint comparisons, independent
configuration recovery, external freshness reporting and the retained proven copy.

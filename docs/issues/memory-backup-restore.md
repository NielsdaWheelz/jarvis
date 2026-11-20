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

the owner authorized stopped provisioning. on 2026-11-20 utc, the private
`jarvis-memory-backups` bucket reported its 30-day lock and expiry rules.
distinct backup and recovery credentials authenticated. a disposable
cloudflare bucket proved the lock and the actual encrypted multipart and
completion-marker paths. long retention was verified by rule readback.
the mac filevault kit
reopened its pinned reader archive built from `d4c702a`. hetzner's
installed age encrypted a
probe that the mac decrypted. the bucket contains no production backup.

remaining prerequisites are the two owner-email checks and an independent
offline copy of the recovery identity. adr 0092 occupies the single candidate
slot with reviewed `d16a507`. preserve it. if 0092 migrates first, qualify
recovery against `0018` before provisioning. record the owner pause in the
authenticated web composer when the deployment window is ready. the backup
timer is still uninstalled.

resolved when the installed backup runs on schedule and the adr 0088 drill
recovers a current generation on an isolated second machine. record actual cut
age, time to verified reads, inventory and checkpoint comparisons, independent
configuration recovery, external freshness reporting and the retained proven copy.

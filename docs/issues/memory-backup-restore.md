# memory backup and restore

status: owner-deferred; not part of the completed online rollout.

problem: this delivery provides no qualified backup-and-restore path for the
canonical memory archive, notes and capture progress.

impact: loss of the central store can lose admitted evidence and its capture
boundaries. native files and rebuildable summaries are not equivalent backups.

evidence: [memory delivery](../memory-delivery.md) explicitly defers backup/restore.
its stopped/resumed preservation comparisons prove an installation retained data;
they do not prove recovery after loss of that data.

resolved when: a separately scoped backup is restored into an isolated target
and demonstrates retained originals, notes, provenance, immutable cuts and
checkpoint integrity, with required private configuration recoverable through
its own protected path. record actual recovery limits without exposing secrets.

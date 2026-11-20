# memory backup and restore

status: open for scheduled-run verification. the first production r2 backup
and both isolated restores passed. [adr 0088 evidence](../decisions/0088-storage-and-memory-recovery.md#implementation-evidence)

on 2026-11-20 utc, `e7f5916` produced generation `20261120T055359985334Z-d2aedd79c2ab490f9511a0a4e91ae0ea`
from the running `0018` database. the mac matched all 20 tables, schema and
grants and reopened an event and a note. the r2 read took 45.196 seconds and
the held-copy read took 42.678 seconds. the owner deferred a spare decryption
identity until the home workstation is ready.

the timer is enabled and active. first scheduled run is 2026-11-20 12:00 utc.
resolve after the journal records a fresh verified generation created by the
timer. locally journaled failures require operator inspection.

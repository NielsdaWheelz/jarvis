# worker prompt contract

problem: main instructions still advertise `c-` native-worker control after
adr 0069 removed that capability in favor of terminal-only v9.

impact: main can plan around unavailable targets/history and misdescribe worker
evidence despite a correctly narrowed tool catalog.

evidence: source `8c0bf36`, `src/jarvis/definitions.py:220–237`, compared with
[adr 0069](../decisions/0069-terminal-only-workers.md); read-only audit,
2026-11-14. no live behavior claimed.

resolved when [slice 1](../one-main-events.md) removes the stale guidance, uses
current terminal-only schemas and distinguishes dispatched bytes/idle from task
success. inspect the rendered main definition and relevant temporary journey;
installed skid proof remains slice 3. delete this record after accepted proof.

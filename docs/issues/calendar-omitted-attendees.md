# incomplete calendar attendee snapshots

status: open; [f1](../mail-calendar-web-reads.md#calendar) owns the narrow repair.

problem: `write_connectors._calendar_snapshot` ignores the provider's
`attendeesOmitted` flag and can compare a returned subset as complete state.
the read parser already rejects true/malformed flags; f1 preserves that rejection
and adds an explicit incomplete-snapshot error plus a textual omission view.

impact: incomplete attendee evidence can mislead mutation/reconciliation checks.
this is a source finding, not an observed production incident.

evidence: jarvis `bbfeb47`, `write_connectors._calendar_snapshot`. supply a valid
event with `attendeesOmitted=true` and a subset of its attendees; the write parser
does not reject that omission. `connectors._calendar_event` already rejects it.

resolved when: text reads expose the exact omission fact; strict read/write
snapshots reject true or malformed flags; controlled checks prove incomplete
evidence cannot authorize mutation or prove an effect. preserve write schemas,
original receipts and existing unavailable/reconciliation handling.

# wake notification

problem: `DueWakeSignal` carries timestamps and derives `overdue`, but its sole
production callback discards the entire value and calls `service.request_work()`.
the durable scheduled action already owns the requested instant.

evidence: `src/jarvis/proactivity.py` and timer construction in `src/jarvis/cli.py`.
only tests and qualification consume the redundant signal fields.

resolved when the timer emits a parameterless work notification and tests observe
actual timing, one durable waking row, and the unchanged creation receipt.

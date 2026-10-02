# testing redesign

problem: the owner-approved [testing reset](../decisions/0046-reset-testing.md)
removes all behavioral tests, fixtures, evaluation data, and qualification runners.
the replacement is deliberately deferred to the next pr.

impact: `scripts/verify` establishes static and package-build evidence only.
behavior, migrations, recovery, containment, and model quality have no current
automated verification. historical reports do not qualify subsequent changes.

evidence: the reset removes `tests/`, `eval/`, qualification scripts and helpers,
pytest dependencies, dependency-suite reruns, and ci's disposable postgres service.

resolved when the subsequent redesign defines and delivers the agreed verification
scope, records results against that scope, and replaces the temporary policy in
spec, acceptance, and repository instructions. begin the design in the next pr;
this issue does not prescribe a framework, test count, or restoration of old tests.

current scoped exception: the [universal-memory contract](../universal-memory.md),
as simplified by [adr 0062](../decisions/0062-simplify-memory-policy-and-retrieval.md),
retains two small regression groups: capture/retry and memory completion.
verify atomic capture and memory progress, bounded background retries, direct-note
idempotency and the unchanged main recovery boundaries. background memory jobs
need no frozen-batch replay or unknown-paid-call tests; interrupted inference may
repeat paid work. targeted review and focused live checks replace per-feature
ceremony; remove exploratory helpers. these checks remain unimplemented and are
not a general replacement suite. focused checks for automatic activation, native
mapped-field validation, deterministic fusion, the shared search gate and seed-only
dreaming need no new harness or model-selection exercise. this issue stays open.

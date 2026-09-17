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

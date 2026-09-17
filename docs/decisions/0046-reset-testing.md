# adr 0046: reset testing

- status: accepted by the owner on 2026-09-17
- supersedes: earlier requirements to retain or execute the existing tests,
  fixtures, evaluations, qualification runners, and automated proof gates.
  product behavior and runtime safeguards remain binding.

## decision

remove the entire test suite, synthetic evaluation corpus, qualification runners,
test-only helpers and dependencies, and ci's disposable database. stop cloning
and running dependency suites from jarvis verification. git retains the old code;
there is no archive suite or replacement harness in this change.

keep `scripts/verify` for frozen dependencies, formatting, lint, types,
documentation links, dependency auditing, and package build/install checks.
keep production migrations, deployment and containment checks, runtime validation,
and the real stopped memory-rebuild command. the local development database is
application infrastructure and remains available.

the owner accepts the temporary absence of automated behavioral, migration,
recovery, containment, and model-quality evidence for this one-user application.
earlier requirements for new regression tests, repeated acceptance trials, replay
qualification, and live qualification runs are suspended as change/release gates
until the subsequent testing-redesign pr establishes their replacement. this does
not relax runtime authority, compatibility, recovery, or data-integrity contracts.

dated qualification reports retain their historical meaning. a successful static
and build check does not establish behavioral correctness, live acceptance, or a
passing result for a removed check. report that evidence as not run, not passed.

## evidence and tradeoff

the existing suite has roughly 38,000 python lines, plus roughly 11,000 lines of
scripts. routine verification also runs all three dependency suites. the owner
judges the maintenance burden excessive and chooses a clean reset over preserving
selected tests. single-user operation and direct repair make the gap acceptable;
repair or code rollback still cannot undo every external effect or data loss.

## migration and follow-up

there is no database migration, runtime dependency-pin change, session-contract
change, or deployment in this removal. test-only package code is removed;
the production memory-rebuild validation it shared is retained unchanged.

the next pr begins the testing redesign, tracked in
[testing redesign](../issues/testing-redesign.md). it defines new verification
requirements from the product contract, without presuming the old suite survives.

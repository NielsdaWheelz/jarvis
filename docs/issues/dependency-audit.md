# locked multidict dependency fails audit

status: open, observed 2026-10-09; the previous audit-network blocker is resolved.

problem: `scripts/verify` reaches pypi successfully, but `pip-audit --local`
reports `GHSA-54p9-h82j-f925` for locked `multidict==6.7.1`, with `6.9.1` listed
as fixed. `uv.lock` still selects the older version.

impact: the required verification command exits 1 at its audit. formatting, lint,
types, 98-document link checks, source/wheel build, clean wheel installation,
import and cli checks passed. behavioral verification was not run. this is
evidence about the locked local environment, not an inspected production install.

reproduce: run `scripts/verify`. the clean wheel installation may resolve a newer
transitive version; that does not change the lock or the final local audit.

resolved when: explicitly update the affected dependency lock and verify the
result, including a successful vulnerability audit. no dependency was changed
during the memory handoff documentation correction.

# locked dependencies fail audit

status: open, observed 2026-10-20; the earlier multidict advisory is resolved by
the current `multidict==6.9.1` lock. no dependency changed in the skid consumer work.

problem: `scripts/verify` reaches the audit and reports eight advisories for
locked `aiohttp==3.14.3`, fixed in `3.14.4`, and `GHSA-6q48-6c7w-9gw2` for
`certifi==2026.7.22`, fixed in `2026.10.19`. the aiohttp ids are
`GHSA-5wr8-gcqf-gqf3`, `GHSA-2g87-pp6c-29x5`, `GHSA-494j-54xm-rwp3`,
`GHSA-pqxq-w44r-73xw`, `GHSA-9xw5-w5jj-pvcg`, `GHSA-gx76-c99x-2c96`,
`GHSA-6cjc-53gc-5rqm` and `GHSA-f9xw-jh8m-3mwq`.

impact: the required verification command exits 1 at its final local audit.
frozen dependencies, formatting, lint, strict types, 117-document links,
source/wheel build, clean wheel installation, import and cli checks passed.
this is locked local-environment evidence, not an inspected production install.
private git dependencies are not covered by the pypi advisory audit.

repeat evidence: after the actual-cli wire repair, all pre-audit checks above
passed again. the final audit then failed on a pypi `503 Backend is unhealthy`
lookup for the private git dependency `llm-agent-kernel/0.1.0`, before a complete
report. the earlier nine advisory findings remain recorded; the later network
failure is not an audit pass or evidence that those lock entries changed.

reproduce: run `scripts/verify`. clean wheel installation can resolve newer
transitive versions; that does not change the lock or final local audit.

resolved when: explicitly update the affected lock entries and run the required
checks, including a successful vulnerability audit. keep that dependency work
separate from the source-only worker schema/configuration cutover.

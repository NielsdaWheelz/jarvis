# urllib3 dependency audit

problem: the frozen dependency environment contains `urllib3==2.7.0`, and the
dependency audit fails on three reported advisories.

impact: `scripts/verify` exits nonzero at its final audit step. this is present
in the unchanged main-branch lock, not introduced by the documentation changes.
the advisory report alone does not establish exploitability in jarvis.

evidence (2026-09-30): `scripts/verify` passed lock/sync, formatting, lint,
types, documentation links, package builds, and clean wheel import/cli checks.
`uv run pip-audit --local` then reported:

- `GHSA-8988-9cw3-xx77`
- `GHSA-gh4c-6fx4-qh6g`
- `GHSA-vxq7-64xx-v4gw`

the audit lists `2.8.0` as the fixed version for all three. `uv.lock` and
`pyproject.toml` are identical to main for this documentation pr.

reproduce: run `uv sync --frozen --all-groups`, then
`uv run pip-audit --local`.

resolved when: an explicit dependency update selects a fixed compatible version,
the frozen environment audit passes, and `scripts/verify` completes. behavioral
verification remains subject to adr 0046's testing reset.

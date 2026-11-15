# dependency audit findings

status: open, observed 2026-11-14 during the documentation-only competitive
research pass at `ce6f48870ca2968f8c57375b7bdcadba133d8973`.

## problem and impact

`scripts/verify` fails at its final `uv run pip-audit --local` step. the scanner
reports 19 known vulnerabilities across four packages in the frozen development
environment. this prevents claiming that the full verification command passes.
the research changed neither dependency declarations nor the lockfile; runtime
reachability and exploitability were not assessed.

## evidence

lock consistency, environment sync, whitespace, formatting, lint, pyright,
documentation links, wheel/sdist build, fresh wheel installation, import and cli
smoke checks completed before the audit failure.

| package | installed version | reported findings | scanner-reported fix versions |
| --- | --- | --- | --- |
| `filelock` | `3.32.5` | 12 | `4.0.9`, `4.2.1`; `4.2.1` is listed for eleven findings |
| `msgpack` | `1.2.2` | 1 | `1.2.3` |
| `opentelemetry-api` | `1.44.0` | 2 | `1.45.1`, `1.45.2` |
| `pyasn1` | `0.6.4` | 4 | `0.6.5` |

reported advisory ids:

- `filelock`: `GHSA-v4x8-3wr5-3wq8`, `GHSA-9vhv-jxww-xfm5`,
  `GHSA-567q-5qvw-pf92`, `GHSA-m462-7rxw-wvpg`, `GHSA-j8f7-rjxc-mr56`,
  `GHSA-8mx5-7m5m-r77g`, `GHSA-69hj-f68j-2879`, `GHSA-9c4x-gm8v-wgc4`,
  `GHSA-rfpc-qcw5-3pc4`, `GHSA-cwqr-hh33-gh44`, `GHSA-fq56-3cx3-fjxp`,
  `GHSA-6627-m3xw-93mp`.
- `msgpack`: `GHSA-j586-36cw-2gc2`.
- `opentelemetry-api`: `GHSA-xcq7-p3pf-p88h`, `GHSA-mf5v-w3w3-f6cg`.
- `pyasn1`: `GHSA-2qm8-x737-gmw5`, `GHSA-fm9c-5rcf-2q5p`,
  `GHSA-mm57-4v3p-rchx`, `GHSA-9m75-vc3g-4x39`.

the scanner also skipped the git-sourced `llm-agent-kernel`, `llm-tools` and
`provider-runtime` packages because they were unavailable on pypi. a successful
index audit would not establish those packages' security.

## reproduction and resolution

run `scripts/verify`, or reproduce only the finding with
`uv run --frozen pip-audit --local`. inspect dependency ownership and affected
paths before choosing compatible upgrades; scanner suggestions alone do not
qualify a library change. no upgrades are authorized by this documentation task.

resolved when the relevant dependency changes are explicitly qualified under
the repository's upgrade rules and the full verification command passes, or
specific findings are otherwise disposed of through an explicit accepted policy.
do not disable the audit to make this research pass appear green.

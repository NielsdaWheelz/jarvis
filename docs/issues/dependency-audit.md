# dependency audit findings

status: open, updated 2026-11-14 during the documentation landing on upstream
`53508d476eac9e7462d4a72593b0acc493cff5bc`.

## problem and impact

`scripts/verify` fails at its final `uv run pip-audit --local` step. the current
frozen environment reports six known vulnerabilities across three packages.
this prevents claiming that the full verification command passes. the docs pr
changes neither dependency declarations nor the lockfile; runtime reachability
and exploitability were not assessed.

## evidence

verification of documentation commit `06421e1` passed lock consistency,
environment sync, whitespace, formatting, lint, pyright, all 132 document-link
checks, wheel/sdist build, fresh wheel installation, import and cli smoke checks
before the audit failure.

| package | installed version | reported findings | scanner-reported fix version |
| --- | --- | --- | --- |
| `msgpack` | `1.2.2` | 1 | `1.2.3` |
| `opentelemetry-api` | `1.45.1` | 1 | `1.45.2` |
| `pyasn1` | `0.6.4` | 4 | `0.6.5` |

reported advisory ids:

- `msgpack`: `GHSA-j586-36cw-2gc2`.
- `opentelemetry-api`: `GHSA-mf5v-w3w3-f6cg`.
- `pyasn1`: `GHSA-2qm8-x737-gmw5`, `GHSA-fm9c-5rcf-2q5p`,
  `GHSA-mm57-4v3p-rchx`, `GHSA-9m75-vc3g-4x39`.

the earlier research/memory-spec pass at `ce6f488` reported 19 findings across
four packages. upstream subsequently supplied `filelock 4.2.4` and
`opentelemetry-api 1.45.1`; that old count and those old installed versions are
historical, not the current reproduction. this docs change performed no upgrade.

the scanner skipped git-sourced `llm-agent-kernel`, `llm-tools` and
`provider-runtime` because they were unavailable on pypi. a successful index
audit would not establish those packages' security.

## reproduction and resolution

run `scripts/verify`, or reproduce only the finding with
`uv run --frozen pip-audit --local`. inspect dependency ownership and affected
paths before choosing compatible upgrades; scanner suggestions alone do not
qualify a library change. dependency changes remain outside this docs landing.

resolved when the relevant dependency changes are explicitly qualified under
the repository's upgrade rules and the full verification command passes, or
specific findings are otherwise disposed of through an explicit accepted policy.
do not disable the audit to make the documentation pass appear green.

# verification network access

status: blocked by execution-environment network access; reproduced 2026-10-08.

problem: `scripts/verify` cannot complete its vulnerability audit because
`pip-audit --local` cannot resolve `pypi.org` in the current restricted environment.
the dependency pins and verification script are unchanged.

impact: full verification is incomplete. static checks, documentation links,
source/wheel builds, clean wheel installation, imports and cli checks passed using
a writable copy of the existing uv cache. behavioral verification was not run.

evidence: the audit exited with `NameResolutionError` / `ConnectionError` fetching
the pypi vulnerability metadata for `aiohappyeyeballs` 2.7.1.
2026-10-08 reruns, including the completed memory-contract pass, passed
format/lint/type, 97-document link checks, build, clean installation, import and
cli. the vulnerability audit alone failed on the same DNS lookup.

reproduce: run `scripts/verify` with a writable uv cache containing its locked build
dependencies. the final audit needs network access even when uv runs offline.

resolved when: the unchanged verification script completes, including the audit,
in an environment with working pypi access. remove this record after that check.

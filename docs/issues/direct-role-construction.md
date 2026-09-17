# direct role construction

problem: old slice1/2 builders survive through tests, and the conversation
runner still accepts their incomplete compositions. repeated definition records
and optional memory paths obscure the current five-role contract.

evidence: trace the builders in `src/jarvis/definitions.py` and their callers in
`scripts/` and `tests/`. the current runtime now builds its five roles directly;
slice3/4 constructors are removed. memory-only qualification uses current role
builders and the memory end-to-end qualifier uses current Main with the existing
read-only diagnostic plan. the remaining old1/2 runner callers are conformance
tests; other kernel and read tests still construct those historical definitions.

resolved when current roles are built directly with one explicit result contract,
consumers qualify the current behavior, and obsolete constructors disappear.
preserve exact existing profile ids, policies, prompts, plans, and fingerprints;
renaming durable identities would invalidate sessions and pending actions.

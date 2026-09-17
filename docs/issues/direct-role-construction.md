# direct role construction

problem: `build_slice6_definitions` constructs slice4, which constructs slice3,
then replaces already-built roles. old slice1/2 builders also survive through
qualification scripts and tests. repeated definition records obscure the five
actual roles and make changes propagate through historical configurations.

evidence: trace the builders in `src/jarvis/definitions.py` and their callers in
`cli.py`, `scripts/`, and `tests/`. memory maintenance also constructs unused
external read bindings to obtain isolated memory definitions.

resolved when current roles are built directly with one explicit result contract,
consumers qualify the current behavior, and obsolete constructors disappear.
preserve exact existing profile ids, policies, prompts, plans, and fingerprints;
renaming durable identities would invalidate sessions and pending actions.

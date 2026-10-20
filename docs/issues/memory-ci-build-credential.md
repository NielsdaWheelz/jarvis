# memory dependency credential blocks hosted verification

status: open, 2026-10-13. tracked in [the owning issue](https://github.com/NielsdaWheelz/jarvis/issues/53).

jarvis actions supplies an empty `UNIVERSAL_MEMORY_READ_TOKEN`; the existing
build-only wrapper rejects it before verification. no repository secret is
configured. local frozen verification remains separate evidence. resolved when
an authorized read-only private-dependency credential is provisioned and the
unchanged hosted `verify` job passes. do not add a fallback or expose the key.

evidence: pr 52, actions run 38462092339. contract:
[memory repairs](../memory-repairs.md). private provisioning remains outside this
source repair; source merging does not waive the hosted check.

2026-10-20 repeat: generalized skid consumer pr54 fails at the same wrapper,
before source checks, in actions runs39496271710 and39496276870. the provided
credential is empty. local adapter proof and pre-audit engineering checks pass;
this hosted result remains failed, independently of the local dependency audit
and the separately deferred installed skid service-state integration.

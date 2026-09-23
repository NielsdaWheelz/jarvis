# admission journal cutover

problem: the deployed private journal has not been checked against the current
configuration. a predecessor journal now blocks startup; repository cleanup does
not establish deployment readiness.

evidence: on 2026-09-17 the active host selected release
`f4e2ce6129c0add09ddb50355a8997a1c589d3d1`. this session could not read
`/var/lib/jarvis/runtime/admission.json`, and `no_new_privs` prevented sudo.
synthetic current-journal and prior-normalizer checks do not replace that evidence.

resolved when a permitted operator completes the stopped
[admission journal cutover](../operations.md#admission-journal-cutover) and confirms
the deployment journal validates under current limits without losing unexpired
reservation identities, expiry or charges. until then, do not activate the new
release or reset the journal to make it start. no production action was taken in
this cleanup.

the [herdr cutover](../operations.md#herdr-cutover-pr-4) runbook orders this
preparation after the owner pause and cooperative stop (step 3) and before the
target's installation and activation; the journal must be current before
`deploy/activate-release`, which requires `admission.json` and never
initializes it. still open as of 2026-09-23.

# admission predecessors

problem: service startup and manual dreaming still enumerate three historical
admission configurations to upgrade the private journal. this preserves old
configuration machinery after the runtime has moved on.

evidence: `RollingAdmissionPort.migrate_limits` callers in `src/jarvis/cli.py` and
the predecessor limit constructors in `src/jarvis/admission.py`.
the stopped proactivity qualifier also uses `slice5_admission_limits` and must
move to current sizing before that helper can be deleted.

blocker: the deployed journal has not been inspected in this cleanup. confirm its
configuration matches the current one without exposing payloads or resetting
charged reservations. removing a needed migration would prevent startup.
on 2026-09-17 the local host identified itself as `dev-server`, with the service
active and `/opt/jarvis/current` selecting release
`f4e2ce6129c0add09ddb50355a8997a1c589d3d1`. the journal at
`/var/lib/jarvis/runtime/admission.json` was unreadable by this session; sudo
refused elevation because `no_new_privs` is set. a permitted operator must make
the content-free configuration comparison before this cut.

resolved when deployment is already on current limits and predecessor migration
paths are removed, with current journal reopen/settlement/recovery still verified.

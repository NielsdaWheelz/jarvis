# skid worker client cutover

updated: 2026-10-21. terminal-only worker v9 implements
[adr 0069](../decisions/0069-terminal-only-workers.md). paired installed
fleet and production service acceptance remain `NOT_RUN`.
[o8 contract](../worker-launch-observation.md) owns remaining delivery and acceptance.

problem: terminal-only targets, closed wire schemas and worker v9 require one
coordinated stopped cutover. the jarvis service cannot read the enrolled owner's
live skid state under its existing uid and containment; the client installer
refuses. the [service-state issue](skid-installed-state-access.md) owns that
separate deployment decision. current dev-server does not read file-based pause
state or install a private jarvis client.

impact: mixed readers can reject valid receipts after effects or refuse ordinary
terminal input. local source qualification does not establish installed behavior.

historical evidence, 2026-10-06: strict adapter/client checks pass null/additive/wrong-kind rejection,
short projection, original-ref capture/dispatch and nonzero partial receipts.
isolated darwin stock providers exercise launch/options/literal stdin, effective
codex selection, guarded input, retained draft, pane change and lost create/input
acknowledgements. real postgres crash/recovery and actual service/cli observation
checks pass. current native cognitive gate proves explicit/grounded consent and
denies absent/conflicting context. source audit defects are corrected. both providers pass linux launch/input/
read/wait/refusal/stop/close, and actual cognitive wait integration passes.
production endpoints and external delivery are unqualified. skid pr 61 is merged,
but published/dev-server v0.13.0 pins predate that orchestration source. a release
containing it and matching installed gateway/cli/jarvis artifacts remain due.

2026-10-06 source inspection: dev-server's `assets/skidbladnir/release-pin.json`
still selects v0.13.0 / `b2ea62aea57a87668835eefbcaebcffcf5761559`.
`lib/skidbladnir.sh:129–175` reads exact `jarvis-paused.v1` json;
`ansible/playbooks/gateway.yml:149` passes `runtime/paused.json`, and dev-server
spec still requires it. jarvis `cli.py:668` instead provides public
`check-paused`: native-file/data checks, canonical database pause and deployment
ownership, without providers/connectors. `deploy/install-agent-client` invokes
that checker through `/opt/jarvis/current`; during native bootstrap this may
still select an obsolete release. no running installation was inspected.
`deploy/install-private-state:19` calls client installation without a release,
before installing `jarvis.env`; forwarding a commit alone cannot bootstrap it.

cutover: drain old actions/turns/required events/delivery, pause and stop cleanly,
stage matching immutable host/cli/jarvis artifacts and resolve live state access,
validate unfinished actions, then activate separately. finalized v1–v8 worker rows
stay opaque after common immutable checks; unfinished retired rows block startup.
no compatibility reader, ref codec, account registry or fallback is added.

current evidence: [adr 0069](../decisions/0069-terminal-only-workers.md) records
reviewed v9 source/integration proof. `deploy/install-agent-client` explicitly
refuses live-state access; `dev-server/lib/skidbladnir.sh` delegates ordinary
installation/application to skid. the earlier file-pause installer requirement is
superseded, not remaining implementation work.

resolved when: authorized installed-service checks prove both provider launches,
current terminal schemas/flags, short discovery, literal input, partial evidence,
original targeting across delay/restart and zero mutation replay. preserve
shared provider ownership, account settings and containment. first qualify the
chosen service-state boundary under the owning issue; no copied stale state,
privilege bridge, fallback or deployment change is assigned here.

blockers: service-state access decision and qualification, paired release/install,
production cognition and authorized activation.

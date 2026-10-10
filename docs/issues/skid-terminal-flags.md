# skid worker client cutover

updated: 2026-10-06. merged source implements
[adr 0064](../decisions/0064-simple-worker-orchestration.md). paired installed
fleet and production service acceptance remain `NOT_RUN`.
[o8 contract](../worker-launch-observation.md) owns remaining delivery and acceptance.

problem: the installed baseline uses the old worker generation; the new short
targets, closed wire schemas, launch options/input and nonblocking wait contract
require one coordinated stopped cutover. dev-server's installer also requires
retired file-based pause state, which native jarvis rejects.

impact: mixed readers can reject valid receipts after effects or refuse ordinary
terminal input. local source qualification does not establish installed behavior.

evidence: strict adapter/client checks pass null/additive/wrong-kind rejection,
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
stage paired immutable cli/jarvis artifacts and private three-peer configuration,
validate unfinished actions, then activate separately. finalized v1–v6 worker rows
stay opaque after common immutable checks; unfinished retired rows block startup.
no compatibility reader, ref codec, account registry or fallback is added.

repair: both installers use the explicit installed target release's existing
`check-paused`, as jarvis:jarvis with existing runtime env/systemd restrictions.
retain clean stopped-service checks and identical-byte/ownership/mode no-ops.
target migration/native conversion must precede that check without activating
the service; reuse the preparation stages in `deploy/activate-release`.
private-state setup installs secrets first; remove its eager client call and
install the client explicitly after target migration/initialization and pause.
dev-server `devbox` must forward validated `JARVIS_RELEASE_COMMIT` to its gateway
playbook/preflight; the current entrypoint sends only product and operation.
remove the retired file guard/spec; no mirrored pause state or database-query
fallback. invalid/unavailable target, canonical pause or ownership refuses before
executable/config replacement.

resolved when: authorized installed-service checks prove both provider launches,
current schemas/flags, short discovery, literal input/options, partial evidence,
original targeting across delay/restart and zero mutation replay. preserve
shared provider ownership, account/plugin/permissions and containment.
prove fileless native bootstrap, exact target selection, inert identical installs
and refusal-before-change through real postgres/public checker/host boundaries.

blockers: canonical-pause/target-release installer repair, paired release/install,
production cognition and authorized activation.

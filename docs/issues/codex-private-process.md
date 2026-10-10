# activate contained codex cognition

status: native source and frozen installed qualification are complete and merged;
production activation remains unrecorded. [adr 0065](../decisions/0065-native-agent-supervision.md)
supersedes the historical shared-process direction with the separate contained
stock endpoint. updated 2026-10-04; no running service was inspected here.

problem: the last recorded deployed release required the removed
`/etc/codex-shared/profiles.json` broker and failed before discord ingress. no
subsequent production migration/activation receipt closes that observation.

impact: useful deployed conversation and physical integration are not established.
the last recorded state is disabled, stopped and durably paused. contained-host
qualification is complete; actual systemd/application activation remains.

evidence: 2026-09-29 deployed release `39d9c9c` failed in `CodexHostConfig.load`
with FileNotFoundError. no pending actions, unfinished decisions or old resolution
processing/delivery remained. the owner explicitly permits downtime.

direction: install the separately contained stock 0.160.0 endpoint under the
existing personal host account using `deploy/install-contained-host`, the provider
catalogue prerequisite and same-release application checks. preserve unrelated
coding hosts and account credentials. do not restore the retired broker.

resolved when: the same-release host/application is installed, stopped legacy
state conversion succeeds, deployed cognition and physical google/discord
integration pass their relevant checks, and explicit owner resumption is recorded.
use the [native cutover](../operations.md#native-cutover); do not reopen completed
library qualification or restore retired broker/capacity machinery.

universal-memory dependency: archive codecs read native history without using
worker-control servers. jarvis cognition persists in the devbox codex-personal
home, so that capture lane stays unadmitted until internal-session exclusion is
qualified. the native cutover changes the cognition endpoint, not the owner's
fleet servers or the future memory collector scope. see the
[native capture issue](universal-memory-capture.md).

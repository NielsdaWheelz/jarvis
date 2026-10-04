# activate contained codex cognition

status: native implementation and local installed qualification are recorded in
the shared kernel handoff; deployed activation remains NOT_RUN. the historical
shared-process direction below was superseded by adr 0063 and the owner's explicit
separate-contained-endpoint decision, 2026-10-02.

problem: the deployed jarvis release still requires `/etc/codex-shared/profiles.json`
and shared sockets. dev-server removed their former broker independently of the
worker cutover. startup fails before discord ingress.

impact: jarvis remains disabled, stopped and durably paused. cognition activation
and full containment are pending; the skid worker client and herdr retirement
proceed independently.

evidence: 2026-09-29 deployed release `39d9c9c` failed in `CodexHostConfig.load`
with FileNotFoundError. no pending actions, unfinished decisions or old resolution
processing/delivery remained. the owner explicitly permits downtime.

direction: install the separately contained stock0.160.0 endpoint under the
existing personal host account using `deploy/install-contained-host`, the provider
catalogue prerequisite and same-release application checks. preserve unrelated
coding hosts and account credentials. do not restore the retired broker.

resolved when: jarvis completes normal cognition and full containment through
the contained endpoint, passes activation checks, and the owner resumes it.

universal-memory dependency: archive codecs read native history without using
worker-control servers. jarvis cognition persists in the devbox codex-personal
home, so that capture lane stays unadmitted until internal-session exclusion is
qualified. the native cutover changes the cognition endpoint, not the owner's
fleet servers or the future memory collector scope. see the
[native capture issue](universal-memory-capture.md).

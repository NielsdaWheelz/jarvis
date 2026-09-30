# restore shared codex cognition

problem: the deployed jarvis release still requires `/etc/codex-shared/profiles.json`
and shared sockets. dev-server removed their former broker independently of the
worker cutover. startup fails before discord ingress.

impact: jarvis remains disabled, stopped and durably paused. cognition activation
and full containment are pending; the skid worker client and herdr retirement
proceed independently.

evidence: 2026-09-29 deployed release `39d9c9c` failed in `CodexHostConfig.load`
with FileNotFoundError. no pending actions, unfinished decisions or old resolution
processing/delivery remained. the owner explicitly permits downtime.

direction: the owner requires the same existing stock codex app-server process.
a private process/account is rejected. repair its provider transport and containment
under a separate accepted contract; do not restore retired broker machinery or
change cognition in the worker-control pr.

resolved when: jarvis completes normal cognition and full containment through
that shared process, passes activation checks, and the owner resumes it.

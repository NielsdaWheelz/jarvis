# nexus memory image qualification

status: open, reconciled 2026-11-14. historical [issue 571](https://github.com/NielsdaWheelz/nexus-web/issues/571)
named private dependency build-secret qualification. that source assumption is
retired; [memory delivery](../memory-delivery.md) owns current acceptance.

problem: clean artifact builds and runtime grant separation need current proof.
current `docker/Dockerfile.backend` performs frozen public dependency fetches
without a build secret, through unified dependency stages and `api`, `worker`,
`worker-checkout` targets. current compose is not the old two-private-builder path.

source evidence: nexus's governing llm contract states the library is public;
its dockerfile has no required memory deploy-key mount. current consumer pins
differ from jarvis's october repair pins. prior compose-secret checks and image
scans qualify only the artifacts recorded on 2026-10-09/13.

resolved when: anonymous clean frozen fetch/build of selected current targets and
actual compose consumers succeeds; resulting images/installed packages match the
selected source and locks; runtime configuration proves only authorized consumers
receive the private memory declaration/grants. automated helpers receive no memory
tools. inspect layers/output/runtime configuration for credential leakage using
task-owned values. public build access is not corpus access. record image digests
and installed dependency identities; do not restore retired build-key plumbing.
start no installed service merely to qualify image construction. new probes are
temporary; installed private client access has its own live receipt.

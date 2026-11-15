# nexus deployment-platform image qualification

status: current anonymous linux/arm64 builds and runtime inspection pass,
2026-11-14; deployment-platform build and installed access pending.

problem: this macbook's successful arm64 image proof does not qualify an amd64
release on the intended host. the local amd64 attempt failed with `exec format
error`; no emulation was installed and no remote docker service was started.

source/evidence: [current integration record](../universal-memory.md#memory-completion-source-qualification)
records nexus `12f74c865eb289e186ff33b310f8d34a28c9220d`, the three exact local
image ids, frozen packages, actual compose consumers and credential scans.
anonymous no-cache api/worker/worker-checkout builds pass; 51 raw/decompressed
layer files, build output and environments contain no task memory credentials.
worker-checkout contains locked dependencies and deliberately mounts application
source. api/interactive receive only the client file; background only the upload
file. automated helpers/native hosts receive neither.

resolved when: build the selected source/lock on the actual deployment
architecture, record image digests/installed identities, and verify current compose
with the intended private files under the owning stopped release procedure.
run the [installed client/capture smoke](nexus-memory-client.md) separately.
current public dependency fetch requires no build key; do not restore retired
private-build-secret plumbing. source checks authorize no service activation.

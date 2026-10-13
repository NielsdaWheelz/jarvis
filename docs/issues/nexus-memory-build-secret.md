# local nexus worker builds omit the private dependency secret

priority: p2. reviewed 2026-10-11 against nexus-web `39dfa9456`.

problem: `docker/Dockerfile.backend:17` and `:28` require the build secret
`universal_memory_deploy_key`, but both worker targets in
`docker/docker-compose.worker.yml:9` supply only build arguments. no compose
build-secret mapping or top-level secret declaration exists.

impact: the documented clean local worker build cannot install the private memory
dependency. having the owner's key available does not make compose mount it.
production ci supplies its build secret correctly; this finding concerns local
compose.

evidence/reproduce: parse the compose file: both build secret sets are empty;
the dockerfile has two required mounts. the local path documented in
`apps/worker/README.md:39` invokes `docker compose ... up`; compose cannot inherit
the separate `docker build --secret` flag documented for manual builds. an actual
credentialed build was not run.

still present in inspected source at nexus `82eb4bab`; no credentialed build ran.
planned repair: [local build contract](../memory-repairs.md#nexus-client-and-local-build-contract).

resolved when: both compose worker builds receive the existing secret through
the build-only secret mechanism and a clean local build succeeds. keep credentials
out of build arguments, image layers and runtime containers.

# adr 0095 git pins block a fresh release install

the all-unit candidate at `bc47458` rehearsed with local git bundles. on
2026-11-23, a shallow fetch into a fresh bare repository returned
`upload-pack: not our ref` for three exact `uv.lock` pins from their declared
github remotes:

- `llm-agent-kernel` `5a699212a0d32ba5316c92cf1260d08a35a3dbed`
- `llm-tools` `37b7688381161d398b8094795d43bb7c87ca1885`
- `universal-memory` `c54aea0fe7f43a7fefc0fc020a741d14f897c154`

the same check fetched `provider-runtime` at `76a95bd`. the production
installer runs `uv sync --frozen` and requires a clean source checkout.
this blocks a reproducible release and leaves the source qualification intact.

make the qualified commits reachable from the declared remotes. close after
a fresh fetch of all four pins and a successful frozen candidate install
through the existing release installer.

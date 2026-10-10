# private memory dependency build access

status: private repository published and process-scoped build paths qualified,
2026-10-09; installed build credentials remain separate.

accepted visibility: the repository stays private while nexus's backend images
remain public, including installed library python source. the owner approved
that distribution boundary explicitly; no image has been published in this work.

problem: the new `NielsdaWheelz/universal-memory` repository is private. the three
existing upstream dependencies are public, so existing jarvis/nexus build paths
have no explicit cross-repository read credential.

impact: a final immutable pin can pass on an authenticated development machine
while clean ci or deployment builders cannot fetch it. source qualification alone
cannot establish installed build access.

evidence: the repository is private at immutable commit
`d824d33df9c136952f1d01f7c4a4ad389df42ef1`. authenticated frozen local installs
resolve all four pins. the actual nexus dockerfile's api and worker builder
stages fetch that commit through a required buildkit secret mount. positive
controls find the installed private package/source; scans find no token or its
http basic encoding in image layers/history, wheels, uv git cache, exported
build cache or build logs. the isolated builder and secret file are removed.
jarvis/nexus ci source wiring uses the same exact-path process-scoped helper;
jarvis's installer checks ordinary builder git access before candidate pruning.
no actual ci secret installation, production build or image publication ran.

resolution: use a build-only credential scoped to library contents read. keep it
out of images, build arguments, runtime configuration, logs and model context.
wire existing ci and build mechanisms; provision the actual secret separately.
ordinary local builds and the stopped jarvis builder use authenticated git. the
installer verifies that builder's access before candidate pruning. ci uses the
existing secret mechanism; nexus uses a buildkit secret mount. no package mirror
or new service.

resolved when: clean jarvis/nexus ci and the stopped deployment builder fetch the
exact private commit using installed scoped credentials. record those checks
separately from local authenticated builds and production activation.

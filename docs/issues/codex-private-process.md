# own codex process

problem: jarvis's cognition reaches codex only through the devbox's shared app
servers (`codex-shared@*`, run as `niels`), attached by `provider-runtime`
through `CODEX_APP_SERVER_SOCKET`. adr 0041 chose sharing so the `codex.*`
tools could steer worker threads on the owner's personal server; adr 0044 and
0048 moved worker control to skid and herdr, so jarvis is now the servers' only
client and the sharing serves nothing else.

impact: dev-server keeps a cross-user service, its socket-permission
machinery and a codex pin (dev-server `docs/issues/codex-daemon-socket.md`)
for one client. codex 0.156 already broke that transport; each codex release
can break it again.

direction: jarvis runs its own `codex app-server` child, as `jarvis`, over
stdio, with its own `CODEX_HOME` logged in once by device auth. that home is
jarvis's credential; it never reads the owner's account homes. needs a
private-process codex transport in `provider-runtime` (removed by adr 0041),
jarvis settings and `verify-containment` rewritten for the new boundary, an adr
superseding 0041's transport decision, and isolated qualification of a paid
decision and the live catalog.

resolved when: installed jarvis serves and passes `check-activation` with the
devbox's `codex-shared@*` services absent, and dev-server has deleted them and
the codex pin.

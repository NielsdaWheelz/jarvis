# herdr gate activation

problem: the [adr 0049](../decisions/0049-drive-herdr-through-an-ssh-gate.md)
codec is active and every host's gate answers, but no codex or claude agent has
yet been driven through a real host's gate by jarvis's own identity.

impact: first use on devbox, macbook and arch is observed, not qualified: linux ssh and sshd behaviour, the owner's interactive aliases adding
`--yolo` and `--dangerously-skip-permissions`, the respecting `codex` wrapper and
real trust menus are unproven through the gate.

evidence (2026-09-24): the codec, tools, history decoding, stale-turn check and
the gate probes of `deploy/verify-containment` passed on darwin through a
user-level `sshd`, the dev-server gate verbatim, a disposable herdr 0.9.1 server
and a disposable postgres (the adr's proof); the scaffolding is deleted. never
exercised: `verify-containment` on linux (its `systemd-run` unit and the checks
before the gate probes), a stop
whose close herdr refuses or whose pane vanishes after the interrupt, and herdr's
exit-2 usage path.

2026-09-24 cutover: dev-server step 1 applied in the stopped window (key
bootstrap `d9767a6`); gates proven as jarvis on devbox and macbook (`agent
list` answers, `status --json` refused); `39d9c9c` activated with every count
zero; `JARVIS_GATE_MACHINES='devbox macbook' deploy/verify-containment` passed,
again after skid v0.8.0 and herdr's integrations; owner `resume`.

arch (2026-09-24, after its reboot): applied; `deploy/verify-containment`
passes with all three machines.

resolved when the [herdr gate cutover](../operations.md#herdr-gate-cutover-pr-5)
completes with `verify-containment` passing on all three hosts, and one
owner-directed journey starts, reads, prompts, interrupts and stops a codex and a
claude agent on each host through the gate, recorded with versions and verdicts
only (never prompts, terminal bytes or credentials).

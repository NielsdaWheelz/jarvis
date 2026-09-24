# herdr gate activation

problem: the [adr 0049](../decisions/0049-drive-herdr-through-an-ssh-gate.md)
codec is not active. production still runs the skid cli release, and no codex or
claude agent has been driven through a real host's gate by jarvis's own identity.

impact: until the cutover, skid pr 5 cannot delete the cli (its delivery step 4
waits on this). after it, first use on devbox, macbook and arch is observed, not
qualified: linux ssh and sshd behaviour, the owner's interactive aliases adding
`--yolo` and `--dangerously-skip-permissions`, the respecting `codex` wrapper and
real trust menus are unproven through the gate.

evidence (2026-09-24): the codec, tools, history decoding and deploy checks
passed on darwin through a user-level `sshd`, the dev-server gate verbatim and a
disposable herdr 0.9.1 server (the adr's proof); the scaffolding is deleted.
never exercised live: a stop whose close herdr refuses or whose pane vanishes
after the interrupt, a read above 32 kib, and herdr's exit-2 usage path.

known blockers: dev-server pr 5 step 1 applied on all three hosts with jarvis's
key committed as `assets/herdr/jarvis-gate.pub`; arch reachable, since
`verify-containment` probes every gate.

resolved when the [herdr gate cutover](../operations.md#herdr-gate-cutover-pr-5)
completes with `verify-containment` passing, and one owner-directed journey
starts, reads, prompts, interrupts and stops a codex and a claude agent on each
host through the gate, recorded with versions and verdicts only (never prompts,
terminal bytes or credentials).

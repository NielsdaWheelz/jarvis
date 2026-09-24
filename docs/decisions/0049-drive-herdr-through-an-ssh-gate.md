# adr 0049: drive herdr through an ssh gate

- status: accepted implementation target, 2026-09-24; production activation
  `NOT_RUN`.
- authority: the owner approved skid's
  [herdr pr 5 specification](https://github.com/NielsdaWheelz/skidbladnir/blob/main/docs/herdr-pr5.md)
  (skid `424ce32`, §5 "jarvis over herdr"), including the owner decisions
  "agents plus pane creation" for the allowlist, per-host gates, and no
  `--machine`. jarvis baseline `3dc3590`.
- supersedes: adr 0044's transport (installed skid executable, private client
  config, one cli process per operation); adr 0045's ordinary cli argv,
  cli-owned references and cli projection; adr 0048's skid envelope and
  exit-status codec, cli refs, `--terminal` send mode, skid status/readiness
  projection, fleet-`list` preflight and its partial shapes. their nine-tool
  roster, provider policy, write grounding, `BilledOnce` single entry,
  non-replay, uncertainty wrapper, closure-scope disclosure, bounds and
  immutable history remain.
- preserves: six tables, serial cognition, recorders, gate isolation and adr
  0046's reset.

## evidence and decision

herdr 0.9.1 already owns what the skid cli wrapped for jarvis: agent detection
and lifecycle (`agent start/get/read/prompt/send-keys`), never-repeated terminal
ids, a blocked-agent refusal before any prompt, and an api envelope defined by
`herdr api schema`. pr 5 deletes the skid cli, peer client and hooks, so jarvis must
switch before they disappear. `--machine` runs `sh` probes and a bridge over
several ssh sessions that a forced command would break, and adds nothing when
the gate already runs herdr on the target.

transport. each call is one `/usr/bin/ssh -F /etc/jarvis-herdr/ssh_config
<label> <shlex-joined argv>` child, environment `PATH=/usr/bin:/bin` only, closed
stdin, bounded stdout and stderr, a joined command of at most 64 kib (sshd hands
it to the gate as one environment string) and a 10-second clock, plus herdr's
15-second readiness wait for `agent start`. dev-server owns
`/etc/jarvis-herdr` (the key, `ssh_config`, `known_hosts`) and installs the gate
in each owner account behind `restrict,command=`. the gate splits the command
without a shell and execs the host's pinned herdr only for this allowlist, whose
content jarvis owns:

| purpose | herdr commands | jarvis emits |
| --- | --- | --- |
| inventory | `agent list`, `agent get`, `pane list`, `workspace list` | all but `workspace list` |
| observe | `agent read`, `agent explain`, `agent wait` | `agent read --source recent\|visible --lines N` |
| create | `workspace create --cwd --label --env`, `pane split --env`, `agent start --kind codex\|claude --pane --timeout` | `workspace create`, then `agent start` on its new pane |
| drive | `agent prompt [--wait --until --timeout]`, `agent send-keys` | `agent prompt NAME TEXT`, `agent send-keys NAME KEY...` |
| end | `pane close` | `pane close PANE` |

`--env` admits only `CODEX_HOME` at the owner's `.codex`, `.codex-work` or
`.codex-work2` and `CLAUDE_CONFIG_DIR` at `.claude-work`. excluded: `pane run`,
`pane send-text`, `pane wait-output`, `--`, herdr's global options, and every
server, config, machine, integration, update, worktree, plugin and notification
command. the gate refuses with exit 1 and one content-free line before herdr
runs. the gate admits any pane id, so ownership is jarvis's rule: `start` creates
its own workspace and starts an agent only in that new pane.

decoding. exit 0 is `{id, result:{type, …}}` whose `type` must be the command's
own (plain text for `agent read`, of which a rolling tail is kept); unknown fields
are ignored, as herdr asks. on exit 1 only stderr's last line counts, since ssh's
own diagnostics come first: the gate's exact refusal line is
`gate_refused/not_sent`, and herdr's `{id, error:{code, message}}` is that code.
it is `not_sent` for the codes herdr 0.9.1 raises before writing, typing,
creating or closing anything, read from its source: `server_not_running` and
`protocol_mismatch` (the cli, before any request), `agent_not_found`,
`agent_target_ambiguous`, `agent_not_ready`, `agent_blocked`,
`empty_agent_prompt` and `invalid_key` (prompt and send-keys,
`src/app/api/agents.rs`), `invalid_env` (workspace create) and `pane_not_found`
and `confirmation_required` (pane close, `src/app/api/panes.rs`); any other
herdr error to a write is `sent`. `agent start` is excluded: its cli keeps
polling after it typed the command, and that wait can end in `agent_not_ready`
(a blocked startup), `server_not_running` or `protocol_mismatch`
(`src/cli/agent.rs`, the post-typing wait and its transport errors), with the
workspace already created, so start forces every error to `sent` with the
created terminal. exit 2 is `usage/not_sent`; anything else, a
timeout, or an oversized or malformed reply is a lost reply.

references. jarvis encodes the machine and `terminal_id` (plus herdr's agent
name for an agent ref) as unpadded base64url of canonical json: opaque to the
model, deterministic so equality is identity. the pr 5 specification lists the
pane id among a reference's parts; it is left out because a pane id is a
location: herdr changes it when a pane moves between workspaces and reissues it
after a restart, while a `terminal_id` is never repeated and herdr's own `agent
start` pins it. herdr clears a name when its agent exits or is replaced. every
addressed call first re-reads its target (`agent get NAME`, or one machine scan
finding the pane that holds a terminal ref's `terminal_id`) and requires the same
name and `terminal_id`; writes go to the name or that current pane. an exit, a
restart, a start under the name elsewhere or a closed pane fails that check
before dispatch. it cannot catch an agent started again by hand under the same
name in the same terminal: name and `terminal_id` both survive, and herdr exposes
nothing that tells the two apart. the check/write race stays accepted.

the gate's view. send, keys, interrupt and stop take the machine and agent name
from the ref itself, with no i/o; the executor's check is the guard, so a stale
agent ref passes the gate and fails `stale_reference/not_sent` in the executor.
kill's terminal ref names neither agent nor pane, so the dispatcher runs one
machine scan for the pane that holds the terminal and the name of any agent
there; a stale terminal ref fails there and creates no action. the gate loses
only the pane for agent-ref writes, which owners name by agent, not pane.

tools. list scans each machine (`pane list`, `agent list`) concurrently; an
unreachable machine is an error entry and makes the inventory partial. info is
one scan; read keeps a rolling tail of `agent read` and returns its last 32 kib,
`truncated` when anything was dropped; start checks the name is free, creates a
workspace labelled with it and carrying the profile's account home, then `agent
start --timeout 15000` on that pane, and requires herdr's reply to name the same
agent and terminal (`start_mismatch/sent` otherwise); send is `agent prompt`, whose blocked
refusal replaces jarvis's readiness gate and the terminal-mode bypass; keys and
interrupt are `send-keys` (interrupt is `ctrl+c`); stop is interrupt, find the
pane that holds the terminal now, `pane close`; kill is `pane close` on that
current pane. profiles (`personal`, `work`, `work2`,
`claude-work`) are part of the tool contract; machine labels and each host's
owner home are explicit settings (`JARVIS_HERDR_MACHINES`), never guessed.

settlement. a herdr error to a write settles `failed` with the dispatch above;
`sent` does not prove no effect. a check, gate or local refusal settles
`failed/not_sent`. a partial effect is staged as `agent_control_v3` the moment
herdr confirms it, not when the tool ends: start's created terminal right after
`workspace create`, stop's interrupt, as `{interrupt: sent, terminal:
unconfirmed}`, right after `send-keys`. a later failure settles with its own
partial; a lost reply, a deadline or a crash after that point settles `uncertain`
with what was staged, inside the existing `agent_uncertainty_v1` wrapper. nothing
replays.

## cutover and proof

bindings move to `jarvis-agent-control-v5` with policy epoch
`jarvis-agent-control-v3`; the main and gate role contract revisions rotate
(`jarvis-main-herdr-gate-v1`, `jarvis-write-gate-herdr-gate-v1`) and the gate's
effect target names the pane instead of the opaque ref. the plan rotation makes
every pending action incompatible, so the
[herdr gate cutover](../operations.md#herdr-gate-cutover-pr-5) activates only at
zero. the kernel resumes a turn only under its recorded definition and plan and
parks any other, which opens the cognitive circuit, so `check-activation` also
counts stale turns (unprocessed, unparked inputs of jarvis's own thread, the
configured channel, whose recorded main decisions carry another definition or
plan) and refuses unless there are none; tolerating
old observation shapes on restore would not help, since the recorded authority
check rejects the turn anyway. v4 receipts decode through `agent_history.py`.
forward only: the previous release needs the skid cli, which pr 5 removes last.
`verify-containment` probes every listed gate as jarvis, in a transient unit that
copies only the service properties deciding what ssh reads and reaches (user and
group, `ProtectHome`, `ProtectSystem`, `PrivateTmp`, `PrivateDevices`,
`NoNewPrivileges`, `RestrictAddressFamilies`): an allowed read, a refused
command, and refused `ssh -W` and `-R` forwarding, which proves `restrict`.

proof ran on darwin through a user-level `sshd` with its own host key, the
dev-server gate verbatim behind `restrict,command=`, and a disposable herdr
0.9.1 server under `/private/tmp`, driving the real controller: codex and claude
starts per profile with the pane's account home reaching the agent, list, info,
read, send (accepted on codex's sign-in screen, herdr's documented misread), keys,
interrupt, stop, kill, stale refs after exit, name reuse and a herdr restart (the
same pane id returned with a new `terminal_id` and survived every stale write), a
pane moved to another workspace (new pane id, same refs, stopped by them), a
partial inventory with an unreachable machine, non-allowlisted commands refused,
a failed start with its staged terminal, a start whose reply names another
terminal, a lost start reply that had staged its terminal and still produced the
agent, the stop interrupt staged on success, a read above 32 kib kept as a tail,
herdr down (`server_not_running`, not sent), refusal codes mapped to not sent, a
forged ref naming an unconfigured machine refused before any ssh, and the known
gap (a hand-started agent of the same name in the same terminal passed the old
ref's check). `verify-containment` ran through its real outer ssh transport into a stand-in
deploy account on the same sshd, with its probe section byte for byte and `sudo`
and `systemd-run` as pass-through stand-ins (no systemd on darwin; the root-only
checks before the probes were left out): every listed label was probed, and an
unreachable host, a gate key without `restrict` and a malformed label each
failed it; the previous version probed only the first label. both stale-turn queries ran on a
disposable migrated postgres, scoped to jarvis's thread. the scaffolding was deleted under adr 0046;
production activation and the linux hosts are `NOT_RUN`.

costs: one ssh handshake per call and no connection reuse, so send, keys and
interrupt cost two calls, kill five and stop five; a stale agent ref costs a gate
decision and a failed action instead of none; herdr's readiness is trusted as is,
including its misreads; an agent herdr detected without a name is reachable only
as a terminal, and a hand-restarted agent of the same name in the same terminal
inherits old refs; interrupt is `ctrl+c` for codex too, where a second one quits
an idle session; `agent read` loses herdr's own truncation flag, and jarvis's
covers only its own cut; prompt text travels in argv, visible in process listings
on devbox and the target; the gate refuses a prompt equal to `--` or a herdr
global option; the not-sent codes are read from herdr 0.9.1's source, so a herdr
pin change requalifies this codec and the gate together.

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
own (plain text for `agent read`); unknown fields are ignored, as herdr asks. the
gate's exact refusal line is `gate_refused/not_sent`; herdr's `{id,
error:{code, message}}` on stderr with exit 1 is that code, `sent`; exit 2 is
`usage/not_sent`; anything else, a timeout, or an oversized or malformed reply is
a lost reply.

references. jarvis encodes the machine and `terminal_id` (plus herdr's agent
name for an agent ref) as unpadded base64url of canonical json: opaque to the
model, deterministic so equality is identity. the pr 5 specification lists the
pane id among a reference's parts; it is left out because a pane id is a
location: herdr changes it when a pane moves between workspaces and reissues it
after a restart, while a `terminal_id` is never repeated and herdr's own `agent
start` pins it. herdr clears a name when its agent exits or is replaced. every
addressed call first re-reads its target (`agent get NAME`, or one machine scan
finding the pane that holds a terminal ref's `terminal_id`) and requires the same
name and `terminal_id`; writes go to the name or that current pane. the
dispatcher runs the same check before the gate, and the executor again just
before the write. a changed target fails before dispatch; the check/write race
stays accepted.

tools. list scans each machine (`pane list`, `agent list`) concurrently; an
unreachable machine is an error entry and makes the inventory partial. info is
one scan; read is the last 32 kib of `agent read`; start checks the name is free,
creates a workspace labelled with it and carrying the profile's account home,
then `agent start --timeout 15000`; send is `agent prompt`, whose blocked
refusal replaces jarvis's readiness gate and the terminal-mode bypass; keys and
interrupt are `send-keys` (interrupt is `ctrl+c`); stop is interrupt, find the
pane that holds the terminal now, `pane close`; kill is `pane close` on that
current pane. profiles (`personal`, `work`, `work2`,
`claude-work`) are part of the tool contract; machine labels and each host's
owner home are explicit settings (`JARVIS_HERDR_MACHINES`), never guessed.

settlement. herdr's error reply settles `failed/sent`, which does not prove no
effect; a check, gate or local refusal settles `failed/not_sent`. start's created
terminal and stop's sent interrupt are staged as `agent_control_v3` before their
failure settles; a lost reply after the mutating command started, or an
unconfirmed close, settles `uncertain` with that prefix in the existing
`agent_uncertainty_v1` wrapper. nothing replays.

## cutover and proof

bindings move to `jarvis-agent-control-v5` with policy epoch
`jarvis-agent-control-v3`; the main and gate role contract revisions rotate
(`jarvis-main-herdr-gate-v1`, `jarvis-write-gate-herdr-gate-v1`) and the gate's
effect target names the pane instead of the opaque ref. the plan rotation makes
every pending action incompatible, so the
[herdr gate cutover](../operations.md#herdr-gate-cutover-pr-5) activates only at
zero. v4 receipts decode through `agent_history.py`. forward only: the previous
release needs the skid cli, which pr 5 removes last.

proof ran on darwin through a user-level `sshd` with its own host key, the
dev-server gate verbatim behind `restrict,command=`, and a disposable herdr
0.9.1 server under `/private/tmp`, driving the real controller: codex and claude
starts per profile with the pane's account home reaching the agent, list, info,
read, send (accepted on codex's sign-in screen, herdr's documented misread), keys,
interrupt, stop, kill, stale refs after exit, name reuse and a herdr restart (the
same pane id returned with a new `terminal_id` and survived every stale write), a
pane moved to another workspace (new pane id, same refs, stopped by them), a
partial inventory with an unreachable machine, non-allowlisted commands refused,
a failed start with its staged terminal, and a lost start reply that staged its
terminal and still produced the agent. the scaffolding was deleted under adr
0046; production activation and the linux hosts are `NOT_RUN`.

costs: one ssh handshake per call and no connection reuse, so with the preflight
and executor checks send, keys and interrupt cost three calls, kill five and stop
six; herdr's readiness is trusted as is, including its misreads; an agent herdr
detected without a name is reachable only as a terminal; interrupt is `ctrl+c`
for codex too, where a second one quits an idle session; `agent read` loses
herdr's own truncation flag; the gate refuses a prompt equal to `--` or a herdr
global option; a herdr pin change requalifies this codec and the gate together.

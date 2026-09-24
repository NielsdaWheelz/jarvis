# adr 0044: control tmux agents through skid

- status: accepted 2026-09-12; cli grammar, target inputs and roster superseded by [adr 0045](0045-use-the-ordinary-fleet-cli.md); native observation/halt, single-session closure, blanket partial-stop uncertainty and 64 kib bounds superseded by [adr 0048](0048-align-with-the-herdr-fleet-cli.md); the skid cli transport superseded by [adr 0049](0049-drive-herdr-through-an-ssh-gate.md).
- authority: the owner approved the cross-repository agent-control spec and its implementation.
- supersedes: adr 0041's five devbox-only codex tools, dedicated terminal launcher,
  worker directory policy, and human-only worker permission responses.
- preserves: cognition containment, six tables, kernel serialization, action
  recording, write grounding, and non-replay after uncertain dispatch.

## decision

use the installed skid cli for all worker operations. its seven verbs are
`agent.list/read/start/send/keys/interrupt/stop`. each configured computer is a
direct peer. codex and claude tmux sessions are ordinary targets; coordinator is
a prompt, not a role. cognition outside tmux is naturally outside inventory.

invoke an absolute executable with an explicit private client-config path and
one json stdin object. never use a shell, direct native worker routing, ssh, or
a second fleet http client. the gateway selects host credentials and validates
the exact tmux/pane/process lifetime. list/start select a configured machine
label; subsequent operations echo the returned machine-bound target.

start creates a terminal using an existing host profile and cwd; it sends no
prompt and promises no readiness. list/read again before send. the 2026-09-13
owner amendment keeps codex terminal-only and claude-work as the sole claude
launch profile. claude retains native status/history/stop; conversational input
and interrupt use terminal control for both providers. terminal observations
have explicit source and bounded coverage.
the operator may answer permission dialogs through explicit terminal input.
worker output adds no jarvis authority.

reads use the existing read recorder. writes remain single-entry billed-once
actions. a child timeout, lost reply, unknown write outcome, or partial stop
never authorizes replay. stop retains separate provider-halt and terminal-close
outcomes. cancellation of the cli does not cancel remote work.

the cli returns exactly `{ok:true,result}` or
`{ok:false,error:{code,dispatch:not_sent|unknown}}` with exit 0/1.
bound stdin/control output to 64 kib, list output to 1 mib, elapsed time to
15 seconds; suppress stderr rather than recording prompts/provider content.

retain codex host configuration needed by cognition. remove obsolete worker
launchers only after the final caller is gone. no new database table, task
schema, ownership graph, scheduler, transcript store, or privilege framework.
the canonical cross-repository wire contract is skid's `docs/agent-control.md`.
existing `codex_uncertainty_v1` action results retain a narrow read-only decoder.
the execution/catalog cut does not rewrite or make canonical history unreadable.

the 2026-09-13 acceptance correction uses the existing `AgentFailure` schema
for pre-action write checks: `policy_denied` for a completed denial or absent
owner input, `write_check_unavailable` for an unavailable preflight or failed
gate, always `dispatch=not_sent`. other connectors retain their common error
contracts. diagnostics retain only stage/outcome/exception class and control
identifiers. authorization, replay rules, and execution budgets are unchanged.

## acceptance and costs

hermetic boundary tests cover the exact catalog, structured stdin/argv, direct
remote targets, bounds, partial outcomes, and no replay after lost dispatch.
an approved live journey covers remote codex and claude, including an ordinary
target using the same cli to manage another agent. absent live proof is not a pass.

costs: dependency on installed skid/config, manual bearer redistribution,
sampled status, partial history, and shared human/agent input. there is no
offline queue, automatic completion callback, or exclusive writer.

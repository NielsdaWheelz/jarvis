# adr 0050: separate herdr worker provider homes

- status: accepted by the owner in the 2026-09-25 herdr-mobile separation scope;
  fleet activation remains not run.
- authority: `skidbladnir/docs/herdr-mobile-separation.md` section 5 in the
  herdr-backed source repository before its github rename.
- supersedes: only adr 0049's four worker account-home paths. its tool roster,
  profile names, ssh gate, authority, revisions, receipts, and action accounting
  remain binding.

## decision

jarvis's four worker profiles select private interactive homes under each
configured host owner's `~/.local/share/herdr/providers/`:

| profile | environment |
| --- | --- |
| `personal` | `CODEX_HOME=.../codex-personal` |
| `work` | `CODEX_HOME=.../codex-work` |
| `work2` | `CODEX_HOME=.../codex-work2` |
| `claude-work` | `CLAUDE_CONFIG_DIR=.../claude-work` |

`...` is that host's absolute owner-home prefix plus
`.local/share/herdr/providers`. the current dev-server `assets/herdr/herdr-gate`
admits these homes. its fifth home, `claude-personal`, is herdr's shell default;
jarvis has no fifth worker profile. jarvis's separate cognition account-home
declaration and services do not move.

`AGENT_PROFILES` is serialized into every agent binding's `policy_inputs`, so
this map change rotates the binding policy identity. the implementation revision
and policy epoch remain as adr 0049 defines: no input schema, result shape,
execution logic, or receipt format changes. before activation, the operator
must settle or explicitly resolve pending incompatible agent actions under the
existing cutover rules; a policy mismatch cannot authorize replay. no live
worker, provider home, service, or credential is changed by this source edit.

## evidence and remaining proof

source inspection found the four old paths in `agent_tools.py` and spec section
7.3; `agent_control.py` already joins the table entry to the configured owner
home, and dev-server's gate already admits the five new private paths. static
verification is a build check. provider login, trust, host gate activation,
worker launch, and runtime isolation remain not run until the coordinated
fleet cutover.

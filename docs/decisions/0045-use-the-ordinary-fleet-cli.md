# adr 0045: use the ordinary fleet cli

- status: accepted implementation target, 2026-09-13; live acceptance pending; `info` preflight, session projection and blanket partial-stop uncertainty superseded by [adr 0048](0048-align-with-the-herdr-fleet-cli.md); cli argv, cli refs and projection superseded by [adr 0049](0049-drive-herdr-through-an-ssh-gate.md).
- authority: owner approved skid's `docs/agent-control-ux.md` implementation.
- supersedes: adr 0044's json-stdin cli grammar, structured target inputs, and seven-tool roster.
- preserves: direct peers, provider policy, write grounding, non-replay, cognition, kernel, budgets, and immutable history.

## evidence and decision

the shipped interface required callers to assemble six identity fields and pipe
json. normal owner requests could not be grounded usefully by an opaque identifier
alone. the owner requested ordinary commands, agent discoverability, and terminal
closure independent of provider halt.

use the installed cli's normal commands plus `--json`. share its session projection
and opaque refs with humans and the tui; remove jarvis's duplicate projection.
add `agent.info` for one-session observation and `agent.kill` for terminal closure.
start sends no prompt and does not wait for readiness. info may observe a new agent;
no mutation follows a refreshed ref implicitly.

one metadata-only `info --ref` at the existing write-preparation boundary supplies
name and machine label to existing effect-target fields. the submitted ref remains
the persisted and executed target. missing owner input denies before lookup;
failed lookup creates no action. this is not a second worker client or authority
source. all normal write gating and uncertainty semantics remain.

parse success envelopes before exit status: partial fleet inventory remains a
read observation; partial stop remains recorded uncertainty. keep one write attempt
and all existing run budgets. use stdin only for literal send text; suppress stderr.

## cutover and proof

drain old agent actions, stage matching cli/jarvis, then switch callers together.
retain bounded immutable receipt rendering; never retain old execution grammar.
prove ordinary-name owner requests, complete tool/argv mapping, literal multiline
input, metadata failure before mutation, preservation of the original effect ref,
partial outcomes, and no replay. native/live absence is NOT_RUN, never a pass.

costs: one bounded metadata read per addressed write, manually provisioned peers,
new-session instruction discovery, shared run budgets, and coordinated hard cutover.

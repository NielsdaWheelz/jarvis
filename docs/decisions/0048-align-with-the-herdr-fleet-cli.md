# adr 0048: align with the herdr fleet cli

- status: accepted implementation target, 2026-09-23; live acceptance `NOT_RUN`;
  its skid cli codec, refs, send mode and preflight superseded by
  [adr 0049](0049-drive-herdr-through-an-ssh-gate.md).
- authority: the owner approved skid's herdr migration and its
  [pr 3 specification](https://github.com/NielsdaWheelz/skidbladnir/blob/main/docs/herdr-pr3.md)
  (skid `99990332cfcbb713a741e37519548c7e674a46db`, merged pr 134; jarvis baseline
  `667a377528c659b685ff83de5755f9008adfe443`).
- supersedes: adr 0044's native claude observation/halt, single-session closure
  and 64 kib control bounds; adr 0045's `info`-based write preflight, session
  projection and old status/stop variants; both adrs' blanket partial-stop
  uncertainty (a known stop prefix with `sent` now settles failed; only unknown
  dispatch or a contradictory pair stays uncertain); and adr 0038's
  calendar-specific silent fallback body, which becomes the generic
  "I couldn't produce a complete answer." because fleet incompleteness shares it.
  their nine-tool roster, direct peers, provider policy, write grounding,
  non-replay, budgets and immutable history remain.
- preserves: six tables, serial cognition, `BilledOnce` single entry, the
  existing uncertainty wrapper, recorders, gate isolation and adr 0046's reset.

## evidence and decision

skid replaced tmux with the herdr runtime. the merged cli now returns
terminals with separate terminal and agent refs, herdr-sourced status with
explicit readiness, `dispatch` on every mutation, closed partial prefixes for
start/stop/kill, and a fleet inventory whose `partial` flag also covers a
reachable host with unaddressable resources. the old consumer decodes none of
this; a compatibility mode would only hide the difference.

decode the actual envelopes: `{ok:true,result}` or
`{ok:false,error:{code,message,dispatch?},partial?}`, optionally with outer
`label,machine`, before interpreting exit status 0/1/2. omitted dispatch is
`unknown`. keep exactly nine `agent.*` tools with the cli's argv: `list`,
`info --ref`, `start --machine --profile --cwd -- NAME`, `read --ref --coverage
--max-bytes`, `send --ref --stdin [--terminal]`, `keys --ref KEY...`,
`interrupt/stop/kill --ref`. info and kill take terminal refs; read, send, keys,
interrupt and stop take agent refs; refs stay opaque and are never derived from
one another. `read --terminal`, the read `mode` input and page keys are removed.

preflight moves from `info` to exact original-target proof: send/keys/interrupt/
stop run one bounded fleet `list` and require exactly one terminal whose current
agent ref equals the submitted ref; kill runs one `info` on the terminal ref and
requires the same ref back. only the peer label, an optional product name and
the original ref enter the gate. no match, several matches, invalid output or
lookup failure is `write_check_unavailable/not_sent` with no action; a positive
exact match is usable while unrelated peers are unavailable. the descriptor adds
`closure_scope: native_linked_workspace_group_may_close` for stop/kill; the gate
denies an owner restriction that a possible cascade could violate.

settlement uses the envelope, never one partial field: a `not_sent` or `sent`
failure is `failed` with its code, dispatch and partial facts retained; an
`unknown` dispatch, an unknown write outcome, or a malformed, oversized, lost or
timed-out reply after child start is `uncertain` with every validated prefix
staged as `agent_control_v2` evidence inside the existing `agent_uncertainty_v1`
wrapper; a known partial prefix is staged before its failure settles, so a crash
loses no created terminal or sent interrupt. classification uses the whole
envelope against the set of partials the host emits; a contradictory pair is
uncertain. nothing replays. encoded input and control results rise to 256 kib;
raw send/read stay 32 kib; the fleet reply stays 1 mib and a larger valid reply
makes discovery and preflight unavailable rather than partial. the read-only
fleet list gets a 17-second deadline, two seconds above the cli's own clock,
because that clock starts after argument parsing and a hung peer would otherwise
turn every partial inventory and preflight into `unavailable`; writes keep 15.

historical receipts of the two shipped generations decode only through
`agent_history.py`, selected by the stored execution contract revision. partial
fleet inventory is turn evidence: `answered`/`silent` cannot conceal it, it
composes with calendar incompleteness, and it survives snapshot restoration.

## cutover and proof

bindings move to `jarvis-agent-control-v4` with policy epoch
`jarvis-agent-control-v2`; main and gate role contract revisions rotate. pr 4
must inventory every nonterminal action under the old release, finish or cancel
incompatible ones with lineage preserved, stage matching skid and jarvis, then
switch. source rollback after new receipts exist requires a consumer that can
read them or forward repair; history is never rewritten.

proofs ran through the real controller, dispatcher, recorder and an isolated
postgres against the real merged cli codec and a scripted loopback gateway,
then were deleted under adr 0046. the live codex/claude journey is `NOT_RUN`:
no herdr runtime is installed on the development host, the fleet still serves
the pre-herdr gateway, and the cli accepts only https on 8443.
it ran on 2026-09-24 ([pr 4 qualification](../qualification/2026-09-23-herdr-pr4.md)), and
[the qualification record](../qualification/2026-09-23-herdr-pr3.md) the evidence.

costs: one fleet list per addressed write; 256 kib envelopes inside unchanged
run budgets; deadline loss stays uncertainty; terminal-only evidence; the
accepted check/write race; narrow archival readers; no retained regression suite;
terminal-mode override is main-role discipline rather than a gate fact; decoded
text containing NUL or lone surrogates fails closed, as an unavailable read or
an uncertain write after child start.

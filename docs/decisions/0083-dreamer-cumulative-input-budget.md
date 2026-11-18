# adr 0083: dreamer cumulative input budget

status: accepted, 2026-11-17, by explicit owner choice: "raise only dreamer input
ceiling to 1,000,000". supersedes only the consolidated memory contract's
160,000-token dreamer input ceiling. source and controlled qualification pass;
actual installed quiet completion remains pending.

## evidence

actual installed run `7b3a3c61-a319-4a3b-914e-cea2852da226` reaches the exact
`provider_input_tokens` guard with 241,692 input tokens, 1,094 output tokens,
three provider turns and 40.581 kernel seconds. notes and consumed progress stay
unchanged. earlier incomplete runs retain their original uncertainty.

independent pinned-source audits find no double counting or bootstrap resend.
native cumulative snapshots become turn-local deltas, accumulated once; cached
input is already a subset of reported input. healthy continuations send only new
observations/corrections, while inference naturally rereads native history. the
complete portable host table measures 218,636 bytes; an empty-seed bootstrap is
220,802 bytes. schema inlining and complete tool contracts explain this cost;
changing publication is separate work.

## decision and trade-offs

raise only `DREAMER_KERNEL_LIMITS.max_provider_input_tokens` from 160,000 to
1,000,000 and advance dreamer from v5 to v6. retain personal-subscription
sol/xhigh, ten turns, 300 cooperative seconds, 16,000 output tokens, 327,680
context bytes, eight tool calls, all grants, ready-seed/full-read scope, nightly
policy and atomic completion. add no budget framework or fallback.

the observed average is 80,564 input tokens per turn; ten such turns extrapolate
to 805,640. one million gives roughly 24% headroom over that extrapolation. this is empirical sizing, not a
guarantee that every ten-turn path fits. 320,000 would cover only about four
turns at that average and size the repair around this failure.

the reported-input threshold rises 6.25 times. cached input counts in that
resource number; it is not a monetary bill. enforcement still uses usage reported
after a generation and can overshoot by an in-flight turn. weekly availability
and useful completion remain unguaranteed. every other finite bound stays fixed.

## qualification

use f2's temporary composed-definition/actual-kernel red/green proof against the
measured aggregate usage and the new exact/over-limit boundary. verify unchanged
other limits, instructions, schemas, grants and policies; retain frozen checks,
independent review and one actual stopped fixed-model quiet completion. delete
only new probes after hash receipts. the real journey and final reset remain.

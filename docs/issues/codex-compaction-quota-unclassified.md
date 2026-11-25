# unclassified codex quota failures can park compaction

stock `0.171.0` and `provider-runtime` expose account quota and session-budget failures as `AgentQuotaExhausted`. when an isolated compaction attempt stops with that type and a fresh account read cannot corroborate included exhaustion, the existing invalid-completion path can park the addressed range. a timeout, recovery between reads, or session-budget failure can reach this branch. a parked range blocks the next dependent construction until operator repair.

adr 0108 defers an addressed batch on independently proved included exhaustion. the ambiguous case retains the prior disposition since the underlying failure cause is unknown. opus identified the ambiguous branch during review.

closure requires a pinned terminal cause contract or a separately adopted bounded retry policy. reproduce a quota-shaped stop with an unavailable or recovered observation and a genuine session-budget stop. verify deterministic disposition and unchanged batch bounds. [adr 0108](../decisions/0108-codex-quota-standby.md)
